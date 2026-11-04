"""Narrative against numbers (D53): a full case's view needs the story in one sentence and its three numbers; each is
set beside the model's and a gap beyond 1 pp (growth, margin) or 10 % (EPS) is flagged on the row and the stock page.
Fictional estimates only."""

from __future__ import annotations

import json

import pytest

from osloquant import judgements as jg
from osloquant.dashboard import reportpdf as rpdf
from osloquant.dashboard import story as sty

from .test_dashboard import GOOD, app  # noqa: F401  (fixture)

EST = {"years": [2026, 2027, 2028, 2029, 2030], "rows": {"rev": [100.0, 110.0, 121.0, 133.1, 140.0], "ebitda": [20.0, 22.0, 24.2, 26.62, 28.0],
                                                        "eps": [2.0, 2.2, 2.4, 2.6, 2.8]}}


def test_model_numbers_and_flags():
    m = sty.model_numbers(EST)
    assert m["rev_cagr"] == pytest.approx(0.10) and m["ebitda_m"] == pytest.approx(0.20) and m["eps"] == 2.6 and m["year"] == 2029
    story = sty.parse({"story": "Fictional: steady growth on a fixed cost base lifts the margin.", "story_rev_cagr": "10", "story_ebitda_m": "23,5 %", "story_eps": "2.6"})
    assert story["ebitda_m"] == pytest.approx(0.235)
    fl = sty.flags(story, m)
    assert len(fl) == 1 and "EBITDA-margin 2029: the story needs 23.5 %, the model has 20.0 % – the story is bigger than the model" == fl[0]
    assert sty.problems({"sentence": "short"}, m)[0].startswith("a full case needs its story") and sty.problems({"sentence": ""}, None) == []
    assert "give the numbers the story needs" in sty.problems({"sentence": "Fictional sentence long enough here"}, m)[0]


def test_a_full_case_view_carries_its_story(app):  # noqa: F811
    client, _ = app
    folder = rpdf.folder("AAA")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "estimates_2026-11-02.json").write_text(json.dumps(EST), encoding="utf-8")
    form = client.get("/stock/AAA").get_data(as_text=True)
    assert "Fortelling mot tall (Damodaran)" in form and 'name="story_ebitda_m"' in form and "Modellen: 20.0 %" in form
    r = client.post("/stock/AAA/judge", data=GOOD)
    assert r.status_code == 400 and "needs its story" in r.get_data(as_text=True)
    ok = GOOD | {"story": "Fictional: steady growth on a fixed cost base lifts the margin.", "story_rev_cagr": "10", "story_ebitda_m": "25", "story_eps": "2.6"}
    assert client.post("/stock/AAA/judge", data=ok).status_code == 303
    st = jg.read_log()[-1]["story"]
    assert st["numbers"]["ebitda_m"] == pytest.approx(0.25) and st["model"]["year"] == 2029 and len(st["flags"]) == 1
    page = client.get("/stock/AAA").get_data(as_text=True)
    assert "Historien og modellen sier ikke det samme" in page and "Fictional: steady growth" in page
    assert client.post("/stock/BBB/judge", data=GOOD).status_code == 303                     # no report for BBB: no story asked
