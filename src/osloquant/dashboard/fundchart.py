"""The frontier chart on the portfolio page (D68): expected return against volatility, drawn so that the model
portfolios can be read without a legend.

What changed from the first version, and why:

- **It opens on the portfolios.** The frontier, the capital market line and the six portfolios sit between 8 and 16 %
  volatility; the single stocks reach 70 %. The single stocks are one click away, not the default.
- **Every diamond has its name beside it**, placed so that two labels do not overlap, and the tangency portfolio and
  the capital market line carry the Sharpe ratio they stand for.
- **No green and no red.** A portfolio is not up or down; the palette is the accent family and neutrals.
- **The page's own numbers**: per cent with a decimal comma, Norwegian dates, no toolbar, no title inside the plot.

Still Plotly: a scatter of volatility against return is not a time series, and Lightweight Charts draws time series.
The theme (font, grid, colours) is the price chart's.
"""

from __future__ import annotations

import json

from osloquant.dashboard.dates import dato, stempel
from osloquant.dashboard.tall import NBSP, tall

DIV = "chart-front"
PALETTE = ("#1a2126", "#1f5f99", "#0f7c7c", "#6a5acd", "#9a6700", "#8a6d3b", "#5c6770", "#3b6fb6")
GRID, TEXT, ACCENT = "#eef1f3", "#4a5560", "#0f7c7c"
STALE_DAYS = 31
PLOT_W, PLOT_H = 1080, 350          # the plot area the label placement assumes, in pixels
OFFSETS = ((56, 0), (-56, 0), (46, -22), (-46, -22), (46, 22), (-46, 22), (0, -30), (0, 30), (70, -40), (-70, -40), (70, 40), (-70, 40))


def _p(v: float | None, d: int = 1) -> str:
    return "–" if v is None else f"{tall(v * 100, d)}{NBSP}%"


def _place(points: list[tuple[float, float, str]], xr: tuple[float, float], yr: tuple[float, float]) -> list[tuple[int, int]]:
    """An offset in pixels for each label so that no two labels, and no label and another point, overlap. Greedy: the
    first of a dozen positions that is free. Sizes are estimated from the text length."""
    sx, sy = PLOT_W / (xr[1] - xr[0]), PLOT_H / (yr[1] - yr[0])
    px = [((x - xr[0]) * sx, (yr[1] - y) * sy) for x, y, _ in points]
    boxes: list[tuple[float, float, float, float]] = []
    out = []
    for i, (cx, cy) in enumerate(px):
        w, h = 6.4 * len(points[i][2]) + 8, 16
        choice = OFFSETS[0]
        for ox, oy in OFFSETS:
            lx = cx + ox - (w / 2 if ox == 0 else (0 if ox > 0 else w))
            ly = cy + oy - h / 2
            box = (lx, ly, lx + w, ly + h)
            inside = 0 <= box[0] and box[2] <= PLOT_W and 0 <= box[1] and box[3] <= PLOT_H
            hits_box = any(not (box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]) for b in boxes)
            hits_point = any(j != i and box[0] - 7 <= qx <= box[2] + 7 and box[1] - 7 <= qy <= box[3] + 7 for j, (qx, qy) in enumerate(px))
            if inside and not hits_box and not hits_point:
                choice, chosen = (ox, oy), box
                break
        else:
            ox, oy = choice
            lx = cx + ox
            chosen = (lx, cy - h / 2, lx + w, cy + h / 2)
        boxes.append(chosen)
        out.append(choice)
    return out


def age_days(b: dict, today) -> int | None:
    import pandas as pd

    try:
        return int((pd.Timestamp(today).normalize() - pd.Timestamp(str(b["built_at"])[:10])).days)
    except (KeyError, ValueError, TypeError):
        return None


def stale_html(b: dict, today) -> str:
    """A clear mark when the build is older than a month: the weights and the chart are then a month's prices behind."""
    days = age_days(b, today)
    if days is None or days <= STALE_DAYS:
        return ""
    return (f'<div class="warn" id="bygg-gammelt"><b>Bygget er {days} dager gammelt.</b> Porteføljene og grafen er regnet på kurser til {dato(b.get("asof"))}. '
            'Bygg på nytt med <code>oq funds build --write</code> (ett minutt) før du leser vektene som dagens.</div>')


def rf_text(label: str) -> str:
    """The risk-free label as a person reads it (older builds stored it in English)."""
    return (str(label).replace("Norges Bank policy rate", "Norges Banks styringsrente").replace(", rates feed)", ")").replace("rates feed not fetched", "rentene er ikke hentet")
            .replace("fallback", "reserveverdi"))


