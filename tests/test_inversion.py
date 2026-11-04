"""Inversion from the model's sensitivity tables (D51): the shift that takes the value to 70 % of the price along each
axis, interpolated and never extrapolated, the cheapest combinations, and the stock-page block. A fictional workbook
with the Toolkit's layout only."""

from __future__ import annotations

import json

import openpyxl
import pytest

from osloquant.dashboard import inversion as iv


def _workbook(tmp_path, slope_g=20.0, slope_m=4.0, base=50.0):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sensitivity"
    steps = [-0.02, -0.01, 0.0, 0.01, 0.02]
    ws.cell(32, 3, base)
    for j, dm in enumerate(steps):
        ws.cell(32, 4 + j, dm)
    for i, dg in enumerate(steps):
        ws.cell(33 + i, 3, dg)
        for j, dm in enumerate(steps):
            ws.cell(33 + i, 4 + j, base + slope_g * dg * 100 + slope_m * dm * 100)       # value per share, linear in both shifts
    waccs = [0.08, 0.09, 0.10, 0.11, 0.12]
    ws.cell(12, 3, "g \\ WACC")
    for j, w in enumerate(waccs):
        ws.cell(12, 4 + j, w)
    for i, g in enumerate([0.015, 0.0175, 0.02, 0.0225, 0.025]):
        ws.cell(13 + i, 3, g)
        for j, w in enumerate(waccs):
            ws.cell(13 + i, 4 + j, base * (1 - 8 * (w - 0.10)) * (1 + 10 * (g - 0.02)))
    for name, ref, val in (("DCF", "B2", base), ("WACC", "B2", 0.10), ("Inputs", "B2", "2026-10-30"), ("Inputs", "B3", 40.0)):
        sh = wb[name] if name in wb.sheetnames else wb.create_sheet(name)
        sh[ref] = val
    x = tmp_path / "model.xlsx"
    wb.save(x)
    m = tmp_path / "map.json"
    m.write_text(json.dumps({"sens": {"t1_hdr": 12, "t1_rows": [13, 17], "t3_hdr": 32, "t3_rows": [33, 37]},
                             "cells": {"DCF|dcf_ps": "B2", "WACC|wacc": "B2", "Inputs|val_date": "B2", "Inputs|price": "B3"}}), encoding="utf8")
    return x, m


def test_the_shift_to_a_30_percent_loss_is_interpolated_along_each_axis(tmp_path):
    x, m = _workbook(tmp_path)
    g = iv.read_grids(x, m)
    assert g["growth_margin"]["rows"] == [-0.02, -0.01, 0.0, 0.01, 0.02] and g["dcf_ps"] == 50.0 and g["model_date"] == "2026-10-30"
    r = iv.invert(g, price=50.0)                                                           # loss line 35
    single = {s["driver"]: s for s in r["single"]}
    assert r["level"] == pytest.approx(35.0)
    assert single["vekst"]["shift"] == pytest.approx(-0.0075)                              # 50 - 20 x 0.75 = 35
    assert single["EBITDA-margin"]["shift"] is None and single["EBITDA-margin"]["edge_value"] == pytest.approx(42.0)   # -2 pp only reaches 42: not extrapolated
    assert single["WACC"]["shift"] is None                                                 # 12 % gives 42: outside the table
    assert r["combos"][0] == {"growth": -0.01, "margin": 0.0, "value": pytest.approx(30.0), "steps": 1.0}
    html = iv.block_html(r | {"file": "model.xlsx"}, "XYZ")
    assert "−30 %" in html and "-0.8 pp" in html and "ikke innenfor tabellen" in html and "aldri ekstrapolert" in html


def test_for_case_reports_missing_models_and_unreadable_tables(tmp_path):
    class C:
        model = {"xlsx": str(tmp_path / "nope.xlsx"), "map": str(tmp_path / "nope.json")}
    assert "not found" in iv.for_case(C(), 40.0)["error"]
    assert iv.for_case(None, 40.0) is None and iv.for_case(C(), None) is None
    x, m = _workbook(tmp_path)
    C.model = {"xlsx": str(x), "map": str(m)}
    assert iv.for_case(C(), 50.0)["file"] == "model.xlsx"
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf8")
    C.model = {"xlsx": str(x), "map": str(bad)}
    assert "could not be read" in iv.for_case(C(), 50.0)["error"] and "could not be read" in iv.block_html(iv.for_case(C(), 50.0), "XYZ")
