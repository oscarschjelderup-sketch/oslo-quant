# Day Trader skill pack: evaluation for the oslo-quant dashboard

What the third-party "Day Trader skill" repository does, whether it is safe to learn from, and what (if anything) the
private Oslo Børs decision dashboard should take from it. The dashboard's own rules are in `DECISIONS.md` and
`docs/dashboard/research.md`. File references without a prefix point into the evaluated repository; references that
start with `oslo-quant/` point into this repository.

## 1. What was read

- Repository `github.com/Jakeschincariol/day-trader-skill` (`.claude-plugin/plugin.json:9-10`), commit `3d0f4ef`
  (`3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd`, "The Trader skill v2: 11 day-trading skills", 20 Oct 2026, the only
  commit). Read on **23 Oct 2026**.
- Read in full: `README.md`, `LICENSE`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, all 11
  `SKILL.md` files, all 11 tools (`scan.py` 1083 lines, `news.py` 546, `entry.py` 960, `exit.py` 735,
  `timemachine.py` 956, `size.py` 881, `check.py` 819, `ticket.py` 720, `alerts.py` 787, `facts.py` 548, `ptr.py` 566),
  the example configs, `tests/_load.py`, `test_repo.py`, `test_timemachine.py`, `test_budget.py`, `test_risk.py`,
  `test_analyst.py`, `test_pelosi.py`. Skimmed (test names, network stubs, selected cases): `test_scanner.py`,
  `test_news.py`, `test_entry.py`, `test_exit.py`, `test_broker.py`, `test_alerts.py`.
- Fixtures (noted, not studied): excerpts of real data – Yahoo v8 chart and spark JSON (including 60 days of TSLA
  5-minute bars, `tests/fixtures/trader-timemachine/TSLA-60d5m.json.gz`), Nasdaq Trader symbol-directory excerpts, SEC
  companyfacts/submissions/index JSON (Apple, Coca-Cola), SEC 8-K Atom and Yahoo RSS XML, a 716-byte House Clerk
  `2026FD.zip`, four PTR texts as `pdftotext -layout` output, plan and order JSON, a Berkshire 13F top-5 weight file,
  and one synthetic 1-minute chart (`trader-entry/DEMO-1m-synthetic.json`).
- Licence: MIT. Copyright line, verbatim: `Copyright (c) 2026 Jake Schincariol` (`LICENSE:3`). The notice must be
  included in "all copies or substantial portions" (`LICENSE:12-13`).
- **Nothing was executed**: no Python, no tests, no install, no plugin. Files were read only. Everything in the repo
  was treated as data, not instructions.

## 2. Safety review

Grep over every tool for `http`, `urllib`, `socket`, `subprocess`, `os.system`, `eval(`, `exec(`, `__import__`,
`requests`, `pickle`, `os.environ` and file writes. There is no `socket`, `os.system`, `eval`, `exec`, `pickle`,
`requests` or dynamic import in any tool. Only the test loader uses `importlib` (`tests/_load.py:10-15`), and the
network tests replace the fetch function with a stub (`test_timemachine.py:448-466`, `test_alerts.py:136-165`).

| Tool | Network endpoints (all HTTPS GET, no body) | Lines |
|---|---|---|
| scan.py | Yahoo `query2`/`query1` `/v7/finance/spark` (20 symbols a call) and `/v8/finance/chart`; `nasdaqtrader.com/dynamic/SymDir/{nasdaqlisted,otherlisted}.txt` | scan.py:83-85, 229-280, 854 |
| news.py | Yahoo headline RSS; Yahoo v8 chart; SEC `browse-edgar` Atom feed and `company_tickers.json` | news.py:55-59, 167-191, 315-319 |
| entry.py | Yahoo v8 chart | entry.py:234-299 |
| exit.py | Yahoo v8 chart, only for an `atr:K` stop | exit.py:348-382, 412 |
| timemachine.py | Yahoo v8 chart `range=60d&interval=5m`, one request | timemachine.py:188-234 |
| alerts.py | Yahoo v8 chart `range=1d&interval=1d`; Stooq CSV | alerts.py:196-201, 253-298 |
| facts.py | SEC `company_tickers.json`, `data.sec.gov` companyfacts and submissions, EDGAR Archives `index.json` | facts.py:53-56, 92-122 |
| ptr.py | House Clerk yearly index ZIP, PTR and FD PDFs | ptr.py:48-50, 82-90 |
| size.py, check.py, ticket.py | none (no network module imported) | size.py:54-59, check.py:62-68, ticket.py:36-42 |

- **What leaves the machine.** Only URLs with tickers, CIKs or years, plus a User-Agent. Yahoo, Nasdaq and the House
  get a fixed string naming the tool (e.g. `timemachine.py:81`). The two SEC tools send the user's own name and e-mail
  as User-Agent to sec.gov and refuse to call SEC without one (`facts.py:79-89, 103-110`; `news.py:148-155, 174-180`).
  No portfolio, plan, key or telemetry is sent anywhere. No POST.
