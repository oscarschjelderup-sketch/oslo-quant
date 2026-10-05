"""Intraday paper accounts: rules watch the 15-minute bars through the day and the account trades their signals.

Every 15 minutes while Oslo is open, for each account:

1. orders sent at an earlier poll are filled at the open of the bar that was starting when they were sent;
2. the holdings are valued at the newest completed bar;
3. the risk rules look at each holding: stop loss, take profit, trailing stop, flat at the close;
4. the signal rule looks at the newest completed bar of each stock on the watchlist and of each holding;
5. BUY and SELL signals become orders, and every signal is logged with what was done about it and why.

Play money only: nothing here can reach a broker.

Two things keep it honest. Yahoo's Oslo quotes are about 15 minutes late, so a rule sees a bar a quarter of
an hour after it closed, and the order it causes is filled at the price the market had moved to by then, not
at the price that raised the signal. And a signal is acted on only if its bar is fresh: a poll that was missed
is a signal that was missed, as it would be for a person who was not at the screen.

The same step function replays stored bars (``oq intraday replay``) with exactly the same delays, so a rule can
be tried on the last weeks before it is left to run.
"""

from __future__ import annotations

import json
import logging
import time as time_module
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from osloquant.contract import IntervalLevel
from osloquant.contract.api import get_data
from osloquant.contract.storage import df_to_db
from osloquant.env import oq_env
from osloquant.intraday.rules import BUY, SELL, Rule, build_rule
from osloquant.trader.schemas import AccountStats, IntradaySignal, IntradaySnapshot, LiveState, Order, TraderInfo
from osloquant.trader.sim_account import PROVIDER, TRADES, SimAccount

logger = logging.getLogger(__name__)

MARKET_TIMEZONE = "Europe/Oslo"
INTERVAL = pd.Timedelta(minutes=15)
FIRST_BAR = pd.Timedelta(hours=9)
LAST_BAR = pd.Timedelta(hours=16, minutes=15)
#: a poll this long after a bar boundary still counts as sent at that boundary
ON_TIME = pd.Timedelta(minutes=3)
#: a signal is acted on only if its bar closed at most this long before the newest quotes
FRESH = pd.Timedelta(minutes=20)
#: a buy that cannot be filled within this long is dropped; a sell waits for as long as it takes
BUY_EXPIRES = pd.Timedelta(minutes=60)

DEFAULT_CONFIG = """\
# The intraday paper accounts. `oq intraday run` steps them every 15 minutes while Oslo is open.
# Play money only. An account starts the first time it is seen and is never restarted: to try other
# rules, add an account under a new name.
#
# watchlist  which stocks an account may buy: the name of a daily factor (its positive targets at the last
#            close, e.g. MomentumFactor or AboveMaFactor), "all", or a list of codes like [EQNR, DNB]
# signal     the rule that raises BUY and SELL: ma_cross (fast, slow), breakout (lookback),
#            macd_cross (fast, slow, n), rsi (period, low, high), or your own as "package.module:ClassName"
# stop_loss / take_profit / trailing_stop   exits measured from the purchase price (trailing: from the highest
#            price since), as fractions: 0.03 is 3 %. Leave out to switch off.
# flat_at_close   true sells everything before the close, so nothing is held overnight
# cooldown_bars   after selling a stock, ignore buy signals in it for this many 15-minute bars. Stops a rule
#            from buying back what it was just stopped out of.

# Yahoo's Oslo quotes arrive about this many minutes late
feed_delay_minutes: 15

costs:
  # Nordnet Mini as of October 2026: 0.15 %, at least NOK 29 per order. Set this to your broker's price list.
  commission_rate: 0.0015
  commission_min: 29
  slippage: 0.001

accounts:
  - name: intraday_ma
    watchlist: MomentumFactor
    signal: {rule: ma_cross, fast: 5, slow: 20}
    stop_loss: 0.03
    take_profit: 0.06
    input_money: 100000
    max_positions: 5
  - name: intraday_breakout
    watchlist: MomentumFactor
    signal: {rule: breakout, lookback: 20}
    stop_loss: 0.03
    trailing_stop: 0.04
    input_money: 100000
    max_positions: 5
  # The same two rules, three to four times slower. A round trip costs about 0.5 % whatever the rule, so a rule
  # that trades a third as often pays a third of the costs. Running fast and slow side by side shows what that is worth.
  - name: intraday_ma_slow
    watchlist: MomentumFactor
    signal: {rule: ma_cross, fast: 20, slow: 60}
    stop_loss: 0.03
    take_profit: 0.06
    input_money: 100000
    max_positions: 5
  - name: intraday_breakout_slow
    watchlist: MomentumFactor
    signal: {rule: breakout, lookback: 60}
    stop_loss: 0.03
    trailing_stop: 0.04
    input_money: 100000
    max_positions: 5
"""


