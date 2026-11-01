# Night audit: trying to break two findings (1 Nov 2026)

Read-only re-measurement of the signal scorecard and the insider study on the frozen test panel (`testdata.load_panel()`,
adjusted Yahoo daily bars 2010-01-04..2026-10-22, 64 stocks, all survivors; `testdata.load_json("insiders")`, 8,433
NewsWeb notifications, 1,818 classified `buy`). Every number below comes from a script run tonight; the method is stated
next to each table. Nothing in the repository, the home folder or the odds files was changed. No notification text and
nothing from the research book appears here.

Conventions, unless a table says otherwise:

- **Excess** = the stock's return from the open of the session after the signal (or the first session after an insider
  notification) to the close *h* sessions after the signal, minus the equal-weighted mean of the same window over all 64
  stocks (the same definition as `signals.scorecard` and `insiders.study`).
- **t (clustered)** = cluster-robust t of the event-weighted mean, clusters = calendar months of the signal date
  (Liang–Zeger: SE = sqrt(sum over months of (sum of within-month deviations)^2) / n). This is *not* the statistic the
  insider yaml prints (see 2.0).
- **Bootstrap CI** = 2,000 resamples of calendar months with replacement; in each resample the event-weighted mean over
  the drawn months; the 2.5th and 97.5th percentiles.
- **Placebo** = pseudo-signals on random sessions; three designs, explained in 1g.

Signal short names: BO60 / BO20 = breakout above 60/20-day high + volume, H52 = new 52-week high, RiseCh / FallCh =
rising / falling channel entry, GoldX / DeathX = golden / death cross MA 20/60, BD60 = breakdown below 60-day low,
DD10 = drawdown 10 % from 60-day high.

---

## 1. Finding 1 – "signals are a coin flip after a 0.5 % round trip; risk signals carry more information than buy signals"

### 1a. Cost sensitivity (raw return net of the round trip, and the share of events that beat the cost)

Mean raw return minus the round trip, in %, and the share of events whose raw return exceeded the cost. The right-hand
columns give the excess over the universe net of 0.5 %.

| Signal | h | n | raw − 0 | raw − 0.25 | raw − 0.5 | raw − 1.0 | hit (raw > 0.5 %) | hit (raw > 1 %) | excess | excess − 0.5 |
|---|---|---|---|---|---|---|---|---|---|---|
| BO60 | 20 | 3448 | +1.44 | +1.19 | +0.94 | +0.44 | 52.2 | 49.4 | +0.35 | −0.15 |
| BO60 | 60 | 3398 | +5.14 | +4.89 | +4.64 | +4.14 | 59.4 | 58.1 | +1.28 | +0.78 |
| BO20 | 20 | 5470 | +1.47 | +1.22 | +0.97 | +0.47 | 52.4 | 49.9 | +0.22 | −0.28 |
| BO20 | 60 | 5399 | +5.11 | +4.86 | +4.61 | +4.11 | 58.8 | 57.6 | +1.09 | +0.59 |
| H52 | 20 | 5813 | +0.81 | +0.56 | +0.31 | −0.19 | 49.2 | 46.6 | +0.03 | −0.47 |
| H52 | 60 | 5699 | +4.02 | +3.77 | +3.52 | +3.02 | 57.1 | 55.5 | +0.56 | +0.06 |
| RiseCh | 20 | 5996 | +1.43 | +1.18 | +0.93 | +0.43 | 52.8 | 50.3 | +0.26 | −0.24 |
| RiseCh | 60 | 5939 | +4.51 | +4.26 | +4.01 | +3.51 | 58.0 | 56.6 | +0.85 | +0.35 |
| GoldX | 20 | 1914 | +1.35 | +1.10 | +0.85 | +0.35 | 51.1 | 49.0 | +0.03 | −0.47 |
| BD60 | 20 | 5040 | +1.06 | +0.81 | +0.56 | +0.06 | 53.2 | 51.0 | −0.51 | −1.01 |
| BD60 | 60 | 5005 | +5.05 | +4.80 | +4.55 | +4.05 | 58.2 | 57.0 | −0.89 | −1.39 |
| DeathX | 20 | 1917 | +0.47 | +0.22 | −0.03 | −0.53 | 48.9 | 46.6 | −0.54 | −1.04 |
| DD10 | 20 | 5918 | +1.31 | +1.06 | +0.81 | +0.31 | 50.8 | 48.4 | +0.02 | −0.48 |
| FallCh | 20 | 3290 | +1.78 | +1.53 | +1.28 | +0.78 | 51.7 | 50.2 | −0.12 | −0.62 |
| FallCh | 60 | 3239 | +4.00 | +3.75 | +3.50 | +3.00 | 56.5 | 55.5 | −1.37 | −1.87 |

What this says:

- Cost is not what kills the 20-day buy signals: their *excess* is 0.0–0.35 % before any cost, so even at zero cost
  they are a coin flip against the universe (hit rates 47–49 %). At 60 days the three momentum buys keep +0.4 to +0.8 %
  of excess after 0.5 %, and only BO60 (+0.28 %) and BO20 (+0.09 %) keep anything after a 1 % round trip, which is the
  realistic figure for the smaller names.
- The raw columns are large and positive for *every* signal, risk signals included: a stock that broke below its 60-day
  low still returned +5.05 % over the next 60 sessions (BO60: +5.14 %). The whole difference between a buy and a risk
  signal sits in the benchmark window, not in the stock: the universe returned +3.85 % in the 60 sessions after BO60
  signals and +5.94 % after BD60 signals (raw − excess, from the same run). Breakdowns cluster in market dips that
  mean-revert; breakouts cluster after rallies. A reader who takes "RISK −0.9 %" as "the stock falls" is misled; it
  means "lags a survivor-weighted universe that is itself rebounding".
- The hit-rate columns show the same: the share of risk-signal events that beat a 0.5 % cost (53–58 %) is as high as
  for the buys.

### 1b. Horizons 5 / 10 / 20 / 60 / 120 (excess, %, clustered t, month-bootstrap 95 % CI)

