"""The whole universe as light cases (D42) and what the price requires against the history (D43): the LTM from the year
and both year-to-dates when Yahoo drops a quarter, the quality grade, the average-margin reading, the batch build that
one bad company cannot stop, the screen's verdicts and candidates, and the pages. Fictional numbers only."""

from __future__ import annotations

import copy
import json

import pandas as pd
import pytest
from typer.testing import CliRunner

from osloquant.dashboard import lightcase as lcm
from osloquant.dashboard import market as mk
from osloquant.dashboard import screen as sc

from .test_coverage import _lightcase_fixture
from .test_dashboard import _snapshot, app  # noqa: F401  (fixture)


def _q(rows):
    return pd.DataFrame([{"report_date": pd.Timestamp(d), "total_revenue": v} for d, v in rows])


# ------------------------------------------------------------------------------------------------ LTM
def test_ltm_from_the_year_and_both_year_to_dates_when_a_quarter_is_missing():
    q = _q([("2025-03-31", 10.0), ("2025-06-30", 11.0), ("2025-12-31", 14.0), ("2026-03-31", 12.0), ("2026-06-30", 13.0)])   # Q3 2025 missing
    y = _q([("2024-12-31", 40.0), ("2025-12-31", 48.0)])
    assert lcm.ltm(q, "total_revenue") == (None, None)                                   # no four in a row, no year given
    v, label = lcm.ltm(q, "total_revenue", y)
    assert v == pytest.approx(48 + 12 + 13 - 10 - 11) and label.startswith("LTM to 2026-06-30") and "YTD" in label
    four = _q([("2025-09-30", 1.0), ("2025-12-31", 2.0), ("2026-03-31", 3.0), ("2026-06-30", 4.0)])
    assert lcm.ltm(four, "total_revenue", y) == (10.0, "LTM to 2026-06-30")              # four consecutive quarters win
    gap = _q([("2025-06-30", 11.0), ("2025-12-31", 14.0), ("2026-03-31", 12.0), ("2026-06-30", 13.0)])
    assert lcm.ltm(gap, "total_revenue", y) == (None, None)                              # Q1 2025 missing too: no prior YTD, no LTM
    closes = _q([("2025-03-31", 10.0), ("2025-06-30", 11.0), ("2025-12-31", 14.0)])
    assert lcm.ltm(closes, "total_revenue", y) == (48.0, "LTM to 2025-12-31")            # the newest quarter closes the year


# ------------------------------------------------------------------------------------------------ quality, history, normalised
def _case(**kw):
    c = copy.deepcopy(_lightcase_fixture())
    c["annual"].insert(0, {"year": 2023, "date": "2023-12-31", "revenue": 400e6, "ebit": 40e6, "net_income": 30e6, "fcf": 20e6, "net_debt": 130e6, "equity": 270e6})
    c["price"]["date"] = "2026-08-20"            # within 115 days of the quarters (2026-06-30)
    c["built_at"] = "2026-08-21T10:00:00Z"
    for k, v in kw.items():
        c[k] = v
    return c


def test_quality_grades_name_every_reason():
    a = lcm.quality(_case())
    assert a["grade"] == "A" and a["issues"] == [] and a["usable"] and any("cyclical" in n for n in a["notes"])   # Seafood
    fy = _case()
    fy["profit"]["ebit"]["period"] = "FY to 2025-12-31"
    b = lcm.quality(fy)
    assert b["grade"] == "B" and b["usable"] and "EBIT from the last full year" in b["issues"][0]
    old = lcm.quality(_case(price={"value": 100.0, "date": "2026-10-30", "source": "t"}, built_at="2026-10-31T10:00:00Z"))
    assert old["grade"] == "B" and "only to 2026-06-30" in old["issues"][0]
    assert lcm.quality(_case(shares=None))["grade"] == "C"
    stale = lcm.quality(_case(balance={"net_debt": 100e6, "equity": 300e6, "minority": 0, "date": "2023-12-31"}))
    assert stale["grade"] == "B" and "balance sheet (net debt, equity) is from 2023-12-31" in stale["issues"][0]
    nav = lcm.quality(_case(group="Investment companies"))
    assert nav["grade"] == "C" and not nav["usable"] and "NAV" in nav["issues"][0]
    dkk = lcm.quality(_case(currency={"reporting": "DKK", "fx": None, "fx_date": None, "source": "t"}))
    assert dkk["grade"] == "C" and "DKKNOK" in dkk["issues"][0]
    unknown = lcm.quality(_case(warnings=["reporting currency unknown – run oq case build with --refresh"]))
    assert unknown["grade"] == "C"
    # a case written before D42 with few fields still grades, it does not crash
    assert lcm.quality({"code": "X", "price": {"value": 1.0, "date": "2026-10-01"}, "financial": False})["grade"] == "C"


