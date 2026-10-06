"""A strategy lab: documented strategies, one cost model, and the tests that tell an edge from luck.

The strategies are fixed in advance and their settings are the published ones, not tuned to Oslo:

==================  =======================================================================  =========================
equal_weight        every eligible stock, equal weights, rebalanced monthly: the hurdle      the survivor basket
momentum            the fifth with the best return from 12 months to 1 month ago             Jegadeesh & Titman (1993)
dual_momentum       the same fifth, but only those whose 12-1 return is positive; cash else   Antonacci (2014)
momentum_trend      the best fifth on 12-1 among the stocks above their 200-day average      the live momentum account
trend               every stock above its 200-day average                                     Faber (2007), per stock
low_volatility      the fifth with the lowest volatility over the last year                  Blitz & van Vliet (2007)
reversal            the fifth with the worst return over the last month                       Jegadeesh (1990)
market_timing       the equal-weight basket while it is above its 10-month average; cash else Faber (2007)
turn_of_month       the basket from the second-to-last to the third trading day of a month    Lakonishok & Smidt (1988)
momentum_buffer     momentum_trend, but a holding is kept until it leaves the best two fifths Novy-Marx & Velikov (2016)
momentum_managed    momentum, scaled down when its own volatility runs above the market's   Barroso & Santa-Clara (2015)
==================  =======================================================================  =========================

Every strategy decides on the close of the last trading day of a month and trades at the close of the next
trading day, so that nothing it trades on was unknown when it decided. Within a month the holdings drift with
their prices. Cash earns nothing.

Costs are those of a real account (``Costs``): a commission with a minimum per order, slippage, and an account
of a given size. With NOK 100 000 split over thirty stocks, the NOK 29 minimum is a full percent of each order,
so how many positions a strategy holds matters as much as how often it trades. Holdings within a quarter of their
target weight are left alone rather than topped up, as an investor paying a minimum fee per order would.

A stock is eligible once it has a year of prices (so that every signal can be computed) and has traded in
the last week. The stock list is today's survivors, which flatters every strategy and the hurdle alike: what
is measured is the excess over the equal-weight basket of the same stocks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from osloquant.research.validation import backtest_overfitting, bootstrap_mean, deflated_sharpe, effective_trials

DAYS, MONTH = 252, 21


@dataclass(frozen=True)
class Strategy:
    name: str
    source: str
    description: str


STRATEGIES = [
    Strategy("equal_weight", "the hurdle", "every eligible stock, equal weights"),
    Strategy("momentum", "Jegadeesh & Titman 1993", "best fifth on the 12-1 month return"),
    Strategy("dual_momentum", "Antonacci 2014", "best fifth on 12-1, only if that return is positive"),
    Strategy("momentum_trend", "the live momentum account", "best fifth on 12-1 among stocks above their 200-day average"),
    Strategy("trend", "Faber 2007", "every stock above its 200-day average"),
    Strategy("low_volatility", "Blitz & van Vliet 2007", "the fifth with the lowest one-year volatility"),
    Strategy("reversal", "Jegadeesh 1990", "the fifth with the worst last month"),
    Strategy("market_timing", "Faber 2007", "the basket while it is above its 10-month average"),
    Strategy("turn_of_month", "Lakonishok & Smidt 1988", "the basket from day -2 to day +3 of each month"),
    Strategy("momentum_buffer", "Novy-Marx & Velikov 2016", "momentum_trend, kept until out of the best two fifths"),
    Strategy("momentum_managed", "Barroso & Santa-Clara 2015", "momentum, scaled down when its volatility exceeds the market's"),
]


# -- the panel ------------------------------------------------------------------------------------


@dataclass
class Panel:
    """Adjusted daily closes on trading days, wide (dates x stocks), and what the signals are made from."""

    close: pd.DataFrame
    prices: pd.DataFrame
    eligible: pd.DataFrame
    ma200: pd.DataFrame
    volatility: pd.DataFrame

    @classmethod
    def from_closes(cls, close: pd.DataFrame) -> Panel:
        close = close.sort_index()
        # a day counts when a fair share of the usual number of stocks traded (keeps out stray holiday bars)
        traded = close.notna().sum(axis=1)
        close = close[traded >= (0.2 * traded.rolling(20, min_periods=1).median()).clip(lower=1)]
        prices = close.ffill()
        history = close.notna().rolling(DAYS + MONTH, min_periods=1).sum() >= DAYS
        recent = close.notna().rolling(5, min_periods=1).sum() > 0
        returns = np.log(prices / prices.shift(1))
        return cls(
            close=close,
            prices=prices,
            eligible=history & recent,
            ma200=prices.rolling(200, min_periods=200).mean(),
            volatility=returns.rolling(DAYS, min_periods=DAYS // 2).std(),
        )

    @classmethod
    def load(cls) -> Panel:
        from osloquant.domain import Stock1dAdjKdata

        df = Stock1dAdjKdata.query_data(columns=["entity_id", "timestamp", "close"])
        if df.empty:
            raise LookupError("no adjusted bars are stored; record them first: oq record")
        return cls.from_closes(df.pivot(index="timestamp", columns="entity_id", values="close"))

    def momentum(self, lookback: int = 12, skip: int = 1) -> pd.DataFrame:
        return self.prices.shift(MONTH * skip) / self.prices.shift(MONTH * lookback) - 1

    def month_ends(self, start: pd.Timestamp | None = None) -> list[int]:
        """Positions of the last trading day of each month (that has a next trading day to trade on)."""
        days = self.close.index
        ends = [i for i in range(len(days) - 1) if (days[i].year, days[i].month) != (days[i + 1].year, days[i + 1].month)]
        return [i for i in ends if start is None or days[i] >= start]


# -- the simulator --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Costs:
    """What trading costs: commission (a share of the order, with a minimum), slippage, and the account paying it."""

    #: commission as a share of the value of an order
    rate: float = 0.0015
    #: the smallest commission an order pays, in NOK
    min_fee: float = 29.0
    #: lost to the spread and the market moving, as a share of the value of an order
    slippage: float = 0.001
    #: the account's value at the start, in NOK
    capital: float = 100_000.0
    #: a holding is left alone while its weight is within this share of its target (0.25: 75 % to 125 % of it)
    buffer: float = 0.25

    @classmethod
    def flat(cls, cost: float) -> Costs:
        """A plain cost per unit traded: no minimum, no buffer."""
        return cls(rate=cost, min_fee=0.0, slippage=0.0, capital=1.0, buffer=0.0)

    def describe(self) -> str:
        if self.min_fee == 0 and self.slippage == 0:
            return f"{100 * self.rate:.2f} % a trade"
        return (
            f"NOK {self.capital:,.0f}, {100 * self.rate:.2f} % commission (at least NOK {self.min_fee:,.0f}) and "
            f"{100 * self.slippage:.2f} % slippage an order, holdings left alone within {self.buffer:.0%} of target"
        )


def simulate(prices: pd.DataFrame, schedule: list[tuple[int, dict[str, float]]], cost: float | Costs) -> pd.Series:
    """Daily returns of a portfolio that trades to the given weights at the close of each scheduled day.

    ``schedule`` is a list of (day position, {stock: weight}); weights may add up to less than one, the rest is
    cash. Between trades the holdings drift with their prices. ``cost`` is a ``Costs``, or a plain share of the
    value traded. The returns start on the day of the first trade, whose return is the cost of making it.

    The result's ``attrs`` hold what the trading took: ``traded`` (value traded, as a share of the portfolio,
    summed over all trades), ``fees`` (the same for the costs) and ``orders``.
    """
    costs = cost if isinstance(cost, Costs) else Costs.flat(cost)
    values = prices.to_numpy(dtype=float)
    column = {c: k for k, c in enumerate(prices.columns)}
    out = np.zeros(len(prices))
    schedule = sorted(schedule, key=lambda item: item[0])
    held: dict[str, float] = {}
    wealth = costs.capital
    traded_total = fees_total = 0.0
    orders = 0
    for n, (day, target) in enumerate(schedule):
        weights, bought = {}, set()
        for stock in set(target) | set(held):
            want, have = target.get(stock, 0.0), held.get(stock, 0.0)
            if want > 0 and have > 0 and abs(have - want) <= costs.buffer * want:
                weights[stock] = have  # close enough to its target: no order
            elif want > 0:
                weights[stock] = want
                bought.add(stock)
        # holdings left alone may leave too little cash for the new targets: scale the orders down to fit
        kept = sum(w for stock, w in weights.items() if stock not in bought)
        buying = sum(weights[stock] for stock in bought)
        if buying > 0 and kept + buying > 1 + 1e-12:
            for stock in bought:
                weights[stock] *= max(1.0 - kept, 0.0) / buying
        fee = 0.0
        for stock in set(weights) | set(held):
            change = abs(weights.get(stock, 0.0) - held.get(stock, 0.0))
            if change > 1e-12:
                value = change * wealth
                fee += max(costs.min_fee, costs.rate * value) + costs.slippage * value
                traded_total += change
                orders += 1
        fee_share = min(fee / wealth, 1.0) if wealth > 0 else 0.0
        fees_total += fee_share
        out[day] = (1 + out[day]) * (1 - fee_share) - 1
        wealth *= 1 - fee_share
        end = schedule[n + 1][0] if n + 1 < len(schedule) else len(prices) - 1
        if end <= day:
            held = {stock: w for stock, w in weights.items() if w}
            continue
        stocks = [stock for stock, w in weights.items() if w]
        w = np.array([weights[stock] for stock in stocks])
        cash = 1.0 - w.sum()
        if stocks:
            path = values[day : end + 1, [column[stock] for stock in stocks]] / values[day, [column[stock] for stock in stocks]]
            value = cash + path @ w
        else:
            path, value = np.ones((end - day + 1, 0)), np.full(end - day + 1, cash)
        out[day + 1 : end + 1] = value[1:] / value[:-1] - 1
        wealth *= value[-1] / value[0]
        held = {stock: float(w[k] * path[-1, k] / value[-1]) for k, stock in enumerate(stocks)} if value[-1] > 0 else {}
    returns = pd.Series(out, index=prices.index)
    returns = returns.iloc[schedule[0][0] :] if schedule else returns.iloc[0:0]
    returns.attrs = {"traded": traded_total, "fees": fees_total, "orders": orders}
    return returns


# -- the strategies -------------------------------------------------------------------------------


def _top(scores: pd.Series, fraction: float, largest: bool = True) -> list[str]:
    scores = scores.dropna()
    if scores.empty:
        return []
    count = max(1, int(np.ceil(fraction * len(scores))))
    ordered = scores.sort_values(ascending=not largest, kind="stable")
    return ordered.index[:count].tolist()


def _equal(stocks: list[str], slots: int | None = None) -> dict[str, float]:
    if not stocks:
        return {}
    weight = 1.0 / (slots or len(stocks))
    return dict.fromkeys(stocks, weight)


def monthly_schedule(panel: Panel, choose: Callable[[int, pd.Index], dict[str, float]], start: pd.Timestamp | None = None) -> list[tuple[int, dict[str, float]]]:
    """Decide at each month end (day i) on the eligible stocks, trade at the close of day i + 1."""
    schedule = []
    for i in panel.month_ends(start):
        eligible = panel.eligible.columns[panel.eligible.iloc[i].to_numpy()]
        schedule.append((i + 1, choose(i, eligible)))
    return schedule


def momentum_weights(panel: Panel, lookback: int = 12, skip: int = 1, fraction: float = 0.2, start=None) -> list:
    signal = panel.momentum(lookback, skip)
    return monthly_schedule(panel, lambda i, eligible: _equal(_top(signal.iloc[i][eligible], fraction)), start)


def build_schedules(panel: Panel, start: pd.Timestamp) -> dict[str, list]:
    """The schedule of every strategy in ``STRATEGIES``."""
    mom = panel.momentum(12, 1)
    above = panel.prices > panel.ma200
    rev = panel.prices / panel.prices.shift(MONTH) - 1

    def dual(i, eligible):
        best = _top(mom.iloc[i][eligible], 0.2)
        slots = len(best)
        return _equal([s for s in best if mom.iat[i, panel.prices.columns.get_loc(s)] > 0], slots)

    def momentum_trend(i, eligible):
        rising = [s for s in eligible if above.iat[i, panel.prices.columns.get_loc(s)]]
        return _equal(_top(mom.iloc[i][rising], 0.2)) if rising else {}

    schedules = {
        "equal_weight": monthly_schedule(panel, lambda i, e: _equal(list(e)), start),
        "momentum": momentum_weights(panel, start=start),
        "dual_momentum": monthly_schedule(panel, dual, start),
        "momentum_trend": monthly_schedule(panel, momentum_trend, start),
        "trend": monthly_schedule(panel, lambda i, e: _equal([s for s in e if above.iat[i, panel.prices.columns.get_loc(s)]]), start),
        "low_volatility": monthly_schedule(panel, lambda i, e: _equal(_top(panel.volatility.iloc[i][e], 0.2, largest=False)), start),
        "reversal": monthly_schedule(panel, lambda i, e: _equal(_top(rev.iloc[i][e], 0.2, largest=False)), start),
    }

    # market timing on the basket's own level: no index data needed, and the same stocks as the hurdle
    basket = (1 + simulate(panel.prices, schedules["equal_weight"], 0.0)).cumprod()
    basket_ma = basket.rolling(10 * MONTH, min_periods=10 * MONTH).mean()

    def timed(i, eligible):
        day = panel.prices.index[i]
        if day not in basket.index or pd.isna(basket_ma.get(day)) or basket[day] <= basket_ma[day]:
            return {}
        return _equal(list(eligible))

    schedules["market_timing"] = monthly_schedule(panel, timed, start)

    turn = []
    for i in panel.month_ends(start):
        if i - 1 < 0 or i + 3 >= len(panel.prices):
            continue
        eligible = list(panel.eligible.columns[panel.eligible.iloc[i - 1].to_numpy()])
        turn += [(i - 1, _equal(eligible)), (i + 3, {})]
    schedules["turn_of_month"] = turn

    # buy in the best fifth, hold until out of the best two fifths: fewer trades for nearly the same exposure
    buffered, holdings = [], []
    for i in panel.month_ends(start):
        eligible = panel.eligible.columns[panel.eligible.iloc[i].to_numpy()]
        rising = [s for s in eligible if above.iat[i, panel.prices.columns.get_loc(s)]]
        scores = mom.iloc[i][rising].dropna()
        if scores.empty:
            holdings = []
            buffered.append((i + 1, {}))
            continue
        rank = scores.rank(pct=True)
        slots = max(1, int(np.ceil(0.2 * len(scores))))
        keep = sorted((s for s in holdings if s in rank.index and rank[s] > 0.6), key=lambda s: -rank[s])[:slots]
        new = [s for s in rank.sort_values(ascending=False, kind="stable").index if rank[s] > 0.8 and s not in keep]
        holdings = keep + new[: slots - len(keep)]
        buffered.append((i + 1, _equal(holdings)))
    schedules["momentum_buffer"] = buffered

    # momentum, scaled down to the market's volatility when its own runs higher (no leverage: never above one)
    plain = simulate(panel.prices, schedules["momentum"], 0.0)
    market = simulate(panel.prices, schedules["equal_weight"], 0.0)
    managed = []
    for day, weights in schedules["momentum"]:
        decided = panel.prices.index[day - 1]
        own, base = plain[:decided].iloc[-126:], market[:decided]
        scale = 1.0
        if len(own) >= 63 and len(base) >= DAYS and own.std() > 0:
            scale = min(1.0, float(base.std() / own.std()))
        managed.append((day, {stock: weight * scale for stock, weight in weights.items()}))
    schedules["momentum_managed"] = managed
    return schedules


# -- measuring ------------------------------------------------------------------------------------


def annual(returns: pd.Series) -> float:
    returns = returns.dropna()
    if returns.empty:
        return float("nan")
    years = len(returns) / DAYS
    return float((1 + returns).prod() ** (1 / years) - 1)


def max_drawdown(returns: pd.Series) -> float:
    wealth = (1 + returns.fillna(0)).cumprod()
    return float((wealth / wealth.cummax() - 1).min())


def turnover_per_year(schedule: list[tuple[int, dict[str, float]]], prices: pd.DataFrame, cost: float | Costs = 0.0) -> float:
    """One-way turnover a year: half of everything bought and sold, over the portfolio's value."""
    returns = simulate(prices, schedule, cost)
    years = len(returns) / DAYS
    return float(returns.attrs["traded"] / 2 / years) if years > 0 else float("nan")