def html(b: dict, today=None) -> str:
    import plotly.graph_objects as go

    rf = float(b["rf"]) * 100
    fr = [(r["vol"] * 100, r["ret"] * 100) for r in (b.get("frontier") or [])]
    tan = b.get("tangency") or {}
    funds = [f for f in b["funds"] if (f.get("est") or {}).get("vol") is not None]
    fig = go.Figure()
    # 0: the single stocks, off until asked for
    names = list(b["inputs"].keys())
    fig.add_trace(go.Scatter(x=[v["vol"] * 100 for v in b["inputs"].values()], y=[v["mu"] * 100 for v in b["inputs"].values()], mode="markers", name="Enkeltaksjer",
                             marker=dict(size=5, color="#b7c1c9"), text=names, visible=False,
                             hovertemplate="<b>%{text}</b><br>Volatilitet %{x:,.1f} %<br>Forventet avkastning %{y:,.1f} % (EST, krympet snitt)<extra></extra>"))
    if fr:
        fig.add_trace(go.Scatter(x=[p[0] for p in fr], y=[p[1] for p in fr], mode="lines", name="Effisient front", line=dict(color=ACCENT, width=2.4),
                                 hovertemplate="Effisient front<br>Volatilitet %{x:,.1f} %<br>Forventet avkastning %{y:,.1f} % (EST)<extra></extra>"))
    vols = [f["est"]["vol"] * 100 for f in funds] + ([tan["vol"] * 100] if tan.get("vol") else []) + [p[0] for p in fr]
    rets = [f["est"]["ret"] * 100 for f in funds] + ([tan["ret"] * 100] if tan.get("ret") else []) + [p[1] for p in fr]
    xmax = (max(vols) if vols else 20) * 1.22
    ymin, ymax = min([rf, *rets]) - 2.5, (max(rets) if rets else rf + 10) + 3.5
    annotations = []
    sharpe_t = None
    if tan.get("vol"):
        sharpe_t = (tan["ret"] * 100 - rf) / (tan["vol"] * 100)
        fig.add_trace(go.Scatter(x=[0, xmax], y=[rf, rf + sharpe_t * xmax], mode="lines", name="Kapitalmarkedslinjen", line=dict(color="#9a6700", width=1.6, dash="dash"),
                                 hovertemplate="Kapitalmarkedslinjen: risikofri rente blandet med tangensporteføljen<br>Volatilitet %{x:,.1f} %<br>Forventet avkastning %{y:,.1f} % (EST)<extra></extra>"))
        x_lab = min(xmax * 0.30, (tan["vol"] * 100) * 0.55)       # on the empty stretch between the risk-free rate and the portfolios
        annotations.append(dict(x=x_lab, y=rf + sharpe_t * x_lab, text=f"Kapitalmarkedslinjen · Sharpe {tall(sharpe_t, 2)}", showarrow=False, xanchor="left",
                                xshift=10, yshift=-12, font=dict(size=11, color="#9a6700")))
    fig.add_trace(go.Scatter(x=[0], y=[rf], mode="markers", name="Risikofri rente", marker=dict(size=8, color="#9a6700", symbol="circle"),
                             hovertemplate=f"Risikofri rente {tall(rf, 2)} %<br>{rf_text(b.get('rf_label', ''))}<extra></extra>"))
    annotations.append(dict(x=0, y=rf, text=f"Risikofri {tall(rf, 2)}{NBSP}%", showarrow=False, xanchor="left", xshift=9, yshift=-11, font=dict(size=11, color="#9a6700")))
    built = stempel(b["built_at"]) if b.get("built_at") else "?"
    points = []
    for i, f in enumerate(funds):
        e = f["est"]
        top = ", ".join(f"{c} {tall(w * 100, 0)} %" for c, w in list(f["weights"].items())[:5])
        cash = f"<br>Kontanter {tall(f['cash'] * 100, 0)} %" if f.get("cash", 0) > 0.005 else ""
        hover = (f"<b>{f['name']}</b><br>Volatilitet {_p(e['vol'])} · forventet avkastning {_p(e['ret'])} (EST)<br>Sharpe {tall(e.get('sharpe'), 2)} (EST) · {f['n']} aksjer{cash}"
                 f"<br>Størst: {top}<br><span style='color:#8a96a0'>Yahoo-kurser til {dato(b.get('asof'))} via lageret, bygget {built}</span>")
        fig.add_trace(go.Scatter(x=[e["vol"] * 100], y=[e["ret"] * 100], mode="markers", name=f["name"],
                                 marker=dict(size=13, color=PALETTE[i % len(PALETTE)], symbol="diamond", line=dict(color="#ffffff", width=1.2)),
                                 hovertemplate=hover + "<extra></extra>"))
        label = f["name"] + (f" · Sharpe {tall(e.get('sharpe'), 2)}" if "tangens" in f["name"].lower() or "sharpe" in f["name"].lower() else "")
        points.append((e["vol"] * 100, e["ret"] * 100, label))
    for (x, y, label), (ox, oy), i in zip(points, _place(points, (0, xmax), (ymin, ymax)), range(len(points)), strict=True):
        annotations.append(dict(x=x, y=y, text=label, showarrow=True, arrowhead=0, arrowwidth=1, arrowcolor="#c3ccd3", ax=ox, ay=oy, standoff=7,
                                xanchor="center" if ox == 0 else ("left" if ox > 0 else "right"), font=dict(size=11.5, color=PALETTE[i % len(PALETTE)]),
                                bgcolor="rgba(255,255,255,0.85)", borderpad=1))
    fig.update_layout(height=PLOT_H + 70, margin=dict(l=58, r=18, t=12, b=46), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="closest",
                      font=dict(color=TEXT, family='"Segoe UI", Arial, Helvetica, sans-serif', size=11.5), showlegend=False, annotations=annotations,
                      hoverlabel=dict(bgcolor="#ffffff", bordercolor="#d9e0e5", font=dict(color="#1a2126", size=12)), separators=", ")
    axis = dict(gridcolor=GRID, zeroline=False, ticksuffix=f"{NBSP}%", tickformat=",.0f", linecolor="#d9e0e5", ticks="outside", tickcolor="#d9e0e5", title_font=dict(size=11.5))
    fig.update_xaxes(title="Volatilitet per år (EST)", range=[0, xmax], **axis)
    fig.update_yaxes(title="Forventet avkastning per år (EST)", range=[ymin, ymax], **axis)
    chart = fig.to_html(include_plotlyjs=False, full_html=False, div_id=DIV, config={"displayModeBar": False, "responsive": True})
    zoom = json.dumps({"x": [0, xmax], "y": [ymin, ymax]})
    script = ("<script>(function(){var b=document.getElementById('front-aksjer');if(!b||!window.Plotly)return;var on=false,z=" + zoom + ";"
              "b.addEventListener('click',function(){on=!on;var g=document.getElementById('" + DIV + "');Plotly.restyle(g,{visible:on},[0]);"
              "Plotly.relayout(g,on?{'xaxis.autorange':true,'yaxis.autorange':true}:{'xaxis.range':z.x,'yaxis.range':z.y});"
              "b.classList.toggle('on',on);b.textContent=on?'Skjul enkeltaksjene':'Vis enkeltaksjene ('+b.dataset.n+')';});})();</script>")
    head = (f'<div class="pc-head"><h3>Forventet avkastning mot volatilitet <span class="pc-info" title="Forventet avkastning er snittet av de siste '
            f'{b["lookback_years"]:.0f} årene, krympet mot tverrsnittet (James–Stein); volatilitet og samvariasjon fra samme periode (Ledoit–Wolf). Historikken har vært '
            'uvanlig god, så tallene er høye. De er estimater på historikk (EST), ikke en prognose.">i</span></h3>'
            f'<span class="src">Bygget {built} · kurser til {dato(b.get("asof"))} · {len(b["stocks"])} aksjer</span></div>')
    tools = (f'<div class="pc-tools"><button type="button" class="per" id="front-aksjer" data-n="{len(names)}" '
             f'title="Enkeltaksjene strekker aksen til 70 % volatilitet; de er av til du ber om dem">Vis enkeltaksjene ({len(names)})</button>'
             '<span class="src">Diamantene er porteføljene slik de står i dag. Hold over en diamant for vekter og kilde.</span></div>')
    foot = (f'<div class="src">Tallene er estimater på {b["lookback_years"]:.0f} års historikk (EST): de sier hva inndataene sier, ikke hva som skjer. '
            + (f'Tangensporteføljen er punktet på fronten med høyest Sharpe ({tall(sharpe_t, 2)}); kapitalmarkedslinjen går fra den risikofrie renten gjennom det punktet. ' if sharpe_t else '')
            + f'Risikofri rente: {rf_text(b.get("rf_label", ""))}. Ut av prøven slo ingen av oppskriftene likevekt – se tabellen under.</div>')
    return head + tools + chart + script + foot
