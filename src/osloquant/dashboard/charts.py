"""Plotly charts for the stock page, rendered as HTML fragments (plotly.js is served locally by the dashboard)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from osloquant.dashboard import market as mk


def price_chart(snap: mk.Snapshot, code: str, case=None, sessions: int = 260) -> str:
    P = snap.panel
    if code not in P["close"].columns:
        return '<p class="empty">no prices</p>'
    c = P["close"][code].dropna().iloc[-sessions:]
    v = P["volume"][code].reindex(c.index)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
    fig.add_trace(go.Scatter(x=c.index, y=c.values, name="Close", line=dict(color="#3b82c4", width=2)), row=1, col=1)
    for n, colr in ((20, "#81b0c0"), (60, "#c98500")):
        if len(c) >= n:
            fig.add_trace(go.Scatter(x=c.index, y=c.rolling(n).mean(), name=f"MA{n}", line=dict(color=colr, width=1)), row=1, col=1)
    fig.add_trace(go.Bar(x=v.index, y=v.values, name="Volume", marker_color="#9aa7b5"), row=2, col=1)
    v_ = (case.view if case else None) or {}
    for key, colr in (("target", "#2e7d4f"), ("bear", "#b3261e"), ("bull", "#2e7d4f")):
        if v_.get(key):
            fig.add_hline(y=v_[key], line=dict(color=colr, dash="dash" if key == "target" else "dot", width=1), row=1, col=1,
                          annotation_text=f"{'TP' if key == 'target' else key} {v_[key]:g}", annotation_position="top left")
    if v_.get("date") and v_.get("price"):
        d = pd.Timestamp(v_["date"])
        if d >= c.index[0]:
            fig.add_trace(go.Scatter(x=[d], y=[v_["price"]], mode="markers", name="View", marker=dict(size=10, color="#c98500", symbol="diamond")), row=1, col=1)
    fig.update_layout(height=450, margin=dict(l=40, r=20, t=64, b=20), legend=dict(orientation="h", y=1.01, yanchor="bottom", x=0), hovermode="x unified",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", title=dict(text=f"{code} – daily close and volume, 12 months (Yahoo Finance, delayed)", font=dict(size=13), y=0.985, yanchor="top"))
    # mid-grey text and faint grids read on both the light and the dark theme (the page follows the system setting)
    fig.update_layout(font=dict(color="#8a96a3"), legend=dict(font=dict(color="#8a96a3")))
    fig.update_xaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    return fig.to_html(include_plotlyjs=False, full_html=False, config={"displaylogo": False})
