"""E19 (docs/forbedring/endringer.md): periods by the calendar, «other» is no shared driver, a Brier of zero is better,
no update after the horizon, and a flat series has no RSI. Synthetic data and a temp home."""

from __future__ import annotations

import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant.dashboard import afterreport as ar
from osloquant.dashboard import charts
from osloquant.dashboard import technicals as tc
from osloquant.dashboard import updates as up

from .test_updates import REPORT, VIEW


def _closes(days: pd.DatetimeIndex, start: float = 100.0, step: float = 0.1) -> pd.Series:
    return pd.Series([start + step * i for i in range(len(days))], index=days)


def test_a_month_is_a_calendar_month_and_a_period_needs_a_close_on_or_before_its_start():
    # every weekday from 2 Jan 2025 to 7 Nov 2026, minus three holidays in May 2026: 6 months back is still 7 May
    days = pd.bdate_range("2025-01-02", "2026-11-09").difference(pd.DatetimeIndex(["2026-05-01", "2026-05-14", "2026-05-25"]))
    c = _closes(days)
    by = {p["key"]: p for p in charts.period_ranges(c)}
    assert by["6m"]["x0"] == "2026-05-08" and by["1m"]["x0"] == "2026-10-09" and by["1a"]["x0"] == "2025-11-07"       # 9 May and 9 Nov 2025 are weekend days
    assert by["6m"]["ret"] == pytest.approx(float(c.iloc[-1] / c.loc["2026-05-08"] - 1))
    assert by["6m"]["sessions"] == len(c[c.index > "2026-05-08"]) and by["6m"]["sessions"] != 126
    assert by["1a"]["enough"] and not by["5a"]["enough"]                  # under five years of history: honestly off
    assert by["5d"]["enough"] and by["5d"]["sessions"] == 5 and by["ytd"]["x0"] == "2025-12-31"
    # the edge: a series that starts exactly one month back has the month; one day shorter has not (funn #70)
    exact = _closes(pd.bdate_range("2026-10-09", "2026-11-09"))
    assert {p["key"]: p["enough"] for p in charts.period_ranges(exact)}["1m"]
    short = _closes(pd.bdate_range("2026-10-12", "2026-11-09"))
    assert not {p["key"]: p["enough"] for p in charts.period_ranges(short)}["1m"]
    six = _closes(pd.bdate_range("2026-11-02", "2026-11-09"))            # six closes: five sessions back exist
    assert {p["key"]: p["enough"] for p in charts.period_ranges(six)}["5d"]
    assert not {p["key"]: p["enough"] for p in charts.period_ranges(six.iloc[1:])}["5d"]


def test_other_is_not_a_driver_two_views_can_share():
    from osloquant.dashboard import portfolio as pf

    class Case:
        def __init__(self, code, kill):
            self.code, self.name, self.kill = code, code, kill
            self.view = {"rating": "BUY", "target": 120.0, "price": 100.0, "kill": kill}

    cases = [Case("AAA", ["something nobody can classify"]), Case("BBB", ["another unclassified thing"]), Case("CCC", ["gross margin below 40%"]),
             Case("DDD", ["EBIT margin under 10%"])]
    ex = pf.exposure(cases, {c.code: "Seafood" for c in cases}, {})
    assert "other" not in ex["shared_drivers"]
    assert ex["shared_drivers"].get("margin") == ["CCC", "DDD"]


def test_a_brier_of_zero_is_better_than_any_other():
    assert up._better(0.0, 0.875) == "bedre" and up._better(0.875, 0.0) == "ikke bedre"
    assert up._better(0.5, 0.5) == "lik" and up._better(None, 0.5) == "–" and up._better(0.5, None) == "–"


def test_a_view_past_its_horizon_takes_no_update_and_asks_for_none(home, monkeypatch):
    jg.append("judgement", VIEW)                                          # 1 Oct 2026, twelve months
    late = {"date": "2027-10-20", "what": "Q3 2027 report", "source": "report reader"}
    monkeypatch.setattr(ar, "newest_report", lambda c, today, cal_doc=None, code=None: late if today > pd.Timestamp("2027-10-01") else REPORT)
    assert [p["code"] for p in up.pending(jg.read_log(), [], pd.Timestamp("2026-10-25"))] == ["AAA"]        # inside the horizon: asked
    assert up.pending(jg.read_log(), [], pd.Timestamp("2027-10-25")) == []                                    # past it: not asked
    form = {"changed": True, "p_bear": "0.1", "p_base": "0.2", "p_bull": "0.7", "trigger_date": "2027-10-20", "trigger_what": "Q3 2027", "trigger_source": "x"}
    with pytest.raises(ValueError, match="avsluttet"):
        up.write("AAA", form, 150.0, "2027-10-25", "2027-10-25")
    assert len(jg.read_log()) == 1
    row = up.write("AAA", form | {"trigger_date": "2026-10-20"}, 110.0, "2026-10-25", "2026-10-25")          # inside the horizon: written
    assert row["kind"] == "update" and up.horizon_end(VIEW) == pd.Timestamp("2027-10-01")


def test_an_update_written_after_the_horizon_is_not_scored(home):
    jg.append("judgement", VIEW)
    rows = jg.read_log()
    inside = {"seq": 2, "kind": "update", "ref_seq": 1, "code": "AAA", "date": "2027-03-01", "p_bear": 0.2, "p_base": 0.6, "p_bull": 0.2, "changed": True}
    hindsight = {"seq": 3, "kind": "update", "ref_seq": 1, "code": "AAA", "date": "2027-11-15", "p_bear": 0.0, "p_base": 0.0, "p_bull": 1.0, "changed": True}
    table = pd.DataFrame([{"seq": 1, "code": "AAA", "status": "final", "scenario_hit": "bull"}])
    sc = up.scoring(rows + [inside, hindsight], table, pd.Timestamp("2027-12-01"))
    (pair,) = sc["pairs"]
    assert pair["updates"] == 1 and pair["brier_updated"] == pytest.approx(up.brier([0.2, 0.6, 0.2], "bull"))     # the perfect hindsight row is ignored
    assert up.scoring(rows + [hindsight], table, pd.Timestamp("2027-12-01"))["pairs"] == []


def test_a_flat_series_has_no_rsi():
    days = pd.bdate_range("2026-01-01", periods=60)
    flat = pd.Series(100.0, index=days)
    rows = {r.label: r for r in tc.rows(flat, None, None)}
    assert rows["RSI 14"].value == "–" and "ikke beveget seg" in rows["RSI 14"].detail
