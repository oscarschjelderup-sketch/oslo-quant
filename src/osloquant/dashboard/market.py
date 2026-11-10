"""Prices for the dashboard: the store's adjusted daily bars (Yahoo Finance, delayed), returns over day / week / month /
year to date, sector groups, and a label for every number saying where it comes from and when."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from osloquant import signals as sg
from osloquant.dashboard.dates import dato

PRICE_SOURCE = "Yahoo Finance via oslo-quant-lageret (daglig sluttkurs, forsinket)"

# The universe's sectors folded into the groups the dashboard shows, each with the driver that moves it.
GROUPS = {
    "Exploration & production": "Energy",
    "Oil service & drilling": "Energy",
    "Tankers & gas shipping": "Shipping",
    "Other shipping": "Shipping",
    "Seafood": "Seafood",
    "Banks & insurance": "Finance",
    "Industrials & materials": "Industrials & materials",
    "Consumer, telecom & real estate": "Consumer, telecom & real estate",
    "Technology & renewables": "Technology & renewables",
    "Investment companies": "Investment companies",
}
GROUP_ORDER = ["Energy", "Shipping", "Seafood", "Finance", "Industrials & materials", "Consumer, telecom & real estate",
               "Technology & renewables", "Investment companies"]


@dataclass
class Snapshot:
    panel: dict[str, pd.DataFrame]          # open/high/low/close/volume, codes as columns
    names: dict[str, str]
    sectors: dict[str, str]                  # code -> universe sector
    asof: pd.Timestamp                       # newest session in the store

    def group(self, code: str) -> str:
        return GROUPS.get(self.sectors.get(code, ""), "Other")


def _sectors() -> dict[str, str]:
    from osloquant.contract.api import get_data
    from osloquant.domain import Stock

    df = get_data(Stock, columns=["code", "sector"])
    return dict(zip(df["code"], df["sector"], strict=True)) if not df.empty else {}


@lru_cache(maxsize=4)
def _snapshot_cached(stamp: str) -> Snapshot:
    P = sg.load_panel(start=pd.Timestamp.now() - pd.Timedelta(days=800))
    asof = P["close"].index[-1] if not P["close"].empty else pd.NaT
    return Snapshot(P, sg.stock_names(), _sectors(), asof)


def snapshot() -> Snapshot:
    """The store's prices, cached until the store has a newer bar (the cache key is the newest bar's date)."""
    from osloquant.contract.api import get_coverage
    from osloquant.domain import Stock1dAdjKdata

    last = get_coverage(Stock1dAdjKdata)["last"]
    return _snapshot_cached(str(last))


_quoted_cache: dict[str, pd.DataFrame] = {}


def quoted_closes() -> pd.DataFrame:
    """The quoted (unadjusted) closes of the last 420 days, codes as columns: what the share actually traded at. The
    adjusted series is a total-return index – right for returns over time, wrong for «the change today» on an ex-day
    and for «the highest price this year» (funn #30, #31). Empty when the quoted table has never been recorded."""
    from osloquant.contract.api import get_coverage, get_data
    from osloquant.domain import Stock1dKdata

    try:
        cov = get_coverage(Stock1dKdata)
        key = f"{cov['last']}|{cov['rows']}"
        if key not in _quoted_cache:
            df = get_data(Stock1dKdata, columns=["code", "timestamp", "close"], start_timestamp=pd.Timestamp.now().normalize() - pd.Timedelta(days=420))
            _quoted_cache.clear()
            _quoted_cache[key] = pd.DataFrame() if df is None or df.empty else df.dropna(subset=["close"]).pivot(index="timestamp", columns="code", values="close")
        return _quoted_cache[key]
    except Exception:  # noqa: BLE001 – no quoted table: the adjusted prices are used and labelled
        return pd.DataFrame()


def quoted_view(snap: Snapshot, code: str, quoted: pd.DataFrame | None = None) -> dict:
    """The day's change and the 12-month range on quoted closes, when the quoted series is as fresh as the adjusted one.
    ``fresh`` is False when it lags (or does not exist): the caller then keeps the adjusted numbers and says so."""
    out = {"fresh": False, "chg_1d": None, "lo12": None, "hi12": None, "n12": 0, "to": None}
    quoted = quoted_closes() if quoted is None else quoted
    C = snap.panel["close"]
    if code not in C.columns or quoted is None or quoted.empty or code not in quoted.columns:
        return out
    a, q = C[code].dropna(), quoted[code].dropna()
    if len(a) < 2 or len(q) < 2 or q.index[-1] != a.index[-1] or q.index[-2] != a.index[-2]:
        return out
    q12 = q.iloc[-250:]
    return {"fresh": True, "chg_1d": float(q.iloc[-1] / q.iloc[-2] - 1), "prev": float(q.iloc[-2]), "lo12": float(q12.min()), "hi12": float(q12.max()),
            "n12": len(q12), "to": q.index[-1]}


def returns(snap: Snapshot) -> pd.DataFrame:
    """Per code: last close, its date, and returns over 1, 5 and 21 sessions and the year to date."""
    C = snap.panel["close"]
    quoted = quoted_closes()
    rows = []
    for code in C.columns:
        c = C[code].dropna()
        if c.empty:
            continue
        last, day = float(c.iloc[-1]), c.index[-1]
        ytd_base = c[c.index < pd.Timestamp(day.year, 1, 1)]
        qv = quoted_view(snap, code, quoted)             # the day's change is a price change, not a total return (funn #30)
        rows.append({
            "code": code, "name": snap.names.get(code, code), "group": snap.group(code), "close": last, "date": day,
            "d1": qv["chg_1d"] if qv["fresh"] else (last / c.iloc[-2] - 1 if len(c) > 1 else None),
            "w1": last / c.iloc[-6] - 1 if len(c) > 5 else None,
            "m1": last / c.iloc[-22] - 1 if len(c) > 21 else None,
            "ytd": last / ytd_base.iloc[-1] - 1 if len(ytd_base) else (last / c.iloc[0] - 1),
            "ytd_from_listing": not len(ytd_base),
            "stale": day < snap.asof,
        })
    return pd.DataFrame(rows).set_index("code") if rows else pd.DataFrame()


def price_label(day: pd.Timestamp) -> str:
    return f"{PRICE_SOURCE}, {dato(day)}"


def last_price(snap: Snapshot, code: str) -> tuple[float, pd.Timestamp] | None:
    if code not in snap.panel["close"].columns:
        return None
    c = snap.panel["close"][code].dropna()
    return (float(c.iloc[-1]), c.index[-1]) if len(c) else None
