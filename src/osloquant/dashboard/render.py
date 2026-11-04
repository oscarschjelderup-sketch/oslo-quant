"""HTML for the dashboard's pages. Server-rendered strings, so the same front page can be served live and written as
a static file for the evening task. Every number carries its source and time; delayed data says so; estimates say EST."""

from __future__ import annotations

import html
from datetime import datetime
from functools import lru_cache

import pandas as pd

from osloquant import signals as sg

E = html.escape

CSS = """
:root { --bg:#ffffff; --panel:#f6f8f9; --text:#1a2126; --muted:#5c6770; --line:#d9e0e5; --accent:#0f7c7c; --accent-dark:#0b5c5c;
        --accent-pale:#dcefed; --buy:#0b7a4b; --buy-bg:#e3f3ea; --risk:#b3261e; --risk-bg:#fbe9e7; --info:#1f5f99; --info-bg:#e8f0fa;
        --gold:#9a6700; --gold-bg:#fff4d6; }
* { box-sizing:border-box; }
html { background:var(--bg); }
body { margin:0; background:var(--bg); color:var(--text); font:13.5px/1.45 "Segoe UI",Arial,Helvetica,sans-serif; font-variant-numeric:tabular-nums; }
.wrap { max-width:1320px; margin:0 auto; padding:0 22px 44px; }
nav.top { display:flex; gap:2px; align-items:center; margin:0 -22px 18px; padding:0 22px; background:var(--accent-dark); min-height:40px; }
nav.top a { padding:10px 12px; color:#e8f3f2; text-decoration:none; font-weight:600; font-size:13px; border-bottom:3px solid transparent; }
nav.top a:hover { background:rgba(255,255,255,0.08); }
nav.top a.on { background:#fff; color:var(--accent-dark); }
nav.top .brand { font-weight:700; margin-right:16px; color:#fff; font-size:14px; letter-spacing:0.2px; }
nav.top form { margin-left:auto; display:flex; gap:6px; }
nav.top input { padding:5px 9px; border:1px solid var(--accent-pale); border-radius:3px; background:#fff; color:var(--text); width:150px; font:inherit; }
a { color:var(--info); text-decoration:none; } a:hover { text-decoration:underline; }
h1 { font-size:30px; font-weight:400; color:var(--accent); margin:6px 0 2px; letter-spacing:-0.2px; }
h1 .code { font-size:15px; color:var(--muted); font-weight:400; margin-left:8px; }
h2 { font-size:15px; font-weight:700; color:var(--accent); margin:26px 0 8px; padding-bottom:4px; border-bottom:1px solid var(--accent); }
h3 { font-size:13px; font-weight:700; color:var(--accent); margin:0 0 6px; padding-bottom:3px; border-bottom:1px solid var(--line); }
.sub { color:var(--muted); margin:0 0 12px; font-size:13px; }
.lead { font-size:16.5px; line-height:1.4; color:#2a3338; max-width:820px; margin:10px 0 6px; }
.card { background:var(--bg); padding:4px 0 10px; margin-bottom:8px; }
.card + .card { margin-top:4px; }
.src { color:var(--muted); font-size:11px; line-height:1.4; margin-top:6px; }
.foot { color:var(--muted); font-size:11.5px; margin-top:30px; padding-top:10px; border-top:1px solid var(--line); line-height:1.5; }
.empty { color:var(--muted); font-style:italic; }
.code { color:var(--muted); font-weight:500; }
.price { font-size:28px; font-weight:700; margin:4px 0 0; color:var(--text); } .price small { font-size:13px; font-weight:600; margin-left:10px; }
.up { color:var(--buy); } .down { color:var(--risk); } .muted { color:var(--muted); font-size:12.5px; }
/* report layout: main column and a right rail, as a sell-side front page */
.report { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:30px; align-items:start; }
@media (max-width:980px) { .report { grid-template-columns:1fr; } }
.rail .box { border-top:2px solid var(--accent); padding:8px 0 10px; margin-bottom:12px; }
.rail h4 { margin:0 0 6px; font-size:11.5px; font-weight:700; color:var(--accent); text-transform:uppercase; letter-spacing:0.4px; }
.rail .view-big { font-size:30px; font-weight:400; color:var(--accent); line-height:1.05; }
.rail .view-tp { font-size:19px; color:var(--accent); margin:2px 0 8px; }
.rail .view-none { font-size:15px; color:var(--muted); margin:2px 0 8px; }
table.facts { width:100%; font-size:12.5px; border-collapse:collapse; }
table.facts td { padding:3px 0; border-top:1px solid var(--line); vertical-align:top; }
table.facts td:first-child { color:var(--text); text-align:left; } table.facts td:last-child { text-align:right; font-weight:600; }
table.facts tr:first-child td { border-top:0; }
.cols3 { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:22px; } @media (max-width:980px) { .cols3 { grid-template-columns:1fr; } }
.cols3 ul { margin:4px 0 0; padding-left:18px; } .cols3 li { margin:4px 0; }
.cols3 .mid { background:var(--panel); padding:8px 12px 10px; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:26px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:18px; }
.cols { display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:18px; }
/* tables: thin rules, tabular numbers, years as columns */
table { width:100%; border-collapse:collapse; font-size:12.5px; }
th, td { text-align:right; padding:4px 7px; border-top:1px solid var(--line); vertical-align:top; }
th { color:var(--text); font-weight:700; border-top:0; border-bottom:1px solid var(--accent); background:transparent; }
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align:left; }
table.odds td, table.odds th { text-align:right; } table.odds td:first-child, table.odds th:first-child { text-align:left; }
table.odds th.grp { text-align:center; }
table.keyfig td:first-child { font-weight:500; } table.keyfig tr.sep td { border-top:2px solid var(--line); }
table.keyfig td.ltm, table.keyfig th.ltm { background:var(--accent-pale); }
.heat td { text-align:right; } .heat td:first-child, .heat td:nth-child(2) { text-align:left; }
/* the decision box */
.decide { border:1px solid var(--risk); border-left:6px solid var(--risk); padding:10px 16px 12px; margin:6px 0 10px; }
.decide h2 { margin-top:0; color:var(--risk); border-bottom-color:var(--risk-bg); }
.item { padding:9px 0; border-top:1px solid var(--line); } .item:first-of-type { border-top:0; }
.item .why { color:var(--muted); font-size:12.5px; }
.tag { display:inline-block; font-size:10.5px; font-weight:700; padding:1px 7px; border-radius:2px; margin-right:6px; text-transform:uppercase; letter-spacing:0.3px; }
.tag.u0 { background:var(--risk); color:#fff; } .tag.u1 { background:var(--gold-bg); color:var(--gold); } .tag.u2 { background:var(--info-bg); color:var(--info); }
/* chips, alerts, lists */
.chips { display:flex; gap:8px; flex-wrap:wrap; margin:10px 0 0; }
.chip { display:inline-block; padding:2px 9px; border-radius:2px; font-size:11.5px; font-weight:700; }
.chip.buy { background:var(--buy-bg); color:var(--buy); } .chip.risk { background:var(--risk-bg); color:var(--risk); }
.chip.info { background:var(--info-bg); color:var(--info); } .chip.plain { background:var(--panel); color:var(--text); }
.alert { display:grid; grid-template-columns:56px 1fr auto; gap:4px 10px; padding:7px 0; border-top:1px solid var(--line); align-items:start; }
.alert:first-of-type { border-top:0; } .alert .d { grid-column:2 / 4; color:var(--muted); font-size:12px; }
.alert b { font-size:13px; } .odds { font-size:11.5px; white-space:nowrap; }
.kv { margin:4px 0 0; padding:0; list-style:none; } .kv li { padding:3px 0; border-top:1px solid var(--line); font-size:12.5px; } .kv li:first-child { border-top:0; }
details { margin-top:6px; } summary { cursor:pointer; color:var(--muted); font-size:12.5px; }
details ul { margin:6px 0 0 18px; padding:0; font-size:12.5px; color:var(--muted); }
details.card summary { color:var(--text); }
.news li { margin:4px 0; } ul.news { padding-left:18px; margin:4px 0; }
.ladder { margin:10px 0 2px; } .ladder svg { width:100%; height:72px; display:block; }
.sector { margin-bottom:18px; } .sector h3 { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.driver { font-size:12px; color:var(--muted); font-weight:400; margin-bottom:4px; }
.bracket { display:block; font-size:11.5px; color:var(--muted); margin-top:2px; }
.t { color:var(--buy); font-weight:700; } .k { color:var(--risk); font-weight:700; } .warn-t { color:var(--gold); }
.err { background:var(--risk-bg); color:var(--risk); padding:8px 12px; border-left:4px solid var(--risk); margin:8px 0; }
.ok { background:var(--buy-bg); color:var(--buy); padding:8px 12px; border-left:4px solid var(--buy); margin:8px 0; }
.warn { background:var(--gold-bg); color:#6b4a00; padding:8px 12px; border-left:4px solid var(--gold); margin:8px 0; font-size:13px; }
.warn ul { margin:4px 0 0; padding-left:18px; }
/* the judgement form */
form.judge label { display:block; font-size:12.5px; font-weight:600; margin:8px 0 3px; }
form.judge input, form.judge select, form.judge textarea { width:100%; padding:6px 8px; border:1px solid var(--line); border-radius:2px; background:#fff; color:var(--text); font:inherit; }
form.judge textarea { min-height:70px; }
.row3 { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; } .row4 { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
button.go { margin-top:12px; padding:9px 20px; border:0; border-radius:2px; background:var(--accent); color:#fff; font-weight:700; cursor:pointer; font:inherit; }
button.go:hover { background:var(--accent-dark); }
"""

NAV = [("/", "I dag"), ("/desk", "Desk"), ("/coverage", "Dekning"), ("/screen", "Prisen krever"), ("/funds", "Porteføljer"), ("/sectors", "Sektorer"), ("/calendar", "Kalender"), ("/calibration", "Kalibrering"), ("/watchlist", "Overvåkning"), ("/health", "Datahelse")]


def pct(v, d=1, sign=True):
    if v is None or (isinstance(v, float) and v != v):
        return "–"
    return f"{v * 100:{'+' if sign else ''}.{d}f}%"


def cls(v):
    return "" if v is None or (isinstance(v, float) and v != v) else ("up" if v > 0 else "down" if v < 0 else "")


def heat(v):
    """Background for a heatmap cell: green up, red down, saturation by size (capped at ±10 %)."""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    a = min(abs(v) / 0.10, 1.0)
    col = "46,125,79" if v >= 0 else "179,38,30"
    return f' style="background:rgba({col},{0.08 + 0.55 * a:.2f})"'


def page(title: str, active: str, body: str, generated: datetime | None = None, static: bool = False) -> str:
    nav = "".join(f'<a href="{href}" class="{"on" if href == active else ""}">{E(label)}</a>' for href, label in NAV)
    search = '' if static else '<form action="/go" method="get"><input name="code" placeholder="Ticker, f.eks. MOWI"></form>'
    plotly = '' if static else '<script src="/static/plotly.min.js"></script>'
    note = ('<div class="src">Static snapshot written by the evening job. Live dashboard: <code>oq dashboard</code> → '
            '<a href="http://127.0.0.1:8060/">http://127.0.0.1:8060/</a></div>') if static else ''
    gen = f'<div class="src">Generated {(generated or datetime.now()):%d %b %Y %H:%M}. Private: research book and judgements are read from ~/osloquant-home, never published.</div>{note}'
    return f"""<!doctype html><html lang="no"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)} – Oslo Børs dashboard</title><style>{CSS}</style>{plotly}</head><body><div class="wrap">
<nav class="top"><span class="brand">Oslo Børs · beslutninger</span>{nav}{search}</nav>
{body}
<div class="foot">{gen}<div class="src">Prices: daily closes from Yahoo Finance via the oslo-quant store – delayed, not real time. Signal odds: measured on this store's history (oq signals score). Nothing here trades or advises.</div></div>
</div></body></html>"""


def link(code: str, text: str | None = None, static: bool = False) -> str:
    href = f"http://127.0.0.1:8060/stock/{code}" if static else f"/stock/{code}"
    return f'<a href="{href}">{E(text or code)}</a>'


