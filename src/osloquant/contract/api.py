"""Reading stored data. Every schema is queried the same way."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from sqlalchemy import DateTime, func, select

from osloquant.contract import AdjustType, IntervalLevel
from osloquant.contract.context import context
from osloquant.contract.schema import EntityRef
from osloquant.contract.storage import get_session


def to_pd_timestamp(value) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts


def encode_entity_id(entity_type: str, exchange: str, code: str) -> str:
    return f"{entity_type}_{exchange}_{code}"


def decode_entity_id(entity_id: str) -> tuple[str, str, str]:
    """stock_ol_EQNR -> ("stock", "ol", "EQNR")"""
    entity_type, exchange, code = entity_id.split("_", 2)
    return entity_type, exchange, code


def get_data(
    data_schema: type,
    provider: str | None = None,
    ids: Iterable[str] | None = None,
    entity_ids: Iterable[str] | None = None,
    entity_id: str | None = None,
    codes: Iterable[str] | None = None,
    code: str | None = None,
    columns: list | None = None,
    return_type: str = "df",
    start_timestamp=None,
    end_timestamp=None,
    filters: list | None = None,
    order=None,
    limit: int | None = None,
    index: str | list[str] | None = None,
    drop_index_col: bool = False,
    time_field: str = "timestamp",
):
    """Query one schema.

    :param columns: column names or column objects; all columns when omitted
    :param return_type: "df" for a DataFrame, "dict" for a list of dicts, "domain" for ORM objects
    :param filters: extra SQLAlchemy conditions, e.g. ``[FinanceFactor.roe > 0.1]``
    :param order: an SQLAlchemy ordering, e.g. ``FinanceFactor.roe.desc()``; by time when omitted
    :param index: column(s) to index the DataFrame by; ``["entity_id", "timestamp"]`` gives the
        two-dimensional index the factors work on
    """
    provider = provider or data_schema.default_provider()
    time_col = getattr(data_schema, time_field)

    if return_type == "domain":
        stmt = select(data_schema)
    elif columns:
        cols = [getattr(data_schema, c) if isinstance(c, str) else c for c in columns]
        stmt = select(*cols)
    else:
        stmt = select(data_schema.__table__)

    if entity_id is not None:
        stmt = stmt.where(data_schema.entity_id == entity_id)
    if entity_ids is not None:
        stmt = stmt.where(data_schema.entity_id.in_(list(entity_ids)))
    if code is not None:
        stmt = stmt.where(data_schema.code == code)
    if codes is not None:
        stmt = stmt.where(data_schema.code.in_(list(codes)))
    if ids is not None:
        stmt = stmt.where(data_schema.id.in_(list(ids)))
    if start_timestamp is not None:
        stmt = stmt.where(time_col >= to_pd_timestamp(start_timestamp).to_pydatetime())
    if end_timestamp is not None:
        stmt = stmt.where(time_col <= to_pd_timestamp(end_timestamp).to_pydatetime())
    for f in filters or []:
        stmt = stmt.where(f)

    stmt = stmt.order_by(order if order is not None else time_col.asc())
    if limit:
        stmt = stmt.limit(limit)

    with get_session(provider, data_schema=data_schema) as session:
        if return_type == "domain":
            rows = list(session.scalars(stmt).all())
            session.expunge_all()
            return rows
        result = session.execute(stmt)
        keys = list(result.keys())
        rows = result.all()

    df = pd.DataFrame([tuple(r) for r in rows], columns=keys)
    for column in data_schema.__table__.columns:
        if column.name in df.columns and isinstance(column.type, DateTime):
            df[column.name] = pd.to_datetime(df[column.name])

    if return_type == "dict":
        return df.astype(object).where(df.notna(), None).to_dict("records")
    if index is not None and not df.empty:
        df = df.set_index(index, drop=drop_index_col).sort_index()
    elif index is not None:
        df = df.set_index(index, drop=drop_index_col)
    return df


def get_entity_schema(entity_type: str) -> type:
    try:
        return context.tradable_schema_map[entity_type]
    except KeyError:
        raise KeyError(f"unknown entity type {entity_type!r}; known: {sorted(context.tradable_schema_map)}") from None


def get_entities(entity_schema: type | None = None, entity_type: str | None = None, **kwargs) -> pd.DataFrame:
    if entity_schema is None:
        entity_schema = get_entity_schema(entity_type)
    kwargs.setdefault("order", entity_schema.code.asc())
    return get_data(data_schema=entity_schema, **kwargs)


def get_entity_refs(entity_schema: type, **kwargs) -> list[EntityRef]:
    df = get_entities(entity_schema=entity_schema, **kwargs)
    return [
        EntityRef(id=r.id, entity_type=r.entity_type, exchange=r.exchange, code=r.code, name=r.name, symbol=r.symbol)
        for r in df.itertuples()
    ]


def get_entity_ids(entity_schema: type | None = None, entity_type: str | None = None, **kwargs) -> list[str]:
    df = get_entities(entity_schema=entity_schema, entity_type=entity_type, columns=["entity_id"], **kwargs)
    return df["entity_id"].tolist()


def get_kdata_schema(entity_type: str | type = "stock", level=IntervalLevel.LEVEL_1DAY, adjust_type=None) -> type:
    """The table holding bars of ``level`` and ``adjust_type`` for an entity type.

    Without ``adjust_type`` the entity type's default is used: adjusted for stocks, raw for the rest.
    """
    if not isinstance(entity_type, str):
        entity_type = entity_type.__name__.lower()
    level = IntervalLevel(level)
    if adjust_type is None:
        adjust_type = context.default_adjust_type.get(entity_type, AdjustType.raw.value)
    adjust_type = AdjustType(adjust_type)
    try:
        return context.kdata_schema_map[(entity_type, level.value, adjust_type.value)]
    except KeyError:
        raise KeyError(f"no kdata schema for {entity_type} {level.value} {adjust_type.value}") from None


def get_kdata(
    entity_id: str | None = None,
    entity_ids: Iterable[str] | None = None,
    level=IntervalLevel.LEVEL_1DAY,
    adjust_type=None,
    **kwargs,
) -> pd.DataFrame:
    """Bars for one or several entities of the same type."""
    first = entity_id if entity_id is not None else next(iter(entity_ids))
    entity_type, _, _ = decode_entity_id(first)
    schema = get_kdata_schema(entity_type, level=level, adjust_type=adjust_type)
    return get_data(data_schema=schema, entity_id=entity_id, entity_ids=entity_ids, **kwargs)


def get_data_count(data_schema: type, provider: str | None = None, filters: list | None = None) -> int:
    provider = provider or data_schema.default_provider()
    stmt = select(func.count()).select_from(data_schema.__table__)
    for f in filters or []:
        stmt = stmt.where(f)
    with get_session(provider, data_schema=data_schema) as session:
        return session.execute(stmt).scalar_one()


def get_coverage(data_schema: type, provider: str | None = None) -> dict:
    """Rows, entities and first/last timestamp of a table. Used by ``oq status`` and the dashboard."""
    provider = provider or data_schema.default_provider()
    table = data_schema.__table__
    stmt = select(
        func.count(), func.count(func.distinct(table.c.entity_id)), func.min(table.c.timestamp), func.max(table.c.timestamp)
    ).select_from(table)
    with get_session(provider, data_schema=data_schema) as session:
        rows, entities, first, last = session.execute(stmt).one()
    return {
        "schema": data_schema.__name__,
        "provider": provider,
        "rows": rows,
        "entities": entities,
        "first": to_pd_timestamp(first),
        "last": to_pd_timestamp(last),
    }
