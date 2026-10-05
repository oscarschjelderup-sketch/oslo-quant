"""Recorders fetch from a provider and write to a schema.

A recorder class names its ``provider`` and ``data_schema``; defining it is enough to make
``data_schema.record_data(provider=...)`` work. Adding a data source means writing recorders, nothing else.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import pandas as pd

from osloquant.contract import AdjustType, IntervalLevel
from osloquant.contract.api import get_data, get_entity_refs, to_pd_timestamp
from osloquant.contract.context import context
from osloquant.contract.schema import EntityRef
from osloquant.contract.storage import delete_data, df_to_db

logger = logging.getLogger(__name__)


@dataclass
class RecordSummary:
    schema: str
    provider: str
    entities: int = 0
    rows: int = 0
    failed: dict[str, str] = field(default_factory=dict)
    #: entities whose whole history was downloaded again because the provider restated it
    refreshed: list[str] = field(default_factory=list)
    #: what the provider's cleaning rules did, e.g. {"open": 12} for twelve repaired opens
    repairs: dict[str, int] = field(default_factory=dict)

    def __str__(self) -> str:
        text = f"{self.schema} <- {self.provider}: {self.rows} rows for {self.entities} entities"
        if self.refreshed:
            text += f", {len(self.refreshed)} restated"
        repaired = {k: v for k, v in self.repairs.items() if v}
        if repaired:
            text += ", repaired " + ", ".join(f"{v} {k}" for k, v in repaired.items())
        if self.failed:
            text += f", {len(self.failed)} failed ({', '.join(sorted(self.failed))})"
        return text


class Recorder:
    provider: str | None = None
    data_schema: type | None = None

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # a class registers when it names its own schema; the provider may come from a base class
        if cls.__dict__.get("data_schema") and cls.provider:
            schema = cls.data_schema
            context.schema_recorders.setdefault(schema, {})[cls.provider] = cls
            providers = context.schema_providers.setdefault(schema, [])
            if cls.provider not in providers:
                providers.append(cls.provider)

    def __init__(self, force_update: bool = False, sleeping_time: float = 0.0) -> None:
        self.force_update = force_update
        self.sleeping_time = sleeping_time
        self.logger = logging.getLogger(type(self).__module__)
        #: counts of repairs made while recording; ends up in the summary
        self.repairs: dict[str, int] = {}

    def run(self) -> RecordSummary:
        raise NotImplementedError


class EntityRecorder(Recorder):
    """Records the entity list itself (the "meta" tables)."""

    def fetch_entities(self) -> pd.DataFrame:
        """Return a frame with at least: entity_type, exchange, code, name, symbol."""
        raise NotImplementedError

    def run(self) -> RecordSummary:
        from osloquant.contract.api import encode_entity_id

        df = self.fetch_entities().copy()
        df["id"] = [encode_entity_id(t, e, c) for t, e, c in zip(df["entity_type"], df["exchange"], df["code"], strict=True)]
        df["entity_id"] = df["id"]
        rows = df_to_db(df, self.data_schema, self.provider, force_update=True)
        summary = RecordSummary(schema=self.data_schema.__name__, provider=self.provider, entities=rows, rows=rows)
        self.logger.info(str(summary))
        return summary


class TimeSeriesRecorder(Recorder):
    """Records rows over time for each entity of ``entity_schema``, fetching only what is missing."""

    entity_schema: type | None = None
    #: provider of the entity list; the recorder's own provider when omitted
    entity_provider: str | None = None
    default_start = "2000-01-01"

    def __init__(
        self,
        entity_ids: list[str] | None = None,
        codes: list[str] | None = None,
        code: str | None = None,
        start_timestamp=None,
        end_timestamp=None,
        force_update: bool = False,
        sleeping_time: float = 0.0,
    ) -> None:
        super().__init__(force_update=force_update, sleeping_time=sleeping_time)
        if code is not None:
            codes = [code]
        self.entity_ids = entity_ids
        self.codes = codes
        self.start_timestamp = to_pd_timestamp(start_timestamp)
        self.end_timestamp = to_pd_timestamp(end_timestamp)

    # -- what a provider implements -------------------------------------------------------------

    def record(self, entity: EntityRef, start: pd.Timestamp, end: pd.Timestamp | None) -> pd.DataFrame | None:
        """Fetch rows for ``entity`` from ``start``. Must return a ``timestamp`` column."""
        raise NotImplementedError

    # -- the shared machinery -------------------------------------------------------------------

    def load_entities(self) -> list[EntityRef]:
        provider = self.entity_provider or self.provider
        if provider not in self.entity_schema.get_providers():
            provider = self.entity_schema.default_provider()
        refs = get_entity_refs(self.entity_schema, provider=provider, entity_ids=self.entity_ids, codes=self.codes)
        if not refs:
            hint = f"run {self.entity_schema.__name__}.record_data() first" if not (self.entity_ids or self.codes) else "check the codes"
            raise LookupError(f"no {self.entity_schema.__name__} entities to record for; {hint}")
        return refs

    def generate_domain_id(self, entity: EntityRef, timestamp: pd.Timestamp) -> str:
        return f"{entity.id}_{timestamp.strftime('%Y-%m-%d')}"

    def get_latest_saved_timestamp(self, entity: EntityRef) -> pd.Timestamp | None:
        df = get_data(
            self.data_schema,
            provider=self.provider,
            entity_id=entity.id,
            columns=["timestamp"],
            order=self.data_schema.timestamp.desc(),
            limit=1,
        )
        return None if df.empty else to_pd_timestamp(df["timestamp"].iloc[0])

    def evaluate_start(self, entity: EntityRef, latest: pd.Timestamp | None) -> pd.Timestamp:
        if self.start_timestamp is not None:
            return self.start_timestamp
        if latest is None or self.force_update:
            return to_pd_timestamp(self.default_start)
        return latest + pd.Timedelta(days=1)

    def finalize(self, entity: EntityRef, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["entity_id"] = entity.id
        df["id"] = [self.generate_domain_id(entity, ts) for ts in df["timestamp"]]
        table_columns = {c.name for c in self.data_schema.__table__.columns}
        for name, value in (("provider", self.provider), ("code", entity.code), ("name", entity.name)):
            if name in table_columns and name not in df.columns:
                df[name] = value
        return df

    def record_entity(self, entity: EntityRef, summary: RecordSummary) -> int:
        latest = self.get_latest_saved_timestamp(entity)
        start = self.evaluate_start(entity, latest)
        df = self.record(entity, start=start, end=self.end_timestamp)
        if df is None or df.empty:
            return 0
        return df_to_db(self.finalize(entity, df), self.data_schema, self.provider, force_update=True)

    def run(self) -> RecordSummary:
        entities = self.load_entities()
        summary = RecordSummary(schema=self.data_schema.__name__, provider=self.provider)
        for i, entity in enumerate(entities):
            try:
                summary.rows += self.record_entity(entity, summary)
                summary.entities += 1
            except Exception as e:  # one bad ticker must not stop the run
                summary.failed[entity.code] = f"{type(e).__name__}: {e}"
                self.logger.warning("%s: could not record %s: %s", self.data_schema.__name__, entity.id, e)
            if self.sleeping_time and i < len(entities) - 1:
                time.sleep(self.sleeping_time)
        summary.repairs = dict(self.repairs)
        self.logger.info(str(summary))
        return summary


class KdataRecorder(TimeSeriesRecorder):
    """Records bars.

    Providers restate history: after a split every earlier price changes, and for adjusted bars every
    dividend does the same. So each update re-fetches a few days that are already stored and compares.
    If they still agree, only the new bars are written. If not, the entity's history is replaced.
    """

    level = IntervalLevel.LEVEL_1DAY
    adjust_type = AdjustType.raw
    #: how many calendar days of stored history to fetch again and compare
    overlap_days = 10
    #: relative difference in close above which the stored history counts as restated
    restate_tolerance = 1e-4

    def generate_domain_id(self, entity: EntityRef, timestamp: pd.Timestamp) -> str:
        if self.level.intraday:
            return f"{entity.id}_{timestamp.strftime('%Y-%m-%dT%H:%M')}"
        return super().generate_domain_id(entity, timestamp)

    def full_start(self) -> pd.Timestamp:
        """Where a download from scratch begins."""
        return self.start_timestamp or to_pd_timestamp(self.default_start)

    def record_entity(self, entity: EntityRef, summary: RecordSummary) -> int:
        latest = self.get_latest_saved_timestamp(entity)
        full_start = self.full_start()

        if latest is None or self.force_update:
            df = self.record(entity, start=full_start, end=self.end_timestamp)
            return self._save(entity, df, replace=self.force_update and latest is not None)

        start = latest - pd.Timedelta(days=self.overlap_days)
        df = self.record(entity, start=start, end=self.end_timestamp)
        if df is None or df.empty:
            return 0
        if self._restated(entity, df, start, latest):
            self.logger.info("%s: history of %s was restated, downloading it again", self.data_schema.__name__, entity.id)
            summary.refreshed.append(entity.code)
            df = self.record(entity, start=full_start, end=self.end_timestamp)
            return self._save(entity, df, replace=True)
        return self._save(entity, df, replace=False, known_before=latest)

    def _restated(self, entity: EntityRef, fetched: pd.DataFrame, start: pd.Timestamp, latest: pd.Timestamp) -> bool:
        saved = get_data(
            self.data_schema,
            provider=self.provider,
            entity_id=entity.id,
            start_timestamp=start,
            columns=["timestamp", "close"],
        )
        # the newest stored bar may have been recorded before the close, so it is allowed to move
        saved = saved[saved["timestamp"] < latest].set_index("timestamp")["close"]
        new = fetched.assign(timestamp=pd.to_datetime(fetched["timestamp"])).set_index("timestamp")["close"]
        both = pd.concat([saved.rename("saved"), new.rename("new")], axis=1, join="inner").dropna()
        if both.empty:
            return False
        return bool(((both["new"] / both["saved"] - 1).abs() > self.restate_tolerance).any())

    def _save(self, entity: EntityRef, df: pd.DataFrame | None, replace: bool, known_before=None) -> int:
        if df is None or df.empty:
            return 0
        df = self.finalize(entity, df)
        df["level"] = self.level.value
        df = df.sort_values("timestamp")
        df["change_pct"] = df["close"].pct_change()
        if known_before is not None and df["timestamp"].iloc[0] <= known_before:
            # the first fetched bar is already stored; it is only there to compute the change of the next one
            df = df.iloc[1:]
        if replace and not self.level.intraday:
            # intraday history older than the provider keeps cannot be downloaded again, so it is never deleted
            delete_data(self.data_schema, self.provider, filters=[self.data_schema.entity_id == entity.id])
        return df_to_db(df, self.data_schema, self.provider, force_update=True)