def monthly(returns: pd.Series) -> pd.Series:
    return (1 + returns).groupby([returns.index.year, returns.index.month]).prod() - 1


@dataclass
class LabResult:
    table: pd.DataFrame
    daily: dict[str, pd.Series]
    overfitting: dict
    start: pd.Timestamp
    end: pd.Timestamp
    cost: Costs
    stocks: int
    #: re-tuning the momentum settings every January on the years before, against keeping the textbook ones
    walk_forward: dict | None = None


PERIODS = (("2001-2008", "2001-01-01", "2008-12-31"), ("2009-2016", "2009-01-01", "2016-12-31"), ("2017-", "2017-01-01", "2100-01-01"))


def momentum_grid(panel: Panel, start: pd.Timestamp, cost: float | Costs) -> dict[str, pd.Series]:
    """The momentum family over its usual settings: the trials the overfitting test chooses among."""
    grid = {}
    for lookback in (3, 6, 9, 12):
        for skip in (0, 1):
            for fraction in (0.1, 0.2, 0.3):
                name = f"momentum {lookback}-{skip} top {fraction:.0%}"
                grid[name] = simulate(panel.prices, momentum_weights(panel, lookback, skip, fraction, start=start), cost)
    return grid


def walk_forward(grid: dict[str, pd.Series], hurdle: pd.Series, fixed: str, warmup_years: int = 5) -> dict:
    """Each January, pick the setting with the best excess over the years before and hold it for the year.

    Switching from one setting's portfolio to another is not charged, which flatters the re-tuning.
    """
    years = sorted(set(hurdle.index.year))
    pieces, picks = [], {}
    for year in years[warmup_years:]:
        before = hurdle.index.year < year
        past = {name: annual(series[series.index.year < year]) - annual(hurdle[before]) for name, series in grid.items()}
        pick = max(past, key=past.get)
        picks[year] = pick
        pieces.append(grid[pick][grid[pick].index.year == year])
    tuned = pd.concat(pieces)
    base = hurdle[hurdle.index.isin(tuned.index)]
    textbook = grid[fixed][grid[fixed].index.isin(tuned.index)]
    return {
        "from": tuned.index[0],
        "tuned_excess": annual(tuned) - annual(base),
        "textbook_excess": annual(textbook) - annual(base),
        "picks": picks,
        "switches": sum(1 for a, b in zip(list(picks.values()), list(picks.values())[1:], strict=False) if a != b),
    }


