"""The coverage universe: every company in the store with the level it is actually covered at, and the plan for it
(DECISIONS D38).

The level is derived from what exists, never typed in:

- ``full``  – a research report has been published to the dashboard (``cases/reports_pdf/<CODE>/``) or the research
  book names a model file: a case with a workbook, a gate and a report behind it;
- ``light`` – a light case (``cases/<CODE>.json``) exists: one page from the store's statements;
- ``watch`` – the company is on the watchlist and nothing more;
- ``none``  – in the store, not looked at.

Separately from the level, each company may have a view from Oscar, from Claude, from both or from neither. A full
case without a view (a report built, the row not yet logged) is shown as exactly that.

The plan is the one thing typed in: ``~/osloquant-home/coverage.yaml`` holds, per company, the level it *should* be
at, who owns the view (``oscar``, ``claude``, ``both``), the rhythm (``report`` = after every quarterly report,
``monthly``, ``quarterly``, ``event``) and a note. The coverage page shows the gap between plan and fact, by sector
group and by company. Private, like the rest of the research book; written only by ``oq coverage set``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from osloquant import judgements as jg
from osloquant.dashboard import market as mk

PLAN_FILE = "coverage.yaml"
LEVELS = ("full", "light", "watch", "none")
LEVEL_LABEL = {"full": "full case", "light": "lett case", "watch": "følges", "none": "ikke dekket"}
OWNERS = ("oscar", "claude", "both")
RHYTHMS = ("report", "monthly", "quarterly", "event")
RHYTHM_LABEL = {"report": "etter hver rapport", "monthly": "månedlig", "quarterly": "kvartalsvis", "event": "ved hendelse"}
LIGHT_STALE_DAYS = 120        # a light case older than this, or built before the newest report, is stale


# ------------------------------------------------------------------------------------------------ the plan
def plan_path() -> Path:
    return jg.home() / PLAN_FILE


def plan() -> dict[str, dict]:
    p = plan_path()
    if not p.exists():
        return {}
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {str(e["code"]).upper(): e for e in doc.get("entries", []) if e.get("code")}


def _write_plan(entries: list[dict]) -> None:
    head = ("# Coverage plan: the level each company should be covered at, who owns the view and how often it is renewed.\n"
            "# Private. The level a company IS at is derived from the files (oq coverage); this file holds only the intent.\n")
    plan_path().write_text(head + yaml.safe_dump({"entries": entries}, sort_keys=False, allow_unicode=True), encoding="utf-8")


def set_plan(code: str, target: str | None = None, owner: str | None = None, rhythm: str | None = None, note: str | None = None,
             today: str | None = None) -> dict:
    """Write or update the plan entry of one company. Fields left None keep their value; an entry is created with
    whatever is given. Returns the entry."""
    code = code.upper().removesuffix(".OL")
    if not code.isalnum():
        raise ValueError("a stock code has letters and digits only")
    if target is not None and target not in LEVELS:
        raise ValueError(f"target must be one of {', '.join(LEVELS)}")
    if owner is not None and owner not in OWNERS:
        raise ValueError(f"owner must be one of {', '.join(OWNERS)}")
    if rhythm is not None and rhythm not in RHYTHMS:
        raise ValueError(f"rhythm must be one of {', '.join(RHYTHMS)}")
    entries = list(plan().values())
    entry = next((e for e in entries if str(e["code"]).upper() == code), None)
    if entry is None:
        entry = {"code": code, "added": today or datetime.now().strftime("%Y-%m-%d")}
        entries.append(entry)
    for k, v in (("target", target), ("owner", owner), ("rhythm", rhythm), ("note", note)):
        if v is not None:
            entry[k] = v.strip() if isinstance(v, str) else v
    entry["updated"] = today or datetime.now().strftime("%Y-%m-%d")
    _write_plan(entries)
    return entry


# ------------------------------------------------------------------------------------------------ the facts
def _level(code: str, case, lc: dict | None, report: dict | None, watched: set[str]) -> str:
    if report or (case and case.model):
        return "full"
    if lc:
        return "light"
    if code in watched:
        return "watch"
    return "none"


def _view(v: dict | None, px: float | None) -> dict | None:
    if not v or not v.get("target"):
        return None
    since = px / v["price"] - 1 if px and v.get("price") else None
    return {"rating": v.get("rating"), "target": float(v["target"]), "date": str(v.get("date", ""))[:10],
            "since": 0.0 if since is not None and abs(since) < 5e-4 else since,      # no "-0.0 %" on the day a view is logged
            "to_tp": float(v["target"]) / px - 1 if px else None}


def universe(snap: mk.Snapshot, cases, watch: list[dict], today: pd.Timestamp | None = None, plan_entries: dict | None = None,
             next_events: dict | None = None) -> list[dict]:
    """One row per company in the store: group, price, level, views, the light case's age, the newest report, the plan
    and the gap to it. Sorted by group order, then level, then code."""
    from osloquant.dashboard import lightcase as lcm
    from osloquant.dashboard import reportpdf as rpdf

    today = today or pd.Timestamp.now().normalize()
    plan_entries = plan() if plan_entries is None else plan_entries
    by_code = {c.code: c for c in cases}
    watched = {w["code"] for w in watch if not w.get("moved_to_book")}
    codes = sorted(set(snap.names) | set(by_code) | watched)
    out = []
    for code in codes:
        c = by_code.get(code)
        lc = lcm.load(code)
        rep = rpdf.latest(code)
        lp = mk.last_price(snap, code)
        px = lp[0] if lp else None
        level = _level(code, c, lc, rep, watched)
        lc_built = str(lc.get("built_at", ""))[:10] if lc else None
        lc_age = (today - pd.Timestamp(lc_built)).days if lc_built else None
        lc_stale = bool(lc_age is not None and (lc_age > LIGHT_STALE_DAYS or (rep and rep["date"] > lc_built)))
        p = plan_entries.get(code) or {}
        target = p.get("target")
        gap = bool(target and LEVELS.index(target) < LEVELS.index(level))
        out.append({"code": code, "name": snap.names.get(code, c.name if c else code), "group": snap.group(code), "price": px,
                    "level": level, "in_store": code in snap.names,
                    "oscar": _view(c.view if c else None, px), "claude": _view(c.claude_view if c else None, px),
                    "lightcase_built": lc_built, "lightcase_age": lc_age, "lightcase_stale": lc_stale,
                    "report": {"date": rep["date"], "tp": rep.get("tp"), "rating": rep.get("rating"), "file": rep["file"]} if rep else None,
                    "model": bool(c and c.model), "plan": p or None, "target": target, "owner": p.get("owner"), "rhythm": p.get("rhythm"),
                    "gap": gap, "next": (next_events or {}).get(code)})
    order = {g: i for i, g in enumerate(mk.GROUP_ORDER + ["Other"])}
    return sorted(out, key=lambda r: (order.get(r["group"], 99), LEVELS.index(r["level"]), r["code"]))


def summary(rows: list[dict]) -> list[dict]:
    """Per sector group (group order, then a total row): companies, how many at each level, with a view from
    Oscar / Claude / either, and how many are below their planned level."""
    out = []
    groups = [g for g in mk.GROUP_ORDER + ["Other"] if any(r["group"] == g for r in rows)]
    for g in groups + ["Alle"]:
        rs = rows if g == "Alle" else [r for r in rows if r["group"] == g]
        out.append({"group": g, "n": len(rs), **{lv: sum(r["level"] == lv for r in rs) for lv in LEVELS},
                    "oscar": sum(bool(r["oscar"]) for r in rs), "claude": sum(bool(r["claude"]) for r in rs),
                    "any_view": sum(bool(r["oscar"] or r["claude"]) for r in rs), "gap": sum(r["gap"] for r in rs),
                    "stale": sum(r["lightcase_stale"] for r in rs)})
    return out


def counts(rows: list[dict]) -> dict:
    """The one-line figures the front page shows."""
    return {"universe": len(rows), **{lv: sum(r["level"] == lv for r in rows) for lv in LEVELS},
            "any_view": sum(bool(r["oscar"] or r["claude"]) for r in rows), "gap": sum(r["gap"] for r in rows)}
