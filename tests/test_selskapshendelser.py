"""Corporate events read off the announcement titles, and the demerger taken out of KOG's adjusted series
(docs/forbedring/endringer.md E10, funn #7 and D13). Synthetic data and a temp home."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from osloquant.dashboard import datahealth as dh
from osloquant.dashboard import feeds as fd
from osloquant.recorders.yahoo.cleaning import apply_exceptions, load_exceptions
from tests.helpers import business_days

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home


@pytest.mark.parametrize(("title", "kind"), [
    ("Wallenius Wilhelmsen ASA - Share capital increase from Private Placement registered", "emisjon"),
    ("Alpha ASA: Rettet emisjon gjennomført", "emisjon"),
    ("Alpha ASA – fortrinnsrettsemisjon: start på tegningsperioden", "emisjon"),
    ("Beta ASA: Reverse share split – key information", "splitt eller spleis"),
    ("Beta ASA: Aksjespleis gjennomført", "splitt eller spleis"),
    ("Kongsberg Gruppen ASA: Demerger completed", "fisjon eller fusjon"),
    ("Gamma ASA: fisjon vedtatt av generalforsamlingen", "fisjon eller fusjon"),
    ("Delta ASA: Change of name and new ticker", "navn eller ticker"),
    ("Delta ASA: navneendring registrert", "navn eller ticker"),
    ("Epsilon ASA: Last day of trading and delisting", "avnotering"),
    ("Vedtak om opptak til handel – Kongsberg Maritime ASA", "ny på børsen"),
    ("Zeta ASA - First day of trading on Euronext Oslo Børs", "ny på børsen"),
    ("Euronext Oslo Børs - PROTECTOR FORSIKRING ASA - Received application for listing of bonds", None),
    ("Protector Forsikring ASA   Prospectus approved for listing of bonds", None),
    ("Alpha ASA: Successful placement of new senior unsecured green bond", None),
    ("Alpha ASA: Third quarter 2026 results", None),
    ("Alpha ASA: Mandatory notification of trade", None),
    ("", None),
])
def test_a_title_is_read_as_the_right_kind_of_event_and_bonds_are_not_shares(title, kind):
    assert fd.corporate_kind(title) == kind


def _message(mid: int, code: str, title: str, when: datetime, issuer: str = "X ASA") -> dict:
    return {"messageId": mid, "issuerSign": code, "issuerName": issuer, "title": title, "publishedTime": when.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "category": [{"category_en": "ADDITIONAL REGULATED INFORMATION"}]}


def test_the_fetch_keeps_events_of_the_universe_and_new_listings_outside_it(home, monkeypatch):
    now = datetime.now(UTC)
    msgs = [_message(1, "AAA", "Alpha ASA: Private placement successfully completed", now - timedelta(days=1)),
            _message(2, "NEW", "Nykommer ASA - First day of trading on Euronext Oslo Børs", now - timedelta(days=2), "Nykommer ASA"),
            _message(3, "ZZZ", "Zulu ASA: Private placement", now - timedelta(days=1)),                # not in the universe: not ours to watch
            _message(4, "AAA", "Alpha ASA: Third quarter results", now - timedelta(days=1)),
            _message(5, "BBB", "Beta ASA - Received application for listing of bonds", now - timedelta(days=1))]
    day = f"{now - timedelta(days=1):%Y-%m-%d}"
    day2 = f"{now - timedelta(days=2):%Y-%m-%d}"

    def get(url, method="GET", **k):
        hit = [m for m in msgs if m["publishedTime"][:10] in url and (day in url or day2 in url)]
        return json.dumps({"data": {"messages": hit}}).encode()

    monkeypatch.setattr(fd, "_get", get)
    doc = fd.fetch_announcements(["AAA", "BBB"])
    assert [(e["code"], e["kind"], e["in_universe"]) for e in sorted(doc["corporate"], key=lambda e: e["id"])] == [
        ("AAA", "emisjon", True), ("NEW", "ny på børsen", False)]
    assert sorted(a["id"] for a in doc["items"]) == [1, 4, 5]                 # the ordinary list is the universe's, as before
    fd.write("announcements", doc)
    assert [e["code"] for e in fd.corporate_events()] == ["AAA", "NEW"]       # newest first
    lines = dh.corporate_lines(fd.corporate_events())
    assert any(x.startswith("AAA: emisjon") for x in lines)
    assert any(x.startswith("NEW: ny på børsen, første handelsdag") and "(ikke i universet)" in x for x in lines)
    # an event older than the alert window stays on the card but leaves the alert
    assert dh.corporate_lines(fd.corporate_events(), now=now + timedelta(days=20)) == []
    # the next fetch keeps what was found, also when the day is no longer asked for
    monkeypatch.setattr(fd, "_get", lambda url, method="GET", **k: b'{"data": {"messages": []}}')
    assert len(fd.fetch_announcements(["AAA", "BBB"])["corporate"]) == 2


def test_data_health_and_the_front_page_show_the_event(app):  # noqa: F811
    client, _ = app
    when = (datetime.now(UTC) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    fd.write("announcements", {"items": [], "corporate": [
        {"id": 9, "code": "AAA", "issuer": "Alpha ASA", "title": "Alpha ASA: Demerger completed", "time": when, "kind": "fisjon eller fusjon",
         "in_universe": True, "url": "https://newsweb.oslobors.no/message/9"}]})
    health = client.get("/health").get_data(as_text=True)
    assert 'id="selskapshendelser"' in health and "Alpha ASA: Demerger completed" in health and "fisjon eller fusjon" in health
    assert "selskapshendelser siste 14 dager" in health
    front = client.get("/").get_data(as_text=True)
    assert 'id="selskapshendelser-varsel"' in front and "AAA: fisjon eller fusjon" in front


def test_the_kog_demerger_is_taken_out_of_the_adjusted_series():
    ex = load_exceptions()
    kog = [e for e in ex["drop_returns"] if e["ticker"] == "KOG.OL"]
    assert len(kog) == 1 and str(kog[0]["date"]) == "2026-04-15" and "EST" in kog[0]["reason"] and "670655" in kog[0]["reason"]
    days = pd.DatetimeIndex(["2026-04-13", "2026-04-14", "2026-04-15", "2026-04-16"])
    closes = [400.0, 398.5, 326.0, 330.0]
    df = pd.DataFrame({"timestamp": days, "open": closes, "high": closes, "low": closes, "close": closes, "adj_close": closes, "volume": 1000.0})
    out = apply_exceptions(df, "KOG.OL")
    adj = out["adj_close"].tolist()
    assert adj[2] / adj[1] == pytest.approx(1.0) and adj[3] / adj[2] == pytest.approx(330.0 / 326.0)        # the gap is gone, the next day is kept
    assert adj[1] / adj[0] == pytest.approx(398.5 / 400.0) and out["close"].tolist() == closes                   # quoted prices untouched
    assert len(business_days(3)) == 3


# ------------------------------------------------------------------------------------------------ on the way to the exchange
def _event(mid: int, code: str, issuer: str, title: str, days_ago: float, kind: str = "ny på børsen", in_universe: bool = False) -> dict:
    when = (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"id": mid, "code": code, "issuer": issuer, "title": title, "time": when, "kind": kind, "in_universe": in_universe,
            "url": f"https://newsweb.oslobors.no/message/{mid}"}


#: the four messages of 9–10 Nov 2026 that read «-: ny på børsen (ikke i universet)» four times on the front page
REAL = [("-", "Oslo Børs", "Euronext Oslo Børs - Received application for admission to trading - Cetus Maritime Holdings Limited", 0.5),
        ("-", "Oslo Børs", "Euronext Oslo Børs - Mottatt søknad om opptak til handel - Cetus Maritime Holdings Limited", 0.5),
        ("-", "Oslo Børs", "Cetus Maritime Holdings Limited: Contemplated Private Placement and Subsequent Listing on Euronext Growth Oslo", 0.6),
        ("-", "Oslo Børs", "Heder Bank intends to apply for a listing on Euronext Oslo Børs", 1.5)]


@pytest.mark.parametrize(("title", "company", "stage"), [
    (REAL[0][2], "Cetus Maritime Holdings Limited", "søknad om opptak til handel"),
    (REAL[1][2], "Cetus Maritime Holdings Limited", "søknad om opptak til handel"),
    (REAL[2][2], "Cetus Maritime Holdings Limited", "notering varslet"),
    (REAL[3][2], "Heder Bank", "notering varslet"),
    ("Nykommer ASA - First day of trading on Euronext Oslo Børs", "Nykommer ASA", "første handelsdag"),
    ("Oslo Børs - Approved for listing", None, "godkjent for notering"),
])
def test_a_listing_title_names_its_company_and_its_stage(title, company, stage):
    assert fd.company_from_title(title) == company and fd.listing_stage(title) == stage


def test_a_company_without_a_ticker_is_named_and_a_planned_listing_is_not_a_warning():
    events = [_event(i, code, issuer, title, ago) for i, (code, issuer, title, ago) in enumerate(REAL, 1)]
    assert dh.corporate_lines(events) == []                                              # nothing in the universe has changed
    coming = dh.coming_lines(events)
    assert len(coming) == 2                                                              # one line per company, not one per message
    assert coming[0].startswith("Cetus Maritime Holdings Limited: søknad om opptak til handel ")
    assert coming[1].startswith("Heder Bank: notering varslet ")
    assert not any(line.startswith("-") or "ny på børsen" in line for line in coming)
    # the day the share trades, it is a reason to look at the universe
    events.append(_event(9, "CETUS", "Cetus Maritime Holdings Limited", "Cetus Maritime Holdings Limited - First day of trading on Euronext Growth Oslo", 0.1))
    assert dh.corporate_lines(events)[0].startswith("CETUS: ny på børsen, første handelsdag ") and "(ikke i universet)" in dh.corporate_lines(events)[0]
    assert fd.corporate_subject({"code": "", "issuer": "Oslo Børs", "title": "Noe uten navn"}) == "Oslo Børs"


def test_the_front_page_says_who_is_on_the_way_without_a_warning(app):  # noqa: F811
    client, _ = app
    fd.write("announcements", {"items": [], "corporate": [_event(i, code, issuer, title, ago) for i, (code, issuer, title, ago) in enumerate(REAL, 1)]})
    front = client.get("/").get_data(as_text=True)
    assert 'id="selskapshendelser-varsel"' not in front and "Universet bør sjekkes" not in front
    box = front.split('id="pa-vei-til-borsen"')[1].split("</div>")[0]
    assert "På vei til Oslo Børs" in box and "Cetus Maritime Holdings Limited: søknad om opptak til handel" in box and "Heder Bank: notering varslet" in box
    assert "Ingen av dem er i universet ennå" in box and "-:" not in box and ".." not in box
    health = client.get("/health").get_data(as_text=True)
    card = health.split('id="selskapshendelser"')[1].split("</table>")[0]
    assert "Cetus Maritime Holdings Limited" in card and "meldt av Oslo Børs" in card and "på vei til børsen" in card
    assert "selskapshendelser siste 14 dager" not in health                              # not among the things that should worry the reader
