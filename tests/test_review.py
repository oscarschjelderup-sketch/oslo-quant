"""The quarterly error review (D49): the scored views largest miss first, fixed questions, one review row per view and
quarter, and the summary (foresight from the pre-mortem, luck, recurring biases). Temporary home, fictional rows."""

from __future__ import annotations

import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant.dashboard import review as rv

from .test_dashboard import GOOD, app  # noqa: F401  (fixture)

ANSWERS = {"premortem_hit": "2", "info_available": "delvis", "cause": "beslutningen", "bias": "ankring til eget kursmål",
           "lesson": "Fictional lesson: reset the target from the model, not from the last one."}


def _table(rows):
    return pd.DataFrame([{"seq": r["seq"], "code": r["code"], "date": r["date"], "rating": r["rating"], "target": r["target"], "price": r["price"],
                          "price_now": r["price"] * f, "vs_target": r["price"] * f / r["target"] - 1, "excess_osebx": f - 1.05, "status": "provisional"}
                         for r, f in zip(rows, (0.8, 1.15), strict=True)])


def test_items_are_sorted_by_the_largest_miss_and_marked_when_reviewed(home):
    a = jg.append("judgement", dict(code="AAA", date="2026-07-01", price=100.0, rating="BUY", target=130.0, horizon_months=12, kill=["x 1"]))
    b = jg.append("judgement", dict(code="BBB", date="2026-07-01", price=50.0, rating="BUY", target=60.0, horizon_months=12, kill=["y 2"]))
    rows = jg.read_log()
    its = rv.items(rows, _table([a, b]), pd.Timestamp("2026-11-05"))
    assert [i["code"] for i in its] == ["AAA", "BBB"] and its[0]["vs_target"] == pytest.approx(80 / 130 - 1) and its[0]["quarter"] == "2026Q4"
    assert rv.quarter(pd.Timestamp("2027-02-01")) == "2027Q1"
    with pytest.raises(ValueError, match="what you will do differently"):
        rv.write(a["seq"], ANSWERS | {"lesson": "short"}, pd.Timestamp("2026-11-05"))
    with pytest.raises(ValueError, match="answer:"):
        rv.write(a["seq"], ANSWERS | {"cause": "the stars"}, pd.Timestamp("2026-11-05"))
    row = rv.write(a["seq"], ANSWERS, pd.Timestamp("2026-11-05"))
    assert row["kind"] == "review" and row["quarter"] == "2026Q4" and row["answers"]["premortem_hit"] == "2" and jg.verify().ok
    with pytest.raises(ValueError, match="already reviewed"):
        rv.write(a["seq"], ANSWERS, pd.Timestamp("2026-12-01"))
    rv.write(a["seq"], ANSWERS | {"premortem_hit": "ingen av dem", "cause": "flaks"}, pd.Timestamp("2027-01-10"))   # next quarter: again
    its = rv.items(jg.read_log(), _table([a, b]), pd.Timestamp("2026-11-05"))
    assert its[0]["review"]["seq"] == row["seq"] and its[1]["review"] is None
    s = rv.summary(jg.read_log())
    assert s["n"] == 2 and s["failed"] == 2 and s["foreseen"] == 1 and s["foresight_rate"] == 0.5 and s["luck"] == 1
    assert s["biases"] == {"ankring til eget kursmål": 2} and len(s["lessons"]) == 2


def test_the_review_page_and_its_form(app):  # noqa: F811
    client, _ = app
    assert client.post("/stock/AAA/judge", data=GOOD).status_code == 303
    page = client.get("/review").get_data(as_text=True)
    assert "Feilgjennomgang" in page and ">Feil</a>" in page and "Dalio" in page
    seq = jg.read_log()[-1]["seq"]
    r = client.post(f"/review/{seq}", data=ANSWERS)
    body = r.get_data(as_text=True)
    if "no view" in body or r.status_code == 400:                                          # unscored (no prices in the synthetic store): still writes
        assert "answer:" not in body
    assert jg.read_log()[-1]["kind"] == "review" and jg.verify().ok
    assert client.post(f"/review/{seq}", data=ANSWERS).status_code == 400                   # once per quarter
