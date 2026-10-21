"""The live store on a branch: what the paper accounts need to carry on, small enough to push after every look.

The whole store is a few hundred megabytes of price history and backtests, but the part that cannot be
regenerated is tiny: the live accounts' saved state, their orders, signals and marks, the configuration files
and the troll's log. ``pack`` cuts the trader database down to the live accounts and gathers those files;
``push`` puts them on the ``store`` branch of the repository as one commit, and ``pull`` brings them back into a
home directory, merging the live rows into whatever that home already holds (its own backtests survive).

This is how the accounts move between machines: a GitHub Actions runner pulls the store, makes a look or the
evening step, and pushes it back; a laptop can pull it to read or review, and push its configuration changes
(a rewrite, a troll entry) without touching the books. Price history is not carried: ``oq record`` fetches it.
"""

from __future__ import annotations

import io
import json
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from contextlib import closing
from pathlib import Path

import pandas as pd

from osloquant.env import oq_env

BRANCH = "store"
TRADER_DB = "osloquant_trader_info.db"
PACKED_DB = "trader_live.db"
#: the trader tables that carry an account's record; every one has a trader_name column
LIVE_TABLES = (
    "trader_info",
    "account_stats",
    "position",
    "order",
    "live_state",
    "intraday_signal",
    "intraday_snapshot",
)
CONFIG_FILES = ("live.yaml", "intraday.yaml", "goats.yaml", "troll.json")
LOG_FILES = ("logs/live.log", "logs/intraday.log")
MANIFEST = "manifest.json"
#: what the runner owns and pushes: the books and the job logs. The configuration and the troll's log belong to
#: the laptop, which pushes them with --config-only; the runner only ever reads them.
BOOK_FILES = (PACKED_DB, *LOG_FILES, MANIFEST)
#: the troll's log keeps at most this many entries when two copies are merged
TROLL_KEEP = 60


def home() -> Path:
    from osloquant.env import data_path

    data_path()  # makes sure the home exists
    return Path(oq_env["home"])


def live_trader_names(db: Path) -> list[str]:
    """The accounts a trader database holds that are live or intraday paper accounts."""
    with closing(sqlite3.connect(db)) as con:
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        names: set[str] = set()
        if "trader_info" in tables:
            names |= {
                r[0] for r in con.execute("select trader_name from trader_info where mode in ('live', 'intraday')")
            }
        if "live_state" in tables:
            names |= {r[0] for r in con.execute("select trader_name from live_state")}
    return sorted(names)


