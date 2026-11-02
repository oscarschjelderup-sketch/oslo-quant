"""Portfolio construction on the store's prices: the inputs (annualised means and a shrunk covariance), long-only
optimisers (minimum variance, maximum Sharpe, risk parity, a point on the capital market line), the efficient
frontier for a chart, and a walk-forward backtest that rebuilds each portfolio from trailing data only (DECISIONS D33).

Everything here is arithmetic on returns that already happened. An expected return from three years of daily data
has a standard error about as large as itself – `expected_returns` reports it – and the optimisers amplify that
noise, which is why every portfolio built here is also run forward out of sample before it is shown as a "fund".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

TRADING_DAYS = 252
DEFAULT_CAP = 0.15           # no single stock above 15 % – the optimisers would otherwise bet the book on one history
COST = 0.0025                # one-way cost on turnover in the backtest and the paper NAV (0.25 %)


# ------------------------------------------------------------------------------------------------ inputs
def returns_matrix(adj: pd.DataFrame, end: pd.Timestamp | None = None, years: float = 3.0, min_coverage: float = 0.9) -> pd.DataFrame:
    """Daily simple returns for the ``years`` up to ``end``, keeping stocks with closes on at least ``min_coverage`` of
    the sessions (a stock listed halfway through the window is left out, not padded)."""
    C = adj.sort_index()
    if end is not None:
        C = C[C.index <= end]
    start = C.index[-1] - pd.DateOffset(years=years)
    C = C[C.index > start]
    ok = C.notna().mean() >= min_coverage
    R = C.loc[:, ok].pct_change()
    return R.iloc[1:].dropna(axis=1, how="all")


def shrunk_cov(R: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Annualised covariance with Ledoit–Wolf shrinkage towards the scaled identity; returns (cov, shrinkage)."""
    from sklearn.covariance import LedoitWolf

    X = R.fillna(0.0).to_numpy()
    lw = LedoitWolf().fit(X)
    return pd.DataFrame(lw.covariance_ * TRADING_DAYS, index=R.columns, columns=R.columns), float(lw.shrinkage_)


def expected_returns(R: pd.DataFrame, kind: str = "shrunk") -> pd.DataFrame:
    """Annualised expected return per stock with its standard error.

    - ``historical``: the sample mean.
    - ``shrunk``: James–Stein towards the cross-sectional mean, each stock pulled in proportion to its own noise.
    - ``zero_alpha``: every stock gets the cross-sectional mean (the optimiser then sees only risk – a check on how
      much of a portfolio is the means and how much the covariance)."""
    n = R.notna().sum()
    mu = R.mean() * TRADING_DAYS
    se = R.std() * np.sqrt(TRADING_DAYS) / np.sqrt(n.clip(lower=1) / TRADING_DAYS)   # SE of an annual mean over n/252 years
    grand = float(mu.mean())
    if kind == "historical":
        est = mu
    elif kind == "zero_alpha":
        est = pd.Series(grand, index=mu.index)
    elif kind == "shrunk":
        disp = float(((mu - grand) ** 2).mean())
        w = (se ** 2 / (se ** 2 + disp)).clip(0, 1) if disp > 0 else pd.Series(1.0, index=mu.index)
        est = grand + (1 - w) * (mu - grand)
    else:
        raise ValueError(kind)
    return pd.DataFrame({"mu": est, "se": se, "raw": mu, "n": n})


def view_returns(views: dict[str, dict], prices: pd.Series, fallback: float) -> pd.Series:
    """Expected return implied by a 12-month target: TP / price − 1 (per year, horizon scaled). A SELL view gives
    its (negative) number; a stock without a view gets ``fallback``. Estimates (EST), not measurements."""
    out = {}
    for code, px in prices.items():
        v = views.get(code)
        if not v or not v.get("target") or not px:
            out[code] = fallback
            continue
        months = int(v.get("horizon_months") or 12)
        out[code] = (float(v["target"]) / float(px) - 1) * 12 / months
    return pd.Series(out)


# ------------------------------------------------------------------------------------------------ optimisers
@dataclass
class Portfolio:
    name: str
    weights: pd.Series                       # long-only, sums to the invested share
    cash: float = 0.0                        # share at the risk-free rate (CML mixes)
    note: str = ""
    inputs: dict = field(default_factory=dict)

    def exp_return(self, mu: pd.Series, rf: float) -> float:
        return float((self.weights * mu.reindex(self.weights.index)).sum() + self.cash * rf)

    def vol(self, cov: pd.DataFrame) -> float:
        w = self.weights.reindex(cov.index).fillna(0.0).to_numpy()
        return float(np.sqrt(w @ cov.to_numpy() @ w))

    def sharpe(self, mu: pd.Series, cov: pd.DataFrame, rf: float) -> float | None:
        v = self.vol(cov)
        return (self.exp_return(mu, rf) - rf) / v if v > 0 else None


