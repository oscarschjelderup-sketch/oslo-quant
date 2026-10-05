"""Intraday rules and accounts on a synthetic market of 15-minute bars, with the clock under the test's control."""

import json

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from osloquant.cli import app
from osloquant.contract.storage import df_to_db
from osloquant.domain import Stock15mKdata, StockAction
from osloquant.intraday import (
    BUY,
    SELL,
    IntradayAccount,
    IntradayAccountConfig,
    IntradayConfig,
    Rule,
    account_summary,
    build_rule,
    engine,
    load_config,
    poll,
    poll_times,
    replay,
    run_session,
)
from osloquant.intraday.engine import config_path, daily_watchlist, order_bar
from osloquant.recorders.yahoo import client
from osloquant.trader import AccountStats, Order, TraderInfo
from osloquant.trader.schemas import IntradaySignal, IntradaySnapshot
from tests.helpers import bars as daily_bars
from tests.helpers import store_bars, store_stocks

A, B, C = "stock_ol_AAA", "stock_ol_BBB", "stock_ol_CCC"
DAY1, DAY2 = pd.Timestamp("2021-03-01"), pd.Timestamp("2021-03-02")  # a Monday and a Tuesday
BARS_PER_DAY = 30
runner = CliRunner(env={"COLUMNS": "220"})


def session(day: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(day + pd.Timedelta(hours=9), day + pd.Timedelta(hours=16, minutes=15), freq="15min")


def at(day: pd.Timestamp, clock: str) -> pd.Timestamp:
    return day + pd.Timedelta(f"{clock}:00")


def make_bars(closes, days=(DAY1, DAY2), opens=None, flags: dict | None = None) -> pd.DataFrame:
    """Bars over ``days``; the open is the previous close unless given. ``flags`` sets the volume of a bar,
    which is how the scripted rule below is told to fire: {bar start: 111 for BUY, 999 for SELL}."""
    index = session(days[0]).append([session(d) for d in days[1:]])
    closes = np.full(len(index), float(closes)) if np.isscalar(closes) else np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]] if opens is None else np.asarray(opens, dtype=float)
    df = pd.DataFrame({"open": opens, "high": np.maximum(opens, closes), "low": np.minimum(opens, closes), "close": closes, "volume": 1000.0}, index=index)
    for bar, flag in (flags or {}).items():
        df.loc[bar, "volume"] = flag
    return df


class FlagRule(Rule):
    """Fires when the newest bar's volume says so. Lets a test put a signal on exactly one bar."""

    code = "flag"

    def evaluate(self, bars):
        volume = bars["volume"].iloc[-1]
        if volume == 111:
            return self.signal(BUY, "flagged", bars)
        if volume == 999:
            return self.signal(SELL, "flagged", bars)
        return None


def trader(config: IntradayConfig | None = None, **account) -> IntradayAccount:
    defaults = {"name": "paper", "signal": {"rule": "tests.test_intraday:FlagRule"}, "watchlist": [A, B, C], "input_money": 10_000, "max_positions": 2}
    return IntradayAccount(IntradayAccountConfig(**{**defaults, **account}), config or free())


def free() -> IntradayConfig:
    return IntradayConfig(accounts=[], commission_rate=0.0, commission_min=0.0, slippage=0.0)


def run(account: IntradayAccount, bars: dict, times, watchlist=(A, B, C), **kwargs):
    return [account.step(t, bars, list(watchlist), **kwargs) for t in times]


def polls(day: pd.Timestamp, first: str, last: str) -> list[pd.Timestamp]:
    return [t for t in poll_times(day, pd.Timedelta(minutes=15)) if at(day, first) <= t <= at(day, last)]


# -- rules ----------------------------------------------------------------------------------------


def frame(closes, highs=None, lows=None) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    index = pd.date_range("2021-03-01 09:00", periods=len(closes), freq="15min")
    return pd.DataFrame({"open": closes, "high": closes if highs is None else highs, "low": closes if lows is None else lows, "close": closes, "volume": 1.0}, index=index)


def signals_over(rule: Rule, bars: pd.DataFrame) -> dict[int, str]:
    """Bar number -> signal code, asking the rule about each bar in turn as the bars arrive."""
    out = {}
    for i in range(rule.min_bars, len(bars) + 1):
        signal = rule.evaluate(bars.iloc[:i])
        if signal is not None:
            out[i - 1] = signal.code
            assert signal.bar == bars.index[i - 1] and signal.price == bars["close"].iloc[i - 1]
    return out


