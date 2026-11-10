"""The frontier chart on the portfolio page (DECISIONS D68): it opens on the portfolios, names every diamond, uses
neither green nor red, speaks the page's own numbers, and marks a build older than a month."""

from __future__ import annotations

import json
import re

import pandas as pd

from osloquant.dashboard import fundchart as fc
from osloquant.dashboard.tall import NBSP


def _build(built: str = "2026-11-02T12:09:57Z") -> dict:
    funds = [("Likevektet", 0.126, 0.232), ("Minimum varians", 0.088, 0.216), ("Risikoparitet", 0.107, 0.226), ("Maks Sharpe (tangens)", 0.100, 0.276),
             ("CML 8% vol", 0.080, 0.229), ("Synene – Claude", 0.143, 0.184)]
    return {"asof": "2026-10-30", "built_at": built, "rf": 0.045, "rf_label": "Norges Bank policy rate 4.5 % (2026-10-30, rates feed)", "lookback_years": 3.0,
            "stocks": [f"S{i}" for i in range(62)], "inputs": {f"S{i}": {"vol": 0.18 + i * 0.008, "mu": 0.10 + (i % 9) * 0.03} for i in range(62)},
            "frontier": [{"vol": 0.0886 + i * 0.004, "ret": 0.2157 + 0.12 * (1 - 0.8 ** i)} for i in range(18)], "tangency": {"ret": 0.276, "vol": 0.100},
            "funds": [{"name": n, "est": {"vol": v, "ret": r, "sharpe": (r - 0.045) / v}, "weights": {"AAA": 0.4, "BBB": 0.35, "CCC": 0.25}, "cash": 0.2 if "CML" in n else 0.0,
                       "n": 3} for n, v, r in funds]}


def _figure(html: str) -> tuple[list, dict]:
    m = re.search(r'Plotly\.newPlot\(\s*"chart-front",\s*(\[.*?\]),\s*(\{.*?\}),\s*\{"displayModeBar"', html, re.S)
    assert m, "no Plotly figure in the chart"
    return json.loads(m.group(1)), json.loads(m.group(2))


def test_the_chart_opens_on_the_portfolios_and_keeps_the_single_stocks_one_click_away():
    html = fc.html(_build(), pd.Timestamp("2026-11-10"))
    data, layout = _figure(html)
    assert data[0]["name"] == "Enkeltaksjer" and data[0]["visible"] is False and len(data[0]["x"]) == 62
    xr, yr = layout["xaxis"]["range"], layout["yaxis"]["range"]
    assert xr[0] == 0 and 15 < xr[1] < 25                                 # the portfolios and the frontier, not the 70 % of the single stocks
    assert yr[0] < 4.5 < 18.4 < yr[1] and yr[1] < 45
    assert 'id="front-aksjer"' in html and "Vis enkeltaksjene (62)" in html and "Plotly.restyle" in html
    assert '"displayModeBar": false' in html and layout.get("showlegend") is False and "title" not in {k for k in layout if k == "title"}


def test_every_diamond_is_named_and_no_two_labels_share_a_place():
    data, layout = _figure(fc.html(_build(), pd.Timestamp("2026-11-10")))
    texts = [a["text"] for a in layout["annotations"]]
    for name in ("Likevektet", "Minimum varians", "Risikoparitet", "CML 8% vol", "Synene – Claude"):
        assert name in texts
    assert "Maks Sharpe (tangens) · Sharpe 2,31" in texts and "Kapitalmarkedslinjen · Sharpe 2,31" in texts
    assert f"Risikofri 4,50{NBSP}%" in texts
    placed = [(a["x"], a["y"], a.get("ax"), a.get("ay")) for a in layout["annotations"] if a.get("showarrow")]
    assert len(placed) == 6 and len({(round(x, 2), round(y, 2), ax, ay) for x, y, ax, ay in placed}) == 6
    pts = [(x, y, "Likevektet") for x, y, _, _ in placed]
    offsets = fc._place(pts, (0, 18), (2, 32))
    assert len(set(zip([p[0] for p in pts], offsets, strict=True))) == 6


def test_no_green_and_no_red_and_the_pages_own_numbers():
    html = fc.html(_build(), pd.Timestamp("2026-11-10"))
    data, layout = _figure(html)
    used = {str(t.get("marker", {}).get("color", "")).lower() for t in data} | {str(t.get("line", {}).get("color", "")).lower() for t in data}
    assert not used & {"#0b7a4b", "#b3261e", "green", "red"}
    assert layout["xaxis"]["ticksuffix"] == f"{NBSP}%" and layout["separators"] == ", "
    assert "Norges Banks styringsrente 4.5 % (2026-10-30)" in html and "policy rate" not in html and "rates feed" not in html
    hover = next(t["hovertemplate"] for t in data if t["name"] == "CML 8% vol")
    assert "Størst: AAA 40 %" in hover and "Kontanter 20 %" in hover and "bygget" in hover and "(EST)" in hover
    assert "ikke en prognose" in html and "slo ingen av oppskriftene likevekt" in html