- **Keys.** No tool reads or stores a key or password. Alpaca keys are typed by the user into Claude Desktop's own
  config as environment variables of a separate MCP server that is not in this repo (`trader-broker/SKILL.md:65-95`;
  placeholders in `trader-broker/claude_desktop_config.example.json:7-8`).
- **Subprocess.** One: `ptr.py` runs `pdftotext -layout <pdf> -` if it is on PATH, as an argument list, no shell,
  60 s timeout (`ptr.py:337-345`). It feeds downloaded PDFs to a local parser. Remote XML is parsed with
  `xml.etree` (`news.py:244, 261`; `ptr.py:107`).
- **Writes.** Only under `./trader/` in the current working directory (the user's project), never in the skill folder
  or the home directory, and every path is a flag: `timemachine.py:861-867`, `size.py:752-770`, `check.py:798-810`,
  `ticket.py:127-135`, `alerts.py:331-362`, `news.py:534-541`, `facts.py:527-541`, `ptr.py:173-179, 458-466`,
  `scan.py:825-831`, `entry.py:572-578`, `exit.py:655-661`. One weak spot: `ptr.py:460` builds the PDF file name from
  the DocID without checking that it is digits; the DocID comes from the command line or the Clerk's XML
  (`ptr.py:113`), so a crafted value could write outside `trader/state/ptr-pdfs/`. Low risk; validate IDs if reused.
- **Orders.** No Python tool can place an order. `ticket.py` says it never talks to a broker (`ticket.py:4`) and has
  no network import. An order happens only if Claude, following `trader-broker/SKILL.md:138-155`, calls
  `place_stock_order` on the external Alpaca MCP server. Guards: (1) a trader-risk PASS for the exact order on the
  same New York day, matched by a 16-hex SHA-256 fingerprint of the Alpaca fields (`check.py:271-275` =
  `ticket.py:145-149`; `ticket.py:315-340`); (2) the user's reply parsed by `parse_yes` (`ticket.py:271-297`), which
  rejects "sure", "ok", "yes to all", replies with "but/if/wait", and tickers or numbers that do not match the order
  (`test_broker.py:45-67`); (3) Claude's own "Allow once" card, because the SKILL tells the user to set the order tool
  to "Needs approval" (`trader-broker/SKILL.md:97-116`). It also forbids orders from scheduled tasks (`SKILL.md:197`).
- **"Paper by default" is a label, not a switch.** `"paper": true` (`trader-budget/config.example.json:18`,
  `size.py:79`) only drives a LIVE warning (`check.py:403-404`) and the ticket header (`ticket.py:356`). Paper or live
  is decided by the external server's `ALPACA_PAPER_TRADE` (`claude_desktop_config.example.json:9`).
- **The "append only" log is not append-only.** `ticket.py:32` calls `trader/state/broker.json` append only, but every
  write rewrites the whole file (`ticket.py:127-135, 516-517`). No hash chain. Not a model for the judgement log.
- **Plugin manifest** declares skills only (`plugin.json:21`, `"skills": "./"`): no hooks, no MCP servers. Installing
  it would load 11 SKILL.md files as instructions, one of which walks Claude towards an order tool.
  **Recommendation: do not install the plugin. Take ideas, and at most two small functions (section 7).**

## 3. The eleven skills

### 3.1 trader-scanner (`scan.py`)
Builds a US universe from Nasdaq Trader's two symbol files with a six-step filter on ticker shape and security name
(no test issues, ETFs, warrants, units, rights, notes or preferreds; ADRs kept) (`scan.py:400-443`). `daily` fetches
3 months of daily closes via Yahoo spark, keeps price ≥ $5 and last volume ≥ 1,000,000 (`scan.py:542-575, 1059`),
drops today's bar until the close (`498-513`) and tags five rules on closes only: close above the 20 closes before it;
a >10 % run over 10 sessions then a 5-day range <5 %; reclaim of the 20-day mean; Wilder RSI(14) <30; RSI <30
yesterday and an up close today (`516-539`, `485-495`). `orb` finds 5-minute opening-range breakouts in two stages
(spark closes as a necessary condition, then v8 highs/lows for at most the 200 most traded candidates) and refuses a
chart with any missing bar (`610-644`, `686-737`). Output `trader/watchlist.json`, sorted by price × volume (`572`).
**Verdict: Does not fit.** US universe and intraday; the daily rules are unmeasured, while oslo-quant already shows
signals with measured odds (D11). Two habits worth keeping: a partial scan is called partial
(`trader-scanner/SKILL.md:139-140`), and a series with a hole is refused rather than patched.

### 3.2 trader-news (`news.py`)
Tickers come from a flag or from the watchlist, plan and portfolio files (`news.py:128-145`). Per ticker it reads
Yahoo's headline RSS, the company's SEC 8-K Atom feed (only with a SEC User-Agent) and the last price against the
previous close, flagged MOVING at ≥ 3 % (`55-63`, `291-305`). Each item gets the watched tickers it mentions
(`(TICKER)`, `$TICKER`, `NYSE: TICKER` or the company name) and keyword tags in ten classes (earnings, analyst,
legal, deal, capital, people, risk, halt, regulatory, macro) (`77-88`, `327-351`); 8-K item numbers become labels and
nine items are marked important (`65-76`, `258-288`). Duplicates merge on id, on link, or on the same normalised title
the same day (`354-372`). A SHA-1 of each item id is remembered for 30 days so it shows once (`375-376`, `411-435`).
**Verdict: Does not fit** as a tool: the dashboard already has NewsWeb announcements and Norwegian RSS headlines with
its own name matching (D5, D10). Ideas: the cross-source dedupe rule, and an "important" flag driven by announcement
category (NewsWeb 1102 primary-insider trades, 1007 own shares; `oslo-quant/docs/dashboard/data-sources.md:72`).

### 3.3 trader-entry (`entry.py`)
Watches one ticker's 1- or 5-minute Yahoo bars for today. Opening-range breakout: range = high and low of the first 15
minutes; trigger = the first completed bar after the range that closes strictly above the range high (or above a
level the user gives), inside the no-entries-before/after window, optionally with volume ≥ X times the range bars'
mean (`entry.py:408-552`). A bar counts only once closed, and on live data only once Yahoo has caught up or 60 s have
passed (`459-468`); Yahoo's off-grid live tick is dropped (`448-449`). `watch` sleeps until just after each bar closes
(`695-779`). Writes `trader/entry.json` (`560-569`). Long only. **Verdict: Does not fit.** It times orders intraday;
the dashboard decides on daily closes and never trades. The rule "never use an incomplete bar" carries over to daily
data.

### 3.4 trader-exit (`exit.py`)
Turns an entry into a plan. Stop by rule – range midpoint, range low, fixed price, % under the entry, or K × ATR(14)
of the session's bars up to the entry (true range, the first bar using its own high − low) – rounded down to the cent;
risk = entry − stop; target = entry + R × risk rounded half-up (2R default) or a fixed price (`exit.py:270-333`,
`469-480`). Refuses a stop at or above the entry, a target at or below it, a risk under 0.05 % of the price
(`59`, `308-327`), and an entry at or after the flat-by time (`505-524`). Cents are handled with `Decimal`
(`196-212`). Writes `trader/plan.json` (`600-607`). **Verdict: Fits with changes (idea only).** "Price, stop, target,
R, refusals" is the structure of a case: last close, kill level, target, R = (target − price) / (price − kill level).
The refusals become form checks. The intraday stop rules do not carry over.

### 3.5 trader-timemachine (`timemachine.py`)
- **Inputs.** A plan (symbol, date, side, entry, entry bar, stop, target, setup, opening range) from
  `trader/plan.json` or flags (`timemachine.py:505-591`), and one Yahoo download of 60 days of 5-minute bars
  (`188-190`). Bars with a missing price, off the 5-minute grid, outside 9:30-16:00 New York, or not complete at the
  earlier of "now" and Yahoo's `regularMarketTime` are dropped (`271-307`).
- **Pool.** Only full sessions (all 78 bars) strictly before the plan date; half days and sessions with a hole are
  left out and listed (`318-330`, `744`). At least 20 are required (`89`, `720-722`). `pool[i]` (i = 1..77) holds every
  pool session's bar i as (open, high, low, close) divided by that session's bar i − 1 close (`335-342`). Bar 0, which
  carries the overnight gap, is never in the pool.
- **One replay.** Start at the plan's entry price after entry bar k. For each bar i = k+1 .. last: draw an offset with
  `randint(-window, window)` (window 2), clamp j = i + offset to 1..77, draw one tuple uniformly from `pool[j]`, and
  scale its high, low and close by the current simulated price; that close becomes the next price (`349-384`). The
  resampling unit is a single 5-minute bar (block length 1). Draws are independent across bars and across source days;
  the only conditioning is time of day. There is no conditioning on volatility, trend, weekday or the entry day's own
  path. The clamp over-weights slots 1 and 77 at the ends of the day; the open ratio is drawn but unused.
- **Outcome.** In the first bar that touches a level: stop if low ≤ stop (checked first), else target if high ≥
  target; a bar touching both counts as the stop (`370-379`). Nothing touched by bar `last` = "neither" (still open).
  `last` is the bar before `--until`: 16:00, or 13:00 on the listed early-close days (`697-703`). The path keeps
  running after a hit, so the "price at until" distribution is unconditional (`380-384`).
- **Statistics.** Shares of target, stop and neither; "green" = target, or neither with a close above the entry
  (`387-389`). R = the target's R at the target, −1 at the stop (also through a gap), else (close − entry) / risk
  (`390-391`). Median, 5th and 95th percentile of the price at until, with `pct(a, q)` = sorted a at index
  `int(q·n)`, no interpolation (`345-346`, `420-422`). A fan chart from a second run of 2,000 paths with the same seed,
  and a 24-bin histogram between the 1st and 99th percentile (`393-415`).
- **Seeds.** `random.Random(seed)`, default 19 (`358`, `929`); each bar consumes one `randint`, then one `choice`.
  Same plan, data and seed give the same numbers; the tests pin the first draws and hash the output
  (`test_timemachine.py:33-39, 104-110, 172-177`).
- **Costs and fills.** None. The entry fills at the plan's price, the stop and target exactly at their levels, with no
  commission or slippage (`timemachine.py:32-34`; `README.md:178-180`).
- **History ("every past day the setup fired").** The same full sessions as the pool (in-sample, no hold-out), and
  only for the opening-range setup (`599-600`, `728-736`). Per session: range = high/low of the first `or_minutes/5`
  bars; entry = the close of the first bar from the end of the range up to `last` that closes above the range high (no
  entry-time window); stop recomputed by the plan's rule (midpoint or range low, rounded away from the entry, or the
  plan's stop distance as a % of the entry; inferred when "auto", `594-621`); target = entry + the plan's R × risk; the
  later bars are walked stop-first, else exit at the `last` close (`435-490`). At most one trade per session, so the
  sample has no overlap. Example from the docs: 59 sessions, fired 33 times, 13 target, 15 stop, 5 neither
  (`trader-timemachine/SKILL.md:129-130`).
- **Verdict line.** share = target / (target + stop) among replays that hit a side; break-even = 1 / (1 + R); a gap
  under 5 points is "close to a coin flip" (1R) or "close to break-even", 5-15 points "leans", 15 or more "strongly"
  (`94-95`, `631-662`). Notes are added when more than 40 % hit neither and when the average R has the other sign
  (`96`, `665-676`). The thresholds are the author's choice, not measured.

**Verdict: Fits with changes.** The output (target first / kill first / neither, a real-history count beside it, a
stated seed, a break-even verdict) is what Part 1 needs. The engine must change: daily bars, horizons of 3, 6 and 12
months, block resampling instead of single bars, costs, and a non-overlap rule for the history (section 5).

### 3.6 trader-budget (`size.py`)
Sizes one long trade from the plan, the config, an optional fresh price and the portfolio cash (`size.py:775-818`).
Reference entry: a limit order's limit price; for a market order the plan's entry, or a price from
`trader/prices.json` if fresh (quote time −60 s to +15 min from now) and higher; a lower price is never used
(`254-265`, `341-346`). Hard refusals: not a buy, plan dated another New York day, missing entry/stop/target, ticker
blocked, no budget, buffer outside 0-100 %, stop ≥ entry, target ≤ entry (`313-353`). Risk and reward in integer
cents (`354-356`). Available cash = budget − buffer (budget × `cash_buffer_pct`), or portfolio cash − buffer if lower
(`358-364`). Four whole-share counts, each floored in integer cents (`shares_for`, `275-280`): max loss / risk per
share; budget × `max_position_pct` / entry; `max_order_usd` / entry; available / entry (`366-381`). qty = the
smallest, and the first limit with that count is named as binding (`383-386`). Soft refusals (no order written):
qty 0, reward:risk under `min_reward_risk`, cost under `min_order_usd` (`389-404`). Otherwise one Alpaca-shaped bracket
order (`418-441`). Defaults: 10 % buffer, 75 % cap, $4,000 max order, $5 minimum, $50 max loss, minimum R 1.0
(`62-85`). A v1 "weights mode" splits a budget over a weight list with an iterative cap, small slices dropped and
total-preserving rounding (`490-681`). **Verdict: Fits with changes.** This is Part 4's method almost line for line,
with the kill level as the stop and the store's last close as the entry.

### 3.7 trader-risk (`check.py`)
A pure function over proposed orders, the config, the portfolio, prices with their times and the day's broker log
(`check.py:373-705`). An order is an exit if it only reduces a holding (`515-525`); exits are blocked only for format,
asset and short-sale faults, everything else becomes a warning (`658-661`). Reference price: the limit price, a stop
order's stop price, else the higher of the plan's entry and a price ≤ 15 minutes old (`407-416`, `487-503`). An entry
is blocked when: the ticker is blocked; value is under the minimum or over the maximum order; cash after the buy falls
under the buffer (a % of cash plus positions) or below zero; the position would exceed `max_position_pct` of the
account; there is no stop while `require_stop`; stop or target sits on the wrong side; shares × (price − stop) exceeds
the max loss per trade; (target − price) / (price − stop) is under the minimum; the max losses of today's placed
entries plus this batch plus this order exceed the daily loss limit; the day's entry count is used up; it is outside
the New York entry window or the market is closed (hard-coded NYSE holidays 2026-27); the optional PDT count is hit;
it duplicates a symbol and side; or the daily order count is used up (`213-242`, `350-368`, `530-655`). Orders are
checked in file order, each PASS applied to a simulated account before the next (`663-683`). Verdicts and
fingerprints go to `trader/state/risk.json` (`798-810`). **Verdict: Fits with changes (ideas).** The shape – a pure
check, plain-text reasons, the batch applied in order, every number traceable – matches the server-side form check in
D3. The day-trade rules (window, PDT, trades per day, Alpaca format) do not.

### 3.8 trader-broker (`ticket.py`)
Renders each proposed order in plain words plus the exact JSON for Alpaca's `place_stock_order`, marks it READY only
if today's risk check passed that exact fingerprint and nothing is recorded yet (`ticket.py:315-340`), records the
user's yes word for word after `parse_yes` (`271-297`, `500-526`), logs placed/denied/failed, applies fills to
`trader/portfolio.json` with oldest-lot-first relief (`394-439`) and builds a market sell to be flat by the close
(`586-628`). The SKILL covers Alpaca MCP and IBKR connector setup (`trader-broker/SKILL.md:58-136`). **Verdict: Does
not fit.** The dashboard never trades and never steps paper accounts (`oslo-quant/DECISIONS.md:7-10`, D2).

### 3.9 trader-alerts (`alerts.py`)
Rule types: above/below (aliases target/stop), % move from the previous close or a reference, a New York clock time,
and the opening bell (`alerts.py:377-492`). Price levels ring once until reset, or re-arm when the price crosses back
(`469-479`); time and bell rules ring once per trading day, % moves once per day; a rule can be tied to one date
(`404-406`). `--from-plan` creates stop, target and flat-by alerts (`500-521`). Quotes come from Yahoo (Stooq returned
404 when the author tested it, `trader-alerts/SKILL.md:78-79`), one ticker per request 0.5 s apart, and are written to
`trader/prices.json` with each quote's own time and fetch time (`313-351`). NYSE calendar hard-coded for 2026-27
(`66-96`). **Verdict: Does not fit.** D7 already turns target/bear/bull crossings and 10 % moves into decision items
on daily closes. The rule "each price carries its own time and old prices are rejected" matches D9.

### 3.10 trader-analyst (`facts.py`)
Pulls a US filer's XBRL "company facts" from SEC and builds a quarterly table (`facts.py:235-278`). Quarters are values
with 80-100-day durations from 10-Q/10-K/20-F/40-F; when a period was filed more than once, the latest filing's value
wins but the fiscal label comes from the first filing (`141-163`); Q4 = the 350-380-day annual value minus exactly
three quarters inside it, marked "derived" (`166-192`). Each metric tries a list of concept names in order and fills
gaps (`62-71`, `195-210`). Per quarter: revenue, gross profit (or revenue − cost of revenue), operating income, net
income, diluted EPS, gross/operating/net margin, and year-on-year growth of revenue, net income and EPS against the
quarter ending 365 ± 10 days earlier (`213-220`, `244-268`); TTM = the last four quarters if they span < 300 days
(`269-275`). "What changed": the latest quarter with YoY, each margin in points against the previous quarter, revenue
quarter-on-quarter with a seasonality warning, and a flag when net income exceeds operating income (`294-333`). It
links the newest 10-Q/10-K and the newest 8-K with item 2.02 and its EX-99.1 press release (`338-381`) and warns when
SEC's facts lag a filed report by > 20 days (`281-291`). It compares only against the company's own history – no
consensus, no model, never "cheap" or "buy" (`trader-analyst/SKILL.md:110-117`). **Verdict: Fits with changes.** The
comparison logic and its caveats fit Part 2; the data source does not exist for Oslo.

### 3.11 trader-pelosi (`ptr.py`)
Reads the House Clerk's yearly index ZIP (XML, one row per filing), keeps FilingType P (transaction reports) and
filters by member name in any order (`ptr.py:104-161`); DocIDs not seen before are new, and the first run shows only
the last 45 days (`166-189`). Each PDF goes through `pdftotext -layout` (`337-345`) and is parsed line by line
(`251-334`): a transaction row is a regex with an optional owner code (SP spouse, JT joint, DC dependent child, blank
= self), asset text, type code, trade date, notification date and amount range (`194-196`); following label lines add
status, description, account and location, and page headers are skipped even inside a row (`197-207`). Buy/sell is
classified only from the type code: P purchase, S sale, "S (partial)" partial sale, E exchange (`57`). Ticker = the
last "(XXX)" in the asset text, asset type = the last "[XX]" code (`221-230`); the description is searched for option
contracts, call/put, strike, expiry and an "exercised" flag, and for a share count (`209-211`, `234-243`). The amount
stays a range with low and high (`214-218`); days to disclose = filing date − trade date, late if over 45
(`244-247`). Tickers in the user's portfolio are flagged (`350-398`). There is no return measurement anywhere.
**Verdict: Fits with changes (pattern only).** Index → new IDs → parse → classify → disclosure delay is the shape of
Part 3; the source and the parser are US-specific.

## 4. Summary table

| Skill | What it does | Fit for long-term Oslo cases | What we take (licence) | Why |
|---|---|---|---|---|
| scanner | US universe; daily close rules; intraday ORB scan | Does not fit | Habit: say "partial", refuse series with holes | Intraday, US, unmeasured rules |
| news | Yahoo RSS + SEC 8-K + move vs prior close, tags, dedupe | Does not fit | Idea: cross-source dedupe; "important" by category | D5/D10 already cover Norwegian sources |
| entry | Bar-by-bar intraday trigger | Does not fit | Rule: never use an incomplete bar | Order timing; no trading |
| exit | Stop/target/R with refusals | Fits with changes | Idea: R and refusals as form checks | Same structure as price/kill/target |
| timemachine | 10,000 bar replays + same rule on past sessions | Fits with changes | Idea; maybe `lean`/`verdict` code (MIT notice) | Part 1 output shape; engine must change |
| budget | Shares = min of four limits; refusals | Fits with changes | Method, reimplemented | Part 4 almost line for line |
| risk | Pure PASS/BLOCK check over a batch | Fits with changes | Ideas: reasons list, batch in order, open-risk cap | Matches D3 validation |
| broker | Tickets, yes-parsing, fills, flatten | Does not fit | Nothing | Dashboard never trades |
| alerts | Price/time alerts on delayed quotes | Does not fit | Rule: each price carries its time (D9) | D7 rules already on daily closes |
| analyst | XBRL quarters, YoY/QoQ, margins, TTM, caveats | Fits with changes | Method; maybe `periods`/`quarterly` code (MIT notice) | Part 2 logic; no XBRL in Oslo |
| pelosi | House PTR index, PDF parse, buy/sell rows | Fits with changes | Pipeline pattern and edge cases | Part 3 shape; US-only source |

## 5. What we take, by planned part

### Part 1 – outcome odds on the stock page
- **Relevant.** `simulate` (`timemachine.py:349-424`), `history_replay` (`451-490`), `full_sessions` and the
  20-session minimum (`318-330`, `720-722`), `pct` (`345-346`), `lean`/`verdict`/`verdict_notes` (`631-676`).
- **Must change.**
  1. Daily data from the oslo-quant store, not 5-minute Yahoo bars; horizons of 3, 6 and 12 months in sessions; the
     pool strictly before the judgement date (keep `timemachine.py:323`).
  2. Resampling unit. Single bars drawn independently by time of day lose volatility clustering and persistence; over
     months that understates the tails. Resample blocks of consecutive days (block length to be chosen and tested in
     oslo-quant, and printed with the result). Time-of-day slots have no daily analogue and go.
  3. Touch rule. If the store keeps daily highs and lows, use the repo's rule (low ≤ kill checked first, then high ≥
     target, both in one day = kill). On closes only, intraday touches are missed: label the result "on closes".
  4. Levels. Target = the case's target price. Kill level must be an explicit price field in the case: D7 says kill
     criteria are written fundamentals, so a price level must never be inferred.
  5. Analogues. The repo's history is one trade per session, so it never overlaps. Daily analogues (every past date
     with the same % distances to target and kill, scored over the same horizon) overlap almost completely between
     neighbouring start dates: count non-overlapping windows, or step by the horizon, and show that n.
  6. Signals. Score each signal's bracket outcome with the store's existing convention: from 2010, entry at the next
     open, 0.5 % round trip, excess vs the equal-weighted universe (`oslo-quant/src/osloquant/resources/signal_odds.yaml:1-7`).
     The Time Machine has no cost at all; do not copy that.
  7. Output: replays, seed, pool dates, sessions used and dropped, simulated and historical counts side by side, and
     the break-even verdict with R = (target − price) / (price − kill). Simulated odds are estimates: label EST (D9).
