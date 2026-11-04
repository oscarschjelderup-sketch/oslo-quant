"""Passes (D54): a decision not to buy is a row with price, date and reason, scored against OSEBX for twelve months;
inside the circle and 20 pp better than the index it is a possible omission. Temporary home, synthetic prices."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from osloquant import judgements as jg
from osloquant.dashboard import passes as ps

from .test_dashboard import app  # noqa: F401  (fixture)


def test_a_pass_is_logged_from_the_stock_page(app):  # noqa: F811
    client, _ = app
    page = client.get("/stock/CCC").get_data(as_text=True)
    assert "Lar du være? Logg det (unnlatelse)" in page and 'action="/stock/CCC/pass"' in page
    assert client.post("/stock/CCC/pass", data={"reason": "kort"}).status_code == 400
    assert client.post("/stock/CCC/pass", data={"reason": "Fictional: the bank's loan book is too opaque for me", "inside": "1"}).status_code == 303
    row = jg.read_log()[-1]
    assert row["kind"] == "pass" and row["inside_circle"] is True and row["price"] > 0 and jg.verify().ok
    assert "1 tidligere" in client.get("/stock/CCC").get_data(as_text=True)
    assert "Unnlatelser (Buffett)" in client.get("/calibration").get_data(as_text=True) and "1 logget" in client.get("/calibration").get_data(as_text=True)


def test_a_pass_that_ran_away_inside_the_circle_is_a_possible_omission():
    days = pd.bdate_range("2026-01-02", periods=300)
    adj = pd.DataFrame({"AAA": np.linspace(100, 160, 300), "BBB": np.linspace(100, 105, 300)}, index=days)
    idx = pd.Series(np.linspace(1000, 1050, 300), index=days)
    prices = jg.Prices(adj, pd.DataFrame(), idx)
    rows = [{"seq": 1, "kind": "pass", "code": "AAA", "date": "2026-01-02", "price": 100.0, "reason": "fictional reason one", "inside_circle": True},
            {"seq": 2, "kind": "pass", "code": "BBB", "date": "2026-01-02", "price": 100.0, "reason": "fictional reason two", "inside_circle": True},
            {"seq": 3, "kind": "pass", "code": "AAA", "date": "2026-01-02", "price": 100.0, "reason": "fictional reason three", "inside_circle": False}]
    sc = ps.scoring(rows, prices, pd.Timestamp("2026-12-31"))
    by = {r["seq"]: r for r in sc["rows"]}
    assert by[1]["tsr"] == pytest.approx(adj["AAA"].loc[:"2026-12-31"].iloc[-1] / 100 - 1) and by[1]["omission"]
    assert not by[2]["omission"] and not by[3]["omission"] and sc["omissions"] == 1             # outside the circle: listed, not counted
    html = ps.calibration_html(sc)
    assert "1 mulige unnlatelser" in html and "mulig unnlatelse" in html
