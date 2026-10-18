"""Margin accounts: shorts, entries sized by the signal's strength, financing, and the margin call."""

import json

import numpy as np
import pandas as pd
import pytest

from osloquant.intraday import (
    BUY,
    SELL,
    IntradayAccount,
    IntradayAccountConfig,
    IntradayConfig,
    Rule,
    account_summary,
    poll,
    replay,
)
from osloquant.intraday.engine import _upgrade_order
from osloquant.intraday.rules import Breakout, clip01
from osloquant.trader.schemas import IntradaySnapshot, Order
from osloquant.trader.sim_account import SimAccount
from tests.helpers import store_stocks
from tests.test_intraday import DAY1, DAY2, A, B, C, at, frame, make_bars, polls, run, store_intraday

COSTLESS = IntradayConfig(accounts=[], commission_rate=0.0, commission_min=0.0, slippage=0.0)


class StrengthRule(Rule):
    """Fires on flagged bars like the intraday tests' rule, and says how emphatic: 112 and 998 are strong."""

    code = "strength"

    def evaluate(self, bars):
        volume = bars["volume"].iloc[-1]
        if volume in (111, 112):
            return self.signal(BUY, "flagged", bars, strength=1.0 if volume == 112 else 0.0)
        if volume in (999, 998):
            return self.signal(SELL, "flagged", bars, strength=1.0 if volume == 998 else 0.0)
        return None


def margin(**account) -> IntradayAccount:
    defaults = {
        "name": "margin",
        "signal": {"rule": "tests.test_margin:StrengthRule"},
        "watchlist": [A, B, C],
        "input_money": 10_000,
        "max_positions": 2,
        "shorts": True,
        "max_leverage": 10,
    }
    return IntradayAccount(IntradayAccountConfig(**{**defaults, **account}), COSTLESS)


def rows(reports) -> list[tuple[str, str]]:
    return [(s["code"], s["outcome"]) for r in reports for s in r.signals]


# -- the account ----------------------------------------------------------------------------------


def test_a_short_round_trip_books_proceeds_a_liability_and_the_profit():
    acc = SimAccount("t", 10_000, buy_cost=0, sell_cost=0, slippage=0, max_leverage=2)
    assert acc.sell_short(A, 100.0, DAY1, money=5_000) == 50
    assert (
        acc.cash == 15_000
        and acc.holdings[A].amount == -50
        and acc.holdings[A].side == "short"
        and acc.holdings[A].shares == 50
    )
    acc.mark({A: 90.0})
    assert (
        acc.all_value == pytest.approx(10_500)
        and acc.holdings[A].profit_rate == pytest.approx(0.1)
        and acc.holdings[A].value == -4_500
    )
    assert acc.exposure == 4_500 and acc.short_exposure == 4_500 and acc.leverage == pytest.approx(4_500 / 10_500)
    assert acc.buy_to_cover(A, 90.0, DAY2) == 50
    assert acc.cash == pytest.approx(10_500) and not acc.holdings
    order = acc.orders_df.iloc[-1]
    assert (
        order["order_type"] == "order_close_short"
        and order["profit"] == pytest.approx(500)
        and order["profit_rate"] == pytest.approx(0.1)
    )
    assert acc.orders_df["order_type"].tolist() == ["order_short", "order_close_short"]


def test_a_cash_account_neither_shorts_nor_borrows():
    acc = SimAccount("t", 10_000, buy_cost=0, sell_cost=0, slippage=0)
    assert not acc.margin and acc.sell_short(A, 100.0, DAY1, money=5_000) == 0
    assert acc.buy(A, 100.0, DAY1, money=25_000) == 100 and acc.cash == 0 and acc.buying_power == 0
    with pytest.raises(ValueError):
        SimAccount("t", 1_000, max_leverage=0.5)


