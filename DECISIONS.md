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

## D20. Signal odds carry their own doubt (night of 1–2 Nov 2026)

The audit (`docs/natt/revisjon.md`) found three things the pooled odds hid: the t-statistics treated clustered events
as independent (naive t 3.9–4.0 on the 60-day breakouts, 1.3–2.1 with one mean per month); the odds differ by period
(the 20-day breakout excess was +0.9 % in 2010–2017 and about zero after); and the universe is today's survivors
(equal-weighted it returned 19.5 %/yr against 11.6 %/yr for OSEBX, 2013–2026). So:

- `scorecard()` adds `tc10/tc20/tc60`: t with one observation per calendar month. `robustness()` measures each
  signal on the two halves (split 1 Jan 2018), on the stocks listed by 1 Jan 2011 (43 of 64), and gives a verdict:
  "holds in both halves" when both halves have the sign of the pooled 60-day excess and |tc60| ≥ 2;
  "period-dependent" when the halves disagree in sign; otherwise "weak". Three signals hold (Breakout 20d,
  Rising channel entry, Falling channel entry); three are period-dependent (Golden cross, Breakdown below 60d low,
  Drawdown 10 %); three are weak.
- The odds file keeps all of it under `robustness`, and `write_odds` preserves the `bracket` results instead of
  dropping them. The file is measured on the frozen test prices to 19 Oct 2026 (`oq signals score --frozen --end
  2026-10-19 --write`), so a test reproduces every number in it; the live store had already drifted by one event.
- Every signal on the dashboard shows one more line: the excess in both halves, on the survivors-from-the-start,
  the clustered t and the verdict, with "only today's 64 stocks (survivors)". The public scorecard page gets the
  same columns. A pooled number is never shown alone again.

## D21. Calibration against references, and probability against outcome

A call is only good relative to something. Each scored judgement now carries three references (`judgements.score`):
OSEBX (direction and excess, as before); **"the price stays where it is"** – did my target miss the later price by
less than a forecast of no change (`beat_flat`); and **the public consensus target** when one was logged with the view
(`consensus_target` + `consensus_source`, entered by hand from a public page because consensus feeds are licensed;
the form refuses a target without its source and date). The calibration page shows the three hit rates for final
calls and for all scored calls, with the counts.

`judgements.reliability()` turns every final call with scenario probabilities into three (stated probability,
happened) pairs – bear, base, bull – buckets them by the stated probability and plots stated against realised with
the binary Brier score. Until the first horizon has passed the page says how many calls are pending and shows no
plot: nothing is calibrated against nothing. Below 20 final calls the page says the plot is noise.

Found on the way: the calibration page crashed when every call was logged today (no price after the call yet). Fixed.

## D22. Before the report: the view goes on record first, and a dead criterion is not logged unknowingly

- **Pre-report item.** A research-book report date within 10 days with no judgement dated in the 30 days before it
  puts "log your view before the report" on top of the front page (`today.pre_report_items`). A view logged after the
  numbers is scored with hindsight; the calibration is only worth something if the view came first.
- **Dry run of the report reader** (`oq reports dryrun CODE file.pdf --period 2026Q2`): what the spec finds, what it
  misses, and for each missing row the lines in the PDF that might be it. For a company that has never reported as a
  listed company there is no previous report on NewsWeb to test on; the dry run is how the spec is written from any
  PDF the company has published (prospectus, an older interim) before the first real one.
- **Inception check.** A BUY view on a company whose latest report reading already marks a kill criterion as
  triggered is refused unless the box "I know" is ticked; the row then carries `triggered_at_entry` and the history
  shows it. The case review found a criterion that had read "triggered" in every reading since the case was written,
  with no check logged: a criterion that is already dead when the view is logged is either not a kill criterion or
  not a BUY, and the log should say which the author chose. HOLD and SELL need no acknowledgement.

## D23. The statistics behind the odds were wrong in kind; corrected

The quant review (`docs/natt/ideer-kvant.md`) found that both yaml files printed a t-statistic of the mean of
monthly means next to an event-weighted mean – a statistic of a different number, inflated by thin months (insider
buys, 60 sessions: t 2.41 shown for a +0.70 % mean whose own cluster-robust t is 0.72). Corrected as follows:

- **One t:** `signals.cluster_t` – the event-weighted mean over a two-way cluster-robust standard error
  (Cameron–Gelbach–Miller: time blocks of ceil(h/21) months, stock, minus the intersection). Used for `tc10/20/60` in
  `scorecard` and for `t_cluster` in the insider study. The naive `t20` stays in the file, labelled naive.
- **An interval on every number:** `signals.boot_ci` – month-block bootstrap of the event-weighted mean, 2,000
  resamples, fixed seed; `lo/hi` per horizon in both files and on every badge.
- **Three sub-periods** (2010–15, 2016–20, 2021–26) instead of two halves, and the survivors-from-the-start column.
- **The dominant stock:** the share of the summed excess one stock carries (`top60`, `topshare60`); for insiders the
  two largest stocks' share, the trimmed and winsorised means and one vote per stock.
- **A grade A–D per signal and horizon** from three checks that can be run tonight – same sign in all three periods,
  interval excludes zero, no stock carries a third of the sum – with the fourth (a two-way placebo band, idea 8 in
  `ideer.md`) marked "not run". On the frozen data to 19 Oct 2026, at 60 sessions: Breakout 60d A, Breakout 20d A,
  Rising channel B, the rest C or D; at 20 sessions only the death cross is A (a −0.5 % effect). "Risk signals carry
  more information" is withdrawn as a general claim: the breakdown signal's −0.9 % is −4.7 % in 2010–15 and +1.0 %
  in 2021–26.
- **Chips are grey** unless the grade is A and (for buys) the raw 20-day return beat the round trip. Colour must not
  say more than the odds do.
- `_edge` no longer fires on the first day an indicator exists (98 phantom entries in the channel and drawdown
  signals). Event counts changed slightly; the brackets were re-measured.
- `docs/dashboard/insider-study.md` carries a correction section and the new table. Both files are regenerated from
  the frozen data (`--frozen`), and the tests reproduce every number.

## D24. The front page for a five-minute visit

The student read (`docs/natt/ideer-student.md`) found the count clear and the order, time and data date not. Now:
the heading shows today's date and, under it, the date of the newest close; an amber banner says when that close is
older than the last weekday (run `oq record`). The decision card opens with "N ting, omtrent M minutter, i denne
rekkefølgen" and numbers the items with "Gjør først / I dag / Kan vente" and a minute estimate per kind (fixed
guesses, to be replaced by measured times). With nothing to decide it says so and names the next date. Signals on
research-book stocks stay open; the rest fold behind one line. The report item's criterion text is no longer cut
at 60 characters. The "static snapshot" note moved to the footer.

## D25. A data-health page, and the dividend audit as a command

