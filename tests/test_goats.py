"""The Trading Goats export: the clocks, the status words, the troll's log, the rewrite flow, the branch publish."""

import json
import shutil
import subprocess

import pandas as pd
import pytest
from typer.testing import CliRunner

from osloquant.cli import app
from osloquant.goats import (
    GoatConfig,
    GoatsConfig,
    _fill_items,
    _signal_items,
    add_troll_entry,
    compact_series,
    export,
    gate_items,
    held_since,
    load_config,
    load_troll,
    market_phase,
    next_review,
    parse_change,
    publish_branch,
    rewrite,
    save_config,
    sessions_since,
    status_for,
    write,
)

runner = CliRunner(env={"COLUMNS": "200"})
OPEN = {"open": True, "label": "open"}
CLOSED = {"open": False, "label": "closed"}


@pytest.mark.parametrize(
    "now, open_, label",
    [
        ("2026-10-13 10:00", True, "open"),  # a Tuesday
        ("2026-10-13 08:30", False, "before the open"),
        ("2026-10-13 16:20", False, "closed"),
        ("2026-10-17 12:00", False, "weekend"),  # a Saturday
    ],
)
def test_the_market_phase_follows_the_oslo_clock(now, open_, label):
    phase = market_phase(pd.Timestamp(now))
    assert (phase["open"], phase["label"]) == (open_, label)
    if open_:
        assert phase["closes_at"] == "2026-10-13T16:20:00"
    else:
        assert phase["next_open"].endswith("T09:00:00")


def test_the_troll_reviews_on_weekday_evenings():
    assert next_review(pd.Timestamp("2026-10-13 10:00")) == pd.Timestamp("2026-10-13 18:55")
    assert next_review(pd.Timestamp("2026-10-13 19:00")) == pd.Timestamp("2026-10-14 18:55")
    assert next_review(pd.Timestamp("2026-10-16 19:00")) == pd.Timestamp("2026-10-19 18:55")  # Friday evening -> Monday


def test_a_long_curve_is_thinned_but_keeps_both_ends():
    series = pd.Series(range(1000), index=pd.date_range("2026-01-01", periods=1000, freq="15min"), dtype=float)
    points = compact_series(series, limit=50)
    assert len(points) <= 50
    assert points[0] == ["2026-01-01T00:00:00", 0.0]
    assert points[-1][1] == 999.0
    assert compact_series(pd.Series(dtype=float)) == []


def test_held_since_is_the_first_buy_after_the_last_sale():
    orders = pd.DataFrame(
        {
            "entity_id": ["a", "a", "a", "a", "b"],
            "order_type": ["order_long", "order_close_long", "order_long", "order_long", "dividend"],
            "timestamp": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"]),
        }
    )
    assert held_since(orders, "a") == pd.Timestamp("2026-10-05")
    assert held_since(orders, "b") is None
    assert held_since(pd.DataFrame(), "a") is None


def test_the_status_words_cover_the_states_a_goat_can_be_in():
    now = pd.Timestamp("2026-10-13 11:00")
    assert (
        status_for(
            "intraday", OPEN, now, holdings=0, slots=3, entries=3, cap=3, day_trade=True, last_poll=now, watching=63
        )["code"]
        == "BENCHED"
    )
    assert status_for("intraday", OPEN, now, holdings=2, slots=5, last_poll=now, watching=12)["code"] == "GRAZING"
    assert status_for("intraday", OPEN, now, holdings=0, slots=5, last_poll=now, watching=12)["code"] == "WATCHING"
    assert (
        status_for("intraday", OPEN, now, holdings=2, slots=5, last_poll=now - pd.Timedelta(hours=2))["code"]
        == "DOZING"
    )
    assert status_for("intraday", CLOSED, now, holdings=0, slots=3, day_trade=True)["code"] == "FLAT"
    assert status_for("intraday", CLOSED, now, holdings=2, slots=5)["code"] == "GRAZING"
    assert (
        status_for(
            "daily",
            CLOSED,
            now,
            holdings=10,
            slots=10,
            last_session=pd.Timestamp("2026-10-12"),
            expected_session=pd.Timestamp("2026-10-12"),
        )["code"]
        == "GRAZING"
    )
    assert (
        status_for(
            "daily",
            CLOSED,
            now,
            holdings=10,
            slots=10,
            last_session=pd.Timestamp("2026-10-09"),
            expected_session=pd.Timestamp("2026-10-12"),
        )["code"]
        == "BEHIND"
    )
    assert status_for("daily", CLOSED, now, holdings=0, slots=10)["code"] == "WAITING"


