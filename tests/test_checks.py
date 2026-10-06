"""The look-ahead and warm-up checks catch what they are meant to, and pass what is sound."""

import pandas as pd

from osloquant.contract.factor import by_entity, filter_result
from osloquant.factors import AboveMaFactor, CrossMaFactor, GoldCrossFactor, MomentumFactor, TechnicalFactor
from osloquant.research.checks import lookahead_check, warmup_check
from tests.helpers import bars, random_walk, store_bars, store_stocks


class TomorrowFactor(TechnicalFactor):
    """Positive when tomorrow's close is higher: the classic mistake, one shift(-1)."""

    def compute_result(self):
        close = self.factor_df["close"]
        tomorrow = by_entity(close).shift(-1)
        self.factor_df = self.factor_df.assign(tomorrow=tomorrow)
        self.result_df = filter_result(tomorrow > close, valid=tomorrow.notna())


class WholeSampleFactor(TechnicalFactor):
    """Positive above the stock's average close over the whole sample: a fit on data not yet seen."""

    def compute_result(self):
        close = self.factor_df["close"]
        mean = by_entity(close).transform("mean")
        self.result_df = filter_result(close > mean)


def market(n: int = 900, codes=("AAA", "BBB", "CCC", "DDD", "EEE")) -> None:
    ids = store_stocks(list(codes))
    for k, entity_id in enumerate(ids):
        store_bars(bars(entity_id, random_walk(n, seed=40 + k, vol=0.02), start="2018-01-01"))


def test_a_factor_that_peeks_at_tomorrow_is_caught():
    market()
    found = lookahead_check(TomorrowFactor, samples=4)
    # caught on every sample day but the last of the data, which has no tomorrow to peek at even with the future
    assert found["date"].nunique() == 3
    assert {"filter_result", "tomorrow"} <= set(found["column"])


def test_a_factor_fitted_on_the_whole_sample_is_caught():
    market()
    found = lookahead_check(WholeSampleFactor, samples=4)
    assert not found.empty and set(found["frame"]) == {"result"}


def test_the_bundled_factors_do_not_look_ahead():
    market()
    for factor_cls, settings in ((CrossMaFactor, {}), (AboveMaFactor, {"window": 50}), (GoldCrossFactor, {}), (MomentumFactor, {"min_entities": 3})):
        found = lookahead_check(factor_cls, samples=3, **settings)
        assert found.empty, (factor_cls.__name__, found.head())


def test_an_exponential_average_depends_on_its_warm_up_and_a_simple_one_does_not():
    market(1500)
    day = pd.bdate_range("2018-01-01", periods=1500)[-1]
    macd = warmup_check(GoldCrossFactor, day, warmups=(60, 200, 800))
    assert macd["largest_deviation"].iloc[0] > macd["largest_deviation"].iloc[-1]  # the more history, the closer
    assert macd["largest_deviation"].iloc[-1] < 1e-6  # 800 days of history is plenty for a 26-day average
    assert macd["largest_deviation"].iloc[0] < 5  # measured against the column's size, a value near zero does not explode it

    ma = warmup_check(CrossMaFactor, day, warmups=(30, 200))
    assert (ma["largest_deviation"] < 1e-9).all() and (ma["verdicts_changed"] == 0).all()

    above = warmup_check(AboveMaFactor, day, warmups=(100, 400))  # a 200-day average needs 200 trading days
    assert above["not_computable"].iloc[0] == 5 and above["not_computable"].iloc[1] == 0


def test_a_rank_shifted_by_one_missing_stock_is_not_a_changed_verdict():
    market(1500, codes=("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"))
    day = pd.bdate_range("2018-01-01", periods=1500)[-1]
    result = warmup_check(MomentumFactor, day, warmups=(380, 2000), min_entities=3)
    # with barely a year of history the scores move a little; what counts is whether a stock changes side
    assert (result["verdicts_changed"] <= result["entities"]).all() and result["verdicts_changed"].iloc[-1] == 0
