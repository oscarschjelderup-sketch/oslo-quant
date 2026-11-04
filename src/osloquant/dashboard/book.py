"""The research book and the watchlist, as the dashboard reads and writes them. All of it is private: it lives in the
home directory (``~/osloquant-home``), never in the repository.

- ``researchbook.yaml`` holds what is *about* a company: name, events (report dates), the model files of its case and,
  for older entries, the view it was added with.
- ``judgements.jsonl`` (osloquant.judgements) holds every view as an append-only, hash-chained row. The current view
  of a company is its newest judgement; the yaml view is used only when the log has none for that code.
- Two analysts write views (D31): Oscar's are the current view and drive everything that sizes, warns or asks for a
  decision; Claude's (``analyst: claude`` rows) are kept on the case as ``claude_view`` and shown beside his.
- ``watchlist.yaml`` holds companies followed without a case. Writing a judgement on a watched company moves it into
  the research book (the watchlist entry is kept, marked as moved, so the history of what was watched stays).

The dashboard writes only by appending: a judgement row (``judgements.append``) and, for a company new to the book,
an entry at the end of ``researchbook.yaml``. Nothing is edited or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from osloquant import judgements as jg
from osloquant import signals as sg

WATCH_FILE = "watchlist.yaml"


@dataclass
class Case:
    code: str
    name: str
    view: dict | None                 # the newest judgement (log row) or the yaml view
    view_source: str                  # "log #n" or "researchbook.yaml"
    events: list[dict] = field(default_factory=list)
    kill: list[str] = field(default_factory=list)
    model: dict | None = None         # {"xlsx": path, "map": path} of the toolkit case, for the reverse DCF
    history: list[dict] = field(default_factory=list)   # Oscar's judgements and kill checks, oldest first
    claude_view: dict | None = None   # Claude's newest judgement on the company (D31)
    claude_history: list[dict] = field(default_factory=list)


def _yaml_view(e: dict) -> dict | None:
    if not e.get("rating") or not e.get("target"):
        return None
    return {"date": str(e.get("valuation_date", "")), "price": e.get("price_at_valuation"), "rating": e["rating"],
            "target": e["target"], "bear": e.get("bear"), "base": e.get("base", e.get("dcf")), "bull": e.get("bull"),
            "p_bear": e.get("p_bear"), "p_base": e.get("p_base"), "p_bull": e.get("p_bull"), "kill": e.get("kill", []),
            "thesis": e.get("thesis")}


def _split(rows: list[dict], code: str) -> tuple[list[dict], list[dict]]:
    mine = [r for r in rows if r.get("code") == code]
    return [r for r in mine if jg.analyst_of(r) == jg.DEFAULT_ANALYST], [r for r in mine if jg.analyst_of(r) == "claude"]


def cases() -> list[Case]:
    """Every company in the research book with Oscar's current view and history, and Claude's newest view."""
    book = sg.load_book()
    rows = jg.read_log()
    out = []
    codes = [e["code"] for e in book]
    for e in book:
        hist, chist = _split(rows, e["code"])
        js = [r for r in hist if r["kind"] == "judgement"]
        cj = [r for r in chist if r["kind"] == "judgement"]
        view = js[-1] if js else _yaml_view(e)
        src = f"log #{js[-1]['seq']}" if js else ("researchbook.yaml" if view else "–")
        kill = list((view or {}).get("kill") or e.get("kill", []))
        out.append(Case(e["code"], e.get("name", e["code"]), view, src, list(e.get("events", [])), kill, e.get("model"), hist,
                        cj[-1] if cj else None, chist))
    # judgements logged for codes that are not (yet) in the yaml book still count as cases
    for code in sorted({r["code"] for r in rows if r["kind"] == "judgement"} - set(codes)):
        hist, chist = _split(rows, code)
        js = [r for r in hist if r["kind"] == "judgement"]
        cj = [r for r in chist if r["kind"] == "judgement"]
        named = (js or cj)[-1]
        out.append(Case(code, named.get("name") or code, js[-1] if js else None, f"log #{js[-1]['seq']}" if js else "–", [],
                        list(js[-1].get("kill") or []) if js else [], None, hist, cj[-1] if cj else None, chist))
    return out


def log_claude_view(code: str, name: str, view: dict, price: float, price_date: str, price_source: str, today: str | None = None) -> dict:
    """Append Claude's view on a company (``analyst: claude``). It needs the same fields as Oscar's – rating, target,
    bear/base/bull with probabilities, kill criteria, a rationale – and is scored the same way; it never becomes the
    research book's current view (D31)."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    missing = [k for k in ("rating", "target", "bear", "base", "bull", "p_bear", "p_base", "p_bull", "kill", "thesis") if view.get(k) in (None, "", [])]
    if missing:
        raise ValueError(f"Claude's view on {code} lacks {', '.join(missing)}")
    fields = dict(code=code, name=name, date=today, price=round(float(price), 4), rating=view["rating"], target=float(view["target"]),
                  horizon_months=int(view.get("horizon_months", 12)), bear=float(view["bear"]), base=float(view["base"]), bull=float(view["bull"]),
                  p_bear=float(view["p_bear"]), p_base=float(view["p_base"]), p_bull=float(view["p_bull"]), kill=[str(k) for k in view["kill"]],
                  thesis=str(view["thesis"]).strip(), price_date=price_date, price_source=price_source, analyst="claude",
                  case_file=view.get("case_file"), source=view.get("source", "light case (oq case)"))
    row = jg.append("judgement", fields)
    if code not in [e["code"] for e in sg.load_book()]:
        _append_book_entry(code, name or code, today)
    return row