# ------------------------------------------------------------------------------------------------ I dag
def today_page(ctx: dict, static: bool = False) -> str:
    """ctx: decisions, upcoming, moves, alerts, sessions, announcements, asof, feeds_note"""
    L = lambda c, t=None: link(c, t, static)  # noqa: E731
    dec = ctx["decisions"]
    today = ctx.get("today") or pd.Timestamp.now().normalize()
    asof = ctx["asof"]
    # the data date is not today's date: say both, and warn when the newest close is older than the last weekday
    expected = today - pd.Timedelta(days=1)
    while expected.weekday() >= 5:
        expected -= pd.Timedelta(days=1)
    stale = asof.normalize() < expected if asof is not None and asof == asof else True
    banner = (f'<div class="warn">Siste sluttkurs i lageret er fra {asof:%A %d %b} – eldre enn siste virkedag ({expected:%d %b}). '
              'Kjør <code>oq record</code> før du stoler på kursene.</div>' if stale else '')
    urgency_word = {0: "Gjør først", 1: "I dag", 2: "Kan vente"}
    minutes = {"kill-check": 10, "report": 15, "pre-report": 20, "post-report": 20, "re-rate": 15, "re-assess": 10, "risk-signal": 3, "stale-view": 10, "report-tp": 15}
    total_min = sum(minutes.get(i.kind, 5) for i in dec)
    if dec:
        summary = (f'<p style="margin:0 0 8px"><b>{len(dec)} ting, omtrent {total_min} minutter, i denne rekkefølgen:</b> '
                   + " ".join(f'{n}) {E(i.code)}' for n, i in enumerate(dec, 1)) + '</p>')
        dec_html = summary + "".join(
            f'<div class="item"><span class="tag {["u0", "u1", "u2"][i.urgency]}">{n}. {E(urgency_word[i.urgency])}</span>'
            f'<span class="src">{E(i.kind)} · ~{minutes.get(i.kind, 5)} min</span><br><b>{L(i.code, i.title)}</b>'
            f'<div class="why">{E(i.detail)}'
            + (f' <a href="/stock/{E(i.code)}/pretrade">Før du kjøper →</a>' if (not static and i.kind in ("pre-report", "post-report", "re-rate", "re-assess", "report-tp")) else '')
            + '</div></div>' for n, i in enumerate(dec, 1))
    else:
        nxt = ctx["upcoming"][0] if ctx.get("upcoming") else None
        dec_html = ('<p style="font-size:16px;margin:4px 0"><b>Ingenting krever en vurdering i dag.</b> Gå til forelesning.</p>'
                    + (f'<div class="src">Neste dato: {nxt["date"]:%d %b} – {L(nxt["code"], nxt["name"])}, {E(nxt["what"])}.</div>' if nxt else ''))
    body = [f'<h1>I dag <span class="code">{today:%A %d %b %Y}</span></h1>',
            f'<div class="sub">Siste sluttkurs: {asof:%A %d %b %Y} (Yahoo, forsinket). Signaler dekker {E(", ".join(ctx["sessions"]) or "–")}.</div>',
            banner,
            f'<div class="card decide"><h2>Dette krever en vurdering fra deg ({len(dec)})</h2>{dec_html}</div>']
    # cases vs target
    rows = "".join(
        f'<tr><td>{L(m["code"], m["name"])}</td><td>{E(m["rating"] or "")}</td><td>{m["price"]:.2f}</td><td class="{cls(m["since"])}">{pct(m["since"])}</td>'
        f'<td>{m["target"]:g}</td><td class="{cls(m["to_tp"])}">{pct(m["to_tp"])}</td><td>{pct(m["to_bear"])}</td><td>{pct(m["to_bull"])}</td>'
        f'<td class="src">{E(str(m["view_date"]))} · {E(m["view_source"])}'
        + (f' <span class="warn-t">· før rapporten {m["stale_report"]:%d %b}</span>' if m.get("stale_report") is not None else '') + '</td></tr>' for m in ctx["moves"])
    cov = ctx.get("coverage")
    cov_line = (f'<div class="src">Dekning: {cov["n"]} selskaper, Claude har syn på {cov["claude"]}' + (f', {cov["only_claude"]} uten ditt syn' if cov["only_claude"] else '')
                + (f'; universet {cov["universe"]} selskaper – {cov["full"]} full case, {cov["light"]} lett case, {cov["watch"]} følges'
                   + (f', <span class="k">{cov["gap"]} under plan</span>' if cov.get("gap") else '') if cov.get("universe") else '')
                + ('' if static else ' – <a href="/coverage">se Dekning</a>') + '.</div>') if cov and cov.get("claude") else ''
    body.append('<h2>Research book mot kursmål</h2><div class="card"><table><thead><tr><th>Company</th><th>View</th><th>Close</th><th>Since view</th>'
                '<th>TP</th><th>To TP</th><th>To bear</th><th>To bull</th><th>View from</th></tr></thead><tbody>'
                + (rows or '<tr><td colspan="9" class="empty">no cases with a view</td></tr>') + '</tbody></table>'
                f'<div class="src">Close: {E(ctx["price_label"])}. A move of 10 % or more since the view, or a report dated after the view, puts the case on '
                'the decision list.</div>' + cov_line + '</div>')
    if ctx.get("portfolio"):
        from osloquant.dashboard import portfolio as pf

        body.append(pf.block_html(ctx["portfolio"], static))
    if "desk" in ctx:
        from osloquant.dashboard import deskpage

        body.append(deskpage.front_block(ctx["desk"], static))
    # upcoming + kill
    up = "".join(f'<li><b>{e["date"]:%d %b}</b> ({(e["date"] - ctx["today"]).days} d) {L(e["code"], e["name"]) if e.get("code") else E(e["name"])} – {E(e["what"])}'
                 + (f' <span class="src">({E(e["source"])})</span>' if e.get("source") else '')
                 + (f'<details><summary>{len(e["kill"])} kill criteria to check at this event</summary><ul>'
                    + "".join(f"<li>{E(k)}</li>" for k in e["kill"]) + '</ul></details>' if e.get("kill") else '') + '</li>' for e in ctx["upcoming"])
    ann = ctx.get("announcements")
    ann_html = ("".join(f'<li><b>{E(a["code"])}</b> {when(a["time"])} – <a href="{E(a["url"])}" target="_blank" rel="noopener">{E(a["title"])}</a></li>' for a in ann["items"])
                or '<li class="empty">no announcements in the window</li>') + f'</ul><div class="src">{E(ann["source"])}</div>' if ann else \
        '<li class="empty">announcements not fetched (oq dashboard --refresh)</li></ul>'
    body.append('<div class="grid2"><div><h2>Kommende datoer (30 dager)</h2><div class="card"><ul class="news">'
                + (up or '<li class="empty">no events in the next 30 days</li>') + '</ul><div class="src">Research book, the issuers\' financial calendars on NewsWeb and Norges Bank; '
                + ('<a href="/calendar">hele kalenderen</a>' if not static else 'full calendar on the dashboard') + '.</div></div></div>'
                '<div><h2>Børsmeldinger – research book og overvåkning</h2><div class="card"><ul class="news">' + ann_html + '</div></div></div>')
    if "insiders" in ctx:
        body.append(insider_front(ctx["insiders"], ctx.get("shorts_moved", []), static))
    # signals since last visit
    alerts = ctx["alerts"]
    book = ctx["book_codes"]
    first = [a for a in alerts if a.code in book] + [a for a in alerts if a.code not in book]
    row = lambda a: (f'<div class="alert"><b>{L(a.code)}</b><span>{E(a.name)} · <b>{E(a.signal)}</b> · {a.session} at {a.price:.2f}'  # noqa: E731
                     + (' <span class="chip info">book</span>' if a.code in book else '') + '</span>'
                     f'<span class="chip {chip_class(a)} odds">{pct(a.exc20)} / {pct(a.exc60)} · hit {pct(a.hit20, 0, False)}{_n(a)}</span>'
                     f'<span class="d">{E(a.detail)}{robustness_line(a.signal)}</span></div>')
    mine = [a for a in first if a.code in book]
    rest = [a for a in first if a.code not in book]
    foot = ('<div class="src">Odds: meravkastning mot de 64 aksjene 20/60 handelsdager etter denne typen signal, treffrate og antall '
            '(oq signals score, 2010–2026, bare dagens aksjer). Ingen kjøpssignal har betalt seg etter kostnader på 20 dager; grad A–D under hvert '
            'signal sier om tallet har holdt seg.</div>')
    open_part = "".join(row(a) for a in mine) or '<p class="empty">no new signals on research-book stocks</p>'
    folded = (f'<details><summary>{len(rest)} signaler på andre aksjer – vis</summary>{"".join(row(a) for a in rest[:60])}</details>' if rest else '')
    body.append(f'<h2>Nye signaler siden sist ({len(alerts)}, {len(mine)} på dine aksjer)</h2><div class="card">{open_part}{folded}{foot}</div>')
    return page("I dag", "/", "\n".join(body), static=static)


# ------------------------------------------------------------------------------------------------ Sektorer
def sectors_page(ret: pd.DataFrame, drivers: dict, groups: list[str], asof) -> str:
    body = [f'<h1>Sektorer</h1><div class="sub">All {len(ret)} stocks by sector. Returns to the close of {asof:%d %b %Y} (Yahoo Finance, delayed). '
            'Colour: green up, red down, full colour at ±10 %.</div>']
    for g in groups:
        sub = ret[ret["group"] == g].sort_values("m1", ascending=False)
        if sub.empty:
            continue
        avg = {k: sub[k].mean() for k in ("d1", "w1", "m1", "ytd")}
        rows = "".join(
            f'<tr><td>{link(code)}</td><td>{E(r["name"])}</td><td>{r["close"]:.2f}</td>'
            + "".join(f'<td{heat(r[k])}>{pct(r[k])}{"*" if k == "ytd" and r["ytd_from_listing"] else ""}</td>' for k in ("d1", "w1", "m1", "ytd"))
            + (f'<td class="src">{r["date"]:%d %b}</td>' if r["stale"] else '<td></td>') + '</tr>' for code, r in sub.iterrows())
        d = drivers.get(g, [])
        dhtml = " · ".join(f'{E(x["label"])}: <b>{E(x["value"])}</b> <span class="src">({E(x["source"])})</span>' for x in d) or "–"
        body.append(f'<div class="card sector"><h3><span>{E(g)} <span class="code">{len(sub)} stocks · avg {pct(avg["d1"])} d / {pct(avg["m1"])} m / {pct(avg["ytd"])} ytd</span></span></h3>'
                    f'<div class="driver">Drivers: {dhtml}</div>'
                    '<table class="heat"><thead><tr><th>Code</th><th>Name</th><th>Close</th><th>Day</th><th>Week</th><th>Month</th><th>YTD</th><th></th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div>')
    body.append('<div class="src">* YTD from the first close in the store (listed this year). A date after a row = that stock has no close for the newest session.</div>')
    return page("Sektorer", "/sectors", "\n".join(body))


# ------------------------------------------------------------------------------------------------ Aksjeside
def _fact_rows(rows: list[tuple[str, str]]) -> str:
    return '<table class="facts">' + "".join(f'<tr><td>{E(k)}</td><td>{v}</td></tr>' for k, v in rows if v not in (None, "")) + '</table>'


def _nok(v, unit=1e9, d=1) -> str:
    return "–" if v is None else f"{v / unit:,.{d}f}".replace(",", " ")


def view_rail(c, px: float, price_label: str, lc: dict | None, next_event: dict | None, today=None) -> str:
    """The right rail of a stock page, as on a sell-side front page: the view (rating and target) large, the summary
    facts, the capital structure from the light case, and the next event. Oscar's view only – Claude's stays folded
    below the fold until Oscar has written his own (D31)."""
    v = (c.view if c else None) or {}
    out = ['<aside class="rail">']
    if v.get("target"):
        tp = float(v["target"])
        up = tp / px - 1
        out.append(f'<div class="box"><div class="view-big">{E(v.get("rating", "?"))}</div><div class="view-tp">TP: NOK {tp:g} <span class="{cls(up)}">({up * 100:+.0f} %)</span></div>'
                   + _fact_rows([("Kurs (siste sluttkurs)", f'{px:.2f}'), ("Kursmål (12 mnd)", f'{tp:g}'), ("Opp-/nedside", f'<span class="{cls(up)}">{pct(up, 0)}</span>'),
                                 ("Bear / bull", f'{v["bear"]:g} / {v["bull"]:g}' if v.get("bear") and v.get("bull") else None),
                                 ("Sannsynlighet bear / base / bull", f'{v["p_bear"]:.0%} / {v["p_base"]:.0%} / {v["p_bull"]:.0%}' if v.get("p_bear") is not None else None),
                                 ("Horisont", f'{v.get("horizon_months", 12)} mnd'), ("Syn fra", f'{E(str(v.get("date")))} <span class="src">({E(c.view_source)})</span>'),
                                 ("Kill-nivå", f'{v["kill_level"]:g}' if v.get("kill_level") else None),
                                 ("Konsensus kursmål", f'{float(v["consensus_target"]):g} <span class="src">({E(str(v.get("consensus_source", "")))})</span>' if v.get("consensus_target") else None)])
                   + '<div class="src">Ditt syn (EST). Kurs: ' + E(price_label) + '.</div></div>')
    else:
        out.append('<div class="box"><div class="view-none">Ingen vurdering fra deg ennå</div>'
                   '<div class="src">Les den lette casen, skriv ditt syn i skjemaet nederst, og les Claudes etterpå.' + (' Claude har et syn (foldet lenger ned).' if c and c.claude_view else '') + '</div></div>')
    if lc:
        m, b, pr = lc["multiples"], lc["balance"], lc["profit"]
        cur = lc["currency"]["reporting"]
        out.append('<div class="box"><h4>Kapitalstruktur</h4>' + _fact_rows([
            ("Markedsverdi (NOK mrd)", _nok(lc.get("mcap_nok"))), ("Aksjer (m)", _nok(lc.get("shares"), 1e6, 1)),
            (f"Netto gjeld ({cur} m)", _nok(b.get("net_debt"), 1e6, 0)), (f"EV ({cur} m)", _nok(m.get("ev"), 1e6, 0) if m.get("ev") else None),
            ("EV/EBIT (LTM)", f'{m["ev_ebit"]:.1f}x' if m.get("ev_ebit") else None), ("P/E (LTM)", f'{m["pe"]:.1f}x' if m.get("pe") else None),
            ("P/B", f'{m["pb"]:.2f}x' if m.get("pb") else None), ("FCF-yield", pct(m.get("fcf_yield"), 1, False) if m.get("fcf_yield") is not None else None),
            ("Rapporteringsvaluta", E(cur) + (f' · {E(cur)}NOK {lc["currency"]["fx"]:.3f}' if lc["currency"].get("fx") and cur != "NOK" else ""))])
            + f'<div class="src">Yahoo-regnskap via lageret, kvartaler til {E(str(lc.get("quarters_through")))}; LTM = {E(str(pr["ebit"]["period"]))}.</div></div>')
    if next_event:
        d = next_event["date"]
        days = f' ({(d - today).days} d)' if today is not None else ''
        out.append(f'<div class="box"><h4>Neste hendelse</h4><div><b>{d:%d %b %Y}</b>{days}<br>{E(next_event["what"])}</div><div class="src">{E(next_event["source"])}</div></div>')
    out.append('</aside>')
    return "".join(out)


def case_columns(c, px: float, lc: dict | None) -> str:
    """Three columns under the chart: downside (kill criteria), the case (thesis and what the price asks for), upside
    (the bull value and its weight) – the investment-case overview of a report, from our own numbers."""
    v = (c.view if c else None) or {}
    if not v.get("target") and not lc:
        return ""
    kills = "".join(f"<li>{E(k)}</li>" for k in (c.kill if c else [])) or '<li class="empty">ingen kill-kriterier logget</li>'
    thesis = E(v.get("thesis") or "") or '<span class="empty">ingen begrunnelse logget</span>'
    reads = f'<p><b>Hva prisen krever:</b> {E(lc["reverse"]["reads"])}</p>' if lc else ''
    bull = (f'<p><b>Bull NOK {v["bull"]:g}</b> ({pct(v["bull"] / px - 1, 0)}), vekt {v["p_bull"]:.0%}.</p>' if v.get("bull") and v.get("p_bull") is not None else
            f'<p><b>Bull NOK {v["bull"]:g}</b> ({pct(v["bull"] / px - 1, 0)}).</p>' if v.get("bull") else '<p class="empty">ingen bull-verdi</p>')
    bear = (f'<p><b>Bear NOK {v["bear"]:g}</b> ({pct(v["bear"] / px - 1, 0)}), vekt {v["p_bear"]:.0%}.</p>' if v.get("bear") and v.get("p_bear") is not None else
            f'<p><b>Bear NOK {v["bear"]:g}</b> ({pct(v["bear"] / px - 1, 0)}).</p>' if v.get("bear") else '')
    return ('<h2>Investeringscase</h2><div class="cols3">'
            f'<div><h3>Nedside – kill-kriterier</h3>{bear}<ul>{kills}</ul><div class="src">Brytes ett, er caset brutt – sjekk og logg.</div>{_kill_source(c)}</div>'
            f'<div class="mid"><h3>Vårt syn</h3><p>{thesis}</p>{reads}<div class="src">Synet er ditt (EST); «hva prisen krever» er regnet fra lett case.</div></div>'
            f'<div><h3>Oppside</h3>{bull}<div class="src">Bull-verdien er synets eget anslag (EST).</div></div></div>')


def _kill_source(c) -> str:
    """One line under the kill list: is it the model's list (D40)?"""
    if not c:
        return ""
    from osloquant.dashboard import killlist as kl

    return kl.block_html(kl.for_case(c))


def key_figures(lc: dict | None, px: float) -> str:
    """Years as columns and LTM last, as in a report's estimates table – historical and LTM only, no estimates."""
    if not lc or not lc.get("annual"):
        return ""
    cur = lc["currency"]["reporting"]
    years = lc["annual"]
    pr, m, r = lc["profit"], lc["multiples"], lc["returns"]
    ltm = {"revenue": pr["revenue"]["value"], "ebit": pr["ebit"]["value"], "net_income": pr["net_income"]["value"], "fcf": pr["fcf"]["value"],
           "net_debt": lc["balance"].get("net_debt")}
    mn = lambda v: "–" if v is None else f"{v / 1e6:,.0f}".replace(",", " ")  # noqa: E731
    mg = lambda e, rv: "–" if not e or not rv else f"{e / rv * 100:.1f} %"  # noqa: E731
    head = "".join(f"<th>{a['year']}</th>" for a in years) + f'<th class="ltm">{E(str(pr["ebit"]["period"] or "LTM")).replace("LTM to ", "LTM ")}</th>'
    rows = []
    for label, key in (("Omsetning", "revenue"), ("EBIT", "ebit"), ("Resultat", "net_income"), ("Fri kontantstrøm", "fcf"), ("Netto gjeld", "net_debt")):
        rows.append(f'<tr><td>{label} ({E(cur)} m)</td>' + "".join(f"<td>{mn(a.get(key))}</td>" for a in years) + f'<td class="ltm">{mn(ltm.get(key))}</td></tr>')
    rows.append('<tr><td>EBIT-margin</td>' + "".join(f"<td>{mg(a.get('ebit'), a.get('revenue'))}</td>" for a in years) + f'<td class="ltm">{mg(ltm["ebit"], ltm["revenue"])}</td></tr>')
    if years and years[0].get("revenue"):
        g = "".join(f"<td>{'–' if i == 0 or not years[i - 1].get('revenue') or not a.get('revenue') else format(a['revenue'] / years[i - 1]['revenue'] - 1, '+.1%').replace('%', ' %')}</td>"
                    for i, a in enumerate(years))
        rows.append(f'<tr><td>Omsetningsvekst</td>{g}<td class="ltm"></td></tr>')
    blank = "<td></td>" * len(years)
    val = [("P/E", f'{m["pe"]:.1f}x' if m.get("pe") else "–"), ("P/B", f'{m["pb"]:.2f}x' if m.get("pb") else "–")]
    if not lc["financial"]:
        val.insert(1, ("EV/EBIT", f'{m["ev_ebit"]:.1f}x' if m.get("ev_ebit") else "–"))
        val.append(("FCF-yield", pct(m.get("fcf_yield"), 1, False) if m.get("fcf_yield") is not None else "–"))
    val.append(("ROE", pct(r.get("roe"), 0, False) if r.get("roe") is not None else "–"))
    if r.get("roic") is not None:
        val.append(("ROIC", pct(r.get("roic"), 0, False)))
    first = True
    for label, x in val:
        rows.append(f'<tr{" class=sep" if first else ""}><td>{label} ved kurs {px:.2f}</td>{blank}<td class="ltm">{x}</td></tr>')
        first = False
    pe = lc.get("peers") or {}
    peer = (f' Sektormedian: P/E {pe["pe"]:.1f}x' if pe.get("pe") else "") + (f', EV/EBIT {pe["ev_ebit"]:.1f}x' if pe.get("ev_ebit") else "") + (f', P/B {pe["pb"]:.2f}x' if pe.get("pb") else "")
    return (f'<h2>Nøkkeltall</h2><table class="keyfig"><thead><tr><th>Årsslutt des</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
            f'<div class="src">Kilde: Yahoo Finance årsregnskap og kvartaler via oslo-quant-lageret (forsinket), i {E(cur)}; LTM = siste fire kvartaler. '
            f'Ingen estimater vises – synets egne tall er merket EST.{E(peer)}{" (" + E(pe.get("group", "")) + ")" if peer else ""}.</div>')


