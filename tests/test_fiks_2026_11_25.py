"""Two faults found in the check of 25 Nov 2026:

- the evening signal task the laptop missed ran the next morning with the market open and stored half a session as
  that day's close (`oq record --closed-only` now leaves it out);
- the Sunday summary the laptop missed ran on Monday morning and failed: «no sessions in the week of 23 Nov» (the
  summary now covers the week just ended).
"""

from __future__ import annotations

import pandas as pd

from osloquant.dashboard import sources
from osloquant.dashboard import weekly as wk
from osloquant.recorders.yahoo import client


def test_the_newest_closed_session_is_yesterday_until_the_close_is_final():
    assert sources.closed_session(pd.Timestamp("2026-11-25 09:54")) == pd.Timestamp("2026-11-24")   # Wednesday morning
    assert sources.closed_session(pd.Timestamp("2026-11-25 16:30")) == pd.Timestamp("2026-11-24")   # the auction, not final yet
    assert sources.closed_session(pd.Timestamp("2026-11-25 18:45")) == pd.Timestamp("2026-11-25")   # the evening run
    assert sources.closed_session(pd.Timestamp("2026-11-23 08:00")) == pd.Timestamp("2026-11-20")   # Monday morning: Friday
    assert sources.closed_session(pd.Timestamp("2026-11-28 12:00")) == pd.Timestamp("2026-11-27")   # Saturday


def test_a_bar_after_the_closed_session_is_left_out_only_when_asked(monkeypatch):
    idx = pd.DatetimeIndex(["2026-11-23", "2026-11-24", "2026-11-25"], tz="Europe/Oslo")
    raw = pd.DataFrame({"Open": [10.0, 11.0, 12.0], "High": [10.5, 11.5, 12.5], "Low": [9.5, 10.5, 11.5], "Close": [10.2, 11.2, 12.2],
                        "Adj Close": [10.2, 11.2, 12.2], "Volume": [100, 100, 40], "Dividends": [0.0, 0.0, 0.0], "Stock Splits": [0.0, 0.0, 0.0]},
                       index=idx)

    class Ticker:
        def history(self, **kwargs):
            return raw

    monkeypatch.setattr(client, "_ticker", lambda symbol: Ticker())
    monkeypatch.setattr(client, "CLOSED_ONLY", None)
    assert list(client._fetch_history("XYZ.OL", pd.Timestamp("2026-11-20"))["timestamp"].dt.day) == [23, 24, 25]
    monkeypatch.setattr(client, "CLOSED_ONLY", pd.Timestamp("2026-11-24"))
    got = client._fetch_history("XYZ.OL", pd.Timestamp("2026-11-20"))
    assert list(got["timestamp"].dt.day) == [23, 24] and got["close"].iloc[-1] == 11.2


def test_the_weekly_summary_covers_the_week_just_ended():
    assert wk.default_day(pd.Timestamp("2026-11-22 18:00")) == pd.Timestamp("2026-11-22")   # Sunday: this week
    assert wk.default_day(pd.Timestamp("2026-11-21 10:00")) == pd.Timestamp("2026-11-21")   # Saturday: this week
    assert wk.default_day(pd.Timestamp("2026-11-23 07:59")) == pd.Timestamp("2026-11-22")   # Monday catch-up: last week
    assert wk.default_day(pd.Timestamp("2026-11-25 12:00")) == pd.Timestamp("2026-11-22")   # midweek by hand: last full week
    assert wk.week_of(wk.default_day(pd.Timestamp("2026-11-23 07:59")))[0] == pd.Timestamp("2026-11-16")


def test_the_signal_task_records_closed_sessions_only():
    from pathlib import Path

    ps1 = (Path(__file__).parents[1] / "scripts" / "run_signals.ps1").read_text(encoding="utf-8")
    assert "record --raw --closed-only" in ps1


def test_texts_stored_in_english_are_shown_in_norwegian():
    from osloquant.dashboard import afterreport as ar
    from osloquant.dashboard import lightcase as lcm

    old = ["light case rebuilt", "report found on NewsWeb: Third quarter 2026 (2026-10-29)",
           "no spec in reports.yaml: dry run found 4 of 6 rows; suggested spec written",
           "Yahoo has quarterly statements only to 2025-12-31: a newer report may be out (see the calendar and NewsWeb) and is not in these figures",
           "net debt missing in Yahoo's balance sheet: EV is the market value alone (cash not deducted)"]
    new = [lcm.norsk(t) for t in old]
    assert new == ["lett case bygget på nytt", "rapport funnet på NewsWeb: Third quarter 2026 (2026-10-29)",
                   "ingen leserspesifikasjon i reports.yaml: prøvekjøringen fant 4 av 6 rader; forslag skrevet",
                   "Yahoo har kvartalsregnskap bare til 2025-12-31: en nyere rapport kan være ute (se kalenderen og NewsWeb), og den er ikke med i disse tallene",
                   "netto gjeld mangler i Yahoos balanse: EV er markedsverdien alene (kontanter er ikke trukket fra)"]
    assert lcm.norsk("Noe annet") == "Noe annet"
    html = ar.block_html("XYZ", {"code": "XYZ", "ran_at": "2026-11-03T19:26:00Z", "steps": old[:3],
                                 "lightcase": {"before": {}, "after": {}, "diff": {}, "warnings": old[3:]}})
    assert "light case" not in html and "Yahoo has" not in html and "lett case bygget på nytt" in html and "Yahoo har kvartalsregnskap" in html


def test_the_stock_page_and_pretrade_show_the_light_case_warnings_in_norwegian_and_the_grade_still_reads_them():
    from osloquant.dashboard import lightcase as lcm

    raw = "reporting currency unknown – run oq case build with --refresh"
    assert lcm.norsk(raw) == "rapporteringsvalutaen er ukjent – kjør oq case build med --refresh"
    case = {"price": {"value": 10.0, "date": "2026-11-20"}, "shares": 1.0, "currency": {}, "warnings": [raw], "annual": [1, 2, 3]}
    assert lcm.quality(case)["grade"] == "C"                       # the check reads the stored text, not the shown one