@dataclass
class IntradayAccountConfig:
    name: str
    signal: dict
    watchlist: str | list = "MomentumFactor"
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop: float | None = None
    flat_at_close: bool = False
    #: after selling a stock, ignore buy signals in it for this many bars (0: none)
    cooldown_bars: int = 0
    input_money: float = 100_000
    max_positions: int = 5


@dataclass
class IntradayConfig:
    accounts: list[IntradayAccountConfig]
    feed_delay: pd.Timedelta = pd.Timedelta(minutes=15)
    commission_rate: float = 0.0015
    commission_min: float = 29.0
    slippage: float = 0.001
    path: Path | None = None
    created: bool = False


def config_path() -> Path:
    from osloquant.env import data_path

    data_path()
    return Path(oq_env["home"]) / "intraday.yaml"


def load_config(path: str | Path | None = None) -> IntradayConfig:
    """Read the intraday configuration, writing the default one first if there is none."""
    path = Path(path) if path is not None else config_path()
    created = not path.exists()
    if created:
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    costs = raw.get("costs") or {}
    accounts = [IntradayAccountConfig(**a) for a in raw.get("accounts") or []]
    names = [a.name for a in accounts]
    if len(set(names)) != len(names):
        raise ValueError(f"{path}: two accounts share a name")
    return IntradayConfig(
        accounts=accounts,
        feed_delay=pd.Timedelta(minutes=float(raw.get("feed_delay_minutes", 15))),
        commission_rate=float(costs.get("commission_rate", 0.0015)),
        commission_min=float(costs.get("commission_min", 29.0)),
        slippage=float(costs.get("slippage", 0.001)),
        path=path,
        created=created,
    )


# -- the clock ------------------------------------------------------------------------------------


def market_now() -> pd.Timestamp:
    """The time in Oslo, without a time zone attached: the clock the bars are stamped with."""
    return pd.Timestamp.now(tz=MARKET_TIMEZONE).tz_localize(None)


def poll_times(day: pd.Timestamp, feed_delay: pd.Timedelta) -> list[pd.Timestamp]:
    """When to look: a minute after each bar of ``day`` has closed *and* come through the delayed feed."""
    day = day.normalize()
    starts = pd.date_range(day + FIRST_BAR, day + LAST_BAR, freq=INTERVAL)
    return [start + INTERVAL + feed_delay + pd.Timedelta(minutes=1) for start in starts]


def worth_looking(now: pd.Timestamp, feed_delay: pd.Timedelta) -> bool:
    """Whether a look at ``now`` can find anything: a weekday, between the first and the last look of the session."""
    if now.dayofweek >= 5:
        return False
    times = poll_times(now, feed_delay)
    slack = pd.Timedelta(minutes=5)
    return times[0] - slack <= now <= times[-1] + slack


def order_bar(now: pd.Timestamp) -> pd.Timestamp:
    """The bar an order sent at ``now`` is filled at the open of: the one starting then, or the next one."""
    boundary = now.floor(INTERVAL)
    return boundary if now - boundary <= ON_TIME else boundary + INTERVAL


# -- data -----------------------------------------------------------------------------------------


def stock_names() -> pd.DataFrame:
    from osloquant.domain import Stock

    return Stock.query_data(columns=["entity_id", "code", "name"]).set_index("entity_id")


def last_daily_session(before: pd.Timestamp) -> pd.Timestamp | None:
    from osloquant.domain import Stock1dAdjKdata

    df = Stock1dAdjKdata.query_data(
        columns=["timestamp"], end_timestamp=before.normalize() - pd.Timedelta(days=1), order=Stock1dAdjKdata.timestamp.desc(), limit=1
    )
    return None if df.empty else df["timestamp"].iloc[0]


@lru_cache(maxsize=4)
def _factor(factor_name: str, newest: pd.Timestamp):
    """The factor over the last years up to the newest daily bar. Its verdict for a day never depends on
    later days, so one computation serves every day asked about."""
    from osloquant.contract import context

    if factor_name not in context.factor_cls_registry:
        raise ValueError(f"watchlist {factor_name!r} is not a factor; known: {', '.join(sorted(context.factor_cls_registry))}, 'all', or a list of codes")
    return context.factor_cls_registry[factor_name](start_timestamp=newest - pd.DateOffset(years=4), end_timestamp=newest)


