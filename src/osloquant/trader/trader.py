"""The trader: walks through the trading days and repeats one thing.

    At a certain time, find the targets that match the conditions, buy and sell them, and see how it went.

Two ways to write a strategy:

*formal*  override ``init_factors`` and return factors; their positive targets are bought, negative ones sold
*solo*    override ``on_time`` and call ``trade_the_targets`` with whatever you worked out yourself

What happens on each trading day, in this order:

1. dividends and splits of the day are booked (only when trading real, unadjusted prices), then orders
   decided on earlier days are filled at today's open (sells first, to free the cash)
2. after the close, the factors are asked for targets using data up to and including today
3. ``on_time`` runs, then profit taking / stop loss
4. the decisions become signals, due at the next trading day's open
5. the account is marked to today's close

A decision made on the close of day t is therefore never filled before the open of day t+1.

Nothing in a day's work looks at a later day, not even at the calendar, so the same loop runs a backtest over
twenty years and steps a live account forward one evening at a time (``osloquant.live``).
"""

from __future__ import annotations

import logging

import pandas as pd

from osloquant.contract import IntervalLevel, TargetType
from osloquant.contract.api import get_data, get_entity_ids, get_kdata_schema, to_pd_timestamp
from osloquant.contract.factor import Factor
from osloquant.contract.storage import delete_data, df_to_db
from osloquant.trader import TradingSignal, TradingSignalType
from osloquant.trader.schemas import TraderInfo
from osloquant.trader.sim_account import PROVIDER, SimAccount


