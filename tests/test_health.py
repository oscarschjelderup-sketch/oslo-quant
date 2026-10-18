"""The health checks: telling a job that did not run from a market that was quiet."""

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from osloquant import health
from osloquant.cli import app
from osloquant.domain import Stock1dAdjKdata, Stock1dKdata
from osloquant.health import (
    FAIL,
    OK,
    WARN,
    Check,
    check_daily_accounts,
    check_daily_data,
    check_intraday_accounts,
    expected_session,
    run_checks,
)
from osloquant.intraday import IntradayAccountConfig, IntradayConfig, poll, poll_times
from osloquant.intraday.engine import look_coverage
from osloquant.live import AccountConfig, LiveConfig, run_live
from tests.helpers import bars, business_days, random_walk, store_bars, store_benchmark, store_stocks
from tests.test_intraday import DAY1, DAY2, A, at, make_bars, polls, store_intraday

runner = CliRunner(env={"COLUMNS": "240"})
DELAY = pd.Timedelta(minutes=15)


# -- which day's prices should be there -----------------------------------------------------------


@pytest.mark.parametrize(
    "now, expected",
    [
        ("2026-10-05 16:30", "2026-10-02"),  # Monday before the bars are final: Friday
        ("2026-10-05 17:30", "2026-10-05"),  # Monday evening: Monday
        ("2026-10-06 08:00", "2026-10-05"),  # Tuesday morning: still Monday
        ("2026-10-04 12:00", "2026-10-02"),  # Sunday: Friday
    ],
)
def test_the_session_that_should_be_in_the_store(now, expected):
    assert expected_session(pd.Timestamp(now)) == pd.Timestamp(expected)


def daily_store(n: int = 40) -> pd.DatetimeIndex:
    store_stocks(["AAA", "BBB", "CCC"])
    for i, code in enumerate(["AAA", "BBB", "CCC"]):
        frame = bars(f"stock_ol_{code}", random_walk(n, seed=i, vol=0.03), start="2026-08-10")
        store_bars(frame, schema=Stock1dAdjKdata)
        store_bars(frame, schema=Stock1dKdata)
    store_benchmark(random_walk(n, seed=9, start=1000), start="2026-08-10")
    return business_days(n, start="2026-08-10")  # ends Friday 2 October 2026


def test_daily_prices_are_fresh_a_day_old_or_stale():
    assert check_daily_data(pd.Timestamp("2026-10-05 12:00")).status == FAIL  # nothing stored
    days = daily_store()
    assert days[-1] == pd.Timestamp("2026-10-02")

    assert (
        check_daily_data(pd.Timestamp("2026-10-05 12:00")).status == OK
    )  # Monday noon: Friday is the newest there can be
    late = check_daily_data(pd.Timestamp("2026-10-05 19:00"))
    assert late.status == WARN and "Mon 05 Oct is missing" in late.detail and "oq live" in late.hint
    assert check_daily_data(pd.Timestamp("2026-10-07 19:00")).status == FAIL


def test_a_daily_account_that_fell_behind_or_was_stepped_late_is_flagged():
    days = daily_store()
    config = LiveConfig(
        accounts=[AccountConfig("paper", "ma", max_positions=2)],
        commission_rate=0.001,
        commission_min=0,
        slippage=0.001,
    )
    evening = lambda day, hour=18: (day + pd.Timedelta(hours=hour)).tz_localize("Europe/Oslo")  # noqa: E731

    run_live(record=False, now=evening(days[-22]), config=config)
    run_live(record=False, now=evening(days[-21]), config=config)
    (check,) = check_daily_accounts(days[-21] + pd.Timedelta(hours=19))
    assert check.status == OK and "fills logged before the open" in check.detail

    # evenings pass without the job
    (check,) = check_daily_accounts(days[-10] + pd.Timedelta(hours=19))
    assert check.status == FAIL and "did not step" in check.hint

    run_live(record=False, now=evening(days[-1]), config=config)  # catches up twenty sessions at once
    (check,) = check_daily_accounts(days[-1] + pd.Timedelta(hours=19))
    assert check.status == WARN and "booked late" in check.hint and "at Fri 02 Oct" in check.detail


# -- how much of the day an intraday account watched ----------------------------------------------


