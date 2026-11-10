"""The data sources (docs/forbedring/endringer.md E4–E6): the scheduled scripts fetch what the pages read, every
attempt is on record, a source that is down or stale is named on the front page and on data health, requests are
retried with a pause, and NewsWeb is asked for no more than is new. Synthetic store and temp home only."""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from osloquant.dashboard import calendar as cal
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import insiders as ins
from osloquant.dashboard import reports as rp
from osloquant.dashboard import sources as src

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home

OLD = "2026-11-06T17:50:00Z"            # a Friday evening (18:50 in Oslo)
NOW = pd.Timestamp("2026-11-10 08:00")  # Tuesday morning: Monday's close is expected


def _by_key(now=NOW) -> dict:
    return {s["key"]: s for s in src.status(now)}


def _utc(oslo: str) -> datetime:
    return pd.Timestamp(oslo, tz="Europe/Oslo").tz_convert("UTC").to_pydatetime()


def _seed_feeds(stamp: str = OLD) -> None:
    docs = {"announcements": {"items": []}, "rates": {"policy_rate": 4.0, "policy_date": "2026-11-06", "gov10y": 3.9, "gov10y_date": "2026-11-06"},
            "fx": {"USDNOK": 10.0, "EURNOK": 11.5, "date": "2026-11-06"}, "salmon": {"value": 70.0, "date": "week 44 2026"},
            "brent": {"value": 80.0, "date": "2026-11-06"}, "news": {"items": []}, "shorts": {"instruments": []},
            "insiders": {"items": {}, "fetched_years": {}}, "calendar": {"companies": {}}}
    for name, doc in docs.items():
        (fd.cache_dir() / f"{name}.json").write_text(json.dumps(doc | {"fetched_at": stamp, "source": "test"}), encoding="utf-8")


def _all_feeds_down(monkeypatch) -> None:
    def down(*a, **k):
        raise ConnectionError("kilden svarer ikke")

    for mod, names in ((fd, ("fetch_announcements", "fetch_rates", "fetch_fx", "fetch_salmon", "fetch_brent", "fetch_news")),
                       (ins, ("fetch_shorts", "fetch")), (cal, ("fetch_financial_calendars",))):
        for n in names:
            monkeypatch.setattr(mod, n, down)


# ------------------------------------------------------------------------------------------------ E4 the scheduled scripts
def test_e4_the_evening_job_records_quoted_bars_and_the_weekly_job_the_statements():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    evening, weekly = (scripts / "run_signals.ps1").read_text(encoding="utf-8"), (scripts / "run_weekly.ps1").read_text(encoding="utf-8")
    assert "& $oq record --raw 2>&1" in evening and "& $oq record 2>&1" not in evening
    assert "& $oq record --raw --finance 2>&1" in weekly
    for text in (evening, weekly):                       # E6: the log keeps æ, ø and å
        assert "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8" in text


# ------------------------------------------------------------------------------------------------ E5 the sources
def test_e5_every_source_down_is_shown_as_failed_with_the_old_time_and_never_as_fresh(app, monkeypatch):  # noqa: F811
    client, _ = app
    _seed_feeds()
    _all_feeds_down(monkeypatch)
    out = fd.refresh([])
    assert len(out) == 9 and all(v.startswith("ConnectionError") for v in out.values())
    assert fd.read("rates")["fetched_at"] == OLD                              # the old cache is kept, with its old time
    sts = _by_key()
    feeds = [s for s in sts.values() if s["kind"] == "feed"]
    assert len(feeds) == 9
    for s in feeds:
        assert s["state"] == "failed" and "kilden svarer ikke" in s["error"], s["key"]
        assert f"{s['last_ok']:%Y-%m-%d %H:%M}" == "2026-11-06 18:50" and s["last_attempt"] > s["last_ok"]     # Oslo time
        assert (s["fails"], s["runs"]) == (1, 1)
    banner = src.banner_html(list(sts.values()))
    for s in feeds:
        assert s["name"] in banner and s["affects"] in banner
    assert "feilet" in banner and "sist hentet 6. nov. 2026 18:50" in banner
    front = client.get("/").get_data(as_text=True)
    assert 'id="kilder-varsel"' in front and "Børsmeldinger" in front and "kilden svarer ikke" in front
    health = client.get("/health").get_data(as_text=True)
    assert 'id="kilder"' in health and health.count(">feilet<") >= 9 and "Shortposisjoner" in health
    assert "Børsmeldinger (Oslo Børs NewsWeb): feilet" in health            # «Ting å vite nå»


