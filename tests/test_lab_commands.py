"""The lab's commands and the monthly trend trader, on a small synthetic store."""

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from osloquant.cli import app
from osloquant.samples import SAMPLE_TRADERS, TrendMonthlyTrader
from tests.helpers import bars, business_days, store_bars, store_stocks

runner = CliRunner(env={"COLUMNS": "260"})
N = 6 * 252


def store_market(n_stocks: int = 8, seed: int = 0, n_days: int = N) -> list[str]:
    rng = np.random.default_rng(seed)
    ids = store_stocks([f"S{k:02d}" for k in range(n_stocks)])
    drifts = np.linspace(-0.0005, 0.001, n_stocks)
    for entity_id, drift in zip(ids, drifts, strict=True):
        store_bars(bars(entity_id, 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.012, n_days))), start="2015-01-01"))
    return ids


def test_the_monthly_trend_trader_holds_the_stocks_above_their_average_and_decides_monthly():
    ids = store_market()
    days = business_days(N, start="2015-01-01")
    trader = TrendMonthlyTrader(start_timestamp=days[400], end_timestamp=days[-1], trader_name="tm", benchmark=None, input_money=100_000).run()
    orders = trader.account.orders_df
    assert not orders.empty and SAMPLE_TRADERS["trend_monthly"] is TrendMonthlyTrader
    # every order was decided on the first trading day of a month
    decided = pd.to_datetime(orders["signal_timestamp"])
    first_days = {d for d in days if d == days[(days.year == d.year) & (days.month == d.month)][0]}
    assert set(decided) <= first_days | {days[400]}
    # new holdings got an equal share of the account at the time: no order was placed only to top one up
    buys = orders[orders["order_type"] == "order_long"]
    assert buys.groupby(["entity_id", "signal_timestamp"]).size().max() == 1
    assert trader.account.holdings.keys() <= set(ids)


def test_the_lab_command_runs_every_part(tmp_path):
    long = 11 * 252  # the re-tuning check needs more than six years after the start
    store_market(n_days=long)
    days = business_days(long, start="2015-01-01")
    months = pd.period_range(days[0], days[-1], freq="M")
    csv = tmp_path / "Norway_market_portfolios_monthly.csv"
    csv.write_text("\n".join(["date,EW,VW,OSEAX,OBX"] + [f"{m.end_time:%Y%m%d},0.01,0.01,," for m in months]), encoding="utf-8")

    result = runner.invoke(app, ["lab", "--start", f"{days[300]:%Y-%m-%d}", "--odegaard", str(csv), "--no-overnight"])
    assert result.exit_code == 0, result.output
    for text in ("momentum_buffer", "momentum_managed", "Deflated Sharpe", "PBO", "Re-tuning", "Survivorship", "by what trading costs", "NOK 100,000"):
        assert text in result.output, text


def test_the_check_factor_command():
    store_market()
    result = runner.invoke(app, ["check-factor", "CrossMaFactor", "--samples", "2"])
    assert result.exit_code == 0, result.output
    assert "No look-ahead" in result.output and "with less history before it" in result.output

    leaky = runner.invoke(app, ["check-factor", "tests.test_checks:TomorrowFactor", "--samples", "2"])
    assert leaky.exit_code == 0 and "Look-ahead found" in leaky.output
    assert runner.invoke(app, ["check-factor", "NoSuchFactor"]).exit_code != 0
