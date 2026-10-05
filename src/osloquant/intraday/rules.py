"""Signal rules: small pieces of code that look at a stock's bars and say BUY, SELL or nothing.

A rule is asked about the *newest completed bar* of one stock and answers only when something changed on
that bar: a cross, a breakout. So a rule fires once, on the bar it happens, not on every bar afterwards.

Rules are picked by their code in the account's configuration:

    signal: {rule: ma_cross, fast: 5, slow: 20}

Your own rule is a subclass of ``Rule`` and is named by its import path: ``{rule: "my_module:MyRule", ...}``.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

BUY, SELL = "BUY", "SELL"


@dataclass(frozen=True)
class Signal:
    code: str
    rule: str
    #: what happened, in words and numbers, so that the log can be read without the chart
    reason: str
    #: the start of the bar that raised it
    bar: pd.Timestamp
    #: the close of that bar
    price: float


class Rule:
    #: the name the rule goes by in a configuration
    code = ""

    def __init__(self, **params) -> None:
        self.params = params

    @property
    def min_bars(self) -> int:
        """How many completed bars the rule needs before it can say anything."""
        return 2

    def evaluate(self, bars: pd.DataFrame) -> Signal | None:
        """``bars``: the completed bars of one stock, oldest first (open, high, low, close, volume), indexed
        by bar start. Return a signal about the last one, or None."""
        raise NotImplementedError

    def signal(self, code: str, reason: str, bars: pd.DataFrame) -> Signal:
        return Signal(code=code, rule=self.code, reason=reason, bar=bars.index[-1], price=float(bars["close"].iloc[-1]))

    def describe(self) -> str:
        inner = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.code}({inner})"


class MaCross(Rule):
    """BUY when the fast moving average crosses above the slow one, SELL when it crosses below."""

    code = "ma_cross"

    def __init__(self, fast: int = 5, slow: int = 20) -> None:
        if fast >= slow:
            raise ValueError("fast must be shorter than slow")
        super().__init__(fast=fast, slow=slow)
        self.fast, self.slow = fast, slow

    @property
    def min_bars(self) -> int:
        return self.slow + 1

    def evaluate(self, bars: pd.DataFrame) -> Signal | None:
        close = bars["close"].to_numpy()[-(self.slow + 1) :]
        fast_now, slow_now = close[-self.fast :].mean(), close[-self.slow :].mean()
        fast_before, slow_before = close[-self.fast - 1 : -1].mean(), close[:-1].mean()
        if fast_before <= slow_before and fast_now > slow_now:
            return self.signal(BUY, f"ma{self.fast} {fast_now:.2f} crossed above ma{self.slow} {slow_now:.2f}", bars)
        if fast_before >= slow_before and fast_now < slow_now:
            return self.signal(SELL, f"ma{self.fast} {fast_now:.2f} crossed below ma{self.slow} {slow_now:.2f}", bars)
        return None


class Breakout(Rule):
    """BUY when the close breaks above the highest high of the previous ``lookback`` bars, SELL when it breaks
    below their lowest low. Only on the bar of the break, not while the price stays out there."""

    code = "breakout"

    def __init__(self, lookback: int = 20) -> None:
        super().__init__(lookback=lookback)
        self.lookback = lookback

    @property
    def min_bars(self) -> int:
        return self.lookback + 2

    def evaluate(self, bars: pd.DataFrame) -> Signal | None:
        n = self.lookback
        high, low, close = (bars[c].to_numpy()[-(n + 2) :] for c in ("high", "low", "close"))
        ceiling, floor = high[-n - 1 : -1].max(), low[-n - 1 : -1].min()
        ceiling_before, floor_before = high[-n - 2 : -2].max(), low[-n - 2 : -2].min()
        if close[-1] > ceiling and close[-2] <= ceiling_before:
            return self.signal(BUY, f"close {close[-1]:.2f} broke above the {n}-bar high {ceiling:.2f}", bars)
        if close[-1] < floor and close[-2] >= floor_before:
            return self.signal(SELL, f"close {close[-1]:.2f} broke below the {n}-bar low {floor:.2f}", bars)
        return None


class MacdCross(Rule):
    """BUY when MACD's diff crosses above its signal line, SELL when it crosses below."""

    code = "macd_cross"

    def __init__(self, fast: int = 12, slow: int = 26, n: int = 9) -> None:
        super().__init__(fast=fast, slow=slow, n=n)
        self.fast, self.slow, self.n = fast, slow, n

    @property
    def min_bars(self) -> int:
        # exponential averages need a run-in before their values settle
        return 3 * self.slow

    def evaluate(self, bars: pd.DataFrame) -> Signal | None:
        close = bars["close"].iloc[-6 * self.slow :]
        diff = close.ewm(span=self.fast, adjust=False).mean() - close.ewm(span=self.slow, adjust=False).mean()
        dea = diff.ewm(span=self.n, adjust=False).mean()
        gap_now, gap_before = diff.iloc[-1] - dea.iloc[-1], diff.iloc[-2] - dea.iloc[-2]
        if gap_before <= 0 < gap_now:
            return self.signal(BUY, f"macd {diff.iloc[-1]:.3f} crossed above its signal {dea.iloc[-1]:.3f}", bars)
        if gap_before >= 0 > gap_now:
            return self.signal(SELL, f"macd {diff.iloc[-1]:.3f} crossed below its signal {dea.iloc[-1]:.3f}", bars)
        return None


