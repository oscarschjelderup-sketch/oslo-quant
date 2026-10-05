"""Backtesting: a trader turns factor targets into signals, a simulated account fills them."""

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from osloquant.contract import IntervalLevel


class TradingSignalType(Enum):
    open_long = "open_long"
    close_long = "close_long"


class OrderType(Enum):
    order_long = "order_long"
    order_close_long = "order_close_long"


@dataclass
class TradingSignal:
    entity_id: str
    #: when the decision was made (the bar whose close it is based on)
    happen_timestamp: pd.Timestamp
    #: the first bar it may be filled on
    due_timestamp: pd.Timestamp | None
    trading_signal_type: TradingSignalType
    trading_level: IntervalLevel = IntervalLevel.LEVEL_1DAY
    #: for buys, the share of the account's total value to put in; for sells, the share of the holding to sell
    position_pct: float | None = None
    order_money: float | None = None
    order_amount: float | None = None
    #: for a live account: the wall-clock time (UTC) the decision was written down
    decided_at: pd.Timestamp | None = None


from osloquant.trader.schemas import AccountStats, Order, Position, TraderInfo  # noqa: E402
from osloquant.trader.sim_account import SimAccount  # noqa: E402
from osloquant.trader.stats import get_trader_stats  # noqa: E402
from osloquant.trader.trader import StockTrader, Trader  # noqa: E402

__all__ = [
    "AccountStats",
    "Order",
    "OrderType",
    "Position",
    "SimAccount",
    "StockTrader",
    "Trader",
    "TraderInfo",
    "TradingSignal",
    "TradingSignalType",
    "get_trader_stats",
]
