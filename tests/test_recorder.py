"""The Yahoo recorders, with Yahoo itself replaced by canned frames."""

import numpy as np
import pandas as pd
import pytest

from osloquant.domain import Index, Stock, Stock1dAdjKdata, Stock1dKdata, StockAction
from osloquant.recorders.yahoo import client
from osloquant.recorders.yahoo.kdata_recorder import to_bars
from osloquant.recorders.yahoo.meta_recorder import load_universe
from tests.helpers import business_days, store_stocks


def history(closes, adj_factor=1.0, start="2020-01-01") -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": business_days(len(closes), start),
            "open": closes - 1,
            "high": closes + 1,
            "low": closes - 2,
            "close": closes,
            "adj_close": closes * adj_factor,
            "volume": 100.0,
        }
    )


@pytest.fixture
def yahoo(monkeypatch):
    """A fake Yahoo: ``yahoo.data[symbol]`` is what a download of everything would return."""

    class Fake:
        data: dict[str, pd.DataFrame] = {}
        calls: list[tuple[str, pd.Timestamp]] = []

    def fetch_history(symbol, start, end=None):
        Fake.calls.append((symbol, start))
        if symbol not in Fake.data:
            raise ConnectionError(f"no data for {symbol}")
        df = Fake.data[symbol]
        return df[df["timestamp"] >= start].reset_index(drop=True)

    Fake.data, Fake.calls = {}, []
    monkeypatch.setattr(client, "fetch_history", fetch_history)
    return Fake


def test_first_run_stores_everything_and_computes_the_daily_change(yahoo):
    store_stocks(["AAA"])
    yahoo.data["AAA.OL"] = history([100, 110, 99])

    summary = Stock1dAdjKdata.record_data(provider="yahoo")

    assert (summary.entities, summary.rows, summary.failed) == (1, 3, {})
    df = Stock1dAdjKdata.query_data(code="AAA")
    assert df["close"].tolist() == [100, 110, 99]
    assert df["change_pct"].iloc[1:].tolist() == pytest.approx([0.10, -0.10])
    assert pd.isna(df["change_pct"].iloc[0])
    assert df["level"].unique().tolist() == ["1d"] and df["name"].unique().tolist() == ["AAA ASA"]


def test_second_run_fetches_only_the_recent_days_and_adds_the_new_bars(yahoo):
    store_stocks(["AAA"])
    closes = list(range(100, 140))
    yahoo.data["AAA.OL"] = history(closes[:30])
    Stock1dAdjKdata.record_data()

    yahoo.data["AAA.OL"] = history(closes)
    yahoo.calls.clear()
    summary = Stock1dAdjKdata.record_data()

    assert summary.refreshed == []
    # asked for a few days of overlap, not for the history since 2000
    assert yahoo.calls[0][1] > pd.Timestamp("2020-01-20")
    df = Stock1dAdjKdata.query_data(code="AAA")
    assert df["close"].tolist() == closes
    assert df["change_pct"].iloc[1:].notna().all()
    assert df["change_pct"].iloc[30] == pytest.approx(130 / 129 - 1)


def test_restated_history_is_downloaded_again(yahoo):
    store_stocks(["AAA"])
    closes = np.arange(100.0, 130.0)
    yahoo.data["AAA.OL"] = history(closes)
    Stock1dAdjKdata.record_data()

    # a dividend goes ex: Yahoo scales every earlier adjusted price down
    restated = np.r_[closes, 130.0, 131.0]
    yahoo.data["AAA.OL"] = history(restated, adj_factor=0.95)
    summary = Stock1dAdjKdata.record_data()

    assert summary.refreshed == ["AAA"]
    df = Stock1dAdjKdata.query_data(code="AAA")
    assert len(df) == 32
    assert df["close"].tolist() == pytest.approx(list(restated * 0.95))


def test_the_newest_stored_bar_may_change_without_counting_as_a_restatement(yahoo):
    store_stocks(["AAA"])
    yahoo.data["AAA.OL"] = history([100, 101, 102, 103, 104.5])  # recorded before the close
    Stock1dAdjKdata.record_data()

    yahoo.data["AAA.OL"] = history([100, 101, 102, 103, 104, 105])
    summary = Stock1dAdjKdata.record_data()

    assert summary.refreshed == []
    assert Stock1dAdjKdata.query_data(code="AAA")["close"].tolist() == [100, 101, 102, 103, 104, 105]


def test_one_failing_ticker_does_not_stop_the_run(yahoo):
    store_stocks(["AAA", "BAD", "CCC"])
    yahoo.data["AAA.OL"] = history([1, 2, 3])
    yahoo.data["CCC.OL"] = history([4, 5, 6])

    summary = Stock1dAdjKdata.record_data()

    assert summary.entities == 2 and list(summary.failed) == ["BAD"]
    assert sorted(Stock1dAdjKdata.query_data()["code"].unique()) == ["AAA", "CCC"]


def test_codes_limit_what_is_recorded(yahoo):
    store_stocks(["AAA", "BBB"])
    yahoo.data["AAA.OL"] = history([1, 2, 3])
    yahoo.data["BBB.OL"] = history([4, 5, 6])

    Stock1dAdjKdata.record_data(code="BBB")

    assert Stock1dAdjKdata.query_data()["code"].unique().tolist() == ["BBB"]


