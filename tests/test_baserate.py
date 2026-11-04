"""Base rates for the estimates (D47): the store's reference class from annual statements, the published table read
from resources (deflated when it is real), the 20–80 flag on either side, and the check in the form and on the row.
Fictional statements and estimates only; the published table is the one in resources/base_rates.yaml."""

from __future__ import annotations

import json

import pytest

from osloquant import judgements as jg
from osloquant.dashboard import baserate as bsr
from osloquant.dashboard import reportpdf as rpdf

from .test_dashboard import GOOD, app  # noqa: F401  (fixture)


def _annual(rev0, rev3, m0, m3, start=2022):
    return [{"year": start + i, "revenue": rev0 * (rev3 / rev0) ** (i / 3), "ebitda": rev0 * (rev3 / rev0) ** (i / 3) * (m0 + (m3 - m0) * i / 3)} for i in range(4)]


def test_the_store_sample_takes_three_year_outcomes_and_skips_banks_and_short_histories():
    annual = {"A": _annual(100, 133.1, 0.10, 0.12), "B": _annual(100, 100, 0.20, 0.15), "BANK": _annual(100, 150, 0.3, 0.3), "SHORT": _annual(100, 120, 0.1, 0.1)[:3]}
    s = bsr.sample_from(annual, {"BANK": "Finance"})
    by = {x["code"]: x for x in s}
    assert set(by) == {"A", "B"} and by["A"]["rev_cagr"] == pytest.approx(0.10) and by["A"]["ebitda_m_chg"] == pytest.approx(0.02)
    assert by["B"]["ebitda_m_chg"] == pytest.approx(-0.05) and by["A"]["from"] == 2022 and by["A"]["to"] == 2025


def test_shares_and_buckets():
    assert bsr.share_at_least(0.05, [0.0, 0.05, 0.10, None]) == pytest.approx(2 / 3) and bsr.share_at_most(0.0, [0.0, 0.05, 0.10]) == pytest.approx(1 / 3)
    assert bsr.bucket_at_least(0.05, [[None, 0.0, 50], [0.0, 0.10, 50]]) == pytest.approx(0.25)
    pub = bsr.published()
    assert pub and pub[0]["source"].startswith("Mauboussin") and sum(b[2] for b in pub[0]["buckets"]) == pytest.approx(100.0, abs=0.2)
    assert bsr.bucket_at_least(0.054, pub[0]["buckets"]) == pytest.approx(0.5, abs=0.03)    # the book's median, 5.4 %


def _est(rev, ebitda):
    return {"years": [2026, 2027, 2028, 2029, 2030], "rows": {"rev": rev, "ebitda": ebitda}}


LOCAL = {"name": "Fictional store", "period": "2022–2025", "rows": [{"rev_cagr": g, "ebitda_m_chg": m} for g, m in
                                                                  zip([-0.05, 0.0, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.20],
                                                                      [-0.05, -0.03, -0.02, -0.01, 0.0, 0.0, 0.01, 0.02, 0.03, 0.06], strict=True)]}


def test_a_forecast_above_the_80th_percentile_is_flagged_and_deflated_for_a_real_table():
    fc = bsr.forecast(_est([100, 115, 132.25, 152.0875, 160], [10, 12, 14, 16, 17]))
    assert fc["rev_cagr"] == pytest.approx(0.15) and fc["ebitda_m_chg"] == pytest.approx(16 / 152.0875 - 0.10)
    res = bsr.check(fc, LOCAL, bsr.published())
    g = next(i for i in res["items"] if i["metric"] == "rev_cagr")
    store = next(r for r in g["refs"] if r["name"] == "Fictional store")
    book = next(r for r in g["refs"] if r["name"].startswith("Mauboussin"))
    assert store["at_least"] == pytest.approx(0.1) and g["side"] == "over" and book["deflated"] == pytest.approx(1.15 / 1.02 - 1)
    assert any("above the 80th percentile of Fictional store" in f for f in res["flags"])
    low = bsr.check(bsr.forecast(_est([100, 90, 81, 72.9, 70], [10, 9, 8, 7, 7])), LOCAL, [])
    assert next(i for i in low["items"] if i["metric"] == "rev_cagr")["side"] == "under"
    mid = bsr.check(bsr.forecast(_est([100, 104, 108.16, 112.4864, 115], [10, 10.4, 10.8, 11.25, 11.5])), LOCAL, [])
    assert mid["flags"] == [] and bsr.forecast({"years": [2026], "rows": {"rev": [1]}}) is None


def test_the_form_shows_the_check_and_the_row_keeps_it(app, monkeypatch):  # noqa: F811
    client, _ = app
    monkeypatch.setattr(bsr, "local_sample", lambda: LOCAL)
    folder = rpdf.folder("AAA")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "estimates_2026-11-02.json").write_text(json.dumps(_est([100, 115, 132.25, 152.0875, 160], [10, 12, 14, 16, 17])), encoding="utf-8")
    form = client.get("/stock/AAA").get_data(as_text=True)
    assert "Base rates (Mauboussin)" in form and 'name="base_rate_reason"' in form and "Utenfor 20–80-båndet" in form and "Base rates for estimatene" in form
    assert client.post("/stock/AAA/judge", data=GOOD | {"base_rate_reason": "Fictional: new stores open in the plan"}).status_code == 303
    br = jg.read_log()[-1]["base_rate"]
    assert br["flags"] and br["reason"].startswith("Fictional") and br["estimates"] == "estimates_2026-11-02.json"
    assert br["items"][0]["metric"] == "rev_cagr" and br["items"][0]["forecast"] == pytest.approx(0.15)