def stock_page(code: str, ctx: dict) -> str:
    st, c = ctx["status"], ctx["case"]
    name = ctx["name"]
    if not st.get("price"):
        return page(code, "", f'<h1>{E(code)}</h1><p class="err">No prices for {E(code)} in the store. Add it to universe.yaml and run oq record.</p>')
    px = st["price"]
    lc = ctx.get("lightcase")
    v = (c.view if c else None) or {}
    lead = v.get("thesis") or ""
    lead_html = f'<div class="lead">{E(lead[:420])}{"…" if len(lead) > 420 else ""}</div>' if lead else ''
    head = (f'<div class="src" style="margin-top:4px">{E(ctx["group"])} · {E(code)} · {E(ctx["price_label"])}</div>'
            f'<h1>{E(name)}</h1>'
            f'<div class="price">{px:.2f}<small class="{cls(st.get("chg_1d"))}">{pct(st.get("chg_1d"))} dag</small>'
            f'<small class="{cls(st.get("chg_20d"))}">{pct(st.get("chg_20d"))} 20 d</small><small class="{cls(ctx.get("ytd"))}">{pct(ctx.get("ytd"))} i år</small></div>'
            + lead_html)
    msgs = "".join(f'<div class="err">{E(m)}</div>' for m in ctx.get("errors", [])) + "".join(f'<div class="ok">{E(m)}</div>' for m in ctx.get("ok", []))
    keys = [("60 d høy / lav", f'{st["hi60"]:.2f} / {st["lo60"]:.2f}' if st.get("hi60") and st.get("lo60") else "–"),
            ("RSI 14", f'{st["rsi"]:.0f}' if st.get("rsi") is not None else "–"), ("MA20 / MA60", f'{st["ma20"]:.2f} / {st["ma60"]:.2f}' if st.get("ma60") else "–"),
            ("Trend", sg.trend_words(st))]
    keyhtml = '<ul class="kv">' + "".join(f"<li><b>{E(k)}</b>: {E(v_)}</li>" for k, v_ in keys) + '</ul><div class="src">Computed from the store\'s daily bars (delayed).</div>'
    sig = "".join(f'<div class="alert"><b>{E(a.kind)}</b><span><b>{E(a.signal)}</b> · {a.session}</span><span class="chip {chip_class(a)} odds">'
                  f'{pct(a.exc20)} / {pct(a.exc60)} · hit {pct(a.hit20, 0, False)}{_n(a)}</span><span class="d">{E(a.detail)}{bracket_line(a.signal)}</span></div>'
                  for a in ctx["alerts"]) or '<p class="empty">no signal in the last 10 sessions</p>'
    news = ctx.get("news")
    nhtml = ("<ul class='news'>" + "".join(f'<li>{when(n["time"])} – <a href="{E(n.get("url") or n.get("link", ""))}" target="_blank" rel="noopener">{E(n["title"])}</a> <span class="src">{E(n.get("kind", ""))}</span></li>' for n in news["items"])
             + f"</ul><div class='src'>{E(news['source'])}</div>") if news and news["items"] else (
             f'<p class="empty">No announcement in the cached window (14 days) and no headline naming the company.</p><div class="src">{E(news["source"])}</div>'
             if news else '<p class="empty">not fetched – oq dashboard --refresh</p>')
    main = [head, msgs, f'<div class="card">{ctx["chart"]}</div>', case_columns(c, px, lc), key_figures(lc, px)]
    parts = ['<div class="report"><div>' + "\n".join(main) + '</div>' + view_rail(c, px, ctx["price_label"], lc, ctx.get("next_event"), ctx.get("today")) + '</div>',
             f'<div class="grid2"><div><h2>Teknisk</h2>{keyhtml}</div><div><h2>Aktive signaler (10 økter)</h2>{sig}</div></div>',
             f'<h2>Børsmeldinger og nyheter</h2><div class="card">{nhtml}</div>', insider_block(code, ctx.get("insiders")),
             ctx.get("reports_html", ""), ctx.get("afterreport_html", "")]
    if c and (c.view or c.history):
        parts.append(case_block(c, px, ctx.get("rdcf")))
        parts.append(report_block(code, ctx.get("report")))
        parts.append(odds_block(ctx.get("odds"), c.view or {}))
    parts.append(lightcase_block(lc))
    parts.append(claude_view_block(c, px))
    if "desk_runs" in ctx:
        from osloquant.dashboard import deskpage

        parts.append(deskpage.stock_block(code, ctx["desk_runs"]))
        if ctx.get("desk_attached"):
            parts.append(deskpage.attached_html(*ctx["desk_attached"]))
    parts.append(judge_form(code, name, px, ctx["price_label"], ctx.get("form", {}), c, ctx.get("sizing")))
    return page(f"{code}", "", "\n".join(parts))


SIDE_NO = {"buy": "kjøp", "sell": "salg", "subscription": "tegning", "programme": "program", "company": "selskapet", "other": "annet", "unknown": "uklart"}


@lru_cache(maxsize=1)
def _insider_study() -> dict:
    from importlib import resources

    import yaml

    p = resources.files("osloquant").joinpath("resources/insider_study.yaml")
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, FileNotFoundError):
        return {}


def insider_study_line(side: str = "buy") -> str:
    st = (_insider_study().get("results") or {}).get(side) or {}
    h = st.get("h60") or {}
    if not h.get("n"):
        return ""
    m = _insider_study().get("measured") or {}
    word = "kjøp" if side == "buy" else "salg"
    ci = f'[{h["ci_lo"] * 100:+.1f}, {h["ci_hi"] * 100:+.1f}]' if h.get("ci_lo") is not None else "–"
    top = f'; de to største aksjene bærer {_p(h["top2_stocks_share"])} av summen' if h.get("top2_stocks_share") is not None else ""
    return (f'<div class="src" style="white-space:normal">Innsideres {word} på Oslo Børs {E(str(m.get("from")))}–{E(str(m.get("to")))}, 60 handelsdager: '
            f'snitt {pct(h["mean_excess"])} mot de 64 aksjene {ci} (95 %), median {pct(h["median_excess"])}, trimmet 5 % {pct(h.get("trimmed_5"))}, '
            f'positiv i {_p(h["hit"])} av {_int(h["n"])} tilfeller, t {h.get("t_cluster")} med klynger på måned × aksje{top}. '
            'Se docs/dashboard/insider-study.md – ikke en fordel man kan handle på.</div>')


def insider_block(code: str, ins: dict | None) -> str:
    """Primary-insider notifications and public short positions for one stock (dashboard/insiders.py)."""
    if ins is None:
        return ""
    items = ins.get("items") or []
    rows = "".join(f'<tr><td>{pd.Timestamp(i["time"]).tz_convert("Europe/Oslo"):%d %b %Y}</td><td><span class="chip {"buy" if i["side"] == "buy" else "risk" if i["side"] == "sell" else ""}">'
                   f'{E(SIDE_NO.get(i["side"], i["side"]))}</span></td><td style="white-space:normal;text-align:left"><a href="{E(i["url"])}" target="_blank" rel="noopener">'
                   f'{E(i["title"][:110])}</a> <span class="src">«{E(i.get("why", ""))}»</span></td></tr>' for i in items)
    itab = (f'<table><tbody>{rows}</tbody></table>' if rows else '<p class="empty">no primary-insider notifications in the cache</p>')
    s = ins.get("shorts")
    if s:
        hold = ", ".join(f"{E(h)} {v:.2f} %" for h, v in s["holders"][:5]) or "ingen over 0,5 %"
        ch = ins.get("short_change_30")
        sh = (f'<p><b>{s["now"]:.2f} %</b> av aksjene shortet offentlig ({E(s["date"])})'
              + (f', {ch:+.2f} prosentpoeng siste 30 dager' if ch is not None else '') + f'. Posisjoner: {hold}.</p>{ins.get("short_chart", "")}'
              f'<div class="src">Finanstilsynet, shortregisteret: bare posisjoner på 0,5 % eller mer er offentlige, og bare de siste to årene; '
              f'{E(str(s.get("fetched_at") or ""))}.</div>')
    else:
        sh = ('<p class="empty">Not in the short register: no public short position of 0.5 % or more in the last two years '
              '(or not fetched yet – oq dashboard --refresh).</p>')
    return (f'<div class="grid2"><div class="card"><h3>Innsidehandler (meldepliktige, siste 12 mnd)</h3>{itab}{insider_study_line("buy")}'
            '<div class="src">Oslo Børs NewsWeb, kategori «Meldepliktig handel for primærinnsidere» (privat bruk). Typen er lest av meldingsteksten '
            '(ordet i «» avgjorde); program, opsjoner og selskapets egne aksjer er ikke kjøp.</div></div>'
            f'<div class="card"><h3>Shortposisjoner</h3>{sh}</div></div>')


def insider_front(rows: list[dict], shorts_moved: list[dict], static: bool = False) -> str:
    """Front page: insider trades and short moves in followed stocks over the last seven days."""
    L = lambda c, t=None: link(c, t, static)  # noqa: E731
    a = "".join(f'<li>{when(i["time"])} {L(i["code"])} <b>{E(SIDE_NO.get(i["side"], i["side"]))}</b> – '
                f'<a href="{E(i["url"])}" target="_blank" rel="noopener">{E(i["title"][:90])}</a></li>' for i in rows)
    b = "".join(f'<li>{L(m["code"])} short {m["now"]:.2f} % ({m["change"]:+.2f} pp på 7 dager, {E(m["date"])})'
                + (f' – {E(m["holders"][0][0])}' if m["holders"] else '') + '</li>' for m in shorts_moved)
    if not a and not b:
        body = '<p class="empty">No insider trade or short move of 0.25 pp or more in followed stocks in the last 7 days.</p>'
    else:
        body = f'<ul class="news">{a}{b}</ul>'
    return (f'<h2>Innsidere og short i aksjer du følger</h2><div class="card">{body}<div class="src">Innsidehandler: NewsWeb (kjøp, salg, tegning). '
            'Short: Finanstilsynet (endring på minst 0,25 prosentpoeng).</div></div>')


METRIC_NAMES = {"revenue": "Revenue", "ebitda": "EBITDA", "ebitda_pre16": "EBITDA before IFRS 16", "ebit_pre16": "EBIT before IFRS 16",
                "net_debt": "Net debt", "clubs": "Clubs", "members_k": "Members (thousand)", "arpm": "ARPM (NOK/month)",
                "personnel_pct_q": "Personnel in % of revenue, quarter", "personnel_pct_ltm": "Personnel in % of revenue, LTM",
                "arpm_yoy": "ARPM growth y/y", "eps": "EPS (NOK)", "profit": "Profit for the period"}
_RATIO = ("pct", "yoy", "margin")


def _fmt_metric(key: str, v) -> str:
    if v is None:
        return "–"
    return pct(v, 1, False) if any(r in key for r in _RATIO) else (f"{v:,.0f}".replace(",", " ") if abs(v) >= 100 else f"{v:g}")


def report_block(code: str, rep: dict | None) -> str:
    """The latest quarterly report read against the previous quarter, consensus and the case (dashboard/reports.py)."""
    if rep is None:
        return ""
    s = rep.get("summary")
    if not s:
        return ('<div class="card"><h3>Siste kvartalsrapport</h3><p class="empty">No report read yet: oq dashboard --refresh reads new reports '
                'from NewsWeb for companies configured in ~/osloquant-home/reports.yaml.</p></div>')
    prev = ((s.get("previous") or {}).get("metrics") or {})
    cons = (s.get("consensus") or {}).get("values") or {}
    rows = []
    for key, f in s["figures"].items():
        if key.startswith("pl_"):
            continue
        cur, ly = f["value"], f["columns"].get("q_ly")
        pv = (prev.get(key) or {}).get("value")
        qoq = cur / pv - 1 if pv else None
        yoy = cur / ly - 1 if ly else None
        cv = cons.get(key)
        rows.append(f'<tr><td>{E(METRIC_NAMES.get(key, key))}</td><td><b>{_fmt_metric(key, cur)}</b></td>'
                    f'<td>{_fmt_metric(key, pv)}</td><td class="{cls(qoq)}">{pct(qoq)}</td><td>{_fmt_metric(key, ly)}</td><td class="{cls(yoy)}">{pct(yoy)}</td>'
                    f'<td>{_fmt_metric(key, cv)}</td><td class="{cls(cur / cv - 1 if cv else None)}">{pct(cur / cv - 1) if cv else "–"}</td>'
                    f'<td class="src">p. {f["page"]}{" ✓" if f["checked"].startswith("matches") else ""}</td></tr>')
    for key in ("personnel_pct_q", "personnel_pct_ltm"):
        if key in s["metrics"]:
            m = s["metrics"][key]
            pv = (prev.get(key) or {}).get("value")
            rows.append(f'<tr><td>{E(METRIC_NAMES.get(key, key))}</td><td><b>{_fmt_metric(key, m["value"])}</b></td><td>{_fmt_metric(key, pv)}</td>'
                        f'<td>{"" if pv is None else format((m["value"] - pv) * 100, "+.1f") + " pp"}</td>'
                        f'<td>{_fmt_metric(key, (s["metrics"].get("personnel_pct_q_ly") or {}).get("value")) if key == "personnel_pct_q" else "–"}</td><td></td><td>–</td><td></td>'
                        f'<td class="src">{E(m["how"])}</td></tr>')
    figures = ('<table class="odds"><thead><tr><th></th><th>Dette kvartal</th><th>Forrige kvartal</th><th>Endring</th><th>Samme kvartal i fjor</th>'
               '<th>Endring</th><th>Konsensus</th><th>Avvik</th><th>Kilde</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table>')
    case = s.get("case") or {}
    crow = []
    for r in (rep.get("spec") or {}).get("vs_case") or []:
        v, cv = (s["metrics"].get(r["metric"]) or {}).get("value"), case.get(r["case"])
        if r.get("pct"):
            diff = "–" if v is None or cv is None else f'{(v - cv) * 100:+.1f} pp'
        else:
            diff = "–" if v is None or not cv else pct(v / cv - 1)
        crow.append(f'<tr><td>{E(r["label"])}</td><td><b>{_fmt_metric(r["metric"], v)}</b></td><td>{_fmt_metric(r["metric"] + ("_pct" if r.get("pct") else ""), cv)}</td><td>{diff}</td></tr>')
    case_t = ((f'<h3 style="margin-top:14px">Mot forutsetningene i casen ({s["year"]}E, EST)</h3><table class="odds"><thead><tr><th></th><th>Rapporten</th><th>Casen</th>'
               '<th>Avvik</th></tr></thead><tbody>' + "".join(crow) + '</tbody></table>') if crow and case else
              '<p class="empty">No case model values for this year.</p>')
    krow = []
    for k in s["kill"]:
        st = k["status"]
        cl = "k" if st == "triggered" else ("warn-t" if "nearer" in st else "")
        thr = "" if k.get("threshold") is None else f'{k["op"]} {_fmt_metric(k["metric"], k["threshold"])}'
        note = f'<div class="src" style="white-space:normal">{E(k["note"])}</div>' if k.get("note") else ""
        krow.append(f'<tr><td style="white-space:normal">{E(k["criterion"])}{note}</td><td class="{cl}"><b>{E(st)}</b></td><td>{_fmt_metric(k.get("metric") or "", k.get("now"))}</td>'
                    f'<td>{_fmt_metric(k.get("metric") or "", k.get("previous"))}</td><td>{E(thr)}</td></tr>')
    kill_t = ('<h3 style="margin-top:14px">Kill-kriterier</h3><table class="odds"><thead><tr><th>Kriterium</th><th>Status</th><th>Nå</th><th>Forrige rapport</th>'
              '<th>Grense</th></tr></thead><tbody>' + "".join(krow) + '</tbody></table>')
    cinfo = s.get("consensus")
    csrc = (f'Konsensus: {E(cinfo["source"])}, {cinfo.get("contributors") or "?"} analytikere, publisert {E(str(cinfo.get("published")))} '
            f'(<a href="{E(cinfo["url"])}" target="_blank" rel="noopener">kilde</a>).' if cinfo else 'Ingen offentlig konsensus funnet for dette kvartalet.')
    foot = (f'<div class="src">Tallene er lest fra rapportens tabeller (side oppgitt; ✓ = stemmer med endringen rapporten selv skriver). LTM = siste hele år + hittil i år − samme periode i fjor. '
            f'{csrc} Casen: {E(case.get("_file", "–"))} (Equity Research Toolkit, privat), verdier for {s["year"]} er casens egne estimater (EST). '
            f'Lest {E(s["analysed_at"].replace("T", " ").replace("Z", " UTC"))}. Ingen tekst er generert: alt er tall med kilde.</div>')
    head = (f'<h3>Siste kvartalsrapport: <a href="{E(s["url"])}" target="_blank" rel="noopener">{E(s["title"])}</a> '
            f'<span class="src">({when(s["published"])}, <a href="/report/{E(code)}/{s["message_id"]}.pdf">PDF</a>)</span></h3>')
    return f'<div class="card">{head}{figures}{case_t}{kill_t}{foot}</div>'


