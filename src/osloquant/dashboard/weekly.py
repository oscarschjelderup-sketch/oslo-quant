"""The Sunday summary: what changed this week, which judgements were logged, and which should have been.

"Should have been" replays the front page's decision rules (dashboard/today.py) at every session of the week, with
the view and prices as they were that day, and lists each item for which no judgement or kill check dated on or
after the trigger was logged. Rows seeded from a written case keep the case's own date, so they never count as an
answer to something that happened after it.

Written to ``~/osloquant-home/weekly/<year>-W<week>.md`` and ``.html`` (private, like everything it reads).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import Path

import pandas as pd

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import feeds as fd
from osloquant.dashboard import market as mk
from osloquant.dashboard import render as rd
from osloquant.dashboard import today as td

E = rd.E


def week_of(day: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Monday and Sunday of the ISO week that holds ``day``."""
    monday = (day - pd.Timedelta(days=day.weekday())).normalize()
    return monday, monday + pd.Timedelta(days=6)


def _asof(snap: mk.Snapshot, d: pd.Timestamp) -> mk.Snapshot:
    return mk.Snapshot({k: v.loc[:d] for k, v in snap.panel.items()}, snap.names, snap.sectors, d)


def _case_asof(c: bk.Case, d: pd.Timestamp) -> bk.Case:
    """The case as it stood after the close of ``d``: the newest view dated on or before it, the rows logged by then."""
    day = f"{d:%Y-%m-%d}"
    hist = [r for r in c.history if r.get("logged_at", r["date"])[:10] <= day]
    views = [r for r in c.history if r["kind"] == "judgement" and r["date"] <= day]
    view = views[-1] if views else (c.view if c.view_source == "researchbook.yaml" else None)
    return dataclasses.replace(c, view=view, history=hist)


def missed(snap: mk.Snapshot, cases: list[bk.Case], watch: list[dict], sessions: list[pd.Timestamp],
           alerts: list[sg.Alert]) -> list[dict]:
    """Decision items raised during the week with no judgement or kill check dated on or after the trigger."""
    first: dict[tuple, dict] = {}
    for d in sessions:
        day_alerts = [a for a in alerts if a.session == f"{d:%Y-%m-%d}"]
        items = td.decisions(_asof(snap, d), [_case_asof(c, d) for c in cases], day_alerts, d, watch)
        for it in items:
            key = (it.code, it.kind, it.title if it.kind in ("risk-signal", "kill-check") else "")
            first.setdefault(key, {"code": it.code, "kind": it.kind, "title": it.title, "detail": it.detail, "date": f"{d:%Y-%m-%d}"})
    rows = jg.read_log() if jg.log_path().exists() else []
    out = []
    for it in first.values():
        answered = [r for r in rows if r.get("code") == it["code"] and r["kind"] in ("judgement", "kill_check") and r["date"] >= it["date"]]
        if not answered:
            out.append(it)
    return sorted(out, key=lambda i: (i["date"], i["code"]))


def summary(day: pd.Timestamp | None = None) -> dict:
    snap = mk.snapshot()
    day = (day or pd.Timestamp.now()).normalize()
    monday, sunday = week_of(day)
    C = snap.panel["close"]
    sessions = [d for d in C.index if monday <= d <= sunday]
    before = C.index[C.index < monday]
    if not sessions or not len(before):
        raise ValueError(f"no sessions in the week of {monday:%d %b %Y} in the store")
    start, end = before[-1], sessions[-1]
    wk = (C.loc[end] / C.loc[start] - 1).dropna()
    groups = pd.Series({c: snap.group(c) for c in wk.index})
    by_group = wk.groupby(groups).median().reindex([g for g in mk.GROUP_ORDER + ["Other"] if g in set(groups)])
    cases, watch = bk.cases(), bk.watchlist()
    alerts, _ = td.signals_since(snap, f"{start:%Y-%m-%d}", max_sessions=len(sessions))
    follow = {c.code for c in cases} | {w["code"] for w in watch if not w.get("moved_to_book")}
    rows = jg.read_log() if jg.log_path().exists() else []
    logged = [r for r in rows if f"{monday:%Y-%m-%d}" <= r.get("logged_at", "")[:10] <= f"{sunday:%Y-%m-%d}"]
    ann = fd.read("announcements") or {}
    week_ann = [a for a in ann.get("items", []) if a["code"] in follow and f"{monday:%Y-%m-%d}" <= a["time"][:10] <= f"{sunday:%Y-%m-%d}"]
    book_rows = []
    for c in cases:
        if c.code not in C.columns or pd.isna(C.at[end, c.code]):
            continue
        px = float(C.at[end, c.code])
        v = c.view or {}
        book_rows.append({"code": c.code, "name": c.name, "close": px, "week": wk.get(c.code), "rating": v.get("rating"),
                          "target": v.get("target"), "to_tp": v["target"] / px - 1 if v.get("target") else None})
    return {
        "monday": monday, "sunday": sunday, "start": start, "end": end, "sessions": [f"{d:%Y-%m-%d}" for d in sessions],
        "groups": by_group, "best": wk.sort_values(ascending=False).head(5), "worst": wk.sort_values().head(5),
        "names": snap.names, "book": book_rows, "announcements": sorted(week_ann, key=lambda a: a["time"]),
        "signals": {k: sum(a.kind == k for a in alerts) for k in (sg.BUY, sg.RISK, sg.INFO)},
        "followed_signals": [a for a in alerts if a.code in follow], "logged": logged,
        "missed": missed(snap, cases, watch, sessions, alerts), "check": jg.verify() if rows else None,
    }


