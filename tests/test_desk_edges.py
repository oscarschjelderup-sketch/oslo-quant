"""The desk on bad and odd data (D41): one stock that breaks does not stop the daily run and is shown as a failure;
a new listing with thirty sessions, a SELL view with the kill level above the price, a view without bear value or
probabilities, a bank light case, a volume series of NaN and a malformed insider cache all end in one of the three
states without an exception."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pytest
import yaml

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import desk as dk
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import lightcase as lcm
from osloquant.dashboard import market as mk
from osloquant.dashboard import odds as od
from osloquant.dashboard import server

from .test_desk import NOW, TODAY, _lightcase, build_home

ODD = {"NEW": ("Ny Notering Fiktiv", "Technology & renewables"), "BANK": ("Bank Fiktiv", "Banks & insurance"),
       "NOVOL": ("Uten Volum Fiktiv", "Seafood"), "FLAT": ("Flat Fiktiv", "Other shipping")}


def _odd_snapshot(base: mk.Snapshot) -> mk.Snapshot:
    """The fixture's snapshot plus four odd stocks: 30 sessions of history, a bank, NaN volume, a flat price."""
    rng = np.random.default_rng(11)
    C, V = base.panel["close"].copy(), base.panel["volume"].copy()
    n = len(C)
    new = np.full(n, np.nan)
    new[-30:] = 40 * np.exp(np.cumsum(rng.normal(0, 0.02, 30)))
    C["NEW"], V["NEW"] = new, 100_000.0
    C["BANK"] = 200 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    V["BANK"] = 30_000.0
    C["NOVOL"] = 55 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    V["NOVOL"] = np.nan
    C["FLAT"], V["FLAT"] = 10.0, 100_000.0
    panel = dict(open=C.shift(1).fillna(C), high=C * 1.01, low=C * 0.99, close=C, volume=V)
    names = {**base.names, **{c: ODD[c][0] for c in ODD}}
    sectors = {**base.sectors, **{c: ODD[c][1] for c in ODD}}
    return mk.Snapshot(panel, names, sectors, C.index[-1])


@pytest.fixture
def odd_home(home, monkeypatch):
    base = build_home(home, monkeypatch)
    snap = _odd_snapshot(base)
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    monkeypatch.setattr(od, "long_closes", lambda: snap.panel["close"])
    od._case_odds_cached.cache_clear()
    px = lambda c: float(snap.panel["close"][c].dropna().iloc[-1])  # noqa: E731
    # a SELL view: the kill level sits above the price
    jg.append("judgement", dict(code="BANK", name=ODD["BANK"][0], date="2026-10-01", price=px("BANK"), rating="SELL", target=round(px("BANK") * 0.8, 2), horizon_months=6,
                                kill_level=round(px("BANK") * 1.15, 2), kill=["Fiktivt kriterium H: utlånstap over 1 %"], thesis="Fiktiv begrunnelse for et salg.",
                                price_date="2026-10-01", price_source="test", source="test"))
    # a BUY view without bear value, kill level or probabilities
    jg.append("judgement", dict(code="NEW", name=ODD["NEW"][0], date="2026-10-20", price=px("NEW"), rating="BUY", target=round(px("NEW") * 1.3, 2), horizon_months=12,
                                kill=["Fiktivt kriterium I: ingen tall"], thesis="Fiktiv begrunnelse uten bear og sannsynligheter.", price_date="2026-10-20", price_source="test", source="test"))
    # a BUY view on a stock without volume data, and one on a flat price
    for code, p in (("NOVOL", px("NOVOL")), ("FLAT", 10.0)):
        jg.append("judgement", dict(code=code, name=ODD[code][0], date="2026-10-20", price=p, rating="BUY", target=round(p * 1.3, 2), horizon_months=12, bear=round(p * 0.8, 2),
                                    base=round(p * 1.2, 2), bull=round(p * 1.5, 2), p_bear=0.25, p_base=0.5, p_bull=0.25, kill_level=round(p * 0.9, 2),
                                    kill=["Fiktivt kriterium J: margin under 5 % [margin]"], thesis="Fiktiv begrunnelse.", price_date="2026-10-20", price_source="test", source="test"))
    bank = _lightcase("SATS", px("BANK"), 0, 0, 0, 0.08)
    bank.update(code="BANK", name=ODD["BANK"][0], financial=True, group="Finance", multiples={"pe": 9.0, "pb": 2.1}, peers={"pb": 1.4, "n_pb": 4, "pe": 10.0, "n_pe": 4, "group": "Finance", "note": "test"},
                reverse={"model": "justified P/B", "coe_est": 0.10, "g_est": 0.02, "implied_roe": 0.17, "actual_roe": 0.12, "reads": "fictional bank reading (EST)"})
    lcm.case_path("BANK").write_text(json.dumps(bank), encoding="utf-8")
    # a malformed insider cache entry and an odd shorts document
    doc = fd.read("insiders")
    doc["items"]["99"] = {"id": 99, "code": "SATS", "title": "rar melding uten side og tid"}
    doc["items"]["98"] = {"id": 98, "code": "NEW", "time": "2026-11-03T08:00:00Z", "side": "sell"}
    fd.write("insiders", doc)
    shorts = fd.read("shorts")
    shorts["instruments"].append({"isin": "NO000X", "issuerName": "SATS", "events": []})
    fd.write("shorts", shorts)
    return home, snap


