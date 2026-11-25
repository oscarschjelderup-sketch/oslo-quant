"""The macro calendar (D71): the rate meetings of Norges Bank, the Fed and the ECB from resource files copied from the
banks' own pages, SSB's releases read from its upcoming-releases page, the US releases from FRED – on /makro, /calendar
and, for the next seven days, on the front page. The SSB page here is a fictional copy of the real page's structure."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from osloquant.dashboard import calendar as cal
from osloquant.dashboard import feeds as fd

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home


def _release(rid: int, name: str, short: str, year: int, month0: int, day: int, period: str) -> dict:
    return {"id": rid, "name": name, "shortName": short, "type": "statistic", "mainSubject": "x",
            "variant": {"id": rid * 10, "day": day, "monthNumber": month0, "year": year, "frequency": "Måned", "period": period},
            "statisticsPageUrl": f"/en/x/{short}", "aboutTheStatisticsDescription": "Fictional text."}


#: the shape of ssb.no/en/kommende-publiseringer: a hydrate script with year -> month -> day -> releases, month zero-based
PAGE = ('<html><script data-react4xp-app-name="mimir" type="application/json">' + json.dumps({"command": "hydrate", "props": {
    "title": "Upcoming releases and publications", "releases": [{"year": "2026", "releases": [
        {"month": "10", "monthName": "Nov", "releases": [
            {"day": "25", "releases": [_release(1, "Labour force survey", "aku", 2026, 10, 25, "Figures for October 2026")]},
            {"day": "27", "releases": [_release(2, "Index of wholesale and retail sales", "doi", 2026, 10, 27, "Figures for October 2026"),
                                       _release(3, "Salmon exports", "laks", 2026, 10, 27, "Figures for week 47 2026")]}]},
        {"month": "11", "monthName": "Dec", "releases": [
            {"day": "10", "releases": [_release(4, "Consumer price index", "kpi", 2026, 11, 10, "Figures for November 2026")]}]}]},
        {"year": "2027", "releases": [{"month": "1", "monthName": "Feb", "releases": [
            {"day": "11", "releases": [_release(5, "Labour force survey", "aku", 2027, 1, 11, "Figures for 4th quarter 2026"),
                                       _release(4, "Consumer price index", "kpi", 2027, 1, 11, "Figures for January 2027")]}]}]}]}})
        + '</script></html>')


def test_ssb_releases_are_read_with_the_zero_based_month_and_said_in_norwegian():
    rel = fd.parse_ssb_calendar(PAGE)
    assert [(r["date"], r["stat"]) for r in rel] == [("2026-11-25", "aku"), ("2026-11-27", "doi"), ("2026-12-10", "kpi"),
                                                    ("2027-02-11", "aku"), ("2027-02-11", "kpi")]   # salmon is not followed
    kpi = next(r for r in rel if r["stat"] == "kpi")
    assert kpi["what"] == "KPI (konsumprisindeksen)" and kpi["period"] == "tall for november 2026"
    assert kpi["url"] == "https://www.ssb.no/en/x/kpi"
    assert fd.ssb_period("Figures for 4th quarter 2026") == "tall for 4. kvartal 2026"
    assert fd.ssb_period("Figures for 5. termin 2026") == "Figures for 5. termin 2026"         # kept as printed
    with pytest.raises(ValueError):                                                           # a changed page is an error, not an empty calendar
        fd.parse_ssb_calendar("<html>no data</html>")


def test_the_macro_feed_keeps_the_last_ssb_calendar_when_the_page_fails(monkeypatch):
    hist = {"t": ["2026-11-02"], "v": [1.0]}
    monkeypatch.setattr(fd, "_nb_history", lambda flow, n=fd.MACRO_OBS: hist)
    monkeypatch.setattr(fd, "_yahoo_histories", lambda symbols: {k: hist for k in symbols})
    monkeypatch.setattr(fd, "_salmon_history", lambda weeks=160: hist)
    monkeypatch.setattr(fd, "_power_history", lambda old, today=None: hist)
    monkeypatch.setattr(fd, "fetch_ssb_calendar", lambda: fd.parse_ssb_calendar(PAGE))
    doc = fd.fetch_macro()
    assert len(doc["ssb_releases"]) == 5 and not [e for e in doc["errors"] if "SSB" in e]
    fd.write("macro", doc)

    def broken():
        raise ValueError("SSB-siden hadde ingen publiseringsdata")

    monkeypatch.setattr(fd, "fetch_ssb_calendar", broken)
    doc2 = fd.fetch_macro()
    assert doc2["ssb_releases"] == doc["ssb_releases"] and "SSB-kalenderen: ValueError" in doc2["errors"]


def test_the_banks_files_have_dates_sources_and_no_guesses():
    for key, name, fname in cal.BANKS:
        doc = cal.bank_meetings(key)
        assert doc and doc["source"].startswith("https://") and doc["read"], fname
        dates = [d["date"] for d in doc["dates"]]
        assert dates == sorted(dates) and len(set(dates)) == len(dates), name
        assert all(d["what"] for d in doc["dates"])
    fed = {str(d["date"]) for d in cal.bank_meetings("fed")["dates"]}
    ecb = {str(d["date"]) for d in cal.bank_meetings("ecb")["dates"]}
    assert "2026-12-09" in fed and "2026-12-17" in ecb                                       # the decision day, the second day of the meeting


def test_events_hold_all_three_banks_and_both_release_calendars(home):
    today = pd.Timestamp("2026-11-13")
    macro = {"ssb_releases": fd.parse_ssb_calendar(PAGE), "releases": [{"date": "2026-12-04", "release_id": 50, "what": "Sysselsetting i USA (Employment Situation)"}]}
    ev = cal.events([], today=today, days=120, macro=macro)
    rates = [(f"{e['date']:%Y-%m-%d}", e["name"]) for e in ev if e["kind"] == "rates"]
    assert ("2026-12-09", "Fed") in rates and ("2026-12-17", "ESB") in rates and ("2026-12-17", "Norges Bank") in rates
    rel = [(f"{e['date']:%Y-%m-%d}", e["name"], e["what"]) for e in ev if e["kind"] == "release"]
    assert ("2026-12-10", "Norge", "KPI (konsumprisindeksen) (tall for november 2026)") in rel
    assert ("2026-12-04", "USA", "Sysselsetting i USA (Employment Situation)") in rel
    assert all(e["source"] for e in ev)
    week = cal.macro_week(ev, today)
    assert [(f"{e['date']:%Y-%m-%d}", e["name"]) for e in week] == []                          # nothing 13-20 Nov in this fixture
    week = cal.macro_week(ev, pd.Timestamp("2026-11-24"))
    assert [(f"{e['date']:%Y-%m-%d}", e["stat"] if "stat" in e else e["name"]) for e in week] == [("2026-11-25", "Norge"), ("2026-11-27", "Norge")]
    html = cal.week_html(week, pd.Timestamp("2026-11-24"))
    assert "Makro de neste sju dagene" in html and "Arbeidsledighet (AKU) (tall for oktober 2026)" in html and "SSBs publiseringskalender" in html


def test_a_meeting_file_that_runs_out_is_named():
    today = pd.Timestamp("2027-10-01")
    notes = cal.refill_notes(today)
    assert any(n.startswith("Norges Bank: siste møte i filen er 16. des. 2027") for n in notes)    # NB's file ends Dec 2027
    assert any(n.startswith("Fed: siste møte i filen er 17. nov. 2027") for n in notes)
    assert not any(n.startswith("ESB") for n in notes)                                            # the ECB's runs to Dec 2028
    assert cal.refill_notes(pd.Timestamp("2026-11-13")) == []


def test_the_macro_page_and_the_front_page_show_the_calendar(app, monkeypatch):  # noqa: F811
    client, _ = app
    today = pd.Timestamp.now().normalize()
    soon = [{"date": f"{today + pd.Timedelta(days=2):%Y-%m-%d}", "stat": "kpi", "what": "KPI (konsumprisindeksen)", "period": "tall for oktober 2026",
             "url": "https://www.ssb.no/en/x/kpi"}]
    fd.write("macro", {"series": {}, "errors": [], "releases": [], "ssb_releases": soon})
    front = client.get("/").get_data(as_text=True)
    block = front.split('id="makro-uke"')[1].split("</div></div>")[0]
    assert "KPI (konsumprisindeksen) (tall for oktober 2026)" in block and "Norge:" in block
    page = client.get("/makro").get_data(as_text=True)
    cal_block = page.split('id="kalender"')[1]
    assert "Tallslipp: KPI (konsumprisindeksen) (tall for oktober 2026)" in cal_block
    assert "ikke med ennå" not in page and "Norges Bank, Fed og ESB" in cal_block
    assert 'href="/aksje/Norge"' not in page                                                     # «Norge» is not a ticker
    kal = client.get("/calendar").get_data(as_text=True)
    assert "tallslipp" in kal and "Fed: 16 møtedatoer" in kal and "ESB: 17 møtedatoer" in kal
