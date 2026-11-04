# Desk: six roles through a stock before the judgement (D41)

One branch, one decision entry (`DECISIONS.md` D41), tests on synthetic data with fictional SATS, OUTLT and ELK.

## What it is – `dashboard/desk.py`, `dashboard/deskpage.py`, `/desk`, `oq desk`
The structure of a six-bot trading desk from social media – one job per role, hard hand-offs, an obligatory bear, a log
of everything – on the data the dashboard already holds; none of its content (memecoins, intraday, orders) and no
language model. Scout → Filter → Analyst → Bear → Reply → Risk, each a set of rules; every finding is a fixed claim with a
number, a source and the time of the data (refused without them; EST and delayed marked). The chain ends in *klar for
vurdering* (the judgement form prefilled from the view and the Risk role, the debate attached, `desk_run` on the row),
*parkert* (a bear reason the rules could not rebut with numbers, or a Risk block) or *drept* (the filter's reason) – and
never in a buy. Fewer than three numbered bear reasons stop the chain; one reason that stands is a veto.

## Where it shows
`/desk`: today's run (scanned, flagged, killed, debated, parked, ready; time; data quality per source; the share the
filter killed against the brief's 90 %), the stocks with the deciding finding, a run button for one stock, the veto
statistic over time, earlier runs. `/desk/run/<id>/<code>`: the full debate log, chronological. The stock page lists
the runs that went through the stock and has the button; the judgement row links to the log it was opened from; the
front page and the evening file carry "Desk i dag". The daily run is a step in `scripts/run_signals.ps1`
(`oq desk run --daily` before the digest).

## The number that decides whether it is worth anything
`veto_stats`: for every veto, did the price reach the kill level before the target within 60 sessions (first daily
close, adjusted, as the odds) – right / wrong / neither / pending / unscorable – beside the same count for the stocks the
desk let through. Shown in words also when the vetoes have not helped.

## What it writes
Only its own run log, append-only, under `~/osloquant-home/desk/` (private; `desk/` added to the privacy test). Never
the research book, the judgement log or the watchlist; the hash chain is untouched (`desk_run` is an optional field on
new rows only). Limits live in `dashboard.yaml` (`sizing`, and `desk:` over `desk.DEFAULTS`).

## Tests
`tests/test_desk.py` (12 tests; one runs only where the frozen real data exists): never a buy and the private files
byte-identical; the bear's three-reason rule, also against a patched bear; no finding without claim, number, source,
time; filter, veto and Risk block each end the chain with the reason visible; runs reproduce and are never overwritten;
the pages, the prefill, the row link, the CLI; the veto statistic on a known price path; config keys. `test_dashboard.py`
now expects the third write route (`POST /desk/run`) and the `desk/` prefix. Full suite green, ruff clean.
