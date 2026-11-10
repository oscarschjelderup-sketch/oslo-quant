"""The desk reads news, events and macro (DECISIONS D69): what flags a stock has a weight, a weak trigger is killed as
noise, a heavy one sends the stock to judgement with the bear's standing points attached, at most five a day, macro is
an input to the analyst and the bear, and the data quality is the dashboard's one list of sources. Fictive home."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant.dashboard import desk as dk
from osloquant.dashboard import deskpage
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import macro as mc

from .test_desk import NOW, TODAY, _daily, desk_home  # noqa: F401  the fictive desk home


def _trigger(sr: dk.StockRun) -> dk.Finding:
    return next(f for f in sr.findings if f.kind == "trigger")


def test_what_flags_a_stock_has_a_weight_and_the_sum_is_written_out(desk_home):  # noqa: F811
    _, snap = desk_home
    run = _daily(snap)
    assert run.stocks and all(s.trigger == _trigger(s).w for s in run.stocks)
    for s in run.stocks:
        scout = [f for f in s.findings if f.role == "scout" and f.kind != "trigger"]
        follow = 2 if s.code in {"SATS", "ELK", "AAA", "DDD"} else 1 if s.code in {"OUTLT", "BBB"} else 0
        assert s.trigger == sum(f.w for f in scout) + follow, s.code
        assert _trigger(s).value.startswith(f"vekt {s.trigger} = ") and ("i research book 2" in _trigger(s).value) == (follow == 2)
    sats = run.stock("SATS")
    ann = next(f for f in sats.findings if f.kind == "announcement")
    assert ann.w >= 2 and ", børsmelding)" in ann.value and f"tyngst (vekt {ann.w}" in ann.value      # its kind and its weight, not just «a message»


def test_a_weak_trigger_is_killed_by_the_filter_with_its_number(desk_home, monkeypatch):  # noqa: F811
    _, snap = desk_home
    monkeypatch.setitem(dk.DEFAULTS, "min_trigger", 99)                              # everything is noise
    run = _daily(snap)
    weak = [s for s in run.stocks if s.reason.startswith(dk.CLAIMS["weak_trigger"])]
    assert weak and all(s.outcome == "killed" and f"utløservekt {s.trigger} < grense 99" in s.reason for s in weak)
    assert all(not any(f.role == "bear" for f in s.findings) for s in weak)          # killed before the debate
    assert run.ready == 0 and run.killed == len(run.stocks)
    manual = dk.run(["SATS"], trigger="manual", snap=snap, today=TODAY, now=NOW, write=False)
    assert manual.stock("SATS").outcome != "killed" or "utløser" not in manual.stock("SATS").reason     # a stock you ask for is never noise


def test_a_heavy_trigger_is_ready_with_the_bears_points_attached_and_no_rating(desk_home, monkeypatch):  # noqa: F811
    _, snap = desk_home
    monkeypatch.setitem(dk.DEFAULTS, "min_trigger", 0)
    monkeypatch.setitem(dk.DEFAULTS, "ready_trigger", 10**6)
    before = {s.code: s.outcome for s in _daily(snap).stocks}
    parked = [c for c, o in before.items() if o == "parked"]
    assert parked, "the fixture has no parked stock to send through"
    monkeypatch.setitem(dk.DEFAULTS, "ready_trigger", 1)
    log_before = jg.log_path().read_bytes()
    run = _daily(snap)
    sent = [s for s in run.stocks if s.outcome == "ready" and s.route == "trigger"]
    assert {s.code for s in sent} >= set(parked) - {s.code for s in run.stocks if s.outcome == "parked"} and sent
    s = sent[0]
    assert s.reason.startswith(dk.CLAIMS["trigger_route"]) and "bjørnen står på" in s.reason and not (s.prefill or {}).get("rating")
    assert any(f.role == "bear" for f in s.findings)                                 # the debate ran and is in the log
    assert jg.log_path().read_bytes() == log_before and "buy" not in dk.OUTCOMES     # still no judgement written, still no buy
    html = deskpage.stock_log_page(run, s)
    assert "Dette er ikke en kjøpskandidat" in html and "uten syn og kursmål" in html


def test_at_most_five_are_ready_and_they_are_the_heaviest(desk_home, monkeypatch):  # noqa: F811
    _, snap = desk_home
    monkeypatch.setitem(dk.DEFAULTS, "min_trigger", 0)
    monkeypatch.setitem(dk.DEFAULTS, "ready_trigger", 1)
    monkeypatch.setitem(dk.DEFAULTS, "max_ready", 1)
    run = _daily(snap)
    ready = [s for s in run.stocks if s.outcome == "ready"]
    capped = [s for s in run.stocks if s.reason.startswith(dk.CLAIMS["ready_cap"])]
    assert len(ready) == 1 == run.ready and capped and all(s.outcome == "parked" and s.prefill is None for s in capped)
    assert ready[0].trigger >= max(s.trigger for s in capped)
    assert all(s.findings[-1].role == "desk" and s.findings[-1].kind == s.outcome for s in run.stocks)       # every log still ends in one closing line


def _macro(monkeypatch, snap, code: str, beta: float, month: float):
    """A macro feed in which ``code`` has followed Brent, and Brent has moved ``month`` the last month."""
    days = snap.panel["close"].index
    n = len(days)
    path = np.concatenate([np.full(n - 22, 80.0), np.linspace(80.0, 80.0 * (1 + month), 22)])
    series = {k: pd.Series(dtype=float) for k in mc.BY_KEY} | {"brent": pd.Series(path, index=days)}
    table = pd.DataFrame([{"code": code, "driver": "brent", "beta": beta, "t": 6.0, "corr": 0.6, "n": 156}])
    monkeypatch.setattr(mc, "load", lambda doc=None: series)
    monkeypatch.setattr(mc, "sensitivities", lambda: table)


def test_macro_is_an_input_to_the_analyst_and_a_reason_for_the_bear(desk_home, monkeypatch):  # noqa: F811
    _, snap = desk_home
    _macro(monkeypatch, snap, "SATS", beta=4.0, month=-0.20)                         # Brent −20 %: corresponds to −8 % for the stock
    run = dk.run(["SATS"], trigger="manual", snap=snap, today=TODAY, now=NOW, write=False)
    s = run.stock("SATS")
    exp = next(f for f in s.findings if f.kind == "macro_exposure")
    assert exp.role == "analyst" and exp.est and "Brent" in exp.value and "tilsvarer" in exp.value and "OSEBX i regresjonen" in exp.source
    bear = next(f for f in s.findings if f.kind == "macro_against")
    assert bear.role == "bear" and float(bear.detail) == pytest.approx(4.0 * (-20.0 / 10.0), rel=0.02)
    reply = next(f for f in s.findings if f.role == "reply" and f.kind == "macro_against")
    c = snap.panel["close"]["SATS"].dropna()
    own = float(c.iloc[-1] / c[c.index <= c.index[-1] - pd.DateOffset(months=1)].iloc[-1] - 1) * 100
    assert reply.status == ("rebuts" if own <= float(bear.detail) else "stands") and f"{own:+.1f} %" in reply.value
    # a driver that went the stock's way is an input but no reason against it
    _macro(monkeypatch, snap, "SATS", beta=4.0, month=+0.20)
    s = dk.run(["SATS"], trigger="manual", snap=snap, today=TODAY, now=NOW, write=False).stock("SATS")
    assert any(f.kind == "macro_exposure" for f in s.findings) and not any(f.kind == "macro_against" for f in s.findings)


def test_an_unusual_week_in_a_followed_driver_flags_the_stock(desk_home, monkeypatch):  # noqa: F811
    _, snap = desk_home
    days = snap.panel["close"].index
    rng = np.random.default_rng(5)
    path = 80 * np.exp(np.cumsum(rng.normal(0, 0.004, len(days))))
    path[-5:] = path[-6] * np.linspace(1.03, 1.15, 5)                               # +15 % in five sessions against a usual week of about one per cent
    series = {k: pd.Series(dtype=float) for k in mc.BY_KEY} | {"brent": pd.Series(path, index=days)}
    monkeypatch.setattr(mc, "load", lambda doc=None: series)
    monkeypatch.setattr(mc, "sensitivities", lambda: pd.DataFrame([{"code": "DDD", "driver": "brent", "beta": 3.0, "t": 5.0, "corr": 0.5, "n": 156}]))
    inp = dk.Inputs(snap, TODAY, NOW)
    m = dk.macro_move(inp, "DDD")
    assert m and m["driver"] == "brent" and m["z"] >= 3 and "siste 5 økter" in m["text"] and "tilsvarer" in m["text"]
    assert dk.macro_move(inp, "SATS") is None                                        # a stock that does not follow the driver is not flagged by it
    found = dk.scout(inp, "DDD")
    macro = next(f for f in found if f.kind == "macro")
    assert macro.w == dk.TRIGGER_WEIGHT["macro_big"] and macro.est


def test_the_desks_data_quality_is_the_dashboards_one_list_of_sources(desk_home):  # noqa: F811
    _, snap = desk_home
    run = _daily(snap)
    names = {q["what"] for q in run.data_quality}
    assert {"Børsmeldinger (Oslo Børs NewsWeb)", "Noterte kurser (Yahoo Finance)", "Regnskap (Yahoo Finance)", "Shortposisjoner (Finanstilsynet)"} <= names
    assert any(not q["ok"] for q in run.data_quality)                                # the fictive home has never fetched statements: the desk says so too
    html = deskpage.quality_html(run)
    assert "Datakvalitet:" in html and "av" in html


def test_a_capped_number_is_shown_as_a_cap():
    import inspect

    src = inspect.getsource(dk.bear)
    assert "over +999 % (taket i regnestykket)" in src


def test_the_replay_runs_past_sessions_without_writing(desk_home, monkeypatch):  # noqa: F811
    home, snap = desk_home
    from osloquant.dashboard import market as mk

    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    before = sorted(p.name for p in dk.desk_dir().glob("*")) if dk.desk_dir().exists() else []
    rows = dk.replay(2)
    assert [r["session"] for r in rows] == [f"{d:%Y-%m-%d}" for d in snap.panel["close"].index[-2:]]
    assert all(r["scanned"] > 0 and r["ready"] <= int(dk.config()["max_ready"]) for r in rows)
    assert (sorted(p.name for p in dk.desk_dir().glob("*")) if dk.desk_dir().exists() else []) == before
    assert fd.read("announcements") is not None
