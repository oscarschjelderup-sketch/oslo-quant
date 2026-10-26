"""Primary insiders and short positions: the classifier on the kinds of text NewsWeb carries, one event per stock and
day with the right entry session, the study's arithmetic, and the short register's shape."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from osloquant.dashboard import insiders as ins
from osloquant.dashboard import testdata as tdata

from .helpers import business_days


@pytest.mark.parametrize(("body", "issuer", "side"), [
    # made-up names and numbers, in the forms NewsWeb notifications take
    ("Kari Nordmann, member of the Board of Directors in Alpha Bank ASA, has 10 March 2022 bought 13 000 shares", "Alpha Bank ASA", "buy"),
    ("Finansdirektør Ola Nordmann har 22. februar 2011 kjøpt 7.700 aksjer til en kurs av kr. 26,70.", "Beta Energi ASA", "buy"),
    ("The country manager has today divested 100,000 shares in Gamma ASA at an average price of NOK 32.00.", "Gamma ASA", "sell"),
    ("En nærstående til en primærinnsider har solgt aksjer i Delta ASA", "Delta ASA", "sell"),
    ("On 17 December 2014 Epsilon Composites ASA bought 78,500 shares in Epsilon Composites ASA", "Epsilon Composites ASA", "company"),
    ("Zeta International ASA has bought 3,000,000 own shares at a price of NOK 5.48 per share.", "Zeta ASA", "company"),
    ("Allocation of shares to primary insiders under the share savings programme", "Eta ASA", "programme"),
    ("exercised 1,300 stock options at a strike price of NOK 70.95 per share", "Theta ASA", "programme"),
    ("has extended TRS agreements relating to 70 million shares", "Iota ASA", "other"),
    ("har gjennom konvertering av obligasjonslån ervervet 25 220 aksjer", "Kappa ASA", "other"),
    ("has today transferred 3,500,000 shares to his private account from his wholly owned company", "Lambda ASA", "other"),
    ("subscribed for 100,000 shares in the private placement", "Mu ASA", "subscription"),
    ("A participant in the plan bought 1,000 shares", "X ASA", "buy"),                  # "participant" is not "pant"
    ("The investment company has bought 500 shares", "X ASA", "buy"),                 # "investment" is not "vest"
    ("Mandatory notification of trade", "X ASA", "unknown"),
])
def test_classify(body, issuer, side):
    assert ins.classify("Mandatory notification of trade", body, issuer)[0] == side


def test_one_event_per_stock_and_day_with_the_next_open():
    sessions = pd.DatetimeIndex(["2026-03-02", "2026-03-03", "2026-03-04"])
    items = [{"id": 1, "code": "A", "side": "buy", "time": "2026-03-02T06:30:00Z"},     # 07:30 Oslo: same day's open
             {"id": 2, "code": "A", "side": "buy", "time": "2026-03-02T08:15:00Z"},     # 09:15 Oslo, same day: one event, two notifications
             {"id": 3, "code": "B", "side": "buy", "time": "2026-03-02T14:00:00Z"},     # in the session: next day
             {"id": 4, "code": "B", "side": "sell", "time": "2026-03-03T06:00:00Z"}]
    ev = ins.events(items, "buy", sessions).set_index("code")
    assert ev.loc["A", "notifications"] == 2 and ev.loc["B", "notifications"] == 1
    assert ev.loc["A", "entry"] == pd.Timestamp("2026-03-03")      # one of the two came after 09:00: next open
    assert ev.loc["B", "entry"] == pd.Timestamp("2026-03-03")
    early = ins.events(items[:1], "buy", sessions).iloc[0]
    assert early["entry"] == pd.Timestamp("2026-03-02")


def test_study_measures_excess_over_the_universe():
    n = 400
    dates = business_days(n, "2015-01-01")
    flat = np.full(n, 100.0)
    up = 100 * np.cumprod(np.r_[1.0, np.full(n - 1, 1.002)])                       # +0.2 % a day
    close = pd.DataFrame({"WIN": up, "F1": flat, "F2": flat}, index=dates)
    P = dict(close=close, open=close.copy())
    items = [{"id": k, "code": "WIN", "side": "buy", "time": f"{dates[10 * k]:%Y-%m-%d}T15:00:00Z"} for k in range(1, 20)]
    r = ins.study(P, items, horizons=(20,), start="2015-01-01")["buy"]
    h = r["h20"]
    assert r["events"] == 19 and h["n"] == 19
    expect = (1.002 ** 19 - 1) * 2 / 3                                             # excess over the equal-weighted three
    assert h["mean_excess"] == pytest.approx(expect, abs=1e-4) and h["hit"] == 1.0
    assert h["net_of_cost"] == pytest.approx(h["mean_excess"] - ins.COST, abs=1e-4)


def test_shorts_from_the_register_shape():
    doc = {"instruments": [{"isin": "NO0010000000", "issuerName": "SCATEC ASA", "events": [
        {"date": "2026-10-20T00:00:00", "shortPercent": 1.9, "activePositions": [
            {"positionHolder": "Fund A", "shortPercent": 0.8}, {"positionHolder": "Fund B", "shortPercent": 1.1}]},
        {"date": "2026-09-01T00:00:00", "shortPercent": 0.6, "activePositions": [{"positionHolder": "Fund B", "shortPercent": 0.6}]}]}]}
    s = ins.shorts("SCATC", doc)
    assert s["now"] == 1.9 and s["date"] == "2026-10-20" and s["holders"][0] == ("Fund B", 1.1)
    assert s["series"] == [("2026-09-01", 0.6), ("2026-10-20", 1.9)]
    assert ins.short_change(s, 30) == pytest.approx(1.3)
    assert ins.shorts("OUTLT", doc) is None


needs_insiders = pytest.mark.skipif(not tdata.available("insiders.json"), reason="no frozen insider cache on this machine (private)")


@needs_insiders
def test_real_insider_study_is_the_same_every_time():
    import yaml

    from osloquant import signals as sg

    items = tdata.load_json("insiders")["items"]
    for it in items.values():
        it["side"], it["why"] = ins.classify(it["title"], it.get("body", ""), it.get("issuer"))
    res = ins.study(tdata.load_panel(), items.values())
    committed = yaml.safe_load((sg.odds_path().parent / "insider_study.yaml").read_text(encoding="utf-8"))
    assert res == committed["results"]
