"""The price chart and the stock-page tabs in a real headless browser (night 10 Nov 2026, K1–K3).

Checked: the chart's state after each button, the colour of the period, log only for 5Å and Maks, candles, the
comparison, the markers, the lines, the hover box beside the point, no console errors, and visual baselines of the
chart, the bar and every tab. Everything runs on a synthetic store and a temp home. The tests skip when the machine
has no Chromium browser, and the visual comparisons skip on a platform without baselines (tests/browser.py)."""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pytest

from osloquant import signals as sg
from osloquant.dashboard import market as mk
from osloquant.dashboard import server

from . import browser
from .helpers import business_days

pytestmark = pytest.mark.skipif(not browser.find(), reason="no Chromium browser (Edge, Chrome or Chromium) on this machine")
TABS = ("oversikt", "regnskap", "verdsettelse", "teknisk", "rapporter", "eiere", "vurdering")
HIDE_TEXT = ("*{color:transparent!important;text-shadow:none!important;caret-color:transparent!important}"
             "svg text{fill:transparent!important}input,textarea,select{color:transparent!important}")


def _snapshot() -> mk.Snapshot:
    rng = np.random.default_rng(11)
    n = 1400
    dates = business_days(n, "2021-03-01")
    codes = ("AAA", "DDD", "EEE", "BBB")
    drift = {"AAA": 0.0005, "DDD": 0.0002, "EEE": -0.0001, "BBB": 0.0}
    close = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(drift[c], 0.016, n))) for c in codes}, index=dates)
    vol = pd.DataFrame(rng.integers(20_000, 90_000, (n, len(codes))).astype(float), index=dates, columns=codes)
    panel = dict(open=close.shift(1).fillna(close) * (1 + rng.normal(0, 0.003, (n, len(codes)))), high=close * 1.012, low=close * 0.988, close=close, volume=vol)
    panel["high"] = pd.concat([panel["high"], panel["open"]]).groupby(level=0).max()
    panel["low"] = pd.concat([panel["low"], panel["open"]]).groupby(level=0).min()
    return mk.Snapshot(panel, {"AAA": "Alpha Seafood", "DDD": "Delta Salmon", "EEE": "Echo Fish", "BBB": "Beta Shipping"},
                       {"AAA": "Seafood", "DDD": "Seafood", "EEE": "Seafood", "BBB": "Other shipping"}, dates[-1])


@pytest.fixture(scope="module")
def chrome():
    b = browser.Browser(browser.find())
    yield b
    b.close()


@pytest.fixture
def live(monkeypatch, home):
    snap = _snapshot()
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    vday = snap.panel["close"].index[-160]
    vpx = float(snap.panel["close"]["AAA"].loc[vday])
    sg.book_path().write_text(
        "entries:\n  - code: AAA\n    name: Alpha Seafood\n    rating: BUY\n"
        f"    valuation_date: {vday:%Y-%m-%d}\n    price_at_valuation: {vpx:.2f}\n"
        f"    target: {vpx * 1.3:.2f}\n    bear: {vpx * 0.75:.2f}\n    bull: {vpx * 1.6:.2f}\n"
        "    kill:\n      - margin below 10%\n", encoding="utf-8")
    app = server.create_app()
    app.testing = True
    base, stop = browser.serve(app)
    yield base, snap
    stop()


def _open(chrome, url: str, width: int = 1280, height: int = 1000, scale: float = 1) -> browser.Page:
    p = chrome.page()
    p.goto(url, width=width, height=height, scale=scale, ready="window.PriceChart && window.PriceChart.state().width > 0")
    return p


def _state(p) -> dict:
    return p.eval("PriceChart.state()")


def _data(p) -> dict:
    return p.eval("JSON.parse(document.getElementById('pc-data').textContent)")


def _click(p, selector: str) -> None:
    p.eval(f"document.querySelector({json.dumps(selector)}).click()")
    p.eval("new Promise(function(r){requestAnimationFrame(function(){requestAnimationFrame(r)})})")


# ------------------------------------------------------------------------------------------------ state
def test_the_chart_opens_on_one_year_with_the_colour_and_the_return_of_that_year(chrome, live):
    base, snap = live
    p = _open(chrome, f"{base}/aksje/AAA")
    try:
        s, d = _state(p), _data(p)
        assert (s["panes"], s["mainPane"], s["volPane"]) == (2, 0, 1)
        one = next(x for x in d["periods"] if x["key"] == "1a")
        assert s["type"] == "area" and s["period"] == "1a" and s["from"] == one["x0"] and s["to"] == d["t"][-1]
        assert s["ret"] == pytest.approx(one["ret"], rel=1e-4) and s["color"] == ("#0b7a4b" if one["ret"] >= 0 else "#b3261e")
        head = p.eval("document.querySelector('.pc-ret').textContent")
        assert head.startswith("1Å ") and "," in head and "%" in head
        assert s["sma"] == {"50": False, "200": False} and s["log"] is False and s["scaleMode"] == 0
        assert s["lines"] == 3                                   # previous close, target, kill level
        assert s["markers"] >= 1                                 # the view in the research book
        assert p.errors() == []
    finally:
        p.close()


