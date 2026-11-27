"""Rates (D73, holiday plan step 2): the ECB deposit rate from the ECB's own data portal, Norges Bank's rate paths from
the hand-copied resource file against the policy rate, and the sectors' measured link to the Norwegian rates. The ECB
answer here is a fictional copy of the real CSV's columns; the sector data are synthetic with a known answer."""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest

from osloquant.dashboard import feeds as fd
from osloquant.dashboard import macro as mc
from osloquant.dashboard import ratepath as rp
from osloquant.dashboard import sources as src

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home

ECB_CSV = ("KEY,FREQ,REF_AREA,CURRENCY,PROVIDER_FM,INSTRUMENT_FM,PROVIDER_FM_ID,DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE,OBS_STATUS,TITLE\n"
           "FM.B.U2.EUR.4F.KR.DFR.LEV,B,U2,EUR,4F,KR,DFR,LEV,2026-03-18,2.0,A,Deposit facility\n"
           "FM.B.U2.EUR.4F.KR.DFR.LEV,B,U2,EUR,4F,KR,DFR,LEV,2026-06-17,2.25,A,Deposit facility\n"
           "FM.B.U2.EUR.4F.KR.DFR.LEV,B,U2,EUR,4F,KR,DFR,LEV,2026-09-16,2.5,A,Deposit facility\n")


# ------------------------------------------------------------------------------------------------ the ECB
def test_the_ecb_rate_is_the_rate_in_force_on_each_business_day():
    ch = fd.parse_ecb_changes("﻿" + ECB_CSV)
    assert ch == [("2026-03-18", 2.0), ("2026-06-17", 2.25), ("2026-09-16", 2.5)]
    h = fd.steps_to_days(ch, "2026-11-27")
    s = pd.Series(h["v"], index=pd.to_datetime(h["t"]))
    assert s.index[0] == pd.Timestamp("2026-03-18") and s.index[-1] == pd.Timestamp("2026-11-27")
    assert s["2026-06-16"] == 2.0 and s["2026-06-17"] == 2.25 and s["2026-11-27"] == 2.5
    assert all(d.dayofweek < 5 for d in s.index)
    assert len(fd.steps_to_days(ch, "2026-11-27", n=10)["t"]) == 10
    with pytest.raises(ValueError):
        fd.parse_ecb_changes("KEY,TIME_PERIOD,OBS_VALUE\n")


def test_the_macro_feed_keeps_the_ecb_rate_when_the_portal_fails(monkeypatch):
    hist = {"t": ["2026-11-02"], "v": [1.0]}
    monkeypatch.setattr(fd, "_nb_history", lambda flow, n=fd.MACRO_OBS: hist)
    monkeypatch.setattr(fd, "_yahoo_histories", lambda symbols: {k: hist for k in symbols})
    monkeypatch.setattr(fd, "_salmon_history", lambda weeks=160: hist)
    monkeypatch.setattr(fd, "_power_history", lambda old, today=None: hist)
    monkeypatch.setattr(fd, "_get", lambda url, **kw: ECB_CSV.encode())          # only the ECB is asked through _get here
    monkeypatch.setattr(fd, "_ecb_history", lambda today=None: fd.steps_to_days(fd.parse_ecb_changes(fd._get(fd.ECB_DFR).decode()), "2026-11-27"))
    doc = fd.fetch_macro()
    assert doc["series"]["esb"]["v"][-1] == 2.5 and "ESB-statistikk" in doc["source"]
    fd.write("macro", doc)

    def down(today=None):
        raise TimeoutError("portal down")

    monkeypatch.setattr(fd, "_ecb_history", down)
    doc2 = fd.fetch_macro()
    assert doc2["series"]["esb"] == doc["series"]["esb"] and "esb: TimeoutError" in doc2["errors"]
    d = mc.BY_KEY["esb"]
    assert d.group == "Renter" and d.steps and d.source.startswith("ESB-statistikk")


# ------------------------------------------------------------------------------------------------ the rate paths
def test_the_path_file_holds_real_reports_with_their_sources():
    doc = rp.load_paths()
    reps = doc["reports"]
    assert len(reps) >= 7 and [r["published"] for r in reps] == sorted(r["published"] for r in reps)
    assert doc["copied"] and doc["source"].startswith("https://www.norges-bank.no/")
    for r in reps:
        assert r["url"].startswith("https://www.norges-bank.no/") and r["data"].endswith(".xlsx") and r["report"].startswith("PPR ")
        qs = sorted(rp.quarter(q) for q in r["path"])
        assert qs[0] == r["published"].to_period("Q") and len(qs) >= 12, r["report"]      # from the report's own quarter on
        assert all(0 <= v <= 10 for v in r["path"].values())
    assert reps[-1]["report"] == "PPR 3/26" and reps[-1]["path"]["2026Q4"] == 4.51         # as printed in the bank's workbook