def test_e5_each_source_alone_down_is_the_only_one_named(home, monkeypatch):
    fetchers = {"announcements": (fd, "fetch_announcements"), "rates": (fd, "fetch_rates"), "fx": (fd, "fetch_fx"), "salmon": (fd, "fetch_salmon"),
                "brent": (fd, "fetch_brent"), "news": (fd, "fetch_news"), "shorts": (ins, "fetch_shorts"), "insiders": (ins, "fetch"),
                "calendar": (cal, "fetch_financial_calendars")}
    good = {"announcements": {"items": []}, "rates": {"policy_rate": 4.0}, "fx": {"USDNOK": 10.0}, "salmon": {"value": 70.0}, "brent": {"value": 80.0},
            "news": {"items": []}, "shorts": {"instruments": []}, "insiders": {"items": {}, "fetched_years": {}}, "calendar": {"companies": {}}}
    now = pd.Timestamp.now(tz="Europe/Oslo").tz_localize(None)
    for victim in fetchers:
        for name, (mod, fn) in fetchers.items():
            if name == victim:
                def down(*a, **k):
                    raise TimeoutError("timed out")
                monkeypatch.setattr(mod, fn, down)
            else:
                monkeypatch.setattr(mod, fn, lambda *a, _doc=good[name], **k: dict(_doc))
        fd.refresh([])
        bad = [s["key"] for s in src.not_ok(src.status(now)) if s["kind"] == "feed"]
        assert bad == [victim], victim
        assert "TimeoutError" in _by_key(now)[victim]["error"]


def test_e5_a_feed_not_fetched_since_the_last_close_is_stale_and_a_fresh_one_is_ok(home):
    _seed_feeds()                                        # fetched Friday evening
    sts = _by_key(pd.Timestamp("2026-11-09 08:00"))      # Monday morning: Friday's close is the newest
    assert sts["rates"]["state"] == "ok" and sts["news"]["state"] == "ok" and sts["salmon"]["state"] == "ok"
    sts = _by_key()                                      # Tuesday morning: Monday evening's fetch never happened
    assert sts["rates"]["state"] == "stale" and "ikke hentet siden 6. nov. 2026 18:50" in sts["rates"]["detail"]
    assert sts["salmon"]["state"] == "ok" and sts["salmon"]["expected"] == "minst én gang i uken"       # weekly: four days is fine
    src.record_run("rates", True, now=_utc("2026-11-09 17:50"))
    assert _by_key()["rates"]["state"] == "ok"
    assert _by_key(pd.Timestamp("2026-11-17 08:00"))["salmon"]["state"] == "stale"
    assert _by_key()["shorts"]["state"] == "stale"
    (fd.cache_dir() / "shorts.json").unlink()
    assert _by_key()["shorts"]["state"] == "never" and _by_key()["shorts"]["state_no"] == "aldri hentet"


def test_e5_holidays_are_not_a_false_alarm():
    assert src._easter(2026).isoformat() == "2026-04-05" and src._easter(2027).isoformat() == "2027-03-28"
    # Tuesday after Easter 2026, in the morning: Maundy Thursday, Good Friday and Easter Monday were closed
    assert f"{src.expected_session(pd.Timestamp('2026-04-07 09:00')):%Y-%m-%d}" == "2026-04-01"
    assert f"{src.expected_session(pd.Timestamp('2026-04-07 18:00')):%Y-%m-%d}" == "2026-04-01"     # the evening job is still running
    assert f"{src.expected_session(pd.Timestamp('2026-04-07 18:30')):%Y-%m-%d}" == "2026-04-07"
    assert f"{src.expected_session(pd.Timestamp('2026-05-18 09:00')):%Y-%m-%d}" == "2026-05-15"     # 17 May 2026 is a Sunday
    assert f"{src.expected_session(pd.Timestamp('2027-05-18 09:00')):%Y-%m-%d}" == "2027-05-14"     # Monday 17 May 2027 is closed
    assert f"{src.expected_session(pd.Timestamp('2026-12-28 09:00')):%Y-%m-%d}" == "2026-12-23"


