"""Paper accounts that are stepped forward one trading day at a time.

A backtest can be made to look good. What cannot be faked is a decision that was written down before the
price it was filled at existed. So each evening after the close, `oq live`:

1. records the day's data;
2. finds the last *completed* session (never a half-finished bar);
3. for each account: books dividends and splits, fills the orders decided earlier at that session's open,
   values the holdings at its close, asks the strategy for new decisions and writes them down with the time;
4. saves where the account stands.

The decisions of this evening are filled at the next open. Every fill carries the wall-clock time its decision
was logged, and counts as *forward* only if that was before the market opened that day. A run that is late and
catches up several sessions at once is still booked, but those fills are marked as not forward.

Differences from the backtests, all in the direction of what a real account sees: fills and valuations are at
real (unadjusted) prices, dividends arrive as cash, share counts are real, and commission has a minimum.
Fills, decisions and cash are never rewritten once stored.
"""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

import pandas as pd
import yaml

from osloquant.contract.api import get_data
from osloquant.contract.storage import df_to_db
from osloquant.env import oq_env
from osloquant.trader import TradingSignal, TradingSignalType
from osloquant.trader.schemas import AccountStats, LiveState, Order, TraderInfo
from osloquant.trader.sim_account import PROVIDER, TRADES

logger = logging.getLogger(__name__)

MARKET_TIMEZONE = "Europe/Oslo"
#: Oslo closes at 16:25 and Yahoo is 15 minutes behind; from this time on, today's bar is taken as final
BARS_FINAL = time(17, 0)

DEFAULT_CONFIG = """\
# The paper accounts `oq live` steps forward after each close.
#
# An account starts on the first session after it appears here and is never restarted: to try a changed
# strategy, add it under a new name and let both run. Removing an account stops it; its history stays stored.
#
# strategy: one of ma, macd, trend, momentum, trend_monthly, or your own as "package.module:ClassName".

costs:
  # Nordnet Mini as of October 2026: 0.15 %, at least NOK 29 per order. Set this to your broker's price list.
  commission_rate: 0.0015
  commission_min: 29
  # paid on top of the opening price on a buy, lost on a sell
  slippage: 0.001

accounts:
  - {name: live_momentum, strategy: momentum, input_money: 100000, max_positions: 10}
  - {name: live_trend, strategy: trend, input_money: 100000, max_positions: 10}
  # the lab's trend strategy as it was tested: every stock above its 200-day average, decided monthly
  - {name: live_trend_monthly, strategy: trend_monthly, input_money: 100000, max_positions: 100}
"""


@dataclass
class AccountConfig:
    name: str
    strategy: str
    input_money: float = 100_000
    max_positions: int = 10


@dataclass
class LiveConfig:
    accounts: list[AccountConfig]
    commission_rate: float = 0.0015
    commission_min: float = 29.0
    slippage: float = 0.001
    path: Path | None = None
    created: bool = False


@dataclass
class StepResult:
    name: str
    #: "started", "stepped", "up to date" or "failed"
    outcome: str
    sessions: list[pd.Timestamp] = field(default_factory=list)
    error: str | None = None


def config_path() -> Path:
    from osloquant.env import data_path

    data_path()  # makes sure the home exists
    return Path(oq_env["home"]) / "live.yaml"


def load_config(path: str | Path | None = None) -> LiveConfig:
    """Read the live configuration, writing the default one first if there is none."""
    path = Path(path) if path is not None else config_path()
    created = not path.exists()
    if created:
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    costs = raw.get("costs") or {}
    accounts = [AccountConfig(**a) for a in raw.get("accounts") or []]
    names = [a.name for a in accounts]
    if len(set(names)) != len(names):
        raise ValueError(f"{path}: two accounts share a name")
    return LiveConfig(
        accounts=accounts,
        commission_rate=float(costs.get("commission_rate", 0.0015)),
        commission_min=float(costs.get("commission_min", 29.0)),
        slippage=float(costs.get("slippage", 0.001)),
        path=path,
        created=created,
    )


def resolve_strategy(strategy: str) -> type:
    from osloquant.samples import SAMPLE_TRADERS

    if strategy in SAMPLE_TRADERS:
        return SAMPLE_TRADERS[strategy]
    if ":" in strategy:
        module, _, name = strategy.partition(":")
        return getattr(importlib.import_module(module), name)
    raise ValueError(f"unknown strategy {strategy!r}; use one of {', '.join(SAMPLE_TRADERS)} or 'package.module:ClassName'")


# -- the session clock ----------------------------------------------------------------------------


