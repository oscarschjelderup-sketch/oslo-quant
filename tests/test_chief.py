"""The head of analysis (D50): thirty rules with a source and a metric each, statuses that say when data is too thin,
proposals ranked and learned from – an approved one goes to the backlog, a rejected one stays away until its metric
worsens (never after «aldri»), and rejections halve the rule's weight. Fictional context and a temporary home only."""

from __future__ import annotations

import pandas as pd
import pytest

from osloquant.dashboard import chief as ch
from osloquant.dashboard import discipline as dsc

from .test_dashboard import GOOD, app  # noqa: F401  (fixture)


def _v(seq, **kw):
    base = {"seq": seq, "kind": "judgement", "code": f"C{seq}", "date": "2026-11-06", "price": 100.0, "rating": "BUY", "target": 130.0, "horizon_months": 12,
            "bear": 70.0, "base": 125.0, "bull": 170.0, "p_bear": 0.2, "p_base": 0.55, "p_bull": 0.25, "kill": ["margin below 10%"], "kill_level": 80.0,
            "checklist": list(dsc.CHECKLIST_KEYS), "desk_run": "x", "position_shares": 100,
            "premortem": ["Fictional reason one", "Fictional reason two", "Fictional reason three"]}
    return base | kw


def _ctx(rows, **kw):
    return ch.Ctx(rows=rows, table=pd.DataFrame(), today=pd.Timestamp("2026-11-10"), sizing={"paper_capital": 1e5, "max_loss": 2e3}, **kw)


def test_thirty_rules_each_with_a_source_and_a_proposal():
    assert len(ch.RULES) == 30 and len({r.id for r in ch.RULES}) == 30
    assert all(r.source and r.measure and r.proposal and r.effect and r.effort in ("S", "M", "L") and r.better in ("high", "low") for r in ch.RULES)


def test_a_disciplined_book_passes_the_view_rules_and_a_thin_one_says_so():
    good = ch.evaluate(_ctx([_v(1), _v(2, code="C2")]))
    st = {r["id"]: r["status"] for r in good}
    for rid in ("R01", "R02", "R09", "R10", "R11", "R12", "R15", "R19", "R24", "R27"):
        assert st[rid] == "ok", rid
    assert st["R03"] == "ikke målt" and st["R30"] == "brudd"                               # no final calls: Brier not measured, sample too small
    bad = dict(p_bear=0.25, p_base=0.5, p_bull=0.25, premortem=None, checklist=None, desk_run=None, kill=["margin falls"], kill_level=None)
    sloppy = ch.evaluate(_ctx([_v(1, **bad), _v(2, code="C2", **bad)]))
    st = {r["id"]: r for r in sloppy}
    for rid in ("R01", "R02", "R09", "R11", "R12", "R19", "R27"):
        assert st[rid]["status"] == "brudd", rid
    assert st["R15"]["value"] < dsc.GOOD_PROCESS
    assert {r["id"]: r["status"] for r in ch.evaluate(_ctx([_v(1, **bad)]))}["R02"] == "for lite data"   # one view is too few for R02
    nosize = {r["id"]: r["status"] for r in ch.evaluate(ch.Ctx(rows=[_v(1)], table=pd.DataFrame(), today=pd.Timestamp("2026-11-10"), sizing=None))}
    assert nosize["R24"] == "brudd"


def test_proposals_are_ranked_and_learn_from_rejections(tmp_path):
    rows = [_v(1, p_bear=0.25, p_base=0.5, p_bull=0.25, premortem=None, checklist=None, desk_run=None, kill=["margin falls"], kill_level=None)]
    res = ch.evaluate(_ctx(rows))
    p = ch.proposals(res, [])
    ids = [x["id"] for x in p["live"]]
    assert "R12:1" in ids and all(x["score"] > 0 for x in p["live"]) and ids == [x["id"] for x in sorted(p["live"], key=lambda x: -x["score"])]
    log = tmp_path / "decisions.jsonl"
    with pytest.raises(ValueError, match="give a reason"):
        ch.decide("R12:1", "avvist", "", "uenig", 0.0, path=log)
    with pytest.raises(ValueError, match="a rejection says why"):
        ch.decide("R12:1", "avvist", "not now please", None, 0.0, path=log)
    ch.decide("R12:1", "avvist", "Fictional: thresholds come later", "ikke nå", 0.0, path=log)
    ch.decide("R27:1", "godkjent", "Fictional: yes, build it", None, 0.0, path=log)
    ch.decide("R09:1", "avvist", "Fictional: not for me", "aldri", 0.0, path=log)
    d = ch.read_decisions(log)
    p2 = ch.proposals(res, d)
    live = [x["id"] for x in p2["live"]]
    assert "R12:1" not in live and "R27:1" not in live and "R09:1" not in live
    assert [b["id"] for b in p2["backlog"]] == ["R27:1"] and {h["id"] for h in p2["held"]} == {"R12:1", "R09:1"}
    # the evidence changes: R12 measured at 0.5 when rejected, now 0.0 – it comes back, with half the weight
    d[0]["metric_at"] = 0.5
    p3 = ch.proposals(res, d)
    back = next(x for x in p3["live"] if x["id"] == "R12:1")
    before = next(x for x in p["live"] if x["id"] == "R12:1")
    assert back["returned"] and back["score"] == pytest.approx(before["score"] * 0.5)
    d[2]["metric_at"] = 0.9                                                                # «aldri» stays away whatever happens
    assert "R09:1" not in [x["id"] for x in ch.proposals(res, d)["live"]]


def test_a_failing_rule_is_reported_not_hidden():
    def boom(c):
        raise RuntimeError("fictional failure")
    orig = ch.RULES[0].fn
    ch.RULES[0].fn = boom
    try:
        res = ch.evaluate(_ctx([_v(1)]))
        assert res[0]["status"] == "feil" and "fictional failure" in res[0]["error"]
    finally:
        ch.RULES[0].fn = orig


def test_the_page_the_decision_route_and_the_weekly_run(app, monkeypatch):  # noqa: F811
    client, _ = app
    assert client.post("/stock/AAA/judge", data=GOOD).status_code == 303
    page = client.get("/chief").get_data(as_text=True)
    assert "Analysesjefen" in page and "De 30 reglene" in page and "beregnet nå, ikke lagret" in page and ">Analysesjef</a>" in page
    assert 'action="/chief/decide"' in page
    r = client.post("/chief/decide", data={"proposal": "R24:1", "decision": "avvist", "reason": "Fictional: later", "reason_kind": "ikke nå", "metric_at": "0"})
    assert r.status_code == 200 and "R24:1: avvist" in r.get_data(as_text=True) and ch.read_decisions()[-1]["proposal"] == "R24:1"
    assert client.post("/chief/decide", data={"proposal": "R99:1", "decision": "godkjent", "reason": "Fictional"}).status_code == 400
    doc = ch.run(ch.build_ctx())
    p = ch.write_run(doc)
    assert p.exists() and p.parent.name == "chief" and len(doc["results"]) == 30
    assert "beregnet nå" not in client.get("/chief").get_data(as_text=True)                  # today's stored run is shown
