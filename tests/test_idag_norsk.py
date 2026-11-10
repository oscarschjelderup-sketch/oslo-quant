"""The front page in Norwegian, with links that land where the action is (docs/forbedring/endringer.md E14)."""

from __future__ import annotations

import re

import pandas as pd

from osloquant import judgements as jg
from osloquant.dashboard import portfolio as pf
from osloquant.dashboard import render as rd
from osloquant.dashboard import server
from osloquant.dashboard import today as td

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home

ENGLISH = ("reached the target", "days old", "past its horizon", "log your view before", "predates the report", "no new signals",
           "can die from the same driver", "sit in one sector group", "renew or retire", "close the case", "log a kill check", "Historically:")


def test_every_kind_of_decision_has_a_norwegian_name_and_a_tab(app):  # noqa: F811
    client, _ = app
    ctx = server.today_context(mark_seen=False)
    kinds = ["kill-check", "re-rate", "re-assess", "stale-view", "pre-report", "post-report", "update", "forecast", "catalyst", "report", "report-tp", "risk-signal"]
    ctx["decisions"] = [td.Item("AAA", k, f"Alpha: {k}", "detail", i % 3) for i, k in enumerate(kinds)] + [td.Item("", "chief", "Analysesjefen", "d", 2),
                                                                                                          td.Item("", "review", "Feilgjennomgang", "d", 2)]
    html = rd.today_page(ctx)
    links = re.findall(r'<b><a href="([^"]+)">Alpha: ([a-z\-]+)</a></b>', html)
    assert dict((k, h) for h, k in links) == {k: f"/aksje/AAA/{td.KIND_TAB[k]}" for k in kinds}
    assert td.KIND_TAB["stale-view"] == "vurdering" and td.KIND_TAB["report"] == "rapporter" and td.KIND_TAB["risk-signal"] == "teknisk"
    assert '<a href="/chief">Analysesjefen</a>' in html and '<a href="/review">Feilgjennomgang</a>' in html
    for k in kinds:                                      # the label a person reads is the Norwegian name, never the key
        assert f">{td.KIND_NO[k]} · ~" in html and f">{k} · ~" not in html
    assert set(td.KIND_NO) >= set(kinds)


def test_the_decisions_the_book_raises_are_written_in_norwegian(app):  # noqa: F811
    client, snap = app
    old = dict(code="AAA", name="Alpha", date="2024-01-02", price=50.0, rating="BUY", target=60.0, horizon_months=12, bear=40.0, base=58.0, bull=80.0,
               p_bear=0.25, p_base=0.5, p_bull=0.25, kill=["fictional: margin below 10%"], thesis="Fictional thesis for the language test.")
    jg.append("judgement", old)
    html = client.get("/").get_data(as_text=True)
    assert "synet er" in html and "dager gammelt" in html                 # the view is past its horizon
    assert "har nådd kursmålet" in html or "er på eller over bull-verdien" in html
    for phrase in ENGLISH:
        assert phrase not in html, phrase
    assert "ingen nye signaler på aksjene i research book" in html or "Nye signaler" in html
    px = float(snap.panel["close"]["AAA"].iloc[-1])
    assert px > 60 or px < 60                             # whichever it is, the item links to the form
    assert '/aksje/AAA/vurdering"' in html


def test_the_book_warnings_are_norwegian_with_grouped_thousands():
    ex = {"one_group": True, "groups": {"Seafood": 2}, "views": 2, "shared_drivers": {"margin": ["AAA", "BBB"]}, "total_loss_share": 0.125, "total_loss_at_kill": 12500.0}
    w = pf.warnings(ex)
    assert w[0] == "Alle 2 åpne BUY-syn ligger i samme sektorgruppe (Seafood)."
    assert w[1] == "2 syn kan dø av samme driver – margin: AAA, BBB."
    assert "NOK 12\N{NARROW NO-BREAK SPACE}500 = 12.5 % av papirsummen" in w[2]
    assert pd.notna(ex["total_loss_at_kill"])