- **Pitfalls the repo's tests and docs show.** One missing close removes a whole session from the pool
  (`test_timemachine.py:243-248`): decide whether a hole ends a block or is skipped, and list what was dropped. Too
  little history is refused, not guessed (`264-274`); recent listings will hit this. Today's incomplete bar must never
  enter the pool (`238-241`; `timemachine.py:302-304`). A 2R plan with fewer target hits can still be at break-even,
  so judge by the share against 1/(1+R), not target vs stop alone (`test_timemachine.py:406-445`). "Neither" can
  dominate when levels are far away; the repo adds a note above 40 % and the price distribution decides those
  (`timemachine.py:665-676`). A gap through the level counts as exactly the level (`README.md:178-180`); across a
  quarterly report the real loss can be far larger, so present the kill-level loss as a lower bound. The repo's history
  is in-sample (same sessions as the pool), so the two numbers are not independent evidence. Our own addition:
  ex-dividend drops in an unadjusted price series can touch a kill level that total return would not; state which
  series is used.

### Part 2 – quarterly report analysis
- **Relevant.** `periods`/`quarterly` (`facts.py:141-192`), `series` with concept fallbacks (`62-71`, `195-210`),
  `_yoy_match` (`213-220`), `analyse` (`235-278`), `changes` (`294-333`), `stale_note` (`281-291`), and the rules in
  `trader-analyst/SKILL.md:53-69, 110-117` (filed numbers first, like with like, say what is derived, say when data
  lags, flag one-offs, never invent a number).
