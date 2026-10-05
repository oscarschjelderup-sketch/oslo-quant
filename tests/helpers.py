"""Builders for synthetic entities and bars."""

from __future__ import annotations

import numpy as np
import pandas as pd

from osloquant.contract.storage import df_to_db
from osloquant.domain import Index, Index1dKdata, Stock, Stock1dAdjKdata


def business_days(n: int, start: str = "2020-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def bars(entity_id: str, closes, start: str = "2020-01-01", opens=None) -> pd.DataFrame:
    """Daily bars for one entity. The open is the previous close unless given."""
    closes = np.asarray(closes, dtype=float)
    dates = business_days(len(closes), start)
    opens = np.r_[closes[0], closes[:-1]] if opens is None else np.asarray(opens, dtype=float)
    code = entity_id.split("_", 2)[2]
    return pd.DataFrame(
        {
            "id": [f"{entity_id}_{d:%Y-%m-%d}" for d in dates],
            "entity_id": entity_id,
            "timestamp": dates,
            "provider": "yahoo",
            "code": code,
            "name": code,
            "level": "1d",
            "open": opens,
            "high": np.maximum(opens, closes) * 1.01,
            "low": np.minimum(opens, closes) * 0.99,
            "close": closes,
            "volume": 1000.0,
            "turnover": closes * 1000.0,
            "change_pct": pd.Series(closes).pct_change().to_numpy(),
        }
    )


def panel(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Bars of several entities as the (entity_id, timestamp)-indexed frame factors work on."""
    df = pd.concat(frames, ignore_index=True)
    return df.set_index(["entity_id", "timestamp"]).sort_index()


def store_stocks(codes: list[str]) -> list[str]:
    df = pd.DataFrame(
        {
            "entity_type": "stock",
            "exchange": "ol",
            "code": codes,
            "name": [f"{c} ASA" for c in codes],
            "symbol": [f"{c}.OL" for c in codes],
            "sector": "Test",
        }
    )
    df["id"] = "stock_ol_" + df["code"]
    df["entity_id"] = df["id"]
    df_to_db(df, Stock, "yahoo")
    return df["id"].tolist()


def store_bars(frame: pd.DataFrame, schema=Stock1dAdjKdata) -> None:
    df_to_db(frame, schema, "yahoo")


def store_benchmark(closes, start: str = "2020-01-01") -> None:
    entity = pd.DataFrame(
        [{"id": "index_ol_OSEBX", "entity_id": "index_ol_OSEBX", "entity_type": "index", "exchange": "ol", "code": "OSEBX", "name": "Benchmark", "symbol": "OSEBX.OL"}]
    )
    df_to_db(entity, Index, "yahoo")
    store_bars(bars("index_ol_OSEBX", closes, start), schema=Index1dKdata)


def random_walk(n: int, seed: int, start: float = 100.0, drift: float = 0.0003, vol: float = 0.02) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(rng.normal(drift, vol, n)))
