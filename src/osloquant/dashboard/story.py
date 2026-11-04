"""Narrative against numbers (DECISIONS D53), after Damodaran (*Narrative and Numbers*, 2017): a valuation is a story
told in numbers, and the two must say the same thing.

For a full case – a company with a published report and its estimates – the judgement form asks for the story in one
sentence and the three numbers the story needs to be true: revenue growth a year over the first three estimate
years, the EBITDA margin in the third year, and EPS in the third year. Beside each it shows what the model says (the
report's ``estimates_*.json``). A story number that differs from the model's by more than one percentage point (growth,
margin) or 10 % (EPS) is flagged: either the story is bigger than the model or the model has drifted from the story,
and the form says which. The sentence, the three numbers, the model's three and the flags are stored on the row
(``story``). Without a published report there is no model to hold the story against, and the fields are not asked.
"""

from __future__ import annotations

import glob
import html
import json
from pathlib import Path

E = html.escape
YEARS = 3
SENTENCE_MIN = 20
NUMBERS = [("rev_cagr", "omsetningsvekst per år", "pp", 0.01), ("ebitda_m", "EBITDA-margin", "pp", 0.01), ("eps", "EPS", "rel", 0.10)]


def model_numbers(est: dict | None) -> dict | None:
    if not est:
        return None
    yrs, rows = est.get("years") or [], est.get("rows") or {}
    rev, ebitda, eps = rows.get("rev") or [], rows.get("ebitda") or [], rows.get("eps") or []
    if len(yrs) <= YEARS or len(rev) <= YEARS or not rev[0] or not rev[YEARS]:
        return None
    out = {"from": yrs[0], "year": yrs[YEARS], "rev_cagr": (rev[YEARS] / rev[0]) ** (1 / YEARS) - 1}
    out["ebitda_m"] = ebitda[YEARS] / rev[YEARS] if len(ebitda) > YEARS and ebitda[YEARS] is not None else None
    out["eps"] = eps[YEARS] if len(eps) > YEARS else None
    return out


def for_code(code: str) -> dict | None:
    from osloquant.dashboard import reportpdf as rpdf

    files = sorted(glob.glob(str(rpdf.folder(code) / "estimates_*.json")))
    if not files:
        return None
    m = model_numbers(json.loads(Path(files[-1]).read_text(encoding="utf-8")))
    return m | {"estimates": Path(files[-1]).name} if m else None


def parse(form: dict) -> dict:
    """The story from the form: the sentence and the three numbers (percent typed as percent; EPS in NOK)."""
    def num(k, pct):
        v = (form.get(k) or "").strip().replace(",", ".").replace("%", "")
        if not v:
            return None
        return float(v) / 100 if pct else float(v)
    return {"sentence": (form.get("story") or "").strip(), "rev_cagr": num("story_rev_cagr", True), "ebitda_m": num("story_ebitda_m", True),
            "eps": num("story_eps", False)}


def problems(story: dict, model: dict | None) -> list[str]:
    if not model:
        return []
    out = []
    if len(story.get("sentence") or "") < SENTENCE_MIN:
        out.append(f"a full case needs its story in one sentence (at least {SENTENCE_MIN} characters) – Damodaran: the numbers must tell the same story")
    missing = [label for key, label, _, _ in NUMBERS if story.get(key) is None and model.get(key) is not None]
    if missing:
        out.append("give the numbers the story needs: " + ", ".join(missing))
    return out


def flags(story: dict, model: dict) -> list[str]:
    out = []
    for key, label, kind, tol in NUMBERS:
        s, m = story.get(key), model.get(key)
        if s is None or m is None:
            continue
        gap = s - m if kind == "pp" else (s / m - 1 if m else None)
        if gap is not None and abs(gap) > tol:
            word = "bigger than the model" if gap > 0 else "smaller than the model"
            out.append(f"{label} {model['year']}: the story needs {_f(key, s)}, the model has {_f(key, m)} – the story is {word}")
    return out


def row_field(story: dict, model: dict | None) -> dict | None:
    if not model or not story.get("sentence"):
        return None
    return {"sentence": story["sentence"], "numbers": {k: story.get(k) for k, *_ in NUMBERS},
            "model": {k: model.get(k) for k, *_ in NUMBERS} | {"year": model["year"], "estimates": model.get("estimates")}, "flags": flags(story, model)}


def _f(key, v) -> str:
    return f"{v:.2f}" if key == "eps" else f"{v * 100:.1f} %"


def box_html(model: dict | None, f: dict) -> str:
    if not model:
        return ""
    val = lambda k: E(str(f.get(k) or ""))  # noqa: E731
    rows = "".join(f'<div><label>{E(label)} {model["year"] if key != "rev_cagr" else str(model["from"]) + "–" + str(model["year"])} – historien krever'
                   f'{" (%)" if key != "eps" else " (NOK)"}</label><input name="story_{key}" inputmode="decimal" value="{val("story_" + key)}">'
                   f'<div class="src">Modellen: {_f(key, model[key]) if model.get(key) is not None else "–"}</div></div>' for key, label, *_ in NUMBERS)
    return ('<div class="warn" style="margin-top:10px"><b>Fortelling mot tall (Damodaran):</b> historien i én setning, og de tre tallene den trenger. '
            'Avvik fra modellen på mer enn 1 pp (vekst, margin) eller 10 % (EPS) flagges på raden.'
            f'<label>Historien i én setning (påkrevd for full case)</label><input name="story" minlength="{SENTENCE_MIN}" value="{val("story")}">'
            f'<div class="row3">{rows}</div><div class="src">Modellens tall fra {E(str(model.get("estimates")))}. Estimater (EST).</div></div>')


def stock_html(view: dict | None) -> str:
    st = (view or {}).get("story")
    if not st:
        return ""
    fl = "".join(f"<li>{E(x)}</li>" for x in st.get("flags") or [])
    nums = " · ".join(f'{E(label)}: historien {_f(key, st["numbers"][key]) if st["numbers"].get(key) is not None else "–"} / modellen '
                      f'{_f(key, st["model"][key]) if st["model"].get(key) is not None else "–"}' for key, label, *_ in NUMBERS)
    return (f'<h2>Fortelling mot tall</h2><div class="card"><p><b>«{E(st["sentence"])}»</b></p><div class="src">{nums} ({st["model"].get("year")}).</div>'
            + (f'<div class="warn"><b>Historien og modellen sier ikke det samme:</b><ul>{fl}</ul></div>' if fl else '<div class="ok">Historien og modellens tall stemmer.</div>')
            + '</div>')