| Signal | kind | h5 | h10 | h20 | h60 | h120 |
|---|---|---|---|---|---|---|
| BO60 | BUY | +0.06 (t 0.46) | +0.09 (0.47) | +0.35 (1.32) [−0.20, +0.90] | +1.28 (2.09) [+0.12, +2.57] | +2.46 (2.75) [+0.68, +4.27] |
| BO20 | BUY | +0.04 (0.33) | −0.00 (−0.01) | +0.22 (0.98) [−0.20, +0.67] | +1.09 (2.46) [+0.21, +2.00] | +2.08 (3.21) [+0.80, +3.33] |
| H52 | BUY | −0.01 (−0.09) | −0.02 (−0.16) | +0.03 (0.11) [−0.46, +0.50] | +0.56 (1.06) [−0.39, +1.59] | +0.76 (1.04) [−0.67, +2.21] |
| RiseCh | BUY | +0.01 (0.15) | +0.08 (0.66) | +0.26 (1.55) [−0.08, +0.59] | +0.85 (2.86) [+0.24, +1.45] | +1.49 (3.44) [+0.65, +2.33] |
| GoldX | INFO | +0.27 (2.21) | +0.20 (1.21) | +0.03 (0.14) [−0.41, +0.49] | −0.16 (−0.38) [−0.95, +0.66] | −0.72 (−1.05) [−2.11, +0.59] |
| BD60 | RISK | −0.21 (−1.24) | −0.28 (−1.07) | −0.51 (−1.16) [−1.36, +0.32] | −0.89 (−1.23) [−2.39, +0.49] | −2.62 (−2.68) [−4.46, −0.65] |
| DeathX | RISK | −0.10 (−0.87) | −0.28 (−1.72) | −0.54 (−2.36) [−0.97, −0.12] | −0.41 (−1.02) [−1.22, +0.35] | −0.57 (−0.92) [−1.79, +0.66] |
| DD10 | RISK | −0.04 (−0.64) | +0.03 (0.24) | +0.02 (0.14) [−0.34, +0.37] | +0.09 (0.28) [−0.55, +0.71] | +0.34 (0.74) [−0.59, +1.22] |
| FallCh | RISK | −0.24 (−2.05) | −0.21 (−1.20) | −0.12 (−0.41) [−0.66, +0.41] | −1.37 (−2.87) [−2.31, −0.40] | −3.03 (−3.67) [−4.65, −1.44] |

Quarter clusters (for the 60- and 120-day windows, which span more than one month) lower every |t| a little further
(BO60 h60 1.76, BO20 2.20, RiseCh 2.59, FallCh h60 −2.43, BD60 h120 −2.35) and widen the CIs by 0.1–0.4 points; no
sign changes.

Nothing is there at 5–10 days except GoldX h5 (+0.27 %, t 2.21) – one cell out of 45, see 1g. Whatever the buys have
lives at 60–120 days, i.e. it is 3–6-month momentum in a survivor universe, not a breakout effect. (In the published
odds file t60 = 3.9–4.1 for the breakouts; clustered by month 2.1–2.5, by quarter 1.8–2.2.)

### 1c. Three sub-periods (excess, %, clustered t by month, n)

| Signal | h | 2010–15 | 2016–20 | 2021–26 |
|---|---|---|---|---|
| BO60 | 20 | +1.09 (1.96, 920) | +0.55 (1.04, 1073) | −0.26 (−0.74, 1455) |
| BO60 | 60 | +1.28 (1.81, 917) | +1.20 (1.54, 1074) | +1.36 (1.06, 1407) |
| BO20 | 20 | +0.99 (2.21, 1508) | +0.04 (0.09, 1749) | −0.16 (−0.52, 2213) |
| BO20 | 60 | +1.66 (2.60, 1503) | +1.10 (1.61, 1750) | +0.68 (0.79, 2146) |
| H52 | 20 | +0.45 (1.01, 1231) | +0.42 (0.77, 1742) | −0.40 (−1.22, 2840) |
| H52 | 60 | +1.60 (1.85, 1230) | +0.68 (0.74, 1742) | +0.01 (0.01, 2727) |
| RiseCh | 20 | −0.32 (−1.30, 1497) | +0.41 (1.54, 1792) | +0.48 (1.65, 2707) |
| RiseCh | 60 | +0.18 (0.31, 1497) | +1.65 (3.25, 1792) | +0.68 (1.49, 2650) |
| GoldX | 60 | +1.28 (1.69, 487) | +0.08 (0.11, 592) | −1.21 (−1.71, 803) |
| BD60 | 20 | −1.44 (−2.77, 1419) | +0.09 (0.10, 1691) | −0.35 (−0.48, 1930) |
| BD60 | 60 | −4.79 (−3.85, 1419) | +0.31 (0.25, 1690) | +0.95 (0.97, 1896) |
| BD60 | 120 | −6.83 (−5.31, 1421) | −2.27 (−1.41, 1691) | +0.43 (0.25, 1770) |
| DeathX | 20 | −0.69 (−1.93, 501) | −0.91 (−1.93, 573) | −0.20 (−0.58, 843) |
| DeathX | 60 | −0.36 (−0.52, 501) | −0.26 (−0.34, 573) | −0.56 (−0.85, 828) |
| DD10 | 60 | +0.81 (1.35, 1577) | +0.26 (0.39, 1704) | −0.46 (−1.01, 2586) |
| FallCh | 20 | −0.85 (−1.80, 908) | +0.44 (0.79, 1110) | −0.08 (−0.18, 1272) |
| FallCh | 60 | −2.78 (−3.74, 907) | −1.50 (−1.63, 1111) | −0.20 (−0.27, 1221) |
| FallCh | 120 | −6.36 (−5.94, 907) | −3.10 (−1.78, 1111) | −0.39 (−0.33, 1173) |

- The 20-day buy excess is a 2010–15 phenomenon; in 2021–26 all four buy signals are at or below zero over 20 days.
- The headline risk result is *entirely* 2010–15: BD60 at 60 days is −4.79 % then, and +0.31 % and +0.95 % after. FallCh
  fades −2.78 → −1.50 → −0.20. In 2021–26 no risk signal has |t| above 1.1 at any horizon, and BD60's 60-day excess is
  positive. Only DeathX at 20 days has the same sign in all three periods, and it is small (−0.2 to −0.9 %).
