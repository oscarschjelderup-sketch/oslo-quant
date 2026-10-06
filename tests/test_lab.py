"""The strategy lab's simulator and strategies, on prices whose outcome is known."""

import numpy as np
import pandas as pd
import pytest

from osloquant.research.lab import (
    MONTH,
    STRATEGIES,
    Panel,
    annual,
    build_schedules,
    max_drawdown,
    run_lab,
    simulate,
    turnover_per_year,
)


def prices(data: dict[str, list[float]], start: str = "2020-01-01") -> pd.DataFrame:
    n = len(next(iter(data.values())))
    return pd.DataFrame(data, index=pd.bdate_range(start, periods=n))


def test_holdings_drift_with_their_prices_between_trades():
    p = prices({"A": [100, 110, 121, 121], "B": [100, 100, 100, 50]})
    returns = simulate(p, [(0, {"A": 0.5, "B": 0.5})], cost=0.0)
    # day 1: (110 + 100) / 200; day 2: (121 + 100) / 210; day 3: (121 + 50) / 221
    assert returns.tolist() == pytest.approx([0.0, 210 / 200 - 1, 221 / 210 - 1, 171 / 221 - 1])
    assert returns.index[0] == p.index[0]  # the day of the first trade, which costs nothing here


def test_cash_is_whatever_the_weights_leave_and_earns_nothing():
    p = prices({"A": [100, 200, 200]})
    assert simulate(p, [(0, {"A": 0.25})], cost=0.0).tolist() == pytest.approx([0.0, 0.25, 0.0])
    assert simulate(p, [(0, {})], cost=0.0).tolist() == [0.0, 0.0, 0.0]


def test_a_trade_pays_cost_on_the_value_traded_and_only_on_that():
    p = prices({"A": [100, 100, 100, 100], "B": [100, 100, 100, 100]})
    buy_all = simulate(p, [(0, {"A": 1.0})], cost=0.01)
    assert buy_all.tolist() == pytest.approx([-0.01, 0.0, 0.0, 0.0])  # buying in costs 1 % of the value, on the day
    switch = simulate(p, [(0, {"A": 1.0}), (2, {"B": 1.0})], cost=0.01)
    assert switch.tolist() == pytest.approx([-0.01, 0.0, -0.02, 0.0])  # sell all of A, buy all of B: 200 % of the value traded
    keep = simulate(p, [(0, {"A": 0.5, "B": 0.5}), (2, {"A": 0.5, "B": 0.5})], cost=0.01)
    assert keep.tolist() == pytest.approx([-0.01, 0.0, 0.0, 0.0])  # nothing drifted, nothing more to trade


def test_rebalancing_back_to_equal_weights_trades_only_the_drift():
    p = prices({"A": [100, 200, 200], "B": [100, 100, 100]})
    returns = simulate(p, [(0, {"A": 0.5, "B": 0.5}), (1, {"A": 0.5, "B": 0.5})], cost=0.01)
    # after day 1 A is two thirds of the value; back to a half means selling a sixth and buying a sixth
    assert returns.iloc[1] == pytest.approx((1 + 0.5) * (1 - 0.01 / 3) - 1)


def test_measures_on_a_known_series():
    returns = pd.Series([0.1, -0.5, 0.2], index=pd.bdate_range("2020-01-01", periods=3))
    assert max_drawdown(returns) == pytest.approx(-0.5)
    flat = pd.Series(0.0, index=pd.bdate_range("2020-01-01", periods=252))
    assert annual(flat) == 0.0


