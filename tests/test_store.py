"""The live store on a branch and the session plan: pack, merge, push, pull, and what the loop does next."""

import json
import shutil
import sqlite3
import subprocess

import pandas as pd
import pytest

from osloquant import init_env
from osloquant.intraday import IntradayAccountConfig, IntradayConfig, account_summary, load_config, poll
from osloquant.session import Plan, plan
from osloquant.store import PACKED_DB, TRADER_DB, live_trader_names, pack, pull, push, unpack
from tests.helpers import store_stocks
from tests.test_intraday import DAY2, A, at, make_bars, polls, store_intraday


def polled_account(home):
    """An intraday paper account with a few looks in the store, plus a backtest row that must stay out of the pack."""
    load_config()  # writes the default intraday.yaml, which travels with the store
    store_stocks(["AAA"])
    store_intraday(A, make_bars(100.0, flags={at(DAY2, "09:45"): 111}))
    config = IntradayConfig(
        accounts=[
            IntradayAccountConfig(
                name="paper",
                signal={"rule": "tests.test_intraday:FlagRule"},
                watchlist=["AAA"],
                input_money=10_000,
                max_positions=2,
            )
        ]
    )
    for when in polls(DAY2, "09:31", "10:46"):
        assert poll(config, now=when, record=False).errors == {}
    with sqlite3.connect(home / "data" / TRADER_DB) as con:
        con.execute(
            "insert into trader_info (id, entity_id, timestamp, trader_name, mode) values ('bt', 'bt', '2026-01-01', 'backtest_x', 'backtest')"
        )
        con.execute(
            "insert into \"order\" (id, entity_id, timestamp, trader_name, order_type) values ('bt_1', 'stock_ol_AAA', '2026-01-01', 'backtest_x', 'order_long')"
        )
        con.commit()
    return config


def test_pack_keeps_the_live_accounts_and_drops_the_backtests(home):
    polled_account(home)
    (home / "troll.json").write_text('{"entries": []}', encoding="utf-8")
    manifest = pack(home / "packed")
    assert (
        manifest["accounts"] == ["paper"]
        and "intraday.yaml" in manifest["files"]
        and "troll.json" in manifest["files"]
        and PACKED_DB in manifest["files"]
    )
    with sqlite3.connect(home / "packed" / PACKED_DB) as con:
        assert con.execute("select count(*) from trader_info").fetchone()[0] == 1
        assert con.execute("select count(*) from \"order\" where trader_name = 'backtest_x'").fetchone()[0] == 0
        assert con.execute("select count(*) from intraday_snapshot").fetchone()[0] == 6
    assert live_trader_names(home / "packed" / PACKED_DB) == ["paper"]


def test_unpack_merges_the_accounts_into_a_home_and_leaves_its_own_rows_alone(home, tmp_path):
    polled_account(home)
    before = account_summary("paper")
    pack(home / "packed")

    # a fresh home: the file is simply installed
    other = tmp_path / "other"
    init_env(other)
    assert unpack(home / "packed", home_dir=other)["accounts"] == ["paper"]
    after = account_summary("paper")
    assert (
        after["value"] == before["value"]
        and after["fills"] == before["fills"]
        and len(after["signals"]) == len(before["signals"])
    )
    assert (other / "intraday.yaml").exists()

    # a home with its own books: the packed accounts replace their rows, the rest survives
    with sqlite3.connect(other / "data" / TRADER_DB) as con:
        con.execute(
            "insert into trader_info (id, entity_id, timestamp, trader_name, mode) values ('mine', 'mine', '2026-01-01', 'my_backtest', 'backtest')"
        )
        con.execute("update intraday_snapshot set all_value = 1 where trader_name = 'paper'")
        con.commit()
    unpack(home / "packed", home_dir=other)
    with sqlite3.connect(other / "data" / TRADER_DB) as con:
        assert con.execute("select count(*) from trader_info where trader_name = 'my_backtest'").fetchone()[0] == 1
        assert con.execute("select max(all_value) from intraday_snapshot where trader_name = 'paper'").fetchone()[0] > 1
    init_env(home)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_push_and_pull_carry_the_store_through_a_branch(home, tmp_path):
    polled_account(home)
    remote, repo = tmp_path / "remote.git", tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)

    assert pull(repo=repo, home_dir=tmp_path / "nothing") is None, "no branch yet"
    push(repo=repo)
    (home / "intraday.yaml").write_text(
        (home / "intraday.yaml").read_text(encoding="utf-8") + "\n# edited on the laptop\n", encoding="utf-8"
    )
    push(repo=repo, only=["intraday.yaml"])  # a configuration push keeps the books on the branch

    fresh = tmp_path / "fresh"
    init_env(fresh)
    manifest = pull(repo=repo, home_dir=fresh)
    assert manifest["accounts"] == ["paper"]
    assert "# edited on the laptop" in (fresh / "intraday.yaml").read_text(encoding="utf-8")
    assert account_summary("paper")["fills"] >= 1
    with pytest.raises(FileNotFoundError):
        push(repo=repo, only=["nothing.yaml"])
    init_env(home)


def test_the_plan_says_what_the_loop_does_next():
    delay = pd.Timedelta(minutes=15)
    assert plan(pd.Timestamp("2026-10-19 08:00"), delay) == Plan(
        "tick", 91 * 60, pd.Timestamp("2026-10-19 09:31")
    )  # the first look is at 09:31
    assert plan(pd.Timestamp("2026-10-19 10:32"), delay) == Plan(
        "tick", 0, pd.Timestamp("2026-10-19 10:31")
    )  # 10:31 is a minute gone: still made, now
    assert plan(pd.Timestamp("2026-10-19 10:32"), delay, after=pd.Timestamp("2026-10-19 10:31")) == Plan(
        "tick", 14 * 60, pd.Timestamp("2026-10-19 10:46")
    ), "made once: 10:46 is next"
    assert (
        str(plan(pd.Timestamp("2026-10-19 10:32"), delay)) == "tick 0 2026-10-19T10:31"
        and str(Plan("done", 0)) == "done 0 -"
    )
    assert plan(pd.Timestamp("2026-10-19 10:36"), delay) == Plan(
        "tick", 10 * 60, pd.Timestamp("2026-10-19 10:46")
    )  # five minutes gone: that bar is stale, 10:46 next
    assert plan(pd.Timestamp("2026-10-19 10:30"), delay) == Plan("tick", 60, pd.Timestamp("2026-10-19 10:31"))
    assert plan(pd.Timestamp("2026-10-19 16:51"), delay) == Plan(
        "evening", 14 * 60
    )  # the last look, 16:46, is past its slack
    assert plan(pd.Timestamp("2026-10-19 18:00"), delay) == Plan(
        "evening", 0
    )  # late start: the evening step is still made once
    assert plan(pd.Timestamp("2026-10-19 18:00"), delay, evening_done=True) == Plan("done", 0)
    assert plan(pd.Timestamp("2026-10-17 12:00"), delay) == Plan("done", 0)  # a Saturday


def test_the_manifest_is_json_the_page_and_people_can_read(home):
    manifest = pack(home / "packed")
    assert (
        manifest["accounts"] == []
        and json.loads((home / "packed" / "manifest.json").read_text(encoding="utf-8"))["schema"] == "store/1"
    )
