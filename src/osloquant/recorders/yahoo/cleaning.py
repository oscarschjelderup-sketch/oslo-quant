"""Yahoo's Oslo data has a handful of recurring faults. They are repaired here, by rule, before anything is stored.

Each rule fixes one fault that was found in the data and can be recognised from the bar itself:

0. *Dividend in another currency.* For a company that pays in USD, EUR or DKK, Yahoo reports the dividend converted
   to NOK at the rate of the day you ask, but scales the adjusted prices with the amount in the foreign currency
   against a price in NOK. The adjustment is then about ten times too small for a dollar dividend, and the adjusted
   series shows a price fall where the shareholder was paid. Rule: the amount Yahoo adjusted with is read off its
   own factor step; when the reported amount is larger by a factor that matches a currency rate, the dividend is
   that amount in that currency, converted at the rate before the ex-date, and the adjusted prices are rescaled
   (``fix_foreign_dividends``). It runs first, because rule 1 reads the dividend amount.
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


#: a reported dividend this many times the amount Yahoo adjusted with is not rounding: it is another currency
FOREIGN_MIN_RATIO = 1.15
#: how close the ratio must be to a currency rate to name the currency (the download day's rate is not known exactly)
FOREIGN_RATE_TOLERANCE = 0.06
#: events of one download share one conversion rate: an event counts when its ratio is this close to the typical one
FOREIGN_SPREAD = 0.03


def fix_foreign_dividends(history: pd.DataFrame, fx: dict[str, pd.Series] | None) -> tuple[pd.DataFrame, int]:
    """Rule 0. ``fx`` maps a currency code to its rate in NOK by date (``fx_rates()``). Returns the history with the
    dividends in NOK at the rate before each ex-date and the adjusted closes rescaled, and how many events changed.
    Without rates, or when no currency fits, nothing is touched."""
    if history.empty or not fx or "dividend" not in history.columns or "adj_close" not in history.columns:
        return history, 0
    df = history.sort_values("timestamp").reset_index(drop=True).copy()
    factor = (df["adj_close"] / df["close"]).to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    events = []
    for i in df.index[df["dividend"].fillna(0) > 0]:
        if i == 0 or not close[i - 1] > 0 or not factor[i] > 0:
            continue
        used = (1 - factor[i - 1] / factor[i]) * close[i - 1]          # the amount Yahoo's own adjustment took off
        reported = float(df.at[i, "dividend"])
        if used > 1e-9 and reported / used >= FOREIGN_MIN_RATIO:
            events.append((i, used, reported / used))
    if not events:
        return history, 0
    typical = float(np.median([r for _, _, r in events]))
    newest = {ccy: float(s.dropna().iloc[-1]) for ccy, s in fx.items() if s is not None and len(s.dropna())}
    near = {ccy: abs(typical / rate - 1) for ccy, rate in newest.items() if rate > 0}
    if not near or min(near.values()) > FOREIGN_RATE_TOLERANCE:
        return history, 0
    ccy = min(near, key=near.get)
    rates = fx[ccy].dropna().sort_index()
    scale = np.ones(len(df))
    fixed = 0
    for i, used, ratio in events:
        if abs(ratio / typical - 1) > FOREIGN_SPREAD:
            continue
        before = rates[rates.index < df.at[i, "timestamp"]]
        if before.empty:
            continue
        nok = used * float(before.iloc[-1])                           # the foreign amount at the rate before the ex-date
        old_step, new_step = 1 - used / close[i - 1], 1 - nok / close[i - 1]
        if not 0 < new_step < 1:
            continue
        scale[:i] *= new_step / old_step
        df.at[i, "dividend"] = nok
        fixed += 1
    if not fixed:
        return history, 0
    df["adj_close"] = df["adj_close"] * scale
    return df, fixed


def fx_rates() -> dict[str, pd.Series]:
    """NOK per USD, EUR and DKK by date, from the store's own currency table (Yahoo). Empty when the table is."""
    try:
        from osloquant.contract.api import get_data
        from osloquant.domain import Currency1dKdata

        df = get_data(Currency1dKdata, columns=["code", "timestamp", "close"])
    except Exception:  # noqa: BLE001 – no currency table yet: rule 0 then does nothing
        return {}
    if df is None or df.empty:
        return {}
    out = {}
    for code, g in df.groupby("code"):
        if isinstance(code, str) and code.endswith("NOK") and len(code) == 6:
            out[code[:3]] = g.set_index("timestamp")["close"].sort_index()
    return out


def clean_history(history: pd.DataFrame, drop_untraded: bool = True, fx: dict[str, pd.Series] | None = None) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply rules 0 to 5 to one symbol's history. Returns the cleaned frame and how often each rule fired."""
    counts = {"foreign_dividend": 0, "dividend_close": 0, "open": 0, "range": 0, "spike": 0, "untraded": 0}
    if history.empty:
        return history, counts
    history, counts["foreign_dividend"] = fix_foreign_dividends(history, fx)
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