def test_history_and_the_average_margin_reading():
    c = _case()
    h = lcm.history(c)
    assert h["from"] == 2023 and h["to"] == 2025 and h["rev_cagr"] == pytest.approx((480 / 400) ** 0.5 - 1)
    margins = [40 / 400, 50 / 450, 55 / 480]
    assert h["margin_avg"] == pytest.approx(sum(margins) / 3) and h["margin_min"] == pytest.approx(0.1) and h["n_margins"] == 3
    n = lcm.normalised(c)
    nopat = sum(margins) / 3 * 500e6 * 0.78
    roic = nopat / (300e6 + 100e6)
    assert n["nopat"] == pytest.approx(nopat) and n["roic"] == pytest.approx(roic)
    assert n["implied_g"] is None and n["kind"] == "below_capital" and "2023–2025 average EBIT margin" in n["reads"]
    assert n["implied_roic_no_growth"] == pytest.approx(190.9e6 * 0.085 / (nopat / roic))
    hi = _case()
    hi["multiples"] = {**hi["multiples"], "ev": 600e6}
    assert lcm.normalised(hi)["implied_g"] == pytest.approx(lcm.implied_growth(600e6, nopat, roic, 0.085)) and lcm.normalised(hi)["kind"] == "grows"
    assert lcm.normalised(_case(financial=True)) is None and lcm.normalised(_case(group="Investment companies")) is None
    short = _case()
    short["annual"] = short["annual"][:2]
    assert lcm.normalised(short) is None                                                 # fewer than three years


# ------------------------------------------------------------------------------------------------ batch build
def test_build_all_isolates_a_broken_company_and_computes_the_medians_once(home, monkeypatch):
    snap = _snapshot()
    frames = {}

    def fr(code):
        if code == "BBB":
            raise RuntimeError("malformed statements")
        if code not in frames:
            q = pd.DataFrame([{"report_period": "quarter", "report_date": pd.Timestamp(d), "total_revenue": 100e6, "ebit": 10e6, "net_income": 7e6,
                               "pretax_income": 9e6, "tax_provision": 2e6, "free_cash_flow": 5e6} for d in ("2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30")])
            y = pd.DataFrame([{"report_period": "year", "report_date": pd.Timestamp(f"{yr}-12-31"), "total_revenue": 400e6, "ebit": 40e6, "net_income": 28e6,
                               "pretax_income": 36e6, "tax_provision": 8e6, "free_cash_flow": 20e6} for yr in (2023, 2024, 2025)])
            bal = pd.DataFrame([{"report_period": p, "report_date": pd.Timestamp("2026-06-30"), "net_debt": 50e6, "total_equity": 200e6,
                                 "minority_interest": 0.0, "shares_outstanding": 10e6} for p in ("quarter", "year")])
            frames[code] = (y, q, bal, y, q)
        return frames[code]
    monkeypatch.setattr(lcm, "_frames", fr)
    monkeypatch.setattr(lcm, "currencies", lambda: {"AAA": {"reporting": "NOK"}, "BBB": {"reporting": "NOK"}})
    res = lcm.build_all(snap)
    assert set(res["built"]) == {"AAA", "CCC"} and res["skipped"] == {"BBB": "RuntimeError: malformed statements"}
    assert lcm.case_path("AAA").exists() and not lcm.case_path("BBB").exists()
    assert res["built"]["AAA"]["peers"]["members"] == ["AAA"]                              # BBB failed; CCC's currency is unknown
    assert any("reporting currency unknown" in w for w in res["built"]["CCC"]["warnings"])
    again = lcm.build_all(snap, only_missing=True, write=False)
    assert set(again["built"]) == set() and "BBB" in again["skipped"]                     # only BBB was missing, and it still fails


def test_cli_case_build_needs_codes_or_all(home, monkeypatch):
    from osloquant import cli

    runner = CliRunner(env={"COLUMNS": "200"})
    snap = _snapshot()
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    monkeypatch.setattr(cli, "_setup", lambda *a, **k: None)
    r = runner.invoke(cli.app, ["case", "build"])
    assert r.exit_code != 0 and "--all" in r.output
    seen = {}
    monkeypatch.setattr(lcm, "build_all", lambda s, codes: seen.setdefault("codes", codes) and {"built": {"AAA": _case(code="AAA")}, "skipped": {"CCC": "no price"}})
    r = runner.invoke(cli.app, ["case", "build", "--all"])
    assert r.exit_code == 0, r.output
    assert seen["codes"] == ["AAA", "BBB", "CCC"] and "AAA A" in r.output and "CCC: not built – no price" in r.output and "1 built (A 1, B 0, C 0)" in r.output


