"""One kill list per case (D40): the model's list is the source, and the dashboard says where the other copies diverge.

Three places hold a case's kill criteria today:

1. **the model** – `KILL` (workbook rows with thresholds) and `KILL_TEXT` (criteria the rows cannot carry) in the
   Toolkit's data module, exported with every report as ``estimates_<date>.json`` → ``kill`` (model, text, source);
2. **the view** – the sentences on the judgement row (Oscar's current view; Claude's beside it) or in researchbook.yaml;
3. **the reader** – the rules in ``reports.yaml`` (``kill: [{criterion, metric, op, value}]``) that mark a criterion
   triggered / nearer / intact after each report.

Nothing here rewrites any of them (the log is append-only, the yaml is Oscar's). What it does is compare: a model
criterion with no sentence in the view, a view sentence with no model criterion behind it, a reader rule whose index
points past the view's list or whose threshold differs from the model's, a model criterion no reader rule checks. The
matching is by the numbers (threshold and the figures in the sentence) and by the words of the label, and it says
when it could not match rather than guessing. The issues go to the data-health page, the stock page and
``oq book check``.
"""

from __future__ import annotations

import re

#: workbook row key -> the reader's derived metric that measures the same thing (where one exists)
ROW_TO_METRIC = {"ebit_adj_m": "ebit_pre16_margin_ltm", "ebitda_m": "ebitda_margin_ltm", "g_pxc": "arpm_yoy", "pers_pct": "personnel_pct_ltm"}
_STOP = {"the", "a", "an", "of", "in", "and", "or", "for", "to", "below", "above", "per", "any", "two", "consecutive", "quarter", "quarters",
         "year", "group", "reported", "pre", "ifrs", "adj", "margin", "growth", "ratio"}


def _nums(text: str) -> set[float]:
    out = set()
    for m in re.finditer(r"(-?\d+(?:[.,]\d+)?)\s?(%|x)?", text or ""):
        v = float(m.group(1).replace(",", "."))
        out.add(round(v / 100, 4) if m.group(2) == "%" else round(v, 4))
    return out


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zæøå]+", (text or "").lower()) if len(w) > 2 and w not in _STOP}


def matches(model: dict, sentence: str) -> bool:
    """A view sentence states the model criterion when it carries the threshold as a number and shares a word of the
    label (so "EBIT adj. margin below 3 %" meets "EBIT adj. margin (pre-IFRS 16) below 3.0 %"), or, for a text
    criterion, when it is the same sentence up to punctuation."""
    if model.get("row") is None:                      # KILL_TEXT: compare the sentences
        a, b = re.sub(r"\W+", " ", model["text"]).strip().lower(), re.sub(r"\W+", " ", sentence).strip().lower()
        return a == b or a[:60] == b[:60]
    th = model.get("threshold")
    nums = _nums(sentence)
    hit = any(abs(n - round(th, 4)) < 1e-6 or (model.get("fmt") == "pct" and abs(n * 100 - th) < 1e-6) for n in nums) if th is not None else False
    return hit and bool(_words(model.get("label", "")) & _words(sentence))


