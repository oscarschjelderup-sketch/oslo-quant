"""Plotly charts for the stock page, rendered as HTML fragments (plotly.js is served locally by the dashboard)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from osloquant.dashboard import market as mk


def price_chart(snap: mk.Snapshot, code: str, case=None, sessions: int = 260) -> str:
    """Twelve months of closes with the 20- and 60-day averages and volume; when the research book has a view, the
    cone from the last close to its bear, target and bull values at the end of the horizon (as a sell-side front
    page draws it), and the diamond where the view was logged."""
    P = snap.panel
    if code not in P["close"].columns:
        return '<p class="empty">no prices</p>'
    c = P["close"][code].dropna().iloc[-sessions:]
    v = P["volume"][code].reindex(c.index)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03)
    fig.add_trace(go.Scatter(x=c.index, y=c.values, name="Sluttkurs", line=dict(color="#0f7c7c", width=2)), row=1, col=1)
    for n, colr in ((20, "#7fb8b8"), (60, "#c98500")):
        if len(c) >= n:
            fig.add_trace(go.Scatter(x=c.index, y=c.rolling(n).mean(), name=f"MA{n}", line=dict(color=colr, width=1)), row=1, col=1)
    fig.add_trace(go.Bar(x=v.index, y=v.values, name="Volum", marker_color="#b7c1c9"), row=2, col=1)
    v_ = (case.view if case else None) or {}
    last_day, last_px = c.index[-1], float(c.iloc[-1])
    x_end = last_day
    if v_.get("target") and v_.get("date"):
        months = int(v_.get("horizon_months") or 12)
        end = pd.Timestamp(v_["date"]) + pd.DateOffset(months=months)
        if end > last_day:
            x_end = end
            tp, bear, bull = float(v_["target"]), v_.get("bear"), v_.get("bull")
            if bear and bull:
                fig.add_trace(go.Scatter(x=[last_day, end, end, last_day], y=[last_px, float(bull), float(bear), last_px], fill="toself",
                                         fillcolor="rgba(15,124,124,0.13)", line=dict(width=0), hoverinfo="skip", showlegend=False), row=1, col=1)
            pts = [("TP", tp, "#0f7c7c")] + ([("Bear", float(bear), "#b3261e")] if bear else []) + ([("Bull", float(bull), "#0b7a4b")] if bull else [])
            for label, y, colr in pts:
                fig.add_trace(go.Scatter(x=[last_day, end], y=[last_px, y], mode="lines", line=dict(color=colr, width=1, dash="dot"), hoverinfo="skip", showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=[end], y=[y], mode="markers+text", marker=dict(size=8, color=colr), text=[f"{label} NOK {y:g} ({y / last_px - 1:+.0%})"],
                                         textposition="middle left", textfont=dict(size=11, color=colr), name=label, showlegend=False, hoverinfo="skip"), row=1, col=1)
            if v_.get("consensus_target"):          # logged by hand on the row, with its source and date (never fetched)
                ct = float(v_["consensus_target"])
                fig.add_trace(go.Scatter(x=[end], y=[ct], mode="markers+text", marker=dict(size=8, color="#5c6770", symbol="diamond-open"),
                                         text=[f"Konsensus NOK {ct:g} (manuell)"], textposition="middle left", textfont=dict(size=11, color="#5c6770"),
                                         name="Konsensus (manuell)", showlegend=False, hovertext=[str(v_.get("consensus_source") or "")], hoverinfo="text"), row=1, col=1)
        d = pd.Timestamp(v_["date"])
        if v_.get("price") and d >= c.index[0]:
            fig.add_trace(go.Scatter(x=[d], y=[v_["price"]], mode="markers", name="Synet", marker=dict(size=10, color="#c98500", symbol="diamond")), row=1, col=1)
    months = max(round(len(c) / 21), 1)
    title = f"{code} – daglig sluttkurs, {months} måneder (Yahoo Finance, forsinket)" + (f"; kjegle til synets bear / kursmål / bull i {x_end:%b %Y} (EST)" if x_end != last_day else "")
    fig.update_layout(height=440, margin=dict(l=44, r=16, t=60, b=16), legend=dict(orientation="h", y=1.01, yanchor="bottom", x=0), hovermode="x unified",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", title=dict(text=title, font=dict(size=12.5), y=0.985, yanchor="top"),
                      font=dict(color="#4a5560", family="Segoe UI, Arial, sans-serif"))
    fig.update_xaxes(gridcolor="#e6ebee", zeroline=False, range=[c.index[0], x_end + pd.Timedelta(days=25 if x_end != last_day else 3)])
    fig.update_yaxes(gridcolor="#e6ebee", zeroline=False)
    return fig.to_html(include_plotlyjs=False, full_html=False, config={"displaylogo": False})


def short_chart(series: list[tuple[str, float]], code: str) -> str:
    """The total public short position over the register's two-year window (step line: it changes on report days)."""
    if not series:
        return ""
    x = [pd.Timestamp(d) for d, _ in series]
    y = [v for _, v in series]
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#b3261e", width=2, shape="hv"), name="Short %"))
    fig.update_layout(height=200, margin=dict(l=40, r=20, t=30, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#4a5560"), showlegend=False,
                      title=dict(text=f"{code} – offentlige shortposisjoner, % av aksjene (Finanstilsynet)", font=dict(size=12)))
    fig.update_xaxes(gridcolor="#e6ebee")
    fig.update_yaxes(gridcolor="#e6ebee", rangemode="tozero", ticksuffix=" %")
    return fig.to_html(include_plotlyjs=False, full_html=False, config={"displaylogo": False})


# ------------------------------------------------------------------------------------------------ the stock page (D57)
#: the period buttons on the stock page: label and sessions back (None = year to date, 0 = everything in the chart)
PERIODS = [("5D", 5), ("1M", 21), ("6M", 126), ("YTD", None), ("1Å", 250), ("5Å", 1250), ("Maks", 0)]
CHART_SESSIONS = 1260          # five years of daily closes in the overview chart


def period_ranges(c: pd.Series, v: pd.Series | None = None) -> list[dict]:
    """For every period button: the x-range, the y-range of the closes inside it (4 % padding), the volume axis top
    and the return from the period's base close to the last. Pure: closes in, numbers out."""
    c = c.dropna()
    if len(c) < 2:
        return []
    last = c.index[-1]
    out = []
    for label, n in PERIODS:
        if n is None:
            before = c[c.index < pd.Timestamp(last.year, 1, 1)]
            base_i = len(before) - 1 if len(before) else 0
        elif n == 0:
            base_i = 0
        else:
            base_i = max(len(c) - 1 - n, 0)
        seg = c.iloc[base_i:]
        lo, hi = float(seg.min()), float(seg.max())
        pad = (hi - lo) * 0.04 or hi * 0.02
        vmax = float(v.reindex(seg.index).max()) if v is not None and len(v) else None
        out.append({"key": label.replace("Å", "a").lower(), "label": label, "x0": f"{seg.index[0]:%Y-%m-%d}", "x1": f"{last:%Y-%m-%d}",
                    "y0": lo - pad, "y1": hi + pad, "v1": vmax * 1.05 if vmax else None, "ret": float(seg.iloc[-1] / seg.iloc[0] - 1) if seg.iloc[0] else None,
                    "sessions": len(seg) - 1, "enough": base_i > 0 or n in (0, None)})
    return out


def long_chart(snap: mk.Snapshot, code: str, sessions: int = CHART_SESSIONS, div_id: str = "chart-price", default: str = "1a") -> tuple[str, list[dict]]:
    """The overview chart: up to five years of closes with the 20- and 60-day averages and volume, opened on the last
    twelve months. The period buttons move the axes client-side with the ranges returned here (no reload). No cone –
    the view's cone lives on the valuation tab."""
    P = snap.panel
    if code not in P["close"].columns:
        return '<p class="empty">ingen kurser</p>', []
    full = P["close"][code].dropna()
    c = full.iloc[-sessions:]
    v = P["volume"][code].reindex(c.index)
    ranges = period_ranges(c, v)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03)
    fig.add_trace(go.Scatter(x=c.index, y=c.values, name="Sluttkurs", line=dict(color="#0f7c7c", width=1.8),
                             hovertemplate="%{y:.2f}<extra>Sluttkurs</extra>"), row=1, col=1)
    for n, colr in ((20, "#7fb8b8"), (60, "#c98500")):
        ma = full.rolling(n).mean().reindex(c.index)
        if ma.notna().any():
            fig.add_trace(go.Scatter(x=c.index, y=ma.values, name=f"MA{n}", line=dict(color=colr, width=1), hovertemplate="%{y:.2f}<extra>MA" + str(n) + "</extra>"), row=1, col=1)
    fig.add_trace(go.Bar(x=v.index, y=v.values, name="Volum", marker_color="#b7c1c9", hovertemplate="%{y:,.0f}<extra>Volum</extra>"), row=2, col=1)
    r0 = next((r for r in ranges if r["key"] == default), ranges[-1])
    title = f"{code} – daglig sluttkurs til {c.index[-1]:%d %b %Y} (Yahoo Finance via lageret, forsinket)"
    fig.update_layout(height=430, margin=dict(l=44, r=16, t=56, b=16), legend=dict(orientation="h", y=1.01, yanchor="bottom", x=0), hovermode="x unified",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", title=dict(text=title, font=dict(size=12.5), y=0.985, yanchor="top"),
                      font=dict(color="#4a5560", family="Segoe UI, Arial, sans-serif"), bargap=0.1)
    fig.update_xaxes(gridcolor="#e6ebee", zeroline=False, range=[r0["x0"], r0["x1"]])
    fig.update_yaxes(gridcolor="#e6ebee", zeroline=False, range=[r0["y0"], r0["y1"]], row=1, col=1)
    if r0.get("v1"):
        fig.update_yaxes(gridcolor="#e6ebee", zeroline=False, range=[0, r0["v1"]], row=2, col=1)
    return fig.to_html(include_plotlyjs=False, full_html=False, div_id=div_id, config={"displaylogo": False, "responsive": True}), ranges


