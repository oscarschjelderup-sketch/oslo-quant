# Night audit, 1–2 November 2026: what is wrong before anything new is built

Everything below was measured on this machine on the evening of 1 Nov 2026 (store: adjusted Yahoo daily closes to
30 Oct 2026, 64 stocks). Scripts were run read-only against the store; nothing private is quoted.

## 1. Git and privacy (checked first)

- 47 commits in history. Paths ever tracked that match a private name: `trader_live.db` (a paper-account database,
  added 21 Oct, removed 30 Oct; it holds paper trades, not research). No research book, judgement log, watchlist,
  feed cache or report PDF was ever tracked.
- Content: the private case's target/bear/bull triple sits in two commits of 19 Oct 2026 (`85eee61`, `23d37bb`), as
  reported before; the current tree is clean. Removing it needs a history rewrite and a force-push – Oscar's call.
- `.gitignore` relied on the private files living outside the repository. Added explicit patterns for all of them
  (research book, judgement log and heads, watchlist, dashboard/report config, feeds, reports, testdata, weekly,
  monthly, `*.summary.json`) as belt and braces. The tracked `researchbook.example.yaml` is unaffected.
- One test read the live research book to build its needles (`test_no_tracked_file_holds_the_private_research_book`).
  It now reads a frozen copy in the private test-data folder and skips where that is absent.

## 2. Data quality

### 2.1 Coverage and gaps
- No stock is stale: all 64 have a close on the newest session (30 Oct 2026).
- 21 of the 64 were listed after January 2010 (first close from 2010-03 for Bakkafrost to 2026-09 for the retail IPO).
  So "since 2010" measurements rest on 43 stocks at the start and 64 at the end.
- Internal gaps (sessions where other stocks traded but the stock has no bar), biggest first: Bouvet 641 (scattered
  thin-trading days in 2010–2011), Borr Drilling 245, Solstad 177, Protector 124, Odfjell 113, Okeanis 112, MPC
  Container 73. Most are early thin-trading days or pre-main-list periods (Okeanis Jul 2018–Feb 2019, MPC Jun–Dec
  2017). **Borr Drilling has no Yahoo bars at all for January–November 2025** (checked live against Yahoo: 0 rows in
  those months, data resumes mid-December 2025). This is a source gap, not a store bug; it cannot be filled from Yahoo.
- The retail IPO stock exists only in the adjusted table, not in the raw-close table (the raw recorder has not run for
  it). Harmless today; noted for the data-health page.

### 2.2 Corporate actions: Yahoo against NewsWeb
- Splits and large distributions are handled: the 1:100 reverse split in Solstad (Oct 2020), the 2:1 split in Grieg
  Seafood (Apr 2026), Aker Solutions' extraordinary dividend (Nov 2024) and a one-day doubled quote in Borr (13 Dec
  2021) all leave the adjusted series continuous.
- **Dividends are missed.** I took every NewsWeb message in category 1101 ("EX DATE") whose title states an
  ex-dividend amount (844 notices across 53 stocks since 2010) and checked whether Yahoo's adjustment factor moves
  within ±7 sessions. 29 notices with a yield above 0.3 % have no adjustment at all. Concentrated in: Bouvet 2010–2015
  (six annual dividends of roughly 5–7 % each – about 35 points of return missing), Mowi 2015–2017 (quarterly
  dividends of 2–2.5 % each, about 21 points in total), Wilh. Wilhelmsen (8.5 points), Aker (one 6.3 % distribution,
  Nov 2024), Kid (4.9), Grieg Seafood, Protector and TGS (1–2 points). Example checked by hand: Mowi 18 Feb 2015,
  ex-dividend NOK 3.40, raw and adjusted close both fall 2.7 % and the factor is unchanged.
- This is a lower bound: several issuers file ex-dates in other categories (DNB's annual dividend never appears in
  1101, yet Yahoo adjusts it correctly every year).