@lru_cache(maxsize=256)
def _factor_targets(factor_name: str, as_of: pd.Timestamp) -> tuple[str, ...]:
    from osloquant.contract import TargetType

    factor = _factor(factor_name, last_daily_session(pd.Timestamp.now() + pd.Timedelta(days=2)) or as_of)
    targets = factor.get_targets(as_of, TargetType.positive)
    scores = factor.get_scores(as_of)
    return tuple(sorted(targets, key=lambda e: (-scores.get(e, 0.0), e)))


def daily_watchlist(spec: str | list, day: pd.Timestamp) -> tuple[list[str], pd.Timestamp | None]:
    """The stocks an account may buy on ``day``, best first, and the daily close the list was made on.

    A factor's list is its positive targets at the last close *before* ``day``: nothing of the day itself.
    """
    from osloquant.contract.api import get_entity_ids
    from osloquant.domain import Stock

    if isinstance(spec, list):
        return get_entity_ids(Stock, codes=[str(c).upper().removesuffix(".OL") for c in spec]), None
    if spec == "all":
        return get_entity_ids(Stock), None
    as_of = last_daily_session(day)
    if as_of is None:
        return [], None
    return list(_factor_targets(spec, as_of)), as_of


def load_bars(entity_ids: list[str] | None, since: pd.Timestamp, until: pd.Timestamp | None = None) -> dict[str, pd.DataFrame]:
    """Stored 15-minute bars per stock, indexed by bar start."""
    from osloquant.domain import Stock15mKdata

    if entity_ids is not None and not entity_ids:
        return {}
    df = Stock15mKdata.query_data(
        entity_ids=entity_ids, start_timestamp=since, end_timestamp=until, columns=["entity_id", "timestamp", "open", "high", "low", "close", "volume"]
    )
    return {entity_id: frame.drop(columns="entity_id").set_index("timestamp").sort_index() for entity_id, frame in df.groupby("entity_id")}


def load_actions(entity_ids: list[str] | None, since: pd.Timestamp) -> pd.DataFrame:
    from osloquant.domain import StockAction

    if entity_ids is not None and not entity_ids:
        return pd.DataFrame(columns=["entity_id", "timestamp", "dividend", "split"])
    return StockAction.query_data(entity_ids=entity_ids, start_timestamp=since, columns=["entity_id", "timestamp", "dividend", "split"])


def completed_bars(bars: pd.DataFrame, feed_time: pd.Timestamp) -> pd.DataFrame:
    """The bars that had closed by ``feed_time``."""
    return bars.iloc[: bars.index.searchsorted(feed_time - INTERVAL, side="right")]