def run_lab(
    panel: Panel | None = None, start: str = "2001-01-01", cost: float | Costs | None = None, blocks: int = 16, bootstrap_samples: int = 2000
) -> LabResult:
    """Every strategy, its excess over the equal-weight basket, and the tests.

    ``cost`` is a ``Costs`` (by default a NOK 100 000 account at Nordnet Mini) or a plain share of the value traded.
    """
    panel = Panel.load() if panel is None else panel
    start = pd.Timestamp(start)
    cost = Costs() if cost is None else cost
    schedules = build_schedules(panel, start)
    daily = {name: simulate(panel.prices, schedule, cost) for name, schedule in schedules.items()}
    gross = {name: simulate(panel.prices, schedule, 0.0) for name, schedule in schedules.items()}
    first = max(series.index[0] for series in daily.values())
    daily = {name: series[series.index >= first] for name, series in daily.items()}
    gross = {name: series[series.index >= first] for name, series in gross.items()}
    hurdle = daily["equal_weight"]

    grid = momentum_grid(panel, start, cost)
    grid = {name: series[series.index >= first] for name, series in grid.items()}
    hurdle_months = monthly(hurdle)
    excess_months = {name: monthly(series) - hurdle_months for name, series in {**daily, **grid}.items() if name != "equal_weight"}
    # every variant tried here is a trial; correlated ones count for less
    trials = effective_trials(pd.DataFrame(excess_months).to_numpy())

    rows = []
    for strategy in STRATEGIES:
        series = daily[strategy.name]
        row = {
            "strategy": strategy.name,
            "source": strategy.source,
            "per_year": annual(series),
            "before_costs": annual(gross[strategy.name]),
            "max_drawdown": max_drawdown(series),
            "turnover": turnover_per_year(schedules[strategy.name], panel.prices, cost),
            "positions": float(np.mean([sum(1 for w in weights.values() if w) for _, weights in schedules[strategy.name] if weights] or [0])),
        }
        if strategy.name != "equal_weight":
            excess = excess_months[strategy.name]
            row["excess"] = row["per_year"] - annual(hurdle)
            interval = bootstrap_mean(excess.to_numpy(), block=3, samples=bootstrap_samples)
            row["excess_low"], row["excess_high"] = 12 * interval["low"], 12 * interval["high"]
            years = excess.groupby(level=0).apply(lambda m: (1 + m).prod() - 1)
            row["years_ahead"] = float((years > 0).mean())
            row["dsr"] = deflated_sharpe(excess.to_numpy(), trials)["dsr"]
            for label, since, until in PERIODS:
                own, base = series[since:until], hurdle[since:until]
                row[label] = annual(own) - annual(base) if len(own) > DAYS // 2 else float("nan")
        rows.append(row)

    matrix = pd.DataFrame({name: excess_months[name] for name in grid}).dropna()
    pbo = backtest_overfitting(matrix.to_numpy(), blocks=blocks)
    best_in_full = matrix.mean().idxmax()
    overfitting = {
        "pbo": pbo.pbo,
        "splits": pbo.splits,
        "degradation": pbo.degradation,
        "probability_of_loss": pbo.probability_of_loss,
        "configurations": matrix.shape[1],
        "best_in_full_sample": best_in_full,
        "best_excess": annual(grid[best_in_full]) - annual(hurdle),
        "trials": len(excess_months),
        "effective_trials": trials,
    }
    stocks = int(panel.eligible[panel.eligible.index >= first].iloc[-1].sum())
    costs = cost if isinstance(cost, Costs) else Costs.flat(cost)
    tuning = walk_forward(grid, hurdle, fixed="momentum 12-1 top 20%") if len(set(hurdle.index.year)) > 6 else None
    return LabResult(pd.DataFrame(rows).set_index("strategy"), daily, overfitting, first, hurdle.index[-1], costs, stocks, tuning)


