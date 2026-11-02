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
    fig.add_trace(go.Scatter(x=c.index, y=c.values, name="Close", line=dict(color="#0f7c7c", width=2)), row=1, col=1)
    for n, colr in ((20, "#7fb8b8"), (60, "#c98500")):
        if len(c) >= n:
            fig.add_trace(go.Scatter(x=c.index, y=c.rolling(n).mean(), name=f"MA{n}", line=dict(color=colr, width=1)), row=1, col=1)
    fig.add_trace(go.Bar(x=v.index, y=v.values, name="Volume", marker_color="#b7c1c9"), row=2, col=1)
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
        d = pd.Timestamp(v_["date"])
        if v_.get("price") and d >= c.index[0]:
            fig.add_trace(go.Scatter(x=[d], y=[v_["price"]], mode="markers", name="View", marker=dict(size=10, color="#c98500", symbol="diamond")), row=1, col=1)
    title = f"{code} – daily close, 12 months (Yahoo Finance, delayed)" + (f"; cone to the view's bear / TP / bull at {x_end:%b %Y} (EST)" if x_end != last_day else "")
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
                      title=dict(text=f"{code} – public short positions, % of shares (Finanstilsynet)", font=dict(size=12)))
    fig.update_xaxes(gridcolor="#e6ebee")
    fig.update_yaxes(gridcolor="#e6ebee", rangemode="tozero", ticksuffix=" %")
    return fig.to_html(include_plotlyjs=False, full_html=False, config={"displaylogo": False})