def last_completed_session(now: pd.Timestamp | None = None) -> pd.Timestamp | None:
    """The newest trading day whose bars are final, or None when no bars are stored.

    ``now`` is a time-zone-aware timestamp; the current time when omitted. Today counts only from
    ``BARS_FINAL`` Oslo time, and only if a fair share of the stocks actually has a bar for it.
    """
    from osloquant.domain import Stock1dKdata

    now = pd.Timestamp.now(tz=MARKET_TIMEZONE) if now is None else now.tz_convert(MARKET_TIMEZONE)
    today = now.tz_localize(None).normalize()
    newest = Stock1dKdata.query_data(columns=["timestamp"], end_timestamp=today, order=Stock1dKdata.timestamp.desc(), limit=1)
    if newest.empty:
        return None
    # the weeks up to the newest stored bar show what a normal day looks like
    since = newest["timestamp"].iloc[0] - pd.Timedelta(days=45)
    recent = Stock1dKdata.query_data(columns=["entity_id", "timestamp"], start_timestamp=since, end_timestamp=today)
    traded = recent.groupby("timestamp")["entity_id"].nunique()
    sessions = traded.index[traded >= 0.5 * traded.median()]
    if now.time() < BARS_FINAL:
        sessions = sessions[sessions < today]
    return sessions.max() if len(sessions) else None


# -- data -----------------------------------------------------------------------------------------


def record_market_data() -> list:
    """Bring the store up to date with what the live accounts read. Returns the record summaries."""
    from osloquant.domain import Index, Index1dKdata, Stock, Stock1dAdjKdata, Stock1dKdata, StockAction
    from osloquant.recorders.yahoo import client

    client.clear_history_cache()
    summaries = []
    if Stock.query_data(limit=1).empty:
        summaries.append(Stock.record_data())
    if Index.query_data(limit=1).empty:
        summaries.append(Index.record_data())
    # the actions go first: they ask for the longest stretch, and the two bar tables are then served from the same download
    for schema in (StockAction, Stock1dAdjKdata, Stock1dKdata, Index1dKdata):
        summaries.append(schema.record_data())
    return summaries


# -- state ----------------------------------------------------------------------------------------


def load_state(name: str) -> dict | None:
    rows = get_data(LiveState, provider=PROVIDER, filters=[LiveState.trader_name == name], return_type="dict")
    return json.loads(rows[0]["state"]) if rows else None


def save_state(name: str, state: dict, wall_clock: pd.Timestamp) -> None:
    row = {
        "id": name,
        "entity_id": name,
        "timestamp": pd.Timestamp(state["last_session"]),
        "trader_name": name,
        "state": json.dumps(state),
        "updated_at": wall_clock,
    }
    df_to_db(pd.DataFrame([row]), LiveState, PROVIDER)


def _signal_to_dict(signal: TradingSignal) -> dict:
    return {
        "entity_id": signal.entity_id,
        "happen_timestamp": signal.happen_timestamp.isoformat(),
        "type": signal.trading_signal_type.value,
        "position_pct": signal.position_pct,
        "order_money": signal.order_money,
        "decided_at": signal.decided_at.isoformat() if signal.decided_at is not None else None,
    }


def _signal_from_dict(data: dict) -> TradingSignal:
    return TradingSignal(
        entity_id=data["entity_id"],
        happen_timestamp=pd.Timestamp(data["happen_timestamp"]),
        due_timestamp=None,
        trading_signal_type=TradingSignalType(data["type"]),
        position_pct=data["position_pct"],
        order_money=data["order_money"],
        decided_at=pd.Timestamp(data["decided_at"]) if data["decided_at"] else None,
    )


# -- stepping -------------------------------------------------------------------------------------


def step_account(account: AccountConfig, config: LiveConfig, session: pd.Timestamp, wall_clock: pd.Timestamp) -> StepResult:
    """Bring one account up to ``session``. A new account starts there; one already at it is left alone."""
    from osloquant.domain import StockAction

    state = load_state(account.name)
    if state is not None and pd.Timestamp(state["last_session"]) >= session:
        return StepResult(account.name, "up to date")
    start = session if state is None else pd.Timestamp(state["start"])

    actions = StockAction.query_data(start_timestamp=start, end_timestamp=session, columns=["entity_id", "timestamp", "dividend", "split"])
    trader = resolve_strategy(account.strategy)(
        start_timestamp=start,
        end_timestamp=session,
        trader_name=account.name,
        adjust_type="raw",
        signal_adjust_type="adj",
        corporate_actions=actions,
        mode="live",
        input_money=account.input_money if state is None else state["input_money"],
        max_positions=account.max_positions,
        buy_cost=config.commission_rate,
        sell_cost=config.commission_rate,
        min_cost=config.commission_min,
        slippage=config.slippage,
    )
    trader.wall_clock = wall_clock
    if state is not None:
        trader.account.restore(state["account"])
        trader.trading_signals = [_signal_from_dict(s) for s in state["pending"]]
    trader.run(after=None if state is None else pd.Timestamp(state["last_session"]))

    if not trader.sessions_processed:
        return StepResult(account.name, "up to date")
    save_state(
        account.name,
        {
            "start": start.isoformat(),
            "last_session": trader.sessions_processed[-1].isoformat(),
            "strategy": account.strategy,
            "input_money": trader.account.input_money,
            "account": trader.account.to_state(),
            "pending": [_signal_to_dict(s) for s in trader.trading_signals],
        },
        wall_clock,
    )
    return StepResult(account.name, "started" if state is None else "stepped", sessions=trader.sessions_processed)