- 2010–15 is also where the survivor bias bites hardest: the 2010–15 breakdowns of stocks that later vanished are not in
  the panel, and the ones that are were, by construction, the ones that recovered or at least survived. Why the
  survivors' breakdowns underperform so strongly in 2010–15 and not later is not something this panel can settle.

### 1d. Leave-one-stock-out (20- and 60-day excess, %)

| Signal | h | full | min (stock out) | max (stock out) | sign flips | most influential stock, its share of the summed excess |
|---|---|---|---|---|---|---|
| BO60 | 20 | +0.35 | +0.18 (NEL) | +0.40 (ARCH) | 0 of 64 | NEL, 50 % |
| BO60 | 60 | +1.28 | +0.97 (SOFF) | +1.42 (FRO) | 0 | SOFF, 25 % |
| BO20 | 20 | +0.22 | +0.12 (NEL) | +0.28 (ARCH) | 0 | NEL, 46 % |
| BO20 | 60 | +1.09 | +0.85 (MPCC) | +1.25 (NAS) | 0 | MPCC, 23 % |
| H52 | 20 | +0.03 | −0.08 (AKER) | +0.09 (ORK) | 9 | – (mean ≈ 0) |
| H52 | 60 | +0.56 | +0.19 (MPCC) | +0.67 (PEN) | 0 | MPCC, 66 % |
| RiseCh | 60 | +0.85 | +0.71 (OET) | +0.95 (HEX) | 0 | OET, 18 % |
| BD60 | 20 | −0.51 | −0.59 (DNO) | −0.33 (BORR) | 0 | BORR, 37 % |
| BD60 | 60 | −0.89 | −1.15 (DNO) | −0.63 (ARCH) | 0 | ARCH, 32 % |
| DeathX | 20 | −0.54 | −0.59 (BWE) | −0.47 (FRO) | 0 | FRO, 15 % |
| FallCh | 60 | −1.37 | −1.54 (HEX) | −0.93 (ARCH) | 0 | ARCH, 34 % |

