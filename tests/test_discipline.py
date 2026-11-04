"""Decision discipline on the row (D46): the pre-mortem is required and stored, the anchoring check compares a new
target with the previous one and the price move, the process score reads only what the row held, and the decision
grid crosses process with outcome (final calls only). Synthetic store, temporary home, fictional rows only."""

from __future__ import annotations

import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant.dashboard import discipline as dsc
from osloquant.dashboard import learn

from .test_dashboard import GOOD, app  # noqa: F401  (fixture)


def test_a_view_needs_three_distinct_pre_mortem_reasons_and_they_are_stored(app):  # noqa: F811
    client, _ = app
    bare = {k: v for k, v in GOOD.items() if not k.startswith("premortem")}
    r = client.post("/stock/BBB/judge", data=bare)
    assert r.status_code == 400 and "pre-mortem needs 3 reasons" in r.get_data(as_text=True) and not jg.read_log()
    r = client.post("/stock/BBB/judge", data=bare | {"premortem_1": "Fictional: price war", "premortem_2": "kort", "premortem_3": "Fictional: costs up a lot"})
    assert r.status_code == 400 and "too short" in r.get_data(as_text=True)
    same = "Fictional: the same reason twice"
    r = client.post("/stock/BBB/judge", data=bare | {"premortem_1": same, "premortem_2": same, "premortem_3": "Fictional: costs up a lot"})
    assert r.status_code == 400 and "must differ" in r.get_data(as_text=True)
    form = client.get("/stock/BBB").get_data(as_text=True)
    assert 'name="premortem_1"' in form and "det er 12 måneder frem" in form and 'name="probs_deliberate"' in form
    assert client.post("/stock/BBB/judge", data=GOOD | {"probs_deliberate": "1"}).status_code == 303
    row = jg.read_log()[-1]
    assert len(row["premortem"]) == 3 and row["premortem"][0].startswith("Fictional reason one") and row["probs_deliberate"] is True
    assert row.get("anchor") is None and jg.verify().ok                                       # the first view has nothing to anchor on


def test_the_second_view_carries_the_anchoring_check_and_the_form_shows_the_previous_one(app):  # noqa: F811
    client, snap = app
    assert client.post("/stock/BBB/judge", data=GOOD).status_code == 303
    form = client.get("/stock/BBB").get_data(as_text=True)
    assert "Forrige syn" in form and "BUY 130" in form and 'name="anchor_reason"' in form
    assert client.post("/stock/BBB/judge", data=GOOD | {"target": "140"}).status_code == 303
    a = jg.read_log()[-1]["anchor"]
    assert a["prev_seq"] == 1 and a["prev_target"] == 130 and a["tp_change"] == pytest.approx(140 / 130 - 1) and a["px_change"] == pytest.approx(0, abs=1e-6)
    assert a["kind"] is None                                                               # same price: nothing to follow


def test_anchor_check_names_following_and_sticky_targets():
    prev = {"seq": 4, "date": "2026-10-06", "price": 40.0, "target": 54.0}
    f = dsc.anchor_check(prev, 44.0, 58.0)                                                 # price +10 %, target +7.4 %
    assert f["kind"] == "follows_price" and f["px_change"] == pytest.approx(0.10) and "follows the price" in dsc.anchor_text(f)
    assert dsc.anchor_check(prev, 44.0, 55.0)["kind"] is None                              # +1.9 % is less than half the move
    assert dsc.anchor_check(prev, 41.0, 56.0)["kind"] is None                              # a 2.5 % move is not something to follow
    s = dsc.anchor_check(prev, 30.0, 54.5)                                                 # price -25 %, target unchanged
    assert s["kind"] == "sticky" and "anchor" in dsc.anchor_text(s)
    assert dsc.anchor_check(None, 44.0, 58.0) is None
    rows = [{"seq": 1, "kind": "judgement", "code": "AAA", "date": "2026-01-01", "price": 10, "target": 12, "rating": "BUY", "horizon_months": 12},
            {"seq": 2, "kind": "judgement", "code": "AAA", "date": "2026-02-01", "price": 11, "target": 13, "rating": "BUY", "horizon_months": 12, "analyst": "claude"},
            {"seq": 3, "kind": "judgement", "code": "AAA", "date": "2026-03-01", "price": 12, "target": 14, "rating": "BUY", "horizon_months": 12}]
    assert dsc.previous_view(rows, "AAA")["seq"] == 3 and dsc.previous_view(rows, "AAA", before_seq=3)["seq"] == 1
    assert dsc.previous_view(rows, "AAA", analyst="claude")["seq"] == 2


