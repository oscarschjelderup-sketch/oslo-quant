"""The day-trade settings and filters, and the opening-range rule."""

import json

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from osloquant.cli import app
from osloquant.contract.storage import df_to_db
from osloquant.domain import Stock1dKdata
from osloquant.intraday import (
    BUY,
    SELL,
    IntradayAccount,
    IntradayAccountConfig,
    IntradayConfig,
    Rule,
    build_rule,
    replay,
)
from osloquant.intraday.engine import config_path, daily_range_table, ranges_as_of, relative_volume
from tests.helpers import store_stocks
from tests.test_intraday import DAY1, DAY2, A, B, C, at, make_bars, polls, run, session, store_intraday

runner = CliRunner(env={"COLUMNS": "240"})


class AtTimes(Rule):
    """BUY on the bars starting at ``buy`` times, SELL on those at ``sell``: a signal exactly where a test wants it."""

    code = "at_times"

    def __init__(self, buy=(), sell=()) -> None:
        super().__init__(buy=list(buy), sell=list(sell))
        self.buy, self.sell = set(buy), set(sell)

    def evaluate(self, bars):
        clock = bars.index[-1].strftime("%H:%M")
        if clock in self.buy:
            return self.signal(BUY, f"scripted at {clock}", bars)
        if clock in self.sell:
            return self.signal(SELL, f"scripted at {clock}", bars)
        return None


def costless() -> IntradayConfig:
    return IntradayConfig(accounts=[], commission_rate=0.0, commission_min=0.0, slippage=0.0)


def bot(buy=(), sell=(), config: IntradayConfig | None = None, **settings) -> IntradayAccount:
    defaults = {"name": "bot", "signal": {"rule": "tests.test_daytrade:AtTimes", "buy": list(buy), "sell": list(sell)}, "watchlist": [A, B, C],
                "input_money": 30_000, "max_positions": 3}  # fmt: skip
    return IntradayAccount(IntradayAccountConfig(**{**defaults, **settings}), config or costless())


def outcomes(reports) -> list[tuple[str, str, str]]:
    return [(s["entity_id"], s["code"], s["outcome"]) for r in reports for s in r.signals]


# -- the opening-range rule -----------------------------------------------------------------------


def opening_day(closes, highs=None, lows=None, start="09:00") -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    index = pd.date_range(at(DAY2, start), periods=len(closes), freq="15min")
    return pd.DataFrame(
        {"open": closes, "high": closes if highs is None else highs, "low": closes if lows is None else lows, "close": closes, "volume": 1.0}, index=index
    )


def signals_over(rule: Rule, bars: pd.DataFrame) -> dict[str, str]:
    out = {}
    for i in range(rule.min_bars, len(bars) + 1):
        signal = rule.evaluate(bars.iloc[:i])
        if signal is not None:
            out[bars.index[i - 1].strftime("%H:%M")] = signal.code
    return out


def test_opening_range_buys_the_break_of_the_first_half_hour_once():
    # the first two bars span 99-101; the 10:00 bar breaks out and the price stays up
    closes = [100, 100.5, 100.8, 102, 103, 102.5, 103]
    bars = opening_day(closes, highs=[101, 100.8, 101, 102, 103, 103, 103], lows=[99, 99.5, 100.2, 101, 102, 102, 102.5])
    rule = build_rule({"rule": "opening_range", "minutes": 30})
    assert signals_over(rule, bars) == {"09:45": BUY}
    signal = rule.evaluate(bars.iloc[:4])
    assert signal.reason == "close 102.00 broke above the 30-minute opening range high 101.00"


def test_opening_range_sells_the_break_below_and_ignores_yesterday():
    yesterday = make_bars(100.0, days=(DAY1,))
    yesterday["high"], yesterday["low"] = 150.0, 50.0  # a wild yesterday must not widen today's range
    today = opening_day([100, 100, 100, 98, 97], highs=[101, 100.5, 100, 100, 98], lows=[99, 99.5, 99.8, 98, 97])
    bars = pd.concat([yesterday, today])
    assert signals_over(build_rule({"rule": "opening_range"}), bars) == {"09:45": SELL}


