"""The after-report loop (D39): the newest report is found from the files, the queue says who owes a view, the loop
rebuilds the light case with before/after and reads the report or writes a suggested spec – with NewsWeb and Yahoo
replaced by canned data in a temporary home."""

from __future__ import annotations

import json

import pandas as pd

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import afterreport as ar
from osloquant.dashboard import book as bk
from osloquant.dashboard import coverage as cv
from osloquant.dashboard import lightcase as lcm
from osloquant.dashboard import reports as rp
from osloquant.dashboard import today as td

from .test_coverage import VIEW, _lightcase_fixture
from .test_dashboard import _snapshot, app  # noqa: F401  (fixture)
from .test_rapporter import PDF


def _light(code, built, price=100.0, ebit=40.0, g=0.01, through="2026-06-30", write=True):
    lcm.case_dir().mkdir(parents=True, exist_ok=True)
    lc = {**_lightcase_fixture(), "code": code, "built_at": f"{built}T10:00:00Z", "price": {"value": price, "date": built, "source": "test"},
          "profit": {"revenue": {"value": 500.0, "period": "LTM"}, "ebit": {"value": ebit, "period": "LTM"}, "net_income": {"value": 25.0, "period": "LTM"},
                     "fcf": {"value": 20.0, "period": "LTM"}},
          "multiples": {"ev_ebit": 10.0, "pe": 15.0}, "reverse": {"model": "value driver", "wacc_est": 0.09, "implied_g": g, "ev_vs_no_growth": 0.1, "reads": "test"},
          "quarters_through": through, "warnings": []}
    if write:
        lcm.case_path(code).write_text(json.dumps(lc), encoding="utf-8")
    return lc


def _newsweb_message(code, mid, title, published):
    d = rp.report_dir(code)
    (d / f"{mid}.json").write_text(json.dumps({"data": {"message": {"messageId": mid, "title": title, "publishedTime": published,
                                                                     "attachments": [{"id": 1, "name": "Q3 report.pdf"}]}}}), encoding="utf-8")
    (d / f"{mid}.pdf").write_bytes(PDF)


def test_newest_report_comes_from_the_newest_of_four_sources_and_the_queue_names_who_owes(home):
    today = pd.Timestamp("2026-11-03")
    sg.book_path().write_text("entries:\n  - code: AAA\n    name: Alpha\n    events:\n      - {date: 2026-10-20, what: Q3 2026 report}\n"
                              "  - code: BBB\n    name: Beta\n    events: []\n", encoding="utf-8")
    jg.append("judgement", dict(code="AAA", name="Alpha", date="2026-10-01", price=100.0, rating="BUY", target=120.0, horizon_months=12))
    bk.log_claude_view("AAA", "Alpha", VIEW, 100.0, "2026-10-25", "test", today="2026-10-25")       # Claude re-logged after the report
    bk.log_claude_view("BBB", "Beta", VIEW, 100.0, "2026-10-01", "test", today="2026-10-01")
    _light("AAA", "2026-10-10")
    _light("BBB", "2026-11-01")
    _newsweb_message("BBB", 777, "Beta – Q3 2026 results", "2026-10-28T07:00:00")
    cases = bk.cases()
    by = {c.code: c for c in cases}
    assert ar.newest_report(by["AAA"], today) == {"date": "2026-10-20", "what": "Q3 2026 report", "source": "research book"}
    assert ar.newest_report(by["BBB"], today) == {"date": "2026-10-28", "what": "Beta – Q3 2026 results", "source": "NewsWeb message 777"}
    cal = {"companies": {"BBB": {"events": [{"date": "2026-10-30", "what": "Q3 2026 report presentation"}]}}}
    assert ar.newest_report(by["BBB"], today, cal)["source"] == "financial calendar on NewsWeb"
    assert ar.newest_report(None, today, code="CCC") is None
    uni = cv.universe(_snapshot(), cases, [], today, plan_entries={})
    q = {it["code"]: it for it in ar.due(cases, uni, today)}
    assert q["AAA"]["owes"] == ["oscar"] and q["AAA"]["lightcase_stale"] and q["AAA"]["ran"] is None       # Oscar's view 1 Oct predates 20 Oct; Claude's does not
    assert q["BBB"]["owes"] == ["claude"] and not q["BBB"]["lightcase_stale"]
    # the downloaded report counts for Oscar's front-page rule too (D29)
    assert td.last_report(by["BBB"], today) == (pd.Timestamp("2026-10-28"), "Beta – Q3 2026 results")
    html = ar.queue_html(list(q.values()), today)
    assert "Alpha" in html and "du" in html and "Claude" in html and "ikke kjørt" in html and "(før rapporten)" in html
    assert "Ingen dekkede selskaper" in ar.queue_html([], today)


