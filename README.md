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
oq goats                 # three of the paper accounts as the document the Trading Goats page reads
oq lab                   # the documented strategies, tested for luck as well as for return
oq check-factor GoldCrossFactor   # does a factor look into the future, or depend on its warm-up?
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

### Margin accounts: shorts and leverage

An intraday account is a cash account unless its configuration says otherwise. With `max_leverage` above 1 it
becomes a margin account: it may borrow to buy, and with `shorts: true` a bearish signal in a stock it does not
hold opens a short instead of being ignored.

```yaml
  - name: lillebukk_v2
    watchlist: all
    signal: {rule: opening_range, minutes: 30}
    day_trade: true
    stop_loss: 0.02
    shorts: true            # a SELL signal in a stock not held opens a short
    max_leverage: 10        # gross exposure up to ten times equity
    financing_rate: 0.06    # yearly, on borrowed cash, charged per calendar day held overnight
    borrow_rate: 0.03       # yearly, on the value sold short
    maintenance_margin: 0.05  # everything is closed when equity falls under 5 % of exposure
```

How much an entry gets is decided by the signal, not the account: every rule now says how emphatic the bar was
(`Signal.strength`, 0 to 1: how far a breakout cleared its range, how fast two averages pulled apart, how deep
the stretch was before an RSI turn), blended with how busy the bar was against the stock's normal volume. A
faint signal gets one slot of exposure (equity over `max_positions`), an emphatic one up to `max_leverage`
slots, and never more than the buying power left (`equity x max_leverage - exposure`). Commission is paid on
the whole notional, so a ten-slot entry pays ten slots of commission; the stops work on the position's own
move, so a 2 % stop on a ten-slot entry costs 20 % of equity. Rules do not change: BUY means bullish and SELL
means bearish, and the account decides what that means for what it holds (close the long, cover the short,
open the other side). A short's stops mirror the long's (a trailing stop follows the low since the entry),
a short pays the dividends of what it borrowed, and `MARGIN` is the exit code of a forced close-out. A
`flat_at_close` account that wakes on a new day still holding (the computer slept through the close) closes
everything at that first look; with leverage, a night nobody meant to hold is the most expensive kind.
`oq intraday replay --rule ... --shorts --max-leverage 10` tries a rule this way before an account is given it.

What leverage does to a rule that loses after costs is multiply the loss; the replay says by how much before
any play money is put behind it. Nothing here resembles a real margin account's rules at a broker: the rates
and the maintenance level are settings, and shorting single Oslo stocks as a retail customer means CFDs or
certificates with their own costs. This is the simulator's version of the idea.

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

### Trading Goats

