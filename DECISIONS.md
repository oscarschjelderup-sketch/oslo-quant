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

## D42. The whole store as light cases, each with a quality grade

Fifteen light cases left 46 of the 64 companies in the store with nothing. `oq case build --all` (or `--missing`)
now builds one for every company: each company's statements are loaded once, the group medians are computed once per
group from the same cases, and one company's bad data is reported as "not built – why" without stopping the others
(`lightcase.build_all`). Building them showed three faults, now fixed:

- **The LTM.** Yahoo often drops one quarter (for most companies the third quarter of 2025), so four quarters in a row
  were missing and the case fell back to the last full year. The LTM is now also taken the way an analyst takes it:
  the last full year plus this year's quarters minus the same quarters a year earlier, labelled as such
  ("FY 2025 + YTD − prior YTD"); none of it is invented – when the prior year's quarter is missing too, there is no LTM.
- **A wrong sentence.** When the enterprise value is below the capital the business employs (NOPAT / ROIC), no growth
  rate solves the value-driver formula, and the case said the price "needs growth at or above the cost of capital" –
  the opposite of the truth. The reading is now one pure function (`value_reading`) with six kinds, one of them
  `below_capital`: no growth rate explains the price, which at no growth pays for a lower return (given). Two
  companies read wrongly before. Case files written earlier get the corrected words on the page, derived again from
  their stored numbers (`lightcase.reading`).
- **Danish kroner.** One company reports in DKK and the store had no DKKNOK rate; it is now recorded with the other
  two (Yahoo `DKKNOK=X`).

Every case now carries a grade, derived from the file (`lightcase.quality`), so old files grade the same way: **C** when
the reading cannot be used (no price, no share count, the reporting currency unknown or not converted, an investment
company valued on its holdings), **B** when an input is missing or old (a full year instead of LTM, quarterly
statements more than 115 days older than the price, a balance sheet more than 400 days older, no net debt, fewer than
three annual years, a price a week older than the build), **A** otherwise; every reason is named. Energy, shipping and
seafood are also read on the average EBIT margin of the annual table applied to today's revenue
(`lightcase.normalised`), because their last twelve months may be a peak or a trough. The grade stands on the stock
page, beside the light case's date on the coverage page and on the screen (D43). First run, 4 Nov 2026, with the
statements re-recorded from Yahoo: 64 built, none failed; A 25, B 37, C 2 (the two investment companies). Most B
grades are quarters that end in June: Yahoo did not yet have the third-quarter statements.

## D43. What the price requires, across the universe – against the company's own history

A light case says what the price pays for; alone it does not say whether that is a lot. `/screen` ("Prisen krever")
and `dashboard/screen.py` set the requirement beside what the company has delivered: the growth the enterprise value
pays for against revenue growth a year over the annual table, for banks and insurers the return on equity the P/B pays
for against the average ROE. Revenue, not EBIT, because EBIT from a low base gives growth rates that mean nothing.
For a cyclical group three or four years of revenue measure the cycle, not growth (2022 was a peak for oil, gas and
freight), so its requirement – read on the average margin – is compared with the long-run growth the light cases
assume (2 %, EST), and the revenue history is shown beside it, not used. A difference under two percentage points a
year is "in line". The verdicts: more than the history, less, a fall (the price expects the result to shrink while
the company grew), in line, and – without a growth rate – an EV below the capital employed, a return below the cost of
capital, or a price that needs growth at the cost of capital. Grade C has no verdict.

The page ends in **candidates for full coverage**: the six largest gaps each way among usable cases not already fully
covered. That is what the screen is for – where the price and the past disagree most is where a full case adds most –
and it says so: the list does not say who is right, it is not a buy or a sell list, and the coverage plan stays
Oscar's (`oq coverage set`). Not tested against returns, and the page says that too: the store holds the statements as
they look today, not as they looked on each date, so a historical test would see the future. First run, 4 Nov 2026:
the price asks more than the comparison in 16, less in 24 (16 of them a fall, 3 an EV below the capital employed),
in line in 8, no comparison in 16. Nothing in the screen writes anything.

## D44. A static copy for someone without the store