def pack(out: Path, home_dir: Path | None = None) -> dict:
    """Write the live store to ``out`` and return its manifest.

    ``trader_live.db`` is a copy of the trader database with every backtest row removed; the configuration
    files, the troll's log and the two job logs come along as they are.
    """
    home_dir = home() if home_dir is None else Path(home_dir)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    src = home_dir / "data" / TRADER_DB
    if src.exists():
        dst = out / PACKED_DB
        if dst.exists():
            dst.unlink()
        with (
            closing(sqlite3.connect(src)) as con,
            closing(sqlite3.connect(dst)) as copy,
        ):  # a consistent copy, even mid-write
            con.backup(copy)
        names = live_trader_names(dst)
        with closing(sqlite3.connect(dst)) as con:
            tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
            marks = ",".join("?" * len(names)) if names else "''"
            for table in LIVE_TABLES:
                if table in tables:
                    con.execute(
                        f'delete from "{table}" where trader_name is null or trader_name not in ({marks})', names
                    )
            con.commit()
            con.execute("vacuum")
    for rel in CONFIG_FILES + LOG_FILES:
        source = home_dir / rel
        if source.exists():
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() and p.name != MANIFEST)
    manifest = {
        "schema": "store/1",
        "packed_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "accounts": names,
        "files": files,
    }
    (out / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def _merge_db(packed: Path, local: Path) -> list[str]:
    """Put the packed accounts' rows into ``local``, replacing what it had for them; everything else stays."""
    names = live_trader_names(packed)
    if not names:
        return []
    marks = ",".join("?" * len(names))
    with closing(sqlite3.connect(local)) as con:
        con.execute("attach database ? as live", (str(packed),))
        local_tables = {r[0] for r in con.execute("select name from main.sqlite_master where type='table'")}
        packed_tables = {r[0] for r in con.execute("select name from live.sqlite_master where type='table'")}
        for table in LIVE_TABLES:
            if table not in packed_tables:
                continue
            if table not in local_tables:
                con.execute(f'create table main."{table}" as select * from live."{table}" where 0')
            mine = [r[1] for r in con.execute(f'pragma main.table_info("{table}")')]
            theirs = [r[1] for r in con.execute(f'pragma live.table_info("{table}")')]
            columns = ", ".join(f'"{c}"' for c in mine if c in theirs)
            con.execute(f'delete from main."{table}" where trader_name in ({marks})', names)
            con.execute(f'insert or replace into main."{table}" ({columns}) select {columns} from live."{table}"')
        con.commit()
        con.execute("detach database live")
    return names


def merge_troll(local: Path, incoming: Path) -> int:
    """Merge two copies of the troll's log: every entry either holds, once, oldest first. Returns the entry count.

    The log is only ever appended to, so a copy that lacks entries is behind, never ahead: a merge can never
    lose a line, whichever copy is older.
    """

    def read(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            return {}

    mine, theirs = read(local), read(incoming)
    seen, entries = set(), []
    for entry in [*mine.get("entries", []), *theirs.get("entries", [])]:
        key = (entry.get("t"), entry.get("kind"), entry.get("goat"), entry.get("text"))
        if key not in seen:
            seen.add(key)
            entries.append(entry)
    entries.sort(key=lambda e: e.get("t") or "")
    entries = entries[-TROLL_KEEP:]
    merged = {**theirs, **mine, "entries": entries, "reviewed_at": entries[-1]["t"] if entries else None}
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(merged, indent=1, ensure_ascii=False), encoding="utf-8")
    return len(entries)


def unpack(
    src: Path, home_dir: Path | None = None, configs: bool = True, logs: bool = True, books: bool = True
) -> dict:
    """Bring a packed store into a home directory. Returns the manifest (empty if the pack has none).

    ``books`` merges the accounts' rows into the home's trader database; ``configs`` copies the configuration
    files over the home's and merges the troll's log (never shortening it); ``logs`` copies the job logs.
    """
    from osloquant.contract.storage import dispose_engines

    home_dir = home() if home_dir is None else Path(home_dir)
    src = Path(src)
    manifest = json.loads((src / MANIFEST).read_text(encoding="utf-8")) if (src / MANIFEST).exists() else {}
    packed = src / PACKED_DB
    if books and packed.exists():
        dispose_engines()  # the database file is about to change under any open connection
        local = home_dir / "data" / TRADER_DB
        local.parent.mkdir(parents=True, exist_ok=True)
        if local.exists():
            _merge_db(packed, local)
        else:
            shutil.copy2(packed, local)
    wanted = (CONFIG_FILES if configs else ()) + (LOG_FILES if logs else ())
    for rel in wanted:
        source = src / rel
        if not source.exists():
            continue
        target = home_dir / rel
        if rel == "troll.json":
            merge_troll(target, source)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return manifest


def push(
    only: list[str] | None = None,
    books_only: bool = False,
    repo: Path | None = None,
    branch: str = BRANCH,
    home_dir: Path | None = None,
    message: str | None = None,
) -> str:
    """Pack the store and put it on the branch as one commit; files already there and not pushed are kept.

    ``only`` limits the push to those files: a laptop pushes its configuration and the troll's log this way and
    never the books. ``books_only`` is the runner's push: the trader database, the job logs and the manifest,
    never the configuration it only reads. With neither, everything goes (the first push of a store). Returns
    the commit id.
    """
    from osloquant.goats import publish_branch

    with tempfile.TemporaryDirectory() as tmp:
        manifest = pack(Path(tmp), home_dir=home_dir)
        packed = {rel: Path(tmp) / rel for rel in [*manifest["files"], MANIFEST]}
        if books_only:
            files, what = {rel: path for rel, path in packed.items() if rel in BOOK_FILES}, "books"
        elif only is not None:
            missing = [rel for rel in only if rel not in packed or rel == MANIFEST]
            if missing:
                raise FileNotFoundError(f"not in the store: {', '.join(missing)}")
            files, what = {rel: packed[rel] for rel in only}, "configuration"
        else:
            files, what = packed, f"{len(manifest['accounts'])} accounts"
        stamp = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%MZ")
        return publish_branch(files, repo=repo, branch=branch, message=message or f"store: {what} at {stamp}")


def fetch(repo: Path | None = None, branch: str = BRANCH, remote: str = "origin") -> Path | None:
    """Download the branch into a temporary directory and return it, or None when the branch does not exist."""
    from osloquant.goats import repo_root

    repo = repo_root() if repo is None else Path(repo)
    ref = f"refs/remotes/{remote}/{branch}"
    fetched = subprocess.run(
        ["git", "fetch", "--quiet", remote, f"+refs/heads/{branch}:{ref}"], cwd=repo, capture_output=True, text=True
    )
    if fetched.returncode != 0:
        return None
    archive = subprocess.run(["git", "archive", "--format=tar", ref], cwd=repo, capture_output=True)
    if archive.returncode != 0:
        raise RuntimeError(f"git archive failed: {archive.stderr.decode(errors='replace').strip()}")
    target = Path(tempfile.mkdtemp(prefix="osloquant-store-"))
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(target, filter="data")
    return target


def pull(
    repo: Path | None = None,
    branch: str = BRANCH,
    home_dir: Path | None = None,
    configs: bool = True,
    logs: bool = True,
    books: bool = True,
) -> dict | None:
    """Fetch the branch and bring it into the home. Returns the manifest, or None when there is no branch yet."""
    folder = fetch(repo=repo, branch=branch)
    if folder is None:
        return None
    try:
        return unpack(folder, home_dir=home_dir, configs=configs, logs=logs, books=books)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