def test_the_gate_lists_the_refused_buys_of_the_latest_day_once_each():
    signals = [
        {
            "kind": "signal",
            "code": "BUY",
            "t": "2026-10-08T15:45:00",
            "goat": "g",
            "stock": "MPCC",
            "outcome": "skipped: too close to the close",
        },
        {
            "kind": "signal",
            "code": "BUY",
            "t": "2026-10-08T15:30:00",
            "goat": "g",
            "stock": "MPCC",
            "outcome": "skipped: too close to the close",
        },
        {
            "kind": "signal",
            "code": "BUY",
            "t": "2026-10-07T10:00:00",
            "goat": "g",
            "stock": "OKEA",
            "outcome": "skipped: no free slot",
        },
        {
            "kind": "signal",
            "code": "SELL",
            "t": "2026-10-08T15:45:00",
            "goat": "g",
            "stock": "FRO",
            "outcome": "ordered",
        },
        {"kind": "fill", "code": "BUY", "t": "2026-10-08T15:45:00", "goat": "g", "stock": "FRO"},
    ]
    gate = gate_items(signals)
    assert gate["day"] == "2026-10-08"
    assert gate["items"] == [
        {"t": "2026-10-08T15:45:00", "goat": "g", "stock": "MPCC", "why": "too close to the close"}
    ]
    assert gate_items([]) == {"day": None, "items": []}


def test_the_default_goats_are_written_once_validated_and_saved_back():
    config = load_config()
    assert config.created and [g.id for g in config.goats] == ["lillebukk", "mellombukk", "storebukk"]
    assert not load_config().created
    config.rewrites = 2
    config.goats[0].lineage.append(
        {"account": "old", "from": "2026-10-01T00:00:00", "to": "2026-10-09T18:55:00", "value": 99000.0, "why": "slow"}
    )
    save_config(config)
    again = load_config()
    assert (
        again.rewrites == 2
        and again.goats[0].lineage[0]["account"] == "old"
        and again.path.read_text(encoding="utf-8").startswith("# The three goats")
    )
    with pytest.raises(ValueError):
        GoatConfig(id="bad id", name="x", account="y")
    with pytest.raises(ValueError):
        GoatConfig(id="ok", name="x", account="y", accent="purple")


def test_the_troll_log_keeps_entries_in_order_and_knows_the_goats():
    load_config()
    assert load_troll()["entries"] == []
    first = add_troll_entry("Who is that tripping over my bridge?", kind="intro", at="2026-10-13T07:40:00Z")
    add_troll_entry("  Lillebukk pays   the toll.  ", kind="verdict", goat="lillebukk")
    log = load_troll()
    assert (
        log["entries"][0] == first
        and log["entries"][1]["text"] == "Lillebukk pays the toll."
        and log["entries"][1]["goat"] == "lillebukk"
    )
    assert log["reviewed_at"] == log["entries"][1]["t"] and log["entries"][1]["t"].endswith("Z")
    with pytest.raises(LookupError):
        add_troll_entry("nobody", goat="trollet")
    with pytest.raises(ValueError):
        add_troll_entry("x", kind="shout")
    with pytest.raises(ValueError):
        add_troll_entry("   ")


