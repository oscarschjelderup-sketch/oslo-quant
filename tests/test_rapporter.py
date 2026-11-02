"""Reports on the stock page, the pre-trade page, the learning blocks and the case health – all on fictional data in a
temporary home (never the real research book or judgement log)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import datahealth as dh
from osloquant.dashboard import learn, server
from osloquant.dashboard import market as mk
from osloquant.dashboard import pretrade as pt
from osloquant.dashboard import reportpdf as rpdf
from osloquant.dashboard import today as td

from .helpers import business_days

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n160\n%%EOF\n"
GOOD = {"rating": "BUY", "target": "130", "rationale": "Margins recover as the price increases stick; cheap on 2027.",
        "kill": "Gross margin below 40%\nNet debt above 3x EBITDA", "bear": "80", "base": "125", "bull": "160",
        "p_bear": "0.25", "p_base": "0.5", "p_bull": "0.25", "horizon": "12", "kill_level": "85"}


def _snapshot(n=300, start="2025-08-01") -> mk.Snapshot:
    rng = np.random.default_rng(0)
    dates = business_days(n, start)
    close = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n))) for c in ("AAA", "BBB")}, index=dates)
    panel = dict(open=close.shift(1).fillna(close), high=close * 1.01, low=close * 0.99, close=close, volume=pd.DataFrame(1000.0, index=dates, columns=close.columns))
    return mk.Snapshot(panel, {"AAA": "Alpha", "BBB": "Beta"}, {"AAA": "Seafood", "BBB": "Seafood"}, dates[-1])


def _estimates(date, tp, rating, price, dcf, rev):
    return {"date": date, "price": price, "price_date": date, "tp": tp, "rating": rating, "dcf_ps": dcf, "years": [2026, 2027, 2028],
            "rows": {"rev": rev, "ebitdaal": [r * 0.2 for r in rev], "ebit_adj": [r * 0.15 for r in rev], "eps": [r / 1000 for r in rev]}}


def _publish(tmp_path, code, date, tp, rating, price, dcf, rev, kind="Update"):
    pdf = tmp_path / f"{code}_Research_Report_{date}.pdf"
    pdf.write_bytes(PDF)
    est = tmp_path / f"est_{code}_{date}.json"
    est.write_text(json.dumps(_estimates(date, tp, rating, price, dcf, rev)), encoding="utf-8")
    return rpdf.publish(code, pdf, est, {"kind": kind, "title": "t", "pages": 1, "gate_ok": True, "built": date})


@pytest.fixture
def app(monkeypatch, home):
    snap = _snapshot()
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    sg.book_path().write_text(
        "entries:\n  - code: AAA\n    name: Alpha\n    rating: BUY\n    valuation_date: 2026-01-05\n    price_at_valuation: 100\n"
        "    target: 120\n    bear: 70\n    bull: 150\n    events:\n      - {date: 2026-12-01, what: Q4 report}\n"
        "    kill:\n      - margin below 10%\n", encoding="utf-8")
    a = server.create_app()
    a.testing = True
    return a.test_client(), snap


# ------------------------------------------------------------------------------------------------ part 1: reports
def test_reports_are_listed_with_revision_and_served(app, home, tmp_path):
    client, _ = app
    assert rpdf.entries("AAA") == []
    _publish(tmp_path, "AAA", "2026-10-07", 54, "BUY", 39.75, 50.7, [5665, 5952, 6301])
    _publish(tmp_path, "AAA", "2026-11-02", 58, "BUY", 43.95, 54.4, [5714, 6004, 6357])
    ents = rpdf.entries("AAA")
    assert [e["date"] for e in ents] == ["2026-11-02", "2026-10-07"] and ents[0]["tp"] == 58 and ents[0]["pages"] == 1
    rev = rpdf.revision(ents)
    assert rev["tp"] == (54, 58) and rev["rows"][0]["label"] == "Revenue" and rev["rows"][0]["chg"] == pytest.approx(5714 / 5665 - 1)
    page = client.get("/stock/AAA").get_data(as_text=True)
    assert "Rapporter" in page and "/reports/AAA/AAA_Research_Report_2026-11-02.pdf" in page and "Siste estimat mot forrige" in page
    r = client.get("/reports/AAA/AAA_Research_Report_2026-11-02.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert client.get("/reports/AAA/../judgements.jsonl").status_code in (404, 400)
    assert client.get("/reports/AAA/nope.pdf").status_code == 404
    with pytest.raises(ValueError):
        rpdf.publish("AAA", tmp_path / "wrong.pdf")


def test_a_report_target_that_differs_from_the_view_asks_for_a_decision(app, home, tmp_path):
    client, _ = app
    view = {"date": "2026-01-05", "target": 120, "rating": "BUY"}
    assert rpdf.tp_mismatch(None, view) is None
    _publish(tmp_path, "AAA", "2026-10-31", 120.2, "BUY", 100, 110, [1, 2, 3])           # same target within tolerance
    assert rpdf.tp_mismatch(rpdf.latest("AAA"), view) is None
    _publish(tmp_path, "AAA", "2026-11-01", 135, "BUY", 100, 125, [1, 2, 3])
    m = rpdf.tp_mismatch(rpdf.latest("AAA"), view)
    assert m and m["report_tp"] == 135 and m["diff"] == pytest.approx(0.125)
    items = td.report_tp_items(bk.cases(), pd.Timestamp("2026-11-04"))
    assert len(items) == 1 and items[0].kind == "report-tp" and "135" in items[0].title
    front = client.get("/").get_data(as_text=True)
    assert "rapporten av 2026-11-01" in front
    stock = client.get("/stock/AAA").get_data(as_text=True)
    assert "har kursmål 135" in stock
    # a judgement logged after the report settles it, whatever the target
    assert client.post("/stock/AAA/judge", data=GOOD).status_code == 303
    assert rpdf.tp_mismatch(rpdf.latest("AAA"), bk.case("AAA").view, bk.case("AAA").history) is None
    assert td.report_tp_items(bk.cases(), pd.Timestamp("2026-11-04")) == []
    # a report older than the view never nags
    assert rpdf.tp_mismatch({"date": "2025-01-01", "tp": 999, "rating": "SELL", "file": "x", "url": "y"}, view) is None


# ------------------------------------------------------------------------------------------------ part 2: before you buy
def test_pretrade_page_collects_the_decision_inputs_and_the_checklist_reaches_the_row(app, home, tmp_path):
    client, _ = app
    (jg.home() / "dashboard.yaml").write_text("sizing:\n  paper_capital: 100000\n  max_loss: 2000\n  max_position: 0.25\n", encoding="utf-8")
    r = client.get("/stock/AAA/pretrade")
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    for s in ("1. Hva markedet priser inn", "2. Utfallsodds", "3. Bull og bear", "4. Hendelser før horisonten", "5. Posisjonsstørrelse", "6. Sjekkliste"):
        assert s in page, s
    assert "Q4 report" in page and "Bear-verdi 70" in page and 'data-key="read_report"' in page
    assert "Kryss av alt over" in page and "Største tillatte posisjon" in page     # bear value 70 is the kill level: a size is computed
    ctx = pt.context("AAA")
    assert ctx["position"]["kill"] == 70 and ctx["position"]["size"].shares > 0
    assert any(a["source"].startswith("din vurdering") for a in ctx["against"])
    assert client.get("/stock/BBB/pretrade").status_code == 200                      # no case: still renders, says what is missing
    assert "Ingen vurdering" in client.get("/stock/BBB/pretrade").get_data(as_text=True)
    # the stock page carries the ticks into the form and the row records them
    stock = client.get("/stock/AAA?checklist=read_report,knows_kill,new_argument,seen_implied").get_data(as_text=True)
    assert 'name="checklist" value="read_report,knows_kill,new_argument,seen_implied"' in stock and "Sjekklisten fra" in stock
    assert client.post("/stock/AAA/judge", data={**GOOD, "checklist": "read_report,knows_kill,new_argument,seen_implied"}).status_code == 303
    (row,) = jg.read_log()
    assert row["checklist"] == ["read_report", "knows_kill", "new_argument", "seen_implied"] and jg.verify().ok
    assert client.post("/stock/AAA/judge", data={**GOOD, "checklist": ""}).status_code == 303
    assert "checklist" not in jg.read_log()[-1]                                      # no ticks: nothing invented on the row
    assert "Før du kjøper" in client.get("/stock/AAA").get_data(as_text=True)


def test_arguments_against_come_from_sources_in_strength_order():
    c = bk.Case("AAA", "Alpha", {"date": "2026-01-05", "target": 120, "bear": 70, "p_bear": 0.25, "rating": "BUY"}, "log #1",
                claude_view={"date": "2026-02-01", "target": 100, "rating": "HOLD", "thesis": "Growth is priced."})
    rep = {"summary": {"quarter": 3, "year": 2026, "published": "2026-10-27T07:00:00Z",
                       "kill": [{"criterion": "margin below 10%", "status": "triggered", "now": 0.08, "threshold": 0.10},
                                {"criterion": "leverage above 3x", "status": "intact, nearer", "now": 2.8, "threshold": 3.0}]}}
    lc = {"built_at": "2026-10-30T10:00:00", "reverse": {"reads": "the price implies 4 % growth for ever"}, "warnings": ["net debt missing"]}
    args = pt.arguments_against(c, lc, rep, [], 100.0)
    assert [a["rank"] for a in args] == sorted(a["rank"] for a in args)
    assert args[0]["text"].startswith("margin below 10%: triggered") and "rapportleseren" in args[0]["source"]
    assert any("Claudes syn HOLD" in a["text"] for a in args) and any("4 % growth" in a["text"] for a in args)
    assert args[-1]["source"].startswith("din vurdering")


# ------------------------------------------------------------------------------------------------ part 3: learning
def _prices(closes: dict, start="2025-01-01"):
    dates = pd.bdate_range(start, periods=len(next(iter(closes.values()))))
    adj = pd.DataFrame(closes, index=dates)
    return jg.Prices(adj, adj.copy(), pd.Series(np.full(len(dates), 1000.0), index=dates))


def test_error_patterns_and_per_case_brier(tmp_path):
    path = tmp_path / "log.jsonl"
    # AAA: a BUY that fell 20 % first, crossed the kill level with no check, and ended below the price – wrong, early, late out
    aaa = np.r_[np.linspace(100, 78, 60), np.linspace(78, 90, 200)]
    # BBB: a BUY that went straight to the target – right; the rationale leans on guidance
    bbb = np.linspace(100, 140, 260)
    prices = _prices({"AAA": aaa, "BBB": bbb}, start="2025-01-02")
    jg.append("judgement", dict(code="AAA", date="2025-01-02", price=100.0, rating="BUY", target=130.0, horizon_months=6, kill_level=85.0,
                                bear=70.0, base=125.0, bull=160.0, p_bear=0.2, p_base=0.5, p_bull=0.3, kill=["x"], thesis="Cheap on cash flow."), path)
    jg.append("judgement", dict(code="BBB", date="2025-01-02", price=100.0, rating="BUY", target=130.0, horizon_months=6, bear=80.0, base=125.0, bull=160.0,
                                p_bear=0.25, p_base=0.5, p_bull=0.25, kill=["y"], thesis="Management guidance of 20% growth is credible.", consensus_target=128.0), path)
    jg.append("kill_check", dict(code="BBB", date="2025-03-03", criterion="y", breached=False, action="none"), path)
    rows = jg.read_log(path)
    table, summary = jg.calibration(rows, prices=prices, asof=pd.Timestamp("2025-12-31"))
    assert set(table["status"]) == {"final"}
    rel = jg.reliability(rows, table=table, prices=prices)
    bc = learn.by_case(table, rel)
    assert [r["code"] for r in bc] == ["AAA", "BBB"] and bc[0]["n_final"] == 1 and bc[0]["brier"] is not None
    assert bc[1]["direction_hit"] == 1.0 and bc[0]["direction_hit"] == 0.0
    ep = learn.error_patterns(rows, table, prices)
    assert ep["n"] == 2 and ep["n_wrong"] == 1
    a = next(r for r in ep["rows"] if r["code"] == "AAA")
    assert a["wrong"] and {"early", "late_out", "no_kill_check"} <= set(a["patterns"])
    b = next(r for r in ep["rows"] if r["code"] == "BBB")
    assert not b["wrong"] and set(b["patterns"]) == {"guidance", "consensus"}
    assert ep["counts"]["early"] == {"all": 1, "wrong": 1} and ep["counts"]["guidance"]["wrong"] == 0
    html = learn.by_case_html(bc) + learn.patterns_html(ep)
    assert "Brier" in html and "for tidlig inn" in html and "1 feil av 2" in html
    assert "Ingen vurdering er scoret" in learn.patterns_html({"n": 0})


def test_calibration_page_shows_the_learning_blocks(app):
    client, _ = app
    assert client.post("/stock/AAA/judge", data=GOOD).status_code == 303
    page = client.get("/calibration").get_data(as_text=True)
    assert "Feilmønster" in page and page.count("Kalibrering") >= 1


# ------------------------------------------------------------------------------------------------ part 4: data health
def test_case_health_names_the_disagreements_between_sources(app, home, tmp_path, monkeypatch):
    client, snap = app
    from osloquant.dashboard import odds as od

    monkeypatch.setattr(od, "long_closes", lambda: snap.panel["close"])
    today = pd.Timestamp("2026-11-04")
    _publish(tmp_path, "AAA", "2026-11-03", 135, "BUY", 100, 125, [1, 2, 3])
    closes = snap.panel["close"]
    (jg.home() / "cases").mkdir(exist_ok=True)
    (jg.home() / "cases" / "AAA.json").write_text(json.dumps({"code": "AAA", "built_at": "2026-10-01T10:00:00", "price": float(closes["AAA"].iloc[-1]) * 0.8,
                                                              "reverse": {}, "warnings": []}), encoding="utf-8")
    rows = dh.case_health(bk.cases(), closes, today)
    (r,) = rows
    issues = " | ".join(r["issues"])
    assert "synet er" in issues and "lett case bygget på kurs" in issues and "rapporten 2026-11-03 sier kursmål 135" in issues
    assert "ingen kommende dato" not in issues           # the book has a Q4 report date
    # price reconciliation: the yaml view says 100 on 2026-01-05 – the synthetic close that day is something else
    assert ("synet er logget til kurs 100.00" in issues) == (abs(float(closes["AAA"][closes.index <= "2026-01-05"].iloc[-1]) / 100 - 1) > 0.01)
    ov = dh.overview(closes, bk.cases(), closes.index[-1])
    probs = dh.problems(ov)
    assert any(p.startswith("AAA: rapporten 2026-11-03") for p in probs)
    page = client.get("/health").get_data(as_text=True)
    assert "Caser: alder og avvik mellom kilder" in page and "kursmål 135" in page
