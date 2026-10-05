"""Daily bars from Yahoo, as quoted and adjusted."""

from __future__ import annotations

import pandas as pd

from osloquant.contract import AdjustType, IntervalLevel
from osloquant.contract.recorder import KdataRecorder
from osloquant.contract.schema import EntityRef
from osloquant.domain.meta import Currency, Future, Index, Stock
from osloquant.domain.quotes import (
    Currency1dKdata,
    Future1dKdata,
    Index1dKdata,
    Stock1dAdjKdata,
    Stock1dKdata,
    Stock15mKdata,
)
from osloquant.recorders.yahoo import client
from osloquant.recorders.yahoo.cleaning import apply_exceptions, clean_history


def to_bars(history: pd.DataFrame, adjust_type: AdjustType) -> pd.DataFrame:
    """Turn Yahoo's history into bars. For adjusted bars the whole bar is scaled by adj_close / close."""
    if history.empty:
        return history
    df = history.copy()
    # value traded is a real amount of money: always the quoted price times the shares
    df["turnover"] = df["close"] * df["volume"]
    if AdjustType(adjust_type) == AdjustType.adj:
        factor = df["adj_close"] / df["close"]
        for column in ("open", "high", "low", "close"):
            df[column] = df[column] * factor
        if "flat" in df.columns:
            # a day whose move was removed as a vendor error (see data_exceptions.yaml) has no usable range
            for column in ("open", "high", "low"):
                df[column] = df[column].where(~df["flat"], df["close"])
    return df[["timestamp", "open", "high", "low", "close", "volume", "turnover"]]


class YahooKdataRecorder(KdataRecorder):
    provider = "yahoo"
    #: repair Yahoo's known faults and apply the listed exceptions; only stocks need it
    clean = False

    def record(self, entity: EntityRef, start: pd.Timestamp, end: pd.Timestamp | None) -> pd.DataFrame:
        history = client.fetch_history(entity.symbol, start, end)
        if self.clean:
            history, counts = clean_history(history)
            for rule, n in counts.items():
                self.repairs[rule] = self.repairs.get(rule, 0) + n
            history = apply_exceptions(history, entity.symbol)
        return to_bars(history, self.adjust_type)


class YahooStock1dKdataRecorder(YahooKdataRecorder):
    entity_schema = Stock
    data_schema = Stock1dKdata
    adjust_type = AdjustType.raw
    clean = True


class YahooStock1dAdjKdataRecorder(YahooKdataRecorder):
    entity_schema = Stock
    data_schema = Stock1dAdjKdata
    adjust_type = AdjustType.adj
    clean = True


class YahooStock15mKdataRecorder(YahooKdataRecorder):
    """15-minute bars. Yahoo keeps 60 days of them; recording regularly is what builds a longer history."""

    entity_schema = Stock
    data_schema = Stock15mKdata
    level = IntervalLevel.LEVEL_15MIN
    adjust_type = AdjustType.raw
    #: the newest stored bar may have been recorded while it was forming; a day of overlap replaces it
    overlap_days = 1
    history_days = 58

    def full_start(self) -> pd.Timestamp:
        return self.start_timestamp or pd.Timestamp.now().normalize() - pd.Timedelta(days=self.history_days)

    def record(self, entity: EntityRef, start: pd.Timestamp, end: pd.Timestamp | None) -> pd.DataFrame:
        # Yahoo refuses intraday requests that reach further back than it keeps
        start = max(start, pd.Timestamp.now().normalize() - pd.Timedelta(days=self.history_days))
        df = client.fetch_intraday(entity.symbol, start, interval=self.level.value)
        if df.empty:
            return df
        df["turnover"] = df["close"] * df["volume"]
        return df


class YahooIndex1dKdataRecorder(YahooKdataRecorder):
    entity_schema = Index
    data_schema = Index1dKdata


class YahooFuture1dKdataRecorder(YahooKdataRecorder):
    entity_schema = Future
    data_schema = Future1dKdata


class YahooCurrency1dKdataRecorder(YahooKdataRecorder):
    entity_schema = Currency
    data_schema = Currency1dKdata
