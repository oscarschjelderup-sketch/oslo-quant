"""Outcome odds: how often has a price like this reached the target first, the kill level first, or neither within a
horizon? A reality check against the store's own history, not a forecast. Reports, rates and news can do what the
history never did.

Two methods, shown side by side (DECISIONS.md D14):

1. **Simulation** – 10,000 paths built by resampling the stock's own daily log returns since 2010 in blocks of 20
   sessions (blocks keep calm and volatile spells together). The stock's own historical drift stays in.
2. **Historical cases** – every month-start since 2010 on each of the 64 stocks, with the target and the kill level
   placed at the same distances measured in that stock's own volatility at the time; and, separately, the stock's
   own history with the same percentage distances. Windows overlap (a 12-month window starts every month), so the
   number of independent cases is smaller than the count; the page says so.

A level counts as reached when a daily close is at or beyond it. The same first-passage rule measures the technical
signals: entry at the next open, target and stop 2 × ATR(20) away, after a 0.5 % round trip.

Everything is deterministic: a fixed seed and the store's closes.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from osloquant import signals as sg

HORIZONS = (("3 mnd", 63), ("6 mnd", 126), ("12 mnd", 252))
PATHS = 10_000
BLOCK = 20
SEED = 20261023
MIN_HISTORY = 250          # sessions of history before a simulation or a historical case counts
VOL_WINDOW = 250           # trailing sessions for the volatility that scales a historical case
STEP = 21                  # a historical case starts every 21 sessions
START = "2010-01-01"
COST = sg.ROUND_TRIP_COST
R_MULT = 2.0               # signal bracket: target and stop R = 2 x ATR(20) from the entry
SIGNAL_HORIZONS = (20, 60)


@dataclass
class Outcome:
    target: float
    kill: float
    neither: float
    n: int
    note: str = ""
    extra: dict = field(default_factory=dict)


def first_passage(rel: np.ndarray, up, down) -> np.ndarray:
    """For each row of relative prices (n, h): +1 if ``up`` is reached first, -1 if ``down`` is, 0 if neither.
    ``up`` and ``down`` are one level for all rows or one per row."""
    h = rel.shape[1]
    up, down = np.asarray(up, dtype=float), np.asarray(down, dtype=float)
    hu = rel >= (up[:, None] if up.ndim else up)
    hd = rel <= (down[:, None] if down.ndim else down)
    fu = np.where(hu.any(axis=1), hu.argmax(axis=1), h)
    fd_ = np.where(hd.any(axis=1), hd.argmax(axis=1), h)
    return np.where(fu < fd_, 1, np.where(fd_ < fu, -1, 0))


def _outcome(res: np.ndarray, note: str = "", **extra) -> Outcome:
    n = len(res)
    if not n:
        return Outcome(np.nan, np.nan, np.nan, 0, note or "no cases", extra)
    return Outcome(float((res == 1).mean()), float((res == -1).mean()), float((res == 0).mean()), n, note, extra)


# ------------------------------------------------------------------------------------------------ method 1: simulation
def simulate(closes: pd.Series, up: float, down: float, horizons=HORIZONS, paths: int = PATHS, block: int = BLOCK,
             seed: int = SEED) -> dict[str, Outcome]:
    c = closes.dropna()
    r = np.diff(np.log(c.to_numpy(dtype=float)))
    if len(r) < MIN_HISTORY:
        return {lab: Outcome(np.nan, np.nan, np.nan, 0, f"too little history ({len(r) + 1} sessions)") for lab, _ in horizons}
    H = max(h for _, h in horizons)
    nb = -(-H // block)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(r) - block + 1, size=(paths, nb))
    idx = (starts[:, :, None] + np.arange(block)).reshape(paths, nb * block)[:, :H]
    rel = np.exp(np.cumsum(r[idx], axis=1))
    drift, vol = float(r.mean() * 252), float(r.std() * np.sqrt(252))
    return {lab: _outcome(first_passage(rel[:, :h], up, down), drift=drift, vol=vol, sessions=len(r) + 1,
                          since=f"{c.index[0]:%Y-%m-%d}") for lab, h in horizons}


# ------------------------------------------------------------------------------------------------ method 2: history
def _starts(n: int, h: int) -> np.ndarray:
    return np.arange(VOL_WINDOW, n - h, STEP)


def analogues(closes: pd.DataFrame, code: str, up: float, down: float, horizons=HORIZONS) -> dict[str, dict[str, Outcome]]:
    """Historical cases: all stocks with the distances scaled to each stock's volatility at the time (``universe``),
    and the stock's own history with the same percentage distances (``own``)."""
    own_c = closes[code].dropna() if code in closes else pd.Series(dtype=float)
    lr = np.log(own_c).diff().dropna()
    if len(lr) < 60:
        empty = {lab: Outcome(np.nan, np.nan, np.nan, 0, f"too little history ({len(own_c)} sessions)") for lab, _ in horizons}
        return {"universe": empty, "own": empty}
    sigma = float(lr.iloc[-VOL_WINDOW:].std() * np.sqrt(252))
    zu, zd = np.log(up) / sigma, np.log(down) / sigma
    out = {"universe": {}, "own": {}}
    for lab, h in horizons:
        uni, own, stocks = [], [], 0
        for s in closes.columns:
            c = closes[s].dropna().to_numpy(dtype=float)
            st = _starts(len(c), h)
            if not len(st):
                continue
            vol = pd.Series(np.log(c)).diff().rolling(VOL_WINDOW).std().to_numpy() * np.sqrt(252)
            st = st[np.isfinite(vol[st])]
            if not len(st):
                continue
            rel = np.stack([c[i + 1:i + 1 + h] / c[i] for i in st])
            res = first_passage(rel, np.exp(zu * vol[st]), np.exp(zd * vol[st]))
            uni.append(res)
            stocks += 1
            if s == code:
                own.append(first_passage(rel, up, down))
        uni_res = np.concatenate(uni) if uni else np.array([])
        own_res = np.concatenate(own) if own else np.array([])
        out["universe"][lab] = _outcome(uni_res, stocks=stocks, independent=round(len(uni_res) * STEP / h))
        out["own"][lab] = _outcome(own_res, independent=round(len(own_res) * STEP / h),
                                   note="" if len(own_res) else f"too little history ({len(own_c)} sessions)")
    return out | {"sigma": sigma}