def test_e5_the_store_is_measured_per_stock_so_one_fresh_stock_hides_nothing(home, monkeypatch):
    fresh, old = pd.Timestamp("2026-11-09"), pd.Timestamp("2026-10-19")
    adj = {f"S{i:02d}": fresh for i in range(64)}
    tables = {"Stock1dAdjKdata": adj, "Stock1dKdata": {c: old for c in adj} | {"S00": fresh}, "Index1dKdata": {"OSEBX": fresh},
              "IncomeStatement": {c: pd.Timestamp("2026-09-30") for c in adj} | {"S01": pd.Timestamp("2026-06-30"), "S02": pd.Timestamp("2026-06-30")}}
    monkeypatch.setattr(src, "table_last", lambda name: tables[name])
    sts = _by_key()
    raw = sts["prices_raw"]
    assert raw["state"] == "stale" and "63 av 64 aksjer ligger etter" in raw["detail"] and "19. okt. 2026" in raw["detail"] and len(raw["behind"]) == 63
    assert sts["prices_adj"]["state"] == "ok" and sts["index"]["state"] == "ok"
    fin = sts["finance"]
    assert fin["state"] == "never" and "oq record --finance" in fin["detail"]
    assert "nyeste periode slutter 30. sep. 2026; 2 har ikke den perioden ennå (S01, S02)" in fin["detail"]
    assert any(x.startswith("Noterte kurser (Yahoo Finance): utdatert – 63 av 64") for x in src.problem_lines(list(sts.values())))
    src.record_run("finance", True, now=_utc("2026-11-08 18:10"))
    assert _by_key()["finance"]["state"] == "ok"
    assert _by_key(pd.Timestamp("2026-11-20 08:00"))["finance"]["state"] == "stale"
    # the adjusted table one session behind, and then one stock without the last close
    tables["Stock1dAdjKdata"] = {c: pd.Timestamp("2026-11-06") for c in adj}
    st = _by_key()["prices_adj"]
    assert st["state"] == "stale" and "siste børsdag var 9. nov. 2026" in st["detail"]
    tables["Stock1dAdjKdata"] = adj | {"S05": old}
    st = _by_key()["prices_adj"]
    assert st["state"] == "partial" and "1 uten siste sluttkurs (S05)" in st["detail"]
    tables["Stock1dKdata"] = {}
    assert _by_key()["prices_raw"]["state"] == "never"


def test_e5_the_record_command_writes_every_table_to_the_run_log(home, monkeypatch):
    from typer.testing import CliRunner

    import osloquant.domain as dm
    from osloquant import cli
    from osloquant.contract.recorder import RecordSummary

    def fake(name, failed=None):
        return classmethod(lambda cls, **k: RecordSummary(name, "yahoo", 3, 30, failed or {}))

    for name in ("Stock", "Index", "Future", "Currency", "StockAction", "Stock1dAdjKdata", "Index1dKdata", "Future1dKdata", "Currency1dKdata"):
        monkeypatch.setattr(getattr(dm, name), "record_data", fake(name))
    monkeypatch.setattr(dm.Stock1dKdata, "record_data", fake("Stock1dKdata", {"AAA": "TimeoutError: read timed out"}))
    r = CliRunner().invoke(cli.app, ["record", "--raw"])
    assert r.exit_code == 0, r.output
    log = src.runs()
    last = log["prices_adj"]["runs"][-1]
    assert last["ok"] is True and last["n"] == 30 and log["prices_adj"]["last_ok"] == last["t"]
    assert log["prices_raw"]["runs"][-1]["ok"] is False and "1 feilet (AAA: TimeoutError" in log["prices_raw"]["last_error"]
    assert "index" in log and "finance" not in log


# ------------------------------------------------------------------------------------------------ E6 retries and fewer calls
def test_e6_a_request_is_tried_again_on_a_network_error_and_given_up_at_once_on_a_404(monkeypatch):
    calls = []

    def flaky(req, timeout):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", None, None)
        if len(calls) == 2:
            raise urllib.error.URLError("reset")
        return b"ok"

    monkeypatch.setattr(fd, "_open", flaky)
    assert fd._get("https://example.invalid/x", pauses=(0, 0)) == b"ok" and len(calls) == 3
    calls.clear()

    def gone(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 404, "not found", None, None)

    monkeypatch.setattr(fd, "_open", gone)
    with pytest.raises(urllib.error.HTTPError):
        fd._get("https://example.invalid/x", pauses=(0, 0))
    assert len(calls) == 1
    calls.clear()

    def dead(req, timeout):
        calls.append(1)
        raise TimeoutError("timed out")

    monkeypatch.setattr(fd, "_open", dead)
    with pytest.raises(TimeoutError):
        fd._get("https://example.invalid/x", pauses=(0, 0))
    assert len(calls) == 3


