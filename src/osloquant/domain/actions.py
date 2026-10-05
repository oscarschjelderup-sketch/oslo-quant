"""Corporate actions: what happens to a shareholder on a given day without any trade.

An account that holds real shares at real prices needs these. On the ex-date of a dividend the price drops and
the cash arrives; on the day of a split the number of shares changes and the price with it. Adjusted bars
fold both into the prices instead, which is right for returns and signals but not for a ledger of holdings.
"""

from sqlalchemy import Column, Float, String
from sqlalchemy.orm import DeclarativeBase

from osloquant.contract.register import register_schema
from osloquant.contract.schema import Mixin


class StockActionBase(DeclarativeBase):
    pass


class StockAction(StockActionBase, Mixin):
    """One row per stock and day with a dividend or a split. ``timestamp`` is the ex-date."""

    __tablename__ = "stock_action"

    provider = Column(String(32))
    code = Column(String(32), index=True)
    name = Column(String(128))
    #: cash per share, in the listing currency; 0 when the day only has a split
    dividend = Column(Float)
    #: new shares per old share: 2 for a 2:1 split, 0.5 for a 1:2 reverse split; 0 when the day only has a dividend
    split = Column(Float)


register_schema(providers=["yahoo"], db_name="stock_action", schema_base=StockActionBase)

__all__ = ["StockAction"]