def _solve(objective, n: int, cap: float, x0=None, extra_constraints=()) -> np.ndarray:
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}, *extra_constraints]
    bounds = [(0.0, cap)] * n
    x0 = np.full(n, 1.0 / n) if x0 is None else x0
    res = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": 500, "ftol": 1e-12})
    w = np.clip(res.x, 0, cap)
    return w / w.sum()


def equal_weight(codes) -> Portfolio:
    return Portfolio("Likevektet", pd.Series(1.0 / len(codes), index=list(codes)), note="every stock the same weight; the reference")


def inverse_vol(cov: pd.DataFrame) -> Portfolio:
    iv = 1.0 / np.sqrt(np.diag(cov.to_numpy()))
    return Portfolio("Invers volatilitet", pd.Series(iv / iv.sum(), index=cov.index), note="weight 1/σ: calmer stocks weigh more, no means used")


def min_variance(cov: pd.DataFrame, cap: float = DEFAULT_CAP) -> Portfolio:
    S = cov.to_numpy()
    w = _solve(lambda w: w @ S @ w, len(S), cap)
    return Portfolio("Minimum varians", pd.Series(w, index=cov.index), note=f"lowest variance, long-only, no stock above {cap:.0%}; no means used")


def max_sharpe(mu: pd.Series, cov: pd.DataFrame, rf: float, cap: float = DEFAULT_CAP) -> Portfolio:
    m, S = mu.reindex(cov.index).to_numpy(), cov.to_numpy()

    def neg_sharpe(w):
        v = np.sqrt(w @ S @ w)
        return -((w @ m - rf) / v) if v > 0 else 0.0

    w = _solve(neg_sharpe, len(S), cap)
    return Portfolio("Maks Sharpe (tangens)", pd.Series(w, index=cov.index), note=f"the tangency portfolio on the capital market line, long-only, cap {cap:.0%}")


def cml_point(tangency: Portfolio, cov: pd.DataFrame, target_vol: float, name: str | None = None) -> Portfolio:
    """The portfolio on the capital market line with volatility ``target_vol``: the tangency portfolio scaled, the
    rest in cash at the risk-free rate. Long-only: no borrowing, so the scale is capped at 1."""
    vt = tangency.vol(cov)
    k = min(target_vol / vt, 1.0) if vt > 0 else 0.0
    return Portfolio(name or f"CML {target_vol:.0%} vol", tangency.weights * k, cash=1.0 - k,
                     note=f"{k:.0%} in the tangency portfolio, {1 - k:.0%} at the policy rate – a point on the CML with {min(target_vol, vt):.0%} volatility")


def risk_parity(cov: pd.DataFrame, cap: float = 0.5) -> Portfolio:
    """Equal risk contribution: each stock contributes the same share of portfolio variance."""
    S = cov.to_numpy()
    n = len(S)

    def obj(w):
        v = w @ S @ w
        rc = w * (S @ w) / v if v > 0 else np.full(n, 1.0 / n)
        return float(((rc - 1.0 / n) ** 2).sum()) * 1e4

    iv = 1.0 / np.sqrt(np.diag(S))
    w = _solve(obj, n, cap, x0=iv / iv.sum())
    return Portfolio("Risikoparitet", pd.Series(w, index=cov.index), note="each stock the same share of the portfolio's variance; no means used")


def view_weighted(mu_view: pd.Series, cov: pd.DataFrame, rf: float, cap: float = 0.25, name: str = "Synene") -> Portfolio:
    """Maximum Sharpe on view-implied expected returns, SELL views and stocks without a view excluded."""
    keep = mu_view[mu_view > rf].index.intersection(cov.index)
    if len(keep) == 0:
        return Portfolio(name, pd.Series(dtype=float), note="no view with an expected return above the policy rate")
    sub = cov.loc[keep, keep]
    cap_eff = max(cap, 1.0 / len(keep) + 1e-9)
    p = max_sharpe(mu_view.loc[keep], sub, rf, cap=cap_eff)
    return Portfolio(name, p.weights, note=f"max Sharpe on the targets' implied returns (EST), {len(keep)} stocks with a view above the policy rate, cap {cap_eff:.0%}")


def frontier(mu: pd.Series, cov: pd.DataFrame, cap: float = DEFAULT_CAP, points: int = 25) -> pd.DataFrame:
    """Minimum variance for a grid of target returns between the min-variance portfolio and the highest reachable."""
    m, S = mu.reindex(cov.index).to_numpy(), cov.to_numpy()
    n = len(S)
    lo = min_variance(cov, cap)
    r_lo = float(lo.weights.to_numpy() @ m)
    r_hi = float(np.sort(m)[::-1][: int(np.ceil(1 / cap))].mean()) if cap < 1 else float(m.max())
    rows = []
    for r in np.linspace(r_lo, r_hi, points):
        w = _solve(lambda w: w @ S @ w, n, cap, extra_constraints=({"type": "eq", "fun": lambda w, r=r: w @ m - r},))
        rows.append({"ret": float(w @ m), "vol": float(np.sqrt(w @ S @ w))})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ out of sample
