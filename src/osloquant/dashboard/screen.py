"""What the price requires, across the universe (DECISIONS D43).

One row per light case: the growth (or, for banks and insurers, the return on equity) the price pays for, set against
what the company has delivered in the annual table, with the case's quality grade beside it (D42). For a cyclical
group the requirement is read on the average EBIT margin, not on a last twelve months that may be a peak.

The comparison is deliberately plain: revenue growth a year over the annual table, not EBIT growth, because EBIT from
a low base gives growth rates that mean nothing; the return on equity averaged over the same years for a bank. For a
cyclical group three or four years of revenue measure the cycle, not growth (2022 was a peak year for oil, gas and
freight), so the requirement is compared with the long-run growth the light cases assume (2 %, EST) and the revenue
history is shown beside it, not used. The
requirement is for good and the history is three or four years, so the gap says where the price and the past
disagree, not which of them is right. That is what the list is for: the companies where the two disagree most are
where a full case adds the most, and the coverage plan is Oscar's to change (``oq coverage set``). Nothing here is a
buy or a sell, and nothing is written.

Not tested against returns: the store holds the statements as they look today, not as they looked on each date, so a
historical test of this screen would see the future (the same reason D16 freezes a copy for the desk's real-data test).
"""

from __future__ import annotations

from osloquant.dashboard import lightcase as lc

GAP_PP = 0.02            # less than two percentage points a year between requirement and history is "in line"
N_CANDIDATES = 6

VERDICT_LABEL = {
    "more": "prisen krever mer enn historikken",
    "less": "prisen krever mindre enn historikken",
    "fall": "prisen regner med at resultatet faller",
    "in_line": "prisen og historikken stemmer",
    "above_wacc": "prisen krever vekst på eller over kapitalkosten",
    "below_capital": "EV er under kapitalen selskapet binder",
    "below_wacc": "avkastningen er under kapitalkosten",
    "nohist": "ingen historikk å sammenligne med",
    "none": "ingen lesning",
}


def row(case: dict, level: str | None = None) -> dict:
    """The screen's row for one light case (pure: the case file and the coverage level only)."""
    q, h, n = lc.quality(case), lc.history(case), lc.normalised(case)
    rv, ret = case.get("reverse") or {}, case.get("returns") or {}
    fin = bool(case.get("financial"))
    cyc = case.get("group") in lc.CYCLICAL_GROUPS
    out = {"code": case["code"], "name": case.get("name", case["code"]), "group": case.get("group"), "level": level, "quality": q,
           "financial": fin, "cyclical": cyc, "history": h, "built_at": str(case.get("built_at", ""))[:10]}
    if fin:
        kind = None
        req, hist, basis = rv.get("implied_roe"), h.get("roe_avg"), "P/B"
        out |= {"measure": "ROE", "now": ret.get("roe")}
    else:
        ltm_r = lc.reading(case)
        used = n if cyc and n else ltm_r
        kind, req = used.get("kind"), used.get("implied_g")
        basis = ("snittmargin " + n["years"]) if used is n else "siste 12 mnd"
        hist = lc.G_LONG_EST if cyc else h.get("rev_cagr")
        out |= {"measure": "vekst", "now": ret.get("roic"), "roic_avg": h.get("roic_avg"), "wacc": rv.get("wacc_est"),
                "req_ltm": ltm_r.get("implied_g"), "req_norm": n.get("implied_g") if n else None, "reads": used.get("reads")}
    out |= {"required": req, "hist": hist, "basis": basis, "gap": None, "kind": kind,
            "ref": "long_run" if cyc and not fin else "history"}
    if not q["usable"]:
        verdict = "none"
    elif req is None:
        verdict = kind if kind in ("below_wacc", "above_wacc", "below_capital") else "none"
    elif hist is None:
        verdict = "nohist"
    else:
        out["gap"] = req - hist
        if out["gap"] > GAP_PP:
            verdict = "more"
        elif out["gap"] < -GAP_PP:
            verdict = "fall" if not fin and req < 0 else "less"
        else:
            verdict = "in_line"
    out["verdict"] = verdict
    out["label"] = VERDICT_LABEL[verdict]
    return out


def rows(cases: list[dict], levels: dict[str, str] | None = None) -> list[dict]:
    levels = levels or {}
    return [row(c, levels.get(c["code"])) for c in cases]


def candidates(rs: list[dict], n: int = N_CANDIDATES) -> dict:
    """Where the price and the history disagree most, among usable cases not already fully covered: the ones the
    price asks more of (largest positive gap first, then those that need growth at the cost of capital) and the ones it
    asks less of (largest negative gap first, a price that expects a fall included, then an EV below the capital
    employed)."""
    pool = [r for r in rs if r["quality"]["usable"] and r["level"] != "full"]
    more = sorted((r for r in pool if r["gap"] is not None and r["gap"] > GAP_PP), key=lambda r: -r["gap"])
    more += [r for r in pool if r["verdict"] == "above_wacc"]
    less = sorted((r for r in pool if r["gap"] is not None and r["gap"] < -GAP_PP), key=lambda r: r["gap"])
    less += [r for r in pool if r["verdict"] == "below_capital"]
    return {"more": more[:n], "less": less[:n]}


def counts(rs: list[dict]) -> dict:
    grades = [r["quality"]["grade"] for r in rs]
    return {"n": len(rs), **{f"grade_{g}": grades.count(g) for g in "ABC"},
            **{v: sum(r["verdict"] == v for r in rs) for v in VERDICT_LABEL}}