def test_diff_and_snapshot():
    b = _light("AAA", "2026-10-10", price=100.0, ebit=40.0, g=0.01)
    a = _light("AAA", "2026-11-03", price=110.0, ebit=44.0, g=0.03, through="2026-09-30")
    d = ar.diff(b, a)
    assert abs(d["price"]["change"] - 0.1) < 1e-12 and abs(d["ebit"]["change"] - 0.1) < 1e-12 and abs(d["implied_g"]["change"] - 0.02) < 1e-12
    assert d["quarters_through"]["change"] == "2026-06-30 → 2026-09-30" and d["pe"]["change"] == 0.0
    assert ar.snapshot(None) == {k: None for k, _ in ar.DIFF_FIELDS}


def test_run_one_rebuilds_reads_or_suggests_and_the_stock_page_shows_it(app, monkeypatch, tmp_path):  # noqa: F811
    client, snap = app
    today = pd.Timestamp("2026-11-03")
    before = _light("BBB", "2026-10-10", price=90.0, ebit=40.0)
    after = {**_light("BBB", "2026-11-03", price=100.0, ebit=44.0, through="2026-09-30", write=False), "warnings": ["a warning from the build"]}
    monkeypatch.setattr(lcm, "build", lambda code, snap=None, **kw: after)
    monkeypatch.setattr(rp, "find_reports", lambda code, since, until=None: [{"messageId": 555, "title": "Beta Q3 2026 report", "publishedTime": "2026-10-28T07:00:00"}])

    def fake_download(code, mid):
        _newsweb_message(code, mid, "Beta Q3 2026 report", "2026-10-28T07:00:00")
        return rp.report_dir(code) / f"{mid}.pdf", {"title": "Beta Q3 2026 report", "publishedTime": "2026-10-28T07:00:00"}

    monkeypatch.setattr(rp, "download", fake_download)
    dry = {"found": {"revenue": {"value": 500.0, "page": 3, "checked": "matches the printed change"}}, "missing": ["ebitda", "ebit", "net_debt", "pl_revenue", "pl_ebit"],
           "candidates": {"ebit": ["p.4: Operating profit before other items 44 40 10 %"]}, "income_statement_header": None, "metrics": {"revenue": 500.0}}
    monkeypatch.setattr(rp, "dry_run", lambda pdf, spec, year=None, q=None: dry)
    log = ar.run_one("BBB", None, snap, refresh=False, today=today)
    assert log["report"]["message_id"] == 555 and log["lightcase"]["diff"]["price"]["change"] - (100 / 90 - 1) < 1e-12
    assert log["reader"]["mode"] == "dry-run" and log["reader"]["found"] == {"revenue": 500.0}
    spec = ar.spec_text("BBB")
    assert spec.startswith("# Suggested reader spec for BBB") and "revenue:" in spec and "# ebit:" in spec and "Operating profit before other items" in spec
    assert ar.load("BBB")["steps"][0] == "light case rebuilt"
    page = client.get("/stock/BBB").get_data(as_text=True)
    assert "Etter rapporten" in page and "Beta Q3 2026 report" in page and "90,00" in page and "100,00" in page and "+11,1\N{NO-BREAK SPACE}%" in page
    assert "Ingen leserspesifikasjon" in page and "a warning from the build" in page and "/report/BBB/555.pdf" in page
    # with a spec the reader runs instead of the dry run
    rp.spec_path().write_text("BBB:\n  key: {revenue: 'Revenue'}\n", encoding="utf-8")
    monkeypatch.setattr(rp, "run", lambda code, model, kill, days=400, force=False: [{"ok": 1}])
    monkeypatch.setattr(rp, "latest", lambda code: {"published": "2026-10-28T07:00:00", "year": 2026, "quarter": 3, "kill": [{"criterion": "margin below 10%", "status": "intact"}]})
    log = ar.run_one("BBB", None, snap, refresh=False, today=today)
    assert log["reader"] == {"mode": "spec", "new": 1, "kill": [{"criterion": "margin below 10%", "status": "intact"}]}
    assert "Rapportleseren: margin below 10 %: intact" in client.get("/stock/BBB").get_data(as_text=True)
    # a failing build is written down, not raised
    monkeypatch.setattr(lcm, "build", lambda code, snap=None, **kw: (_ for _ in ()).throw(ValueError("no statements")))
    log = ar.run_one("BBB", None, snap, refresh=False, today=today)
    assert log["lightcase"]["error"] == "no statements" and log["steps"][0].startswith("light case not rebuilt")
    assert before["price"]["value"] == 90.0


def test_coverage_page_carries_the_queue(app):  # noqa: F811
    client, snap = app
    bk.log_claude_view("BBB", "Beta Shipping", VIEW, 100.0, "2026-10-01", "test", today="2026-10-01")
    _light("BBB", "2026-10-01")
    _newsweb_message("BBB", 778, "Beta Q3 2026 report", "2026-10-28T07:00:00")
    page = client.get("/coverage").get_data(as_text=True)
    assert "Etter rapport – til ny vurdering" in page and "Beta Shipping" in page and "NewsWeb message 778" in page