def test_ma_cross_fires_on_the_bar_of_the_cross_and_only_there():
    closes = [10.0] * 6 + [10, 11, 12, 13, 14, 15] + [14, 12, 10, 8, 6, 4, 4, 4]
    assert signals_over(build_rule({"rule": "ma_cross", "fast": 2, "slow": 5}), frame(closes)) == {7: BUY, 13: SELL}


def test_breakout_fires_once_when_the_range_is_left():
    closes = [10, 11, 10, 11, 10, 11, 10, 12, 13, 14, 13, 9, 8, 9]
    assert signals_over(build_rule({"rule": "breakout", "lookback": 5}), frame(closes)) == {7: BUY, 11: SELL}


def test_macd_cross_and_rsi_fire_on_a_turn():
    down_then_up = np.r_[np.linspace(100, 60, 100), np.linspace(60, 100, 60)]
    macd = signals_over(build_rule({"rule": "macd_cross"}), frame(down_then_up))
    assert list(macd.values()) == [BUY] and 100 <= next(iter(macd)) <= 110

    rsi = signals_over(build_rule({"rule": "rsi", "period": 14}), frame(np.r_[np.linspace(100, 60, 100), np.linspace(60, 100, 60), np.linspace(100, 90, 40)]))
    codes = list(rsi.values())
    assert codes[0] == BUY and SELL in codes  # out of oversold on the turn up, out of overbought on the turn down


def test_a_rule_reports_what_it_saw_in_words():
    signal = build_rule({"rule": "ma_cross", "fast": 2, "slow": 5}).evaluate(frame([10.0] * 6 + [10, 11]))
    assert signal.rule == "ma_cross" and signal.reason == "ma2 10.50 crossed above ma5 10.20"


def test_rules_are_built_by_code_or_by_import_path():
    assert build_rule({"rule": "breakout", "lookback": 7}).describe() == "breakout(lookback=7)"
    assert isinstance(build_rule({"rule": "tests.test_intraday:FlagRule"}), FlagRule)
    with pytest.raises(ValueError, match="unknown rule"):
        build_rule({"rule": "nonsense"})
    with pytest.raises(ValueError, match="fast must be shorter"):
        build_rule({"rule": "ma_cross", "fast": 20, "slow": 5})


# -- the clock ------------------------------------------------------------------------------------


def test_the_looks_follow_the_bars_through_the_delayed_feed():
    times = poll_times(DAY1, pd.Timedelta(minutes=15))
    # the 09:00 bar closes at 09:15 and comes through the feed at 09:30: look at 09:31
    assert len(times) == BARS_PER_DAY and times[0] == at(DAY1, "09:31") and times[-1] == at(DAY1, "16:46")


def test_an_order_is_filled_at_the_bar_starting_as_it_is_sent():
    assert order_bar(at(DAY1, "10:16")) == at(DAY1, "10:15")
    assert order_bar(at(DAY1, "10:22")) == at(DAY1, "10:30")  # sent late: the next bar


# -- one account ----------------------------------------------------------------------------------


def test_a_signal_is_seen_a_quarter_late_and_filled_at_the_price_the_market_has_moved_to():
    closes = np.full(60, 100.0)
    closes[30 + 3 :] = 110.0  # the 09:45 bar of day 2 jumps to 110 and raises the signal
    opens = np.r_[100.0, closes[:-1]]
    opens[30 + 5] = 113.0  # by the time the order arrives (the 10:15 bar) the market is at 113
    bars = {A: make_bars(closes, opens=opens, flags={at(DAY2, "09:45"): 111})}
    account = trader()

    run(account, bars, polls(DAY2, "09:31", "10:01"))
    assert account.pending == [] and not account.account.holdings  # the 09:45 bar has not come through yet

    (report,) = run(account, bars, [at(DAY2, "10:16")])
    assert [(s["code"], s["outcome"], s["timestamp"]) for s in report.signals] == [(BUY, "ordered", at(DAY2, "09:45"))]
    assert not account.account.holdings and account.pending[0]["bar"] == at(DAY2, "10:15")

    (report,) = run(account, bars, [at(DAY2, "10:31")])
    order = account.account.orders_df.iloc[0]
    assert (order["timestamp"], order["signal_timestamp"], order["order_price"]) == (at(DAY2, "10:15"), at(DAY2, "09:45"), 113.0)
    assert order["reason"] == "BUY flag: flagged" and order["order_amount"] == 44  # half of 10 000 at 113
    assert report.fills[0]["price"] == 113.0 and account.pending == []