REALITY = ('<div class="warn"><b>En realitetssjekk, ikke en prognose.</b> Tallene sier hvor ofte kurser som denne har nådd ett av '
           'nivåene først i historikken. Rapporter, renter og nyheter kan gjøre ting historikken aldri har gjort.</div>')


def _int(n) -> str:
    return f"{int(n):,}".replace(",", "\u202f")


def _p(x) -> str:
    return "–" if x is None or x != x else f"{x * 100:.0f} %"


def odds_block(o, view: dict) -> str:
    """Target first / kill level first / neither, by simulation and by historical cases (dashboard/odds.py)."""
    if o is None:
        return ""
    stand_in = (' <span class="src">(kill-nivået er bear-verdien som stedfortreder – sett et eget kill-nivå i neste vurdering)</span>'
                if "bear" in o.kill_source else "")
    head = f'<h3>Utfallsodds: kursmål {o.target:g} først, kill-nivå {o.kill:g} først, eller ingen av dem{stand_in}</h3>'
    if o.note:
        return f'<div class="card">{head}{REALITY}<p class="empty">{E(o.note)}</p></div>'
    rows = []
    for lab in o.simulation:
        s, u, w = o.simulation[lab], o.universe[lab], o.own[lab]
        cell = lambda x: (f'<td class="t">{_p(x.target)}</td><td class="k">{_p(x.kill)}</td><td>{_p(x.neither)}</td>')  # noqa: E731
        rows.append(f'<tr><td>{E(lab)}</td>{cell(s)}{cell(u)}<td>{_int(u.n)}</td>{cell(w)}<td>{_int(w.n) if w.n else E(w.note or "–")}</td></tr>')
    s0 = next(iter(o.simulation.values()))
    u0 = o.universe[list(o.universe)[-1]]
    w0 = o.own[list(o.own)[-1]]
    table = ('<table class="odds"><thead><tr><th></th><th class="grp" colspan="3">Simulering, egne avkastninger</th>'
             '<th class="grp" colspan="4">Historiske tilfeller, alle 64 aksjer</th><th class="grp" colspan="4">Aksjens egen historikk</th></tr>'
             '<tr><th>Horisont</th>' + '<th>Mål først</th><th>Kill først</th><th>Ingen</th>' * 1
             + '<th>Mål først</th><th>Kill først</th><th>Ingen</th><th>Tilfeller</th>' * 2 + '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>')
    from osloquant.dashboard.odds import breakeven

    r, be = breakeven(o.price, o.target, o.kill)
    s12 = list(o.simulation.values())[-1]
    decided = s12.target + s12.kill
    share = s12.target / decided if decided else float("nan")
    gap = share - be
    lean = ("nær myntkast" if abs(gap) < 0.05 else ("heller mot målet" if gap > 0 else "heller mot kill-nivået") if abs(gap) < 0.15
            else ("klart mot målet" if gap > 0 else "klart mot kill-nivået"))
    verdict = (f'<p style="margin:8px 0"><b>Break-even:</b> målet ligger {pct(o.target / o.price - 1, 0)} unna og kill-nivået {pct(o.kill / o.price - 1, 0)} '
               f'(R = {r:.2f}), så målet må nås først i {_p(be)} av tilfellene som når et nivå. Simuleringen over 12 mnd (EST): {_p(share)} – {lean}.'
               + (f' «Ingen» er {_p(s12.neither)}: da avgjør kursen ved horisonten, ikke nivåene.' if s12.neither > 0.4 else '') + '</p>')
    mine = ""
    if all(view.get(k) is not None for k in ("p_bear", "p_base", "p_bull")):
        mine = (f'<div class="src" style="margin-top:6px">Ditt syn: bear {_p(view["p_bear"])} / base {_p(view["p_base"])} / bull {_p(view["p_bull"])} – '
                'sannsynligheter for verdier ved horisonten, ikke for hvilket nivå som nås først. Ikke samme spørsmål, men et stort avvik er verdt en ny titt.</div>')
    foot = (f'<div class="src">Kurs {o.price:.2f} ({o.asof:%d %b %Y}, Yahoo Finance daglig sluttkurs via oslo-quant, forsinket; justerte kurser, utbytte reinvestert). Kill-nivå {o.kill:g}: {E(o.kill_source)}. '
            f'Simulering: 10 000 baner av {E(o.code)}s egne daglige avkastninger siden {E(s0.extra.get("since", "?"))}, trukket i blokker på 20 handelsdager, fast frø; '
            f'utvalgets egen årlige drift {pct(s0.extra.get("drift"))} er med; volatilitet i utvalget {pct(s0.extra.get("vol"), 0, False)}, nå {pct(o.sigma, 0, False)}. '
            f'Historiske tilfeller: hver månedsstart siden 2010 på de 64 aksjene, nivåene lagt like langt unna målt i aksjens egen volatilitet den gang '
            f'({u0.extra.get("stocks", 0)} aksjer; vinduene overlapper, så 12 mnd-kolonnen tilsvarer omtrent {_int(u0.extra.get("independent", 0))} uavhengige tilfeller'
            + f'; egen historikk ca. {w0.extra.get("independent", 0)}). Et nivå teller når en daglig sluttkurs når det. Bare dagens 64 aksjer: selskaper som forsvant fra børsen mangler.</div>')
    return f'<div class="card">{head}{REALITY}{table}{verdict}{mine}{foot}</div>'


def bracket_line(signal: str) -> str:
    b = ((_odds().get("signals") or {}).get(signal) or {}).get("bracket") or {}
    h = b.get("h20")
    if not h or not h.get("events"):
        return robustness_line(signal)
    return (f'<span class="bracket">Kjøpt på signalet: mål først {_p(h["target"])} · stopp først {_p(h["stop"])} · ingen {_p(h["neither"])} '
            f'innen 20 dager, snitt {h["mean_R"]:+.2f} R etter 0,5 % kostnad (mål og stopp 2 × ATR, {_int(h["events"])} tilfeller)</span>'
            + robustness_line(signal))


def grade_words(g: str, checks: dict | None) -> str:
    """'stabil (4 av 4 sjekker)' – counted from the checks that actually ran, so the words never promise a check that
    was skipped."""
    done = [v for v in (checks or {}).values() if v is not None]
    n, ok = len(done), sum(bool(v) for v in done)
    if g == "A":
        return f"stabil ({ok} av {n} sjekker)"
    if g == "D":
        return f"ustabil ({ok} av {n})"
    return f"{ok} av {n} sjekker"


def robustness_line(signal: str) -> str:
    """How the signal's odds held up: raw return and the universe's over the same window, the 95 % interval, the
    two-way clustered t, three sub-periods, the survivors, the dominant stock, and a grade (DECISIONS D20, D23)."""
    sig = (_odds().get("signals") or {}).get(signal) or {}
    r = sig.get("robustness")
    if not r or "periods" not in r:
        return ""
    per = " · ".join(f'{E(lab)} {pct(v.get("exc60"))}' for lab, v in r["periods"].items())
    sv = (r.get("survivors") or {}).get("exc60")
    lo, hi, tc = sig.get("lo60"), sig.get("hi60"), sig.get("tc60")
    ci = f"[{lo * 100:+.1f}, {hi * 100:+.1f}]" if lo is not None and hi is not None else "–"
    share = sig.get("topshare60")
    top = ("" if share is None else f'{E(str(sig.get("top60") or "–"))} bærer {_p(share)} av summen'
           + (" (summen er nær null, så andelen sier lite)" if share > 1 else ""))
    g60, g20 = r.get("grade60", "?"), r.get("grade20", "?")
    cls = "buy" if g60 == "A" and (sig.get("exc60") or 0) > 0 else "risk" if g60 == "A" else "warn-t" if g60 == "B" else ""
    pb = r.get("placebo60") or {}
    if pb.get("mean") is not None:
        plac = (f'tilfeldige dager med samme aksje- og månedsmiks ({pb["reps"]} trekk): {pct(pb["mean"])} [{pb["lo"] * 100:+.1f}, {pb["hi"] * 100:+.1f}], '
                f'z {pb["z"]:+.1f} – {"utenfor båndet" if pb.get("outside") else "innenfor båndet: aksjene og månedene forklarer tallet, ikke dagen"}')
    else:
        plac = "placebo-bånd ikke kjørt"
    return (f'<span class="bracket">60 d: aksjen {pct(sig.get("raw60"))}, de 64 i samme vindu {pct(sig.get("bench60"))}, meravkastning {pct(sig.get("exc60"))} '
            f'{ci} (95 %), t {"–" if tc is None else format(tc, ".1f")} med klynger på tid × aksje · per periode {per} · '
            f'{r.get("survivor_stocks", "?")} aksjer notert fra start {pct(sv)} · {top} · {plac} → '
            f'<b class="{cls}">grad {E(g60)} – {E(grade_words(g60, r.get("checks60")))}</b> (20 d: {E(g20)}). Bare dagens 64 aksjer (overlevere).</span>')


def chip_class(a) -> str:
    """Green only when the signal's raw 20-day return beat the round trip and its 60-day grade is A; red when the grade
    is A on the risk side; otherwise neutral – the colour must not say more than the odds do (DECISIONS D23)."""
    sig = (_odds().get("signals") or {}).get(a.signal) or {}
    g = (sig.get("robustness") or {}).get("grade60")
    raw20, cost = sig.get("raw20"), (_odds().get("measured") or {}).get("round_trip_cost", 0.005)
    if g == "A" and (sig.get("exc60") or 0) > 0 and raw20 is not None and raw20 > cost:
        return "buy"
    if g == "A" and (sig.get("exc60") or 0) < 0:
        return "risk"
    return ""


def _n(a) -> str:
    """The number of past signals behind the odds, from the measured odds file."""
    ev = ((_odds().get("signals") or {}).get(a.signal) or {}).get("events")
    return f" · n {_int(ev)}" if ev else ""


@lru_cache(maxsize=1)
def _odds() -> dict:
    return sg.load_odds()


def when(t: str) -> str:
    """A feed's UTC timestamp as Oslo time, e.g. '20 Oct 10:32'."""
    try:
        ts = pd.Timestamp(t)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
        return E(f"{ts.tz_convert('Europe/Oslo'):%d %b %H:%M}")
    except (ValueError, TypeError):
        return E(t)


def _position(r: dict) -> str:
    if not r.get("position_shares") and r.get("kill_level") is None:
        return ""
    kl = f'kill-nivå {r["kill_level"]:g}' if r.get("kill_level") is not None else ""
    if r.get("triggered_at_entry"):
        kl += (" · " if kl else "") + f'<span class="k">logget med utløst kill-kriterium ({len(r["triggered_at_entry"])})</span>'
    pos = (f'; papirposisjon {_int(r["position_shares"])} aksjer = NOK {_int(r["position_value"])}, tap ved kill-nivået NOK {_int(r["loss_at_kill"])} '
           f'(bindende: {E(r.get("sizing", {}).get("binding", "?"))})' if r.get("position_shares") else "")
    return f'<div class="src">{kl}{pos}</div>'


def _rationale(r: dict) -> str:
    """The full rationale (folded when long); rows seeded from a written case point to the case instead."""
    t = r.get("thesis") or ""
    if not t:
        return f'<span class="src">no rationale text – seeded from {E(r.get("source") or "the research book")}</span>'
    if len(t) <= 160:
        return E(t)
    return f'<details><summary>{E(t[:140])}…</summary>{E(t)}</details>'


def case_block(c, px: float, rd: dict | None) -> str:
    v = c.view or {}
    rows = []
    for r in c.history:
        if r["kind"] == "judgement":
            desk = (f' <a href="/desk/run/{E(r["desk_run"])}/{E(c.code)}" title="debattloggen fra desken">desk</a>' if r.get("desk_run") else "")
            rows.append(f'<tr><td>#{r["seq"]}</td><td>{E(r["date"])}</td><td>{E(r["rating"])}</td><td>{r["price"]:g}</td><td>{r["target"]:g}</td>'
                        f'<td>{r.get("bear", "–")} / {r.get("base", "–")} / {r.get("bull", "–")}</td><td>{r.get("p_bear", "–")} / {r.get("p_base", "–")} / {r.get("p_bull", "–")}</td>'
                        f'<td>{_rationale(r)}{_position(r)}{desk}</td><td class="src">{E(r.get("logged_at", ""))}</td></tr>')
        elif r["kind"] == "kill_check":
            rows.append(f'<tr><td>#{r["seq"]}</td><td>{E(r["date"])}</td><td colspan="5">kill check: {E(r["criterion"])} – '
                        f'<b>{"BREACHED" if r["breached"] else "intact"}</b>, action: {E(r["action"])}</td><td></td><td class="src">{E(r.get("logged_at", ""))}</td></tr>')
    hist = ('<table><thead><tr><th>#</th><th>Date</th><th>View</th><th>Price</th><th>TP</th><th>Bear/base/bull</th><th>Probabilities</th><th>Rationale</th><th>Logged (UTC)</th></tr></thead><tbody>'
            + ("".join(rows) or '<tr><td colspan="9" class="empty">no rows in the log yet – the view below is from researchbook.yaml</td></tr>') + '</tbody></table>')
    from osloquant.signals_page import ladder_svg

    ladder = ladder_svg(px, {"bear": v.get("bear"), "dcf": v.get("base"), "target": v.get("target"), "bull": v.get("bull")}) if v.get("target") else ""
    if rd and not rd.get("error"):
        rdh = (f'<table><thead><tr><th></th><th>Market-implied</th><th>Ours</th><th>Reference</th></tr></thead><tbody>'
               f'<tr><td>EBIT margin, final year</td><td><b>{pct(rd["rd_m_last"], 1, False)}</b></td><td>{pct(rd["rd_m_last_ours"], 1, False)}</td><td>{pct(rd["rd_m_last_ref"], 1, False)} last actual</td></tr>'
               f'<tr><td>Revenue CAGR</td><td><b>{pct(rd["rd_cagr"], 1, False)}</b></td><td>{pct(rd["rd_cagr_ours"], 1, False)}</td><td>{pct(rd["rd_cagr_ref"], 1, False)} history</td></tr>'
               f'<tr><td>WACC</td><td><b>{pct(rd["rd_wacc"], 1, False)}</b></td><td>{pct(rd["rd_wacc_ours"], 1, False)}</td><td></td></tr></tbody></table>'
               f'<div class="src">Reverse DCF at the model price {rd["price"]:.2f} ({rd["price_date"]:%d %b %Y}); DCF {rd["dcf"]:.1f}, TP {rd["tp"]} {E(str(rd["rating"]))}; '
               f'each pp of margin ≈ NOK {rd["rd_k"]:.1f}/share. Source: {E(rd["file"])} (Equity Research Toolkit, private). Model values are estimates (EST).</div>')
    elif rd:
        rdh = f'<p class="err">{E(rd["error"])}</p>'
    else:
        rdh = '<p class="empty">no model linked (researchbook.yaml: model: {xlsx, map})</p>'
    kill = "".join(f"<li>{E(k)}</li>" for k in c.kill) or "<li class=empty>none</li>"
    return (f'<h2>Research book</h2><div class="grid2"><div class="card"><h3>Current view – {E(v.get("rating", "?"))} TP {v.get("target", "?")} '
            f'<span class="src">({E(str(v.get("date")))}, {E(c.view_source)})</span></h3><div class="ladder">{ladder}</div>'
            f'<div class="src">Bear / DCF-base / TP / bull are the view\'s own estimates (EST).</div><h3 style="margin-top:12px">Kill criteria</h3><ul>{kill}</ul></div>'
            f'<div class="card"><h3>Hva priser markedet inn (reverse DCF)</h3>{rdh}</div></div>'
            f'<div class="card"><h3>Vurderingshistorikk (append-only)</h3>{hist}</div>')


