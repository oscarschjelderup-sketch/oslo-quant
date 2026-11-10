"""Regression tests for the improvement pass of 10 Nov 2026 (docs/forbedring/endringer.md). One test per change, named
by its number there. Everything runs on a synthetic store and a temp home – never the real research book or log."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant import signals as sg
from osloquant.dashboard import casefile, server
from osloquant.dashboard import forecasts as fc
from osloquant.dashboard import market as mk

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home

RD_KEYS = ("rd_m_last", "rd_m_last_ours", "rd_m_last_ref", "rd_cagr", "rd_cagr_ours", "rd_cagr_ref", "rd_wacc", "rd_wacc_ours", "rd_k")


def _model(tmp_path, values: dict, drop: str | None = None, name: str = "model") -> dict:
    """A tiny Toolkit-shaped workbook and its cell map; `values` overrides a cell, `drop` leaves a key out of the map."""
    import openpyxl

    cells, wb = {}, openpyxl.Workbook()
    wb.remove(wb.active)
    base = {**{f"Reverse_DCF|{k}": 0.1 for k in RD_KEYS}, "Reverse_DCF|rd_k": 2.5, "Inputs|price": 100.0, "Inputs|price_date": "2026-01-05",
            "DCF|dcf_ps": 120.0, "DCF|tp": 125, "DCF|rating": "BUY", "WACC|wacc": 0.08, "Inputs|val_date": "2026-01-05"} | values
    for i, (key, v) in enumerate(base.items(), start=1):
        sheet = key.split("|")[0]
        ws = wb[sheet] if sheet in wb.sheetnames else wb.create_sheet(sheet)
        ws[f"B{i}"] = v
        if key != drop:
            cells[key] = f"B{i}"
    xlsx, cmap = tmp_path / f"{name}.xlsx", tmp_path / f"{name}.json"
    wb.save(xlsx)
    cmap.write_text(json.dumps({"cells": cells}), encoding="utf8")
    return {"xlsx": str(xlsx), "map": str(cmap)}


def _book_with_model(model: dict) -> None:
    sg.book_path().write_text(
        "entries:\n  - code: AAA\n    name: Alpha\n    rating: BUY\n    valuation_date: 2026-01-05\n    price_at_valuation: 100\n"
        "    target: 120\n    bear: 70\n    bull: 150\n    kill:\n      - margin below 10%\n"
        f"    model: {{xlsx: '{model['xlsx']}', map: '{model['map']}'}}\n", encoding="utf-8")


# ------------------------------------------------------------------------------------------------ E1 one row, one file
def test_e1_text_in_a_model_cell_shows_in_the_card_and_the_page_still_opens(app, tmp_path):  # noqa: F811
    client, _ = app
    model = _model(tmp_path, {"Reverse_DCF|rd_cagr": "n.a.", "Reverse_DCF|rd_wacc": "outside range"})
    rd = casefile.reverse_dcf(model)
    assert rd["rd_cagr"] is None and rd["rd_wacc"] is None and rd["rd_m_last"] == pytest.approx(0.1)
    assert rd["notes"] == {"rd_cagr": "n.a.", "rd_wacc": "outside range"}
    _book_with_model(model)
    for tab in ("oversikt", "verdsettelse", "vurdering"):
        r = client.get(f"/aksje/AAA/{tab}")
        assert r.status_code == 200, tab
    html = client.get("/aksje/AAA/verdsettelse").get_data(as_text=True)
    assert "outside range" in html and "n.a." in html
    assert client.get("/stock/AAA/pretrade").status_code == 200


def test_e1_a_model_that_cannot_be_read_is_the_cards_own_error(app, tmp_path):  # noqa: F811
    client, _ = app
    missing_key = _model(tmp_path, {}, drop="Reverse_DCF|rd_k", name="nokey")
    assert "rd_k" in casefile.reverse_dcf(missing_key)["error"]
    empty = _model(tmp_path, {"Inputs|price": None, "DCF|dcf_ps": None, "Reverse_DCF|rd_k": None}, name="empty")
    rd = casefile.reverse_dcf(empty)
    assert rd["price"] is None and rd["dcf"] is None
    broken = dict(empty)
    (tmp_path / "broken.xlsx").write_text("not a workbook", encoding="utf-8")
    broken["xlsx"] = str(tmp_path / "broken.xlsx")
    assert "kunne ikke leses" in casefile.reverse_dcf(broken)["error"]
    for model in (missing_key, empty, broken):
        _book_with_model(model)
        assert client.get("/aksje/AAA/verdsettelse").status_code == 200
        assert client.get("/stock/AAA/pretrade").status_code == 200


def test_e1_the_calibration_page_survives_a_forecast_row_of_another_shape(app):  # noqa: F811
    client, _ = app
    good = dict(code="AAA", date="2026-01-10", metric="revenue", label="Revenue", low=90.0, mid=100.0, high=110.0)
    jg.append("forecast", good | {"report": {"date": "2026-02-01", "what": "Q4 report", "source": "book"}})
    # an older or hand-written row: the report as plain text. Written past the validation, as such a row once was.
    path = jg.log_path()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    odd = {k: v for k, v in rows[-1].items() if k not in ("hash", "prev")} | {"seq": rows[-1]["seq"] + 1, "report": "Q4 2026 report", "metric": "ebitda"}
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(odd) + "\n", encoding="utf-8")
    fs = fc.forecasts(jg.read_log())
    assert [f["report"]["date"] for f in fs] == ["2026-02-01", ""] and fs[1]["report"]["what"] == "Q4 2026 report"
    r = client.get("/calibration")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Kvartalsprognoser" in html and "Q4 2026 report" in html
    assert client.get("/aksje/AAA/vurdering").status_code == 200 and client.get("/").status_code == 200


def test_e1_the_log_refuses_a_forecast_without_a_report_date(home):
    good = dict(code="AAA", date="2026-01-10", metric="revenue", low=90.0, mid=100.0, high=110.0)
    with pytest.raises(ValueError, match="report"):
        jg.append("forecast", good | {"report": "Q4 2026 report"})
    with pytest.raises(ValueError, match="report"):
        jg.append("forecast", good | {"report": {"what": "Q4"}})
    assert not jg.log_path().exists() or jg.read_log() == []


def test_e1_one_failing_block_leaves_the_rest_of_the_calibration_page(app, monkeypatch):  # noqa: F811
    client, _ = app
    from osloquant.dashboard import passes

    def boom(*a, **k):
        raise RuntimeError("kaputt i blokken")

    monkeypatch.setattr(passes, "scoring", boom)
    r = client.get("/calibration")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Kvartalsprognoser" in html
    assert "Denne delen kunne ikke vises" in html and "kaputt i blokken" in html and "Traceback" not in html


# ------------------------------------------------------------------------------------------------ E2 the empty store
def test_e2_an_empty_store_is_an_empty_state_on_every_page(monkeypatch, home):
    empty = pd.DataFrame(index=pd.DatetimeIndex([]), dtype=float)
    snap = mk.Snapshot(dict(open=empty, high=empty, low=empty, close=empty, volume=empty), {}, {}, pd.NaT)
    monkeypatch.setattr(mk, "snapshot", lambda: snap)
    a = server.create_app()
    a.testing = True
    client = a.test_client()
    for url in ("/", "/sectors", "/coverage", "/screen", "/calendar", "/health", "/watchlist", "/calibration", "/review", "/desk", "/chief", "/funds"):
        r = client.get(url)
        assert r.status_code == 200, url
    for url in ("/", "/sectors"):
        html = client.get(url).get_data(as_text=True)
        assert "Lageret har ingen kurser" in html and "oq record" in html


# ------------------------------------------------------------------------------------------------ E3 error pages
def test_e3_an_unknown_address_and_a_crash_get_a_norwegian_page_with_the_menu(app, monkeypatch):  # noqa: F811
    client, _ = app
    r = client.get("/finnes-ikke")
    html = r.get_data(as_text=True)
    assert r.status_code == 404 and "Siden finnes ikke" in html and 'href="/health"' in html and "/finnes-ikke" in html
    client.application.testing = False                 # as in real use: the handler answers, the exception is not re-raised
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    from osloquant.dashboard import render

    def boom(*a, **k):
        raise RuntimeError("kaputt i siden")

    monkeypatch.setattr(render, "calendar_page", boom, raising=False)
    monkeypatch.setattr("osloquant.dashboard.calendar.page_html", boom)
    r = client.get("/calendar")
    html = r.get_data(as_text=True)
    assert r.status_code == 500 and "Noe gikk galt" in html and 'href="/health"' in html
    assert "RuntimeError" in html and "Traceback" not in html