def test_a_margin_account_borrows_up_to_its_buying_power_and_pays_for_it():
    acc = SimAccount(
        "t", 10_000, buy_cost=0, sell_cost=0, slippage=0, max_leverage=3, financing_rate=0.06, borrow_rate=0.03
    )
    assert acc.buying_power == 30_000
    assert acc.buy(A, 100.0, DAY1, money=25_000) == 250
    acc.mark({A: 100.0})
    assert (
        acc.cash == -15_000
        and acc.exposure == 25_000
        and acc.leverage == pytest.approx(2.5)
        and acc.buying_power == pytest.approx(5_000)
    )
    assert acc.sell_short(B, 50.0, DAY1, money=20_000) == 100, "capped at the 5 000 of buying power left"
    acc.mark({A: 100.0, B: 50.0})
    assert acc.exposure == 30_000 and acc.buying_power == 0 and acc.cash == -10_000
    # a year of interest on the 10 000 borrowed and the borrow fee on the 5 000 short
    charge = acc.charge_financing(365, DAY2)
    assert charge == pytest.approx(600 + 150) and acc.cash == pytest.approx(-10_750)
    assert acc.orders_df.iloc[-1]["order_type"] == "financing" and acc.orders_df.iloc[-1]["cost"] == pytest.approx(750)
    assert acc.charge_financing(0, DAY2) == 0


def test_a_short_pays_the_dividend_and_close_takes_either_side():
    acc = SimAccount("t", 10_000, buy_cost=0, sell_cost=0, slippage=0, max_leverage=2)
    acc.sell_short(A, 100.0, DAY1, money=5_000)
    assert acc.receive_dividend(A, 2.0, DAY2) == -100 and acc.cash == pytest.approx(14_900)
    acc.buy(B, 10.0, DAY1, money=1_000)
    assert (
        acc.close(A, 100.0, DAY2) == 50
        and acc.close(B, 10.0, DAY2) == 100
        and acc.close(C, 1.0, DAY2) == 0
        and not acc.holdings
    )
    with pytest.raises(ValueError):
        acc.sell_short(A, 100.0, DAY1, money=1_000)
        acc.buy(A, 100.0, DAY1, money=1_000)


# -- the engine -----------------------------------------------------------------------------------


def test_a_bearish_signal_opens_a_short_only_when_the_account_may():
    bars = {A: make_bars(100.0, flags={at(DAY2, "09:45"): 999})}
    plain = IntradayAccount(
        IntradayAccountConfig(
            name="plain",
            signal={"rule": "tests.test_margin:StrengthRule"},
            watchlist=[A],
            input_money=10_000,
            max_positions=2,
        ),
        COSTLESS,
    )
    reports = run(plain, bars, polls(DAY2, "09:31", "10:31"))
    assert rows(reports) == [] and not plain.account.holdings, (
        "a sell signal in something not held is not news to a long-only account"
    )

    short = margin()
    reports = run(short, bars, polls(DAY2, "09:31", "10:31"))
    assert rows(reports) == [(SELL, "ordered: short x1.0")]
    assert short.account.holdings[A].amount == -50 and short.account.cash == 15_000, "one slot of 5 000 at 100"
    assert reports[-1].fills[0]["action"] == "open_short" and reports[-1].fills[0]["side"] == SELL
    assert short.account.orders_df["order_type"].tolist() == ["order_short"]


def test_a_strong_signal_gets_more_slots_and_a_faint_one_gets_one():
    bars = {A: make_bars(100.0, flags={at(DAY2, "09:45"): 112}), B: make_bars(100.0, flags={at(DAY2, "09:45"): 111})}
    account = margin()
    reports = run(account, bars, polls(DAY2, "09:31", "10:31"))
    # strength 1 blended with a quiet bar is 0.6: 1 + 9 x 0.6 slots of 5 000
    assert {s["entity_id"]: s["outcome"] for r in reports for s in r.signals} == {A: "ordered x6.4", B: "ordered x1.0"}
    assert account.account.holdings[A].amount == 320 and account.account.holdings[B].amount == 50
    assert account.account.leverage == pytest.approx(3.7) and account.account.cash == pytest.approx(-27_000)