def case(code: str) -> Case | None:
    code = code.upper()
    return next((c for c in cases() if c.code == code), None)


# ------------------------------------------------------------------------------------------------ watchlist
def watch_path() -> Path:
    return jg.home() / WATCH_FILE


def watchlist() -> list[dict]:
    p = watch_path()
    if not p.exists():
        return []
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return list(doc.get("entries", []))


def _write_watchlist(entries: list[dict]) -> None:
    p = watch_path()
    head = "# Watchlist: companies followed without a full case. Private – written by the dashboard, append-only in spirit.\n"
    p.write_text(head + yaml.safe_dump({"entries": entries}, sort_keys=False, allow_unicode=True), encoding="utf-8")


def add_watch(code: str, note: str, today: str | None = None) -> dict:
    """Follow a company. A code already watched (and not moved) is not added twice."""
    code = code.upper().removesuffix(".OL")
    if not code.isalnum():
        raise ValueError("a stock code has letters and digits only")
    entries = watchlist()
    if any(e["code"] == code and not e.get("moved_to_book") for e in entries):
        raise ValueError(f"{code} is already on the watchlist")
    entry = {"code": code, "added": today or datetime.now().strftime("%Y-%m-%d"), "note": note.strip()}
    entries.append(entry)
    _write_watchlist(entries)
    return entry


def mark_moved(code: str, seq: int, today: str | None = None) -> None:
    entries = watchlist()
    changed = False
    for e in entries:
        if e["code"] == code and not e.get("moved_to_book"):
            e["moved_to_book"] = today or datetime.now().strftime("%Y-%m-%d")
            e["judgement"] = seq
            changed = True
    if changed:
        _write_watchlist(entries)


# ------------------------------------------------------------------------------------------------ writing a judgement
REQUIRED = ("rating", "target", "rationale", "kill")


