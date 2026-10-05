"""Market quotes. Table names follow ``{Entity}{level}{Adj}Kdata``; "kdata" is a bar (K-line).

``Stock1dKdata``     daily bars as quoted
``Stock1dAdjKdata``  daily bars restated for splits and dividends: use these for returns and backtests
"""

from sqlalchemy import Column, Float, String
from sqlalchemy.orm import DeclarativeBase

from osloquant.contract import AdjustType, IntervalLevel
from osloquant.contract.register import register_kdata_schema, register_schema
from osloquant.contract.schema import Mixin
from osloquant.domain.meta import Currency, Future, Index, Stock


class KdataCommon(Mixin):
    provider = Column(String(32))
    code = Column(String(32), index=True)
    name = Column(String(128))
    level = Column(String(32))

    open = Column(Float)
    close = Column(Float)
    high = Column(Float)
    low = Column(Float)
    #: shares traded
    volume = Column(Float)
    #: value traded in the listing currency, as quoted close times volume
    turnover = Column(Float)
    #: close-to-close change
    change_pct = Column(Float)


class Stock1dKdataBase(DeclarativeBase):
    pass


class Stock1dKdata(Stock1dKdataBase, KdataCommon):
    __tablename__ = "stock_1d_kdata"


class Stock1dAdjKdataBase(DeclarativeBase):
    pass


class Stock1dAdjKdata(Stock1dAdjKdataBase, KdataCommon):
    __tablename__ = "stock_1d_adj_kdata"


class Stock15mKdataBase(DeclarativeBase):
    pass


class Stock15mKdata(Stock15mKdataBase, KdataCommon):
    """15-minute bars as quoted. ``timestamp`` is the start of the bar, in Oslo time."""

    __tablename__ = "stock_15m_kdata"


class Index1dKdataBase(DeclarativeBase):
    pass


class Index1dKdata(Index1dKdataBase, KdataCommon):
    __tablename__ = "index_1d_kdata"


class Future1dKdataBase(DeclarativeBase):
    pass


class Future1dKdata(Future1dKdataBase, KdataCommon):
    __tablename__ = "future_1d_kdata"


class Currency1dKdataBase(DeclarativeBase):
    pass


class Currency1dKdata(Currency1dKdataBase, KdataCommon):
    __tablename__ = "currency_1d_kdata"


_DAY = IntervalLevel.LEVEL_1DAY

register_schema(providers=["yahoo"], db_name="stock_1d_kdata", schema_base=Stock1dKdataBase)
register_schema(providers=["yahoo"], db_name="stock_1d_adj_kdata", schema_base=Stock1dAdjKdataBase)
register_schema(providers=["yahoo"], db_name="stock_15m_kdata", schema_base=Stock15mKdataBase)
register_schema(providers=["yahoo"], db_name="index_1d_kdata", schema_base=Index1dKdataBase)
register_schema(providers=["yahoo"], db_name="future_1d_kdata", schema_base=Future1dKdataBase)
register_schema(providers=["yahoo"], db_name="currency_1d_kdata", schema_base=Currency1dKdataBase)

register_kdata_schema(Stock1dAdjKdata, Stock, _DAY, AdjustType.adj, default=True)
register_kdata_schema(Stock1dKdata, Stock, _DAY, AdjustType.raw)
register_kdata_schema(Stock15mKdata, Stock, IntervalLevel.LEVEL_15MIN, AdjustType.raw)
register_kdata_schema(Index1dKdata, Index, _DAY, AdjustType.raw)
register_kdata_schema(Future1dKdata, Future, _DAY, AdjustType.raw)
register_kdata_schema(Currency1dKdata, Currency, _DAY, AdjustType.raw)

__all__ = ["Currency1dKdata", "Future1dKdata", "Index1dKdata", "KdataCommon", "Stock1dAdjKdata", "Stock1dKdata", "Stock15mKdata"]