def test_changes_are_parsed_into_typed_values_and_nested_keys():
    assert parse_change("signal.lookback=40") == (["signal", "lookback"], 40)
    assert parse_change("stop_loss=0.03") == (["stop_loss"], 0.03)
    assert parse_change("day_trade=true") == (["day_trade"], True)
    assert parse_change("entry_window=09:30,14:00") == (["entry_window"], ["09:30", "14:00"])
    assert parse_change("take_profit=null") == (["take_profit"], None)
    with pytest.raises(ValueError):
        parse_change("nonsense")
    assert sessions_since("2026-10-06", pd.Timestamp("2026-10-13 10:00")) == 5


def test_a_rewrite_forks_the_account_and_the_goat_follows_the_fork(home):
    from osloquant.intraday import engine as intraday

    intraday.load_config()  # writes the default intraday.yaml with daytrade_orb in it
    config = load_config()
    now = pd.Timestamp("2026-10-13 18:55")
    with pytest.raises(PermissionError):  # no state: the account counts as started now, so it is too young
        rewrite("lillebukk", ["stop_loss=0.03"], "too tight", config=config, now=now)
    result = rewrite(
        "lillebukk",
        ["stop_loss=0.03", "max_entries_per_day=2", "signal.minutes=45"],
        "stopped out six times in a week",
        config=config,
        now=now,
        force=True,
    )
    assert result["old"] == "daytrade_orb" and result["new"] == "lillebukk_v2" and result["value"] == 100000
    accounts = {a.name: a for a in intraday.load_config().accounts}
    assert "daytrade_orb" in accounts, "the old account keeps running"
    new = accounts["lillebukk_v2"]
    assert (new.stop_loss, new.max_entries_per_day, new.signal["minutes"], new.input_money, new.day_trade) == (
        0.03,
        2,
        45,
        100000,
        True,
    )
    assert (
        "rewritten by the troll on 2026-10-13 18:55 from daytrade_orb: stopped out six times in a week"
        in intraday.config_path().read_text(encoding="utf-8")
    )
    again = load_config()
    goat = again.goat("lillebukk")
    assert (
        goat.account == "lillebukk_v2"
        and goat.lineage[0]["account"] == "daytrade_orb"
        and goat.lineage[0]["changes"] == {"stop_loss": 0.03, "max_entries_per_day": 2, "signal.minutes": 45}
    )
    assert again.rewrites == 1
    entry = load_troll()["entries"][-1]
    assert entry["kind"] == "rewrite" and entry["goat"] == "lillebukk" and "lillebukk_v2 starts there" in entry["text"]
    with pytest.raises(ValueError):  # the name is taken now
        rewrite("lillebukk", ["stop_loss=0.04"], "again", config=again, now=now, force=True, name="daytrade_orb")
    with pytest.raises(ValueError):
        rewrite("lillebukk", [], "no change", config=again, now=now, force=True)


def test_a_broken_rewrite_leaves_the_file_as_it_was(home):
    from osloquant.intraday import engine as intraday

    intraday.load_config()
    before = intraday.config_path().read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        rewrite(
            "lillebukk",
            ["entry_window=07:00,23:00"],
            "nonsense window",
            config=load_config(),
            now=pd.Timestamp("2026-10-13 18:55"),
            force=True,
        )
    assert intraday.config_path().read_text(encoding="utf-8") == before
    assert load_config().rewrites == 0


