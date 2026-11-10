"""The stock page's price chart (night 10 Nov 2026, K1–K3): the payload the browser draws, the events on the right
sessions, the target and kill lines, the comparisons, and the library served with its licence and attribution. All on
a synthetic store and a temp home – never the real research book or log."""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest

from osloquant.dashboard import market as mk
from osloquant.dashboard import pricechart as pc
from osloquant.dashboard import snapshot as sn

from .helpers import business_days
from .test_dashboard import app  # noqa: F401  the synthetic store, book and home


def _payload(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="pc-data">(.*?)</script>', html, re.S)
    assert m, "no chart payload on the page"
    return json.loads(m.group(1).replace("<\\/", "</"))


def _snap(n: int, codes=("AAA", "DDD", "EEE", "BBB"), start="2020-01-01") -> mk.Snapshot:
    rng = np.random.default_rng(3)
    dates = business_days(n, start)
    close = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n))) for c in codes}, index=dates)
    panel = dict(open=close.shift(1).fillna(close), high=close * 1.01, low=close * 0.99, close=close,
                 volume=pd.DataFrame(1000.0, index=dates, columns=close.columns))
    sectors = {"AAA": "Seafood", "DDD": "Seafood", "EEE": "Seafood", "BBB": "Other shipping"}
    return mk.Snapshot(panel, {c: c for c in codes}, {c: sectors.get(c, "Seafood") for c in codes}, dates[-1])


class View:
    def __init__(self, view):
        self.view, self.view_source = view, "research book"


# ------------------------------------------------------------------------------------------------ the page
def test_the_stock_page_draws_the_new_chart_with_the_library_its_licence_and_the_attribution(app):  # noqa: F811
    client, snap = app
    html = client.get("/aksje/AAA").get_data(as_text=True)
    assert f'<script src="/static/{pc.LIB}"></script>' in html and f'<script src="/static/{pc.SCRIPT}"></script>' in html
    assert 'id="chart-price"' in html and "js-plotly-plot" not in html.split('id="chart-price"')[0][-400:]
    assert "TradingView Lightweight Charts™ 5.2.1" in html and 'href="https://www.tradingview.com/"' in html and "Apache-2.0" in html
    assert "ingenting hentes fra TradingView" in html
    lib = client.get(f"/static/{pc.LIB}")
    assert lib.status_code == 200 and b"TradingView Lightweight Charts\xe2\x84\xa2 v5.2.1" in lib.get_data()[:200]
    assert client.get(f"/static/{pc.SCRIPT}").status_code == 200
    assert (pc.STATIC / "lightweight-charts.LICENSE").read_text(encoding="utf-8").lstrip().startswith("Apache License")
    assert "TradingView, Inc." in pc.notice()


def test_the_payload_is_plain_json_one_entry_per_session_and_the_buttons_carry_only_dates(app):  # noqa: F811
    client, snap = app
    html = client.get("/aksje/AAA").get_data(as_text=True)
    d = _payload(html)
    c = snap.panel["close"]["AAA"].dropna()
    assert len(d["t"]) == len(c) and d["t"] == sorted(set(d["t"])) and all(len(d[k]) == len(d["t"]) for k in "ohlcv")
    assert d["c"][-1] == pytest.approx(float(c.iloc[-1]), rel=1e-5) and d["prev"] == pytest.approx(float(c.iloc[-2]), rel=1e-5)
    assert all(lo <= min(o, cl) and hi >= max(o, cl) for o, hi, lo, cl in zip(d["o"], d["h"], d["l"], d["c"], strict=True))
    one = next(p for p in d["periods"] if p["key"] == "1a")
    assert one["enough"] and d["default"] == "1a" and one["ret"] == pytest.approx(float(c.iloc[-1] / c.iloc[-251] - 1), rel=1e-4)
    assert not next(p for p in d["periods"] if p["key"] == "5a")["enough"]          # 300 sessions: 5Å is honestly off
    # the buttons' data-r has the dates only, so a missing volume can never put NaN in it (funn #4)
    for r in re.findall(r"data-r='([^']*)'", html):
        assert set(json.loads(r)) == {"x0", "x1"}
    assert "NaN" not in html.split('id="pc-data">')[1].split("</script>")[0]