def test_period_buttons_move_the_chart_the_axes_and_the_return_together(chrome, live):
    base, _ = live
    p = _open(chrome, f"{base}/aksje/AAA")
    try:
        d = _data(p)
        for key in ("6m", "5a", "maks", "ytd", "1m"):
            per = next(x for x in d["periods"] if x["key"] == key)
            assert per["enough"], key
            _click(p, f'.panel[data-tab="oversikt"] button.per[data-p="{key}"]')
            s = _state(p)
            assert s["period"] == key and s["from"] == per["x0"] and s["to"] == per["x1"], key
            assert s["ret"] == pytest.approx(per["ret"], rel=1e-4) and s["color"] == ("#0b7a4b" if per["ret"] >= 0 else "#b3261e"), key
            assert p.eval("document.querySelector('.pc-ret').textContent").startswith(per["label"] + " "), key
            assert p.eval(f"document.querySelectorAll('button.per.on[data-p=\"{key}\"]').length") == 2, key   # the bar and the card
        assert s["logical"]["from"] == pytest.approx(d["t"].index(s["from"]) - 0.5, abs=0.01)
        assert p.errors() == []
    finally:
        p.close()


def test_log_scale_only_for_5a_and_maks_and_never_while_comparing(chrome, live):
    base, _ = live
    p = _open(chrome, f"{base}/aksje/AAA")
    try:
        assert p.eval("document.querySelector('[data-opt=log]').disabled")
        _click(p, '.panel[data-tab="oversikt"] button.per[data-p="maks"]')
        assert not p.eval("document.querySelector('[data-opt=log]').disabled")
        _click(p, "[data-opt=log]")
        assert _state(p)["log"] is True and _state(p)["scaleMode"] == 1
        _click(p, "[data-cmp=sector]")
        s = _state(p)
        assert s["cmp"]["sector"] and s["log"] is False and s["scaleMode"] == 0 and p.eval("document.querySelector('[data-opt=log]').disabled")
        assert "rebasert til" in p.eval("document.querySelector('.pc-ret').textContent")
        _click(p, "[data-cmp=sector]")
        _click(p, '.panel[data-tab="oversikt"] button.per[data-p="1m"]')
        assert _state(p)["log"] is False and p.eval("document.querySelector('[data-opt=log]').disabled")
    finally:
        p.close()


def test_candles_sma_comparison_and_markers_toggle(chrome, live):
    base, _ = live
    p = _open(chrome, f"{base}/aksje/AAA")
    try:
        _click(p, "[data-type=candles]")
        assert _state(p)["type"] == "candles" and _state(p)["lines"] == 3
        _click(p, "[data-type=area]")
        _click(p, "[data-sma='50']")
        _click(p, "[data-sma='200']")
        assert _state(p)["sma"] == {"50": True, "200": True}
        assert p.eval("document.querySelector('[data-cmp=osebx]').disabled")            # no OSEBX in the synthetic store
        assert "OSEBX finnes ikke i lageret" in p.eval("document.querySelector('[data-cmp=osebx]').title")
        _click(p, "[data-cmp=sector]")
        _click(p, "[data-cmp=sector]")
        _click(p, "[data-type=candles]")
        s = _state(p)
        assert (s["panes"], s["mainPane"], s["volPane"]) == (2, 0, 1), s       # every rebuild keeps prices on top, volume under
        _click(p, "[data-type=area]")
        n = _state(p)["markers"]
        _click(p, "[data-ev=vurdering]")
        assert _state(p)["markers"] == n - 1 and not _state(p)["ev"]["vurdering"]
        assert p.errors() == []
    finally:
        p.close()


def test_the_hover_box_sits_beside_the_point_never_on_it(chrome, live):
    base, _ = live
    p = _open(chrome, f"{base}/aksje/AAA")
    try:
        r = p.rect("#chart-price")
        for fx in (0.03, 0.25, 0.5, 0.75, 0.9):
            for fy in (0.15, 0.5, 0.7, 0.93):                    # 0.93 is the volume pane
                x, y = r["x"] + r["width"] * fx, r["y"] + r["height"] * fy
                p.mouse(x, y)
                assert not p.eval("document.querySelector('.pc-tip').hidden"), (fx, fy)
                t = _state(p)["tip"]
                assert abs(t["px"] - (x - r["x"])) < 3 and abs(t["py"] - (y - r["y"])) < 3, (fx, fy, t)   # the point is where the mouse is
                assert not (t["x"] <= t["px"] <= t["x"] + t["w"] and t["y"] <= t["py"] <= t["y"] + t["h"]), (fx, fy, t)
                assert t["x"] >= 0 and t["x"] + t["w"] <= r["width"] + 1, (fx, fy, t)
        txt = p.eval("document.querySelector('.pc-tip').textContent")
        assert "Sluttkurs" in txt and "Volum" in txt
    finally:
        p.close()


