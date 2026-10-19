"""Is everything that should be running, running?

The paper accounts are driven by scheduled jobs on a laptop that sleeps. A job that silently does not run
looks, from the outside, exactly like a quiet market. These checks make the difference visible: how fresh the
data is, whether each account is where it should be, how many of the day's looks were actually made, and
whether the scheduled tasks exist and what their last run returned.

``oq doctor`` prints them; the dashboard shows the ones that need no call to the operating system.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass

import pandas as pd

OK, WARN, FAIL = "ok", "warn", "fail"
MARKET_TIMEZONE = "Europe/Oslo"
TASKS = ("oslo-quant live", "oslo-quant intraday", "oslo-quant signals")


@dataclass
class Check:
    name: str
    status: str
    detail: str
    #: what to do about it, when there is something to do
    hint: str | None = None


def market_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz=MARKET_TIMEZONE).tz_localize(None)


def expected_session(now: pd.Timestamp) -> pd.Timestamp:
    """The newest weekday whose daily bars should be final at ``now`` (Oslo time). Holidays are not known here."""
    day = now.normalize()
    if now - day < pd.Timedelta(hours=17):
        day -= pd.Timedelta(days=1)
    while day.dayofweek >= 5:
        day -= pd.Timedelta(days=1)
    return day


def _sessions_behind(newest: pd.Timestamp, expected: pd.Timestamp) -> int:
    return max(len(pd.bdate_range(newest, expected)) - 1, 0)


def check_daily_data(now: pd.Timestamp) -> Check:
    from osloquant.contract.api import get_coverage
    from osloquant.domain import Stock1dAdjKdata

    newest = get_coverage(Stock1dAdjKdata)["last"]
    if newest is None:
        return Check("Daily prices", FAIL, "none stored", "oq record")
    expected = expected_session(now)
    behind = _sessions_behind(newest.normalize(), expected)
    detail = f"newest bar {newest:%a %d %b}"
    if behind == 0:
        return Check("Daily prices", OK, detail)
    if behind == 1:
        return Check(
            "Daily prices",
            WARN,
            f"{detail}; {expected:%a %d %b} is missing",
            "the evening job has not run since that close (or Oslo was closed that day): oq live",
        )
    return Check(
        "Daily prices",
        FAIL,
        f"{detail}: {behind} sessions behind",
        "the evening job is not running: oq live, then oq doctor",
    )


def check_daily_accounts(now: pd.Timestamp) -> list[Check]:
    from osloquant.live.engine import account_summary, last_completed_session, live_account_names

    checks = []
    session = last_completed_session(now.tz_localize(MARKET_TIMEZONE))
    for name in live_account_names():
        summary = account_summary(name)
        late = summary["fills"] - summary["forward_fills"]
        detail = f"at {summary['last_session']:%a %d %b}, {summary['forward_fills']} of {summary['fills']} fills logged before the open"
        if session is not None and summary["last_session"] < session:
            checks.append(
                Check(name, FAIL, f"{detail}; the store has {session:%a %d %b}", "the account did not step: oq live")
            )
        elif late:
            checks.append(
                Check(
                    name,
                    WARN,
                    detail,
                    f"{late} fills were booked late and are not evidence; keep the evening job running",
                )
            )
        else:
            checks.append(Check(name, OK, detail))
    return checks


def check_intraday_accounts(now: pd.Timestamp) -> list[Check]:
    from osloquant.intraday.engine import (
        account_summary,
        config_path,
        intraday_account_names,
        load_config,
        worth_looking,
    )

    feed_delay = load_config().feed_delay if config_path().exists() else pd.Timedelta(minutes=15)
    checks = []
    for name in intraday_account_names():
        summary = account_summary(name, feed_delay=feed_delay)
        coverage = summary["coverage"]
        made, due = coverage["today_made"], coverage["today_due"]
        overall = (
            f"{coverage['share']:.0%} of all looks since the start"
            if coverage["share"] is not None
            else "no look due yet"
        )
        missed_days = len(coverage["days_missed"])
        if missed_days:
            overall += f", {missed_days} whole day{'s' if missed_days > 1 else ''} missed"
        if due == 0:
            checks.append(Check(name, OK, f"no look due today; {overall}"))
            continue
        detail = f"{made} of {due} looks made today; {overall}"
        lag = summary["feed_lag"]
        if made == 0 and due >= 4:
            checks.append(
                Check(
                    name,
                    FAIL,
                    detail,
                    "the 15-minute task is not running: scripts/schedule_intraday.ps1, then oq doctor",
                )
            )
        elif made < due - 1:
            checks.append(
                Check(
                    name, WARN, detail, "looks are missed while the computer sleeps; a missed look is a missed signal"
                )
            )
        elif lag is not None and lag > 35 and worth_looking(now, feed_delay):
            checks.append(
                Check(
                    name,
                    WARN,
                    f"{detail}; the newest quote was {lag:.0f} minutes old",
                    "Yahoo's feed is later than the 15 minutes assumed: raise feed_delay_minutes in intraday.yaml",
                )
            )
        else:
            checks.append(Check(name, OK, detail))
    return checks


def goats_publish_status(
    published: pd.Timestamp | None, newest_look: pd.Timestamp | None, slack: pd.Timedelta = pd.Timedelta(minutes=30)
) -> Check:
    """Whether the Trading Goats page is as fresh as the books: the goats branch against the newest look, both in UTC."""
    if newest_look is None:
        return Check("Goats page", OK, "no look to publish yet")
    if published is None:
        return Check("Goats page", WARN, "never published", "oq goats --publish, and read its error if it fails")
    behind = newest_look - published
    if behind > slack:
        hours = behind.total_seconds() / 3600
        return Check(
            "Goats page",
            WARN,
            f"published {published:%a %d %b %H:%M} UTC, {hours:.0f} h behind the newest look",
            "the publish after the look fails: run oq goats --publish by hand and read the error; the headless log has the traceback",
        )
    return Check("Goats page", OK, f"published {published:%a %d %b %H:%M} UTC, with the newest look")


def check_goats_publish() -> list[Check]:
    """The goats branch of the repository against the newest intraday look. Only when goats are configured."""
    from pathlib import Path

    from osloquant.contract.api import get_data
    from osloquant.env import oq_env
    from osloquant.trader.schemas import IntradaySnapshot
    from osloquant.trader.sim_account import PROVIDER

    if not (Path(oq_env["home"]) / "goats.yaml").exists():
        return []
    from osloquant.goats import BRANCH, repo_root

    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", f"refs/heads/{BRANCH}"],
            cwd=repo_root(),
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        published = pd.Timestamp(out).tz_convert("UTC").tz_localize(None) if out else None
    except Exception as e:  # noqa: BLE001  - no git, no repo: the check says so instead of failing
        return [Check("Goats page", WARN, f"the goats branch could not be read: {type(e).__name__}")]
    snaps = get_data(
        IntradaySnapshot, provider=PROVIDER, columns=["timestamp"], order=IntradaySnapshot.timestamp.desc(), limit=1
    )
    newest = (
        None
        if snaps.empty
        else pd.Timestamp(snaps["timestamp"].iloc[0]).tz_localize(MARKET_TIMEZONE).tz_convert("UTC").tz_localize(None)
    )
    return [goats_publish_status(published, newest)]


def store_branch_status(
    pushed: pd.Timestamp | None, now: pd.Timestamp, stale_after: pd.Timedelta = pd.Timedelta(hours=26)
) -> Check:
    """Whether the runner that owns the books has pushed them lately. ``pushed`` and ``now`` are UTC."""
    if pushed is None:
        return Check("Store branch", WARN, "no store branch", "oq store push from the machine that holds the books")
    age = now - pushed
    detail = f"last pushed {pushed:%a %d %b %H:%M} UTC"
    if now.dayofweek < 5 and age > stale_after:
        return Check(
            "Store branch",
            WARN,
            f"{detail}, {age.total_seconds() / 3600:.0f} h ago on a weekday",
            "the GitHub session has not run: look at the goats-session workflow, or run the books here and push",
        )
    return Check("Store branch", OK, detail)


def check_store_branch() -> list[Check]:
    """The store branch on origin: when the runner last pushed the books. Only when a goats.yaml says this home is part of that setup."""
    from pathlib import Path

    from osloquant.env import oq_env

    if not (Path(oq_env["home"]) / "goats.yaml").exists():
        return []
    from osloquant.goats import repo_root
    from osloquant.store import BRANCH

    try:
        repo = repo_root()
        subprocess.run(
            ["git", "fetch", "--quiet", "origin", f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}"],
            cwd=repo,
            capture_output=True,
            timeout=60,
        )
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", f"refs/remotes/origin/{BRANCH}"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        pushed = pd.Timestamp(out).tz_convert("UTC").tz_localize(None) if out else None
    except Exception as e:  # noqa: BLE001
        return [Check("Store branch", WARN, f"could not be read: {type(e).__name__}")]
    return [store_branch_status(pushed, pd.Timestamp.now(tz="UTC").tz_localize(None))]


def check_tasks() -> list[Check]:
    """The Windows scheduled tasks: registered, and what their last run returned."""
    if sys.platform != "win32":
        return []
    script = (
        "Get-ScheduledTask -TaskName 'oslo-quant*' -ErrorAction SilentlyContinue | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; "
        '[pscustomobject]@{ name = $_.TaskName; state = "$($_.State)"; result = [int64]$i.LastTaskResult; '
        "last = if ($i.LastRunTime) { $i.LastRunTime.ToString('s') } else { $null }; "
        "next = if ($i.NextRunTime) { $i.NextRunTime.ToString('s') } else { $null } } } | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=30
        ).stdout.strip()
        found = json.loads(out) if out else []
    except Exception as e:
        return [Check("Scheduled tasks", WARN, f"could not be read: {type(e).__name__}")]
    found = {t["name"]: t for t in ([found] if isinstance(found, dict) else found)}

    checks = []
    for name in TASKS:
        task = found.get(name)
        script_name = f"schedule_{name.split()[-1]}.ps1"          # schedule_live / schedule_intraday / schedule_signals
        if task is None:
            checks.append(
                Check(
                    f"Task '{name}'",
                    FAIL,
                    "not registered",
                    f"powershell -NoProfile -ExecutionPolicy Bypass -File scripts/{script_name}",
                )
            )
            continue
        last = (
            pd.Timestamp(task["last"]).strftime("%a %d %b %H:%M")
            if task["last"] and not task["last"].startswith("1999")
            else "never"
        )
        upcoming = pd.Timestamp(task["next"]).strftime("%a %H:%M") if task["next"] else "nothing scheduled"
        detail = f"last run {last}, next {upcoming}"
        # 0: fine. 0x41301: running now. 0x41303: has not run yet.
        if task["state"] == "Disabled":
            checks.append(
                Check(
                    f"Task '{name}'",
                    WARN,
                    f"disabled; {detail}",
                    "fine while the accounts run on GitHub Actions (see 'Store branch'); Enable-ScheduledTask to run them here again",
                )
            )
        elif task["result"] in (0, 0x41301, 0x41303):
            checks.append(Check(f"Task '{name}'", OK, detail))
        else:
            checks.append(
                Check(
                    f"Task '{name}'",
                    WARN,
                    f"{detail}; the last run returned 0x{task['result'] & 0xFFFFFFFF:X}",
                    "one failed run is normal after a wake from sleep; if it repeats, run the command by hand",
                )
            )
    return checks


def run_checks(now: pd.Timestamp | None = None, tasks: bool = True) -> list[Check]:
    """Every check. One that cannot be made reports that instead of stopping the rest."""
    now = market_now() if now is None else now
    checks: list[Check] = []
    for part in (
        lambda: [check_daily_data(now)],
        lambda: check_daily_accounts(now),
        lambda: check_intraday_accounts(now),
        check_goats_publish,
        check_store_branch,
        *([check_tasks] if tasks else []),
    ):
        try:
            checks += part()
        except Exception as e:
            checks.append(Check("A check", WARN, f"could not be made: {type(e).__name__}: {e}"))
    return checks
