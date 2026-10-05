"""Charts. Every figure the framework draws is built here, so they all look and read the same.

Colour does one job per chart. Up and down bars are a polarity (blue / red, not red / green, which a
colour-blind reader cannot tell apart). Lines drawn over the price take the categorical colours in a fixed
order. Buy and sell marks are told apart by shape and label, not by colour. Two measures on different
scales get two panels, never two y-axes on one.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from osloquant.contract.api import get_entities, get_kdata

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

UP = "#2a78d6"
DOWN = "#e34948"
#: categorical slots for lines over the price, in this fixed order; validated for colour-blind separation
OVERLAY = ["#eb6834", "#1baf7a", "#eda100", "#4a3aa7"]
PRIMARY = "#2a78d6"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def style(fig: go.Figure, title: str | None = None, height: int = 520) -> go.Figure:
    fig.update_layout(
        title={"text": title, "font": {"size": 15, "color": INK}, "x": 0, "xref": "paper", "xanchor": "left"} if title else None,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"family": FONT, "size": 12, "color": INK_SECONDARY},
        height=height,
        margin={"l": 56, "r": 24, "t": 64 if title else 32, "b": 40},
        hovermode="x unified",
        hoverlabel={"bgcolor": SURFACE, "font": {"family": FONT, "color": INK}},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "xanchor": "right", "x": 1, "font": {"color": INK_SECONDARY}},
        bargap=0.2,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickfont={"color": MUTED}, rangeslider_visible=False)
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, zeroline=False, linecolor=SURFACE, tickfont={"color": MUTED})
    return fig


def _skip_weekends(fig: go.Figure) -> None:
    fig.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}])


def _resolve_entity(entity_id: str | None, code: str | None, candidates: list[str]) -> str:
    if entity_id is None and code is not None:
        entity_id = next((e for e in candidates if e.split("_", 2)[2] == code), None)
        if entity_id is None:
            raise LookupError(f"{code} is not among the entities")
    if entity_id is None:
        entity_id = candidates[0]
    return entity_id


def _entity_title(entity_id: str) -> str:
    try:
        from osloquant.contract.api import decode_entity_id, get_entity_schema

        entity_type, _, code = decode_entity_id(entity_id)
        df = get_entities(get_entity_schema(entity_type), entity_ids=[entity_id], columns=["name"])
        return f"{df['name'].iloc[0]} ({code})" if not df.empty else code
    except Exception:
        return entity_id


def draw_kline(
    bars: pd.DataFrame,
    title: str | None = None,
    overlays: pd.DataFrame | None = None,
    subs: pd.DataFrame | None = None,
    marks: pd.DataFrame | None = None,
    height: int = 560,
) -> go.Figure:
    """A price chart.

    :param bars: indexed by timestamp, with close and optionally open / high / low
    :param overlays: lines on the price scale (moving averages, bands), indexed like ``bars``
    :param subs: lines for a panel below the price (MACD, momentum); a column named ``macd`` is drawn as bars
    :param marks: buys and sells with columns timestamp, signal ("buy" / "sell") and optionally price
    """
    has_sub = subs is not None and not subs.empty
    if has_sub:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
    else:
        fig = make_subplots(rows=1, cols=1)

    if {"open", "high", "low"}.issubset(bars.columns):
        fig.add_trace(
            go.Candlestick(
                x=bars.index, open=bars["open"], high=bars["high"], low=bars["low"], close=bars["close"], name="Price",
                increasing={"line": {"color": UP, "width": 1}, "fillcolor": UP},
                decreasing={"line": {"color": DOWN, "width": 1}, "fillcolor": DOWN},
            ),
            row=1, col=1,
        )  # fmt: skip
    else:
        fig.add_trace(go.Scatter(x=bars.index, y=bars["close"], name="Close", mode="lines", line={"color": PRIMARY, "width": 2}), row=1, col=1)

    if overlays is not None:
        for color, column in zip(OVERLAY, overlays.columns, strict=False):
            fig.add_trace(
                go.Scatter(x=overlays.index, y=overlays[column], name=column, mode="lines", line={"color": color, "width": 1.5}),
                row=1, col=1,
            )  # fmt: skip

    if marks is not None and not marks.empty:
        low = bars["low"] if "low" in bars.columns else bars["close"]
        high = bars["high"] if "high" in bars.columns else bars["close"]
        pad = 0.012 * float(bars["close"].max() - bars["close"].min() or bars["close"].max())
        for signal, symbol, anchor, offset in (("buy", "triangle-up", low, -pad), ("sell", "triangle-down", high, pad)):
            rows = marks[(marks["signal"] == signal) & marks["timestamp"].isin(bars.index)]
            if rows.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=rows["timestamp"], y=anchor.reindex(rows["timestamp"]).to_numpy() + offset, name=signal.capitalize(), mode="markers",
                    marker={"symbol": symbol, "size": 10, "color": INK, "line": {"color": SURFACE, "width": 2}},
                    customdata=rows["price"] if "price" in rows.columns else None,
                    hovertemplate=f"{signal.capitalize()}" + (" at %{customdata:.2f}" if "price" in rows.columns else "") + "<extra></extra>",
                ),
                row=1, col=1,
            )  # fmt: skip

    if has_sub:
        lines = [c for c in subs.columns if c != "macd"]
        if "macd" in subs.columns:
            fig.add_trace(go.Bar(x=subs.index, y=subs["macd"], name="macd", marker={"color": MUTED, "line": {"width": 0}}), row=2, col=1)
        for color, column in zip(OVERLAY, lines, strict=False):
            fig.add_trace(
                go.Scatter(x=subs.index, y=subs[column], name=column, mode="lines", line={"color": color, "width": 1.5}),
                row=2, col=1,
            )  # fmt: skip

    style(fig, title=title, height=height)
    _skip_weekends(fig)
    return fig


def draw_factor(factor, entity_id: str | None = None, code: str | None = None, last: int | None = 500) -> go.Figure:
    """One entity's price with the factor's lines and the days its verdict flipped."""
    df = factor.factor_df
    entity_id = _resolve_entity(entity_id, code, df.index.get_level_values("entity_id").unique().tolist())
    one = df.xs(entity_id, level="entity_id")
    if "close" not in one.columns:
        raise ValueError(f"{type(factor).__name__} is not computed from bars, so there is no price to draw it on")
    if last:
        one = one.iloc[-last:]
    signals = factor.get_signal_df()
    signals = signals[signals["entity_id"] == entity_id]
    overlays = one[[c for c in factor.overlay_cols if c in one.columns]] if factor.overlay_cols else None
    subs = one[[c for c in factor.sub_cols if c in one.columns]] if factor.sub_cols else None
    return draw_kline(one, title=f"{_entity_title(entity_id)}: {type(factor).__name__}", overlays=overlays, subs=subs, marks=signals)


def draw_account(trader_name: str) -> go.Figure:
    """The account against its benchmark, both indexed to 100, with the account's drawdown below."""
    from osloquant.trader.stats import get_account_df, get_benchmark_series

    account = get_account_df(trader_name)
    values = account["all_value"]
    benchmark = get_benchmark_series(trader_name, values.index)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.05)
    # a young account is a handful of points: draw them as points, a line through two days says nothing
    mode = "lines+markers" if len(values) < 40 else "lines"
    base_date = values.index[0] if benchmark is None else benchmark.index[0]
    indexed = 100 * values / values.loc[base_date]
    if benchmark is not None:
        bench = 100 * benchmark / benchmark.iloc[0]
        fig.add_trace(
            go.Scatter(x=bench.index, y=bench, name=benchmark.name.split("_", 2)[2], mode=mode, line={"color": MUTED, "width": 2}),
            row=1, col=1,
        )  # fmt: skip
    universe = account["universe_value"].dropna() if "universe_value" in account.columns else pd.Series(dtype=float)
    if len(universe) > 1:
        whole = 100 * universe / universe.loc[base_date]
        fig.add_trace(
            go.Scatter(x=whole.index, y=whole, name="All stocks, equal weight", mode=mode, line={"color": OVERLAY[0], "width": 2}),
            row=1, col=1,
        )  # fmt: skip
    fig.add_trace(go.Scatter(x=indexed.index, y=indexed, name=trader_name, mode=mode, line={"color": PRIMARY, "width": 2}), row=1, col=1)

    peak = values.cummax().clip(lower=float(account["input_money"].iloc[0]))
    drawdown = 100 * (values / peak - 1)
    fig.add_trace(
        go.Scatter(x=drawdown.index, y=drawdown, name="Drawdown, %", mode=mode, line={"color": PRIMARY, "width": 1.5},
                   fill="tozeroy", fillcolor="rgba(42,120,214,0.12)", showlegend=False),
        row=2, col=1,
    )  # fmt: skip
    style(fig, title=f"{trader_name}: account value, indexed to 100 on {base_date:%d %b %Y}", height=560)
    fig.update_yaxes(title_text="Index", row=1, col=1, title_font={"color": MUTED, "size": 11})
    fig.update_yaxes(title_text="Drawdown, %", row=2, col=1, title_font={"color": MUTED, "size": 11})
    return fig