def test_a_bar_still_forming_in_the_feed_raises_nothing():
    bars = {A: make_bars(100.0, flags={at(DAY2, "10:00"): 111})}
    account = trader()
    # at 10:16 the feed is at 10:01: the 10:00 bar exists but has not closed
    reports = run(account, bars, polls(DAY2, "09:31", "10:16"))
    assert all(r.signals == [] for r in reports)
    assert run(account, bars, [at(DAY2, "10:31")])[0].signals[0]["outcome"] == "ordered"


def test_a_signal_whose_moment_has_passed_is_not_acted_on():
    # the stock stops trading after its flagged 09:45 bar; the account is only started at noon
    quiet = make_bars(100.0, flags={at(DAY2, "09:45"): 111})
    quiet = quiet[quiet.index <= at(DAY2, "09:45")]
    account = trader()
    reports = run(account, {A: quiet}, polls(DAY2, "12:01", "13:01"))
    assert all(r.signals == [] for r in reports) and account.pending == []
    assert account.seen[A] == at(DAY2, "09:45")  # looked at, and deliberately let go


def test_each_bar_is_judged_once():
    bars = {A: make_bars(100.0, flags={at(DAY2, "09:45"): 111})}
    account = trader(max_positions=1)
    reports = run(account, bars, [at(DAY2, "10:16"), at(DAY2, "10:17"), at(DAY2, "10:18")])
    assert [len(r.signals) for r in reports] == [1, 0, 0]


def test_slots_watchlist_and_holdings_decide_what_a_buy_signal_leads_to():
    flag = {at(DAY2, "09:45"): 111}
    bars = {A: make_bars(100.0, flags=flag), B: make_bars(50.0, flags=flag), C: make_bars(20.0, flags=flag)}
    account = trader(max_positions=1)
    (report,) = run(account, bars, [at(DAY2, "10:16")], watchlist=(B, A))
    assert {s["entity_id"]: s["outcome"] for s in report.signals} == {B: "ordered", A: "skipped: no free slot"}  # C is not on the list and not held

    run(account, bars, [at(DAY2, "10:31")], watchlist=(B, A))
    assert set(account.account.holdings) == {B}
    again = {B: make_bars(50.0, flags={at(DAY2, "11:00"): 111}), A: bars[A], C: bars[C]}
    (report,) = run(account, again, [at(DAY2, "11:31")], watchlist=(B, A))
    assert [s["outcome"] for s in report.signals] == ["skipped: already held"]


def test_a_sell_signal_closes_a_holding_and_is_silent_otherwise():
    bars = {A: make_bars(100.0, flags={at(DAY2, "09:45"): 111, at(DAY2, "11:00"): 999}), B: make_bars(50.0, flags={at(DAY2, "11:00"): 999})}
    account = trader()
    reports = run(account, bars, polls(DAY2, "09:31", "12:01"))
    logged = [(s["entity_id"], s["code"], s["outcome"]) for r in reports for s in r.signals]
    assert logged == [(A, BUY, "ordered"), (A, SELL, "ordered")]  # B's sell signal is not news: it was never held
    orders = account.account.orders_df
    assert orders["order_type"].tolist() == ["order_long", "order_close_long"] and orders["timestamp"].tolist() == [at(DAY2, "10:15"), at(DAY2, "11:30")]
    assert not account.account.holdings and account.account.cash == 10_000


@pytest.mark.parametrize(
    "risk, path, code",
    [
        ({"stop_loss": 0.03}, [100, 100, 96, 96, 96], "STOP"),
        ({"take_profit": 0.05}, [100, 100, 106, 106, 106], "TARGET"),
        ({"trailing_stop": 0.04}, [100, 110, 105, 105, 105], "TRAIL"),
    ],
)
def test_the_risk_rules_sell_at_their_thresholds(risk, path, code):
    closes = np.full(60, 100.0)
    start = 30 + 6  # the 10:30 bar of day 2, after the purchase at the 10:15 open
    closes[start : start + len(path)] = path
    closes[start + len(path) :] = path[-1]
    bars = {A: make_bars(closes, flags={at(DAY2, "09:45"): 111})}
    account = trader(**risk)
    reports = run(account, bars, polls(DAY2, "09:31", "13:01"))

    exits = [s for r in reports for s in r.signals if s["code"] == code]
    assert len(exits) == 1 and exits[0]["rule"] == "risk" and exits[0]["outcome"] == "ordered"
    sell = account.account.orders_df.iloc[-1]
    assert sell["order_type"] == "order_close_long" and sell["reason"].startswith(f"{code} risk:")
    # judged on the bar that crossed the threshold, sold at the open of the bar two later: one for the feed, one for the order
    crossed = exits[0]["timestamp"]
    assert sell["timestamp"] == crossed + pd.Timedelta(minutes=30) and not account.account.holdings