- Effect: a missed dividend looks like a price drop. It can fire a false "drawdown"/"breakdown" signal that day and it
  lowers the measured forward return of any buy signal within the window. 29 events among roughly 40,000 signal
  events over 16 years – small on the pooled odds, but material for the total return of those stocks over those
  years, and therefore for any calibration row that would span them (none of today's cases does).
- Extreme single-day moves in the adjusted series (26 days with |move| > 40 % since 2010) are all in distressed or
  penny-priced periods (Borr, Norwegian, Archer, MPC, Solstad 2020; Frontline 2011; Aker BP 2011). None coincides
  with an adjustment-factor jump, so they are quotes, not adjustment errors – but they are unverified against a second
  source.

## 3. Biases in the measured odds

### 3.1 Survivorship (today's 64 stocks)
- The equal-weighted universe of today's 64 returned **+19.5 %/yr** from March 2013 to October 2026, against
  **+11.6 %/yr** for OSEBX as stored (Yahoo "Oslo Børs Benchmark Index", from 2013-03-05 in the store). The gap of
  about 8 points a year is survivorship plus equal weighting; the two cannot be separated without delisted stocks and
  market caps, which the store does not have. Every "excess vs the universe" figure is measured against this inflated
  benchmark, and every stock in it is a company that is still listed.
- Restricting the signal odds to the 43 stocks listed by 2010: the 20-day excess of the buy signals shrinks from
  +0.22…+0.35 % to +0.11…+0.17 % (breakouts), and "New 52-week high" turns negative (−0.14 %).

### 3.2 Period dependence
- 2010–2017 vs 2018–2026, 20-day excess: Breakout 60d +0.97 % (naive t 3.4) vs −0.02 %; Breakout 20d +0.91 % (t 4.0) vs
  −0.26 %; New 52-week high +0.36 % vs −0.21 %; Breakdown below 60d low −0.82 %/−3.08 % (20/60 d) vs −0.41 %/+0.15 %.
  Only "Rising channel entry" is better in the second half (+0.53 % vs −0.15 %). The pooled 2010–2026 numbers in
  `signal_odds.yaml` hide this.

### 3.3 Overstated t-statistics
- `scorecard()` computes t on all events as if independent. Events cluster (many stocks fire in the same week). With
  one mean per calendar month, the 60-day t of the buy signals falls from 3.9–4.0 (naive) to 1.3–2.1; Breakout 60d
  from 3.9 to 1.3. The one result that survives clustering is a risk signal: "Falling channel entry", 60-day excess
  −1.39 %, clustered t −4.2 (naive −3.9); "Death cross" −0.55 % at 20 days, clustered t −2.3.
- So "no buy signal pays after costs" stands, and "risk signals carry more information" stands for two of the five.

### 3.4 Look-ahead
- Indicators: 20/60/250-day highs and the 60-day low use `shift(1)` (yesterday's window); moving averages, RSI, the
  120-day regression slope and the volume confirmation use data through today's close; entry is the next open. No
  look-ahead found. The equal-weighted benchmark averages the stocks that have data each day, so a stock enters the
  benchmark on its first bar.
- Hidden choices: 9 signals, 3 horizons, 6 tunable constants (volume ratio 1.5, channel 120 days, slope 0.20,
  drawdown −10 %, cost 0.5 %, horizons 10/20/60). The signal code was written once (19 Oct) and the constants were not
  tuned against the odds afterwards (git history: two commits, then the brackets). Still, 9 × 3 × 2 cells were read
  before "the best" were named; the quant review (ideer-kvant.md) measures the placebo distribution.

## 4. Tests

- 346 tests, all green in the worktree (6 min). Line coverage 85 % overall (`coverage` installed into the venv for the
  night; not a project dependency).
- Lowest: `dashboard/casefile.py` 38 % (the reverse-DCF reader runs only on the real model – no synthetic workbook
  fixture), `recorders/yahoo/client.py` 38 % (network), `session.py` 52 %, `dashboard/testdata.py` 56 %, `cli.py` 61 %
  (most commands are never invoked in tests), `dashboard/insiders.py` 70 % (fetch loop and `reclassify` untested),
  `goats.py` 74 %, `dashboard/reports.py` 75 % (`find_reports`, `download`, `run` need the network – only the parsers
  are tested), `dashboard/render.py` 76 % (several page states never rendered: no-feed, errors, SELL views).
- Not tested at all: the evening PowerShell scripts, the Windows task registration, `oq record` against Yahoo, the
  dashboard's behaviour when the store is empty, a judgement on a stock with no price, a SELL view's sizing (refused
  by design, but no test says so), the static front page's links.
- Tests that touch real data: six, all against the frozen private copy (`~/osloquant-home/testdata/2026-10-22`), none
  against the live research book or log any more.

## 5. Fixed tonight before building
1. `.gitignore` patterns for every private file (section 1).
2. The privacy test reads the frozen copy, not the live book (section 1).
3. `scorecard()` now also reports a month-clustered t (`tc20/tc60`) and the odds file carries both halves of the
   period, so the badges can say when a signal's odds did not hold (built in step 4; see DECISIONS D20).

## 6. Not fixable tonight (reported)
- Borr Drilling's 2025 gap and the missed dividends are Yahoo's. Options: a second price source (none free with
  redistribution-free terms found), or marking the affected stock-years on the data-health page so no odds are read off
  them. The latter is built (step 4).
- Survivorship: needs delisted stocks' prices. Not available free. The honest fix is to label every odds figure
  "survivors only" and show the 43-stock and sub-period variants, which is done.
