"""The signal watch as a page: one self-contained HTML file per session, written next to the Markdown digest.

No external scripts or styles, so the file opens anywhere, offline, on a phone from a synced folder. It draws
the research book as cards (price against bear, DCF, target and bull on one scale; a sparkline of the last 120
sessions with the 60-day range; today's signals on the stock; the dates that test the case), then today's alerts
across the universe in two columns and, at the bottom, what each kind of signal has meant historically.
"""

from __future__ import annotations

import html
from datetime import datetime

import pandas as pd

from osloquant.signals import BUY, INFO, RISK, ROUND_TRIP_COST, Alert, status, trend_words

CSS = """
:root { --bg:#f4f6f8; --card:#ffffff; --text:#1b2430; --muted:#5f6b7a; --line:#dde3ea; --accent:#003255;
        --buy:#2e7d4f; --buy-bg:#e5f3ea; --risk:#b3261e; --risk-bg:#fbe9e7; --info:#1f5f99; --info-bg:#e6f0fa; --gold:#c98500; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#111820; --card:#1a2330; --text:#e6ecf2; --muted:#9aa7b5; --line:#2a3647; --accent:#9ec3d1;
          --buy:#6fcf97; --buy-bg:#17352a; --risk:#f28b82; --risk-bg:#3a1f1d; --info:#7fb3f0; --info-bg:#1b2d44; --gold:#e3a93a; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.45 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
.wrap { max-width:1180px; margin:0 auto; padding:20px 16px 48px; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:18px; margin:28px 0 10px; } h3 { font-size:16px; margin:0; }
.sub { color:var(--muted); margin-bottom:14px; }
.chips { display:flex; gap:8px; flex-wrap:wrap; margin:10px 0 0; }
.chip { display:inline-block; padding:3px 10px; border-radius:999px; font-size:12.5px; font-weight:600; }
.chip.buy { background:var(--buy-bg); color:var(--buy); } .chip.risk { background:var(--risk-bg); color:var(--risk); }
.chip.info { background:var(--info-bg); color:var(--info); } .chip.plain { background:var(--line); color:var(--text); }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:14px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }
.head { display:flex; justify-content:space-between; align-items:baseline; gap:10px; flex-wrap:wrap; }
.code { color:var(--muted); font-weight:500; }
.price { font-size:30px; font-weight:700; margin:6px 0 0; } .price small { font-size:14px; font-weight:600; margin-left:8px; }
.up { color:var(--buy); } .down { color:var(--risk); }
.muted { color:var(--muted); font-size:13px; }
.ladder { margin:12px 0 4px; } .ladder svg { width:100%; height:72px; display:block; }
.spark svg { width:100%; height:78px; display:block; margin-top:6px; }
.kv { margin:8px 0 0; padding:0; list-style:none; } .kv li { padding:3px 0; border-top:1px solid var(--line); font-size:13.5px; }
.kv li:first-child { border-top:0; }
details { margin-top:8px; } summary { cursor:pointer; color:var(--muted); font-size:13px; }
details ul { margin:6px 0 0 18px; padding:0; font-size:13px; color:var(--muted); }
.cols { display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:14px; }
.alert { display:grid; grid-template-columns:64px 1fr auto; gap:6px 10px; padding:8px 0; border-top:1px solid var(--line); align-items:start; }
.alert:first-of-type { border-top:0; } .alert .d { grid-column:2 / 4; color:var(--muted); font-size:12.5px; }
.alert b { font-size:14px; } .odds { font-size:12px; white-space:nowrap; }
table { width:100%; border-collapse:collapse; font-size:13px; } th, td { text-align:right; padding:6px 8px; border-top:1px solid var(--line); }
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align:left; } th { color:var(--muted); font-weight:600; border-top:0; }
.foot { color:var(--muted); font-size:12.5px; margin-top:24px; line-height:1.5; }
.empty { color:var(--muted); font-style:italic; }
"""


def _pct(v: float | None, digits: int = 1, sign: bool = True) -> str:
    if v is None or v != v:
        return "–"
    return f"{v * 100:{'+' if sign else ''}.{digits}f}%"