def portfolio_returns(weights: pd.Series, R: pd.DataFrame, cash: float = 0.0, rf_daily: float = 0.0) -> pd.Series:
    """Daily returns of a portfolio held at fixed weights (rebalanced daily to them) – fine for a month at a time."""
    w = weights.reindex(R.columns).fillna(0.0)
    return R.fillna(0.0) @ w + cash * rf_daily


def max_drawdown(nav: pd.Series) -> float:
    return float((nav / nav.cummax() - 1).min()) if len(nav) else 0.0


def perf(r: pd.Series, rf: float = 0.0) -> dict:
    """Annualised return, volatility, Sharpe and max drawdown of a daily return series."""
    r = r.dropna()
    if len(r) < 20:
        return {"n": int(len(r))}
    nav = (1 + r).cumprod()
    years = len(r) / TRADING_DAYS
    cagr = float(nav.iloc[-1] ** (1 / years) - 1)
    vol = float(r.std() * np.sqrt(TRADING_DAYS))
    return {"n": int(len(r)), "years": round(years, 2), "cagr": cagr, "vol": vol, "sharpe": (cagr - rf) / vol if vol > 0 else None,
            "max_dd": max_drawdown(nav), "total": float(nav.iloc[-1] - 1)}


def walk_forward(adj: pd.DataFrame, builders: dict, start: pd.Timestamp, end: pd.Timestamp | None = None, lookback_years: float = 3.0,
                 rf: float = 0.0, cost: float = COST, step_months: int = 1) -> dict:
    """Rebuild every portfolio at each month end from trailing data only, hold it a month, chain the months. Returns
    per name the daily return series (net of ``cost`` on turnover) and the rebalance dates. ``builders`` maps a name
    to f(R_trailing, rf) -> Portfolio."""
    adj = adj.sort_index()
    end = end or adj.index[-1]
    month_ends = [d for d in adj.index if d >= start and d <= end]
    marks = pd.DatetimeIndex(month_ends).to_period("M").drop_duplicates()
    rebal = [adj.index[adj.index.to_period("M") == p][0] for p in marks]
    out = {name: [] for name in builders}
    prev = {name: None for name in builders}
    turnover = {name: [] for name in builders}
    rf_daily = rf / TRADING_DAYS
    for i, d in enumerate(rebal):
        stop = rebal[i + 1] if i + 1 < len(rebal) else end + pd.Timedelta(days=1)
        hold = adj[(adj.index >= d) & (adj.index < stop)].pct_change().iloc[1:]
        if hold.empty:
            continue
        R_tr = returns_matrix(adj, end=d - pd.Timedelta(days=1), years=lookback_years)
        for name, build in builders.items():
            try:
                p = build(R_tr, rf)
            except Exception:  # noqa: BLE001 – a month the optimiser cannot solve is a month in cash, recorded as such
                p = Portfolio(name, pd.Series(dtype=float), cash=1.0)
            w = p.weights.reindex(hold.columns).fillna(0.0)
            r = portfolio_returns(w, hold, p.cash, rf_daily)
            tw = float((w - prev[name].reindex(w.index).fillna(0.0)).abs().sum()) if prev[name] is not None else float(w.abs().sum())
            turnover[name].append(tw)
            if len(r):
                r.iloc[0] -= tw * cost
            out[name].append(r)
            prev[name] = w
    series = {name: (pd.concat(parts) if parts else pd.Series(dtype=float)) for name, parts in out.items()}
    return {"returns": series, "rebalances": [f"{d:%Y-%m-%d}" for d in rebal],
            "turnover": {name: float(np.mean(t)) if t else 0.0 for name, t in turnover.items()}}


def sharpe_diff_ci(a: pd.Series, b: pd.Series, n: int = 1000, seed: int = 20261102) -> dict:
    """Difference in annualised Sharpe (a − b) with a monthly block-bootstrap 95 % interval: is one portfolio's
    out-of-sample edge over the other more than noise?"""
    df = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
    if len(df) < 60:
        return {"diff": None, "lo": None, "hi": None, "months": 0}
    blocks = [g for _, g in df.groupby(df.index.to_period("M")) if len(g) > 0]
    rng = np.random.default_rng(seed)

    def sh(x):
        return float(x.mean() / x.std() * np.sqrt(TRADING_DAYS)) if x.std() > 0 else 0.0

    diffs = []
    for _ in range(n):
        pick = rng.integers(0, len(blocks), len(blocks))
        s = pd.concat([blocks[i] for i in pick])
        diffs.append(sh(s["a"]) - sh(s["b"]))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"diff": sh(df["a"]) - sh(df["b"]), "lo": float(lo), "hi": float(hi), "months": len(blocks)}
