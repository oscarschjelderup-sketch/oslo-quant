"""The dashboard's callbacks and the command line, on a small synthetic store."""

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from osloquant.cli import app
from osloquant.domain import Stock1dKdata
from osloquant.samples import SAMPLE_TRADERS, MaTrader
from osloquant.ui import app as ui
from tests.helpers import bars, business_days, random_walk, store_bars, store_benchmark, store_stocks

# wide enough that rich never wraps a table cell the assertions look for
runner = CliRunner(env={"COLUMNS": "200"})
N = 420
CODES = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]


@pytest.fixture
def store():
    ids = store_stocks(CODES)
    for i, entity_id in enumerate(ids):
        frame = bars(entity_id, random_walk(N, seed=i, drift=0.0002 * i))
        store_bars(frame)
        store_bars(frame, schema=Stock1dKdata)
    store_benchmark(random_walk(N, seed=99, start=1000, vol=0.01))
    ui._factor.cache_clear()
    return ids


def test_the_layout_builds_on_an_empty_store():
    layout = ui.create_app().layout()
    assert "No backtest is stored yet" in str(layout) and "No bars are stored yet" in str(layout)


def test_the_backtest_tab_shows_a_stored_run(store):
    MaTrader(start_timestamp=business_days(N)[30], end_timestamp=business_days(N)[-1], trader_name="ma", max_positions=3).run()
    assert "ma" in str(ui.serve_layout())

    tiles, figure, notes, options, first, table = ui.show_trader("ma")
    assert len(tiles) == 7 and "Total return" in str(tiles[0]) and "OSEBX" in str(tiles[1])
    assert [t.name for t in figure.data][:3] == ["OSEBX", "All stocks, equal weight", "ma"]
    assert "next day's open" in notes and "6 stocks" in notes
    assert first == options[0]["value"] and "fills" in options[0]["label"]
    assert "Buy" in str(table) or "Sell" in str(table)

    trades = ui.show_trades(first, "ma")
    assert {t.name for t in trades.data} >= {"Price", "Buy"}
    assert ui.show_trades(None, "ma").layout.annotations[0].text == "This backtest never traded."


def test_the_live_tab_shows_a_paper_account(store):
    from osloquant.live import AccountConfig, LiveConfig, run_live

    assert "No live account yet" in str(ui.serve_layout())
    config = LiveConfig(accounts=[AccountConfig("paper", "ma", input_money=100_000, max_positions=3)], commission_rate=0.0015, commission_min=29, slippage=0.001)
    for i in (400, 401, 402):
        run = run_live(record=False, now=(business_days(N)[i] + pd.Timedelta(hours=18)).tz_localize("Europe/Oslo"), config=config)
        assert [r.outcome for r in run.results] in (["started"], ["stepped"]), run.results
    assert "paper" in str(ui.serve_layout())

    tiles, notes, pending, holdings, figure, orders, signals = ui.show_live("paper")
    assert signals == []  # a daily account has no signal log
    assert len(tiles) == 6 and "3 sessions" in str(tiles[1]) and "only these are evidence" in str(tiles[4])
    assert "0.15 % commission (at least 29)" in notes and "No real money" in notes
    assert "Cash" in str(holdings) and "Before the open" in str(orders)
    assert [t.name for t in figure.data][:3] == ["OSEBX", "All stocks, equal weight", "paper"]
    assert figure.data[2].mode == "lines+markers"
    # a live account does not appear among the backtests
    assert "No backtest is stored yet" in str(ui.serve_layout())


@pytest.mark.parametrize("factor", list(ui.FACTORS))
def test_the_factor_tab_draws_every_listed_factor(store, factor):
    figure, title, targets = ui.show_factor(factor, store[0], "1 year")
    assert figure.data[0].name == "Price"
    assert "of 6 stocks are positive targets" in title
    assert targets is not None


def test_cli_status_and_query(store):
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0 and "Stock1dAdjKdata" in result.output

    result = runner.invoke(app, ["query", "Stock1dAdjKdata", "--code", "bbb", "--limit", "3"])
    assert result.exit_code == 0 and result.output.count("stock_ol_BBB") == 3

    assert runner.invoke(app, ["query", "NoSuchSchema"]).exit_code != 0


def test_cli_targets(store):
    result = runner.invoke(app, ["targets", "MomentumFactor"])
    assert result.exit_code == 0 and "positive targets" in result.output and "DDD ASA" in result.output
    assert runner.invoke(app, ["targets", "NoSuchFactor"]).exit_code != 0


def test_cli_check_lists_only_the_extreme_bars(store):
    crash = np.r_[np.full(10, 100.0), 45.0, np.full(10, 45.0)]
    store_stocks(["ZZZ"])
    store_bars(bars("stock_ol_ZZZ", crash))
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0 and "ZZZ" in result.output and "AAA" not in result.output


@pytest.mark.parametrize("strategy", list(SAMPLE_TRADERS))
def test_cli_backtest_runs_every_sample_strategy(store, strategy):
    start = f"{business_days(N)[300]:%Y-%m-%d}"
    result = runner.invoke(app, ["backtest", strategy, "--start", start, "--end", f"{business_days(N)[-1]:%Y-%m-%d}", "--positions", "3"])
    assert result.exit_code == 0, result.output
    assert "Return per year" in result.output and "OSEBX" in result.output

    listing = runner.invoke(app, ["traders"])
    assert listing.exit_code == 0 and strategy in listing.output


def test_cli_messages_on_an_empty_store():
    assert "No backtest is stored yet" in runner.invoke(app, ["traders"]).output
    assert runner.invoke(app, ["check"]).exit_code == 1
    assert runner.invoke(app, ["backtest", "nonsense"]).exit_code != 0


def test_recording_from_the_cli_uses_the_recorders(monkeypatch):
    from osloquant.recorders.yahoo import client

    def fetch_history(symbol, start, end=None):
        closes = random_walk(30, seed=len(symbol))
        return pd.DataFrame({"timestamp": business_days(30), "open": closes, "high": closes * 1.01, "low": closes * 0.99,
                             "close": closes, "adj_close": closes, "volume": 100.0, "dividend": 0.0})  # fmt: skip

    monkeypatch.setattr(client, "fetch_history", fetch_history)
    result = runner.invoke(app, ["record", "--codes", "eqnr,DNB.OL"])
    assert result.exit_code == 0, result.output
    assert "Stock1dAdjKdata <- yahoo: 60 rows for 2 entities" in result.output
