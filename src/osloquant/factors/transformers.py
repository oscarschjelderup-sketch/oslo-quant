"""Indicators. Each adds columns to a (entity_id, timestamp)-indexed frame, using only past rows."""

from __future__ import annotations

import pandas as pd

from osloquant.contract.factor import Transformer, by_entity


class MaTransformer(Transformer):
    """Simple moving averages of the close: ma5, ma10, ..."""

    def __init__(self, windows: tuple[int, ...] | list[int] = (5, 10)) -> None:
        self.windows = list(windows)
        self.indicators = [f"ma{w}" for w in self.windows]

    def transform(self, input_df: pd.DataFrame) -> pd.DataFrame:
        df = input_df.copy()
        close = by_entity(df["close"])
        for window, name in zip(self.windows, self.indicators, strict=True):
            df[name] = close.transform(lambda s, w=window: s.rolling(w).mean())
        return df


class MacdTransformer(Transformer):
    """MACD: diff = EMA(fast) - EMA(slow), dea = EMA(diff, n), macd = diff - dea."""

    def __init__(self, fast: int = 12, slow: int = 26, n: int = 9) -> None:
        self.fast, self.slow, self.n = fast, slow, n
        self.indicators = ["diff", "dea", "macd"]

    def transform(self, input_df: pd.DataFrame) -> pd.DataFrame:
        df = input_df.copy()
        close = by_entity(df["close"])
        ema_fast = close.transform(lambda s: s.ewm(span=self.fast, adjust=False, min_periods=self.fast).mean())
        ema_slow = close.transform(lambda s: s.ewm(span=self.slow, adjust=False, min_periods=self.slow).mean())
        df["diff"] = ema_fast - ema_slow
        df["dea"] = by_entity(df["diff"]).transform(lambda s: s.ewm(span=self.n, adjust=False, min_periods=self.n).mean())
        df["macd"] = df["diff"] - df["dea"]
        return df


class BollTransformer(Transformer):
    """Bollinger bands: a moving average and bands ``window_dev`` standard deviations around it."""

    def __init__(self, window: int = 20, window_dev: float = 2.0) -> None:
        self.window, self.window_dev = window, window_dev
        self.indicators = ["bb_mid", "bb_upper", "bb_lower"]

    def transform(self, input_df: pd.DataFrame) -> pd.DataFrame:
        df = input_df.copy()
        close = by_entity(df["close"])
        mid = close.transform(lambda s: s.rolling(self.window).mean())
        std = close.transform(lambda s: s.rolling(self.window).std(ddof=0))
        df["bb_mid"] = mid
        df["bb_upper"] = mid + self.window_dev * std
        df["bb_lower"] = mid - self.window_dev * std
        return df


class MomentumTransformer(Transformer):
    """Return from ``lookback`` bars ago to ``skip`` bars ago. 252 and 21 give the classic 12-1 momentum."""

    def __init__(self, lookback: int = 252, skip: int = 21) -> None:
        if skip >= lookback:
            raise ValueError("skip must be shorter than lookback")
        self.lookback, self.skip = lookback, skip
        self.indicators = ["momentum"]

    def transform(self, input_df: pd.DataFrame) -> pd.DataFrame:
        df = input_df.copy()
        close = by_entity(df["close"])
        df["momentum"] = close.shift(self.skip) / close.shift(self.lookback) - 1
        return df