def draw_trades(trader_name: str, entity_id: str, padding_days: int = 30) -> go.Figure:
    """One entity's price with the trader's fills on it."""
    from osloquant.trader.stats import get_orders_df

    orders = get_orders_df(trader_name)
    orders = orders[orders["entity_id"] == entity_id]
    if orders.empty:
        raise LookupError(f"{trader_name} never traded {entity_id}")
    pad = pd.Timedelta(days=padding_days)
    bars = get_kdata(
        entity_id=entity_id,
        start_timestamp=orders["timestamp"].min() - pad,
        end_timestamp=orders["timestamp"].max() + pad,
        columns=["timestamp", "open", "high", "low", "close"],
        index="timestamp",
        drop_index_col=True,
    )
    marks = pd.DataFrame(
        {
            "timestamp": orders["timestamp"],
            "signal": orders["order_type"].map({"order_long": "buy", "order_close_long": "sell"}),
            "price": orders["order_price"],
        }
    )
    return draw_kline(bars, title=f"{_entity_title(entity_id)}: fills by {trader_name}", marks=marks)


def draw_prediction(machine, entity_id: str | None = None, code: str | None = None) -> go.Figure:
    """What the model predicted against what happened, for one entity over the test period."""
    assert machine.pred_y is not None, "predict() first"
    entity_id = _resolve_entity(entity_id, code, machine.pred_y.index.get_level_values("entity_id").unique().tolist())
    pred = machine.pred_y.xs(entity_id, level="entity_id")
    fig = go.Figure()
    if machine.label_method == "raw":
        close = machine.kdata_df["close"].xs(entity_id, level="entity_id")
        close = close[close.index >= pred.index[0]]
        # a prediction made on day t is about day t + predict_steps: draw it there
        target_dates = close.index.to_series().shift(-machine.predict_steps).reindex(pred.index).dropna()
        fig.add_trace(go.Scatter(x=close.index, y=close, name="Close", mode="lines", line={"color": MUTED, "width": 2}))
        fig.add_trace(
            go.Scatter(x=target_dates.to_numpy(), y=pred.reindex(target_dates.index), name="Predicted close", mode="lines", line={"color": PRIMARY, "width": 2})
        )
        title = f"{_entity_title(entity_id)}: close and the close predicted {machine.predict_steps} days earlier"
    else:
        actual = machine.testing_y.xs(entity_id, level="entity_id")
        label = "return" if machine.label_method == "change" else "probability of a rise"
        fig.add_trace(go.Scatter(x=actual.index, y=actual, name=f"Realised {label}", mode="lines", line={"color": MUTED, "width": 2}))
        fig.add_trace(go.Scatter(x=pred.index, y=pred, name="Predicted", mode="lines", line={"color": PRIMARY, "width": 2}))
        title = f"{_entity_title(entity_id)}: {machine.predict_steps}-day {label}, predicted and realised"
    style(fig, title=title, height=420)
    return fig


def coverage_table(schemas: list[type]) -> pd.DataFrame:
    """Rows, entities and date range of each schema's table."""
    from osloquant.contract.api import get_coverage

    rows = []
    for schema in schemas:
        for provider in schema.get_providers():
            try:
                rows.append(get_coverage(schema, provider=provider))
            except Exception as e:  # a table that cannot be read should not take the overview down
                rows.append({"schema": schema.__name__, "provider": provider, "rows": 0, "entities": 0, "first": None, "last": None, "error": str(e)})
    return pd.DataFrame(rows)


__all__ = ["coverage_table", "draw_account", "draw_factor", "draw_kline", "draw_prediction", "draw_trades"]