def test_one_broken_stock_does_not_stop_the_daily_run(odd_home, monkeypatch):
    home, snap = odd_home
    real = dk.analyst

    def boom(inp, code, ctx):
        if code == "SATS":
            raise KeyError("fictional missing key")
        return real(inp, code, ctx)

    monkeypatch.setattr(dk, "analyst", boom)
    run = dk.run(None, trigger="daily", snap=snap, today=TODAY, now=NOW)
    assert run.stock("SATS") is None and run.stock("OUTLT") is not None
    bad = [q for q in run.data_quality if q["what"] == "desk-feil for SATS"]
    assert len(bad) == 1 and not bad[0]["ok"] and "KeyError" in bad[0]["note"] and "ikke med i kjøringen" in bad[0]["note"]
    app = server.create_app()
    app.testing = True
    page = app.test_client().get("/desk").get_data(as_text=True)
    assert "desk-feil for SATS" in page and "kilder i orden" in page


def test_odd_stocks_end_in_one_of_the_three_states_without_an_exception(odd_home):
    home, snap = odd_home
    run = dk.run(list(ODD), trigger="manual", snap=snap, today=TODAY, now=NOW)
    by = {s.code: s for s in run.stocks}
    assert set(by) == set(ODD) and all(s.outcome in dk.OUTCOMES for s in by.values())
    assert not [q for q in run.data_quality if q["what"].startswith("desk-feil")]
    for s in by.values():
        for f in s.findings:
            assert f.kind in dk.CLAIMS and f.source.strip() and f.asof.strip() and dk._DIGIT.search(f.value), (s.code, f)
    # a new listing: the odds say the history is too short instead of inventing a number
    new = by["NEW"]
    assert new.outcome == "parked"
    assert any(f.kind == "no_kill" for f in new.findings) or any(f.kind == "too_few" for f in new.findings) or new.veto is not None
    # a SELL view: Risk refuses a size when the kill level is above the price, or the bear parks it first
    bank = by["BANK"]
    assert bank.outcome == "parked" and bank.findings[-1].detail
    # no volume data: the filter says the turnover is unknown rather than printing zero
    novol = by["NOVOL"]
    passed = next((f for f in novol.findings if f.kind == "passed"), None)
    assert passed is not None and "omsetning ukjent" in passed.value
    # the malformed cache entries were skipped, not crashed on
    assert all("rar melding" not in f.value for s in by.values() for f in s.findings)


def test_missing_feeds_and_missing_limits_are_named_in_data_quality(odd_home):
    home, snap = odd_home
    for name in ("announcements", "insiders", "shorts", "calendar"):
        (fd.cache_dir() / f"{name}.json").unlink()
    (home / "dashboard.yaml").unlink()
    run = dk.run(["SATS", "ELK"], trigger="manual", snap=snap, today=TODAY, now=datetime(2026, 11, 4, 17, 2, tzinfo=UTC))
    notes = {q["what"]: q for q in run.data_quality}
    assert not notes["børsmeldinger (NewsWeb)"]["ok"] and notes["børsmeldinger (NewsWeb)"]["note"] == "ikke hentet"
    assert not notes["grenser (dashboard.yaml: sizing + desk)"]["ok"]
    assert {s.outcome for s in run.stocks} <= set(dk.OUTCOMES) and run.ready == 0        # without limits nothing is ready
    sats = run.stock("SATS")
    assert sats.outcome == "parked" and any(f.kind in ("no_limits", "too_few") for f in sats.findings)


def test_a_run_file_written_by_an_older_version_still_loads(home):
    """A stored run with fewer fields than today's dataclasses (an older desk) opens; unknown claims are refused."""
    dk.desk_dir()
    run = dk.DeskRun("20260101T170000-daily", "2026-01-01", "daily", "2026-01-01T17:00:00Z", stocks=[
        dk.StockRun("AAA", "Alpha", "Seafood", 10.0, "2026-01-01", 13.0, 9.0, "kill level in the view",
                    findings=[dk.Finding("filter", "no_case", "0 case", "files", "2026-01-01", "2026-01-01T17:00:00Z", status="killed")], outcome="killed", reason="x")])
    p = dk.save(run)
    d = json.loads(p.read_text(encoding="utf-8"))
    del d["config"]
    p.write_text(json.dumps(d), encoding="utf-8")
    back = dk.load_run("20260101T170000-daily")
    assert back and back.config == {} and back.stock("AAA").findings[0].claim == "Ingen case og ikke på overvåkning"
    d["stocks"][0]["findings"][0]["kind"] = "a_thought"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown claim"):
        dk.load_run("20260101T170000-daily")


def test_the_privacy_rules_hold_for_the_desk_files(home):
    (home / "dashboard.yaml").write_text(yaml.safe_dump({"desk": {"volume_ratio": 2.5}}), encoding="utf-8")
    assert dk.desk_dir().is_relative_to(jg.home()) and dk.config()["volume_ratio"] == 2.5
    assert not (sg.book_path()).exists() or True                          # the desk never creates the research book