[beebots.tech](https://beebots.tech/) shows three AI bees trading crypto with real money. `oq goats` is the Oslo Børs
version with play money: three of the paper accounts above are the three billy goats Gruff, a troll looks at
them every evening, and a page shows where they stand.

```bash
oq goats                      # write ~/osloquant-home/goats.json
oq goats --split out --show   # also one JSON file per page document: meta/state, goats/<id>, herd, stream, gate, troll/log
oq goats --publish            # also push goats.json to the `goats` branch of origin, where the public page reads it
oq goats troll                # read the troll's log
oq goats troll "Out of the pasture, goat." --kind verdict --goat lillebukk
oq goats rewrite lillebukk --set stop_loss=0.03 --set max_entries_per_day=2 --why "stopped out six times in a week"
```

The mapping lives in `~/osloquant-home/goats.yaml` (written with three defaults on the first run: `daytrade_orb`
as Lillebukk, `intraday_breakout_slow` as Mellombukk, `live_momentum` as Storebukk). The export reads the store
and writes JSON; it trades nothing and never touches an account. Each goat carries its holdings with stop
levels, its equity curve, its latest signal, a status in one word (`GRAZING`, `WATCHING`, `BENCHED`, `FLAT`,
`DOZING` when the laptop has slept through the looks, `BEHIND` when the evening job has not run) and how many
of its looks it actually made. The other accounts are exported as the herd, and the buy signals the filters
refused as the bridge gate.

The troll is whoever reviews the goats (a scheduled Claude task, in practice). Its lines go into
`~/osloquant-home/troll.json` with `oq goats troll` and travel inside the document. When it decides a goat needs
new rules, `oq goats rewrite` adds a new account to `intraday.yaml` or `live.yaml` with the changed settings and
the old account's current value as its stake, and points the goat at it. The old account keeps running in the
herd under its own name (accounts are never edited or restarted), and the goat's curve is its lineage stitched
together, so a rewrite never resets the record. A goat's account must be `min_sessions_between_rewrites`
sessions old (five by default) before it can be rewritten. The charter the troll works to is `site/TROLL.md`.

The page is `site/trading-goats.html`, published at https://oscarschjelderup-sketch.github.io/oslo-quant/ by
`.github/workflows/goats-site.yml` whenever it changes. Opened as a claude.ai artifact it reads the artifact's
store; on GitHub Pages it reads `goats.json` from the `goats` branch, which `python -m osloquant.tick` refreshes
after every look and `scripts/run_live.ps1` after every evening run.

### Running the accounts on GitHub Actions

A laptop sleeps; a paper account that is only looked at while the laptop is awake misses closes and stops, and
with leverage those are the nights that cost. So the accounts can run on GitHub Actions instead, with the books
on a branch:

```bash
oq store push                 # once, from the machine that holds the books: the live store goes to the `store` branch
oq store pull                 # any machine: fetch the branch and merge the live accounts into this home
oq store push --config-only   # a laptop's changes to live.yaml, intraday.yaml, goats.yaml, troll.json; never its books
oq session next-tick          # what the day's loop does next: "tick 540", "evening 0" or "done 0"
oq session step tick          # one look, then the goats page and the store are pushed (evening: the evening job)
```

The store is the trader database cut down to the live accounts (a few hundred kilobytes), the configuration
files, the troll's log and the two job logs; price history is not carried, `oq record` fetches it and the
workflow caches it between runs. `.github/workflows/goats-session.yml` runs the day as one job: kick-started
before the open, it pulls the store, looks every quarter of an hour, makes the evening step after the close,
pushes the page and the store after each, and queues its own successor before the six-hour job limit (the
same loop the oil repository uses for its quotes). The `store` branch is the system of record: while it runs,
nothing else may step these accounts. The Windows tasks are disabled with
`scripts/schedule_live.ps1 -Remove` and `scripts/schedule_intraday.ps1 -Remove` (or Disable-ScheduledTask), and
a laptop that wants to read or review pulls first and pushes only its configuration.

### Signal watch: Investtech-style signals, with their odds

`oq signals` is the alert layer: a daily scan of the universe for the signals technical-analysis services sell
(a breakout above the 60-day high on volume, a new 52-week high, entry into a rising trend channel, and on the
risk side a breakdown below the 60-day low, a death cross, a 10 % drawdown, a falling channel), each tagged with
what that kind of signal has meant on this store's own history. `oq signals score --write` measures them
(entry at the next open, excess return over the equal-weighted universe 10/20/60 sessions later, hit rate) and
writes `resources/signal_odds.yaml`; `oq signals scan` lists today's signals; `oq signals digest --notify`
adds the research book (`~/osloquant-home/researchbook.yaml`, see `resources/researchbook.example.yaml`: the
companies you have a written case on, with target, bear and bull values, report dates and kill criteria),
writes `~/osloquant-home/signals/<session>.md` and raises a Windows toast. `scripts/schedule_signals.ps1`
registers the evening task (`run_signals.ps1`: `oq record`, then the digest); it never steps the paper accounts.

What the scorecard says (2010-2026, 64 stocks, round trip ~0.5 %): no buy signal has an edge after costs over
20 sessions (excess -0.5 to +0.4 %, hit rates 44-49 %); the best is the 60-day breakout on volume (+1.3 % over
60 sessions, 17 alerts a month), and breakouts worked 2010-18 and not since. The sell side carries more
information: a breakdown below the 60-day low is followed by -0.9 % excess over 60 sessions, a death cross by
-0.5 %. So the signals are a timing and risk layer on a case, not a strategy, and the digest says so.

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

## The lab: what holds up

Everything above invites the same mistake: try rules until one looks good. `oq lab` does the opposite. It tests a
fixed list of strategies from the research literature, with their published settings, on 25 years of Oslo prices,
and asks three questions of each: does it beat the equal-weight basket of the same stocks after real costs, is that
excess clearly above zero, and would it survive the charge for every other variant tried?

```bash
oq lab
oq lab --capital 1000000      # the same with a bigger account
oq lab --odegaard Norway_market_portfolios_monthly.csv   # and measure the survivorship (see below)
```

The tests:

- **Real costs.** Nordnet Mini (0.15 %, at least NOK 29 an order) plus 0.1 % slippage, paid out of a NOK 100 000
  account. With thirty positions the minimum is a full percent of each order, so how many stocks a strategy
  holds matters as much as how often it trades. Holdings within a quarter of their target weight are left alone.
- **A bootstrap interval** (stationary blocks, Politis & Romano 1994) for the excess over the basket.
- **The deflated Sharpe ratio** (Bailey & López de Prado 2014): the probability that the excess is skill rather
  than the luck of the best of all the variants tried, with correlated variants counted as fewer independent ones.
- **The probability of backtest overfitting** (Bailey, Borwein, López de Prado & Zhu 2017), by combinatorially
  symmetric cross-validation over 24 settings of momentum: pick the best on half of the history, see where it ranks
  on the other half, for all 12 870 ways of halving it.
- **Walk-forward re-tuning:** each January, pick the momentum setting that did best so far and hold it for the year.

On 6 October 2026, February 2001 to October 2026, 62 stocks:

| Strategy | Source | Per year | Over the basket | 95 % interval | Deflated Sharpe | Largest drawdown |
|---|---|---:|---:|---:|---:|---:|
| equal weight (the hurdle) | | +17.7 % | | | | -62 % |
| momentum + 200-day trend | (the live momentum account) | +29.0 % | +11.4 % | +1.0 to +19.7 % | 0.52 | -51 % |
| trend: every stock above its 200-day average | Faber 2007 | +26.4 % | +8.8 % | +2.5 to +17.5 % | 0.62 | -42 % |
| momentum with a buy/hold buffer | Novy-Marx & Velikov 2016 | +26.3 % | +8.6 % | -1.1 to +17.1 % | 0.36 | -57 % |
| momentum 12-1, best fifth | Jegadeesh & Titman 1993 | +24.5 % | +6.9 % | -2.1 to +11.9 % | 0.32 | -57 % |
| momentum, volatility-managed | Barroso & Santa-Clara 2015 | +23.8 % | +6.1 % | -3.1 to +11.2 % | 0.26 | -55 % |
| dual momentum | Antonacci 2014 | +23.3 % | +5.6 % | -5.0 to +12.0 % | 0.20 | -47 % |
| market timing, 10-month average | Faber 2007 | +15.8 % | -1.9 % | -13.3 to +4.9 % | 0.00 | -31 % |
| low volatility | Blitz & van Vliet 2007 | +12.8 % | -4.9 % | -13.8 to +0.3 % | 0.00 | -62 % |
| short-term reversal | Jegadeesh 1990 | +6.1 % | -11.5 % | -16.5 to -2.0 % | 0.00 | -71 % |
| turn of the month | Lakonishok & Smidt 1988 | ruined by costs | | | | |

What it says:

1. **Trend and momentum are the only candidates**, and both are slow: decided once a month, held for months,
   overnight. Their intervals stay above zero, but neither clears a deflated Sharpe of 0.95, so luck has not been
   ruled out. Trend's excess came mostly from leaving the market before 2008 (+19.8 % a year over the basket in
   2001-2008, +2.6 % since 2017); momentum with the trend filter was ahead in all three periods.