# ------------------------------------------------------------------------------------------------ the screen
def test_screen_verdicts_compare_the_requirement_with_the_history():
    base = _case()
    hist = lcm.history(base)["rev_cagr"]                                                  # ~9.5 % a year
    r = sc.row(base, "light")                                                             # EV 191m below the 400m capital employed
    assert r["basis"].startswith("snittmargin") and r["kind"] == "below_capital" and r["required"] is None and r["verdict"] == "below_capital"
    assert "below the capital the business employs" in lcm.normalised(base)["reads"]
    assert lcm.reading(base) == base["reverse"] | {"kind": None}                          # no stored NOPAT: the stored reading stands
    old = {**base, "reverse": {**base["reverse"], "nopat": 46.8e6, "roic": 0.117, "reads": "the price needs growth at or above the 8.5% cost of capital (EST)"}}
    assert lcm.reading(old)["kind"] == "below_capital" and "at or above" not in lcm.reading(old)["reads"]   # a pre-D42 file gets the corrected words
    fall = _case()
    fall["multiples"] = {**fall["multiples"], "ev": 450e6}                                # between the capital (400m) and the no-growth value
    norm = lcm.normalised(fall)["implied_g"]
    rf = sc.row(fall)
    assert norm < 0 and rf["required"] == pytest.approx(norm) and rf["verdict"] == "fall"
    assert rf["ref"] == "long_run" and rf["hist"] == lcm.G_LONG_EST and rf["gap"] == pytest.approx(norm - lcm.G_LONG_EST)   # cyclical: not the cycle's revenue
    steady = _case(group="Consumer, telecom & real estate")
    steady["reverse"] = {**steady["reverse"], "implied_g": 0.15}
    rs = sc.row(steady)
    assert rs["basis"] == "siste 12 mnd" and rs["ref"] == "history" and rs["verdict"] == "more" and rs["gap"] == pytest.approx(0.15 - hist)
    steady["reverse"]["implied_g"] = hist + 0.01
    assert sc.row(steady)["verdict"] == "in_line"
    steady["reverse"] = {**steady["reverse"], "implied_g": None, "reads": "the price needs growth at or above the 8.0% cost of capital (EST)"}
    assert sc.row(steady)["verdict"] == "above_wacc"
    bank = _case(group="Finance", financial=True)
    bank["reverse"] = {"model": "justified P/B", "implied_roe": 0.05, "reads": "t"}
    rb = sc.row(bank)
    assert rb["measure"] == "ROE" and rb["hist"] == pytest.approx(lcm.history(bank)["roe_avg"]) and rb["verdict"] == "less"
    assert sc.row(_case(shares=None))["verdict"] == "none"                                 # grade C: no reading


def test_candidates_leave_out_full_cases_and_unusable_ones():
    def mk_row(code, gap, level="light", usable=True, verdict=None):
        return {"code": code, "gap": gap, "level": level, "quality": {"usable": usable, "grade": "A" if usable else "C"},
                "verdict": verdict or ("more" if gap and gap > 0 else "less")}
    rs = [mk_row("A", 0.10), mk_row("B", 0.30), mk_row("C", 0.50, level="full"), mk_row("D", 0.40, usable=False),
          mk_row("E", -0.20), mk_row("F", -0.05), mk_row("G", 0.01, verdict="in_line"), mk_row("H", None, verdict="above_wacc")]
    c = sc.candidates(rs)
    assert [r["code"] for r in c["more"]] == ["B", "A", "H"] and [r["code"] for r in c["less"]] == ["E", "F"]
    cnt = sc.counts([sc.row(_case()), sc.row(_case(shares=None))])
    assert cnt["n"] == 2 and cnt["grade_A"] == 1 and cnt["grade_C"] == 1 and cnt["none"] == 1


def test_screen_page_stock_page_and_coverage_show_the_grade(app, monkeypatch):  # noqa: F811
    client, snap = app
    lcm.case_dir().mkdir(parents=True, exist_ok=True)
    lcm.case_path("AAA").write_text(json.dumps(_case()), encoding="utf-8")
    page = client.get("/screen").get_data(as_text=True)
    assert "Hva prisen krever" in page and "Kandidater for full dekning" in page and "Ikke testet mot avkastning" in page
    assert ">Prisen krever</a>" in page and "Alpha" in page and "snittmargin 2023–2025" in page and "1 lette caser" in page
    assert "langsiktig EST (syklisk; omsetning +9.5% /år 2023–2025)" in page
    stock = client.get("/stock/AAA").get_data(as_text=True)
    assert "Kvalitet A" in stock and "On the average margin" in stock and "History 2023–2025" in stock
    cov = client.get("/coverage").get_data(as_text=True)
    assert 'class="chip buy" title="no issues">A</span>' in cov
