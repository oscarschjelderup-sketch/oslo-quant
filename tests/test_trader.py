import numpy as np
import pandas as pd
import pytest

from osloquant.contract.factor import Factor
from osloquant.factors import CrossMaFactor
from osloquant.trader import AccountStats, Order, Position, SimAccount, StockTrader, TraderInfo, get_trader_stats
from osloquant.trader.stats import get_trader_names, performance
from tests.helpers import bars, business_days, store_bars, store_benchmark, store_stocks

A, B, C = "stock_ol_AAA", "stock_ol_BBB", "stock_ol_CCC"
T = pd.Timestamp("2020-01-01")


def day(i: int) -> pd.Timestamp:
    return business_days(i + 1)[-1]


# -- the account ----------------------------------------------------------------------------------


def test_buy_pays_slippage_and_commission_and_only_whole_shares():
    account = SimAccount("t", input_money=10_000, buy_cost=0.001, sell_cost=0.001, slippage=0.01)
    bought = account.buy(A, price=100.0, timestamp=T, money=5_000)

    fill = 101.0
    assert bought == 49  # 5000 / (101 * 1.001) = 49.45
    assert account.cash == pytest.approx(10_000 - 49 * fill * 1.001)
    assert account.holdings[A].average_price == pytest.approx(fill)
    order = account.orders_df.iloc[0]
    assert (order["order_type"], order["order_price"], order["order_amount"]) == ("order_long", fill, 49)
    assert order["cost"] == pytest.approx(49 * fill * 0.001)


def test_buy_never_spends_more_than_the_cash_at_hand():
    account = SimAccount("t", input_money=1_000, buy_cost=0.0, sell_cost=0.0, slippage=0.0)
    assert account.buy(A, 100.0, T, money=50_000) == 10
    assert account.cash == 0
    assert account.buy(B, 100.0, T, money=50_000) == 0
    assert B not in account.holdings and len(account.orders_df) == 1


def test_sell_books_the_round_trip_after_all_costs():
    account = SimAccount("t", input_money=10_000, buy_cost=0.001, sell_cost=0.001, slippage=0.01)
    account.buy(A, 100.0, T, money=5_000)
    paid = 49 * 101.0 * 1.001
    sold = account.sell(A, price=120.0, timestamp=T + pd.Timedelta(days=1))

    proceeds = 49 * 118.8 * 0.999
    assert sold == 49 and A not in account.holdings
    assert account.cash == pytest.approx(10_000 - paid + proceeds)
    order = account.orders_df.iloc[1]
    assert order["profit"] == pytest.approx(proceeds - paid)
    assert order["profit_rate"] == pytest.approx(proceeds / paid - 1)


def test_two_buys_average_the_price_and_a_partial_sell_keeps_the_rest():
    account = SimAccount("t", input_money=100_000, buy_cost=0.0, sell_cost=0.0, slippage=0.0)
    account.buy(A, 100.0, T, money=1_000)
    account.buy(A, 200.0, T, money=2_000)
    assert account.holdings[A].amount == 20 and account.holdings[A].average_price == pytest.approx(150.0)

    account.sell(A, 150.0, T, pct=0.5)
    assert account.holdings[A].amount == 10 and account.holdings[A].cost == pytest.approx(1_500)
    assert account.sell(B, 150.0, T) == 0  # nothing held, nothing sold


def test_closing_marks_to_market_and_keeps_the_last_price_when_one_is_missing():
    account = SimAccount("t", input_money=10_000, buy_cost=0.0, sell_cost=0.0, slippage=0.0)
    account.buy(A, 100.0, T, money=5_000)
    account.on_trading_close(T, {A: 110.0})
    assert account.all_value == pytest.approx(5_000 + 50 * 110)
    assert account.holdings[A].profit_rate == pytest.approx(0.10)

    account.on_trading_close(T + pd.Timedelta(days=1), {A: float("nan")})
    assert account.all_value == pytest.approx(5_000 + 50 * 110)
    assert account.stats_df["holdings"].tolist() == [1.0, 1.0]


# -- the trader -----------------------------------------------------------------------------------


class Scripted(Factor):
    """A factor that says exactly what the test tells it to: {day index: (positive, negative)}."""

    def __init__(self, script: dict, entities: list[str], n: int) -> None:
        index = pd.MultiIndex.from_product([entities, business_days(n)], names=["entity_id", "timestamp"])
        verdict = pd.Series(pd.NA, index=index, dtype="boolean")
        for i, (positive, negative) in script.items():
            for entity in positive:
                verdict[(entity, day(i))] = True
            for entity in negative:
                verdict[(entity, day(i))] = False
        super().__init__(data_df=verdict.to_frame("filter_result"), compute=False)
        self.result_df = self.data_df


