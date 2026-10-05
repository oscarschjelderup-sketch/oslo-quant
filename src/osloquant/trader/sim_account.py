"""A simulated long-only cash account.

Fills are whole shares at the given price plus slippage, commission is charged on the traded value (with an
optional minimum per order), and nothing is bought with money that is not there. The account is kept in
memory during a run and written to the trader tables at the end.

An account on real (unadjusted) prices also receives dividends as cash and has its share counts changed by
splits. Its state can be saved and restored, which is how a live account is stepped forward one day at a time.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass

import pandas as pd

from osloquant.contract import IntervalLevel
from osloquant.contract.storage import delete_data, df_to_db
from osloquant.trader.schemas import AccountStats, Order, Position

logger = logging.getLogger(__name__)

PROVIDER = "osloquant"

#: the order types that are trades; the others (dividend, split) are things that happen to a holding
TRADES = ("order_long", "order_close_long")


@dataclass
class Holding:
    entity_id: str
    amount: float = 0.0
    #: average fill price
    average_price: float = 0.0
    #: everything paid for the shares held, commission included
    cost: float = 0.0
    last_price: float = 0.0
    profit_rate: float = 0.0


class SimAccount:
    def __init__(
        self,
        trader_name: str,
        input_money: float = 1_000_000,
        buy_cost: float = 0.0005,
        sell_cost: float = 0.0005,
        slippage: float = 0.001,
        min_cost: float = 0.0,
        level: IntervalLevel = IntervalLevel.LEVEL_1DAY,
    ) -> None:
        """
        :param buy_cost: commission on a buy, as a share of the traded value
        :param min_cost: the smallest commission per order, in money; what makes small orders expensive
        """
        self.trader_name = trader_name
        self.input_money = float(input_money)
        self.buy_cost, self.sell_cost, self.slippage, self.min_cost = buy_cost, sell_cost, slippage, min_cost
        self.level = level

        self.cash = float(input_money)
        #: value of holdings plus cash at the last close
        self.all_value = float(input_money)
        self.holdings: dict[str, Holding] = {}

        #: orders recorded before this object existed (a restored live account continues the numbering)
        self._order_offset = 0
        self._orders: list[dict] = []
        self._stats: list[dict] = []
        self._positions: list[dict] = []

    # -- trading ----------------------------------------------------------------------------------

    def commission(self, value: float, rate: float) -> float:
        return max(self.min_cost, value * rate) if value > 0 else 0.0

    def buy(self, entity_id: str, price: float, timestamp: pd.Timestamp, money: float, signal_timestamp=None, **log) -> float:
        """Buy for at most ``money`` (and at most the cash at hand), commission included. Returns the shares bought."""
        fill = price * (1 + self.slippage)
        budget = min(money, self.cash)
        if fill <= 0 or budget <= self.min_cost:
            return 0.0
        # whichever binds: the percentage commission or the minimum one
        amount = min(math.floor(budget / (fill * (1 + self.buy_cost))), math.floor((budget - self.min_cost) / fill))
        if amount < 1:
            logger.debug("%s: no money to buy %s at %s", self.trader_name, entity_id, timestamp)
            return 0.0
        commission = self.commission(amount * fill, self.buy_cost)
        paid = amount * fill + commission
        self.cash -= paid

        holding = self.holdings.setdefault(entity_id, Holding(entity_id=entity_id))
        holding.average_price = (holding.amount * holding.average_price + amount * fill) / (holding.amount + amount)
        holding.amount += amount
        holding.cost += paid
        holding.last_price = price
        self._record_order(entity_id, timestamp, signal_timestamp, "order_long", fill, amount, cost=commission, **log)
        return float(amount)

    def sell(self, entity_id: str, price: float, timestamp: pd.Timestamp, pct: float = 1.0, signal_timestamp=None, **log) -> float:
        """Sell ``pct`` of the holding. Returns the shares sold, 0 if there is nothing to sell."""
        holding = self.holdings.get(entity_id)
        if holding is None or holding.amount <= 0:
            return 0.0
        amount = holding.amount if pct >= 1 else math.floor(holding.amount * pct)
        if amount < 1:
            return 0.0
        fill = price * (1 - self.slippage)
        commission = self.commission(amount * fill, self.sell_cost)
        proceeds = amount * fill - commission
        cost_share = holding.cost * amount / holding.amount
        self.cash += proceeds

        holding.amount -= amount
        holding.cost -= cost_share
        if holding.amount <= 0:
            del self.holdings[entity_id]
        self._record_order(
            entity_id,
            timestamp,
            signal_timestamp,
            "order_close_long",
            fill,
            amount,
            cost=commission,
            profit=proceeds - cost_share,
            profit_rate=(proceeds - cost_share) / cost_share if cost_share else None,
            **log,
        )
        return float(amount)

    def receive_dividend(self, entity_id: str, per_share: float, timestamp: pd.Timestamp) -> float:
        """Cash for a holding on its ex-date. Returns the amount received."""
        holding = self.holdings.get(entity_id)
        if holding is None or holding.amount <= 0 or per_share <= 0:
            return 0.0
        received = holding.amount * per_share
        self.cash += received
        self._record_order(entity_id, timestamp, None, "dividend", per_share, holding.amount, cost=0.0, profit=received)
        return received

    def apply_split(self, entity_id: str, ratio: float, timestamp: pd.Timestamp) -> None:
        """``ratio`` new shares per old one. The holding is worth the same before and after."""
        holding = self.holdings.get(entity_id)
        if holding is None or holding.amount <= 0 or ratio <= 0 or ratio == 1:
            return
        exact = holding.amount * ratio
        whole = math.floor(exact + 1e-9)
        holding.average_price /= ratio
        holding.last_price /= ratio
        # a fraction of a share left over by a reverse split is paid out in cash
        self.cash += (exact - whole) * holding.last_price
        holding.cost *= whole / exact
        holding.amount = whole
        self._record_order(entity_id, timestamp, None, "split", ratio, holding.amount, cost=0.0)
        if holding.amount <= 0:
            del self.holdings[entity_id]

    def _record_order(
        self, entity_id, timestamp, signal_timestamp, order_type, price, amount, cost, profit=None, profit_rate=None, decided_at=None, forward=None, reason=None
    ):
        self._orders.append(
            {
                "id": f"{self.trader_name}_{self._order_offset + len(self._orders):07d}",
                "entity_id": entity_id,
                "timestamp": timestamp,
                "trader_name": self.trader_name,
                "signal_timestamp": signal_timestamp,
                "decided_at": decided_at,
                "forward": forward,
                "order_type": order_type,
                "order_price": price,
                "order_amount": amount,
                "cost": cost,
                "profit": profit,
                "profit_rate": profit_rate,
                "status": "success",
                "level": self.level.value,
                "reason": reason,
            }
        )

    # -- valuation --------------------------------------------------------------------------------

    def mark(self, close_prices) -> float:
        """Mark the holdings to ``close_prices`` (entity_id -> close; a missing price keeps the last one)."""
        value = 0.0
        for holding in self.holdings.values():
            price = close_prices.get(holding.entity_id)
            if price is not None and price == price and price > 0:
                holding.last_price = float(price)
            holding.profit_rate = holding.last_price / holding.average_price - 1 if holding.average_price else 0.0
            value += holding.amount * holding.last_price
        self.all_value = value + self.cash
        return value

    def on_trading_close(self, timestamp: pd.Timestamp, close_prices, universe_value: float | None = None) -> None:
        """Mark to the close and write the day into the account's history."""
        date = timestamp.strftime("%Y-%m-%d")
        stats_id = f"{self.trader_name}_{date}"
        self.mark(close_prices)
        for holding in self.holdings.values():
            holding_value = holding.amount * holding.last_price
            self._positions.append(
                {
                    "id": f"{self.trader_name}_{holding.entity_id}_{date}",
                    "entity_id": holding.entity_id,
                    "timestamp": timestamp,
                    "trader_name": self.trader_name,
                    "account_stats_id": stats_id,
                    "long_amount": holding.amount,
                    "average_long_price": holding.average_price,
                    "value": holding_value,
                    "profit": holding_value - holding.cost,
                    "profit_rate": holding.profit_rate,
                }
            )
        self._stats.append(self.day_row(timestamp, universe_value=universe_value))

    def day_row(self, timestamp: pd.Timestamp, universe_value: float | None = None) -> dict:
        """The account as it stands, as a row of ``AccountStats`` for the day of ``timestamp``. Call ``mark`` first."""
        day = timestamp.normalize()
        return {
            "id": f"{self.trader_name}_{day:%Y-%m-%d}",
            "entity_id": self.trader_name,
            "timestamp": day,
            "trader_name": self.trader_name,
            "input_money": self.input_money,
            "cash": self.cash,
            "value": self.all_value - self.cash,
            "all_value": self.all_value,
            "profit": self.all_value - self.input_money,
            "profit_rate": self.all_value / self.input_money - 1,
            "holdings": float(len(self.holdings)),
            "universe_value": universe_value,
        }

    # -- state ------------------------------------------------------------------------------------

    def to_state(self) -> dict:
        """Everything needed to carry on tomorrow, as plain values."""
        return {
            "cash": self.cash,
            "all_value": self.all_value,
            "orders_recorded": self._order_offset + len(self._orders),
            "holdings": [asdict(h) for h in self.holdings.values()],
        }

    def restore(self, state: dict) -> None:
        self.cash = float(state["cash"])
        self.all_value = float(state["all_value"])
        self._order_offset = int(state["orders_recorded"])
        self.holdings = {h["entity_id"]: Holding(**h) for h in state["holdings"]}

    # -- results ----------------------------------------------------------------------------------

    @property
    def stats_df(self) -> pd.DataFrame:
        return pd.DataFrame(self._stats)

    @property
    def orders_df(self) -> pd.DataFrame:
        return pd.DataFrame(self._orders)

    @property
    def positions_df(self) -> pd.DataFrame:
        return pd.DataFrame(self._positions)

    def persist(self, append: bool = False) -> None:
        """Write the run. A backtest replaces what an earlier run of the same trader stored; a live account appends."""
        for schema, df in ((AccountStats, self.stats_df), (Position, self.positions_df), (Order, self.orders_df)):
            if not append:
                delete_data(schema, PROVIDER, filters=[schema.trader_name == self.trader_name])
            df_to_db(df, schema, PROVIDER)
