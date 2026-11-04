"""The quarterly error review (DECISIONS D49), after Dalio (pain + reflection = progress, an issue log), Duke (separate
the decision from the outcome) and Klein (the pre-mortem is checked afterwards).

Once a quarter every scored view of Oscar's is gone through, the largest misses first (the price against the target,
in absolute terms), with the same questions each time. The answers are one row of kind ``review`` per view and
quarter in the judgement log, so they are as permanent as the views. The page counts what the answers add up to:
how often the failure was among the pre-mortem's three reasons (foresight), how often the decisive information was
available at the time, how much is put down to luck, which biases recur, and the lessons in one list.

Nothing here scores or rewrites a view; the review is Oscar's reading of his own record, kept so the next one can be
compared with it.
"""

from __future__ import annotations

import html

import pandas as pd

from osloquant import judgements as jg
from osloquant.dashboard import discipline as dsc

E = html.escape
LESSON_MIN = 15
QUESTIONS = [
    ("premortem_hit", "Var det som skjedde blant pre-mortem-punktene dine?", ("1", "2", "3", "ingen av dem", "caset holdt")),
    ("info_available", "Fantes informasjonen som avgjorde utfallet da du tok beslutningen?", ("ja", "delvis", "nei")),
    ("cause", "Hva avgjorde mest – beslutningen eller flaks?", ("beslutningen", "flaks", "begge", "vet ikke ennå")),
    ("bias", "Kjenner du igjen en av disse?", ("ankring til eget kursmål", "bekreftelse (leste bare det som støttet caset)", "for sikker (for smalt bånd)",
                                             "for tidlig inn", "for sent ut", "fulgte ledelsens guiding", "ingen")),
]


def quarter(day: pd.Timestamp) -> str:
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def reviews(rows: list[dict], quarter_: str | None = None) -> list[dict]:
    return [r for r in rows if r.get("kind") == "review" and (quarter_ is None or r.get("quarter") == quarter_)]


def items(rows: list[dict], table: pd.DataFrame, today: pd.Timestamp, analyst: str = jg.DEFAULT_ANALYST) -> list[dict]:
    """Oscar's scored views, the largest miss against the target first, with whether this quarter's review is done."""
    q = quarter(today)
    done = {r["ref_seq"]: r for r in reviews(rows, q)}
    by_seq = {r["seq"]: r for r in jg.judgements(rows)}
    out = []
    if not len(table):
        return out
    for _, t in table.iterrows():
        j = by_seq.get(int(t["seq"]))
        if j is None or jg.analyst_of(j) != analyst or t.get("status") not in ("final", "provisional"):
            continue
        vt = None if pd.isna(t.get("vs_target")) else float(t["vs_target"])
        out.append({"seq": int(t["seq"]), "code": t["code"], "date": t["date"], "rating": t["rating"], "target": float(t["target"]), "price": float(t["price"]),
                    "price_now": None if pd.isna(t.get("price_now")) else float(t["price_now"]), "vs_target": vt,
                    "excess": None if pd.isna(t.get("excess_osebx")) else float(t["excess_osebx"]), "status": t["status"],
                    "premortem": j.get("premortem") or [], "process": dsc.process_score(j), "review": done.get(int(t["seq"])), "quarter": q})
    return sorted(out, key=lambda x: -(abs(x["vs_target"]) if x["vs_target"] is not None else -1))


def form_problems(form: dict) -> list[str]:
    out = [f"answer: {label}" for key, label, opts in QUESTIONS if form.get(key) not in opts]
    if len((form.get("lesson") or "").strip()) < LESSON_MIN:
        out.append(f"write what you will do differently next time (at least {LESSON_MIN} characters)")
    return out


def write(seq: int, form: dict, today: pd.Timestamp, rows: list[dict] | None = None) -> dict:
    rows = jg.read_log() if rows is None else rows
    j = next((r for r in jg.judgements(rows) if r["seq"] == seq), None)
    if j is None:
        raise ValueError(f"no view #{seq} in the log")
    q = quarter(today)
    if any(r.get("ref_seq") == seq for r in reviews(rows, q)):
        raise ValueError(f"view #{seq} is already reviewed in {q}; the next review is next quarter")
    problems = form_problems(form)
    if problems:
        raise ValueError("; ".join(problems))
    answers = {key: form[key] for key, _, _ in QUESTIONS} | {"lesson": form["lesson"].strip()}
    return jg.append("review", dict(code=j["code"], date=f"{today:%Y-%m-%d}", ref_seq=seq, quarter=q, answers=answers,
                                    vs_target=form.get("vs_target"), status=form.get("status"), source="dashboard"))