class Trader:
    entity_schema: type | None = None

    def __init__(
        self,
        entity_ids: list[str] | None = None,
        codes: list[str] | None = None,
        start_timestamp=None,
        end_timestamp=None,
        provider: str | None = None,
        level=IntervalLevel.LEVEL_1DAY,
        trader_name: str | None = None,
        adjust_type=None,
        profit_threshold: tuple[float, float] | None = (3, -0.3),
        input_money: float = 1_000_000,
        max_positions: int = 10,
        buy_cost: float = 0.0005,
        sell_cost: float = 0.0005,
        slippage: float = 0.001,
        min_cost: float = 0.0,
        signal_adjust_type=None,
        corporate_actions: pd.DataFrame | None = None,
        mode: str = "backtest",
        execution: str = "next_open",
        rebalance: str = "daily",
        factor_mode: str = "and",
        pre_load_days: int = 400,
        benchmark: str | None = "index_ol_OSEBX",
        max_pending_days: int = 5,
        kdata: pd.DataFrame | None = None,
    ) -> None:
        """
        :param profit_threshold: (take profit, stop loss) on a holding's return since purchase, e.g.
            (3, -0.3) sells at +300 % or -30 %; None switches it off
        :param max_positions: the account is split in this many equal slots, one per holding
        :param execution: "next_open" fills at the next day's open; "signal_close" fills at the very close
            the decision was based on, which is how zvt does it and is slightly optimistic
        :param min_cost: the smallest commission per order, in money
        :param adjust_type: the bars orders are filled and holdings valued at; adjusted by default
        :param signal_adjust_type: the bars the factors read; the same as ``adjust_type`` when omitted. A real-money
            account fills at "raw" prices while its signals come from "adj" ones
        :param corporate_actions: dividends and splits (entity_id, timestamp, dividend, split) to book on their
            day. Needed when filling at raw prices, wrong when filling at adjusted ones
        :param rebalance: act on factor targets "daily", or only on the first trading day of each
            "weekly" / "monthly" period (and on the trader's very first day)
        :param factor_mode: with several factors, "and" buys what all of them like and sells what any
            dislikes; "or" buys what any likes and sells what all dislike
        :param pre_load_days: calendar days of history loaded before the start, so indicators are warm
        :param kdata: bars to trade on instead of reading the store (entity_id, timestamp, open, close)
        """
        assert self.entity_schema is not None, "use StockTrader, or set entity_schema on your trader"
        assert start_timestamp is not None and end_timestamp is not None
        if execution not in ("next_open", "signal_close"):
            raise ValueError("execution must be 'next_open' or 'signal_close'")
        if rebalance not in ("daily", "weekly", "monthly"):
            raise ValueError("rebalance must be 'daily', 'weekly' or 'monthly'")
        if factor_mode not in ("and", "or"):
            raise ValueError("factor_mode must be 'and' or 'or'")

        self.logger = logging.getLogger(type(self).__module__)
        self.trader_name = trader_name or type(self).__name__.lower()
        self.provider = provider
        self.level = IntervalLevel(level)
        self.adjust_type = adjust_type
        self.signal_adjust_type = signal_adjust_type if signal_adjust_type is not None else adjust_type
        self.mode = mode
        #: set by whoever steps a live account: the time the decisions of this run are written down
        self.wall_clock: pd.Timestamp | None = None
        self.start_timestamp = to_pd_timestamp(start_timestamp)
        self.end_timestamp = to_pd_timestamp(end_timestamp)
        self.profit_threshold = profit_threshold
        self.max_positions = max_positions
        self.execution = execution
        self.rebalance = rebalance
        self.factor_mode = factor_mode
        self.pre_load_days = pre_load_days
        self.benchmark = benchmark
        self.max_pending_days = max_pending_days

        if entity_ids is None and codes is not None:
            entity_ids = get_entity_ids(self.entity_schema, codes=codes)
        self.entity_ids = entity_ids

        self.kdata_schema = get_kdata_schema(self.entity_schema, level=self.level, adjust_type=adjust_type)
        self.signal_schema = get_kdata_schema(self.entity_schema, level=self.level, adjust_type=self.signal_adjust_type)
        self._load_bars(kdata)
        self._actions: dict[pd.Timestamp, list[tuple[str, float, float]]] = {}
        if corporate_actions is not None:
            for row in corporate_actions.itertuples():
                self._actions.setdefault(to_pd_timestamp(row.timestamp), []).append((row.entity_id, row.dividend or 0.0, row.split or 0.0))

        self.account = SimAccount(
            trader_name=self.trader_name,
            input_money=input_money,
            buy_cost=buy_cost,
            sell_cost=sell_cost,
            slippage=slippage,
            min_cost=min_cost,
            level=self.level,
        )
        self.trading_signals: list[TradingSignal] = []

        self.factors: list[Factor] = self.init_factors(
            entity_ids=self.entity_ids,
            entity_schema=self.entity_schema,
            start_timestamp=self.start_timestamp - pd.Timedelta(days=self.pre_load_days),
            end_timestamp=self.end_timestamp,
            adjust_type=self.signal_adjust_type,
            provider=self.provider,
        ) or []
        self.on_init()

    # -- what a strategy overrides ----------------------------------------------------------------

    def init_factors(self, entity_ids, entity_schema, start_timestamp, end_timestamp, adjust_type=None, provider=None) -> list[Factor]:
        """Return the factors that pick the targets (formal mode). None by default."""
        return []

    def on_init(self) -> None:
        pass

    def on_time(self, timestamp: pd.Timestamp) -> None:
        """Called after each close (solo mode). Use data up to ``timestamp`` only."""

    def on_factor_targets_filtered(self, timestamp, level, factor: Factor, long_targets: list[str], short_targets: list[str]):
        """A chance to veto what one factor selected. Return (long targets, short targets)."""
        return long_targets, short_targets

    def rank_targets(self, timestamp: pd.Timestamp, entity_ids: list[str]) -> list[str]:
        """Which candidates come first when there are more of them than free slots.

        By the first scoring factor's score when there is one, else by id so that a run is repeatable.
        """
        for factor in self.factors:
            scores = factor.get_scores(timestamp)
            if not scores.empty:
                return sorted(entity_ids, key=lambda e: (-scores.get(e, float("-inf")), e))
        return sorted(entity_ids)

    def long_position_control(self) -> float:
        """The share of the account's value given to each new holding."""
        return 1.0 / self.max_positions

    def short_position_control(self) -> float:
        """The share of a holding sold when it becomes a negative target."""
        return 1.0

    def on_profit_control(self) -> list[str]:
        """Holdings to close because they hit the take-profit or stop-loss threshold."""
        if not self.profit_threshold:
            return []
        take_profit, stop_loss = self.profit_threshold
        return [h.entity_id for h in self.account.holdings.values() if h.profit_rate >= take_profit or h.profit_rate <= stop_loss]

    # -- bars and calendar ------------------------------------------------------------------------

    def _load_bars(self, kdata: pd.DataFrame | None) -> None:
        injected = kdata
        if kdata is None:
            kdata = get_data(
                self.kdata_schema,
                provider=self.provider,
                entity_ids=self.entity_ids,
                start_timestamp=self.start_timestamp - pd.Timedelta(days=10),
                end_timestamp=self.end_timestamp,
                columns=["entity_id", "timestamp", "open", "close"],
            )
        if kdata.empty:
            raise LookupError(f"no bars in {self.kdata_schema.__name__} for this trader; record them first")
        kdata = kdata.reset_index(drop=True) if "entity_id" in kdata.columns else kdata.reset_index()
        self.open_df = kdata.pivot(index="timestamp", columns="entity_id", values="open").sort_index()
        self.close_df = kdata.pivot(index="timestamp", columns="entity_id", values="close").sort_index()
        self._last_close_df = self.close_df.ffill()
        if self.entity_ids is None:
            self.entity_ids = self.close_df.columns.tolist()

        # the universe line measures returns, so it needs adjusted closes even when the fills are at raw prices
        self._universe_close_df = self._last_close_df
        if injected is None and self.signal_schema is not self.kdata_schema:
            adjusted = get_data(
                self.signal_schema,
                provider=self.provider,
                entity_ids=self.entity_ids,
                start_timestamp=self.start_timestamp - pd.Timedelta(days=10),
                end_timestamp=self.end_timestamp,
                columns=["entity_id", "timestamp", "close"],
            )
            if not adjusted.empty:
                self._universe_close_df = adjusted.pivot(index="timestamp", columns="entity_id", values="close").sort_index().ffill()

        # a day counts as a trading day when a fair share of the usual number of entities has a bar,
        # which keeps out the odd stray bar a provider reports on a holiday
        traded = self.close_df.notna().sum(axis=1)
        usual = traded.rolling(20, min_periods=1).median()
        #: every trading day in the loaded bars, including the few before the start
        self._calendar = traded.index[traded >= (0.2 * usual).clip(lower=1)]
        dates = self._calendar[self._calendar >= self.start_timestamp]
        self.trading_dates = dates[dates <= self.end_timestamp]
        if len(self.trading_dates) == 0:
            raise LookupError("no trading days between the start and the end")

    def universe_values(self) -> pd.Series:
        """The account's starting money spread equally over the whole universe, rebalanced daily, without costs.

        This is the hurdle a selection has to clear. When the universe is a list of today's survivors, buying
        all of it already beats the index, and a strategy only adds something if it beats this line too.
        """
        closes = self._universe_close_df
        average_return = (closes / closes.shift(1) - 1).mean(axis=1).reindex(self.trading_dates).fillna(0.0)
        average_return.iloc[0] = 0.0
        return self.account.input_money * (1 + average_return).cumprod()

    def is_rebalance_date(self, timestamp: pd.Timestamp) -> bool:
        """Whether factor targets are acted on today: the first trading day of a new week or month.

        Decided from the days that have been, never from the calendar ahead, so that a live account can tell
        on the evening itself.
        """
        if self.rebalance == "daily" or timestamp == self.trading_dates[0]:
            return True
        position = self._calendar.searchsorted(timestamp)
        if position == 0:
            return True
        previous = self._calendar[position - 1]
        if self.rebalance == "weekly":
            return timestamp.isocalendar()[:2] != previous.isocalendar()[:2]
        return (timestamp.year, timestamp.month) != (previous.year, previous.month)

    #: where and when the market opens; a live decision counts as forward when it was written down before this
    market_timezone = "Europe/Oslo"
    market_open = pd.Timedelta(hours=9)

    def session_open_utc(self, timestamp: pd.Timestamp) -> pd.Timestamp:
        opening = (timestamp.normalize() + self.market_open).tz_localize(self.market_timezone)
        return opening.tz_convert("UTC").tz_localize(None)

    # -- signals ----------------------------------------------------------------------------------

    def _held(self) -> set[str]:
        return set(self.account.holdings)

    def _pending(self, signal_type: TradingSignalType) -> set[str]:
        return {s.entity_id for s in self.trading_signals if s.trading_signal_type == signal_type}

    def buy(self, timestamp: pd.Timestamp, entity_ids, ignore_in_position: bool = True) -> None:
        """Queue buys for the next fill. Fills the free slots, in ``rank_targets`` order."""
        candidates = set(entity_ids) - self._pending(TradingSignalType.open_long)
        if ignore_in_position:
            candidates -= self._held()
        if not candidates:
            return
        closing = self._pending(TradingSignalType.close_long) & self._held()
        free_slots = self.max_positions - len(self._held() - closing) - len(self._pending(TradingSignalType.open_long))
        if free_slots <= 0:
            return
        position_pct = self.long_position_control()
        for entity_id in self.rank_targets(timestamp, sorted(candidates))[:free_slots]:
            self.trading_signals.append(
                TradingSignal(
                    entity_id=entity_id,
                    happen_timestamp=timestamp,
                    due_timestamp=self._next_trading_date(timestamp),
                    trading_signal_type=TradingSignalType.open_long,
                    trading_level=self.level,
                    position_pct=position_pct,
                    decided_at=self.wall_clock,
                )
            )

    def sell(self, timestamp: pd.Timestamp, entity_ids) -> None:
        """Queue sells for the next fill, for whatever of ``entity_ids`` is actually held."""
        to_close = (set(entity_ids) & self._held()) - self._pending(TradingSignalType.close_long)
        position_pct = self.short_position_control()
        for entity_id in sorted(to_close):
            self.trading_signals.append(
                TradingSignal(
                    entity_id=entity_id,
                    happen_timestamp=timestamp,
                    due_timestamp=self._next_trading_date(timestamp),
                    trading_signal_type=TradingSignalType.close_long,
                    trading_level=self.level,
                    position_pct=position_pct,
                    decided_at=self.wall_clock,
                )
            )

    def trade_the_targets(self, due_timestamp=None, happen_timestamp=None, long_selected=None, short_selected=None) -> None:
        """Sell ``short_selected`` and buy ``long_selected``. This is what a solo strategy calls from ``on_time``."""
        timestamp = to_pd_timestamp(happen_timestamp if happen_timestamp is not None else due_timestamp)
        if short_selected:
            self.sell(timestamp, short_selected)
        if long_selected:
            self.buy(timestamp, long_selected)

    def _next_trading_date(self, timestamp: pd.Timestamp) -> pd.Timestamp | None:
        pos = self.trading_dates.searchsorted(timestamp, side="right")
        return self.trading_dates[pos] if pos < len(self.trading_dates) else None

    def _fill(self, timestamp: pd.Timestamp, prices: pd.Series) -> None:
        """Fill the queued signals at ``prices``; one without a price today waits, for a few days at most."""
        waiting: list[TradingSignal] = []
        sells_first = sorted(self.trading_signals, key=lambda s: s.trading_signal_type != TradingSignalType.close_long)
        for signal in sells_first:
            price = prices.get(signal.entity_id)
            if price is None or price != price or price <= 0:
                age = self.trading_dates.searchsorted(timestamp) - self.trading_dates.searchsorted(signal.happen_timestamp)
                if age < self.max_pending_days:
                    waiting.append(signal)
                else:
                    self.logger.debug("dropped %s for %s: no bar to fill it on", signal.trading_signal_type.value, signal.entity_id)
                continue
            log = {}
            if signal.decided_at is not None:
                log = {"decided_at": signal.decided_at, "forward": float(signal.decided_at < self.session_open_utc(timestamp))}
            if signal.trading_signal_type == TradingSignalType.close_long:
                self.account.sell(signal.entity_id, price, timestamp, pct=signal.position_pct or 1.0, signal_timestamp=signal.happen_timestamp, **log)
            else:
                money = signal.order_money if signal.order_money is not None else (signal.position_pct or 0) * self.account.all_value
                self.account.buy(signal.entity_id, price, timestamp, money=money, signal_timestamp=signal.happen_timestamp, **log)
        self.trading_signals = waiting

    # -- the loop ---------------------------------------------------------------------------------

    def select_from_factors(self, timestamp: pd.Timestamp) -> tuple[set[str], set[str]]:
        long_sets, short_sets = [], []
        for factor in self.factors:
            longs = factor.get_targets(timestamp, TargetType.positive)
            shorts = factor.get_targets(timestamp, TargetType.negative)
            longs, shorts = self.on_factor_targets_filtered(timestamp, self.level, factor, longs, shorts)
            long_sets.append(set(longs or []))
            short_sets.append(set(shorts or []))
        if not long_sets:
            return set(), set()
        if self.factor_mode == "and":
            return set.intersection(*long_sets), set.union(*short_sets)
        return set.union(*long_sets), set.intersection(*short_sets)

    def run(self, after: pd.Timestamp | None = None) -> Trader:
        """Walk through the trading days. With ``after``, only the days later than it (a resumed account)."""
        universe = self.universe_values()
        self.sessions_processed: list[pd.Timestamp] = []
        for timestamp in self.trading_dates:
            if after is not None and timestamp <= after:
                continue
            self.process_session(timestamp, universe_value=float(universe.loc[timestamp]))
            self.sessions_processed.append(timestamp)
        self.on_finish()
        return self

    def process_session(self, timestamp: pd.Timestamp, universe_value: float | None = None) -> None:
        """One trading day, start to finish. Uses nothing later than ``timestamp``."""
        for entity_id, dividend, split in self._actions.get(timestamp, []):
            if split:
                self.account.apply_split(entity_id, split, timestamp)
            if dividend:
                self.account.receive_dividend(entity_id, dividend, timestamp)

        if self.execution == "next_open" and self.trading_signals:
            self._fill(timestamp, self.open_df.loc[timestamp])

        # everything below is decided on today's close, so the holdings are valued at it first
        self.account.mark(self._last_close_df.loc[timestamp])

        long_selected: set[str] = set()
        short_selected: set[str] = set()
        if self.factors and self.is_rebalance_date(timestamp):
            long_selected, short_selected = self.select_from_factors(timestamp)

        self.on_time(timestamp)

        short_selected |= set(self.on_profit_control())
        if short_selected:
            self.sell(timestamp, short_selected)
        if long_selected:
            self.buy(timestamp, long_selected - short_selected)

        if self.execution == "signal_close" and self.trading_signals:
            self._fill(timestamp, self.close_df.loc[timestamp])

        self.account.on_trading_close(timestamp, self._last_close_df.loc[timestamp], universe_value=universe_value)

    def on_finish(self) -> None:
        self.persist(append=self.mode == "live")

    # -- results ----------------------------------------------------------------------------------

    def persist(self, append: bool = False) -> None:
        info = pd.DataFrame(
            [
                {
                    "id": self.trader_name,
                    "entity_id": self.trader_name,
                    "timestamp": self.trading_dates[0],
                    "trader_name": self.trader_name,
                    "entity_type": self.entity_schema.__name__.lower(),
                    "start_timestamp": self.trading_dates[0],
                    "end_timestamp": self.trading_dates[-1],
                    "provider": self.provider or self.kdata_schema.default_provider(),
                    "level": self.level.value,
                    "kdata_adjust_type": self.kdata_schema.adjust_type.value,
                    "execution": self.execution,
                    "rebalance": self.rebalance,
                    "benchmark": self.benchmark,
                    "input_money": self.account.input_money,
                    "buy_cost": self.account.buy_cost,
                    "sell_cost": self.account.sell_cost,
                    "slippage": self.account.slippage,
                    "min_cost": self.account.min_cost,
                    "universe_size": float(len(self.entity_ids)),
                    "mode": self.mode,
                }
            ]
        )
        delete_data(TraderInfo, PROVIDER, filters=[TraderInfo.trader_name == self.trader_name])
        df_to_db(info, TraderInfo, PROVIDER)
        self.account.persist(append=append)

    def stats(self) -> dict:
        """Performance of the finished run. See :func:`osloquant.trader.stats.get_trader_stats`."""
        from osloquant.trader.stats import get_trader_stats

        return get_trader_stats(self.trader_name)

    def draw(self, show: bool = False):
        """The account value against the benchmark."""
        from osloquant.contract.drawer import draw_account

        fig = draw_account(self.trader_name)
        if show:
            fig.show()
        return fig


class StockTrader(Trader):
    """A trader on Oslo Børs stocks, on adjusted daily bars."""

    def __init__(self, *args, **kwargs) -> None:
        from osloquant.domain.meta import Stock

        self.entity_schema = Stock
        super().__init__(*args, **kwargs)
