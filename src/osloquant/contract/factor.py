"""Factors: the calculation model on a two-dimensional index.

A factor moves through three DataFrames, all indexed by (entity_id, timestamp):

``data_df``    rows read from a schema with ``query_data``
``factor_df``  ``data_df`` plus whatever the transformer computed (moving averages, MACD, ...)
``result_df``  the verdict: ``filter_result`` (True / False / unknown) and/or ``score_result`` (0 to 1)

A row of ``result_df`` at time t may only depend on data up to and including t. Selecting targets and
backtesting both read ``result_df`` and nothing else, so that one rule is what keeps a backtest honest.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from osloquant.contract import IntervalLevel, TargetType
from osloquant.contract.api import get_data, get_entity_ids, to_pd_timestamp
from osloquant.contract.context import context

INDEX = ["entity_id", "timestamp"]


def by_entity(data: pd.Series | pd.DataFrame):
    """Group a (entity_id, timestamp)-indexed object by entity, keeping the row order."""
    return data.groupby(level="entity_id", sort=False, group_keys=False)


def filter_result(condition: pd.Series, valid: pd.Series | None = None) -> pd.DataFrame:
    """A ``filter_result`` column from a condition; rows where ``valid`` is False become unknown."""
    out = condition.astype("boolean")
    if valid is not None:
        out = out.where(valid.astype(bool))
    return out.to_frame("filter_result")


class Transformer:
    """Adds columns to a frame, entity by entity, using only each row's past."""

    def transform(self, input_df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError


class Scorer:
    """Turns factor columns into a ``score_result`` between 0 and 1."""

    def score(self, input_df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError


class RankScorer(Scorer):
    """Each day, rank the entities on ``column``: the highest gets 1, the lowest close to 0."""

    def __init__(self, column: str, ascending: bool = True, min_entities: int = 5) -> None:
        self.column = column
        self.ascending = ascending
        self.min_entities = min_entities

    def score(self, input_df: pd.DataFrame) -> pd.DataFrame:
        by_day = input_df[self.column].groupby(level="timestamp")
        score = by_day.rank(pct=True, ascending=self.ascending)
        enough = by_day.transform("count") >= self.min_entities
        return score.where(enough).to_frame("score_result")


class Factor:
    #: read from this schema; the kdata schema of the entity type when omitted (see TechnicalFactor)
    data_schema: type | None = None
    #: columns to read; all when omitted
    columns: list[str] | None = None
    #: carry the last result forward between rows, for data that arrives rarely (reports)
    fill_gap = False
    #: how many business days a carried result stays valid
    fill_gap_limit = 280
    #: a score at or above this is a positive target, below ``short_threshold`` a negative one
    long_threshold = 0.8
    short_threshold = 0.2
    #: chart hints: columns of factor_df drawn over the price, and in a panel below it
    overlay_cols: list[str] = []
    sub_cols: list[str] = []

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        context.factor_cls_registry[cls.__name__] = cls

    def __init__(
        self,
        entity_schema: type | None = None,
        provider: str | None = None,
        entity_provider: str | None = None,
        entity_ids: list[str] | None = None,
        codes: list[str] | None = None,
        start_timestamp=None,
        end_timestamp=None,
        columns: list[str] | None = None,
        filters: list | None = None,
        level=IntervalLevel.LEVEL_1DAY,
        transformer: Transformer | None = None,
        scorer: Scorer | None = None,
        data_df: pd.DataFrame | None = None,
        compute: bool = True,
    ) -> None:
        if entity_schema is None:
            from osloquant.domain.meta import Stock

            entity_schema = Stock
        self.entity_schema = entity_schema
        self.provider = provider
        self.entity_provider = entity_provider
        self.entity_ids = entity_ids
        self.codes = codes
        self.start_timestamp = to_pd_timestamp(start_timestamp)
        self.end_timestamp = to_pd_timestamp(end_timestamp)
        if columns is not None:
            self.columns = columns
        self.filters = filters
        self.level = IntervalLevel(level)
        self.transformer = transformer
        self.scorer = scorer

        self.data_df: pd.DataFrame | None = data_df
        self.factor_df: pd.DataFrame | None = None
        self.result_df: pd.DataFrame | None = None
        self._positive: pd.DataFrame | None = None
        self._negative: pd.DataFrame | None = None
        self._scores: pd.DataFrame | None = None

        if self.data_df is None:
            self.load_data()
        if compute:
            self.compute()

    # -- data -------------------------------------------------------------------------------------

    def load_data(self) -> None:
        entity_ids = self.entity_ids
        if entity_ids is None and self.codes is not None:
            entity_ids = get_entity_ids(self.entity_schema, provider=self.entity_provider, codes=self.codes)
        columns = None
        if self.columns is not None:
            columns = list(dict.fromkeys([*INDEX, *self.columns]))
        self.data_df = get_data(
            self.data_schema,
            provider=self.provider,
            entity_ids=entity_ids,
            start_timestamp=self.start_timestamp,
            end_timestamp=self.end_timestamp,
            columns=columns,
            filters=self.filters,
            index=INDEX,
            drop_index_col=True,
        )

    # -- computation ------------------------------------------------------------------------------

    def compute(self) -> None:
        self.compute_factor()
        self.compute_result()
        self._positive = self._negative = self._scores = None

    def compute_factor(self) -> None:
        if self.transformer is not None and not self.data_df.empty:
            self.factor_df = self.transformer.transform(self.data_df)
        else:
            self.factor_df = self.data_df

    def compute_result(self) -> None:
        """Set ``result_df``. The default scores with the scorer, if there is one."""
        if self.scorer is not None and not self.factor_df.empty:
            self.result_df = self.scorer.score(self.factor_df)

    # -- reading the verdict ----------------------------------------------------------------------

    def _wide(self, column: str) -> pd.DataFrame | None:
        if self.result_df is None or self.result_df.empty or column not in self.result_df.columns:
            return None
        wide = self.result_df[column].unstack("entity_id").sort_index()
        if self.fill_gap:
            end = self.end_timestamp or pd.Timestamp.now().normalize()
            calendar = pd.bdate_range(wide.index.min(), max(end, wide.index.max()))
            wide = wide.reindex(wide.index.union(calendar)).ffill(limit=self.fill_gap_limit)
        return wide

    def _build_targets(self) -> None:
        filters = self._wide("filter_result")
        scores = self._wide("score_result")
        positive = negative = None
        if filters is not None:
            positive = (filters == True).fillna(False).astype(bool)  # noqa: E712
            negative = (filters == False).fillna(False).astype(bool)  # noqa: E712
        if scores is not None:
            high = (scores >= self.long_threshold).fillna(False).astype(bool)
            low = (scores < self.short_threshold).fillna(False).astype(bool)
            if positive is None:
                positive, negative = high, low
            else:
                high, low = high.reindex_like(positive).fillna(False), low.reindex_like(negative).fillna(False)
                positive, negative = positive & high.astype(bool), negative | low.astype(bool)
        if positive is None:
            positive = negative = pd.DataFrame()
        self._positive, self._negative, self._scores = positive, negative, scores

    def _row(self, wide: pd.DataFrame | None, timestamp) -> pd.Series | None:
        if wide is None or wide.empty:
            return None
        timestamp = to_pd_timestamp(timestamp)
        if self.fill_gap:
            pos = wide.index.searchsorted(timestamp, side="right") - 1
            return None if pos < 0 else wide.iloc[pos]
        return wide.loc[timestamp] if timestamp in wide.index else None

    def get_targets(self, timestamp, target_type: TargetType = TargetType.positive) -> list[str]:
        """The entities that are positive (or negative) targets at ``timestamp``."""
        if self._positive is None:
            self._build_targets()
        wide = self._positive if TargetType(target_type) == TargetType.positive else self._negative
        row = self._row(wide, timestamp)
        return [] if row is None else row.index[row.to_numpy(dtype=bool)].tolist()

    def get_scores(self, timestamp) -> pd.Series:
        """Scores at ``timestamp`` by entity; empty when the factor does not score."""
        if self._positive is None:
            self._build_targets()
        row = self._row(self._scores, timestamp)
        return pd.Series(dtype=float) if row is None else row.dropna().astype(float)

    def get_signal_df(self) -> pd.DataFrame:
        """Where the verdict flips: one row per (entity_id, timestamp) with ``signal`` "buy" or "sell"."""
        if self._positive is None:
            self._build_targets()
        if self._positive.empty:
            return pd.DataFrame(columns=["entity_id", "timestamp", "signal"])
        state = pd.DataFrame(np.nan, index=self._positive.index, columns=self._positive.columns)
        state = state.mask(self._positive, 1.0).mask(self._negative, -1.0)
        # no opinion on a day means the last opinion stands
        held = state.ffill().fillna(0.0)
        before = held.shift(1).fillna(0.0)
        frames = []
        for signal, flips in (("buy", (held == 1) & (before != 1)), ("sell", (held == -1) & (before == 1))):
            timestamps, entities = np.nonzero(flips.to_numpy())
            frames.append(
                pd.DataFrame({"entity_id": flips.columns[entities], "timestamp": flips.index[timestamps], "signal": signal})
            )
        out = pd.concat(frames, ignore_index=True)
        return out.sort_values(["entity_id", "timestamp"]).reset_index(drop=True)

    def draw(self, entity_id: str | None = None, code: str | None = None, show: bool = False, last: int | None = 500):
        """A price chart of one entity with the factor's lines and its buy / sell flips, over the ``last`` bars."""
        from osloquant.contract.drawer import draw_factor

        fig = draw_factor(self, entity_id=entity_id, code=code, last=last)
        if show:
            fig.show()
        return fig


class ScoreFactor(Factor):
    """A factor whose verdict is a score. Give it a scorer, or override ``compute_result``."""
