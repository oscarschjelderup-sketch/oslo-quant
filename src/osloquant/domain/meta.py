"""Tradable entities. Ids read ``{entity_type}_{exchange}_{code}``, e.g. ``stock_ol_EQNR``."""

from sqlalchemy import Column, String
from sqlalchemy.orm import DeclarativeBase

from osloquant.contract.register import register_schema
from osloquant.contract.schema import TradableEntity


class StockMetaBase(DeclarativeBase):
    pass


class Stock(StockMetaBase, TradableEntity):
    """A share listed on Oslo Børs."""

    __tablename__ = "stock"

    sector = Column(String(64))


class IndexMetaBase(DeclarativeBase):
    pass


class Index(IndexMetaBase, TradableEntity):
    """A market index. You cannot buy it, but you measure against it."""

    __tablename__ = "index"

    #: "price" or "total_return"; a total return index is the fair benchmark for adjusted stock prices
    category = Column(String(32))


class FutureMetaBase(DeclarativeBase):
    pass


class Future(FutureMetaBase, TradableEntity):
    """A continuous front-month futures contract, e.g. Brent."""

    __tablename__ = "future"


class CurrencyMetaBase(DeclarativeBase):
    pass


class Currency(CurrencyMetaBase, TradableEntity):
    """A currency pair, quoted as units of the second currency per unit of the first."""

    __tablename__ = "currency"


register_schema(providers=["yahoo"], db_name="stock_meta", schema_base=StockMetaBase)
register_schema(providers=["yahoo"], db_name="index_meta", schema_base=IndexMetaBase)
register_schema(providers=["yahoo"], db_name="future_meta", schema_base=FutureMetaBase)
register_schema(providers=["yahoo"], db_name="currency_meta", schema_base=CurrencyMetaBase)

__all__ = ["Currency", "Future", "Index", "Stock"]