def test_opening_range_needs_a_whole_range_from_the_open():
    late_start = opening_day([100, 103, 104], start="09:15")  # nothing traded at 09:00
    gap = opening_day([100, 103, 104]).drop(at(DAY2, "09:15"))  # nothing traded at 09:15
    rule = build_rule({"rule": "opening_range"})
    assert signals_over(rule, late_start) == {} and signals_over(rule, gap) == {}
    with pytest.raises(ValueError, match="multiple of 15"):
        build_rule({"rule": "opening_range", "minutes": 20})


# -- day-trade settings ---------------------------------------------------------------------------


def test_day_trade_is_shorthand_for_four_settings_and_each_can_still_be_set():
    cfg = IntradayAccountConfig(name="x", signal={"rule": "ma_cross"}, day_trade=True)
    assert (cfg.flat_at_close, cfg.exit_on_signal, cfg.entry_window, cfg.max_entries_per_stock_per_day) == (True, False, ["09:30", "14:30"], 1)
    own = IntradayAccountConfig(name="x", signal={"rule": "ma_cross"}, day_trade=True, exit_on_signal=True, entry_window=["10:00", "12:00"], max_entries_per_stock_per_day=2)
    assert (own.flat_at_close, own.exit_on_signal, own.entry_window, own.max_entries_per_stock_per_day) == (True, True, ["10:00", "12:00"], 2)
    plain = IntradayAccountConfig(name="x", signal={"rule": "ma_cross"})
    assert (plain.flat_at_close, plain.exit_on_signal, plain.entry_window) == (False, True, None)
    with pytest.raises(ValueError, match="entry_window"):
        IntradayAccountConfig(name="x", signal={"rule": "ma_cross"}, entry_window=["15:00", "10:00"])


def test_buys_only_inside_the_entry_window():
    bars = {A: make_bars(100.0), B: make_bars(50.0), C: make_bars(20.0)}
    account = bot(buy=["09:15", "10:00", "14:45"], entry_window=["09:30", "14:30"])
    found = {(e, o) for e, _, o in outcomes(run(account, bars, polls(DAY2, "09:31", "15:16")))}
    assert {o for _, o in found} == {"ordered", "skipped: outside the entry window 09:30-14:30", "skipped: already held"}
    first = [o for e, _, o in outcomes(run(bot(buy=["09:15"], entry_window=["09:30", "14:30"]), bars, polls(DAY2, "09:31", "09:46")))]
    assert set(first) == {"skipped: outside the entry window 09:30-14:30"}


def test_a_day_trader_holds_until_its_stop_or_the_close_and_ignores_the_rules_sell():
    bars = {A: make_bars(100.0)}
    account = bot(buy=["09:45"], sell=["11:00"], day_trade=True)
    reports = run(account, bars, polls(DAY2, "09:31", "16:46"))

    logged = outcomes(reports)
    assert (A, BUY, "ordered") in logged and (A, SELL, "not acted on: this account exits by its stops and at the close") in logged
    assert (A, "CLOSE", "ordered") in logged
    orders = account.account.orders_df
    assert orders["order_type"].tolist() == ["order_long", "order_close_long"]
    assert orders["timestamp"].dt.normalize().nunique() == 1 and not account.account.holdings  # in and out the same day
    assert orders["timestamp"].iloc[-1] == at(DAY2, "15:45")


