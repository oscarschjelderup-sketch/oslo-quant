"""One kill list per case (D40): the model's list is matched against the view's sentences and the reader's rules by
numbers and label words; every divergence is named; nothing is rewritten. Fictional data only."""

from __future__ import annotations

import json

import pandas as pd

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import book as bk
from osloquant.dashboard import datahealth as dh
from osloquant.dashboard import killlist as kl
from osloquant.dashboard import reportpdf as rpdf
from osloquant.dashboard import reports as rp

from .test_dashboard import app  # noqa: F401  (fixture)
from .test_rapporter import PDF

MODEL = {"model": [{"label": "EBIT adj. margin (pre-IFRS 16)", "row": "ebit_adj_m", "op": "below", "threshold": 0.10, "buffer": 0.01, "fmt": "pct",
                    "text": "EBIT adj. margin (pre-IFRS 16) below 10.0 %"},
                   {"label": "NIBD / EBITDAaL", "row": "lev", "op": "above", "threshold": 2.0, "buffer": 0.25, "fmt": "mult", "text": "NIBD / EBITDAaL above 2.00x"},
                   {"label": "Price/mix growth, group", "row": "g_pxc", "op": "below", "threshold": 0.015, "buffer": 0.01, "fmt": "pct",
                    "text": "Price/mix growth, group below 1.5 %"}],
         "text": ["Net club openings below the committed pipeline (13 clubs through 2028)"], "source": "test_data.py KILL / KILL_TEXT, model 2026-11-03"}


def test_matching_is_by_threshold_and_label_words():
    m = MODEL["model"][0]
    assert kl.matches(m, "EBIT adj. margin back below 10% of revenue")
    assert kl.matches(m, "Adjusted EBIT margin under 10 %")
    assert not kl.matches(m, "Personnel costs back above 37% of revenue")          # wrong number
    assert not kl.matches(m, "Leverage above 10x")                                 # right number, no label word
    assert kl.matches(MODEL["model"][1], "NIBD / EBITDAaL above 2.0x") and kl.matches(MODEL["model"][2], "Price/mix below 1.5% a year")
    t = {"text": MODEL["text"][0], "row": None, "label": MODEL["text"][0]}
    assert kl.matches(t, "Net club openings below the committed pipeline (13 clubs through 2028).") and not kl.matches(t, "Clubs grow")


def test_compare_names_every_divergence_and_is_quiet_when_the_lists_agree():
    view = ["EBIT adj. margin below 10 %", "NIBD / EBITDAaL above 2.0x", "Price/mix growth below 1.5 % a year",
            "Net club openings below the committed pipeline (13 clubs through 2028)"]
    rules = [{"criterion": 0, "metric": "ebit_pre16_margin_ltm", "op": "<", "value": 0.10}, {"criterion": 2, "metric": "arpm_yoy", "op": "<", "value": 0.015}]
    ok = kl.compare(MODEL, view, rules)
    assert ok["issues"] == [] and ok["model_n"] == 4 and ok["view_n"] == 4 and ok["unchecked"] == ["NIBD / EBITDAaL above 2.00x"]
    # a view that drifted: a different threshold, one criterion missing, one extra; a reader rule out of range and off-threshold
    drifted = ["EBIT adj. margin below 8 %", "Gross margin below 49 %", "NIBD / EBITDAaL above 2.0x"]
    bad_rules = [{"criterion": 5, "metric": "ebit_pre16_margin_ltm", "op": "<", "value": 0.10}, {"criterion": 0, "metric": "arpm_yoy", "op": "<", "value": 0.02}]
    r = kl.compare(MODEL, drifted, bad_rules)
    text = " | ".join(r["issues"])
    assert "modellen har 4 kill-kriterier, synet 3" in text
    assert "står ikke i synet: «EBIT adj. margin (pre-IFRS 16) below 10.0 %»" in text and "Price/mix" in text and "Net club openings" in text
    assert "ingen modellinje bak seg: «EBIT adj. margin below 8 %»" in text and "«Gross margin below 49 %»" in text
    assert "peker på kriterium 5, synet har 3" in text and "bruker 0.02, modellen 0.015" in text
    # no view yet: said plainly; no model and no rules: nothing to compare
    assert kl.compare(MODEL, [], [])["issues"] == ["modellen har 4 kill-kriterier, ingen vurdering er logget"]
    assert kl.compare(None, view, [])["issues"] == [] and kl.compare(None, view, [{"criterion": 9, "metric": "x"}])["issues"][0].startswith("leserregelen")
    # Claude's list is reported as separate, not as wrong
    c = kl.compare(MODEL, view, rules, claude_kill=["Members per club below 2 000", "Churn above 4 % a month"])
    assert any("Claudes kill-liste deler ingen" in i for i in c["issues"])
    assert kl.compare(MODEL, view, rules, claude_kill=["EBIT adj. margin below 10 %"])["issues"] == []


