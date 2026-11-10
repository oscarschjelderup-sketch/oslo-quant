"""After the report (D39): when a covered company has reported, the numbers behind the view are refreshed, the report
is read, and the view is queued for a new judgement – for every covered company, not only the ones with a hand-written
reader spec.

What "the newest report" is, with no network: the reader's newest summary (``reports/<CODE>/*.summary.json``), a
report downloaded by this loop (``reports/<CODE>/<id>.json`` from NewsWeb), a research-book event with report words
that has passed, or a passed report date from the issuer's financial calendar on NewsWeb (the calendar feed). The
newest of these wins and names its source.

``oq case after-report`` (the only part that touches the network) does, per company:

1. re-records the statements from Yahoo and rebuilds the light case, keeping the figures before and after so the
   stock page can say what changed (price, LTM revenue / EBIT / net income, EV/EBIT, P/E, what the price pays for);
2. finds the newest quarterly report on NewsWeb and downloads it; with a spec in ``reports.yaml`` it runs the reader
   (kill criteria marked), without one it runs the reader's dry run with a generic spec and writes the suggested
   spec to ``cases/specs/<CODE>.suggested.yaml`` – so the next quarter can be machine-read;
3. writes ``cases/afterreport/<CODE>.json``: the report, before/after, the reader's result or the dry run.

The queue (``due``) is derived, not stored: a company is in it when its newest report is newer than its light case,
or newer than the view of an analyst who has one. Oscar's items keep going to the front page through the existing
post-report rule (D29); Claude's are listed on the coverage page and never nag Oscar (D31).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yaml

from osloquant import judgements as jg
from osloquant.dashboard.dates import dato, stempel

AR_DIR = "afterreport"
SPEC_DIR = "specs"
REPORT_WORDS = ("report", "rapport", "results", "resultat", "q1", "q2", "q3", "q4", "quarter", "kvartal", "interim", "half-year", "halvår")
#: a first spec for a company without one: labels most Oslo issuers print in the key-figure table and the income statement
GENERIC_SPEC = {"key": {"revenue": r"(?:Total operating income|Operating income|Total operating revenues?|Operating revenues?|Total revenues?|Revenues?)",
                        "ebitda": r"EBITDA", "ebit": r"(?:EBIT|Operating profit(?: \(loss\))?)", "net_debt": r"Net[- ]interest[- ]bearing debt(?: \(NIBD\))?|Net debt"},
                "pl": {"revenue": r"(?:Total operating income|Operating income|Total operating revenues?|Operating revenues?|Total revenues?|Revenues?)",
                       "ebit": r"(?:EBIT|Operating profit(?: \(loss\))?)"}}
DIFF_FIELDS = (("price", ("price", "value")), ("revenue", ("profit", "revenue", "value")), ("ebit", ("profit", "ebit", "value")),
               ("net_income", ("profit", "net_income", "value")), ("ev_ebit", ("multiples", "ev_ebit")), ("pe", ("multiples", "pe")),
               ("implied_g", ("reverse", "implied_g")), ("ev_vs_no_growth", ("reverse", "ev_vs_no_growth")), ("quarters_through", ("quarters_through",)))


# ------------------------------------------------------------------------------------------------ files
def ar_dir() -> Path:
    return jg.home() / "cases" / AR_DIR


def path(code: str) -> Path:
    return ar_dir() / f"{code.upper()}.json"


def load(code: str) -> dict | None:
    p = path(code)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def spec_path(code: str) -> Path:
    return jg.home() / "cases" / SPEC_DIR / f"{code.upper()}.suggested.yaml"


# ------------------------------------------------------------------------------------------------ the newest report
def _downloaded(code: str) -> list[tuple[pd.Timestamp, str, str]]:
    """Reports this loop or the reader downloaded from NewsWeb: (published, title, source)."""
    d = jg.home() / "reports" / code
    out = []
    for p in d.glob("*.json") if d.exists() else []:
        if p.name.endswith(".summary.json"):
            continue
        try:
            msg = json.loads(p.read_text(encoding="utf-8"))["data"]["message"]
        except (ValueError, KeyError, TypeError):
            continue
        if msg.get("publishedTime") and msg.get("title"):
            out.append((pd.Timestamp(str(msg["publishedTime"])[:10]), str(msg["title"]), f"NewsWeb message {p.stem}"))
    return out


def newest_report(c, today: pd.Timestamp, cal_doc: dict | None = None, code: str | None = None) -> dict | None:
    """The newest report of a company that has passed: {date, what, source}. ``c`` is a book Case or None (then
    ``code`` names the company). No network."""
    from osloquant.dashboard import reports as rp

    code = (c.code if c else code).upper()
    found: list[tuple[pd.Timestamp, str, str]] = []
    s = rp.latest(code)
    if s:
        found.append((pd.Timestamp(s["published"][:10]), f"Q{s['quarter']} {s['year']} report", "report reader"))
    found += _downloaded(code)
    for ev in (c.events if c else []):
        d = pd.Timestamp(ev["date"])
        if d <= today and any(w in str(ev.get("what", "")).lower() for w in REPORT_WORDS):
            found.append((d, str(ev["what"]), "research book"))
    for ev in ((cal_doc or {}).get("companies") or {}).get(code, {}).get("events", []):
        d = pd.Timestamp(ev["date"])
        if d <= today and re.search(r"(?i)report|rapport|result", str(ev.get("what", ""))):
            found.append((d, str(ev["what"]), "financial calendar on NewsWeb"))
    if not found:
        return None
    d, what, src = max(found, key=lambda x: x[0])
    return {"date": f"{d:%Y-%m-%d}", "what": what, "source": src}


def _view_date(v: dict | None) -> str | None:
    return str(v.get("date", ""))[:10] if v and v.get("date") else None


def due(cases, universe: list[dict], today: pd.Timestamp, cal_doc: dict | None = None) -> list[dict]:
    """Companies at level full or light whose newest report is newer than their light case or than an analyst's
    view: {code, name, level, report, lightcase_built, lightcase_stale, owes: [analysts], ran} – the loop's queue."""
    by_code = {c.code: c for c in cases}
    out = []
    for r in universe:
        if r["level"] not in ("full", "light"):
            continue
        c = by_code.get(r["code"])
        rep = newest_report(c, today, cal_doc, code=r["code"])
        if not rep:
            continue
        owes = []
        for who, v in (("oscar", c.view if c else None), ("claude", c.claude_view if c else None)):
            d = _view_date(v)
            if d and d < rep["date"]:
                owes.append(who)
        built = r.get("lightcase_built")
        stale = bool(built and built < rep["date"])
        log = load(r["code"])
        ran = log["ran_at"][:10] if log and log.get("report", {}).get("date") == rep["date"] else None
        if stale or owes:
            out.append({"code": r["code"], "name": r["name"], "level": r["level"], "report": rep, "lightcase_built": built,
                        "lightcase_stale": stale, "owes": owes, "ran": ran, "days": (today - pd.Timestamp(rep["date"])).days})
    return sorted(out, key=lambda x: (-len(x["owes"]), x["days"], x["code"]))