def test_an_empty_store_exports_missing_goats_and_the_cli_writes_the_files(home):
    config = GoatsConfig(goats=[GoatConfig(id="g1", name="One", account="nobody")])
    add_troll_entry("first word", kind="intro")
    doc = export(config, now=pd.Timestamp("2026-10-13 10:00"))
    assert doc["meta"]["schema"] == "goats/1" and doc["meta"]["market"]["open"] is True and doc["meta"]["goats"] == 0
    assert doc["goats"][0]["missing"] is True and doc["goats"][0]["status"]["code"] == "MISSING"
    assert doc["herd"]["items"] == [] and doc["stream"]["items"] == [] and doc["gate"]["items"] == []
    assert doc["troll"]["entries"][0]["text"] == "first word" and doc["troll"]["rewrites"] == 0
    written = write(doc, out=home / "out" / "goats.json", split=home / "split")
    assert (home / "split" / "goats" / "g1.json").exists() and (home / "split" / "troll" / "log.json").exists()
    assert json.loads(written[0].read_text(encoding="utf-8"))["goats"][0]["id"] == "g1"

    result = runner.invoke(app, ["goats", "--split", str(home / "cli")])
    assert result.exit_code == 0, result.output
    assert "Wrote the default goats" in result.output and (home / "cli" / "stream" / "latest.json").exists()
    result = runner.invoke(app, ["goats", "troll", "Out of the honey, goat.", "--kind", "handsoff"])
    assert result.exit_code == 0, result.output
    assert load_troll()["entries"][-1]["kind"] == "handsoff"
    result = runner.invoke(app, ["goats", "troll"])
    assert result.exit_code == 0 and "Out of the honey" in result.output


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_publishing_puts_the_files_on_a_single_commit_branch_and_keeps_the_rest(tmp_path):
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", "--quiet", str(remote)], check=True)
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    env_args = ["-c", "user.name=t", "-c", "user.email=t@t"]
    (repo / "a.json").write_text('{"a": 1}', encoding="utf-8")
    (repo / "b.json").write_text('{"b": 1}', encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), *env_args, "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)

    first = publish_branch({"goats.json": repo / "a.json", "troll.json": repo / "b.json"}, repo=repo, branch="goats")
    (repo / "a.json").write_text('{"a": 2}', encoding="utf-8")
    second = publish_branch({"goats.json": repo / "a.json"}, repo=repo, branch="goats")
    assert first != second

    def show(ref: str, path: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True, text=True, check=True
        ).stdout

    assert show("origin/goats", "goats.json") == '{"a": 2}' and show("origin/goats", "troll.json") == '{"b": 1}', (
        "the other file survived"
    )
    parents = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "goats"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert parents == "1", "the branch never grows"
    assert not (repo / "goats.json").exists(), "the working tree is untouched"


def test_decision_times_are_marked_utc_and_bar_times_stay_oslo():
    names = pd.DataFrame({"code": ["EQNR"], "name": ["Equinor"]}, index=pd.Index(["stock_ol_EQNR"], name="entity_id"))
    signals = pd.DataFrame(
        {"entity_id": ["stock_ol_EQNR"], "timestamp": [pd.Timestamp("2026-10-13 09:45")], "decided_at": [pd.Timestamp("2026-10-13 08:01:07")],
         "code": ["BUY"], "rule": ["breakout"], "reason": ["close above"], "price": [400.0], "outcome": ["ordered"]}
    )  # fmt: skip
    item = _signal_items("g", signals, names)[0]
    assert item["t"] == "2026-10-13T09:45:00" and item["at"] == "2026-10-13T08:01:07Z" and item["stock"] == "EQNR"
    orders = pd.DataFrame(
        {"entity_id": ["stock_ol_EQNR"], "timestamp": [pd.Timestamp("2026-10-13 10:00")], "decided_at": [pd.Timestamp("2026-10-13 08:01:07")],
         "order_type": ["order_long"], "order_price": [401.0], "order_amount": [50.0], "cost": [30.0], "profit": [float("nan")], "profit_rate": [float("nan")],
         "reason": ["BUY breakout: close above"], "forward": [1.0]}
    )  # fmt: skip
    fill = _fill_items("g", orders, names)[0]
    assert (
        fill["at"].endswith("Z")
        and fill["t"] == "2026-10-13T10:00:00"
        and fill["pnl"] is None
        and fill["value"] == 401.0 * 50
        and fill["forward"] is True
    )