def _p(v) -> str:
    return "–" if v is None or pd.isna(v) else f"{v * 100:+.1f}%"


def to_markdown(s: dict) -> str:
    n = s["names"]
    L = [f"# Week {s['monday']:%G-W%V}: {s['monday']:%d %b} – {s['sunday']:%d %b %Y}", "",
         f"Sessions {', '.join(s['sessions'])}. Returns from the close of {s['start']:%d %b} to {s['end']:%d %b}, "
         "Yahoo Finance daily closes via the oslo-quant store (delayed). Private.", "",
         f"## Judgements that should have been made ({len(s['missed'])})", ""]
    L += [f"- **{m['code']}** {m['date']} · {m['kind']}: {m['title']} – {m['detail']}" for m in s["missed"]] or ["- none: every decision item got a logged judgement or kill check."]
    L += ["", f"## Judgements logged this week ({len(s['logged'])})", ""]
    for r in s["logged"]:
        if r["kind"] == "judgement":
            L.append(f"- #{r['seq']} {r['code']} {r['rating']} TP {r['target']:g} at {r['price']:g} (view dated {r['date']}, source: {r.get('source', '')})")
        elif r["kind"] == "kill_check":
            L.append(f"- #{r['seq']} {r['code']} kill check {r['date']}: {r['criterion']} – {'BREACHED' if r['breached'] else 'intact'}")
        else:
            L.append(f"- #{r['seq']} {r['code']} {r['kind']} {r['date']}")
    if not s["logged"]:
        L.append("- none")
    if s["check"] is not None:
        L.append(f"\nLog: {s['check'].rows} rows, chain {'verifies' if s['check'].ok else 'BROKEN: ' + '; '.join(s['check'].problems)}.")
    L += ["", "## What changed", "", "### Research book", "", "| Code | View | Close | Week | To TP |", "|---|---|---|---|---|"]
    L += [f"| {b['code']} | {b['rating'] or '–'} {'' if b['target'] is None else 'TP ' + format(b['target'], 'g')} | {b['close']:.2f} | {_p(b['week'])} | {_p(b['to_tp'])} |" for b in s["book"]]
    L += ["", "### Sectors (median week return)", ""] + [f"- {g}: {_p(v)}" for g, v in s["groups"].items()]
    L += ["", "### Biggest moves", "", "Up: " + ", ".join(f"{c} {n.get(c, c)} {_p(v)}" for c, v in s["best"].items()),
          "", "Down: " + ", ".join(f"{c} {n.get(c, c)} {_p(v)}" for c, v in s["worst"].items())]
    sig = s["signals"]
    L += ["", f"### Signals: {sig[sg.BUY]} buy, {sig[sg.RISK]} risk, {sig[sg.INFO]} info across the 64", ""]
    L += [f"- {a.session} {a.code} {a.signal} at {a.price:.2f}" for a in s["followed_signals"]] or ["- none on research-book or watched stocks"]
    L += ["", f"### Announcements, research book and watchlist ({len(s['announcements'])})", ""]
    L += [f"- {a['time'][:10]} {a['code']}: {a['title']} ({a['url']})" for a in s["announcements"]] or ["- none in the cache (Oslo Børs NewsWeb, fetched by oq dashboard --refresh)"]
    L += ["", f"Generated {datetime.now():%d %b %Y %H:%M}. Nothing here trades or advises."]
    return "\n".join(L) + "\n"