def test_the_chart_uses_the_whole_history_in_the_store_so_5a_and_maks_mean_what_they_say(monkeypatch):
    snap = _snap(300, start="2025-06-02")
    long = _snap(1600, start="2020-01-01")
    full = pd.DataFrame({k: long.panel[k]["AAA"] for k in ("open", "high", "low", "close", "volume")})
    monkeypatch.setattr(pc, "_store_bars", lambda code, key: full)
    d = pc.payload(snap, "AAA")
    assert d["t"][0] == "2020-01-01" and len(d["t"]) == 1600
    five, maks = (next(p for p in d["periods"] if p["key"] == k) for k in ("5a", "maks"))
    assert five["enough"] and five["sessions"] == 1250 and maks["x0"] == "2020-01-01"


def test_history_falls_back_to_the_snapshot_and_repairs_impossible_bars(monkeypatch):
    snap = _snap(50)
    snap.panel["open"].iloc[5, 0] = 0.0
    snap.panel["high"].iloc[6, 0] = 1.0                      # below the close
    monkeypatch.setattr(pc, "_store_bars", lambda code, key: pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))
    h = pc.history(snap, "AAA")
    assert len(h) == 50 and h["open"].iloc[5] == h["close"].iloc[5]
    assert (h["high"] >= h[["open", "close"]].max(axis=1)).all() and (h["low"] <= h[["open", "close"]].min(axis=1)).all()


# ------------------------------------------------------------------------------------------------ events and lines
def test_events_land_on_the_next_session_and_only_oscars_rows_count():
    idx = pd.bdate_range("2026-01-05", "2026-03-31")
    cal = {"companies": {"AAA": {"events": [{"date": "2026-02-07", "what": "Quarterly Report - Q4"},       # a Saturday
                                            {"date": "2026-02-20", "what": "Annual General Meeting"},     # not a report
                                            {"date": "2026-05-12", "what": "Quarterly Report - Q1"}]}}}   # after the last bar
    divs = [{"date": "2026-03-02", "dividend": 2.5, "split": 0}, {"date": "2026-01-15", "dividend": 0, "split": 2.0}]
    ins = [{"time": "2026-02-10T15:00:00Z", "side": "buy", "title": "CEO buys 10 000 shares"}, {"time": "2026-02-11T09:00:00Z", "side": "programme", "title": "LTIP"}]
    rows = [{"kind": "judgement", "code": "AAA", "date": "2026-01-20", "target": 120, "price": 100, "seq": 1},
            {"kind": "judgement", "code": "AAA", "date": "2026-01-21", "target": 99, "price": 100, "seq": 2, "analyst": "claude"},
            {"kind": "note", "code": "AAA", "date": "2026-01-22", "text": "x", "seq": 3}]
    case = View({"date": "2026-03-10", "target": 130})
    ev = pc.events("AAA", idx, case, divs, ins, [{"date": "2026-02-09", "title": "Q4 report"}], cal, rows)
    kinds = [(e["t"], e["k"]) for e in ev]
    assert ("2026-02-09", "rapport") in kinds and sum(k == "rapport" for _, k in kinds) == 1     # Saturday → Monday, merged with the download
    assert not any("General Meeting" in e["txt"] or "Q1" in e["txt"] for e in ev)
    div = next(e for e in ev if e["k"] == "utbytte" and "Eks-utbytte" in e["txt"])
    assert div["t"] == "2026-03-02" and "NOK 2,50" in div["txt"] and any("Aksjesplitt 2:1" in e["txt"] for e in ev)
    buys = [e for e in ev if e["k"] == "innside"]
    assert buys[0]["side"] == "buy" and "side" not in buys[1] and "kjøp" in buys[0]["txt"]
    mine = [e for e in ev if e["k"] == "vurdering"]
    assert [e["t"] for e in mine] == ["2026-01-20", "2026-03-10"] and "kursmål NOK 120,00" in mine[0]["txt"]
    assert kinds == sorted(kinds)


