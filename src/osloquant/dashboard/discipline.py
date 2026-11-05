"""Decision discipline on the judgement row (DECISIONS D46): what the best investors do before and after a call,
turned into fields that are checked when the view is written and counted when it is scored.

- **Pre-mortem** (Gary Klein; Annie Duke): before a view can be logged, three reasons it failed – "it is twelve months
  from now, the case failed, why?" – are written and stored on the row. The error review (D49) asks which of them
  happened, so foresight can be counted.
- **Anchoring check** (Kahneman/Tversky; Tetlock on updating): a new target on a company the analyst already has a view
  on is compared with the previous target and the price move since. A target that moved the same way as the price by at
  least half as much *follows the price*; one left within 2 % after a 15 % move is *sticky*. Either is stored on the row
  (``anchor``) and named – it is a question, not a block.
- **Process score** (Duke: decision quality is not the outcome): every row is scored on what it held when it was
  written – a pre-mortem, own probabilities (not the Toolkit's 25/50/25 default unless ticked as deliberate), a kill
  criterion with a number, the «Før du kjøper» checklist, a blind view where Claude had one, the desk's debate, no
  unexplained price-following target, and the base-rate check (D47). The score is the share of the items that apply.
  ``decision_grid`` crosses it with the outcome: deserved win, bad break, dumb luck, deserved loss.

Everything here reads the row and the scored table; nothing rewrites an earlier row.
"""

from __future__ import annotations

import html
import re

import pandas as pd

E = html.escape
PREMORTEM_N = 3
PREMORTEM_MIN_CHARS = 15
TEMPLATE_PROBS = (0.25, 0.50, 0.25)      # the Toolkit's default scenario probabilities (SCENARIO_ADJ "prob" row)
FOLLOW_MIN_MOVE = 0.05                   # a price move below 5 % is not something a target can follow
FOLLOW_SHARE = 0.5                       # the target moved the same way by at least half the price move
STICKY_MOVE = 0.15                       # a 15 % price move ...
STICKY_TP = 0.02                         # ... with the target left within 2 %
GOOD_PROCESS = 0.7                       # share of applicable process items for a "good decision"
CHECKLIST_KEYS = ("read_report", "knows_kill", "new_argument", "seen_implied")
ITEM_LABEL = {
    "premortem": "pre-mortem skrevet (3 grunner)",
    "own_probs": "egne sannsynligheter (ikke malens 25/50/25)",
    "kill_numeric": "kill-kriterium med et tall",
    "checklist": "sjekklisten i «Før du kjøper» krysset av",
    "blind": "blindt (før Claudes syn)",
    "debated": "kjørt gjennom desken (bjørnen hørt)",
    "not_anchored": "kursmålet fulgte ikke bare kursen",
    "base_rate": "estimatene innenfor base rate (eller begrunnet)",
    "variant": "variant og katalysator med dato (BUY/SELL)",
}


# ------------------------------------------------------------------------------------------------ pre-mortem
def premortem_from_form(form) -> list[str]:
    return [(form.get(f"premortem_{i}") or "").strip() for i in range(1, PREMORTEM_N + 1)]


def premortem_problems(items: list[str] | None) -> list[str]:
    items = [x.strip() for x in (items or []) if x and x.strip()]
    if len(items) < PREMORTEM_N:
        return [f"the pre-mortem needs {PREMORTEM_N} reasons: it is twelve months from now and the case failed – why? ({len(items)} written)"]
    short = [i + 1 for i, x in enumerate(items) if len(x) < PREMORTEM_MIN_CHARS]
    if short:
        return [f"pre-mortem reason {', '.join(map(str, short))} is too short to be checked later (at least {PREMORTEM_MIN_CHARS} characters)"]
    if len({x.lower() for x in items}) < len(items):
        return ["the three pre-mortem reasons must differ"]
    return []


# ------------------------------------------------------------------------------------------------ anchoring
def previous_view(rows: list[dict], code: str, analyst: str = "oscar", before_seq: int | None = None) -> dict | None:
    from osloquant import judgements as jg

    js = [r for r in jg.judgements(rows) if r["code"] == code and jg.analyst_of(r) == analyst and (before_seq is None or r["seq"] < before_seq)]
    return js[-1] if js else None


def anchor_check(prev: dict | None, price: float, target: float) -> dict | None:
    """The new target against the previous one and the price move since (None without a previous view)."""
    if not prev or not prev.get("price") or not prev.get("target"):
        return None
    px = price / float(prev["price"]) - 1
    tp = target / float(prev["target"]) - 1
    kind = None
    if abs(px) >= FOLLOW_MIN_MOVE and px * tp > 0 and abs(tp) >= FOLLOW_SHARE * abs(px):
        kind = "follows_price"
    elif abs(px) >= STICKY_MOVE and abs(tp) < STICKY_TP:
        kind = "sticky"
    return {"prev_seq": prev["seq"], "prev_date": prev["date"], "prev_target": float(prev["target"]), "prev_price": float(prev["price"]),
            "px_change": px, "tp_change": tp, "kind": kind}


