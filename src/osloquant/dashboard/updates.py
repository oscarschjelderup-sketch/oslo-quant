"""The update log (DECISIONS D48), after Tetlock: superforecasters update often and in small steps, and the record
says whether they did.

When new information arrives on a company with an open view – a quarterly report that has passed (from the report
reader, a downloaded report, a research-book event or the financial calendar, as D39 finds it) – the stock page asks:
*has your probability changed?* The answer is a row in the judgement log of kind ``update``: the view it refers to,
the trigger with its date and source, the three scenario probabilities after the news (the same three if nothing
changed) and, when unchanged, why. The target is not changed by an update – a new target is a new view.

Not answering is recorded too, without anyone writing anything: a trigger older than 14 days with no update after it
is *not updated*, derived from the dates every time the page is drawn and counted by the weekly review (D50). When a
view's horizon is reached, the Brier score of the last update is set beside the original's, so the log shows whether
updating made the forecast better.
"""

from __future__ import annotations

import html

import pandas as pd

from osloquant import judgements as jg

E = html.escape
UPDATE_DUE_DAYS = 14
REASON_MIN = 10


def updates(rows: list[dict], ref_seq: int | None = None) -> list[dict]:
    return [r for r in rows if r.get("kind") == "update" and (ref_seq is None or r.get("ref_seq") == ref_seq)]


def last_touch(rows: list[dict], view: dict) -> str:
    """The date the view was last looked at: its own date or its newest update."""
    us = updates(rows, view["seq"])
    return max([str(view["date"])[:10]] + [str(u["date"])[:10] for u in us])


def pending(rows: list[dict], cases, today: pd.Timestamp, cal_doc: dict | None = None, analyst: str = jg.DEFAULT_ANALYST) -> list[dict]:
    """Open views whose newest report is newer than the view and its last update: {code, view_seq, trigger, days,
    overdue}. ``overdue`` = older than 14 days – counted as not updated."""
    from osloquant.dashboard import afterreport as ar

    by_code = {c.code: c for c in cases}
    out = []
    for code, v in jg.latest_by_code(rows, analyst).items():
        rep = ar.newest_report(by_code.get(code), today, cal_doc, code=code)
        if not rep:
            continue
        touched = last_touch(rows, v)
        if rep["date"] <= touched:
            continue
        days = int((today - pd.Timestamp(rep["date"])).days)
        out.append({"code": code, "view_seq": v["seq"], "view": v, "trigger": rep, "days": days, "overdue": days > UPDATE_DUE_DAYS})
    return sorted(out, key=lambda x: -x["days"])


def form_problems(form: dict) -> list[str]:
    probs = [form.get(k) for k in ("p_bear", "p_base", "p_bull")]
    changed = form.get("changed")
    out = []
    if changed:
        if any(p in (None, "") for p in probs):
            out.append("give the three probabilities after the news")
        else:
            ps = [float(p) for p in probs]
            if any(not 0 <= p <= 1 for p in ps):
                out.append("probabilities are between 0 and 1")
            elif abs(sum(ps) - 1) > 0.011:
                out.append(f"the probabilities sum to {sum(ps):.2f}, not 1")
    elif len((form.get("reason") or "").strip()) < REASON_MIN:
        out.append("say in a sentence why the news does not change the probabilities (at least 10 characters)")
    return out


def write(code: str, form: dict, price: float, price_date: str, today: str, rows: list[dict] | None = None, cases=(), cal_doc=None) -> dict:
    """Append one ``update`` row for the open view on ``code``. Raises ValueError with the problems."""
    rows = jg.read_log() if rows is None else rows
    view = jg.latest_by_code(rows).get(code)
    if not view:
        raise ValueError(f"no open view on {code} to update")
    problems = form_problems(form)
    if problems:
        raise ValueError("; ".join(problems))
    trig = {"date": form.get("trigger_date"), "what": form.get("trigger_what"), "source": form.get("trigger_source")}
    if not trig["date"]:
        raise ValueError("an update needs the news it answers (trigger date)")
    changed = bool(form.get("changed"))
    probs = [float(form[k]) for k in ("p_bear", "p_base", "p_bull")] if changed else [view.get("p_bear"), view.get("p_base"), view.get("p_bull")]
    fields = dict(code=code, date=today, ref_seq=view["seq"], trigger=trig, changed=changed,
                  p_bear=probs[0], p_base=probs[1], p_bull=probs[2],
                  prior=[view.get("p_bear"), view.get("p_base"), view.get("p_bull")],
                  reason=(form.get("reason") or "").strip() or None, price=round(float(price), 4), price_date=price_date, source="dashboard")
    return jg.append("update", fields)


def brier(probs: list, hit: str) -> float | None:
    if any(p is None for p in probs) or hit not in ("bear", "base", "bull"):
        return None
    idx = ("bear", "base", "bull").index(hit)
    return float(sum((float(p) - (1.0 if i == idx else 0.0)) ** 2 for i, p in enumerate(probs)))