- **Must change.** Oslo has no XBRL feed: the figures come from the report PDF attached to the NewsWeb announcement
  (`message?messageId=` returns attachments, `oslo-quant/docs/dashboard/data-sources.md:70`). Each quarter's numbers
  are entered (or extracted and checked) with source link, page, units and currency. Comparisons: (a) previous quarter
  – margin points and QoQ with the seasonality caveat, as `facts.py:318-332`; (b) same quarter last year, matched on
  period end ± 10 days; (c) public consensus, only as a manually entered value with source and date, because
  consensus feeds are licensed (`oslo-quant/docs/dashboard/research.md:346`); (d) the case's own assumptions; (e) each
  kill criterion marked nearer / unchanged / triggered, which D7 already asks for at report dates.
- **Pitfalls.** Restated periods: take the latest value but keep the first filing's label
  (`test_analyst.py:66-77`). A derived Q4 is marked derived and its EPS is approximate (`test_analyst.py:48-53`);
  check per issuer whether a Q4 report exists before deriving. Say when the stored figures are older than the newest
  report (`test_analyst.py:107-112`). Flag net income above operating income (`test_analyst.py:114-120`). Banks and
  insurers have no gross margin: blank, not zero (`trader-analyst/SKILL.md:68-69`, `metrics.example.json:30-33`). TTM
  only with four quarters inside 300 days (`facts.py:271-273`). Record which line item was used, since names differ
  between issuers (`test_analyst.py:158-159`). Our own addition: some Oslo issuers report in USD or EUR, so store
  currency and units with every number.

