"""The coverage universe (D38): the level is derived from the files, the plan is typed in, the page shows both and the
gap between them. Synthetic store and a temporary home only."""

from __future__ import annotations

import json

import pandas as pd
import pytest
import yaml

from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import coverage as cv
from osloquant.dashboard import lightcase as lcm
from osloquant.dashboard import render as rd
from osloquant.dashboard import reportpdf as rpdf

from .test_coverage import VIEW
from .test_dashboard import _snapshot, app  # noqa: F401  (fixture)
from .test_rapporter import PDF


def _light(code, built="2026-10-01"):
    lcm.case_dir().mkdir(parents=True, exist_ok=True)
    lcm.case_path(code).write_text(json.dumps({"code": code, "built_at": f"{built}T10:00:00Z", "price": {"value": 100.0, "date": built},
                                                "reverse": {"model": "value driver", "implied_g": 0.01, "ev_vs_no_growth": 0.1}, "financial": False}), encoding="utf-8")


def _report(tmp_path, code, date="2026-10-20"):
    pdf = tmp_path / f"{code}_Research_Report_{date}.pdf"
    pdf.write_bytes(PDF)
    est = tmp_path / f"est_{code}.json"
    est.write_text(json.dumps({"date": date, "tp": 130, "rating": "BUY", "price": 100.0}), encoding="utf-8")
    rpdf.publish(code, pdf, est, {"kind": "Initiation", "title": "t", "pages": 1, "gate_ok": True, "built": date})


def test_levels_are_derived_from_the_files_and_the_plan_names_the_gap(home, tmp_path):
    snap = _snapshot()
    today = pd.Timestamp("2026-11-03")
    sg.book_path().write_text("entries:\n  - code: AAA\n    name: Alpha\n    events: []\n", encoding="utf-8")
    _report(tmp_path, "AAA")                                  # a report published: full case, no view yet
    _light("BBB", built="2026-06-01")                         # a light case, old
    bk.log_claude_view("BBB", "Beta Shipping", VIEW, 100.0, "2026-11-02", "test", today="2026-11-02")
    bk.add_watch("CCC", "a bank to follow", today="2026-11-01")
    cv.set_plan("CCC", target="light", owner="claude", rhythm="report", note="fills the finance gap", today="2026-11-03")
    cv.set_plan("AAA", target="full", owner="oscar", today="2026-11-03")
    with pytest.raises(ValueError, match="target"):
        cv.set_plan("CCC", target="deep")
    with pytest.raises(ValueError, match="owner"):
        cv.set_plan("CCC", owner="robot")

    uni = {r["code"]: r for r in cv.universe(snap, bk.cases(), bk.watchlist(), today)}
    assert uni["AAA"]["level"] == "full" and uni["AAA"]["oscar"] is None and uni["AAA"]["report"]["tp"] == 130 and not uni["AAA"]["gap"]
    assert uni["BBB"]["level"] == "light" and uni["BBB"]["claude"]["rating"] == "BUY" and uni["BBB"]["lightcase_stale"]   # 155 days old
    assert uni["CCC"]["level"] == "watch" and uni["CCC"]["gap"] and uni["CCC"]["owner"] == "claude" and uni["CCC"]["rhythm"] == "report"
    # the plan file keeps both entries, the second call updated instead of duplicating
    doc = yaml.safe_load(cv.plan_path().read_text(encoding="utf-8"))
    assert [e["code"] for e in doc["entries"]] == ["CCC", "AAA"] and doc["entries"][0]["note"] == "fills the finance gap"
    s = {x["group"]: x for x in cv.summary(list(uni.values()))}
    assert s["Alle"]["n"] == 3 and s["Alle"]["full"] == 1 and s["Alle"]["light"] == 1 and s["Alle"]["watch"] == 1 and s["Alle"]["gap"] == 1
    assert s["Finance"]["watch"] == 1 and s["Seafood"]["full"] == 1 and s["Alle"]["stale"] == 1
    n = cv.counts(list(uni.values()))
    assert n == {"universe": 3, "full": 1, "light": 1, "watch": 1, "none": 0, "any_view": 1, "gap": 1}
    # a light case built before the newest report is stale even when young
    _light("AAA", built="2026-10-10")
    assert {r["code"]: r for r in cv.universe(snap, bk.cases(), bk.watchlist(), today)}["AAA"]["lightcase_stale"]


def test_a_company_in_the_store_with_nothing_is_level_none():
    snap = _snapshot()
    uni = cv.universe(snap, [], [], pd.Timestamp("2026-11-03"), plan_entries={})
    assert [r["level"] for r in uni] == ["none"] * 3 and [r["group"] for r in uni] == ["Shipping", "Seafood", "Finance"]   # GROUP_ORDER
    assert cv.summary(uni)[-1] == {"group": "Alle", "n": 3, "full": 0, "light": 0, "watch": 0, "none": 3, "oscar": 0, "claude": 0, "any_view": 0, "gap": 0, "stale": 0}


def test_coverage_page_shows_the_universe_and_the_front_page_counts_it(app, tmp_path):  # noqa: F811
    client, snap = app
    _report(tmp_path, "AAA")
    cv.set_plan("CCC", target="light", owner="claude", rhythm="monthly", note="bank", today="2026-11-03")
    page = client.get("/coverage").get_data(as_text=True)
    assert "3 selskaper i lageret" in page and "1 med full case" in page and "1 ligger under nivået planen sier" in page
    assert "Universet" in page and "lett case · claude · månedlig" in page and "under plan" in page and "Sektorgruppe" in page
    assert "Selskaper med et syn" in page and "Alpha" in page
    home_page = client.get("/").get_data(as_text=True)
    assert "universet 3 selskaper" not in home_page or "Dekning:" in home_page   # the line appears only once Claude has a view
    bk.log_claude_view("BBB", "Beta Shipping", VIEW, 100.0, "2026-11-02", "test")
    home_page = client.get("/").get_data(as_text=True)
    assert "universet 3 selskaper – 1 full case" in home_page and "1 under plan" in home_page
    # the old signature still renders (no universe given)
    assert "Universet" not in rd.coverage_page([], pd.Timestamp("2026-11-03"))