def _cls(v: float | None) -> str:
    return "" if v is None or v != v else ("up" if v > 0 else "down" if v < 0 else "")


def _odds_chip(a: Alert) -> str:
    if a.exc20 is None:
        return '<span class="chip plain odds">no odds</span>'
    cls = "buy" if (a.exc60 or 0) > 0 else "risk"
    return f'<span class="chip {cls} odds">{_pct(a.exc20)} / {_pct(a.exc60)} · hit {_pct(a.hit20, 0, False)}</span>'


def ladder_svg(price: float, points: dict[str, float | None]) -> str:
    """Bear, DCF, target and bull on one horizontal scale, with the price as the heavy marker."""
    vals = {k: v for k, v in points.items() if v}
    lo = min([price, *vals.values()]) * 0.93
    hi = max([price, *vals.values()]) * 1.05
    w, h = 600, 72
    x = lambda v: 24 + (w - 48) * (v - lo) / (hi - lo)  # noqa: E731
    colour = {"bear": "var(--risk)", "dcf": "var(--accent)", "target": "var(--buy)", "bull": "var(--buy)"}
    label = {"bear": "Bear", "dcf": "DCF", "target": "TP", "bull": "Bull"}
    parts = [f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">',
             f'<line x1="24" y1="34" x2="{w - 24}" y2="34" stroke="var(--line)" stroke-width="4" stroke-linecap="round"/>']
    if "bear" in vals and "bull" in vals:
        parts.append(f'<line x1="{x(vals["bear"]):.1f}" y1="34" x2="{x(vals["bull"]):.1f}" y2="34" stroke="var(--info-bg)" stroke-width="4"/>')
    last_x, row = -1e9, 0
    for k, v in sorted(vals.items(), key=lambda kv: kv[1]):       # labels closer than 52px go on a second row
        row = 1 - row if x(v) - last_x < 52 else 0
        last_x = x(v)
        parts.append(f'<line x1="{x(v):.1f}" y1="26" x2="{x(v):.1f}" y2="42" stroke="{colour[k]}" stroke-width="2"/>')
        parts.append(f'<text x="{x(v):.1f}" y="{54 + 13 * row}" font-size="11" text-anchor="middle" fill="{colour[k]}">{label[k]} {v:g}</text>')
    parts.append(f'<circle cx="{x(price):.1f}" cy="34" r="6" fill="var(--text)"/>')
    parts.append(f'<text x="{x(price):.1f}" y="16" font-size="12" font-weight="700" text-anchor="middle" fill="var(--text)">{price:.2f}</text>')
    parts.append("</svg>")
    return "".join(parts)


