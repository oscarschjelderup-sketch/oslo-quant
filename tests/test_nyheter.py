"""News that matters first (DECISIONS D67): the weight of an item, the session it belongs to, the price reaction, the
ranked list on the front page, the day-by-day list and the chart markers on the stock page. Synthetic store, temp home."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from osloquant.dashboard import feeds as fd
from osloquant.dashboard import news as nw
from osloquant.dashboard import pricechart as pc

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home

INSIDE = "INSIDE INFORMATION"
ROUTINE = "ACQUISITION OR DISPOSAL OF AN ISSUER'S OWN SHARES"


def _ann(mid: int, code: str, title: str, when: str, category: str = "NON-REGULATORY PRESS RELEASES") -> dict:
    return {"id": mid, "code": code, "issuer": code, "title": title, "time": when, "category": category, "url": f"https://newsweb.oslobors.no/message/{mid}"}


@pytest.mark.parametrize(("title", "category", "weight", "kind"), [
    ("Alpha ASA: Contract award", INSIDE, 5, "innsideinformasjon"),
    ("Alpha ASA: Third quarter 2026 results", "NON-REGULATORY PRESS RELEASES", 5, "rapport"),
    ("Alpha ASA – kvartalsrapport 3. kvartal", "HALF YEAR FINANCIAL REPORT", 5, "rapport"),
    ("Alpha ASA: Private placement successfully completed", INSIDE, 5, "emisjon"),
    ("Alpha ASA: Mandatory notification of trade", "MANAGERS’ TRANSACTION", 3, "innsidehandel"),
    ("Flagging in Alpha ASA", "MAJOR SHAREHOLDINGS NOTIFICATION", 3, "flagging"),
    ("Alpha ASA: status for tilbakekjøpsprogram etter uke 45", ROUTINE, 1, "egne aksjer"),
    ("Alpha ASA: Invitation to presentation of Q3 2026 results", "ADDITIONAL REGULATED INFORMATION REQUIRED TO BE DISCLOSED UNDER THE LAWS OF A MEMBER STATE", 1, "børsmelding"),
    ("Alpha ASA: Interest adjustment", "ADJUSTMENT OF INTEREST RATE", 0, "obligasjonsrente"),
    ("Alpha ASA: Something else", "UNKNOWN CATEGORY", 2, "børsmelding"),
])
def test_the_kind_and_base_weight_of_an_announcement(title, category, weight, kind):
    assert nw.kind_of({"title": title, "category": category}) == (weight, kind)


def test_a_headline_from_a_newspaper_has_the_papers_name_as_its_kind():
    assert nw.kind_of({"title": "Alpha stiger", "outlet": "E24"}) == (nw.MEDIA_WEIGHT, "E24")


def test_an_item_belongs_to_the_session_it_could_move():
    idx = pd.DatetimeIndex(["2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"])
    assert nw.session_of("2026-11-06T07:00:00Z", idx) == pd.Timestamp("2026-11-06")           # before the open: the same day
    assert nw.session_of("2026-11-06T15:20:00Z", idx) == pd.Timestamp("2026-11-06")           # 16:20 Oslo: still that session
    assert nw.session_of("2026-11-06T15:40:00Z", idx) == pd.Timestamp("2026-11-09")           # 16:40 Oslo on a Friday: Monday
    assert nw.session_of("2026-11-07T10:00:00Z", idx) == pd.Timestamp("2026-11-09")           # a Saturday
    assert nw.session_of("2026-11-12T10:00:00Z", idx) is None and nw.session_of("rubbish", idx) is None


def test_the_reaction_measures_the_session_against_the_stocks_own_moves(app):  # noqa: F811
    _, snap = app
    c = snap.panel["close"]["AAA"].dropna().copy()
    day = c.index[-3]
    i = c.index.get_loc(day)
    usual = float(c.pct_change().iloc[i - 60:i].std())
    c.iloc[i:] = c.iloc[i:] * (1 + 5 * usual) / (c.iloc[i] / c.iloc[i - 1])               # that session: five ordinary moves up
    r = nw.reaction(c, day)
    assert r["ret"] == pytest.approx(5 * usual, rel=1e-6) and r["z"] == pytest.approx(5.0, rel=1e-6)
    assert nw.reaction(c, c.index[5]) is None and nw.reaction(c, pd.Timestamp("2030-01-01")) is None
    it = nw.weigh(_ann(1, "AAA", "Alpha ASA: Contract", f"{day:%Y-%m-%d}T08:00:00Z", INSIDE), c, in_book=True)
    assert it["weight"] == 5 + 3 + nw.BOOK_BONUS and it["level"] == 3
    assert any("ganger et vanlig dagsutslag" in x for x in it["reasons"]) and "i research book" in it["reasons"]
    quiet = nw.weigh(_ann(2, "AAA", "Alpha ASA: buy-back", f"{c.index[-10]:%Y-%m-%d}T08:00:00Z", ROUTINE), c, watched=True)
    assert quiet["weight"] == 1 + nw.WATCH_BONUS and quiet["level"] == 1 and quiet["reasons"] == ["på overvåkningslisten"]


def _feeds(snap, now: datetime) -> None:
    d = lambda back, hm="08:00": f"{snap.panel['close'].index[-1 - back]:%Y-%m-%d}T{hm}:00Z"  # noqa: E731
    fd.write("announcements", {"items": [
        _ann(1, "AAA", "Alpha ASA: status for tilbakekjøpsprogram", d(0, "08:05"), ROUTINE),
        _ann(2, "AAA", "Alpha ASA: Contract award worth NOK 500 million", d(1), INSIDE),
        _ann(3, "AAA", "Alpha ASA: Kontraktstildeling på 500 millioner kroner", d(1), INSIDE),          # the same message in Norwegian
        _ann(4, "BBB", "Beta Shipping ASA: Private placement completed", d(0), INSIDE),
        _ann(5, "CCC", "Gamma ASA: Financial calendar", d(0)),
    ]})
    fd.write("news", {"items": [{"title": "Alpha vinner storkontrakt", "link": "https://e24.no/x", "time": d(1, "09:00"), "outlet": "E24"},
                                {"title": "Ingen selskaper nevnt her", "link": "https://e24.no/y", "time": d(0), "outlet": "E24"}]})


def test_the_ranked_list_puts_what_matters_first_and_keeps_one_language(app):  # noqa: F811
    _, snap = app
    now = datetime.combine(snap.panel["close"].index[-1].date(), datetime.min.time(), tzinfo=UTC).replace(hour=20)
    _feeds(snap, now)
    out = nw.ranked(snap, {"AAA", "BBB", "CCC"}, book={"AAA"}, days=3, now=now)
    titles = [x["title"] for x in out]
    assert titles[0].startswith("Alpha ASA: Kontraktstildeling") and "Alpha ASA: Contract award worth NOK 500 million" not in titles     # one per minute, the Norwegian one
    assert titles.index("Beta Shipping ASA: Private placement completed") < titles.index("Alpha vinner storkontrakt")                 # a share issue outweighs a headline
    assert titles[-1] == "Gamma ASA: Financial calendar" or titles[-1].startswith("Alpha ASA: status")                                # routine last
    assert [x["weight"] for x in out] == sorted((x["weight"] for x in out), reverse=True)
    assert all(x["code"] != "CCC" or x["weight"] <= 2 for x in out)
    assert nw.ranked(snap, {"AAA"}, days=3, now=now, limit=1)[0]["code"] == "AAA"


def test_the_front_page_shows_the_ranked_news_under_the_strip(app):  # noqa: F811
    client, snap = app
    stamp = (datetime.now(UTC) - pd.Timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:00Z")        # the front page counts three days back from now
    fd.write("announcements", {"items": [_ann(1, "AAA", "Alpha ASA: Contract award", stamp, INSIDE), _ann(2, "BBB", "Beta: buy-back", stamp, ROUTINE)]})
    html = client.get("/").get_data(as_text=True)
    assert 'id="nyheter"' in html and "Nyheter som betyr noe" in html
    assert html.index('id="makrostripe"') < html.index('id="nyheter"') < html.index("Dette krever en vurdering")
    block = html.split('id="nyheter"')[1].split("</div></div>")[0]
    assert "innsideinformasjon" in block and "i research book" in block and "ikke hva som bør gjøres" in html
    assert "Børsmeldinger – research book og overvåkning" not in html                      # the clock-ordered list is replaced, not duplicated


def test_the_stock_page_groups_news_by_session_and_marks_the_heavy_ones_on_the_chart(app):  # noqa: F811
    client, snap = app
    _feeds(snap, datetime.now(UTC))
    days = nw.by_day(snap, "AAA")
    assert [g["day"] for g in days] == sorted((g["day"] for g in days), reverse=True) and len(days) == 2
    assert days[0]["react"] is not None and days[1]["items"][0]["kind_no"] == "innsideinformasjon"
    html = client.get("/aksje/AAA/oversikt").get_data(as_text=True)
    card = html.split('id="nyheter-aksje"')[1][:6000]
    assert "Meldinger og nyheter, dag for dag" in card and card.count('class="nday"') >= 2 and "kurs " in card
    ev = nw.chart_events(snap, "AAA")
    assert [e["kind_no"] for e in ev] == ["innsideinformasjon"]                             # the routine notice and the headline are not on the chart
    idx = snap.panel["close"]["AAA"].dropna().index
    marks = [e for e in pc.events("AAA", idx, news=ev) if e["k"] == "melding"]
    assert len(marks) == 1 and marks[0]["t"] == f"{idx[-2]:%Y-%m-%d}" and marks[0]["txt"].startswith("Innsideinformasjon: Alpha ASA")
    assert '"k": "melding"' in html or '"k":"melding"' in html
    assert "melding" in pc.EV_LABEL and 'data-ev="melding"' in html or "Meldinger" in html


def test_a_headline_about_another_company_with_a_similar_name_is_not_ours():
    names = {"KOG": "Kongsberg Gruppen", "AKER": "Aker", "AKRBP": "Aker BP"}
    assert not fd.mentions("Kongsberg Maritime lanserer ubemannet ubåtjeger", "KOG", names)
    assert fd.mentions("Kongsberg Gruppen får ny kontrakt", "KOG", names) and fd.mentions("Kongsberg med rekordordre", "KOG", names)
    assert not fd.mentions("Aker Solutions vinner kontrakt", "AKER", names) and fd.mentions("Aker kjøper seg opp", "AKER", names)