def scoring(rows: list[dict], table: pd.DataFrame, today: pd.Timestamp, cases=(), cal_doc=None) -> dict:
    """Per final view with updates: the original and the last update's Brier. Plus the live count of triggers
    answered, answered unchanged, and overdue (not updated)."""
    out = {"pairs": [], "answered": len(updates(rows)), "unchanged": sum(not u.get("changed") for u in updates(rows))}
    if len(table) and "scenario_hit" in table:
        for _, t in table[table["status"] == "final"].iterrows():
            us = updates(rows, int(t["seq"]))
            if not us or pd.isna(t.get("scenario_hit")):
                continue
            j = next(r for r in rows if r.get("seq") == int(t["seq"]))
            b0 = brier([j.get("p_bear"), j.get("p_base"), j.get("p_bull")], t["scenario_hit"])
            last = us[-1]
            b1 = brier([last.get("p_bear"), last.get("p_base"), last.get("p_bull")], t["scenario_hit"])
            out["pairs"].append({"code": t["code"], "seq": int(t["seq"]), "updates": len(us), "brier_view": b0, "brier_updated": b1})
    pend = pending(rows, cases, today, cal_doc)
    out["pending"] = pend
    out["overdue"] = [p for p in pend if p["overdue"]]
    return out


# ------------------------------------------------------------------------------------------------ html
def block_html(item: dict | None, rows: list[dict]) -> str:
    """The question on the stock page, when news has arrived since the view and its last update."""
    if not item:
        return ""
    v, t = item["view"], item["trigger"]
    us = updates(rows, v["seq"])
    cur = us[-1] if us else v
    pv = [cur.get("p_bear"), cur.get("p_base"), cur.get("p_bull")]
    pvs = " / ".join("–" if p is None else f"{float(p):.0%}" for p in pv)
    late = (f' <span class="k">{item["days"]} dager siden – teller som «ikke oppdatert» til du svarer.</span>' if item["overdue"] else
            f' {item["days"]} dager siden.')
    hidden = "".join(f'<input type="hidden" name="trigger_{k}" value="{E(str(t.get(k) or ""))}">' for k in ("date", "what", "source"))
    return (f'<div class="decide"><h2>Har sannsynligheten din endret seg?</h2><p><b>{E(t["what"])}</b> ({E(t["date"])}, {E(t["source"])}) kom etter '
            f'vurderingen din #{v["seq"]} av {E(str(v["date"]))[:10]}.{late} Nå: bear / base / bull {pvs}.</p>'
            f'<form class="judge" method="post" action="/stock/{E(item["code"])}/update">{hidden}'
            '<div class="row3"><div><label>Bear etter nyheten</label><input name="p_bear" inputmode="decimal"></div>'
            '<div><label>Base</label><input name="p_base" inputmode="decimal"></div><div><label>Bull</label><input name="p_bull" inputmode="decimal"></div></div>'
            '<label style="font-weight:600"><input type="checkbox" style="width:auto" name="changed" value="1"> Sannsynlighetene er endret (fyll inn de tre over)</label>'
            '<label>Hvis uendret: hvorfor endrer ikke nyheten noe?</label><input name="reason">'
            '<button class="go" type="submit">Logg oppdateringen</button></form>'
            '<div class="src">Skrives som en rad av typen «update» i vurderingsloggen (Tetlock: små, hyppige oppdateringer). Kursmålet endres ikke her – et nytt kursmål er en ny vurdering. '
            'Når horisonten er nådd, settes Brier for siste oppdatering ved siden av den opprinnelige.</div></div>')


def calibration_html(sc: dict) -> str:
    pairs = sc.get("pairs") or []
    rows = "".join(f'<tr><td>{E(p["code"])} #{p["seq"]}</td><td>{p["updates"]}</td><td>{_b(p["brier_view"])}</td><td>{_b(p["brier_updated"])}</td>'
                   f'<td>{"bedre" if (p["brier_updated"] or 9) < (p["brier_view"] or 9) else "ikke bedre"}</td></tr>' for p in pairs)
    over = ", ".join(f'{E(p["code"])} ({E(p["trigger"]["what"])}, {p["days"]} d)' for p in sc.get("overdue") or []) or "ingen"
    return ('<h2>Oppdateringer etter ny informasjon</h2><div class="card">'
            f'<p>{sc["answered"]} oppdateringer logget, {sc["unchanged"]} av dem «uendret». Ikke oppdatert (nyhet eldre enn {UPDATE_DUE_DAYS} dager uten svar): {over}.</p>'
            + (f'<table class="odds"><thead><tr><th>Vurdering</th><th>Oppdateringer</th><th>Brier, opprinnelig</th><th>Brier, siste oppdatering</th><th></th></tr></thead><tbody>{rows}</tbody></table>'
               if rows else '<div class="src">Ingen vurdering med oppdateringer har nådd horisonten ennå.</div>')
            + '<div class="src">Brier = kvadrert avstand mellom sannsynlighetene og scenarioet som skjedde (0 er perfekt, 2 er verst). Tetlock: de beste oppdaterer ofte og lite.</div></div>')


def _b(v) -> str:
    return "–" if v is None else f"{v:.3f}"