def to_html(s: dict) -> str:
    n = s["names"]
    link = lambda c: rd.link(c, None, True)  # noqa: E731
    miss = "".join(f'<div class="item"><span class="chip risk">{E(m["kind"])}</span> {link(m["code"])} {E(m["date"])} – <b>{E(m["title"])}</b>'
                   f'<div class="src">{E(m["detail"])}</div></div>' for m in s["missed"]) or '<p class="empty">none: every decision item got a logged judgement or kill check</p>'
    logged = "".join(f'<li>#{r["seq"]} {link(r["code"])} ' + (f'{E(r["rating"])} TP {r["target"]:g} at {r["price"]:g} <span class="src">view dated {E(r["date"])}, {E(r.get("source", ""))}</span>'
                     if r["kind"] == "judgement" else E(f'{r["kind"]} {r["date"]}')) + '</li>' for r in s["logged"]) or '<li class="empty">none</li>'
    book = "".join(f'<tr><td>{link(b["code"])}</td><td>{E(b["rating"] or "–")}</td><td>{b["close"]:.2f}</td><td>{_p(b["week"])}</td>'
                   f'<td>{"–" if b["target"] is None else format(b["target"], "g")}</td><td>{_p(b["to_tp"])}</td></tr>' for b in s["book"])
    grp = "".join(f'<tr><td>{E(g)}</td><td>{_p(v)}</td></tr>' for g, v in s["groups"].items())
    mv = lambda ser: ", ".join(f'{link(c)} {E(n.get(c, c))} {_p(v)}' for c, v in ser.items())  # noqa: E731
    sig = s["signals"]
    fs = "".join(f'<li>{E(a.session)} {link(a.code)} {E(a.signal)} at {a.price:.2f}</li>' for a in s["followed_signals"]) or '<li class="empty">none on research-book or watched stocks</li>'
    ann = "".join(f'<li>{rd.when(a["time"])} {link(a["code"])} <a href="{E(a["url"])}">{E(a["title"])}</a></li>' for a in s["announcements"]) or '<li class="empty">none in the cache</li>'
    body = f"""<h1>Uke {s['monday']:%V} <span class="code">{s['monday']:%d %b} – {s['sunday']:%d %b %Y}</span></h1>
<p class="src">Sessions {', '.join(s['sessions'])}. Returns from the close of {s['start']:%d %b} to {s['end']:%d %b}, Yahoo Finance daily closes via the oslo-quant store (delayed).</p>
<div class="card decide"><h2>Vurderinger som burde vært gjort ({len(s['missed'])})</h2>{miss}</div>
<h2>Vurderinger logget denne uka ({len(s['logged'])})</h2><div class="card"><ul class="news">{logged}</ul></div>
<h2>Hva endret seg</h2>
<div class="grid2"><div class="card"><h3>Research book</h3><table><thead><tr><th>Code</th><th>View</th><th>Close</th><th>Week</th><th>TP</th><th>To TP</th></tr></thead><tbody>{book}</tbody></table></div>
<div class="card"><h3>Sektorer (median)</h3><table><tbody>{grp}</tbody></table></div></div>
<div class="card"><h3>Største bevegelser</h3><p>Opp: {mv(s['best'])}</p><p>Ned: {mv(s['worst'])}</p></div>
<div class="grid2"><div class="card"><h3>Signaler: {sig[sg.BUY]} kjøp, {sig[sg.RISK]} risiko, {sig[sg.INFO]} info</h3><ul class="news">{fs}</ul></div>
<div class="card"><h3>Børsmeldinger (book og overvåkning)</h3><ul class="news">{ann}</ul><div class="src">Oslo Børs NewsWeb, private use only.</div></div></div>"""
    return rd.page(f"Uke {s['monday']:%V}", "", body, static=True)


def weekly_dir() -> Path:
    d = jg.home() / "weekly"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write(day: pd.Timestamp | None = None) -> tuple[Path, Path, dict]:
    s = summary(day)
    stem = f"{s['monday']:%G-W%V}"
    md, html = weekly_dir() / f"{stem}.md", weekly_dir() / f"{stem}.html"
    md.write_text(to_markdown(s), encoding="utf-8")
    page = to_html(s)
    html.write_text(page, encoding="utf-8")
    (weekly_dir() / "latest.html").write_text(page, encoding="utf-8")
    return md, html, s
