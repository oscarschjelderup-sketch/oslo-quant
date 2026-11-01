# Did primary-insider buys predict returns on Oslo Børs, 2010–2026?

Measured 23 Oct 2026 on the oslo-quant store (prices to 22 Oct 2026) with `oq insiders study`; statistics corrected
2 Nov 2026 after the night audit (see "Correction" below). The numbers are in
`src/osloquant/resources/insider_study.yaml`; a test reproduces them from a frozen copy of the data.

## Answer

**No – not in a way you can act on, and the first version of this page overstated what was there.** The typical
insider buy was followed by a slightly *worse* return than the 64 stocks: the median excess return is negative at
every horizon from 20 to 250 sessions, fewer than half the buys beat the universe, and the trimmed mean (5 % off each
tail) is negative at every horizon. The *average* is positive and grows with the horizon (+0.7 % over 60 sessions,
+5.5 % over 250), but it is carried by a handful of large winners in two stocks: the two largest stocks account for
more than the whole sum at 20 and 60 sessions, one vote per stock gives −0.2 %, and the 95 % interval covers zero at
every horizon except 250 sessions. Insider sells were followed by nothing measurable.

The positive average is also flattered by survivorship: the universe is today's 64 stocks, so companies that fell out
of the exchange after insiders bought are missing.

## Correction (2 Nov 2026)

The first version printed, next to each event-weighted mean, a t-statistic of the mean of *monthly means* (60
sessions: t 2.41). That statistic belongs to a different number (+1.98 % – the average of 198 monthly averages, 28 of
them months with one or two events), not to the +0.70 % beside it. The cluster-robust t of the printed mean, with
clusters on time blocks and on stock, is **0.72**. The "+1.9 % in 2010–17 vs −0.2 % in 2018–26" contrast was also
reported as if it meant something; the bootstrap intervals of the two halves overlap almost entirely. Both are
withdrawn. The yaml now carries, per horizon: the two-way clustered t, a month-bootstrap interval, the trimmed and
winsorised means, one vote per stock, and the share of the sum in the two largest stocks.

## Data

- **Source:** Oslo Børs NewsWeb, category 1102 ("Meldepliktig handel for primærinnsidere"), every notification for
  the 64 stocks from 1 Jan 2010 to 22 Oct 2026: 8,433 notifications. Private use only, so the notifications stay in
  a local cache. This file holds only aggregate numbers.
- **Classification** from the notification text (`dashboard/insiders.py`), in this order:
  - `company`: the company trading its own shares (2,818);
  - `programme`: share programmes, options, awards and dividend reinvestment (2,829);
  - `other`: loans, pledges, TRS and other derivatives, gifts, transfers and conversions (262);
  - `subscription`: shares subscribed in an issue (55);
  - `buy` (1,818) and `sell` (444); `unknown` (207).
  Only `buy` and `sell` are measured.
- **Check by hand:** a fresh random sample of 30 buys had 28 right, one wrong (a purchase in another company) and one
  borderline (shares bought in a mandatory offer). A sample of 15 sells had 15 right. An earlier sample of 30 buys
  had found two error types – the company itself as the buyer, and a bond conversion – and both were fixed before this
  run.

## Method

- One event per stock and publication day: several insiders on one day are one event. That gives 1,585 buy events
  in 61 stocks and 421 sell events in 56 stocks.
- Entry at the open of the first session after publication (Oslo time; before 09:00 means the same day). Exit at the
  close h sessions later.
- Excess return: the stock minus the equal-weighted 64 stocks over the same window. The net figure takes off a
  0.5 % round trip.
- **t-statistic:** of the event-weighted mean, with a two-way cluster-robust variance (time blocks of ceil(h/21)
  months, stock, minus their intersection). **Interval:** month-block bootstrap, 2,000 resamples, fixed seed.
  Four horizons and two sides were tested; nothing else was tried.

## Results (excess return vs the 64 stocks)

| | Horizon | Events | Mean | 95 % interval | t (two-way) | Median | Trimmed 5 % | One vote per stock | Top-2 stocks' share of the sum | Positive | Net of 0.5 % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Buy | 20 sessions | 1,560 | +0.23 % | [−0.47, +0.93] | 0.63 | −0.29 % | −0.06 % | −0.22 % | 115 % | 49 % | −0.27 % |
| Buy | 60 | 1,538 | +0.70 % | [−0.83, +2.26] | 0.72 | −0.24 % | −0.14 % | −0.23 % | 138 % | 49 % | +0.20 % |
| Buy | 120 | 1,510 | +1.58 % | [−0.89, +4.04] | 1.03 | −1.00 % | −0.55 % | +0.68 % | 88 % | 47 % | +1.08 % |
| Buy | 250 | 1,462 | +5.51 % | [+0.69, +10.74] | 1.77 | −3.55 % | −1.02 % | +5.37 % | 74 % | 45 % | +5.01 % |
| Sell | 20 | 416 | −0.24 % | [−1.20, +0.74] | −0.44 | −0.87 % | −0.42 % | −0.27 % | – | 44 % | −0.74 % |
| Sell | 60 | 412 | +0.12 % | [−1.96, +2.27] | 0.12 | −0.80 % | −0.24 % | −0.09 % | – | 48 % | −0.38 % |
| Sell | 120 | 410 | +0.32 % | [−2.45, +2.99] | 0.19 | −0.76 % | −0.41 % | −2.15 % | – | 48 % | −0.18 % |
| Sell | 250 | 390 | +0.06 % | [−4.40, +5.05] | 0.02 | −7.14 % | −1.99 % | −4.34 % | – | 43 % | −0.44 % |

A top-2 share above 100 % means the rest of the stocks together pull the other way. (For sells the sum is near zero,
so the share is not meaningful and is left out.)

The only cell whose interval excludes zero is the 250-session mean of buys – with a median of −3.6 %, a trimmed mean
of −1.0 % and a two-way t of 1.8. That is a few large winners over a year, not a pattern a buyer of insider buys would
have caught.

## How the dashboard uses it

The stock page lists insider notifications and short positions. Next to them it shows the 60-session line above as
context – mean, interval, median, trimmed mean, t and the top-2 share – never as a signal. The front page lists
insider trades in followed stocks only so that you can read them.
