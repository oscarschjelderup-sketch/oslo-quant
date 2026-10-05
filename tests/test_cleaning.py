"""The repair rules for Yahoo's recurring faults, each on the smallest history that shows the fault."""

import pandas as pd
import pytest

from osloquant.recorders.yahoo.cleaning import apply_exceptions, clean_history, load_exceptions
from osloquant.recorders.yahoo.kdata_recorder import to_bars
from tests.helpers import business_days


def history(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp"] = business_days(len(df))
    for column, default in (("volume", 1000.0), ("dividend", 0.0)):
        if column not in df.columns:
            df[column] = default
    if "adj_close" not in df.columns:
        df["adj_close"] = df["close"]
    return df


def bar(open_, high, low, close, **extra) -> dict:
    return {"open": open_, "high": high, "low": low, "close": close, **extra}


def test_a_dividend_booked_a_day_early_is_put_back():
    # SalMar, June 2024: the last cum-dividend day closed at 626.5, Yahoo reports 591.5 (= 626.5 - 35)
    wrong_factor = 1 - 35 / 591.5
    df = history(
        [
            bar(627.0, 627.0, 617.5, 619.5, adj_close=619.5 * wrong_factor),
            bar(620.0, 629.5, 618.5, 591.5, adj_close=591.5 * wrong_factor),
            bar(591.0, 601.0, 591.0, 601.0, dividend=35.0, adj_close=601.0),
        ]
    )
    cleaned, counts = clean_history(df)

    assert counts["dividend_close"] == 1
    assert cleaned["close"].tolist() == [619.5, 626.5, 601.0]
    # the adjusted series now holds the true total returns of both days
    right_factor = 1 - 35 / 626.5
    assert cleaned["adj_close"].tolist() == pytest.approx([619.5 * right_factor, 626.5 * right_factor, 601.0])
    returns = cleaned["adj_close"].pct_change().iloc[1:]
    # Yahoo's adjustment takes the dividend off the cum-day close, so the ex-day return is 601 / (626.5 - 35) - 1:
    # +1.6 %, where the uncleaned series showed -4.5 % followed by +8.0 %
    assert returns.tolist() == pytest.approx([626.5 / 619.5 - 1, 601.0 / (626.5 - 35) - 1])


def test_a_close_below_the_low_is_left_alone_when_no_dividend_explains_it():
    df = history([bar(100, 101, 99, 100), bar(100, 102, 99, 95), bar(95, 96, 94, 95, dividend=1.0)])
    cleaned, counts = clean_history(df)
    assert counts["dividend_close"] == 0 and counts["range"] == 1
    assert cleaned["close"].tolist() == [100, 95, 95]
    assert cleaned["low"].tolist() == [99, 95, 94]  # the range is widened to hold the close


def test_an_open_outside_the_range_is_moved_to_its_nearest_end():
    df = history([bar(15.0, 16.0, 15.0, 15.5), bar(3.9, 16.1, 15.5, 15.6), bar(20.0, 16.0, 15.0, 15.2)])
    cleaned, counts = clean_history(df)
    assert counts["open"] == 2
    assert cleaned["open"].tolist() == [15.0, 15.5, 16.0]


def test_an_open_and_low_left_unrestated_for_a_split_are_pulled_back_to_the_closes_around_them():
    # DNO, May 2005: open and low are a quarter of the closes on either side
    df = history([bar(2.10, 2.15, 2.05, 2.10), bar(0.52, 2.08, 0.51, 2.08), bar(2.09, 2.40, 2.05, 2.38)])
    cleaned, counts = clean_history(df)
    assert counts["open"] == 1
    # the open goes to the previous close, and then into the day's own (correct) high of 2.08
    assert cleaned.loc[1, ["open", "low", "high"]].tolist() == [2.08, 2.08, 2.08]


def test_a_stale_open_with_a_stale_high_does_not_drag_the_open_back():
    # Orkla, January 2007: open and high are both a fifth of the close and the low
    df = history([bar(72.8, 74.5, 72.4, 74.0), bar(14.94, 14.94, 74.0, 74.4), bar(74.4, 74.6, 73.7, 73.9)])
    cleaned, counts = clean_history(df)
    assert counts["open"] == 1
    assert cleaned.loc[1, ["open", "high", "low", "close"]].tolist() == [74.0, 74.4, 74.0, 74.4]


def test_an_open_at_exactly_half_is_caught():
    # Tomra, 2000: opens left unrestated for a 2:1 split
    df = history([bar(30, 30.5, 29.5, 30.0), bar(15.0, 30.2, 15.0, 30.0, volume=0.0), bar(30, 31, 30, 30.6)])
    cleaned, counts = clean_history(df)
    assert counts["open"] == 1 and cleaned.loc[1, ["open", "low"]].tolist() == [30.0, 30.0]


def test_a_real_gap_is_not_mistaken_for_a_stale_open():
    # Norwegian, May 2020: opened 60 % down and closed 31 % down. The close moved too, so the open is real.
    df = history([bar(160, 162, 155, 158.0), bar(62.8, 132.7, 62.8, 108.9), bar(108, 110, 95, 100)])
    cleaned, counts = clean_history(df)
    assert counts["open"] == 0 and cleaned.loc[1, "open"] == 62.8


def test_a_one_day_spike_without_volume_is_dropped_but_one_with_volume_is_kept():
    rows = [bar(84, 85, 83, 84.0), bar(334, 334, 334, 334.0, volume=0.0), bar(84.6, 84.6, 82.3, 82.3), bar(82, 83, 81, 82.5)]
    cleaned, counts = clean_history(history(rows))
    assert counts["spike"] == 1 and cleaned["close"].tolist() == [84.0, 82.3, 82.5]

    rows[1]["volume"] = 5000.0
    cleaned, counts = clean_history(history(rows))
    assert counts["spike"] == 0 and len(cleaned) == 4


def test_every_cleaned_bar_has_open_and_close_inside_its_range():
    df = history([bar(10, 11, 9, 12), bar(2, 11, 9, 8), bar(10, 10, 10, 10)])
    cleaned, _ = clean_history(df)
    assert ((cleaned[["open", "close"]].min(axis=1) >= cleaned["low"]) & (cleaned[["open", "close"]].max(axis=1) <= cleaned["high"])).all()


def test_padding_is_dropped_but_a_traded_or_moving_bar_is_not():
    df = history(
        [
            bar(10, 10.5, 9.5, 10),
            bar(10, 10, 10, 10, volume=0.0),  # padding: flat, unchanged, no volume
            bar(11, 11, 11, 11, volume=0.0),  # the price moved, so only the volume is missing
            bar(11, 11, 11, 11, volume=5.0),  # flat and unchanged, but it traded
        ]
    )
    cleaned, counts = clean_history(df)
    assert counts["untraded"] == 1
    assert cleaned["timestamp"].tolist() == [df["timestamp"].iloc[i] for i in (0, 2, 3)]
    assert len(clean_history(df, drop_untraded=False)[0]) == 4


def test_cleaning_an_empty_history_is_harmless():
    empty = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "adj_close", "volume", "dividend"])
    cleaned, counts = clean_history(empty)
    assert cleaned.empty and sum(counts.values()) == 0
    assert apply_exceptions(empty, "AAA.OL").empty


