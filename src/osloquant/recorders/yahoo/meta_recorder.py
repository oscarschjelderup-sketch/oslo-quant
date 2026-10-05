"""The entity lists. Yahoo cannot list an exchange, so the lists are kept in this package."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pandas as pd
import yaml

from osloquant.contract.recorder import EntityRecorder
from osloquant.domain.meta import Currency, Future, Index, Stock


def load_universe(path: str | Path | None = None) -> pd.DataFrame:
    """Read a universe file (sector -> Yahoo ticker -> name) into entity rows."""
    if path is None:
        text = resources.files("osloquant").joinpath("resources/universe.yaml").read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    rows, seen = [], set()
    for sector, members in (yaml.safe_load(text) or {}).items():
        for symbol, name in (members or {}).items():
            code, _, suffix = symbol.partition(".")
            if suffix.upper() != "OL":
                raise ValueError(f"{symbol}: only Oslo tickers (ending in .OL) belong in the stock universe")
            if code in seen:
                raise ValueError(f"{symbol} is listed twice in the universe")
            seen.add(code)
            rows.append(
                {"entity_type": "stock", "exchange": "ol", "code": code, "name": name, "symbol": symbol, "sector": sector}
            )
    return pd.DataFrame(rows)


class YahooStockMetaRecorder(EntityRecorder):
    provider = "yahoo"
    data_schema = Stock

    def __init__(self, universe: str | Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.universe = universe

    def fetch_entities(self) -> pd.DataFrame:
        return load_universe(self.universe)


class _FixedListRecorder(EntityRecorder):
    provider = "yahoo"
    entity_type: str = ""
    #: (exchange, code, name, symbol, extra columns)
    entities: list[tuple] = []

    def fetch_entities(self) -> pd.DataFrame:
        rows = []
        for exchange, code, name, symbol, extra in self.entities:
            rows.append({"entity_type": self.entity_type, "exchange": exchange, "code": code, "name": name, "symbol": symbol, **extra})
        return pd.DataFrame(rows)


class YahooIndexMetaRecorder(_FixedListRecorder):
    data_schema = Index
    entity_type = "index"
    entities = [
        ("ol", "OSEBX", "Oslo Børs Benchmark Index", "OSEBX.OL", {"category": "total_return"}),
        ("ol", "OBX", "OBX Total Return Index", "OBX.OL", {"category": "total_return"}),
        ("ol", "OSEFX", "Oslo Børs Mutual Fund Index", "OSEFX.OL", {"category": "total_return"}),
        ("us", "GSPC", "S&P 500", "^GSPC", {"category": "price"}),
        ("eu", "STOXX", "STOXX Europe 600", "^STOXX", {"category": "price"}),
    ]


class YahooFutureMetaRecorder(_FixedListRecorder):
    data_schema = Future
    entity_type = "future"
    entities = [
        ("ice", "BRENT", "Brent crude, front month", "BZ=F", {}),
        ("nymex", "NATGAS", "Henry Hub natural gas, front month", "NG=F", {}),
    ]


class YahooCurrencyMetaRecorder(_FixedListRecorder):
    data_schema = Currency
    entity_type = "currency"
    entities = [
        ("fx", "USDNOK", "US dollar in kroner", "NOK=X", {}),
        ("fx", "EURNOK", "Euro in kroner", "EURNOK=X", {}),
    ]