def test_reader_stub_drafts_rules_from_the_model():
    stub = kl.reader_stub(MODEL, ["NIBD / EBITDAaL above 2.0x", "EBIT adj. margin below 10 %"])
    assert "{criterion: 1, metric: ebit_pre16_margin_ltm, op: '<', value: 0.1, row: ebit_adj_m}" in stub
    assert "criterion: 0, metric: TODO (model row lev)" in stub and "not machine-checkable" in stub


def _publish_with_kill(tmp_path, code, date, kill):
    pdf = tmp_path / f"{code}_Research_Report_{date}.pdf"
    pdf.write_bytes(PDF)
    est = tmp_path / f"est_{code}.json"
    est.write_text(json.dumps({"date": date, "tp": 130, "rating": "BUY", "price": 100.0, "kill": kill}), encoding="utf-8")
    rpdf.publish(code, pdf, est, {"kind": "Initiation", "title": "t", "pages": 1, "gate_ok": True, "built": date})


def test_stock_page_data_health_and_cli_carry_the_comparison(app, tmp_path, monkeypatch):  # noqa: F811
    client, snap = app
    _publish_with_kill(tmp_path, "AAA", "2026-11-03", MODEL)      # the book's AAA view has one criterion: "margin below 10%"
    rp.spec_path().write_text("AAA:\n  key: {revenue: 'Revenue'}\n  kill:\n    - {criterion: 0, metric: ebit_pre16_margin_ltm, op: '<', value: 0.10}\n", encoding="utf-8")
    c = bk.case("AAA")
    r = kl.for_case(c)
    assert r["model_n"] == 4 and r["view_n"] == 1 and "modellen har 4 kill-kriterier, synet 1" in r["issues"]
    page = client.get("/stock/AAA").get_data(as_text=True)
    assert "Kill-listen mot modellen" in page and "spriker" in page and "Ikke maskinsjekket" in page
    from osloquant.dashboard import odds as od

    monkeypatch.setattr(od, "long_closes", lambda: snap.panel["close"])
    rows = dh.case_health(bk.cases(), snap.panel["close"], pd.Timestamp("2026-11-04"))
    assert any(i.startswith("kill-listen: modellen har 4") for i in rows[0]["issues"])
    # a view logged with the model's four sentences: one list
    jg.append("judgement", dict(code="AAA", name="Alpha", date="2026-11-04", price=100.0, rating="BUY", target=130.0, horizon_months=12,
                                kill=["EBIT adj. margin below 10 %", "NIBD / EBITDAaL above 2.0x", "Price/mix growth below 1.5 % a year",
                                      "Net club openings below the committed pipeline (13 clubs through 2028)"]))
    assert kl.for_case(bk.case("AAA"))["issues"] == []
    assert "én liste" in client.get("/stock/AAA").get_data(as_text=True)
    assert kl.for_case(bk.case("BBB")) is None                        # nothing published, no rules: nothing to compare
    assert sg.load_book()


def test_cli_book_check_prints_per_case(app, tmp_path):  # noqa: F811
    from typer.testing import CliRunner

    from osloquant.cli import app as cli

    _publish_with_kill(tmp_path, "AAA", "2026-11-03", MODEL)
    res = CliRunner().invoke(cli, ["book", "check", "AAA", "--stub"])
    assert res.exit_code == 0, res.output
    assert "AAA" in res.output and "avvik" in res.output and "kill:" in res.output and "1 case(s) with a diverging kill list" in res.output
