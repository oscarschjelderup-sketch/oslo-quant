"""Portfolio construction (D33): the optimisers keep their constraints and beat the obvious reference in sample, the
CML point really holds cash, the walk-forward uses trailing data only, the paper NAV chains rebalances with costs,
and the page renders from a build. Synthetic prices throughout."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from osloquant import allocation as al
from osloquant.dashboard import funds as fn
from osloquant.dashboard import render as rd

from .helpers import business_days


def _prices(n=1300, k=8, seed=3, start="2021-01-04"):
    rng = np.random.default_rng(seed)
    dates = business_days(n, start)
    common = rng.normal(0.0003, 0.008, n)
    vols = np.linspace(0.008, 0.03, k)
    drifts = np.linspace(0.0001, 0.0008, k)
    r = np.column_stack([drifts[i] + 0.6 * common + rng.normal(0, vols[i], n) for i in range(k)])
    return pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=dates, columns=[f"S{i}" for i in range(k)])


def test_inputs_shrink_towards_the_cross_section_and_report_their_noise():
    adj = _prices()
    R = al.returns_matrix(adj, years=3)
    assert R.shape[1] == 8 and 700 < len(R) < 800
    er = al.expected_returns(R, "shrunk")
    raw = al.expected_returns(R, "historical")
    grand = raw["mu"].mean()
    assert ((er["mu"] - grand).abs() <= (raw["mu"] - grand).abs() + 1e-12).all()      # pulled in, never pushed out
    assert (er["se"] > 0).all() and er["se"].median() > 0.05                             # the noise is of the order of the mean
    assert al.expected_returns(R, "zero_alpha")["mu"].nunique() == 1
    cov, shrink = al.shrunk_cov(R)
    assert 0 <= shrink <= 1 and cov.shape == (8, 8) and (np.diag(cov) > 0).all()


def test_optimisers_respect_constraints_and_order_as_theory_says():
    adj = _prices()
    R = al.returns_matrix(adj, years=3)
    cov, _ = al.shrunk_cov(R)
    mu = al.expected_returns(R, "shrunk")["mu"]
    rf = 0.04
    ew, mv, ms, rp = al.equal_weight(R.columns), al.min_variance(cov, cap=0.3), al.max_sharpe(mu, cov, rf, cap=0.3), al.risk_parity(cov)
    for p in (ew, mv, ms, rp):
        assert p.weights.sum() == pytest.approx(1.0, abs=1e-6) and (p.weights >= -1e-9).all()
    assert (mv.weights <= 0.3 + 1e-6).all() and (ms.weights <= 0.3 + 1e-6).all()
    assert mv.vol(cov) <= ew.vol(cov) + 1e-9 and mv.vol(cov) <= rp.vol(cov) + 1e-9
    assert ms.sharpe(mu, cov, rf) >= ew.sharpe(mu, cov, rf) - 1e-9 and ms.sharpe(mu, cov, rf) >= mv.sharpe(mu, cov, rf) - 1e-9
    # risk parity: equal risk contributions
    w = rp.weights.to_numpy()
    S = cov.to_numpy()
    rc = w * (S @ w) / (w @ S @ w)
    assert rc.max() - rc.min() < 0.02
    # the CML point: tangency scaled, the rest cash, volatility on target when the target is below the tangency's
    c = al.cml_point(ms, cov, target_vol=ms.vol(cov) / 2)
    assert c.cash == pytest.approx(0.5, abs=1e-6) and c.vol(cov) == pytest.approx(ms.vol(cov) / 2, rel=1e-6)
    assert c.exp_return(mu, rf) == pytest.approx(0.5 * ms.exp_return(mu, rf) + 0.5 * rf, rel=1e-6)
    high = al.cml_point(ms, cov, target_vol=10.0)
    assert high.cash == 0.0                                                              # no borrowing: capped at the tangency
    fr = al.frontier(mu, cov, cap=0.3, points=8)
    assert len(fr) == 8 and fr["vol"].iloc[0] <= fr["vol"].iloc[-1] and fr["ret"].is_monotonic_increasing


def test_view_returns_and_the_view_weighted_portfolio_exclude_sells():
    px = pd.Series({"A": 100.0, "B": 50.0, "C": 20.0})
    views = {"A": {"target": 120, "horizon_months": 12}, "B": {"target": 40, "horizon_months": 6}}
    mu = al.view_returns(views, px, fallback=-1.0)
    assert mu["A"] == pytest.approx(0.20) and mu["B"] == pytest.approx(-0.40) and mu["C"] == -1.0      # B: −20 % over 6 months, annualised
    cov = pd.DataFrame(np.diag([0.04, 0.09, 0.02]), index=list("ABC"), columns=list("ABC"))
    p = al.view_weighted(mu, cov, rf=0.04)
    assert list(p.weights.index) == ["A"] and p.weights["A"] == pytest.approx(1.0)
    none = al.view_weighted(pd.Series({"A": 0.01}), cov.loc[["A"], ["A"]], rf=0.04)
    assert none.weights.empty and "no view" in none.note


def test_walk_forward_uses_only_trailing_data_and_charges_turnover():
    adj = _prices(n=1500)
    seen = []

    def spy(R, rf):
        seen.append(R.index[-1])
        return al.equal_weight(R.columns)

    wf = al.walk_forward(adj, {"EW": spy, "MV": lambda R, rf: al.min_variance(al.shrunk_cov(R)[0], cap=0.5)}, start=adj.index[-260], lookback_years=2, rf=0.0, cost=0.01)
    assert len(wf["rebalances"]) >= 12
    for d, last in zip(wf["rebalances"], seen, strict=True):
        assert last < pd.Timestamp(d)                                                   # the training window ends before the rebalance day
    r = wf["returns"]["EW"]
    assert len(r) > 200 and not r.index.duplicated().any()
    # equal weight rebalanced monthly: first day of the test carries the full 1 % cost, later months little
    raw = al.portfolio_returns(pd.Series(1 / 8, index=adj.columns), adj.pct_change().reindex(r.index))
    assert (raw.iloc[0] - r.iloc[0]) == pytest.approx(0.01, abs=1e-9)
    assert wf["turnover"]["MV"] > wf["turnover"]["EW"]
    p = al.perf(r, rf=0.0)
    assert {"cagr", "vol", "sharpe", "max_dd", "total"} <= set(p) and p["max_dd"] <= 0
    ci = al.sharpe_diff_ci(wf["returns"]["MV"], r, n=200)
    assert ci["months"] >= 12 and ci["lo"] <= ci["diff"] <= ci["hi"]


def test_build_and_the_paper_nav_chain(home, monkeypatch):
    adj = _prices(n=1400)
    index = adj.mean(axis=1)
    monkeypatch.setattr(fn, "risk_free", lambda: (0.04, "test rate"))
    px = adj.iloc[-1]
    b = fn.build(adj, index, views_claude={"S7": {"target": px["S7"] * 1.5, "horizon_months": 12}, "S0": {"target": px["S0"] * 0.5, "horizon_months": 12}}, backtest=True)
    names = [f["name"] for f in b["funds"]]
    assert names[:5] == ["Likevektet", "Minimum varians", "Risikoparitet", "Maks Sharpe (tangens)", "CML 8% vol"] and "Synene – Claude" in names
    cml = next(f for f in b["funds"] if f["name"].startswith("CML"))
    assert cml["cash"] > 0 and cml["est"]["vol"] == pytest.approx(0.08, abs=0.002)
    claude = next(f for f in b["funds"] if f["name"] == "Synene – Claude")
    assert list(claude["weights"]) == ["S7"]                                             # S0 is a SELL (target half the price), S7 the only BUY
    assert b["backtest"]["rows"]["Likevektet"]["n"] > 200 and "OSEBX" in b["backtest"]["rows"] and "CML 8% vol" in b["backtest"]["rows"]
    assert "Synene – Claude" not in b["backtest"]["rows"]                                # views are not backtested
    assert all(0 < v <= 0.15 + 1e-6 for v in b["funds"][1]["weights"].values())
    fn.save_build(b)
    assert fn.load_build()["asof"] == b["asof"]
    # write the funds at a past date, then the NAV from there with the recorded weights
    asof = f"{adj.index[-30]:%Y-%m-%d}"
    px = adj.loc[asof]
    for f in b["funds"]:
        if f["weights"]:
            fn.write(f, asof, px)
    docs = fn.load_all()
    assert set(docs) == {f["slug"] for f in b["funds"] if f["weights"]} and "_latest" not in docs
    again = fn.write(b["funds"][0], asof, px)
    assert len(again["rebalances"]) == 1                                                 # the same day twice is one rebalance
    later = f"{adj.index[-10]:%Y-%m-%d}"
    doc = fn.write(b["funds"][0], later, adj.loc[later])
    assert len(doc["rebalances"]) == 2 and json.loads((fn.fund_dir() / "likevektet.json").read_text(encoding="utf-8"))["rebalances"][0]["date"] == asof
    n = fn.nav(doc, adj, rf=0.04, cost=0.0)
    ew = (1 + al.portfolio_returns(pd.Series(1 / 8, index=adj.columns), adj.loc[asof:].pct_change().iloc[1:])).cumprod() * 100
    assert n.index[0] > pd.Timestamp(asof) and n.iloc[-1] == pytest.approx(ew.iloc[-1], rel=1e-9)
    with_cost = fn.nav(doc, adj, rf=0.04)
    assert with_cost.iloc[-1] < n.iloc[-1]
    tr = fn.tracking(adj, index, 0.04)
    assert {t["slug"] for t in tr} == set(docs) and all(t["days"] > 20 and t["ew"] is not None for t in tr)
    html = rd.funds_page(b, tr, adj.index[-1])
    assert "Kapitalmarkedslinjen" in html and "Ut av prøven" in html and "Papirfondene siden de ble skrevet" in html and "overlevere" in html
    assert "EST" in html and "Likevektet" in html and "mot likevekt" in html
    assert "Ingen bygg ennå" in rd.funds_page(None, [], adj.index[-1])
    # written on the newest close: the funds exist but have nothing to measure yet
    fresh = fn.write(b["funds"][1], f"{adj.index[-1]:%Y-%m-%d}", adj.iloc[-1])
    assert len(fresh["rebalances"]) == 2
    day0 = [t for t in fn.tracking(adj, index, 0.04) if t["slug"] == "minimum-varians"][0]
    assert day0["days"] > 0                                                              # it had an earlier rebalance, so it is measured from that
    only_new = {"name": "x", "slug": "x-new", "what": "", "rebalances": [{"date": f"{adj.index[-1]:%Y-%m-%d}", "weights": {"S1": 1.0}, "cash": 0.0}]}
    (fn.fund_dir() / "x-new.json").write_text(json.dumps(only_new), encoding="utf-8")
    t0 = [t for t in fn.tracking(adj, index, 0.04) if t["slug"] == "x-new"][0]
    assert t0["days"] == 0 and t0["nav"] == 100.0
    assert "den nyeste sluttkursen" in rd.funds_page(b, [t0], adj.index[-1])