def test_force_update_replaces_the_history(yahoo):
    store_stocks(["AAA"])
    yahoo.data["AAA.OL"] = history([1, 2, 3, 4])
    Stock1dAdjKdata.record_data()
    yahoo.data["AAA.OL"] = history([2, 3, 4], start="2020-01-02")  # the first day is gone at the source

    Stock1dAdjKdata.record_data(force_update=True)

    assert Stock1dAdjKdata.query_data(code="AAA")["close"].tolist() == [2, 3, 4]


def test_recording_without_entities_says_what_to_do():
    with pytest.raises(LookupError, match=r"Stock\.record_data"):
        Stock1dAdjKdata.record_data()


def test_adjusted_bars_scale_the_whole_bar_but_not_the_value_traded(yahoo):
    raw = to_bars(history([100, 200], adj_factor=0.5), "raw")
    adjusted = to_bars(history([100, 200], adj_factor=0.5), "adj")

    assert raw["close"].tolist() == [100, 200] and adjusted["close"].tolist() == [50, 100]
    assert adjusted["open"].tolist() == [49.5, 99.5] and adjusted["high"].tolist() == [50.5, 100.5]
    assert adjusted["turnover"].tolist() == raw["turnover"].tolist() == [100 * 100, 200 * 100]


def test_raw_and_adjusted_tables_are_recorded_separately(yahoo):
    store_stocks(["AAA"])
    yahoo.data["AAA.OL"] = history([100, 200], adj_factor=0.5)
    Stock1dKdata.record_data()
    Stock1dAdjKdata.record_data()

    assert Stock1dKdata.query_data()["close"].tolist() == [100, 200]
    assert Stock1dAdjKdata.query_data()["close"].tolist() == [50, 100]


def test_the_bundled_universe_loads_and_records():
    universe = load_universe()
    assert len(universe) > 50 and universe["code"].is_unique
    assert {"EQNR", "DNB", "MOWI"} <= set(universe["code"])
    assert universe.loc[universe["code"] == "EQNR", "symbol"].item() == "EQNR.OL"

    summary = Stock.record_data()
    stocks = Stock.query_data(index="code")
    assert summary.rows == len(universe) == len(stocks)
    assert stocks.loc["EQNR", "id"] == "stock_ol_EQNR" and stocks.loc["EQNR", "sector"] == "Exploration & production"

    Index.record_data()
    assert "index_ol_OSEBX" in Index.query_data()["id"].tolist()


def test_a_custom_universe_file(tmp_path):
    path = tmp_path / "mine.yaml"
    path.write_text('"Banks":\n  DNB.OL: DNB\n  MING.OL: SpareBank 1 SMN\n', encoding="utf-8")
    Stock.record_data(universe=path)
    assert Stock.query_data()["code"].tolist() == ["DNB", "MING"]


@pytest.mark.parametrize(
    "text, message",
    [('"A":\n  AAPL: Apple\n', "only Oslo tickers"), ('"A":\n  DNB.OL: DNB\n"B":\n  DNB.OL: DNB again\n', "listed twice")],
)
def test_a_bad_universe_file_is_refused(tmp_path, text, message):
    path = tmp_path / "bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_universe(path)


def test_dividends_and_splits_are_recorded_from_the_price_history(yahoo):
    store_stocks(["AAA"])
    data = history([100, 101, 97, 98, 49, 50])
    data["dividend"] = [0, 0, 4.0, 0, 0, 0]
    data["split"] = [0, 0, 0, 0, 2.0, 0]
    yahoo.data["AAA.OL"] = data

    summary = StockAction.record_data()

    stored = StockAction.query_data(code="AAA")
    assert summary.rows == 2 and stored["timestamp"].tolist() == [business_days(6)[2], business_days(6)[4]]
    assert stored["dividend"].tolist() == [4.0, 0.0] and stored["split"].tolist() == [0.0, 2.0]
    # recording again adds nothing
    StockAction.record_data()
    assert len(StockAction.query_data()) == 2


def test_one_download_serves_the_recorders_that_ask_for_less(monkeypatch):
    calls = []

    def download(symbol, start, end=None):
        calls.append((symbol, start))
        df = history(range(100, 140))
        return df[df["timestamp"] >= start].reset_index(drop=True)

    monkeypatch.setattr(client, "_fetch_history", download)
    client.clear_history_cache()
    wide = client.fetch_history("AAA.OL", pd.Timestamp("2020-01-01"))
    narrow = client.fetch_history("AAA.OL", pd.Timestamp("2020-02-03"))
    other = client.fetch_history("BBB.OL", pd.Timestamp("2020-02-03"))

    assert len(calls) == 2 and [c[0] for c in calls] == ["AAA.OL", "BBB.OL"]
    assert len(wide) == 40 and narrow["timestamp"].min() == pd.Timestamp("2020-02-03") and len(other) == len(narrow)
    # a request reaching further back than what is held is downloaded
    client.fetch_history("BBB.OL", pd.Timestamp("2020-01-01"))
    assert len(calls) == 3
    client.clear_history_cache()
