"""The research book and the watchlist, as the dashboard reads and writes them. All of it is private: it lives in the
home directory (``~/osloquant-home``), never in the repository.

- ``researchbook.yaml`` holds what is *about* a company: name, events (report dates), the model files of its case and,
  for older entries, the view it was added with.
- ``judgements.jsonl`` (osloquant.judgements) holds every view as an append-only, hash-chained row. The current view
  of a company is its newest judgement; the yaml view is used only when the log has none for that code.
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
    history: list[dict] = field(default_factory=list)   # every judgement and kill check, oldest first


def _yaml_view(e: dict) -> dict | None:
    if not e.get("rating") or not e.get("target"):
        return None
    return {"date": str(e.get("valuation_date", "")), "price": e.get("price_at_valuation"), "rating": e["rating"],
            "target": e["target"], "bear": e.get("bear"), "base": e.get("base", e.get("dcf")), "bull": e.get("bull"),
            "p_bear": e.get("p_bear"), "p_base": e.get("p_base"), "p_bull": e.get("p_bull"), "kill": e.get("kill", []),
            "thesis": e.get("thesis")}


def cases() -> list[Case]:
    """Every company in the research book with its current view and full history."""
    book = sg.load_book()
    rows = jg.read_log()
    out = []
    codes = [e["code"] for e in book]
    for e in book:
        hist = [r for r in rows if r.get("code") == e["code"]]
        js = [r for r in hist if r["kind"] == "judgement"]
        view = js[-1] if js else _yaml_view(e)
        src = f"log #{js[-1]['seq']}" if js else "researchbook.yaml"
        kill = list((view or {}).get("kill") or e.get("kill", []))
        out.append(Case(e["code"], e.get("name", e["code"]), view, src, list(e.get("events", [])), kill, e.get("model"), hist))
    # judgements logged for codes that are not (yet) in the yaml book still count as cases
    for code in sorted({r["code"] for r in rows if r["kind"] == "judgement"} - set(codes)):
        hist = [r for r in rows if r.get("code") == code]
        js = [r for r in hist if r["kind"] == "judgement"]
        out.append(Case(code, js[-1].get("name") or code, js[-1], f"log #{js[-1]['seq']}", [], list(js[-1].get("kill") or []), None, hist))
    return out


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
    today = today or datetime.now().strftime("%Y-%m-%d")
    kill = [k.strip() for k in form["kill"] if k.strip()]
    fields = dict(code=code, name=name, date=today, price=round(float(price), 4), rating=form["rating"], target=float(form["target"]),
                  horizon_months=int(form.get("horizon") or 12),
                  bear=form.get("bear"), base=form.get("base"), bull=form.get("bull"),
                  p_bear=form.get("p_bear"), p_base=form.get("p_base"), p_bull=form.get("p_bull"),
                  kill=kill, thesis=form["rationale"].strip(), price_date=price_date, price_source=price_source,
                  source="dashboard")
    row = jg.append("judgement", fields)
    book = sg.load_book()
    if code not in [e["code"] for e in book]:
        _append_book_entry(code, name or code, today)
    mark_moved(code, row["seq"], today)
    return row


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