def _html(fig: go.Figure, height: int, title: str) -> str:
    fig.update_layout(height=height, margin=dict(l=44, r=16, t=48, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#4a5560", family="Segoe UI, Arial, sans-serif"), title=dict(text=title, font=dict(size=12.5), y=0.98, yanchor="top"),
                      legend=dict(orientation="h", y=1.0, yanchor="bottom", x=0))
    fig.update_xaxes(gridcolor="#e6ebee", zeroline=False)
    fig.update_yaxes(gridcolor="#e6ebee", zeroline=False)
    return fig.to_html(include_plotlyjs=False, full_html=False, config={"displaylogo": False, "responsive": True})


def revenue_result_chart(rows: list[dict], cur: str, period: str) -> str:
    """Revenue and net result as grouped bars, one chart per period (annual or quarterly) – the tab toggles them."""
    if not rows:
        return ""
    x = [r["label"] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=[(r.get("total_revenue") or 0) / 1e6 for r in rows], name="Omsetning", marker_color="#0f7c7c", hovertemplate="%{y:,.0f} m<extra>Omsetning</extra>"))
    fig.add_trace(go.Bar(x=x, y=[(r.get("net_income") or 0) / 1e6 for r in rows], name="Resultat", marker_color="#c98500", hovertemplate="%{y:,.0f} m<extra>Resultat</extra>"))
    fig.update_layout(barmode="group", bargap=0.25)
    per = "år" if period == "year" else "kvartal"
    return _html(fig, 300, f"Omsetning og resultat per {per} ({cur} m, Yahoo-regnskap via lageret)")