No signal with a non-trivial mean is a one-stock artefact: the sign survives every single exclusion. But single stocks
move the number a lot: NEL alone is half of the summed 20-day BO60 excess, MPCC two-thirds of H52's 60-day excess, ARCH
a third of the two risk results at 60 days (ARCH's breakdowns and channel exits were followed by its worst spells). A
measurement that prints "+0.35 %" is really "+0.18 % to +0.40 % depending on whether NEL is in the panel".

### 1e. Month-block bootstrap, 95 % intervals

Already in the 1b table (brackets). Summary of which intervals exclude zero, 2,000 month resamples:

- 20 days: **none of the four buy signals**; of the risk signals only DeathX (−0.54 %, [−0.97, −0.12]).
- 60 days: BO60 [+0.12, +2.57], BO20 [+0.21, +2.00], RiseCh [+0.24, +1.45] exclude zero on the buy side; FallCh
  [−2.31, −0.40] on the risk side; BD60 [−2.39, +0.49] does not.
- 120 days: the same three buys, BD60 and FallCh.
- With quarter blocks: identical set, intervals 0.1–0.4 points wider.

### 1f. Does "risk signals carry more information than buy signals" survive (b)–(e)?

Counting cells at 20/60/120 days with the bootstrap CI excluding zero: buys 6 of 12 (all at 60–120 days), risks 4 of 12
(DeathX 20, FallCh 60/120, BD60 120; FallCh 5 would be a fifth if the 5-day horizon counted). Mean |t| (clustered by
month) over the 20/60/120-day cells: BUY 1.91, RISK 1.46; at 20 days alone BUY 0.99, RISK 1.02. By sub-period at
60 days, the number of signals with |t| > 2: buys 1/1/0, risks 2/0/0 (2010–15 / 2016–20 / 2021–26); the largest |t|
at any horizon in 2021–26 is 1.65 for a buy and 1.08 for a risk signal. The 20-day comparison in the docstring ("no buy
signal has an edge after costs over 20 sessions; the sell-side signals carry more information") is true as a statement
about 2010–2026 point estimates (−0.5 % for BD60 and DeathX vs +0.0 to +0.35 % for the buys), but:

- at 20 days only DeathX's interval excludes zero, and only just;
- the larger risk numbers (BD60, FallCh at 60–120 days) are a 2010–15 result that has not been seen since 2016;
- in the most recent five years neither family carries measurable information at any horizon;
- the risk family's excess is, in raw terms, a stock that *rises* less than a rebounding survivor universe.

So the claim **weakens to**: "over 2010–2026 the point estimates for the risk signals are more negative than the buys'
are positive at 20 days, but the two families are statistically indistinguishable, and the risk edge has faded to zero
since 2016".

### 1g. Multiple testing: is the best-looking cell noise?

Setup: 9 signals × 3 horizons (10 / 20 / 60) × 2 metrics (mean excess, hit rate) = 54 cells. For each signal, 500
placebo frames were drawn and the same 54 cells computed; a cell's z is (real − placebo mean) / placebo sd; the
family-wise statistic is the largest |z| in the table, compared with the largest |z| of each placebo replicate scored
against the other 499. Three placebo designs:

- **strict** – the same count per (stock, month), random sessions within the stock-month. *Not usable as a null*: a
  stock-month that contains a breakout is a month in which the stock rallied, and a random session in it inherits that
  rally – the strict placebo for BO60 has a 10-day excess of +3.24 % (band [+3.01, +3.45]), for H52 +2.89 % at 20 days,
  and for BD60 −3.69 %. Against it every real signal is "worse than random" with |z| 6–35, which only says that the
  signal day comes late in the move. Reported so nobody builds this one.
- **loose** – the same count per month, any stock. Centred on 0.00 % everywhere (it is the universe by construction).
- **two-way** – the same count per month and per stock in expectation (multinomial over valid stock-months), random
  sessions within the cell. Keeps the stock mix and the market timing of each signal, drops the day. The fair null.

| Signal | h | real mean | two-way placebo mean [band] | z mean | pct | z hit | loose z mean |
|---|---|---|---|---|---|---|---|
| BO60 | 20 | +0.35 | +0.05 [−0.31, +0.40] | +1.72 | 96 | +1.05 | +2.02 |
| BO60 | 60 | +1.28 | +0.15 [−0.40, +0.74] | **+3.76** | 100 | +3.23 | +4.26 |
| BO20 | 20 | +0.22 | +0.03 [−0.21, +0.28] | +1.36 | 91 | +1.95 | +1.70 |
| BO20 | 60 | +1.09 | +0.05 [−0.41, +0.56] | **+4.10** | 100 | +3.69 | +4.41 |
| H52 | 60 | +0.56 | +0.20 [−0.15, +0.63] | +1.71 | 95 | +0.95 | +2.38 |
| RiseCh | 20 | +0.26 | +0.01 [−0.22, +0.28] | +1.96 | 97 | +1.98 | +2.02 |
| RiseCh | 60 | +0.85 | +0.06 [−0.34, +0.52] | **+3.63** | 100 | +1.65 | +4.08 |
| GoldX | 10 | +0.20 | −0.05 [−0.36, +0.27] | +1.55 | 95 | +1.60 | +1.18 |
| BD60 | 20 | −0.51 | −0.33 [−0.65, −0.01] | −1.05 | 15 | −0.68 | −3.25 |
| BD60 | 60 | −0.89 | −0.60 [−1.21, −0.03] | −1.01 | 16 | −0.78 | −3.33 |
| DeathX | 20 | −0.54 | −0.06 [−0.53, +0.41] | −2.08 | 2 | −2.35 | −2.47 |
| DD10 | 60 | +0.09 | −0.11 [−0.57, +0.34] | +0.86 | 80 | −1.12 | +0.44 |
| FallCh | 20 | −0.12 | −0.19 [−0.61, +0.21] | +0.35 | 65 | +0.28 | −0.63 |
| FallCh | 60 | −1.37 | −0.52 [−1.26, +0.17] | −2.31 | 1 | −0.14 | −4.40 |

Family-wise result (two-way null): the best real cell has |z| = 4.10 (BO20, 60 days, mean); the largest |z| in a
placebo table is 2.40 in the median replicate and 3.18 at the 95th percentile; **1 of 500 placebo tables beat the real
best cell (P = 0.002)**. 11 of 54 cells lie outside their placebo 95 % band against ≈ 2.7 expected under noise: BO60
60 d (mean, hit), BO20 60 d (mean, hit), BO20 20 d (hit), RiseCh 60 d (mean), RiseCh 20 d (hit), DeathX 10 d (hit),
DeathX 20 d (mean, hit), FallCh 60 d (mean). Under the loose null 23 cells are outside the band and P = 0.002 as well.

Two consequences:

- **The best-looking cell is not noise – but it is the 60-day momentum cell, not a 20-day one, and not a risk one.** No
  20-day buy cell is outside the two-way band on the mean metric. BD60, the risk signal the docstring leans on, is inside
  the two-way band at 10, 20 and 60 days (pct 15–22): stocks that break down often are the period's losers, and a random
  day in those stocks in those months already yields −0.6 % over 60 days. What remains of the risk family after the
  stock mix is taken out is DeathX at 20 days (−0.54 % vs −0.06 %, z −2.1) and FallCh at 60 days (z −2.3) – each a
  single cell at the edge of the band in a table of 54.
- **The month-clustered t is itself overconfident when a signal concentrates in a few stocks.** The largest month-
  clustered |t| in a *random* two-way table is 2.77 in the median replicate and 4.07 at the 95th percentile, so the real
  table's maximum of 2.87 is nothing special by that yardstick (P = 0.44). The stock margin introduces dependence that
  month clusters do not see. Clustering two ways (month and stock, Cameron–Gelbach–Miller) lowers the real t's: BO60
  60 d 2.09 → 1.92, BO20 2.46 → 2.24, RiseCh 2.86 → 2.04, FallCh 60 d −2.87 → −1.88, the 120-day cells from 2.7–3.7 to
  2.1–2.5; insiders at 250 days 2.19 → 1.46. The z-against-placebo in the table above is the statistic that already
  accounts for this.

For GoldX at 5 days (the only 5–10-day cell with t > 2 in 1b): its 10-day cell is at the 95th percentile of the
two-way placebo, and with 45–54 cells one such cell is expected; it is noise until it repeats out of sample.

### 1h. Look-ahead in `signal_frames` / `indicators`

Checked by reading the code and by a truncation test: every indicator and every signal frame was recomputed on the panel
cut at session 3,000 (of 4,219) and compared with the full-panel values on the overlap. **All differences are exactly
0.0** for `hi60`, `lo60`, `vol20`, `ma20`, `ma60`, `dd60`, `rsi`, `channel_slope`, and 0 differing cells in all nine
signal frames. Nothing uses a future bar. Details:

- `hi20/hi60/hi250/lo60`: `rolling().max().shift(1)` – yesterday's trailing extreme; a close above it is a genuine
  breakout. Entry at the next open (`opens.shift(-1)`), exit at `C.shift(-h)`; the benchmark is the same window. Fine.
- `rsi`: `ewm(adjust=False)` on `diff()` – causal. Only used in the detail text, not in any signal.
- `channel_slope`: rolling regression over the last 120 closes including today – causal (and identical under truncation).
- Volume confirmation: `vol20 = V.rolling(20).mean()` *includes the signal day's volume*. Not look-ahead (known at the
  close) but it makes the filter stricter than "1.5× the prior average" (equivalent to 1.54× the prior 19 days). With
  `vol20.shift(1)` BO60 has 3,645 events instead of 3,465 and the same excess (+0.34 / +1.24 % vs +0.35 / +1.28 % at
  20 / 60 days). Without the volume filter the breakouts have 9,948 / 15,982 events and excess of only +0.05 / +0.31 %
  (BO60) and +0.01 / +0.38 % (BO20) at 20 / 60 days: the volume filter is doing all the work, which is worth knowing.
- `_edge`: `state & ~state.shift(1).fillna(False)` – on the first session an indicator exists (or after a hole in the
  data) yesterday's state is "unknown", treated as False, so an edge fires if the state is already true: 25 of 6,034
  RiseCh events, 19 of 3,313 FallCh, 54 of 5,979 DD10 (< 1 %). Harmless, but a `.shift(1)` NaN should mask the edge.
- Delaying entry by one more session (open of day +2) changes nothing (BO60 +1.28 → +1.23 % at 60 days; FallCh −1.37 →
  −1.32 %), so no result depends on an unattainable fill. The overnight gap from the signal close to the entry open is
  +0.1 to +0.3 % and is correctly excluded.
- Bars are internally consistent after adjustment: 0 of 224,122 bars with close or open outside [low, high]. 1,977 flat
  bars (high = low), 1,237 zero-volume sessions, 1,655 missing sessions after a stock's first bar (holes in Yahoo's
  history); the comparisons treat NaN as False, so a hole can only lose a signal, never create one.