def scripted_trader_unrun(script: dict, closes: dict[str, list[float]], opens: dict[str, list[float]] | None = None, **kwargs):
    n = len(next(iter(closes.values())))
    kdata = pd.concat([bars(e, c, opens=(opens or {}).get(e)) for e, c in closes.items()], ignore_index=True)
    factor = Scripted(script, list(closes), n)

    class ScriptedTrader(StockTrader):
        def init_factors(self, **_):
            return [factor]

    defaults = {"start_timestamp": day(0), "end_timestamp": day(n - 1), "kdata": kdata, "buy_cost": 0.0, "sell_cost": 0.0,
                "slippage": 0.0, "input_money": 10_000, "max_positions": 2, "profit_threshold": None, "benchmark": None}  # fmt: skip
    return ScriptedTrader(**{**defaults, **kwargs})


def scripted_trader(script: dict, closes: dict[str, list[float]], opens: dict[str, list[float]] | None = None, **kwargs):
    return scripted_trader_unrun(script, closes, opens, **kwargs).run()


def test_a_decision_on_the_close_is_filled_at_the_next_open():
    closes = {A: [100, 100, 100, 100, 100]}
    opens = {A: [100, 100, 90, 100, 120]}
    trader = scripted_trader({1: ([A], []), 3: ([], [A])}, closes, opens)
    orders = trader.account.orders_df

    buy, sell = orders.iloc[0], orders.iloc[1]
    assert (buy["signal_timestamp"], buy["timestamp"], buy["order_price"]) == (day(1), day(2), 90)
    assert (sell["signal_timestamp"], sell["timestamp"], sell["order_price"]) == (day(3), day(4), 120)
    assert buy["order_amount"] == 55  # half of 10 000 in a two-slot account, at 90
    assert trader.account.cash == pytest.approx(10_000 + 55 * (120 - 90))


def test_signal_close_execution_fills_on_the_bar_that_made_the_decision():
    closes = {A: [100, 105, 100, 100, 100]}
    trader = scripted_trader({1: ([A], [])}, closes, execution="signal_close")
    buy = trader.account.orders_df.iloc[0]
    assert (buy["timestamp"], buy["order_price"]) == (day(1), 105)


def test_nothing_is_filled_before_the_first_decision_or_after_the_last_bar():
    trader = scripted_trader({4: ([A], [])}, {A: [100, 100, 100, 100, 100]})
    assert trader.account.orders_df.empty  # decided on the last close: there is no next open
    assert trader.account.stats_df["all_value"].tolist() == [10_000] * 5


def test_holdings_never_exceed_the_slots_and_candidates_fill_them_in_id_order():
    closes = {e: [100.0] * 6 for e in (A, B, C)}
    trader = scripted_trader({0: ([C, B, A], []), 2: ([C], []), 3: ([], [A]), 4: ([C], [])}, closes)
    orders = trader.account.orders_df

    assert orders["entity_id"].tolist() == [A, B, A, C]
    assert orders["order_type"].tolist() == ["order_long", "order_long", "order_close_long", "order_long"]
    # C had to wait for A to be sold; it was not bought on day 3 while both slots were taken
    assert orders.iloc[3]["timestamp"] == day(5)
    assert trader.account.stats_df["holdings"].max() == 2


def test_a_sell_and_a_buy_decided_together_use_the_freed_cash():
    closes = {A: [100.0] * 5, B: [100.0] * 5, C: [100.0] * 5}
    trader = scripted_trader({0: ([A, B], []), 2: ([C], [A])}, closes)
    filled = trader.account.orders_df[trader.account.orders_df["timestamp"] == day(3)]
    assert filled["entity_id"].tolist() == [A, C] and filled["order_type"].tolist() == ["order_close_long", "order_long"]


def test_a_holding_is_not_bought_twice():
    trader = scripted_trader({0: ([A], []), 1: ([A], []), 2: ([A], [])}, {A: [100.0] * 5})
    assert len(trader.account.orders_df) == 1


def test_stop_loss_and_take_profit_close_the_holding():
    closes = {A: [100, 100, 100, 65, 65, 65], B: [100, 100, 100, 100, 160, 160]}
    trader = scripted_trader({0: ([A, B], [])}, closes, profit_threshold=(0.5, -0.3))
    sells = trader.account.orders_df[trader.account.orders_df["order_type"] == "order_close_long"]

    # A closed at 65 on day 3 (-35 %): sold at the next open. B closed at 160 on day 4 (+60 %).
    assert sells["entity_id"].tolist() == [A, B]
    assert sells["signal_timestamp"].tolist() == [day(3), day(4)]
    assert sells["timestamp"].tolist() == [day(4), day(5)]


