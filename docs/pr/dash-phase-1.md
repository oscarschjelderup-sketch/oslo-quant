# Dashboard phase 1: research – what to show, and which free data can show it

## Summary

- `docs/dashboard/research.md`: what Nordnet, Investtech, Infront, Koyfin, Finansavisen and Bloomberg show on
  their overview and stock pages, how their alerts and watchlists work, and what analysts actually use in a day.
  61 sources, each marked "Read", "Search only" or "Could not be read" (accessed 22 Oct 2026). Ends with a
  take / drop / why table and the list of what is only behind a paywall.
- `docs/dashboard/data-sources.md`: every free source the dashboard can use, fetched from this machine on
  22 Oct 2026 – NewsWeb (announcements), Norges Bank (rates, FX), SSB 03024 (salmon export price), Brent (Yahoo,
  EIA, FRED), media RSS (E24, DN, Finansavisen, NRK), Fish Pool, Yahoo – with URLs, fields, update times, terms and
  the label each number should carry. Ends with what is paywalled or licensed.
- `DECISIONS.md`: D1–D9 – technology (Flask on 127.0.0.1:8060), what the dashboard may write (two append-only
  files), the judgement form, caching, the chosen sources, take/drop, the "needs a decision" rules, privacy, labels.

## Findings that shaped the design

- The professional tools differ from the retail ones mainly in **condition alerts with a log** (Infront, Koyfin,
  Bloomberg) and in **comparing your own numbers with the price** (Bloomberg ANR/EE, LSEG). Nordnet's alerts are
  price-level or % only.
- The closest retail feature to a judgement log is Nordnet's private notes per stock – free text, not scored.
- Analysts start the day with news and an overnight scan, then monitor for changes that matter to the case. No
  survey of which screens analysts use daily was found (CFA or NFF); the research says so instead of guessing.
- Investtech's Score has undisclosed weights, so it is dropped: a score that cannot be decomposed cannot be
  calibrated.

## Paywalled (not attempted)

Real-time and depth data, consensus estimates and broker targets, broker research, fundamentals databases,
full-text news, Investtech's signals, Baltic freight indices, official ICE/LME settlement prices.

## Not in this PR

No code. The pages come in phase 2.

## Test plan

- [x] Every URL in data-sources.md marked VERIFIED was fetched on 22 Oct 2026 (scripts kept outside the repo).
- [x] No private file, ticker target or judgement is in these documents.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
