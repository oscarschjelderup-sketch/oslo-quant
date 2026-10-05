"""The only module that talks to Yahoo. Everything else sees plain DataFrames, which is what tests replace."""

from __future__ import annotations

import logging
import time

import pandas as pd

logger = logging.getLogger(__name__)

_RETRIES = 3


def _ticker(symbol: str):
    import yfinance as yf

    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    return yf.Ticker(symbol)


def _with_retries(what: str, fn):
    for attempt in range(1, _RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == _RETRIES:
                raise
            logger.info("%s failed (%s), retrying", what, e)
            time.sleep(1.5 * attempt)


#: histories fetched in the last few minutes: the raw bars, the adjusted bars and the corporate actions of a
#: stock all come from the same download, so recording the three costs one request, not three
_history_cache: dict[tuple, tuple[float, pd.Timestamp, pd.DataFrame]] = {}
_HISTORY_CACHE_SECONDS = 300


def fetch_history(symbol: str, start: pd.Timestamp, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Daily bars for ``symbol`` as Yahoo has them.

    Columns: timestamp, open, high, low, close, adj_close, volume, dividend (per share, on the ex-date) and
    split (new shares per old share on the day of a split, else 0).
    """
    key = (symbol, end)
    cached = _history_cache.get(key)
    # a download that started earlier holds everything a later start asks for
    if cached is not None and time.time() - cached[0] < _HISTORY_CACHE_SECONDS and cached[1] <= start:
        df = cached[2]
        return df[df["timestamp"] >= start].reset_index(drop=True)
    df = _fetch_history(symbol, start, end)
    _history_cache[key] = (time.time(), start, df)
    return df.copy()


def clear_history_cache() -> None:
    _history_cache.clear()


def _fetch_history(symbol: str, start: pd.Timestamp, end: pd.Timestamp | None = None) -> pd.DataFrame:

    def call():
        # Yahoo's end date is exclusive
        end_arg = None if end is None else (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        return _ticker(symbol).history(
            start=start.strftime("%Y-%m-%d"), end=end_arg, interval="1d", auto_adjust=False, actions=True
        )

    raw = _with_retries(f"history {symbol}", call)
    columns = ["timestamp", "open", "high", "low", "close", "adj_close", "volume", "dividend", "split"]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=columns)

    index = pd.DatetimeIndex(raw.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    df = pd.DataFrame(
        {
            "timestamp": index.normalize(),
            "open": raw["Open"].to_numpy(),
            "high": raw["High"].to_numpy(),
            "low": raw["Low"].to_numpy(),
            "close": raw["Close"].to_numpy(),
            "adj_close": raw["Adj Close"].to_numpy() if "Adj Close" in raw.columns else raw["Close"].to_numpy(),
            "volume": raw["Volume"].to_numpy(),
            "dividend": raw["Dividends"].to_numpy() if "Dividends" in raw.columns else 0.0,
            "split": raw["Stock Splits"].to_numpy() if "Stock Splits" in raw.columns else 0.0,
        }
    )
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    return df.drop_duplicates(subset="timestamp", keep="last").reset_index(drop=True)


def fetch_intraday(symbol: str, start: pd.Timestamp, interval: str = "15m") -> pd.DataFrame:
    """Intraday bars for ``symbol``: timestamp (the start of the bar, exchange local time), open, high, low, close, volume.

    Yahoo keeps 60 days of 15-minute bars and quotes Oslo with a delay of about 15 minutes. The newest bar is
    usually still forming: its open is final, the rest is not.
    """

    def call():
        return _ticker(symbol).history(start=start.strftime("%Y-%m-%d"), interval=interval, auto_adjust=False, actions=False)

    raw = _with_retries(f"intraday {symbol}", call)
    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=columns)
    index = pd.DatetimeIndex(raw.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    df = pd.DataFrame(
        {
            "timestamp": index,
            "open": raw["Open"].to_numpy(),
            "high": raw["High"].to_numpy(),
            "low": raw["Low"].to_numpy(),
            "close": raw["Close"].to_numpy(),
            "volume": raw["Volume"].to_numpy(),
        }
    )
    df = df.dropna(subset=["open", "close"])
    df = df[df["close"] > 0]
    return df.drop_duplicates(subset="timestamp", keep="last").reset_index(drop=True)


_STATEMENTS = {
    ("income", "year"): "income_stmt",
    ("income", "quarter"): "quarterly_income_stmt",
    ("balance", "year"): "balance_sheet",
    ("balance", "quarter"): "quarterly_balance_sheet",
    ("cashflow", "year"): "cashflow",
    ("cashflow", "quarter"): "quarterly_cashflow",
}

#: statements already fetched in this process, so that recording four finance tables costs six requests, not twenty
_statement_cache: dict[tuple[str, str, str], pd.DataFrame] = {}


def fetch_statement(symbol: str, kind: str, period: str) -> pd.DataFrame:
    """One financial statement as Yahoo gives it: line items in the index, period ends in the columns."""
    key = (symbol, kind, period)
    if key not in _statement_cache:
        attribute = _STATEMENTS[(kind, period)]
        df = _with_retries(f"{attribute} {symbol}", lambda: getattr(_ticker(symbol), attribute))
        _statement_cache[key] = df if df is not None else pd.DataFrame()
    return _statement_cache[key]


def clear_statement_cache() -> None:
    _statement_cache.clear()