def test_a_listed_bad_print_is_removed_from_the_adjusted_series_only():
    # a close that doubles for one day and reverts, as with a split booked a day late
    df = history([bar(15, 15.5, 14.5, 15.0), bar(15, 15.5, 14.8, 30.0), bar(14.0, 15.2, 14.0, 15.0), bar(15, 16, 15, 15.3)])
    listed = {
        "drop_returns": [
            {"ticker": "AAA.OL", "date": str(df["timestamp"].iloc[1].date())},
            {"ticker": "AAA.OL", "date": str(df["timestamp"].iloc[2].date())},
            {"ticker": "BBB.OL", "date": str(df["timestamp"].iloc[3].date())},
        ],
        "history_start": {},
    }
    cleaned, _ = clean_history(df)
    fixed = apply_exceptions(cleaned, "AAA.OL", listed)
    adjusted, quoted = to_bars(fixed, "adj"), to_bars(fixed, "raw")

    assert adjusted["close"].pct_change().iloc[1:].tolist() == pytest.approx([0.0, 0.0, 0.02])
    assert adjusted["close"].iloc[-1] == 15.3  # the newest prices are never rescaled
    flat = adjusted.iloc[[1, 2]]
    assert (flat["open"] == flat["close"]).all() and (flat["high"] == flat["low"]).all()
    assert quoted["close"].tolist() == [15.0, 30.0, 15.0, 15.3]


def test_history_before_a_listed_start_is_dropped():
    df = history([bar(1, 1, 1, 1), bar(2, 2, 2, 2), bar(3, 3, 3, 3)])
    listed = {"drop_returns": [], "history_start": {"AAA.OL": {"date": str(df["timestamp"].iloc[1].date())}}}
    assert apply_exceptions(df, "AAA.OL", listed)["close"].tolist() == [2, 3]
    assert apply_exceptions(df, "BBB.OL", listed)["close"].tolist() == [1, 2, 3]


def test_the_bundled_exceptions_are_well_formed():
    listed = load_exceptions()
    assert listed["drop_returns"] and listed["history_start"]
    for item in listed["drop_returns"]:
        assert item["ticker"].endswith(".OL") and pd.Timestamp(item["date"]) and len(item["reason"]) > 20
    for ticker, item in listed["history_start"].items():
        assert ticker.endswith(".OL") and pd.Timestamp(item["date"]) and len(item["reason"]) > 20