def test_nothing_is_sold_while_no_threshold_is_crossed():
    bars = {A: make_bars(100.0, flags={at(DAY2, "09:45"): 111})}
    account = trader(stop_loss=0.03, take_profit=0.05, trailing_stop=0.04)
    run(account, bars, polls(DAY2, "09:31", "16:46"))
    assert set(account.account.holdings) == {A} and len(account.account.orders_df) == 1


def test_flat_at_close_sells_everything_before_the_close_and_buys_nothing_late():
    bars = {A: make_bars(100.0, flags={at(DAY2, "09:45"): 111}), B: make_bars(50.0, flags={at(DAY2, "15:30"): 111})}
    account = trader(flat_at_close=True)
    reports = run(account, bars, polls(DAY2, "09:31", "16:46"))

    logged = {(s["entity_id"], s["code"]): s["outcome"] for r in reports for s in r.signals}
    assert logged[(A, "CLOSE")] == "ordered" and logged[(B, BUY)] == "skipped: too close to the close"
    assert not account.account.holdings and account.account.orders_df["timestamp"].iloc[-1] == at(DAY2, "15:45")


def test_a_buy_that_cannot_be_filled_expires_but_a_sell_waits():
    stops_trading = make_bars(100.0, flags={at(DAY2, "09:45"): 111})
    stops_trading = stops_trading[stops_trading.index <= at(DAY2, "09:45")]
    account = trader()
    reports = run(account, {A: stops_trading}, polls(DAY2, "10:16", "12:01"))
    assert [s["outcome"] for r in reports for s in r.signals] == ["ordered", "expired: no trade to fill it on"]
    assert account.pending == []

    held = make_bars(100.0, flags={at(DAY1, "09:45"): 111, at(DAY1, "11:00"): 999})
    held = held[(held.index <= at(DAY1, "11:00")) | (held.index >= at(DAY2, "09:00"))]  # no trades for the rest of day 1
    account = trader()
    run(account, {A: held}, polls(DAY1, "09:31", "16:46"))
    assert account.pending and account.pending[0]["side"] == SELL
    run(account, {A: held}, polls(DAY2, "09:31", "10:01"))
    assert not account.account.holdings and account.account.orders_df["timestamp"].iloc[-1] == at(DAY2, "09:00")


def test_a_buy_signal_after_the_last_bar_has_started_is_not_ordered():
    bars = {A: make_bars(100.0, flags={at(DAY2, "16:00"): 111})}
    account = trader()
    reports = run(account, bars, polls(DAY2, "16:16", "16:46"))
    assert [s["outcome"] for r in reports for s in r.signals] == ["skipped: the market has closed"]


def test_an_account_rebuilt_from_its_saved_state_at_every_look_ends_where_one_kept_in_memory_does():
    rng = np.random.default_rng(3)
    flags = lambda: {t: (111 if rng.random() < 0.5 else 999) for t in rng.choice(session(DAY2), 6, replace=False)}  # noqa: E731
    bars = {e: make_bars(100 * np.cumprod(1 + rng.normal(0, 0.004, 60)), flags={pd.Timestamp(t): f for t, f in flags().items()}) for e in (A, B, C)}
    times = polls(DAY2, "09:31", "16:46")
    config, cfg = free(), IntradayAccountConfig(name="paper", signal={"rule": "tests.test_intraday:FlagRule"}, input_money=10_000, max_positions=2, stop_loss=0.01)

    kept = IntradayAccount(cfg, config)
    run(kept, bars, times)

    state, orders = None, []
    for when in times:
        rebuilt = IntradayAccount(cfg, config, None if state is None else json.loads(json.dumps(state)))
        rebuilt.step(when, bars, [A, B, C])
        state, orders = rebuilt.to_state(), [*orders, *rebuilt.account.orders_df.to_dict("records")]

    assert len(orders) == len(kept.account.orders_df) > 2
    assert [o["id"] for o in orders] == kept.account.orders_df["id"].tolist()
    assert [o["order_price"] for o in orders] == kept.account.orders_df["order_price"].tolist()
    assert state["account"]["cash"] == pytest.approx(kept.account.cash) and state["pending"] == kept.to_state()["pending"]


