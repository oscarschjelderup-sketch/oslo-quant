"""What the scheduler runs every 15 minutes: one look at the market, if there can be anything to see.

    pythonw -m osloquant.tick

The task fires around the clock, and for two thirds of the day Oslo is closed. Loading the whole framework
only to find that out takes seconds each time, so the first question is asked with the standard library alone:
is it a weekday, somewhere between the open and a little after the close in Oslo? If not, the run is over in
milliseconds and leaves no trace. If so, it hands over to ``oq intraday poll --if-open``, which knows the exact
times and does the work, and then to ``oq goats --publish``, which puts the fresh books on the goats branch for
the Trading Goats page.
"""

from __future__ import annotations

import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

#: a generous window around the session; the exact times are checked by the poll itself
OPENS, CLOSES = time(9, 0), time(17, 30)


def might_be_open(now: datetime | None = None) -> bool:
    now = now or datetime.now(ZoneInfo("Europe/Oslo"))
    return now.weekday() < 5 and OPENS <= now.time() <= CLOSES


def main() -> int:
    if not might_be_open():
        return 0
    from osloquant.cli import app

    code = 0
    try:
        app(["intraday", "poll", "--if-open"])
    except SystemExit as stop:
        code = int(stop.code or 0)
    # the look is done; now the goats page gets the new books. A failed publish never counts against the look.
    try:
        app(["goats", "--publish", "--quiet"])
    except SystemExit:
        pass
    except Exception as e:  # noqa: BLE001  - the scheduler only sees the exit code; the log sees the reason
        print(f"goats publish failed: {type(e).__name__}: {e}")
    return code


if __name__ == "__main__":
    sys.exit(main())