def test_one_entry_per_stock_a_day_and_a_cap_on_the_day():
    flat = make_bars(100.0)
    flat.loc[at(DAY2, "10:30"):, "close"] = 97.0  # A falls through its stop after the purchase
    bars = {A: flat, B: make_bars(50.0), C: make_bars(20.0)}
    account = bot(buy=["09:45", "12:00"], stop_loss=0.02, max_entries_per_stock_per_day=1, max_entries_per_day=2, max_positions=3)
    logged = outcomes(run(account, bars, polls(DAY2, "09:31", "13:01")))

    at_noon = {e: o for e, c, o in logged if c == BUY and o != "ordered"}
    assert [o for e, c, o in logged if c == BUY][:3] == ["ordered", "ordered", "skipped: 2 entries today already"]
    assert at_noon[A] == "skipped: already traded today"  # stopped out, and not bought back the same day

    tomorrow = pd.Timestamp("2021-03-03")
    more = {e: pd.concat([frame, make_bars(frame["close"].iloc[-1], days=(tomorrow,))]) for e, frame in bars.items()}
    next_day = outcomes(run(account, more, polls(tomorrow, "09:31", "10:16")))
    assert any(e == A and o == "ordered" for e, _, o in next_day)  # a new day, a new allowance


def test_entries_of_the_day_survive_a_restart_of_the_account():
    bars = {A: make_bars(100.0)}
    settings = {"buy": ["09:45", "12:00"], "sell": [], "max_entries_per_stock_per_day": 1, "take_profit": 0.0001}
    first = bot(**settings)
    bars[A].loc[at(DAY2, "10:30"):, "close"] = 101.0  # sold at the target before noon
    run(first, bars, polls(DAY2, "09:31", "11:31"))
    assert not first.account.holdings

    again = IntradayAccount(first.cfg, costless(), json.loads(json.dumps(first.to_state())))
    logged = outcomes(run(again, bars, polls(DAY2, "11:46", "12:31")))
    assert (A, BUY, "skipped: already traded today") in logged


# -- the filters ----------------------------------------------------------------------------------


def busy_bars(volume_at_ten: float, price: float = 100.0) -> pd.DataFrame:
    bars = make_bars(price)
    bars["volume"] = 1000.0
    bars.loc[at(DAY2, "10:00"), "volume"] = volume_at_ten
    return bars


def test_relative_volume_compares_with_the_sessions_before():
    bars = busy_bars(3000.0)
    assert relative_volume(bars.loc[: at(DAY2, "10:00")]) == pytest.approx(3.0)
    assert relative_volume(bars.loc[: at(DAY1, "12:00")]) is None  # nothing before the first day


def test_a_quiet_signal_is_skipped_and_the_busiest_is_taken_first():
    bars = {A: busy_bars(3000.0), B: busy_bars(1200.0)}
    strict = bot(buy=["10:00"], watchlist=[B, A], min_relative_volume=1.5)
    logged = {e: o for e, _, o in outcomes(run(strict, bars, polls(DAY2, "10:31", "10:31")))}
    assert logged == {A: "ordered", B: "skipped: volume 1.2x normal, under 1.5x"}

    one_slot = bot(buy=["10:00"], watchlist=[B, A], min_relative_volume=1.0, max_positions=1)
    logged = outcomes(run(one_slot, bars, polls(DAY2, "10:31", "10:31")))
    assert logged == [(A, BUY, "ordered"), (B, BUY, "skipped: no free slot")]  # A trades three times its usual volume


def test_a_stock_that_does_not_move_enough_to_pay_for_the_trade_is_skipped():
    config = IntradayConfig(accounts=[], commission_rate=0.0015, commission_min=29.0, slippage=0.001)
    account = bot(buy=["10:00"], config=config, input_money=100_000, max_positions=3, min_range_to_cost=4)
    assert account.round_trip_cost() == pytest.approx(2 * (0.0015 + 0.001))  # 33 333 a position: the minimum does not bind
    bars = {A: make_bars(100.0), B: make_bars(50.0), C: make_bars(20.0)}
    reports = run(account, bars, polls(DAY2, "10:31", "10:31"), ranges={A: 0.03, B: 0.01})
    assert {e: o for e, _, o in outcomes(reports)} == {
        A: "ordered",
        B: "skipped: daily range 1.0% is under 4 round trips of 0.50%",
        C: "skipped: no daily range to weigh the costs against",
    }

    small = bot(config=config, input_money=10_000, max_positions=5)
    assert small.round_trip_cost() == pytest.approx(2 * (29 / 2000 + 0.001))  # 2 000 a position: the NOK 29 floor is 1.45 % each way