def test_a_chart_in_a_hidden_tab_gets_its_period_when_the_tab_opens(chrome, live):
    base, _ = live
    p = chrome.page()
    try:
        p.goto(f"{base}/aksje/AAA/verdsettelse", ready="!!window.PriceChart")
        assert p.eval("PriceChart.state().width") == 0
        _click(p, 'nav.tabs a[data-tab="oversikt"]')
        p.wait("PriceChart.state().width > 0")
        p.eval("new Promise(function(r){setTimeout(r, 150)})")
        s = _state(p)
        assert s["period"] == "1a" and s["logical"]["from"] == pytest.approx(_data(p)["t"].index(s["from"]) - 0.5, abs=0.01)
        assert p.errors() == []
    finally:
        p.close()


def test_no_console_error_on_any_tab(chrome, live):
    base, _ = live
    for code in ("AAA", "BBB"):
        for tab in TABS:
            p = chrome.page()
            try:
                p.goto(f"{base}/aksje/{code}/{tab}", ready="!!document.querySelector('nav.tabs')")
                p.eval("new Promise(function(r){setTimeout(r, 300)})")
                assert p.errors() == [], (code, tab)
            finally:
                p.close()


# ------------------------------------------------------------------------------------------------ visual baselines
def _need_baseline(*names: str) -> None:
    """Skip before opening the browser when this platform has no baselines (and none are being written)."""
    if not all(browser.has_baseline(n) for n in names):
        pytest.skip(f"no visual baseline for {names[0]} on this platform (OQ_UPDATE_VISUAL=1 writes it)")


def _compare(name: str, grid: dict, png: bytes | None = None, **tol) -> None:
    try:
        msg = browser.compare_grid(name, grid, png, **tol)
    except LookupError as e:
        pytest.skip(str(e))
    assert msg is None, msg


def _chart_grid(p, cols: int = 96) -> tuple[dict, bytes]:
    r = p.rect(".pc")
    png = p.screenshot({"x": r["x"], "y": r["y"], "width": r["width"], "height": r["height"]})
    return p.grid(png, cols), png


@pytest.mark.parametrize("setup", [("1a", "area"), ("maks", "candles"), ("5a", "sector")])
def test_visual_price_chart(chrome, live, setup):
    base, _ = live
    key, extra = setup
    _need_baseline(f"pricechart-{key}-{extra}")
    p = _open(chrome, f"{base}/aksje/AAA", scale=2)
    try:
        _click(p, f'.panel[data-tab="oversikt"] button.per[data-p="{key}"]')
        if extra == "candles":
            _click(p, "[data-type=candles]")
        elif extra == "sector":
            _click(p, "[data-cmp=sector]")
        p.eval("new Promise(function(r){setTimeout(r, 250)})")
        name = f"pricechart-{key}-{extra}"
        grid, png = _chart_grid(p)
        # About one run in six the first screenshot of a page catches the canvas before its last paint. A chart that has
        # really changed differs every time; a paint that was late does not. So a mismatch gets one more look, after
        # two animation frames, before it counts.
        if os.environ.get("OQ_UPDATE_VISUAL") != "1" and browser.has_baseline(name) and browser.compare_grid(name, grid, None) is not None:
            p.eval("new Promise(function(r){requestAnimationFrame(function(){requestAnimationFrame(function(){setTimeout(r, 400)})})})")
            grid, png = _chart_grid(p)
        _compare(name, grid, png)
    finally:
        p.close()


@pytest.mark.parametrize("tab", TABS)
def test_visual_stock_page_tab(chrome, live, tab):
    """The bar and the tab row as pixels, and the panel's layout with the text hidden – dates and today's numbers
    change, the boxes, charts and borders should not."""
    base, _ = live
    _need_baseline(f"aksjeside-bar-{tab}", f"aksjeside-panel-{tab}")
    p = _open(chrome, f"{base}/aksje/AAA/{tab}", height=1400, scale=2) if tab == "oversikt" else chrome.page()
    try:
        if tab != "oversikt":
            p.goto(f"{base}/aksje/AAA/{tab}", height=1400, scale=2, ready="!!document.querySelector('nav.tabs')")
        p.eval(f"(function(){{var s=document.createElement('style');s.textContent={json.dumps(HIDE_TEXT + '.stockbar .view,.foot,.pc-tip{visibility:hidden!important}')};document.head.appendChild(s);}})()")
        p.eval("new Promise(function(r){setTimeout(r, 300)})")
        top = p.rect(".stockbar")
        nav = p.rect("nav.tabs")
        png = p.screenshot({"x": top["x"], "y": top["y"], "width": top["width"], "height": nav["y"] + nav["height"] - top["y"]})
        # fine cells and a strict share: the active tab's 3 px underline must count
        _compare(f"aksjeside-bar-{tab}", p.grid(png, 192), png, mean_tol=1.5, cell_tol=40, cell_share=0.001)
        panel = p.rect(f'.panel[data-tab="{tab}"]')
        png = p.screenshot({"x": panel["x"], "y": panel["y"], "width": panel["width"], "height": min(panel["height"], 1300)})
        _compare(f"aksjeside-panel-{tab}", p.grid(png, 48), png)
    finally:
        p.close()