def judge_form(code: str, name: str, px: float, label: str, f: dict, c, sz: dict | None = None) -> str:
    v = (c.view if c else None) or {}
    val = lambda k, d="": E(str(f.get(k, d) if f.get(k, d) is not None else ""))  # noqa: E731
    sel = lambda opt: " selected" if (f.get("rating") or v.get("rating")) == opt else ""  # noqa: E731
    kill_default = "\n".join(c.kill) if c and not f else ""
    ck = str(f.get("checklist") or "")
    dr = str(f.get("desk_run") or "")
    pre = (f'<div class="ok">Sjekklisten fra «Før du kjøper» er krysset av ({E(ck.replace(",", ", "))}) og skrives på raden.</div>' if ck else
           f'<div class="warn"><b>Skal du kjøpe?</b> Gå via <a href="/stock/{E(code)}/pretrade">Før du kjøper</a> først: hva markedet priser inn, oddsene, '
           'motargumentene, hendelsene før horisonten, posisjonsstørrelsen og sjekklisten – på én side. Et syn uten sjekkliste kan logges, men merkes slik.</div>')
    if dr:
        pre += f'<div class="ok">Desk-kjøringen {E(dr)} vedlegges raden (feltet desk_run); debattloggen står over skjemaet. Tallene under er forhåndsutfylt fra synet i boken og Risk-rollen – ingenting er skrevet for deg.</div>'
    return f"""<h2 id="judge">Ny vurdering</h2><div class="card">{pre}<form class="judge" method="post" action="/stock/{E(code)}/judge">
<input type="hidden" name="checklist" value="{E(ck)}"><input type="hidden" name="desk_run" value="{E(dr)}">
<div class="src">Writes one new row to the judgement log (~/osloquant-home/judgements.jsonl) and, if {E(code)} is not in the research book, adds it.
Nothing earlier can be changed: a new view is a new row. Date = today; price = the last close {px:.2f} ({E(label)}).</div>
<input type="hidden" name="name" value="{E(name)}">
<div class="row4"><div><label>Mitt syn</label><select name="rating"><option value="">–</option><option{sel("BUY")}>BUY</option><option{sel("HOLD")}>HOLD</option><option{sel("SELL")}>SELL</option></select></div>
<div><label>Kursmål (12 mnd)</label><input name="target" inputmode="decimal" value="{val("target")}"></div>
<div><label>Horisont (mnd)</label><input name="horizon" inputmode="numeric" value="{val("horizon", 12)}"></div>
<div><label>Kill-nivå (kurs)</label><input name="kill_level" inputmode="decimal" placeholder="kursen der caset er brutt" value="{val("kill_level", v.get("kill_level") or "")}"></div></div>
<div class="row3"><div><label>Bear (verdi)</label><input name="bear" inputmode="decimal" value="{val("bear")}"></div>
<div><label>Base (verdi)</label><input name="base" inputmode="decimal" value="{val("base")}"></div>
<div><label>Bull (verdi)</label><input name="bull" inputmode="decimal" value="{val("bull")}"></div></div>
<div class="row3"><div><label>Sannsynlighet bear</label><input name="p_bear" inputmode="decimal" placeholder="0.25" value="{val("p_bear")}"></div>
<div><label>Sannsynlighet base</label><input name="p_base" inputmode="decimal" placeholder="0.50" value="{val("p_base")}"></div>
<div><label>Sannsynlighet bull</label><input name="p_bull" inputmode="decimal" placeholder="0.25" value="{val("p_bull")}"></div></div>
<div class="row3"><div><label>Konsensus kursmål (valgfritt, offentlig kilde)</label><input name="consensus_target" inputmode="decimal" value="{val("consensus_target")}"></div>
<div style="grid-column:span 2"><label>Kilde og dato for konsensus (påkrevd hvis mål)</label><input name="consensus_source" placeholder="f.eks. selskapets IR-side, 2026-10-22" value="{val("consensus_source")}"></div></div>
<label>Begrunnelse (påkrevd)</label><textarea name="rationale" required minlength="20">{val("rationale")}</textarea>
<label>Kill-kriterier (påkrevd, ett per linje)</label><textarea name="kill" required>{E(f.get("kill_text", kill_default))}</textarea>
{saw_claude_box(c, f)}
{ack_box(code, f)}
{sizing_box(px, sz, val("position_shares"))}
<button class="go" type="submit">Logg vurderingen</button></form></div>"""


def saw_claude_box(c, f: dict) -> str:
    """Asked only when Claude has a view on the company: the answer splits your views into blind and anchored (D31)."""
    if not (c and c.claude_view):
        return ""
    ch = lambda v: " checked" if f.get("saw_claude") == v else ""  # noqa: E731
    return ('<input type="hidden" name="claude_exists" value="1"><div class="warn"><b>Hadde du lest Claudes syn på selskapet før du skrev dette?</b> '
            f'<div style="display:flex;gap:24px;margin:8px 0">'
            f'<label style="display:inline-flex;align-items:center;gap:6px;margin:0"><input type="radio" style="width:auto;margin:0" name="saw_claude" value="no"{ch("no")}> Nei – blindt</label>'
            f'<label style="display:inline-flex;align-items:center;gap:6px;margin:0"><input type="radio" style="width:auto;margin:0" name="saw_claude" value="yes"{ch("yes")}> Ja</label></div>'
            '<div class="src">Svaret lagres på raden og deler kalibreringen i blinde syn og syn skrevet etter Claudes.</div></div>')


def ack_box(code: str, f: dict) -> str:
    """Shown when the latest report reading has a kill criterion over the line: the view can still be logged, but only
    knowingly, and the row records it (D22)."""
    from osloquant.dashboard import book as bk

    hits = bk.triggered_now(code)
    if not hits:
        return ""
    items = "".join(f"<li>{E(h)}</li>" for h in hits)
    checked = " checked" if f.get("ack_triggered") else ""
    return (f'<div class="warn"><b>Et kill-kriterium er allerede over streken i siste rapport:</b><ul>{items}</ul>'
            f'<label style="font-weight:600"><input type="checkbox" name="ack_triggered" value="1"{checked}> Jeg vet det – logg et BUY-syn likevel '
            '(raden merkes «logget med utløst kill-kriterium»)</label></div>')


def sizing_box(px: float, sz: dict | None, current: str = "") -> str:
    """Position size from the paper sum and the max loss in dashboard.yaml, the kill level being the stop (sizing.py).
    The numbers update as the kill level and the position are typed; the server checks them again on submit."""
    if not sz:
        return ('<div class="src" style="margin-top:10px">Posisjonsstørrelse: ingen grenser satt. Legg inn <code>sizing</code> '
                '(paper_capital, max_loss, max_position) i ~/osloquant-home/dashboard.yaml for størrelse og sperre.</div>')
    cfg = sz["cfg"]
    attrs = (f'data-price="{px}" data-cost="{sz["cost"]}" data-cap="{cfg["paper_capital"]}" data-maxloss="{cfg["max_loss"]}" '
             f'data-maxpos="{cfg.get("max_position", 1)}" data-free="{sz["free"]}" data-total="{cfg.get("max_total_loss") or ""}" data-openloss="{sz["open_loss"]}"')
    return f"""<div class="sizing" {attrs} style="margin-top:12px;padding:10px 12px;border:1px solid var(--line);border-radius:8px">
<b>Posisjonsstørrelse (papir, bare for BUY)</b>
<div class="row3"><div><label>Posisjon (antall aksjer)</label><input name="position_shares" inputmode="numeric" placeholder="tom = største tillatte" value="{current}"></div>
<div style="grid-column:span 2"><div id="sz-out" style="margin-top:26px;font-size:13.5px">Skriv inn et kill-nivå under kursen.</div></div></div>
<div class="src">Papirsum NOK {_int(cfg["paper_capital"])}, maks tap NOK {_int(cfg["max_loss"])} per vurdering, maks {float(cfg.get("max_position", 1)) * 100:.0f} % i én aksje
{f', maks NOK {_int(cfg["max_total_loss"])} for alle åpne BUY-vurderinger' if cfg.get("max_total_loss") else ''} (dashboard.yaml). Fritt nå: NOK {_int(sz["free"])}.
Tapet ved kill-nivået er et gulv, ikke et tak: en rapport eller et gap kan åpne kursen under det. Tap per aksje = kurs − kill-nivå + {sz["cost"] * 100:.1f} % tur-retur.</div></div>
<script>
(function(){{
  var box=document.querySelector('.sizing'); if(!box) return;
  var f=box.closest('form'), out=document.getElementById('sz-out'), d=box.dataset;
  function num(s){{ s=(s||'').replace(/\\s/g,'').replace(',','.'); return s===''?NaN:parseFloat(s); }}
  function fmt(x){{ return Math.round(x).toLocaleString('nb-NO'); }}
  function upd(){{
    var r=f.rating.value, px=+d.price, k=num(f.kill_level.value);
    if(r!=='BUY'){{ out.textContent='Ingen posisjon for '+(r||'et syn uten retning')+'.'; return; }}
    if(!(k<px)){{ out.textContent='Kill-nivået må ligge under kursen '+px.toFixed(2)+'.'; return; }}
    var lps=px-k+(+d.cost)*px, lim={{'maks tap':Math.floor(+d.maxloss/lps),'maks andel':Math.floor(+d.cap*(+d.maxpos)/px),'fri papirsum':Math.floor(+d.free/px)}};
    if(d.total) lim['samlet tap']=Math.floor(Math.max(+d.total-(+d.openloss),0)/lps);
    var bind=Object.keys(lim).reduce(function(a,b){{return lim[a]<=lim[b]?a:b;}}), max=Math.max(lim[bind],0);
    var n=num(f.position_shares.value); if(isNaN(n)) n=max;
    var loss=n*lps, over=n>max;
    out.innerHTML='Største tillatte: <b>'+fmt(max)+' aksjer</b> (bindende: '+bind+'). '+fmt(n)+' aksjer = NOK '+fmt(n*px)+' ('+(100*n*px/(+d.cap)).toFixed(1)+' % av papirsummen); '+
      'tap hvis kill-nivået nås: <b style="color:'+(over?'var(--risk)':'inherit')+'">NOK '+fmt(loss)+'</b>'+(over?' – over grensen, blir avvist.':'.');
  }}
  ['input','change'].forEach(function(e){{ f.addEventListener(e,upd); }}); upd();
}})();
</script>"""


# ------------------------------------------------------------------------------------------------ Kalibrering
def fingerprint_block(fp: dict | None) -> str:
    """Template marks across the open views (D30): shown as a warning when two companies share a number that should
    come from the company, as an all-clear otherwise."""
    if not fp or fp["views"] < 2:
        return ""
    if fp["marks"]:
        items = "".join(f'<li>{E(m["what"])} in {m["n"]} of {fp["views"]} views: {", ".join(link(c) for c in m["codes"])}</li>' for m in fp["marks"])
        inner = f'<div class="warn"><b>Samme tall i flere selskaper:</b><ul>{items}</ul></div>'
    else:
        inner = f'<div class="ok">No target, probability set or bull/bear spread is repeated across the {fp["views"]} open views.</div>'
    return ('<h2>Malspor</h2><div class="card">' + inner
            + '<div class="src">Two companies at different prices with the same target, or the same scenario probabilities, say more about the spreadsheet '
              'than about the companies. Not an error – a question to answer in the next view.</div></div>')


def calibration_page(table: pd.DataFrame, summary: dict, check, kills: list[dict], rel: dict | None = None, fp: dict | None = None,
                     h2h: dict | None = None, learn_html: str = "") -> str:
    body = ['<h1>Kalibrering</h1><div class="sub">What I said, what happened, how far off. Calls younger than their horizon are provisional and are not evidence.</div>']
    chain = "verifies" if check.ok else "BROKEN: " + "; ".join(check.problems[:3])
    body.append(f'<div class="src">Judgement log: {check.rows} rows, chain {E(chain)}, head {check.head[:16]}.</div>')
    tiles = []
    for label, key in (("Final (horizon reached)", "final"), ("All scored incl. provisional", "all_scored")):
        s = summary.get(key, {"n": 0})
        tiles.append(f'<div class="card"><h3>{E(label)}: {s["n"]} calls</h3>' + (
            f'<ul class="kv"><li>Direction right (vs OSEBX): <b>{pct(s["direction_hit_rate"], 0, False)}</b></li>'
            f'<li>Price vs target: mean {pct(s["mean_vs_target"])}, mean absolute {pct(s["mean_abs_vs_target"], 1, False)}</li>'
            f'<li>Mean total return {pct(s["mean_tsr"])}, excess vs OSEBX {pct(s.get("mean_excess_osebx"))}</li>'
            f'<li>Inside the bear-bull band: {pct(s.get("in_band_rate"), 0, False)}</li>'
            + (f'<li>Scenario Brier score: {s["mean_brier"]:.2f} (0 = perfect, 0.67 = uniform)</li>' if "mean_brier" in s else '') + '</ul>'
            if s["n"] else '<p class="empty">none yet</p>') + '</div>')
    body.append('<div class="grid2">' + "".join(tiles) + '</div>')
    body.append(benchmarks_block(table[table["analyst"] == "oscar"] if len(table) and "analyst" in table else table, summary))
    body.append(analysts_block(summary, h2h))
    if rel is not None:
        body.append(reliability_block(rel))
    body.append(learn_html)
    body.append(fingerprint_block(fp))
    if len(table):
        rows = "".join(
            f'<tr><td>#{r["seq"]}</td><td>{E({"claude": "Claude"}.get(r.get("analyst"), "du"))}</td><td>{link(r["code"])}</td><td>{E(r["date"])}</td><td>{E(r["rating"])}</td><td>{r["price"]:.2f}</td><td>{r["target"]:g}</td>'
            f'<td>{r.get("price_now", float("nan")):.2f}</td><td class="{cls(r.get("tsr"))}">{pct(r.get("tsr"))}</td><td class="{cls(r.get("excess_osebx"))}">{pct(r.get("excess_osebx"))}</td>'
            f'<td>{pct(r.get("vs_target"))}</td><td>{"" if pd.isna(r.get("in_band")) else ("yes" if r.get("in_band") else "no")}</td>'
            f'<td>{"✓" if r.get("direction_hit") is True else "✗" if r.get("direction_hit") is False else ""}</td><td>{E(r["status"])} ({r["days"]} d)</td></tr>'
            for _, r in table.iterrows())
        body.append('<h2>Per vurdering</h2><div class="card"><table><thead><tr><th>#</th><th>Hvem</th><th>Code</th><th>Date</th><th>View</th><th>Price</th><th>TP</th><th>Now</th>'
                    '<th>TSR</th><th>vs OSEBX</th><th>vs TP</th><th>In band</th><th>Direction</th><th>Status</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table><div class="src">Total return from the call price on the adjusted series (dividends included); OSEBX from the store; '
                    'prices delayed. Direction for BUY/SELL = sign of the excess over OSEBX.</div></div>')
        if {"tsr", "excess_osebx", "direction_hit"} <= set(table.columns):
            per = (table[table["analyst"] == "oscar"] if "analyst" in table else table).groupby("code").agg(n=("seq", "count"), tsr=("tsr", "mean"), ex=("excess_osebx", "mean"), hit=("direction_hit", "mean"))
            prow = "".join(f'<tr><td>{link(code)}</td><td>{int(r["n"])}</td><td>{pct(r["tsr"])}</td><td>{pct(r["ex"])}</td><td>{pct(r["hit"], 0, False)}</td></tr>' for code, r in per.iterrows())
            body.append(f'<h2>Per case</h2><div class="card"><table><thead><tr><th>Code</th><th>Calls</th><th>Mean TSR</th><th>Mean vs OSEBX</th><th>Direction right</th></tr></thead><tbody>{prow}</tbody></table></div>')
        else:
            body.append('<h2>Per case</h2><div class="card"><p class="empty">No call has a price after its date yet (a view logged today is scored from tomorrow).</p></div>')
    kb = sum(bool(k["breached"]) for k in kills)
    body.append(f'<h2>Kill-kriterier</h2><div class="card"><p>{len(kills)} checks logged, {kb} breached, '
                f'{sum(bool(k["breached"]) and str(k.get("action", "")).lower() not in ("held", "none", "nothing", "ignored") for k in kills)} acted on.</p>'
                '<div class="src">Log a check with oq book kill --code X --date YYYY-MM-DD --criterion "..." --breached/--intact --action "..."</div></div>')
    body.append(signal_brackets_block())
    return page("Kalibrering", "/calibration", "\n".join(body))


