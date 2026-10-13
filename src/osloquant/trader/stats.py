"""How a finished run did, measured from what it stored."""

from __future__ import annotations

import numpy as np
import pandas as pd

from osloquant.contract.api import decode_entity_id, get_data, get_kdata
from osloquant.trader.schemas import AccountStats, Order, TraderInfo
from osloquant.trader.sim_account import CLOSES, PROVIDER, TRADES

TRADING_DAYS = 252


def performance(values: pd.Series, start_value: float | None = None, risk_free: float = 0.0) -> dict:
    """Return and risk of a daily value series indexed by date.

    :param start_value: what the series was worth before its first day; its first value when omitted
    :param risk_free: annual rate subtracted in the Sharpe ratio
    """
    values = values.dropna()
    if values.empty:
        return {}
    start_value = float(values.iloc[0]) if start_value is None else float(start_value)
    returns = values.pct_change()
    returns.iloc[0] = values.iloc[0] / start_value - 1
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1 / TRADING_DAYS)
    total_return = values.iloc[-1] / start_value - 1
    volatility = returns.std(ddof=1) * np.sqrt(TRADING_DAYS) if len(returns) > 1 else np.nan
    cagr = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0
    excess = returns.mean() * TRADING_DAYS - risk_free
    peak = pd.concat([pd.Series([start_value]), values]).cummax().iloc[1:]
    peak.index = values.index
    drawdown = values / peak - 1
    return {
        "start": values.index[0],
        "end": values.index[-1],
        "days": int(len(values)),
        "total_return": float(total_return),
        "cagr": float(cagr),
        "volatility": float(volatility),
        "sharpe": float(excess / volatility) if volatility and volatility > 0 else np.nan,
        "max_drawdown": float(drawdown.min()),
        "max_drawdown_date": drawdown.idxmin(),
        "best_day": float(returns.max()),
        "worst_day": float(returns.min()),
    }


def get_trader_info(trader_name: str) -> dict | None:
    rows = get_data(TraderInfo, provider=PROVIDER, filters=[TraderInfo.trader_name == trader_name], return_type="dict")
    return rows[0] if rows else None


def get_trader_names(mode: str | None = "backtest") -> list[str]:
    """The stored traders. Backtests by default; "live" for the live accounts, None for both."""
    df = get_data(TraderInfo, provider=PROVIDER, columns=["trader_name", "mode"], order=TraderInfo.trader_name.asc())
    if mode is not None:
        is_live = df["mode"] == "live"
        df = df[is_live] if mode == "live" else df[~is_live]
    return df["trader_name"].tolist()


def get_account_df(trader_name: str) -> pd.DataFrame:
    """The account at each close, indexed by date."""
    return get_data(
        AccountStats, provider=PROVIDER, filters=[AccountStats.trader_name == trader_name], index="timestamp"
    )


def get_orders_df(trader_name: str) -> pd.DataFrame:
    return get_data(Order, provider=PROVIDER, filters=[Order.trader_name == trader_name])


def get_benchmark_series(trader_name: str, index: pd.DatetimeIndex) -> pd.Series | None:
    """The benchmark's close on the account's dates, or None when there is no benchmark data."""
    info = get_trader_info(trader_name)
    if not info or not info.get("benchmark"):
        return None
    try:
        decode_entity_id(info["benchmark"])
        df = get_kdata(
            entity_id=info["benchmark"],
            columns=["timestamp", "close"],
            start_timestamp=index[0] - pd.Timedelta(days=10),
        )
    except (KeyError, ValueError, LookupError):
        return None
    if df.empty:
        return None
    series = df.set_index("timestamp")["close"]
    # the last known close on each account date, but nothing before the benchmark's own first bar
    return series.reindex(series.index.union(index)).ffill().reindex(index).dropna().rename(info["benchmark"])


def get_trader_stats(trader_name: str, risk_free: float = 0.0) -> dict:
    """Performance, trading activity, and two comparisons: the benchmark index and the trader's own universe.

    The benchmark comparison covers only the days both series exist; ``benchmark_from`` says where it starts.
    The universe comparison is the equal-weighted return of everything the trader could choose from.
    """
    account = get_account_df(trader_name)
    if account.empty:
        raise LookupError(f"no stored run for trader {trader_name!r}")
    values = account["all_value"]
    input_money = float(account["input_money"].iloc[0])
    stats = {"trader_name": trader_name, **performance(values, start_value=input_money, risk_free=risk_free)}
    stats["final_value"] = float(values.iloc[-1])
    stats["exposure"] = float((account["value"] / account["all_value"]).mean())

    every_entry = get_orders_df(trader_name)
    orders = every_entry[every_entry["order_type"].isin(TRADES)] if not every_entry.empty else every_entry
    dividends = every_entry[every_entry["order_type"] == "dividend"] if not every_entry.empty else every_entry
    stats["dividends_received"] = float(dividends["profit"].sum()) if not dividends.empty else 0.0
    sells = orders[orders["order_type"].isin(CLOSES)] if not orders.empty else orders
    stats["orders"] = int(len(orders))
    stats["round_trips"] = int(len(sells))
    stats["win_rate"] = float((sells["profit"] > 0).mean()) if len(sells) else np.nan
    stats["average_round_trip"] = float(sells["profit_rate"].mean()) if len(sells) else np.nan
    stats["costs_paid"] = float(orders["cost"].sum()) if not orders.empty else 0.0
    traded_value = float((orders["order_price"] * orders["order_amount"]).sum()) if not orders.empty else 0.0
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1 / TRADING_DAYS)
    # one-way turnover per year: half of everything bought and sold, over the average account value
    stats["turnover"] = traded_value / 2 / float(values.mean()) / years

    universe = account["universe_value"].dropna() if "universe_value" in account.columns else pd.Series(dtype=float)
    if len(universe) > 1:
        whole = performance(universe, start_value=input_money, risk_free=risk_free)
        stats.update(
            {
                "universe_total_return": whole["total_return"],
                "universe_cagr": whole["cagr"],
                "universe_volatility": whole["volatility"],
                "universe_max_drawdown": whole["max_drawdown"],
                "excess_cagr_over_universe": stats["cagr"] - whole["cagr"],
            }
        )

    benchmark = get_benchmark_series(trader_name, values.index)
    if benchmark is not None and len(benchmark) > 1:
        same_days = values.reindex(benchmark.index)
        bench = performance(benchmark)
        own = performance(same_days)
        daily = pd.concat([same_days.pct_change(), benchmark.pct_change()], axis=1, keys=["own", "bench"]).dropna()
        beta = (
            daily["own"].cov(daily["bench"]) / daily["bench"].var()
            if len(daily) > 2 and daily["bench"].var() > 0
            else np.nan
        )
        stats.update(
            {
                "benchmark": benchmark.name,
                "benchmark_from": benchmark.index[0],
                "benchmark_total_return": bench["total_return"],
                "benchmark_cagr": bench["cagr"],
                "benchmark_volatility": bench["volatility"],
                "benchmark_max_drawdown": bench["max_drawdown"],
                "same_days_total_return": own["total_return"],
                "same_days_cagr": own["cagr"],
                "excess_cagr": own["cagr"] - bench["cagr"],
                "beta": float(beta),
            }
        )
    return stats