- Two things the code cannot see and that *are* look-ahead in a wider sense: (i) the panel is **dividend-adjusted**, so
  a "52-week high" on it is not the 52-week high a chartist saw at the time (past prices are scaled down by every later
  dividend, making a new adjusted high easier than a new raw high); the effect cannot be measured without unadjusted
  bars; (ii) the universe is today's 64 names, chosen with knowledge of who survived to 2026 – the largest single
  forward-looking choice in the whole exercise.

### Verdict on Finding 1

**The "coin flip after costs" half stands, and is if anything understated: at 20 days the buy signals have no excess
before costs either (0.0–0.35 %, every bootstrap interval covers zero, and in 2021–26 all four are negative).** What
the buys do have is a 60–120-day excess of +0.6 to +2.5 % that survives month, quarter and month+stock clustering
(t 1.9–2.2 two-way at 60 days), survives leaving any one stock out, sits outside the two-way placebo band (the best
cell, BO20 60 d, is beaten by 1 of 500 random tables) and keeps +0.3 to +0.8 % after a 0.5 % round trip – but it is
3–6-month momentum in a survivor-only, equal-weighted universe, it is fading (BO20 60 d: +1.66 / +1.10 / +0.68 % across
the three periods), and single names move it a lot (NEL, MPCC, SOFF). **The "risk signals carry more information" half
weakens substantially**: the two large risk results (BD60, FallCh) are 2010–15 results, nothing in the risk family has
|t| > 1.1 in 2021–26, BD60's 60-day interval covers zero over the whole sample and BD60 sits *inside* the two-way placebo
band at every horizon (its negative excess is the stock mix, not the day), and in raw terms a stock that triggers a risk
signal still rose ~4–5 % over the next 60 sessions. The honest one-liner is "neither family predicts anything over
20 days; the buys show fading 3–6-month momentum; the risk signals showed something before 2016 and nothing since".

---

## 2. Finding 2 – insider buys: "median negative, mean positive and carried by the top 5 %; +1.9 % (2010–17) vs −0.2 % (2018–26) at 60 days"

Events reproduced from `insiders.events` on the frozen panel: 1,585 buy events (one per stock and day), 61 stocks;
1,560 / 1,538 / 1,510 / 1,462 with a complete 20 / 60 / 120 / 250-session window; means +0.23 / +0.70 / +1.58 /
+5.51 %, medians −0.29 / −0.24 / −1.00 / −3.55 % – identical to `insider_study.yaml`.

### 2.0 First, a statistic that does not match its mean

`insider_study.yaml` prints `t_month` 1.29 / 2.41 / 2.67 / 2.81. That t is computed on **one average per calendar
month, each month weighted equally**, which is a test of a different number than the mean printed beside it:

| h | event-weighted mean (printed) | mean of the ~200 monthly means | t of the monthly means (printed) | cluster-robust t of the event-weighted mean |
|---|---|---|---|---|
| 20 | +0.23 % | +0.47 % | 1.29 | 0.62 |
| 60 | +0.70 % | +1.98 % | 2.41 | 0.88 |
| 120 | +1.58 % | +4.29 % | 2.67 | 1.25 |
| 250 | +5.51 % | +8.36 % | 2.81 | 2.19 |

The 28 months with only 1–2 buy events (14 % of months) have a mean 60-day excess of +6.3 % (+18 % at 120 days, +22 %
at 250); the 59 months with 10 or more events average +0.3 % (60 d). Equal month weights hand those thin months a
seven-times-larger vote than they have in the event-weighted mean. Either number is legitimate, but a table should not
pair the mean of one weighting with the t of another. Read with the matching t, the 20-, 60- and 120-day means are
0.6–1.3 standard errors from zero.

### 2a. Winsorised and trimmed means (excess, %)

| h | n | mean | median | hit | winsorised 1 % | winsorised 5 % | trimmed 1 % | trimmed 5 % | top 5 % of events as share of the sum |
|---|---|---|---|---|---|---|---|---|---|
| 20 | 1560 | +0.23 | −0.29 | 48.8 | +0.06 | −0.03 | +0.01 | −0.06 | 517 % |
| 60 | 1538 | +0.70 | −0.24 | 49.0 | +0.40 | +0.05 | +0.25 | −0.14 | 378 % |
| 120 | 1510 | +1.58 | −1.00 | 47.5 | +0.84 | +0.06 | +0.39 | −0.55 | 293 % |
| 250 | 1462 | +5.51 | −3.55 | 45.3 | +3.87 | +0.97 | +2.35 | −1.02 | 186 % |

Capping the extreme 1 % on each side halves the mean at every horizon; capping 5 % removes it entirely (+0.05 % at
60 days). The trimmed 5 % mean is negative at every horizon. The study's own sentence – "carried by a small number of
very large winners" – is exactly right; the numbers above make it quantitative: the positive mean is the top 1–5 % of
events and nothing else.

### 2b. By stock

| h | summed excess | stocks with a positive mean | median of the 61 stock means | top contributors (events, mean, share of the sum) | mean after dropping the top-2 / top-5 stocks by contribution | mean of stock means (one vote per stock) |
|---|---|---|---|---|---|---|
| 60 | 10.78 | 29 of 61 | −0.53 % | AKRBP (47, +17.4 %, 76 %), NOD (53, +12.7 %, 62 %), PROT (92, +3.8 %, 33 %), KID (30, +8.1 %, 23 %), HEX (27, +6.3 %, 16 %) | **−0.29 % / −0.91 %** | −0.23 % |
| 250 | 80.58 | 28 of 61 | −1.15 % | AKRBP (47, +69.2 %, 40 %), MPCC (46, +58.5 %, 33 %), PROT (84, +29.7 %, 31 %), NOD (48, +30.5 %, 18 %), BWLPG (32, +32.4 %, 13 %) | +1.54 % / −2.39 % | +5.37 % |