@dataclass
class LiveRun:
    session: pd.Timestamp | None
    wall_clock: pd.Timestamp
    results: list[StepResult]
    recorded: list = field(default_factory=list)
    record_error: str | None = None
    config: LiveConfig | None = None


def run_live(record: bool = True, now: pd.Timestamp | None = None, config: LiveConfig | None = None) -> LiveRun:
    """The evening job: record, find the session, step every account. One failing account does not stop the others."""
    config = load_config() if config is None else config
    wall_clock = (pd.Timestamp.now(tz="UTC") if now is None else now.tz_convert("UTC")).tz_localize(None)
    run = LiveRun(session=None, wall_clock=wall_clock, results=[], config=config)

    if record:
        try:
            run.recorded = record_market_data()
        except Exception as e:  # stale data must be visible, but yesterday's sessions can still be stepped
            run.record_error = f"{type(e).__name__}: {e}"
            logger.warning("recording failed: %s", e)

    run.session = last_completed_session(now)
    if run.session is None:
        return run
    for account in config.accounts:
        try:
            run.results.append(step_account(account, config, run.session, wall_clock))
        except Exception as e:
            logger.exception("account %s failed", account.name)
            run.results.append(StepResult(account.name, "failed", error=f"{type(e).__name__}: {e}"))
    return run


# -- reading an account ---------------------------------------------------------------------------


def live_account_names() -> list[str]:
    df = get_data(TraderInfo, provider=PROVIDER, filters=[TraderInfo.mode == "live"], columns=["trader_name"], order=TraderInfo.trader_name.asc())
    return df["trader_name"].tolist()


def account_summary(name: str) -> dict:
    """Where a live account stands, in plain since-the-start numbers (nothing annualised)."""
    from osloquant.domain import Stock
    from osloquant.trader.stats import get_benchmark_series

    state = load_state(name)
    if state is None:
        raise LookupError(f"no live account named {name!r}")
    stats = get_data(AccountStats, provider=PROVIDER, filters=[AccountStats.trader_name == name], index="timestamp")
    names = Stock.query_data(columns=["entity_id", "code", "name"]).set_index("entity_id")
    input_money = float(stats["input_money"].iloc[0])
    value = float(stats["all_value"].iloc[-1])

    def label(entity_id: str) -> tuple[str, str]:
        if entity_id in names.index:
            return names.loc[entity_id, "code"], names.loc[entity_id, "name"]
        return entity_id.split("_", 2)[2], ""

    holdings = []
    for h in sorted(state["account"]["holdings"], key=lambda h: -h["amount"] * h["last_price"]):
        code, company = label(h["entity_id"])
        holdings.append(
            {"entity_id": h["entity_id"], "code": code, "name": company, "shares": h["amount"], "average_price": h["average_price"],
             "last_price": h["last_price"], "value": h["amount"] * h["last_price"], "profit_rate": h["profit_rate"]}
        )  # fmt: skip
    pending = []
    for s in state["pending"]:
        code, company = label(s["entity_id"])
        side = "buy" if s["type"] == TradingSignalType.open_long.value else "sell"
        pending.append({"entity_id": s["entity_id"], "code": code, "name": company, "side": side, "decided_on": pd.Timestamp(s["happen_timestamp"]), "decided_at": s["decided_at"]})

    orders = get_data(Order, provider=PROVIDER, filters=[Order.trader_name == name], order=Order.id.asc())
    trades = orders[orders["order_type"].isin(TRADES)] if not orders.empty else orders
    universe = stats["universe_value"].dropna()
    benchmark = get_benchmark_series(name, stats.index)

    return {
        "name": name,
        "strategy": state.get("strategy"),
        "start": pd.Timestamp(state["start"]),
        "last_session": pd.Timestamp(state["last_session"]),
        "sessions": int(len(stats)),
        "input_money": input_money,
        "value": value,
        "cash": float(stats["cash"].iloc[-1]),
        "total_return": value / input_money - 1,
        "universe_return": float(universe.iloc[-1] / input_money - 1) if len(universe) else None,
        "benchmark_return": float(benchmark.iloc[-1] / benchmark.iloc[0] - 1) if benchmark is not None and len(benchmark) else None,
        "holdings": holdings,
        "pending": pending,
        "fills": int(len(trades)),
        "forward_fills": int((trades["forward"] == 1).sum()) if not trades.empty else 0,
        "costs_paid": float(trades["cost"].sum()) if not trades.empty else 0.0,
        "dividends_received": float(orders.loc[orders["order_type"] == "dividend", "profit"].sum()) if not orders.empty else 0.0,
        "orders": orders,
    }