def test_e6_announcements_ask_for_the_days_since_the_last_fetch_not_fourteen(home, monkeypatch):
    today = date(2026, 11, 10)
    assert fd.days_to_fetch("2026-11-09T20:50:00Z", today) == 3          # yesterday evening: today, yesterday and one of overlap
    assert fd.days_to_fetch("2026-11-10T07:00:00Z", today) == 2
    assert fd.days_to_fetch("2026-11-03T20:50:00Z", today) == 9
    assert fd.days_to_fetch("2026-09-01T20:50:00Z", today) == 14 and fd.days_to_fetch(None, today) == 14
    posts = []
    monkeypatch.setattr(fd, "_get", lambda url, method="GET", **k: posts.append(url) or b'{"data": {"messages": []}}')
    fd.fetch_announcements(["AAA"])
    assert len(posts) == 14                                              # an empty cache: the full window
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    item = {"id": 1, "code": "AAA", "title": "x", "time": yesterday, "category": "", "url": "u", "issuer": "A"}
    (fd.cache_dir() / "announcements.json").write_text(json.dumps({"items": [item], "fetched_at": yesterday}), encoding="utf-8")
    posts.clear()
    doc = fd.fetch_announcements(["AAA"])
    assert len(posts) == 3 and [a["id"] for a in doc["items"]] == [1]    # and what was cached is kept


def test_e6_insiders_list_the_year_from_the_last_listing(home, monkeypatch):
    asked = []
    monkeypatch.setattr(ins, "_list", lambda code, start, end: asked.append((code, start, end)) or [])
    monkeypatch.setattr(ins.time, "sleep", lambda s: None)
    doc = ins.fetch(["AAA"], start_year=2026, today=date(2026, 11, 9), log=lambda s: None)
    assert asked == [("AAA", date(2026, 1, 1), date(2026, 11, 9))] and doc["listed_to"] == {"AAA": "2026-11-09"}
    fd.write(ins.cache_name(), doc)
    asked.clear()
    ins.fetch(["AAA", "BBB"], start_year=2026, today=date(2026, 11, 10), log=lambda s: None)
    assert asked == [("AAA", date(2026, 11, 8), date(2026, 11, 10)), ("BBB", date(2026, 1, 1), date(2026, 11, 10))]


def test_e6_one_newspaper_down_is_partial_and_named_and_a_consensus_failure_is_on_record(home, monkeypatch):
    rss = b"<rss><channel><item><title>Alpha stiger</title><link>https://e/1</link><pubDate>Mon, 09 Nov 2026 10:00:00 +0100</pubDate></item></channel></rss>"

    def get(url, method="GET", **k):
        if "dn.no" in url:
            raise urllib.error.URLError("down")
        return rss

    monkeypatch.setattr(fd, "_get", get)
    fd.write("news", src.timed("news", fd.fetch_news))
    now = pd.Timestamp.now(tz="Europe/Oslo").tz_localize(None)
    st = _by_key(now)["news"]
    assert st["state"] == "partial" and "DN" in st["detail"] and st["state_no"] == "delvis"
    assert src.not_ok([st]) == []                        # partial is shown on data health, not shouted on the front page

    def http(code):
        def f(url, **k):
            raise urllib.error.HTTPError(url, code, "x", None, None)
        return f

    monkeypatch.setattr(fd, "_get", http(404))
    assert rp.fetch_consensus("sats", 2026, 3) is None
    st = _by_key(now)["consensus"]
    assert st["state"] == "ok" and "ingen konsensus publisert" in st["detail"]
    monkeypatch.setattr(fd, "_get", http(500))
    assert rp.fetch_consensus("sats", 2026, 3) is None
    st = _by_key(now)["consensus"]
    assert st["state"] == "failed" and "HTTP 500" in st["error"] and src.not_ok([st]) == [st]
