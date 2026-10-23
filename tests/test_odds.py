"""Outcome odds: first passage, the block simulation, historical cases, the signal brackets – on synthetic data
everywhere, and on the frozen real data (prices to 22 Oct 2026) where it exists, with the same answer every time."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from osloquant import signals as sg
from osloquant.dashboard import odds
from osloquant.dashboard import testdata as tdata

from .helpers import business_days


def test_first_passage_decides_by_the_first_close_beyond_a_level():
    rel = np.array([[1.0, 1.05, 1.11, 0.80],     # target 1.10 first
                    [1.0, 0.95, 0.89, 1.20],     # kill 0.90 first
                    [1.0, 1.02, 0.98, 1.01],     # neither
                    [1.0, 1.10, 0.90, 1.00]])    # exactly at the target counts
    assert list(odds.first_passage(rel, 1.10, 0.90)) == [1, -1, 0, 1]
    # one pair of levels per row
    assert list(odds.first_passage(rel[:2], np.array([1.2, 1.2]), np.array([0.9, 0.85]))) == [-1, 1]


def test_simulation_is_deterministic_and_respects_distance():
    rng = np.random.default_rng(1)
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, 1500))), index=business_days(1500, "2015-01-01"))
    a = odds.simulate(c, 1.2, 0.8)
    b = odds.simulate(c, 1.2, 0.8)
    assert all(a[k].target == b[k].target and a[k].n == odds.PATHS for k in a)
    near, far = odds.simulate(c, 1.05, 0.95)["3 mnd"], odds.simulate(c, 2.0, 0.5)["3 mnd"]
    assert near.neither < 0.2 and far.neither > 0.9
    for o in a.values():
        assert abs(o.target + o.kill + o.neither - 1) < 1e-9
    short = odds.simulate(c.iloc[:100], 1.2, 0.8)["12 mnd"]
    assert short.n == 0 and "too little history" in short.note


def test_historical_cases_scale_by_volatility_and_count_overlap():
    rng = np.random.default_rng(2)
    n = 2000
    dates = business_days(n, "2012-01-02")
    closes = pd.DataFrame({"CALM": 100 * np.exp(np.cumsum(rng.normal(0, 0.008, n))),
                           "WILD": 100 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))}, index=dates)
    out = odds.analogues(closes, "CALM", 1.10, 0.90)
    u, own = out["universe"]["12 mnd"], out["own"]["12 mnd"]
    assert u.extra["stocks"] == 2 and u.n > own.n > 0
    assert u.extra["independent"] == round(u.n * odds.STEP / 252)
    # the wild stock gets levels just as far away in its own volatility, so it does not just hit everything first
    assert 0 < u.neither < 1


def test_a_sell_view_mirrors_the_levels(monkeypatch):
    rng = np.random.default_rng(3)
    n = 1500
    closes = pd.DataFrame({"AAA": 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))}, index=business_days(n, "2015-01-01"))
    monkeypatch.setattr(odds, "long_closes", lambda: closes)
    px = float(closes["AAA"].iloc[-1])
    buy = odds.case_odds("AAA", px * 1.2, px * 0.8, "test")
    sell = odds.case_odds("AAA", px * 0.8, px * 1.2, "test")
    for k in buy.simulation:
        assert sell.simulation[k].target == pytest.approx(buy.simulation[k].kill)
        assert sell.simulation[k].kill == pytest.approx(buy.simulation[k].target)
    inside = odds.case_odds("AAA", px * 0.9, px * 0.8, "test")
    assert inside.note and "not between" in inside.note


def test_breakeven_and_the_open_session():
    r, be = odds.breakeven(100, 130, 85)
    assert r == pytest.approx(2.0) and be == pytest.approx(1 / 3)
    idx = pd.to_datetime(["2026-10-21", "2026-10-22"])
    closes = pd.DataFrame({"A": [1.0, 2.0]}, index=idx)
    during = pd.Timestamp("2026-10-22 14:00", tz="Europe/Oslo")
    after = pd.Timestamp("2026-10-22 17:00", tz="Europe/Oslo")
    assert len(odds.complete_sessions(closes, during)) == 1 and len(odds.complete_sessions(closes, after)) == 2


def test_kill_level_prefers_the_views_own_level():
    assert odds.kill_level({"kill_level": 30, "bear": 25}) == (30.0, "kill level in the view")
    assert odds.kill_level({"bear": 25})[0] == 25.0 and "bear" in odds.kill_level({"bear": 25})[1]
    assert odds.kill_level({}) == (None, "no kill level or bear value")


def test_signal_brackets_on_a_known_path():
    n = 120
    dates = business_days(n, "2020-01-01")
    close = pd.DataFrame({"UP": np.r_[np.full(80, 100.0), np.linspace(100, 160, 40)],
                          "FLAT": np.full(n, 100.0)}, index=dates)
    P = dict(open=close.shift(1).fillna(close), high=close * 1.01, low=close * 0.99, close=close,
             volume=pd.DataFrame(1000.0, index=dates, columns=close.columns))
    P["volume"].iloc[80, 0] = 3000.0
    rows = odds.signal_brackets(P)
    for name, r in rows.items():
        h = r["h20"]
        if h["events"]:
            assert abs(h["target"] + h["stop"] + h["neither"] - 1) < 1e-3
            if name.startswith("Breakout"):
                assert h["target"] == 1.0 and h["mean_R"] == pytest.approx(1.0)


# ------------------------------------------------------------------------------------------------ frozen real data
needs_real = pytest.mark.skipif(not tdata.available(), reason="no frozen real data on this machine (private, not in git)")


@needs_real
def test_real_outcome_odds_are_the_same_every_time():
    """EQNR on the frozen prices (last close 22 Oct 2026), levels 480 and 380 (illustrative, not a case)."""
    C = tdata.load_panel()["close"]
    c = C["EQNR"].dropna()
    px = float(c.iloc[-1])
    assert px == pytest.approx(431.8, abs=0.01)
    sim = odds.simulate(c, 480 / px, 380 / px)
    an = odds.analogues(C, "EQNR", 480 / px, 380 / px)
    expect = {"3 mnd": ((0.4244, 0.209, 0.3666), (0.5176, 0.3247, 0.1577, 9752), (0.371, 0.1935, 0.4355, 186)),
              "6 mnd": ((0.5847, 0.3066, 0.1087), (0.5939, 0.3745, 0.0317, 9563), (0.5191, 0.3279, 0.153, 183)),
              "12 mnd": ((0.6455, 0.3432, 0.0113), (0.6073, 0.3892, 0.0035, 9185), (0.5819, 0.3616, 0.0565, 177))}
    for lab, (s, u, w) in expect.items():
        assert (round(sim[lab].target, 4), round(sim[lab].kill, 4), round(sim[lab].neither, 4)) == s
        x = an["universe"][lab]
        assert (round(x.target, 4), round(x.kill, 4), round(x.neither, 4), x.n) == u
        y = an["own"][lab]
        assert (round(y.target, 4), round(y.kill, 4), round(y.neither, 4), y.n) == w


@needs_real
def test_the_committed_signal_brackets_reproduce_from_the_frozen_prices():
    rows = odds.signal_brackets(tdata.load_panel(), end="2026-10-19")
    doc = yaml.safe_load(sg.odds_path().read_text(encoding="utf-8"))
    assert doc["measured"]["to"] == "2026-10-19" and doc["measured"]["bracket"]["round_trip_cost"] == 0.005
    for name, r in rows.items():
        assert doc["signals"][name]["bracket"] == {k: v for k, v in r.items() if k != "kind"}, name