Leave-one-stock-out range at 60 days: +0.17 % (AKRBP out) to +0.93 % (BWO out); at 250 days +3.40 % (AKRBP out) to
+6.62 % (BWO out). The 60-day mean is two stocks: insiders at Aker BP and Nordic Semiconductor bought before big runs,
and the other 59 stocks net to −0.29 %. The 250-day mean is broader (the mean of stock means is +5.4 %) but still
29 of 61 stocks have a negative mean, and it also rests on the two largest shipping and oil winners of the period. The
top five stocks by *event count* (PROT, ORK, TOM, NOD, STB) hold 21 % of all events.

### 2c. By size of the buy

The notification bodies are in the frozen copy, so a size was parsed from them (share count after a buy verb × the
first price mentioned; aggregated per event; no text is reproduced here). Parsed for 1,229 of 1,585 events; the value
quantiles are 93 k / 190 k / 498 k / 2.1 M / 13.8 M NOK (10/25/50/75/90 %). Terciles among the parsed events, excess
in %, clustered t, month-bootstrap CI of the mean:

| h | small (≤ ~0.25 M) | mid | large (≥ ~1.1 M) | unparsed (356) |
|---|---|---|---|---|
| 20 | +0.55 (t 0.71) [−0.78, +2.45] | +0.38 (0.77) [−0.51, +1.37] | +0.38 (0.65) [−0.75, +1.46] | −0.50 (−0.93) |
| 60 | +1.37 (1.05) [−0.92, +4.04] | +2.55 (2.42) [+0.59, +4.72] | −0.18 (−0.12) [−3.11, +2.58] | −1.23 (−1.12) |
| 250 | +7.79 (1.83) [−0.26, +16.51] | +11.80 (2.72) [+3.78, +20.39] | +5.87 (1.30) [−2.35, +15.49] | −4.79 (−1.39) |

Buys of 1 MNOK or more (421 events): −0.16 % at 60 days, +5.40 % at 250 (median −4.3 %); buys of 5 MNOK or more (214):
−1.22 % and +4.51 %. There is **no size gradient in the direction the "insiders know" story needs**: the largest buys do
worst at 60 days and no better than the small ones at 250. The mid tercile looks best, which is what noise looks like
with three bins. The unparsed third (older or free-form notifications) is negative everywhere, so the parsed subset is
not a random subset; the parse is crude and this table is indicative only.

### 2d. Month-block bootstrap intervals (2,000 resamples of months; median and trimmed mean with 500)

| h | mean [CI] | median [CI] | trimmed-5 % mean [CI] |
|---|---|---|---|
| 20 | +0.23 [−0.51, +0.96] | −0.29 [−0.78, +0.39] | −0.06 [−0.66, +0.52] |
| 60 | +0.70 [−0.82, +2.28] | −0.24 [−1.43, +0.70] | −0.14 [−1.22, +1.19] |
| 120 | +1.58 [−0.79, +4.23] | −1.00 [−3.05, +1.14] | −0.55 [−2.35, +1.45] |
| 250 | +5.51 [+0.93, +10.61] | −3.55 [−7.32, −0.34] | −1.02 [−4.05, +2.48] |

Sub-periods, mean [CI], clustered t:

| period | h20 | h60 | h120 | h250 |
|---|---|---|---|---|
| 2010–17 (640) | +0.37 [−0.60, +1.58] | +1.90 [−0.20, +4.18] t 1.65 | +0.63 [−2.40, +3.92] | +2.21 [−4.03, +9.03] |
| 2018–26 (920) | +0.13 [−0.82, +1.10] | −0.16 [−2.25, +1.89] t −0.15 | +2.29 [−1.11, +6.27] | +8.09 [+1.52, +15.84] t 2.25 |
| 2010–15 (475) | +0.42 | +2.55 [−0.28, +5.29] | +2.08 | +4.44 [−3.64, +13.59] |
| 2016–20 (529) | −0.57 | −1.42 [−3.98, +1.38] | +0.84 | +9.27 [+0.52, +20.32] |
| 2021–26 (556) | +0.82 [−0.20, +1.76] | +1.16 [−0.71, +3.03] | +1.89 | +2.26 [−4.27, +8.75] |

Only the 250-day mean has an interval that excludes zero, and at that horizon the *median* interval is entirely negative.
The "+1.9 % vs −0.2 %" sub-period contrast at 60 days is two numbers whose intervals overlap almost completely
([−0.20, +4.18] vs [−2.25, +1.89]); it is not evidence that something changed in 2018.

### 2e. Placebo pseudo-events (1,000 replicates each)

Three designs, each with 1,585 pseudo-events:

- **two-way**: the same number of events per calendar month *and* per stock (in expectation; cells drawn as a
  multinomial over valid stock-months, then random sessions within the cell). This is the fair null: it keeps "insiders
  at PROT, ORK, TOM buy often" and "2020 had many buys" but not *which day*.
- **loose**: the same count per month, any stock.
- **strict**: the same count per (stock, month). Reported for completeness but **not a null**: a random session in a
  month in which an insider bought inherits that month's move (insiders buy into declines, so the strict placebo is
  negative at 20 days, −0.26 %, and the real result looks good against it for the wrong reason). The same leak makes
  the strict placebo for breakout signals absurdly *positive* (+3.3 % at 10 days, see 1g).

| h | real mean | two-way placebo mean [2.5, 97.5] | z | percentile | real median vs two-way median band | real trimmed-5 % vs band |
|---|---|---|---|---|---|---|
| 20 | +0.23 | +0.10 [−0.39, +0.61] | +0.47 | 69 | −0.29 vs −0.32 [−0.75, +0.11], z +0.14 | −0.06 vs [−0.54, +0.30], z +0.28 |
| 60 | +0.70 | +0.27 [−0.67, +1.24] | +0.91 | 82 | −0.24 vs −0.57 [−1.33, +0.25], z +0.81 | −0.14 vs [−1.05, +0.53], z +0.30 |
| 120 | +1.58 | +0.76 [−0.66, +2.23] | +1.12 | 86 | −1.00 vs −1.08 [−2.26, +0.13], z +0.12 | −0.55 vs [−1.67, +0.67], z −0.01 |
| 250 | +5.51 | +1.55 [−0.85, +4.27] | **+2.96** | **99** | −3.55 vs −4.71 [−6.76, −2.59], z +1.13 | −1.02 vs [−3.95, +0.03], z +0.96 |

