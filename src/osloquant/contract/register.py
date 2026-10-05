"""Signing schemas into the registry."""

from __future__ import annotations

from osloquant.contract.context import context
from osloquant.contract.schema import TradableEntity


def register_schema(providers: list[str], db_name: str, schema_base: type) -> None:
    """Register every table of ``schema_base`` as living in ``db_name`` and served by ``providers``."""
    context.db_schema_base[db_name] = schema_base
    for mapper in schema_base.registry.mappers:
        schema = mapper.class_
        if schema in context.schema_db_name:
            continue
        context.schemas.append(schema)
        context.schema_db_name[schema] = db_name
        context.schema_providers[schema] = list(providers)
        context.schema_recorders.setdefault(schema, {})
        if issubclass(schema, TradableEntity):
            context.tradable_schema_map[schema.__name__.lower()] = schema


def register_kdata_schema(schema: type, entity_schema: type, level, adjust_type, default: bool = False) -> None:
    """Tell the registry which bars a kdata table holds, so ``get_kdata_schema`` can find it."""
    from osloquant.contract import AdjustType, IntervalLevel

    entity_type = entity_schema.__name__.lower()
    level = IntervalLevel(level)
    adjust_type = AdjustType(adjust_type)
    schema.entity_schema = entity_schema
    schema.level = level
    schema.adjust_type = adjust_type
    context.kdata_schema_map[(entity_type, level.value, adjust_type.value)] = schema
    if default or entity_type not in context.default_adjust_type:
        context.default_adjust_type[entity_type] = adjust_type.value
