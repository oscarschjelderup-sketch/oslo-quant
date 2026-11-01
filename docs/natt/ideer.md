# Ideas from five pairs of eyes, 1 Nov 2026 – and what gets built tonight

Five reviews were run on the setup, each doing the job rather than imitating the voice. Their full notes are next to
this file: `ideer-pm.md` (portfolio manager, 12 ideas), `ideer-kvant.md` (quantitative analyst, 13 ideas and the
measurements behind them), `ideer-cases.md` (sell-side analyst and sceptical investor on the two cases, 18 ideas),
`ideer-student.md` (five minutes before a lecture, 14 ideas). The case-specific findings are in a private file
outside git. Below: what each review found in one paragraph, the merged list scored, and the build list.

## What they found

- **PM.** The book is two Norwegian consumer companies: 100 % of open views in one of eight sector groups, near-zero
  correlation with the Energy group that dominates the index proxy, so the book is a bet on the domestic consumer and
  against oil beta – and nothing on the dashboard says so. Six of the eight kill criteria would fire from one
  domestic household squeeze. The per-view loss limit binds in every variant and says nothing about the two losses
  arriving together. One case's valuation date is older than a report that has already passed, with no new row.
- **Quant.** "Coin flip after costs" at 20 days stands and is understated (every month-bootstrap interval covers
  zero; all four buy signals negative in 2021–26). What the buys have is a 60–120-day excess that survives two-way
  clustering and a fair placebo but is fading (Breakout 20d at 60 days: +1.7 → +1.1 → +0.7 % across three periods)
  and keeps +0.3–0.8 % after cost. "Risk signals carry more information" weakens: the breakdown signal's −4.8 % is all
  2010–15, and under a placebo with the same count per month and stock its excess is the stock mix, not the day.
  **The t-statistics in both yaml files were wrong in kind:** a t of the mean of monthly means next to an
  event-weighted mean (insiders 60 d: t 2.41 shown, cluster-robust t of the printed mean 0.88). The insider mean is
  two stocks; trimming 5 % removes it. No look-ahead found (frames bit-identical on a truncated panel).
- **Cases.** The monitoring loop is the weak part, not the models: a kill criterion already breached in the base year
  reads "triggered" in every reading with no check logged; two copies of the kill list disagree; the variable that
  both against-arguments run through is in neither list; a report KPI is compared with a model that never says which
  currency or window it meant; the sum-of-the-parts that explains the price is a side file.
- **Student.** The count of things to do is clear; the order and the time are not. The heading says "I dag" with
  Friday's date on a Sunday. The 31-row signal block is the longest thing on the page and its green chips contradict
  the page's own footnote. Mixed language reads as unfinished.

## The merged list, scored

Scores 0–3 each: **D** better decisions, **M** stricter measurement, **H** honesty about uncertainty; **E** effort
(S/M/L); **R** risk to the rules (private data, trading, data terms). Source in brackets.

