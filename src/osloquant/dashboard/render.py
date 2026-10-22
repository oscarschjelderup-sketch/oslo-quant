"""HTML for the dashboard's pages. Server-rendered strings, so the same front page can be served live and written as
a static file for the evening task. Every number carries its source and time; delayed data says so; estimates say EST."""

from __future__ import annotations

import html
from datetime import datetime
from functools import lru_cache

import pandas as pd

from osloquant import signals as sg
from osloquant.signals_page import CSS as BASE_CSS

E = html.escape

CSS = BASE_CSS + """
nav.top { display:flex; gap:4px; flex-wrap:wrap; align-items:center; margin:-4px 0 16px; padding-bottom:10px; border-bottom:1px solid var(--line); }
nav.top a { padding:6px 12px; border-radius:8px; color:var(--text); text-decoration:none; font-weight:600; font-size:14px; }
nav.top a.on { background:var(--accent); color:var(--card); }
nav.top .brand { font-weight:800; margin-right:12px; color:var(--accent); }
nav.top form { margin-left:auto; display:flex; gap:6px; }
nav.top input { padding:5px 8px; border:1px solid var(--line); border-radius:8px; background:var(--card); color:var(--text); width:110px; }
a { color:var(--info); }
.src { color:var(--muted); font-size:11.5px; }
.decide { border:2px solid var(--risk); }
.decide h2 { margin-top:0; color:var(--risk); }
.item { padding:9px 0; border-top:1px solid var(--line); } .item:first-of-type { border-top:0; }
.item .why { color:var(--muted); font-size:13px; }
.tag { display:inline-block; font-size:11px; font-weight:700; padding:1px 7px; border-radius:6px; margin-right:6px; text-transform:uppercase; }
.tag.u0 { background:var(--risk-bg); color:var(--risk); } .tag.u1 { background:#fff4d6; color:#8a5a00; } .tag.u2 { background:var(--info-bg); color:var(--info); }
.heat td { text-align:right; font-variant-numeric:tabular-nums; } .heat td:first-child, .heat td:nth-child(2) { text-align:left; }
.sector { margin-bottom:14px; } .sector h3 { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.driver { font-size:12.5px; color:var(--muted); font-weight:400; }
form.judge label { display:block; font-size:13px; font-weight:600; margin:8px 0 3px; }
form.judge input, form.judge select, form.judge textarea { width:100%; padding:7px; border:1px solid var(--line); border-radius:8px; background:var(--card); color:var(--text); font:inherit; }
form.judge textarea { min-height:70px; }
.row3 { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; } .row4 { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
button.go { margin-top:12px; padding:9px 18px; border:0; border-radius:8px; background:var(--accent); color:var(--card); font-weight:700; cursor:pointer; }
.err { background:var(--risk-bg); color:var(--risk); padding:8px 12px; border-radius:8px; margin:8px 0; }
.ok { background:var(--buy-bg); color:var(--buy); padding:8px 12px; border-radius:8px; margin:8px 0; }
.news li { margin:4px 0; } .grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:14px; }
"""

