"""The data-health page: stale stocks, long gaps and big moves in a synthetic panel; feed ages against their limits;
the one-line problem list; the dividend-audit matcher on fake NewsWeb replies; and the page rendering."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from osloquant.dashboard import datahealth as dh
from osloquant.dashboard import feeds as fd

from .helpers import business_days


def _closes():
    n = 300
    dates = business_days(n, "2025-08-01")
    rng = np.random.default_rng(0)
    c = pd.DataFrame({k: 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))) for k in ("AAA", "BBB", "CCC")}, index=dates)
    c.loc[dates[-1], "BBB"] = np.nan                       # stale: no close on the newest session
    c.loc[dates[100:140], "CCC"] = np.nan                   # a 40-session source gap
    c.loc[dates[-5], "AAA"] = c.loc[dates[-6], "AAA"] * 1.4  # a 40 % day
    return c


def test_price_health_finds_stale_gaps_and_big_moves():
    c = _closes()
    h = dh.price_health(c)
    assert h["stale"] == ["BBB"] and h["with_gaps"] == ["CCC"]
    ccc = next(r for r in h["rows"] if r["code"] == "CCC")
    assert ccc["gaps"][0][2] == 40 and ccc["missing_250"] >= 40
    aaa = next(r for r in h["rows"] if r["code"] == "AAA")
    assert len(aaa["big_moves"]) == 2 and aaa["big_moves"][0][1] > 0.3     # the jump up and the drop back


def test_feed_health_ages_against_limits(home):
    now = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)
    (fd.cache_dir() / "rates.json").write_text(json.dumps({"value": 1, "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}), encoding="utf-8")
    (fd.cache_dir() / "shorts.json").write_text(json.dumps({"instruments": [], "fetched_at": (now - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%SZ")}), encoding="utf-8")
    rows = {r["feed"]: r for r in dh.feed_health(now=now)}
    assert rows["rates"]["status"] == "ok" and rows["shorts"]["status"] == "stale" and rows["news"]["status"] == "never fetched"
    assert rows["shorts"]["age_days"] >= 8.9 and rows["shorts"]["limit_days"] == 7


def test_problem_list_and_page(home, monkeypatch):
    c = _closes()
    monkeypatch.setattr(dh, "store_health", lambda: {"adjusted": {"last": "2026-10-30", "entities": 3, "rows": 900}})
    ov = dh.overview(c, [], c.index[-1])
    probs = dh.problems(ov)
    assert any("BBB" in x for x in probs) and any("utbytterevisjonen er aldri kjørt" in x for x in probs)
    assert any(x.startswith("Børsmeldinger (Oslo Børs NewsWeb): aldri hentet") for x in probs)      # the sources list (D60), in Norwegian
    html = dh.page_html(ov)
    assert "Datahelse" in html and "BBB" in html and "Ting å vite nå" in html and "Ikke kjørt" in html
    fd.write(dh.AUDIT_FILE, {"since": "2010-01-01", "stocks": 3, "notices": 10, "missed": [
        {"code": "AAA", "date": "2015-02-18", "amount": 3.4, "price": 96.1, "yield": 0.0354, "adjusted": False, "url": "https://newsweb.oslobors.no/message/1"}],
        "missed_yield_by_code": {"AAA": 0.0354}, "failed": [], "source": "test"})
    ov = dh.overview(c, [], c.index[-1])
    assert any("1 ex-utbyttemeldinger uten Yahoo-justering" in x for x in dh.problems(ov))
    assert "3.5%" in dh.page_html(ov)


def test_dividend_audit_matches_notices_to_factor_jumps(monkeypatch):
    dates = business_days(120, "2015-01-02")
    raw = pd.DataFrame({"AAA": np.full(120, 100.0), "BBB": np.full(120, 50.0)}, index=dates)
    adj = raw.copy()
    adj.loc[:dates[59], "AAA"] *= 0.97                                           # a 3 % dividend adjusted on day 60
    ex_a, ex_b = f"{dates[60]:%Y-%m-%d}", f"{dates[80]:%Y-%m-%d}"
    replies = {"AAA": [{"messageId": 1, "title": "AAA: Ex-dividend NOK 3.00 today", "publishedTime": ex_a + "T06:00:00Z"}],
               "BBB": [{"messageId": 2, "title": "BBB: Eks utbytte NOK 1,00 i dag", "publishedTime": ex_b + "T06:00:00Z"},
                       {"messageId": 3, "title": "BBB: something else", "publishedTime": ex_b + "T07:00:00Z"}]}
    monkeypatch.setattr(fd, "_get", lambda url, method="GET", timeout=20: json.dumps({"data": {"messages": replies["AAA" if "issuer=AAA" in url else "BBB"]}}).encode())
    res = dh.dividend_audit(adj, raw, codes=["AAA", "BBB"], pause=0)
    assert res["notices"] == 2 and [m["code"] for m in res["missed"]] == ["BBB"]        # BBB's 2 % dividend never adjusted
    assert res["missed_yield_by_code"] == {"BBB": 0.02}
