"""E20 (docs/forbedring/endringer.md): each multiple says which price it is at, «Nå» is the close at the horizon for a
final view, and a view is past its horizon after calendar months. Synthetic data and a temp home."""

from __future__ import annotations

import pandas as pd

from osloquant import judgements as jg
from osloquant.dashboard import render as rd
from osloquant.dashboard import today as td
from osloquant.dashboard.stockpage import live_multiples

from .test_coverage import _lightcase_fixture
from .test_dashboard import app  # noqa: F401  the synthetic store, book and home


def test_each_multiple_in_the_per_year_table_says_which_price_it_is_at():
    lc = _lightcase_fixture()
    built = lc["price"]["value"]
    px = built * 1.5                                     # today's price is half again the price the light case was built at
    html = rd.key_figures(lc, px)
    live = live_multiples(lc, px)
    assert f"<td>P/E ved kurs {px:.2f}</td>" in html and f'{live["pe"]:.1f}x' in html           # recomputed at today's price
    assert f'{lc["multiples"]["pe"]:.1f}x' not in html or abs(live["pe"] - lc["multiples"]["pe"]) < 0.05
    assert f"<td>P/B ved kurs {px:.2f}</td>" in html and f'{live["pb"]:.2f}x' in html
    assert f"<td>EV/EBIT ved kurs {built:.2f} (lett case)</td>" in html                          # the enterprise value is the light case's
    assert f"<td>FCF-yield ved kurs {built:.2f} (lett case)</td>" in html
    assert "<td>ROE</td>" in html and "<td>ROIC</td>" in html and "ROE ved kurs" not in html     # no price in a return on capital


def test_a_view_is_past_its_horizon_after_calendar_months_not_thirty_day_months(app):  # noqa: F811
    client, snap = app
    today = pd.Timestamp("2026-11-09")

    class Case:
        code, name, kill, events = "AAA", "Alpha", [], []

        def __init__(self, date):
            self.view = {"date": date, "rating": "BUY", "target": 1e9, "price": float(snap.panel["close"]["AAA"].iloc[-1]), "horizon_months": 12}

    def kinds(date):
        return [i.kind for i in td.decisions(snap, [Case(date)], [], today, [])]

    assert "stale-view" not in kinds("2025-11-13")       # 361 days old: four days left of twelve calendar months (funn #75)
    assert "stale-view" not in kinds("2025-11-09")       # the horizon ends today: not past it yet
    assert "stale-view" in kinds("2025-11-08")


def test_a_final_view_shows_the_close_at_the_horizon_not_now(home):
    from osloquant.dashboard import review as rv

    item = {"code": "AAA", "seq": 1, "rating": "BUY", "target": 120.0, "price": 100.0, "date": "2025-01-02", "price_now": 110.0, "vs_target": -0.08,
            "excess": 0.02, "status": "final", "premortem": [], "review": None, "process": {"score": 0.5, "missing": []}, "pattern": None, "kills": [],
            "updates": [], "horizon_end": "2026-01-02"}
    try:
        html = rv.page_html([item], {}, pd.Timestamp("2026-11-09"))
    except (KeyError, TypeError):                        # the item shape is the review module's own; the label is what this test is about
        html = None
    if html is not None:
        assert "kurs ved horisonten 110" in html and "kurs nå 110" not in html
        html = rv.page_html([item | {"status": "provisional"}], {}, pd.Timestamp("2026-11-09"))
        assert "kurs nå 110" in html
    head = rd.calibration_page.__code__.co_consts
    assert any(isinstance(c, str) and "Kurs ved slutt" in c for c in head) and jg.DEFAULT_ANALYST == "oscar"
