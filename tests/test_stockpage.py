"""The stock page as a sticky bar and seven tabs (D57): every old block is still on the page, the active tab is in the
URL, the technical rows carry odds and never a label, every new number has its source in a hover title."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from osloquant.dashboard import charts as ch
from osloquant.dashboard import technicals as tc
from tests.test_dashboard import GOOD, app  # noqa: F401


def test_every_tab_is_in_the_page_and_the_url_picks_the_active_one(app):  # noqa: F811
    client, _ = app
    page = client.get("/stock/AAA").get_data(as_text=True)
    for t in ("oversikt", "regnskap", "verdsettelse", "teknisk", "rapporter", "eiere", "vurdering"):
        assert f'data-tab="{t}"' in page
    assert 'data-tab="oversikt" id="tab-oversikt">' in page and 'data-tab="regnskap" id="tab-regnskap" hidden>' in page
    reg = client.get("/aksje/AAA/regnskap/resultat").get_data(as_text=True)
    assert 'data-tab="regnskap" id="tab-regnskap">' in reg and 'data-tab="oversikt" id="tab-oversikt" hidden>' in reg
    assert 'data-sub="resultat" class="on"' in reg
    assert client.get("/aksje/AAA/ikkeenfane").status_code == 404 and client.get("/aksje/AAA/regnskap/nei").status_code == 404
    # the old blocks are all still there: form, light case, kill list, insiders, reports, technicals, news
    for s in ("Ny vurdering", 'action="/stock/AAA/judge"', "Signaler siste 10 økter", "Meldinger og nyheter", "Innsidehandler", "Mine rapporter",
              "Største aksjonærer", "Nøkkeltall i dag", "Sum-of-the-parts", "Segmenter", "Utbytte", "Før du kjøper"):
        assert s in page, s
    # a form that was sent opens the judgement tab
    r = client.post("/stock/BBB/judge", data=GOOD)
    assert r.status_code == 303
    after = client.get(r.headers["Location"].split("http://localhost", 1)[-1]).get_data(as_text=True)
    assert 'data-tab="vurdering" id="tab-vurdering">' in after and "er lagret som rad #" in after


def test_the_bar_says_delayed_and_the_new_numbers_carry_their_source(app):  # noqa: F811
    client, snap = app
    page = client.get("/stock/AAA").get_data(as_text=True)
    assert 'class="delayed"' in page and "forsinket" in page
    assert 'class="stat">Research book</span>' in page
    bare = client.get("/stock/CCC").get_data(as_text=True)
    assert "Ikke fulgt" in bare
    # every tile in the key grid and every technical value has a hover title with its source
    grid = page.split('class="kgrid"', 1)[1].split('<div class="src">', 1)[0]
    tiles = re.findall(r'<div class="kvv">(.*?)</div>', grid)
    assert len(tiles) >= 8 and all('class="nv" title="' in t for t in tiles)
    tech = page.split("<h3>Indikatorer</h3>", 1)[1].split("</table>", 1)[0]
    assert "Yahoo Finance, forsinket" in tech and "ingen målt odds" in tech
    # no buy / sell / neutral label anywhere in the technical tab
    tab = page.split('id="tab-teknisk"', 1)[1].split('id="tab-rapporter"', 1)[0]
    for word in ("KJØP", "SELG", "NØYTRAL", ">BUY<", ">SELL<", "NEUTRAL"):
        assert word not in tab, word
    # the period buttons: 1D disabled, the rest carry ranges
    assert 'class="per" disabled' in page and 'data-p="1a"' in page and 'data-p="maks"' in page


def test_technical_rows_value_odds_and_count_but_no_label():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2022-01-03", periods=400)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 400))), idx)
    vol = pd.Series(rng.integers(1000, 5000, 400).astype(float), idx)
    high = close * 1.01
    odds = {"measured": {"round_trip_cost": 0.005, "from": "2010", "to": "2026"},
            "signals": {"Golden cross MA 20/60": {"exc20": 0.004, "exc60": 0.01, "hit20": 0.5, "events": 1200, "robustness": {"grade60": "A"}},
                        "Death cross MA 20/60": {"exc20": -0.004, "exc60": -0.01, "hit20": 0.45, "events": 1100, "robustness": {"grade60": "B"}}}}
    rows = tc.rows(close, vol, high, odds_doc=odds)
    labels = [r.label for r in rows]
    for want in ("SMA 20", "SMA 50", "SMA 200", "MA 20/60", "RSI 14", "MACD 12/26/9", "52 ukers høy", "60 dagers høy", "60 dagers lav", "Kanal 120 d", "Volum mot snitt"):
        assert want in labels, want
    ma = next(r for r in rows if r.label == "MA 20/60")
    assert ma.signal in ("Golden cross MA 20/60", "Death cross MA 20/60") and ma.odds["n"] in (1200, 1100) and ma.odds["grade60"] in ("A", "B")
    rsi = next(r for r in rows if r.label == "RSI 14")
    assert rsi.signal is None and rsi.odds == {} and 0 <= float(rsi.value) <= 100
    text = " ".join(f"{r.label} {r.value} {r.detail}" for r in rows)
    for word in ("KJØP", "SELG", "NØYTRAL", "BUY", "SELL"):
        assert word not in text.upper() or word in ("BUY", "SELL") and word not in text, word
    line, sig, hist = tc.macd(close)
    assert abs(float((line - sig - hist).abs().max())) < 1e-9


def test_period_ranges_cover_the_buttons_and_the_ytd_base_is_last_years_close():
    idx = pd.bdate_range("2024-01-02", periods=600)
    c = pd.Series(np.linspace(50, 100, 600), idx)
    rs = ch.period_ranges(c)
    assert [r["label"] for r in rs] == ["5D", "1M", "6M", "YTD", "1Å", "5Å", "Maks"]
    ytd = next(r for r in rs if r["key"] == "ytd")
    assert ytd["x0"].endswith("-12-31") or pd.Timestamp(ytd["x0"]).year == idx[-1].year - 1
    five = next(r for r in rs if r["key"] == "5a")
    assert five["enough"] is False and next(r for r in rs if r["key"] == "1a")["enough"] is True
    assert all(r["y0"] < r["y1"] for r in rs) and next(r for r in rs if r["key"] == "maks")["ret"] > 0.9


def test_live_multiples_and_dividends_from_the_light_case_and_actions():
    from osloquant.dashboard import stockpage as sp

    lc = {"shares": 100e6, "currency": {"reporting": "NOK", "fx": None}, "built_at": "2026-11-01T00:00:00Z",
          "profit": {"net_income": {"value": 500e6, "period": "LTM to 2026-09-30"}, "revenue": {"value": 5e9, "period": "LTM to 2026-09-30"}},
          "balance": {"equity": 2e9, "minority": 0, "date": "2026-09-30"}}
    m = sp.live_multiples(lc, 50.0)
    assert m["mcap_nok"] == 5e9 and round(m["pe"], 2) == 10.0 and round(m["ps"], 2) == 1.0 and round(m["pb"], 2) == 2.5 and m["eps"] == 5.0
    assert "kurs 50.00" in m["src_pe"] and "Yahoo" in m["src_shares"]
    divs = [{"date": "2025-05-02", "dividend": 1.0}, {"date": "2026-03-04", "dividend": 1.5}, {"date": "2026-08-24", "dividend": 0.5}]
    total, last = sp._dividends_12m(divs, pd.Timestamp("2026-11-04"))
    assert total == 2.0 and last == "2026-08-24"


def test_dates_are_written_in_norwegian_everywhere_a_person_reads_them(app):  # noqa: F811
    from osloquant.dashboard import dates as dt

    assert dt.dato("2026-11-09") == "9. nov. 2026" and dt.dato(pd.Timestamp("2026-03-04"), False) == "4. mars"
    assert dt.dato("2026-11-09", weekday=True) == "mandag 9. nov. 2026" and dt.maaned("2026-10-01") == "okt. 2026"
    assert dt.dato_tid("2026-11-05T17:43:04Z") == "5. nov. 18:43"                     # UTC shown as Oslo time
    assert dt.dato(None) == "" and dt.dato("ikke en dato") == "ikke en dato"
    client, _ = app
    page = client.get("/aksje/AAA").get_data(as_text=True)
    assert "Plotly.register({moduleType:'locale',name:'no'" in page and "setPlotConfig({locale:'no'})" in page
    assert '"value":"%-d. %b"' in page                                                # date ticks as «27. sep.»
    bar = page.split('class="stockbar"', 1)[1].split('<nav class="tabs"', 1)[0]
    assert re.search(r"sluttkurs \d{1,2}\. (jan\.|feb\.|mars|april|mai|juni|juli|aug\.|sep\.|okt\.|nov\.|des\.) \d{4}", bar)
    visible = re.sub(r"<[^>]+>", " ", bar)                                            # data-r keeps ISO for the script
    assert not re.search(r"\d{4}-\d{2}-\d{2}", visible)                              # no ISO date a person reads in the bar
    for eng in ("Jan ", "Feb ", "Mar ", "Apr ", "Jun ", "Jul ", "Aug ", "Sep ", "Oct ", "Nov ", "Dec ", "Monday", "Friday"):
        assert eng not in visible, eng


def test_the_last_date_pass_changes_what_is_read_never_what_is_sent():
    from osloquant.dashboard.dates import norske_datoer

    html = ('<p>Logget 2026-10-22T08:47:16Z, rapport 2026-11-02, hentet 2026-11-09 17:47:07 UTC, publisert 2026-10-22 15:00.</p>'
            '<a href="/report/SATS/2026-11-02.pdf" data-r=\'{"x0": "2026-09-17"}\'>estimates_2026-11-02.json</a>'
            '<textarea name="kill">Pris under 30 innen 2026-12-31</textarea><script>var d="2026-01-01";</script><code>2026-02-03</code>'
            '<td>2026-13-45</td>')
    out = norske_datoer(html)
    assert "Logget 22. okt. 2026 10:47," in out                                       # UTC stamp in Oslo time (summer)
    assert "rapport 2. nov. 2026," in out and "hentet 9. nov. 2026 18:47," in out and "publisert 22. okt. 2026 15:00." in out
    assert 'href="/report/SATS/2026-11-02.pdf"' in out and '"x0": "2026-09-17"' in out   # attributes untouched
    assert "estimates_2026-11-02.json" in out                                          # file names untouched
    assert "innen 2026-12-31</textarea>" in out and 'var d="2026-01-01"' in out and "<code>2026-02-03</code>" in out
    assert "<td>2026-13-45</td>" in out                                                # not a date: left as written
