import pandas as pd
import pytest

from osloquant.contract import context
from osloquant.contract.api import decode_entity_id, get_coverage, get_entity_ids, get_kdata, get_kdata_schema
from osloquant.contract.storage import df_to_db
from osloquant.domain import Index1dKdata, Stock, Stock1dAdjKdata, Stock1dKdata
from tests.helpers import bars, store_bars, store_stocks


def test_recording_the_same_rows_twice_does_not_duplicate_them():
    frame = bars("stock_ol_AAA", [10, 11, 12])
    assert df_to_db(frame, Stock1dAdjKdata, "yahoo") == 3
    assert df_to_db(frame, Stock1dAdjKdata, "yahoo") == 3
    assert len(Stock1dAdjKdata.query_data()) == 3


def test_a_row_recorded_again_is_overwritten():
    store_bars(bars("stock_ol_AAA", [10, 11, 12]))
    store_bars(bars("stock_ol_AAA", [10, 11, 99]))
    assert Stock1dAdjKdata.query_data(code="AAA")["close"].tolist() == [10, 11, 99]


def test_force_update_false_keeps_the_stored_row():
    store_bars(bars("stock_ol_AAA", [10, 11, 12]))
    df_to_db(bars("stock_ol_AAA", [10, 11, 99]), Stock1dAdjKdata, "yahoo", force_update=False)
    assert Stock1dAdjKdata.query_data(code="AAA")["close"].tolist() == [10, 11, 12]


def test_query_filters_order_limit_and_index():
    store_bars(bars("stock_ol_AAA", [10, 11, 12, 13]))
    store_bars(bars("stock_ol_BBB", [20, 21, 22, 23]))

    assert len(Stock1dAdjKdata.query_data(codes=["AAA", "BBB"])) == 8
    assert Stock1dAdjKdata.query_data(code="BBB", start_timestamp="2020-01-02", end_timestamp="2020-01-03")["close"].tolist() == [21, 22]
    newest = Stock1dAdjKdata.query_data(entity_id="stock_ol_AAA", order=Stock1dAdjKdata.timestamp.desc(), limit=1)
    assert newest["close"].tolist() == [13]
    expensive = Stock1dAdjKdata.query_data(filters=[Stock1dAdjKdata.close > 21.5], columns=["code", "close"])
    assert expensive["code"].unique().tolist() == ["BBB"] and list(expensive.columns) == ["code", "close"]

    two_dimensional = Stock1dAdjKdata.query_data(index=["entity_id", "timestamp"], drop_index_col=True)
    assert two_dimensional.index.names == ["entity_id", "timestamp"]
    assert two_dimensional.loc[("stock_ol_BBB", pd.Timestamp("2020-01-01")), "close"] == 20


def test_query_return_types():
    store_bars(bars("stock_ol_AAA", [10, 11]))
    as_dicts = Stock1dAdjKdata.query_data(return_type="dict")
    as_objects = Stock1dAdjKdata.query_data(return_type="domain")
    assert as_dicts[0]["close"] == 10 and as_dicts[0]["change_pct"] is None
    assert [o.close for o in as_objects] == [10, 11]


def test_timestamps_come_back_as_datetimes():
    store_bars(bars("stock_ol_AAA", [10, 11]))
    df = Stock1dAdjKdata.query_data()
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


def test_entities_and_ids():
    ids = store_stocks(["AAA", "BBB"])
    assert get_entity_ids(Stock) == ids
    assert get_entity_ids(Stock, codes=["BBB"]) == ["stock_ol_BBB"]
    assert decode_entity_id("stock_ol_SB1NO") == ("stock", "ol", "SB1NO")


def test_kdata_schema_lookup_defaults_to_adjusted_for_stocks():
    assert get_kdata_schema("stock") is Stock1dAdjKdata
    assert get_kdata_schema("stock", adjust_type="raw") is Stock1dKdata
    assert get_kdata_schema("index") is Index1dKdata
    with pytest.raises(KeyError):
        get_kdata_schema("index", adjust_type="adj")


def test_get_kdata_reads_the_table_of_the_entity_type():
    store_bars(bars("stock_ol_AAA", [10, 11]))
    assert get_kdata(entity_id="stock_ol_AAA")["close"].tolist() == [10, 11]


def test_coverage_of_an_empty_and_a_filled_table():
    assert get_coverage(Stock1dAdjKdata)["rows"] == 0
    store_bars(bars("stock_ol_AAA", [10, 11, 12]))
    coverage = get_coverage(Stock1dAdjKdata)
    assert (coverage["rows"], coverage["entities"]) == (3, 1)
    assert coverage["first"] == pd.Timestamp("2020-01-01") and coverage["last"] == pd.Timestamp("2020-01-03")


def test_every_schema_is_registered_with_a_database_and_a_provider():
    assert context.schemas
    for schema in context.schemas:
        assert context.schema_db_name[schema]
        assert schema.get_providers()
    assert context.schema_by_name("stock1dadjkdata") is Stock1dAdjKdata
    with pytest.raises(KeyError):
        context.schema_by_name("NoSuchSchema")


def test_every_market_schema_has_a_yahoo_recorder():
    for schema in context.schemas:
        if "osloquant" in schema.get_providers():
            continue  # the trader's own tables are written by the trader
        assert "yahoo" in schema.provider_map_recorder(), schema.__name__


def test_a_store_written_before_a_column_existed_gains_it(home):
    import sqlite3

    from osloquant.contract.storage import dispose_engines
    from osloquant.trader import AccountStats

    # a trader database as an earlier version left it: the account table without the universe column
    path = home / "data" / "osloquant_trader_info.db"
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE account_stats (id VARCHAR PRIMARY KEY, entity_id VARCHAR, timestamp DATETIME, trader_name VARCHAR(128), all_value FLOAT)')
        db.execute("INSERT INTO account_stats VALUES ('old_2020-01-01', 'old', '2020-01-01 00:00:00.000000', 'old', 123.0)")
    dispose_engines()

    old = AccountStats.query_data()
    assert old["all_value"].tolist() == [123.0] and pd.isna(old["universe_value"].iloc[0])
    row = old.assign(id="new_2020-01-02", universe_value=5.0)
    df_to_db(row, AccountStats, "osloquant")
    assert AccountStats.query_data()["universe_value"].tolist()[1] == 5.0
