import numpy as np
import pandas as pd
import pytest

from osloquant.contract import TargetType, context
from osloquant.contract.storage import df_to_db
from osloquant.domain import FinanceFactor
from osloquant.factors import (
    AboveMaFactor,
    BollFactor,
    BullFactor,
    CrossMaFactor,
    GoldCrossFactor,
    GoodCompanyFactor,
    MacdTransformer,
    MaTransformer,
    MomentumFactor,
    SelectMode,
    TargetSelector,
)
from tests.helpers import bars, business_days, panel, random_walk, store_bars, store_stocks

A, B = "stock_ol_AAA", "stock_ol_BBB"


def day(i: int) -> pd.Timestamp:
    return business_days(i + 1)[-1]


def two_stocks(n: int = 300) -> pd.DataFrame:
    return panel([bars(A, random_walk(n, seed=1)), bars(B, random_walk(n, seed=2))])


def test_moving_average_matches_a_hand_calculation_and_stays_within_each_entity():
    df = panel([bars(A, [1, 2, 3, 4, 5]), bars(B, [10, 20, 30, 40, 50])])
    out = MaTransformer(windows=[3]).transform(df)

    assert out.loc[A, "ma3"].tolist()[2:] == [2, 3, 4]
    assert out.loc[B, "ma3"].tolist()[2:] == [20, 30, 40]
    # the first rows of B must not be averaged with the last rows of A
    assert out.loc[B, "ma3"].iloc[:2].isna().all()


def test_macd_matches_pandas_ewm():
    closes = random_walk(120, seed=3)
    out = MacdTransformer().transform(panel([bars(A, closes)])).loc[A]
    s = pd.Series(closes)
    diff = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()

    assert out["diff"].iloc[60] == pytest.approx(diff.iloc[60])
    assert out["macd"].iloc[-1] == pytest.approx(out["diff"].iloc[-1] - out["dea"].iloc[-1])
    assert out["diff"].iloc[:25].isna().all()  # not enough history yet


def test_cross_ma_targets():
    rising = [10.0] * 10 + list(np.linspace(11, 30, 20))
    falling = [30.0] * 10 + list(np.linspace(29, 10, 20))
    factor = CrossMaFactor(windows=(3, 5), data_df=panel([bars(A, rising), bars(B, falling)]))

    assert factor.get_targets(day(29)) == [A]
    assert factor.get_targets(day(29), TargetType.negative) == [B]
    # while the long average is still warming up there is no verdict either way
    assert factor.get_targets(day(2)) == [] and factor.get_targets(day(2), TargetType.negative) == []
    # a day without bars has no targets
    assert factor.get_targets("2019-01-01") == []


def test_a_verdict_never_depends_on_later_data():
    full = two_stocks(300)
    cut = full[full.index.get_level_values("timestamp") <= day(200)]
    for factor_cls, kwargs in ((CrossMaFactor, {}), (AboveMaFactor, {"window": 50}), (GoldCrossFactor, {}), (BullFactor, {}), (BollFactor, {})):
        with_future = factor_cls(data_df=full, **kwargs).result_df
        without = factor_cls(data_df=cut, **kwargs).result_df
        pd.testing.assert_frame_equal(with_future.loc[without.index], without, check_names=False)


def test_momentum_never_depends_on_later_data_and_skips_the_last_month():
    frames = [bars(f"stock_ol_S{i}", random_walk(400, seed=10 + i)) for i in range(8)]
    full = panel(frames)
    cut = full[full.index.get_level_values("timestamp") <= day(350)]
    with_future = MomentumFactor(data_df=full)
    without = MomentumFactor(data_df=cut)

    pd.testing.assert_frame_equal(with_future.result_df.loc[without.result_df.index], without.result_df)

    close = full["close"].xs("stock_ol_S0", level="entity_id")
    expected = close.iloc[350 - 21] / close.iloc[350 - 252] - 1
    assert with_future.factor_df.loc[("stock_ol_S0", day(350)), "momentum"] == pytest.approx(expected)


def test_momentum_ranks_the_winner_first_and_uses_both_thresholds():
    n = 300
    growth = {f"stock_ol_S{i}": 1 + 0.0005 * i for i in range(10)}  # S9 rises fastest
    frames = [bars(e, 100 * g ** np.arange(n)) for e, g in growth.items()]
    factor = MomentumFactor(data_df=panel(frames))
    last = day(n - 1)

    scores = factor.get_scores(last)
    assert scores.idxmax() == "stock_ol_S9" and scores.max() == pytest.approx(1.0)
    assert factor.get_targets(last) == ["stock_ol_S7", "stock_ol_S8", "stock_ol_S9"]  # score >= 0.8
    assert factor.get_targets(last, TargetType.negative) == [f"stock_ol_S{i}" for i in range(4)]  # score < 0.5
    assert factor.get_targets(day(100)) == []  # a year of history is needed first


