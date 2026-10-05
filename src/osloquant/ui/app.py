"""The dashboard: backtests, factors and data coverage, read straight from the local store.

It only reads. Strategies are written and run in code; this is where you look at what they did.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd
from dash import Dash, Input, Output, callback, dcc, html

from osloquant.contract import context
from osloquant.contract.api import get_coverage
from osloquant.contract.drawer import (
    AXIS,
    FONT,
    GRID,
    INK,
    INK_SECONDARY,
    MUTED,
    SURFACE,
    coverage_table,
    draw_account,
    draw_trades,
    style,
)

PAGE = "#f9f9f7"
NAVY = "#003255"

FACTORS = {
    "CrossMaFactor": "5-day average above 10-day average",
    "AboveMaFactor": "Close above 200-day average",
    "GoldCrossFactor": "MACD above its signal line",
    "BullFactor": "MACD and signal line above zero",
    "BollFactor": "Bollinger band mean reversion",
    "MomentumFactor": "12-1 month momentum rank",
}
WINDOWS = {"1 year": 1, "2 years": 2, "5 years": 5}

CARD = {"background": SURFACE, "border": "1px solid rgba(11,11,11,0.10)", "borderRadius": "8px", "padding": "16px", "marginBottom": "16px"}
LABEL = {"fontSize": "12px", "color": MUTED, "marginBottom": "4px"}
TH = {"textAlign": "left", "padding": "6px 12px 6px 0", "color": MUTED, "fontWeight": 500, "fontSize": "12px", "borderBottom": f"1px solid {AXIS}"}
TD = {"padding": "6px 12px 6px 0", "fontSize": "13px", "color": INK, "borderBottom": f"1px solid {GRID}", "fontVariantNumeric": "tabular-nums"}


def _pct(value, digits: int = 1) -> str:
    return "–" if value is None or value != value else f"{100 * value:+.{digits}f} %"


def _num(value, digits: int = 2) -> str:
    return "–" if value is None or value != value else f"{value:,.{digits}f}".replace(",", " ")


def _date(value) -> str:
    return "–" if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%d.%m.%Y")


def _table(headers: list[str], rows: list[list[str]]) -> html.Table:
    return html.Table(
        [html.Thead(html.Tr([html.Th(h, style=TH) for h in headers])), html.Tbody([html.Tr([html.Td(c, style=TD) for c in row]) for row in rows])],
        style={"borderCollapse": "collapse", "width": "100%"},
    )


def _tile(label: str, value: str, note: str | None = None) -> html.Div:
    children = [html.Div(label, style=LABEL), html.Div(value, style={"fontSize": "22px", "color": INK, "fontWeight": 600})]
    if note:
        children.append(html.Div(note, style={"fontSize": "12px", "color": INK_SECONDARY, "marginTop": "2px"}))
    return html.Div(children, style={**CARD, "marginBottom": "0", "flex": "1 1 140px", "minWidth": "140px", "boxSizing": "border-box"})


def _message(text: str) -> html.Div:
    return html.Div(text, style={**CARD, "color": INK_SECONDARY})


def _empty_figure(text: str):
    import plotly.graph_objects as go

    fig = style(go.Figure(), height=320)
    fig.add_annotation(text=text, showarrow=False, font={"color": MUTED, "size": 13})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# -- data access ----------------------------------------------------------------------------------


def _trader_names() -> list[str]:
    from osloquant.trader.stats import get_trader_names

    try:
        return get_trader_names()
    except Exception:
        return []


def _stock_options() -> list[dict]:
    from osloquant.domain import Stock, Stock1dAdjKdata

    try:
        stocks = Stock.query_data(columns=["entity_id", "code", "name"], order=Stock.code.asc())
        recorded = set(Stock1dAdjKdata.query_data(columns=["entity_id"], filters=[Stock1dAdjKdata.timestamp >= _latest_bar() - pd.Timedelta(days=30)])["entity_id"])
    except Exception:
        return []
    return [{"label": f"{r.code}  {r.name}", "value": r.entity_id} for r in stocks.itertuples() if r.entity_id in recorded]


def _latest_bar() -> pd.Timestamp:
    from osloquant.domain import Stock1dAdjKdata

    last = get_coverage(Stock1dAdjKdata)["last"]
    return last if last is not None else pd.Timestamp.now().normalize()


@lru_cache(maxsize=8)
def _factor(name: str, latest: pd.Timestamp):
    """The factor over the whole universe for the last years; cached until new bars arrive."""
    factor_cls = context.factor_cls_registry[name]
    return factor_cls(start_timestamp=latest - pd.DateOffset(years=7), end_timestamp=latest)


# -- layout ---------------------------------------------------------------------------------------


def _traders_tab() -> html.Div:
    names = _trader_names()
    if not names:
        return _message("No backtest is stored yet. Run one with: oq backtest momentum")
    return html.Div(
        [
            html.Div(
                [html.Div("Backtest", style=LABEL), dcc.Dropdown(id="trader", options=names, value=names[0], clearable=False, style={"maxWidth": "360px"})],
                style={"marginBottom": "16px"},
            ),
            html.Div(id="trader-tiles", style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "16px"}),
            html.Div(dcc.Graph(id="trader-account", config={"displaylogo": False}), style=CARD),
            html.Div(id="trader-notes", style={"fontSize": "12px", "color": INK_SECONDARY, "margin": "-8px 0 16px 2px", "maxWidth": "900px", "lineHeight": 1.5}),
            html.Div(
                [
                    html.Div("Fills in one stock", style=LABEL),
                    dcc.Dropdown(id="trader-entity", clearable=False, style={"maxWidth": "360px", "marginBottom": "8px"}),
                    dcc.Graph(id="trader-trades", config={"displaylogo": False}),
                ],
                style=CARD,
            ),
            html.Div([html.Div("Latest fills", style=LABEL), html.Div(id="trader-orders")], style=CARD),
        ]
    )


def _live_names() -> list[str]:
    """The paper accounts: the daily ones first, then the intraday ones."""
    from osloquant.intraday import intraday_account_names
    from osloquant.live import live_account_names

    try:
        return [*live_account_names(), *intraday_account_names()]
    except Exception:
        return []


def _system_card() -> html.Div:
    """Whether the jobs behind the accounts have been running. Status is a word, never a colour alone."""
    from osloquant.health import run_checks

    words = {"ok": "OK", "warn": "Check", "fail": "Not running"}
    try:
        checks = run_checks(tasks=False)
    except Exception as e:
        return _message(f"The health checks could not be made: {e}")
    rows = [[words[c.status], c.name, c.detail, c.hint or ""] for c in checks]
    return html.Div([html.Div("Is it running?", style=LABEL), _table(["", "What", "Finding", "What to do"], rows)], style=CARD)


def _live_tab() -> html.Div:
    names = _live_names()
    if not names:
        return _message("No live account yet. Start the daily paper accounts with: oq live. Start the intraday ones with: oq intraday run")
    return html.Div(
        [
            _system_card(),
            html.Div(
                [html.Div("Paper account", style=LABEL), dcc.Dropdown(id="live", options=names, value=names[0], clearable=False, style={"maxWidth": "360px"})],
                style={"marginBottom": "16px"},
            ),
            html.Div(id="live-tiles", style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "16px"}),
            html.Div(id="live-notes", style={"fontSize": "12px", "color": INK_SECONDARY, "margin": "0 0 16px 2px", "maxWidth": "900px", "lineHeight": 1.5}),
            html.Div([html.Div("Decided, waiting to be filled", style=LABEL), html.Div(id="live-pending")], style=CARD),
            html.Div([html.Div("Holdings", style=LABEL), html.Div(id="live-holdings")], style=CARD),
            html.Div(dcc.Graph(id="live-account", config={"displaylogo": False}), style=CARD),
            html.Div(id="live-signals"),
            html.Div([html.Div("Everything booked, newest first", style=LABEL), html.Div(id="live-orders")], style=CARD),
        ]
    )


def _factors_tab() -> html.Div:
    stocks = _stock_options()
    if not stocks:
        return _message("No bars are stored yet. Record them with: oq record")
    return html.Div(
        [
            html.Div(
                [
                    html.Div([html.Div("Factor", style=LABEL), dcc.Dropdown(id="factor", options=[{"label": f"{k}: {v}", "value": k} for k, v in FACTORS.items()], value="CrossMaFactor", clearable=False)], style={"flex": "2 1 320px"}),
                    html.Div([html.Div("Stock", style=LABEL), dcc.Dropdown(id="factor-entity", options=stocks, value=stocks[0]["value"], clearable=False)], style={"flex": "2 1 260px"}),
                    html.Div([html.Div("Period", style=LABEL), dcc.Dropdown(id="factor-window", options=list(WINDOWS), value="1 year", clearable=False)], style={"flex": "1 1 140px"}),
                ],
                style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "16px"},
            ),
            html.Div(dcc.Graph(id="factor-chart", config={"displaylogo": False}), style=CARD),
            html.Div([html.Div(id="factor-targets-title", style=LABEL), html.Div(id="factor-targets")], style=CARD),
        ]
    )


def _data_tab() -> html.Div:
    df = coverage_table(context.schemas)
    rows = [[r["schema"], r["provider"], _num(r["rows"], 0), _num(r["entities"], 0), _date(r["first"]), _date(r["last"])] for r in df.to_dict("records")]
    return html.Div(
        [
            html.Div(_table(["Schema", "Provider", "Rows", "Entities", "First", "Last"], rows), style=CARD),
            html.Div(
                "Every schema is recorded with Schema.record_data() and read with Schema.query_data(). Prices are Yahoo's and delayed. "
                "The stock list holds companies listed today, so companies that were delisted are missing from the history.",
                style={"fontSize": "12px", "color": INK_SECONDARY, "maxWidth": "900px", "lineHeight": 1.5},
            ),
        ]
    )


def serve_layout() -> html.Div:
    tab_style = {"padding": "10px 16px", "border": "none", "background": PAGE, "color": INK_SECONDARY, "fontFamily": FONT}
    selected = {**tab_style, "color": INK, "fontWeight": 600, "borderBottom": f"2px solid {NAVY}"}
    return html.Div(
        [
            html.Div(
                [html.Div("oslo-quant", style={"fontSize": "20px", "fontWeight": 700, "color": NAVY}), html.Div("Backtests, factors and data for Oslo Børs", style={"fontSize": "13px", "color": INK_SECONDARY})],
                style={"marginBottom": "16px"},
            ),
            dcc.Tabs(
                [
                    dcc.Tab(_traders_tab(), label="Backtests", style=tab_style, selected_style=selected),
                    dcc.Tab(_live_tab(), label="Live", style=tab_style, selected_style=selected),
                    dcc.Tab(_factors_tab(), label="Factors", style=tab_style, selected_style=selected),
                    dcc.Tab(_data_tab(), label="Data", style=tab_style, selected_style=selected),
                ],
                style={"marginBottom": "20px", "borderBottom": f"1px solid {AXIS}"},
            ),
        ],
        style={"fontFamily": FONT, "background": PAGE, "minHeight": "100vh", "padding": "24px 32px", "color": INK, "maxWidth": "1280px", "margin": "0 auto"},
    )


# -- callbacks ------------------------------------------------------------------------------------


@callback(
    Output("trader-tiles", "children"),
    Output("trader-account", "figure"),
    Output("trader-notes", "children"),
    Output("trader-entity", "options"),
    Output("trader-entity", "value"),
    Output("trader-orders", "children"),
    Input("trader", "value"),
)
def show_trader(trader_name: str):
    from osloquant.domain import Stock
    from osloquant.trader.stats import get_orders_df, get_trader_info, get_trader_stats

    stats = get_trader_stats(trader_name)
    info = get_trader_info(trader_name) or {}
    has_benchmark = "benchmark_cagr" in stats
    has_universe = "universe_cagr" in stats
    index_name = stats["benchmark"].split("_", 2)[2] if has_benchmark else ""
    tiles = [
        _tile("Total return", _pct(stats["total_return"]), f"{_date(stats['start'])} to {_date(stats['end'])}"),
        _tile("Return per year", _pct(stats["cagr"]), f"{index_name} {_pct(stats['benchmark_cagr'])} from {_date(stats['benchmark_from'])}" if has_benchmark else None),
        _tile("All stocks, equal weight", _pct(stats["universe_cagr"]) if has_universe else "–", "per year: the hurdle to clear"),
        _tile("Volatility", _pct(stats["volatility"]).lstrip("+"), f"Sharpe {_num(stats['sharpe'])}"),
        _tile("Largest drawdown", _pct(stats["max_drawdown"]), f"{index_name} {_pct(stats['benchmark_max_drawdown'])}" if has_benchmark else None),
        _tile("Round trips", _num(stats["round_trips"], 0), f"{_pct(stats['win_rate']).lstrip('+')} profitable"),
        _tile("Invested on average", _pct(stats["exposure"]).lstrip("+"), f"Turnover {_num(stats['turnover'], 1)}x a year"),
    ]
    fills_at = "the next day's open" if info.get("execution") == "next_open" else "the same close the decision was based on"
    notes = (
        f"Chosen from {_num(info.get('universe_size'), 0)} stocks, acting {info.get('rebalance')}. Decisions are made on the close and filled at {fills_at}, "
        f"with {10000 * (info.get('slippage') or 0):.0f} bp slippage and {10000 * (info.get('buy_cost') or 0):.0f} bp commission each way. "
        "Prices are adjusted for dividends and splits. The stock list holds only companies listed today, so simply owning all of it "
        "already beats the index. That is the orange line, and the one a strategy has to beat."
    )

    orders = get_orders_df(trader_name)
    names = Stock.query_data(columns=["entity_id", "code", "name"]).set_index("entity_id")
    traded = orders.groupby("entity_id").size().sort_values(ascending=False) if not orders.empty else pd.Series(dtype=int)
    options = [{"label": f"{names.loc[e, 'code']}  {names.loc[e, 'name']}  ({n} fills)" if e in names.index else e, "value": e} for e, n in traded.items()]
    rows = []
    for o in orders.sort_values("timestamp", ascending=False).head(25).itertuples():
        code = names.loc[o.entity_id, "code"] if o.entity_id in names.index else o.entity_id
        rows.append([_date(o.timestamp), code, "Buy" if o.order_type == "order_long" else "Sell", _num(o.order_amount, 0), _num(o.order_price), _pct(o.profit_rate) if o.order_type != "order_long" else ""])
    table = _table(["Filled", "Stock", "Side", "Shares", "Price", "Round trip"], rows) if rows else html.Div("No fills.", style={"color": INK_SECONDARY})
    return tiles, draw_account(trader_name), notes, options, (options[0]["value"] if options else None), table


@callback(Output("trader-trades", "figure"), Input("trader-entity", "value"), Input("trader", "value"))
def show_trades(entity_id: str | None, trader_name: str):
    if not entity_id:
        return _empty_figure("This backtest never traded.")
    try:
        return draw_trades(trader_name, entity_id)
    except LookupError:
        return _empty_figure("This backtest never traded this stock.")


@callback(
    Output("factor-chart", "figure"),
    Output("factor-targets-title", "children"),
    Output("factor-targets", "children"),
    Input("factor", "value"),
    Input("factor-entity", "value"),
    Input("factor-window", "value"),
)
def show_factor(name: str, entity_id: str, window: str):
    from osloquant.contract import TargetType
    from osloquant.domain import Stock

    latest = _latest_bar()
    factor = _factor(name, latest)
    try:
        fig = factor.draw(entity_id=entity_id, last=None)
        fig.update_xaxes(range=[latest - pd.DateOffset(years=WINDOWS[window]), latest + pd.Timedelta(days=3)])
        # fit the price axis to the bars in view rather than to the whole history
        bars = factor.factor_df.xs(entity_id, level="entity_id")
        shown = bars[bars.index >= latest - pd.DateOffset(years=WINDOWS[window])]
        if not shown.empty:
            columns = [c for c in ("low", "high", "close", *factor.overlay_cols) if c in shown.columns]
            low, high = float(shown[columns].min().min()), float(shown[columns].max().max())
            fig.update_yaxes(range=[low - 0.04 * (high - low), high + 0.04 * (high - low)], row=1, col=1)
    except (KeyError, LookupError):
        fig = _empty_figure("No bars for this stock in the period.")

    names = Stock.query_data(columns=["entity_id", "code", "name", "sector"]).set_index("entity_id")
    targets = factor.get_targets(latest, TargetType.positive)
    scores = factor.get_scores(latest)
    rows = []
    for e in sorted(targets, key=lambda e: -scores.get(e, 0.0)):
        if e in names.index:
            row = [names.loc[e, "code"], names.loc[e, "name"], names.loc[e, "sector"]]
            rows.append([*row, _num(scores[e])] if not scores.empty else row)
    headers = ["Stock", "Company", "Sector"] + (["Score"] if not scores.empty else [])
    title = f"{len(rows)} of {factor.factor_df.index.get_level_values('entity_id').nunique()} stocks are positive targets on {_date(latest)}"
    return fig, title, (_table(headers, rows) if rows else html.Div("None.", style={"color": INK_SECONDARY}))


@callback(
    Output("live-tiles", "children"),
    Output("live-notes", "children"),
    Output("live-pending", "children"),
    Output("live-holdings", "children"),
    Output("live-account", "figure"),
    Output("live-orders", "children"),
    Output("live-signals", "children"),
    Input("live", "value"),
)
def show_live(name: str):
    from osloquant.intraday import intraday_account_names
    from osloquant.live import account_summary
    from osloquant.trader.stats import get_trader_info

    if name in intraday_account_names():
        return show_intraday(name)
    summary = account_summary(name)
    info = get_trader_info(name) or {}
    tiles = [
        _tile("Value", _num(summary["value"], 0), f"started with {_num(summary['input_money'], 0)}"),
        _tile("Return since the start", _pct(summary["total_return"], 2), f"{summary['sessions']} session{'' if summary['sessions'] == 1 else 's'} from {_date(summary['start'])}"),
        _tile("All stocks, equal weight", _pct(summary["universe_return"], 2), "the hurdle to clear"),
        _tile("OSEBX", _pct(summary["benchmark_return"], 2)),
        _tile("Fills logged before the open", f"{summary['forward_fills']} of {summary['fills']}", "only these are evidence"),
        _tile("Costs paid", _num(summary["costs_paid"], 0), f"dividends received {_num(summary['dividends_received'], 0)}"),
    ]
    notes = (
        f"A paper account running the {summary['strategy']} strategy, stepped forward after each close; last session {_date(summary['last_session'])}. "
        "Decisions are made on the close and filled at the next open at real, unadjusted prices, "
        f"with {10000 * (info.get('slippage') or 0):.0f} bp slippage and {100 * (info.get('buy_cost') or 0):.2f} % commission (at least {_num(info.get('min_cost'), 0)}) per order. "
        "Dividends arrive as cash. No real money is involved. A few weeks of this say nothing either way: the point is the record, not the number."
    )

    pending_rows = [[o["side"].capitalize(), o["code"], o["name"], _date(o["decided_on"])] for o in summary["pending"]]
    pending = _table(["Side", "Stock", "Company", "Decided on the close of"], pending_rows) if pending_rows else html.Div("Nothing waiting.", style={"color": INK_SECONDARY})

    holding_rows = [
        [h["code"], h["name"], _num(h["shares"], 0), _num(h["average_price"]), _num(h["last_price"]), _num(h["value"], 0), _pct(h["profit_rate"])]
        for h in summary["holdings"]
    ]
    if holding_rows:
        holding_rows.append(["Cash", "", "", "", "", _num(summary["cash"], 0), ""])
        holdings = _table(["Stock", "Company", "Shares", "Bought at", "Close", "Value", "Since bought"], holding_rows)
    else:
        holdings = html.Div(f"All in cash: {_num(summary['cash'], 0)}.", style={"color": INK_SECONDARY})

    labels = {"order_long": "Buy", "order_close_long": "Sell", "dividend": "Dividend", "split": "Split"}
    codes = {h["entity_id"]: h["code"] for h in summary["holdings"]}
    order_rows = []
    for o in summary["orders"].sort_values("id", ascending=False).head(40).itertuples():
        is_trade = o.order_type in ("order_long", "order_close_long")
        logged = ("Before the open" if o.forward == 1 else "Late") if is_trade else ""
        result = _pct(o.profit_rate) if o.order_type == "order_close_long" else (_num(o.profit, 0) if o.order_type == "dividend" else "")
        order_rows.append([_date(o.timestamp), labels.get(o.order_type, o.order_type), codes.get(o.entity_id, o.entity_id.split("_", 2)[2]),
                           _num(o.order_amount, 0), _num(o.order_price), _num(o.cost, 0) if is_trade else "", result, logged])  # fmt: skip
    orders = _table(["Day", "What", "Stock", "Shares", "Price", "Commission", "Result", "Decision logged"], order_rows) if order_rows else html.Div("Nothing booked yet. The first fills come at the open after the first evening.", style={"color": INK_SECONDARY})
    figure = draw_account(name) if summary["sessions"] > 1 else _empty_figure("The chart starts with the second session.")
    return tiles, notes, pending, holdings, figure, orders, []


def _time(value) -> str:
    return "–" if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%d.%m %H:%M")


def show_intraday(name: str):
    """The same seven pieces as a daily account, for one that trades through the day."""
    import plotly.graph_objects as go

    from osloquant.contract.drawer import PRIMARY
    from osloquant.intraday import account_summary
    from osloquant.trader.stats import get_trader_info

    summary = account_summary(name)
    info = get_trader_info(name) or {}
    tiles = [
        _tile("Value", _num(summary["value"], 0), f"started with {_num(summary['input_money'], 0)}"),
        _tile("Return since the start", _pct(summary["total_return"], 2), f"since {_time(summary['start'])}"),
        _tile("OSEBX", _pct(summary["benchmark_return"], 2), "over the same days"),
        _tile("Round trips", _num(summary["round_trips"], 0), f"{_pct(summary['win_rate']).lstrip('+')} profitable"),
        _tile("Fills", _num(summary["fills"], 0), f"{summary['forward_fills']} at prices not yet seen when ordered"),
        _tile("Costs paid", _num(summary["costs_paid"], 0), "commission, both ways"),
        _tile(
            "Looks made today",
            f"{summary['coverage']['today_made']} of {summary['coverage']['today_due']}",
            f"{summary['coverage']['share']:.0%} of all since the start" if summary["coverage"]["share"] is not None else "none due yet",
        ),
    ]
    as_of = f" as of the close of {_date(summary['watchlist_as_of'])}" if summary["watchlist_as_of"] is not None else ""
    notes = (
        f"A play-money account trading the {summary['strategy']} rule on 15-minute bars; last look {_time(summary['last_poll'])} Oslo time. "
        f"It may buy: {', '.join(summary['watchlist']) or 'nothing'}{as_of}. "
        "Yahoo's quotes are about 15 minutes late, so a signal is seen a quarter of an hour after its bar closed and the order is filled at the price the market has moved to by then, "
        f"with {10000 * (info.get('slippage') or 0):.0f} bp slippage and {100 * (info.get('buy_cost') or 0):.2f} % commission (at least {_num(info.get('min_cost'), 0)}) per order. "
        "No real money is involved."
    )

    pending_rows = [[o["side"].capitalize(), o["code"], o["name"], o["signal"], o["reason"], _time(o["decided_on"])] for o in summary["pending"]]
    pending = _table(["Side", "Stock", "Company", "Signal", "Why", "Bar"], pending_rows) if pending_rows else html.Div("Nothing waiting.", style={"color": INK_SECONDARY})

    holding_rows = [
        [h["code"], h["name"], _num(h["shares"], 0), _num(h["average_price"]), _num(h["last_price"]), _num(h["value"], 0), _pct(h["profit_rate"])]
        for h in summary["holdings"]
    ]
    if holding_rows:
        holding_rows.append(["Cash", "", "", "", "", _num(summary["cash"], 0), ""])
        holdings = _table(["Stock", "Company", "Shares", "Bought at", "Last", "Value", "Since bought"], holding_rows)
    else:
        holdings = html.Div(f"All in cash: {_num(summary['cash'], 0)}.", style={"color": INK_SECONDARY})

    snapshots = summary["snapshots"]
    if len(snapshots) > 1:
        # drawn against the look number, not the clock: nights and weekends would otherwise be most of the chart
        labels = [t.strftime("%d.%m %H:%M") for t in snapshots.index]
        figure = style(go.Figure(go.Scatter(x=labels, y=snapshots["all_value"], mode="lines", line={"color": PRIMARY, "width": 2}, name=name)), title=f"{name}: account value at each look", height=360)
        figure.update_xaxes(type="category", nticks=8)
    else:
        figure = _empty_figure("The chart starts with the second look.")

    kinds = {"order_long": "Buy", "order_close_long": "Sell", "dividend": "Dividend", "split": "Split"}
    order_rows = []
    for o in summary["orders"].sort_values("id", ascending=False).head(40).itertuples():
        is_trade = o.order_type in ("order_long", "order_close_long")
        result = _pct(o.profit_rate) if o.order_type == "order_close_long" else (_num(o.profit, 0) if o.order_type == "dividend" else "")
        order_rows.append([_time(o.timestamp), kinds.get(o.order_type, o.order_type), o.stock, _num(o.order_amount, 0), _num(o.order_price), _num(o.cost, 0) if is_trade else "", result, o.reason or ""])
    orders = _table(["Bar", "What", "Stock", "Shares", "Price", "Commission", "Result", "Signal"], order_rows) if order_rows else html.Div("Nothing booked yet.", style={"color": INK_SECONDARY})

    signal_rows = [[_time(r.timestamp), r.code, r.stock, _num(r.price), r.reason, r.outcome] for r in summary["signals"].sort_values("id", ascending=False).head(40).itertuples()]
    signal_table = _table(["Bar", "Signal", "Stock", "Price", "Why", "What was done"], signal_rows) if signal_rows else html.Div("The rules have raised nothing yet.", style={"color": INK_SECONDARY})
    signals = html.Div([html.Div("Signals, newest first", style=LABEL), signal_table], style=CARD)
    return tiles, notes, pending, holdings, figure, orders, signals


def create_app() -> Dash:
    import osloquant.domain  # noqa: F401  registers the schemas
    import osloquant.factors  # noqa: F401  registers the factors
    import osloquant.trader  # noqa: F401  registers the trader tables

    app = Dash(__name__, title="oslo-quant", suppress_callback_exceptions=True)
    app.layout = serve_layout
    return app


def main(host: str = "127.0.0.1", port: int = 8050, debug: bool = False) -> None:
    create_app().run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