def test_a_build_older_than_a_month_is_marked():
    b = _build("2026-09-30T10:00:00Z")
    assert fc.age_days(b, pd.Timestamp("2026-11-10")) == 41
    warn = fc.stale_html(b, pd.Timestamp("2026-11-10"))
    assert 'id="bygg-gammelt"' in warn and "41 dager gammelt" in warn and "oq funds build --write" in warn
    assert fc.stale_html(_build(), pd.Timestamp("2026-11-10")) == "" and fc.stale_html({}, pd.Timestamp("2026-11-10")) == ""


def test_the_nav_charts_use_the_frontier_charts_colours_and_neither_green_nor_red():
    b = _build()
    colours = fc.fund_colours(b)
    assert list(colours) == [f["name"] for f in b["funds"]] and len(set(colours.values())) == 6
    series = {n: {"2026-11-02": 100.0, "2026-11-03": 100.0 + i} for i, n in enumerate(sorted(colours))} | {"OSEBX": {"2026-11-02": 100.0, "2026-11-03": 99.0}}
    html = fc.nav_html(series, "NAV fra 100 ved første skriving", colours, 300)
    m = re.search(r"Plotly\.newPlot\(\s*\"[^\"]+\",\s*(\[.*?\]),\s*(\{.*?\}),\s*\{\"displayModeBar\"", html, re.S)
    assert m, "no Plotly figure in the NAV chart"
    data, layout = json.loads(m.group(1)), json.loads(m.group(2))
    by_name = {t["name"]: t["line"] for t in data}
    assert all(by_name[n]["color"] == colours[n] for n in colours)                   # a fund is the same colour in every chart on the page
    assert by_name["OSEBX"]["dash"] == "dot" and by_name["Likevektet"]["width"] > by_name["Risikoparitet"]["width"]
    assert not {str(line["color"]).lower() for line in by_name.values()} & {"#0b7a4b", "#b3261e", "green", "red"}
    assert "title" not in layout and html.startswith('<div class="src"') and "NAV fra 100 ved første skriving" in html.split("<script")[0]
    assert '"displayModeBar": false' in html
    # a fund the build does not know still gets a colour, and not one that is taken
    extra = fc.nav_html({"Likevektet": {"2026-11-02": 100.0}, "Ny oppskrift": {"2026-11-02": 100.0}}, "x", colours)
    assert "Ny oppskrift" in extra


def test_the_note_under_a_fund_reads_in_norwegian():
    assert fc.note_text("every stock the same weight; the reference") == "alle aksjer samme vekt; referansen"
    assert fc.note_text("lowest variance, long-only, no stock above 15%; no means used") == "lavest varians, bare lange posisjoner, ingen aksje over 15%; ingen forventet avkastning brukt"
    assert fc.note_text("80% in the tangency portfolio, 20% at the policy rate – a point on the CML with 8% volatility") == (
        "80% i tangensporteføljen, 20% til styringsrenten – et punkt på kapitalmarkedslinjen med 8% volatilitet")
    assert fc.note_text("max Sharpe on the targets' implied returns (EST), 4 stocks with a view above the policy rate, cap 25%") == (
        "maks Sharpe på kursmålenes impliserte avkastning (EST), 4 aksjer med syn over styringsrenten, tak 25% per aksje")
    assert fc.note_text("en tekst listen ikke kjenner") == "en tekst listen ikke kjenner" and fc.note_text(None) == ""


def test_every_note_the_allocation_code_writes_is_known():
    import numpy as np

    from osloquant import allocation as al

    codes = ["AAA", "BBB", "CCC", "DDD"]
    cov = pd.DataFrame(np.diag([0.04, 0.05, 0.06, 0.07]) + 0.005, index=codes, columns=codes)
    mu = pd.Series([0.08, 0.10, 0.12, 0.14], index=codes)
    tangency = al.max_sharpe(mu, cov, 0.045, 0.5)
    made = [al.equal_weight(codes), al.inverse_vol(cov), al.min_variance(cov, 0.5), tangency, al.cml_point(tangency, cov, 0.08), al.risk_parity(cov),
            al.view_weighted(mu, cov, 0.045), al.view_weighted(mu * 0, cov, 0.045)]
    for p in made:
        assert fc.note_text(p.note) != p.note, p.note                                 # no English line reaches the page
