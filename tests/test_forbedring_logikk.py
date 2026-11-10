"""Wrong numbers and wrong logic fixed in the improvement pass (docs/forbedring/endringer.md, E7 and on). Synthetic
store and temp home only."""

from __future__ import annotations

import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant.dashboard import afterreport as ar
from osloquant.dashboard import odds as od
from osloquant.dashboard import render as rd

from .test_dashboard import GOOD, app  # noqa: F401  the synthetic store, book and home
from .test_updates import REPORT, VIEW


# ------------------------------------------------------------------------------------------------ E7 the log and the forms
def test_e7_a_number_is_what_a_person_types_and_never_nan_or_infinity():
    assert jg.parse_number("0,25") == 0.25 and jg.parse_number("13 500") == 13500.0 and jg.parse_number("45.5") == 45.5
    assert jg.parse_number("13 500,5") == 13500.5 and jg.parse_number("") is None and jg.parse_number(None) is None
    for bad in ("nan", "NaN", "inf", "-inf", "1e999", "abc", "1,2,3"):
        with pytest.raises(ValueError, match="ikke et"):
            jg.parse_number(bad)


def test_e7_the_log_refuses_a_row_with_a_number_that_is_not_finite(home):
    with pytest.raises(ValueError, match="target is not a finite number"):
        jg.append("judgement", VIEW | {"target": float("nan")})
    with pytest.raises(ValueError, match="bull is not a finite number"):
        jg.append("judgement", VIEW | {"bull": float("inf")})
    with pytest.raises(ValueError, match=r"prior\[1\] is not a finite number"):
        jg.append("update", dict(code="AAA", date="2026-10-21", ref_seq=1, trigger=REPORT, p_bear=0.2, p_base=0.5, p_bull=0.3, prior=[0.2, float("nan"), 0.3]))
    assert not jg.log_path().exists()


def test_e7_the_forms_refuse_nan_and_infinity_and_write_nothing(app):  # noqa: F811
    client, _ = app
    for field, value in (("target", "nan"), ("target", "inf"), ("bear", "1e999"), ("p_bear", "nan")):
        r = client.post("/stock/BBB/judge", data={**GOOD, field: value})
        assert r.status_code == 400, (field, value)
        assert "ikke et endelig tall" in r.get_data(as_text=True), (field, value)
    assert not jg.log_path().exists() or jg.read_log() == []
    r = client.post("/stock/BBB/judge", data={**GOOD, "target": "130,5", "p_bear": "0,25"})          # a decimal comma is a number
    assert r.status_code == 303 and jg.read_log()[-1]["target"] == 130.5


def test_e7_the_update_form_never_throws_typed_probabilities_away(app, monkeypatch):  # noqa: F811
    client, _ = app
    jg.append("judgement", VIEW)
    monkeypatch.setattr(ar, "newest_report", lambda c, today, cal_doc=None, code=None: REPORT if code == "AAA" else None)
    trig = {"trigger_date": REPORT["date"], "trigger_what": REPORT["what"], "trigger_source": REPORT["source"]}
    new = {"p_bear": "0.10", "p_base": "0.50", "p_bull": "0.40", "reason": "Fictional: the quarter changed my view."}
    r = client.post("/stock/AAA/update", data=trig | new)                    # new numbers, «endret» not ticked
    assert r.status_code == 400 and "kryss av for «endret»" in r.get_data(as_text=True)
    assert len(jg.read_log()) == 1                                           # nothing written
    r = client.post("/stock/AAA/update", data=trig | new | {"changed": "1", "p_bear": "0,10", "p_base": "0,50", "p_bull": "0,40"})
    assert r.status_code == 303 and jg.read_log()[-1]["p_bull"] == 0.40      # decimal commas are numbers here too
    r = client.post("/stock/AAA/update", data=trig | {"changed": "1", "p_bear": "x", "p_base": "0.5", "p_bull": "0.4"})
    assert r.status_code == 400 and "ikke et tall" in r.get_data(as_text=True) and "Traceback" not in r.get_data(as_text=True)
    # the view's own numbers typed again without the tick are «unchanged», not an error
    same = {"p_bear": "0.25", "p_base": "0.5", "p_bull": "0.25", "reason": "Fictional: as expected, nothing changes."}
    r = client.post("/stock/AAA/update", data=trig | same)
    assert r.status_code == 303 and jg.read_log()[-1]["changed"] is False


def test_e7_the_forecast_form_reads_decimal_commas_and_refuses_infinity(app):  # noqa: F811
    from osloquant.dashboard import forecasts as fc

    today = pd.Timestamp("2026-11-01")
    rep = {"date": "2026-12-01", "what": "Q4 report", "source": "book"}
    allowed = {"revenue": "Revenue"}
    assert fc.form_problems({"metric": "revenue", "low": "13 000", "mid": "13 250,5", "high": "13500"}, allowed, rep, today) == []
    probs = fc.form_problems({"metric": "revenue", "low": "1", "mid": "inf", "high": "3"}, allowed, rep, today)
    assert len(probs) == 1 and "ikke et endelig tall" in probs[0]


# ------------------------------------------------------------------------------------------------ E8 odds without a simulation
def _odds(sim: od.Outcome) -> od.CaseOdds:
    ok = od.Outcome(0.4, 0.3, 0.3, 500, extra={"since": "2010"})
    return od.CaseOdds(code="NEW", price=40.0, asof=pd.Timestamp("2026-11-09"), target=50.0, kill=33.0, kill_source="logget kill-nivå",
                       simulation={"3 mnd": sim, "12 mnd": sim}, universe={"3 mnd": ok, "12 mnd": ok}, own={"3 mnd": sim, "12 mnd": sim}, sigma=0.3, note="")


def test_e8_the_odds_card_takes_no_side_without_a_simulation():
    nan = float("nan")
    for empty in (od.Outcome(nan, nan, nan, 0, "too little history (33 sessions)", {"since": "2026-09"}), od.Outcome(0.0, 0.0, 1.0, 0, extra={"since": "2026-09"})):
        html = rd.odds_block(_odds(empty), {})
        assert "Ingen simulering" in html and "Kortet tar ikke stilling" in html
        assert "mot kill-nivået" not in html and "mot målet" not in html and "myntkast" not in html
    assert "too little history (33 sessions)" in rd.odds_block(_odds(od.Outcome(nan, nan, nan, 0, "too little history (33 sessions)", {"since": "2026-09"})), {})
    html = rd.odds_block(_odds(od.Outcome(0.2, 0.6, 0.2, 10000, extra={"since": "2015"})), {})
    assert "klart mot kill-nivået" in html and "Ingen simulering" not in html          # a real simulation still gets its verdict
