"""The evening job, played forward on a synthetic market with the clock under the test's control."""

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from osloquant.cli import app
from osloquant.contract.storage import df_to_db
from osloquant.domain import Stock1dAdjKdata, Stock1dKdata, StockAction
from osloquant.live import (
    AccountConfig,
    LiveConfig,
    account_summary,
    last_completed_session,
    live_account_names,
    load_config,
    run_live,
)
from osloquant.live.engine import config_path, load_state
from osloquant.samples import MaTrader
from osloquant.trader import AccountStats, Order
from tests.helpers import bars, business_days, random_walk, store_bars, store_benchmark, store_stocks

N = 60
CODES = ["AAA", "BBB", "CCC", "DDD", "EEE"]
DAYS = business_days(N)
runner = CliRunner(env={"COLUMNS": "200"})


def evening(i: int, hour: int = 18) -> pd.Timestamp:
    """The evening of trading day ``i``, Oslo time."""
    return (DAYS[i] + pd.Timedelta(hours=hour)).tz_localize("Europe/Oslo")


@pytest.fixture
def market():
    """Sixty days of five stocks, as quoted and adjusted (the same here: nobody pays a dividend), plus the index."""
    ids = store_stocks(CODES)
    for i, entity_id in enumerate(ids):
        frame = bars(entity_id, random_walk(N, seed=20 + i, vol=0.03))
        store_bars(frame, schema=Stock1dKdata)
        store_bars(frame, schema=Stock1dAdjKdata)
    store_benchmark(random_walk(N, seed=1, start=1000, vol=0.01))
    return ids


def config(*accounts: AccountConfig, commission_min: float = 0.0) -> LiveConfig:
    accounts = accounts or (AccountConfig("paper_ma", "ma", input_money=100_000, max_positions=3),)
    return LiveConfig(accounts=list(accounts), commission_rate=0.001, commission_min=commission_min, slippage=0.001)


# -- the session clock ----------------------------------------------------------------------------


def test_today_counts_only_once_its_bars_are_final(market):
    assert last_completed_session(evening(40, hour=16)) == DAYS[39]  # 16:00: the close has not been
    assert last_completed_session(evening(40, hour=18)) == DAYS[40]
    assert last_completed_session((DAYS[40] + pd.Timedelta(days=1, hours=8)).tz_localize("Europe/Oslo")) == DAYS[40]  # next morning


def test_the_clock_is_read_in_oslo_time_whatever_zone_it_is_given_in(market):
    # 16:30 in Lisbon is 17:30 in Oslo: the bars are final
    lisbon = (DAYS[40] + pd.Timedelta(hours=16, minutes=30)).tz_localize("Europe/Lisbon")
    assert last_completed_session(lisbon) == DAYS[40]


def test_a_day_on_which_only_a_stray_stock_has_a_bar_is_not_a_session(market):
    saturday = DAYS[-1] + pd.Timedelta(days=1)
    stray = bars("stock_ol_AAA", [100.0], start=f"{saturday:%Y-%m-%d}")
    store_bars(stray, schema=Stock1dKdata)
    assert last_completed_session((saturday + pd.Timedelta(hours=20)).tz_localize("Europe/Oslo")) == DAYS[-1]


def test_without_bars_there_is_no_session():
    assert last_completed_session(evening(10)) is None
    run = run_live(record=False, now=evening(10), config=config())
    assert run.session is None and run.results == []


# -- evenings -------------------------------------------------------------------------------------


def test_the_first_evening_decides_and_the_next_morning_fills(market):
    first = run_live(record=False, now=evening(30), config=config())
    assert [r.outcome for r in first.results] == ["started"] and first.session == DAYS[30]

    summary = account_summary("paper_ma")
    assert summary["value"] == 100_000 and summary["holdings"] == [] and summary["fills"] == 0
    assert summary["pending"] and {o["side"] for o in summary["pending"]} == {"buy"}
    assert all(o["decided_on"] == DAYS[30] for o in summary["pending"])
    decided = {o["entity_id"] for o in summary["pending"]}

    second = run_live(record=False, now=evening(31), config=config())
    assert [r.outcome for r in second.results] == ["stepped"]
    summary = account_summary("paper_ma")
    fills = summary["orders"]
    assert set(fills["entity_id"]) == decided
    assert (fills["timestamp"] == DAYS[31]).all() and (fills["signal_timestamp"] == DAYS[30]).all()
    # filled at the open of day 31 as quoted, plus slippage
    opens = Stock1dKdata.query_data(start_timestamp=DAYS[31], end_timestamp=DAYS[31]).set_index("entity_id")["open"]
    assert fills.set_index("entity_id")["order_price"].to_dict() == pytest.approx({e: opens[e] * 1.001 for e in decided})
    # written down the evening before, so every one of them is evidence
    assert (fills["forward"] == 1).all() and summary["forward_fills"] == summary["fills"] == len(decided)
    assert (fills["decided_at"] == evening(30).tz_convert("UTC").tz_localize(None)).all()