def test_a_newer_report_than_the_file_is_said():
    doc = rp.load_paths()
    meetings = {"dates": [{"date": "2026-11-05", "what": "Rentebeslutning (kl. 10.00)"},
                          {"date": "2026-12-17", "what": "Rentebeslutning og pengepolitisk rapport (kl. 10.00)"}]}
    assert rp.refill_note(pd.Timestamp("2026-11-27"), doc, meetings) is None
    assert rp.refill_note(pd.Timestamp("2026-12-17"), doc, meetings) is None                 # out at 10.00: counted from the next day
    note = rp.refill_note(pd.Timestamp("2026-12-18"), doc, meetings)
    assert note.startswith("Rentebanen må fylles på") and "17. des. 2026" in note and "PPR 3/26" in note
    assert "mangler" in rp.refill_note(pd.Timestamp("2026-12-18"), None, meetings)


def _rate() -> pd.Series:
    d = pd.bdate_range("2025-01-01", "2026-11-26")
    return pd.Series(np.where(d < pd.Timestamp("2025-06-20"), 4.5, np.where(d < pd.Timestamp("2026-05-08"), 4.0, 4.25)), index=d)


def test_what_was_signalled_against_what_happened():
    doc = {"reports": [{"report": "PPR X", "published": pd.Timestamp("2025-03-27"), "url": "https://x",
                        "path": {"2025Q1": 4.5, "2025Q2": 4.4, "2025Q3": 4.2, "2025Q4": 4.0, "2026Q1": 3.8, "2026Q4": 3.5}}]}
    q = rp.quarterly_actual(_rate())
    assert rp.quarter("2026Q4") not in q.index and q[rp.quarter("2025Q3")] == 4.0          # an unfinished quarter is left out
    row = rp.signal_rows(doc, _rate())[0]
    assert row["next"]["said"] == 4.4 and row["next"]["was"] == pytest.approx(q[rp.quarter("2025Q2")])
    assert row["year"]["said"] == 3.8 and row["year"]["was"] == 4.0
    assert row["n"] == 4 and row["gap"] == pytest.approx(np.mean([q[rp.quarter("2025Q2")] - 4.4, 4.0 - 4.2, 4.0 - 4.0, 4.0 - 3.8]))


def test_the_chart_data_sit_on_one_even_weekly_grid():
    raw = rp.chart_json(rp.load_paths(), _rate())
    data = json.loads(re.search(r'id="rp-data">(.*)</script>', raw, re.S).group(1))
    grid = pd.to_datetime(data["grid"])
    assert (grid.dayofweek == 4).all() and set(np.diff(grid.values).astype("timedelta64[D]").astype(int)) == {7}
    assert set(data["actual"]["t"]) <= set(data["grid"]) and data["actual"]["v"][-1] == 4.25
    newest = next(p for p in data["paths"] if p["rank"] == 0)
    assert newest["name"] == "PPR 3/26" and set(newest["t"]) <= set(data["grid"]) and newest["q"][0] == "3. kv. 2026"


