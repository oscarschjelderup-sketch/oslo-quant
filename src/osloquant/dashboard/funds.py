"""Model portfolios ("funds") built from the store, judged out of sample, and tracked as paper NAVs from the day
they are written (DECISIONS D33).

Each fund is a recipe: a universe (every stock in the store, or the companies with a view), an expected-return
input (none, shrunk history, or the targets' implied returns) and an optimiser from ``osloquant.allocation``. Three
things are shown for every fund, and they are kept apart:

1. **What it is today** – the weights, and the expected return / volatility / Sharpe *on the inputs* (EST: the
   inputs are three years of history or the views' targets, both uncertain, and the optimiser leans into the noise).
2. **How the recipe did out of sample** – the walk-forward backtest: rebuilt each month end from trailing data only,
   held a month, costs on turnover; against equal weight and OSEBX, with a bootstrap interval on the Sharpe
   difference. On today's 64 stocks, so flattered by survivorship like everything else measured on this store.
3. **How it has done since it was written** – the paper NAV from the recorded weights and the store's closes, with
   the same costs on each recorded rebalance. Private: ``~/osloquant-home/funds/<slug>.json``, append-only.

Nothing here trades. The risk-free rate is Norges Bank's policy rate from the rates feed, named on the page.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from osloquant import allocation as al
from osloquant import judgements as jg

FUND_DIR = "funds"
LOOKBACK_YEARS = 3.0
BACKTEST_YEARS = 5
TARGET_VOL = 0.08           # below the tangency portfolio's own volatility, so the CML point really holds cash
RF_FALLBACK = 0.045          # used only when the rates feed is missing; the page says which it was
BUILD_FILE = "_latest.json"  # the newest build, so the page reads instead of recomputing a 40-second backtest


def risk_free() -> tuple[float, str]:
    from osloquant.dashboard import feeds as fd

    r = fd.read("rates") or {}
    if r.get("policy_rate") is not None:
        return float(r["policy_rate"]) / 100, f"Norges Bank policy rate {r['policy_rate']} % ({r.get('policy_date', '?')}, rates feed)"
    return RF_FALLBACK, f"fallback {RF_FALLBACK:.1%} – rates feed not fetched (oq dashboard --refresh)"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("æ", "ae").replace("ø", "o").replace("å", "a")).strip("-")


# ------------------------------------------------------------------------------------------------ recipes
def recipes(views_claude: dict[str, dict] | None = None, views_oscar: dict[str, dict] | None = None) -> list[dict]:
    """The funds in the order they are shown. ``builder(R, rf, prices)`` returns a Portfolio from trailing returns."""
    def ew(R, rf, px=None):
        return al.equal_weight(R.columns)

    def minvar(R, rf, px=None):
        return al.min_variance(al.shrunk_cov(R)[0])

    def maxsharpe(R, rf, px=None):
        return al.max_sharpe(al.expected_returns(R, "shrunk")["mu"], al.shrunk_cov(R)[0], rf)

    def cml(R, rf, px=None):
        cov = al.shrunk_cov(R)[0]
        return al.cml_point(al.max_sharpe(al.expected_returns(R, "shrunk")["mu"], cov, rf), cov, TARGET_VOL)

    def rp(R, rf, px=None):
        return al.risk_parity(al.shrunk_cov(R)[0])

    def views(which: str, vs: dict[str, dict]):
        def build(R, rf, px=None):
            cov = al.shrunk_cov(R)[0]
            if px is None:
                return al.Portfolio(f"Synene – {which}", pd.Series(dtype=float), note="needs today's prices for the targets' implied returns")
            mu = al.view_returns(vs, px.reindex(cov.index), fallback=-1.0)
            return al.view_weighted(mu, cov, rf, name=f"Synene – {which}")
        return build

    out = [
        {"name": "Likevektet", "universe": "all", "builder": ew, "uses_means": False, "backtest": True,
         "what": "Alle aksjene i lageret med lik vekt. Referansen de andre måles mot."},
        {"name": "Minimum varians", "universe": "all", "builder": minvar, "uses_means": False, "backtest": True,
         "what": "Lavest mulig varians på tre års historikk, bare risiko – ingen forventede avkastninger inn."},
        {"name": "Risikoparitet", "universe": "all", "builder": rp, "uses_means": False, "backtest": True,
         "what": "Hver aksje bidrar like mye til porteføljens varians."},
        {"name": "Maks Sharpe (tangens)", "universe": "all", "builder": maxsharpe, "uses_means": True, "backtest": True,
         "what": "Tangensporteføljen på kapitalmarkedslinjen, med krympede historiske snitt som forventet avkastning (EST)."},
        {"name": f"CML {TARGET_VOL:.0%} vol", "universe": "all", "builder": cml, "uses_means": True, "backtest": True,
         "what": f"Et punkt på kapitalmarkedslinjen: tangensporteføljen skalert til {TARGET_VOL:.0%} volatilitet, resten til styringsrenten."},
    ]
    if views_claude:
        out.append({"name": "Synene – Claude", "universe": "coverage", "builder": views("Claude", views_claude), "uses_means": True, "backtest": False,
                    "what": "Maks Sharpe på Claudes kursmål (implisert avkastning, EST); SELL og selskaper uten syn er ute. Kan ikke backtestes – synene er nye."})
    if views_oscar and len(views_oscar) >= 3:
        out.append({"name": "Synene – Oscar", "universe": "coverage", "builder": views("Oscar", views_oscar), "uses_means": True, "backtest": False,
                    "what": "Maks Sharpe på Oscars kursmål (EST); SELL og selskaper uten syn er ute."})
    return out


# ------------------------------------------------------------------------------------------------ build
def build(adj: pd.DataFrame, index: pd.Series, asof: pd.Timestamp | None = None, views_claude: dict | None = None, views_oscar: dict | None = None,
          backtest: bool = True) -> dict:
    """Everything the page shows: inputs, each fund's weights and EST statistics, the frontier and CML, the
    walk-forward backtest with verdicts. Pure given the frames (tests pass synthetic ones)."""
    rf, rf_label = risk_free()
    asof = asof or adj.index[-1]
    R = al.returns_matrix(adj, end=asof, years=LOOKBACK_YEARS)
    cov, shrink = al.shrunk_cov(R)
    er = al.expected_returns(R, "shrunk")
    px = adj.loc[:asof].iloc[-1]
    funds = []
    recs = recipes(views_claude, views_oscar)
    for rec in recs:
        p = rec["builder"](R, rf, px)
        w = p.weights[p.weights > 0.0005].sort_values(ascending=False)
        funds.append({"name": rec["name"], "slug": slug(rec["name"]), "what": rec["what"], "uses_means": rec["uses_means"], "universe": rec["universe"],
                      "weights": {k: round(float(v), 4) for k, v in w.items()}, "cash": round(float(p.cash), 4), "n": int(len(w)), "note": p.note,
                      "est": {"ret": p.exp_return(er["mu"], rf) if len(p.weights) else None, "vol": p.vol(cov) if len(p.weights) else None,
                              "sharpe": p.sharpe(er["mu"], cov, rf) if len(p.weights) else None}})
    fr = al.frontier(er["mu"], cov, points=20)
    tang = next((f for f in funds if f["name"].startswith("Maks Sharpe")), None)
    out = {"asof": f"{asof:%Y-%m-%d}", "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "rf": rf, "rf_label": rf_label,
           "lookback_years": LOOKBACK_YEARS, "stocks": list(R.columns), "shrinkage": shrink, "cap": al.DEFAULT_CAP, "cost": al.COST,
           "inputs": {c: {"mu": float(er.loc[c, "mu"]), "se": float(er.loc[c, "se"]), "raw": float(er.loc[c, "raw"]), "vol": float(np.sqrt(cov.loc[c, c]))} for c in R.columns},
           "frontier": fr.round(5).to_dict("records"), "tangency": {"ret": tang["est"]["ret"], "vol": tang["est"]["vol"]} if tang else None,
           "funds": funds, "backtest": None}
    if backtest:
        start = asof - pd.DateOffset(years=BACKTEST_YEARS)
        builders = {rec["name"]: (lambda R_, rf_, b=rec["builder"]: b(R_, rf_)) for rec in recs if rec["backtest"]}
        wf = al.walk_forward(adj, builders, start=start, end=asof, lookback_years=LOOKBACK_YEARS, rf=rf)
        ew = wf["returns"].get("Likevektet")
        idx = index.pct_change().reindex(ew.index).dropna() if ew is not None and len(index) else pd.Series(dtype=float)
        rows = {}
        for name, r in wf["returns"].items():
            rows[name] = al.perf(r, rf) | {"turnover": wf["turnover"][name],
                                            "vs_ew": al.sharpe_diff_ci(r, ew) if name != "Likevektet" and ew is not None else None,
                                            "vs_osebx": al.sharpe_diff_ci(r, idx) if len(idx) else None}
        if len(idx):
            rows["OSEBX"] = al.perf(idx, rf) | {"turnover": 0.0, "vs_ew": None, "vs_osebx": None}
        navs = {name: (1 + r).cumprod().resample("W-FRI").last().round(4) for name, r in wf["returns"].items()}
        if len(idx):
            navs["OSEBX"] = (1 + idx).cumprod().resample("W-FRI").last().round(4)
        out["backtest"] = {"start": f"{start:%Y-%m-%d}", "rebalances": len(wf["rebalances"]), "rows": rows,
                           "nav": {k: {f"{d:%Y-%m-%d}": float(v) for d, v in s.dropna().items()} for k, s in navs.items()}}
    return out


def verdict(row: dict, name: str) -> str:
    """One sentence on the out-of-sample result against equal weight, honest about the interval."""
    if not row or row.get("n", 0) < 60:
        return "ikke nok historikk"
    if name == "Likevektet":
        return "referansen"
    d = row.get("vs_ew") or {}
    if d.get("diff") is None:
        return "–"
    if d["lo"] > 0:
        return f"bedre Sharpe enn likevekt ({d['diff']:+.2f}, 95 % [{d['lo']:+.2f}, {d['hi']:+.2f}]) – mer enn støy"
    if d["hi"] < 0:
        return f"dårligere Sharpe enn likevekt ({d['diff']:+.2f}, [{d['lo']:+.2f}, {d['hi']:+.2f}])"
    return f"Sharpe {d['diff']:+.2f} mot likevekt, intervall [{d['lo']:+.2f}, {d['hi']:+.2f}] dekker null – ikke skillbart fra likevekt"


# ------------------------------------------------------------------------------------------------ paper funds
def fund_dir():
    return jg.home() / FUND_DIR


def save_build(out: dict) -> None:
    fund_dir().mkdir(parents=True, exist_ok=True)
    (fund_dir() / BUILD_FILE).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


def load_build() -> dict | None:
    p = fund_dir() / BUILD_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_all() -> dict[str, dict]:
    d = fund_dir()
    if not d.exists():
        return {}
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json")) if not p.name.startswith("_")}


def write(fund: dict, asof: str, prices: pd.Series) -> dict:
    """Record a fund's weights as of ``asof``: a new file at inception, else one more rebalance appended. The
    recorded weights are never edited."""
    d = fund_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{fund['slug']}.json"
    doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"name": fund["name"], "slug": fund["slug"], "what": fund["what"], "rebalances": []}
    if doc["rebalances"] and doc["rebalances"][-1]["date"] == asof:
        return doc
    doc["rebalances"].append({"date": asof, "written_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "weights": fund["weights"], "cash": fund["cash"],
                              "prices": {c: float(prices[c]) for c in fund["weights"] if c in prices.index and pd.notna(prices[c])},
                              "est": fund["est"], "note": fund["note"]})
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return doc


def nav(doc: dict, adj: pd.DataFrame, rf: float, cost: float = al.COST) -> pd.Series:
    """Paper NAV from 100 at inception: the recorded weights held (rebalanced daily to them) between recorded
    rebalances, costs on turnover at each rebalance, cash at the policy rate."""
    rebs = doc.get("rebalances") or []
    if not rebs:
        return pd.Series(dtype=float)
    parts = []
    prev = None
    for i, rb in enumerate(rebs):
        start = pd.Timestamp(rb["date"])
        stop = pd.Timestamp(rebs[i + 1]["date"]) if i + 1 < len(rebs) else None
        seg = adj[adj.index >= start]
        if stop is not None:
            seg = seg[seg.index <= stop]
        R = seg.pct_change().iloc[1:]
        w = pd.Series(rb["weights"], dtype=float)
        r = al.portfolio_returns(w, R, rb.get("cash", 0.0), rf / al.TRADING_DAYS)
        tw = float((w - prev.reindex(w.index).fillna(0.0)).abs().sum()) if prev is not None else float(w.sum())
        if len(r):
            r.iloc[0] -= tw * cost
        parts.append(r)
        prev = w
    r = pd.concat(parts) if parts else pd.Series(dtype=float)
    r = r[~r.index.duplicated(keep="last")]
    return 100 * (1 + r).cumprod()


def tracking(adj: pd.DataFrame, index: pd.Series, rf: float) -> list[dict]:
    """Every recorded fund since its inception: NAV now, return, against equal weight and OSEBX over the same days."""
    out = []
    for s, doc in load_all().items():
        n = nav(doc, adj, rf)
        start = pd.Timestamp(doc["rebalances"][0]["date"])
        if n.empty:                                   # written on the newest close: nothing to measure yet, but it exists
            out.append({"slug": s, "name": doc["name"], "since": f"{start:%Y-%m-%d}", "rebalances": len(doc["rebalances"]), "days": 0,
                        "nav": 100.0, "ret": 0.0, "ew": None, "osebx": None, "max_dd": 0.0, "series": {}})
            continue
        ew = al.portfolio_returns(pd.Series(1.0 / adj.shape[1], index=adj.columns), adj[adj.index >= start].pct_change().iloc[1:])
        ew_nav = 100 * (1 + ew).cumprod()
        ix = index[index.index >= start]
        out.append({"slug": s, "name": doc["name"], "since": f"{start:%Y-%m-%d}", "rebalances": len(doc["rebalances"]), "days": int(len(n)),
                    "nav": float(n.iloc[-1]), "ret": float(n.iloc[-1] / 100 - 1), "ew": float(ew_nav.iloc[-1] / 100 - 1) if len(ew_nav) else None,
                    "osebx": float(ix.iloc[-1] / ix.iloc[0] - 1) if len(ix) > 1 else None, "max_dd": al.max_drawdown(n),
                    "series": {f"{d:%Y-%m-%d}": round(float(v), 3) for d, v in n.items()}})
    return out