def anchor_text(a: dict | None) -> str:
    if not a or not a.get("kind"):
        return ""
    if a["kind"] == "follows_price":
        return (f"the target moved {a['tp_change'] * 100:+.1f} % from {a['prev_target']:g} while the price moved {a['px_change'] * 100:+.1f} % "
                f"since the view of {a['prev_date']}: it follows the price – what changed in the case, not in the quote?")
    return (f"the price moved {a['px_change'] * 100:+.1f} % since the view of {a['prev_date']} and the target stayed at {a['prev_target']:g} "
            "(within 2 %): is it the case that has not changed, or the anchor?")


# ------------------------------------------------------------------------------------------------ process score
def process_items(row: dict) -> dict[str, bool | None]:
    """What the row held when it was written. None = the item does not apply to this row."""
    probs = [row.get(k) for k in ("p_bear", "p_base", "p_bull")]
    has_probs = all(p is not None for p in probs)
    template = has_probs and all(abs(float(p) - t) < 1e-9 for p, t in zip(probs, TEMPLATE_PROBS, strict=True))
    kills = row.get("kill") or []
    br = row.get("base_rate")
    a = row.get("anchor")
    return {
        "premortem": not premortem_problems(row.get("premortem")),
        "own_probs": bool(has_probs and (not template or row.get("probs_deliberate"))),
        "kill_numeric": any(re.search(r"\d", str(k)) for k in kills),
        "checklist": all(k in (row.get("checklist") or []) for k in CHECKLIST_KEYS),
        "blind": None if row.get("saw_claude") is None else row.get("saw_claude") is False,
        "debated": bool(row.get("desk_run")),
        "not_anchored": None if not a else (a.get("kind") is None or bool(row.get("anchor_reason"))),
        "base_rate": None if not br else (not br.get("flags") or bool(br.get("reason"))),
        "variant": (None if row.get("rating") not in ("BUY", "SELL") or str(row.get("date", ""))[:10] < "2026-11-05"
                    else bool((row.get("variant") or {}).get("by"))),
    }


def process_score(row: dict) -> dict:
    items = process_items(row)
    applies = {k: v for k, v in items.items() if v is not None}
    met = [k for k, v in applies.items() if v]
    score = len(met) / len(applies) if applies else None
    return {"items": items, "met": met, "missing": [k for k, v in applies.items() if not v], "score": score,
            "good": None if score is None else score >= GOOD_PROCESS}


GRID = {(True, True): "fortjent gevinst", (True, False): "uflaks", (False, True): "flaks", (False, False): "fortjent tap"}


def decision_grid(rows: list[dict], table: pd.DataFrame, analyst: str = "oscar") -> dict:
    """Process (at the time of the call) against outcome (direction against OSEBX), for scored calls of one analyst.
    Final calls make the grid; provisional ones are listed beside it and are not evidence (Duke: resulting)."""
    from osloquant import judgements as jg

    by_seq = {r["seq"]: r for r in jg.judgements(rows)}
    out = {"cells": {v: [] for v in GRID.values()}, "provisional": [], "unscored": [], "rows": []}
    if not len(table):
        return out
    for _, t in table.iterrows():
        r = by_seq.get(t["seq"])
        if r is None or jg.analyst_of(r) != analyst:
            continue
        ps = process_score(r)
        status = t.get("status")
        hit = t.get("direction_hit")
        entry = {"seq": int(t["seq"]), "code": t["code"], "date": t["date"], "rating": t["rating"], "score": ps["score"], "good": ps["good"],
                 "missing": ps["missing"], "status": status, "hit": None if pd.isna(hit) else bool(hit),
                 "excess": None if pd.isna(t.get("excess_osebx")) else float(t["excess_osebx"])}
        out["rows"].append(entry)
        if status not in ("final", "provisional") or entry["hit"] is None:
            out["unscored"].append(entry)
        elif status == "provisional":
            out["provisional"].append(entry | {"cell": GRID[(bool(ps["good"]), entry["hit"])]})
        else:
            out["cells"][GRID[(bool(ps["good"]), entry["hit"])]].append(entry)
    out["n_final"] = sum(len(v) for v in out["cells"].values())
    scores = [e["score"] for e in out["rows"] if e["score"] is not None]
    out["mean_score"] = sum(scores) / len(scores) if scores else None
    miss: dict[str, int] = {}
    for e in out["rows"]:
        for k in e["missing"]:
            miss[k] = miss.get(k, 0) + 1
    out["missing_counts"] = dict(sorted(miss.items(), key=lambda kv: -kv[1]))
    return out


