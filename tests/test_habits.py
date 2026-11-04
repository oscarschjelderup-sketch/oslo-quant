"""The loops on the front page (D48–D52): an unanswered report asks for the probability update and replaces the
post-report item, a near report asks for the quarterly forecast until it is logged, undecided proposals of the
stored chief run are listed, and the error review appears in the last three weeks of a quarter. Temporary home,
fictional rows only."""

from __future__ import annotations

import pandas as pd

from osloquant import judgements as jg
from osloquant.dashboard import afterreport as ar
from osloquant.dashboard import chief as ch
from osloquant.dashboard import forecasts as fc
from osloquant.dashboard import today as td

from .test_dashboard import app  # noqa: F401  (fixture)


class Case:
    def __init__(self, code, view=True, events=()):
        self.code, self.name, self.events = code, f"Fictional {code}", list(events)
        self.view = {"date": "2026-07-01"} if view else None
        self.claude_view, self.history, self.kill, self.model = None, [], [], None


def _view(code="AAA", date="2026-07-01"):
    return jg.append("judgement", dict(code=code, date=date, price=100.0, rating="BUY", target=120.0, horizon_months=12, p_bear=0.2, p_base=0.6, p_bull=0.2,
                                       kill=["fictional 1"]))


def test_update_and_forecast_items_come_and_go(home, monkeypatch):
    _view()
    rep = {"date": "2026-10-20", "what": "Q3 2026 report", "source": "report reader"}
    monkeypatch.setattr(ar, "newest_report", lambda c, today, cal_doc=None, code=None: rep if code == "AAA" else None)
    nxt = {"date": "2026-11-12", "what": "Q4 report", "source": "research book"}
    monkeypatch.setattr(fc, "upcoming", lambda code, cases, today: nxt if code == "AAA" else None)
    items = td.habit_items([Case("AAA")], pd.Timestamp("2026-11-05"))
    kinds = {i.kind: i for i in items}
    assert kinds["update"].code == "AAA" and kinds["update"].urgency == 0 and "ikke oppdatert" in kinds["update"].detail   # 16 days: overdue
    assert kinds["forecast"].code == "AAA" and "7 d" in kinds["forecast"].title
    post = td.Item("AAA", "post-report", "t", "d", 1)
    merged = td.merge_items([post], items)
    assert not any(i.kind == "post-report" for i in merged)                                  # the update question replaces it
    jg.append("forecast", dict(code="AAA", date="2026-11-05", report=nxt, metric="revenue", low=1.0, mid=2.0, high=3.0))
    jg.append("update", dict(code="AAA", date="2026-11-05", ref_seq=1, trigger=rep, changed=False, p_bear=0.2, p_base=0.6, p_bull=0.2, reason="fictional reason"))
    assert td.habit_items([Case("AAA")], pd.Timestamp("2026-11-05")) == []


def test_chief_and_review_items(home, monkeypatch):
    monkeypatch.setattr(ar, "newest_report", lambda *a, **k: None)
    monkeypatch.setattr(fc, "upcoming", lambda *a, **k: None)
    _view(date="2026-07-01")
    c = ch.Ctx(rows=jg.read_log(), table=pd.DataFrame(), today=pd.Timestamp("2026-11-10"), sizing=None)
    ch.write_run(ch.run(c, decisions=[]))
    items = td.habit_items([Case("AAA")], pd.Timestamp("2026-11-10"))
    assert [i.kind for i in items] == ["chief"] and "forslag venter" in items[0].title         # mid-quarter: no review item yet
    late = td.habit_items([Case("AAA")], pd.Timestamp("2026-12-15"))
    rv_item = next(i for i in late if i.kind == "review")
    assert "2026Q4: 1 vurderinger venter" in rv_item.title


def test_the_front_page_links_the_loops(app, monkeypatch):  # noqa: F811
    client, _ = app
    monkeypatch.setattr(td, "habit_items", lambda cases, today, rows=None, cal_doc=None: [td.Item("", "chief", "Analysesjefen: 2 forslag venter", "x", 2)])
    page = client.get("/").get_data(as_text=True)
    assert '<a href="/chief">Analysesjefen: 2 forslag venter</a>' in page