# ------------------------------------------------------------------------------------------------ before / after
def _get(d: dict | None, keys: tuple) -> object:
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def snapshot(lc: dict | None) -> dict:
    return {name: _get(lc, keys) for name, keys in DIFF_FIELDS}


def diff(before: dict | None, after: dict | None) -> dict:
    """Field by field: before, after and the change (relative for amounts and multiples, in points for the implied
    growth and the EV gap, text for the quarter the statements reach)."""
    b, a = snapshot(before), snapshot(after)
    out = {}
    for name, _ in DIFF_FIELDS:
        x, y = b.get(name), a.get(name)
        if name == "quarters_through":
            out[name] = {"before": x, "after": y, "change": None if x == y else f"{x} → {y}"}
        elif name in ("implied_g", "ev_vs_no_growth"):
            out[name] = {"before": x, "after": y, "change": None if None in (x, y) else y - x, "unit": "pp"}
        else:
            out[name] = {"before": x, "after": y, "change": None if None in (x, y) or not x else y / x - 1, "unit": "rel"}
    return out


# ------------------------------------------------------------------------------------------------ the loop
def _write_suggested_spec(code: str, dry: dict, title: str) -> Path:
    p = spec_path(code)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Suggested reader spec for {code}, from a dry run of the generic spec on «{title}». Finish it and move it to",
             "# ~/osloquant-home/reports.yaml under the company's code; kill rules refer to the case's kill list by index.",
             f"{code}:", "  key:"]
    for k, lab in GENERIC_SPEC["key"].items():
        f = dry["found"].get(k)
        if f:
            lines.append(f"    {k}: {json.dumps(lab)}   # found p.{f['page']}: {f['value']} ({f['checked']})")
        else:
            lines.append(f"    # {k}: {json.dumps(lab)}   # not found; candidates:")
            lines += [f"    #   {c}" for c in dry["candidates"].get(k, [])[:4]]
    lines.append("  pl:")
    for k, lab in GENERIC_SPEC["pl"].items():
        f = dry["found"].get(f"pl_{k}")
        lines.append(f"    {k}: {json.dumps(lab)}" + (f"   # found p.{f['page']}" if f else "   # not found under the income-statement header"))
    lines.append(f"  # income-statement header seen: {dry.get('income_statement_header') or 'none'}")
    lines.append("  kill: []   # {criterion: <index into the kill list>, metric: <derived metric>, op: '<' or '>', value: ...}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def run_one(code: str, c, snap, refresh: bool = True, days: int = 120, today: pd.Timestamp | None = None) -> dict:
    """The loop for one company. Network: Yahoo statements (with ``refresh``), NewsWeb for the report."""
    from osloquant.dashboard import lightcase as lcm
    from osloquant.dashboard import reports as rp

    code = code.upper()
    today = today or pd.Timestamp.now().normalize()
    log: dict = {"code": code, "ran_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "refresh": refresh, "steps": []}
    before = lcm.load(code)
    # 1. statements and the light case
    try:
        if refresh:
            from osloquant.domain import BalanceSheet, CashFlowStatement, IncomeStatement

            for schema in (IncomeStatement, BalanceSheet, CashFlowStatement):
                schema.record_data(provider="yahoo", codes=[code], force_update=True, sleeping_time=0.8)
        after = lcm.build(code, snap=snap)
        log["lightcase"] = {"before": snapshot(before), "after": snapshot(after), "diff": diff(before, after), "warnings": after.get("warnings", [])}
        log["steps"].append("light case rebuilt" + (" after re-recording the statements" if refresh else ""))
    except Exception as e:  # noqa: BLE001 – the loop reports, it does not stop the other companies
        log["lightcase"] = {"before": snapshot(before), "after": None, "error": str(e)}
        log["steps"].append(f"light case not rebuilt: {e}")
    # 2. the report
    rep = None
    try:
        msgs = rp.find_reports(code, (today - pd.Timedelta(days=days)).date(), today.date())
        if msgs:
            m = msgs[-1]
            pdf, msg = rp.download(code, m["messageId"])
            rep = {"message_id": m["messageId"], "title": msg["title"], "date": str(msg["publishedTime"])[:10], "pdf": pdf.name,
                   "url": f"https://newsweb.oslobors.no/message/{m['messageId']}", "source": "NewsWeb"}
            log["steps"].append(f"report found on NewsWeb: {msg['title']} ({rep['date']})")
    except Exception as e:  # noqa: BLE001
        log["steps"].append(f"NewsWeb not read: {e}")
    log["report"] = rep
    # 3. the reader, or the dry run
    if rep:
        spec = rp.specs().get(code)
        if spec:
            try:
                done = rp.run(code, c.model if c else None, list(c.kill) if c else [], days=days)
                s = rp.latest(code)
                log["reader"] = {"mode": "spec", "new": len(done), "kill": [{"criterion": k["criterion"], "status": k["status"]} for k in (s or {}).get("kill", [])]}
                log["steps"].append(f"reader ran with the spec: {len(done)} new summary(ies)")
            except Exception as e:  # noqa: BLE001
                log["reader"] = {"mode": "spec", "error": str(e)}
                log["steps"].append(f"reader failed: {e}")
        else:
            try:
                yq = rp.period_of(rep["title"])
                dry = rp.dry_run(rp.report_dir(code) / rep["pdf"], GENERIC_SPEC, *(reversed(yq) if yq else (None, None)))
                p = _write_suggested_spec(code, dry, rep["title"])
                log["reader"] = {"mode": "dry-run", "found": {k: v["value"] for k, v in dry["found"].items()}, "missing": dry["missing"],
                                 "metrics": dry.get("metrics", {}), "suggested_spec": str(p)}
                log["steps"].append(f"no spec in reports.yaml: dry run found {len(dry['found'])} of {len(dry['found']) + len(dry['missing'])} rows; suggested spec written")
            except Exception as e:  # noqa: BLE001
                log["reader"] = {"mode": "dry-run", "error": str(e)}
                log["steps"].append(f"dry run failed: {e}")
    ar_dir().mkdir(parents=True, exist_ok=True)
    path(code).write_text(json.dumps(log, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return log


# ------------------------------------------------------------------------------------------------ html
def _fmt(name: str, v) -> str:
    if v is None:
        return "–"
    if name == "price":
        return f"{v:.2f}"
    if name in ("revenue", "ebit", "net_income"):
        return f"{v / 1e6:,.0f}".replace(",", " ")
    if name in ("ev_ebit", "pe"):
        return f"{v:.1f}x"
    if name in ("implied_g", "ev_vs_no_growth"):
        return f"{v * 100:+.1f} %"
    if name == "quarters_through":
        return dato(v)
    return str(v)


def _chg(d: dict) -> str:
    c = d.get("change")
    if c is None:
        return ""
    if d.get("unit") == "pp":
        return f"{c * 100:+.1f} pp"
    if d.get("unit") == "rel":
        return f"{c * 100:+.1f} %"
    return str(c)


def block_html(code: str, log: dict | None) -> str:
    """The stock page block: what the loop did after the newest report and what moved in the light case."""
    from osloquant.dashboard.render import E

    if not log:
        return ""
    rep = log.get("report")
    lc = log.get("lightcase") or {}
    labels = {"price": "Kurs", "revenue": "Omsetning LTM (m)", "ebit": "EBIT LTM (m)", "net_income": "Resultat LTM (m)", "ev_ebit": "EV/EBIT",
              "pe": "P/E", "implied_g": "Vekst prisen krever", "ev_vs_no_growth": "EV mot null-vekst", "quarters_through": "Regnskap til"}
    rows = "".join(f'<tr><td>{E(lab)}</td><td>{E(_fmt(k, d.get("before")))}</td><td>{E(_fmt(k, d.get("after")))}</td><td>{E(_chg(d))}</td></tr>'
                   for k, lab in labels.items() if (d := (lc.get("diff") or {}).get(k)))
    rd = log.get("reader") or {}
    if rd.get("mode") == "spec":
        reader = "Rapportleseren: " + ("; ".join(f'{E(k["criterion"][:60])}: {E(k["status"])}' for k in rd.get("kill", [])) or E(rd.get("error") or "no kill rows"))
    elif rd.get("mode") == "dry-run":
        reader = (f'Ingen leserspesifikasjon: prøvekjøring fant {len(rd.get("found") or {})} rader ({", ".join(rd.get("found") or {})}), mangler {", ".join(rd.get("missing") or []) or "ingen"}. '
                  f'Forslag skrevet til {E(str(rd.get("suggested_spec") or ""))}.' if not rd.get("error") else f'Prøvekjøring feilet: {E(rd["error"])}')
    else:
        reader = ""
    head = (f'Rapport: <a href="{E(rep["url"])}">{E(rep["title"])}</a> ({dato(rep["date"])}, {E(rep["source"])}) – PDF <a href="/report/{code}/{rep["message_id"]}.pdf">{E(rep["pdf"])}</a>.'
            if rep else "Ingen rapport funnet på NewsWeb i perioden.")
    return (f'<h2>Etter rapporten</h2><div class="card"><p>{head}</p>'
            + (f'<table class="odds"><thead><tr><th>Lett case</th><th>Før</th><th>Etter</th><th>Endring</th></tr></thead><tbody>{rows}</tbody></table>' if rows else
               f'<div class="warn">{E(lc.get("error") or "lett case ikke bygget på nytt")}</div>')
            + (f'<div class="sub" style="margin-top:8px">{reader}</div>' if reader else "")
            + "".join(f'<div class="warn">{E(w)}</div>' for w in lc.get("warnings") or [])
            + f'<div class="src">Kjørt {stempel(log["ran_at"])} (oq case after-report). ' + " · ".join(E(s) for s in log.get("steps", [])) + '</div></div>')


def queue_html(items: list[dict], today: pd.Timestamp) -> str:
    """The coverage page section: who owes a new view after which report, and whether the loop has run."""
    from osloquant.dashboard.render import E, link

    if not items:
        return ('<h2>Etter rapport – til ny vurdering</h2><div class="card"><p class="empty">Ingen dekkede selskaper har rapportert etter siste syn og lett case.</p>'
                '<div class="src">Køen utledes av filene: nyeste rapport (rapportleser, nedlastet rapport, research book, finanskalender) mot datoen på lett case og på hvert syn.</div></div>')
    rows = []
    for it in items:
        owes = " og ".join({"oscar": "du", "claude": "Claude"}[w] for w in it["owes"]) or "–"
        lc = (f'{it["lightcase_built"]} <span class="warn-t">(før rapporten)</span>' if it["lightcase_stale"] else it["lightcase_built"] or "–")
        rows.append(f'<tr><td>{link(it["code"], it["name"])}</td><td>{E(it["report"]["date"])} · {E(it["report"]["what"][:50])} <span class="src">({E(it["report"]["source"])})</span></td>'
                    f'<td>{it["days"]} d</td><td class="{"k" if "oscar" in it["owes"] else ""}">{E(owes)}</td><td class="src">{lc}</td>'
                    f'<td>{"kjørt " + E(it["ran"]) if it["ran"] else "<span class=warn-t>ikke kjørt</span>"}</td></tr>')
    return ('<h2>Etter rapport – til ny vurdering</h2><div class="card"><table class="odds"><thead><tr><th>Selskap</th><th>Nyeste rapport</th><th>Siden</th>'
            '<th>Skylder nytt syn</th><th>Lett case bygget</th><th>Løypen</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
            '<div class="src">Køen utledes av filene: nyeste rapport (rapportleser, nedlastet rapport, research book, finanskalender) mot datoen på lett case og på hvert syn. '
            'Kjør <code>oq case after-report --due</code> for å bygge lett case på nytt og lese rapporten; synet logges av den som skylder det – ditt på aksjesiden, Claudes med '
            '<code>oq case log</code>. Dine står også på «I dag»; Claudes står bare her (D31).</div></div>')


def suggested_specs() -> dict[str, Path]:
    d = jg.home() / "cases" / SPEC_DIR
    return {p.name.split(".")[0]: p for p in d.glob("*.suggested.yaml")} if d.exists() else {}


def spec_text(code: str) -> str | None:
    p = spec_path(code)
    return p.read_text(encoding="utf-8") if p.exists() else None


__all__ = ["due", "newest_report", "run_one", "load", "diff", "snapshot", "block_html", "queue_html", "GENERIC_SPEC", "suggested_specs", "spec_text", "yaml"]
