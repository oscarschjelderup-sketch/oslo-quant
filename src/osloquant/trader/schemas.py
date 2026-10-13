"""What a backtest leaves behind: the run, the account day by day, the holdings and the orders."""

from sqlalchemy import Column, DateTime, Float, String, Text
from sqlalchemy.orm import DeclarativeBase

from osloquant.contract.register import register_schema
from osloquant.contract.schema import Mixin


class TraderBase(DeclarativeBase):
    pass


class TraderInfo(TraderBase, Mixin):
    """One row per trader: how it was run."""

    __tablename__ = "trader_info"

    trader_name = Column(String(128), index=True)
    entity_type = Column(String(32))
    start_timestamp = Column(DateTime)
    end_timestamp = Column(DateTime)
    provider = Column(String(32))
    level = Column(String(32))
    kdata_adjust_type = Column(String(32))
    execution = Column(String(32))
    rebalance = Column(String(32))
    benchmark = Column(String(64))
    input_money = Column(Float)
    buy_cost = Column(Float)
    sell_cost = Column(Float)
    slippage = Column(Float)
    #: the smallest commission charged per order, in money
    min_cost = Column(Float)
    #: how many entities the trader chose from
    universe_size = Column(Float)
    #: "backtest" for a run over history, "live" for an account that is stepped forward day by day
    mode = Column(String(16))


class AccountStats(TraderBase, Mixin):
    """The account at each close."""

    __tablename__ = "account_stats"

    trader_name = Column(String(128), index=True)
    input_money = Column(Float)
    cash = Column(Float)
    #: market value of the holdings
    value = Column(Float)
    #: holdings plus cash
    all_value = Column(Float)
    profit = Column(Float)
    profit_rate = Column(Float)
    holdings = Column(Float)
    #: what the same money would be worth spread equally over the trader's whole universe, without costs
    universe_value = Column(Float)


class Position(TraderBase, Mixin):
    """Each holding at each close."""

    __tablename__ = "position"

    trader_name = Column(String(128), index=True)
    account_stats_id = Column(String, index=True)
    long_amount = Column(Float)
    average_long_price = Column(Float)
    value = Column(Float)
    profit = Column(Float)
    profit_rate = Column(Float)


class Order(TraderBase, Mixin):
    """Each fill, dividend and split. ``timestamp`` is the day it happened, ``signal_timestamp`` the day a fill was decided.

    For a live account ``decided_at`` is the wall-clock time (UTC) the decision was written down, and
    ``forward`` says whether that was before the market opened on the day of the fill. Only those fills
    are evidence: a decision logged after its fill could have been made with hindsight.
    """

    __tablename__ = "order"

    trader_name = Column(String(128), index=True)
    signal_timestamp = Column(DateTime)
    decided_at = Column(DateTime)
    #: 1 when decided_at was before the open of the fill day, 0 when not, empty for a backtest
    forward = Column(Float)
    #: order_long, order_close_long, order_short, order_close_short, dividend, split or financing
    order_type = Column(String(32))
    #: the fill price, after slippage
    order_price = Column(Float)
    order_amount = Column(Float)
    #: commission paid
    cost = Column(Float)
    #: for sells: what the round trip earned after all costs
    profit = Column(Float)
    profit_rate = Column(Float)
    status = Column(String(32))
    level = Column(String(32))
    #: for an intraday account: the signal that caused the order, in words
    reason = Column(String(256))


class LiveState(TraderBase, Mixin):
    """Where a live account stands after its last session: cash, holdings and the orders waiting for the next open.

    One row per account; ``timestamp`` is the last session processed. Everything else about the account is in
    the other tables, appended session by session and never rewritten.
    """

    __tablename__ = "live_state"

    trader_name = Column(String(128), index=True)
    #: JSON
    state = Column(Text)
    updated_at = Column(DateTime)


class IntradaySignal(TraderBase, Mixin):
    """Every signal an intraday account's rules raised, acted on or not. ``timestamp`` is the bar that raised it."""

    __tablename__ = "intraday_signal"

    trader_name = Column(String(128), index=True)
    #: BUY or SELL from the signal rule; STOP, TARGET, TRAIL or CLOSE from the risk rules
    code = Column(String(16))
    rule = Column(String(64))
    reason = Column(String(256))
    #: the close of the bar that raised the signal
    price = Column(Float)
    #: "ordered", or why not: "already held", "no free slot", ...
    outcome = Column(String(64))
    decided_at = Column(DateTime)


class IntradaySnapshot(TraderBase, Mixin):
    """An intraday account at each poll: what the value chart of the day is drawn from."""

    __tablename__ = "intraday_snapshot"

    trader_name = Column(String(128), index=True)
    cash = Column(Float)
    value = Column(Float)
    all_value = Column(Float)
    holdings = Column(Float)
    #: minutes between the look and the start of the newest bar the feed had: what the delay really was
    feed_lag = Column(Float)
    #: the gross value of the holdings, longs and shorts added, and that over the equity (a margin account)
    exposure = Column(Float)
    leverage = Column(Float)


register_schema(providers=["osloquant"], db_name="trader_info", schema_base=TraderBase)

__all__ = ["AccountStats", "IntradaySignal", "IntradaySnapshot", "LiveState", "Order", "Position", "TraderInfo"]