def benchmarks_block(table: pd.DataFrame, summary: dict) -> str:
    """Am I better than doing nothing? Three references per call: OSEBX (direction and excess), a forecast that the
    price stays where it is (target error against the naive error), and the public consensus target when one was
    logged with the view (DECISIONS D21)."""
    if not len(table):
        return ""
    scored = table[table["status"].isin(["final", "provisional"])] if "status" in table else table.iloc[0:0]
    if not len(scored) or "direction_hit" not in scored:
        return ('<h2>Er jeg bedre enn referansene?</h2><div class="card"><p class="empty">Nothing to compare yet: a view is scored against '
                'OSEBX, «kursen står stille» and consensus from its first session after the call.</p></div>')
    fin = scored[scored["status"] == "final"]
    rows = []
    for label, t in (("Final calls", fin), ("All scored (incl. provisional)", scored)):
        if not len(t):
            rows.append(f'<tr><td>{E(label)}</td><td colspan="4" class="empty">none yet</td></tr>')
            continue
        osebx = t["direction_hit"].dropna()
        flat = t["beat_flat"].dropna() if "beat_flat" in t else pd.Series(dtype=bool)
        cons = t["beat_consensus"].dropna() if "beat_consensus" in t else pd.Series(dtype=bool)
        cell = lambda b: f'<b>{pct(b.astype(bool).mean(), 0, False)}</b> <span class="src">({int(b.astype(bool).sum())} av {len(b)})</span>' if len(b) else '–'  # noqa: E731
        rows.append(f'<tr><td>{E(label)}</td><td>{cell(osebx)}</td><td>{pct(t["excess_osebx"].mean()) if t["excess_osebx"].notna().any() else "–"}</td>'
                    f'<td>{cell(flat)}</td><td>{cell(cons) if len(cons) else "<span class=src>no consensus logged</span>"}</td></tr>')
    return ('<h2>Er jeg bedre enn referansene?</h2><div class="card"><table class="odds"><thead><tr><th></th><th>Retning riktig mot OSEBX</th>'
            '<th>Meravkastning mot OSEBX, snitt</th><th>Kursmålet nærmere enn «kursen står stille»</th><th>Kursmålet nærmere enn konsensus</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table><div class="src">«Kursen står stille»: hvor ofte mitt kursmål bommet mindre på sluttkursen enn en '
            'prognose om uendret kurs. Konsensus: bare for vurderinger der et offentlig konsensusmål ble lagt inn med kilde i skjemaet. '
            'OSEBX fra lageret (Yahoo). Provisoriske vurderinger er ikke bevis.</div></div>')


def reliability_block(rel: dict) -> str:
    """Stated probability against realised frequency for bear/base/bull, with the binary Brier score."""
    n_final, pending = rel.get("final_calls", 0), rel.get("pending_calls", 0)
    head = '<h2>Oppgitt sannsynlighet mot det som skjedde</h2><div class="card">'
    if not rel.get("pairs"):
        return (head + f'<p class="empty">No final call with scenario probabilities yet ({pending} pending). The plot appears when the first '
                'horizon has passed; until then there is nothing to calibrate against.</p></div>')
    import plotly.graph_objects as go

    b = rel["buckets"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color="#9aa7b5", dash="dot"), name="perfect"))
    fig.add_trace(go.Scatter(x=[x["stated"] for x in b], y=[x["realised"] for x in b], mode="markers+text",
                             marker=dict(size=[10 + 3 * min(x["n"], 20) for x in b], color="#3b82c4"),
                             text=[f'n {x["n"]}' for x in b], textposition="top center", name="my calls"))
    fig.update_layout(height=320, margin=dict(l=40, r=20, t=20, b=40), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#8a96a3"), showlegend=False, xaxis=dict(title="Oppgitt sannsynlighet", range=[0, 1], tickformat=".0%"),
                      yaxis=dict(title="Andel som skjedde", range=[0, 1], tickformat=".0%"))
    fig.update_xaxes(gridcolor="rgba(128,128,128,0.15)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)")
    plot = fig.to_html(include_plotlyjs=False, full_html=False, config={"displaylogo": False})
    rows = "".join(f'<tr><td>{x["lo"]:.0%}–{x["hi"]:.0%}</td><td>{x["n"]}</td><td>{x["stated"]:.0%}</td><td>{x["realised"]:.0%}</td>'
                   f'<td class="{cls(x["realised"] - x["stated"])}">{(x["realised"] - x["stated"]) * 100:+.0f} pp</td></tr>' for x in b)
    return (head + f'<p>{n_final} endelige vurderinger ({3 * n_final} scenario-sannsynligheter), {pending} venter på horisonten. '
            f'Brier (binær, per scenario): <b>{rel["brier_binary"]:.3f}</b> – 0 er perfekt, 0.25 er å si 50 % om alt.</p>{plot}'
            f'<table class="odds"><thead><tr><th>Oppgitt</th><th>n</th><th>Snitt oppgitt</th><th>Skjedde</th><th>Avvik</th></tr></thead><tbody>{rows}</tbody></table>'
            '<div class="src">Hvert endelig syn gir tre par (bear, base, bull): sannsynligheten jeg oppga og om det scenarioet lå nærmest sluttkursen. '
            'Punkter under linjen: jeg var for sikker. Få punkter sier lite: under 20 endelige vurderinger er dette støy.</div></div>')


def signal_brackets_block() -> str:
    """Every signal as a trade: target first, stop first or neither, after the round trip (resources/signal_odds.yaml)."""
    doc = _odds()
    m = (doc.get("measured") or {})
    b = m.get("bracket")
    if not b:
        return '<h2>Signalenes utfallsodds</h2><div class="card"><p class="empty">not measured yet: oq signals brackets --write</p></div>'
    rows = []
    for name, s in (doc.get("signals") or {}).items():
        br = s.get("bracket") or {}
        cells = ""
        for h in b.get("horizons", []):
            x = br.get(f"h{h}") or {}
            cells += (f'<td class="t">{_p(x.get("target"))}</td><td class="k">{_p(x.get("stop"))}</td><td>{_p(x.get("neither"))}</td>'
                      f'<td class="{cls(x.get("mean_R"))}">{"–" if x.get("mean_R") is None else format(x["mean_R"], "+.2f")} R</td>')
        n = (br.get(f"h{b['horizons'][0]}") or {}).get("events")
        rows.append(f'<tr><td>{E(name)}</td><td>{E(s.get("kind", ""))}</td>{cells}<td>{_int(n) if n else "–"}</td></tr>')
    hdr = "".join(f'<th class="grp" colspan="4">{h} dager</th>' for h in b["horizons"])
    sub = "<th>Mål først</th><th>Stopp først</th><th>Ingen</th><th>Snitt</th>" * len(b["horizons"])
    return (f'<h2>Signalenes utfallsodds</h2><div class="card">{REALITY}<table class="odds"><thead><tr><th></th><th></th>{hdr}<th></th></tr>'
            f'<tr><th>Signal</th><th>Type</th>{sub}<th>Tilfeller</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            f'<div class="src">Hvert signal som om det ble kjøpt: inngang på neste åpning, mål = inngang × (1 + {b["round_trip_cost"] * 100:.1f} %) + R, '
            f'stopp = inngang − R, R = {E(b["R"])}. Første daglige sluttkurs ved eller forbi et nivå avgjør; «Snitt» er gjennomsnittlig resultat i R etter '
            f'kostnaden (mål = +1 R). Målt {E(str(m.get("from")))} til {E(str(m.get("to")))} på {m.get("stocks")} aksjer, i kroner (ikke mot indeksen). '
            'Risikosignaler er tatt med som kjøp for å vise hva det koster å kjøpe på dem.</div></div>')


# ------------------------------------------------------------------------------------------------ Overvåkning
def watchlist_page(entries: list[dict], ret: pd.DataFrame, alerts: list[sg.Alert], msg: dict | None = None) -> str:
    msg = msg or {}
    rows = []
    for e in entries:
        code = e["code"]
        r = ret.loc[code] if code in ret.index else None
        moved = e.get("moved_to_book")
        sig = ", ".join(a.signal for a in alerts if a.code == code) or ""
        rows.append(f'<tr><td>{link(code)}</td><td>{E(r["name"]) if r is not None else "<span class=err>not in the store</span>"}</td>'
                    f'<td>{"–" if r is None else format(r["close"], ".2f")}</td>'
                    + "".join(f'<td{heat(r[k]) if r is not None else ""}>{pct(r[k]) if r is not None else "–"}</td>' for k in ("d1", "w1", "m1", "ytd"))
                    + f'<td>{E(sig)}</td><td>{E(e.get("note", ""))}</td><td class="src">{E(str(e.get("added", "")))}</td>'
                    f'<td>{"moved to the book " + E(str(moved)) if moved else link(code, "write a case view →")}</td></tr>')
    form = ('<form method="post" action="/watchlist" class="judge" style="display:grid;grid-template-columns:140px 1fr auto;gap:8px;align-items:end">'
            '<div><label>Ticker</label><input name="code" required></div><div><label>Hvorfor følger jeg den?</label><input name="note" required minlength="5"></div>'
            '<div><button class="go" type="submit">Legg til</button></div></form>')
    m = "".join(f'<div class="err">{E(x)}</div>' for x in msg.get("errors", [])) + "".join(f'<div class="ok">{E(x)}</div>' for x in msg.get("ok", []))
    body = ['<h1>Overvåkning</h1><div class="sub">Companies followed without a full case. Writing a view on the stock page moves a company into the research book.</div>',
            m, f'<div class="card">{form}</div>',
            '<div class="card"><table class="heat"><thead><tr><th>Code</th><th>Name</th><th>Close</th><th>Day</th><th>Week</th><th>Month</th><th>YTD</th><th>Signals (10 sessions)</th>'
            '<th>Note</th><th>Added</th><th></th></tr></thead><tbody>' + ("".join(rows) or '<tr><td colspan="11" class="empty">nothing watched yet</td></tr>') + '</tbody></table>'
            '<div class="src">Prices: Yahoo Finance via the store, delayed. Stored privately in ~/osloquant-home/watchlist.yaml.</div></div>']
    return page("Overvåkning", "/watchlist", "\n".join(body))


# ------------------------------------------------------------------------------------------------ coverage (D31)
def _mn(v, unit=1e6) -> str:
    return "–" if v is None else f"{v / unit:,.0f}".replace(",", " ")


def _x(v, d=1) -> str:
    return "–" if v is None else f"{v:.{d}f}x"


def lightcase_block(lc: dict | None) -> str:
    """The light case: what the price is, what the company earns, how it is priced against its sector group, and what
    the price asks for. Every figure with its period and source; the judgement inputs marked EST."""
    if not lc:
        return ""
    cur = lc["currency"]["reporting"]
    p, m, r, rv, pe = lc["profit"], lc["multiples"], lc["returns"], lc["reverse"], lc.get("peers") or {}
    fx = lc["currency"].get("fx")
    fxs = "" if cur == "NOK" else f' · {E(cur)}NOK {fx:.4f} ({E(str(lc["currency"].get("fx_date")))})' if fx else f" · no {E(cur)}NOK rate"
    figs = "".join(f'<tr><td>{E(lab)}</td><td>{_mn(p[k]["value"])}</td><td class="src">{E(str(p[k]["period"] or "–"))}</td></tr>'
                   for lab, k in (("Revenue", "revenue"), ("EBIT", "ebit"), ("Net income", "net_income"), ("Free cash flow", "fcf")))
    b = lc["balance"]
    figs += (f'<tr><td>Net debt</td><td>{_mn(b.get("net_debt"))}</td><td class="src">{E(str(b.get("date") or "–"))}</td></tr>'
             f'<tr><td>Equity</td><td>{_mn(b.get("equity"))}</td><td class="src">{E(str(b.get("date") or "–"))}</td></tr>')
    mult = [("P/E", m.get("pe"), pe.get("pe"), pe.get("n_pe")), ("P/B", m.get("pb"), pe.get("pb"), pe.get("n_pb"))]
    if not lc["financial"]:
        mult.insert(1, ("EV/EBIT", m.get("ev_ebit"), pe.get("ev_ebit"), pe.get("n_ev_ebit")))
    mrows = "".join(f'<tr><td>{E(k)}</td><td><b>{_x(v)}</b></td><td>{_x(g)} <span class="src">(n {n or 0})</span></td></tr>' for k, v, g, n in mult)
    if m.get("fcf_yield") is not None:
        mrows += f'<tr><td>FCF yield</td><td><b>{pct(m["fcf_yield"], 1, False)}</b></td><td></td></tr>'
    rets = " · ".join(x for x in (f'ROE {pct(r.get("roe"), 0, False)}' if r.get("roe") is not None else "",
                                  f'ROIC {pct(r.get("roic"), 0, False)}' if r.get("roic") is not None else "",
                                  f'tax {pct(r.get("tax_rate"), 0, False)} ({E(str(r.get("tax_period")))})') if x)
    warn = "".join(f"<li>{E(w)}</li>" for w in lc.get("warnings", []))
    from osloquant.dashboard import lightcase as lcm

    q, n, h = lcm.quality(lc), lcm.normalised(lc), lcm.history(lc)
    qline = (f'<p>{grade_chip(q)} <b>Kvalitet {q["grade"]}</b>'
             + (": " + E("; ".join(q["issues"])) if q["issues"] else ": price, shares, currency, LTM and quarters in place")
             + ("".join(f' <span class="src">· {E(x)}</span>' for x in q["notes"])) + '</p>')
    hist = ""
    if h.get("years"):
        hist = (f'<div class="src">History {h["from"]}–{h["to"]}: revenue {pct(h.get("rev_cagr"))} a year, EBIT {pct(h.get("ebit_cagr"))} a year, '
                f'EBIT margin {pct(h.get("margin_avg"), 1, False)} on average ({pct(h.get("margin_min"), 1, False)} to {pct(h.get("margin_max"), 1, False)})'
                + (f', ROIC {pct(h.get("roic_avg"), 0, False)} on average' if h.get("roic_avg") is not None and not lc["financial"] else "")
                + (f', ROE {pct(h.get("roe_avg"), 0, False)} on average' if h.get("roe_avg") is not None and lc["financial"] else "")
                + ' (annual table below the figures; Yahoo annual statements).</div>')
    norm = f'<div class="sub" style="margin-bottom:8px">On the average margin: {E(n["reads"])}.</div>' if n else ""
    return (f'<h2>Lett case – grunnlaget for tallene</h2><div class="card"><div class="sub" style="margin-bottom:8px"><b>{E(lcm.reading(lc).get("reads") or rv.get("reads") or "")}</b></div>'
            + norm + qline + hist
            + (f'<div class="warn"><ul>{warn}</ul></div>' if warn else "")
            + f'<div class="grid2"><div><table class="odds"><thead><tr><th>{E(cur)} m</th><th></th><th>Period</th></tr></thead><tbody>{figs}</tbody></table></div>'
            f'<div><table class="odds"><thead><tr><th></th><th>{E(lc["code"])}</th><th>{E(pe.get("group", "group"))} median</th></tr></thead><tbody>{mrows}</tbody></table>'
            f'<div class="src" style="margin-top:6px">{rets}</div></div></div>'
            f'<div class="src">Price {lc["price"]["value"]:.2f} NOK ({E(lc["price"]["date"])}, {E(lc["price"]["source"])}); market value NOK {_mn(lc.get("mcap_nok"), 1e9)} bn; '
            f'reports in {E(cur)}{fxs}. Statements: {E(lc["statements_source"])}, quarters to {E(str(lc.get("quarters_through")))}. '
            f'Group medians: {E(pe.get("note", ""))}. Cost of capital and long-run growth are EST. Built {E(lc["built_at"])} (oq case build).</div></div>')