def test_running_the_same_evening_twice_changes_nothing(market):
    run_live(record=False, now=evening(30), config=config())
    run_live(record=False, now=evening(31), config=config())
    before = (AccountStats.query_data(), Order.query_data(), load_state("paper_ma"))

    again = run_live(record=False, now=evening(31, hour=23), config=config())

    assert [r.outcome for r in again.results] == ["up to date"]
    after = (AccountStats.query_data(), Order.query_data(), load_state("paper_ma"))
    pd.testing.assert_frame_equal(before[0], after[0])
    pd.testing.assert_frame_equal(before[1], after[1])
    assert before[2] == after[2]


def test_a_late_run_catches_up_but_its_fills_are_not_forward(market):
    run_live(record=False, now=evening(30), config=config())
    late = run_live(record=False, now=evening(34), config=config())  # three evenings were missed

    assert late.results[0].sessions == list(DAYS[31:35])
    orders = Order.query_data(order=Order.id.asc())
    on_day_31 = orders[orders["timestamp"] == DAYS[31]]
    # decided on the evening of day 30, before the open of day 31: still forward
    assert not on_day_31.empty and (on_day_31["forward"] == 1).all()
    # anything decided "on day 31, 32 or 33" was in fact written down on the evening of day 34
    later = orders[orders["signal_timestamp"] > DAYS[30]]
    assert (later["forward"] == 0).all()
    summary = account_summary("paper_ma")
    assert summary["forward_fills"] == len(on_day_31) and summary["sessions"] == 5


def test_stepping_evening_by_evening_gives_the_same_account_as_one_run_over_the_period(market):
    for i in range(30, N):
        run_live(record=False, now=evening(i), config=config())
    live = account_summary("paper_ma")

    actions = pd.DataFrame(columns=["entity_id", "timestamp", "dividend", "split"])
    one_run = MaTrader(start_timestamp=DAYS[30], end_timestamp=DAYS[-1], trader_name="one_run", adjust_type="raw", signal_adjust_type="adj",
                       corporate_actions=actions, input_money=100_000, max_positions=3, buy_cost=0.001, sell_cost=0.001, slippage=0.001).run()  # fmt: skip

    assert live["sessions"] == N - 30 and live["fills"] > 4
    assert live["value"] == pytest.approx(one_run.account.all_value)
    stored = AccountStats.query_data(filters=[AccountStats.trader_name == "paper_ma"])
    assert stored["all_value"].tolist() == pytest.approx(one_run.account.stats_df["all_value"].tolist())
    assert stored["universe_value"].tolist() == pytest.approx(one_run.account.stats_df["universe_value"].tolist())
    assert live["forward_fills"] == live["fills"]  # never late, so all of it is evidence


def test_bars_already_in_the_store_for_later_days_are_not_looked_at(market):
    run_live(record=False, now=evening(30), config=config())
    run_live(record=False, now=evening(31), config=config())
    decided = load_state("paper_ma")["pending"]

    # rewrite the future: the days after 31 now crash. Decisions made on day 31 must not have known.
    for entity_id in market:
        frame = bars(entity_id, np.full(N, 1.0))
        future = frame[frame["timestamp"] > DAYS[31]]
        store_bars(future, schema=Stock1dKdata)
        store_bars(future, schema=Stock1dAdjKdata)
    # a second account started on the same evening over the changed store decides the same
    twin = config(AccountConfig("twin", "ma", input_money=100_000, max_positions=3))
    run_live(record=False, now=evening(30), config=twin)
    run_live(record=False, now=evening(31), config=twin)
    assert [(s["entity_id"], s["type"]) for s in load_state("twin")["pending"]] == [(s["entity_id"], s["type"]) for s in decided]


