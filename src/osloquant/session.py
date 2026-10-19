"""One trading day as a loop: a look every quarter of an hour, the evening step after the close, the books pushed
after each.

GitHub runs scheduled workflows on a best-effort basis, so a ``*/15`` cron cannot keep a 15-minute rhythm; one
running job can. The workflow in ``.github/workflows/goats-session.yml`` asks ``oq session next-tick`` what to do
next, sleeps until then, and runs ``oq session step``. The plan is pure and tested; the step does the work:

- ``tick``: one look (``oq intraday poll --if-open``), then the goats page and the store are pushed;
- ``evening``: the evening job (``oq live``: record the day's bars, step the daily accounts), then the same pushes;
- ``done``: nothing more today.

Every step pushes the live store to the ``store`` branch, so the next run, on whatever machine, carries on from
there. A publish or push that fails is reported and does not undo the look.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import time

import pandas as pd

MARKET_TIMEZONE = "Europe/Oslo"
#: the evening step: the daily bars are final from 17:00 Oslo time (the live engine's BARS_FINAL)
EVENING = time(17, 5)
#: a tick this long overdue is still made; later ones are skipped (their bars are no longer fresh)
TICK_SLACK = pd.Timedelta(minutes=4)


@dataclass(frozen=True)
class Plan:
    #: "tick", "evening" or "done"
    kind: str
    #: seconds to wait before doing it
    wait: int

    def __str__(self) -> str:
        return f"{self.kind} {self.wait}"


def market_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz=MARKET_TIMEZONE).tz_localize(None)


def plan(now: pd.Timestamp, feed_delay: pd.Timedelta = pd.Timedelta(minutes=15), evening_done: bool = False) -> Plan:
    """What the loop does next at ``now`` (Oslo time): the next look, the evening step, or nothing more today.

    Looks are due at the intraday engine's poll times. After the last one, the evening step is due at 17:05;
    a run that starts later than that still makes the evening step once (``oq live`` changes nothing when the
    accounts are already up to date), and is done after it. Weekends are done before they start.
    """
    from osloquant.intraday.engine import poll_times

    if now.dayofweek >= 5:
        return Plan("done", 0)
    for when in poll_times(now, feed_delay):
        if when >= now - TICK_SLACK:
            return Plan("tick", max(int((when - now).total_seconds()), 0))
    if evening_done:
        return Plan("done", 0)
    evening = now.normalize() + pd.Timedelta(hours=EVENING.hour, minutes=EVENING.minute)
    return Plan("evening", max(int((evening - now).total_seconds()), 0))


def _run_cli(args: list[str]) -> int:
    """Run an ``oq`` command in this process and return its exit code instead of exiting."""
    from osloquant.cli import app

    try:
        app(args)
    except SystemExit as stop:
        return int(stop.code or 0)
    return 0


def step(kind: str, publish: bool = True, push: bool = True) -> int:
    """Make one step of the day and push what changed. Returns the step's own exit code; a failed publish or
    push is printed and does not count against the step."""
    from osloquant import store

    if kind == "tick":
        code = _run_cli(["intraday", "poll", "--if-open"])
    elif kind == "evening":
        code = _run_cli(["live"])
    else:
        raise ValueError(f"unknown step {kind!r}; tick or evening")
    if publish:
        rc = _run_cli(["goats", "--publish", "--quiet"])
        if rc:
            print(f"goats publish failed (exit {rc})", file=sys.stderr)
    if push:
        try:
            commit = store.push()
            print(f"store pushed ({commit[:10]})")
        except Exception as e:  # noqa: BLE001  - the books are safe in the home; the next step pushes them
            print(f"store push failed: {type(e).__name__}: {e}", file=sys.stderr)
    return code