def test_target_and_kill_lines_carry_the_distance_from_todays_price():
    ls = pc.lines(View({"date": "2026-01-05", "target": 120, "bear": 70}), 100.0)
    assert [(ln["k"], ln["p"]) for ln in ls] == [("target", 120.0), ("kill", 70.0)]
    assert ls[0]["dist"] == pytest.approx(0.2) and ls[1]["dist"] == pytest.approx(-0.3)
    assert "bear-verdien" in ls[1]["src"] and "EST" in ls[0]["src"]
    assert pc.lines(View({"date": "2026-01-05", "target": 120, "kill_level": 85}), 100.0)[1]["p"] == 85.0
    assert pc.lines(None, 100.0) == [] and pc.lines(View({"rating": "HOLD"}), 100.0) == []


def test_the_card_shows_the_lines_with_a_real_minus_and_the_counts_on_the_event_buttons():
    snap = _snap(300)
    d = pc.payload(snap, "AAA", View({"date": "2020-06-01", "target": 1e6, "bear": 1.0}))
    html = pc.card_html(d)
    assert "Kursmål" in html and "Kill-nivå" in html and "−" in html and "fra dagens kurs" in html
    assert re.search(r'data-ev="vurdering"[^>]*class="ev-vurdering on"', html) and 'data-ev="innside" class="ev-innside"' in html
    assert 'data-ev="rapport" class="ev-rapport" aria-pressed="false" title="' in html and "Ingen i lageret" in html


# ------------------------------------------------------------------------------------------------ comparisons
def test_sector_index_is_the_mean_daily_return_of_the_members_chained():
    idx = pd.bdate_range("2026-01-05", periods=4)
    closes = pd.DataFrame({"A": [100, 110, 110, 121], "B": [50, 50, None, 55], "C": [None, None, 10, 11]}, index=idx, dtype=float)
    s = pc.sector_index(closes)
    assert s.iloc[0] == 1.0 and s.iloc[1] == pytest.approx(1.05)                 # (+10 % + 0 %) / 2
    assert s.iloc[2] == pytest.approx(1.05)                                      # one return only: the day adds nothing
    assert s.iloc[3] == pytest.approx(1.05 * (1 + (0.10 + 0.10) / 2))            # B has no close the day before
    assert pc.sector_index(closes[["A"]]).empty


def test_comparisons_say_why_one_is_off(monkeypatch):
    snap = _snap(300)
    monkeypatch.setattr(pc, "_osebx_store", lambda key: pd.Series(dtype=float))
    monkeypatch.setattr(pc, "_closes_store", lambda codes, key: pd.DataFrame())
    out = pc.comparisons(snap, "AAA", snap.panel["close"].index)
    assert "osebx" in out["off"] and "oq record" in out["off"]["osebx"]
    sec = out["cmp"]["sector"]
    assert "2 andre aksjer" in sec["label"] and "DDD, EEE" in sec["src"] and "egen beregning" in sec["src"] and len(sec["v"]) == 300
    alone = pc.comparisons(snap, "BBB", snap.panel["close"].index)
    assert "sector" not in alone["cmp"] and "for få andre aksjer" in alone["off"]["sector"]


def test_the_static_copy_carries_the_chart_scripts():
    assert sn.fname(f"/static/{pc.LIB}") == pc.LIB and sn.fname("/static/pricechart.js") == "pricechart.js"
    assert sn.fname("/static/plotly.min.js") == "plotly.min.js"