def margins_chart(rows: list[dict], period: str) -> str:
    """EBIT and net margin over time."""
    pts = [r for r in rows if r.get("total_revenue")]
    if len(pts) < 2:
        return ""
    x = [r["label"] for r in pts]
    fig = go.Figure()
    for key, name, colr in (("ebit", "EBIT-margin", "#0f7c7c"), ("net_income", "Resultatmargin", "#c98500")):
        y = [((r.get(key) or 0) / r["total_revenue"]) * 100 if r.get(key) is not None else None for r in pts]
        fig.add_trace(go.Scatter(x=x, y=y, name=name, mode="lines+markers", line=dict(color=colr, width=1.6), hovertemplate="%{y:.1f} %<extra>" + name + "</extra>"))
    fig.update_yaxes(ticksuffix=" %")
    per = "år" if period == "year" else "kvartal"
    return _html(fig, 260, f"Marginer per {per} (regnet av Yahoo-regnskapet)")


def waterfall_chart(r: dict, cur: str) -> str:
    """From revenue to net result for one period, with the lines Yahoo reports; a missing line is skipped."""
    if not r or not r.get("total_revenue"):
        return ""
    steps = [("Omsetning", r["total_revenue"], "absolute")]
    rev, gp, op, pt, ni = r["total_revenue"], r.get("gross_profit"), r.get("operating_income"), r.get("pretax_income"), r.get("net_income")
    if gp is not None:
        steps += [("Varekostnad", gp - rev, "relative"), ("Bruttoresultat", gp, "total")]
    if op is not None:
        steps += [("Driftskostnader", op - (gp if gp is not None else rev), "relative"), ("Driftsresultat", op, "total")]
    if pt is not None and op is not None:
        steps += [("Finans m.m.", pt - op, "relative"), ("Resultat før skatt", pt, "total")]
    if ni is not None and pt is not None:
        steps += [("Skatt m.m.", ni - pt, "relative"), ("Resultat", ni, "total")]
    elif ni is not None:
        steps += [("Resultat", ni, "total")]
    if len(steps) < 3:
        return ""
    fig = go.Figure(go.Waterfall(x=[s[0] for s in steps], y=[s[1] / 1e6 for s in steps], measure=[s[2] for s in steps],
                                 increasing=dict(marker=dict(color="#0b7a4b")), decreasing=dict(marker=dict(color="#b3261e")), totals=dict(marker=dict(color="#0f7c7c")),
                                 connector=dict(line=dict(color="#d9e0e5")), hovertemplate="%{y:,.0f} m<extra>%{x}</extra>"))
    fig.update_layout(showlegend=False)
    return _html(fig, 300, f"Fra omsetning til resultat, {r['label']} ({cur} m)")


def multiples_history_chart(points: list[dict]) -> str:
    """P/E and P/S at each year end against the price then: the company against its own history."""
    pts = [p for p in points if p.get("pe") is not None or p.get("ps") is not None]
    if len(pts) < 2:
        return ""
    x = [p["label"] for p in pts]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=x, y=[p.get("pe") for p in pts], name="P/E", mode="lines+markers", line=dict(color="#0f7c7c", width=1.6), hovertemplate="%{y:.1f}x<extra>P/E</extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=[p.get("ps") for p in pts], name="P/S", mode="lines+markers", line=dict(color="#c98500", width=1.6), hovertemplate="%{y:.2f}x<extra>P/S</extra>"), secondary_y=True)
    fig.update_yaxes(ticksuffix="x", secondary_y=False)
    fig.update_yaxes(ticksuffix="x", secondary_y=True, showgrid=False)
    return _html(fig, 260, "P/E og P/S ved hvert årsslutt (årssluttkurs × aksjer / årets tall; aksjetall fra balansen, EST)")