def test_a_dividend_on_a_holding_arrives_as_cash(market):
    run_live(record=False, now=evening(30), config=config())
    run_live(record=False, now=evening(31), config=config())
    held = account_summary("paper_ma")["holdings"][0]
    payout = pd.DataFrame(
        [{"id": f"{held['entity_id']}_{DAYS[32]:%Y-%m-%d}", "entity_id": held["entity_id"], "timestamp": DAYS[32], "dividend": 2.5, "split": 0.0}]
    )
    df_to_db(payout, StockAction, "yahoo")

    run_live(record=False, now=evening(32), config=config())

    summary = account_summary("paper_ma")
    assert summary["dividends_received"] == pytest.approx(2.5 * held["shares"])
    dividend = summary["orders"][summary["orders"]["order_type"] == "dividend"].iloc[0]
    assert dividend["timestamp"] == DAYS[32] and dividend["order_amount"] == held["shares"]
    assert summary["fills"] == len(summary["orders"]) - 1  # a dividend is not a fill


def test_the_minimum_commission_is_charged(market):
    run_live(record=False, now=evening(30), config=config(commission_min=29))
    run_live(record=False, now=evening(31), config=config(commission_min=29))
    orders = account_summary("paper_ma")["orders"]
    # a third of 100 000 at 0.1 % would be 33: above the floor. The floor is there all the same.
    assert (orders["cost"] >= 29).all()
    small = config(AccountConfig("small", "ma", input_money=6_000, max_positions=3), commission_min=29)
    run_live(record=False, now=evening(30), config=small)
    run_live(record=False, now=evening(31), config=small)
    assert (account_summary("small")["orders"]["cost"] == 29).all()  # 2 000 at 0.1 % is 2: the floor binds


def test_accounts_are_independent_and_one_failing_does_not_stop_the_others(market):
    both = config(
        AccountConfig("broken", "no_such_strategy"),
        AccountConfig("paper_ma", "ma", input_money=100_000, max_positions=3),
        AccountConfig("paper_trend", "tests.test_live:ShortTrend", input_money=50_000, max_positions=2),
    )
    run = run_live(record=False, now=evening(30), config=both)

    assert [r.outcome for r in run.results] == ["failed", "started", "started"]
    assert "unknown strategy" in run.results[0].error
    assert live_account_names() == ["paper_ma", "paper_trend"]
    assert account_summary("paper_trend")["input_money"] == 50_000 and account_summary("paper_trend")["strategy"] == "tests.test_live:ShortTrend"


def test_an_account_added_later_starts_on_that_evening(market):
    run_live(record=False, now=evening(30), config=config())
    two = config(AccountConfig("paper_ma", "ma", input_money=100_000, max_positions=3), AccountConfig("late", "ma", input_money=100_000, max_positions=3))
    run = run_live(record=False, now=evening(35), config=two)

    assert {r.name: r.outcome for r in run.results} == {"paper_ma": "stepped", "late": "started"}
    assert account_summary("late")["start"] == DAYS[35] and account_summary("late")["sessions"] == 1
    assert account_summary("paper_ma")["start"] == DAYS[30]


class ShortTrend(MaTrader):
    """A strategy of the test's own, to show that live accounts take any trader by its import path."""

    windows = (3, 8)


# -- configuration and the command ----------------------------------------------------------------


def test_the_default_configuration_is_written_once_and_read_back():
    first = load_config()
    assert first.created and first.path == config_path() and first.path.exists()
    assert [a.name for a in first.accounts] == ["live_momentum", "live_trend"]
    assert (first.commission_rate, first.commission_min, first.slippage) == (0.0015, 29.0, 0.001)
    assert not load_config().created


def test_two_accounts_with_one_name_are_refused(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("accounts:\n  - {name: a, strategy: ma}\n  - {name: a, strategy: trend}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="share a name"):
        load_config(path)


def test_the_command_steps_reports_and_logs(market, home):
    config_path().write_text("costs: {commission_rate: 0.001, commission_min: 0, slippage: 0.001}\naccounts:\n  - {name: paper_ma, strategy: ma, max_positions: 3}\n", encoding="utf-8")

    result = runner.invoke(app, ["live", "--no-record"])
    assert result.exit_code == 0, result.output
    assert "paper_ma started" in result.output and "to be filled at the next open" in result.output

    again = runner.invoke(app, ["live", "--no-record"])
    assert again.exit_code == 0 and "nothing to do" in again.output

    status = runner.invoke(app, ["live", "--status"])
    assert status.exit_code == 0 and "paper_ma (ma)" in status.output and "nothing to do" not in status.output

    log = (home / "logs" / "live.log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 2 and "paper_ma=started" in log[0] and "paper_ma=up to date" in log[1]
    # a live account is not listed among the backtests
    assert "No backtest is stored yet" in runner.invoke(app, ["traders"]).output
