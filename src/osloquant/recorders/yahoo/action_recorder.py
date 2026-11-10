"""Dividends and splits from Yahoo. They ride along in the price history, so they cost no extra request."""

from __future__ import annotations

import pandas as pd

from osloquant.contract.recorder import TimeSeriesRecorder
from osloquant.contract.schema import EntityRef
from osloquant.domain.actions import StockAction
from osloquant.domain.meta import Stock
from osloquant.recorders.yahoo import client
from osloquant.recorders.yahoo.cleaning import fix_foreign_dividends, fx_rates


def to_actions(history: pd.DataFrame) -> pd.DataFrame:
    """The days of a price history that carry a dividend or a split."""
    columns = ["timestamp", "dividend", "split"]
    if history.empty or "dividend" not in history.columns:
        return pd.DataFrame(columns=columns)
    df = history[columns].fillna(0.0)
    return df[(df["dividend"] > 0) | (df["split"] > 0)].reset_index(drop=True)


class YahooStockActionRecorder(TimeSeriesRecorder):
    provider = "yahoo"
    entity_schema = Stock
    data_schema = StockAction
    #: Yahoo sometimes adds a dividend a day or two after the ex-date, so the last weeks are always asked again
    lookback_days = 30

    def evaluate_start(self, entity: EntityRef, latest: pd.Timestamp | None) -> pd.Timestamp:
        if self.start_timestamp is not None:
            return self.start_timestamp
        if latest is None or self.force_update:
            return pd.Timestamp(self.default_start)
        return pd.Timestamp.now().normalize() - pd.Timedelta(days=self.lookback_days)

    #: currency rates for a dividend paid in another currency (cleaning rule 0), read once per run
    _fx: dict | None = None

    def record(self, entity: EntityRef, start: pd.Timestamp, end: pd.Timestamp | None) -> pd.DataFrame:
        if self._fx is None:
            self._fx = fx_rates()
        history, _ = fix_foreign_dividends(client.fetch_history(entity.symbol, start, end), self._fx)
        return to_actions(history)