NAV = [("/", "I dag"), ("/sectors", "Sektorer"), ("/calibration", "Kalibrering"), ("/watchlist", "Overvåkning")]


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
    gen = f'<div class="src">Generated {(generated or datetime.now()):%d %b %Y %H:%M}. Private: research book and judgements are read from ~/osloquant-home, never published.</div>'
    return f"""<!doctype html><html lang="no"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)} – Oslo Børs dashboard</title><style>{CSS}</style>{plotly}</head><body><div class="wrap">
<nav class="top"><span class="brand">Oslo Børs · beslutninger</span>{nav}{search}</nav>{note}
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
    tags = {0: "u0", 1: "u1", 2: "u2"}
    dec_html = "".join(f'<div class="item"><span class="tag {tags[i.urgency]}">{E(i.kind)}</span><b>{L(i.code, i.title)}</b>'
                       f'<div class="why">{E(i.detail)}</div></div>' for i in dec) or '<p class="empty">Nothing needs a decision today.</p>'
    body = [f'<h1>I dag <span class="code">{ctx["asof"]:%A %d %b %Y}</span></h1>',
            f'<div class="sub">Newest close in the store: {ctx["asof"]:%d %b %Y} (delayed). Signals cover {E(", ".join(ctx["sessions"]) or "–")}.</div>',
            f'<div class="card decide"><h2>Dette krever en vurdering fra deg ({len(dec)})</h2>{dec_html}</div>']
    # cases vs target
    rows = "".join(
        f'<tr><td>{L(m["code"], m["name"])}</td><td>{E(m["rating"] or "")}</td><td>{m["price"]:.2f}</td><td class="{cls(m["since"])}">{pct(m["since"])}</td>'
        f'<td>{m["target"]:g}</td><td class="{cls(m["to_tp"])}">{pct(m["to_tp"])}</td><td>{pct(m["to_bear"])}</td><td>{pct(m["to_bull"])}</td>'
        f'<td class="src">{E(str(m["view_date"]))} · {E(m["view_source"])}</td></tr>' for m in ctx["moves"])
    body.append('<h2>Research book mot kursmål</h2><div class="card"><table><thead><tr><th>Company</th><th>View</th><th>Close</th><th>Since view</th>'
                '<th>TP</th><th>To TP</th><th>To bear</th><th>To bull</th><th>View from</th></tr></thead><tbody>'
                + (rows or '<tr><td colspan="9" class="empty">no cases with a view</td></tr>') + '</tbody></table>'
                f'<div class="src">Close: {E(ctx["price_label"])}. A move of 10 % or more since the view puts the case on the decision list.</div></div>')
    # upcoming + kill
    up = "".join(f'<li><b>{e["date"]:%d %b}</b> ({(e["date"] - ctx["today"]).days} d) {L(e["code"], e["name"])} – {E(e["what"])}'
                 + (f'<details><summary>{len(e["kill"])} kill criteria to check at this event</summary><ul>'
                    + "".join(f"<li>{E(k)}</li>" for k in e["kill"]) + '</ul></details>' if e["kill"] else '') + '</li>' for e in ctx["upcoming"])
    ann = ctx.get("announcements")
    ann_html = ("".join(f'<li><b>{E(a["code"])}</b> {when(a["time"])} – <a href="{E(a["url"])}" target="_blank" rel="noopener">{E(a["title"])}</a></li>' for a in ann["items"])
                or '<li class="empty">no announcements in the window</li>') + f'</ul><div class="src">{E(ann["source"])}</div>' if ann else \
        '<li class="empty">announcements not fetched (oq dashboard --refresh)</li></ul>'
    body.append('<div class="grid2"><div><h2>Kommende datoer (30 dager)</h2><div class="card"><ul class="news">'
                + (up or '<li class="empty">no events in the next 30 days</li>') + '</ul><div class="src">From researchbook.yaml (your own entries).</div></div></div>'
                '<div><h2>Børsmeldinger – research book og overvåkning</h2><div class="card"><ul class="news">' + ann_html + '</div></div></div>')
    # signals since last visit
    alerts = ctx["alerts"]
    book = ctx["book_codes"]
    first = [a for a in alerts if a.code in book] + [a for a in alerts if a.code not in book]
    al = "".join(f'<div class="alert"><b>{L(a.code)}</b><span>{E(a.name)} · <b>{E(a.signal)}</b> · {a.session} at {a.price:.2f}'
                 + (' <span class="chip info">book</span>' if a.code in book else '') + f'</span>'
                 f'<span class="chip {"buy" if (a.exc60 or 0) > 0 else "risk"} odds">{pct(a.exc20)} / {pct(a.exc60)} · hit {pct(a.hit20, 0, False)}{_n(a)}</span>'
                 f'<span class="d">{E(a.detail)}</span></div>' for a in first[:60])
    body.append(f'<h2>Nye signaler siden sist ({len(alerts)})</h2><div class="card">{al or "<p class=empty>no new signals</p>"}'
                '<div class="src">Odds: average excess return over the equal-weighted universe 20/60 sessions after this kind of signal, and the hit rate '
                '(oq signals score, 2010-2026). No buy signal has paid after costs; risk signals carry more information.</div></div>')
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
def stock_page(code: str, ctx: dict) -> str:
    st, c = ctx["status"], ctx["case"]
    name = ctx["name"]
    if not st.get("price"):
        return page(code, "", f'<h1>{E(code)}</h1><p class="err">No prices for {E(code)} in the store. Add it to universe.yaml and run oq record.</p>')
    head = (f'<h1>{E(name)} <span class="code">{E(code)} · {E(ctx["group"])}</span></h1>'
            f'<div class="price">{st["price"]:.2f}<small class="{cls(st.get("chg_1d"))}">{pct(st.get("chg_1d"))} day</small>'
            f'<small class="{cls(st.get("chg_20d"))}">{pct(st.get("chg_20d"))} 20d</small></div>'
            f'<div class="src">{E(ctx["price_label"])}</div>')
    msgs = "".join(f'<div class="err">{E(m)}</div>' for m in ctx.get("errors", [])) + "".join(f'<div class="ok">{E(m)}</div>' for m in ctx.get("ok", []))
    keys = [("60d high", f'{st["hi60"]:.2f}' if st.get("hi60") else "–"), ("60d low", f'{st["lo60"]:.2f}' if st.get("lo60") else "–"),
            ("RSI 14", f'{st["rsi"]:.0f}' if st.get("rsi") is not None else "–"), ("MA20 / MA60", f'{st["ma20"]:.2f} / {st["ma60"]:.2f}' if st.get("ma60") else "–"),
            ("Trend", sg.trend_words(st)), ("YTD", pct(ctx.get("ytd")))]
    keyhtml = '<ul class="kv">' + "".join(f"<li><b>{E(k)}</b>: {E(v)}</li>" for k, v in keys) + '</ul><div class="src">Computed from the store\'s daily bars (delayed).</div>'
    sig = "".join(f'<div class="alert"><b>{E(a.kind)}</b><span><b>{E(a.signal)}</b> · {a.session}</span><span class="chip {"buy" if (a.exc60 or 0) > 0 else "risk"} odds">'
                  f'{pct(a.exc20)} / {pct(a.exc60)} · hit {pct(a.hit20, 0, False)}{_n(a)}</span><span class="d">{E(a.detail)}</span></div>' for a in ctx["alerts"]) or '<p class="empty">no signal in the last 10 sessions</p>'
    news = ctx.get("news")
    nhtml = ("<ul class='news'>" + "".join(f'<li>{when(n["time"])} – <a href="{E(n.get("url") or n.get("link", ""))}" target="_blank" rel="noopener">{E(n["title"])}</a> <span class="src">{E(n.get("kind", ""))}</span></li>' for n in news["items"])
             + f"</ul><div class='src'>{E(news['source'])}</div>") if news and news["items"] else (
             f'<p class="empty">No announcement in the cached window (14 days) and no headline naming the company.</p><div class="src">{E(news["source"])}</div>'
             if news else '<p class="empty">not fetched – oq dashboard --refresh</p>')
    parts = [head, msgs, f'<div class="card">{ctx["chart"]}</div>',
             f'<div class="grid2"><div class="card"><h3>Nøkkeltall</h3>{keyhtml}</div><div class="card"><h3>Aktive signaler (10 økter)</h3>{sig}</div></div>',
             f'<div class="card"><h3>Børsmeldinger og nyheter</h3>{nhtml}</div>']
    if c:
        parts.append(case_block(c, st["price"], ctx.get("rdcf")))
    parts.append(judge_form(code, name, st["price"], ctx["price_label"], ctx.get("form", {}), c))
    return page(f"{code}", "", "\n".join(parts))


def _n(a) -> str:
    """The number of past signals behind the odds, from the measured odds file."""
    ev = ((_odds().get("signals") or {}).get(a.signal) or {}).get("events")
    return f" · n {int(ev):,}".replace(",", " ") if ev else ""


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
            rows.append(f'<tr><td>#{r["seq"]}</td><td>{E(r["date"])}</td><td>{E(r["rating"])}</td><td>{r["price"]:g}</td><td>{r["target"]:g}</td>'
                        f'<td>{r.get("bear", "–")} / {r.get("base", "–")} / {r.get("bull", "–")}</td><td>{r.get("p_bear", "–")} / {r.get("p_base", "–")} / {r.get("p_bull", "–")}</td>'
                        f'<td>{_rationale(r)}</td><td class="src">{E(r.get("logged_at", ""))}</td></tr>')
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


def judge_form(code: str, name: str, px: float, label: str, f: dict, c) -> str:
    v = (c.view if c else None) or {}
    val = lambda k, d="": E(str(f.get(k, d) if f.get(k, d) is not None else ""))  # noqa: E731
    sel = lambda opt: " selected" if (f.get("rating") or v.get("rating")) == opt else ""  # noqa: E731
    kill_default = "\n".join(c.kill) if c and not f else ""
    return f"""<h2>Ny vurdering</h2><div class="card"><form class="judge" method="post" action="/stock/{E(code)}/judge">
