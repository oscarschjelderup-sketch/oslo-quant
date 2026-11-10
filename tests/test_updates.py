"""The update log (D48): a report after the open view puts the question on the stock page, the answer is an
``update`` row (changed probabilities, or unchanged with a reason), an unanswered report older than 14 days counts
as not updated, and a final view's Brier is set beside its last update's. Temporary home, fictional rows only."""

from __future__ import annotations

import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant.dashboard import afterreport as ar
from osloquant.dashboard import updates as up

from .test_dashboard import app  # noqa: F401  (fixture)

VIEW = dict(code="AAA", name="Alpha", date="2026-10-01", price=100.0, rating="BUY", target=120.0, horizon_months=12, bear=80.0, base=118.0, bull=150.0,
            p_bear=0.25, p_base=0.5, p_bull=0.25, kill=["fictional: margin below 10%"], thesis="Fictional thesis for the update test.")
REPORT = {"date": "2026-10-20", "what": "Q3 2026 report", "source": "report reader"}


def test_a_report_after_the_view_is_pending_and_overdue_after_14_days(home, monkeypatch):
    jg.append("judgement", VIEW)
    monkeypatch.setattr(ar, "newest_report", lambda c, today, cal_doc=None, code=None: REPORT if code == "AAA" else None)
    p = up.pending(jg.read_log(), [], pd.Timestamp("2026-10-25"))
    assert [x["code"] for x in p] == ["AAA"] and p[0]["days"] == 5 and not p[0]["overdue"] and p[0]["view_seq"] == 1
    late = up.pending(jg.read_log(), [], pd.Timestamp("2026-11-10"))
    assert late[0]["overdue"] and late[0]["days"] == 21
    monkeypatch.setattr(ar, "newest_report", lambda c, today, cal_doc=None, code=None: {**REPORT, "date": "2026-09-20"})
    assert up.pending(jg.read_log(), [], pd.Timestamp("2026-11-10")) == []              # the report came before the view


def test_the_answer_is_an_update_row_and_resolves_the_question(app, monkeypatch):  # noqa: F811
    client, _ = app
    jg.append("judgement", VIEW)
    monkeypatch.setattr(ar, "newest_report", lambda c, today, cal_doc=None, code=None: REPORT if code == "AAA" else None)
    page = client.get("/stock/AAA").get_data(as_text=True)
    assert "Har sannsynligheten din endret seg?" in page and "Q3 2026 report" in page and 'action="/stock/AAA/update"' in page
    trig = {"trigger_date": REPORT["date"], "trigger_what": REPORT["what"], "trigger_source": REPORT["source"]}
    r = client.post("/stock/AAA/update", data=trig)
    assert r.status_code == 400 and "why the news does not change" in r.get_data(as_text=True)
    r = client.post("/stock/AAA/update", data=trig | {"changed": "1", "p_bear": "0.3", "p_base": "0.5", "p_bull": "0.3"})
    assert r.status_code == 400 and "sum to 1,10" in r.get_data(as_text=True)
    r = client.post("/stock/AAA/update", data=trig | {"changed": "1", "p_bear": "0.35", "p_base": "0.45", "p_bull": "0.2"})
    assert r.status_code == 303
    row = jg.read_log()[-1]
    assert row["kind"] == "update" and row["ref_seq"] == 1 and row["changed"] and row["p_bear"] == 0.35 and row["prior"] == [0.25, 0.5, 0.25]
    assert row["trigger"]["what"] == "Q3 2026 report" and jg.verify().ok
    after = client.get("/stock/AAA").get_data(as_text=True)
    assert "Har sannsynligheten din endret seg?" not in after and "oppdatering av #1" in after
    assert jg.latest_by_code()["AAA"]["seq"] == 1                                         # an update is not a new view
    r = client.post("/stock/AAA/update", data=trig | {"reason": "Fictional: the quarter was as expected."})
    assert r.status_code == 303 and jg.read_log()[-1]["changed"] is False and jg.read_log()[-1]["p_bear"] == 0.25   # unchanged keeps the view's


def test_brier_of_the_last_update_is_set_beside_the_original(home, monkeypatch):
    jg.append("judgement", VIEW)
    jg.append("update", dict(code="AAA", date="2026-10-21", ref_seq=1, trigger=REPORT, changed=True, p_bear=0.6, p_base=0.3, p_bull=0.1))
    monkeypatch.setattr(ar, "newest_report", lambda *a, **k: None)
    table = pd.DataFrame([{"seq": 1, "code": "AAA", "status": "final", "scenario_hit": "bear"}])
    sc = up.scoring(jg.read_log(), table, pd.Timestamp("2027-10-02"))
    pair = sc["pairs"][0]
    assert pair["brier_view"] == pytest.approx(0.75 ** 2 + 0.5 ** 2 + 0.25 ** 2) and pair["brier_updated"] == pytest.approx(0.4 ** 2 + 0.3 ** 2 + 0.1 ** 2)
    assert sc["answered"] == 1 and sc["unchanged"] == 0 and "bedre" in up.calibration_html(sc)
    with pytest.raises(ValueError, match="sum to 1"):
        jg.append("update", dict(code="AAA", date="2026-10-22", ref_seq=1, trigger=REPORT, changed=True, p_bear=0.6, p_base=0.6, p_bull=0.1))