def test_look_coverage_counts_the_looks_that_were_due_and_made():
    due = poll_times(DAY2, DELAY)
    start = at(DAY1, "09:00")

    everything = look_coverage(pd.DatetimeIndex(poll_times(DAY1, DELAY) + due), start, at(DAY2, "17:00"), DELAY)
    assert (everything["made"], everything["due"], everything["share"]) == (60, 60, 1.0) and everything[
        "days_missed"
    ] == []

    # day 1 not watched at all; on day 2 the computer slept from 11:00 to 13:00 and one look came late but in time
    awake = [t for t in due if not at(DAY2, "11:00") <= t < at(DAY2, "13:00")]
    awake[3] += pd.Timedelta(minutes=9)
    partial = look_coverage(pd.DatetimeIndex(awake), start, at(DAY2, "17:00"), DELAY)
    assert (partial["today_made"], partial["today_due"]) == (22, 30)
    assert (partial["made"], partial["due"]) == (22, 60) and partial["days_missed"] == [DAY1]

    # in the middle of the day only the looks due so far count
    midday = look_coverage(pd.DatetimeIndex(due[:10]), start, at(DAY2, "12:05"), DELAY)
    assert (midday["today_made"], midday["today_due"]) == (10, 11)

    # an account started in the afternoon is not blamed for the morning
    afternoon = look_coverage(pd.DatetimeIndex([]), at(DAY2, "14:00"), at(DAY2, "17:00"), DELAY)
    assert afternoon["today_due"] == 12 and afternoon["share"] == 0.0  # 14:01 to 16:46


def intraday_market() -> IntradayConfig:
    store_stocks(["AAA"])
    store_intraday(A, make_bars(100.0))
    return IntradayConfig(
        accounts=[IntradayAccountConfig(name="paper", signal={"rule": "ma_cross"}, watchlist=["AAA"])],
        commission_rate=0.0,
        commission_min=0.0,
        slippage=0.0,
    )


def test_an_intraday_account_that_missed_its_looks_is_flagged(monkeypatch):
    from osloquant.intraday import engine

    config = intraday_market()
    looks = polls(DAY2, "09:31", "16:46")
    for when in looks[:6]:
        poll(config, now=when, record=False)

    monkeypatch.setattr(engine, "market_now", lambda: at(DAY2, "11:05"))  # six of seven made
    (check,) = check_intraday_accounts(at(DAY2, "11:05"))
    assert check.status == OK and "6 of 7 looks made today" in check.detail

    monkeypatch.setattr(engine, "market_now", lambda: at(DAY2, "15:05"))  # then the computer slept
    (check,) = check_intraday_accounts(at(DAY2, "15:05"))
    assert check.status == WARN and "6 of 23 looks made today" in check.detail and "missed signal" in check.hint

    day3 = pd.Timestamp("2021-03-03")
    monkeypatch.setattr(engine, "market_now", lambda: at(day3, "12:05"))  # and the next day the task never ran
    (check,) = check_intraday_accounts(at(day3, "12:05"))
    assert check.status == FAIL and "0 of 11 looks made today" in check.detail and "schedule_intraday.ps1" in check.hint

    monkeypatch.setattr(engine, "market_now", lambda: pd.Timestamp("2021-03-06 12:00"))  # a Saturday owes no looks
    (check,) = check_intraday_accounts(pd.Timestamp("2021-03-06 12:00"))
    assert (
        check.status == OK and "no look due today" in check.detail and "3 whole days missed" in check.detail
    )  # Wednesday to Friday


def test_the_feed_lag_of_each_look_is_stored_and_a_slow_feed_is_flagged(monkeypatch):
    from osloquant.intraday import engine
    from osloquant.trader.schemas import IntradaySnapshot

    config = intraday_market()
    for when in polls(DAY2, "09:31", "10:31"):
        poll(config, now=when, record=False)
    lags = IntradaySnapshot.query_data()["feed_lag"].tolist()
    # the store here holds every bar already, so the "feed" is not late at all: the newest bar starts a minute before each look
    assert lags == [pytest.approx(1.0)] * 5

    # the same looks against a feed that has stopped an hour earlier
    stale = IntradayConfig(
        accounts=[IntradayAccountConfig(name="slow", signal={"rule": "ma_cross"}, watchlist=["AAA"])],
        commission_rate=0.0,
        commission_min=0.0,
        slippage=0.0,
    )
    bars_until = make_bars(100.0)
    monkeypatch.setattr(
        engine, "load_bars", lambda ids, since, until=None: {A: bars_until[bars_until.index <= at(DAY2, "09:30")]}
    )
    for when in polls(DAY2, "09:31", "10:31"):
        poll(stale, now=when, record=False)
    monkeypatch.setattr(engine, "market_now", lambda: at(DAY2, "10:35"))
    slow = next(c for c in check_intraday_accounts(at(DAY2, "10:35")) if c.name == "slow")
    assert slow.status == WARN and "61 minutes old" in slow.detail and "feed_delay_minutes" in slow.hint


