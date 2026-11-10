"""Coverage with two analysts (D31): light cases computed from statements, Claude's views logged beside Oscar's and
never in their place, Oscar's views split into blind and anchored, and the pages that show both. Synthetic data only."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import lightcase as lc
from osloquant.dashboard import render as rd
from osloquant.dashboard import today as td

from .test_dashboard import GOOD, app  # noqa: F401  (fixture)

VIEW = {"rating": "BUY", "target": 130, "bear": 85, "base": 125, "bull": 160, "p_bear": 0.25, "p_base": 0.5, "p_bull": 0.25,
        "kill": ["Fictional margin below 10 %"], "thesis": "Synthetic thesis for a test company that does not exist."}


# ------------------------------------------------------------------------------------------------ light case maths
def test_implied_growth_inverts_the_value_driver_formula():
    nopat, roic, wacc, g = 100.0, 0.15, 0.09, 0.03
    ev = nopat * (1 - g / roic) / (wacc - g)
    assert lc.implied_growth(ev, nopat, roic, wacc) == pytest.approx(g)
    assert lc.implied_growth(ev, -5.0, roic, wacc) is None                   # no profit, no answer
    assert lc.implied_growth(nopat * 100, nopat, roic, wacc) is None          # needs growth at the cost of capital
    below = lc.implied_growth(nopat / wacc * 0.8, nopat, roic, wacc)
    assert below is not None and below < 0                                    # under the no-growth value: profit must fall
    assert lc.implied_roe(1.5, 0.10, 0.02) == pytest.approx(0.14)


def _frames(currency_scale=1.0, quarters=4, gap=False):
    q_dates = pd.date_range("2025-09-30", periods=quarters, freq="QE")
    if gap:
        q_dates = q_dates.delete(1)
    inc_q = pd.DataFrame({"report_date": q_dates, "report_period": "quarter", "total_revenue": 250.0 * currency_scale,
                          "ebit": 40.0 * currency_scale, "net_income": 25.0 * currency_scale, "pretax_income": 32.0 * currency_scale,
                          "tax_provision": 7.0 * currency_scale, "diluted_shares": 10.0})
    y_dates = pd.to_datetime(["2023-12-31", "2024-12-31", "2025-12-31"])
    inc_y = pd.DataFrame({"report_date": y_dates, "report_period": "year", "total_revenue": [900.0, 950.0, 1000.0],
                          "ebit": [140.0, 150.0, 160.0], "net_income": [90.0, 95.0, 100.0], "pretax_income": [120.0, 125.0, 130.0],
                          "tax_provision": [26.0, 27.0, 28.0], "diluted_shares": 10.0})
    bal = pd.concat([pd.DataFrame({"report_date": y_dates, "report_period": "year", "net_debt": 200.0, "total_equity": 600.0,
                                   "minority_interest": 0.0, "shares_outstanding": 10.0}),
                     pd.DataFrame({"report_date": q_dates, "report_period": "quarter", "net_debt": 220.0, "total_equity": 650.0,
                                   "minority_interest": 0.0, "shares_outstanding": 10.0})], ignore_index=True)
    cf_q = pd.DataFrame({"report_date": q_dates, "report_period": "quarter", "free_cash_flow": 20.0})
    cf_y = pd.DataFrame({"report_date": y_dates, "report_period": "year", "free_cash_flow": [70.0, 75.0, 80.0]})
    return inc_y, inc_q, bal, cf_y, cf_q


def test_light_case_uses_ltm_converts_currency_and_names_its_sources():
    inc_y, inc_q, bal, cf_y, cf_q = _frames()
    c = lc.compute("XYZ", "Xyz", "Industrials & materials", price=200.0, price_date="2026-07-15", shares=10.0, currency="USD", fx=10.0,
                   fx_date="2026-07-15", inc_y=inc_y, inc_q=inc_q, bal=bal, cf_y=cf_y, cf_q=cf_q)
    assert c["profit"]["ebit"] == {"value": 160.0, "period": "LTM to 2026-06-30"}
    assert c["mcap_nok"] == 2000.0 and c["multiples"]["pe"] == pytest.approx(200.0 / 100.0)       # NOK 2000 = USD 200, LTM NI 100
    assert c["multiples"]["ev"] == pytest.approx(420.0) and c["multiples"]["ev_ebit"] == pytest.approx(420 / 160)
    assert c["returns"]["tax_rate"] == pytest.approx(28 / 128)
    assert c["reverse"]["model"] == "value driver" and c["reverse"]["wacc_est"] == lc.WACC_EST["Industrials & materials"]
    assert "EST" in c["reverse"]["reads"] and c["warnings"] == []
    assert len(c["annual"]) == 3 and c["annual"][-1]["revenue"] == 1000.0
    # a gap in the quarters falls back to the last full year, said so
    g = lc.compute("XYZ", "Xyz", "Industrials & materials", 200.0, "2026-07-15", 10.0, "USD", 10.0, "2026-07-15", *_frames(quarters=5, gap=True))
    assert g["profit"]["ebit"]["period"] == "FY to 2025-12-31"
    # no FX for a foreign reporter: no multiples, and a warning
    nofx = lc.compute("XYZ", "Xyz", "Energy", 200.0, "2026-07-15", 10.0, "DKK", None, None, inc_y, inc_q, bal, cf_y, cf_q)
    assert nofx["mcap_nok"] == 2000.0 and nofx["multiples"] == {} and any("DKKNOK" in w for w in nofx["warnings"])
    # statements well behind the price date are flagged
    late = lc.compute("XYZ", "Xyz", "Energy", 200.0, "2026-11-30", 10.0, "USD", 10.0, "2026-11-30", inc_y, inc_q, bal, cf_y, cf_q)
    assert any("only to 2026-06-30" in w for w in late["warnings"])


def test_financials_get_the_justified_pb_instead_of_ev():
    inc_y, inc_q, bal, cf_y, cf_q = _frames()
    c = lc.compute("BNK", "Bank", "Finance", 97.5, "2026-07-15", 10.0, "NOK", 1.0, None, inc_y, inc_q, bal, cf_y, cf_q)
    assert "ev" not in c["multiples"] and c["multiples"]["fcf_yield"] is None
    assert c["multiples"]["pb"] == pytest.approx(975 / 650) and c["reverse"]["model"] == "justified P/B"
    assert c["reverse"]["implied_roe"] == pytest.approx(1.5 * (lc.COE_EST - lc.G_LONG_EST) + lc.G_LONG_EST)
    html = rd.lightcase_block(c)
    assert "return on equity" in html and "EST" in html and "EV/EBIT" not in html


def test_peer_medians_skip_missing_and_negative_multiples():
    p = lc.peer_stats([{"code": "A", "ev_ebit": 8.0, "pe": 10.0, "pb": 1.0}, {"code": "B", "ev_ebit": 12.0, "pe": -4.0, "pb": None},
                       {"code": "C", "ev_ebit": None, "pe": 14.0, "pb": 2.0}])
    assert p["ev_ebit"] == 10.0 and p["n_ev_ebit"] == 2 and p["pe"] == 12.0 and p["n_pe"] == 2 and p["members"] == ["A", "B", "C"]


# ------------------------------------------------------------------------------------------------ two analysts in one log
def test_rows_without_an_analyst_stay_oscars_and_claude_never_becomes_the_current_view(home):
    jg.append("judgement", dict(code="AAA", date="2026-01-05", price=100.0, rating="BUY", target=120.0, horizon_months=12))
    jg.append("judgement", dict(code="AAA", date="2026-02-05", price=101.0, rating="SELL", target=80.0, horizon_months=12, analyst="claude"))
    with pytest.raises(ValueError, match="analyst"):
        jg.append("judgement", dict(code="AAA", date="2026-02-05", price=101.0, rating="BUY", target=120.0, horizon_months=12, analyst="robot"))
    rows = jg.read_log()
    assert "analyst" not in rows[0] and jg.analyst_of(rows[0]) == "oscar" and jg.verify().ok
    assert jg.latest_by_code()["AAA"]["rating"] == "BUY" and jg.latest_by_code(analyst="claude")["AAA"]["rating"] == "SELL"
    assert [r["seq"] for r in jg.judgements(analyst="claude")] == [2]


def test_a_company_only_claude_covers_is_a_case_without_a_view_and_is_not_nagged(home):
    sg.book_path().write_text("entries:\n  - code: AAA\n    name: Alpha\n    events:\n      - {date: 2026-11-12, what: Q3 2026 report}\n", encoding="utf-8")
    bk.log_claude_view("BBB", "Beta", VIEW, 100.0, "2026-11-02", "test", today="2026-11-02")
    bk.log_claude_view("AAA", "Alpha", VIEW, 100.0, "2026-11-02", "test", today="2026-11-02")
    with pytest.raises(ValueError, match="lacks"):
        bk.log_claude_view("CCC", "Gamma", {"rating": "BUY", "target": 10}, 9.0, "2026-11-02", "test")
    cases = {c.code: c for c in bk.cases()}
    assert cases["AAA"].view is None and cases["AAA"].claude_view["rating"] == "BUY" and cases["AAA"].history == []
    assert cases["BBB"].view is None and cases["BBB"].claude_view["analyst"] == "claude"
    assert "BBB" in [e["code"] for e in sg.load_book()]                       # Claude's company joins the book, with no view
    assert td.pre_report_items(list(cases.values()), pd.Timestamp("2026-11-02")) == []
    assert td.post_report_items(list(cases.values()), pd.Timestamp("2026-11-20")) == []


def test_calibration_scores_both_and_splits_oscar_into_blind_and_anchored(home):
    dates = pd.bdate_range("2025-01-01", periods=400)
    adj = pd.DataFrame({"AAA": np.linspace(100, 140, 400), "BBB": np.linspace(100, 90, 400)}, index=dates)
    prices = jg.Prices(adjusted=adj, raw=adj.copy(), index=pd.Series(np.linspace(100, 110, 400), index=dates))
    rows = []
    for i, (code, analyst, rating, target, saw) in enumerate([("AAA", "claude", "BUY", 130.0, None), ("AAA", None, "BUY", 140.0, False),
                                                              ("BBB", "claude", "SELL", 85.0, None), ("BBB", None, "BUY", 120.0, True)]):
        r = dict(seq=i + 1, kind="judgement", code=code, date="2025-01-02", price=100.0, rating=rating, target=target, horizon_months=12)
        if analyst:
            r["analyst"] = analyst
        if saw is not None:
            r["saw_claude"] = saw
        rows.append(r)
    table, summary = jg.calibration(rows, prices=prices, asof=pd.Timestamp("2025-06-30"))
    assert summary["all_scored"]["n"] == 2                                    # the headline is Oscar's alone
    assert summary["by_analyst"]["claude"]["all_scored"]["n"] == 2 and summary["by_analyst"]["claude"]["judgements"] == 2
    assert summary["oscar_blind"]["n"] == 1 and summary["oscar_saw_claude"]["n"] == 1
    h = jg.head_to_head(table)
    assert h["n"] == 2 and {r["code"] for r in h["rows"]} == {"AAA", "BBB"} and h["agree"] == 1
    html = rd.analysts_block(summary, h)
    assert "Du og Claude" in html and "blind" in html and "Side om side" in html


# ------------------------------------------------------------------------------------------------ pages
def test_stock_page_folds_claudes_view_and_the_form_asks_whether_it_was_read(app):  # noqa: F811
    client, snap = app
    bk.log_claude_view("BBB", "Beta Shipping", VIEW, 100.0, "2026-11-02", "test")
    page = client.get("/stock/BBB").get_data(as_text=True)
    assert "<details class=\"card\"><summary><b>Claudes syn</b>" in page and "Hadde du lest Claudes syn" in page
    assert "Ingen vurdering fra deg ennå" in page and "Claude har et syn (foldet lenger ned)" in page
    r = client.post("/stock/BBB/judge", data=GOOD | {"claude_exists": "1"})
    assert r.status_code == 400 and "say whether you had read Claude" in r.get_data(as_text=True)
    r = client.post("/stock/BBB/judge", data=GOOD | {"claude_exists": "1", "saw_claude": "no", "kill_level": "50"})
    assert r.status_code == 303
    mine = jg.latest_by_code()["BBB"]
    assert mine["saw_claude"] is False and jg.analyst_of(mine) == "oscar"
    cov = client.get("/coverage").get_data(as_text=True)
    assert "Dekning" in cov and "Beta Shipping" in cov and "Claudes syn" in cov
    assert "Dekning: " in client.get("/").get_data(as_text=True)


def test_coverage_page_lists_both_views_and_agreement():
    today = pd.Timestamp("2026-11-02")
    rows = [{"code": "AAA", "name": "Alpha", "group": "Energy", "price": 110.0,
             "oscar": {"rating": "BUY", "target": 130.0, "since": 0.1, "to_tp": 0.18}, "claude": {"rating": "HOLD", "target": 115.0, "since": 0.05, "to_tp": 0.05},
             "reads": "+2.0 %/år vekst for alltid", "next": {"date": pd.Timestamp("2026-11-12")}},
            {"code": "BBB", "name": "Beta", "group": "Shipping", "price": 50.0, "oscar": None,
             "claude": {"rating": "SELL", "target": 40.0, "since": None, "to_tp": -0.2}, "reads": None, "next": None}]
    html = rd.coverage_page(rows, today)
    assert "2 selskaper" in html and "du har syn på 1, Claude på 2" in html and "Bare Claude har syn på 1" in html
    assert "✗" in html and "12. nov. (10 d)" in html


# ------------------------------------------------------------------------------------------------ report layout (D32)
def _lightcase_fixture():
    return {"code": "AAA", "name": "Alpha", "group": "Seafood", "financial": False, "built_at": "2026-11-02T10:00:00Z",
            "price": {"value": 100.0, "date": "2026-10-30", "source": "test"}, "shares": 10e6, "mcap_nok": 1e9,
            "currency": {"reporting": "EUR", "fx": 11.0, "fx_date": "2026-10-30", "source": "test"},
            "profit": {k: {"value": v, "period": "LTM to 2026-06-30"} for k, v in (("revenue", 500e6), ("ebit", 60e6), ("net_income", 40e6), ("fcf", 30e6))},
            "balance": {"net_debt": 100e6, "equity": 300e6, "minority": 0, "date": "2026-06-30"},
            "annual": [{"year": 2024, "date": "2024-12-31", "revenue": 450e6, "ebit": 50e6, "net_income": 35e6, "fcf": 25e6, "net_debt": 120e6, "equity": 280e6},
                       {"year": 2025, "date": "2025-12-31", "revenue": 480e6, "ebit": 55e6, "net_income": 38e6, "fcf": 28e6, "net_debt": 110e6, "equity": 290e6}],
            "multiples": {"pe": 2.27, "pb": 0.3, "fcf_yield": 0.33, "ev": 190.9e6, "ev_ebit": 3.2, "ev_sales": 0.38},
            "returns": {"tax_rate": 0.22, "tax_period": "LTM", "roe": 0.13, "roic": 0.117},
            "reverse": {"model": "value driver", "wacc_est": 0.085, "implied_g": 0.01, "reads": "the price pays for +1.0 % a year growth (EST)"},
            "peers": {"pe": 15.0, "n_pe": 4, "ev_ebit": 10.0, "n_ev_ebit": 4, "pb": 2.0, "n_pb": 4, "group": "Seafood", "note": "test"},
            "statements_source": "test", "warnings": [], "quarters_through": "2026-06-30"}


def test_stock_page_is_laid_out_as_a_report_front_page(app, monkeypatch):  # noqa: F811
    from osloquant.dashboard import lightcase as lcm

    client, snap = app
    monkeypatch.setattr(lcm, "load", lambda code: _lightcase_fixture() if code == "AAA" else None)
    page = client.get("/stock/AAA").get_data(as_text=True)
    assert 'class="stockbar"' in page and 'class="tabs"' in page                                 # sticky bar and seven tabs (D57)
    assert all(f'data-tab="{t}"' in page for t in ("oversikt", "regnskap", "verdsettelse", "teknisk", "rapporter", "eiere", "vurdering"))
    assert '<div class="view-big">BUY</div>' in page and "TP: NOK 120" in page                  # the research-book view, large (Min vurdering)
    assert "Mitt syn <b>BUY</b>" in page and "NOK 120" in page                                     # and in short form in the bar
    assert "Kapitalstruktur" in page and "EV/EBIT (LTM)" in page and "EURNOK 11,000" in page      # Regnskap → Oversikt
    assert "Neste hendelse" in page and "Q4 report" in page                                      # from the book's events (Rapporter)
    assert "Investeringscase" in page and "Nedside – kill-kriterier" in page and "margin below 10%" in page
    assert 'class="keyfig"' in page and "<th>2024</th><th>2025</th>" in page and "Omsetningsvekst" in page and "+6,7 %" in page
    assert "Ingen estimater vises" in page and "EST" in page
    assert "prefers-color-scheme" not in page                                                      # one light theme (D32)
    # a company without a case keeps the layout, with the view box saying so
    bare = client.get("/stock/CCC").get_data(as_text=True)
    assert 'class="stockbar"' in bare and "Ingen vurdering fra deg ennå" in bare and 'class="keyfig"' not in bare and "Ikke fulgt" in bare


def test_price_chart_draws_the_cone_to_the_views_values(app):  # noqa: F811
    from osloquant.dashboard.charts import price_chart

    client, snap = app
    c = bk.case("AAA")
    html = price_chart(snap, "AAA", c)
    assert "TP NOK 120" in html and "Bear NOK 70" in html and "Bull NOK 150" in html and "kjegle til synets" in html
    plain = price_chart(snap, "BBB", None)
    assert "kjegle" not in plain and "Sluttkurs" in plain