| # | Idea | D | M | H | E | R | Tonight |
|---|---|---|---|---|---|---|---|
| 1 | Cluster-robust two-way t of the event-weighted mean in both yamls, replacing the monthly-means t [kvant 1, 10] | 1 | 3 | 3 | S | – | **yes** |
| 2 | Month-bootstrap interval on every odds badge [kvant 2] | 1 | 2 | 3 | S | – | **yes** |
| 3 | Odds in three sub-periods, newest first [kvant 3; revisjon] | 2 | 2 | 3 | S | – | **yes** |
| 4 | Stability grade A–D per signal and horizon from four checks [kvant 6] | 3 | 2 | 3 | S | – | **yes** (3 of 4 checks; placebo band later) |
| 5 | Raw return and benchmark window shown next to the excess [kvant 7] | 2 | 1 | 2 | S | – | **yes** |
| 6 | Trimmed mean, one-vote-per-stock mean and top-2 share in the insider study, and a corrected write-up [kvant 8] | 1 | 3 | 3 | S | – | **yes** |
| 7 | Survivorship line computed in the yamls [kvant 9; revisjon] | 1 | 2 | 3 | S | – | done in D20 |
| 8 | Two-way placebo band per cell and family-wise max-z on the page [kvant 4, 5] | 1 | 3 | 3 | M | – | later |
| 9 | Frozen placebo table as a CI test against look-ahead [kvant 11] | 0 | 3 | 1 | M | – | later |
| 10 | Unadjusted bars for chart signals [kvant 12] | 1 | 1 | 1 | M | – | later |
| 11 | Mask `_edge` after a gap [kvant 13] | 0 | 1 | 1 | S | – | **yes** |
| 12 | Calibration: Brier and stated-vs-realised plot [brief] | 2 | 3 | 3 | S | – | done (D21) |
| 13 | References: OSEBX, "price unchanged", consensus [brief] | 3 | 3 | 2 | S | – | done (D21) |
| 14 | Data-health page: stale, gaps, missed dividends, feed ages, reader status [brief; revisjon] | 2 | 2 | 3 | M | – | **yes** |
| 15 | Event calendar: reports, ex-dividend, Norges Bank meetings [brief; cases 16] | 2 | 1 | 1 | M | data terms: public pages | **yes** |
| 16 | View before the report (pre-report item) [brief] | 3 | 3 | 2 | S | – | **yes** |
| 17 | Report-reader dry run on a hand-supplied PDF with candidate lines [brief] | 2 | 2 | 1 | S | – | **yes** |
| 18 | Inception check: a BUY with a kill criterion already triggered needs an acknowledgement and is marked [cases 3] | 3 | 2 | 3 | S | – | **yes** |
| 19 | Shared-kill warning: tag criteria with a driver, warn on overlap between open BUYs [pm 2] | 3 | 1 | 2 | S–M | – | if time |
| 20 | Bear stress across all views with a thesis-correlation slider [pm 3] | 2 | 1 | 3 | M | – | later |
| 21 | Portfolio exposure page (sector, beta to groups) [pm 1] | 2 | 1 | 2 | M | – | later |
| 22 | Loss caps per sector group / driver [pm 4] | 2 | 1 | 1 | S | – | later |
| 23 | Stale-case detector (valuation older than a passed event) [pm 8] | 2 | 2 | 2 | S | – | covered by 16 + report items; badge later |
| 24 | Price reconciliation at entry (book price vs store close) [pm 9] | 1 | 2 | 2 | S | – | later |
| 25 | Template-fingerprint check (identical probabilities across cases) [pm 7] | 1 | 1 | 2 | S | – | later |
| 26 | Correlation matrix with sample-size badges [pm 5] | 1 | 1 | 2 | M | – | later |
| 27 | One generated kill list with a divergence gate [cases 1] | 2 | 2 | 1 | S | Toolkit repo | later (needs the other repo) |
| 28 | Kill-or-signpost test via the what-if runner [cases 2] | 3 | 2 | 2 | M | Toolkit | later |
| 29 | Window and seasonality per criterion [cases 4] | 2 | 2 | 2 | M | – | later |
| 30 | Currency-adjusted KPI capture in the reader [cases 5] | 3 | 2 | 1 | M | – | later |
| 31 | Guidance facts from report text, diffed quarter to quarter [cases 7] | 2 | 1 | 1 | M | – | later |
| 32 | Consensus archive and surprise history [cases 8] | 1 | 2 | 1 | S | – | later |
| 33 | Quarterly reverse-DCF series [cases 13] | 2 | 1 | 1 | S | – | later |
| 34 | Pre-mortem block in the routine [cases 11] | 2 | 0 | 2 | S | Toolkit | later |
| 35 | Real date + data date + stale banner on the front page [student 1] | 2 | 0 | 3 | S | – | **yes** |
| 36 | Summary line and numbered items with "do first / can wait" [student 2, 3] | 3 | 0 | 1 | S | – | **yes** |
| 37 | All-clear state [student 6] | 2 | 0 | 1 | S | – | **yes** |
| 38 | Signals block collapsed with a one-line summary [student 8] | 2 | 0 | 1 | S | – | **yes** |
| 39 | Fix the truncated reason sentence; snapshot test [student 9] | 1 | 0 | 2 | S | – | **yes** |
| 40 | Neutral chips unless the after-cost edge is positive [student 14] | 2 | 0 | 3 | S | – | **yes** |
| 41 | "Log it" deep link per item [student 5] | 2 | 0 | 0 | M | – | later |
| 42 | Language pass and glossary [student 12] | 1 | 0 | 1 | M | – | later |
| 43 | Kill checks written automatically from readings [cases 15] | 1 | 2 | 1 | S | writes to the log without a judgement – against D2 | no |

## Build list for tonight (in order)

1. **Odds and insider statistics made honest** (1–6, 11): the proper t, intervals, three periods, grade, raw vs
   benchmark, corrected insider write-up.
2. **Before the report** (16–18): pre-report item, reader dry run, inception acknowledgement.
3. **Front page for a five-minute visit** (35–40).
4. **Data health page** (14).
5. **Event calendar** (15).
6. **Shared-kill warning** (19) if time remains.

Each on its own branch from the night branch, tests on frozen or synthetic data, full suite green, dashboard opened
and screenshotted, then merged into `natt-2026-11-02`. Nothing goes to `main`.
