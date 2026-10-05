import numpy as np
import pandas as pd
import pytest

from osloquant.ml import MaStockMLMachine
from tests.helpers import bars, business_days, panel, random_walk, store_bars, store_stocks

A, B = "stock_ol_AAA", "stock_ol_BBB"
N = 700
SPLIT = business_days(N)[500]


def kdata() -> pd.DataFrame:
    return panel([bars(A, random_walk(N, seed=1)), bars(B, random_walk(N, seed=2))])[["close"]]


def machine(label_method="change", **kwargs) -> MaStockMLMachine:
    defaults = {"kdata_df": kdata(), "start_timestamp": "2020-01-01", "end_timestamp": business_days(N)[-1],
                "predict_start_timestamp": SPLIT, "predict_steps": 20, "label_method": label_method}  # fmt: skip
    return MaStockMLMachine(**{**defaults, **kwargs})


def test_the_label_is_the_future_and_the_features_are_the_past():
    m = machine("change")
    close = m.kdata_df["close"].xs(A, level="entity_id")
    t = business_days(N)[400]

    assert m.label_ser.loc[(A, t)] == pytest.approx(close.iloc[420] / close.iloc[400] - 1)
    assert m.feature_df.loc[(A, t), "close_to_ma5"] == pytest.approx(close.iloc[400] / close.iloc[396:401].mean() - 1)
    assert not m.feature_df.isna().any().any()  # the warm-up rows are gone


def test_the_label_never_crosses_from_one_stock_into_the_next():
    m = machine("raw")
    last_rows_of_a = m.label_ser.xs(A, level="entity_id").iloc[-20:]
    assert last_rows_of_a.isna().all()  # there is no close 20 days after A's last days, and B's must not fill in


def test_training_labels_do_not_reach_into_the_test_period():
    m = machine("change")
    dates = business_days(N)
    last_training_day = m.training_X.index.get_level_values("timestamp").max()

    assert m.testing_X.index.get_level_values("timestamp").min() == SPLIT
    # the label of the last training row is the return until 20 bars later, which must still be before the split
    assert dates[dates.get_loc(last_training_day) + 20] < SPLIT
    assert m.training_y.notna().all() and len(m.training_X) == len(m.training_y)
    # the newest test rows have no outcome yet but are still predicted
    assert m.testing_y.isna().sum() == 2 * 20 and len(m.testing_X) == 2 * 200


@pytest.mark.parametrize("label_method, keys", [("change", {"mae", "naive_mae", "r2_vs_naive", "hit_rate", "rank_ic"}), ("raw", {"mae", "naive_mae", "r2_vs_naive"}), ("behavior_cls", {"accuracy", "naive_accuracy"})])
def test_train_predict_evaluate(label_method, keys):
    m = machine(label_method)
    m.train()
    predictions = m.predict()
    result = m.evaluate()

    assert len(predictions) == len(m.testing_X) and predictions.notna().all()
    assert keys <= set(result) and result["observations"] == 2 * 180
    if label_method == "behavior_cls":
        assert set(np.unique(predictions)) <= {0.0, 1.0} and 0 <= result["accuracy"] <= 1
    assert m.draw_result(entity_id=B).data


def test_a_random_walk_is_not_predictable_and_the_evaluation_says_so():
    m = machine("change")
    m.train()
    m.predict()
    result = m.evaluate()
    # noise cannot be learned: the model must not come out clearly ahead of predicting no change
    assert result["r2_vs_naive"] < 0.05 and abs(result["rank_ic"]) < 0.3


def test_a_planted_pattern_is_found():
    # returns that mean-revert to the 5-day average: tomorrow's move is predictable from close / ma5
    rng = np.random.default_rng(0)
    closes = [100.0]
    for _ in range(N - 1):
        recent = np.mean(closes[-5:])
        closes.append(closes[-1] * (1 - 0.5 * (closes[-1] / recent - 1) + rng.normal(0, 0.005)))

    class ShortMemory(MaStockMLMachine):
        windows = (5,)

    m = ShortMemory(kdata_df=panel([bars(A, closes)])[["close"]], start_timestamp="2020-01-01", end_timestamp=business_days(N)[-1],
                    predict_start_timestamp=SPLIT, predict_steps=1, label_method="change")  # fmt: skip
    m.train()
    m.predict()
    result = m.evaluate()
    assert result["rank_ic"] > 0.2 and result["r2_vs_naive"] > 0.02 and result["hit_rate"] > 0.55


def test_the_machine_reads_from_the_store():
    store_stocks(["AAA"])
    store_bars(bars(A, random_walk(N, seed=1)))
    m = MaStockMLMachine(codes=["AAA"], start_timestamp="2020-01-01", end_timestamp=business_days(N)[-1], predict_start_timestamp=SPLIT)
    assert m.entity_ids == [A] and len(m.kdata_df) == N


def test_bad_arguments_are_refused():
    with pytest.raises(ValueError, match="label_method"):
        machine("nonsense")
    with pytest.raises(AssertionError):
        machine(predict_start_timestamp="2019-01-01")