def sparkline_svg(closes: pd.Series, hi60: float | None, lo60: float | None, mark: float | None = None) -> str:
    """The last 120 closes, with the 60-day range as dashed lines and the valuation price as a dotted line."""
    c = closes.dropna().iloc[-120:]
    if len(c) < 2:
        return '<div class="muted">not enough history for a chart</div>'
    w, h, pad = 600, 78, 6
    levels = [v for v in (hi60, lo60, mark) if v]
    lo, hi = min([c.min(), *levels]), max([c.max(), *levels])
    span = (hi - lo) or 1.0
    x = lambda i: pad + (w - 2 * pad) * i / (len(c) - 1)  # noqa: E731
    y = lambda v: h - pad - (h - 2 * pad) * (v - lo) / span  # noqa: E731
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(c.values))
    parts = [f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">']
    for v, col in ((hi60, "var(--buy)"), (lo60, "var(--risk)")):
        if v:
            parts.append(f'<line x1="{pad}" y1="{y(v):.1f}" x2="{w - pad}" y2="{y(v):.1f}" stroke="{col}" stroke-width="1" stroke-dasharray="4 4" opacity="0.7"/>')
    if mark:
        parts.append(f'<line x1="{pad}" y1="{y(mark):.1f}" x2="{w - pad}" y2="{y(mark):.1f}" stroke="var(--gold)" stroke-width="1" stroke-dasharray="2 3"/>')
    parts.append(f'<path d="{path}" fill="none" stroke="var(--accent)" stroke-width="2"/>')
    parts.append(f'<circle cx="{x(len(c) - 1):.1f}" cy="{y(c.values[-1]):.1f}" r="3.5" fill="var(--accent)"/>')
    parts.append("</svg>")
    return "".join(parts)


def book_card(entry: dict, P: dict[str, pd.DataFrame], alerts: list[Alert], today: pd.Timestamp) -> str:
    code = entry["code"]
    name = html.escape(str(entry.get("name", code)))
    st = status(P, code)
    rating = html.escape(str(entry.get("rating", "")))
    tp = entry.get("target")
    head = f'<div class="head"><h3>{name} <span class="code">{code}</span></h3><span class="chip plain">{rating}{f" · TP {tp:g}" if tp else ""}</span></div>'
    if not st.get("price"):
        return f'<div class="card">{head}<p class="empty">no bars in the store yet – oq record</p></div>'
    px = st["price"]
    chg = st.get("chg_1d")
    price = f'<div class="price">{px:.2f}<small class="{_cls(chg)}">{_pct(chg)} today</small></div>'
    p0, d0 = entry.get("price_at_valuation"), entry.get("valuation_date", "")
    since = f'<div class="muted">session {st["session"]}' + (f' · <span class="{_cls(px / p0 - 1)}">{_pct(px / p0 - 1)}</span> since the case ({d0} at {p0:g})' if p0 else "") + "</div>"
    ladder = f'<div class="ladder">{ladder_svg(px, {"bear": entry.get("bear"), "dcf": entry.get("dcf"), "target": tp, "bull": entry.get("bull")})}</div>'
    dist = []
    if tp:
        dist.append(f'<b class="{_cls(tp / px - 1)}">{_pct(tp / px - 1, 0)}</b> to TP')
    if entry.get("bear"):
        dist.append(f'{_pct(entry["bear"] / px - 1, 0)} to bear')
    if entry.get("bull"):
        dist.append(f'{_pct(entry["bull"] / px - 1, 0)} to bull')
    dist_line = f'<div class="muted">{" · ".join(dist)}</div>' if dist else ""
    spark = f'<div class="spark">{sparkline_svg(P["close"][code], st.get("hi60"), st.get("lo60"), p0)}</div>'
    tech = [trend_words(st)]
    if st.get("hi60"):
        tech.append(f'{_pct(px / st["hi60"] - 1)} vs 60d high, {_pct(px / st["lo60"] - 1)} vs 60d low')
    if st.get("rsi") is not None:
        tech.append(f'RSI {st["rsi"]:.0f}')
    tech_line = f'<div class="muted">{" · ".join(html.escape(t) for t in tech)}</div>'
    mine = [a for a in alerts if a.code == code]
    chips = "".join(f'<span class="chip {a.kind.lower()}" title="{html.escape(a.detail)}">{a.kind}: {html.escape(a.signal)}</span>' for a in mine)
    chips = f'<div class="chips">{chips}</div>' if chips else '<div class="chips"><span class="chip plain">no signal today</span></div>'
    events = []
    for ev in entry.get("events", []):
        when = pd.Timestamp(ev["date"])
        days = (when.normalize() - today.normalize()).days
        if days >= -1:
            events.append(f'<li><b>{when:%d %b %Y}</b> ({"today" if days == 0 else f"in {days} days" if days > 0 else "yesterday"}) – {html.escape(str(ev["what"]))}</li>')
    ev_html = f'<ul class="kv">{"".join(events)}</ul>' if events else ""
    kill = entry.get("kill", [])
    kill_html = f'<details><summary>{len(kill)} kill criteria to check at the reports</summary><ul>{"".join(f"<li>{html.escape(str(k))}</li>" for k in kill)}</ul></details>' if kill else ""
    return f'<div class="card">{head}{price}{since}{ladder}{dist_line}{spark}{tech_line}{chips}{ev_html}{kill_html}</div>'


def alert_row(a: Alert) -> str:
    return (f'<div class="alert"><b>{a.code}</b><span>{html.escape(a.name)} · <b>{html.escape(a.signal)}</b> at {a.price:.2f}</span>'
            f'{_odds_chip(a)}<span class="d">{html.escape(a.detail)}</span></div>')


def odds_table(odds: dict) -> str:
    rows = odds.get("signals", {})
    if not rows:
        return ""
    order = {BUY: 0, RISK: 1, INFO: 2}
    items = sorted(rows.items(), key=lambda kv: (order.get(kv[1].get("kind"), 3), kv[0]))
    body = "".join(
        f'<tr><td>{html.escape(k)}</td><td><span class="chip {str(v.get("kind", "")).lower()}">{v.get("kind", "")}</span></td>'
        f'<td>{v.get("per_month") or 0:.1f}</td><td>{_pct(v.get("raw20"))}</td><td>{_pct(v.get("exc20"))}</td>'
        f'<td>{_pct(v.get("exc60"))}</td><td>{_pct(v.get("hit20"), 0, False)}</td><td>{v.get("t20") or 0:.1f}</td></tr>'
        for k, v in items
    )
    m = odds.get("measured", {})
    return (f'<h2>What these signals have meant</h2><div class="card"><table><thead><tr><th>Signal</th><th>Kind</th><th>Alerts / month</th>'
            f'<th>Raw 20d</th><th>Excess 20d</th><th>Excess 60d</th><th>Hit 20d</th><th>t 20d</th></tr></thead><tbody>{body}</tbody></table>'
            f'<div class="muted" style="margin-top:8px">Entry at the next open; excess = minus the equal-weighted universe over the same window; '
            f'measured {m.get("from", "?")} to {m.get("to", "?")} on {m.get("stocks", "?")} stocks. A round trip costs ~{ROUND_TRIP_COST * 100:.1f}%, '
            f'so a 20-day signal pays only if its raw return beats that.</div></div>')


def render_html(P: dict[str, pd.DataFrame], alerts: list[Alert], book: list[dict], session: str, odds: dict | None = None,
                today: pd.Timestamp | None = None, generated: datetime | None = None) -> str:
    today = today or pd.Timestamp.now().normalize()
    generated = generated or datetime.now()
    odds = odds or {}
    buys = [a for a in alerts if a.kind == BUY]
    risks = [a for a in alerts if a.kind == RISK]
    infos = [a for a in alerts if a.kind == INFO]
    chips = (f'<div class="chips"><span class="chip buy">{len(buys)} buy-type</span><span class="chip risk">{len(risks)} risk</span>'
             f'<span class="chip info">{len(infos)} info</span><span class="chip plain">{P["close"].shape[1] if not P["close"].empty else 0} stocks</span></div>')
    cards = "".join(book_card(e, P, alerts, today) for e in book) or '<p class="empty">no research book yet (~/osloquant-home/researchbook.yaml)</p>'
    left = "".join(alert_row(a) for a in buys) or '<p class="empty">no buy-type signals today</p>'
    right = "".join(alert_row(a) for a in risks + infos) or '<p class="empty">no risk signals today</p>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Signal watch {session}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>Signal watch <span class="code">session {session}</span></h1>
<div class="sub">Generated {generated:%d %b %Y %H:%M}. Technical signals with their measured odds; the research book against the newest prices. Nothing here is advice.</div>
{chips}
<h2>Research book</h2>
<div class="grid">{cards}</div>
<h2>Today's alerts across the universe</h2>
<div class="cols"><div class="card"><h3>Buy-type signals</h3>{left}</div><div class="card"><h3>Risk and info signals</h3>{right}</div></div>
{odds_table(odds)}
<div class="foot">Buy signals are timing on a case you have written, not a reason on their own: on this universe no buy signal has had an edge after costs over 20 sessions. The risk signals carry more information. Written by <code>oq signals digest</code> (oslo-quant); paper and research only, no real money.</div>
</div></body></html>
"""