def test_a_dividend_goes_to_a_holding_bought_before_the_day_and_only_once():
    bars = {A: make_bars(100.0, flags={at(DAY1, "09:45"): 111}), B: make_bars(50.0, flags={at(DAY2, "09:45"): 111})}
    actions = pd.DataFrame({"entity_id": [A, B], "timestamp": [DAY2, DAY2], "dividend": [2.0, 1.0], "split": [0.0, 0.0]})
    account = trader()
    run(account, bars, polls(DAY1, "09:31", "16:46"), actions=actions)
    assert account.account.cash == 5_000  # nothing yet: the day has not come

    run(account, bars, polls(DAY2, "09:31", "16:46"), actions=actions)
    dividends = account.account.orders_df[account.account.orders_df["order_type"] == "dividend"]
    # A was held going into day 2; B was bought during it and has no claim
    assert dividends["entity_id"].tolist() == [A] and dividends["profit"].tolist() == [100.0]


# -- the watchlist --------------------------------------------------------------------------------


def test_a_factor_watchlist_is_made_on_the_close_before_the_day():
    store_stocks(["AAA", "BBB"])
    rising = np.r_[np.full(15, 100.0), np.linspace(101, 130, 15)]
    store_bars(daily_bars(A, rising, start="2021-01-18"))  # 30 business days, the last one is Friday 26 February
    store_bars(daily_bars(B, rising[::-1].copy(), start="2021-01-18"))

    watchlist, as_of = daily_watchlist("CrossMaFactor", DAY1)
    assert (watchlist, as_of) == ([A], pd.Timestamp("2021-02-26"))
    assert daily_watchlist(["bbb", "AAA.OL"], DAY1)[0] == [A, B] and daily_watchlist("all", DAY1)[0] == [A, B]
    with pytest.raises(ValueError, match="not a factor"):
        daily_watchlist("NoSuchFactor", DAY1)


# -- polling over the store -----------------------------------------------------------------------


def store_intraday(entity_id: str, frame: pd.DataFrame) -> None:
    df = frame.reset_index(names="timestamp")
    df["entity_id"] = entity_id
    df["id"] = [f"{entity_id}_{t:%Y-%m-%dT%H:%M}" for t in df["timestamp"]]
    df["code"] = entity_id.split("_", 2)[2]
    df_to_db(df, Stock15mKdata, "yahoo")


@pytest.fixture
def market():
    store_stocks(["AAA", "BBB"])
    closes = np.full(60, 100.0)
    closes[30 + 8 :] = 96.0  # falls through the stop after the purchase
    store_intraday(A, make_bars(closes, flags={at(DAY2, "09:45"): 111}))
    store_intraday(B, make_bars(50.0, flags={at(DAY2, "10:00"): 111}))
    return IntradayConfig(
        accounts=[IntradayAccountConfig(name="paper", signal={"rule": "tests.test_intraday:FlagRule"}, watchlist=["AAA", "BBB"], stop_loss=0.03, input_money=100_000, max_positions=2)],
        commission_rate=0.0015, commission_min=29.0, slippage=0.001,
    )  # fmt: skip


def test_polling_through_a_day_stores_the_orders_the_signals_and_the_account(market):
    for when in polls(DAY2, "09:31", "16:46"):
        result = poll(market, now=when, record=False)
        assert result.errors == {} and result.feed_lag is not None

    orders = Order.query_data(order=Order.id.asc())
    assert orders["order_type"].tolist() == ["order_long", "order_long", "order_close_long"]
    assert orders["id"].is_unique and (orders["forward"] == 1).all() and orders["decided_at"].notna().all()
    assert (orders["cost"] >= 29).all() and orders["level"].unique().tolist() == ["15m"]
    assert orders["reason"].iloc[-1].startswith("STOP risk: 96.00 is -4.")

    signals = IntradaySignal.query_data(order=IntradaySignal.id.asc())
    assert signals["code"].tolist() == [BUY, BUY, "STOP"] and signals["outcome"].unique().tolist() == ["ordered"]
    assert len(IntradaySnapshot.query_data()) == BARS_PER_DAY
    day_rows = AccountStats.query_data()
    assert len(day_rows) == 1 and day_rows["timestamp"].iloc[0] == DAY2  # one row per day, kept up to date
    info = TraderInfo.query_data().iloc[0]
    assert (info["mode"], info["level"], info["min_cost"]) == ("intraday", "15m", 29.0)

    summary = account_summary("paper")
    assert summary["kind"] == "intraday" and summary["strategy"] == "flag()"
    assert [h["code"] for h in summary["holdings"]] == ["BBB"] and summary["round_trips"] == 1 and summary["win_rate"] == 0.0
    assert summary["fills"] == summary["forward_fills"] == 3 and summary["watchlist"] == ["AAA", "BBB"]
    assert summary["value"] == pytest.approx(day_rows["all_value"].iloc[0]) and summary["value"] < 100_000
    assert summary["signals"]["stock"].tolist() == ["AAA", "BBB", "AAA"]