### Part 3 – primary insiders and short positions
- **Relevant.** The `ptr.py` pipeline: index, filter, new IDs since the last check, fetch, parse, classify, render
  (`104-189`, `251-334`, `458-473`); owner and type codes (`57-58`); option and exercise handling (`209-211`,
  `234-243`); disclosure delay (`244-247`); the rules "fast, not early", "amounts are ranges", "owner matters", "say
  the delay", "options are options", "no return claims" (`trader-pelosi/SKILL.md:24-27, 47-58, 137-139`).
- **Must change.** Source = NewsWeb category 1102, mandatory notification of trade by primary insiders
  (`oslo-quant/docs/dashboard/data-sources.md:72`), from the list endpoint the dashboard already calls. New = a
  messageId not seen before; handle corrections through `correctionForMessageId`/`correctedByMessageId`
  (`data-sources.md:66-67`). Parse the notification (free text, often with a form attached) into person, role, buy or
  sell, shares, price, trade date and publication time; store only what D5 allows in the private cache. Count only
  market purchases and sales; keep exercises, exchanges and other non-market transfers apart, as the repo does for
  options and type E (`ptr.py:57, 240`; `test_pelosi.py:168-179`). Finanstilsynet net short positions: the repo has
  nothing for this.
- **Measurement since 2010.** The repo measures nothing. Use oslo-quant's signal-odds method
  (`signal_odds.yaml:1-7`) with the event at the NewsWeb publication time and entry at the next open after it – not
  the trade date, which is the repo's point about disclosure delay (`ptr.py:244-247`).
