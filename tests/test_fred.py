"""FRED (DECISIONS D70): the owner's key is read from the private home and never written anywhere, a series whose notes
carry a copyright line is never used, a rejected key stops at the first request, no key is no alarm, and the page
shows the notice the FRED API terms require and the US release dates. No network: the requests are faked."""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import date

import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import macro as mc
from osloquant.dashboard import macropage as mp

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home

KEY = "abcdef0123456789abcdef0123456789"          # a made-up key of the right shape


def _save_key(text: str = KEY) -> None:
    p = jg.home() / "keys" / "fred.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _others(monkeypatch) -> None:
    """Norges Bank, Yahoo, SSB and the power price answer with one small series each."""
    hist = {"t": ["2026-11-06", "2026-11-09"], "v": [1.0, 2.0]}
    monkeypatch.setattr(fd, "_nb_history", lambda flow, n=fd.MACRO_OBS: hist)
    monkeypatch.setattr(fd, "_yahoo_histories", lambda symbols: {k: hist for k in symbols})
    monkeypatch.setattr(fd, "_salmon_history", lambda weeks=160: hist)
    monkeypatch.setattr(fd, "_power_history", lambda old, today=None: hist)


def _fred_server(notes: dict[str, str] | None = None, calls: list | None = None):
    """A fake FRED: series metadata, observations with FRED's «.» for a missing day, and release dates."""
    notes = notes or {}
    today = date.today()

    def get(url, *a, **k):
        if calls is not None:
            calls.append(url)
        assert url.startswith(fd.FRED) and f"api_key={KEY}" in url and "file_type=json" in url
        sid = url.split("series_id=")[1].split("&")[0] if "series_id=" in url else None
        if "/series/observations?" in url:
            return json.dumps({"observations": [{"date": "2026-11-05", "value": "4.10"}, {"date": "2026-11-06", "value": "."},
                                                {"date": "2026-11-09", "value": "4.05"}]}).encode()
        if "/series?" in url:
            return json.dumps({"seriess": [{"id": sid, "notes": notes.get(sid, "Public domain.")}]}).encode()
        if "/release/dates?" in url:
            rid = int(url.split("release_id=")[1].split("&")[0])
            ds = [today - pd.Timedelta(days=3), today + pd.Timedelta(days=5 + rid % 7), today + pd.Timedelta(days=400)]
            return json.dumps({"release_dates": [{"release_id": rid, "date": f"{d:%Y-%m-%d}"} for d in ds]}).encode()
        raise AssertionError(url)
    return get


def test_the_key_is_read_from_the_private_home_or_the_environment_and_a_malformed_one_is_refused(monkeypatch):
    assert fd.fred_key() == (None, "mangler")
    _save_key("  " + KEY + "\n")
    assert fd.fred_key() == (KEY, "ok")
    _save_key("not-a-key")
    assert fd.fred_key() == (None, "feil format")
    monkeypatch.setenv("FRED_API_KEY", KEY.upper())
    assert fd.fred_key() == (KEY.upper(), "ok")                                        # the environment wins over the file


def test_without_a_key_nothing_is_asked_and_nothing_is_an_alarm(monkeypatch):
    _others(monkeypatch)
    monkeypatch.setattr(fd, "_get", lambda *a, **k: pytest.fail("FRED was asked without a key"))
    doc = fd.fetch_macro()
    assert doc["errors"] == [] and doc["fred"]["key"] == "mangler" and doc["releases"] == []
    assert not set(fd.MACRO_FRED) & set(doc["series"]) and "FRED" not in doc["source"]
    fd.write("macro", doc)
    html = mp.driver_card(mc.BY_KEY["us2y"], mc.load(), pd.DataFrame(), {})
    assert "Krever en gratis nøkkel fra FRED" in html and "keys/fred.txt" in html


def test_the_series_and_the_release_dates_come_in_and_the_key_is_written_nowhere(monkeypatch):
    _others(monkeypatch)
    _save_key()
    monkeypatch.setattr(fd, "_get", _fred_server())
    doc = fd.fetch_macro()
    assert set(fd.MACRO_FRED) <= set(doc["series"]) and doc["fred"] == {"key": "ok", "series": sorted(fd.MACRO_FRED), "refused": []}
    assert doc["series"]["us2y"] == {"t": ["2026-11-05", "2026-11-09"], "v": [4.10, 4.05]}          # FRED's «.» is a missing day, not a zero
    today = f"{date.today():%Y-%m-%d}"
    assert doc["releases"] and all(today <= r["date"] for r in doc["releases"]) and {r["release_id"] for r in doc["releases"]} == set(fd.FRED_RELEASES)
    assert all(r["date"] <= f"{date.today() + pd.Timedelta(days=fd.FRED_RELEASE_DAYS):%Y-%m-%d}" for r in doc["releases"])
    assert "FRED (St. Louis Fed)" in doc["source"]
    fd.write("macro", doc)
    for p in jg.home().rglob("*"):
        if p.is_file() and p.name != "fred.txt":
            assert KEY not in p.read_text(encoding="utf-8", errors="replace"), p          # not in the feed, not in the run log


