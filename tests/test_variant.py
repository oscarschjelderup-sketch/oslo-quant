"""Variant and catalyst (D55): a BUY or SELL names its edge, what the price misses and a dated catalyst inside the
horizon; HOLD is not asked; a passed catalyst date puts a question on the front page. Fictional rows only."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from osloquant import judgements as jg
from osloquant.dashboard import variant as vrt

from .test_dashboard import GOOD, app  # noqa: F401  (fixture)


def test_a_buy_needs_its_edge_and_a_dated_catalyst(app):  # noqa: F811
    client, _ = app
    bare = {k: v for k, v in GOOD.items() if k not in ("variant_kind", "variant_edge", "catalyst", "catalyst_by")}
    r = client.post("/stock/BBB/judge", data=bare)
    assert r.status_code == 400 and "which kind of edge" in r.get_data(as_text=True) and "name the catalyst" in r.get_data(as_text=True)
    late = GOOD | {"catalyst_by": (date.today() + timedelta(days=500)).isoformat()}
    assert "inside the horizon" in client.post("/stock/BBB/judge", data=late).get_data(as_text=True)
    assert client.post("/stock/BBB/judge", data=bare | {"rating": "HOLD"}).status_code == 303          # HOLD is not asked
    assert client.post("/stock/BBB/judge", data=GOOD).status_code == 303
    v = jg.read_log()[-1]["variant"]
    assert v["kind"] == "analytical" and v["by"] == GOOD["catalyst_by"]
    assert "Variant og katalysator" in client.get("/stock/BBB").get_data(as_text=True)


def test_a_passed_catalyst_date_asks_on_the_front_page():
    class C:
        code, name = "AAA", "Fictional A"
        view = {"seq": 1, "variant": {"kind": "analytical", "edge": "x" * 20, "catalyst": "Fictional: margin in Q4", "by": "2026-11-01"}}
        history = [{"kind": "judgement", "date": "2026-10-01"}]
    d = vrt.due([C()], pd.Timestamp("2026-11-05"))
    assert d and d[0]["days"] == 4 and d[0]["catalyst"].startswith("Fictional")
    C.history = C.history + [{"kind": "kill_check", "date": "2026-11-03"}]
    assert vrt.due([C()], pd.Timestamp("2026-11-05")) == []
    assert vrt.problems(vrt.parse({}), "HOLD", "2026-11-05") == []