COST_SETTINGS = {
    "flat 0.4 %": Costs.flat(0.004),
    "NOK 100k, no buffer": Costs(buffer=0.0),
    "NOK 100k": Costs(),
    "NOK 1m": Costs(capital=1_000_000.0),
}


def cost_sensitivity(panel: Panel | None = None, start: str = "2001-01-01", settings: dict[str, Costs] | None = None) -> pd.DataFrame:
    """Each strategy's excess a year over the basket under several cost settings: what account size does to it."""
    panel = Panel.load() if panel is None else panel
    schedules = build_schedules(panel, pd.Timestamp(start))
    columns = {}
    for label, costs in (settings or COST_SETTINGS).items():
        daily = {name: simulate(panel.prices, schedule, costs) for name, schedule in schedules.items()}
        first = max(series.index[0] for series in daily.values())
        hurdle = annual(daily["equal_weight"][daily["equal_weight"].index >= first])
        own = {name: annual(series[series.index >= first]) for name, series in daily.items()}
        # a strategy whose costs took everything is reported as such (-1), not as an excess below -100 %
        columns[label] = {name: -1.0 if own[name] <= -0.99 else own[name] - (hurdle if name != "equal_weight" else 0.0) for name in daily}
    return pd.DataFrame(columns).loc[[s.name for s in STRATEGIES]]