def validate_form(form: dict) -> list[str]:
    """What is wrong with a judgement form, in words. Empty = it can be written."""
    problems = []
    for k in REQUIRED:
        v = form.get(k)
        if v in (None, "", []) or (isinstance(v, list) and not any(x.strip() for x in v)):
            problems.append({"rating": "choose BUY, HOLD or SELL", "target": "a target price is required",
                             "rationale": "a written rationale is required", "kill": "at least one kill criterion is required"}[k])
    if form.get("rationale") and len(form["rationale"].strip()) < 20:
        problems.append("the rationale must say why (at least 20 characters)")
    if form.get("rating") not in (None, "", "BUY", "HOLD", "SELL"):
        problems.append("the view must be BUY, HOLD or SELL")
    if form.get("consensus_target") not in (None, "") and not (form.get("consensus_source") or "").strip():
        problems.append("a consensus target needs its source and date")
    from osloquant.dashboard import discipline as dsc

    problems += dsc.premortem_problems(form.get("premortem") or dsc.premortem_from_form(form))                 # D46: no view without three reasons it could fail
    if form.get("claude_exists") and form.get("saw_claude") not in ("yes", "no"):
        problems.append("say whether you had read Claude's view on the company before writing this (it decides how the view is scored)")
    for k in ("target", "bear", "base", "bull"):
        if form.get(k) is not None and form[k] != "" and float(form[k]) <= 0:
            problems.append(f"{k} must be a positive price")
    probs = [form.get(k) for k in ("p_bear", "p_base", "p_bull")]
    given = [p for p in probs if p not in (None, "")]
    if given:
        if len(given) < 3:
            problems.append("give all three probabilities or none")
        elif any(not 0 <= float(p) <= 1 for p in given):
            problems.append("probabilities are between 0 and 1")
        elif abs(sum(float(p) for p in given) - 1) > 0.011:
            problems.append(f"the probabilities sum to {sum(float(p) for p in given):.2f}, not 1")
    return problems


def write_judgement(code: str, name: str | None, form: dict, price: float, price_date: str, price_source: str,
                    today: str | None = None) -> dict:
    """Append one judgement row. A company that is not in the research book gets an entry at the end of the yaml;
    a watched company is marked as moved. Returns the written row."""
    problems = validate_form(form)
    if problems:
        raise ValueError("; ".join(problems))
    already = triggered_now(code) if form["rating"] == "BUY" else []
    if already and not form.get("ack_triggered"):
        raise ValueError("already over the line in the latest report: " + "; ".join(already)
                         + " – tick «I know» to log the view anyway; it is then recorded as logged with a kill criterion triggered")
    today = today or datetime.now().strftime("%Y-%m-%d")
    kl = form.get("kill_level")
    if kl not in (None, ""):
        kl = float(kl)
        if form["rating"] == "BUY" and not kl < price:
            raise ValueError(f"for a BUY the kill level must be below the price {price:.2f}")
        if form["rating"] == "SELL" and not kl > price:
            raise ValueError(f"for a SELL the kill level must be above the price {price:.2f}")
    else:
        kl = None
    from osloquant.dashboard import sizing

    pos = {}
    cfg = sizing.config()
    if cfg and form["rating"] == "BUY":
        if kl is None:
            raise ValueError("a BUY needs a kill level: it is the stop the position size is measured against")
        raw = form.get("position_shares")
        groups = _groups()
        s = sizing.size(price, kl, cfg, code, group=groups.get(code), groups=groups)
        shares = s.shares if raw in (None, "") else int(float(raw))
        s, problems = sizing.check(shares, price, kl, cfg, code, group=groups.get(code), groups=groups)
        if problems:
            raise ValueError("; ".join(problems))
        pos = dict(position_shares=shares, position_value=round(shares * price, 2), loss_at_kill=round(shares * s.loss_per_share, 2),
                   sizing={"paper_capital": float(cfg["paper_capital"]), "max_loss": float(cfg["max_loss"]),
                           "max_position": cfg.get("max_position"), "binding": s.binding, "limits": s.limits, "round_trip_cost": sizing.COST})
    kill = [k.strip() for k in form["kill"] if k.strip()]
    from osloquant.dashboard import discipline as dsc

    anchor = dsc.anchor_check(dsc.previous_view(jg.read_log(), code.upper()), float(price), float(form["target"]))   # D46
    from osloquant.dashboard import baserate as bsr

    try:
        base_rate = bsr.row_field(bsr.for_code(code.upper()), form.get("base_rate_reason"))                          # D47
    except Exception:  # noqa: BLE001 – no store statements: the row is written without the check, and R07 counts it
        base_rate = None
    fields = dict(code=code, name=name, date=today, price=round(float(price), 4), rating=form["rating"], target=float(form["target"]),
                  horizon_months=int(form.get("horizon") or 12),
                  bear=form.get("bear"), base=form.get("base"), bull=form.get("bull"),
                  p_bear=form.get("p_bear"), p_base=form.get("p_base"), p_bull=form.get("p_bull"),
                  kill=kill, kill_level=kl, thesis=form["rationale"].strip(), price_date=price_date, price_source=price_source,
                  triggered_at_entry=already or None,
                  consensus_target=float(form["consensus_target"]) if form.get("consensus_target") not in (None, "") else None,
                  consensus_source=(form.get("consensus_source") or "").strip() or None,
                  saw_claude={"yes": True, "no": False}.get(form.get("saw_claude")) if form.get("claude_exists") else None,
                  checklist=[k for k in str(form.get("checklist") or "").split(",") if k] or None,
                  desk_run=_desk_run(form.get("desk_run")),
                  premortem=[x.strip() for x in form.get("premortem") or dsc.premortem_from_form(form) if x and x.strip()] or None,
                  probs_deliberate=True if form.get("probs_deliberate") else None,
                  anchor=anchor, anchor_reason=(form.get("anchor_reason") or "").strip() or None, base_rate=base_rate,
                  source="dashboard", **pos)
    row = jg.append("judgement", fields)
    book = sg.load_book()
    if code not in [e["code"] for e in book]:
        _append_book_entry(code, name or code, today)
    mark_moved(code, row["seq"], today)
    return row


