"""The macro picture (DECISIONS D65, D66): the strip's cells, the sensitivity measured on synthetic data with a known
answer, the feed that keeps what it could not fetch, the page, the stock card, and the menu with «Mer»."""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest

from osloquant.dashboard import feeds as fd
from osloquant.dashboard import macro as mc
from osloquant.dashboard import macropage as mp
from osloquant.dashboard import render as rd
from osloquant.dashboard import sources as src
from osloquant.dashboard.tall import MINUS, NBSP

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home


def _days(n: int, end: str = "2026-11-09") -> pd.DatetimeIndex:
    return pd.bdate_range(end=end, periods=n)


def _series(n: int = 800, seed: int = 1) -> dict[str, pd.Series]:
    """Synthetic drivers: a rate that steps twice, a rate that moves every day, an oil price and an index."""
    rng = np.random.default_rng(seed)
    d = _days(n)
    out = {k: pd.Series(dtype=float) for k in mc.BY_KEY}
    out["styringsrente"] = pd.Series([4.0] * (n // 2) + [4.25] * (n // 4) + [4.5] * (n - n // 2 - n // 4), index=d)
    out["stat10y"] = pd.Series(4.0 + np.cumsum(rng.normal(0, 0.02, n)), index=d)
    out["brent"] = pd.Series(80 * np.exp(np.cumsum(rng.normal(0, 0.015, n))), index=d)
    out["osebx"] = pd.Series(1500 * np.exp(np.cumsum(rng.normal(0.0003, 0.008, n))), index=d)
    return out


# ------------------------------------------------------------------------------------------------ the strip
def test_a_cell_states_the_change_the_way_its_driver_is_read():
    s = _series()
    rate = mc.cell(mc.BY_KEY["styringsrente"], s["styringsrente"])
    assert rate["level"] == 4.5 and rate["d1"] == 0 and rate["y1"] == pytest.approx(0.25)          # percentage points for a rate
    assert mc.fmt_change(mc.BY_KEY["styringsrente"], 0.25) == f"+0,25{NBSP}pp" and mc.fmt_level(mc.BY_KEY["styringsrente"], 4.5) == f"4,50{NBSP}%"
    oil = mc.cell(mc.BY_KEY["brent"], s["brent"])
    assert oil["d1"] == pytest.approx(float(s["brent"].iloc[-1] / s["brent"].iloc[-2] - 1))          # a fraction for a price
    assert mc.fmt_change(mc.BY_KEY["brent"], -0.014) == f"{MINUS}1,4{NBSP}%" and len(oil["spark"]) == 90
    month_back = s["brent"][s["brent"].index <= s["brent"].index[-1] - pd.DateOffset(months=1)].iloc[-1]
    assert oil["m1"] == pytest.approx(float(s["brent"].iloc[-1] / month_back - 1))                   # a calendar month, like the period buttons
    assert mc.cell(mc.BY_KEY["laks"], pd.Series(dtype=float))["empty"]


def test_the_strip_has_one_cell_per_driver_and_says_when_one_is_not_fetched():
    html = mc.strip_html(_series())
    assert html.count('class="mcell') == len(mc.STRIP) == 8
    assert 'href="/makro#d-brent"' in html and "<polyline" in html and "Kilde: Yahoo Finance (BZ=F), forsinket" in html
    assert "ikke hentet" in html and "Laksepris" in html                   # a driver with no data is shown as such, never left out
    static = mc.strip_html(_series(), static=True)
    assert "<a " not in static and static.count('class="mcell') == 8       # the evening copy has no links into the live dashboard


def test_a_trend_line_is_green_up_and_red_down():
    assert "var(--buy)" in mc.sparkline([1, 2, 3]) and "var(--risk)" in mc.sparkline([3, 2, 1]) and mc.sparkline([1]) == ""
    assert "var(--muted)" in mc.sparkline([2, 3, 2])


# ------------------------------------------------------------------------------------------------ sensitivity
def test_the_sensitivity_finds_the_exposure_that_was_built_in_and_nothing_where_there_is_none():
    s = _series()
    rng = np.random.default_rng(7)
    d = s["brent"].index
    oil, mkt = np.log(s["brent"]).diff().fillna(0), np.log(s["osebx"]).diff().fillna(0)
    noise = lambda: rng.normal(0, 0.01, len(d))  # noqa: E731
    closes = pd.DataFrame({
        "OIL": 100 * np.exp(np.cumsum(1.0 * mkt + 0.5 * oil + noise())),            # half the oil price, on top of the market
        "MKT": 100 * np.exp(np.cumsum(1.0 * mkt + noise())),                        # the market only
        "NEG": 100 * np.exp(np.cumsum(0.8 * mkt - 0.4 * oil + noise())),
    }, index=d)
    t = mc.sensitivity(closes, s).set_index(["code", "driver"])
    assert t.loc[("OIL", "brent"), "t"] > 6 and t.loc[("OIL", "brent"), "beta"] == pytest.approx(0.5 * np.log(1.1) * 100, rel=0.25)   # per +10 % in the driver
    assert t.loc[("NEG", "brent"), "t"] < -5 and t.loc[("NEG", "brent"), "beta"] < 0
    assert abs(t.loc[("MKT", "brent"), "t"]) < mc.FOLLOWS                             # no exposure built in, none found
    assert t.loc[("MKT", "osebx"), "beta"] == pytest.approx(np.log(1.1) * 100, rel=0.2)
    assert "styringsrente" not in t.index.get_level_values("driver")                  # two steps in three years: not measured
    assert mc.measurable(s) == {"stat10y", "brent", "osebx"}
    rows = mc.for_stock("OIL", t.reset_index(), s)
    assert [r["driver"] for r in rows] == ["brent"] and rows[0]["strength"] == "sterk" and rows[0]["cell"]["level"] == pytest.approx(float(s["brent"].iloc[-1]))
    assert mc.for_stock("MKT", t.reset_index(), s) == []                              # the market itself is never «a driver the stock follows»
    m = mc.sector_matrix(t.reset_index(), {"OIL": "Energy", "NEG": "Finance", "MKT": "Finance"}).set_index(["group", "driver"])
    assert m.loc[("Energy", "brent"), "follow"] == 1 and m.loc[("Finance", "brent"), "follow"] == 1 and m.loc[("Finance", "brent"), "n"] == 2


def test_too_little_history_gives_no_sensitivity():
    s = {k: v.iloc[-100:] for k, v in _series().items()}                               # twenty weeks
    assert mc.sensitivity(pd.DataFrame({"A": s["brent"]}), s).empty
    assert mc.sensitivity(pd.DataFrame(), _series()).empty


# ------------------------------------------------------------------------------------------------ the feed
def test_the_macro_feed_keeps_what_it_could_not_fetch_and_names_it(home, monkeypatch):
    hist = {"t": ["2026-11-06", "2026-11-09"], "v": [1.0, 2.0]}
    monkeypatch.setattr(fd, "_nb_history", lambda flow, n=fd.MACRO_OBS: hist)
    monkeypatch.setattr(fd, "_yahoo_histories", lambda symbols: {k: hist for k in symbols if k != "gass_ttf"})
    monkeypatch.setattr(fd, "_salmon_history", lambda weeks=160: hist)
    monkeypatch.setattr(fd, "_power_history", lambda old, today=None: hist)
    doc = fd.fetch_macro()
    assert set(doc["series"]) == (set(fd.MACRO_NB) | set(fd.MACRO_YAHOO) | {"laks", "kraft_no2"}) - {"gass_ttf"}
    assert doc["errors"] == ["gass_ttf: ingen data fra Yahoo"]
    fd.write("macro", doc)

    def down(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(fd, "_nb_history", down)                                       # Norges Bank is down the next evening
    doc2 = fd.fetch_macro()
    assert doc2["series"]["styringsrente"] == hist and any(e.startswith("styringsrente: TimeoutError") for e in doc2["errors"])
    for name in ("_yahoo_histories", "_salmon_history", "_power_history"):
        monkeypatch.setattr(fd, name, down)
    (fd.cache_dir() / "macro.json").unlink()
    with pytest.raises(RuntimeError):                                                  # nothing at all: the feed fails, and the source list says so
        fd.fetch_macro()
    assert "macro" in fd.FEEDS and src.BY_KEY["macro"].cadence == "daily"


def test_power_prices_are_built_a_few_days_at_a_time(home, monkeypatch):
    from datetime import date

    asked = []

    def get(url, **k):
        asked.append(url)
        return json.dumps([{"NOK_per_kWh": 1.0}, {"NOK_per_kWh": 3.0}]).encode()

    monkeypatch.setattr(fd, "_get", get)
    out = fd._power_history(None, today=date(2026, 11, 10))
    assert len(asked) == fd.POWER_DAYS_PER_RUN and out["t"][-1] == "2026-11-10" and out["v"][-1] == 200.0      # the day's mean in øre/kWh
    assert "/2026/11-10_NO2.json" in asked[0]
    asked.clear()
    again = fd._power_history(out, today=date(2026, 11, 11))
    assert len(asked) == 1 and len(again["t"]) == fd.POWER_DAYS_PER_RUN + 1                                   # only the new day is asked for


# ------------------------------------------------------------------------------------------------ the pages
def _write_feed(s: dict[str, pd.Series]) -> None:
    fd.write("macro", {"series": {k: {"t": [f"{d:%Y-%m-%d}" for d in v.index], "v": [float(x) for x in v]} for k, v in s.items() if len(v) and k != "osebx"},
                       "errors": [], "source": "test"})


def test_the_macro_page_the_front_page_strip_and_the_menu(app):  # noqa: F811
    client, _ = app
    _write_feed(_series())
    page = client.get("/makro")
    html = page.get_data(as_text=True)
    assert page.status_code == 200 and "<h1>Makro</h1>" in html and 'id="makrostripe"' in html
    for d in mc.DRIVERS:
        assert f'id="d-{d.key}"' in html, d.key
    assert 'class="mc" data-key="brent"' in html and 'id="mc-data"' in html and f"/static/{mp.MINI_SCRIPT}" in html
    assert set(json.loads(re.search(r'id="mc-data">(.*?)</script>', html, re.S).group(1))) >= {"brent", "stat10y", "styringsrente"}
    assert "Ikke hentet ennå" in html                                                  # the drivers with nothing in the feed say so
    assert "Hvem følger hva" in html and "ikke årsak og ikke en prognose" in html and "TradingView Lightweight Charts" in html
    assert client.get(f"/static/{mp.MINI_SCRIPT}").status_code == 200
    front = client.get("/").get_data(as_text=True)
    assert 'id="makrostripe"' in front and front.index('id="makrostripe"') < front.index("Dette krever en vurdering")
    # the menu: the daily pages in the bar, the rest under «Mer», and nothing gone
    bar = front.split('<span class="links">')[1].split("</nav>")[0]
    top, more = bar.split("<details")[0], bar.split("<details")[1]
    assert [h for h, _ in rd.NAV_TOP] == re.findall(r'href="([^"]+)"', top)
    assert all(f'href="{h}"' in more for h, _ in rd.NAV_MORE) and "<summary>Mer</summary>" in more
    for href, _label in rd.NAV:
        assert client.get(href).status_code == 200, href
    assert "<summary>Mer · Datahelse</summary>" in client.get("/health").get_data(as_text=True)
    assert 'class="more on"' in client.get("/funds").get_data(as_text=True) and 'class="more on"' not in front


def test_the_stock_page_has_the_macro_card_and_says_so_when_nothing_is_followed(app, monkeypatch):  # noqa: F811
    client, snap = app
    s = _series(len(snap.panel["close"]))
    row = {"code": "AAA", "driver": "brent", "beta": 3.9, "t": 9.6, "corr": 0.7, "n": 156}
    monkeypatch.setattr(mc, "for_stock", lambda code, *a, **k: [row | {"name": "Brent", "step": 10.0, "kind": "price", "strength": "sterk",
                                                                      "cell": mc.cell(mc.BY_KEY["brent"], s["brent"])}] if code == "AAA" else [])
    html = client.get("/aksje/AAA/oversikt").get_data(as_text=True)
    card = html.split('id="makro-aksje"')[1][:2500]
    assert "Makro som betyr noe for denne aksjen" in card and 'href="/makro#d-brent"' in card and "sterk" in card and f"+3,9{NBSP}%" in card
    assert "ikke en prognose" in card
    none = client.get("/aksje/BBB/oversikt").get_data(as_text=True).split('id="makro-aksje"')[1][:700]
    assert "Ingen av driverne vi følger har forklart" in none
