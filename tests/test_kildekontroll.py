"""One source against another, and the krone index from Norges Bank (docs/forbedring/endringer.md E18, funn D12)."""

from __future__ import annotations

import pandas as pd
import pytest

from osloquant.dashboard import feeds as fd
from osloquant.dashboard import sources as src

from .test_dashboard import app  # noqa: F401  the synthetic store, book and home

DAY = pd.Timestamp("2026-11-09")


def _fx_table(usd: float, eur: float) -> dict[str, pd.Series]:
    return {"USD": pd.Series([9.40, usd], index=[DAY - pd.Timedelta(days=3), DAY]), "EUR": pd.Series([10.50, eur], index=[DAY - pd.Timedelta(days=3), DAY])}


def test_two_sources_for_the_same_rate_are_compared_and_a_gap_over_the_limit_is_named(home):
    fd.write("fx", {"USDNOK": 9.41, "EURNOK": 10.54, "date": "2026-11-09", "source": "Norges Bank"})
    px = {"AAA": (DAY, 100.0), "BBB": (DAY, 50.0)}
    rows = src.cross_checks(_fx_table(9.43, 10.55), px, dict(px))
    usd, eur, last = rows
    assert usd["what"] == "USD/NOK" and usd["diff"] == pytest.approx(9.43 / 9.41 - 1) and not usd["over"] and not eur["over"]
    assert not last["over"] and "2 aksjer med samme siste dato stemmer" in last["note"]
    assert src.cross_lines(rows) == []
    rows = src.cross_checks(_fx_table(9.70, 10.55), px, {"AAA": (DAY, 100.0), "BBB": (DAY, 51.0)})       # 3 % apart; one last close 2 % off
    assert rows[0]["over"] and rows[2]["over"] and "1 av 2 aksjer avviker: BBB" in rows[2]["note"]
    lines = src.cross_lines(rows)
    assert len(lines) == 2 and lines[0].startswith("kildekontroll: USD/NOK avviker +3.08 % mellom Norges Bank og Yahoo Finance")
    html = src.cross_html(rows)
    assert html.count("over grensen") == 2 and "innenfor" in html


def test_a_check_that_cannot_be_made_says_why(home):
    rows = src.cross_checks({}, {"AAA": (DAY, 100.0)}, {"AAA": (DAY - pd.Timedelta(days=20), 90.0)})
    assert rows[0]["note"] == "Norges Bank-kursen er ikke hentet" and rows[0]["diff"] is None and not rows[0]["over"]
    assert "de noterte kursene ligger etter" in rows[2]["note"] and rows[2]["diff"] is None
    fd.write("fx", {"USDNOK": 9.41, "EURNOK": 10.54, "date": "2026-11-09"})
    assert "lageret har ingen Yahoo-kurs for 9. nov. 2026" in src.cross_checks({}, {}, {})[0]["note"]
    assert "ikke sammenlignet" in src.cross_html(src.cross_checks({}, {}, {}))


def test_data_health_shows_the_card(app):  # noqa: F811
    client, _ = app
    html = client.get("/health").get_data(as_text=True)
    assert 'id="kildekontroll"' in html and "Kontroll mellom kilder" in html and "USD/NOK" in html


def test_the_krone_index_rides_along_and_its_failure_never_costs_the_rates(home, monkeypatch):
    def nb(flow):
        if "I44" in flow:
            return [{"OBS_VALUE": "109.57", "TIME_PERIOD": "2026-11-10"}]
        return [{"BASE_CUR": "USD", "OBS_VALUE": "9.41", "TIME_PERIOD": "2026-11-10"}, {"BASE_CUR": "EUR", "OBS_VALUE": "10.54", "TIME_PERIOD": "2026-11-10"}]

    monkeypatch.setattr(fd, "_nb_last", nb)
    doc = fd.fetch_fx()
    assert doc["I44"] == 109.57 and doc["I44_date"] == "2026-11-10" and doc["USDNOK"] == 9.41 and "errors" not in doc
    fd.write("fx", doc)
    drivers = fd.sector_drivers()
    labels = [d["label"] for d in drivers["Industrials & materials"]]
    assert "Kronekursindeks I44 (høyere = svakere krone)" in labels and any("109.57" in d["value"] for d in drivers["Seafood"])

    def nb_without(flow):
        if "I44" in flow:
            raise TimeoutError("timed out")
        return nb(flow)

    monkeypatch.setattr(fd, "_nb_last", nb_without)
    doc = fd.fetch_fx()
    assert doc["USDNOK"] == 9.41 and "I44" not in doc and doc["errors"] == ["I44: TimeoutError"]
    fd.write("fx", doc)
    assert "Kronekursindeks I44 (høyere = svakere krone)" not in [d["label"] for d in fd.sector_drivers()["Seafood"]]