<div class="src">Writes one new row to the judgement log (~/osloquant-home/judgements.jsonl) and, if {E(code)} is not in the research book, adds it.
Nothing earlier can be changed: a new view is a new row. Date = today; price = the last close {px:.2f} ({E(label)}).</div>
<input type="hidden" name="name" value="{E(name)}">
<div class="row4"><div><label>Mitt syn</label><select name="rating"><option value="">–</option><option{sel("BUY")}>BUY</option><option{sel("HOLD")}>HOLD</option><option{sel("SELL")}>SELL</option></select></div>
<div><label>Kursmål (12 mnd)</label><input name="target" inputmode="decimal" value="{val("target")}"></div>
<div><label>Horisont (mnd)</label><input name="horizon" inputmode="numeric" value="{val("horizon", 12)}"></div><div></div></div>
<div class="row3"><div><label>Bear (verdi)</label><input name="bear" inputmode="decimal" value="{val("bear")}"></div>
<div><label>Base (verdi)</label><input name="base" inputmode="decimal" value="{val("base")}"></div>
<div><label>Bull (verdi)</label><input name="bull" inputmode="decimal" value="{val("bull")}"></div></div>
<div class="row3"><div><label>Sannsynlighet bear</label><input name="p_bear" inputmode="decimal" placeholder="0.25" value="{val("p_bear")}"></div>
<div><label>Sannsynlighet base</label><input name="p_base" inputmode="decimal" placeholder="0.50" value="{val("p_base")}"></div>
<div><label>Sannsynlighet bull</label><input name="p_bull" inputmode="decimal" placeholder="0.25" value="{val("p_bull")}"></div></div>
<label>Begrunnelse (påkrevd)</label><textarea name="rationale" required minlength="20">{val("rationale")}</textarea>
<label>Kill-kriterier (påkrevd, ett per linje)</label><textarea name="kill" required>{E(f.get("kill_text", kill_default))}</textarea>
<button class="go" type="submit">Logg vurderingen</button></form></div>"""


# ------------------------------------------------------------------------------------------------ Kalibrering
def calibration_page(table: pd.DataFrame, summary: dict, check, kills: list[dict]) -> str:
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
    if len(table):
        rows = "".join(
            f'<tr><td>#{r["seq"]}</td><td>{link(r["code"])}</td><td>{E(r["date"])}</td><td>{E(r["rating"])}</td><td>{r["price"]:.2f}</td><td>{r["target"]:g}</td>'
            f'<td>{r.get("price_now", float("nan")):.2f}</td><td class="{cls(r.get("tsr"))}">{pct(r.get("tsr"))}</td><td class="{cls(r.get("excess_osebx"))}">{pct(r.get("excess_osebx"))}</td>'
            f'<td>{pct(r.get("vs_target"))}</td><td>{"" if pd.isna(r.get("in_band")) else ("yes" if r.get("in_band") else "no")}</td>'
            f'<td>{"✓" if r.get("direction_hit") is True else "✗" if r.get("direction_hit") is False else ""}</td><td>{E(r["status"])} ({r["days"]} d)</td></tr>'
            for _, r in table.iterrows())
        body.append('<h2>Per vurdering</h2><div class="card"><table><thead><tr><th>#</th><th>Code</th><th>Date</th><th>View</th><th>Price</th><th>TP</th><th>Now</th>'
                    '<th>TSR</th><th>vs OSEBX</th><th>vs TP</th><th>In band</th><th>Direction</th><th>Status</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table><div class="src">Total return from the call price on the adjusted series (dividends included); OSEBX from the store; '
                    'prices delayed. Direction for BUY/SELL = sign of the excess over OSEBX.</div></div>')
        per = table.groupby("code").agg(n=("seq", "count"), tsr=("tsr", "mean"), ex=("excess_osebx", "mean"), hit=("direction_hit", "mean"))
        prow = "".join(f'<tr><td>{link(code)}</td><td>{int(r["n"])}</td><td>{pct(r["tsr"])}</td><td>{pct(r["ex"])}</td><td>{pct(r["hit"], 0, False)}</td></tr>' for code, r in per.iterrows())
        body.append(f'<h2>Per case</h2><div class="card"><table><thead><tr><th>Code</th><th>Calls</th><th>Mean TSR</th><th>Mean vs OSEBX</th><th>Direction right</th></tr></thead><tbody>{prow}</tbody></table></div>')
    kb = sum(bool(k["breached"]) for k in kills)
    body.append(f'<h2>Kill-kriterier</h2><div class="card"><p>{len(kills)} checks logged, {kb} breached, '
                f'{sum(bool(k["breached"]) and str(k.get("action", "")).lower() not in ("held", "none", "nothing", "ignored") for k in kills)} acted on.</p>'
                '<div class="src">Log a check with oq book kill --code X --date YYYY-MM-DD --criterion "..." --breached/--intact --action "..."</div></div>')
    return page("Kalibrering", "/calibration", "\n".join(body))


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
