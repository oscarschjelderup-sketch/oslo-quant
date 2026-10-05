"""One SQLite file per (provider, database). Writing is an upsert on ``id``, so recording twice is harmless."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import Engine, create_engine, delete, inspect, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from osloquant.contract.context import context

_engines: dict[tuple[str, str, str], Engine] = {}


def get_engine(provider: str, db_name: str | None = None, data_schema: type | None = None) -> Engine:
    from osloquant.env import data_path

    if db_name is None:
        db_name = context.schema_db_name[data_schema]
    folder = data_path()
    key = (str(folder), provider, db_name)
    engine = _engines.get(key)
    if engine is None:
        db_file = folder / f"{provider}_{db_name}.db"
        engine = create_engine(f"sqlite:///{db_file.as_posix()}")
        metadata = context.db_schema_base[db_name].metadata
        metadata.create_all(engine)
        _add_missing_columns(engine, metadata)
        _engines[key] = engine
    return engine


def _add_missing_columns(engine: Engine, metadata) -> None:
    """A store written by an older version lacks the columns added since. Add them, empty."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    column_type = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'))


def get_session(provider: str, db_name: str | None = None, data_schema: type | None = None) -> Session:
    return Session(get_engine(provider, db_name=db_name, data_schema=data_schema))


def dispose_engines() -> None:
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


def _to_records(df: pd.DataFrame) -> list[dict]:
    # object dtype turns numpy scalars into Python ones, which is what the SQLite driver wants
    return df.astype(object).where(df.notna(), None).to_dict("records")


def df_to_db(df: pd.DataFrame, data_schema: type, provider: str, force_update: bool = True, chunk: int = 500) -> int:
    """Upsert ``df`` into the table of ``data_schema``. Returns the number of rows written."""
    if df is None or df.empty:
        return 0
    table = data_schema.__table__
    columns = [c.name for c in table.columns if c.name in df.columns]
    if "id" not in columns:
        raise ValueError(f"{data_schema.__name__}: the frame has no 'id' column")
    df = df[columns].drop_duplicates(subset="id", keep="last")

    stmt = sqlite_insert(table)
    if force_update and len(columns) > 1:
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_={c: stmt.excluded[c] for c in columns if c != "id"}
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])

    records = _to_records(df)
    with get_engine(provider, data_schema=data_schema).begin() as conn:
        for i in range(0, len(records), chunk):
            conn.execute(stmt, records[i : i + chunk])
    return len(records)


def delete_data(data_schema: type, provider: str, filters: list | None = None) -> int:
    stmt = delete(data_schema.__table__)
    for f in filters or []:
        stmt = stmt.where(f)
    with get_engine(provider, data_schema=data_schema).begin() as conn:
        return conn.execute(stmt).rowcount
