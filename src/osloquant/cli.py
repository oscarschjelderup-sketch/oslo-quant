"""The command line: ``oq record``, ``oq status``, ``oq check``, ``oq doctor``, ``oq lab``, ``oq check-factor``, ``oq query``, ``oq targets``, ``oq backtest``, ``oq live``, ``oq intraday``, ``oq ui``."""

from __future__ import annotations

import logging
import sys

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table


def _keep_output_when_there_is_no_console() -> None:
    """Started by a scheduler through pythonw there is nowhere to print. Keep what would have been printed in a log."""
    if sys.stdout is not None:
        return
    from pathlib import Path

    from osloquant.env import data_path, oq_env

    data_path()
    log = Path(oq_env["log_path"]) / f"headless-{pd.Timestamp.now():%Y-%m}.log"
    sys.stdout = sys.stderr = log.open("a", encoding="utf-8", buffering=1)
    print(f"=== {pd.Timestamp.now():%Y-%m-%d %H:%M:%S} {' '.join(sys.argv[1:])} ===")


_keep_output_when_there_is_no_console()

app = typer.Typer(add_completion=False, help="oslo-quant: record data, select targets and backtest strategies on Oslo Børs.")
console = Console()


def _setup(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")
    import osloquant.domain  # noqa: F401
    import osloquant.factors  # noqa: F401
    import osloquant.trader  # noqa: F401


def _codes(value: str | None) -> list[str] | None:
    return [c.strip().upper().removesuffix(".OL") for c in value.split(",") if c.strip()] if value else None


def _pct(value, digits: int = 1) -> str:
    return "–" if value is None or value != value else f"{100 * value:+.{digits}f} %"


@app.command()
def record(
    codes: str = typer.Option(None, help="Comma-separated stock codes, e.g. EQNR,DNB. All stocks when omitted."),
    finance: bool = typer.Option(False, "--finance", help="Also record financial statements and ratios (slow: six requests per stock)."),
    raw: bool = typer.Option(False, "--raw", help="Also record unadjusted bars."),
    force: bool = typer.Option(False, "--force", help="Download everything again instead of only what is missing."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Record the entity lists and daily bars from Yahoo. Run it again any time: only what is missing is fetched."""
    _setup(verbose)
    from osloquant.domain import (
        BalanceSheet,
        CashFlowStatement,
        Currency,
        Currency1dKdata,
        FinanceFactor,
        Future,
        Future1dKdata,
        IncomeStatement,
        Index,
        Index1dKdata,
        Stock,
        Stock1dAdjKdata,
        Stock1dKdata,
        StockAction,
    )
    from osloquant.recorders.yahoo import client

    client.clear_history_cache()
    stock_codes = _codes(codes)
    steps = [(schema, {}) for schema in (Stock, Index, Future, Currency)]
    # the actions ask for the longest stretch, so they go first and the bar tables reuse the same download
    steps.append((StockAction, {"codes": stock_codes, "force_update": force}))
    steps.append((Stock1dAdjKdata, {"codes": stock_codes, "force_update": force}))
    if raw:
        steps.append((Stock1dKdata, {"codes": stock_codes, "force_update": force}))
    steps += [(schema, {"force_update": force}) for schema in (Index1dKdata, Future1dKdata, Currency1dKdata)]
    if finance:
        steps += [(schema, {"codes": stock_codes, "force_update": force}) for schema in (IncomeStatement, BalanceSheet, CashFlowStatement, FinanceFactor)]

    for schema, kwargs in steps:
        with console.status(f"Recording {schema.__name__} ..."):
            summary = schema.record_data(provider="yahoo", **kwargs)
        console.print(f"[green]ok[/green] {summary}" if not summary.failed else f"[yellow]partly[/yellow] {summary}")


@app.command()
def status() -> None:
    """What is stored: rows, entities and date range per schema."""
    _setup()
    from osloquant.contract import context
    from osloquant.contract.drawer import coverage_table
    from osloquant.env import data_path

    table = Table(title=f"Store: {data_path()}")
    for column in ("Schema", "Provider", "Rows", "Entities", "First", "Last"):
        table.add_column(column, justify="right" if column in ("Rows", "Entities") else "left")
    for r in coverage_table(context.schemas).to_dict("records"):
        first, last = (pd.Timestamp(v).strftime("%Y-%m-%d") if v is not None and not pd.isna(v) else "–" for v in (r["first"], r["last"]))
        table.add_row(r["schema"], r["provider"], f"{r['rows']:,}", f"{r['entities']:,}", first, last)
    console.print(table)


@app.command()
def check(threshold: float = typer.Option(0.4, help="Flag a bar whose close-to-close move, opening gap or open-to-close move exceeds this.")) -> None:
    """List the extreme bars in the adjusted stock prices, so a vendor error can be told from a real crash.

    A real one stays. A vendor error goes into resources/data_exceptions.yaml with its reason.
    """
    _setup()
    from osloquant.domain import Stock1dAdjKdata

    df = Stock1dAdjKdata.query_data(columns=["code", "timestamp", "open", "close", "volume", "change_pct"])
    if df.empty:
        console.print("No bars are stored. Run: oq record")
        raise typer.Exit(1)
    df["gap"] = df["open"] / df.groupby("code")["close"].shift(1) - 1
    df["intraday"] = df["close"] / df["open"] - 1
    extreme = df[(df[["change_pct", "gap", "intraday"]].abs() > threshold).any(axis=1)]

    table = Table(title=f"{len(extreme)} bars of {len(df):,} move more than {threshold:.0%}")
    for column in ("Code", "Date", "Close to close", "Opening gap", "Open to close", "Volume"):
        table.add_column(column, justify="left" if column in ("Code", "Date") else "right")
    for r in extreme.itertuples():
        table.add_row(r.code, f"{r.timestamp:%Y-%m-%d}", _pct(r.change_pct), _pct(r.gap), _pct(r.intraday), f"{r.volume:,.0f}")
    console.print(table)


@app.command()
def query(
    schema: str = typer.Argument(..., help="Schema name, e.g. Stock1dAdjKdata or FinanceFactor."),
    code: str = typer.Option(None, help="One code, e.g. EQNR."),
    start: str = typer.Option(None, help="First date, YYYY-MM-DD."),
    limit: int = typer.Option(10, help="Number of rows; the newest are shown."),
) -> None:
    """Print the newest rows of a schema."""
    _setup()
    from osloquant.contract import context

    data_schema = context.schema_by_name(schema)
    df = data_schema.query_data(code=code.upper() if code else None, start_timestamp=start, order=data_schema.timestamp.desc(), limit=limit)
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        console.print(df.iloc[::-1].drop(columns=["id"], errors="ignore").to_string(index=False))


@app.command()
def targets(
    factor: str = typer.Argument("MomentumFactor", help="Factor class name, e.g. CrossMaFactor, AboveMaFactor, GoldCrossFactor, MomentumFactor, GoodCompanyFactor."),
    date: str = typer.Option(None, help="As of this date; the newest stored bar when omitted."),
) -> None:
    """The stocks a factor selects on a given day."""
    _setup()
    from osloquant.contract import TargetType, context
    from osloquant.contract.api import get_coverage
    from osloquant.domain import Stock, Stock1dAdjKdata

    if factor not in context.factor_cls_registry:
        raise typer.BadParameter(f"unknown factor; known: {', '.join(sorted(context.factor_cls_registry))}")
    as_of = pd.Timestamp(date) if date else get_coverage(Stock1dAdjKdata)["last"]
    if as_of is None:
        console.print("No bars are stored. Run: oq record")
        raise typer.Exit(1)
    instance = context.factor_cls_registry[factor](start_timestamp=as_of - pd.DateOffset(years=3), end_timestamp=as_of)
    selected = instance.get_targets(as_of, TargetType.positive)
    scores = instance.get_scores(as_of)
    names = Stock.query_data(columns=["entity_id", "code", "name", "sector"]).set_index("entity_id")

    table = Table(title=f"{factor}: {len(selected)} positive targets on {as_of:%Y-%m-%d}")
    for column in ("Code", "Company", "Sector", "Score"):
        table.add_column(column)
    for entity_id in sorted(selected, key=lambda e: -scores.get(e, 0.0)):
        row = names.loc[entity_id]
        table.add_row(row["code"], row["name"], row["sector"], f"{scores[entity_id]:.2f}" if entity_id in scores.index else "")
    console.print(table)


@app.command()
def backtest(
    strategy: str = typer.Argument("momentum", help="One of: ma, macd, trend, momentum."),
    start: str = typer.Option("2015-01-01", help="First day."),
    end: str = typer.Option(None, help="Last day; today when omitted."),
    codes: str = typer.Option(None, help="Comma-separated stock codes; the whole universe when omitted."),
    positions: int = typer.Option(10, help="Number of equal slots the account is split in."),
    name: str = typer.Option(None, help="Name to store the run under; the strategy name when omitted."),
) -> None:
    """Run one of the sample strategies and store the result. Look at it with: oq ui"""
    _setup()
    from osloquant.samples import SAMPLE_TRADERS

    if strategy not in SAMPLE_TRADERS:
        raise typer.BadParameter(f"unknown strategy; known: {', '.join(SAMPLE_TRADERS)}")
    with console.status(f"Running {strategy} ..."):
        trader = SAMPLE_TRADERS[strategy](
            codes=_codes(codes),
            start_timestamp=start,
            end_timestamp=end or pd.Timestamp.now().normalize(),
            max_positions=positions,
            trader_name=name or strategy,
        ).run()
    print_stats(trader.stats())


def print_stats(stats: dict) -> None:
    table = Table(title=f"{stats['trader_name']}: {stats['start']:%Y-%m-%d} to {stats['end']:%Y-%m-%d}")
    table.add_column("")
    table.add_column("Strategy", justify="right")
    has_benchmark = "benchmark_cagr" in stats
    has_universe = "universe_cagr" in stats
    if has_universe:
        table.add_column("All stocks, equal weight", justify="right")
    if has_benchmark:
        table.add_column(stats["benchmark"].split("_", 2)[2], justify="right")

    def row(label: str, own: str, whole: str = "", bench: str = "") -> None:
        table.add_row(label, own, *([whole] if has_universe else []), *([bench] if has_benchmark else []))

    row("Total return", _pct(stats["total_return"]), _pct(stats.get("universe_total_return")), _pct(stats.get("benchmark_total_return")))
    row("Return per year", _pct(stats["cagr"]), _pct(stats.get("universe_cagr")), _pct(stats.get("benchmark_cagr")))
    row("Volatility", _pct(stats["volatility"]).lstrip("+"), _pct(stats.get("universe_volatility")).lstrip("+"), _pct(stats.get("benchmark_volatility")).lstrip("+"))
    row("Sharpe", f"{stats['sharpe']:.2f}")
    row("Largest drawdown", _pct(stats["max_drawdown"]), _pct(stats.get("universe_max_drawdown")), _pct(stats.get("benchmark_max_drawdown")))
    row("Round trips", f"{stats['round_trips']}")
    row("Profitable round trips", _pct(stats["win_rate"]).lstrip("+"))
    row("Invested on average", _pct(stats["exposure"]).lstrip("+"))
    row("Turnover per year", f"{stats['turnover']:.1f}x")
    row("Costs paid", f"{stats['costs_paid']:,.0f}")
    console.print(table)
    if has_benchmark and stats["benchmark_from"] > stats["start"] + pd.Timedelta(days=10):
        console.print(
            f"The benchmark only has data from {stats['benchmark_from']:%Y-%m-%d}; over those days the strategy returned "
            f"{_pct(stats['same_days_cagr'])} a year."
        )
    console.print(
        "[dim]The stock list holds only companies listed today, which flatters every backtest. "
        "Compare with the equal-weight column, not only with the index.[/dim]"
    )


@app.command()
def traders() -> None:
    """The stored backtests, side by side."""
    _setup()
    from osloquant.trader.stats import get_trader_names, get_trader_stats

    names = get_trader_names()
    if not names:
        console.print("No backtest is stored yet. Run one with: oq backtest momentum")
        return
    table = Table(title="Stored backtests")
    for column in ("Trader", "From", "To", "Per year", "Volatility", "Sharpe", "Drawdown", "All stocks per year", "Index per year"):
        table.add_column(column, justify="left" if column == "Trader" else "right")
    for trader_name in names:
        s = get_trader_stats(trader_name)
        table.add_row(
            trader_name, f"{s['start']:%Y-%m-%d}", f"{s['end']:%Y-%m-%d}", _pct(s["cagr"]), _pct(s["volatility"]).lstrip("+"),
            f"{s['sharpe']:.2f}", _pct(s["max_drawdown"]), _pct(s.get("universe_cagr")), _pct(s.get("benchmark_cagr")),
        )  # fmt: skip
    console.print(table)


@app.command()
def live(
    status_only: bool = typer.Option(False, "--status", help="Only show where the accounts stand; record and step nothing."),
    no_record: bool = typer.Option(False, "--no-record", help="Step the accounts on the data already stored."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Step the paper accounts forward to the last completed session. Meant to run every evening after the close.

    Orders decided on an earlier evening are filled at the session's open, the holdings are valued at its close,
    and tonight's decisions are written down to be filled at the next open. Running it twice changes nothing.
    """
    _setup(verbose)
    from osloquant.live import account_summary, live_account_names, load_config, run_live

    config = load_config()
    if config.created:
        console.print(f"Wrote the default accounts to {config.path}. Edit that file to change them.")
    if not status_only:
        with console.status("Recording today's data and stepping the accounts ..."):
            run = run_live(record=not no_record, config=config)
        _log_live_run(run)
        if run.record_error:
            console.print(f"[yellow]Recording failed ({run.record_error}); the accounts were stepped on stored data.[/yellow]")
        for summary in run.recorded:
            if summary.failed:
                console.print(f"[yellow]partly[/yellow] {summary}")
        if run.session is None:
            console.print("No completed session in the store yet.")
            raise typer.Exit(1)
        for result in run.results:
            if result.outcome == "failed":
                console.print(f"[red]{result.name} failed:[/red] {result.error}")
            elif result.outcome == "up to date":
                console.print(f"{result.name}: already at {run.session:%Y-%m-%d}, nothing to do")
            else:
                days = ", ".join(f"{d:%Y-%m-%d}" for d in result.sessions)
                console.print(f"[green]{result.name}[/green] {result.outcome}: {days}")
                if len(result.sessions) > 1:
                    console.print("  [yellow]More than one session in one run: the fills of the earlier ones were decided late and do not count as forward.[/yellow]")

    names = live_account_names()
    if not names:
        console.print("No live account yet. Run: oq live")
        return
    for name in names:
        print_live_account(account_summary(name), active=name in {a.name for a in config.accounts})
    if not status_only and any(r.outcome == "failed" for r in run.results):
        raise typer.Exit(1)
    if not status_only and run.record_error:
        # tells a scheduler that the evening's data is still missing and the run is worth repeating
        raise typer.Exit(2)


def _log_live_run(run) -> None:
    """One line per run in logs/live.log, so that a job nobody watched can be checked afterwards."""
    from pathlib import Path

    from osloquant.env import oq_env

    outcomes = ", ".join(f"{r.name}={r.outcome}" + (f" ({len(r.sessions)})" if r.sessions else "") for r in run.results)
    session = f"{run.session:%Y-%m-%d}" if run.session is not None else "none"
    line = f"{run.wall_clock:%Y-%m-%d %H:%M}Z session={session} {outcomes}"
    if run.record_error:
        line += f" record_error={run.record_error}"
    with (Path(oq_env["log_path"]) / "live.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def print_live_account(summary: dict, active: bool = True) -> None:
    title = f"{summary['name']} ({summary['strategy']}): {summary['start']:%Y-%m-%d} to {summary['last_session']:%Y-%m-%d}, {summary['sessions']} session{'' if summary['sessions'] == 1 else 's'}"
    if not active:
        title += "  [stopped: no longer in live.yaml]"
    table = Table(title=title)
    for column in ("Value", "Return", "All stocks, equal weight", "OSEBX", "Cash", "Costs paid", "Dividends", "Fills logged before the open"):
        table.add_column(column, justify="right")
    table.add_row(
        f"{summary['value']:,.0f}", _pct(summary["total_return"]), _pct(summary["universe_return"]), _pct(summary["benchmark_return"]),
        f"{summary['cash']:,.0f}", f"{summary['costs_paid']:,.0f}", f"{summary['dividends_received']:,.0f}", f"{summary['forward_fills']} of {summary['fills']}",
    )  # fmt: skip
    console.print(table)

    if summary["holdings"]:
        holdings = Table(title="Holdings at the close")
        for column in ("Code", "Company", "Shares", "Bought at", "Close", "Value", "Since bought"):
            holdings.add_column(column, justify="left" if column in ("Code", "Company") else "right")
        for h in summary["holdings"]:
            holdings.add_row(h["code"], h["name"], f"{h['shares']:,.0f}", f"{h['average_price']:.2f}", f"{h['last_price']:.2f}", f"{h['value']:,.0f}", _pct(h["profit_rate"]))
        console.print(holdings)
    if summary["pending"]:
        pending = Table(title="Decided, to be filled at the next open")
        for column in ("Side", "Code", "Company", "Decided on the close of"):
            pending.add_column(column)
        for o in summary["pending"]:
            pending.add_row(o["side"].capitalize(), o["code"], o["name"], f"{o['decided_on']:%Y-%m-%d}")
        console.print(pending)
    elif not summary["holdings"]:
        console.print("  No holdings and nothing decided.")


@app.command()
def doctor() -> None:
    """Check that everything that should be running is: data, accounts, the day's looks, the scheduled tasks.

    A job that silently does not run looks exactly like a quiet market. This tells the two apart.
    """
    _setup()
    from osloquant.health import FAIL, OK, run_checks

    marks = {"ok": "[green]ok[/green]", "warn": "[yellow]check[/yellow]", "fail": "[red]FAILED[/red]"}
    with console.status("Checking ..."):
        checks = run_checks()
    table = Table(title="oslo-quant health")
    for column in ("", "What", "Finding", "What to do"):
        table.add_column(column)
    for check in checks:
        table.add_row(marks[check.status], check.name, check.detail, check.hint or "")
    console.print(table)
    if all(c.status == OK for c in checks):
        console.print("Everything is running.")
    if any(c.status == FAIL for c in checks):
        raise typer.Exit(1)


@app.command()
def lab(
    start: str = typer.Option("2001-01-01", help="First month to trade."),
    capital: float = typer.Option(100_000, help="The account's size in NOK: with a NOK 29 minimum per order, it decides what a trade costs."),
    buffer: float = typer.Option(0.25, help="Leave a holding alone while it is within this share of its target weight."),
    flat_cost: float = typer.Option(None, help="Instead of the account's costs, a plain cost per unit traded, e.g. 0.004."),
    overnight: bool = typer.Option(True, help="Also split the returns into overnight and intraday."),
    sensitivity: bool = typer.Option(True, help="Also show the excess under other account sizes and costs."),
    odegaard: str = typer.Option(None, help="Path to Ødegaard's Norway_market_portfolios_monthly.csv: measures what the list of survivors adds."),
) -> None:
    """Test the documented strategies against the equal-weight basket, with the tests that tell an edge from luck.

    The strategies and their settings are fixed in advance (see osloquant/research/lab.py), so nothing here is
    tuned to the data. An edge counts when it beats the basket of the same stocks after costs, when the bootstrap
    interval of that excess stays above zero, and when its deflated Sharpe ratio (which charges for every variant
    tried) is high.
    """
    _setup()
    from osloquant.research.lab import STRATEGIES, Costs, cost_sensitivity, overnight_split, run_lab, survivorship_gap

    costs = Costs.flat(flat_cost) if flat_cost is not None else Costs(capital=capital, buffer=buffer)
    with console.status("Running the strategies (about a minute) ..."):
        result = run_lab(start=start, cost=costs)
    console.print(f"[bold]The lab, {result.start:%Y-%m-%d} to {result.end:%Y-%m-%d}[/bold]: {result.stocks} stocks. Costs: {costs.describe()}.")
    table = Table()
    columns = ("Strategy", "Source", "Per year", "Before costs", "Over the basket", "95 % interval", "Years ahead", "Deflated Sharpe",
               "Largest drawdown", "Positions", "Turnover", "2001-08", "2009-16", "2017-")  # fmt: skip
    for column in columns:
        table.add_column(column, justify="left" if column in ("Strategy", "Source") else "right")
    for strategy in STRATEGIES:
        r = result.table.loc[strategy.name]
        if r["per_year"] <= -0.99:
            # the NOK 29 minimum on many small orders, paid out of a shrinking account, takes all of it
            table.add_row(strategy.name, strategy.source, "ruined", _pct(r["before_costs"]), "", "", "", "", "", f"{r['positions']:.0f}", f"{r['turnover']:.1f}x", "", "", "")
            continue
        if strategy.name == "equal_weight":
            table.add_row(strategy.name, strategy.source, _pct(r["per_year"]), _pct(r["before_costs"]), "", "", "", "", _pct(r["max_drawdown"]),
                          f"{r['positions']:.0f}", f"{r['turnover']:.1f}x", "", "", "")  # fmt: skip
            continue
        table.add_row(
            strategy.name, strategy.source, _pct(r["per_year"]), _pct(r["before_costs"]), _pct(r["excess"]),
            f"{_pct(r['excess_low'])} to {_pct(r['excess_high'])}", f"{r['years_ahead']:.0%}", f"{r['dsr']:.2f}",
            _pct(r["max_drawdown"]), f"{r['positions']:.0f}", f"{r['turnover']:.1f}x", _pct(r["2001-2008"]), _pct(r["2009-2016"]), _pct(r["2017-"]),
        )  # fmt: skip
    console.print(table)
    o = result.overfitting
    console.print(
        f"Overfitting in the momentum family ({o['configurations']} settings, {o['splits']:,} splits): PBO {o['pbo']:.0%}; the in-sample best "
        f"kept {o['degradation']:.0%} of its Sharpe out of sample and lost money in {o['probability_of_loss']:.0%} of the splits. "
        f"Best over the whole period: {o['best_in_full_sample']} ({_pct(o['best_excess'])} a year over the basket)."
    )
    console.print(f"Trials charged for: {o['trials']} variants, worth {o['effective_trials']:.1f} independent ones.")
    if result.walk_forward:
        w = result.walk_forward
        picks = list(w["picks"].values())
        chosen = f"it picked {picks[0]} every year" if not w["switches"] else f"{w['switches']} changes of setting, most often {max(set(picks), key=picks.count)}"
        console.print(
            f"Re-tuning the momentum settings every January on the years before, from {w['from']:%Y}: {_pct(w['tuned_excess'])} a year over the basket "
            f"({chosen}), against {_pct(w['textbook_excess'])} for keeping the textbook 12-1 top fifth."
        )

    if sensitivity:
        with console.status("Running the strategies under other costs ..."):
            grid = cost_sensitivity(start=start)
        cost_table = Table(title="Excess a year over the basket, by what trading costs (the basket's own return in its row)")
        cost_table.add_column("Strategy")
        for label in grid.columns:
            cost_table.add_column(label, justify="right")
        for name, row in grid.iterrows():
            cost_table.add_row(name, *["ruined" if v <= -0.99 else _pct(v) for v in row])
        console.print(cost_table)

    if odegaard:
        gap = survivorship_gap(odegaard, start=start)
        periods = ", ".join(f"{label} {_pct(value)}" for label, value in gap["periods"].items())
        console.print(
            f"Survivorship, {gap['from']} to {gap['to']}: our basket of today's stocks {_pct(gap['ours'])} a year, every stock listed at the time "
            f"(Ødegaard, equal weight) {_pct(gap['market_ew'])}: the list of survivors adds {_pct(gap['gap'])} a year ({periods}). "
            "It flatters every absolute return above; the comparisons with the basket share the same list."
        )

    if overnight:
        with console.status("Splitting the returns into overnight and intraday ..."):
            split = overnight_split()
        night = Table(title="Where the returns are earned, 2010 onwards, a year")
        for column in ("Stocks", "Close to open (overnight)", "Open to close (intraday)", "Total"):
            night.add_column(column, justify="left" if column == "Stocks" else "right")
        for group, row in split.iterrows():
            night.add_row(group, _pct(row["overnight"]), _pct(row["intraday"]), _pct(row["total"]))
        console.print(night)
    console.print(
        "[dim]Over the basket: the strategy's return a year minus that of the equal-weight basket of the same stocks. The interval is a block "
        "bootstrap of that excess. Deflated Sharpe: the probability that the excess is skill and not the luck of the best of the variants tried; "
        "0.95 or more is convincing. The stocks are today's survivors, and cash earns nothing.[/dim]"
    )


@app.command("check-factor")
def check_factor(
    factor: str = typer.Argument(..., help="Factor class name, e.g. GoldCrossFactor, or package.module:ClassName for your own."),
    codes: str = typer.Option(None, help="Comma-separated codes to check on; all stocks when omitted."),
    samples: int = typer.Option(6, help="How many dates to test for look-ahead."),
) -> None:
    """Does a factor look into the future, and does it depend on how much history it is given?

    After freqtrade's lookahead-analysis and recursive-analysis. The factor is computed on all the data and on
    the data up to each of a few dates; any difference in what it says about such a date is look-ahead. Then the
    newest date is computed with less and less history before it.
    """
    _setup()
    import importlib

    from osloquant.contract import context
    from osloquant.research.checks import lookahead_check, warmup_check

    if ":" in factor:
        module, _, name = factor.partition(":")
        factor_cls = getattr(importlib.import_module(module), name)
    elif factor in context.factor_cls_registry:
        factor_cls = context.factor_cls_registry[factor]
    else:
        raise typer.BadParameter(f"unknown factor; known: {', '.join(sorted(context.factor_cls_registry))}")
    settings = {"codes": _codes(codes)} if codes else {}
    start = pd.Timestamp.now().normalize() - pd.DateOffset(years=6)

    with console.status("Looking for look-ahead ..."):
        found = lookahead_check(factor_cls, start=start, samples=samples, **settings)
    if found.empty:
        console.print(f"[green]No look-ahead[/green]: on {samples} dates, {factor} said the same with and without the days after.")
    else:
        console.print(f"[red]Look-ahead found[/red] on {found['date'].nunique()} of {samples} dates, in {', '.join(sorted(found['column'].unique()))}:")
        console.print(found.head(10).to_string(index=False))

    with console.status("Checking the warm-up ..."):
        newest = factor_cls(start_timestamp=start, **settings).factor_df.index.get_level_values("timestamp").max()
        warm = warmup_check(factor_cls, newest, **settings)
    table = Table(title=f"{factor} on {newest:%Y-%m-%d}, with less history before it")
    for column in ("History", "Largest deviation", "In", "Not computable", "Verdicts changed"):
        table.add_column(column, justify="left" if column == "In" else "right")
    for r in warm.itertuples():
        table.add_row(f"{r.warmup_days} days", f"{r.largest_deviation:.2%}", r.column or "", f"{r.not_computable}", f"{r.verdicts_changed} of {r.entities}")
    console.print(table)
    console.print("[dim]The traders load 400 days before their start (pre_load_days). If a shorter history changes verdicts, give them more.[/dim]")


intraday_app = typer.Typer(add_completion=False, help="Intraday paper accounts: signal rules on 15-minute bars. Play money only.")
app.add_typer(intraday_app, name="intraday")


def _intraday_config():
    from osloquant.intraday import load_config

    config = load_config()
    if config.created:
        console.print(f"Wrote the default intraday accounts to {config.path}. Edit that file to change the rules.")
    return config


def _print_poll(result) -> None:
    from osloquant.intraday.engine import stock_names

    names = stock_names()
    code = lambda e: names.loc[e, "code"] if e in names.index else e.split("_", 2)[2]  # noqa: E731
    lag = f", newest bar {result.feed_lag.total_seconds() / 60:.0f} min old" if result.feed_lag is not None else ""
    console.print(f"[bold]{result.now:%Y-%m-%d %H:%M}[/bold] Oslo{lag}")
    if result.record_error:
        console.print(f"  [yellow]quotes could not be fetched: {result.record_error}[/yellow]")
    for name, error in result.errors.items():
        console.print(f"  [red]{name} failed:[/red] {error}")
    for report in result.reports:
        console.print(f"  {report.name}: {report.value:,.0f}")
        for fill in report.fills:
            console.print(f"    [green]filled[/green] {fill['side']} {fill['shares']:,.0f} {code(fill['entity_id'])} at {fill['price']:.2f} ({fill['bar']:%H:%M} bar): {fill['reason']}")
        for signal in report.signals:
            console.print(f"    signal {signal['code']} {code(signal['entity_id'])} at {signal['price']:.2f} ({signal['timestamp']:%H:%M} bar): {signal['reason']} -> {signal['outcome']}")


def _log_intraday(result) -> None:
    from pathlib import Path

    from osloquant.env import oq_env

    parts = [f"{r.name}={r.value:.0f} fills={len(r.fills)} signals={len(r.signals)}" for r in result.reports]
    parts += [f"{name}=FAILED {error}" for name, error in result.errors.items()]
    line = f"{result.now:%Y-%m-%d %H:%M} " + ", ".join(parts)
    if result.feed_lag is not None:
        line += f" feed_lag={result.feed_lag.total_seconds() / 60:.0f}min"
    if result.record_error:
        line += f" record_error={result.record_error}"
    with (Path(oq_env["log_path"]) / "intraday.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


@intraday_app.command("run")
def intraday_run(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """Follow today's session: look every 15 minutes while Oslo is open, then stop. Meant to be started each morning.

    Started before the open it waits. Started in the middle of the day it looks at once and carries on.
    """
    _setup(verbose)
    from osloquant.intraday import run_session

    config = _intraday_config()
    if not config.accounts:
        console.print("No intraday accounts are configured.")
        raise typer.Exit(1)

    def on_poll(result) -> None:
        _print_poll(result)
        _log_intraday(result)

    console.print(f"Following {len(config.accounts)} intraday accounts until the close. Play money only. Ctrl+C stops it.")
    polls = run_session(config, on_poll=on_poll)
    console.print(f"Session over after {polls} looks." if polls else "The market is closed: nothing to follow today.")


@intraday_app.command("poll")
def intraday_poll(
    no_record: bool = typer.Option(False, "--no-record", help="Use the bars already stored."),
    if_open: bool = typer.Option(False, "--if-open", help="Do nothing outside Oslo's trading hours. For a scheduler that calls this every 15 minutes."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Look at the market once, now: fill, value, raise signals, send orders. What `run` does every 15 minutes."""
    _setup(verbose)
    from osloquant.intraday import poll
    from osloquant.intraday.engine import market_now, worth_looking

    config = _intraday_config()
    if if_open and not worth_looking(market_now(), config.feed_delay):
        console.print("Oslo is closed: nothing to look at.")
        return
    result = poll(config, record=not no_record)
    _print_poll(result)
    _log_intraday(result)
    if result.errors:
        raise typer.Exit(1)


@intraday_app.command("status")
def intraday_status(signals: int = typer.Option(15, help="How many of the latest signals to list per account.")) -> None:
    """Where the intraday accounts stand, and what their rules have said lately."""
    _setup()
    from osloquant.intraday import account_summary, intraday_account_names

    names = intraday_account_names()
    if not names:
        console.print("No intraday account yet. Start them with: oq intraday run")
        return
    for name in names:
        print_intraday_account(account_summary(name), signals)


def print_intraday_account(summary: dict, signals: int = 15) -> None:
    table = Table(title=f"{summary['name']} ({summary['strategy']}): since {summary['start']:%Y-%m-%d %H:%M}, last look {summary['last_poll']:%Y-%m-%d %H:%M}")
    for column in ("Value", "Return", "OSEBX", "Cash", "Round trips", "Profitable", "Costs paid"):
        table.add_column(column, justify="right")
    table.add_row(
        f"{summary['value']:,.0f}", _pct(summary["total_return"]), _pct(summary["benchmark_return"]), f"{summary['cash']:,.0f}",
        f"{summary['round_trips']}", _pct(summary["win_rate"]).lstrip("+"), f"{summary['costs_paid']:,.0f}",
    )  # fmt: skip
    console.print(table)
    as_of = f" (from the close of {summary['watchlist_as_of']:%Y-%m-%d})" if summary["watchlist_as_of"] is not None else ""
    console.print(f"  Watchlist{as_of}: {', '.join(summary['watchlist']) or 'empty'}")
    coverage = summary["coverage"]
    if coverage["due"]:
        missed = f", {len(coverage['days_missed'])} whole days missed" if coverage["days_missed"] else ""
        console.print(f"  Looks made: {coverage['today_made']} of {coverage['today_due']} today, {coverage['share']:.0%} of all since the start{missed}")
    for h in summary["holdings"]:
        console.print(f"  Holds {h['shares']:,.0f} {h['code']} bought at {h['average_price']:.2f}, now {h['last_price']:.2f} ({_pct(h['profit_rate'])})")
    for o in summary["pending"]:
        console.print(f"  Ordered: {o['side']} {o['code']} ({o['signal']}: {o['reason']})")
    log = summary["signals"].tail(signals)
    if not log.empty:
        recent = Table(title=f"Latest {len(log)} signals")
        for column in ("Bar", "Signal", "Stock", "Price", "Why", "What was done"):
            recent.add_column(column, justify="right" if column == "Price" else "left")
        for r in log.itertuples():
            recent.add_row(f"{r.timestamp:%m-%d %H:%M}", r.code, r.stock, f"{r.price:.2f}", r.reason, r.outcome)
        console.print(recent)


@intraday_app.command("rules")
def intraday_rules() -> None:
    """The signal rules there are, with their settings."""
    import inspect

    from osloquant.intraday import RULES

    table = Table(title="Signal rules: use the code as `rule:` in intraday.yaml, or with `oq intraday replay --rule`")
    for column in ("Code", "Settings (default)", "What it does"):
        table.add_column(column)
    for code, rule in RULES.items():
        settings = ", ".join(f"{name}={p.default}" for name, p in inspect.signature(rule.__init__).parameters.items() if name != "self")
        table.add_row(code, settings, " ".join((rule.__doc__ or "").split()))
    console.print(table)
    console.print("Risk settings for any account: stop_loss, take_profit, trailing_stop (fractions), flat_at_close (true/false), cooldown_bars.")
    console.print(
        "Day trading: day_trade (true), exit_on_signal, entry_window, max_entries_per_stock_per_day, max_entries_per_day, "
        "min_relative_volume, min_range_to_cost, max_per_sector. See the comments at the top of intraday.yaml."
    )


def _parse_setting(text: str) -> tuple[str, float | int]:
    name, _, value = text.partition("=")
    if not value:
        raise typer.BadParameter(f"--param takes name=value, not {text!r}")
    number = float(value)
    return name.strip(), int(number) if number.is_integer() else number


@intraday_app.command("replay")
def intraday_replay(
    days: int = typer.Option(30, help="How many calendar days back to replay (Yahoo keeps about 58 days of 15-minute bars)."),
    account: str = typer.Option(None, help="Only this account from intraday.yaml; all of them when omitted."),
    rule: str = typer.Option(None, help="Try this rule instead of the configured accounts, e.g. ma_cross. See `oq intraday rules`."),
    param: list[str] = typer.Option(None, help="A setting of --rule as name=value; repeat for several, e.g. --param fast=10 --param slow=40."),
    watchlist: str = typer.Option("MomentumFactor", help="With --rule: a daily factor, 'all', or codes separated by commas."),
    stop_loss: float = typer.Option(None, help="With --rule: e.g. 0.03."),
    take_profit: float = typer.Option(None, help="With --rule: e.g. 0.06."),
    trailing_stop: float = typer.Option(None, help="With --rule: e.g. 0.04."),
    cooldown: int = typer.Option(0, help="With --rule: bars to stay out of a stock after selling it."),
    positions: int = typer.Option(5, help="With --rule: the number of slots."),
    day_trade: bool = typer.Option(False, "--day-trade", help="With --rule: flat at the close, exits by the stops, entries 09:30-14:30, one a stock a day."),
    max_per_sector: int = typer.Option(None, help="With --rule: at most this many positions in one sector."),
    min_relative_volume: float = typer.Option(None, help="With --rule: the signal bar must trade this many times the usual volume."),
    min_range_cost: float = typer.Option(None, help="With --rule: the stock's daily range must be at least this many round-trip costs."),
    record: bool = typer.Option(True, help="Fetch the 15-minute history for every stock first."),
) -> None:
    """Run rules over the stored bars of the last weeks, with the delays of a live run. Stores nothing.

    Each account is played twice: with the real costs, and with free trading. The second number is the rule
    itself. If that is not clearly positive, no change to the costs or the stops will rescue it.

    This is a backtest with all of a backtest's weaknesses: a few weeks, one market, and every setting you try
    is one more chance to fit the past. Use it to see what a rule does, not what it will earn.
    """
    _setup()
    from dataclasses import replace

    from osloquant.domain import Index1dKdata, Stock15mKdata
    from osloquant.intraday import IntradayAccountConfig, replay
    from osloquant.intraday.engine import load_bars, market_now

    config = _intraday_config()
    if rule:
        spec = {"rule": rule, **dict(_parse_setting(p) for p in param or [])}
        codes = watchlist if "," not in watchlist and not watchlist.isupper() else [c.strip() for c in watchlist.split(",")]
        chosen = [
            IntradayAccountConfig(name="trial", signal=spec, watchlist=codes, stop_loss=stop_loss, take_profit=take_profit,
                                  trailing_stop=trailing_stop, cooldown_bars=cooldown, max_positions=positions, day_trade=day_trade,
                                  max_per_sector=max_per_sector, min_relative_volume=min_relative_volume, min_range_to_cost=min_range_cost)
        ]  # fmt: skip
    else:
        chosen = [a for a in config.accounts if account in (None, a.name)]
        if not chosen:
            raise typer.BadParameter(f"no account named {account!r} in {config.path}")
    if record:
        with console.status("Fetching 15-minute bars for every stock ..."):
            summary = Stock15mKdata.record_data()
        console.print(f"[green]ok[/green] {summary}" if not summary.failed else f"[yellow]partly[/yellow] {summary}")
    end = market_now()
    bars = load_bars(None, since=end.normalize() - pd.Timedelta(days=days + 12), until=end)
    if not bars:
        console.print("No 15-minute bars are stored.")
        raise typer.Exit(1)
    free = replace(config, commission_rate=0.0, commission_min=0.0, slippage=0.0)

    table = Table(title=f"Replay of the last {days} days. Play money, nothing stored.")
    for column in ("Account", "Rule", "Days", "Return", "Without the best trade", "With free trading", "OSEBX", "Round trips", "Profitable",
                   "Per round trip before costs", "Costs paid"):  # fmt: skip
        table.add_column(column, justify="left" if column in ("Account", "Rule") else "right")
    exits = Table(title="How the positions were closed")
    for column in ("Account", "Closed by", "Times", "Profitable", "Average result"):
        exits.add_column(column, justify="left" if column in ("Account", "Closed by") else "right")

    for cfg in chosen:
        with console.status(f"Replaying {cfg.name} ..."):
            result = replay(cfg, config, days=days, bars=bars, end=end)
            gross = replay(cfg, free, days=days, bars=bars, end=end)
        trades = result.orders[result.orders["order_type"].isin(["order_long", "order_close_long"])] if not result.orders.empty else result.orders
        sells = trades[trades["order_type"] == "order_close_long"] if not trades.empty else trades
        index = Index1dKdata.query_data(code="OSEBX", start_timestamp=result.start, end_timestamp=result.end, columns=["timestamp", "close"]) if result.start is not None else pd.DataFrame()
        benchmark = index["close"].iloc[-1] / index["close"].iloc[0] - 1 if len(index) > 1 else None
        style = " (day trade)" if cfg.flat_at_close and not cfg.exit_on_signal else ""
        # a result that rests on one trade is luck until shown otherwise
        best = sells["profit"].max() if len(sells) else 0.0
        without_best = (result.value - result.input_money - max(best, 0.0)) / result.input_money
        # what one round trip earned before any cost: the most a rule could pay per round trip and still break even
        gross_sells = gross.orders[gross.orders["order_type"] == "order_close_long"] if not gross.orders.empty else gross.orders
        table.add_row(
            result.name, result.rule + style, f"{result.days}", _pct(result.total_return), _pct(without_best), _pct(gross.total_return), _pct(benchmark),
            f"{len(sells)}", _pct((sells["profit"] > 0).mean() if len(sells) else None).lstrip("+"),
            _pct(gross_sells["profit_rate"].mean() if len(gross_sells) else None, 2), f"{trades['cost'].sum() if not trades.empty else 0:,.0f}",
        )  # fmt: skip
        if len(sells):
            by_exit = sells.assign(closed_by=sells["reason"].str.split().str[0]).groupby("closed_by")
            for closed_by, group in sorted(by_exit, key=lambda g: -len(g[1])):
                exits.add_row(result.name, closed_by, f"{len(group)}", _pct((group["profit"] > 0).mean()).lstrip("+"), _pct(group["profit_rate"].mean()))
    console.print(table)
    if exits.row_count:
        console.print(exits)
    console.print(
        "[dim]\"With free trading\" is the rule without commission and slippage. \"Per round trip before costs\" is what a round trip "
        "earned on average before costs: the rule loses money whenever a round trip costs more than that (about 0.5 % with Nordnet Mini). "
        "A few weeks of one market say little, and every variant you try is one more chance to fit the past.[/dim]"
    )


@app.command()
def ui(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8050),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Start the dashboard at http://127.0.0.1:8050"""
    from osloquant.ui.app import main

    console.print(f"Dashboard at http://{host}:{port}  (Ctrl+C to stop)")
    main(host=host, port=port, debug=debug)


if __name__ == "__main__":
    app()