2. **Tuning is overfitting.** Among the 24 momentum settings, the best one on half of the history landed in the
   bottom half on the other half 78 % of the time. Re-tuned every January, momentum earned +2.1 % a year over the
   basket; the textbook 12-1 setting, never touched, earned +5.7 %. Use the published settings.
3. **Costs decide what is left.** Short-term reversal trades its portfolio nine times a year and pays almost five
   points a year for it (+10.9 % before costs, +6.1 % after); turn of the month, trading forty stocks twice a month,
   is eaten whole by the NOK 29 minimum. `oq lab --capital 1000000` shows how much of that is the account's size.
4. **Momentum is real on Oslo Børs.** Ødegaard's momentum factor over every stock that was listed at the time,
   delisted ones included, earned 1.44 % a month from 2001 to 2024, with a t-statistic of 4.0. That is independent
   evidence, on data without our survivorship problem.

### Survivorship, measured

The stock list holds today's companies, so the past looks better than it was. Bernt Arne Ødegaard publishes an
equal-weighted index of every stock listed on Oslo Børs at the time, from 1980
([his data page](https://ba-odegaard.no/financial_data/ose_asset_pricing_data/index.html)). Download
`Norway_market_portfolios_monthly.csv` from there and pass it with `--odegaard`. From March 2001 to December 2024:

| | Per year |
|---|---:|
| our equal-weight basket of today's 62 stocks | +17.2 % |
| every stock listed at the time, equal weight (Ødegaard) | +9.6 % |
| **the list of survivors adds** | **+7.6 %** |

The gap is 6-10 points in every period. Take it off every absolute return in this README. The comparisons with
the basket share the same list, so they are hurt less; for trend and momentum, which tend to sell a stock long
before it is delisted, probably not at all, but that is a reasoned guess, not a measurement.

### Where the returns are earned

The lab also splits each day's return into close-to-open (overnight) and open-to-close (intraday), after Lou,
Polk & Skouras (2019). From 2010, for a portfolio rebalanced daily and trading for free:

| | Overnight | Intraday | Whole day |
|---|---:|---:|---:|
| all stocks | +44.2 % | -17.4 % | +19.2 % |
| momentum winners | +39.9 % | -8.8 % | +27.6 % |
| momentum losers | +88.1 % | -41.4 % | +10.2 % |

Part of the split is the spread (a close at the bid, an open at the ask), which nobody can trade, so the sizes
should not be taken literally. The direction should: on Oslo Børs the long side has earned its return while the
market was closed, and lost during the day. That is why the day-trade bots above found nothing, and why the
candidates in the lab hold overnight.

### Two checks on any factor

`oq check-factor NAME` runs two checks borrowed from freqtrade (`lookahead-analysis` and `recursive-analysis`).
Neither reads the code:

- **Look-ahead.** The factor is computed on all the data and again on the data up to each of a few dates. If
  what it says about a date changes once later days are known, it looked into the future (a `shift(-1)`, a
  centred window, a fit on the whole sample).
- **Warm-up.** The newest date is computed with less and less history before it. Exponential averages never
  forget where they started. MACD needs about 400 days before its verdicts stop moving; 12-1 momentum needs more
  than a year to have a value at all.

Every factor that ships passes the look-ahead check. A factor of your own is checked with
`oq check-factor my_module:MyFactor`.

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

- **Survivorship.** Measured above at 7.6 percentage points a year on the equal-weight basket. The only real fix
  is a data vendor that keeps delisted companies (Titlon, at several Norwegian universities, may have them).
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
  research/    the lab: strategies, the cost model, the tests for luck, the checks on factors
  health.py    the checks behind `oq doctor`
  goats.py     the Trading Goats export: three paper accounts as one JSON document
  store.py     the live store on a branch: pack, push, pull, merge
  session.py   the trading day as a loop for a runner: what to do next, and doing it
  tick.py      what the 15-minute scheduled task runs
  ml/          the machine-learning harness
  ui/          the Dash dashboard
  samples.py   the four sample strategies
  cli.py       the `oq` command
examples/      runnable scripts: queries, a formal and a solo strategy, a selector, machine learning
scripts/       the evening job and the intraday looks for Windows Task Scheduler
tests/         265 tests on synthetic data; none touches the network
```

```bash
pytest          # about four minutes
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
- A strategy lab with the deflated Sharpe ratio, the probability of backtest overfitting and walk-forward
  re-tuning, and look-ahead and warm-up checks on factors after freqtrade.
- Monthly and weekly strategies act on the first trading day of the period, so the loop never needs to know
  the calendar ahead.
- Live accounts are paper accounts at real prices with a timestamped decision log, where zvt connects to a
  broker.

Not carried over: weekly and one-minute bars, the Chinese data vendors, the tag system, the REST server and
its separate front end, live trading through a broker, and the state-carrying accumulators.

zvt is MIT-licensed, © zvtvz. This project is MIT-licensed too; see [LICENSE](LICENSE).
