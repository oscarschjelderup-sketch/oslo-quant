# Part 1: outcome odds on the stock page

Our version of the Day Trader skill's Time Machine, for long-term cases on daily data (D15).

## Summary

- **Cases** (`dashboard/odds.py`): for every research-book stock, how often a price like today's has reached the
  target first, the kill level first, or neither within 3, 6 and 12 months – by two methods side by side:
  - simulation: 10,000 paths from the stock's own daily returns since 2010, resampled in 20-session blocks, fixed seed;
  - historical cases: every month-start since 2010 on the 64 stocks with the levels at the same distance in each
    stock's volatility, plus the stock's own history; the number of cases and the approximate independent count shown.
  - break-even: the share of decided cases the target must win, 1/(1+R), against the simulation's share.
  - "En realitetssjekk, ikke en prognose" above the table; a view without a kill level uses its bear value as a
    labelled stand-in.
- **Kill level** field in the judgement form, stored in the log row; must be below the price for a BUY, above for a SELL.
- **Signals**: target first / stop first / neither after a 0.5 % round trip (R = 2 x ATR(20)), measured 2010 to
  19 Oct 2026 and added to `signal_odds.yaml` (`oq signals brackets --write`); under each active signal and as a table
  on the calibration page. Every signal averages within ±0.07 R of zero.
- **Frozen real data** for deterministic tests, outside the repo (`oq freeze-testdata`, D16).

## Example (frozen prices, 22 Oct 2026; EQNR at 431.80 with illustrative levels 480 / 380)

| Horizon | Simulation T / K / N | All 64 stocks T / K / N (n) | Own history T / K / N (n) |
|---|---|---|---|
| 3 months | 42 / 21 / 37 % | 52 / 32 / 16 % (9,752) | 37 / 19 / 44 % (186) |
| 12 months | 65 / 34 / 1 % | 61 / 39 / 0 % (9,185) | 58 / 36 / 6 % (177) |

## Test plan

- [x] `pytest`: 312 passed. New: first passage, deterministic simulation, volatility-scaled cases and overlap count,
      SELL mirroring, break-even, the open session left out, kill-level precedence, brackets on a known path; on the
      frozen real data, EQNR's odds to four decimals and the committed brackets reproduced exactly; the stock page
      shows the reality check; the form stores the kill level and rejects one on the wrong side.
- [x] Dashboard run, SATS / EQNR / calibration pages opened and screenshotted (kept outside the repo: they show the
      private research book).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