def test_an_entry_never_takes_more_than_the_buying_power_left():
    account = margin(max_leverage=2)  # 20 000 of buying power, 5 000 a slot
    order = {"action": "open_long", "strength": 1.0}
    assert account.size(order, None) == (pytest.approx(10_000), pytest.approx(2.0)), (
        "no volume to blend with: the rule's word stands"
    )
    assert account.size(order, 0.1) == (pytest.approx(8_000), pytest.approx(1.6)), (
        "a quiet bar takes the strength down to 0.6"
    )
    account.pending.append({"action": "open_long", "notional": 18_000, "entity_id": B})
    assert account.size(order, 0.1) == (pytest.approx(2_000), pytest.approx(0.4))
    account.pending.append({"action": "open_short", "notional": 1_500, "entity_id": C})
    assert account.size(order, 0.1) == (pytest.approx(500), pytest.approx(0.1))
    assert account.size(order, 5.0)[0] == pytest.approx(500), "a busy bar raises the strength, not the cap"
    cash = IntradayAccount(
        IntradayAccountConfig(
            name="cash", signal={"rule": "tests.test_margin:StrengthRule"}, input_money=10_000, max_positions=2
        ),
        COSTLESS,
    )
    assert cash.size(order, 5.0) == (5_000, 1.0)


@pytest.mark.parametrize(
    "risk, path, code, reason",
    [
        ({"stop_loss": 0.02}, [103.0] * 22, "STOP", "103.00 is +3.0% from the short at 100.00"),
        ({"take_profit": 0.05}, [94.0] * 22, "TARGET", "94.00 is -6.0% from the short at 100.00"),
        (
            {"trailing_stop": 0.04},
            [90.0] * 5 + [94.0] * 17,
            "TRAIL",
            "94.00 is +4.4% from the low of 90.00 since the short",
        ),
    ],
)
def test_short_stops_mirror_the_long_ones(risk, path, code, reason):
    closes = np.full(60, 100.0)
    closes[30 + 8 :] = path
    account = margin(**risk)
    reports = run(account, {A: make_bars(closes, flags={at(DAY2, "09:45"): 999})}, polls(DAY2, "09:31", "16:46"))
    assert rows(reports) == [(SELL, "ordered: short x1.0"), (code, "ordered")]
    assert [s["reason"] for r in reports for s in r.signals][-1] == reason
    assert not account.account.holdings and account.account.orders_df["order_type"].tolist() == [
        "order_short",
        "order_close_short",
    ]
    exit_price = path[-1] if code != "TRAIL" else 94.0
    assert account.account.orders_df.iloc[-1]["profit"] == pytest.approx(50 * (100 - exit_price))


def test_a_margin_call_closes_everything():
    closes = np.full(60, 100.0)
    closes[30 + 8 :] = 70.0
    account = margin()  # no stop: the loss runs until the margin is gone
    reports = run(account, {A: make_bars(closes, flags={at(DAY2, "09:45"): 112})}, polls(DAY2, "09:31", "16:46"))
    assert rows(reports) == [(BUY, "ordered x6.4"), ("MARGIN", "ordered")]
    assert [s["reason"] for r in reports for s in r.signals][-1] == "equity 400 is under 5% of the exposure 22,400"
    assert not account.account.holdings and account.account.all_value == pytest.approx(400)


def test_financing_is_charged_on_the_first_look_of_a_new_day():
    bars = {A: make_bars(100.0, flags={at(DAY1, "09:45"): 112})}
    account = margin()
    reports = run(account, bars, polls(DAY1, "09:31", "16:46"))
    # the first day has no volume history to blend with, so a strong signal takes all ten slots: 50 000 at 100
    assert account.account.cash == pytest.approx(-40_000) and all(r.financing == 0 for r in reports)
    (report,) = run(account, bars, [at(DAY2, "09:31")])
    assert report.financing == pytest.approx(40_000 * 0.06 / 365)
    assert account.account.orders_df.iloc[-1]["order_type"] == "financing"
    assert account.account.cash == pytest.approx(-40_000 - report.financing)
    assert run(account, bars, [at(DAY2, "09:46")])[0].financing == 0, "once a day"


