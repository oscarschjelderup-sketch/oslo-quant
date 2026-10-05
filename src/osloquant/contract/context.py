"""The registry every schema, recorder and factor signs into when its module is imported."""

from __future__ import annotations


class Registry:
    def __init__(self) -> None:
        #: every data schema (table)
        self.schemas: list[type] = []
        #: entity type ("stock", "index", ...) -> entity schema
        self.tradable_schema_map: dict[str, type] = {}
        #: schema -> name of the database it lives in
        self.schema_db_name: dict[type, str] = {}
        #: database name -> declarative base holding its tables
        self.db_schema_base: dict[str, type] = {}
        #: schema -> providers, the first one is the default
        self.schema_providers: dict[type, list[str]] = {}
        #: schema -> {provider: recorder class}
        self.schema_recorders: dict[type, dict[str, type]] = {}
        #: (entity type, level, adjust type) -> kdata schema
        self.kdata_schema_map: dict[tuple[str, str, str], type] = {}
        #: entity type -> adjust type used when none is asked for
        self.default_adjust_type: dict[str, str] = {}
        #: factor class name -> factor class
        self.factor_cls_registry: dict[str, type] = {}

    def schema_by_name(self, name: str) -> type:
        for schema in self.schemas:
            if schema.__name__.lower() == name.lower():
                return schema
        known = ", ".join(sorted(s.__name__ for s in self.schemas))
        raise KeyError(f"unknown schema {name!r}; known schemas: {known}")


context = Registry()
