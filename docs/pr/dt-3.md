# Part 3: primary insiders and short positions

## Summary

- `dashboard/insiders.py`: every NewsWeb primary-insider notification for the 64 stocks since 2010 (8,433),
  classified from its text (company, programme, other, subscription, buy, sell, unknown – the deciding word shown);
  Finanstilsynet's short register (open API: public positions ≥ 0.5 %, daily, two years) matched by hand to 37 stocks.
- Stock page: the last 12 months of insider notifications, and the short position with its history chart and holders.
  Front page: insider buys/sells/subscriptions and short moves ≥ 0.25 pp in followed stocks over the last 7 days.
- `oq insiders backfill` (once, ~1.5 h) and `oq insiders study --write`; `--refresh` keeps the current year and the
  short register up to date.
- **The study** (`docs/dashboard/insider-study.md`, numbers in `resources/insider_study.yaml`): the typical insider
  buy on Oslo Børs since 2010 was followed by a *below*-universe return (negative median at every horizon, under half
  positive); the positive average (+0.7 % at 60 sessions, +5.5 % at 250) rests on a few large winners, did not hold
  at 60 sessions after 2017, and is flattered by survivorship. Insider sells: nothing. Written plainly, shown as
  context only (D18).

## Test plan

- [x] `pytest tests/test_insiders.py`: the classifier on 15 kinds of NewsWeb text (incl. "participant" ≠ pledge,
      "investment" ≠ vesting, the company as buyer, conversions); one event per stock and day with the right entry
      session; the study's arithmetic on a known path; the short register's shape; on the frozen real cache (private),
      the committed study reproduces exactly.
- [x] Hand check of the classifier: 28 of 30 random buys right (one wrong company, one mandatory-offer purchase),
      15 of 15 sells right.
- [x] Dashboard run: SCATC, MOWI and the front page opened and screenshotted (outside the repo).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
