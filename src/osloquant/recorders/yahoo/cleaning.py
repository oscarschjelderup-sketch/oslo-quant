"""Yahoo's Oslo data has a handful of recurring faults. They are repaired here, by rule, before anything is stored.

Each rule fixes one fault that was found in the data and can be recognised from the bar itself:

1. *Dividend booked a day early.* On the last day before a stock goes ex-dividend, Yahoo often reports the
   close with the dividend already taken off, although the high and low of that day are not. The close then
   lies below the day's low by exactly the dividend, and the adjusted series shows a drop one day and a jump
   back the next. Rule: if the next bar pays a dividend and adding it puts the close back inside the day's
   range, add it.
2. *Open, high or low not restated for an old split.* Some from the early 2000s are a half, a quarter or a
   fifth of the closes on either side. Rule: an open at about half or less (or about double or more) of both
   the previous close and the day's own close, on a day when the close itself hardly moved, is replaced by
   the previous close; a high or low that is off by the same kind of factor is pulled in to the open and
   close. A real gap does not trip this, because the close moves with it.
3. *Open or close outside the day's range.* The open is moved to the nearest end of the range, and the range
   is widened to hold the close, so that every stored bar satisfies low <= open, close <= high.
4. *One-day spike without volume.* A zero-volume close that is more than double (or less than half) the
   previous close and is gone again the next day is a misprint. The bar is dropped.
5. *Padding.* On days a stock did not trade, Yahoo repeats the previous close with zero volume. Rule: a
   zero-volume bar that is flat and unchanged from the day before is dropped. (Zero volume alone is not
   enough: for some stocks Yahoo has prices but no volumes for years.)

Faults that cannot be recognised by rule are listed one by one, with the reason, in
``resources/data_exceptions.yaml``.
"""

from __future__ import annotations

from importlib import resources

import numpy as np
import pandas as pd
import yaml

#: how far outside the day's range a repaired close may still land, as a fraction of the price
RANGE_TOLERANCE = 0.005
#: an open, high or low at this fraction (or its inverse) of the prices around it is a leftover from a split
STALE = 0.55
#: ... but an open only counts as stale when the close hardly moved; a real gap takes the close with it
STEADY_CLOSE = 0.25


def clean_history(history: pd.DataFrame, drop_untraded: bool = True) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply rules 1 to 5 to one symbol's history. Returns the cleaned frame and how often each rule fired."""
    counts = {"dividend_close": 0, "open": 0, "range": 0, "spike": 0, "untraded": 0}
    if history.empty:
        return history, counts
    df = history.sort_values("timestamp").reset_index(drop=True).copy()

    if "dividend" in df.columns:
        coming = df["dividend"].shift(-1).fillna(0.0)
        restored = df["close"] + coming
        early = (
            (coming > 0)
            & (df["close"] < df["low"] * (1 - 1e-6))
            & (restored >= df["low"] * (1 - RANGE_TOLERANCE))
            & (restored <= df["high"] * (1 + RANGE_TOLERANCE))
        )
        counts["dividend_close"] = int(early.sum())
        # Yahoo also derived the dividend's adjustment factor from the wrong close, so the adjusted closes of
        # that day and of every earlier day are a little off: put the factor right for all of them
        factor_fix = ((1 - coming / restored) / (1 - coming / df["close"])).where(early, 1.0)
        df["adj_close"] = df["adj_close"] * factor_fix[::-1].cumprod()[::-1]
        df.loc[early, "adj_close"] = df.loc[early, "adj_close"] * restored[early] / df.loc[early, "close"]
        df.loc[early, "close"] = restored[early]

    previous = df["close"].shift(1).fillna(df["close"])
    below, above = np.minimum(previous, df["close"]), np.maximum(previous, df["close"])
    steady_close = (df["close"] / previous - 1).abs() < STEADY_CLOSE
    stale_open = steady_close & ((df["open"] < STALE * below) | (df["open"] > above / STALE))
    df["open"] = df["open"].where(~stale_open, previous)
    body_low, body_high = np.minimum(df["open"], df["close"]), np.maximum(df["open"], df["close"])
    df["low"] = df["low"].where((df["low"] >= STALE * body_low) & (df["low"] <= body_high / STALE), body_low)
    df["high"] = df["high"].where((df["high"] <= body_high / STALE) & (df["high"] >= STALE * body_low), body_high)

    outside = ((df["open"] < df["low"]) | (df["open"] > df["high"])) & (df["low"] <= df["high"])
    counts["open"] = int((stale_open | outside).sum())
    df["open"] = df["open"].where(~outside, df["open"].clip(lower=df["low"], upper=df["high"]))

    counts["range"] = int(((df["close"] < df["low"]) | (df["close"] > df["high"])).sum())
    df["low"] = np.minimum(df["low"], np.minimum(df["open"], df["close"]))
    df["high"] = np.maximum(df["high"], np.maximum(df["open"], df["close"]))

    untraded = df["volume"].fillna(0) == 0
    before, after = df["close"].shift(1), df["close"].shift(-1)
    jump = (df["close"] > 2 * before) | (df["close"] < 0.5 * before)
    spike = untraded & jump & ((after / before - 1).abs() < 0.2)
    counts["spike"] = int(spike.sum())
    df = df[~spike].reset_index(drop=True)

    if drop_untraded:
        padding = (df["volume"].fillna(0) == 0) & (df["high"] == df["low"]) & (df["close"] == df["close"].shift(1))
        counts["untraded"] = int(padding.sum())
        df = df[~padding].reset_index(drop=True)
    return df, counts


def load_exceptions() -> dict:
    text = resources.files("osloquant").joinpath("resources/data_exceptions.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    return {"drop_returns": data.get("drop_returns") or [], "history_start": data.get("history_start") or {}}


def apply_exceptions(history: pd.DataFrame, symbol: str, exceptions: dict | None = None) -> pd.DataFrame:
    """Apply the listed exceptions for ``symbol``.

    ``history_start`` drops everything before a date. ``drop_returns`` removes one day's close-to-close move
    from the adjusted series: earlier adjusted closes are rescaled so the move becomes zero, and that day's
    bar is flattened to its close. The quoted prices (open, high, low, close) are left as Yahoo has them.
    """
    if history.empty:
        return history
    exceptions = load_exceptions() if exceptions is None else exceptions
    df = history.sort_values("timestamp").reset_index(drop=True).copy()

    start = exceptions["history_start"].get(symbol)
    if start:
        df = df[df["timestamp"] >= pd.Timestamp(start["date"])].reset_index(drop=True)

    df["flat"] = False
    for item in sorted((e for e in exceptions["drop_returns"] if e["ticker"] == symbol), key=lambda e: e["date"]):
        date = pd.Timestamp(item["date"])
        hit = df.index[df["timestamp"] == date]
        if len(hit) == 0 or hit[0] == 0:
            continue
        i = hit[0]
        df.loc[: i - 1, "adj_close"] *= df.at[i, "adj_close"] / df.at[i - 1, "adj_close"]
        df.at[i, "flat"] = True
    return df
