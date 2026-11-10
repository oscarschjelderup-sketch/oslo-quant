"""Dividends paid in another currency (docs/forbedring/endringer.md E9, funn #5). Yahoo reports the amount converted
to NOK at the download day's rate, but scales the adjusted prices with the amount in the foreign currency against a
price in NOK. The rule recovers the foreign amount from Yahoo's own factor step, converts it at the rate before the
ex-date, and puts both the adjusted prices and the stored dividend right."""

from __future__ import annotations

import pandas as pd
import pytest

from osloquant.recorders.yahoo.action_recorder import to_actions
from osloquant.recorders.yahoo.cleaning import clean_history, fix_foreign_dividends
from tests.helpers import business_days


def _history(closes: list[float], dividends: dict[int, tuple[float, float]]) -> pd.DataFrame:
    """Quoted closes and, per ex-day index, (the amount Yahoo reports, the amount Yahoo adjusted with)."""
    n = len(closes)
    df = pd.DataFrame({"timestamp": business_days(n), "open": closes, "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
                       "close": closes, "volume": 1000.0, "dividend": 0.0, "split": 0.0})
    factor = [1.0] * n
    for i, (reported, used) in dividends.items():
        df.loc[i, "dividend"] = reported
        step = 1 - used / closes[i - 1]
        for j in range(i):
            factor[j] *= step
    df["adj_close"] = df["close"] * factor
    return df


def _fx(n: int, usd: list[float] | float = 10.0, dkk: float = 1.45, eur: float = 11.5) -> dict[str, pd.Series]:
    days = business_days(n)
    u = usd if isinstance(usd, list) else [usd] * n
    return {"USD": pd.Series(u, index=days), "DKK": pd.Series(dkk, index=days), "EUR": pd.Series(eur, index=days)}


def test_a_dollar_dividend_is_adjusted_with_its_amount_in_kroner_at_the_ex_date():
    closes = [100.0] * 6 + [95.0] * 6
    usd = [10.0] * 6 + [9.5] * 6                        # NOK per USD: 10 before the ex-date, 9.5 on the download day
    # USD 1 per share, ex on day 6: Yahoo reports 9.5 (today's rate) and adjusts with 1.0 against a price of 100
    df = _history(closes, {6: (9.5, 1.0)})
    assert df["adj_close"].iloc[0] == pytest.approx(99.0)                    # Yahoo: one per cent, ten times too little
    fixed, n = fix_foreign_dividends(df, _fx(12, usd))
    assert n == 1
    assert fixed["dividend"].iloc[6] == pytest.approx(10.0, rel=1e-6)        # USD 1 at the rate before the ex-date
    assert fixed["adj_close"].iloc[:6].tolist() == pytest.approx([90.0] * 6, rel=1e-6)
    assert fixed["adj_close"].iloc[6:].tolist() == pytest.approx([95.0] * 6)
    # the adjusted series is now the total return: 100 -> 95 plus 10 received = +5 %
    assert fixed["adj_close"].iloc[6] / fixed["adj_close"].iloc[5] - 1 == pytest.approx(0.0556, abs=1e-4)
    assert to_actions(fixed)["dividend"].tolist() == pytest.approx([10.0], rel=1e-6)


def test_a_krone_dividend_and_a_history_without_rates_are_left_alone():
    closes = [200.0] * 5 + [190.0] * 5
    nok = _history(closes, {5: (10.0, 10.0)})
    fixed, n = fix_foreign_dividends(nok, _fx(10))
    assert n == 0 and fixed["adj_close"].tolist() == pytest.approx(nok["adj_close"].tolist()) and fixed["dividend"].iloc[5] == 10.0
    usd = _history(closes, {5: (10.0, 1.0)})
    for rates in ({}, None):                             # no currency table in the store yet: nothing is guessed
        fixed, n = fix_foreign_dividends(usd, rates)
        assert n == 0 and fixed["adj_close"].tolist() == pytest.approx(usd["adj_close"].tolist())
    # a ratio that is no known currency (a restated amount, a data error) is left alone too
    odd = _history(closes, {5: (10.0, 3.0)})
    fixed, n = fix_foreign_dividends(odd, _fx(10))
    assert n == 0 and fixed["dividend"].iloc[5] == 10.0


def test_danish_kroner_and_several_dividends_in_one_history():
    closes = [300.0] * 4 + [290.0] * 4 + [280.0] * 4
    # DKK 6 and DKK 8: reported at 1.45, adjusted with the DKK amounts
    df = _history(closes, {4: (8.70, 6.0), 8: (11.60, 8.0)})
    fixed, n = fix_foreign_dividends(df, _fx(12))
    assert n == 2
    assert fixed["dividend"].iloc[[4, 8]].tolist() == pytest.approx([8.70, 11.60], rel=1e-6)
    s1, s2 = 1 - 8.70 / 300.0, 1 - 11.60 / 290.0
    assert fixed["adj_close"].iloc[0] == pytest.approx(300.0 * s1 * s2, rel=1e-6)
    assert fixed["adj_close"].iloc[5] == pytest.approx(290.0 * s2, rel=1e-6)
    assert fixed["adj_close"].iloc[-1] == pytest.approx(280.0)


def test_mixed_histories_fix_only_the_foreign_events():
    closes = [100.0] * 4 + [98.0] * 4 + [96.0] * 4
    df = _history(closes, {4: (2.0, 2.0), 8: (9.5, 1.0)})          # a krone dividend, then a dollar one
    fixed, n = fix_foreign_dividends(df, _fx(12, [10.0] * 12))
    assert n == 1 and fixed["dividend"].iloc[4] == 2.0 and fixed["dividend"].iloc[8] == pytest.approx(10.0, rel=1e-6)
    assert fixed["adj_close"].iloc[0] == pytest.approx(100.0 * (1 - 2 / 100) * (1 - 10 / 98), rel=1e-6)


def test_the_cleaning_runs_the_rule_first_and_counts_it():
    closes = [100.0] * 6 + [95.0] * 6
    df = _history(closes, {6: (9.5, 1.0)})
    cleaned, counts = clean_history(df, fx=_fx(12))
    assert counts["foreign_dividend"] == 1 and cleaned["adj_close"].iloc[0] == pytest.approx(90.0, rel=1e-6)
    cleaned, counts = clean_history(df)
    assert counts["foreign_dividend"] == 0 and cleaned["adj_close"].iloc[0] == pytest.approx(99.0)
