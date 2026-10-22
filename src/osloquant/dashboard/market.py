"""Prices for the dashboard: the store's adjusted daily bars (Yahoo Finance, delayed), returns over day / week / month /
year to date, sector groups, and a label for every number saying where it comes from and when."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from osloquant import signals as sg

PRICE_SOURCE = "Yahoo Finance via oslo-quant store (daily close, delayed)"

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


def returns(snap: Snapshot) -> pd.DataFrame:
    """Per code: last close, its date, and returns over 1, 5 and 21 sessions and the year to date."""
    C = snap.panel["close"]
    rows = []
    for code in C.columns:
        c = C[code].dropna()
        if c.empty:
            continue
        last, day = float(c.iloc[-1]), c.index[-1]
        ytd_base = c[c.index < pd.Timestamp(day.year, 1, 1)]
        rows.append({
            "code": code, "name": snap.names.get(code, code), "group": snap.group(code), "close": last, "date": day,
            "d1": last / c.iloc[-2] - 1 if len(c) > 1 else None,
            "w1": last / c.iloc[-6] - 1 if len(c) > 5 else None,
            "m1": last / c.iloc[-22] - 1 if len(c) > 21 else None,
            "ytd": last / ytd_base.iloc[-1] - 1 if len(ytd_base) else (last / c.iloc[0] - 1),
            "ytd_from_listing": not len(ytd_base),
            "stale": day < snap.asof,
        })
    return pd.DataFrame(rows).set_index("code") if rows else pd.DataFrame()


def price_label(day: pd.Timestamp) -> str:
    return f"{PRICE_SOURCE}, {day:%d %b %Y}"


def last_price(snap: Snapshot, code: str) -> tuple[float, pd.Timestamp] | None:
    if code not in snap.panel["close"].columns:
        return None
    c = snap.panel["close"][code].dropna()
    return (float(c.iloc[-1]), c.index[-1]) if len(c) else None