def open_at_or_after(bars: pd.DataFrame, since: pd.Timestamp, feed_time: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """The first bar starting at or after ``since`` that the feed has shown the open of."""
    first, visible = bars.index.searchsorted(since, side="left"), bars.index.searchsorted(feed_time, side="right")
    if first >= visible:
        return None
    return bars.index[first], float(bars["open"].iloc[first])


# -- one account ----------------------------------------------------------------------------------


@dataclass
class StepReport:
    name: str
    fills: list[dict] = field(default_factory=list)
    signals: list[dict] = field(default_factory=list)
    value: float = 0.0


class IntradayAccount:
    """One paper account and the rules that drive it."""

    def __init__(self, account: IntradayAccountConfig, config: IntradayConfig, state: dict | None = None) -> None:
        self.cfg = account
        self.feed_delay = config.feed_delay
        self.rule: Rule = build_rule(account.signal)
        self.account = SimAccount(
            trader_name=account.name,
            input_money=account.input_money if state is None else state["input_money"],
            buy_cost=config.commission_rate,
            sell_cost=config.commission_rate,
            slippage=config.slippage,
            min_cost=config.commission_min,
            level=IntervalLevel.LEVEL_15MIN,
        )
        #: orders sent and not yet filled
        self.pending: list[dict] = []
        #: per stock, the newest bar the signal rule has already looked at
        self.seen: dict[str, pd.Timestamp] = {}
        #: per holding, the highest close since it was bought (for the trailing stop)
        self.peaks: dict[str, float] = {}
        #: per holding, the bar it was bought on (a dividend belongs to whoever held the day before it)
        self.opened: dict[str, pd.Timestamp] = {}
        #: the dividends and splits already booked, so that none is booked twice
        self.booked: list[str] = []
        #: per stock, the bar it was last sold on (for the cooldown)
        self.closed: dict[str, pd.Timestamp] = {}
        self.start: pd.Timestamp | None = None
        self.last_poll: pd.Timestamp | None = None
        self.watchlist: list[str] = []
        self.watchlist_as_of: pd.Timestamp | None = None
        self.signals_recorded = 0
        if state is not None:
            self.account.restore(state["account"])
            self.pending = [{**o, "bar": pd.Timestamp(o["bar"]), "signal_bar": pd.Timestamp(o["signal_bar"])} for o in state["pending"]]
            self.seen = {e: pd.Timestamp(t) for e, t in state["seen"].items()}
            self.peaks = dict(state["peaks"])
            self.opened = {e: pd.Timestamp(t) for e, t in state.get("opened", {}).items()}
            self.booked = list(state.get("booked", []))
            self.closed = {e: pd.Timestamp(t) for e, t in state.get("closed", {}).items()}
            self.start = pd.Timestamp(state["start"])
            self.last_poll = pd.Timestamp(state["last_poll"])
            self.signals_recorded = int(state.get("signals_recorded", 0))

    # -- state ------------------------------------------------------------------------------------

    def to_state(self) -> dict:
        return {
            "kind": "intraday",
            "start": self.start.isoformat(),
            "last_poll": self.last_poll.isoformat(),
            "last_session": self.last_poll.normalize().isoformat(),
            "strategy": self.rule.describe(),
            "input_money": self.account.input_money,
            "account": self.account.to_state(),
            "pending": [{**o, "bar": o["bar"].isoformat(), "signal_bar": o["signal_bar"].isoformat()} for o in self.pending],
            "seen": {e: t.isoformat() for e, t in self.seen.items()},
            "peaks": self.peaks,
            "opened": {e: t.isoformat() for e, t in self.opened.items()},
            "booked": self.booked[-200:],
            "closed": {e: t.isoformat() for e, t in self.closed.items()},
            "watchlist": self.watchlist,
            "watchlist_as_of": self.watchlist_as_of.isoformat() if self.watchlist_as_of is not None else None,
            "signals_recorded": self.signals_recorded,
        }

    # -- the step ---------------------------------------------------------------------------------

    def step(
        self,
        now: pd.Timestamp,
        bars: dict[str, pd.DataFrame],
        watchlist: list[str],
        wall_clock: pd.Timestamp | None = None,
        actions: pd.DataFrame | None = None,
    ) -> StepReport:
        """Everything the account does at one poll.

        ``now`` is Oslo time. ``wall_clock`` (UTC) marks a live run: its fills are flagged as forward, because
        the price they were filled at had not come through the feed when the order was written down.
        ``actions`` are recent dividends and splits (entity_id, timestamp, dividend, split).
        """
        report = StepReport(name=self.cfg.name)
        feed_time = now - self.feed_delay
        if self.start is None:
            self.start = now
        self.watchlist = watchlist
        log = {} if wall_clock is None else {"decided_at": wall_clock, "forward": 1.0}
        self._book_actions(now, actions)

        # 1. fill what was sent earlier, sells first so that their cash is there for the buys
        waiting = []
        for order in sorted(self.pending, key=lambda o: o["side"] != SELL):
            fill = open_at_or_after(bars[order["entity_id"]], order["bar"], feed_time) if order["entity_id"] in bars else None
            if fill is None:
                if order["side"] == BUY and feed_time - order["bar"] > BUY_EXPIRES:
                    report.signals.append(self._signal_row(order, "expired: no trade to fill it on", wall_clock))
                else:
                    waiting.append(order)
                continue
            bar, price = fill
            entity_id, reason = order["entity_id"], f"{order['code']} {order['rule']}: {order['reason']}"
            if order["side"] == BUY:
                amount = self.account.buy(
                    entity_id, price, bar, money=self.account.all_value / self.cfg.max_positions, signal_timestamp=order["signal_bar"], reason=reason, **log
                )
                if amount:
                    self.peaks[entity_id] = price
                    self.opened[entity_id] = bar
            else:
                amount = self.account.sell(entity_id, price, bar, signal_timestamp=order["signal_bar"], reason=reason, **log)
                self.peaks.pop(entity_id, None)
                self.opened.pop(entity_id, None)
                if amount:
                    self.closed[entity_id] = bar
            if amount:
                report.fills.append({"entity_id": entity_id, "side": order["side"], "bar": bar, "price": price, "shares": amount, "reason": reason})
        self.pending = waiting

        # 2. value the holdings at the newest completed bar
        done = {entity_id: completed_bars(frame, feed_time) for entity_id, frame in bars.items()}
        prices = {entity_id: float(frame["close"].iloc[-1]) for entity_id, frame in done.items() if len(frame)}
        self.account.mark(prices)

        # 3. the risk rules, on what is held and not already being sold
        selling = {o["entity_id"] for o in self.pending if o["side"] == SELL}
        closing_time = self.cfg.flat_at_close and now >= now.normalize() + LAST_BAR - 2 * INTERVAL
        for entity_id, holding in list(self.account.holdings.items()):
            if entity_id in selling or entity_id not in prices or not len(done[entity_id]):
                continue
            price, bought = prices[entity_id], holding.average_price
            self.peaks[entity_id] = peak = max(self.peaks.get(entity_id, bought), price)
            exit_signal = None
            if self.cfg.stop_loss and price <= bought * (1 - self.cfg.stop_loss):
                exit_signal = ("STOP", f"{price:.2f} is {price / bought - 1:+.1%} from the purchase at {bought:.2f}")
            elif self.cfg.take_profit and price >= bought * (1 + self.cfg.take_profit):
                exit_signal = ("TARGET", f"{price:.2f} is {price / bought - 1:+.1%} from the purchase at {bought:.2f}")
            elif self.cfg.trailing_stop and price <= peak * (1 - self.cfg.trailing_stop):
                exit_signal = ("TRAIL", f"{price:.2f} is {price / peak - 1:+.1%} from the high of {peak:.2f} since the purchase")
            elif closing_time:
                exit_signal = ("CLOSE", "nothing is held overnight")
            if exit_signal:
                order = self._order(entity_id, SELL, exit_signal[0], "risk", exit_signal[1], done[entity_id].index[-1], price, now)
                self.pending.append(order)
                selling.add(entity_id)
                report.signals.append(self._signal_row(order, "ordered", wall_clock))

        # 4. the signal rule, on the newest completed bar of each stock it has not looked at yet
        buying = {o["entity_id"] for o in self.pending if o["side"] == BUY}
        last_fillable = now.normalize() + LAST_BAR
        for entity_id in [*watchlist, *[e for e in self.account.holdings if e not in watchlist]]:
            frame = done.get(entity_id)
            if frame is None or len(frame) < self.rule.min_bars:
                continue
            newest = frame.index[-1]
            if entity_id in self.seen and newest <= self.seen[entity_id]:
                continue
            self.seen[entity_id] = newest
            if newest + INTERVAL < feed_time - FRESH:
                continue  # the bar closed long ago: whatever it said, the moment has passed
            signal = self.rule.evaluate(frame)
            if signal is None:
                continue
            held = entity_id in self.account.holdings
            order = self._order(entity_id, signal.code, signal.code, signal.rule, signal.reason, signal.bar, signal.price, now)
            if signal.code == SELL:
                if not held or entity_id in selling:
                    continue  # a sell signal for something not held is not news
                self.pending.append(order)
                selling.add(entity_id)
                outcome = "ordered"
            else:
                free = self.cfg.max_positions - len(set(self.account.holdings) - selling) - len(buying)
                cooling = self.cfg.cooldown_bars and entity_id in self.closed and signal.bar < self.closed[entity_id] + self.cfg.cooldown_bars * INTERVAL
                if held:
                    outcome = "skipped: already held"
                elif cooling:
                    outcome = "skipped: cooling off after the last sale"
                elif entity_id in buying:
                    outcome = "skipped: already ordered"
                elif entity_id not in watchlist:
                    outcome = "skipped: not on today's watchlist"
                elif closing_time:
                    outcome = "skipped: too close to the close"
                elif order["bar"] > last_fillable:
                    outcome = "skipped: the market has closed"
                elif free <= 0:
                    outcome = "skipped: no free slot"
                else:
                    self.pending.append(order)
                    buying.add(entity_id)
                    outcome = "ordered"
            report.signals.append(self._signal_row(order, outcome, wall_clock))

        self.last_poll = now
        report.value = self.account.all_value
        return report

    def _book_actions(self, now: pd.Timestamp, actions: pd.DataFrame | None) -> None:
        """Dividends and splits for what was held going into their day. They reach the store on the evening of
        the day, so in a live run they are booked the morning after."""
        if actions is None or actions.empty:
            return
        today = now.normalize()
        for row in actions.itertuples():
            key = f"{row.entity_id}_{row.timestamp:%Y-%m-%d}"
            if key in self.booked or row.timestamp > today or row.timestamp < self.start.normalize():
                continue
            self.booked.append(key)
            if row.entity_id not in self.account.holdings or self.opened.get(row.entity_id, today) >= row.timestamp:
                continue  # not held, or bought on the day itself or later: no claim on it
            if row.split and row.split != 1:
                self.account.apply_split(row.entity_id, row.split, row.timestamp)
                if row.entity_id in self.peaks:
                    self.peaks[row.entity_id] /= row.split
            if row.dividend:
                self.account.receive_dividend(row.entity_id, row.dividend, row.timestamp)

    def _order(self, entity_id, side, code, rule, reason, signal_bar, price, now) -> dict:
        return {"entity_id": entity_id, "side": side, "code": code, "rule": rule, "reason": reason, "signal_bar": signal_bar, "price": price, "bar": order_bar(now)}

    def _signal_row(self, order: dict, outcome: str, wall_clock) -> dict:
        self.signals_recorded += 1
        return {
            "id": f"{self.cfg.name}_s{self.signals_recorded:07d}",
            "entity_id": order["entity_id"],
            "timestamp": order["signal_bar"],
            "trader_name": self.cfg.name,
            "code": order["code"],
            "rule": order["rule"],
            "reason": order["reason"],
            "price": order["price"],
            "outcome": outcome,
            "decided_at": wall_clock,
        }


# -- stepping every account, live -----------------------------------------------------------------


def load_state(name: str) -> dict | None:
    rows = get_data(LiveState, provider=PROVIDER, filters=[LiveState.trader_name == name], return_type="dict")
    return json.loads(rows[0]["state"]) if rows else None


def _persist(
    account: IntradayAccount, config: IntradayConfig, report: StepReport, now: pd.Timestamp, wall_clock: pd.Timestamp, feed_lag: pd.Timedelta | None = None
) -> None:
    name, sim = account.cfg.name, account.account
    sim.persist(append=True)  # the orders; an intraday account writes no daily positions
    df_to_db(pd.DataFrame(report.signals), IntradaySignal, PROVIDER)
    snapshot = {
        "id": f"{name}_{now:%Y-%m-%dT%H:%M}",
        "entity_id": name,
        "timestamp": now,
        "trader_name": name,
        "cash": sim.cash,
        "value": sim.all_value - sim.cash,
        "all_value": sim.all_value,
        "holdings": float(len(sim.holdings)),
        "feed_lag": None if feed_lag is None else feed_lag.total_seconds() / 60,
    }
    df_to_db(pd.DataFrame([snapshot]), IntradaySnapshot, PROVIDER)
    df_to_db(pd.DataFrame([sim.day_row(now)]), AccountStats, PROVIDER)  # the day's row, overwritten until the day is over
    info = {
        "id": name,
        "entity_id": name,
        "timestamp": account.start,
        "trader_name": name,
        "entity_type": "stock",
        "start_timestamp": account.start,
        "end_timestamp": now,
        "provider": "yahoo",
        "level": "15m",
        "kdata_adjust_type": "raw",
        "execution": "next_bar_open",
        "rebalance": "15m",
        "benchmark": "index_ol_OSEBX",
        "input_money": sim.input_money,
        "buy_cost": sim.buy_cost,
        "sell_cost": sim.sell_cost,
        "slippage": sim.slippage,
        "min_cost": sim.min_cost,
        "universe_size": float(len(account.watchlist)),
        "mode": "intraday",
    }
    df_to_db(pd.DataFrame([info]), TraderInfo, PROVIDER)
    state = {"id": name, "entity_id": name, "timestamp": now, "trader_name": name, "state": json.dumps(account.to_state()), "updated_at": wall_clock}
    df_to_db(pd.DataFrame([state]), LiveState, PROVIDER)


@dataclass
class PollResult:
    now: pd.Timestamp
    reports: list[StepReport] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    record_error: str | None = None
    #: how far behind the clock the newest stored bar is: the real delay of the feed
    feed_lag: pd.Timedelta | None = None


def poll(config: IntradayConfig, now: pd.Timestamp | None = None, record: bool = True) -> PollResult:
    """One look at the market for every account: record the newest bars, step, store. Safe to call at any time."""
    from osloquant.domain import Stock15mKdata

    now = market_now() if now is None else now
    wall_clock = pd.Timestamp.now(tz="UTC").tz_localize(None)
    result = PollResult(now=now)

    accounts: list[IntradayAccount] = []
    for cfg in config.accounts:
        try:
            account = IntradayAccount(cfg, config, load_state(cfg.name))
            account.watchlist, account.watchlist_as_of = daily_watchlist(cfg.watchlist, now)
            accounts.append(account)
        except Exception as e:
            logger.exception("intraday account %s could not be set up", cfg.name)
            result.errors[cfg.name] = f"{type(e).__name__}: {e}"

    needed = sorted({e for a in accounts for e in [*a.watchlist, *a.account.holdings, *[o["entity_id"] for o in a.pending]]})
    if record and needed:
        try:
            Stock15mKdata.record_data(entity_ids=needed)
        except Exception as e:
            result.record_error = f"{type(e).__name__}: {e}"
            logger.warning("recording intraday bars failed: %s", e)
    bars = load_bars(needed, since=now - pd.Timedelta(days=12))
    actions = load_actions(needed, since=now.normalize() - pd.Timedelta(days=30))
    # the newest bar that has started: how far behind the clock it is, is how late the feed really is
    started = [frame.index[frame.index.searchsorted(now, side="right") - 1] for frame in bars.values() if len(frame) and frame.index[0] <= now]
    result.feed_lag = now - max(started) if started else None

    for account in accounts:
        try:
            report = account.step(now, bars, account.watchlist, wall_clock=wall_clock, actions=actions)
            _persist(account, config, report, now, wall_clock, feed_lag=result.feed_lag)
            result.reports.append(report)
        except Exception as e:
            logger.exception("intraday account %s failed", account.cfg.name)
            result.errors[account.cfg.name] = f"{type(e).__name__}: {e}"
    return result


def run_session(config: IntradayConfig, on_poll=None, sleep=time_module.sleep, clock=market_now) -> int:
    """Poll through today's session and return when it is over. Returns the number of polls made.

    Started before the open it waits; started in the middle it polls at once and then keeps to the grid;
    started after the last poll, or on a weekend, it returns immediately.
    """
    now = clock()
    if now.dayofweek >= 5:
        return 0
    times = poll_times(now, config.feed_delay)
    polls = 0
    if times[0] < now <= times[-1]:
        result = poll(config, now=now)
        polls += 1
        if on_poll:
            on_poll(result)
    for when in times:
        now = clock()
        if when <= now:
            continue
        sleep(max((when - now).total_seconds(), 0))
        result = poll(config, now=clock())
        polls += 1
        if on_poll:
            on_poll(result)
    return polls


# -- how much of the market an account actually watched --------------------------------------------


def look_coverage(looks: pd.DatetimeIndex, start: pd.Timestamp, now: pd.Timestamp, feed_delay: pd.Timedelta) -> dict:
    """How many of the looks an account was due it actually made.

    A look is due a minute after each bar comes through the feed, on every weekday from the account's start
    to ``now``. It counts as made if the account looked at any time before the next one was due: the bar was
    still fresh then. Public holidays are weekdays here, so they show up as days with all looks made and no bars.
    """
    looks = pd.DatetimeIndex(looks).sort_values()
    per_day = {}
    for day in pd.bdate_range(start.normalize(), now.normalize()):
        due = [t for t in poll_times(day, feed_delay) if start <= t <= now]
        made = sum(1 for t in due if looks.searchsorted(t - pd.Timedelta(minutes=1)) < looks.searchsorted(t + INTERVAL))
        if due:
            per_day[day] = (made, len(due))
    today = per_day.get(now.normalize(), (0, 0))
    made, due = sum(m for m, _ in per_day.values()), sum(d for _, d in per_day.values())
    return {
        "today_made": today[0],
        "today_due": today[1],
        "made": made,
        "due": due,
        "share": made / due if due else None,
        "days_missed": [day for day, (m, d) in per_day.items() if m == 0 and d >= 4],
        "per_day": per_day,
    }


# -- replay ---------------------------------------------------------------------------------------


@dataclass
class ReplayResult:
    name: str
    rule: str
    days: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    input_money: float
    value: float
    orders: pd.DataFrame
    signals: pd.DataFrame
    daily_values: pd.Series

    @property
    def total_return(self) -> float:
        return self.value / self.input_money - 1


def replay(account: IntradayAccountConfig, config: IntradayConfig, days: int = 30, bars: dict[str, pd.DataFrame] | None = None, end: pd.Timestamp | None = None) -> ReplayResult:
    """Run an account over the stored bars of the last ``days`` calendar days, poll by poll, as it would have run live.

    Nothing is stored. The delays are the live ones: a bar is seen ``feed_delay`` after it closed, and an order is
    filled at the open of the bar that was starting when it was sent.
    """
    end = market_now() if end is None else end
    since = end.normalize() - pd.Timedelta(days=days)
    if bars is None:
        bars = load_bars(None, since=since - pd.Timedelta(days=12), until=end)
    sessions = sorted({ts.normalize() for frame in bars.values() for ts in frame.index if ts >= since})
    actions = load_actions(None, since=since)
    trader = IntradayAccount(account, config)
    signals, daily = [], {}
    for day in sessions:
        watchlist, _ = daily_watchlist(account.watchlist, day)
        for when in poll_times(day, config.feed_delay):
            if when > end:
                break
            signals += trader.step(when, bars, watchlist, actions=actions).signals
        daily[day] = trader.account.all_value
    return ReplayResult(
        name=account.name,
        rule=trader.rule.describe(),
        days=len(sessions),
        start=sessions[0] if sessions else None,
        end=sessions[-1] if sessions else None,
        input_money=trader.account.input_money,
        value=trader.account.all_value,
        orders=trader.account.orders_df,
        signals=pd.DataFrame(signals),
        daily_values=pd.Series(daily, dtype=float),
    )


# -- reading an account ---------------------------------------------------------------------------


def intraday_account_names() -> list[str]:
    df = get_data(TraderInfo, provider=PROVIDER, filters=[TraderInfo.mode == "intraday"], columns=["trader_name"], order=TraderInfo.trader_name.asc())
    return df["trader_name"].tolist()


def account_summary(name: str, feed_delay: pd.Timedelta = pd.Timedelta(minutes=15)) -> dict:
    """Where an intraday account stands: value, holdings, orders waiting, its latest signals, and how much of
    the market it has actually watched."""
    from osloquant.trader.stats import get_benchmark_series

    state = load_state(name)
    if state is None or state.get("kind") != "intraday":
        raise LookupError(f"no intraday account named {name!r}")
    names = stock_names()

    def label(entity_id: str) -> tuple[str, str]:
        if entity_id in names.index:
            return names.loc[entity_id, "code"], names.loc[entity_id, "name"]
        return entity_id.split("_", 2)[2], ""

    stats = get_data(AccountStats, provider=PROVIDER, filters=[AccountStats.trader_name == name], index="timestamp")
    orders = get_data(Order, provider=PROVIDER, filters=[Order.trader_name == name], order=Order.id.asc())
    signals = get_data(IntradaySignal, provider=PROVIDER, filters=[IntradaySignal.trader_name == name], order=IntradaySignal.id.asc())
    snapshots = get_data(IntradaySnapshot, provider=PROVIDER, filters=[IntradaySnapshot.trader_name == name], index="timestamp")
    for frame in (orders, signals):
        if not frame.empty:
            frame["stock"] = [label(e)[0] for e in frame["entity_id"]]
    trades = orders[orders["order_type"].isin(TRADES)] if not orders.empty else orders
    sells = trades[trades["order_type"] == "order_close_long"] if not trades.empty else trades
    input_money = float(state["input_money"])
    value = float(state["account"]["all_value"])
    benchmark = get_benchmark_series(name, stats.index) if not stats.empty else None

    holdings = []
    for h in sorted(state["account"]["holdings"], key=lambda h: -h["amount"] * h["last_price"]):
        code, company = label(h["entity_id"])
        holdings.append(
            {"entity_id": h["entity_id"], "code": code, "name": company, "shares": h["amount"], "average_price": h["average_price"],
             "last_price": h["last_price"], "value": h["amount"] * h["last_price"], "profit_rate": h["profit_rate"]}
        )  # fmt: skip
    pending = []
    for o in state["pending"]:
        code, company = label(o["entity_id"])
        pending.append({"entity_id": o["entity_id"], "code": code, "name": company, "side": o["side"].lower(), "signal": o["code"], "reason": o["reason"], "decided_on": pd.Timestamp(o["signal_bar"])})

    return {
        "name": name,
        "kind": "intraday",
        "strategy": state["strategy"],
        "start": pd.Timestamp(state["start"]),
        "last_session": pd.Timestamp(state["last_session"]),
        "last_poll": pd.Timestamp(state["last_poll"]),
        "sessions": int(len(stats)),
        "input_money": input_money,
        "value": value,
        "cash": float(state["account"]["cash"]),
        "total_return": value / input_money - 1,
        "universe_return": None,
        "benchmark_return": float(benchmark.iloc[-1] / benchmark.iloc[0] - 1) if benchmark is not None and len(benchmark) else None,
        "holdings": holdings,
        "pending": pending,
        "watchlist": [label(e)[0] for e in state.get("watchlist", [])],
        "watchlist_as_of": pd.Timestamp(state["watchlist_as_of"]) if state.get("watchlist_as_of") else None,
        "fills": int(len(trades)),
        "forward_fills": int((trades["forward"] == 1).sum()) if not trades.empty else 0,
        "round_trips": int(len(sells)),
        "win_rate": float((sells["profit"] > 0).mean()) if len(sells) else None,
        "costs_paid": float(trades["cost"].sum()) if not trades.empty else 0.0,
        "dividends_received": float(orders.loc[orders["order_type"] == "dividend", "profit"].sum()) if not orders.empty else 0.0,
        "coverage": look_coverage(snapshots.index, pd.Timestamp(state["start"]), market_now(), feed_delay),
        "feed_lag": float(snapshots["feed_lag"].dropna().iloc[-1]) if "feed_lag" in snapshots.columns and snapshots["feed_lag"].notna().any() else None,
        "orders": orders,
        "signals": signals,
        "snapshots": snapshots,
    }

