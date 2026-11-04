"""The desk (DECISIONS D41) on a synthetic store and a fictional research book – SATS, OUTLT and ELK with made-up
numbers, never the real book: the chain never ends in a buy and writes nothing to the log or the book; the Bear gets
nothing through with fewer than three reasons with numbers; no role writes free text without a source; the filter,
the veto and the Risk block each end the chain with their reason visible; runs are stored and open from the Desk page,
the stock page and the judgement row; and the veto statistic counts honestly."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
import yaml

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import desk as dk
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import insiders as ins
from osloquant.dashboard import lightcase as lcm
from osloquant.dashboard import market as mk
from osloquant.dashboard import odds as od
from osloquant.dashboard import server
from osloquant.dashboard import testdata as tdata

TODAY = pd.Timestamp("2026-11-04")
NOW = datetime(2026, 11, 4, 16, 45, tzinfo=UTC)
CODES = {"SATS": ("Sats Fiktiv ASA", "Consumer, telecom & real estate"), "OUTLT": ("Outlet Fiktiv ASA", "Consumer, telecom & real estate"),
         "ELK": ("Elkem Fiktiv ASA", "Industrials & materials"), "AAA": ("Alpha Salmon", "Seafood"), "BBB": ("Beta Shipping", "Other shipping"),
         "CCC": ("Gamma Bank", "Banks & insurance"), "DDD": ("Delta Energy", "Exploration & production"), "EEE": ("Epsilon Metals", "Industrials & materials"),
         "FFF": ("Zeta Retail", "Consumer, telecom & real estate"), "GGG": ("Eta Tech", "Technology & renewables"),
         "HHH": ("Theta Materials", "Industrials & materials"), "III": ("Iota Salmon", "Seafood")}
BASE = {"SATS": 100, "OUTLT": 95, "ELK": 30, "AAA": 50, "BBB": 12, "CCC": 200, "DDD": 280, "EEE": 60, "FFF": 40, "GGG": 15, "HHH": 90, "III": 70}
LAST_MOVE = {"OUTLT": 0.96, "ELK": 0.965, "AAA": 1.05}
VOLUME = {"SATS": 50_000.0, "OUTLT": 50_000.0, "ELK": 150_000.0, "AAA": 50_000.0, "DDD": 50_000.0}      # the rest trade 1 000 shares a day


def _snapshot() -> mk.Snapshot:
    rng = np.random.default_rng(7)
    n = 400
    dates = pd.bdate_range(end=TODAY, periods=n)
    close = {}
    for code, b in BASE.items():
        if code == "SATS":
            path = 90 + 10 * np.arange(n) / (n - 1) + rng.normal(0, 0.3, n)      # a gentle uptrend: the odds stay readable
            path[-2], path[-1] = 100.0, 106.0
        elif code == "GGG":
            path = np.linspace(15.5, 15.0, n)                                   # a slow, noiseless slide: no signal can fire
        else:
            walk = np.exp(np.cumsum(rng.normal(0.0002, 0.015, n)))
            path = b * walk / walk[-2]                                          # the day before today closes at the base
            path[-1] = b * LAST_MOVE.get(code, 1.0 + float(rng.normal(0, 0.002)))
        close[code] = path
    C = pd.DataFrame(close, index=dates)
    V = pd.DataFrame({c: VOLUME.get(c, 1_000.0) for c in C.columns}, index=dates)
    for c in ("SATS", "FFF", "DDD"):
        V.iloc[-1, V.columns.get_loc(c)] *= 3
    panel = dict(open=C.shift(1).fillna(C), high=C * 1.01, low=C * 0.99, close=C, volume=V)
    return mk.Snapshot(panel, {c: CODES[c][0] for c in C.columns}, {c: CODES[c][1] for c in C.columns}, dates[-1])


def _lightcase(code: str, px: float, ev_ebit: float, peer_ev_ebit: float, implied_g: float, roic: float) -> dict:
    name, group = CODES[code]
    return {"code": code, "name": name, "group": mk.GROUPS[group], "financial": False, "built_at": "2026-10-20T10:00:00Z",
            "price": {"value": px, "date": "2026-10-20", "source": mk.PRICE_SOURCE}, "shares": 1e8,
            "currency": {"reporting": "NOK", "fx": None, "fx_date": None, "source": "test"}, "mcap_nok": px * 1e8,
            "profit": {k: {"value": v, "period": "LTM to 2026-06-30"} for k, v in (("revenue", 5000e6), ("ebit", 600e6), ("net_income", 400e6), ("fcf", 350e6))},
            "balance": {"net_debt": 1500e6, "equity": 3000e6, "minority": 0, "date": "2026-06-30"},
            "annual": [{"year": y, "revenue": r * 1e6, "ebit": e * 1e6, "net_income": e * 0.7e6, "fcf": e * 0.6e6, "net_debt": 1600e6} for y, r, e in ((2024, 4500, 500), (2025, 4800, 560))],
            "multiples": {"pe": px * 1e8 / 400e6, "pb": px * 1e8 / 3000e6, "ev": px * 1e8 + 1500e6, "ev_ebit": ev_ebit, "ev_sales": 1.5, "fcf_yield": 0.04},
            "returns": {"tax_rate": 0.22, "tax_period": "FY2025", "roe": 0.13, "roic": roic},
            "reverse": {"model": "value driver", "wacc_est": 0.09, "nopat": 468e6, "roic": roic, "implied_g": implied_g, "no_growth_ev": 5200e6, "ev_vs_no_growth": 0.25,
                        "reads": f"fictional reading for {code}: the price pays for {implied_g * 100:+.1f} % growth (EST)"},
            "peers": {"ev_ebit": peer_ev_ebit, "n_ev_ebit": 3, "pe": 12.0, "n_pe": 3, "pb": 1.8, "n_pb": 3, "members": ["SATS", "OUTLT", "FFF"], "group": mk.GROUPS[group], "note": "test"},
            "statements_source": "test statements", "warnings": [], "quarters_through": "2026-06-30"}


def _view(code: str, date: str, price: float, rating: str, target: float, bear: float, base: float, bull: float, probs=(0.25, 0.5, 0.25), kill_level=None,
          kill=(), thesis="Fiktiv begrunnelse: driftsmarginen løftes av høyere volum i eksisterende enheter.", **extra) -> dict:
    return jg.append("judgement", dict(code=code, name=CODES[code][0], date=date, price=price, rating=rating, target=target, horizon_months=12,
                                       bear=bear, base=base, bull=bull, p_bear=probs[0], p_base=probs[1], p_bull=probs[2], kill=list(kill), kill_level=kill_level,
                                       thesis=thesis, price_date=date, price_source="test", source="test", **extra))


def build_home(home, monkeypatch) -> mk.Snapshot:
    snap = _snapshot()
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    monkeypatch.setattr(od, "long_closes", lambda: snap.panel["close"])
    od._case_odds_cached.cache_clear()
    for code, issuer in (("OUTLT", "OUTLET FIKTIV"), ("BBB", "BETA SHIPPING")):
        monkeypatch.setitem(ins.SSR_NAMES, code, issuer)
    (home / "dashboard.yaml").write_text(yaml.safe_dump({"sizing": {"paper_capital": 100000, "max_loss": 2000, "max_position": 0.25, "max_total_loss": 6000, "max_loss_per_group": 3000},
                                                         "desk": {"volume_ratio": 2.0}}), encoding="utf-8")
    sg.book_path().write_text(yaml.safe_dump({"entries": [
        {"code": "SATS", "name": CODES["SATS"][0], "events": [{"date": "2026-12-10", "what": "Q4 2026 report"}]},
        {"code": "ELK", "name": CODES["ELK"][0], "events": [{"date": "2026-10-29", "what": "Q3 2026 report"}]},
        {"code": "AAA", "name": CODES["AAA"][0], "events": [{"date": "2026-08-14", "what": "Q2 2026 report"}]},
        {"code": "DDD", "name": CODES["DDD"][0], "events": []}]}, sort_keys=False), encoding="utf-8")
    _view("SATS", "2026-10-01", 100.0, "BUY", 131, 72, 124, 160, kill_level=86, kill=("Fiktivt kriterium A: klubbmargin under 20 % [margin]", "Fiktivt kriterium B: medlemsvekst under 2 % [volume]"),
          position_shares=90, position_value=9000.0, loss_at_kill=1305.0)
    jg.append("judgement", dict(code="SATS", name=CODES["SATS"][0], date="2026-10-02", price=100.5, rating="BUY", target=140, horizon_months=12, bear=80, base=130, bull=165,
                                p_bear=0.2, p_base=0.55, p_bull=0.25, kill=["Fiktivt kriterium C: churn over 40 %"], thesis="Fiktiv Claude-begrunnelse med tall fra den lette casen.",
                                price_date="2026-10-02", price_source="test", analyst="claude", source="test"))
    _view("ELK", "2026-10-01", 30.0, "BUY", 41, 23, 38, 50, probs=(0.3, 0.5, 0.2), kill_level=26, kill=("Fiktivt kriterium D: silisiummargin under 8 % [margin]", "Fiktivt kriterium E: gjeld over 3x EBITDA [leverage]"),
          position_shares=160, position_value=4800.0, loss_at_kill=664.0)
    _view("AAA", "2026-07-01", 50.0, "HOLD", 55, 40, 54, 65, kill=("Fiktivt kriterium F: laksepris under 60 kr/kg",))
    _view("DDD", "2026-10-10", 280.0, "BUY", 300, 230, 295, 360, probs=(0.2, 0.6, 0.2), kill_level=250, kill=("Fiktivt kriterium G: oljepris under 55 USD [other]",))
    bk.add_watch("OUTLT", "fiktiv notis", today="2026-10-05")
    bk.add_watch("BBB", "fiktiv notis", today="2026-10-05")
    lcm.case_path("SATS").parent.mkdir(parents=True, exist_ok=True)
    lcm.case_path("SATS").write_text(json.dumps(_lightcase("SATS", 100.0, 9.0, 10.0, 0.015, 0.14)), encoding="utf-8")
    lcm.case_path("OUTLT").write_text(json.dumps(_lightcase("OUTLT", 95.0, 14.0, 10.0, 0.045, 0.12)), encoding="utf-8")
    rep = home / "reports" / "ELK"
    rep.mkdir(parents=True)
    (rep / "777.summary.json").write_text(json.dumps({
        "code": "ELK", "message_id": 777, "title": "Elkem Fiktiv: Q3 2026 report", "published": "2026-10-29T06:00:00Z", "year": 2026, "quarter": 3,
        "url": "https://newsweb.oslobors.no/message/777", "pdf": "777.pdf", "figures": {},
        "metrics": {"revenue": {"value": 3500, "how": "report p. 3"}, "revenue_yoy": {"value": -0.04, "how": "revenue vs the same quarter a year earlier (p. 3)"},
                    "ebitda_margin_ltm": {"value": 0.095, "how": "ebitda / revenue, last twelve months"}},
        "previous": None, "consensus": None, "case": {},
        "kill": [{"criterion": "Fiktivt kriterium D: silisiummargin under 8 % [margin]", "metric": "ebitda_margin_ltm", "op": "<", "threshold": 0.08, "now": 0.095, "previous": 0.11, "status": "intact, nearer", "note": ""},
                 {"criterion": "Fiktivt kriterium E: gjeld over 3x EBITDA [leverage]", "metric": None, "status": "not machine-checkable: read the report", "now": None}],
        "analysed_at": "2026-10-29T18:00:00Z"}), encoding="utf-8")
    fd.write("announcements", {"items": [{"id": 1, "code": "SATS", "issuer": "SATS", "title": "Fiktiv melding: ny klubb åpnet i Bergen", "time": "2026-11-04T07:30:00Z",
                                          "category": "Additional regulated information", "url": "https://newsweb.oslobors.no/message/1"}], "source": "Oslo Børs NewsWeb (test)"})
    items = {}
    for i, (code, side, day, title) in enumerate((("SATS", "buy", "2026-10-15", "SATS: Fiktiv primærinnsider kjøper 5 000 aksjer"), ("SATS", "buy", "2026-09-20", "SATS: Fiktivt kjøp"),
                                                   ("SATS", "sell", "2026-09-05", "SATS: Fiktivt salg av 2 000 aksjer")), 1):
        items[str(i)] = {"id": i, "code": code, "issuer": code, "title": title, "time": f"{day}T08:00:00Z", "url": f"https://newsweb.oslobors.no/message/{i}", "side": side, "why": side}
    fd.write("insiders", {"items": items, "fetched_years": {}, "source": "NewsWeb 1102 (test)"})

    def inst(name, series):
        return {"isin": "NO000TEST", "issuerName": name, "events": [{"date": f"{d}T00:00:00", "shortPercent": v, "activePositions": [{"positionHolder": "Fund X", "shortPercent": v}]} for d, v in series]}
    fd.write("shorts", {"instruments": [inst("SATS", (("2026-10-01", 1.5), ("2026-10-27", 1.5), ("2026-11-03", 1.2))),
                                        inst("OUTLET FIKTIV", (("2026-10-01", 1.6), ("2026-10-27", 1.9), ("2026-11-03", 2.1))),
                                        inst("BETA SHIPPING", (("2026-10-01", 0.8), ("2026-10-27", 0.8), ("2026-11-03", 1.4)))],
                        "source": "Finanstilsynet (test)"})
    fd.write("calendar", {"companies": {"OUTLT": {"message_id": 5, "published": "2026-10-01T08:00:00Z", "events": [{"date": "2026-11-12", "what": "Quarterly Report - Q3"}], "url": "https://newsweb.oslobors.no/message/5"},
                                        "AAA": {"message_id": 6, "published": "2026-10-01T08:00:00Z", "events": [{"date": "2026-11-06", "what": "Quarterly Report - Q3"}], "url": "https://newsweb.oslobors.no/message/6"}},
                          "source": "NewsWeb financial calendars (test)"})
    return snap


@pytest.fixture
def desk_home(home, monkeypatch):
    snap = build_home(home, monkeypatch)
    return home, snap


def _daily(snap) -> dk.DeskRun:
    return dk.run(None, trigger="daily", snap=snap, today=TODAY, now=NOW)


# ------------------------------------------------------------------------------------------------ the chain
def test_the_chain_never_ends_in_a_buy_and_writes_nothing_but_its_own_log(desk_home):
    home, snap = desk_home
    log_before, book_before, watch_before = jg.log_path().read_bytes(), sg.book_path().read_bytes(), bk.watch_path().read_bytes()
    run = _daily(snap)
    assert run.scanned == len(CODES) and run.stocks and {s.outcome for s in run.stocks} <= set(dk.OUTCOMES)
    assert "buy" not in dk.OUTCOMES and all(s.findings[-1].role == "desk" and s.findings[-1].kind == s.outcome for s in run.stocks)
    assert jg.log_path().read_bytes() == log_before and sg.book_path().read_bytes() == book_before and bk.watch_path().read_bytes() == watch_before
    assert jg.verify().ok
    assert dk.run_path(run.run_id).exists() and dk.index()[-1]["run_id"] == run.run_id
    assert run.flagged == len(run.stocks) and run.killed + run.parked + run.ready == len(run.stocks)
    by = {s.code: s for s in run.stocks}
    # the three states, each with its reason visible
    assert by["SATS"].outcome == "ready" and by["SATS"].prefill["position_shares"] == 97 and by["SATS"].prefill["target"] == 131
    assert by["OUTLT"].outcome == "parked" and by["OUTLT"].findings[by["OUTLT"].veto].kind == "implied"
    assert by["ELK"].outcome == "parked" and by["ELK"].findings[by["ELK"].veto].kind == "kill_nearer" and "nå 0.095 mot < 0.08" in by["ELK"].reason
    assert by["DDD"].outcome == "parked" and by["DDD"].findings[by["DDD"].veto].kind == "too_few"
    assert by["FFF"].outcome == "killed" and "no_case" in {f.kind for f in by["FFF"].findings}
    assert by["AAA"].outcome == "killed" and "report_unread" in {f.kind for f in by["AAA"].findings}
    assert by["BBB"].outcome == "killed" and "liquidity" in {f.kind for f in by["BBB"].findings}
    assert len(by) == run.flagged < len(CODES)                                # a stock with nothing unusual is not in the run


def test_the_bear_gets_nothing_through_with_fewer_than_three_reasons_with_numbers(desk_home, monkeypatch):
    home, snap = desk_home
    run = _daily(snap)
    for s in run.stocks:
        reasons = [f for f in s.findings if f.role == "bear" and f.kind != "too_few"]
        if s.outcome == "ready" or any(f.role == "reply" for f in s.findings):
            assert len(reasons) >= dk.MIN_BEAR_REASONS, s.code
            assert all(dk._DIGIT.search(f.value) for f in reasons), s.code
        if any(f.kind == "too_few" for f in s.findings):
            assert s.outcome == "parked" and len(reasons) < dk.MIN_BEAR_REASONS and not any(f.role in ("reply", "risk") for f in s.findings)
    # a bear that hands over two reasons without saying so is stopped by the chain itself
    two = lambda inp, code, ctx: [dk.Finding("bear", "bear_value", "bear 72 (-32 %) med sannsynlighet 25 %", "egen vurdering", "2026-10-01"),  # noqa: E731
                                  dk.Finding("bear", "short_pos", "1.2 % short", "register", "2026-11-03")]
    monkeypatch.setattr(dk, "bear", two)
    forced = dk.run(["SATS"], trigger="manual", snap=snap, today=TODAY, now=datetime(2026, 11, 4, 17, 0, tzinfo=UTC))
    s = forced.stock("SATS")
    assert s.outcome == "parked" and s.findings[s.veto].kind == "too_few" and "2 grunner" in s.reason and not any(f.role == "risk" for f in s.findings)


def test_no_role_writes_free_text_without_a_number_a_source_and_a_time(desk_home):
    home, snap = desk_home
    run = _daily(snap)
    for s in run.stocks:
        for f in s.findings:
            assert f.role in dk.ROLES and f.kind in dk.CLAIMS and f.claim
            assert f.value.strip() and f.source.strip() and f.asof.strip() and f.t.strip(), (s.code, f)
            assert dk._DIGIT.search(f.value), (s.code, f.kind, f.value)
            if f.role == "reply":
                assert f.ref is not None and s.findings[f.ref].role == "bear" and s.findings[f.ref].kind == f.kind
    with pytest.raises(ValueError, match="needs a source"):
        dk.Finding("bear", "bear_value", "bear 72", "", "2026-10-01")
    with pytest.raises(ValueError, match="unknown claim"):
        dk.Finding("bear", "a_thought", "72", "me", "2026-10-01")
    with pytest.raises(ValueError, match="carry a number"):
        dk.Finding("analyst", "distance", "far from the target", "view", "2026-10-01")
    with pytest.raises(ValueError, match="unknown role"):
        dk.Finding("pundit", "distance", "12", "tv", "2026-10-01")
    # estimates and delayed data are marked on the finding
    sats = run.stock("SATS")
    assert any(f.est for f in sats.findings if f.kind == "bear_value") and any(f.delayed for f in sats.findings if f.role == "scout")


def test_the_debate_is_logged_in_order_with_rebuttals_pointing_at_their_reason(desk_home):
    home, snap = desk_home
    run = _daily(snap)
    sats = run.stock("SATS")
    roles = [f.role for f in sats.findings]
    order = {"scout": 0, "filter": 1, "analyst": 2, "bear": 3, "reply": 4, "risk": 5, "desk": 6}
    assert roles == sorted(roles, key=order.get) and roles[-1] == "desk"
    bears = [f for f in sats.findings if f.role == "bear"]
    replies = [f for f in sats.findings if f.role == "reply"]
    assert len(bears) == len(replies) >= 3 and all(b.status == "rebutted" for b in bears) and all(r.status == "rebuts" for r in replies)
    assert {b.kind for b in bears} == {"bear_value", "short_pos", "insider_sell"}
    ev = next(r for r in replies if r.kind == "bear_value")
    assert "forventet verdi 120.0 (+13.2 %)" in ev.value
    risk = [f for f in sats.findings if f.role == "risk"]
    assert {f.kind for f in risk} >= {"size", "group_share", "group_loss", "total_loss", "events"} and not any(f.status == "blocked" for f in risk)
    assert "97 aksjer" in next(f.value for f in risk if f.kind == "size")
    # the scout flagged with numbers: volume, move against the sector, a signal, an announcement, a short move
    assert {f.kind for f in sats.findings if f.role == "scout"} >= {"vol", "move", "announcement", "short"}
    # outlet: the veto stands with the light case's number, and the reply says why it could not rebut
    out = run.stock("OUTLT")
    veto = out.findings[out.veto]
    rep = next(f for f in out.findings if f.role == "reply" and f.ref == out.veto)
    assert veto.kind == "implied" and "+4.5 %" in veto.value and rep.status == "stands" and "0 full casemodell" in rep.value
    assert any(f.kind == "no_view" for f in out.findings)                     # a watched company without a view is said so


def test_risk_blocks_over_the_limits_and_without_limits(desk_home):
    home, snap = desk_home
    (home / "dashboard.yaml").write_text(yaml.safe_dump({"sizing": {"paper_capital": 100000, "max_loss": 2000, "max_position": 0.25}, "desk": {"max_group_share": 0.05}}), encoding="utf-8")
    run = dk.run(["SATS"], trigger="manual", snap=snap, today=TODAY, now=NOW)
    s = run.stock("SATS")
    blocked = [f for f in s.findings if f.status == "blocked"]
    assert s.outcome == "parked" and blocked and blocked[0].kind == "group_share" and "grense 5 %" in blocked[0].value and s.prefill is None
    (home / "dashboard.yaml").unlink()
    run2 = dk.run(["SATS"], trigger="manual", snap=snap, today=TODAY, now=datetime(2026, 11, 4, 17, 1, tzinfo=UTC))
    s2 = run2.stock("SATS")
    assert s2.outcome == "parked" and s2.findings[-2].kind == "no_limits" and "dashboard.yaml" in s2.reason


def test_a_manual_run_forces_a_quiet_stock_through_and_runs_reproduce(desk_home):
    home, snap = desk_home
    run = dk.run(["GGG", "ELK"], trigger="manual", snap=snap, today=TODAY, now=NOW)
    ggg = run.stock("GGG")
    assert ggg.findings[0].kind == "quiet" and ggg.outcome == "killed" and "no_case" in {f.kind for f in ggg.findings}
    again = dk.run(["GGG", "ELK"], trigger="manual", snap=snap, today=TODAY, now=NOW, write=False)
    assert [asdict(s) for s in again.stocks] == [asdict(s) for s in run.stocks]
    with pytest.raises(FileExistsError):
        dk.save(again)                                                        # the same run id is never overwritten


# ------------------------------------------------------------------------------------------------ pages and the row
@pytest.fixture
def client(desk_home):
    a = server.create_app()
    a.testing = True
    return a.test_client()


def test_the_desk_page_runs_one_stock_and_the_log_opens_from_the_stock_page_and_the_row(desk_home, client):
    home, snap = desk_home
    page = client.get("/desk").get_data(as_text=True)
    assert "Dagens kjøring" in page and "Ingen kjøring lagret" in page and "ingen avgjorte vetoer" in page
    r = client.post("/desk/run", data={"code": "sats.ol"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/SATS")
    run_id = r.headers["Location"].split("/")[-2]
    log = client.get(f"/desk/run/{run_id}/SATS").get_data(as_text=True)
    assert "Debattlogg" in log and "Bjørn" in log and "Analytikeren svarer" in log and "klar for vurdering" in log and "forsinket" in log and "EST" in log
    assert "Yahoo Finance via oslo-quant store" in log                        # the source line on the findings
    assert client.get(f"/desk/run/{run_id}").status_code == 200 and client.get("/desk/run/20200101T000000-daily/SATS").status_code == 404
    assert client.get("/desk/run/../x/SATS").status_code == 404
    assert client.post("/desk/run", data={"code": "../x"}).status_code == 400
    assert client.post("/desk/run", data={"code": "ZZZ"}).status_code == 400  # no close in the store
    page = client.get("/desk").get_data(as_text=True)
    assert "Skannet" in page and f"/desk/run/{run_id}" in page and "Tidligere kjøringer" in page
    stock = client.get("/stock/SATS").get_data(as_text=True)
    assert "Kjør desk på SATS" in stock and f"/desk/run/{run_id}/SATS" in stock and "klar for vurdering" in stock
    # opened from the run: the form is prefilled from the view and the Risk role, the debate attached, nothing written
    rows = len(jg.read_log())
    form = client.get(f"/stock/SATS?desk={run_id}").get_data(as_text=True)
    assert f'name="desk_run" value="{run_id}"' in form and 'name="position_shares"' in form and 'value="97"' in form and 'name="target" inputmode="decimal" value="131"' in form
    assert "Desken om SATS" in form and "vedlegges raden" in form and len(jg.read_log()) == rows
    px = float(snap.panel["close"]["SATS"].iloc[-1])
    data = {"rating": "BUY", "target": "131", "bear": "72", "base": "124", "bull": "160", "p_bear": "0.25", "p_base": "0.5", "p_bull": "0.25", "horizon": "12",
            "kill_level": "86", "position_shares": "97", "rationale": "Fiktiv begrunnelse etter desken, lang nok til å telle.", "kill": "Fiktivt kriterium A: klubbmargin under 20 % [margin]",
            "claude_exists": "1", "saw_claude": "no", "desk_run": run_id}
    r = client.post("/stock/SATS/judge", data=data)
    assert r.status_code == 303, r.get_data(as_text=True)
    row = jg.read_log()[-1]
    assert row["desk_run"] == run_id and row["price"] == pytest.approx(px, abs=1e-4) and jg.verify().ok
    stock = client.get("/stock/SATS").get_data(as_text=True)
    assert f'href="/desk/run/{run_id}/SATS" title="debattloggen fra desken">desk</a>' in stock
    # an id that is not a stored run is dropped, never refused: the view is Oscar's whatever the desk said
    r = client.post("/stock/SATS/judge", data={**data, "desk_run": "20200101T000000-daily", "rationale": "Enda en fiktiv begrunnelse, lang nok til å telle."})
    assert r.status_code == 303 and "desk_run" not in jg.read_log()[-1]


def test_the_front_page_carries_the_daily_run(desk_home, client):
    home, snap = desk_home
    before = client.get("/").get_data(as_text=True)
    assert "Desk i dag" in before and "Ingen desk-kjøring" in before
    run = _daily(snap)
    line = f"Skannet {run.scanned}, flagget {run.flagged}, drept {run.killed}, debattert {run.debated}, parkert {run.parked}, klar {run.ready}"
    page = client.get("/").get_data(as_text=True)
    assert line in page and "Klar for vurdering" in page and "/stock/SATS" in page and run.ready == 1
    static = server.static_today_html()
    assert line in static and "http://127.0.0.1:8060/stock/SATS" in static and "/desk/run/" not in static


def test_the_cli_runs_and_shows(desk_home):
    from typer.testing import CliRunner

    from osloquant import cli

    home, snap = desk_home
    runner = CliRunner(env={"COLUMNS": "200"})
    r = runner.invoke(cli.app, ["desk", "run", "SATS,OUTLT,ELK"])
    assert r.exit_code == 0, r.output
    assert "scanned 3" in r.output and "klar for vurdering" in r.output and "parkert" in r.output
    r = runner.invoke(cli.app, ["desk", "show", "--code", "ELK"])
    assert r.exit_code == 0 and "bear" in r.output and "nærmere terskelen" in r.output and "rapportleseren" in r.output
    r = runner.invoke(cli.app, ["desk", "stats"])
    assert r.exit_code == 0 and "bear's veto" in r.output


# ------------------------------------------------------------------------------------------------ the statistic
def test_the_veto_statistic_counts_kill_first_target_first_pending_and_unscorable():
    dates = pd.bdate_range("2026-01-05", periods=80)
    closes = pd.DataFrame({"AAA": np.r_[np.full(20, 100.0), np.linspace(100, 70, 60)],        # falls through the kill level
                           "BBB": np.r_[np.full(20, 100.0), np.linspace(100, 140, 60)],       # reaches the target
                           "CCC": np.full(80, 100.0),                                          # goes nowhere
                           "DDD": np.r_[np.full(20, 100.0), np.linspace(100, 70, 60)]}, index=dates)
    session = f"{dates[19]:%Y-%m-%d}"
    rows = [{"run_id": "20260130T170000-daily", "session": session, "trigger": "daily", "finished_at": "", "scanned": 4, "flagged": 4, "killed": 0, "debated": 4, "parked": 3, "ready": 1,
             "stocks": {"AAA": {"outcome": "parked", "veto_kind": "odds", "reason": "x", "price": 100.0, "target": 130.0, "kill": 80.0},
                        "BBB": {"outcome": "parked", "veto_kind": "short_pos", "reason": "x", "price": 100.0, "target": 130.0, "kill": 80.0},
                        "CCC": {"outcome": "parked", "veto_kind": "too_few", "reason": "x", "price": 100.0, "target": 130.0, "kill": 80.0},
                        "DDD": {"outcome": "ready", "veto_kind": None, "reason": "", "price": 100.0, "target": 130.0, "kill": 80.0}}},
            {"run_id": "20260401T170000-daily", "session": f"{dates[-1]:%Y-%m-%d}", "trigger": "daily", "finished_at": "", "scanned": 1, "flagged": 1, "killed": 0, "debated": 1, "parked": 1, "ready": 0,
             "stocks": {"CCC": {"outcome": "parked", "veto_kind": "implied", "reason": "x", "price": 100.0, "target": 130.0, "kill": 80.0},
                        "EEE": {"outcome": "parked", "veto_kind": "implied", "reason": "x", "price": 100.0, "target": None, "kill": None}}}]
    st = dk.veto_stats(closes, horizon=60, rows=rows)
    assert st["veto"] == {"right": 1, "wrong": 1, "neither": 0, "pending": 1, "unscorable": 1, "decided": 2, "share_right": 0.5, "n": 4}
    assert st["through"] == {"right": 1, "wrong": 0, "neither": 0, "pending": 0, "unscorable": 0, "decided": 1, "share_right": 1.0, "n": 1}
    short = dk.veto_stats(closes, horizon=10, rows=rows[:1])
    assert short["veto"]["neither"] == 2 and short["through"]["neither"] == 1  # the window closed before any level was reached
    from osloquant.dashboard import deskpage

    html = deskpage.stats_html(st)
    assert "50 %" in html and "av 2 avgjorte" in html and "ikke skilt seg" in html and "Ikke målbart" in html


def test_config_takes_only_known_keys_and_keeps_the_defaults(home):
    assert dk.config() == dk.DEFAULTS
    (home / "dashboard.yaml").write_text(yaml.safe_dump({"desk": {"volume_ratio": 3, "min_bear_reasons": 1, "made_up": 9}}), encoding="utf-8")
    cfg = dk.config()
    assert cfg["volume_ratio"] == 3 and "min_bear_reasons" not in cfg and "made_up" not in cfg and dk.MIN_BEAR_REASONS == 3


# ------------------------------------------------------------------------------------------------ frozen real data (private, skipped where absent)
def test_the_desk_on_the_frozen_real_data_keeps_its_rules(home, monkeypatch):
    """On the owner's machine: the frozen prices, caches and research-book copy (never the live files). The same
    invariants as above; the outcomes are not asserted, the data decides them."""
    d = tdata.default_dir()
    if not tdata.available("panel.pkl", "names.json", "insiders.json", "shorts.json") or not (d / "researchbook.yaml").exists():
        pytest.skip("no frozen test data on this machine")
    import shutil

    P = tdata.load_panel()
    names = tdata.load_json("names")
    for name in ("insiders", "shorts"):
        shutil.copy2(d / f"{name}.json", fd.cache_dir() / f"{name}.json")
    shutil.copy2(d / "researchbook.yaml", sg.book_path())
    if (d / "reports").exists():
        shutil.copytree(d / "reports", home / "reports", dirs_exist_ok=True)
    asof = P["close"].index[-1]
    snap = mk.Snapshot({k: v.loc[asof - pd.Timedelta(days=800):] for k, v in P.items()}, names, {}, asof)
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    monkeypatch.setattr(od, "long_closes", lambda: P["close"])
    od._case_odds_cached.cache_clear()
    jg.sync_book(sg.load_book())
    log_before = jg.log_path().read_bytes() if jg.log_path().exists() else b""
    run = dk.run(["SATS", "OUTLT", "ELK"], trigger="manual", snap=snap, today=asof + pd.Timedelta(days=1), now=datetime(2026, 10, 23, 17, 0, tzinfo=UTC))
    assert {s.code for s in run.stocks} <= {"SATS", "OUTLT", "ELK"} and run.stocks
    assert (jg.log_path().read_bytes() if jg.log_path().exists() else b"") == log_before
    for s in run.stocks:
        assert s.outcome in dk.OUTCOMES
        reasons = [f for f in s.findings if f.role == "bear" and f.kind != "too_few"]
        if s.outcome == "ready":
            assert len(reasons) >= dk.MIN_BEAR_REASONS and all(f.status == "rebutted" for f in reasons)
        for f in s.findings:
            assert f.kind in dk.CLAIMS and f.source.strip() and f.asof.strip() and dk._DIGIT.search(f.value)