def test_a_short_survives_a_round_trip_through_the_saved_state():
    bars = {A: make_bars(100.0, flags={at(DAY2, "09:45"): 998})}
    account = margin()
    run(account, bars, polls(DAY2, "09:31", "10:16"))
    state = json.loads(json.dumps(account.to_state()))
    assert state["pending"][0]["action"] == "open_short" and state["pending"][0]["notional"] == pytest.approx(32_000)
    rebuilt = IntradayAccount(account.cfg, COSTLESS, state)
    run(rebuilt, bars, [at(DAY2, "10:31")])
    assert rebuilt.account.holdings[A].amount == -320 and rebuilt.to_state()["account"]["holdings"][0]["amount"] == -320
    assert (
        _upgrade_order({"side": BUY})["action"] == "open_long"
        and _upgrade_order({"side": SELL})["action"] == "close_long"
    )
    assert _upgrade_order({"side": SELL, "action": "open_short"})["action"] == "open_short"


def test_the_margin_settings_are_checked():
    with pytest.raises(ValueError):
        IntradayAccountConfig(name="x", signal={}, max_leverage=11)
    with pytest.raises(ValueError):
        IntradayAccountConfig(name="x", signal={}, shorts=True)
    with pytest.raises(ValueError):
        IntradayAccountConfig(name="x", signal={}, max_leverage=2, maintenance_margin=1.5)


def test_rules_say_how_emphatic_a_bar_was():
    strong = Breakout(20).evaluate(frame([100] * 21 + [112], highs=[101] * 21 + [112], lows=[99] * 21 + [112]))
    assert strong.code == BUY and strong.strength == 1.0, (
        "a close half a range-width past the high is as emphatic as it gets"
    )
    faint = Breakout(20).evaluate(frame([100] * 21 + [101.1], highs=[101] * 21 + [101.1], lows=[99] * 21 + [101.1]))
    assert faint.code == BUY and faint.strength == pytest.approx(0.1)
    down = Breakout(20).evaluate(frame([100] * 21 + [98.5], highs=[101] * 21 + [98.5], lows=[99] * 21 + [98.5]))
    assert down.code == SELL and down.strength == pytest.approx(0.5)
    assert clip01(float("nan")) == 0 and clip01(3) == 1 and clip01(-1) == 0


# -- through the store ----------------------------------------------------------------------------


@pytest.fixture
def market():
    store_stocks(["AAA", "BBB"])
    store_intraday(A, make_bars(100.0, flags={at(DAY2, "09:45"): 998}))
    store_intraday(B, make_bars(50.0, flags={at(DAY2, "10:00"): 112}))
    return IntradayConfig(
        accounts=[IntradayAccountConfig(name="margin", signal={"rule": "tests.test_margin:StrengthRule"}, watchlist=["AAA", "BBB"], input_money=100_000, max_positions=2, shorts=True, max_leverage=5)],
        commission_rate=0.0015, commission_min=29.0, slippage=0.001,
    )  # fmt: skip


def test_a_polled_margin_account_stores_sides_exposure_and_leverage(market):
    for when in polls(DAY2, "09:31", "11:01"):
        assert poll(market, now=when, record=False).errors == {}
    assert Order.query_data(order=Order.id.asc())["order_type"].tolist() == ["order_short", "order_long"]
    summary = account_summary("margin")
    assert {h["code"]: h["side"] for h in summary["holdings"]} == {"AAA": "short", "BBB": "long"}
    assert all(h["shares"] > 0 for h in summary["holdings"]) and summary["exposure"] > 0 and summary["leverage"] > 1
    snaps = IntradaySnapshot.query_data(order=IntradaySnapshot.timestamp.asc())
    assert snaps["exposure"].iloc[-1] == pytest.approx(summary["exposure"]) and snaps["leverage"].iloc[-1] > 1
    result = replay(market.accounts[0], market, days=3, end=at(DAY2, "16:46"))
    assert result.orders["order_type"].tolist()[:2] == ["order_short", "order_long"]
    # held overnight: the first look of the next day charges financing, and the summary must still read
    assert poll(market, now=at(DAY2 + pd.Timedelta(days=1), "09:31"), record=False).errors == {}
    summary = account_summary("margin")
    assert summary["financing_paid"] > 0 and "financing" in Order.query_data()["order_type"].tolist()
    assert summary["orders"]["stock"].tolist()[-1] == "financing"
