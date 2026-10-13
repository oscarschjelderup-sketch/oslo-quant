"""A simulated account: long-only on cash by default, a margin account with shorts and leverage when asked.

Fills are whole shares at the given price plus slippage, commission is charged on the traded value (with an
optional minimum per order), and a cash account buys nothing with money that is not there. The account is kept
in memory during a run and written to the trader tables at the end.

An account on real (unadjusted) prices also receives dividends as cash and has its share counts changed by
splits. Its state can be saved and restored, which is how a live account is stepped forward one day at a time.

With ``max_leverage`` above 1 the account is a margin account: it may borrow cash to buy (``cash`` goes negative,
interest is charged on it), and it may sell shares it does not own (a holding with a negative ``amount``; a borrow
fee is charged on what is short). Equity is cash plus the net value of the holdings, exposure is the gross value
of the holdings, and leverage is their ratio. The caller sizes each order inside ``buying_power`` and decides when
equity has fallen too far; the account only books what it is told.
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

#: the order types that are trades; the others (dividend, split, financing) are things that happen to a holding
TRADES = ("order_long", "order_close_long", "order_short", "order_close_short")
#: the trades that close a position: a round trip ends with one of these
CLOSES = ("order_close_long", "order_close_short")
#: the trades that open one
OPENS = ("order_long", "order_short")
DAYS_PER_YEAR = 365.0


@dataclass
class Holding:
    entity_id: str
    #: shares held; negative for a short position
    amount: float = 0.0
    #: average fill price
    average_price: float = 0.0
    #: long: everything paid for the shares held, commission included. Short: the proceeds kept, net of commission
    cost: float = 0.0
    last_price: float = 0.0
    #: the position's gain as a share of its entry price; for a short, a falling price is a gain
    profit_rate: float = 0.0

    @property
    def side(self) -> str:
        return "short" if self.amount < 0 else "long"

    @property
    def shares(self) -> float:
        return abs(self.amount)

    @property
    def value(self) -> float:
        """The position's net value: negative for a short, which is a liability."""
        return self.amount * self.last_price


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
        max_leverage: float = 1.0,
        financing_rate: float = 0.06,
        borrow_rate: float = 0.03,
    ) -> None:
        """
        :param buy_cost: commission on a buy, as a share of the traded value
        :param min_cost: the smallest commission per order, in money; what makes small orders expensive
        :param max_leverage: gross exposure may reach this many times equity; 1 is a plain cash account
        :param financing_rate: yearly interest on borrowed cash (negative ``cash``)
        :param borrow_rate: yearly fee on the value of what is sold short
        """
        if max_leverage < 1:
            raise ValueError("max_leverage is at least 1 (a cash account)")
        self.trader_name = trader_name
        self.input_money = float(input_money)
        self.buy_cost, self.sell_cost, self.slippage, self.min_cost = buy_cost, sell_cost, slippage, min_cost
        self.level = level
        self.max_leverage = float(max_leverage)
        self.financing_rate, self.borrow_rate = float(financing_rate), float(borrow_rate)

        self.cash = float(input_money)
        #: equity: value of holdings (net of shorts) plus cash at the last mark
        self.all_value = float(input_money)
        self.holdings: dict[str, Holding] = {}

        #: orders recorded before this object existed (a restored live account continues the numbering)
        self._order_offset = 0
        self._orders: list[dict] = []
        self._stats: list[dict] = []
        self._positions: list[dict] = []

    # -- margin -----------------------------------------------------------------------------------

    @property
    def margin(self) -> bool:
        """Whether this account may borrow: buy beyond its cash, or sell short."""
        return self.max_leverage > 1

    @property
    def exposure(self) -> float:
        """The gross value of the holdings at their last prices, longs and shorts added together."""
        return sum(abs(h.amount) * h.last_price for h in self.holdings.values())

    @property
    def short_exposure(self) -> float:
        return sum(-h.amount * h.last_price for h in self.holdings.values() if h.amount < 0)

    @property
    def leverage(self) -> float:
        """Exposure over equity; 0 with nothing held, infinite with no equity left."""
        if not self.holdings:
            return 0.0
        return self.exposure / self.all_value if self.all_value > 0 else math.inf

    @property
    def buying_power(self) -> float:
        """How much more gross exposure the account may take on. A cash account: its cash."""
        if not self.margin:
            return max(self.cash, 0.0)
        return max(self.all_value * self.max_leverage - self.exposure, 0.0)

    def charge_financing(self, days: float, timestamp: pd.Timestamp) -> float:
        """Interest on borrowed cash and the borrow fee on shorts for ``days`` calendar days. Returns the charge."""
        if days <= 0:
            return 0.0
        borrowed = max(-self.cash, 0.0)
        charge = (borrowed * self.financing_rate + self.short_exposure * self.borrow_rate) * days / DAYS_PER_YEAR
        if charge <= 0:
            return 0.0
        self.cash -= charge
        self._record_order("", timestamp, None, "financing", 0.0, days, cost=charge, profit=-charge)
        return charge

    # -- trading ----------------------------------------------------------------------------------

    def commission(self, value: float, rate: float) -> float:
        return max(self.min_cost, value * rate) if value > 0 else 0.0

    def buy(
        self, entity_id: str, price: float, timestamp: pd.Timestamp, money: float, signal_timestamp=None, **log
    ) -> float:
        """Buy for at most ``money``, commission included. A cash account also stops at the cash at hand; a margin
        account stops at its buying power. Returns the shares bought."""
        fill = price * (1 + self.slippage)
        budget = min(money, self.buying_power)
        if fill <= 0 or budget <= self.min_cost:
            return 0.0
        # whichever binds: the percentage commission or the minimum one
        # a hair of rounding (5 000 x 6.4 is not quite 32 000) must not cost a share
        amount = min(math.floor(budget / (fill * (1 + self.buy_cost)) + 1e-9), math.floor((budget - self.min_cost) / fill + 1e-9))
        if amount < 1:
            logger.debug("%s: no money to buy %s at %s", self.trader_name, entity_id, timestamp)
            return 0.0
        commission = self.commission(amount * fill, self.buy_cost)
        paid = amount * fill + commission
        self.cash -= paid

        holding = self.holdings.setdefault(entity_id, Holding(entity_id=entity_id))
        if holding.amount < 0:
            raise ValueError(f"{entity_id} is short; cover it before buying")
        holding.average_price = (holding.amount * holding.average_price + amount * fill) / (holding.amount + amount)
        holding.amount += amount
        holding.cost += paid
        holding.last_price = price
        self._record_order(entity_id, timestamp, signal_timestamp, "order_long", fill, amount, cost=commission, **log)
        return float(amount)

    def sell(
        self, entity_id: str, price: float, timestamp: pd.Timestamp, pct: float = 1.0, signal_timestamp=None, **log
    ) -> float:
        """Sell ``pct`` of a long holding. Returns the shares sold, 0 if there is nothing to sell."""
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

    def sell_short(
        self, entity_id: str, price: float, timestamp: pd.Timestamp, money: float, signal_timestamp=None, **log
    ) -> float:
        """Sell short for at most ``money`` of exposure, within the buying power. Returns the shares sold."""
        if not self.margin:
            return 0.0
        fill = price * (1 - self.slippage)
        budget = min(money, self.buying_power)
        if fill <= 0 or budget <= self.min_cost:
            return 0.0
        amount = math.floor(budget / fill + 1e-9)
        if amount < 1:
            return 0.0
        commission = self.commission(amount * fill, self.sell_cost)
        proceeds = amount * fill - commission
        self.cash += proceeds

        holding = self.holdings.setdefault(entity_id, Holding(entity_id=entity_id))
        if holding.amount > 0:
            raise ValueError(f"{entity_id} is held long; sell it before shorting")
        shares = -holding.amount
        holding.average_price = (shares * holding.average_price + amount * fill) / (shares + amount)
        holding.amount -= amount
        holding.cost += proceeds
        holding.last_price = price
        self._record_order(entity_id, timestamp, signal_timestamp, "order_short", fill, amount, cost=commission, **log)
        return float(amount)

    def buy_to_cover(
        self, entity_id: str, price: float, timestamp: pd.Timestamp, pct: float = 1.0, signal_timestamp=None, **log
    ) -> float:
        """Buy back ``pct`` of a short. Returns the shares covered, 0 if nothing is short."""
        holding = self.holdings.get(entity_id)
        if holding is None or holding.amount >= 0:
            return 0.0
        shares = -holding.amount
        amount = shares if pct >= 1 else math.floor(shares * pct)
        if amount < 1:
            return 0.0
        fill = price * (1 + self.slippage)
        commission = self.commission(amount * fill, self.buy_cost)
        paid = amount * fill + commission
        proceeds_share = holding.cost * amount / shares
        self.cash -= paid

        holding.amount += amount
        holding.cost -= proceeds_share
        if holding.amount >= 0:
            del self.holdings[entity_id]
        self._record_order(
            entity_id,
            timestamp,
            signal_timestamp,
            "order_close_short",
            fill,
            amount,
            cost=commission,
            profit=proceeds_share - paid,
            profit_rate=(proceeds_share - paid) / proceeds_share if proceeds_share else None,
            **log,
        )
        return float(amount)

    def close(self, entity_id: str, price: float, timestamp: pd.Timestamp, signal_timestamp=None, **log) -> float:
        """Close whatever is held in ``entity_id``, long or short. Returns the shares traded."""
        holding = self.holdings.get(entity_id)
        if holding is None:
            return 0.0
        if holding.amount < 0:
            return self.buy_to_cover(entity_id, price, timestamp, signal_timestamp=signal_timestamp, **log)
        return self.sell(entity_id, price, timestamp, signal_timestamp=signal_timestamp, **log)

    def receive_dividend(self, entity_id: str, per_share: float, timestamp: pd.Timestamp) -> float:
        """Cash for a holding on its ex-date; a short pays it instead. Returns the amount received (negative when paid)."""
        holding = self.holdings.get(entity_id)
        if holding is None or holding.amount == 0 or per_share <= 0:
            return 0.0
        received = holding.amount * per_share
        self.cash += received
        self._record_order(entity_id, timestamp, None, "dividend", per_share, holding.amount, cost=0.0, profit=received)
        return received

    def apply_split(self, entity_id: str, ratio: float, timestamp: pd.Timestamp) -> None:
        """``ratio`` new shares per old one. The holding is worth the same before and after."""
        holding = self.holdings.get(entity_id)
        if holding is None or holding.amount == 0 or ratio <= 0 or ratio == 1:
            return
        sign = 1 if holding.amount > 0 else -1
        exact = abs(holding.amount) * ratio
        whole = math.floor(exact + 1e-9)
        holding.average_price /= ratio
        holding.last_price /= ratio
        # a fraction of a share left over by a reverse split is paid out in cash (owed, for a short)
        self.cash += sign * (exact - whole) * holding.last_price
        holding.cost *= whole / exact
        holding.amount = sign * whole
        self._record_order(entity_id, timestamp, None, "split", ratio, holding.amount, cost=0.0)
        if holding.amount == 0:
            del self.holdings[entity_id]

    def _record_order(
        self,
        entity_id,
        timestamp,
        signal_timestamp,
        order_type,
        price,
        amount,
        cost,
        profit=None,
        profit_rate=None,
        decided_at=None,
        forward=None,
        reason=None,
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
        """Mark the holdings to ``close_prices`` (entity_id -> close; a missing price keeps the last one).
        Returns the net value of the holdings."""
        value = 0.0
        for holding in self.holdings.values():
            price = close_prices.get(holding.entity_id)
            if price is not None and price == price and price > 0:
                holding.last_price = float(price)
            if not holding.average_price:
                holding.profit_rate = 0.0
            elif holding.amount < 0:
                holding.profit_rate = 1 - holding.last_price / holding.average_price
            else:
                holding.profit_rate = holding.last_price / holding.average_price - 1
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
                    "profit": holding_value - holding.cost if holding.amount > 0 else holding.cost + holding_value,
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