# ------------------------------------------------------------------------------------------------ cases
def complete_sessions(closes: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Drop today's bar while the session is still open (Oslo closes 16:20; Yahoo is ~15 minutes behind), so a
    half-finished day never enters the odds."""
    now = now if now is not None else pd.Timestamp.now(tz="Europe/Oslo")
    if len(closes) and closes.index[-1].date() == now.date() and (now.hour, now.minute) < (16, 40):
        return closes.iloc[:-1]
    return closes


@lru_cache(maxsize=2)
def _long_closes(stamp: str) -> pd.DataFrame:
    return complete_sessions(sg.load_panel(start=START)["close"])


def breakeven(price: float, target: float, kill: float) -> tuple[float, float]:
    """R = reward / risk to the two levels, and the share of decided cases (target or kill reached) the target must
    win for the bet to break even: 1 / (1 + R)."""
    r = abs(target - price) / abs(price - kill)
    return r, 1 / (1 + r)


def long_closes() -> pd.DataFrame:
    from osloquant.contract.api import get_coverage
    from osloquant.domain import Stock1dAdjKdata

    now = pd.Timestamp.now(tz="Europe/Oslo")
    return _long_closes(f'{get_coverage(Stock1dAdjKdata)["last"]}|{(now.hour, now.minute) >= (16, 40)}|{now.date()}')


@dataclass
class CaseOdds:
    code: str
    price: float
    asof: pd.Timestamp
    target: float
    kill: float
    kill_source: str
    simulation: dict[str, Outcome]
    universe: dict[str, Outcome]
    own: dict[str, Outcome]
    sigma: float | None
    note: str = ""


@lru_cache(maxsize=32)
def _case_odds_cached(code: str, asof: str, target: float, kill: float, kill_source: str, stamp: int) -> CaseOdds:
    closes = long_closes()
    c = closes[code].dropna() if code in closes else pd.Series(dtype=float)
    price = float(c.iloc[-1])
    note = ""
    if not (min(target, kill) < price < max(target, kill)):
        note = f"the price {price:.2f} is not between the target {target:g} and the kill level {kill:g}"
        empty = {lab: Outcome(np.nan, np.nan, np.nan, 0, note) for lab, _ in HORIZONS}
        return CaseOdds(code, price, c.index[-1], target, kill, kill_source, empty, empty, empty, None, note)
    # a SELL view has its target below the price and its kill level above: measure the mirror and swap the labels
    upside = target > price
    up, down = (target / price, kill / price) if upside else (kill / price, target / price)
    an = analogues(closes, code, up, down)
    sim = simulate(c, up, down)
    if not upside:
        swap = lambda d: {k: dataclasses.replace(o, target=o.kill, kill=o.target) for k, o in d.items()}  # noqa: E731
        sim, an["universe"], an["own"] = swap(sim), swap(an["universe"]), swap(an["own"])
    return CaseOdds(code, price, c.index[-1], target, kill, kill_source, sim, an["universe"], an["own"], an.get("sigma"), note)


def case_odds(code: str, target: float, kill: float, kill_source: str) -> CaseOdds | None:
    closes = long_closes()
    if code not in closes or closes[code].dropna().empty:
        return None
    c = closes[code].dropna()
    return _case_odds_cached(code, f"{c.index[-1]:%Y-%m-%d}", float(target), float(kill), kill_source, len(c))


def kill_level(view: dict | None) -> tuple[float | None, str]:
    """The price that stands for the kill criteria: the view's own kill level, else its bear value."""
    v = view or {}
    if v.get("kill_level"):
        return float(v["kill_level"]), "kill level in the view"
    if v.get("bear"):
        return float(v["bear"]), "bear value (no kill level set)"
    return None, "no kill level or bear value"


# ------------------------------------------------------------------------------------------------ signals
def atr(P: dict[str, pd.DataFrame], n: int = 20) -> pd.DataFrame:
    prev = P["close"].shift(1)
    tr = np.maximum(P["high"] - P["low"], np.maximum((P["high"] - prev).abs(), (P["low"] - prev).abs()))
    return tr.rolling(n).mean()


def signal_brackets(P: dict[str, pd.DataFrame], end: str | None = None, horizons=SIGNAL_HORIZONS, r_mult: float = R_MULT,
                    cost: float = COST) -> pd.DataFrame:
    """For every signal: enter at the next open, target = entry x (1 + cost) + R, stop = entry - R, R = r_mult x ATR(20)
    on the signal day; first daily close at or beyond a level decides. Returns per signal and horizon the share of
    targets, stops and neither, and the average result in R after the round trip."""
    if end:
        P = {k: v.loc[:end] for k, v in P.items()}
    C = P["close"]
    cv, ov, av = C.to_numpy(dtype=float), P["open"].to_numpy(dtype=float), atr(P).to_numpy(dtype=float)
    n_days = len(C)
    rows = {}
    for name, (kind, f) in sg.signal_frames(P).items():
        fv = f.reindex(index=C.index, columns=C.columns).fillna(False).to_numpy(dtype=bool)
        ii, jj = np.nonzero(fv)
        row = {"kind": kind}
        for h in horizons:
            keep = (ii + 1 + h <= n_days - 1)
            res, rr = [], []
            for i, j in zip(ii[keep], jj[keep], strict=True):
                entry, R = ov[i + 1, j], r_mult * av[i, j]
                if not (np.isfinite(entry) and np.isfinite(R) and R > 0 and entry > 0):
                    continue
                path = cv[i + 1:i + 1 + h, j]
                if not np.isfinite(path).all():
                    continue
                up, dn = entry * (1 + cost) + R, entry - R
                o = first_passage(path[None, :] / entry, up / entry, dn / entry)[0]
                res.append(o)
                if o == 1:
                    rr.append(1.0)
                elif o == -1:
                    rr.append(-(R + cost * entry) / R)
                else:
                    rr.append((path[-1] - entry * (1 + cost)) / R)
            res, rr = np.array(res), np.array(rr)
            n = len(res)
            row[f"h{h}"] = {"target": round(float((res == 1).mean()), 4) if n else None,
                            "stop": round(float((res == -1).mean()), 4) if n else None,
                            "neither": round(float((res == 0).mean()), 4) if n else None,
                            "mean_R": round(float(rr.mean()), 4) if n else None, "events": n}
        rows[name] = row
    return rows


def write_brackets(rows: dict, path=None) -> None:
    """Add the bracket outcomes to the odds file next to the excess returns, without touching those."""
    import yaml

    path = path or sg.odds_path()
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    doc.setdefault("measured", {})["bracket"] = {
        "entry": "next open", "target": "entry x (1 + cost) + R", "stop": "entry - R", "R": f"{R_MULT:g} x ATR(20) on the signal day",
        "decided_by": "first daily close at or beyond a level", "round_trip_cost": COST, "horizons": list(SIGNAL_HORIZONS)}
    for name, row in rows.items():
        if name in doc.get("signals", {}):
            doc["signals"][name]["bracket"] = {k: v for k, v in row.items() if k != "kind"}
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
