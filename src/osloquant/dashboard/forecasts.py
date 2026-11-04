"""Quarterly forecasts with a quick answer (DECISIONS D52), after Tetlock: calibration needs many forecasts and fast
feedback, and two twelve-month views a month give neither – the first one is scored in October 2027.

Before a company's next report (from the financial calendar, the research book or the issuer's calendar on
NewsWeb, as the calendar page reads them) the stock page asks for one number: the quarter's revenue, EBITDA or EBIT,
as a middle estimate and an 80 % interval. The row is of kind ``forecast`` in the judgement log, written only before
the report date. When the report has been read – by the report reader (``reports/<CODE>/*.summary.json``, with the
company's spec) or the after-report loop's generic reading (``cases/afterreport/<CODE>.json``) – the forecast is
answered with the printed number of the same name: inside the interval or not, and the miss against the middle.
An 80 % interval should hold the answer about eight times in ten; the calibration page shows how often it does, with
the count, and calls fewer than ten answers too few to say anything.

Nothing is guessed: a forecast whose metric the reading does not hold stays unanswered and says so.
"""

from __future__ import annotations

import glob
import html
import json
from pathlib import Path

import pandas as pd

from osloquant import judgements as jg

E = html.escape
METRICS = {"revenue": "omsetning", "ebitda": "EBITDA", "ebit": "EBIT"}
INTERVAL = 0.8
HORIZON_DAYS = 60            # a report this far ahead or nearer can be forecast
ANSWER_DAYS = 120            # the reading must come within this many days of the forecast
MIN_ANSWERS = 10


def metrics_for(code: str) -> dict[str, str]:
    """The metrics a forecast may name: the generic three plus the keys the company's reader spec reads."""
    from osloquant.dashboard import reports as rp

    out = dict(METRICS)
    spec = (rp.specs() or {}).get(code) or {}
    for k in (spec.get("key") or {}):
        out.setdefault(k, k.replace("_", " "))
    return out


def upcoming(code: str, cases, today: pd.Timestamp) -> dict | None:
    """The company's next report within 60 days: {date, what, source}."""
    from osloquant.dashboard import calendar as cal

    for e in cal.events(cases, None, today=today, days=HORIZON_DAYS):
        if e.get("code") == code and e["kind"] in ("report", "case") and pd.Timestamp(e["date"]) > today:
            what = str(e.get("what") or "")
            if e["kind"] == "report" or any(w in what.lower() for w in ("report", "rapport", "result", "kvartal", "quarter")):
                return {"date": f"{pd.Timestamp(e['date']):%Y-%m-%d}", "what": what or "report", "source": e.get("source", "")}
    return None


def forecasts(rows: list[dict], code: str | None = None, analyst: str = jg.DEFAULT_ANALYST) -> list[dict]:
    return [r for r in rows if r.get("kind") == "forecast" and (code is None or r["code"] == code) and jg.analyst_of(r) == analyst]


def form_problems(form: dict, allowed: dict, report: dict | None, today: pd.Timestamp) -> list[str]:
    out = []
    if not report:
        out.append("no upcoming report within 60 days to forecast")
    elif pd.Timestamp(report["date"]) <= today:
        out.append("a forecast must be written before the report date")
    if form.get("metric") not in allowed:
        out.append(f"metric must be one of {', '.join(allowed)}")
    try:
        lo, mid, hi = (float(form[k]) for k in ("low", "mid", "high"))
    except (TypeError, ValueError, KeyError):
        return out + ["give the low end, the middle and the high end of the 80 % interval as numbers"]
    if not lo <= mid <= hi:
        out.append("low ≤ middle ≤ high")
    if lo == hi:
        out.append("an 80 % interval has a width – low and high cannot be the same")
    return out


def write(code: str, form: dict, report: dict | None, today: pd.Timestamp, rows: list[dict] | None = None) -> dict:
    rows = jg.read_log() if rows is None else rows
    allowed = metrics_for(code)
    problems = form_problems(form, allowed, report, today)
    if not problems and any(f["metric"] == form["metric"] and f["report"]["date"] == report["date"] for f in forecasts(rows, code)):
        problems.append(f"{form['metric']} for the report of {report['date']} is already forecast – one forecast per number")
    if problems:
        raise ValueError("; ".join(problems))
    return jg.append("forecast", dict(code=code, date=f"{today:%Y-%m-%d}", report=report, metric=form["metric"], label=allowed[form["metric"]],
                                      low=float(form["low"]), mid=float(form["mid"]), high=float(form["high"]), interval=INTERVAL,
                                      unit="NOKm (or the report's currency), the quarter as printed", source="dashboard"))


def readings(code: str) -> list[dict]:
    """Every reading of the company's reports: {date, figures: {key: value}, source}."""
    out = []
    for p in glob.glob(str(jg.home() / "reports" / code / "*.summary.json")):
        s = json.loads(Path(p).read_text(encoding="utf-8"))
        figs = {k: v.get("value") for k, v in (s.get("figures") or {}).items() if isinstance(v, dict) and v.get("value") is not None}
        out.append({"date": str(s.get("published", ""))[:10], "figures": figs, "source": f"report reader, {s.get('title', '')} ({s.get('url', '')})"})
    ar = jg.home() / "cases" / "afterreport" / f"{code}.json"
    if ar.exists():
        d = json.loads(ar.read_text(encoding="utf-8"))
        found = ((d.get("reader") or {}).get("found") or {})
        if found and (d.get("report") or {}).get("date"):
            out.append({"date": d["report"]["date"], "figures": dict(found), "source": f"after-report reading ({(d.get('reader') or {}).get('mode', '')}), {d['report'].get('title', '')}"})
    return sorted(out, key=lambda r: r["date"])


