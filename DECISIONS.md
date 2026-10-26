# Decisions

Decisions behind the local Oslo Børs dashboard (`oq dashboard`). Each entry says what was decided and why, and
points to the evidence: `docs/dashboard/research.md` (what market products show and what analysts use; sources
S1–S61) and `docs/dashboard/data-sources.md` (free data sources, each fetched on 22 Oct 2026).

The fixed rules from the brief apply to every entry: the dashboard runs locally and starts with one command; it
reads data and never trades or steps a paper account (they keep running on GitHub Actions); the research book, every
written case and every judgement stay private; nothing is pushed without an explicit yes; every number shows its
source and time, delayed data is labelled delayed, estimates are labelled EST, and no number is made up.

## D1. Technology: Flask, server-rendered pages, on 127.0.0.1:8060

- Flask already ships with Dash, which oslo-quant uses for `oq ui`, so the dashboard adds no new web framework.
- Server-rendered HTML instead of a second Dash app, because:
  - the judgement form must be a plain POST that appends one row and redirects (no client state that could resend
    or edit a row);
  - the same render function writes the front page as a static file for the evening task (phase 3), so the page
    the Windows task opens and the page the server shows are the same code.
- Charts are Plotly figures rendered to HTML fragments. plotly.js is served from the installed `plotly` package, so
  the dashboard works offline and loads nothing from a CDN.
- Port 8060 (the existing `oq ui` uses 8050). Bound to 127.0.0.1 only: the pages show private files.
- `openpyxl` is added as a dependency to read the reverse-DCF block of the private case models (D7).

## D2. What the dashboard may write

Exactly two things, both append-only:

1. A judgement row in `~/osloquant-home/judgements.jsonl`, through `osloquant.judgements.append` (the SHA-256 hash
   chain from the analysis mission). If the company is not yet in the research book, one entry is appended to
   `researchbook.yaml`.
2. A watchlist entry in `~/osloquant-home/watchlist.yaml` (add, or mark "moved to the book" by the row number of
   the judgement that moved it).

There is no edit or delete route. A changed view is a new row. The dashboard imports nothing from the paper-account
code and has no route that fetches prices into the store.

## D3. The judgement form

- Required: view (BUY/HOLD/SELL), target price, rationale (at least 20 characters) and at least one kill criterion.
  The server rejects the row otherwise (HTTP 400 with the reasons) – the browser's `required` is a convenience, not
  the check.
- Date and price are not typed. The server takes today's date and the last close in the store, with the price's own
  date and source in the row, so a view cannot be backdated to a better price.
- Optional: horizon (default 12 months), bear/base/bull values and their probabilities. Probabilities must sum to
  1 when given (checked in `book.validate_form`).
- Evidence: Nordnet's private notes per stock [S11] are the closest consumer feature; the pro tools tie each alert
  to a log [S19][S30]. The difference here is structure: a dated, priced view with probabilities that the
  calibration report can score.

## D4. Pages read caches; the network is touched only by `--refresh`

- Feeds (announcements, rates, FX, salmon price, Brent, headlines) are fetched by `oq dashboard --refresh` (and the
  evening task in phase 3) into `~/osloquant-home/feeds/*.json`, each with `fetched_at`.
- A page never waits on a remote server, and a feed that fails keeps its old cache and says when it was fetched.
- Prices come from the oslo-quant store (Yahoo daily closes, delayed); the dashboard does not record prices.

## D5. Data sources (from data-sources.md)

| Need | Source used | Why this one |
|---|---|---|
| Company announcements | Oslo Børs NewsWeb JSON API, `POST .../newsreader/list` by date window | Verified, no key, real time. Terms allow private use only, so announcements stay in the private cache and are never published. Only title, time, category and a link to NewsWeb are stored. |
| Policy rate, 10-year yield, USD/NOK, EUR/NOK | Norges Bank SDMX (CSV) | Verified, NLOD 2.0, daily fixing (labelled "daily, not live"). |
| Salmon price | SSB table 03024 (export price, fresh, NOK/kg), PxWebApi v2 | Verified, CC BY 4.0. Labelled as a weekly **export price**, not the spot price. |
| Brent | Yahoo `BZ=F` daily close via yfinance | Verified, ~10 min delayed, already a dependency. FRED forbids caching; the EIA spreadsheet needs a new `.xls` dependency – kept as the fallback if Yahoo breaks. |
| Headlines | RSS from E24, DN, Finansavisen, NRK | Verified. Headline, link, time and outlet only – no description or article text is stored. |
| Freight rates | none | Baltic Exchange indices are licensed. The sector page says "not free" instead of showing a number. |
| Fish Pool salmon index and forwards | not used | The JSON works, but the units of the forward prices and the terms of use are unverified. |