def test_monthly_rebalancing_acts_on_the_first_trading_day_of_a_month_and_on_the_very_first_day():
    n = 45  # January and February 2020
    liked_from_day_3 = {i: ([A], []) for i in range(3, n)}
    trader = scripted_trader(liked_from_day_3, {A: [100.0] * n}, rebalance="monthly")
    buy = trader.account.orders_df.iloc[0]

    # liked since 6 January, but a monthly trader only looks again on the first trading day of February
    assert buy["signal_timestamp"] == pd.Timestamp("2020-02-03")
    assert buy["timestamp"] == pd.Timestamp("2020-02-04")

    # the first day of a run is always acted on, so that an account does not sit in cash until the month turns
    liked_from_the_start = {i: ([A], []) for i in range(n)}
    trader = scripted_trader(liked_from_the_start, {A: [100.0] * n}, rebalance="monthly")
    assert trader.account.orders_df.iloc[0]["signal_timestamp"] == day(0)


def test_weekly_rebalancing_acts_on_the_first_trading_day_of_a_week():
    liked_from_day_1 = {i: ([A], []) for i in range(1, 10)}
    trader = scripted_trader(liked_from_day_1, {A: [100.0] * 10}, rebalance="weekly")
    # 1 January 2020 is a Wednesday; the next week starts on Monday the 6th
    assert trader.account.orders_df.iloc[0]["signal_timestamp"] == pd.Timestamp("2020-01-06")


def test_the_rebalance_day_is_decided_without_looking_at_the_calendar_ahead():
    # the same day gets the same answer whether or not later days exist yet
    n = 45
    closes = {A: [100.0] * n}
    whole = scripted_trader({}, closes, rebalance="monthly")
    for cut in (20, 23, 24, 30):
        part = scripted_trader({}, {A: [100.0] * cut}, rebalance="monthly")
        assert part.is_rebalance_date(day(cut - 1)) == whole.is_rebalance_date(day(cut - 1))
    assert [d for d in whole.trading_dates if whole.is_rebalance_date(d)] == [day(0), pd.Timestamp("2020-02-03"), pd.Timestamp("2020-03-02")]


def test_an_order_waits_for_a_bar_and_is_dropped_when_none_comes():
    closes = {A: [100.0] * 10, B: [100.0] * 10}
    kdata = pd.concat([bars(A, closes[A]), bars(B, closes[B])], ignore_index=True)
    b_missing = (kdata["entity_id"] == B) & kdata["timestamp"].isin([day(2), day(3)])
    a_missing = (kdata["entity_id"] == A) & (kdata["timestamp"] > day(1))

    waits = scripted_trader({1: ([B], [])}, closes, kdata=kdata[~b_missing])
    assert waits.account.orders_df.iloc[0]["timestamp"] == day(4)

    never = scripted_trader({1: ([A], [])}, closes, kdata=kdata[~a_missing])
    assert never.account.orders_df.empty and never.trading_signals == []


def test_solo_mode_trades_from_on_time():
    class BuyTheDip(StockTrader):
        def on_time(self, timestamp):
            close = self.close_df.loc[:timestamp, A]
            if len(close) > 1 and close.iloc[-1] < 0.95 * close.iloc[-2]:
                self.trade_the_targets(happen_timestamp=timestamp, long_selected=[A])
            elif A in self.account.holdings and close.iloc[-1] > 1.05 * close.iloc[-2]:
                self.trade_the_targets(happen_timestamp=timestamp, short_selected=[A])

    closes = [100, 90, 90, 100, 100, 100]
    trader = BuyTheDip(start_timestamp=day(0), end_timestamp=day(5), kdata=bars(A, closes), benchmark=None, max_positions=1,
                       buy_cost=0, sell_cost=0, slippage=0, input_money=9_000).run()  # fmt: skip
    orders = trader.account.orders_df

    assert orders["timestamp"].tolist() == [day(2), day(4)]
    assert orders["order_price"].tolist() == [90, 100]
    assert trader.account.cash == pytest.approx(9_000 + 100 * 10)