def test_no_more_than_the_cap_in_one_sector():
    bars = {A: make_bars(100.0), B: make_bars(50.0), C: make_bars(20.0)}
    sectors = {A: "Shipping", B: "Shipping", C: "Banks"}
    account = bot(buy=["10:00"], max_per_sector=1)
    logged = {e: o for e, _, o in outcomes(run(account, bars, polls(DAY2, "10:31", "10:31"), sectors=sectors))}
    assert logged == {A: "ordered", B: "skipped: 1 already in Shipping", C: "ordered"}


def test_daily_ranges_are_those_known_at_the_close_before():
    store_stocks(["AAA"])
    days = pd.bdate_range("2021-02-01", "2021-03-02")
    rows = pd.DataFrame({"timestamp": days, "high": 102.0, "low": 98.0, "close": 100.0})
    rows.loc[rows["timestamp"] == DAY2, ["high", "low"]] = (130.0, 70.0)  # the day itself is wild
    rows["entity_id"], rows["code"] = A, "AAA"
    rows["id"] = [f"{A}_{d:%Y-%m-%d}" for d in rows["timestamp"]]
    df_to_db(rows, Stock1dKdata, "yahoo")

    table = daily_range_table(None, since=days[0], until=DAY2)
    assert ranges_as_of(table, DAY2)[A] == pytest.approx(0.04)  # the 60 % range of the day itself is not known yet
    assert ranges_as_of(table, pd.Timestamp("2021-03-03"))[A] > 0.04
    assert ranges_as_of(table, days[0]) == {}


# -- a whole bot over stored bars -----------------------------------------------------------------


def test_a_day_trade_bot_replayed_over_stored_bars_never_holds_overnight():
    store_stocks(["AAA", "BBB"])
    rng = np.random.default_rng(11)
    days = pd.bdate_range("2021-03-01", periods=8)
    for entity_id, start in ((A, 100.0), (B, 50.0)):
        closes = start * np.cumprod(1 + rng.normal(0.0004, 0.004, len(days) * 30))
        index = session(days[0]).append([session(d) for d in days[1:]])
        frame = pd.DataFrame({"open": np.r_[closes[0], closes[:-1]], "close": closes, "volume": rng.uniform(500, 3000, len(closes))}, index=index)
        frame["high"], frame["low"] = frame[["open", "close"]].max(axis=1) * 1.002, frame[["open", "close"]].min(axis=1) * 0.998
        store_intraday(entity_id, frame)
    cfg = IntradayAccountConfig(name="bot", signal={"rule": "opening_range"}, watchlist=["AAA", "BBB"], day_trade=True, stop_loss=0.02, max_positions=2)
    result = replay(cfg, IntradayConfig(accounts=[cfg]), days=30, end=days[-1] + pd.Timedelta(hours=23))

    trades = result.orders[result.orders["order_type"].isin(["order_long", "order_close_long"])]
    assert len(trades) >= 2 and len(trades) % 2 == 0
    by_day = trades.groupby([trades["entity_id"], trades["timestamp"].dt.normalize()])["order_type"].apply(list)
    assert all(kinds == ["order_long", "order_close_long"] for kinds in by_day)  # each day: bought once, sold the same day
    assert result.daily_values.index.tolist() == list(days)


def test_the_replay_command_takes_the_day_trade_settings():
    store_stocks(["AAA", "BBB"])
    store_intraday(A, make_bars(100.0))
    store_intraday(B, make_bars(50.0))
    config_path().write_text("accounts: []\n", encoding="utf-8")
    trial = runner.invoke(app, ["intraday", "replay", "--no-record", "--days", "5000", "--rule", "opening_range", "--day-trade", "--watchlist", "AAA,BBB",
                                "--max-per-sector", "1", "--min-relative-volume", "1.5", "--min-range-cost", "4"])  # fmt: skip
    assert trial.exit_code == 0, trial.output
    assert "opening_range(minutes=30)" in trial.output and "day trade" in trial.output