Sharing the dashboard meant a hand-made crawl. `oq snapshot OUT [--cdn]` (`dashboard/snapshot.py`) renders every page
reachable from the front page through the app itself (Flask's test client – no server has to run), writes them with
flat relative names (`/stock/SATS` → `stock-SATS.html`; the front page as `idag.html` and `index.html`), switches the
forms off in script except the ticker search, puts a banner with the time of the copy on every page, copies the
dashboard's own report PDFs and links the companies' quarterly reports to their NewsWeb message instead of copying
them. `--cdn` loads plotly.js from cdnjs, the version the installed plotly bundles, for hosts that refuse the 3.5 MB
file. A page that fails is reported, and the rest of the copy is written. The crawl found that opening the front page
marks the signals seen; a copy must not, so the app has a `SNAPSHOT` flag the front page respects. The copy holds what
the dashboard shows – the research book, the judgement log, private cases – so it is refused inside the repository,
and publishing it is the owner's act, not the command's.

## D45. The dashboard as an app on the PC

Opening the dashboard meant a terminal (`oq dashboard`) and a browser tab. `oq app --install` now puts a shortcut,
"Oslo Børs-dashbord", on the desktop and in the Start menu (`dashboard/desktop.py`). The shortcut runs the module with
the environment's `pythonw.exe`, so no console opens: if nothing answers on port 8060 it starts `oq dashboard
--no-browser` in the background without a window (output to `~/osloquant-home/app/dashboard.log`), waits until the new
`/ping` answers, and opens the dashboard in an app window – Edge or Chrome with `--app=`, its own window and taskbar
entry, no address bar. A dashboard already running (a terminal, the evening task, Claude's preview, or one started
before `/ping` existed) is reused, never started twice; a server that dies is reported in a message box that names the
log. Closing the window leaves the server running, as a terminal-started one does. The icon – a teal square with
three rising bars – is drawn in code and written as PNG and ICO without an image library; the dashboard serves it as
its favicon, so the window and a browser tab carry it, and a snapshot (D44) copies it. Nothing here touches the
research book; the only files written are the icon, the log and the two shortcuts. `oq app` does the same from a
terminal.

## The night of 4–5 November 2026: the head of analysis (D46–D52)

Brief: make the set-up think like the best investors and forecasters and improve without Oscar having to invent what
to build; every change must make buying decisions better or the measurement of being wrong stricter. Phase 1 read
the sources and distilled thirty rules (docs/natt/beste-praksis.md); phase 2 audited every page and chain against them
(docs/natt/gap.md); D46–D52 are what scored highest. Nothing here changes a view, a target, a kill criterion, a
probability or an odds calculation on its own – the system proposes, with evidence, and Oscar decides. Everything was
tested on temporary homes with fictional rows; the real research book, judgement log and hash chain were only read.

## D46. Discipline on the row: pre-mortem, anchoring check, process against outcome

- **Pre-mortem** (Klein, HBR 2007; Duke). A view cannot be logged without three different reasons, of at least fifteen
  characters each, why it failed twelve months from now. They are stored on the row (`premortem`) and asked about
  again in the error review (D49), so foresight can be counted.
- **Anchoring check** (Tversky and Kahneman; Tetlock on updating). A new target on a company with a previous view
  of the same analyst is compared with the previous target and the price move since. A target that moved the same way
  as the price by at least half as much (on a move of 5 % or more) *follows the price*; one within 2 % after a 15 %
  move is *sticky*. The form shows the previous view and the target that would count as following before it is typed;
  the row stores `anchor` and an optional `anchor_reason`. A question, not a block.
- **Own probabilities.** Probabilities equal to the Toolkit's default 25/50/25 count as the template's unless ticked as
  deliberate (`probs_deliberate`) – otherwise the Brier score measures the spreadsheet (Tetlock on granularity;
  Friedman et al. 2018).
- **Process score and the decision grid** (Duke, *How to Decide*). Each row is scored on what it held when it was
  written: pre-mortem, own probabilities, a kill criterion with a number, the «Før du kjøper» checklist, blind where
  Claude had a view, the desk's debate, no unexplained price-following target, the base-rate check (D47). The share
  of applicable items is the score; 70 % or more is a good process. The calibration page crosses it with the outcome
  (direction against OSEBX) for final calls only: deserved win, bad break, dumb luck, deserved loss; provisional calls
  stand beside the grid, marked. A new error pattern, `anchored`, comes from the row.

## D47. Base rates for the estimates

The newest report's estimates (`estimates_*.json`) give revenue growth a year over three estimate years and the
EBITDA margin change over the same years. Each is set against two reference classes, named with sample and period
wherever shown: the store (non-financial companies with four annual statements, one three-year period that starts at
a cyclical peak – small and said to be) and Mauboussin, Callahan and Majd's *Base Rate Book* (Credit Suisse 2016,
Exhibit 2, p. 22: the top 1,000 global companies 1950–2015, real growth; the nominal forecast is deflated by 2 %, EST,
before it is looked up). The table is in `resources/base_rates.yaml` with its source and page; the book's size-class
column for $325–700m has an arithmetic error and is not used; the book has no distribution of margin changes, so the
margin is checked against the store only and the book's persistence (r = 0.79 over three years, p. 59) is quoted.
Outside the 20th–80th percentile band on either side is flagged in the form (with a reason field), on the stock page
and on the row (`base_rate`). First run, 5 Nov 2026: one of the three full cases has a growth assumption above the
store's 80th percentile; the other two sit near the middle.

## D48. The update log

When a report has passed after an open view and its last update (as D39 finds reports), the stock page asks whether
the scenario probabilities changed. The answer is a row of kind `update` (the view it refers to, the trigger, the
probabilities after the news – the same ones if unchanged – the prior ones and, when unchanged, why). The target is
not changed by an update. A trigger older than 14 days without an answer is *not updated* – derived, never written –
and counted by the head of analysis. When the view is final, the last update's Brier is set beside the original's.
A fourth write route (`POST /stock/<code>/update`), appending to the same hash-chained log.

## D49. The quarterly error review

`/review` lists Oscar's scored views, the largest miss against the target first, with the pre-mortem written at the
time and the process score, and asks the same questions every time: was it among the pre-mortem's reasons, was the
decisive information available, the decision or luck, which bias, what to do differently. The answers are a `review`
row per view and quarter in the log; the page counts foresight, availability, luck and recurring biases and lists the
lessons (Dalio's issue log; Duke; Klein; Mawer's annual review; Tetlock's post-mortems on successes too).

## D50. The head of analysis

`dashboard/chief.py`, `/chief`, `oq chief run [--write]`: the thirty rules, each with a source, a metric over what
the system holds, a target and a minimum sample; status *ok*, *brudd*, *for lite data* or *ikke målt*, never a number
from too little data. A rule off target yields a proposal from a fixed catalogue (what, why with the numbers, expected
effect, effort), ranked by the distance from target, weighted for decisions over measurement, halved per earlier
rejection of the same rule. Oscar approves or rejects on /chief with a reason (`chief/decisions.jsonl`, private,
append-only); approved goes to the backlog; rejected stays away until its metric is 10 % further from target, and
never after «aldri». The weekly run is a Monday step in `scripts/run_signals.ps1` and writes only its own run file.
First live reading (5 Nov, read-only): 3 rules ok, 12 off target, 15 not measurable yet – mostly because the two
open views predate the checks that measure them.

## D51. Inversion from the model's sensitivities

For every full case with a model: what has to go wrong for a 30 % loss from the last close, read from the workbook's
growth × EBITDA margin table and WACC × terminal growth table (cached values via openpyxl; no Excel). Along each axis
alone the shift that reaches the line is interpolated between grid points and never extrapolated – a line the grid
does not reach is said to be outside it, with the edge value; the cheapest combinations inside the grid are listed.
On the stock page; the head of analysis counts full cases without it (R18). Munger: invert, always invert.

## D52. Quarterly forecasts with a quick answer

Two twelve-month views a month cannot be calibrated before 2027. Before a covered company's next report (within 60
days, from the calendar), the stock page takes an 80 % interval for the quarter's revenue, EBITDA or EBIT (or a key
of the company's reader spec), one per number and report, written before the report date as a `forecast` row. The
report reader's printed figure of the same name – or the after-report loop's generic reading – answers it: inside or
not, and the miss against the middle. The calibration page shows the share inside against the 80 % it should be, and
says fewer than ten answers are too few. A number the reading does not print stays unanswered; nothing is guessed.

## D53. Narrative against numbers

Damodaran (*Narrative and Numbers*, 2017): a valuation is a story told in numbers, and the two must agree. For a full
case – a company with a published report and its estimates – the judgement form now asks for the story in one
sentence and the three numbers it needs: revenue growth a year over the first three estimate years, the EBITDA margin
in the third year and EPS in the third year. The model's three stand beside them (from `estimates_*.json`). A story
number more than one percentage point (growth, margin) or 10 % (EPS) from the model's is flagged – the story is bigger
or smaller than the model – on the row (`story`) and on the stock page under the research book. Required for a full
case, not asked without a report (there is no model to hold the story against). It does not change the model or the
target; it makes the gap between what is said and what is computed visible when the view is written.

## Also that night

- **The loops on the front page.** An unanswered report asks for the probability update (D48) and replaces the
  post-report item (D29) – answering the update, even "unchanged", puts the view on record after the report; a report
  within 14 days asks for the quarterly forecast (D52) until it is logged; the stored chief run's undecided proposals
  are one item (D50); in the last three weeks of a quarter the error review of views older than 90 days is one item
  (D49). Without this they would be built and not used.
- **Fragility** (Taleb et al., IMF WP/12/216, 2012) in the inversion block: H = [f(−Δ) + f(+Δ)]/2 − f(0) around the
  base point of the growth × margin table, scaled by the value; negative is concave (the value falls faster than it
  rises).
- **Toolkit:** the same base-rate check in the research report – an exhibit in "What we do not know" and a `[flag]`
  line in the build gate that never fails the build (Toolkit DECISIONS 2026-11-05).

## D54. Passes: the decisions not to buy

Buffett (letter for 1989): the costliest mistakes were opportunities understood and not taken, and they never show in
the accounts. A pass is now a row of kind `pass` (POST /stock/<code>/pass): the price and date set by the server, the
reason (at least fifteen characters) and whether the company was inside the circle of competence. It is scored like a
view without a target – total return against OSEBX for twelve months – and a pass inside the circle that beat OSEBX by
more than 20 percentage points is a *possible omission* (the threshold is mine). The calibration page lists them; the
head of analysis counts passes as forecasts in R04. Cheap on purpose: one sentence and a tick.

## D55. Variant perception and the catalyst

Marks ("It's Not Easy", 2015: different and better than the consensus), Mauboussin and Callahan ("Who Is On the Other
Side?": behavioural, analytical, informational or technical edges) and Klarman (a catalyst closes the gap, and its
date is part of the margin of safety). A BUY or SELL now names the kind of edge, what the price misses in one sentence,
and the catalyst with a date inside the horizon; HOLD is not asked. Stored on the row (`variant`), counted in the
process score for views written from 5 Nov 2026, and when the date has passed with no kill check or view since, the
front page asks whether it happened.

## D56. The pages read as one thing: a nav that never squeezes, Norwegian labels, folded detail

A visual pass over every page at 1400, 1250, 1100 and 900 px (headless Edge, 5 Nov 2026) found the nav squeezing
its words below about 1250 px ("I dag" on two lines, the search cut off), four blocks that ran as walls of text, one
table that overflowed, chart labels that overlapped, and headings and footers still in English from the first phases.

- **The nav** is one row of whole words in four groups with a thin rule between them – the day (I dag, Desk,
  Kalender), the universe (Dekning, Prisen krever, Sektorer, Porteføljer), yourself (Kalibrering, Feil, Analysesjef),
  the machinery (Overvåkning, Datahelse). Nothing may wrap inside a word: below 1320 px the padding shrinks and the
  brand drops to "Oslo Børs"; below 760 px the links wrap to a second row as whole tabs. `NAV_GROUPS` is the order;
  `NAV` is kept flat for anything that reads it.
- **Folded detail.** The kill-list comparison on the stock page is one line ("spriker – 10 avvik") that opens to the
  list; the data-health box carries one line per case for it, and the case table's "Avvik" cell is a plain left-aligned
  list, not a red paragraph. The desk's bear verdict no longer repeats the nine sources on every row (new runs write
  the short form; old runs are shown short). The screen's candidate tables wrap their reading column instead of
  running off the page. The portfolio chart's diamonds lost their text labels; the legend names them.
- **Norwegian** on the front page's table, the calibration page, sectors, the watchlist, the light-case block, the
  chart legends and titles, the footer. The analytic sentences the light case writes ("at a 9.5 % cost of capital …")
  stay English for now: they are quoted by the desk, the screen and the tests, and are changed together or not at all.
- Tests that pinned the English words were moved to the Norwegian ones; the source-labelling test accepts
  "forsinket" as well as "delayed".

## D57. The stock page as a sticky bar and seven tabs

Oscar (9 Nov 2026): give the stock page the overview of the stock pages at Finansavisen and TradingView – learn the
patterns, copy nothing, keep everything the page already had. The inventory of every old block and where it went is
`docs/design/aksjeside-inventar.md` (36 rows, none without a place).

- **The bar** (sticky): name and ticker, the last close with the change in NOK and percent against the previous
  close, the date and a «forsinket» mark (the store has daily closes from Yahoo, nothing live), the period buttons,
  and – when the company is in the research book – your rating, target and upside and the next report date, with a
  status chip (research book / overvåkning / ikke fulgt). **1D is disabled**: there is no intraday curve in the store,
  so the day's open, high and low stand in the key grid instead of pretending.
- **Seven tabs, the active one in the URL** (`/aksje/<code>/<tab>`, Regnskap also `/<sub>`): Oversikt, Regnskap,
  Verdsettelse, Teknisk, Rapporter, Eiere, Min vurdering. All panels are server-rendered into one page and the
  inactive ones hidden, so every test that reads `/stock/<code>` still sees every block; a small script switches tabs
  with `history.pushState`, and `/stock/<code>` keeps working (it opens Min vurdering after a form was sent).
- **Period buttons without a reload**: the overview chart holds five years of closes; the server computes each
  period's x-range, y-range and return once and the button calls `Plotly.relayout`. Under the chart the same buttons
  show the period returns (close to close, adjusted).
- **Only data the store has.** Turnover is close × volume and marked EST; market value, P/E, P/S, P/B and EPS are the
  light case's share count and LTM figures at today's price, with the formula in the hover; dividends and ex-dates from
  `StockAction`; the statements tables and charts from the income statement, balance sheet and cash flow in the store.
  Segments, SOTP, shareholder lists and analyst consensus are not free, and say «ikke tilgjengelig»; a consensus target
  logged by hand on a judgement row (with source and date) is shown and marked *manuell*.
- **Teknisk labels nothing.** `dashboard/technicals.py` computes SMA 20/50/200, the MA 20/60 state, RSI 14, MACD
  12/26/9, the 52-week and 60-day extremes, the drawdown, the channel and volume against its averages. A row that is one
  of the measured signals shows that signal's excess return over 20 and 60 sessions after the 0.5 % round trip, the hit
  rate, the number of historical cases and the stability grade from `signal_odds.yaml`; a row nothing measures says
  «ingen målt odds». The signal catalogue's kinds are shown as «opp» / «risiko» / «info» – the direction the odds were
  measured on – never as a word to act on. Insider trade chips lost their green and red: colour is for up and down only.
- **Visual system** on every page: a calm grey background, white cards with a 1 px rule and 10 px corners, one accent
  colour, tabular numbers right-aligned, and every new number with its source and time in a hover title. The front
  page and the sectors page got the cards without any content moving.
- Kitron (KIT) joined the universe under Industrials & materials and was recorded so the page could be tested on
  SATS, Kitron and Elkem. `view_rail` and `case_block` were split into cards the tabs place separately; the old
  composites remain for anything that calls them.

## D58. Dates in one Norwegian form

Oscar (9 Nov 2026), on the OUTLT page: «kan du fikse alle datoene». The page mixed three forms – «2026-11-09» in the
bar, «12 Nov 2026» for the next report, «Sep 27 / Oct 4» on the chart axis – and the rest of the dashboard added
English weekdays («Monday 09 Nov») and UTC stamps («2026-11-09T17:47:07Z»).

- **One form** (`dashboard/dates.py`): «9. nov. 2026», «9. nov.» without the year where the year is obvious,
  «mandag 9. nov. 2026» in page headings, «9. nov. 2026 18:47» for a time, «nov. 2026» for a month. Month
  abbreviations as Språkrådet writes them (mars, april, mai, juni and juli in full). UTC stamps are shown as Oslo time.
  Light-case periods read «LTM til 30. sep. 2026» and «år til 31. des. 2025».
- **The charts** get a Norwegian Plotly locale registered once per page (month and day names; numbers keep the page's
  point decimals and space thousands so a chart and its table read alike) and date ticks in Norwegian order:
  «27. sep.» for days, «sep. 2026» for months, «2026» for years; hover shows «9. nov. 2026».
- **A last pass in `page()`** turns any ISO date left in visible text into the same form. It never touches tags or
  attributes (links, the period buttons' data), scripts, styles, form fields, code or file names – it changes what is
  read, never what is sent or stored. Logs, rows, run ids and files keep ISO dates.
- Left as they are: sentences stored in English (the light case's readings and warnings, rationales on log rows),
  citations («26 Sep 2016»), the weekly mail and the public signals page, which are written in English.
- With it: a stock listed less than a year ago opens its chart on «Maks» instead of a disabled «1Å», and a period
  button that reaches back before the first close shows no return – before, OUTLT showed +9.2 % under 6M, 1Å and 5Å
  for six weeks of history.

## D59. The price chart on TradingView Lightweight Charts

Oscar (10 Nov 2026): «vil ha tradingview hvis det gjør det bedre», and yes to downloading the library. Night brief,
part 1. The old Plotly chart read the 800-day snapshot, so 5Å was always off and Maks was about two years (funn #12).
It had gaps for weekends on the date axis, and its unified hover box sat on the line it described.

- **Library:** TradingView Lightweight Charts™ 5.2.1 (Apache-2.0, 198 kB). It sits in `dashboard/static` next to its
  LICENSE and NOTICE, is served locally and is carried by the static copy (D44).
- **Attribution:** the licence asks for credit. The chart keeps TradingView's attribution logo, and the NOTICE text
  with a link to tradingview.com stands under the chart. This is the one TradingView mark on the dashboard. The D57
  rule «no logos from TradingView» still holds for everything else.
- **Data:** the library only draws. The data are the store's own adjusted daily bars for the whole history, one query
  per stock and cached per snapshot bar. Nothing is fetched from TradingView. The paid TradingView MCP connector was
  not added; that is Oscar's call.
- **Our own code:** `pricechart.py` builds one JSON payload and `static/pricechart.js` draws it.
  - Area chart by default, with candles as an option. Volume sits in its own pane, so the price axis never runs below
    zero.
  - No time gaps: every series shares the stock's sessions.
  - The period buttons set the window, the colour (green up, red down) and the return in the header in one step.
    Zooming or dragging does the same for the visible window.
  - Log scale only for 5Å and Maks, and never while comparing.
  - The last price is on the axis. The previous close, the view's target and the kill level are dashed lines, the
    target and kill level with their distance from today's price. The axis stretches so both stay on screen.
- **Comparison:** OSEBX (a total-return index, like the adjusted prices) and the rest of the stock's group, equal
  weighted. Both are rebased to the first session in the window where every line has a close. The header then shows
  each line's return from that session. The sector line is marked as our own calculation, and the button says it
  uses today's universe.
- **Event markers**, each with its own toggle:
  - Reports (calendar and downloads; older report dates are not in the store, and the button says so).
  - Ex-dividends and splits.
  - Insider trades. Off by default, because a long history makes them crowd.
  - Oscar's judgements: his rows in the log plus the book's view. Claude's rows are not shown.
- **SMA 50 and 200** are off by default.
- **Hover box:** it always sits beside the point, in both panes. A browser test checks this against the real mouse
  position.
- **Fallback:** if the new chart fails on the server, the old Plotly chart is drawn, so the page always opens. The
  period buttons' `data-r` now carries only dates, so a missing volume can no longer put NaN into it (funn #4).
- **Tests:**
  - Unit tests of the payload, events, lines and comparisons.
  - Browser tests (`tests/browser.py`, DevTools protocol) of the state after every button, panes after rebuilds, the
    hover box, a chart opened in a hidden tab, and console errors on every tab.
  - Visual baselines (`tests/visual/win32`) of three chart views and, for every tab, the bar (fine cells, so the
    active tab counts) and the panel with its text hidden.
  - Baselines exist per platform. On a platform without them, such as CI on Linux, the visual comparison skips and
    the state tests still run.

## D60. Improvement pass (10 Nov 2026): branch, order and the data sources in one list

Oscar's brief: audit and improve the whole dashboard (visual, functions, data fetching), on a branch, no merge, no
push, no questions. Findings are in `docs/forbedring/funn.md`, each change in `docs/forbedring/endringer.md` before
it is made, progress in `PROGRESS.md`.

- **Branch:** `forbedring-2026-11-10`, cut from `natt-2026-11-10`. The brief names the price chart as the standard
  the rest must hold, and that chart lives on the night branch. The findings of 9 Nov (`feilsok-2026-11-09`) are
  merged in, so their numbers (#1–#132) stay valid references.
- **Phase 1 reuses the audit of 9 Nov.** Its 105 open findings were checked against this branch instead of being
  found again. New work went where that audit had not looked: every data source, the scheduled task's logs, the
  visual system and the three flows.
- **One list of sources (`dashboard/sources.py`).** Before, a feed's age came from its cache file and a table's age
  from its newest row. Both hid the two real faults in the data: the scheduled task never fetched quoted prices or
  statements, and a failed fetch left no trace outside a log file.
  - Every attempt is written to `feeds/_runs.json` in the home folder (the last 60 per source). The file is the
    dashboard's own and is not in git.
  - Four states: ok, stale, failed, never fetched. «Partial» is a fifth for a source that answered in part (one
    newspaper down, one stock without the last close). Partial shows on data health only; the front page warns for
    the other three.
  - A daily source is stale when it has not been fetched since the last session's close. The alternative, a number
    of days per feed, let a daily feed be three to seven days old before anything showed.
  - Today's close is expected from 18:30 Oslo time. The evening job starts 17:45 and takes about ten minutes, so an
    earlier limit would warn every evening while the job runs.
  - Oslo Børs' holidays are computed (Easter by the Gregorian algorithm, plus the fixed days and the two half-week
    closures at Christmas), so the morning after a holiday is not a false alarm (funn #58).
  - Store tables are measured per stock. The statements use `report_date` (the period), not `timestamp`, which is
    the period plus an assumed publication lag.
- **The scheduled scripts.** `run_signals.ps1` now runs `oq record --raw`: the quoted bars come from the same
  download as the adjusted ones, so the cost is zero requests. `run_weekly.ps1` runs `oq record --raw --finance`
  on Sundays: six requests per company once a week, not every evening. The scripts take effect when the branch is
  merged, because the task runs the scripts in the main checkout.
- **Retries.** `feeds._get` makes up to three attempts with 2 and 5 seconds between them, on network errors,
  timeouts, 429 and 5xx. A 404 is an answer and is not retried. Longer waits were not chosen: the job runs twice
  an evening, so the second run is the long retry.
- **Fewer requests to NewsWeb.** Announcements ask for the days since the last good fetch plus one, at most 14.
  Insider lists ask from the day before the last listing. NewsWeb's terms allow private use; asking for less is
  the polite reading of them. The short register has no partial query, so it is still fetched whole.
- **Consensus (MFN).** A 404 means the company published none. Any other failure is now written to the run log
  and shows as «feilet», because «no consensus» and «could not ask» are different facts.

## D61. Numbers in one Norwegian form, as a last pass

- **What:** `dashboard/tall.py`. `norske_tall` runs last in `page()`, after the date pass (D58): decimal comma, a
  no-break space before the per cent sign, a real minus sign, and «−0,00» becomes «0,00».
- **Why a pass and not sixteen rewritten helpers:** the audit counted sixteen formatting helpers in three forms
  (funn #128). Rewriting them would touch a few hundred call sites and still miss the next one written. One pass
  makes every page read alike, including pages written later.
- **What it never touches:** tags and attributes (links, form values, data for scripts), `script`, `style`, `code`,
  `pre`, `textarea` and `select`. Version numbers (5.2.1), addresses (127.0.0.1), dotted dates (09.11.2026), file
  names, and a number hyphenated to a word (Apache-2.0) are left as written. Hover text in `title="…"` is the one
  attribute that is read by a person, so it is formatted.
- **Idempotent, so no regrouping of thousands.** After the pass «9.410» reads «9,410». A second pass that grouped
  thousands would read that as nine thousand. Counts are grouped where they are written (`tall.heltall`).
- **A user's own text is formatted too.** A kill criterion typed as «margin below 10%» is shown as «10 %». The log
  keeps what was typed; only the page changes.
- **Plotly** gets the decimal comma through the Norwegian locale registered on every page. The price chart already
  wrote Norwegian numbers (D59).

## D62. The visual system: one accent, green and red for up and down, text left and numbers right

- **Colours.** The accent is the teal already in the nav. Green and red now mean one thing: a price went up or
  down, or a level above or below the price (target, kill). The decision list, its tags, error boxes, confirmation
  boxes and status words no longer use them. An error box is amber with a thick border; a status is quiet when ok
  and amber and bold when not (`st-ok`, `st-warn`, `st-bad`).
- **Tables.** One script on every page left-aligns a column when most of its cells are text. A class on each cell
  was the alternative; there are a few hundred cells, and the next table would forget it. A cell with its own
  alignment keeps it.
- **Language.** The front page's decisions, the book's warnings and data health are in Norwegian, and each kind of
  decision has a Norwegian name. Machine statuses and log fields keep their English keys; only what is shown is
  translated. Error messages from the judgement form's validation are still English (see the report's open list).
- **Not done here:** one Plotly theme for every chart (the price chart is the standard; the others have the decimal
  comma but their own grid and colours), and a hover with source and time on every key figure outside the stock
  page.

## D63. New free sources assessed

Only one source was built, and its terms are the ones verified earlier in `docs/dashboard/data-sources.md`. For the
others the terms column is what is generally known of them: they were not re-read in this session, and each must be
read before anything is built on it.

| Source | Gives | Terms | Decision |
|---|---|---|---|
| Norges Bank open data, I44 | the import-weighted krone index, daily | NLOD 2.0, verified earlier, same API | **built** (E18): one more series in the FX fetch |
| Norges Bank, more yields (2y, 5y) | the government curve | NLOD 2.0 | not built: no page uses a curve yet |
| Brønnøysund, Regnskapsregisteret open API | annual accounts as filed | NLOD | not built now; the best candidate for checking Yahoo's statements against a second source |
| Companies' IR pages, largest shareholders | top-20 lists | each site has its own terms; the lists come from Euronext Securities or Modular Finance under licence | rejected: no uniform terms, sixty-five different pages to scrape |
| Companies' IR pages, report calendar | report dates | as above | rejected: the issuers' own «Financial calendar» announcements on NewsWeb already give this |
| Euronext live.euronext.com | delayed quotes, company data | the site's terms forbid automated collection | rejected |
| ECB reference rates | EUR crosses, daily | free reuse with attribution | not built: Norges Bank against Yahoo already gives two sources for USD and EUR |
| SSB, more tables (CPI, exports) | macro series | CC BY 4.0 | not built: no page asks for them |

Paid or paywalled sources were not considered.

## D64. Corrections to the store's data that take effect on the next recording

Two fixes change stored prices, and both need Oscar's eyes before a merge because the paper accounts read the same
store.

- **Dividends in another currency (cleaning rule 0, E9).** The adjusted history of every stock that has paid in USD
  or DKK is restated the first time `oq record` runs: FRO, HAFNI, OET, BWLPG, BWO, SNI, WAWI, BORR, ODL, MPCC, EQNR,
  AKRBP and BAKKA. One-year total returns rise by 10–40 percentage points for the tanker and gas names. Checked on
  Yahoo's real histories without writing anything: FRO +82.0 % → +107.5 %, where quoted closes plus the dividends
  give +107.3 %. DNB, MOWI and SATS do not move. The currency is named by the ratio between the reported amount and
  the amount Yahoo adjusted with, so nothing is changed unless a rate fits within 6 %.
- **KOG, 15 Apr 2026 (E10).** The demerger day's move is removed from the adjusted series, as for AKSO in 2024. The
  whole close-to-close move is taken as the distribution, so returns across the date are an estimate.
- **Quoted prices for the day's change and the 12-month range (E16)** read the quoted table and fall back to the
  adjusted one, labelled, while the quoted table lags.

## D65. The macro picture: drivers, a strip, a page, and sensitivity measured on our own data

Oscar's brief (10 Nov 2026): news and macro should be visible wherever they matter, on the level of the price chart.
Research first (`docs/loft/research.md`): what the best tools do that can be read in ten seconds, and which free
sources may be used.

- **Fifteen drivers in one feed (`macro`).** Rates (policy rate, 3-month bill, 10-year, US 10-year), currencies
  (USD/NOK, EUR/NOK, the I44 krone index), commodities (Brent, TTF gas, aluminium, copper, the salmon export price,
  the NO2 power price) and the market (OSEBX from the store, VIX). Three years of daily history each, because the
  sensitivity needs it. A source that fails keeps its series from the cache and is named.
- **Sources and terms.** Norges Bank's open API (NLOD 2.0), SSB table 03024 (CC BY 4.0), Yahoo Finance for the
  futures and indices we already used it for, and hvakosterstrommen.no for the power price («fritt tilgjengelig for
  hvem som helst, til hva som helst»). The power price is asked for one day per request, at most fourteen a run, so
  the history is built without leaning on a free service. Nord Pool's own site forbids automatic extraction and is
  not used.
- **One cell shape (`macro.cell_html`).** Name, level, change, a trend line, date. A rate changes in percentage
  points, a price in per cent. Identical cells are what makes a row of numbers readable at a glance; the trend line
  is inline SVG, so it needs no library and prints sharp.
- **Sensitivity (`macro.sensitivity`).** For each stock and driver: the stock's weekly return regressed on the
  driver's weekly change over three years, with OSEBX in the same regression. What is left is what the stock did
  beyond the market when the driver moved. A stock «follows» a driver at |t| ≥ 2.
  - The alternative, a plain correlation, makes every stock look sensitive to everything that moves with risk
    appetite. With the market in the regression the number answers the question a stock picker asks.
  - It is co-movement in our own data, not cause and not a forecast, and every place it is shown says so. An
    oil-heavy index makes banks look as if they fall against the market when Brent rises; the method note says that
    too.
  - A driver that hardly moves is not measured: the policy rate changed in a handful of weeks in three years, so a
    regression on it measures two or three events. The 3-month bill carries the rate story instead.
  - The market and its mood (OSEBX, VIX) are shown in the strip but never listed as «a driver the stock follows».
- **The macro page (`/makro`).** A card per driver with a Lightweight Charts line (`static/minichart.js`), the stocks
  most sensitive to it, a matrix of sector groups against drivers, and what is coming. Blue and orange in the
  matrix, not green and red: co-movement is not up or down.
- **One attribution per page.** The mini charts do not each carry the TradingView logo; the page has the notice and
  the link once, under the charts, which the licence allows. The price chart keeps its logo (D59).
- **Not built:** release dates for CPI, GDP and foreign central banks. SSB's calendar is embedded JSON on a web page
  (fragile), and the foreign ones need a source whose terms have been read. The calendar says so.

## D66. The menu: what is looked at every day, and «Mer»

- The top line holds «I dag», «Makro», «Sektorer», «Dekning», «Desk», «Kalender» and «Prisen krever». The six pages
  Oscar named as less important – Porteføljer, Kalibrering, Feil, Analysesjef, Overvåkning, Datahelse – are under
  «Mer». Nothing is removed and every old address works.
- «Mer» is a `<details>` element: it opens without script and works with the keyboard. When the open page lives
  under it, the label says which («Mer · Datahelse») and is marked like any other open page.
- In a window under 1040 px «Dekning», «Kalender» and «Prisen krever» leave the bar and appear in «Mer», so the bar
  never wraps or squeezes a word.
- «Dekning» stays in the bar as the list of all stocks. Oscar suggested «aksjer» as a daily page; whether the page
  should be renamed is his call and is in the open questions.

## D67. News that matters first

- **A weight per item (`news.py`).** The kind of item (inside information, a report or a corporate event weigh 5, a
  flagging or an insider trade 3, a routine buy-back notice 1), the price reaction that session measured in the
  stock's own usual daily moves over sixty sessions, and whether the company is followed. Each reason is shown
  beside the headline.
- **Why a weight and not the clock:** a list by the clock puts a buy-back notice above yesterday's report. Every tool
  in the research that can be read quickly puts a few ranked items first and the stream below.
- **A weight is a sorting key.** It says what to read first, never what to do. The page says so.
- **The session an item belongs to** is the day it was published, or the next session when it came after 16:30 Oslo
  time or on a day without trading. That is the session whose price move is its reaction.
- **Where it shows:** «Nyheter som betyr noe» under the macro strip on the front page (replacing the clock-ordered
  list), day by day on the stock page with that session's price move, as «M» markers on the price chart for the
  weighty ones, and per sector beside the sector's drivers.
- **Only titles and links**, as before. One item per company and minute when an issuer publishes in two languages.

## D68. The frontier chart on the portfolio page

- It opens on the portfolios and the frontier (0–18 % volatility); the single stocks, which stretch the axis to
  70 %, are behind a button.
- Every diamond has its name beside it, placed by a small greedy routine so labels do not overlap. The tangency
  portfolio and the capital market line carry their Sharpe ratio.
- No green and no red: a portfolio is not up or down.
- Still Plotly: volatility against return is not a time series, and Lightweight Charts draws time series. The font,
  grid and number format are the price chart's; the toolbar and the in-plot title are gone.
- A build older than 31 days is marked above the chart with the command that rebuilds it.
- D33 stands and is said under the chart: no recipe beat equal weight out of sample.
- The two NAV charts below it (the walk-forward test and the paper funds) follow: a fund has the same colour in all three
  charts, the index is grey and dotted, the title is text above the plot, and the old chart functions in `render.py` are
  gone. They had a green and a red line, which on this dashboard mean up and down.
- The one-line note under each fund is read in Norwegian (`fundchart.note_text`). The build stores it in English, so the
  page translates it rather than waiting for the next build; a test fails if the allocation code writes a note the
  list does not know.

## D69. The desk reads news, events and macro

The desk of D41 flagged 40 of 65 stocks a day, killed one, and never ended in «klar». Three causes: any new
announcement flagged a stock (a buy-back notice as much as a report), the filter had no rule for a weak trigger, and
«klar» required every bear reason rebutted, which in practice needs a full case.

- **What flags a stock has a weight.** An announcement weighs what `news.py` gives it; volume, a move against the
  sector, a measured signal, an insider trade, a short change, an unusual five-session move in a driver the stock
  follows, and a report within five days each have a fixed weight; a stock in the research book adds 2, one on the
  watchlist 1. The sum is a finding with the arithmetic written out. Several signals the same day are one event:
  the first weighs 2, the second 1, the rest nothing.
- **The filter kills a trigger under 5.** That is noise, and it is the filter's to take away, with the number.
- **Macro is an input, not a seventh role** (Oscar's starting point, kept). The analyst lists every driver the stock
  has followed, what it did the last month and what that corresponds to for the stock. When that is −2 % or worse
  it is also a reason for the bear. The reply answers with the stock's own month: if the price has already fallen
  at least as much, the reason is rebutted («kursen har tatt det»), otherwise it stands.
- **A heavy trigger is «klar for vurdering».** At 8 or more the stock goes to judgement even when the bear's
  reasons stand. The veto is not weakened: the standing points are listed first, the page says «dette er ikke en
  kjøpskandidat», and the form opens with no rating and no target. The question has changed from «is this a buy»
  to «what does this change». The old route, every reason rebutted and no limit broken, still exists and still
  prefills the form.
- **At most five a day**, the heaviest. The rest are parked with the weight that was not enough.
- **The thresholds were set on a replay** (`desk.replay`): the rules run on each of the last ten sessions with the
  price panel cut at the session and the announcements read as of it. The table is in `docs/loft/desk-replay.md`.
  The scout and the filter are exact in the replay; the bear's side uses today's short register and light cases
  and is approximate.
- **Whether a trigger is worth anything is not known yet.** The measure Oscar proposed is the right one: did
  triggered judgements change his view more often, and did the price move more afterwards, than for stocks with no
  trigger. Every run stores the weight per stock, so the comparison can be made when there are judgements to
  compare. It is not built, because there is nothing to measure it on yet.
- **Data quality** comes from the dashboard's one list of sources (D60), so the desk no longer says «6 av 6 i
  orden» while the front page says the quoted prices are stale.
- **Unchanged:** no role writes free text, every finding has a number, a source and a time, the desk writes only its
  own log, and the chain never ends in a buy.

## D70. FRED: US rates, the dollar and the US release calendar, with the owner's own key

Oscar asked for FRED on 10 Nov 2026, the first item on the research list's «worth building later» (`docs/loft/research.md`,
B3). FRED's keyless CSV works but the site discourages automated extraction; the API with a free key is the allowed way.

- **What it adds.** Three drivers: the US 2-year yield (DGS2), the Fed funds target's upper bound (DFEDTARU) and the
  broad dollar index (DTWEXBGS). And the coming release dates for US CPI, the jobs report
  and GDP from FRED's release calendar, in «Det som kommer» on /makro. The US 10-year stays on Yahoo: it is current
  where FRED's is a day behind, and one source per driver keeps the cell's source line true.
- **The key is the owner's.** It is read from `FRED_API_KEY` or from `keys/fred.txt` in the private home, never from
  the repository. It is taken out of every text that can reach a feed, the run log or a page (`feeds._scrub`), and the
  test fixture removes the variable so no test ever sees it. Without a key nothing is asked and nothing is an alarm:
  the three cards say what a key would add. A key FRED rejects stops at the first request.
- **The terms** (read 10 Nov 2026, https://fred.stlouisfed.org/docs/api/terms_of_use.html):
  - The required notice («This product uses the FRED® API but is not endorsed or certified by the Federal Reserve
    Bank of St. Louis.») is shown at the top and the foot of /makro whenever the page shows FRED data, with a link to
    the terms. Without FRED data the page does not claim to use it.
  - Third-party data needs its owner's permission, and such series are marked by «Copyright» in their notes. The fetch
    reads each series' notes on every run and refuses a series that carries the word; a copy from an earlier run is
    dropped too. Checked on the real API on 10 Nov 2026: the ECB deposit rate (ECBDFR) carries «Copyright» and was
    taken out; DGS2, DFEDTARU and DTWEXBGS do not. VIX (CBOE) and the ICE bond indices are not taken from FRED either.
  - No fixed rate limit is stated. The feed asks nine times a day (three series with their notes, three calendars).
- **The Fed rate is shown, not measured.** Like Norges Bank's policy rate it moves in a handful of weeks in three
  years, so the sensitivity (D65, `MIN_MOVES`) leaves it out. The 2-year yield and the dollar index are measured.
- **Not built:** the FOMC and ECB meeting dates. FRED's «FOMC Press Release» (101) and «Key ECB Interest Rates» (484)
  list every day the data is updated, not the meetings. The ECB rate itself can come from the ECB's own data portal
  once its terms are read. SSB's release calendar is not built either.