def test_polling_twice_at_the_same_moment_books_nothing_twice(market):
    for when in polls(DAY2, "09:31", "10:46"):
        poll(market, now=when, record=False)
    before = (Order.query_data(), IntradaySignal.query_data())
    poll(market, now=at(DAY2, "10:46"), record=False)
    pd.testing.assert_frame_equal(before[0], Order.query_data())
    pd.testing.assert_frame_equal(before[1], IntradaySignal.query_data())


def test_one_broken_account_does_not_stop_the_other(market):
    market.accounts.insert(0, IntradayAccountConfig(name="broken", signal={"rule": "nonsense"}))
    result = poll(market, now=at(DAY2, "10:16"), record=False)
    assert list(result.errors) == ["broken"] and [r.name for r in result.reports] == ["paper"]


def test_a_replay_is_the_live_run_played_over_stored_bars_and_stores_nothing(market):
    result = replay(market.accounts[0], market, days=5, end=at(DAY2, "23:00"))

    assert result.days == 2 and (result.start, result.end) == (DAY1, DAY2)
    assert result.orders["order_type"].tolist() == ["order_long", "order_long", "order_close_long"]
    assert len(result.signals) == 3 and result.total_return < 0
    assert result.daily_values.index.tolist() == [DAY1, DAY2] and result.daily_values.iloc[0] == 100_000
    assert Order.query_data().empty and TraderInfo.query_data().empty

    for when in polls(DAY1, "09:31", "16:46") + polls(DAY2, "09:31", "16:46"):
        poll(market, now=when, record=False)
    live = Order.query_data(order=Order.id.asc())
    assert live["order_price"].tolist() == result.orders["order_price"].tolist() and live["timestamp"].tolist() == result.orders["timestamp"].tolist()


def test_dividends_reach_a_polled_account_from_the_store(market):
    for when in polls(DAY2, "09:31", "16:46"):
        poll(market, now=when, record=False)
    day3 = pd.Timestamp("2021-03-03")
    store_intraday(B, make_bars(50.0, days=(day3,)))
    df_to_db(pd.DataFrame([{"id": f"{B}_2021-03-03", "entity_id": B, "timestamp": day3, "dividend": 1.5, "split": 0.0}]), StockAction, "yahoo")
    poll(market, now=at(day3, "09:31"), record=False)
    poll(market, now=at(day3, "09:46"), record=False)

    dividends = Order.query_data(filters=[Order.order_type == "dividend"])
    assert len(dividends) == 1 and dividends["entity_id"].iloc[0] == B and dividends["order_price"].iloc[0] == 1.5


# -- the session loop -----------------------------------------------------------------------------


@pytest.mark.parametrize("started, expected", [("08:40", 30), ("12:05", 20), ("16:50", 0)])
def test_the_session_loop_waits_polls_and_stops(monkeypatch, started, expected):
    now = [at(DAY2, started)]
    looks = []

    def fake_sleep(seconds):
        now[0] += pd.Timedelta(seconds=seconds)

    monkeypatch.setattr(engine, "poll", lambda config, now=None, record=True: looks.append(now))
    made = run_session(free(), sleep=fake_sleep, clock=lambda: now[0])

    assert made == len(looks) == expected
    if started == "08:40":
        assert looks[0] == at(DAY2, "09:31") and looks[-1] == at(DAY2, "16:46")
    if started == "12:05":
        assert looks[0] == at(DAY2, "12:05") and looks[1] == at(DAY2, "12:16")  # at once, then back on the grid


def test_the_session_loop_does_nothing_on_a_weekend(monkeypatch):
    monkeypatch.setattr(engine, "poll", lambda *a, **k: pytest.fail("polled on a Saturday"))
    assert run_session(free(), sleep=lambda s: None, clock=lambda: pd.Timestamp("2021-03-06 10:00")) == 0


# -- recording, configuration, commands -----------------------------------------------------------


