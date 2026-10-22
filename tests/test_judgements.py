"""The judgement log is append-only and tamper-evident; calibration scores calls against prices."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from osloquant import judgements as jg

T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def _call(**kw):
    base = dict(code="aaa.ol", date="2025-01-02", price=100.0, rating="BUY", target=130.0, horizon_months=12,
                bear=70.0, base=125.0, bull=170.0, p_bear=0.25, p_base=0.5, p_bull=0.25, kill=["margin below 10%"])
    base.update(kw)
    return base


def test_rows_chain_and_any_edit_is_found(tmp_path):
    path = tmp_path / "log.jsonl"
    a = jg.append("judgement", _call(), path, now=T0)
    b = jg.append("judgement", _call(target=140.0, bull=180.0), path, now=T0)
    assert a["code"] == "AAA" and b["prev"] == a["hash"] and b["seq"] == 2
    assert jg.verify(path).ok and jg.verify(path).head == b["hash"]
    lines = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["target"] = 200.0                                     # rewrite history
    path.write_text("\n".join([json.dumps(row), lines[1]]) + "\n", encoding="utf-8")
    check = jg.verify(path)
    assert not check.ok and "content changed" in check.problems[0]
    with pytest.raises(RuntimeError):
        jg.append("note", dict(code="AAA", date="2025-02-01", text="x"), path)
    path.write_text(lines[1] + "\n", encoding="utf-8")       # drop the first row
    assert any("sequence" in p for p in jg.verify(path).problems)


def test_validation(tmp_path):
    path = tmp_path / "log.jsonl"
    with pytest.raises(ValueError, match="rating"):
        jg.append("judgement", _call(rating="STRONG BUY"), path)
    with pytest.raises(ValueError, match="sum to 1"):
        jg.append("judgement", _call(p_bull=0.5), path)
    with pytest.raises(ValueError, match="between"):
        jg.append("judgement", _call(target=200.0), path)
    with pytest.raises(ValueError, match="needs"):
        jg.append("kill_check", dict(code="AAA", date="2025-03-01"), path)
    assert not path.exists() or jg.verify(path).rows == 0


def test_sync_book_logs_only_changed_views(tmp_path):
    path = tmp_path / "log.jsonl"
    book = [{"code": "BBB", "name": "Beta", "rating": "BUY", "valuation_date": "2025-03-03", "price_at_valuation": 98.0,
             "dcf": 125.0, "target": 130, "bear": 70, "bull": 170, "kill": ["x"]},
            {"code": "NOPE", "name": "no view"}]
    assert len(jg.sync_book(book, path)) == 1
    assert jg.sync_book(book, path) == []
    book[0] = {**book[0], "target": 120, "valuation_date": "2025-04-01", "price_at_valuation": 105.0}
    rows = jg.sync_book(book, path)
    assert len(rows) == 1 and rows[0]["seq"] == 2 and jg.verify(path).ok


def _prices(path_closes: dict[str, np.ndarray], start="2025-01-01", idx=None):
    dates = pd.bdate_range(start, periods=len(next(iter(path_closes.values()))))
    adj = pd.DataFrame(path_closes, index=dates)
    index = pd.Series(idx if idx is not None else np.full(len(dates), 1000.0), index=dates)
    return jg.Prices(adjusted=adj, raw=adj.copy(), index=index)


def test_calibration_scores_final_and_provisional_calls(tmp_path):
    path = tmp_path / "log.jsonl"
    n = 400
    up = np.r_[np.linspace(100, 128, 255), np.full(n - 255, 128.0)]   # 128 at the 12-month mark: in band, nearest base 125
    flat = np.full(n, 50.0)
    prices = _prices({"AAA": up, "BBB": flat})
    jg.append("judgement", _call(), path, now=T0)                                           # final by asof
    jg.append("judgement", _call(code="BBB", price=50.0, rating="SELL", target=40.0, bear=30.0, base=40.0, bull=60.0,
                                 date="2026-01-02"), path, now=T0)                           # provisional
    jg.append("kill_check", dict(code="AAA", date="2025-06-02", criterion="margin below 10%", breached=True, action="reviewed"), path)
    rows = jg.read_log(path)
    table, summary = jg.calibration(rows, prices=prices, asof=pd.Timestamp("2026-07-01"))
    a = table.set_index("code").loc["AAA"]
    assert a["status"] == "final" and a["direction_hit"] and not a["target_reached"] and a["in_band"]
    assert a["scenario_hit"] == "base" and a["brier"] == pytest.approx(0.25 ** 2 + 0.5 ** 2 + 0.25 ** 2)
    assert a["kills_breached"] == 1 and a["kills_acted"] == 1
    b = table.set_index("code").loc["BBB"]
    assert b["status"] == "provisional" and "brier" not in b or pd.isna(b.get("brier"))
    assert summary["final"]["n"] == 1 and summary["all_scored"]["n"] == 2 and summary["kills_acted"] == 1
    text = jg.report_markdown(table, summary, jg.verify(path))
    assert "chain verifies" in text and "| 1 | AAA |" in text and "Brier" in text


def test_public_page_states_the_verdict():
    from osloquant.signals_page import public_page

    odds = {"measured": {"from": "2010-01-01", "to": "2026-10-19", "stocks": 64},
            "signals": {"Breakout 60d high + volume": {"kind": "BUY", "per_month": 17.2, "raw20": 0.0144, "exc20": 0.0035,
                                                        "exc60": 0.0128, "hit20": 0.48, "t20": 1.96},
                        "Breakdown below 60d low": {"kind": "RISK", "per_month": 25.3, "raw20": 0.0106, "exc20": -0.0051,
                                                    "exc60": -0.009, "hit20": 0.47, "t20": -2.8}}}
    page = public_page(odds)
    assert "No buy signal pays after costs" in page and "+0.3%" in page or "+0.4%" in page
    assert "Breakdown below 60d low" in page and "-0.9%" in page and "survivorship" in page


def test_recorded_heads_catch_a_rewritten_log(home):
    jg.append("judgement", _call(), now=T0)
    check = jg.verify()
    jg.record_head(check)
    assert jg.heads_consistent(check) == []
    # rewrite the whole log consistently (a new chain) – verify() passes, the recorded head does not
    path = jg.log_path()
    path.unlink()
    jg.append("judgement", _call(target=150.0, bull=180.0), now=T0)
    assert jg.verify().ok
    assert jg.heads_consistent(jg.verify()) and "no longer matches" in jg.heads_consistent(jg.verify())[0]