def _row(**kw):
    base = {"seq": 1, "kind": "judgement", "code": "AAA", "date": "2026-01-02", "price": 100.0, "rating": "BUY", "target": 120.0, "horizon_months": 12,
            "p_bear": 0.2, "p_base": 0.6, "p_bull": 0.2, "kill": ["margin below 10%"], "checklist": list(dsc.CHECKLIST_KEYS), "desk_run": "x",
            "premortem": ["Fictional reason one here", "Fictional reason two here", "Fictional reason three here"]}
    return base | kw


def test_process_score_reads_only_the_row():
    full = dsc.process_score(_row())
    assert full["score"] == 1.0 and full["good"] and full["items"]["blind"] is None and full["items"]["base_rate"] is None
    tmpl = dsc.process_score(_row(p_bear=0.25, p_base=0.5, p_bull=0.25))
    assert "own_probs" in tmpl["missing"] and dsc.process_score(_row(p_bear=0.25, p_base=0.5, p_bull=0.25, probs_deliberate=True))["score"] == 1.0
    weak = dsc.process_score(_row(premortem=None, kill=["margin falls"], checklist=None, desk_run=None, saw_claude=True))
    assert weak["score"] == pytest.approx(1 / 6) and not weak["good"] and set(weak["missing"]) == {"premortem", "kill_numeric", "checklist", "debated", "blind"}
    anchored = dsc.process_score(_row(anchor={"kind": "follows_price"}))
    assert "not_anchored" in anchored["missing"] and dsc.process_score(_row(anchor={"kind": "follows_price"}, anchor_reason="new contract"))["score"] == 1.0
    assert dsc.process_score(_row(base_rate={"flags": ["revenue CAGR above the 80th percentile"]}))["items"]["base_rate"] is False


def test_the_decision_grid_counts_final_calls_only():
    rows = [_row(seq=1, code="A1"), _row(seq=2, code="A2"), _row(seq=3, code="A3", premortem=None, kill=["x"], checklist=None, desk_run=None),
            _row(seq=4, code="A4", premortem=None, kill=["x"], checklist=None, desk_run=None), _row(seq=5, code="A5"), _row(seq=6, code="A6", analyst="claude")]
    table = pd.DataFrame([{"seq": 1, "code": "A1", "date": "d", "rating": "BUY", "status": "final", "direction_hit": True, "excess_osebx": 0.1},
                          {"seq": 2, "code": "A2", "date": "d", "rating": "BUY", "status": "final", "direction_hit": False, "excess_osebx": -0.1},
                          {"seq": 3, "code": "A3", "date": "d", "rating": "BUY", "status": "final", "direction_hit": True, "excess_osebx": 0.2},
                          {"seq": 4, "code": "A4", "date": "d", "rating": "BUY", "status": "final", "direction_hit": False, "excess_osebx": -0.3},
                          {"seq": 5, "code": "A5", "date": "d", "rating": "BUY", "status": "provisional", "direction_hit": True, "excess_osebx": 0.05},
                          {"seq": 6, "code": "A6", "date": "d", "rating": "BUY", "status": "final", "direction_hit": True, "excess_osebx": 0.05}])
    g = dsc.decision_grid(rows, table)
    assert {k: [e["code"] for e in v] for k, v in g["cells"].items()} == {"fortjent gevinst": ["A1"], "uflaks": ["A2"], "flaks": ["A3"], "fortjent tap": ["A4"]}
    assert [e["code"] for e in g["provisional"]] == ["A5"] and g["n_final"] == 4 and g["missing_counts"]["premortem"] == 2
    html = dsc.grid_html(g)
    assert "Beslutning mot utfall" in html and "flaks" in html and "A5 #5 (fortjent gevinst så langt)" in html


def test_the_anchored_pattern_comes_from_the_row():
    class P:
        adjusted = pd.DataFrame()
    j = _row(anchor={"kind": "follows_price"})
    assert "anchored" in learn.patterns_for(j, {"scored_to": "2026-02-01", "days": 30}, P(), [j])
    assert "anchored" not in learn.patterns_for(_row(), {"scored_to": "2026-02-01", "days": 30}, P(), [_row()])


def test_the_calibration_page_shows_the_grid(app):  # noqa: F811
    client, _ = app
    assert client.post("/stock/AAA/judge", data=GOOD).status_code == 303
    page = client.get("/calibration").get_data(as_text=True)
    assert "Beslutning mot utfall" in page and "resulting" in page
