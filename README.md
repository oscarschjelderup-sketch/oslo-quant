# oslo-quant

[![CI](https://github.com/oscarschjelderup-sketch/oslo-quant/actions/workflows/ci.yml/badge.svg)](https://github.com/oscarschjelderup-sketch/oslo-quant/actions/workflows/ci.yml)

A modular quant framework for Oslo Børs: one way to record and query data, factors on a two-dimensional
index, a backtester that cannot see the future, paper accounts that are stepped forward every evening,
intraday paper accounts that trade on signals from coded rules, a machine-learning harness and a dashboard.

The architecture follows [zvt](https://github.com/zvtvz/zvt), an open-source framework built around Chinese
markets and Chinese data vendors. None of zvt's data sources cover Oslo, so this is a rewrite of its ideas
for a different market, not a fork: the same concepts and the same class names where they carry over, new
code underneath. [What was carried over and what was not](#relation-to-zvt) is listed at the end.

```python
from osloquant.domain import Stock, Stock1dAdjKdata
from osloquant.samples import MomentumTrader

Stock.record_data()                      # the stock list
Stock1dAdjKdata.record_data()            # daily bars since 2000, stored locally, updated incrementally
trader = MomentumTrader(start_timestamp="2015-01-01", end_timestamp="2026-10-02").run()
trader.stats()                           # return, risk, turnover, against the index and against the universe
```

## Install

Python 3.11 or newer.

```bash
pip install -e ".[dev]"
```

## Five minutes

```bash
oq record --finance      # entity lists, daily bars, financial statements. About four minutes the first time
oq status                # what is stored
oq check                 # the extreme bars in the data, to tell vendor errors from real crashes
oq targets MomentumFactor
oq backtest momentum     # also: ma, macd, trend
oq traders               # the stored backtests side by side
oq live                  # step the paper accounts forward to the last completed session
oq intraday replay       # try the intraday rules on the last weeks of 15-minute bars
oq intraday run          # follow today's session: a look every 15 minutes, play money only
oq doctor                # is everything that should be running, running?
oq ui                    # the dashboard at http://127.0.0.1:8050
```

`oq record` can be run again at any time. It fetches only what is missing. Everything is stored as SQLite
files under `~/osloquant-home/data` (move it with the `OSLOQUANT_HOME` environment variable).

## The ideas

### Entities and schemas

A *tradable entity* is something you can hold or watch. Its id reads `{type}_{exchange}_{code}`:
`stock_ol_EQNR`, `index_ol_OSEBX`, `future_ice_BRENT`, `currency_fx_USDNOK`.

A *schema* is a table: the entity lists (`Stock`, `Index`, `Future`, `Currency`), the bars
(`Stock1dAdjKdata`, `Stock1dKdata`, `Stock15mKdata`, `Index1dKdata`, ...), dividends and splits (`StockAction`), the reports
(`IncomeStatement`, `BalanceSheet`, `CashFlowStatement`, `FinanceFactor`). Every schema is used the same two ways:

```python
Schema.record_data(provider="yahoo", codes=["EQNR", "DNB"])   # fetch and store what is missing
Schema.query_data(code="EQNR", start_timestamp="2026-01-01")  # read it back as a DataFrame
```

`query_data` takes SQLAlchemy conditions, so a market-wide screen is one call:

```python
FinanceFactor.query_data(
    filters=[FinanceFactor.report_period == "year", FinanceFactor.roe > 0.15, FinanceFactor.revenue_growth_yoy > 0],
    order=FinanceFactor.roe.desc(), limit=10, columns=["code", "roe", "revenue_growth_yoy"],
)
```

A *recorder* connects a schema to a data provider. Defining a recorder class that names its `provider` and
`data_schema` is all it takes for `record_data(provider=...)` to work, so a second data source is added
without touching anything that reads the data.

### Factors

A factor moves through three DataFrames, all indexed by `(entity_id, timestamp)`:

| Frame | What it holds |
|---|---|
| `data_df` | rows read from a schema |
| `factor_df` | `data_df` plus what the transformer computed: moving averages, MACD, momentum |
| `result_df` | the verdict: `filter_result` (True, False or unknown) and/or `score_result` (0 to 1) |

```python
from osloquant.factors import GoldCrossFactor

factor = GoldCrossFactor(codes=["EQNR", "DNB"], start_timestamp="2025-01-01")
factor.result_df                      # the verdict per stock and day
factor.get_targets("2026-10-02")      # the stocks that are positive targets that day
factor.draw(code="EQNR", show=True)   # price, MACD, and the days the verdict flipped
```

Included: `CrossMaFactor`, `AboveMaFactor`, `GoldCrossFactor`, `BullFactor`, `BollFactor`, `MomentumFactor`
(a cross-sectional score) and `GoodCompanyFactor` (from reports). `TargetSelector` combines several.

A row of `result_df` at time t may only depend on data up to t. That one rule is tested for every factor
(compute it with and without the future, compare), and it is what the backtester relies on.

### Traders

> At a certain time, find the targets that match the conditions, buy and sell them, and see how it went.

*Formal*: return factors from `init_factors`; their positive targets are bought and negative ones sold.

```python
class SlowMaTrader(StockTrader):
    def init_factors(self, entity_ids, entity_schema, start_timestamp, end_timestamp, adjust_type=None, provider=None):
        common = {"entity_ids": entity_ids, "start_timestamp": start_timestamp, "end_timestamp": end_timestamp}
        return [CrossMaFactor(windows=(20, 60), **common), AboveMaFactor(window=200, **common)]
```

*Solo*: override `on_time` and call `trade_the_targets` with whatever you worked out yourself
([examples/follow_reports_trader.py](examples/follow_reports_trader.py)).

What happens on each trading day, in this order:

1. Orders decided on earlier days are filled at today's open, sells first.
2. After the close, the factors are asked for targets using data up to and including today.
3. `on_time` runs, then take-profit and stop-loss.
4. The decisions become signals, due at the next trading day's open.
5. The account is marked to today's close.

So a decision made on the close of day t is never filled before the open of day t+1. The account is long-only
and cash-only, buys whole shares, and is split in `max_positions` equal slots. Defaults: 5 bp commission each
way and 10 bp slippage. A finished run is stored (`TraderInfo`, `AccountStats`, `Position`, `Order`) and can
be read back with `query_data` like any other schema.

Nothing in a day's work looks at a later day, not even at the calendar: a monthly strategy acts on the first
trading day of a month, which can be told that evening, rather than on the last, which cannot. That is what
lets the same loop run a backtest and step a live account.

### Live paper accounts

A backtest can always be made to look good. What cannot be faked is a decision that was written down before
the price it was filled at existed. `oq live` keeps accounts like that:

```bash
oq live            # record today's data, step every account to the last completed session, show where they stand
oq live --status   # only show
```

Each evening it books dividends and splits, fills the orders decided earlier at that session's open, values
the holdings at its close, asks the strategy for new decisions and stores them with the wall-clock time.
Every fill then says whether its decision was logged before the market opened that day. A run that is late
and catches up several sessions still books them, but marks those fills as late: they are not evidence.

A live account differs from a backtest in the direction of what a real account sees:

| | Backtest | Live account |
|---|---|---|
| Fills and valuation | adjusted prices | real, unadjusted prices |
| Dividends | folded into the prices | arrive as cash on the ex-date |
| Splits | folded into the prices | change the number of shares |
| Commission | a percentage | a percentage with a minimum per order |
| History | recomputed on every run | appended, never rewritten |

The accounts are listed in `~/osloquant-home/live.yaml` (written with two defaults on the first run:
`momentum` and `trend`, NOK 100 000 each, Nordnet Mini's 0.15 % with a NOK 29 minimum). An account starts on
the first session after it appears there and is never restarted; to try a changed strategy, add it under a
new name and let both run. Any trader class can be used: `strategy: "my_package.my_module:MyTrader"`.

To run it every evening on Windows:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/schedule_live.ps1
```

That registers a task for weekdays at 17:30 and 21:30 and every morning at 07:30, local time. Oslo closes at
16:25; the two later runs are fallbacks and do nothing when the first one succeeded. `-Remove` takes the task
away again. Each run appends one line to `~/osloquant-home/logs/live.log`.

No real money is involved anywhere, and a few weeks of a paper account say nothing either way. The point of
starting is that the record only begins to exist once it runs.

### Intraday paper accounts

The daily accounts decide once, after the close. The intraday accounts watch the 15-minute bars through the
day and trade the BUY and SELL signals of a coded rule, with play money.

```bash
oq intraday rules              # the signal rules there are, and their settings
oq intraday replay --days 30   # the configured rules over the last weeks, with the delays of a live run
oq intraday run                # follow today's session until the close
oq intraday poll               # or: one look, now
oq intraday status             # the accounts, their holdings, their latest signals and the looks made
```

Every 15 minutes while Oslo is open, each account fills the orders it sent earlier, values its holdings, lets
the risk rules look at each holding, lets the signal rule look at the newest completed bar of each stock on
its watchlist, and turns the signals into orders. Every signal is logged with what was done about it and why.
The log reads like this (made-up numbers, to show the format):

```
10:16  signal BUY FRO at 268.40 (09:45 bar): ma5 267.90 crossed above ma20 267.55 -> ordered
10:31  filled BUY 74 FRO at 269.10 (10:15 bar): BUY ma_cross: ma5 267.90 crossed above ma20 267.55
13:46  signal STOP FRO at 260.90 (13:15 bar): 260.90 is -3.0% from the purchase at 269.10 -> ordered
```

An account is a few lines in `~/osloquant-home/intraday.yaml`:

```yaml
accounts:
  - name: intraday_ma
    watchlist: MomentumFactor                     # may only buy what the daily factor liked at the last close
    signal: {rule: ma_cross, fast: 5, slow: 20}   # the rule that says BUY and SELL
    stop_loss: 0.03                               # the risk rules: sell 3 % below the purchase price,
    take_profit: 0.06                             # or 6 % above it
    input_money: 100000
    max_positions: 5
```

| Rule | BUY when | SELL when |
|---|---|---|
| `ma_cross` (fast, slow) | the fast average crosses above the slow one | it crosses below |
| `breakout` (lookback) | the close breaks above the high of the last bars | it breaks below their low |
| `macd_cross` (fast, slow, n) | MACD crosses above its signal line | it crosses below |
| `rsi` (period, low, high) | RSI comes back up through `low` | RSI falls back through `high` |
| `opening_range` (minutes) | a bar closes above the high of the day's first `minutes` | one closes below its low |

Risk rules: `stop_loss`, `take_profit`, `trailing_stop` (from the highest price since the purchase),
`flat_at_close` (hold nothing overnight) and `cooldown_bars` (after selling a stock, ignore buy signals in it
for that many bars, so a rule does not buy back what it was just stopped out of). The watchlist is a daily factor's positive targets, `all`, or a list
of codes. A rule of your own is a subclass of `Rule` with one method, named by its import path:

```python
from osloquant.intraday import BUY, Rule

class ThreeUp(Rule):
    code = "three_up"

    def evaluate(self, bars):                       # the completed bars of one stock; the verdict is about the last
        last = bars["close"].iloc[-4:]
        if last.is_monotonic_increasing and last.is_unique:
            return self.signal(BUY, "three higher closes in a row", bars)
```

Two things keep the result honest:

- **The quotes are late.** Yahoo's Oslo prices arrive about 15 minutes after the fact. A rule sees a bar a
  quarter of an hour after it closed, and the order is filled at the price the market has moved to by then
  (the open of the bar starting as the order is sent), not at the price that raised the signal.
- **A missed look is a missed signal.** A signal is acted on only while its bar is fresh. If the computer was
  asleep, nothing is traded in hindsight.

`oq intraday replay` runs the same step function over stored bars with the same delays, and plays each
account twice: with the real costs, and with free trading. The second number is the rule itself; if it is not
clearly positive, no tuning of stops or costs will rescue the rule. A table below it shows how the positions
were closed (by the rule's SELL, by the stop, by the target), which is usually where a rule's trouble shows.

To try a variant without touching the configuration:

```bash
oq intraday replay --rule ma_cross --param fast=20 --param slow=60 --stop-loss 0.03 --take-profit 0.06
```

On 5 October 2026, over the 21 trading days before it:

| | Return | With free trading | Round trips | Commission paid |
|---|---:|---:|---:|---:|
| `ma_cross(5, 20)` | -8.9 % | +3.7 % | 129 | 7 605 |
| `breakout(20)` | -3.1 % | +2.9 % | 60 | 3 695 |
| `ma_cross(20, 60)` | +0.2 % | +4.9 % | 45 | 2 854 |
| `breakout(60)` | +1.2 % | +3.8 % | 23 | 1 520 |
| OSEBX | -1.5 % | | | |

Read the two return columns together. Before costs, all four rules made money in these weeks; after them, the
fast ones lost most of it again. A round trip costs about 0.5 % here (commission with its NOK 29 minimum both
ways, plus slippage), whatever the rule, so what decides the result is how often a rule trades. The slow
versions keep what the fast ones pay away. That is why the default configuration runs each rule fast and slow
side by side: the live accounts will show whether the difference holds on days the replay has not seen.

And read them with suspicion. Three weeks of one market are very little, the slow variants were picked
*after* seeing these numbers, and every variant tried is one more chance to fit the past. The accounts are
there to watch rules work and to try ideas for free.

On Windows, `scripts/schedule_intraday.ps1` registers a task that runs `python -m osloquant.tick` every 15
minutes around the clock, without a window; `-Remove` takes it away. Outside Oslo's trading hours a run asks
the clock and stops within milliseconds. It repeats without a daily start time on purpose: a repetition that
hangs on "weekdays from 07:46" never starts on a day the laptop was asleep at 07:46, which is how the first
trading day was missed.

### The day-trade bots

Two accounts are day traders: `daytrade_orb` buys the break of the day's first half hour (the classic opening
range breakout), `daytrade_breakout` buys a new two-day high. Both are built around the one thing the numbers
above made plain, that a round trip costs about 0.5 % whatever the rule:

- **Few trades, each given time.** A position is closed by its stop or at the close, not by the next wobble of
  the rule (`exit_on_signal: false`). Entries only between 09:30 and 14:30, so that the opening noise is
  skipped and a position has hours left to move. One entry per stock a day, three a day in all, three slots.
- **Only trades that can pay for themselves.** The stock's average daily range must be at least four round-trip
  costs (`min_range_to_cost: 4`), and the signal bar must trade at least 1.5 times its usual volume
  (`min_relative_volume: 1.5`); signals arriving together are taken busiest first.
- **Not one bet five times.** At most one position per sector (`max_per_sector: 1`); the momentum list is mostly
  shipping and oil.
- **Nothing overnight.** Everything is sold before the close (`flat_at_close`).

`day_trade: true` turns on the first and the last of these; the rest are settings of their own, documented at
the top of `intraday.yaml`. The same settings work in a replay:

```bash
oq intraday replay --rule opening_range --day-trade --stop-loss 0.02 --max-per-sector 1 --min-relative-volume 1.5 --min-range-cost 4
```

Over the 43 trading days of 15-minute bars Yahoo had on 5 October 2026, next to the four accounts that hold
overnight:

| | Return | Without the best trade | With free trading | Round trips | Per round trip before costs |
|---|---:|---:|---:|---:|---:|
| `daytrade_orb` | -23.3 % | -24.2 % | -1.1 % | 126 | -0.02 % |
| `daytrade_breakout` | -5.5 % | -6.2 % | +6.1 % | 66 | +0.27 % |
| `ma_cross(5, 20)` | -11.9 % | -13.4 % | +14.7 % | 262 | +0.20 % |
| `breakout(20)` | +0.8 % | -5.3 % | +13.9 % | 121 | +0.43 % |
| `ma_cross(20, 60)` | +2.9 % | +1.5 % | +11.4 % | 78 | +0.54 % |
| `breakout(60)` | +6.1 % | +0.9 % | +10.6 % | 43 | +0.47 % |
| OSEBX | +2.3 % | | | | |

The last column is the most any round trip could cost for the rule to break even. Three things follow:

1. **The day-trade bots do not work.** The opening-range breakout earned nothing before costs, so no broker is
   cheap enough for it. The day-trade breakout earned 0.27 % a round trip against a cost of about 0.5 %.
2. **The faster quotes are not the answer.** The same bots replayed as if Yahoo's quotes were real time gave
   -24.7 % and -5.7 %: the same. Whatever these rules are missing, it is not 15 minutes.
3. **What the overnight accounts earned came mostly from overnight moves**, and much of it from very few of them.
   The best trade of `breakout(20)` was AutoStore, bought on 7 August and sold on 13 August after the stock
   opened 25 % higher; without that one trade the account lost 5.3 %. Without its best trade, no account beat
   simply holding the index. A day trader, flat every evening, gives up exactly those moves.

The bots run as live paper accounts all the same: forty-three days are few, and a record kept forward is the
only one that cannot be fitted. But nothing here suggests that a rule on 15-minute bars, at retail costs, beats
owning the market.

### Is it running?

A job that silently does not run looks exactly like a quiet market. `oq doctor` tells the two apart:

```
ok      Daily prices                newest bar Mon 05 Oct
ok      live_momentum               at Mon 05 Oct, 10 of 10 fills logged before the open
check   intraday_ma                 22 of 30 looks made today; 81% of all looks since the start
ok      Task 'oslo-quant intraday'  last run Mon 05 Oct 19:31, next Mon 19:46
```

It checks that the daily prices are as fresh as they can be, that each daily account has stepped to the newest
session (and how many of its fills were decided in time), how many of the day's looks each intraday account
made and how late Yahoo's quotes really were, and whether the scheduled tasks exist and what their last run
returned. The Live tab of the dashboard shows the same, without the tasks.

### Machine learning

```python
from osloquant.ml import MaStockMLMachine

machine = MaStockMLMachine(codes=["EQNR", "DNB", "MOWI"], predict_start_timestamp="2023-01-01", predict_steps=20)
machine.train()          # any scikit-learn estimator can be passed in
machine.predict()
machine.evaluate()       # out of sample, next to the naive forecast it has to beat
```

The split is in time. The last `predict_steps` bars before the split are left out of training, because their
labels are computed from prices inside the test period.

## What the sample strategies did

63 stocks, 2 January 2015 to 2 October 2026, ten equal slots, costs as above. Recorded on 2 October 2026;
re-running `oq record` and the backtests later will move the numbers.

| | Per year | Volatility | Sharpe | Largest drawdown | Turnover per year |
|---|---:|---:|---:|---:|---:|
| `momentum`: top fifth on 12-1 month return, above the 200-day average, monthly | +25.6 % | 22.5 % | 1.13 | -36.5 % | 0.9x |
| `trend`: close above the 200-day average, the ones furthest above it first | +26.3 % | 21.5 % | 1.20 | -31.4 % | 1.3x |
| `macd`: MACD above its signal line | +14.4 % | 22.6 % | 0.71 | -34.8 % | 21.6x |
| `ma`: 5-day average above 10-day | +8.8 % | 20.3 % | 0.52 | -37.7 % | 28.4x |
| **All 63 stocks, equal weight, no costs** | **+19.0 %** | 17.8 % | | -46.3 % | |
| OSEBX | +11.4 % | 16.3 % | | -32.8 % | |

**Read the bold row first.** The stock list holds companies that are listed today. Owning all of them
equally returned 19.0 % a year, 7.6 points more than the index, with no skill at all: the list is a list of
survivors (and tilts to smaller companies than the cap-weighted index). So the hurdle for a strategy here is
19 %, not 11 %. Against it, the two fast strategies lose most of what they make to turnover, and `momentum`
and `trend` are ahead. Those two are one bet, not two: both buy what has already risen. And the edge is
overstated by an unknown amount, because a rule that buys winners, run over survivors, never buys a winner
that later went to zero.

**Then distrust the `trend` row.** When more stocks qualify than there are slots, something has to pick. The
first version took them in alphabetical order and returned 19.3 % a year. Ranking by distance above the
average instead gave 26.3 %. A result that moves seven points on a tie-break is telling you how much room
there is to tune a backtest into whatever you hoped to see. That is the reason for the live accounts.

These are textbook rules, there to exercise the framework and to be argued with. None is a recommendation.

## Data quality

Yahoo is free and delayed, and its Oslo data has faults. The ones that follow a pattern are repaired by rule
when recording ([cleaning.py](src/osloquant/recorders/yahoo/cleaning.py)); the record summary reports how often
each rule fired. On the full history of the 63 stocks:

| Fault | Rule | Bars |
|---|---|---:|
| A dividend is taken off the close one day early, so the adjusted series drops and jumps back | If the next bar pays a dividend and adding it puts the close back inside the day's range, add it | 218 |
| An open, high or low was not restated for an old split (a half, quarter or fifth of the price) | Replace by the neighbouring closes when the close itself hardly moved | 456 |
| The close lies outside the day's high and low | Widen the range | 295 |
| A one-day spike on zero volume | Drop the bar | 1 |
| Padding: the previous close repeated on a day without trading | Drop the bar | 6 137 |

The first one matters more than it looks. For SalMar in June 2024 the uncleaned series shows -4.5 % one day
and +8.0 % the next where the true moves were +1.1 % and +1.6 %; a stop-loss or a volatility estimate sees
moves that never happened, once per dividend.

Faults that follow no pattern are listed one by one, with the reason, in
[data_exceptions.yaml](src/osloquant/resources/data_exceptions.yaml): four bad prints (AKSO 2024, SOFF 2020,
BORR 2021 twice) and the history of NEL before it was a hydrogen company. `oq check` lists every bar that
moves more than 40 %, which is how a new one is found. After the repairs 50 such bars remain in 297 775, all
with real events behind them (2020, restructurings, bids).

## Limits worth knowing

- **Survivorship.** See above. The only real fix is a data vendor that keeps delisted companies.
- **Reports.** Yahoo keeps about four annual and five quarterly reports per company and not the day each was
  published. A report is treated as public 90 days (annual) or 60 days (quarterly) after its period end, which
  is deliberately late. Factors on reports can screen today's market; they cannot be backtested over a cycle.
- **Fills.** Every order is filled in full at the open plus slippage. No volume limit, no market impact,
  which is generous for the smaller names.
- **Adjusted prices.** Backtests trade on prices restated for dividends and splits, so share counts are not
  the real ones and a dividend is reinvested the moment the stock goes ex. The live accounts do not: they
  hold real shares at real prices.
- **The jobs run on your computer.** A laptop that sleeps misses intraday looks, and those signals are lost;
  the evening job catches up missed sessions but marks their fills late. `oq doctor` shows how much was missed.
- **Long-only, one currency.** Research and backtests are on daily bars; only the intraday paper accounts use
  15-minute bars, of which Yahoo keeps 60 days.

## Extending it

**Another stock.** Add a line to [universe.yaml](src/osloquant/resources/universe.yaml), or keep your own
file and run `Stock.record_data(universe="my.yaml")`, then `oq record`.

**Another factor.** Subclass `TechnicalFactor`, pass a transformer, set `result_df` in `compute_result`:

```python
class NewHighFactor(TechnicalFactor):
    def compute_result(self):
        close = self.factor_df["close"]
        high = by_entity(close).transform(lambda s: s.rolling(250).max())
        self.result_df = filter_result(close >= high, valid=high.notna())
```

**Another data provider.** Subclass `KdataRecorder` (or `TimeSeriesRecorder`), name the `provider` and the
`data_schema`, and return a DataFrame from `record(entity, start, end)`. Storage, incremental updates and
the check for restated history are inherited.

## Layout

```
src/osloquant/
  contract/    what a schema, a recorder and a factor are; storage, queries, charts
  domain/      the schemas: entities, bars, reports
  recorders/   data providers (yahoo: client, cleaning rules, recorders)
  factors/     indicators, factors, the target selector
  trader/      the trader loop, the simulated account, the stored results, statistics
  live/        the evening job: session clock, stepping the paper accounts, their saved state
  intraday/    signal rules on 15-minute bars and the play-money accounts that trade them
  health.py    the checks behind `oq doctor`
  tick.py      what the 15-minute scheduled task runs
  ml/          the machine-learning harness
  ui/          the Dash dashboard
  samples.py   the four sample strategies
  cli.py       the `oq` command
examples/      runnable scripts: queries, a formal and a solo strategy, a selector, machine learning
scripts/       the evening job and the intraday looks for Windows Task Scheduler
tests/         201 tests on synthetic data; none touches the network
```

```bash
pytest          # about two and a half minutes
ruff check .
```

## Relation to zvt

Carried over, as concepts and mostly as names: tradable entities and their ids; schemas with `record_data`
and `query_data`; several providers per schema; recorders with incremental updates; the three-frame factor
model with transformers and scorers; `TargetSelector`; `Trader` / `StockTrader` with `init_factors`,
`on_time` and `trade_the_targets`; the simulated account and its stored tables; `MLMachine` and
`MaStockMLMachine`; a Dash dashboard.

Done differently on purpose:

- Orders fill at the next open. zvt fills at the close the decision was made on (available here as
  `execution="signal_close"`).
- The account is split in equal slots instead of spending a share of the remaining cash.
- Every backtest is compared with the equal-weighted universe as well as the index.
- The machine-learning split leaves a gap before the test period, and `evaluate()` reports the model next to
  a naive forecast.
- Data is cleaned by rule when recorded, and restated history is detected and downloaded again.
- Monthly and weekly strategies act on the first trading day of the period, so the loop never needs to know
  the calendar ahead.
- Live accounts are paper accounts at real prices with a timestamped decision log, where zvt connects to a
  broker.

Not carried over: weekly and one-minute bars, the Chinese data vendors, the tag system, the REST server and
its separate front end, live trading through a broker, and the state-carrying accumulators.

zvt is MIT-licensed, © zvtvz. This project is MIT-licensed too; see [LICENSE](LICENSE).
