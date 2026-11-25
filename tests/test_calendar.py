"""The calendar: NewsWeb financial-calendar text parsed into dates, merged with the research book and Norges Bank, shown
on the front page without repeating the book's own dates."""

from __future__ import annotations

import pandas as pd

from osloquant.dashboard import book as bk
from osloquant.dashboard import calendar as cal
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import today as td

TEXT = ("Financial calendar for Example ASA FINANCIAL YEAR 2026 12.11.2026 - Quarterly Report - Q3 25.02.2027 - Quarterly Report - Q4 "
        "FINANCIAL YEAR 2027 19.08.2027 - Half-yearly Report 08.04.2027 - Annual Report 05.05.2027 - Annual General Meeting "
        "14.05.2027 - Quarterly Report - Q1 This information is published pursuant to the requirements set out in the Continuing obligations.")


def test_financial_calendar_text_is_parsed_into_sorted_dates():
    ev = cal.parse_financial_calendar(TEXT)
    assert [e["date"] for e in ev] == ["2026-11-12", "2027-02-25", "2027-04-08", "2027-05-05", "2027-05-14", "2027-08-19"]
    assert ev[0]["what"] == "Quarterly Report - Q3" and ev[3]["what"] == "Annual General Meeting"
    assert cal.parse_financial_calendar("<p>no dates here</p>") == []
    assert cal.parse_financial_calendar("31.02.2027 - impossible 01.03.2027 - fine") == [{"date": "2027-03-01", "what": "fine"}]


def test_events_merge_book_calendar_and_norges_bank(home, monkeypatch):
    today = pd.Timestamp("2026-11-02")
    c = bk.Case("XYZ", "Xyz", None, "log", [{"date": "2026-11-12", "what": "Q3 2026 report – first as listed"}], ["k"], None, [])
    fd.write(cal.CAL_FEED, {"companies": {"XYZ": {"message_id": 1, "published": "2026-09-23T06:00:00Z", "url": "u",
                                                   "events": cal.parse_financial_calendar(TEXT)}}, "source": "test"})
    monkeypatch.setattr(cal, "norges_bank_meetings", lambda: {"source": "norges-bank.no calendar", "read": "2026-11-02",
                                                               "dates": [{"date": "2026-11-05", "what": "Policy rate decision"}, {"date": "2027-06-18", "what": "x"}]})
    ev = cal.events([c], today=today, days=120)
    kinds = [(f"{e['date']:%Y-%m-%d}", e["kind"]) for e in ev]
    assert kinds[0] == ("2026-11-05", "rates")
    assert ("2026-11-12", "case") in kinds and ("2026-11-12", "report") in kinds and ("2027-02-25", "report") in kinds
    assert ("2027-06-18", "rates") not in kinds                                        # beyond 120 days
    rep = next(e for e in ev if e["kind"] == "report" and f"{e['date']:%Y-%m-%d}" == "2026-11-12")
    assert rep["duplicate_of_case_event"] and rep["in_book"]
    up = td.upcoming([c], today, days=30)
    assert [(f"{e['date']:%Y-%m-%d}", e["source"]) for e in up] == [("2026-11-12", None)]   # rate meetings are in the macro week (D71)
    week = cal.macro_week(ev, today)
    assert [(f"{e['date']:%Y-%m-%d}", e["name"]) for e in week] == [("2026-11-05", "Norges Bank")]
    html = cal.page_html(ev, today, fd.read(cal.CAL_FEED), cal.norges_bank_meetings())
    assert "Kalender" in html and "Policy rate decision" in html and "står også i research book" in html
    assert ">rentemøte<" in html and ">rapport<" in html and ">rates<" not in html             # the type column is Norwegian


def test_calendar_page_says_what_is_missing(home, monkeypatch):
    monkeypatch.setattr(cal, "norges_bank_meetings", lambda: None)
    today = pd.Timestamp("2026-11-02")
    html = cal.page_html(cal.events([], today=today), today, None, None)
    assert "ikke hentet ennå" in html and "kildefilen mangler" in html and "Ingen datoer er gjettet" in html