class Rsi(Rule):
    """Mean reversion: BUY when RSI climbs back above ``low`` after being oversold, SELL when it falls back
    below ``high`` after being overbought."""

    code = "rsi"

    def __init__(self, period: int = 14, low: float = 30, high: float = 70) -> None:
        super().__init__(period=period, low=low, high=high)
        self.period, self.low, self.high = period, low, high

    @property
    def min_bars(self) -> int:
        return 5 * self.period

    def evaluate(self, bars: pd.DataFrame) -> Signal | None:
        change = bars["close"].iloc[-10 * self.period :].diff()
        gain = change.clip(lower=0).ewm(alpha=1 / self.period, adjust=False).mean()
        loss = (-change.clip(upper=0)).ewm(alpha=1 / self.period, adjust=False).mean()
        rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        now, before = rsi.iloc[-1], rsi.iloc[-2]
        if np.isnan(now) or np.isnan(before):
            return None
        if before < self.low <= now:
            return self.signal(BUY, f"rsi {now:.0f} came back above {self.low:.0f}", bars)
        if before > self.high >= now:
            return self.signal(SELL, f"rsi {now:.0f} fell back below {self.high:.0f}", bars)
        return None


class OpeningRange(Rule):
    """The classic day-trade entry: BUY when a bar closes above the high of the day's opening range (its first
    ``minutes``), SELL when one closes below its low. The range is the day's own, so the rule needs nothing from
    earlier days and fires at most once each way on a quiet day."""

    code = "opening_range"

    def __init__(self, minutes: int = 30) -> None:
        if minutes <= 0 or minutes % 15:
            raise ValueError("minutes must be a positive multiple of 15")
        super().__init__(minutes=minutes)
        self.minutes = minutes
        self.n = minutes // 15

    @property
    def min_bars(self) -> int:
        return self.n + 1

    def evaluate(self, bars: pd.DataFrame) -> Signal | None:
        today = bars.index[-1].normalize()
        day = bars.iloc[bars.index.searchsorted(today) :]
        opening_bars = pd.date_range(today + pd.Timedelta(hours=9), periods=self.n, freq="15min")
        # the range is only a range if the stock traded in every one of its bars
        if len(day) <= self.n or not day.index[: self.n].equals(opening_bars):
            return None
        opening = day.iloc[: self.n]
        high, low = opening["high"].max(), opening["low"].min()
        now, before = day["close"].iloc[-1], day["close"].iloc[-2]
        if before <= high < now:
            return self.signal(BUY, f"close {now:.2f} broke above the {self.minutes}-minute opening range high {high:.2f}", bars)
        if before >= low > now:
            return self.signal(SELL, f"close {now:.2f} broke below the {self.minutes}-minute opening range low {low:.2f}", bars)
        return None


RULES: dict[str, type[Rule]] = {rule.code: rule for rule in (MaCross, Breakout, MacdCross, Rsi, OpeningRange)}


def build_rule(spec: dict) -> Rule:
    """A rule from its configuration: ``{"rule": "ma_cross", "fast": 5, "slow": 20}``."""
    params = dict(spec)
    name = params.pop("rule", None)
    if name is None:
        raise ValueError(f"a signal needs a 'rule'; known rules: {', '.join(RULES)}")
    if name in RULES:
        return RULES[name](**params)
    if ":" in name:
        module, _, cls = name.partition(":")
        rule = getattr(importlib.import_module(module), cls)(**params)
        rule.code = rule.code or cls
        return rule
    raise ValueError(f"unknown rule {name!r}; known rules: {', '.join(RULES)}, or 'package.module:ClassName'")