## D6. Take and drop (from research.md, section 4)

- Built: the "needs a decision from you" list on top of the front page; own view against price (ladder of
  bear/DCF/TP/bull with the price); calibration page; events from the research book; announcements and headlines
  with links; technical signals with their measured odds; sector heatmap for the 64 stocks; watchlist with signal
  state and returns; single-stock page in the "describe, chart, news" order [S46], with the case below.
- Dropped: order book and live quotes (free data is delayed and decisions are daily), buy/sell buttons, social
  feeds, AI summaries, black-box scores (cannot be calibrated), consensus feeds and full-text news (licensed), a
  large screener (64 stocks fit in a table).
- Later: peer valuation, seasonality, insider trades / short positions / block trades as events.

## D7. "Dette krever en vurdering fra deg" – the rules

An item appears when (constants in `dashboard/today.py`):

| Rule | Trigger |
|---|---|
| Kill check | A research-book event (e.g. a quarterly report) happened in the last 3 days and no judgement or kill check has been logged since. Kill criteria are written fundamentals, so the dashboard cannot test them on prices; it asks for them on the dates where they can be tested. |
| Re-rate | The last close is at or through the target, the bear value or the bull value. |
| Re-assess | The price has moved 10 % or more since the view, towards or away from the target. |
| Risk signal | A RISK signal fired today on a research-book or watchlist stock (with the measured odds). |
| Stale view | The view is older than its horizon. |

"Kill criteria approaching" is shown as the report dates of the next 14 days with the number of criteria to check;
the reverse-DCF block (read from the private model) shows what the price implies against the case's own numbers.

## D8. Privacy

- Every private file lives in `~/osloquant-home`, outside the repository: `researchbook.yaml`, `judgements.jsonl`,
  `judgements-heads.txt`, `watchlist.yaml`, `feeds/`, `dashboard_state.json`, `signals/`, and the case models in the
  Toolkit repo's git-ignored files.
- The static front page is written to `~/osloquant-home/signals/latest.html`, never to `site/` (GitHub Pages).
- A test asserts that git tracks none of these names and that no tracked file contains the research-book tickers'
  private targets.

## D9. Labels

- Every price carries "Yahoo Finance via oslo-quant store (daily close, delayed)" and its date.
- Every feed value carries its source, the observation date and when it was fetched.
- Bear/base/bull values, probabilities and model values are the case's own estimates and are labelled EST.
- Signal odds are the store's own measured history (`oq signals score`), shown with the sample behind them.

## D10. Which headlines belong to a company

A headline is shown on a stock page when it names the company: whole words, case-sensitive, with a short alias
list where the press does not use the listed name (`NEWS_KEYS` in `dashboard/feeds.py`, e.g. "Norwegian" for
Norwegian Air Shuttle, "Lerøy" for Lerøy Seafood). The longer names of other companies are removed first, so
"Aker BP" is not news about Aker and "Odfjell Drilling" is not news about Odfjell. Checked on the 107 headlines in
the cache on 22 Oct 2026: 13 matched, all correct on reading. No text is matched beyond the headline itself.

## D11. Signal odds show their sample

Each signal badge shows the average excess return after 20 and 60 sessions, the hit rate and the number of past
signals behind them (`n`). Most hit rates are 45–48 %: the signals are close to a coin flip on this store's
history, and the page says so instead of hiding it.

## D12. The evening page is the dashboard's front page

`oq signals digest` (run by the "oslo-quant signals" task) writes the front page as `signals/latest.html`, with
the newest session's signals as "new", and the task opens it on a new session as before. Its links point at the
running dashboard. The task first runs `oq dashboard --refresh-only`, so announcements and drivers are current. If
the dashboard page fails for any reason, the classic signal page is written instead – the evening digest must never
be lost to a dashboard bug.

## D13. The Sunday summary

`oq book weekly` (task "oslo-quant weekly", Sundays 18:00 local time) writes `weekly/<year>-W<week>.md/.html`:

1. **Judgements that should have been made** – the front page's rules replayed at each session of the week with
   the view and prices of that day; an item counts as answered only by a judgement or kill check *dated* on or after
   it. Rows seeded from a written case keep the case's date, so they cannot answer later events.