def grade_chip(q: dict | None) -> str:
    if not q:
        return ""
    klass = {"A": "buy", "B": "info", "C": "risk"}[q["grade"]]
    return f'<span class="chip {klass}" title="{E("; ".join(q["issues"]) or "no issues")}">{q["grade"]}</span>'


def screen_page(rs: list[dict], cand: dict, cnt: dict, today) -> str:
    """What the price requires across the universe, against the company's own history (D43)."""
    from osloquant.dashboard import screen as sc

    def req(r):
        if r["required"] is None:
            return "–"
        return pct(r["required"], 1, r["measure"] != "ROE") + (" ROE" if r["measure"] == "ROE" else " /år")

    def hist(r):
        h = r["history"]
        if r.get("ref") == "long_run":
            seen = f'omsetning {pct(h.get("rev_cagr"))} /år {h.get("from")}–{h.get("to")}' if h.get("rev_cagr") is not None else "ingen historikk"
            return f'{pct(r["hist"], 1)} /år <span class="src">langsiktig EST (syklisk; {seen})</span>'
        if r["hist"] is None:
            return "–"
        return f'{pct(r["hist"], 1, r["measure"] != "ROE")}{" ROE snitt" if r["measure"] == "ROE" else " /år"} <span class="src">({h.get("from")}–{h.get("to")})</span>'

    def line(r, with_group=False):
        verdict_cls = "" if r["verdict"] in ("more", "less", "fall", "above_wacc") else "src"     # no colour: a gap is not good or bad
        gap = "–" if r["gap"] is None else f'{r["gap"] * 100:+.1f} pp'
        roic = ("–" if r["financial"] else f'{pct(r.get("now"), 0, False)} / {pct(r.get("roic_avg"), 0, False)} <span class="src">mot {pct(r.get("wacc"), 1, False)} EST</span>')
        return (f'<tr><td>{link(r["code"], r["name"])}</td>' + (f'<td class="src">{E(r["group"])}</td>' if with_group else "")
                + f'<td>{_level_chip(r["level"]) if r["level"] else "–"}</td><td>{grade_chip(r["quality"])}</td>'
                f'<td><b>{req(r)}</b> <span class="src">{E(r["basis"])}</span></td><td>{hist(r)}</td>'
                f'<td>{gap}</td>'
                f'<td>{roic}</td><td class="{verdict_cls}">{E(r["label"])}</td></tr>')
    head = ('<thead><tr><th>Selskap</th>{grp}<th>Nivå</th><th>Kvalitet</th><th>Prisen krever</th><th>Sammenlignet med (omsetning; bank: ROE; syklisk: 2 % EST)</th>'
            '<th>Spenn</th><th>ROIC nå / snitt</th><th>Lesning</th></tr></thead>')

    def table(items, with_group=False, empty="ingen"):
        body = "".join(line(r, with_group) for r in items) or f'<tr><td colspan="9" class="empty">{empty}</td></tr>'
        return f'<table class="odds">{head.format(grp="<th>Gruppe</th>" if with_group else "")}<tbody>{body}</tbody></table>'

    groups, body = [], []
    for g in [x for x in mk_group_order() if any(r["group"] == x for r in rs)]:
        members = sorted((r for r in rs if r["group"] == g), key=lambda r: (r["gap"] is None, -(r["gap"] or 0)))
        groups.append(f'<h3 style="margin-top:14px">{E(g)} <span class="src">({len(members)})</span></h3>' + table(members))
    body.append("".join(groups))
    c = cnt
    intro = (f'<div class="card"><p><b>{c["n"]} lette caser</b>: kvalitet A {c["grade_A"]}, B {c["grade_B"]}, C {c["grade_C"]}. '
             f'Prisen krever mer enn historikken i {c["more"] + c["above_wacc"]}, mindre i {c["less"] + c["fall"] + c["below_capital"]} (av dem regner {c["fall"]} med at resultatet faller, '
             f'og i {c["below_capital"]} er EV under kapitalen selskapet binder), '
             f'stemmer i {c["in_line"]}; {c["none"] + c["nohist"] + c["below_wacc"]} uten sammenligning.</p>'
             '<div class="src">Prisen krever = veksten i driftsresultatet for alltid som EV betaler for (EV = NOPAT × (1 − g/ROIC) / (WACC − g)), for banker og forsikring '
             'avkastningen på egenkapitalen P/B betaler for. For energi, shipping og sjømat leses kravet på snittmarginen i årstabellen, ikke på siste tolv måneder. '
             f'Historikken er omsetningsvekst per år over årstabellen (3–4 år, Yahoo), for banker snittet av ROE. For sykliske grupper måler tre–fire år syklusen, ikke vekst (2022 var et toppår for olje, gass og frakt), så kravet sammenlignes med den langsiktige veksten casene antar ({pct(lcm_g(), 0, False)}, EST), og omsetningen vises ved siden av. «Spenn» = krav minus sammenligningen; under {sc.GAP_PP * 100:.0f} pp regnes som likt. '
             'Kapitalkostnad og langsiktig vekst er EST. Kvalitet A/B/C: se D42 (C = lesningen kan ikke brukes).</div></div>')
    cands = ('<h2>Kandidater for full dekning</h2><div class="card"><p>Der prisen og historikken spriker mest, blant caser som kan brukes og ikke alt har full case. '
             'En full case avgjør hvem som har rett – listen sier ikke hvem, og den er ikke et kjøps- eller salgsråd.</p>'
             '<h3>Prisen krever mer enn selskapet har levert (syklisk: mer enn 2 % for alltid)</h3>' + table(cand["more"], True)
             + '<h3 style="margin-top:14px">Prisen krever mindre enn selskapet har levert (syklisk: mindre enn 2 % for alltid)</h3>' + table(cand["less"], True)
             + '<div class="src">Planen endres med <code>oq coverage set KODE --target full</code>; en full case starter med <code>oq case export KODE</code> og '
             'Toolkitens <code>new_case.py</code>.</div></div>')
    caveat = ('<div class="card"><div class="src"><b>Ikke testet mot avkastning.</b> Lageret har regnskapene slik de ser ut i dag, ikke slik de så ut på hver dato, '
              'så en historisk test av denne skjermen ville sett fremtiden. Kravet gjelder for alltid; historikken er noen få år – sammenligningen sier hvor de spriker, '
              'ikke hvem som har rett. Kurs: Yahoo via lageret (daglig sluttkurs, forsinket). Regnskap: Yahoo års- og kvartalstall via lageret. '
              'Bygget med <code>oq case build --all</code>; se datoen på hver aksjeside.</div></div>')
    return page("Prisen krever", "/screen", (
        '<h1>Hva prisen krever</h1><div class="sub">Hele universet: veksten kursen betaler for, mot det selskapet har levert, med kvaliteten på tallene ved siden av.</div>'
        + intro + cands + '<h2>Alle selskaper, per sektorgruppe</h2><div class="card">' + "".join(body) + '</div>' + caveat))


def lcm_g() -> float:
    from osloquant.dashboard import lightcase as lcm

    return lcm.G_LONG_EST


def mk_group_order() -> list[str]:
    from osloquant.dashboard import market as mk

    return mk.GROUP_ORDER + ["Other"]


def claude_view_block(c, px: float | None) -> str:
    """Claude's view, folded: read it after writing your own – the form asks, and the answer decides whether your view
    counts as blind (D31)."""
    v = c.claude_view if c else None
    if not v:
        return ""
    since = f" · {pct(px / v['price'] - 1)} since" if px and v.get("price") else ""
    kill = "".join(f"<li>{E(k)}</li>" for k in v.get("kill") or [])
    return (f'<details class="card"><summary><b>Claudes syn</b> – logget {E(v["date"])} (rad #{v["seq"]}). Skriv ditt eget først; skjemaet spør om du har lest dette.</summary>'
            f'<p style="margin-top:8px"><b>{E(v["rating"])} kursmål {v["target"]:g}</b> (kurs da {v["price"]:g}{since}) · bear / base / bull {v["bear"]:g} / {v["base"]:g} / {v["bull"]:g} '
            f'med {v["p_bear"]:.0%} / {v["p_base"]:.0%} / {v["p_bull"]:.0%} · horisont {v.get("horizon_months", 12)} mnd</p>'
            f'<p>{E(v.get("thesis", ""))}</p><h3>Kill-kriterier</h3><ul>{kill}</ul>'
            '<div class="src">Claude (AI) writes its views from the light case and the public reports; they are estimates (EST), scored on the same terms as yours.</div></details>')


def coverage_page(rows: list[dict], today, h2h: dict | None = None, universe: list[dict] | None = None, summ: list[dict] | None = None,
                  queue_html: str = "") -> str:
    """The coverage page (D31, D38): the universe by sector group and level, every company with a view from either
    analyst (the price now, each view and how it has moved since, whether they agree, the next report), and the
    whole universe with the plan per company."""
    def view(v: dict | None) -> str:
        if not v:
            return '<td colspan="3" class="empty">–</td>'
        return (f'<td><b>{E(v["rating"])}</b> {v["target"]:g}</td><td class="{cls(v.get("since"))}">{pct(v.get("since"))}</td>'
                f'<td class="{cls(v.get("to_tp"))}">{pct(v.get("to_tp"))}</td>')
    body = []
    for r in rows:
        agree = "" if not (r["oscar"] and r["claude"]) else ("✓" if r["oscar"]["rating"] == r["claude"]["rating"] else "✗")
        nxt = f'{r["next"]["date"]:%d %b} ({(r["next"]["date"] - today).days} d)' if r.get("next") else "–"
        body.append(f'<tr><td>{link(r["code"], r["name"])}</td><td class="src">{E(r["group"])}</td><td>{"–" if r["price"] is None else format(r["price"], ".2f")}</td>'
                    f'{view(r["oscar"])}{view(r["claude"])}<td>{agree}</td><td>{E(r.get("reads") or "")}</td><td>{nxt}</td></tr>')
    n_o, n_c = sum(bool(r["oscar"]) for r in rows), sum(bool(r["claude"]) for r in rows)
    only_c = [r["code"] for r in rows if r["claude"] and not r["oscar"]]
    hh = ""
    if h2h and h2h.get("n"):
        hh = (f'<div class="src">Side om side på {h2h["n"]} selskaper: kursmålet ditt nærmest kursen i {h2h["oscar_closer"]}, Claudes i {h2h["claude_closer"]}; '
              f'samme rating i {h2h["agree"]}. Se Kalibrering for tallene.</div>')
    return page("Dekning", "/coverage", (
        '<h1>Dekning</h1><div class="sub">Hele universet i lageret: hvilket nivå hvert selskap er dekket på, synene fra deg og Claude, og planen per selskap.</div>'
        + coverage_summary_block(universe, summ, today) + queue_html
        + f'<h2>Selskaper med et syn</h2><div class="card"><p><b>{len(rows)} selskaper</b>: du har syn på {n_o}, Claude på {n_c}.'
        + (f' Bare Claude har syn på {len(only_c)} – åpne aksjesiden, les den lette casen og logg ditt eget før du leser Claudes.' if only_c else '') + '</p>'
        '<table class="odds"><thead><tr><th>Selskap</th><th>Sektor</th><th>Kurs</th><th colspan="3">Ditt syn · siden · til kursmål</th>'
        '<th colspan="3">Claudes syn · siden · til kursmål</th><th>Enige</th><th>Hva prisen krever (lett case)</th><th>Neste rapport</th></tr></thead>'
        f'<tbody>{"".join(body) or "<tr><td colspan=12 class=empty>no views yet</td></tr>"}</tbody></table>{hh}'
        '<div class="src">Kurs: Yahoo via lageret (forsinket). «Siden» = kursendring siden synet ble logget (ikke utbytte). Rapportdatoer fra selskapenes '
        'finanskalendere på NewsWeb og research book. Claude er en AI; synene er estimater (EST).</div></div>'
        + coverage_universe_block(universe, today)))


def _level_chip(level: str) -> str:
    from osloquant.dashboard import coverage as cv

    klass = {"full": "buy", "light": "info", "watch": "plain", "none": "plain"}.get(level, "plain")
    return f'<span class="chip {klass}">{E(cv.LEVEL_LABEL.get(level, level))}</span>'


def coverage_summary_block(universe: list[dict] | None, summ: list[dict] | None, today) -> str:
    """Per sector group: how many companies the store holds, how many are at each level, how many have a view, and
    how many sit below the level the plan asks for."""
    if not universe or not summ:
        return ""
    from osloquant.dashboard import coverage as cv

    rows = []
    for s in summ:
        tot = s["group"] == "Alle"
        rows.append(f'<tr{" style=font-weight:700" if tot else ""}><td>{E(s["group"])}</td><td>{s["n"]}</td>'
                    + "".join(f'<td>{s[lv] or "–"}</td>' for lv in cv.LEVELS)
                    + f'<td>{s["any_view"] or "–"}</td><td>{s["oscar"] or "–"}</td><td>{s["claude"] or "–"}</td>'
                    f'<td class="{"k" if s["gap"] else ""}">{s["gap"] or "–"}</td><td class="{"warn-t" if s["stale"] else ""}">{s["stale"] or "–"}</td></tr>')
    n = cv.counts(universe)
    return (f'<div class="card"><p><b>{n["universe"]} selskaper i lageret</b>: {n["full"]} med full case, {n["light"]} med lett case, {n["watch"]} følges, '
            f'{n["none"]} ikke dekket. Et syn fra deg eller Claude på {n["any_view"]}.'
            + (f' <span class="k">{n["gap"]} ligger under nivået planen sier.</span>' if n["gap"] else '') + '</p>'
            '<table class="odds"><thead><tr><th>Sektorgruppe</th><th>Selskaper</th><th>Full case</th><th>Lett case</th><th>Følges</th><th>Ikke dekket</th>'
            '<th>Med syn</th><th>Ditt</th><th>Claudes</th><th>Under plan</th><th>Lett case utdatert</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            '<div class="src">Nivået er utledet av filene: full case = rapport publisert til dashbordet eller modellfil i research book; lett case = cases/&lt;KODE&gt;.json; '
            f'følges = på overvåkningslisten. «Utdatert» = lett case eldre enn {cv.LIGHT_STALE_DAYS} dager eller bygget før siste rapport. Planen står i ~/osloquant-home/coverage.yaml '
            '(oq coverage set).</div></div>')


def coverage_universe_block(universe: list[dict] | None, today) -> str:
    """Every company in the store, by sector group: level, light-case age, newest report, plan, gap, next report."""
    if not universe:
        return ""
    from osloquant.dashboard import coverage as cv

    body, last_group = [], None
    for r in universe:
        if r["group"] != last_group:
            body.append(f'<tr><th colspan="10" style="text-align:left;background:var(--panel)">{E(r["group"])}</th></tr>')
            last_group = r["group"]
        views = " · ".join(x for x in ((f'du {E(r["oscar"]["rating"])} {r["oscar"]["target"]:g}' if r["oscar"] else ""),
                                       (f'Claude {E(r["claude"]["rating"])} {r["claude"]["target"]:g}' if r["claude"] else "")) if x) or "–"
        lcs = (f'{r["lightcase_built"]}' + (f' <span class="warn-t">({r["lightcase_age"]} d)</span>' if r["lightcase_stale"] else f' ({r["lightcase_age"]} d)')
               + (f' {grade_chip(r["lightcase_quality"])}' if r.get("lightcase_quality") else "")) if r["lightcase_built"] else "–"
        rep = (f'{r["report"]["date"]}' + (f' · {E(str(r["report"]["rating"] or ""))} {r["report"]["tp"]:g}' if r["report"].get("tp") else "")) if r["report"] else "–"
        plan = (f'{E(cv.LEVEL_LABEL.get(r["target"], r["target"]))}' + (f' · {E(r["owner"])}' if r["owner"] else "") + (f' · {E(cv.RHYTHM_LABEL.get(r["rhythm"], r["rhythm"]))}' if r["rhythm"] else "")) if r["target"] else "–"
        nxt = f'{r["next"]["date"]:%d %b} ({(r["next"]["date"] - today).days} d)' if r.get("next") else "–"
        body.append(f'<tr><td>{link(r["code"], r["name"])}</td><td>{"–" if r["price"] is None else format(r["price"], ".2f")}</td><td>{_level_chip(r["level"])}</td>'
                    f'<td>{views}</td><td class="src">{lcs}</td><td class="src">{rep}</td><td class="src">{plan}</td>'
                    f'<td class="{"k" if r["gap"] else ""}">{"under plan" if r["gap"] else ""}</td><td class="src">{E((r.get("plan") or {}).get("note") or "")}</td><td>{nxt}</td></tr>')
    return ('<h2>Universet</h2><div class="card"><table class="odds"><thead><tr><th>Selskap</th><th>Kurs</th><th>Nivå</th><th>Syn</th><th>Lett case bygget</th>'
            '<th>Siste rapport</th><th>Plan (nivå · eier · rytme)</th><th></th><th>Notat</th><th>Neste rapport</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>'
            '<div class="src">Et selskap uten lett case får en med <code>oq case build KODE --refresh</code>; en full case bygges i Equity Research Toolkit og publiseres '
            'til dashbordet av build_report.py. Planen settes med <code>oq coverage set KODE --target light --owner claude --rhythm report</code>.</div></div>')