def compare(model: dict | None, view_kill: list[str] | None, reader_rules: list[dict] | None, claude_kill: list[str] | None = None) -> dict:
    """{"issues": [...], "model_n", "view_n", "reader_n", "unmatched_model", "unmatched_view", "unchecked"}. With no model
    list (no report published) the model side is simply absent and only the reader-vs-view index check runs."""
    issues: list[str] = []
    mrows = list((model or {}).get("model") or []) + [{"text": t, "row": None, "label": t} for t in (model or {}).get("text") or []]
    view = [str(k) for k in (view_kill or []) if str(k).strip()]
    rules = list(reader_rules or [])
    unmatched_model = [m["text"] for m in mrows if not any(matches(m, s) for s in view)] if view else [m["text"] for m in mrows]
    unmatched_view = [s for s in view if not any(matches(m, s) for m in mrows)] if mrows else []
    if mrows and view:
        if len(mrows) != len(view):
            issues.append(f"modellen har {len(mrows)} kill-kriterier, synet {len(view)}")
        for t in unmatched_model:
            issues.append(f"modellens kriterium står ikke i synet: «{t[:70]}»")
        for s in unmatched_view:
            issues.append(f"synets kriterium har ingen modellinje bak seg: «{s[:70]}»")
    elif mrows and not view:
        issues.append(f"modellen har {len(mrows)} kill-kriterier, ingen vurdering er logget")
    dangling = [r for r in rules if isinstance(r.get("criterion"), int) and r["criterion"] >= len(view)]
    for r in dangling:
        issues.append(f"leserregelen for {r.get('metric')} peker på kriterium {r['criterion']}, synet har {len(view)}")
    unchecked = []
    for m in mrows:
        if m.get("row") is None:
            continue
        metric = ROW_TO_METRIC.get(m["row"])
        rule = next((r for r in rules if r.get("row") == m["row"] or (metric and r.get("metric") == metric)), None)
        if rule is None:
            unchecked.append(m["text"])
        elif m.get("threshold") is not None and rule.get("value") is not None and abs(float(rule["value"]) - float(m["threshold"])) > 1e-9:
            issues.append(f"leserregelen for {rule.get('metric')} bruker {rule['value']}, modellen {m['threshold']} ({m['label']})")
    if claude_kill is not None and mrows:
        cl = [str(k) for k in claude_kill if str(k).strip()]
        shared = sum(any(matches(m, s) for s in cl) for m in mrows)
        if cl and shared == 0:
            issues.append("Claudes kill-liste deler ingen kriterier med modellens (to analytikere, to lister – ikke feil, men verdt å vite)")
    return {"issues": issues, "model_n": len(mrows), "view_n": len(view), "reader_n": len(rules), "unmatched_model": unmatched_model,
            "unmatched_view": unmatched_view, "unchecked": unchecked, "source": (model or {}).get("source")}


def for_case(c) -> dict | None:
    """The comparison for a research-book case from the files: the newest published estimates, the view, reports.yaml."""
    from osloquant.dashboard import reportpdf as rpdf
    from osloquant.dashboard import reports as rp

    if c is None:
        return None
    ent = rpdf.latest(c.code)
    model = ((ent or {}).get("estimates") or {}).get("kill")
    rules = (rp.specs().get(c.code) or {}).get("kill") or []
    if not model and not rules:
        return None
    return compare(model, list(c.kill), rules, list((c.claude_view or {}).get("kill") or []) if c.claude_view else None)


def reader_stub(model: dict | None, view_kill: list[str]) -> str:
    """Reader rules for reports.yaml drafted from the model's list: the criterion index found by matching the view's
    sentence, the metric from ROW_TO_METRIC where one exists, otherwise TODO. Printed, never written."""
    lines = ["  kill:"]
    for m in (model or {}).get("model") or []:
        idx = next((i for i, s in enumerate(view_kill) if matches(m, s)), None)
        metric = ROW_TO_METRIC.get(m["row"], f"TODO (model row {m['row']})")
        op = "<" if m["op"] == "below" else ">"
        lines.append(f"    - {{criterion: {idx if idx is not None else 'TODO'}, metric: {metric}, op: '{op}', value: {m['threshold']}, row: {m['row']}}}   # {m['label']}")
    for t in (model or {}).get("text") or []:
        lines.append(f"    # not machine-checkable – read the report: {t}")
    return "\n".join(lines)


def block_html(res: dict | None) -> str:
    from osloquant.dashboard.render import E

    if not res:
        return ""
    if not res["issues"]:
        body = f'<span class="chip buy">én liste</span> modell {res["model_n"]} · syn {res["view_n"]} · leserregler {res["reader_n"]}'
    else:
        body = '<span class="chip risk">spriker</span> ' + " · ".join(E(i) for i in res["issues"])
    unchecked = (f'<div class="src">Ikke maskinsjekket av rapportleseren: {E("; ".join(res["unchecked"]))}</div>' if res.get("unchecked") else "")
    return (f'<div class="sub" style="margin-top:6px"><b>Kill-listen mot modellen:</b> {body}</div>{unchecked}'
            + (f'<div class="src">Modellens liste: {E(str(res.get("source") or ""))}. Rettes i data-modulen (Toolkit) og logges på nytt som vurdering; ingen fil skrives om her (D40).</div>' if res.get("source") else ""))
