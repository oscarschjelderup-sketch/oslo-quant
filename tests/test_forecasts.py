"""Quarterly forecasts (D52): an 80 % interval logged before the next report, one per number, answered by the report
reader's printed figure of the same name, and the share inside the interval counted. Temporary home, fictional
report readings only."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant.dashboard import forecasts as fc

from .test_dashboard import app  # noqa: F401  (fixture)

REPORT = {"date": "2026-12-01", "what": "Q4 report", "source": "research book"}


def test_the_stock_page_asks_for_a_forecast_before_the_report_and_keeps_one_per_number(app, monkeypatch):  # noqa: F811
    client, _ = app
    soon = {**REPORT, "date": f"{pd.Timestamp.now().normalize() + pd.Timedelta(days=20):%Y-%m-%d}"}     # always ahead of the test's today
    monkeypatch.setattr(fc, "upcoming", lambda code, cases, today: soon if code == "AAA" else None)
    page = client.get("/stock/AAA").get_data(as_text=True)
    assert "Prognose for neste rapport" in page and "Q4 report" in page and 'action="/stock/AAA/forecast"' in page
    base = {"report_date": soon["date"], "report_what": soon["what"], "report_source": soon["source"], "metric": "revenue"}
    assert client.post("/stock/AAA/forecast", data=base | {"low": "120", "mid": "100", "high": "130"}).status_code == 400
    assert client.post("/stock/AAA/forecast", data=base | {"low": "100", "mid": "100", "high": "100"}).status_code == 400
    assert client.post("/stock/AAA/forecast", data=base | {"low": "90", "mid": "100", "high": "112"}).status_code == 303
    row = jg.read_log()[-1]
    assert row["kind"] == "forecast" and row["metric"] == "revenue" and row["interval"] == 0.8 and row["report"]["date"] == soon["date"] and jg.verify().ok
    r = client.post("/stock/AAA/forecast", data=base | {"low": "91", "mid": "100", "high": "112"})
    assert r.status_code == 400 and "already forecast" in r.get_data(as_text=True)
    assert "90 – <b>100</b> – 112" in client.get("/stock/AAA").get_data(as_text=True)


def test_upcoming_reads_the_calendar_within_60_days(home):
    class C:
        code, name, events = "AAA", "Alpha", [{"date": "2026-12-01", "what": "Q4 report"}]
    assert fc.upcoming("AAA", [C()], pd.Timestamp("2026-11-05"))["date"] == "2026-12-01"
    assert fc.upcoming("AAA", [C()], pd.Timestamp("2026-09-01")) is None                    # more than 60 days ahead


def test_a_forecast_after_the_report_date_is_refused():
    p = fc.form_problems({"metric": "revenue", "low": "1", "mid": "2", "high": "3"}, fc.METRICS, REPORT, pd.Timestamp("2026-12-01"))
    assert p == ["a forecast must be written before the report date"]
    assert "no upcoming report" in fc.form_problems({"metric": "revenue", "low": "1", "mid": "2", "high": "3"}, fc.METRICS, None, pd.Timestamp("2026-11-01"))[0]
    assert "metric must be one of" in fc.form_problems({"metric": "eps", "low": "1", "mid": "2", "high": "3"}, fc.METRICS, REPORT, pd.Timestamp("2026-11-01"))[0]


def test_the_answer_comes_from_the_reading_and_coverage_is_counted(home):
    jg.append("forecast", dict(code="AAA", date="2026-11-05", report=REPORT, metric="revenue", label="omsetning", low=90.0, mid=100.0, high=112.0, interval=0.8))
    jg.append("forecast", dict(code="AAA", date="2026-11-05", report=REPORT, metric="ebitda", label="EBITDA", low=10.0, mid=12.0, high=14.0, interval=0.8))
    jg.append("forecast", dict(code="AAA", date="2026-11-05", report=REPORT, metric="ebit", label="EBIT", low=5.0, mid=6.0, high=7.0, interval=0.8))
    d = jg.home() / "reports" / "AAA"
    d.mkdir(parents=True)
    (d / "1.summary.json").write_text(json.dumps({"published": "2026-12-01T06:00:00Z", "title": "Fictional Q4", "url": "u",
                                                   "figures": {"revenue": {"value": 108.0}, "ebitda": {"value": 15.5}}}), encoding="utf-8")
    old = jg.home() / "reports" / "AAA" / "0.summary.json"                                  # a reading before the forecast does not answer it
    old.write_text(json.dumps({"published": "2026-08-20T06:00:00Z", "figures": {"revenue": {"value": 50.0}, "ebit": {"value": 1.0}}}), encoding="utf-8")
    sc = fc.scoring(jg.read_log())
    by = {x["metric"]: x for x in sc["rows"]}
    assert by["revenue"]["answer"]["inside"] and by["revenue"]["answer"]["miss"] == pytest.approx(0.08)
    assert by["ebitda"]["answer"]["inside"] is False and by["ebit"]["answer"] is None          # EBIT not printed: unanswered, not guessed
    assert sc["n"] == 3 and sc["answered"] == 2 and sc["coverage"] == 0.5 and not sc["enough"]
    html = fc.calibration_html(sc)
    assert "50 %</b> innenfor" in html and "færre enn 10 svar" in html and "ikke avgjort ennå" in html