def analysts_block(summary: dict, h2h: dict | None) -> str:
    """Oscar and Claude on the same terms, and Oscar's blind views against those written after reading Claude's."""
    ba = summary.get("by_analyst") or {}
    if not ba.get("claude", {}).get("judgements"):
        return ""

    def col(s: dict) -> str:
        if not s.get("n"):
            return '<td colspan="4" class="empty">none scored yet</td>'
        return (f'<td>{s["n"]}</td><td>{pct(s.get("direction_hit_rate"), 0, False)}</td><td>{pct(s.get("mean_abs_vs_target"), 1, False)}</td>'
                f'<td>{pct(s.get("beat_flat_rate"), 0, False) if s.get("beat_flat_rate") is not None else "–"}</td>')
    rows = "".join(f'<tr><td>{E(lab)}</td>{col(s)}</tr>' for lab, s in (
        ("Du – alle", ba.get("oscar", {}).get("all_scored", {})), ("Claude – alle", ba.get("claude", {}).get("all_scored", {})),
        ("Du – blind (før Claudes syn)", summary.get("oscar_blind") or {}), ("Du – etter å ha lest Claudes syn", summary.get("oscar_saw_claude") or {})))
    hh = ""
    if h2h and h2h.get("rows"):
        hrows = "".join(f'<tr><td>{link(x["code"])}</td><td>{E(x["oscar"]["rating"])} {x["oscar"]["target"]:g}</td><td>{pct(x["oscar"]["vs_target"])}</td>'
                        f'<td>{E(x["claude"]["rating"])} {x["claude"]["target"]:g}</td><td>{pct(x["claude"]["vs_target"])}</td><td>{E(x["closer"])}</td></tr>' for x in h2h["rows"])
        hh = ('<h3 style="margin-top:10px">Side om side (nyeste syn per selskap)</h3><table class="odds"><thead><tr><th>Selskap</th><th>Du</th><th>Kurs mot ditt mål</th>'
              f'<th>Claude</th><th>Kurs mot Claudes mål</th><th>Nærmest</th></tr></thead><tbody>{hrows}</tbody></table>')
    return ('<h2>Du og Claude</h2><div class="card"><table class="odds"><thead><tr><th></th><th>Scored</th><th>Retning riktig mot OSEBX</th>'
            f'<th>Snittavvik fra kursmål</th><th>Nærmere enn «kursen står stille»</th></tr></thead><tbody>{rows}</tbody></table>{hh}'
            '<div class="src">Inkluderer provisoriske vurderinger – de er ikke bevis før horisonten er nådd. Blind/etter: dine syn på selskaper Claude også har vurdert, '
            'delt etter svaret ditt i skjemaet. Toppen av siden er dine tall alene.</div></div>')


# ------------------------------------------------------------------------------------------------ funds (D33)
def _pc(v, d=1):
    return "–" if v is None or (isinstance(v, float) and v != v) else f"{v * 100:.{d}f} %"


def _sh(v):
    return "–" if v is None else f"{v:.2f}"


def frontier_chart(b: dict) -> str:
    import plotly.graph_objects as go

    fig = go.Figure()
    fr = b.get("frontier") or []
    if fr:
        fig.add_trace(go.Scatter(x=[r["vol"] for r in fr], y=[r["ret"] for r in fr], mode="lines", name="Effisient front (lang, tak 15 %)", line=dict(color="#0f7c7c", width=2)))
    rf, t = b["rf"], b.get("tangency")
    if t and t.get("vol"):
        slope = (t["ret"] - rf) / t["vol"]
        xmax = max(max(r["vol"] for r in fr) if fr else t["vol"], t["vol"]) * 1.15
        fig.add_trace(go.Scatter(x=[0, xmax], y=[rf, rf + slope * xmax], mode="lines", name="Kapitalmarkedslinjen (CML)", line=dict(color="#9a6700", width=1.5, dash="dash")))
    xs = [v["vol"] for v in b["inputs"].values()]
    ys = [v["mu"] for v in b["inputs"].values()]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name="Enkeltaksjer (3 år, krympet snitt)", marker=dict(size=5, color="#b7c1c9"),
                             text=list(b["inputs"].keys()), hovertemplate="%{text}: vol %{x:.1%}, E[r] %{y:.1%}<extra></extra>"))
    cols = ["#1a2126", "#1f5f99", "#0b7a4b", "#0f7c7c", "#9a6700", "#b3261e", "#6a1b9a"]
    for i, f in enumerate(b["funds"]):
        e = f["est"]
        if e.get("vol") is None:
            continue
        fig.add_trace(go.Scatter(x=[e["vol"]], y=[e["ret"]], mode="markers+text", name=f["name"], text=[f["name"]], textposition="top center",
                                 textfont=dict(size=10.5, color=cols[i % len(cols)]), marker=dict(size=11, color=cols[i % len(cols)], symbol="diamond")))
    fig.update_layout(height=430, margin=dict(l=50, r=20, t=40, b=40), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="closest",
                      font=dict(color="#4a5560", family="Segoe UI, Arial, sans-serif"), legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=11)),
                      title=dict(text=f"Forventet avkastning mot volatilitet, {b['lookback_years']:.0f} års historikk til {b['asof']} (EST – se teksten)", font=dict(size=12.5)))
    fig.update_xaxes(title="Volatilitet (årlig)", tickformat=".0%", gridcolor="#e6ebee", rangemode="tozero")
    fig.update_yaxes(title="Forventet avkastning (årlig, EST)", tickformat=".0%", gridcolor="#e6ebee")
    return fig.to_html(include_plotlyjs=False, full_html=False, config={"displaylogo": False})


def nav_chart(series: dict[str, dict], title: str, height: int = 320) -> str:
    import plotly.graph_objects as go

    fig = go.Figure()
    cols = ["#1a2126", "#1f5f99", "#0b7a4b", "#0f7c7c", "#9a6700", "#b3261e", "#6a1b9a", "#555"]
    for i, (name, s) in enumerate(series.items()):
        if not s:
            continue
        xs = list(s.keys())
        fig.add_trace(go.Scatter(x=xs, y=list(s.values()), mode="lines", name=name, line=dict(color=cols[i % len(cols)], width=2.2 if name in ("OSEBX", "Likevektet") else 1.5,
                                                                                               dash="dot" if name == "OSEBX" else "solid")))
    fig.update_layout(height=height, margin=dict(l=44, r=16, t=40, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
                      font=dict(color="#4a5560", family="Segoe UI, Arial, sans-serif"), legend=dict(orientation="h", y=-0.14, x=0, font=dict(size=11)),
                      title=dict(text=title, font=dict(size=12.5)))
    fig.update_xaxes(gridcolor="#e6ebee")
    fig.update_yaxes(gridcolor="#e6ebee")
    return fig.to_html(include_plotlyjs=False, full_html=False, config={"displaylogo": False})


def funds_page(b: dict | None, tracked: list[dict], today) -> str:
    from osloquant.dashboard import funds as fn

    if not b:
        return page("Porteføljer", "/funds", '<h1>Porteføljer</h1><div class="card"><p class="empty">Ingen bygg ennå – kjør <code>oq funds build</code> '
                    '(ett minutt: fem års walk-forward-backtest).</p></div>')
    bt = b.get("backtest") or {}
    rows = bt.get("rows") or {}
    # 1. today's funds
    cards = []
    for f in b["funds"]:
        e = f["est"]
        w = "".join(f'<tr><td>{link(c)}</td><td>{v * 100:.1f} %</td></tr>' for c, v in list(f["weights"].items())[:12])
        more = f' <span class="src">+ {f["n"] - 12} til</span>' if f["n"] > 12 else ''
        cash = f'<tr><td>Kontanter (styringsrenten)</td><td>{f["cash"] * 100:.1f} %</td></tr>' if f["cash"] > 0.0005 else ''
        bt_row = rows.get(f["name"])
        cards.append(f'<div class="card"><h3>{E(f["name"])}</h3><p style="margin:4px 0 6px">{E(f["what"])}</p>'
                     f'<table class="facts"><tr><td>Forventet avkastning (EST)</td><td>{_pc(e.get("ret"))}</td></tr><tr><td>Volatilitet (EST)</td><td>{_pc(e.get("vol"))}</td></tr>'
                     f'<tr><td>Sharpe (EST)</td><td>{_sh(e.get("sharpe"))}</td></tr><tr><td>Aksjer</td><td>{f["n"]}</td></tr></table>'
                     f'<details><summary>Vekter{more}</summary><table class="odds">{w}{cash}</table></details>'
                     + (f'<div class="src" style="margin-top:6px"><b>Ut av prøven, {bt.get("rebalances", 0)} mnd:</b> {E(fn.verdict(bt_row, f["name"]))}.</div>' if bt_row else
                        ('<div class="src" style="margin-top:6px">Ingen backtest: synene er nye, så oppskriften kan bare måles fremover.</div>' if not f.get("backtest", True) or f["name"].startswith("Synene") else ''))
                     + f'<div class="src">{E(f["note"])}</div></div>')
    # 2. backtest table
    order = [f["name"] for f in b["funds"] if f["name"] in rows] + (["OSEBX"] if "OSEBX" in rows else [])
    trs = "".join(
        f'<tr><td>{E(n)}</td><td>{_pc(r.get("cagr"))}</td><td>{_pc(r.get("vol"))}</td><td>{_sh(r.get("sharpe"))}</td><td>{_pc(r.get("max_dd"))}</td>'
        f'<td>{_pc(r.get("turnover"), 0)}</td><td style="white-space:normal;text-align:left">{E(fn.verdict(r, n)) if n != "OSEBX" else "indeksen"}</td></tr>' for n in order for r in [rows[n]])
    bt_html = ('<h2>Ut av prøven: oppskriftene bygget på nytt hver måned, fem år</h2><div class="card">'
               '<table class="odds"><thead><tr><th>Portefølje</th><th>Avkastning p.a.</th><th>Volatilitet</th><th>Sharpe</th><th>Største fall</th><th>Omsetning/mnd</th><th>Mot likevekt</th></tr></thead>'
               f'<tbody>{trs}</tbody></table>'
               + nav_chart(bt.get("nav") or {}, f"Verdi av 1 fra {bt.get('start', '?')}, bygget på nytt hver måned av foregående tre år, kostnad {b['cost']:.2%} av omsetning")
               + f'<div class="src">Walk-forward: ved hvert månedsskifte bygges porteføljen av de foregående {b["lookback_years"]:.0f} årene alene og holdes én måned. '
               f'Sharpe mot styringsrenten ({E(b["rf_label"])}). Intervallene er måneds-blokk-bootstrap (1000 trekk) på Sharpe-differansen. '
               '<b>Universet er dagens aksjer i lageret – overlevere. Likevekt slo OSEBX med god margin i denne perioden av samme grunn; '
               'det riktige sammenligningsgrunnlaget for en oppskrift er likevekt, ikke indeksen.</b></div></div>') if rows else ''
    # 3. tracked paper funds
    if tracked and all(t["days"] == 0 for t in tracked):
        track_html = (f'<h2>Papirfondene siden de ble skrevet</h2><div class="card"><p>{len(tracked)} fond skrevet med vektene fra {E(tracked[0]["since"])} – den nyeste sluttkursen. '
                      'Målingen starter med første sluttkurs etter det; da vises NAV mot likevekt og OSEBX her.</p>'
                      '<div class="src">Vektene ligger i ~/osloquant-home/funds/ og endres ikke; en ny måned er en ny rad. Papirpenger.</div></div>')
    elif tracked:
        trows = "".join(f'<tr><td>{E(t["name"])}</td><td>{E(t["since"])}</td><td>{t["rebalances"]}</td><td>{t["nav"]:.2f}</td><td class="{cls(t["ret"])}">{pct(t["ret"])}</td>'
                        f'<td class="{cls(t["ew"])}">{pct(t["ew"])}</td><td class="{cls(t["osebx"])}">{pct(t["osebx"])}</td><td>{_pc(t["max_dd"])}</td></tr>' for t in tracked)
        track_html = ('<h2>Papirfondene siden de ble skrevet</h2><div class="card"><table class="odds"><thead><tr><th>Fond</th><th>Fra</th><th>Rebalanseringer</th><th>NAV</th>'
                      f'<th>Avkastning</th><th>Likevekt samme dager</th><th>OSEBX</th><th>Største fall</th></tr></thead><tbody>{trows}</tbody></table>'
                      + nav_chart({t["name"]: t["series"] for t in tracked if t["series"]}, "NAV fra 100 ved første skriving (daglig, kostnad på hver rebalansering)", 300)
                      + '<div class="src">Vektene er skrevet til ~/osloquant-home/funds/ og endres ikke; en ny måned er en ny rad. Papirpenger. '
                      'Et fond som har levd kortere enn et år sier lite – det står her for å kunne dømmes om et år, ikke nå.</div></div>')
    else:
        track_html = ('<h2>Papirfondene siden de ble skrevet</h2><div class="card"><p class="empty">Ingen fond skrevet ennå. <code>oq funds build --write</code> '
                      'skriver dagens vekter som startpunkt; deretter måles de daglig mot likevekt og OSEBX.</p></div>')
    inputs = sorted(b["inputs"].items(), key=lambda kv: -kv[1]["mu"])
    irows = "".join(f'<tr><td>{link(c)}</td><td>{_pc(v["raw"])}</td><td>{_pc(v["mu"])}</td><td>± {_pc(v["se"])}</td><td>{_pc(v["vol"])}</td></tr>' for c, v in inputs)
    inputs_html = (f'<h2>Inndataene – og hvor usikre de er</h2><div class="card"><details><summary>{len(inputs)} aksjer: historisk snitt, krympet snitt, standardfeil, volatilitet</summary>'
                   f'<table class="odds"><thead><tr><th>Aksje</th><th>Snitt 3 år</th><th>Krympet (brukt)</th><th>Standardfeil</th><th>Volatilitet</th></tr></thead><tbody>{irows}</tbody></table></details>'
                   f'<div class="src">Standardfeilen på et treårssnitt er omtrent like stor som snittet selv – derfor krympes snittene mot tverrsnittet (James–Stein), '
                   f'kovariansen krympes (Ledoit–Wolf, {b["shrinkage"]:.0%}), ingen aksje får over {b["cap"]:.0%}, og hver oppskrift dømmes ut av prøven før den kalles et fond. '
                   'Porteføljene som ikke bruker snitt (likevekt, minimum varians, risikoparitet) er de minst sårbare for dette.</div></div>')
    body = ['<h1>Porteføljer</h1><div class="sub">Modellporteføljer satt sammen av lagerets aksjer: hvor de ligger mot den effisiente fronten og kapitalmarkedslinjen, '
            'hvordan oppskriften gjorde det ut av prøven, og hvordan de går som papirfond fra den dagen de ble skrevet.</div>',
            f'<div class="src">Bygget {E(b["built_at"])} på kurser til {E(b["asof"])} ({len(b["stocks"])} aksjer med tre års historikk). Risikofri rente: {E(b["rf_label"])}. Alt EST der det står.</div>',
            f'<div class="card">{frontier_chart(b)}<div class="src">Fronten og CML er regnet på de samme inndataene som fondene – de sier hva inndataene sier, ikke hva som skjer. '
            'Diamantene er fondene slik de står i dag.</div></div>',
            '<h2>Fondene i dag</h2><div class="grid">' + "".join(cards) + '</div>', bt_html, track_html, inputs_html]
    return page("Porteføljer", "/funds", "\n".join(body))