Loose placebo (any stock, same months): z for the mean +0.85 / +1.50 / +2.18 / +4.24 at 20 / 60 / 120 / 250 days;
its band is centred on 0.00 % at every horizon, so the two-way placebo's positive centre (+1.55 % at 250 days) is the
contribution of *which stocks* insiders happen to be in – about a quarter of the 250-day mean comes from the stock mix
alone.

Reading: at 20–120 days the insider mean sits inside the two-way placebo band (percentiles 69–86). At 250 days the mean
is outside the band (99th percentile), but the median and the trimmed mean are not (z 1.1 and 1.0). The only thing that
distinguishes insider buys from random days in the same stocks and months is the upper tail of 250-day outcomes.

### 2f. Excluding the first five sessions after publication

The first five sessions themselves (entry open to the close of session 5): mean −0.05 %, median −0.10 %, t −0.25.
There is no immediate reaction to buy into or to miss. Measured from the close of session 5 to the close of session h:

| h | mean [CI] | median | trimmed-5 % | hit | clustered t | two-way placebo percentile |
|---|---|---|---|---|---|---|
| 20 | +0.23 [−0.25, +0.77] | −0.13 | −0.03 | 49.4 | 0.86 | 77 |
| 60 | +0.61 [−0.77, +2.10] | −0.39 | −0.11 | 49.1 | 0.86 | 80 |
| 120 | +1.42 [−0.84, +3.91] | −1.56 | −0.64 | 47.2 | 1.18 | 85 |
| 250 | +5.32 [+0.77, +10.10] | −3.00 | −1.12 | 45.7 | 2.22 | 99 |

Nothing changes: no delayed reaction, no front-loaded one.

### Verdict on Finding 2

**The claim as written stands – and the strengthened reading of it is harsher than the write-up.** Median negative at
every horizon: confirmed, and the 250-day median's bootstrap interval is entirely below zero. Mean positive and carried
by the top 5 %: confirmed and quantified – winsorising 5 % or trimming 5 % removes the mean at every horizon; at
60 days the mean is two stocks (AKRBP, NOD) and the other 59 net to −0.29 %; a one-vote-per-stock mean is −0.23 %. The
sub-period contrast (+1.9 % vs −0.2 %) is real as point estimates but its intervals overlap almost completely, so it
should not be told as "it worked until 2017". What *falls* is the statistical dressing: the yaml's t of 2.41 at 60 days
is the t of a month-weighted mean (+1.98 %) that is almost three times the event-weighted mean it is printed beside;
the matching cluster-robust t is 0.88, the bootstrap interval is [−0.82, +2.28], and the two-way placebo puts the real
60-day mean at the 82nd percentile of random days in the same stocks and months. The one survivor is the 250-day
mean (+5.5 %, placebo percentile 99, CI [+0.9, +10.6], but a month+stock two-way clustered t of only 1.46) – an
upper-tail, survivor-universe, two-stock-heavy number that no one can harvest with a median of −3.6 %. Size of the buy does not help (large buys do worst at 60 days). Excluding
the first five sessions changes nothing.

---

## 3. Ideas for making the measurement stricter in the tool

Each: what it solves, how we know it works, effort (S < half a day, M = a day or two, L = a week).

1. **One weighting, one t.** `insiders.study` prints an event-weighted mean next to a month-weighted t. Print the
   cluster-robust t of the event-weighted mean (the `tclust` used tonight: SE = sqrt(sum over months of (sum of
   within-month deviations)^2) / n), and if the monthly-means statistic is kept, print its own mean next to it. Same
   function for `signals.scorecard`, replacing the naive `t{h}`. *Solves:* the 2.41-vs-0.88 mismatch. *Test:* on the
   frozen panel the yaml's 60-day buy row must read mean +0.70 %, t 0.88; a synthetic panel with iid returns must give
   |t| > 2 in about 5 % of cells. *Effort S.*

2. **Bootstrap interval on every badge.** Store `ci_lo/ci_hi` (2,000 month resamples, as in 1b/2d) in `signal_odds.yaml`
   and `insider_study.yaml`, and render "exc +0.35 % [−0.20, +0.90]" instead of "exc +0.35 %" in the alert line and
   the stock page. *Solves:* a point estimate that reads as a fact. *Test:* the interval for BO60 h20 must contain zero
   and the one for BO60 h60 must not; a deterministic seed makes the yaml reproducible. *Effort S* (the sums-and-counts
   bootstrap runs in milliseconds per cell).

3. **Odds per sub-period, and a "last 5 years" column first.** Add `periods: {2010-15, 2016-20, 2021-26}` with mean,
   n and clustered t per signal and horizon, and show the most recent period in the alert text before the full-sample
   number. *Solves:* BD60's −0.9 % that is really −4.8 % / +0.3 % / +1.0 %. *Test:* the yaml's 2021–26 cell for BD60
   h60 must be positive (+0.95 %), and a change of the period boundaries must change only those cells. *Effort S.*

