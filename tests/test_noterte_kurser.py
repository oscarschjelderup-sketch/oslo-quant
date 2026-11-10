"""The day's change and the 12-month range on quoted closes (docs/forbedring/endringer.md E16, funn #30 and #31)."""

from __future__ import annotations

import pandas as pd
import pytest

from osloquant.dashboard import market as mk
from osloquant.dashboard.tall import MINUS, NBSP

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home


def _quoted(snap: mk.Snapshot, dividend: float = 5.0) -> pd.DataFrame:
    """Quoted closes for AAA: the adjusted series un-adjusted for a dividend that goes ex on the last session."""
    a = snap.panel["close"]["AAA"].dropna()
    q = a.copy()
    step = 1 - dividend / (float(a.iloc[-2]) + dividend)                  # the adjusted prices before the ex-day were scaled by this
    q.iloc[:-1] = a.iloc[:-1] / step
    return q.to_frame("AAA")


def test_the_days_change_on_an_ex_day_is_the_price_change_not_the_total_return(app, monkeypatch):  # noqa: F811
    client, snap = app
    q = _quoted(snap)
    monkeypatch.setattr(mk, "quoted_closes", lambda: q)
    a = snap.panel["close"]["AAA"].dropna()
    total, price = float(a.iloc[-1] / a.iloc[-2] - 1), float(q["AAA"].iloc[-1] / q["AAA"].iloc[-2] - 1)
    assert price < total - 0.02                                           # the dividend is the difference
    v = mk.quoted_view(snap, "AAA")
    assert v["fresh"] and v["chg_1d"] == pytest.approx(price) and v["hi12"] == pytest.approx(float(q["AAA"].iloc[-250:].max()))
    assert mk.returns(snap).loc["AAA", "d1"] == pytest.approx(price)       # /sectors and the front page
    assert mk.returns(snap).loc["BBB", "d1"] == pytest.approx(float(snap.panel["close"]["BBB"].iloc[-1] / snap.panel["close"]["BBB"].iloc[-2] - 1))
    html = client.get("/aksje/AAA/oversikt").get_data(as_text=True)
    shown = f"{price * 100:+.1f}".replace(".", ",").replace("-", MINUS) + f"{NBSP}%"
    assert shown in html.split('class="stockbar"')[1][:1500]
    assert "laveste og høyeste noterte sluttkurs" in html and "12 m lav / høy (justert)" not in html
    lo, hi = float(q["AAA"].iloc[-250:].min()), float(q["AAA"].iloc[-250:].max())
    assert f"{lo:.2f} / {hi:.2f}".replace(".", ",") in html


def test_a_quoted_series_that_lags_is_not_used_and_the_page_says_so(app, monkeypatch):  # noqa: F811
    client, snap = app
    stale = _quoted(snap).iloc[:-5]                                       # the quoted table stopped five sessions ago
    monkeypatch.setattr(mk, "quoted_closes", lambda: stale)
    assert not mk.quoted_view(snap, "AAA")["fresh"]
    a = snap.panel["close"]["AAA"].dropna()
    assert mk.returns(snap).loc["AAA", "d1"] == pytest.approx(float(a.iloc[-1] / a.iloc[-2] - 1))
    html = client.get("/aksje/AAA/oversikt").get_data(as_text=True)
    assert "12 m lav / høy (justert)" in html and "de noterte kursene mangler for de siste øktene" in html
    monkeypatch.setattr(mk, "quoted_closes", lambda: pd.DataFrame())      # never recorded: the same
    assert not mk.quoted_view(snap, "AAA")["fresh"] and "12 m lav / høy (justert)" in client.get("/aksje/AAA/oversikt").get_data(as_text=True)