2. **Judgements logged** this week, and whether the log's chain verifies.
3. **What changed** – the research book's week, sector medians, the five biggest moves each way, signal counts and
   the signals on followed stocks, and the week's announcements for followed companies.

It lists what was missed; it does not grade the judgements. The calibration page and the market do that.

## D14. The Day Trader skill: read, not installed; ideas taken, code reimplemented

The skill pack (github.com/Jakeschincariol/day-trader-skill, commit 3d0f4ef, MIT) was read in full and never run,
installed or given keys. `docs/dashboard/day-trader-vurdering.md` says what each of its 11 skills does, the safety
review (HTTPS GETs only; no tool can place an order, but one skill steers Claude toward an outside broker tool) and
what fits long-term cases on Oslo Børs. Taken as ideas: the Time Machine's question and output (target first, stop
first, neither; simulated and historical counts side by side; break-even share 1/(1+R)), the analyst's comparisons
(previous quarter, same quarter last year, what is derived), the insider pipeline's shape, and the budget/risk sizing
(minimum of several limits, the binding limit named, zero shares is a refusal). Not taken: order execution, the
intraday scanner and entry timer, delayed-quote alerts, US data code. No code is copied, so no MIT notice is needed;
if a later change copies any, the notice ships with it.

## D15. Outcome odds: target first, kill level first, or neither

On the stock page of every research-book company (`dashboard/odds.py`), for 3, 6 and 12 months:

- **Simulation:** 10,000 paths from the stock's own daily log returns since 2010 (or its listing), resampled in
  blocks of 20 sessions so calm and volatile spells stay together, with a fixed seed. The Day Trader skill draws single
  5-minute bars by time of day; over months that would lose volatility clustering, so the unit changed. The sample's
  own drift stays in and is printed, with its volatility and today's.
- **Historical cases:** every month-start since 2010 on all 64 stocks, with the target and kill level at the same
  distances measured in each stock's volatility at the time; and the stock's own history at the same percentage
  distances. Windows overlap, so the page prints the approximate number of independent cases (n x 21 / horizon).
- **Rule:** a level counts when a daily close reaches it; adjusted closes (dividends reinvested); today's bar is left
  out until the session has closed (16:40 Oslo).
- **Break-even:** R = distance to target / distance to kill level; the target must come first in 1/(1+R) of the
  decided cases. The page compares the simulation's share with that, in the skill's words for the gap
  (coin flip under 5 points, leans 5–15, clearly over 15).
- **Kill level:** a price field in the judgement form (`kill_level`, stored in the log row; below the price for a BUY,
  above for a SELL). A view without one uses its bear value as a stand-in, and the page says so in the heading.
- **Signals:** each signal as a trade – entry at the next open, target = entry x (1 + 0.5 %) + R, stop = entry - R,
  R = 2 x ATR(20) – measured over the same period as the existing odds (2010 to 19 Oct 2026) and added to
  `signal_odds.yaml` under `bracket` without touching the existing numbers (`oq signals brackets --write`). Shown
  under each active signal and as a table on the calibration page. Result: after costs every signal's average is
  within ±0.07 R of zero at 20 and 60 sessions – the same finding as D11, now in trade terms.