def test_intraday_bars_are_recorded_with_the_time_in_their_id_and_history_is_kept(monkeypatch):
    store_stocks(["AAA"])
    full = make_bars(100 + np.arange(60) * 0.1).reset_index(names="timestamp")
    served = {"rows": full.iloc[:40]}
    # the recorder never asks Yahoo for more than it keeps; these bars are from 2021, so lift that limit here
    from osloquant.recorders.yahoo.kdata_recorder import YahooStock15mKdataRecorder

    monkeypatch.setattr(YahooStock15mKdataRecorder, "history_days", 100_000)
    monkeypatch.setattr(client, "fetch_intraday", lambda symbol, start, interval="15m": served["rows"][served["rows"]["timestamp"] >= start].reset_index(drop=True))

    Stock15mKdata.record_data(start_timestamp="2021-03-01")
    served["rows"] = full.iloc[30:]  # Yahoo has dropped the first day and added bars
    Stock15mKdata.record_data(start_timestamp="2021-03-02")

    stored = Stock15mKdata.query_data(code="AAA")
    assert len(stored) == 60 and stored["id"].iloc[0] == "stock_ol_AAA_2021-03-01T09:00"
    assert stored["timestamp"].iloc[-1] == at(DAY2, "16:15") and stored["level"].unique().tolist() == ["15m"]
    assert stored["turnover"].iloc[0] == pytest.approx(100.0 * 1000)


def test_the_default_intraday_configuration():
    config = load_config()
    assert config.created and config.path == config_path() and not load_config().created
    names = [a.name for a in config.accounts]
    assert names == ["daytrade_orb", "daytrade_breakout", "intraday_ma", "intraday_breakout", "intraday_ma_slow", "intraday_breakout_slow"]
    orb, day_breakout = config.accounts[:2]
    assert orb.signal == {"rule": "opening_range", "minutes": 30} and orb.watchlist == "all" and day_breakout.signal == {"rule": "breakout", "lookback": 60}
    for bot in (orb, day_breakout):
        assert bot.flat_at_close and not bot.exit_on_signal and bot.entry_window == ["09:30", "14:30"] and bot.max_entries_per_stock_per_day == 1
        assert (bot.max_positions, bot.max_per_sector, bot.min_relative_volume, bot.min_range_to_cost, bot.stop_loss) == (3, 1, 1.5, 4, 0.02)
    assert config.feed_delay == pd.Timedelta(minutes=15) and (config.commission_rate, config.commission_min) == (0.0015, 29.0)
    ma, breakout, ma_slow, breakout_slow = config.accounts[2:]
    assert ma_slow.signal == {"rule": "ma_cross", "fast": 20, "slow": 60} and breakout_slow.signal == {"rule": "breakout", "lookback": 60}
    # the slow twins differ from the fast ones in the speed of the rule and in nothing else
    assert (ma_slow.stop_loss, ma_slow.take_profit, breakout_slow.trailing_stop) == (ma.stop_loss, ma.take_profit, 0.04)
    assert ma.signal == {"rule": "ma_cross", "fast": 5, "slow": 20} and (ma.stop_loss, ma.take_profit, ma.max_positions) == (0.03, 0.06, 5)
    assert breakout.trailing_stop == 0.04 and breakout.watchlist == "MomentumFactor"
    for account in config.accounts:
        IntradayAccount(account, config)  # the rules named in the default file exist


def test_the_commands(market, home):
    config_path().write_text(
        "feed_delay_minutes: 15\ncosts: {commission_rate: 0.0015, commission_min: 29, slippage: 0.001}\n"
        "accounts:\n  - {name: paper, signal: {rule: 'tests.test_intraday:FlagRule'}, watchlist: [AAA, BBB], stop_loss: 0.03, max_positions: 2}\n",
        encoding="utf-8",
    )
    assert "No intraday account yet" in runner.invoke(app, ["intraday", "status"]).output

    # the real clock is years after these bars: a look now finds nothing fresh, which is the point of the freshness rule
    look = runner.invoke(app, ["intraday", "poll", "--no-record"])
    assert look.exit_code == 0, look.output
    assert "paper: 100,000" in look.output and "signal" not in look.output

    status = runner.invoke(app, ["intraday", "status"])
    assert status.exit_code == 0 and "paper (flag())" in status.output and "Watchlist: AAA, BBB" in status.output

    played = runner.invoke(app, ["intraday", "replay", "--no-record", "--days", "5000"])
    assert played.exit_code == 0, played.output
    assert "paper" in played.output and "flag()" in played.output and "nothing stored" in played.output
    # the position that hit its stop shows up in the breakdown, and free trading is the better of the two numbers
    assert "How the positions were closed" in played.output and "STOP" in played.output and "With free trading" in played.output
    assert "Without the best trade" in played.output and "Per round trip before costs" in played.output

    trial = runner.invoke(app, ["intraday", "replay", "--no-record", "--days", "5000", "--rule", "breakout", "--param", "lookback=7",
                                "--watchlist", "AAA,BBB", "--stop-loss", "0.02", "--cooldown", "4", "--positions", "1"])  # fmt: skip
    assert trial.exit_code == 0, trial.output
    assert "trial" in trial.output and "breakout(lookback=7)" in trial.output
    assert runner.invoke(app, ["intraday", "replay", "--no-record", "--rule", "ma_cross", "--param", "fast"]).exit_code != 0

    listing = runner.invoke(app, ["intraday", "rules"])
    assert listing.exit_code == 0 and all(code in listing.output for code in ("ma_cross", "breakout", "macd_cross", "rsi", "opening_range", "fast=5", "cooldown_bars", "min_range_to_cost"))
    assert (home / "logs" / "intraday.log").read_text(encoding="utf-8").count("paper=100000") == 1