4. **A placebo band next to each odds number.** Keep the two-way placebo (same count per month and per stock, random
   sessions) as the null: 500 replicates per signal, store the 2.5/97.5 band and the real percentile for mean excess
   and hit rate. Show "inside the placebo band" / "outside" rather than a t. Do *not* use the stock-month-matched
   placebo (1g, 2e). *Solves:* benchmark-window and stock-mix effects that a t against zero cannot see; it also doubles
   as the multiple-testing control (idea 5). *Test:* for a frame of truly random signals, the real percentile must be
   uniform over replicates; the two-way placebo for insiders must centre on ≈ +1.5 % at 250 days as tonight. *Effort M*
   (the ranking trick in tonight's script samples one 4219×64 placebo in 50 ms).

5. **Family-wise honesty: report the max-|z| of the whole table against its placebo distribution.** With 54 cells, the
   best one will look good; print "best cell z = x; a table of random signals beats it y % of the time" at the top of the
   signal page. *Solves:* the GoldX-h5-type cell. *Test:* the number from 1g must be reproduced from the yaml. *Effort S*
   once idea 4 exists.

6. **A stability grade per signal and horizon (A–D) from four binary checks**: (i) same sign of the mean excess in all
   three sub-periods, (ii) month-bootstrap interval excludes zero, (iii) no single stock carries more than a third of
   the summed excess (|share| ≤ 1/3), (iv) outside the two-way placebo 95 % band. A = 4 of 4, B = 3, C = 2, D = 0–1.
   Computed from tonight's tables:

   | Signal | 20 d: (i) (ii) (iii) (iv) → grade | 60 d: (i) (ii) (iii) (iv) → grade |
   |---|---|---|
   | BO60 | no, no, no (NEL 50 %), no (pct 96) → **D** | yes, yes, yes (SOFF 25 %), yes → **A** |
   | BO20 | no, no, no (NEL 46 %), no (91) → **D** | yes, yes, yes (MPCC 23 %), yes → **A** |
   | H52 | no, no, no, no → **D** | yes, no, no (MPCC 66 %), no (95) → **D** |
   | RiseCh | no, no, yes (ARCH 22 %), no (97) → **D** | yes, yes, yes (OET 18 %), yes → **A** |
   | GoldX | no, no, no, no → **D** | no, no, no, no → **D** |
   | BD60 | no, no, no (BORR 37 %), no (15) → **D** | no, no, yes (ARCH 32 %), no (16) → **D** |
   | DeathX | yes, yes, yes (FRO 15 %), yes (pct 2) → **A** | yes, no, no (ARCH 46 %), no (26) → **D** |
   | DD10 | no, no, no, no → **D** | no, no, no, no → **D** |
   | FallCh | no, no, no (FRO 89 %), no (65) → **D** | yes, yes, no (ARCH 34 %), yes (1) → **B** |

   The grade says "stable and distinguishable", not "large": DeathX's A at 20 days is a −0.54 % effect, which is why the
   badge should print the grade *and* the interval. *Solves:* the alert line needs one word, not six numbers; a D next to
   "+0.35 %" ends the discussion. *Test:* the grade is a pure function of yaml fields with a unit test per rule; the
   table above is the fixture. *Effort S* after ideas 2–4.

7. **Show the raw return and the benchmark window next to the excess.** "+5.05 % raw, universe +5.94 %, excess −0.89 %"
   for a BD60 alert. *Solves:* the reader who thinks a RISK signal means the stock fell. *Test:* raw − excess must equal
   the EW universe return over the same window to 1e-12 on the frozen panel. *Effort S.*

8. **Trimmed mean and one-vote-per-stock mean in the insider table.** Add `trimmed_5`, `winsor_1`, `mean_of_stock_means`
   and `top2_stocks_share` to `insider_study.yaml` and to the stock-page line ("60 d: mean +0.7 %, trimmed −0.1 %, two
   stocks carry it"). *Solves:* the mean/median split is otherwise an unexplained oddity. *Test:* the frozen panel
   reproduces −0.14 % / −0.23 % at 60 days. *Effort S.*

9. **A survivorship line in both yamls, computed, not asserted.** Store the mean excess restricted to the 38 stocks with
   bars on 2010-01-04 and the share of events in stocks listed after 2015; show the ratio to the full-sample figure.
   *Solves:* every reader asks it; the parent's own check (20-day excess shrinks to +0.1–0.2 %) deserves a permanent
   home. *Test:* a stock added to the universe must change the "post-2015 share" field and nothing else. *Effort S.*
   (The real fix – a point-in-time universe with delisted names – is *L* and needs a data source the project does not
   have.)

10. **Cluster two ways (month and stock), and by quarter for long windows.** A 60- or 120-day window spans 3–6 months,
    so month clusters still overlap (quarter clustering lowers the 60-day |t| by 10–15 %, 1b); and a signal that fires
    repeatedly in the same few stocks carries stock-level dependence that month clusters miss – a *random* two-way
    placebo table reaches a month-clustered max |t| of 2.77 in the median replicate (1g). Use the Cameron–Gelbach–Miller
    two-way variance (V_month + V_stock − V_month×stock), with the time cluster = ceil(h / 21) months. On the frozen
    panel this takes BO20 60 d from 2.46 to 2.24, RiseCh 2.86 → 2.04, FallCh −2.87 → −1.88, insiders 250 d 2.19 → 1.46.
    *Solves:* over-confidence at long horizons and in concentrated signals. *Test:* with one stock the two-way t must
    equal the month t; with h = 20 the time cluster must equal the month. *Effort S.*

11. **Freeze a "placebo table" in `tests/`.** A synthetic panel with iid log-returns and the real signal counts must
    produce |t| > 2 in 4–6 % of the 45 cells and zero stability grades above C; run it in CI. *Solves:* any future change
    that leaks the future (a wrong `shift`) shows up as a table full of A grades. *Test:* it is the test. *Effort M.*

12. **Unadjusted bars for the chart signals.** Store Yahoo's unadjusted close/high/low (the recorder has them) and
    compute `hi250` / `lo60` on them, with returns still total-return. *Solves:* 1h(i), "52-week high" on a dividend-
    adjusted series is not the chart a human saw. *Test:* for a stock with a large dividend inside the window the two
    frames must differ on the ex-date week and agree elsewhere. *Effort M.*

13. **Mask `_edge` after a NaN** (`state.shift(1).isna()` → no edge). *Solves:* 98 phantom entries in 1h. *Test:* a
    frame that starts True must produce no edge on its first row. *Effort S.*

---

## Appendix: scripts (in the session scratchpad, not in the repository)

`sig_core.py` (event tables, cost grid, horizons, sub-periods, LOSO, month/quarter bootstrap), `sig_placebo.py`
(three placebo designs × 500 replicates, cell statistics, max-|z|), `ins_core.py` (insider events, trimmed means,
by stock, size parse, bootstrap, placebos × 1,000, 5-session split), plus two inline checks (month-means vs clustered t;
look-ahead truncation test). All read `testdata.load_panel()` / `load_json("insiders")` and import `osloquant.signals`
and `osloquant.dashboard.insiders` unchanged.