- **Pitfalls.** Page breaks split rows, columns run together, names wrap over lines (`test_pelosi.py:153-179`); the
  Clerk's XML has a BOM (`test_pelosi.py:64-71`): expect the same class of layout faults in Norwegian forms and test
  on real samples. The first run is limited to recent filings so it does not flood (`ptr.py:182-189`). Our own
  additions: the 64-stock universe is today's list (`signal_odds.yaml:4`), so a since-2010 study is survivor-biased;
  check how far back the NewsWeb API returns category 1102 (not verified in `data-sources.md`); several insiders buying
  on one day are one event, not several.

### Part 4 – position size in the judgement form
- **Relevant.** `size_trade` (`size.py:305-415`), `shares_for` (`275-280`), the account checks in `check.py:542-558`,
  the loss and reward:risk checks (`check.py:589-614`), the daily-loss rule (`check.py:615-621`), and the refusals in
  `exit.py:308-327`.
- **Method for oslo-quant.** Inputs: paper sum P, max loss L in NOK, the store's last close S with its date (D3),
  kill level K, target T. Shares = min(floor(L / (S − K)), floor(P × cap % / S), floor(free paper sum / S)), in whole
  shares and integer øre, naming the binding limit (`size.py:366-386`). The server rejects the judgement (HTTP 400,
  D3) when K ≥ S or T ≤ S for a BUY, when floor(L / (S − K)) = 0, and optionally when (T − S) / (S − K) is under a
  minimum R (`size.py:389-404`). Across the book: the sum of max losses at kill levels over all open BUY views must stay
  under a cap, as the repo counts every entry's full max loss in its daily limit (`check.py:615-621`;
  `trader-risk/SKILL.md:88-90`), and allocations are checked in order against the free paper sum (`check.py:663-683`).
