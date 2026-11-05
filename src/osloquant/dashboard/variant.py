"""Variant perception and the catalyst (DECISIONS D55), after Marks (second-level thinking: different and better than
the consensus), Mauboussin and Callahan ("Who Is On the Other Side?": behavioural, analytical, informational or
technical – BAIT) and Klarman (a catalyst closes the gap between price and value, and its date is part of the margin
of safety).

A BUY or SELL asks for three short things: which kind of edge it is (one of the four), what you know or weigh that the
price does not (one sentence), and the catalyst – what should happen and by when, inside the horizon. They are stored
on the row (``variant``). When the catalyst's date has passed, the front page asks whether it happened; the answer is
a kill check or a new view, as for any other test of the case. The process score counts a BUY or SELL written after
5 Nov 2026 without them.
"""

from __future__ import annotations

import html

import pandas as pd

E = html.escape
SINCE = "2026-11-05"
KINDS = {"behavioural": "atferd (andre overreagerer eller ekstrapolerer)", "analytical": "analytisk (jeg vekter informasjonen bedre)",
         "informational": "informasjon (jeg har gjort arbeidet andre ikke har)", "technical": "teknisk (tvungne selgere eller kjøpere, flyt)"}
EDGE_MIN = 15


def parse(form: dict) -> dict:
    return {"kind": (form.get("variant_kind") or "").strip(), "edge": (form.get("variant_edge") or "").strip(),
            "catalyst": (form.get("catalyst") or "").strip(), "by": (form.get("catalyst_by") or "").strip()}


def problems(v: dict, rating: str | None, today: str, horizon_months: int = 12) -> list[str]:
    if rating not in ("BUY", "SELL"):
        return []
    out = []
    if v["kind"] not in KINDS:
        out.append("say which kind of edge this is (who is on the other side: behavioural, analytical, informational or technical)")
    if len(v["edge"]) < EDGE_MIN:
        out.append(f"say in one sentence what you know or weigh that the price does not (at least {EDGE_MIN} characters)")
    if not v["catalyst"] or not v["by"]:
        out.append("name the catalyst and the date it should have happened by")
    else:
        try:
            by = pd.Timestamp(v["by"])
        except ValueError:
            return out + ["the catalyst date must be a date (YYYY-MM-DD)"]
        t = pd.Timestamp(today)
        if not t < by <= t + pd.DateOffset(months=horizon_months):
            out.append("the catalyst date must lie after today and inside the horizon")
    return out


def row_field(v: dict, rating: str | None) -> dict | None:
    if rating not in ("BUY", "SELL") or not v.get("kind"):
        return None
    return {"kind": v["kind"], "edge": v["edge"], "catalyst": v["catalyst"], "by": v["by"]}


def due(cases, today: pd.Timestamp) -> list[dict]:
    """Open views whose catalyst date has passed with no judgement or kill check since: {code, name, catalyst, by, view_seq}."""
    out = []
    for c in cases:
        v = c.view or {}
        cat = v.get("variant") or {}
        if not cat.get("by"):
            continue
        by = pd.Timestamp(cat["by"])
        if by > today:
            continue
        if any(r["kind"] in ("judgement", "kill_check") and pd.Timestamp(str(r["date"])[:10]) >= by for r in c.history):
            continue
        out.append({"code": c.code, "name": c.name, "catalyst": cat["catalyst"], "by": cat["by"], "view_seq": v.get("seq"), "days": int((today - by).days)})
    return out


def box_html(f: dict) -> str:
    opts = "".join(f'<option value="{k}"{" selected" if f.get("variant_kind") == k else ""}>{E(v)}</option>' for k, v in KINDS.items())
    val = lambda k: E(str(f.get(k) or ""))  # noqa: E731
    return ('<div class="warn" style="margin-top:10px"><b>Variant og katalysator (påkrevd for BUY og SELL):</b> hvem er på andre siden, hva vet du som prisen ikke har med, '
            'og hva skal skje innen når?'
            f'<div class="row3"><div><label>Hvilken fordel</label><select name="variant_kind"><option value="">–</option>{opts}</select></div>'
            f'<div style="grid-column:span 2"><label>Hva vet eller vekter du som markedet ikke priser? (én setning)</label><input name="variant_edge" value="{val("variant_edge")}"></div></div>'
            f'<div class="row3"><div style="grid-column:span 2"><label>Katalysator</label><input name="catalyst" placeholder="f.eks. Q4-rapporten viser marginløft" value="{val("catalyst")}"></div>'
            f'<div><label>Innen (dato)</label><input name="catalyst_by" placeholder="2027-02-28" value="{val("catalyst_by")}"></div></div>'
            '<div class="src">Marks: annerledes og bedre enn konsensus. Mauboussin: hvem er på andre siden (BAIT). Klarman: katalysatoren lukker gapet – datoen er en del av sikkerhetsmarginen. '
            'Når datoen har passert, spør forsiden om den skjedde.</div></div>')