# -- what the list of survivors does to the basket -------------------------------------------------


def _correlation(a: pd.Series, b: pd.Series) -> float:
    """Pearson correlation, or NaN when either series never moves."""
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(a.corr(b))


def survivorship_gap(path, panel: Panel | None = None, start: str = "2001-01-01") -> dict:
    """Our equal-weight basket against an index of every stock that was listed at the time.

    ``path`` is Bernt Arne Ødegaard's ``Norway_market_portfolios_monthly.csv`` (columns date, EW, VW, ...), from
    https://ba-odegaard.no/financial_data/ose_asset_pricing_data/index.html. His indices include the companies
    that were later delisted; ours does not. The difference over the same months is what the list of survivors
    adds to every return measured on it.
    """
    market = pd.read_csv(path, dtype={"date": str})
    market["month"] = pd.to_datetime(market["date"], format="%Y%m%d").dt.to_period("M")
    market = market.set_index("month")
    panel = Panel.load() if panel is None else panel
    ours = monthly(simulate(panel.prices, build_schedules(panel, pd.Timestamp(start))["equal_weight"], 0.0))
    ours.index = pd.PeriodIndex([pd.Period(year=y, month=m, freq="M") for y, m in ours.index])
    both = pd.DataFrame({"ours": ours}).join(market[["EW", "VW"]], how="inner").dropna()
    both = both.iloc[1:]  # the first month holds only part of a month of our returns

    def ann(r: pd.Series) -> float:
        return float((1 + r).prod() ** (12 / len(r)) - 1)

    periods = {}
    for label, since, until in PERIODS:
        part = both[(both.index >= pd.Period(since[:7], "M")) & (both.index <= pd.Period(until[:7], "M"))]
        if len(part) >= 12:
            periods[label] = ann(part["ours"]) - ann(part["EW"])
    return {
        "from": both.index[0],
        "to": both.index[-1],
        "months": len(both),
        "ours": ann(both["ours"]),
        "market_ew": ann(both["EW"]),
        "market_vw": ann(both["VW"]),
        "gap": ann(both["ours"]) - ann(both["EW"]),
        "correlation": _correlation(both["ours"], both["EW"]),
        "periods": periods,
    }


