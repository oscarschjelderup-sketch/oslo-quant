# Day Trader skill: what it does and what fits our dashboard

## Summary

- `docs/dashboard/day-trader-vurdering.md`: the Day Trader skill pack (github.com/Jakeschincariol/day-trader-skill,
  commit 3d0f4ef, MIT) read in full – never run, installed or given keys. A safety review (every network call, what
  leaves the machine, how orders are gated), what each of the 11 skills does and how, a fit verdict for long-term
  cases on Oslo Børs, and what each of our four planned parts takes from it, with the pitfalls its own tests show.
- `DECISIONS.md` D14: ideas taken, code reimplemented, no install.

## Verdict in one line each

scanner, news, entry, broker, alerts: do not fit (intraday, US data, or trading). exit, risk: ideas for the form's
checks. timemachine: the question and output fit, the engine must change (daily data, block resampling). budget:
the sizing method fits almost exactly. analyst: the comparison logic fits, but Oslo has no XBRL. pelosi: the pipeline
shape fits; the source becomes NewsWeb's insider category.

## Test plan

- [x] Nothing from the repository was executed.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