# -- everything together --------------------------------------------------------------------------


def test_a_check_that_cannot_be_made_does_not_stop_the_others(monkeypatch):
    daily_store()
    monkeypatch.setattr(health, "check_daily_accounts", lambda now: 1 / 0)
    checks = run_checks(now=pd.Timestamp("2026-10-05 12:00"), tasks=False)
    assert [c.status for c in checks] == [OK, WARN] and "ZeroDivisionError" in checks[1].detail


def test_scheduled_tasks_are_read_from_windows(monkeypatch):
    listing = '[{"name":"oslo-quant live","state":"Ready","result":0,"last":"2026-10-05T17:37:11","next":"2026-10-05T21:30:00"},' \
              '{"name":"oslo-quant intraday","state":"Ready","result":2147946720,"last":"2026-10-05T19:08:16","next":"2026-10-06T07:46:00"}]'  # fmt: skip
    monkeypatch.setattr(health.sys, "platform", "win32")
    monkeypatch.setattr(health.subprocess, "run", lambda *a, **k: type("Done", (), {"stdout": listing})())
    live, intraday = health.check_tasks()
    assert live.status == OK and "last run Mon 05 Oct 17:37, next Mon 21:30" in live.detail
    assert intraday.status == WARN and "0x800710E0" in intraday.detail

    monkeypatch.setattr(health.subprocess, "run", lambda *a, **k: type("Done", (), {"stdout": ""})())
    assert [c.status for c in health.check_tasks()] == [FAIL, FAIL] and "schedule_live.ps1" in health.check_tasks()[
        0
    ].hint

    monkeypatch.setattr(health.sys, "platform", "linux")
    assert health.check_tasks() == []


def test_the_doctor_command(monkeypatch):
    monkeypatch.setattr(health, "run_checks", lambda: [Check("Daily prices", OK, "newest bar Fri 02 Oct")])
    fine = runner.invoke(app, ["doctor"])
    assert fine.exit_code == 0 and "Everything is running." in fine.output

    monkeypatch.setattr(
        health,
        "run_checks",
        lambda: [Check("paper", FAIL, "0 of 11 looks made today", "register the task"), Check("x", WARN, "y")],
    )
    broken = runner.invoke(app, ["doctor"])
    assert (
        broken.exit_code == 1
        and "FAILED" in broken.output
        and "register the task" in broken.output
        and "Everything is running" not in broken.output
    )


def test_the_values_are_not_touched_by_looking(monkeypatch):
    # checks only read: an account's stored numbers are the same before and after
    from osloquant.trader import AccountStats

    config = intraday_market()
    poll(config, now=at(DAY2, "09:31"), record=False)
    before = AccountStats.query_data()
    run_checks(now=at(DAY2, "09:40"), tasks=False)
    pd.testing.assert_frame_equal(before, AccountStats.query_data())
    assert np.isfinite(before["all_value"]).all()


def test_the_goats_page_check_compares_the_branch_with_the_newest_look():
    from osloquant.health import goats_publish_status

    look = pd.Timestamp("2026-10-15 10:46")
    assert goats_publish_status(pd.Timestamp("2026-10-15 10:47"), look).status == "ok"
    assert goats_publish_status(pd.Timestamp("2026-10-15 10:20"), look).status == "ok", "half an hour of slack"
    late = goats_publish_status(pd.Timestamp("2026-10-15 07:20"), look)
    assert late.status == "warn" and "3 h behind" in late.detail and "oq goats --publish" in late.hint
    assert goats_publish_status(None, look).status == "warn" and goats_publish_status(None, None).status == "ok"