- A reality check, not a forecast: the page says so above the table. Reports, rates and news can do what the history
  never did; survivorship (today's 64 stocks) flatters the historical cases.

## D16. Frozen real data for deterministic tests

Tests that must give the same answer every time run on a frozen copy of real data – the store's prices to
22 Oct 2026, and later the insider and short caches and the report PDFs – in `~/osloquant-home/testdata/2026-10-22`
(`oq freeze-testdata`). It stays outside the repository: Yahoo's prices and NewsWeb's texts are for private use.
Those tests skip where the copy is absent (CI); synthetic tests cover the same code everywhere. One of them checks that
the committed `signal_odds.yaml` brackets reproduce exactly from the frozen prices.

## D17. Quarterly reports: read, compared, kill criteria marked – no generated text

When a research-book company publishes a quarterly report on NewsWeb (a message with a report PDF and a quarter in the
title; SATS files them as "half year financial report"), `oq dashboard --refresh` – and so the evening task –
downloads the PDF to `~/osloquant-home/reports/<code>/` and reads it (`dashboard/reports.py`, `pypdf` added):

- **What is read** is configured per company in the private `~/osloquant-home/reports.yaml`: rows of the key-figure
  table (quarter, year-ago quarter, change, YTD, YTD a year ago, change) and of the income statement (one number per
  column of its header). Numbers use spaces as thousands separators; each key-figure row is split so the printed
  change matches, and marked ✓ when it does. Note references before income-statement numbers are skipped.
- **Compared** with the previous quarter's report, the same quarter a year earlier (from the report), the consensus
  the company publishes before the report (SATS: compiled by Modular Finance on its behalf, released through MFN;
  public), and the case model's numbers for the report's year (EST). Last-twelve-month figures: last full year +
  year to date − the same period a year earlier.
- **Kill criteria:** those with a measurable threshold get a rule in `reports.yaml` (metric, operator, value) and are
  marked triggered, intact-nearer, intact-further or unchanged against the previous report; the others are listed as
  "not machine-checkable: read the report". A report read in the last 21 days with a criterion triggered or nearer,
  and no judgement or kill check dated after it, goes to "Dette krever en vurdering fra deg".
- **No text is generated.** The research dropped AI summaries (D6) because an unverifiable summary weakens the log;
  this is a table of read numbers with their page, the formulas, and links to the announcement and the PDF.
- Tested on SATS's last four reports (Q3 2025 – Q2 2026): every key figure matched its printed change. The test on
  SATS's Q3 2026 report (27 Oct 2026) runs as a one-off scheduled task that morning.

## D18. Primary insiders and short positions

- **Insiders:** every NewsWeb notification in category 1102 for the 64 stocks since 2010 (8,433), fetched once
  (`oq insiders backfill`, about 1.5 hours at one request at a time with a pause) and then the current year at each
  `--refresh`. The text decides the type – company, programme, other, subscription, buy, sell or unknown, in that
  order, with the deciding word shown on the page. A random sample was checked by hand (`docs/dashboard/insider-study.md`).
  Private cache only (NewsWeb's terms).
- **Shorts:** Finanstilsynet's short sale register has an open API (`ssr.finanstilsynet.no/api/v2/instruments`):
  public positions of 0.5 % or more, daily, the last two years, per holder. Its issuer names were matched by hand to
  37 of the 64 stocks (`SSR_NAMES`). A first fuzzy match got OKEA and Aker wrong, so no fuzzy matching. The others had
  no public position in the window. The register states no licence terms on its pages; it is public disclosure data,
  kept in the private cache.
- **Pages:** the stock page lists the last 12 months of notifications (with type and deciding word) and the short
  position with its history and holders. The front page lists insider buys, sells and subscriptions, and short moves
  of 0.25 points or more, in followed stocks over the last seven days.
- **The study** (`oq insiders study`): one event per stock and day, entry at the next open after publication, excess
  return against the equal-weighted 64 stocks, monthly-clustered t. The answer is written plainly: the typical insider
  buy was followed by a below-median return, and the positive average rests on a few large winners and on
  survivorship. The 60-day line is shown on the stock page as context, never as a signal.

## D19. Position size in the judgement form

For a BUY view the form computes a paper position with the kill level as the stop (`dashboard/sizing.py`), the Day
Trader skill's budget method moved to long-term views:

- shares = the smallest of: max loss / loss per share, paper sum x max position / price, free paper sum / price, and
  (if set) what is left of a total loss cap across all open BUY views / loss per share. Loss per share = price − kill
  level + the 0.5 % round trip. The binding limit is named in the form and stored in the row.
- The limits are Oscar's, in the private `~/osloquant-home/dashboard.yaml`. The paper sum is the NOK 100,000 each
  paper account starts with (`live.yaml`); max loss (NOK 2,000) and max position (25 %) were set by Claude as starting
  values and are marked so in the file. Without the file there is no sizing and no block.
- The form shows the largest allowed size, the position's value and share of the paper sum, and the loss if the kill
  level is reached, as the kill level and the size are typed; the server checks again on submit and refuses a
  position whose loss at the kill level is over the limit (or over the cap, the free sum or the total cap) – nothing is
  written. With a sizing config, a BUY needs a kill level; HOLD and SELL get no size.
- The row stores `position_shares`, `position_value`, `loss_at_kill` and the limits used. Open positions (the newest
  BUY row per stock) reduce the free paper sum for the next one.
- The loss at the kill level is a floor, not a cap: a report or a gap can open the price below it. The form says so.
- Paper only: nothing is bought, and no paper account is stepped.