- **Must change.** No "fresh price" logic: the price is the store's last close with its date. Sizing is fields on the
  judgement row, computed by the server like date and price, because the dashboard may write only judgement rows and
  watchlist entries (D2); it never steps a paper account. HOLD and SELL views get no size (the repo sizes longs only,
  `size.py:320-321`). The kill level is a review trigger, not a stop order, so "max loss at the kill level" is a floor,
  not a cap (`README.md:178-180`; `size.py:472`), and must be labelled that way.
- **Pitfalls.** Every limit can bind and the page must say which (`test_budget.py:164-171`). Zero shares is a plain
  refusal and nothing is written (`test_budget.py:148-162`). Use integer cents or `Decimal`, not floats
  (`size.py:275-280`; `exit.py:196-212`; raw Yahoo floats in `test_exit.py:61`). A higher price raises the risk and a
  lower one never shrinks it (`test_budget.py:173-183`, `test_risk.py:188-190`): if the form shows a newer price than
  the stored close, size from the stored close and show both dates.

## 6. What we do not take
- **Order execution** (`trader-broker`, the Alpaca/IBKR setup, `parse_yes`, fills, flatten): the dashboard never
  trades and never steps paper accounts (`DECISIONS.md:7-10`; D6 drops buy/sell buttons).
- **Intraday scanner and entry timer** (`scan.py orb`, `entry.py`), **intraday stop rules and flat-by**
  (`exit.py`): decisions are daily (D6 drops live quotes).