def answer(f: dict, reads: list[dict]) -> dict | None:
    """The first reading after the forecast (within 120 days) that prints the forecast's metric."""
    start = pd.Timestamp(f["date"])
    for r in reads:
        d = pd.Timestamp(r["date"])
        if start < d <= start + pd.Timedelta(days=ANSWER_DAYS) and r["figures"].get(f["metric"]) is not None:
            a = float(r["figures"][f["metric"]])
            return {"actual": a, "date": r["date"], "source": r["source"], "inside": f["low"] <= a <= f["high"],
                    "miss": a / f["mid"] - 1 if f["mid"] else None}
    return None


def scoring(rows: list[dict], analyst: str = jg.DEFAULT_ANALYST) -> dict:
    fs = forecasts(rows, analyst=analyst)
    cache: dict[str, list[dict]] = {}
    out = []
    for f in fs:
        reads = cache.setdefault(f["code"], readings(f["code"]))
        out.append(f | {"answer": answer(f, reads)})
    done = [x for x in out if x["answer"]]
    inside = sum(x["answer"]["inside"] for x in done)
    return {"rows": out, "n": len(out), "answered": len(done), "inside": inside, "coverage": inside / len(done) if done else None,
            "enough": len(done) >= MIN_ANSWERS}


# ------------------------------------------------------------------------------------------------ html
def block_html(code: str, report: dict | None, rows: list[dict]) -> str:
    if not report:
        return ""
    allowed = metrics_for(code)
    done = {f["metric"] for f in forecasts(rows, code) if f["report"]["date"] == report["date"]}
    left = {k: v for k, v in allowed.items() if k not in done}
    mine = "".join(f'<li>{E(f["label"])}: {f["low"]:g} – <b>{f["mid"]:g}</b> – {f["high"]:g} (logget {E(f["date"])})</li>'
                   for f in forecasts(rows, code) if f["report"]["date"] == report["date"])
    opts = "".join(f'<option value="{E(k)}">{E(v)}</option>' for k, v in left.items())
    hidden = "".join(f'<input type="hidden" name="report_{k}" value="{E(str(report.get(k) or ""))}">' for k in ("date", "what", "source"))
    form = (f'<form class="judge" method="post" action="/stock/{E(code)}/forecast">{hidden}<div class="row4"><div><label>Tall</label><select name="metric">{opts}</select></div>'
            '<div><label>Lav (10 %)</label><input name="low" inputmode="decimal"></div><div><label>Midt</label><input name="mid" inputmode="decimal"></div>'
            '<div><label>Høy (90 %)</label><input name="high" inputmode="decimal"></div></div><button class="go" type="submit">Logg prognosen</button></form>') if left else ""
    return (f'<h2>Prognose for neste rapport</h2><div class="card"><p><b>{E(report["what"])}</b> {E(report["date"])} ({E(report["source"])}). '
            'Skriv kvartalets tall som et 80 %-intervall før rapporten: rapportleseren gir fasiten, og kalibreringen viser hvor ofte tallet havner innenfor.</p>'
            + (f'<ul>{mine}</ul>' if mine else "") + form
            + '<div class="src">Tetlock: mange prognoser med rask fasit er det som gjør kalibreringen målbar – en 12-måneders vurdering gir ett svar i året. '
            'Enhet: kvartalet som rapporten trykker det (NOKm eller rapportens valuta). Skrives som en rad av typen «forecast» i vurderingsloggen.</div></div>')


def calibration_html(sc: dict) -> str:
    rows = "".join(f'<tr><td>{E(x["code"])}</td><td>{E(x["label"])}</td><td>{E(x["report"]["date"])}</td><td>{x["low"]:g} – {x["mid"]:g} – {x["high"]:g}</td>'
                   + (f'<td>{x["answer"]["actual"]:g}</td><td>{"innenfor" if x["answer"]["inside"] else "utenfor"}</td><td>{x["answer"]["miss"] * 100:+.1f} %</td>'
                      if x["answer"] else '<td colspan="3" class="empty">ikke avgjort ennå</td>') + '</tr>' for x in sc["rows"])
    cov = "–" if sc["coverage"] is None else f'{sc["coverage"] * 100:.0f} %'
    return ('<h2>Kvartalsprognoser (80 %-intervall)</h2><div class="card">'
            f'<p>{sc["n"]} logget, {sc["answered"]} avgjort, <b>{cov}</b> innenfor intervallet (et kalibrert 80 %-intervall holder fasiten omtrent åtte av ti ganger)'
            + ("" if sc["enough"] else f' – færre enn {MIN_ANSWERS} svar er for lite til å si noe') + '.</p>'
            + (f'<table class="odds"><thead><tr><th>Selskap</th><th>Tall</th><th>Rapport</th><th>Lav – midt – høy</th><th>Fasit</th><th></th><th>Bom mot midt</th></tr></thead><tbody>{rows}</tbody></table>' if rows else "")
            + '<div class="src">Fasit: rapportleserens tall med samme navn, eller etter-rapporten-lesingen (D39). Mange «utenfor» betyr for smale intervaller (Mauboussin: analytikernes '
            'prognoser spriker mindre enn utfallene).</div></div>')