`/health` ("Datahelse", `dashboard/datahealth.py`) shows, before any number is read: the store's newest dates per
table; every stock without a close on the newest session, its missing sessions in the last 250, gaps of 20 sessions
or more (Borr Drilling's 2025 source gap shows here) and daily moves of 25 % or more in the last 60 sessions; each
feed's age against a limit (announcements and news 3 days, rates, FX, Brent, shorts and insiders 7, salmon 14);
the report reader's state per case (spec, latest report, rows not found, kill rules against kill texts); the
judgement log's chain and recorded heads; whether the frozen test data is present; and the dividend audit. The
warning box at the top is also `oq data health` for the terminal.

The audit (`oq data audit`) matches every NewsWeb ex-dividend notice since 2010 against Yahoo's adjustment factor
and caches the result in the private feed folder, because it costs one NewsWeb request per stock; the page shows
when it was last run. The night audit found 29 notices with no adjustment (Bouvet 2010–15, Mowi 2015–17, Wilh.
Wilhelmsen, Aker, Kid, Grieg, Protector, TGS) – a dividend Yahoo missed looks like a price fall, fires false risk
signals and understates that stock-year's return. Nothing can repair Yahoo's series; knowing which stock-years are
affected is the honest substitute.

## D26. A calendar from the issuers' own announcements

Report dates come from the "Financial calendar" messages the issuers file on NewsWeb ("DD.MM.YYYY - Quarterly
Report - Q3"), fetched for research-book and watched companies at each refresh (two requests per company) and parsed
into dates; the research book's own events stay the primary list and a date both have is shown once with a note.
Norges Bank's decision dates live in a resource file with the page they were read from and the day – one date was
verifiable tonight (5 Nov 2026), so the file holds one date and the page says the rest must be added from the
official calendar. Ex-dividend dates are left out: NewsWeb announces them on the day and the advance notices have no
fixed form; guessing them would be worse than not listing them. The front page's "Kommende datoer" draws from the
same list.

## D27. The book as one thing: shared kill drivers and sector concentration

The per-view loss limit (D19) treats two views as independent. With two consumer-discretionary BUYs whose kill
criteria both start with a margin line, that is not true: one bad quarter for Norwegian retail spending can kill
both, and the loss at the kill levels adds up. The front page now has a block under the research-book table that
sums the loss at kill per sector group and per kill driver, and says in words when every open BUY sits in one
group or when two views can die from the same driver. The driver of a kill criterion is read from an explicit tag
at the end of the line (`... below 30% [margin]`) or, without one, inferred from its words and marked with a star
so the author can overrule it – inference is a hint, never a verdict. The sizing gets an optional
`max_loss_per_group` (NOK) across open BUY views in the same sector group, applied like `max_total_loss`; the
default config writes it as 3000 against a 6000 total, which Oscar should set himself. Nothing here changes a
rating; it changes what the size form allows and what the morning visit sees.

## D28. The fourth grade check: a two-way placebo band

D23 left the grade at three checks and said so. The quant review built the missing one and found that the obvious
placebo – random days in the same stock-months as the real signal – is not a null: a month in which a stock broke
out is a month in which it rallied, and a random day in it inherits the rally. The placebo that is fair to the
signal keeps its stock mix and its month mix but not the day: the signal's count is spread over stock-months in
proportion to its month totals times its stock totals (a multinomial draw), and random traded sessions are drawn in
each cell. `placebo_band` does that `PLACEBO_N` = 200 times per signal with a fixed seed and scores each frame
exactly like the scorecard's mean excess; the fourth check passes when the real mean lies beyond the 95 % band on
its own side. 200 draws, not the review's 500: the band's edges move by less than the rounding at 200 and the
committed file has to reproduce in the test suite in about a minute and a half. The check is optional in the code
(`robustness(..., placebo=None)` still says "not run"), on by default in `oq signals score`, and written into the
odds file with its design, count and seed. The dashboard's grade words now count the checks that ran, and the signal
line says whether the stocks and months already explain the number.

## D29. A view older than the last report is not the view

D22 asks for a view *before* a report. The other half was missing: once the report is out, the view on record was
formed without its numbers, and the calibration keeps scoring that pre-report view as if it were current. The
front page now raises a "post-report" item when a report has passed in the last 45 days – one the reader summarised,
or a research-book event with report words, so it works for a company without a reader spec – and no *judgement* is
dated on or after it (a kill check is not a view). The research-book table marks such a view with "før rapporten
DD Mon". A code with a post-report item drops its "moved 10 %" re-assess item, because the post-report item asks for
the same act with the better reason. Nothing is written automatically: the re-assessment is Oscar's, and "unchanged"
is a valid answer once it is logged with the report in hand.

## D30. Template marks across the open views

Two companies at different prices with the same target, the same scenario probabilities, or the same bull/bear
spread around the target say more about the spreadsheet than about the companies. The calibration page now lists
such repeats across the open views (`jg.fingerprint`), as a question for the next view rather than an error: a
shared number can be a coincidence, but it should be one the author has noticed. It reads only the views; nothing is
written. Norges Bank's calendar (D26) was re-read on 2 Nov from the policy-rate-decisions page, which lists the full
published schedule – ten dates through December 2027 – so the resource file now holds all of them.

## D31. Two analysts: Oscar and Claude, scored apart

Oscar wants many companies to follow, not two. Writing ten views himself at once would make them thin; having Claude
write them into his log would make the calibration measure Claude. So the log gets a second analyst. A row's
`analyst` field says whose it is; a row without it is Oscar's, so no existing row changes and the hash chain holds.
Everything that sizes, warns, nags or counts as "the research book's view" stays Oscar's: `latest_by_code()` and
`Case.view` read his rows only, the pre-report and post-report items skip companies only Claude covers, the reader
warnings on the data-health page are for his cases. Claude's newest view sits on the case as `claude_view`.

The calibration's headline numbers are Oscar's. Claude's are scored the same way under `by_analyst`, the two are put
side by side on the companies both cover (`head_to_head`), and Oscar's views on those companies are split by the
answer to a required question in the form – had he read Claude's view before writing? – into blind and anchored.
Claude's view is folded on the stock page so it can be read after, not before.

Claude's views come from a light case (`oq case build`): the store's Yahoo statements, the reporting currency from
Yahoo's quote summary (cached once per stock), FX from the store, LTM figures where four consecutive quarters exist,
multiples against the sector group's medians computed the same way, and one line on what the price asks for – the
value-driver formula solved for growth for operating companies, the justified P/B solved for ROE for banks and
insurers. The cost of capital per sector group and the long-run growth are round numbers marked EST. A case says
when Yahoo's quarters lag the newest report, when net debt is missing, when a currency has no NOK rate. Claude also
reads the company's own latest report announcement on NewsWeb before writing; the figures quoted in a view come
from there or from the case, never from memory.

Claude's ratings follow one rule: BUY when the 12-month target is 10 % or more above the price, SELL when it is 10 %
or more below, HOLD between. The first ten (2 Nov 2026): EQNR, AKRBP, MOWI, DNB, GJF, FRO, KOG, YAR, NOD, ORK –
eight sector groups. SUBC was dropped before logging: its merger with Saipem is close to completion and the share
may stop trading in Oslo inside the horizon, which would leave the view unscorable.

## D32. The pages look like a research front page, not an app

Oscar put a Capital IQ profile and a DNB Markets note side by side with the dashboard and asked for the same ease:
one light theme, dense but legible, every block with a heading and a source line. So: one theme (light; the
automatic dark mode is gone – it made screenshots and the real screen disagree), a teal rule under every section
heading, thin lines instead of cards, tabular numbers, and the stock page laid out as a note's first page – the
name and the thesis on the left, the view large on the right ("BUY · TP: NOK 54 (+23 %)") with the summary facts,
the capital structure from the light case and the next event; under the chart the investment case in three columns
(downside = the kill criteria, our view, upside = the bull value), then key figures with years as columns and LTM
last. The chart draws the cone from the last close to the view's bear, target and bull at the end of the horizon,
as the note does. Two things the note has that the page does not: estimates by year – we show history and LTM only
and never invent an "e" column – and consensus, which is licensed; the consensus target stays a field Oscar fills
in by hand with its source. The right rail shows Oscar's view only; Claude's stays folded below (D31).

## D33. Model portfolios: built on the frontier, judged out of sample, tracked as paper funds

Oscar asked for portfolios put together on risk-adjusted return – the efficient frontier and the capital market
line – as "almost funds", and for them to be judged. Three things are kept apart on the page because they are
different kinds of knowledge. (1) What a portfolio *is* today: weights and the expected return, volatility and
Sharpe on the inputs, marked EST – the inputs are three years of daily history (means shrunk towards the
cross-section, covariance shrunk by Ledoit–Wolf, no stock above 15 %) or the views' targets. (2) How the *recipe*
did out of sample: rebuilt at every month end from trailing data only, held a month, 0.25 % on turnover, five
years, against equal weight and OSEBX, with a monthly block-bootstrap interval on the Sharpe difference. On the
first build (2 Nov 2026) no optimised recipe is distinguishable from equal weight; maximum Sharpe is ahead on the
point estimate and minimum variance behind, both inside wide intervals. (3) How each *fund* does from the day its
weights were written: a paper NAV from the recorded weights and the store's closes, append-only in
`~/osloquant-home/funds/`, compared with equal weight and OSEBX over the same days.

The reference is equal weight, not OSEBX: the universe is today's stocks, and survivorship alone made equal weight
beat the index by about eight points a year in the test period. The risk-free rate is Norges Bank's policy rate
from the rates feed. The view-weighted funds (Claude's, and Oscar's once he has three views) cannot be backtested
and say so; they exist to be judged forward. `oq funds build` recomputes and caches; `--write` records a rebalance.
Nothing trades; paper money.

## D34. Research reports on the stock page, and a report is not a decision

The Equity Research Toolkit now writes a full report per company and edition; its builder copies the PDF, the
estimates snapshot and a meta file into `~/osloquant-home/cases/reports_pdf/<CODE>/` (private). The stock page
lists the editions (date, kind, rating, target, DCF value, price and date, pages, whether the build gate passed)
and opens the PDF from the dashboard; with two editions it shows the latest estimates against the previous ones,
line by line. A report's target does **not** change the research book: when the newest report is dated after the
view and its target or rating differs, the front page lists it as a decision ("report-tp") until a judgement is
logged on or after the report date – also a judgement that keeps the old target. Reason: the model is an input;
the judgement log must record that Oscar chose, not that a build happened. Rapporter 2026-11-02, part 1.

## D35. «Før du kjøper»: one page before the form, numbers and quotes only

A page per stock (`/stock/<code>/pretrade`) that collects, in this order, what the market prices in against the
view (the toolkit model's reverse DCF, the light case's implied growth), the outcome odds at 3, 6 and 12 months,
the scenarios with the strongest arguments against buying, the dated events before the horizon, the position size
at the maximum loss with the exposure already in the same sector group, and a four-point checklist. Nothing on it is
written for the occasion: every line is a number from a named source or a quotation from the case, the latest
report reading, Claude's view, the light case or a risk signal, in a fixed order of strength (a kill criterion over
the line first, the case's own bear value last). The checklist gates the link to the form in the browser only – a
view can still be logged without it, but the ticks are written on the row (`checklist`), so the calibration can
later split views with and without the page. Rapporter 2026-11-02, part 2.

## D36. Learning blocks: per-case Brier and an error-pattern report built from rules

The calibration page gets the Brier score and the stated-probability-against-outcome points per case, and a
report of error patterns: for every scored call, rules on the log and the price path say whether it was early (a
drawdown of 15 % or more against the call first), late out (the kill level crossed with no judgement or check
within ten sessions), a kill criterion ignored (breached and held), never checked (90 days without a kill check),
anchored to guidance (a word match in the rationale, labelled as a question) or herded (target within 5 % of a
logged consensus). The counts are shown among the wrong calls and among all calls. With two of Oscar's rows the
report is a structure, not a finding; it is built now so that the rows accumulate against it. Nothing in it reads
the text beyond the labelled word match. Rapporter 2026-11-02, part 3.

## D37. Data health names the disagreements between sources per case

The data-health page adds a table per research-book case: the age of the view, the light case's build date and
its price against the store's last close, the newest report's date and target, the model file's date, and the
issues in words – a report target that differs from the view, a report dated after the view with no new
judgement, a model file older than the newest report, a light case built at a price more than 10 % from today's,
no coming date in the book. The front-page problem list carries them. The rule: no number is read off one source
without knowing that another source says something else. Rapporter 2026-11-02, part 4.

## D38. The coverage universe: a level per company, derived from the files; the plan typed in

Every company in the store is on the coverage page, at the level it is actually covered at: *full* when a research
report has been published to the dashboard (`cases/reports_pdf/<CODE>/`) or the research book names a model file,
*light* when a light case exists, *watch* when it is only on the watchlist, *none* otherwise. The level is never typed
in – it is read off what exists, so the page cannot claim coverage that is not there. The views are shown
separately from the level: a full case with no logged row is shown as exactly that. The one thing typed in is the
plan (`~/osloquant-home/coverage.yaml`, written by `oq coverage set`): the level a company should be at, who owns
the view (oscar, claude, both) and the rhythm (after every report, monthly, quarterly, at an event). The page and
`oq coverage` show, per sector group, how many companies the store holds, how many sit at each level, how many have
a view, how many are below their planned level and how many light cases are stale (older than 120 days or built
before the newest report). The front page carries the same counts in one line. Dekning 2026-11-03, part 1.

## D39. After the report: the numbers are refreshed and the view is queued, for every covered company

A report changes the numbers under a view; until now only SATS had a reader spec, and only Oscar's views were asked
for again (D29). The loop `oq case after-report` does, for any covered company: re-record the statements and rebuild
the light case keeping before and after (price, LTM revenue, EBIT and net income, EV/EBIT, P/E, what the price pays
for, the quarter the statements reach); fetch the newest quarterly report from NewsWeb; read it with the company's
spec when there is one, otherwise dry-run a generic spec (revenue, EBITDA, EBIT, net debt, the income statement) and
write a suggested spec to `cases/specs/<CODE>.suggested.yaml`, so the next quarter can be machine-read. The result is
written to `cases/afterreport/<CODE>.json` and shown on the stock page as "Etter rapporten". The queue is derived,
never stored: a company is due when its newest report – the reader's summary, a downloaded report, a research-book
event or the issuer's financial calendar, whichever is newest, with its source named – is newer than its light case
or than an analyst's view. Oscar's items reach the front page through D29 (a downloaded report now counts as a
report there too); Claude's are listed on the coverage page only (D31). Nothing in the loop writes a judgement: the
analyst who owes the view logs it. Dekning 2026-11-03, part 2.

## D40. One kill list per case: the model's, published with the report; the dashboard names where the copies diverge

A case's kill criteria lived in three places that drifted apart: the Toolkit data module (`KILL`, workbook rows with
thresholds, and from now `KILL_TEXT` for criteria the rows cannot carry), the sentences on the judgement row, and the
reader's rules in `reports.yaml`. The model's list is the source: the Toolkit exports it with every report's estimates
(`kill`: rows, text, source), and `dashboard/killlist.py` compares the other two copies with it – by the numbers
(the threshold must appear in the sentence) and the words of the label, never by guessing. It names a model criterion
with no sentence in the view, a sentence with no model line behind it, a reader rule whose index points past the
view's list or whose threshold differs from the model's, and the model criteria no rule checks. The result stands
under the kill list on the stock page ("én liste" or "spriker"), in the case's data-health issues and in
`oq book check` (with `--stub` drafting the reader rules from the model's list). Nothing is rewritten: the log is
append-only, the yaml is Oscar's, and a diverging list is fixed in the data module and then re-logged as a view.
First run (3 Nov 2026): the SATS view of 6 Oct carries three sentences, the model five criteria, and the reader's
ARPM threshold is not the model's price/mix threshold – ten divergences, now on the page. Claude's
list is compared too but reported as "two analysts, two lists", not as an error. Dekning 2026-11-03, part 4
(the Toolkit side: `kill_list_of` in rb_data.py, `KILL_TEXT` in elkem_data.py).

## D41. The desk: six roles through a stock before the judgement, every point with a number, never a buy

A six-bot "trading desk" from social media gave the structure: one job per role, hard hand-offs, an obligatory
counter-argument, a log of everything. The content – memecoins, intraday, orders placed by the bots – was not taken,
and neither was a language model: every role in `dashboard/desk.py` is a set of rules over data the dashboard already
holds (the store's prices, the signals with their measured odds, NewsWeb announcements and insider notifications,
Finanstilsynet's short register, the report reader, the research book and the judgement log, the toolkit model's
reverse DCF, the light cases, the calibration page's error patterns). No new source, no key, no fetch: a run reads the
caches and the store and reproduces for a given close.

- **A role never writes free text.** Its output is a list of findings; a finding is a fixed claim (`CLAIMS`, the only
  sentences a role can make), a value that must carry a number, a source and the time of the data, and is refused
  without any of them. Estimates are marked EST, cached and delayed data are marked. A finding may quote a source (a
  criterion's sentence, an announcement's title) – a quotation, never prose. The same rule as the pretrade page (D35),
  now enforced by the data class.
- **The roles, in order:** Scout (every stock: volume against its 60-session average, the day's move against the
  sector group's median, a signal today, a new announcement, an insider notification, a move in the short register);
  Filter (kills: no case and not watched, median turnover below the limit, a report inside five days with the previous
  one not dealt with, a kill criterion already triggered in the latest reading, the price through the view's kill
  level); Analyst (the market's implied margin and growth from the reverse DCF against the view, the light case's
  implied growth, the newest toolkit report against the book, the outcome odds at 3/6/12 months with break-even on the
  decided paths, the latest report's kill rows and LTM against the case, the distance to target and kill level);
  Bear (reasons against buying, strongest first, one per kind, each with a number: a kill criterion nearer in the
  report, a metric down year on year, Claude's lower view, what the light case says the price requires, a multiple
  above the group, odds below break-even, a risk signal with its interval and grade, a public short, insider sells in
  the window, same-group exposure and shared kill drivers in the paper book, the calibration's most common error
  pattern, the view's own bear value); Reply (one rule per reason: expected value with the view's own probabilities,
  distance to the threshold as a share of it, LTM against the case's estimate, shared drivers, the pattern against the
  situation now, the signal's grade and interval, the short's 30-day direction, buys against sells, the full model's
  reverse DCF or DCF value against the light case – each either rebuts with numbers or stands); Risk (the position at
  the maximum loss with the kill level as the stop, the group's share of the paper sum after the buy, the group and
  total loss at the kill levels, the dated events before the horizon – blocks over the limits).
- **Hard hand-offs.** Fewer than three bear reasons with numbers stop the chain, and the chain checks this itself, not
  only the bear. One reason that stands is a veto. Risk blocks over the limits in `dashboard.yaml` (`sizing`, and a
  `desk:` section whose defaults are in `desk.DEFAULTS`: volume 2x, move 3 pp, turnover NOK 2m, report within 5 days,
  group share 50 %, veto window 60 sessions). Without sizing limits Risk cannot size and blocks – nothing is ready
  until the limits are Oscar's.
- **Three end states and no fourth.** *Klar for vurdering* opens the judgement form prefilled from the view and the
  Risk role, with the debate attached and the run id written on the row (`desk_run`, a new optional field; old rows are
  untouched, the chain holds); *parkert* with the veto or the block visible; *drept* with the filter's reason. The
  decision stays Oscar's: a parked or killed stock can still be judged, and the form then carries the log and the
  reason. Nothing in the desk writes a judgement, an order or a watchlist entry; the one new write is the run log
  itself, append-only under `~/osloquant-home/desk/` (private; `desk/` is added to the privacy test), the third thing
  the dashboard may write after D2's two.
- **The page.** `/desk`: today's run (scanned, flagged, killed, debated, parked, ready; time; the share the filter
  killed against the 90 % the brief asks for; data quality per source), the stocks with the deciding finding, a run
  button for one stock, the veto statistic, the earlier runs. The debate log per stock is chronological with role,
  claim, number, source and data time, EST and delayed marks, and status – and opens from the stock page and from the
  judgement row. The daily run is a step in the signal-watch task (`oq desk run --daily` before the digest), so the
  front page and the evening file carry "Desk i dag".
- **The only number that decides whether the desk is worth anything** is kept honestly (`veto_stats`): for every veto,
  did the price reach the kill level before the target within the window (first daily close, adjusted, as the odds) –
  right, wrong, neither, pending, unscorable – beside the same count for the stocks the desk let through. A veto on a
  stock without a target or kill level is unscorable and says so. The page prints the verdict in words even when the
  vetoes have not helped.
- Tested on synthetic SATS, OUTLT and ELK with fictional numbers (`tests/test_desk.py`): the chain never ends in a buy
  and leaves the log, the book and the watchlist byte-identical; the bear gets nothing through with fewer than three
  numbered reasons, also when a patched bear hands over two; no finding without a claim from the table, a number, a
  source and a time; the filter, the veto and the Risk block each end the chain with the reason visible; runs
  reproduce for the same close and are never overwritten; the pages, the prefill and the row link; the veto statistic
  on a known price path. A test on the frozen real data (prices, caches and the research-book copy, D16) runs where
  that copy exists and asserts the same invariants without fixing the outcomes.
- Robustness (same night): a sweep over 52 random synthetic homes with odd data – thirty-session listings, NaN and
  zero volume, flat prices, a SELL view with the kill level above the price, a view without bear value or
  probabilities, a bank light case, a model path that does not exist, missing feeds and limits, malformed insider
  entries – found no crash. Still, one stock's bad data must never stop the daily run: `run()` isolates each stock,
  and a failure is written to the run's data-quality list ("desk-feil for CODE") and shown on the page, never hidden.
  Unknown turnover (no volume data) is said to be unknown, not printed as zero (`tests/test_desk_edges.py`).