def test_boll_has_no_opinion_between_the_bands():
    closes = [100.0] * 25 + [80.0] + [100.0] * 3 + [101.0]
    factor = BollFactor(data_df=panel([bars(A, closes)]))
    verdict = factor.result_df.loc[A, "filter_result"]

    assert verdict.iloc[25] is True or verdict.iloc[25] == True  # noqa: E712  the plunge is below the lower band
    assert factor.get_targets(day(25)) == [A]
    assert factor.get_targets(day(29), TargetType.negative) == [A]  # back above the middle
    assert pd.isna(verdict.iloc[10])


def test_signal_df_marks_the_days_the_verdict_flips():
    closes = [10.0] * 10 + list(np.linspace(11, 30, 10)) + list(np.linspace(29, 5, 15))
    factor = CrossMaFactor(windows=(3, 5), data_df=panel([bars(A, closes)]))
    signals = factor.get_signal_df()

    assert signals["signal"].tolist() == ["buy", "sell"]
    buy, sell = signals["timestamp"].tolist()
    assert day(10) <= buy <= day(12) and day(20) <= sell <= day(24)
    # a sell is only marked after a buy
    only_down = CrossMaFactor(windows=(3, 5), data_df=panel([bars(A, np.linspace(30, 5, 30))]))
    assert only_down.get_signal_df().empty


def test_technical_factor_reads_from_the_store():
    ids = store_stocks(["AAA", "BBB"])
    store_bars(bars(A, random_walk(60, seed=1)))
    store_bars(bars(B, random_walk(60, seed=2)))

    everything = CrossMaFactor()
    one = CrossMaFactor(codes=["BBB"], start_timestamp="2020-02-03")

    assert sorted(everything.factor_df.index.get_level_values("entity_id").unique()) == ids
    assert one.factor_df.index.get_level_values("entity_id").unique().tolist() == [B]
    assert one.factor_df.index.get_level_values("timestamp").min() == pd.Timestamp("2020-02-03")
    assert list(one.factor_df.columns[:6]) == ["open", "high", "low", "close", "volume", "turnover"]


def store_reports(entity_id: str, roes: list[float], first_year: int = 2021) -> None:
    rows = []
    for i, roe in enumerate(roes):
        report_date = pd.Timestamp(f"{first_year + i}-12-31")
        rows.append(
            {
                "id": f"{entity_id}_year_{report_date:%Y-%m-%d}",
                "entity_id": entity_id,
                "timestamp": report_date + pd.Timedelta(days=90),
                "report_date": report_date,
                "report_period": "year",
                "code": entity_id.split("_", 2)[2],
                "roe": roe,
                "revenue_growth_yoy": 0.05,
                "cash_conversion": 1.0,
            }
        )
    df_to_db(pd.DataFrame(rows), FinanceFactor, "yahoo")


def test_good_company_is_known_only_from_the_publication_date_and_carried_forward():
    store_reports(A, [0.15, 0.20, 0.18])  # reports for 2021, 2022, 2023
    store_reports(B, [0.15, 0.02, 0.18])
    factor = GoodCompanyFactor(count=2, end_timestamp="2024-12-31")

    # the 2022 report is public at the end of March 2023: before that only one report exists
    assert factor.get_targets("2023-03-15") == []
    assert factor.get_targets("2023-04-03") == [A]
    assert factor.get_targets("2023-04-03", TargetType.negative) == [B]
    # carried forward between reports, also on a day with no report
    assert factor.get_targets("2023-11-20") == [A]
    assert factor.get_targets("2024-06-03") == [A]
    # B's good 2023 does not make up for its bad 2022 when two good years are asked for
    assert factor.get_targets("2024-06-03", TargetType.negative) == [B]


def test_a_carried_verdict_expires():
    store_reports(A, [0.15, 0.20])
    factor = GoodCompanyFactor(count=2, end_timestamp="2026-12-31")
    assert factor.get_targets("2023-06-01") == [A]
    assert factor.get_targets("2025-06-02") == []  # two years after the last report nothing is assumed


def test_target_selector_modes():
    up = [10.0] * 10 + list(np.linspace(11, 30, 20))
    down = [30.0] * 10 + list(np.linspace(29, 10, 20))
    # A rises in both; B rises on the short view only
    short_view = CrossMaFactor(windows=(3, 5), data_df=panel([bars(A, up), bars(B, up)]))
    long_view = CrossMaFactor(windows=(3, 5), data_df=panel([bars(A, up), bars(B, down)]))
    last = day(29)

    both = TargetSelector(factors=[short_view, long_view])
    either = TargetSelector(factors=[short_view, long_view], select_mode=SelectMode.condition_or)

    assert both.get_open_long_targets(last) == [A] and both.get_open_short_targets(last) == [B]
    assert either.get_open_long_targets(last) == [A, B] and either.get_open_short_targets(last) == []


def test_factor_classes_register_by_name():
    for name in ("CrossMaFactor", "AboveMaFactor", "GoldCrossFactor", "BullFactor", "BollFactor", "MomentumFactor", "GoodCompanyFactor"):
        assert name in context.factor_cls_registry