def test_the_dashboard_shows_an_intraday_account(market):
    from osloquant.ui import app as ui

    for when in polls(DAY2, "09:31", "16:46"):
        poll(market, now=when, record=False)
    assert "paper" in str(ui.serve_layout())

    tiles, notes, pending, holdings, figure, orders, signals = ui.show_live("paper")
    assert len(tiles) == 7 and "Round trips" in str(tiles[3]) and "3 at prices not yet seen when ordered" in str(tiles[4])
    assert "Looks made today" in str(tiles[6]) and "Is it running?" in str(ui.serve_layout())
    assert "flag() rule on 15-minute bars" in notes and "It may buy: AAA, BBB" in notes and "No real money" in notes
    assert "BBB" in str(holdings) and "Cash" in str(holdings)
    assert figure.data[0].name == "paper" and len(figure.data[0].y) == BARS_PER_DAY
    assert "STOP risk" in str(orders) and "Signals, newest first" in str(signals) and "ordered" in str(signals)


def test_a_scheduler_can_call_every_quarter_and_only_trading_hours_count():
    from osloquant.intraday.engine import worth_looking

    delay = pd.Timedelta(minutes=15)
    assert [worth_looking(at(DAY2, clock), delay) for clock in ("08:46", "09:31", "12:16", "16:46", "17:16")] == [False, True, True, True, False]
    assert not worth_looking(pd.Timestamp("2021-03-06 12:16"), delay)  # a Saturday


def test_the_poll_command_stays_quiet_when_oslo_is_closed(home, monkeypatch):
    from osloquant.intraday import engine as intraday_engine

    monkeypatch.setattr(intraday_engine, "market_now", lambda: pd.Timestamp("2021-03-06 12:16"))
    monkeypatch.setattr(intraday_engine, "poll", lambda *a, **k: pytest.fail("looked at a closed market"))
    result = runner.invoke(app, ["intraday", "poll", "--if-open"])
    assert result.exit_code == 0 and "Oslo is closed" in result.output
    assert not (home / "logs" / "intraday.log").exists()


def test_a_stock_just_sold_is_left_alone_for_the_cooldown():
    flags = {at(DAY2, "09:45"): 111, at(DAY2, "10:45"): 999, at(DAY2, "11:15"): 111, at(DAY2, "13:00"): 111}
    bars = {A: make_bars(100.0, flags=flags)}

    eager = trader()
    run(eager, bars, polls(DAY2, "09:31", "14:01"))
    assert eager.account.orders_df["order_type"].tolist() == ["order_long", "order_close_long", "order_long"]  # buys straight back

    patient = trader(cooldown_bars=4)
    reports = run(patient, bars, polls(DAY2, "09:31", "14:01"))
    outcomes = [s["outcome"] for r in reports for s in r.signals]
    # sold at the 11:15 bar; the signal on that very bar is inside the hour of cooling off, the one at 13:00 is not
    assert outcomes == ["ordered", "ordered", "skipped: cooling off after the last sale", "ordered"]
    assert patient.account.orders_df["timestamp"].tolist() == [at(DAY2, "10:15"), at(DAY2, "11:15"), at(DAY2, "13:30")]


def test_the_scheduler_tick_asks_the_clock_before_loading_anything(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from osloquant import tick

    oslo = ZoneInfo("Europe/Oslo")
    when = lambda text: datetime.fromisoformat(text).replace(tzinfo=oslo)  # noqa: E731
    assert [tick.might_be_open(when(t)) for t in ("2026-10-05 08:59", "2026-10-05 09:00", "2026-10-05 12:16", "2026-10-05 17:30", "2026-10-05 17:31")] == [False, True, True, True, False]
    assert not tick.might_be_open(when("2026-10-03 12:16"))  # a Saturday

    called = []
    monkeypatch.setattr("osloquant.cli.app", lambda args: called.append(args))
    monkeypatch.setattr(tick, "might_be_open", lambda: False)
    assert tick.main() == 0 and called == []
    monkeypatch.setattr(tick, "might_be_open", lambda: True)
    assert tick.main() == 0 and called == [["intraday", "poll", "--if-open"]]
