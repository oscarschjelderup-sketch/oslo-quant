# Dashboard phase 3: the habit – the evening page and the Sunday summary

Builds on phase 2.

## Summary

- **The evening page is the dashboard.** `oq signals digest` now writes the dashboard's front page as
  `~/osloquant-home/signals/latest.html` ("Dette krever en vurdering fra deg", the book against its targets, report
  dates, announcements, the session's signals with odds). The Windows task "oslo-quant signals" opens it on a new
  session as before; links go to the running dashboard. If the dashboard page fails, the classic page is written,
  so the evening digest is never lost.
- **Feeds before the digest.** `scripts/run_signals.ps1` runs `oq dashboard --refresh-only` after `oq record`.
- **The Sunday summary.** `oq book weekly` writes `~/osloquant-home/weekly/<year>-W<week>.md/.html`:
  judgements that should have been made (the front page's rules replayed for each session of the week, unanswered
  by a judgement or kill check dated on or after the trigger), judgements logged, and what changed (book, sector
  medians, biggest moves, signals, announcements). `scripts/schedule_weekly.ps1` registers the task
  "oslo-quant weekly", Sundays 18:00 local time (start time stored without a UTC offset, so it stays 18:00 when
  summer time ends).
- README section "The decision dashboard"; DECISIONS D12–D13.

## Notes

- On 22 Oct 2026 the summary for the real home lists one missed judgement: the SATS risk signal of 19 Oct
  (drawdown 10 % from the 60-day high), which no logged judgement or kill check answers.
- The existing "oslo-quant signals" task stores 17:45 with today's UTC offset, so after summer time ends it will run
  at 16:45 local time (still after the Oslo close in Lisbon). Not changed here.

## Test plan

- [x] `pytest`: 301 passed (2 new): the CLI digest writes the dashboard front page, and the classic page when the
      dashboard fails; the weekly summary lists a 10 % move as a missed judgement and drops it once a judgement dated
      after it is logged, and writes the files to `weekly/`.
- [x] In a copy of the home directory: `oq dashboard --refresh-only` (all six feeds ok), `oq signals digest` wrote
      the front page with the session's 14 signals; `oq book weekly` wrote 2026-W43.
- [x] The three PowerShell scripts parse; the task is registered (next run 25 Oct 2026 18:00).
- [x] `ruff check` clean; no private file tracked.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
