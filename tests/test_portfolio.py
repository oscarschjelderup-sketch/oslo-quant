"""The book as one thing: kill drivers read from tags or words, shared drivers across open BUY views, sector
concentration, and the optional loss cap per sector group in the sizing."""

from __future__ import annotations

import pytest

from osloquant.dashboard import book as bk
from osloquant.dashboard import portfolio as pf
from osloquant.dashboard import sizing


def test_driver_from_tag_or_words():
    assert pf.driver_of("Gross margin below 49% [margin]") == ("margin", "tag")
    assert pf.driver_of("Net club openings below the committed pipeline") == ("volume", "inferred")
    assert pf.driver_of("Price/mix below 2% a year") == ("pricing", "inferred")
    assert pf.driver_of("NIBD / EBITDAaL above 2.5x") == ("leverage", "inferred")
    assert pf.driver_of("Something unusual happens") == ("other", "none")
    assert pf.driver_of("Personnel costs above 37% of revenue [volume]") == ("volume", "tag")     # the tag wins over the words


def _case(code, group_kill, rating="BUY", loss=None):
    view = {"rating": rating, "target": 100, "loss_at_kill": loss}
    return bk.Case(code, code, view, "log #1", [], group_kill, None, [])


def test_exposure_finds_shared_drivers_and_one_group():
    cases = [_case("AAA", ["Margin below 10% [margin]", "Store openings below plan"], loss=2000),
             _case("BBB", ["EBIT margin below 11%", "Debt above 3x"], loss=1800),
             _case("CCC", ["Anything"], rating="HOLD")]
    ex = pf.exposure(cases, {"AAA": "Consumer", "BBB": "Consumer", "CCC": "Energy"}, {"paper_capital": 100000})
    assert ex["views"] == 2 and ex["one_group"] and ex["shared_drivers"] == {"margin": ["AAA", "BBB"]}
    assert ex["total_loss_at_kill"] == 3800 and ex["total_loss_share"] == pytest.approx(0.038)
    assert ex["drivers"]["margin"]["loss"] == 3800 and ex["drivers"]["volume"]["cases"] == ["AAA"]
    w = pf.warnings(ex)
    assert any("one sector group" in x for x in w) and any("same driver – margin: AAA, BBB" in x for x in w)
    html = pf.block_html(ex)
    assert "Boken samlet" in html and "margin" in html and "AAA" in html
    spread = pf.exposure(cases, {"AAA": "Consumer", "BBB": "Energy", "CCC": "Energy"}, None)
    assert not spread["one_group"] and spread["total_loss_share"] is None


def test_loss_cap_per_sector_group(home):
    cfg = {"paper_capital": 100000, "max_loss": 2000, "max_position": 0.25, "max_loss_per_group": 3000}
    rows = [{"seq": 1, "kind": "judgement", "code": "AAA", "rating": "BUY", "position_shares": 100, "position_value": 10000, "loss_at_kill": 1995}]
    groups = {"AAA": "Consumer", "BBB": "Consumer", "CCC": "Energy"}
    same = sizing.size(100.0, 90.0, cfg, "BBB", rows, group="Consumer", groups=groups)
    assert same.binding == "loss in the Consumer group" and same.shares == 95                     # (3000 - 1995) / 10.5
    other = sizing.size(100.0, 90.0, cfg, "CCC", rows, group="Energy", groups=groups)
    assert other.binding == "max loss" and other.shares == 190
    _, problems = sizing.check(120, 100.0, 90.0, cfg, "BBB", rows, group="Consumer", groups=groups)
    assert any("Consumer group" in p for p in problems)