def test_a_formal_trader_on_the_store_persists_a_readable_run():
    store_stocks(["AAA", "BBB"])
    n = 120
    trend = np.r_[np.full(20, 100.0), np.linspace(101, 160, 50), np.linspace(159, 90, 50)]
    store_bars(bars(A, trend))
    store_bars(bars(B, trend[::-1].copy()))
    store_benchmark(np.linspace(1000, 1100, n))

    class MaTrader(StockTrader):
        def init_factors(self, entity_ids, entity_schema, start_timestamp, end_timestamp, adjust_type=None, provider=None):
            return [CrossMaFactor(windows=(3, 5), entity_ids=entity_ids, start_timestamp=start_timestamp, end_timestamp=end_timestamp)]

    trader = MaTrader(start_timestamp=day(10), end_timestamp=day(n - 1), trader_name="ma_test", max_positions=2).run()
    stats = trader.stats()

    assert get_trader_names() == ["ma_test"]
    assert len(AccountStats.query_data()) == n - 10
    assert len(Order.query_data()) == stats["orders"] > 0
    assert TraderInfo.query_data()["universe_size"].item() == 2
    assert not Position.query_data().empty
    assert stats["benchmark"] == "index_ol_OSEBX" and stats["benchmark_total_return"] == pytest.approx(1100 / np.linspace(1000, 1100, n)[10] - 1)
    assert stats["total_return"] == pytest.approx(trader.account.all_value / 1_000_000 - 1)
    assert 0 <= stats["exposure"] <= 1 and 0 <= stats["win_rate"] <= 1

    # the same trader run again replaces its rows instead of adding to them
    MaTrader(start_timestamp=day(10), end_timestamp=day(n - 1), trader_name="ma_test", max_positions=2).run()
    assert len(AccountStats.query_data()) == n - 10 and len(TraderInfo.query_data()) == 1
    assert get_trader_stats("ma_test")["total_return"] == pytest.approx(stats["total_return"])

    assert trader.draw().data and trader.factors[0].draw(entity_id=A).data


def test_a_trader_without_bars_says_so():
    with pytest.raises(LookupError, match="record them first"):
        StockTrader(start_timestamp="2020-01-01", end_timestamp="2020-02-01")


def test_performance_of_a_known_series():
    dates = pd.to_datetime(["2020-01-01", "2020-07-01", "2021-01-01", "2022-01-01"])
    values = pd.Series([110.0, 88.0, 99.0, 121.0], index=dates)
    result = performance(values, start_value=100.0)

    assert result["total_return"] == pytest.approx(0.21)
    assert result["max_drawdown"] == pytest.approx(88 / 110 - 1)
    assert result["max_drawdown_date"] == pd.Timestamp("2020-07-01")
    assert result["cagr"] == pytest.approx(1.21 ** (1 / (731 / 365.25)) - 1)
    assert result["best_day"] == pytest.approx(121 / 99 - 1) and result["worst_day"] == pytest.approx(-0.2)


def test_a_flat_account_has_no_sharpe_instead_of_a_division_by_zero():
    values = pd.Series(100.0, index=business_days(10))
    result = performance(values)
    assert result["total_return"] == 0 and np.isnan(result["sharpe"]) and result["max_drawdown"] == 0


def test_the_universe_line_is_the_equal_weighted_return_of_everything_the_trader_could_pick():
    # A doubles, B halves, C starts trading late and gains 10 %: bought equally and rebalanced daily
    closes = {A: [100, 200, 200], B: [100, 50, 50]}
    kdata = pd.concat([bars(A, closes[A]), bars(B, closes[B]), bars(C, [100, 110], start=f"{day(1):%Y-%m-%d}")], ignore_index=True)
    trader = scripted_trader({}, closes, kdata=kdata)
    universe = trader.account.stats_df["universe_value"].tolist()

    day_1 = (1.0 - 0.5) / 2  # C has no return on its first day
    day_2 = (0.0 + 0.0 + 0.10) / 3
    assert universe == pytest.approx([10_000, 10_000 * (1 + day_1), 10_000 * (1 + day_1) * (1 + day_2)])


# -- real prices: commission floor, dividends, splits ---------------------------------------------


def test_the_minimum_commission_binds_on_a_small_order_and_not_on_a_large_one():
    account = SimAccount("t", input_money=200_000, buy_cost=0.0015, sell_cost=0.0015, slippage=0.0, min_cost=29)
    account.buy(A, 100.0, T, money=10_000)  # 0.15 % would be 15: the minimum of 29 applies
    small = account.orders_df.iloc[0]
    assert small["order_amount"] == 99 and small["cost"] == 29
    assert account.cash == pytest.approx(200_000 - 99 * 100 - 29)

    account.buy(B, 100.0, T, money=100_000)  # 0.15 % is about 150: above the minimum
    large = account.orders_df.iloc[1]
    assert large["order_amount"] == 998 and large["cost"] == pytest.approx(998 * 100 * 0.0015)

    account.sell(A, 100.0, T)
    assert account.orders_df.iloc[2]["cost"] == 29
    assert account.orders_df.iloc[2]["profit"] == pytest.approx(-58)  # bought and sold at the same price: two minimum fees