# -- where the returns are earned: overnight or during the day ------------------------------------


def _grow(returns: pd.Series, years: float) -> float:
    return float((1 + returns).prod() ** (1 / years) - 1)


def overnight_split(start: str = "2010-01-01", fraction: float = 0.2) -> pd.DataFrame:
    """Each group's return a year from the close to the next open (overnight) and from the open to the close.

    Groups: all stocks equal weight, and the best and worst fifth on 12-1 momentum, re-formed monthly. After Lou,
    Polk & Skouras (2019), who found that momentum profits accrue overnight and partly reverse during the day.
    Each figure is what a portfolio of the group, rebalanced daily and trading for free, would have earned holding
    only overnight or only during the day. Part of the gap is the spread (a close at the bid and an open at the
    ask), which no one can trade. Starts in 2010 because Yahoo's opens before then are often the previous close
    repeated (see cleaning.py).
    """
    from osloquant.domain import Stock1dAdjKdata

    df = Stock1dAdjKdata.query_data(columns=["entity_id", "timestamp", "open", "close"], start_timestamp=pd.Timestamp(start) - pd.DateOffset(years=2))
    opens = df.pivot(index="timestamp", columns="entity_id", values="open").sort_index()
    closes = df.pivot(index="timestamp", columns="entity_id", values="close").sort_index()
    panel = Panel.from_closes(closes)
    opens = opens.reindex(panel.close.index)
    previous_close = panel.close.ffill().shift(1)
    night = (opens / previous_close - 1).where(panel.close.notna())
    day = panel.close / opens - 1

    mom = panel.momentum(12, 1)
    group = pd.DataFrame(np.nan, index=panel.close.index, columns=panel.close.columns)
    ends = panel.month_ends(pd.Timestamp(start))
    for n, i in enumerate(ends):
        until = ends[n + 1] + 1 if n + 1 < len(ends) else len(group)
        eligible = panel.eligible.columns[panel.eligible.iloc[i].to_numpy()]
        winners, losers = _top(mom.iloc[i][eligible], fraction), _top(mom.iloc[i][eligible], fraction, largest=False)
        group.iloc[i + 1 : until, group.columns.get_indexer(eligible)] = 0
        group.iloc[i + 1 : until, group.columns.get_indexer(winners)] = 1
        group.iloc[i + 1 : until, group.columns.get_indexer(losers)] = -1
    held = group.notna()
    rows = []
    for label, mask in (("all stocks", held), ("momentum winners", group == 1), ("momentum losers", group == -1)):
        active = mask.any(axis=1)
        years = active.sum() / DAYS
        nightly = night.where(mask).mean(axis=1)[active].fillna(0.0)
        daily = day.where(mask).mean(axis=1)[active].fillna(0.0)
        rows.append(
            {
                "group": label,
                "overnight": _grow(nightly, years),
                "intraday": _grow(daily, years),
                "total": _grow((1 + nightly) * (1 + daily) - 1, years),
            }
        )
    return pd.DataFrame(rows).set_index("group")