def synthetic_panel(n_stocks: int = 12, years: int = 6, seed: int = 0, spread: float = 0.0018) -> Panel:
    """Stocks with persistent drifts: the ones that rose most keep rising, so momentum must win here."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2014-01-01", periods=years * 252)
    drifts = np.linspace(-spread / 3, 2 * spread / 3, n_stocks)
    walks = 100 * np.exp(np.cumsum(drifts + rng.normal(0, 0.01, (len(days), n_stocks)), axis=0))
    closes = pd.DataFrame(walks, index=days, columns=[f"stock_ol_S{k:02d}" for k in range(n_stocks)])
    closes.iloc[:400, -1] = np.nan  # one stock lists later
    return Panel.from_closes(closes)


def test_a_stock_is_eligible_only_with_a_year_of_prices():
    panel = synthetic_panel()
    late = panel.eligible["stock_ol_S11"]
    assert late.any() and panel.close.index.get_loc(late.idxmax()) == 400 + 251  # its 252nd trading day


def test_the_strategies_decide_on_month_ends_and_trade_the_day_after():
    panel = synthetic_panel()
    schedules = build_schedules(panel, pd.Timestamp("2015-06-01"))
    assert set(schedules) == {s.name for s in STRATEGIES}
    days = panel.close.index
    for name in ("equal_weight", "momentum", "trend", "low_volatility"):
        for day, _weights in schedules[name]:
            decided = days[day - 1]
            assert (decided.month != days[day].month) and decided >= pd.Timestamp("2015-06-01")
    momentum = dict(schedules["momentum"])
    picks = momentum[schedules["momentum"][-1][0]]
    assert len(picks) == 3 and sum(picks.values()) == pytest.approx(1.0)  # a fifth of 12, rounded up
    assert set(picks) <= {f"stock_ol_S{k:02d}" for k in range(8, 12)}  # the strongest drifts
    turn = schedules["turn_of_month"]
    assert all(weights == {} for _, weights in turn[1::2]) and all(weights for _, weights in turn[0::2])


def test_a_signal_never_uses_the_day_it_trades_on():
    panel = synthetic_panel()
    start = pd.Timestamp("2015-06-01")
    before = build_schedules(panel, start)["momentum"]
    # change every price after the first decision: the first trade must not notice
    changed = panel.close.copy()
    first_trade = before[0][0]
    changed.iloc[first_trade:] *= np.random.default_rng(9).uniform(0.5, 1.5, changed.iloc[first_trade:].shape)
    after = build_schedules(Panel.from_closes(changed), start)["momentum"]
    assert after[0] == before[0]


def test_the_lab_finds_planted_momentum_and_reports_every_test():
    result = run_lab(synthetic_panel(years=16, seed=1, spread=0.003), start="2015-06-01", cost=0.004, blocks=8, bootstrap_samples=200)
    table = result.table
    assert list(table.index) == [s.name for s in STRATEGIES]
    momentum = table.loc["momentum"]
    assert momentum["excess"] > 0.05 and momentum["excess_low"] > 0 and momentum["dsr"] > 0.9
    assert table.loc["reversal", "excess"] < 0  # buying last month's losers loses where trends persist
    assert table.loc["equal_weight", "turnover"] < table.loc["momentum", "turnover"]
    assert result.overfitting["pbo"] < 0.2 and result.overfitting["configurations"] == 24  # a real edge is not overfitting
    assert 1 < result.overfitting["effective_trials"] < result.overfitting["trials"] == 34
    assert result.overfitting["splits"] == 70  # C(8, 4)
    assert {"2009-2016", "2017-"} <= set(table.columns)


def test_turnover_counts_one_way_trades_a_year():
    p = prices({"A": [100.0] * 253, "B": [100.0] * 253})
    switch_monthly = [(k, {"A": 1.0} if (k // MONTH) % 2 == 0 else {"B": 1.0}) for k in range(0, 252, MONTH)]
    # buying in once, then eleven switches that sell all of one and buy all of the other: 23 portfolios traded,
    # half of which is the one-way turnover, over a year
    assert turnover_per_year(switch_monthly, p) == pytest.approx(11.5, rel=0.02)


# -- real costs -----------------------------------------------------------------------------------


def test_the_minimum_fee_makes_many_small_orders_dear():
    from osloquant.research.lab import Costs

    p = prices({f"S{k}": [100.0] * 4 for k in range(30)})
    spread_thin = {f"S{k}": 1 / 30 for k in range(30)}
    small = simulate(p, [(0, spread_thin)], Costs(rate=0.0015, min_fee=29, slippage=0.0, capital=100_000, buffer=0.0))
    # thirty orders of NOK 3 333: the NOK 29 minimum binds on every one of them
    assert small.iloc[0] == pytest.approx(-30 * 29 / 100_000)
    large = simulate(p, [(0, spread_thin)], Costs(rate=0.0015, min_fee=29, slippage=0.0, capital=10_000_000, buffer=0.0))
    assert large.iloc[0] == pytest.approx(-0.0015)  # orders of NOK 333 333: the percentage binds
    assert small.attrs == {"traded": pytest.approx(1.0), "fees": pytest.approx(30 * 29 / 100_000), "orders": 30}


def test_a_holding_close_to_its_target_is_left_alone():
    from osloquant.research.lab import Costs

    p = prices({"A": [100, 110, 110], "B": [100, 100, 100]})
    costs = Costs(rate=0.0, min_fee=10, slippage=0.0, capital=1_000, buffer=0.25)
    # after day 1 A is 52.4 % and B 47.6 %: both within a quarter of their 50 % target, so no order and no fee
    kept = simulate(p, [(0, {"A": 0.5, "B": 0.5}), (1, {"A": 0.5, "B": 0.5})], costs)
    assert kept.attrs["orders"] == 2 and kept.iloc[1] == pytest.approx(0.05)
    # without the buffer the drift is traded back, at the minimum fee for each of the two orders
    traded = simulate(p, [(0, {"A": 0.5, "B": 0.5}), (1, {"A": 0.5, "B": 0.5})], Costs(rate=0.0, min_fee=10, slippage=0.0, capital=1_000, buffer=0.0))
    assert traded.attrs["orders"] == 4


def test_new_orders_are_scaled_to_the_cash_that_is_left():
    from osloquant.research.lab import Costs

    p = prices({"A": [100, 300, 300, 300], "B": [100, 100, 100, 100], "C": [100, 100, 100, 100]})
    costs = Costs(rate=0.0, min_fee=0, slippage=0.0, capital=1_000, buffer=10.0)  # a wide buffer: holdings are never trimmed
    returns = simulate(p, [(0, {"A": 0.5, "B": 0.5}), (1, {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})], costs)
    # A grew to 75 % and B is 25 %: both kept, so there is no cash for C and it is not bought
    assert returns.attrs["orders"] == 2 and returns.iloc[2:].tolist() == [0.0, 0.0]


def test_the_survivorship_gap_against_a_whole_market_index(tmp_path):
    from osloquant.research.lab import survivorship_gap

    panel = synthetic_panel(years=4, seed=3)
    days = panel.close.index
    months = pd.period_range(days[0], days[-1], freq="M")
    # a whole market that earns 1 % a month: our survivors are measured against that
    rows = ["date,EW,VW,OSEAX,OBX"] + [f"{m.end_time:%Y%m%d},0.01,0.008,," for m in months]
    path = tmp_path / "Norway_market_portfolios_monthly.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    gap = survivorship_gap(path, panel=panel, start=str(days[300].date()))
    assert gap["market_ew"] == pytest.approx(1.01**12 - 1)
    assert gap["gap"] == pytest.approx(gap["ours"] - gap["market_ew"]) and gap["months"] > 24