- **Price alerts on delayed quotes** (`alerts.py`): D7 already covers price-vs-case triggers on daily closes.
- **US data code**: Yahoo spark/v8 fetchers, Nasdaq universe, SEC feeds, House Clerk parser. oslo-quant has its own
  Yahoo recorders; Oslo has no XBRL; the PTR layout parser fits no Norwegian form.
- **NYSE calendars and the New York time code** copied into every tool (e.g. `check.py:94-125`), hard-coded to
  2026-27 with a warning outside those years (`check.py:221-223`). Oslo needs its own calendar.
- **Day-trade limits** (entry window, trades per day, PDT guard, Alpaca format checks) and the v1 **weights mode**
  (13F split, `size.py:490-681`).
- **The scanner's daily setups** as signals: unmeasured; oslo-quant shows only signals with measured odds (D11).
- **The plugin itself**: no install (section 2).

## 7. Copy or reimplement

Reimplement by default: the core of `simulate` must change (unit, conditioning, costs), and the sizing and check
logic is short. Two pieces may be worth copying with light edits:
- `facts.py:141-192` (`periods`, `quarterly`) and `facts.py:213-226` (`_yoy_match`, `pct`) – about 65 lines that
  handle restatements (latest value, first label) and derived Q4 for any list of `{start, end, val, filed, id}` facts.
  The form filter at `facts.py:149` must accept oslo-quant's own source tag instead of SEC form names.
- `timemachine.py:631-676` (`lean`, `verdict`, `verdict_notes`) – the break-even framing and its wording, about 45
  lines. Simple enough to rewrite; copy only if the wording is kept.

Any copied or adapted portion must ship with the MIT notice, in the copied file's header or in a third-party notice
file beside it: the line `Copyright (c) 2026 Jake Schincariol`, the full permission notice and disclaimer
(`LICENSE:1-21`), the source URL, commit `3d0f4ef` and the line ranges taken. oslo-quant is public on GitHub, so the
notice must be in the repository, not only on this machine.