def test_an_order_too_small_for_the_minimum_commission_is_not_placed():
    account = SimAccount("t", input_money=100, buy_cost=0.0015, sell_cost=0.0015, slippage=0.0, min_cost=29)
    assert account.buy(A, 80.0, T, money=100) == 0 and account.cash == 100


def test_a_dividend_is_cash_and_a_split_changes_the_shares_but_not_the_value():
    account = SimAccount("t", input_money=10_000, buy_cost=0.0, sell_cost=0.0, slippage=0.0)
    account.buy(A, 100.0, T, money=5_000)

    assert account.receive_dividend(A, 4.0, T) == 200 and account.cash == 5_200
    assert account.receive_dividend(B, 4.0, T) == 0  # not held

    account.apply_split(A, 2.0, T)
    holding = account.holdings[A]
    assert (holding.amount, holding.average_price, holding.last_price, holding.cost) == (100, 50.0, 50.0, 5_000)

    # a 1:3 reverse split of 100 shares leaves 33 and a third of a share, which is paid out
    account.apply_split(A, 1 / 3, T)
    assert account.holdings[A].amount == 33
    assert account.cash == pytest.approx(5_200 + (100 / 3 - 33) * 150)
    assert account.holdings[A].amount * 150 + account.cash == pytest.approx(5_200 + 5_000)
    assert account.orders_df["order_type"].tolist() == ["order_long", "dividend", "split", "split"]


def test_a_trader_on_real_prices_books_dividends_and_splits_on_their_day():
    # the stock pays 10 on day 2 (and drops by it), then splits 2:1 on day 4
    closes = {A: [100, 100, 90, 90, 45, 45]}
    opens = {A: [100, 100, 90, 90, 45, 45]}
    actions = pd.DataFrame(
        {"entity_id": [A, A, B], "timestamp": [day(2), day(4), day(2)], "dividend": [10.0, 0.0, 5.0], "split": [0.0, 2.0, 0.0]}
    )
    trader = scripted_trader({0: ([A], [])}, closes, opens, corporate_actions=actions, max_positions=1)
    stats = trader.account.stats_df.set_index("timestamp")

    assert trader.account.holdings[A].amount == 200  # 100 bought, doubled by the split
    assert stats["all_value"].tolist() == pytest.approx([10_000] * 6)  # the holder is no poorer for either event
    assert stats.loc[day(2), "cash"] == 1_000
    assert trader.account.orders_df["order_type"].tolist() == ["order_long", "dividend", "split"]
    assert trader.stats()["dividends_received"] == 1_000 and trader.stats()["orders"] == 1


def test_a_resumed_account_ends_where_an_uninterrupted_one_does():
    n = 30
    rng = np.random.default_rng(5)
    closes = {e: list(100 * np.cumprod(1 + rng.normal(0, 0.02, n))) for e in (A, B, C)}
    script = {2: ([A, B], []), 9: ([C], [A]), 15: ([A], [B]), 22: ([], [C])}

    whole = scripted_trader(script, closes, trader_name="whole")

    # the same run in three sittings, each one rebuilt from what the last one left behind
    state, signals, previous_end = None, [], 0
    for end in (10, 20, n):
        part = scripted_trader_unrun(script, {e: c[:end] for e, c in closes.items()}, trader_name="parts", mode="live")
        if state is not None:
            part.account.restore(state)
            part.trading_signals = signals
        part.run(after=None if state is None else day(previous_end - 1))
        state, signals, previous_end = part.account.to_state(), part.trading_signals, end

    assert part.account.cash == pytest.approx(whole.account.cash)
    assert {e: h.amount for e, h in part.account.holdings.items()} == {e: h.amount for e, h in whole.account.holdings.items()}
    stored = AccountStats.query_data(filters=[AccountStats.trader_name == "parts"])
    assert stored["all_value"].tolist() == pytest.approx(whole.account.stats_df["all_value"].tolist())
    orders = Order.query_data(filters=[Order.trader_name == "parts"], order=Order.id.asc())
    assert orders["id"].is_unique and len(orders) == len(whole.account.orders_df)
    assert orders["order_price"].tolist() == pytest.approx(whole.account.orders_df["order_price"].tolist())
