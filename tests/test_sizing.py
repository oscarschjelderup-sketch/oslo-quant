"""Position size in the judgement form: the kill level is the stop, the smallest limit binds and is named, and a
judgement whose loss at the kill level is over the limit is refused without writing anything."""

from __future__ import annotations

import pytest

from osloquant import judgements as jg
from osloquant.dashboard import book as bk
from osloquant.dashboard import sizing

CFG = {"paper_capital": 100000, "max_loss": 2000, "max_position": 0.25}
FORM = {"rating": "BUY", "target": 130, "rationale": "A rationale that says why, long enough.", "kill": ["margin below 10%"]}


def _config(home, **kw):
    import yaml

    (home / sizing.CONFIG).write_text(yaml.safe_dump({"sizing": {**CFG, **kw}}), encoding="utf-8")


def test_size_takes_the_smallest_limit_and_names_it():
    s = sizing.size(100.0, 90.0, CFG)                        # loss per share 10 + 0.5 = 10.5
    assert s.loss_per_share == pytest.approx(10.5)
    assert s.limits == {"max loss": 190, "max position": 250, "free paper sum": 1000}
    assert (s.shares, s.binding) == (190, "max loss") and s.loss_at_kill == pytest.approx(1995.0)
    wide = sizing.size(100.0, 99.0, CFG)                     # a tight stop: the position cap binds
    assert (wide.shares, wide.binding) == (250, "max position")
    with pytest.raises(ValueError, match="below the price"):
        sizing.size(100.0, 100.0, CFG)


def test_check_refuses_a_loss_over_the_limit():
    _, problems = sizing.check(190, 100.0, 90.0, CFG, "AAA")
    assert problems == []
    _, problems = sizing.check(200, 100.0, 90.0, CFG, "AAA")
    assert len(problems) == 1 and "above your limit of NOK 2" in problems[0] and "at most 190 shares" in problems[0]


def test_the_form_writes_the_size_and_blocks_over_the_limit(home):
    _config(home)
    with pytest.raises(ValueError, match="needs a kill level"):
        bk.write_judgement("AAA", "Alpha", {**FORM}, 100.0, "2026-10-22", "test")
    with pytest.raises(ValueError, match="above your limit"):
        bk.write_judgement("AAA", "Alpha", {**FORM, "kill_level": 90, "position_shares": 500}, 100.0, "2026-10-22", "test")
    assert not jg.log_path().exists() or jg.read_log() == []                  # nothing written
    row = bk.write_judgement("AAA", "Alpha", {**FORM, "kill_level": 90}, 100.0, "2026-10-22", "test")
    assert row["position_shares"] == 190 and row["loss_at_kill"] == pytest.approx(1995.0)
    assert row["sizing"]["binding"] == "max loss" and row["sizing"]["max_loss"] == 2000
    # the open position takes its share of the paper sum from the next stock's free sum
    s = sizing.size(50.0, 49.0, CFG, "BBB")
    assert s.free == pytest.approx(100000 - 19000) and s.limits["free paper sum"] == 1620


def test_hold_and_sell_get_no_size_and_no_limit_means_no_block(home):
    _config(home)
    row = bk.write_judgement("AAA", "Alpha", {**FORM, "rating": "HOLD"}, 100.0, "2026-10-22", "test")
    assert "position_shares" not in row
    (home / sizing.CONFIG).unlink()
    row = bk.write_judgement("BBB", "Beta", {**FORM}, 100.0, "2026-10-22", "test")   # no config: no kill level needed
    assert "position_shares" not in row


def test_total_loss_cap_across_open_views(home):
    _config(home, max_total_loss=3000)
    bk.write_judgement("AAA", "Alpha", {**FORM, "kill_level": 90}, 100.0, "2026-10-22", "test")   # 1995 at risk
    s = sizing.size(100.0, 90.0, CFG | {"max_total_loss": 3000}, "BBB")
    assert s.binding == "total loss, all open views" and s.shares == 95                         # (3000 - 1995) / 10.5
