# Did primary-insider buys predict returns on Oslo Børs, 2010–2026?

Measured 23 Oct 2026 on the oslo-quant store (prices to 22 Oct 2026) with `oq insiders study`. The numbers are in
`src/osloquant/resources/insider_study.yaml`; a test reproduces them from a frozen copy of the data.

## Answer

**Not in a way you can act on.** The typical insider buy was followed by a slightly *worse* return than the 64
stocks: the median excess return is negative at every horizon from 20 to 250 sessions, and fewer than half the
buys beat the universe. The *average* is positive and grows with the horizon (+0.7 % over 60 sessions, +5.5 % over
250), but it is carried by a small number of very large winners: the best 5 % of buys make up more than the whole
sum. At 60 sessions the average was +1.9 % in 2010–2017 and −0.2 % in 2018–2026. Insider sells were followed by
nothing measurable.

The positive average is also flattered by survivorship: the universe is today's 64 stocks, so companies that fell out
of the exchange after insiders bought are missing.

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
- t-statistics use one average per calendar month, because events in the same month are not independent. Four
  horizons and two sides were tested; nothing else was tried.

## Results (excess return vs the 64 stocks)

| | Horizon | Events | Mean | Median | Positive | Net of 0.5 % | t (monthly) |
|---|---|---|---|---|---|---|---|
| Buy | 20 sessions | 1,560 | +0.23 % | −0.29 % | 49 % | −0.27 % | 1.29 |
| Buy | 60 | 1,538 | +0.70 % | −0.24 % | 49 % | +0.20 % | 2.41 |
| Buy | 120 | 1,510 | +1.58 % | −1.00 % | 47 % | +1.08 % | 2.67 |
| Buy | 250 | 1,462 | +5.51 % | −3.55 % | 45 % | +5.01 % | 2.81 |
| Sell | 20 | 416 | −0.24 % | −0.87 % | 44 % | −0.74 % | −1.06 |
| Sell | 60 | 412 | +0.12 % | −0.80 % | 48 % | −0.38 % | 0.06 |
| Sell | 120 | 410 | +0.32 % | −0.76 % | 48 % | −0.18 % | 0.13 |
| Sell | 250 | 390 | +0.06 % | −7.14 % | 43 % | −0.44 % | 0.68 |

### Robustness of the buy result

| | 60 sessions | 250 sessions |
|---|---|---|
| Mean | +0.70 % | +5.51 % |
| Mean with the top and bottom 1 % capped | +0.40 % | +3.87 % |
| Mean / median, buys 2010–2017 | +1.90 % / +0.21 % (642) | +2.21 % / −5.10 % (641) |
| Mean / median, buys 2018–2026 | −0.16 % / −0.94 % (896) | +8.09 % / −2.21 % (821) |
| Best 5 % of buys, share of the summed excess | 376 % | 184 % |

## How the dashboard uses it

The stock page lists insider notifications and short positions. Next to them it shows the 60-session line above as
context – an average, not advice. No signal fires on an insider buy, and the front page lists insider trades in
followed stocks only so that you can read them.