# ------------------------------------------------------------------------------------------------ rates and the sectors
def _market(weeks: int = 160, seed: int = 4):
    """Weekly synthetic prices: «Finance» falls 2 % beyond the market per +0.25 pp in the 10-year rate; «Energy» has
    no link to it. The 3-month rate is noise."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end="2026-11-20", periods=weeks * 5)
    fri = pd.date_range(end="2026-11-20", periods=weeks, freq="W-FRI")
    d10 = pd.Series(rng.normal(0, 0.08, weeks), index=fri)
    mkt = pd.Series(rng.normal(0.001, 0.02, weeks), index=fri)
    cols = {}
    for i in range(4):
        cols[f"F{i}"] = mkt - 0.08 * d10 + rng.normal(0, 0.01, weeks)
        cols[f"E{i}"] = mkt + rng.normal(0, 0.01, weeks)
    closes = (100 * np.exp(pd.DataFrame(cols).cumsum())).reindex(days, method="ffill").bfill()
    series = {"stat10y": (4 + d10.cumsum()).reindex(days, method="ffill").bfill(),
              "stat3m": pd.Series(4 + np.cumsum(rng.normal(0, 0.03, len(days))), index=days),
              "osebx": (1500 * np.exp(mkt.cumsum())).reindex(days, method="ffill").bfill()}
    groups = {c: "Finance" if c.startswith("F") else "Energy" for c in cols}
    return closes, series, groups


def test_the_sector_link_is_measured_and_no_link_is_said():
    closes, series, groups = _market()
    t = rp.sector_rates(closes, series, groups)
    fin = t[(t["group"] == "Finance") & (t["driver"] == "stat10y")].iloc[0]
    en = t[(t["group"] == "Energy") & (t["driver"] == "stat10y")].iloc[0]
    assert fin["beta"] == pytest.approx(-2.0, abs=0.4) and fin["t"] < -5 and fin["stocks"] == 4 and fin["n"] >= 150
    assert abs(en["t"]) < 2
    html = rp.sector_section(t, pd.DataFrame(columns=["group", "beta", "t", "n"]), {**series, "styringsrente": _rate()}, ["Energy", "Finance"], [])
    assert "Målbar sammenheng:</b> Finans og 10 års stat" in html and "Ingen målbar følsomhet for 10 års stat:</b> Energi" in html
    assert "uker" in html and "ikke årsak og ikke en prognose" in html and "Ikke målt:</b> styringsrenten selv (2 endringer" in html
    for word in ("kjøp", "selg", "BUY", "SELL"):
        assert word not in html


def test_report_days_are_counted():
    closes, series, groups = _market()
    doc = {"reports": [{"report": f"PPR {i}", "published": d, "path": {"2027Q1": 4.0 + 0.1 * i * i, "2027Q2": 3.9 + 0.1 * i * i}}
                       for i, d in enumerate(pd.date_range("2025-06-06", periods=5, freq="8W-FRI"))]}
    revs = rp.path_revisions(doc)
    assert len(revs) == 4 and revs[0]["revision"] == pytest.approx(0.1) and revs[0]["quarters"] == 2
    ev = rp.report_day_moves(closes, series["osebx"], groups, doc)
    assert set(ev["group"]) == {"Energy", "Finance"} and (ev["n"] == 4).all()


# ------------------------------------------------------------------------------------------------ the page and the sources
def test_the_macro_page_shows_the_path_the_ecb_and_the_sectors(app):  # noqa: F811
    client, _ = app
    d = pd.bdate_range(end="2026-11-26", periods=800)
    rng = np.random.default_rng(5)
    s = {"styringsrente": pd.Series(4.5, index=d), "stat10y": pd.Series(4 + np.cumsum(rng.normal(0, 0.02, 800)), index=d),
         "stat3m": pd.Series(4.5 + np.cumsum(rng.normal(0, 0.01, 800)), index=d), "esb": pd.Series(2.5, index=d)}
    s["esb"].iloc[:300] = 2.25
    fd.write("macro", {"series": {k: {"t": [f"{x:%Y-%m-%d}" for x in v.index], "v": [float(y) for y in v]} for k, v in s.items()}, "errors": [], "source": "test"})
    html = client.get("/makro").get_data(as_text=True)
    assert 'id="rentebane"' in html and 'id="rp-chart"' in html and 'id="rp-data"' in html and "/static/ratepath.js" in html
    assert html.index('id="rentebane"') < html.index('id="g-valuta"')                      # under the rate cards
    assert "PPR 3/26" in html and "figurdataene" in html and "Norges Banks åpne data" in html
    assert 'id="renter-sektorer"' in html
    assert 'id="d-esb"' in html and "sist endret" in html and fd.ECB_TERMS in html and "ESB-statistikk" in html
    assert client.get("/static/ratepath.js").status_code == 200


def test_the_path_file_is_a_source_on_the_data_health_page():
    st = {s["key"]: s for s in src.status(pd.Timestamp("2026-11-27 12:00"))}
    assert st["ratepath"]["state"] == "ok" and "PPR 3/26" in st["ratepath"]["detail"] and st["ratepath"]["last_ok"] == pd.Timestamp("2026-11-27")
    late = {s["key"]: s for s in src.status(pd.Timestamp("2026-12-18 12:00"))}["ratepath"]
    assert late["state"] == "stale" and "fylles på" in late["detail"]
    assert "ESB" in {s["key"]: s for s in src.status()}["macro"]["origin"]