def _desk_run(value) -> str | None:
    """The id of the desk run a view was opened from (D41): kept on the row so the debate log can be found from it;
    an id that is not a stored run is dropped rather than refused – the view is Oscar's whatever the desk said."""
    from osloquant.dashboard import desk

    v = str(value or "").strip()
    return v if v and desk.RUN_ID.match(v) and desk.load_run(v) is not None else None


def _groups() -> dict[str, str]:
    """Sector group per code from the store, empty when the store is not there (tests without prices)."""
    try:
        from osloquant.dashboard import market as mk

        snap = mk.snapshot()
        return {c: snap.group(c) for c in snap.names}
    except Exception:  # noqa: BLE001 – sizing must work without a store
        return {}


def triggered_now(code: str) -> list[str]:
    """Kill criteria the latest quarterly-report reading already marks as triggered (D22: a view should not be logged
    with a dead criterion unknowingly)."""
    from osloquant.dashboard import reports as rp

    s = rp.latest(code)
    if not s:
        return []
    out = []
    for k in s.get("kill", []):
        if k.get("status") == "triggered":
            now, thr = k.get("now"), k.get("threshold")
            val = f" ({now * 100:.1f} % vs {k.get('op', '')} {thr * 100:.1f} %)" if isinstance(now, (int, float)) and isinstance(thr, (int, float)) and abs(thr) < 5 else ""
            out.append(f"{k['criterion'][:70]}{val}, {s['title'][:40]}")
    return out


def _append_book_entry(code: str, name: str, today: str) -> None:
    """Add a company to researchbook.yaml by appending text, so nothing already there is rewritten."""
    p = sg.book_path()
    if not p.exists():
        p.write_text("# The research book: companies with a written case. Private – not in any repository.\nentries:\n", encoding="utf-8")
    entry = yaml.safe_dump([{"code": code, "name": name, "added": today, "events": [], "note": "added from the dashboard; the view is in judgements.jsonl"}],
                           sort_keys=False, allow_unicode=True)
    nl = "\n"
    lead = "" if p.read_text(encoding="utf-8").endswith(nl) else nl
    with p.open("a", encoding="utf-8", newline=nl) as f:
        f.write(lead + nl.join("  " + line if line else line for line in entry.splitlines()) + nl)
    sg.load_book()   # fails loudly if the append broke the file