# ------------------------------------------------------------------------------------------------ html
def premortem_box(f: dict) -> str:
    vals = f.get("premortem") or premortem_from_form(f)
    vals = list(vals) + [""] * (PREMORTEM_N - len(vals))
    inputs = "".join(f'<label>Grunn {i + 1}</label><input name="premortem_{i + 1}" required minlength="{PREMORTEM_MIN_CHARS}" '
                     f'placeholder="{E(["f.eks. prisøkningene stoppet ved 2 % fordi lavpriskjedene la seg under", "", ""][i])}" value="{E(vals[i])}">'
                     for i in range(PREMORTEM_N))
    return ('<div class="warn" style="margin-top:10px"><b>Pre-mortem (påkrevd):</b> det er 12 måneder frem, og caset feilet. Hvorfor? Tre ulike grunner. '
            f'De lagres på raden, og feilgjennomgangen spør senere hvilken av dem som skjedde.{inputs}</div>')


def probs_box(f: dict) -> str:
    ck = " checked" if f.get("probs_deliberate") else ""
    return ('<label style="font-weight:600"><input type="checkbox" style="width:auto" name="probs_deliberate" value="1"' + ck + '> '
            'Sannsynlighetene er mine, også om de er 25/50/25 (malens standard) – ellers teller de ikke som egne i prosessmålingen</label>')


def anchor_box(prev: dict | None, px: float, f: dict) -> str:
    """Before the target is typed: the previous view, the price move since, and the targets that would 'follow the price'."""
    if not prev:
        return ""
    move = px / float(prev["price"]) - 1
    lo = float(prev["target"]) * (1 + FOLLOW_SHARE * move)
    band = ""
    if abs(move) >= FOLLOW_MIN_MOVE:
        band = (f' Et nytt kursmål {"over" if move > 0 else "under"} {lo:.1f} følger kursen (flytter seg minst halvparten så mye samme vei) og blir merket.')
    if abs(move) >= STICKY_MOVE:
        band += f' Et kursmål innenfor 2 % av {float(prev["target"]):g} etter en slik bevegelse blir merket som «fast».'
    return (f'<div class="src" style="margin:8px 0"><b>Forrige syn</b> {E(prev["date"])}: {E(prev["rating"])} {float(prev["target"]):g} ved kurs {float(prev["price"]):g}. '
            f'Kursen er {move * 100:+.1f} % siden.{band} Er det caset som har endret seg, eller kursen? '
            f'<input name="anchor_reason" placeholder="hvis merket: hva i caset endret seg (valgfritt)" value="{E(str(f.get("anchor_reason") or ""))}" style="margin-top:4px"></div>')


def grid_html(g: dict) -> str:
    if not g.get("rows"):
        return ""
    cells = g["cells"]

    def cell(name, note):
        es = cells[name]
        items = ", ".join(f'{E(e["code"])} #{e["seq"]}' for e in es) or "–"
        return f'<td><b>{len(es)}</b> {E(name)}<div class="src">{note}</div><div class="src">{items}</div></td>'
    prov = ", ".join(f'{E(e["code"])} #{e["seq"]} ({E(e["cell"])} så langt)' for e in g["provisional"]) or "ingen"
    miss = "; ".join(f'{E(ITEM_LABEL.get(k, k))}: mangler i {n}' for k, n in g["missing_counts"].items()) or "ingenting mangler"
    def pc(v):
        return "–" if v is None else f"{v * 100:.0f} %"
    rows = "".join(f'<tr><td>{E(e["code"])} #{e["seq"]}</td><td>{E(e["date"])}</td><td>{E(e["rating"])}</td>'
                   f'<td>{pc(e["score"])}</td><td class="src">{E(", ".join(ITEM_LABEL.get(k, k) for k in e["missing"]) or "–")}</td>'
                   f'<td>{E(str(e["status"]))}</td><td>{"–" if e["hit"] is None else ("riktig" if e["hit"] else "feil")}</td></tr>' for e in g["rows"])
    return ('<h2>Beslutning mot utfall</h2><div class="card"><p>Prosessen måles på det raden inneholdt da vurderingen ble skrevet, ikke på hvordan det gikk '
            f'(Annie Duke: «resulting»). God prosess = minst {GOOD_PROCESS:.0%} av punktene som gjelder. Bare vurderinger med nådd horisont teller i rutenettet.</p>'
            '<table class="odds"><thead><tr><th></th><th>Godt utfall (retning riktig mot OSEBX)</th><th>Dårlig utfall</th></tr></thead><tbody>'
            f'<tr><th style="text-align:left">God prosess</th>{cell("fortjent gevinst", "gjenta")}{cell("uflaks", "ikke straff deg selv – sjekk pre-mortem")}</tr>'
            f'<tr><th style="text-align:left">Svak prosess</th>{cell("flaks", "ikke lær feil lekse")}{cell("fortjent tap", "prosessen var feilen")}</tr></tbody></table>'
            f'<div class="src">Foreløpige (ikke bevis): {prov}. Snitt prosesspoeng: {pc(g["mean_score"])}. '
            f'Hyppigst manglende: {miss}.</div>'
            '<details><summary>Per vurdering</summary><table class="odds"><thead><tr><th>Vurdering</th><th>Dato</th><th>Syn</th><th>Prosess</th>'
            f'<th>Manglet</th><th>Status</th><th>Retning</th></tr></thead><tbody>{rows}</tbody></table></details></div>')