def summary(rows: list[dict]) -> dict:
    rs = reviews(rows)
    a = [r["answers"] for r in rs]
    failed = [x for x in a if x.get("premortem_hit") != "caset holdt"]
    foreseen = [x for x in failed if x.get("premortem_hit") in ("1", "2", "3")]
    biases: dict[str, int] = {}
    for x in a:
        if x.get("bias") and x["bias"] != "ingen":
            biases[x["bias"]] = biases.get(x["bias"], 0) + 1
    return {"n": len(rs), "failed": len(failed), "foreseen": len(foreseen),
            "foresight_rate": len(foreseen) / len(failed) if failed else None,
            "info_available": sum(x.get("info_available") == "ja" for x in a), "luck": sum(x.get("cause") == "flaks" for x in a),
            "biases": dict(sorted(biases.items(), key=lambda kv: -kv[1])), "lessons": [(r["code"], r["quarter"], r["answers"]["lesson"]) for r in rs]}


# ------------------------------------------------------------------------------------------------ page
def page_html(its: list[dict], summ: dict, today: pd.Timestamp) -> str:
    q = quarter(today)
    todo = [i for i in its if not i["review"]]
    blocks = []
    for i in its:
        pm = "".join(f"<li>{n + 1}. {E(x)}</li>" for n, x in enumerate(i["premortem"])) or "<li class=empty>ingen pre-mortem på raden (logget før D46)</li>"
        now = "–" if i["price_now"] is None else f'{i["price_now"]:.2f}'
        head = (f'<h3>{E(i["code"])} #{i["seq"]} – {E(i["rating"])} {i["target"]:g} fra {i["price"]:g} ({E(i["date"])}) · '
                f'kurs nå {now} · mot kursmål {_p(i["vs_target"])} · mot OSEBX {_p(i["excess"])} · {E(i["status"])}</h3>')
        proc = (f'<div class="src">Prosess da vurderingen ble skrevet: {_p(i["process"]["score"], False)} – mangler: '
                f'{E(", ".join(dsc.ITEM_LABEL.get(k, k) for k in i["process"]["missing"]) or "ingenting")}.</div>')
        if i["review"]:
            ans = i["review"]["answers"]
            body = "<ul class=kv>" + "".join(f"<li>{E(label)} <b>{E(str(ans.get(key)))}</b></li>" for key, label, _ in QUESTIONS) + f"<li>Lærdom: <b>{E(ans.get('lesson', ''))}</b></li></ul>"
        else:
            qs = "".join(f'<label>{E(label)}</label><select name="{key}"><option value="">–</option>' + "".join(f"<option>{E(o)}</option>" for o in opts) + "</select>"
                         for key, label, opts in QUESTIONS)
            body = (f'<form class="judge" method="post" action="/review/{i["seq"]}"><input type="hidden" name="vs_target" value="{"" if i["vs_target"] is None else i["vs_target"]}">'
                    f'<input type="hidden" name="status" value="{E(i["status"])}">{qs}<label>Hva gjør du annerledes neste gang?</label>'
                    f'<input name="lesson" minlength="{LESSON_MIN}"><button class="go" type="submit">Lagre gjennomgangen</button></form>')
        blocks.append(f'<div class="card">{head}<div class="grid2"><div><b>Pre-mortem da</b><ul>{pm}</ul>{proc}</div><div>{body}</div></div></div>')
    s = summ
    stats = (f'<p>{s["n"]} gjennomganger totalt. Av {s["failed"]} der caset ikke holdt, sto feilen i pre-mortem i {s["foreseen"]} '
             f'({_p(s["foresight_rate"], False)}). Informasjonen fantes da i {s["info_available"]}; «flaks» som viktigste årsak i {s["luck"]}. '
             + ("Gjentatte feil: " + "; ".join(f"{E(k)} ({v})" for k, v in s["biases"].items()) + "." if s["biases"] else "") + '</p>')
    lessons = "".join(f"<li>{E(c)} {E(qq)}: {E(t)}</li>" for c, qq, t in s["lessons"]) or "<li class=empty>ingen ennå</li>"
    return ('<h1>Feilgjennomgang</h1><div class="sub">Hvert kvartal: alle vurderinger med utfall, største avvik først, de samme spørsmålene hver gang. '
            f'Svarene lagres i vurderingsloggen og kan ikke endres.</div><div class="card"><p><b>{q}</b>: {len(its)} vurderinger med utfall, {len(todo)} ikke gjennomgått.</p>'
            f'{stats}<details><summary>Lærdommer så langt</summary><ul>{lessons}</ul></details>'
            '<div class="src">Dalio: smerte + refleksjon = fremgang. Duke: skill beslutningen fra utfallet. Klein: pre-mortem sjekkes etterpå. '
            'Foreløpige vurderinger (horisonten ikke nådd) er med, men merket – de er ikke bevis.</div></div>' + "".join(blocks))


def _p(v, sign=True) -> str:
    if v is None:
        return "–"
    return f"{v * 100:+.1f} %" if sign else f"{v * 100:.0f} %"