def test_a_series_with_a_copyright_line_is_never_used_and_an_old_copy_is_dropped(monkeypatch):
    _others(monkeypatch)
    _save_key()
    fd.write("macro", {"series": {"dollar": {"t": ["2026-11-02"], "v": [120.0]}}, "errors": []})
    monkeypatch.setattr(fd, "_get", _fred_server(notes={"DTWEXBGS": "Copyright, 2026, Some Index Owner. All rights reserved."}))
    doc = fd.fetch_macro()
    assert "dollar" not in doc["series"] and doc["fred"]["refused"] == ["dollar"]
    assert "dollar: opphavsrett i serienotatet – ikke brukt (FRED-vilkårene)" in doc["errors"]
    assert {"us2y", "fed"} <= set(doc["series"])
    assert "esb" not in fd.MACRO_FRED and "ECBDFR" not in fd.MACRO_FRED.values()       # checked on the real API 10 Nov 2026: the ECB rate is marked «Copyright»


def test_a_rejected_key_stops_at_the_first_request_and_is_never_in_an_error(monkeypatch):
    _others(monkeypatch)
    _save_key()
    calls = []

    def reject(url, *a, **k):
        calls.append(url)
        body = b'{"error_code":400,"error_message":"Bad Request.  The value for variable api_key is not registered."}'
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr(fd, "_get", reject)
    doc = fd.fetch_macro()
    assert len(calls) == 1 and doc["fred"]["key"] == "avvist" and doc["errors"] == ["FRED: FRED avviste nøkkelen (HTTP 400)"]
    assert KEY not in json.dumps(doc)
    fd.write("macro", doc)
    html = mp.driver_card(mc.BY_KEY["fed"], mc.load(), pd.DataFrame(), {})
    assert "FRED avviste nøkkelen" in html


def test_an_error_that_carries_the_url_never_carries_the_key(monkeypatch):
    _save_key()
    assert fd._scrub(f"URLError: https://api.stlouisfed.org/fred/series?api_key={KEY}", KEY).endswith("api_key=<nøkkel>")

    def boom():
        raise ValueError(f"failed https://api.stlouisfed.org/fred/series?api_key={KEY}")

    for name in ("announcements", "rates", "fx", "salmon", "brent", "news", "calendar"):
        monkeypatch.setattr(fd, f"fetch_{name}", lambda: {"items": [], "errors": []}, raising=False)
    monkeypatch.setattr(fd, "fetch_macro", boom)
    from osloquant.dashboard import calendar as cal
    from osloquant.dashboard import insiders as ins

    monkeypatch.setattr(ins, "fetch_shorts", lambda: {"items": []})
    monkeypatch.setattr(ins, "fetch", lambda *a, **k: {"items": []})
    monkeypatch.setattr(cal, "fetch_financial_calendars", lambda codes: {"items": []})
    out = fd.refresh([])
    assert KEY not in out["macro"] and "<nøkkel>" in out["macro"]


def test_the_macro_page_shows_the_fred_notice_and_the_us_releases(app, monkeypatch):  # noqa: F811
    client, _ = app
    soon = f"{date.today() + pd.Timedelta(days=6):%Y-%m-%d}"
    fd.write("macro", {"series": {"us2y": {"t": ["2026-11-06", "2026-11-09"], "v": [4.1, 4.05]}}, "errors": [], "source": "test",
                       "fred": {"key": "ok", "series": ["us2y"], "refused": []}, "releases": [{"date": soon, "release_id": 10, "what": "KPI i USA"}]})
    html = client.get("/makro").get_data(as_text=True)
    assert 'id="fred-notice"' in html and fd.FRED_NOTICE.replace("®", "") in html.replace("®", "").replace("&#174;", "")
    assert fd.FRED_TERMS in html
    assert "Tallslipp: KPI i USA" in html and "FRED-kalenderen (St. Louis Fed)" in html
    assert 'href="/aksje/USA"' not in html                                             # the country is not a ticker
    assert 'id="d-us2y"' in html and 'id="d-dollar"' in html
    # without FRED data there is no FRED notice: the page does not claim to use what it does not use
    fd.write("macro", {"series": {}, "errors": [], "source": "test", "fred": {"key": "mangler", "series": [], "refused": []}, "releases": []})
    html = client.get("/makro").get_data(as_text=True)
    assert 'id="fred-notice"' not in html and "Tallslipp i USA kommer med FRED-nøkkelen" in html
