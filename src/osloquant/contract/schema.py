"""The two things every table has in common: how it is recorded and how it is queried.

``Schema.record_data(provider=...)`` fetches from a provider and stores locally, incrementally.
``Schema.query_data(...)`` reads it back as a DataFrame. Nothing else is needed to use a table.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Column, DateTime, String

from osloquant.contract.context import context


class Mixin:
    """Columns and class methods shared by every schema."""

    #: unique per row; recording the same row again overwrites it
    id = Column(String, primary_key=True)
    #: which entity the row is about, e.g. stock_ol_EQNR
    entity_id = Column(String, index=True)
    #: when the row became known
    timestamp = Column(DateTime, index=True)

    @classmethod
    def help(cls) -> None:
        print(f"{cls.__name__}  (table {cls.__tablename__}, providers {cls.get_providers()})")
        for column in cls.__table__.columns:
            print(f"  {column.name:<28}{column.type}")

    @classmethod
    def important_cols(cls) -> list[str]:
        return [c.name for c in cls.__table__.columns]

    @classmethod
    def get_providers(cls) -> list[str]:
        return list(context.schema_providers.get(cls, []))

    @classmethod
    def default_provider(cls) -> str:
        providers = cls.get_providers()
        if not providers:
            raise LookupError(f"{cls.__name__} is not registered with any provider")
        return providers[0]

    @classmethod
    def provider_map_recorder(cls) -> dict[str, type]:
        return dict(context.schema_recorders.get(cls, {}))

    @classmethod
    def record_data(cls, provider: str | None = None, **kwargs):
        """Fetch from ``provider`` and store locally. Only what is missing is fetched.

        Common keyword arguments: ``code`` / ``codes`` / ``entity_ids`` to limit the entities,
        ``force_update`` to re-download from scratch, ``sleeping_time`` between requests.
        """
        recorders = context.schema_recorders.get(cls) or {}
        if not recorders:
            raise LookupError(f"no recorder is registered for {cls.__name__}")
        if provider is None:
            provider = next((p for p in cls.get_providers() if p in recorders), next(iter(recorders)))
        if provider not in recorders:
            raise LookupError(f"{cls.__name__} has no recorder for provider {provider!r}; available: {list(recorders)}")
        return recorders[provider](**kwargs).run()

    @classmethod
    def query_data(cls, **kwargs):
        """Read stored rows. See :func:`osloquant.contract.api.get_data` for the arguments."""
        from osloquant.contract.api import get_data

        return get_data(data_schema=cls, **kwargs)


class TradableEntity(Mixin):
    """Something you can hold or watch: a stock, an index, a future, a currency pair."""

    entity_type = Column(String(32))
    exchange = Column(String(32))
    code = Column(String(32), index=True)
    name = Column(String(128))
    #: the ticker the data provider knows it by
    symbol = Column(String(32))
    list_date = Column(DateTime)
    end_date = Column(DateTime)


@dataclass(frozen=True)
class EntityRef:
    """What a recorder needs to know about an entity."""

    id: str
    entity_type: str
    exchange: str
    code: str
    name: str | None = None
    symbol: str | None = None
