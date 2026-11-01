"""Signal watch: the rules fire on the right session, the digest reads without a network, the odds file loads."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from osloquant import signals
from osloquant.signals import BUY, INFO, RISK, Alert

from .helpers import bars, business_days


def _panel(frames: dict[str, np.ndarray], start="2020-01-01") -> dict[str, pd.DataFrame]:
    dates = business_days(len(next(iter(frames.values()))), start)
    close = pd.DataFrame(frames, index=dates)
    high, low = close * 1.01, close * 0.99
    open_ = close.shift(1).fillna(close)
    volume = pd.DataFrame(1000.0, index=dates, columns=close.columns)
    return dict(open=open_, high=high, low=low, close=close, volume=volume)


def test_breakout_fires_once_on_the_breakout_day_and_needs_volume():
    flat = np.full(80, 100.0)
    up = flat.copy()
    up[70:] = 108.0                                  # jumps above the 60-day high on day 70 and stays there
    P = _panel({"A": up, "B": flat})
    P["volume"].iloc[70, 0] = 2000.0                 # the breakout day has twice the 20-day volume
    frames = signals.signal_frames(P)
    kind, f = frames["Breakout 60d high + volume"]
    assert kind == BUY
    assert f["A"].sum() == 1 and f["A"].iloc[70]
    assert not f["B"].any()
    _, f20 = frames["Breakout 20d high + volume"]
    assert f20["A"].iloc[70]
    # the same breakout without volume confirmation is not a signal
    P["volume"].iloc[70, 0] = 1000.0
    _, f2 = signals.signal_frames(P)["Breakout 60d high + volume"]
    assert not f2["A"].any()


def test_breakdown_and_death_cross_are_risk_signals():
    down = np.r_[np.full(80, 100.0), np.linspace(100, 60, 60)]
    P = _panel({"A": down})
    frames = signals.signal_frames(P)
    kind, f = frames["Breakdown below 60d low"]
    assert kind == RISK and f["A"].any()
    kind, f = frames["Death cross MA 20/60"]
    assert kind == RISK and f["A"].sum() == 1
    kind, f = frames["Drawdown 10% from 60d high"]
    assert kind == RISK and f["A"].sum() == 1


def test_channel_slope_sign_and_position():
    n = 200
    rising = 100 * np.exp(np.linspace(0, 0.4, n))
    P = _panel({"A": rising, "B": rising[::-1]})
    slope = signals.channel_slope(P["close"]).iloc[-1]
    assert slope["A"] > signals.CHANNEL_SLOPE and slope["B"] < -signals.CHANNEL_SLOPE
    pos = signals.channel_position(P["close"]).iloc[-1]
    assert 0 <= pos["A"] <= 1
    st = signals.status(P, "A")
    assert "rising" in signals.trend_words(st)
    assert signals.trend_words(signals.status(_panel({"C": np.full(30, 5.0)}), "C")).startswith("too short")


def test_scan_reads_the_store_and_tags_odds(home):
    from osloquant.contract.storage import df_to_db
    from osloquant.domain import Stock1dAdjKdata

    from .helpers import store_stocks

    store_stocks(["AAA", "BBB"])
    closes = np.full(90, 50.0)
    closes[80:] = 56.0
    frame = bars("stock_ol_AAA", closes)
    frame.loc[frame.index[80], "volume"] = 5000.0
    df_to_db(frame, Stock1dAdjKdata, "yahoo")
    df_to_db(bars("stock_ol_BBB", np.full(90, 20.0)), Stock1dAdjKdata, "yahoo")
    P = signals.load_panel()
    odds = {"signals": {"Breakout 60d high + volume": {"exc20": 0.0035, "exc60": 0.0127, "hit20": 0.48}}}
    day = P["close"].index[80]
    alerts = signals.scan(P, asof=day, odds=odds)
    kinds = {(a.code, a.signal) for a in alerts}
    assert ("AAA", "Breakout 60d high + volume") in kinds
    a = next(a for a in alerts if a.signal == "Breakout 60d high + volume")
    assert a.exc20 == 0.0035 and "60-day high" in a.detail
    assert not [a for a in alerts if a.code == "BBB"]


def test_digest_and_summary_with_a_research_book(tmp_path):
    P = _panel({"AAA": np.linspace(33, 41, 150), "SATS": np.full(150, 40.0)})
    today = P["close"].index[-1]
    book = [
        {"code": "AAA", "name": "Alpha Retail", "rating": "BUY", "target": 60, "bear": 35, "bull": 80, "dcf": 55.0,
         "price_at_valuation": 45.0, "valuation_date": "2025-01-02",
         "events": [{"date": (today + pd.Timedelta(days=12)).strftime("%Y-%m-%d"), "what": "Q3 report"}],
         "kill": ["gross margin below 40%"]},
        {"code": "NOPE", "name": "Not stored"},
    ]
    alerts = [Alert("AAA", "Alpha Retail", "New 52-week high", BUY, f"{today:%Y-%m-%d}", 41.0, "above the 250-day high", 0.0002, 0.0055, 0.47),
              Alert("SATS", "SATS", "Golden cross MA 20/60", INFO, f"{today:%Y-%m-%d}", 40.0, "MA20 vs MA60")]
    text = signals.digest(P, alerts, book, today=today, odds={"measured": {"from": "2010", "to": "2026", "stocks": 63}})
    assert "upside to TP 60: +46%" in text
    assert "Q3 report" in text and "in 12 days" in text
    assert "watch: gross margin" in text
    assert "no bars in the store yet" in text
    assert "1 buy-type, 0 risk, 1 info" in text
    line = signals.summary_line(alerts, book, P)
    assert line.startswith("AAA 41.00") and "TP 60" in line and "AAA New 52-week high" in line
    md, js = signals.write_digest(text, alerts, f"{today:%Y-%m-%d}")
    assert md.exists() and js.exists() and (md.parent / "latest.md").read_text(encoding="utf-8") == text
    assert signals.previous_session() == f"{today:%Y-%m-%d}"


def test_html_page_draws_the_book_and_the_alerts(tmp_path):
    from osloquant.signals_page import render_html

    P = _panel({"AAA": np.linspace(33, 41, 150), "SATS": np.full(150, 40.0)})
    today = P["close"].index[-1]
    book = [{"code": "AAA", "name": "Alpha Retail", "rating": "BUY", "target": 60, "bear": 35, "bull": 80, "dcf": 55.0,
             "price_at_valuation": 45.0, "valuation_date": "2025-01-02", "events": [{"date": "2099-01-01", "what": "Q3 report"}],
             "kill": ["gross margin below 40%"]},
            {"code": "NOPE", "name": "Not stored"}]
    alerts = [Alert("AAA", "Alpha Retail", "New 52-week high", BUY, f"{today:%Y-%m-%d}", 41.0, "above the 250-day high", 0.0002, 0.0055, 0.47),
              Alert("SATS", "SATS", "Death cross MA 20/60", RISK, f"{today:%Y-%m-%d}", 40.0, "MA20 vs MA60", -0.0054, -0.0042, 0.45)]
    odds = {"measured": {"from": "2010", "to": "2026", "stocks": 63}, "signals": {"New 52-week high": {"kind": BUY, "per_month": 29.1, "raw20": 0.008, "exc20": 0.0002, "exc60": 0.0055, "hit20": 0.47, "t20": 0.2}}}
    page = render_html(P, alerts, book, f"{today:%Y-%m-%d}", odds=odds, today=today)
    assert page.startswith("<!doctype html>") and "<svg" in page
    assert "Alpha Retail" in page and "TP 60" in page and "+46%" in page            # upside to the target
    assert "no bars in the store yet" in page and "Q3 report" in page
    assert "Death cross MA 20/60" in page and "1 buy-type" in page and "1 risk" in page
    assert "What these signals have meant" in page and "29.1" in page
    md, js = signals.write_digest("x", alerts, f"{today:%Y-%m-%d}", page=page)
    assert (md.parent / "latest.html").read_text(encoding="utf-8") == page


def test_scorecard_counts_events_and_odds_file_round_trip(tmp_path):
    rng = np.random.default_rng(0)
    walk = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, (400, 4)), axis=0))
    P = _panel({c: walk[:, i] for i, c in enumerate("ABCD")})
    table = signals.scorecard(P)
    assert set(table.index) == set(signals.signal_frames(P))
    assert (table["events"] >= 0).all() and "exc20" in table.columns
    path = signals.write_odds(table, "2020-01-01", "2021-07-01", 4, path=tmp_path / "odds.yaml")
    odds = signals.load_odds(path)
    assert odds["measured"]["stocks"] == 4
    assert set(odds["signals"]) == set(table.index)
    assert odds["signals"]["New 52-week high"]["kind"] == BUY


def test_shipped_odds_file_covers_every_signal():
    odds = signals.load_odds()
    P = _panel({"A": np.full(10, 1.0)})
    assert set(signals.signal_frames(P)) <= set(odds.get("signals", {}))


def test_scorecard_reports_clustered_t_intervals_and_grades():
    rng = np.random.default_rng(5)
    n = 2600                                              # ~10 years from 2010
    frames = {c: 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.02, n))) for c in ("A", "B", "C", "D")}
    P = _panel(frames, start="2010-01-04")
    for k in P:
        P[k].loc[P[k].index[:1500], "D"] = np.nan             # D is listed late: not a "survivor from the start"
    table = signals.scorecard(P)
    assert {"tc20", "tc60", "lo20", "hi20", "lo60", "hi60", "bench20", "top60", "topshare60"} <= set(table.columns)
    row = table.loc["Breakout 20d high + volume"]
    if row["events"] > 10:
        assert np.isfinite(row["tc20"]) and row["lo20"] <= row["exc20"] <= row["hi20"]
        assert row["raw20"] - row["exc20"] == pytest.approx(row["bench20"], abs=1e-12)
    rob = signals.robustness(P, periods=(("2010-01-01", "2013-12-31"), ("2014-01-01", "2016-12-31"), ("2017-01-01", "2030-12-31")), listed_by="2011-01-01")
    for r in rob.values():
        assert set(r) >= {"periods", "survivors", "grade20", "grade60", "checks20", "checks60", "survivor_stocks"}
        assert r["survivor_stocks"] == 3 and len(r["periods"]) == 3
        assert r["grade60"] in "ABCD" and r["checks60"]["outside_placebo_band"] is None
    # iid noise must not look stable: no signal gets an A on both horizons
    assert not any(r["grade20"] == "A" and r["grade60"] == "A" for r in rob.values())


def test_cluster_t_and_bootstrap_on_known_series():
    idx = pd.MultiIndex.from_product([pd.bdate_range("2020-01-01", periods=240), ["A", "B"]])
    rng = np.random.default_rng(0)
    noise = pd.Series(rng.normal(0, 0.02, len(idx)), index=idx)
    assert abs(signals.cluster_t(noise, 20)) < 3
    shifted = noise + 0.05
    assert signals.cluster_t(shifted, 20) > 5
    lo, hi = signals.boot_ci(shifted)
    assert lo < 0.05 < hi and hi - lo < 0.02
    one = pd.Series([0.5, 0.0, 0.0], index=pd.MultiIndex.from_tuples([(pd.Timestamp("2020-01-02"), c) for c in "ABC"]))
    code, share = signals.dominant_stock(one)
    assert code == "A" and share == pytest.approx(1.0)
    assert signals.grade({"a": True, "b": True, "c": True, "d": None}) == "A"
    assert signals.grade({"a": True, "b": False, "c": True, "d": None}) == "B"
    assert signals.grade({"a": False, "b": False, "c": False, "d": None}) == "D"


def test_edge_does_not_fire_on_the_first_day_an_indicator_exists():
    state = pd.DataFrame({"A": [False, True, True, False, True]})
    valid = pd.DataFrame({"A": [False, True, True, True, True]})        # the indicator starts on day 2
    assert list(signals._edge(state)["A"]) == [False, True, False, False, True]
    assert list(signals._edge(state, valid)["A"]) == [False, False, False, False, True]


def test_write_odds_keeps_bracket_results(tmp_path):
    import yaml

    path = tmp_path / "odds.yaml"
    path.write_text(yaml.safe_dump({"measured": {"bracket": {"R": "2 x ATR"}},
                                    "signals": {"New 52-week high": {"exc20": 0.1, "bracket": {"h20": {"target": 0.4}}}}}), encoding="utf-8")
    table = pd.DataFrame([{"signal": "New 52-week high", "kind": BUY, "events": 3.0, "per_month": 1.0, "exc20": 0.001, "tc20": 0.5}]).set_index("signal")
    signals.write_odds(table, "2010-01-01", "2026-10-19", 64, path=path, robust={"New 52-week high": {"grade60": "D", "periods": {}}})
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["signals"]["New 52-week high"]["bracket"] == {"h20": {"target": 0.4}}
    assert doc["measured"]["bracket"] == {"R": "2 x ATR"}
    assert doc["signals"]["New 52-week high"]["robustness"]["grade60"] == "D"
    assert doc["signals"]["New 52-week high"]["exc20"] == 0.001
