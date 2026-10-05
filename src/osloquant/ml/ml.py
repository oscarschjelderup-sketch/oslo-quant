"""Machine learning on bars: features from the past, a label from the future, a model in between.

    machine = MaStockMLMachine(codes=["EQNR"], predict_start_timestamp="2024-01-01")
    machine.train()
    machine.predict()
    machine.evaluate()      # out of sample, next to the naive forecast it has to beat

The data is split in time, never at random. The last ``predict_steps`` bars before the split are left out
of training, because their labels are computed from prices inside the test period.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from osloquant.contract import IntervalLevel
from osloquant.contract.api import get_data, get_entity_ids, get_kdata_schema, to_pd_timestamp
from osloquant.contract.factor import INDEX, by_entity
from osloquant.factors.transformers import MaTransformer

logger = logging.getLogger(__name__)

LABEL_METHODS = ("raw", "change", "behavior_cls")


class MLMachine:
    entity_schema: type | None = None

    def __init__(
        self,
        entity_ids: list[str] | None = None,
        codes: list[str] | None = None,
        start_timestamp="2015-01-01",
        end_timestamp=None,
        predict_start_timestamp="2023-01-01",
        predict_steps: int = 20,
        level=IntervalLevel.LEVEL_1DAY,
        adjust_type=None,
        data_provider: str | None = None,
        label_method: str = "change",
        kdata_df: pd.DataFrame | None = None,
    ) -> None:
        """
        :param predict_start_timestamp: train before this date, test from it on
        :param predict_steps: how many bars ahead the label looks
        :param label_method: "raw" predicts the close ``predict_steps`` ahead, "change" the return until
            then, "behavior_cls" whether that return is positive (1) or not (0)
        :param kdata_df: bars to use instead of reading the store, indexed by (entity_id, timestamp)
        """
        if label_method not in LABEL_METHODS:
            raise ValueError(f"label_method must be one of {LABEL_METHODS}")
        self.start_timestamp = to_pd_timestamp(start_timestamp)
        self.end_timestamp = to_pd_timestamp(end_timestamp) if end_timestamp is not None else pd.Timestamp.now().normalize()
        self.predict_start_timestamp = to_pd_timestamp(predict_start_timestamp)
        assert self.start_timestamp < self.predict_start_timestamp < self.end_timestamp
        self.predict_steps = predict_steps
        self.level = IntervalLevel(level)
        self.adjust_type = adjust_type
        self.data_provider = data_provider
        self.label_method = label_method

        if entity_ids is None and codes is not None:
            entity_ids = get_entity_ids(self.entity_schema, codes=codes)
        self.entity_ids = entity_ids

        self.kdata_df = kdata_df if kdata_df is not None else self.build_kdata()
        if self.kdata_df.empty:
            raise LookupError("no bars to learn from; record them first")

        self.feature_df = self.build_feature(self.entity_ids, self.start_timestamp, self.end_timestamp).dropna()
        self.feature_names = list(self.feature_df.columns)
        self.label_ser = self.build_label().reindex(self.feature_df.index)
        self.label_name = self.label_ser.name

        self.training_X, self.training_y, self.testing_X, self.testing_y = self.split_data()
        self.model = None
        self.pred_y: pd.Series | None = None

    # -- data -------------------------------------------------------------------------------------

    def build_kdata(self) -> pd.DataFrame:
        schema = get_kdata_schema(self.entity_schema, level=self.level, adjust_type=self.adjust_type)
        return get_data(
            schema,
            provider=self.data_provider,
            entity_ids=self.entity_ids,
            start_timestamp=self.start_timestamp,
            end_timestamp=self.end_timestamp,
            columns=["entity_id", "timestamp", "close"],
            index=INDEX,
            drop_index_col=True,
        )

    def build_feature(self, entity_ids, start_timestamp: pd.Timestamp, end_timestamp: pd.Timestamp) -> pd.DataFrame:
        """Return the features, indexed by (entity_id, timestamp). A row may only use bars up to its own."""
        raise NotImplementedError

    def build_label(self) -> pd.Series:
        close = self.kdata_df["close"]
        future = by_entity(close).shift(-self.predict_steps)
        if self.label_method == "raw":
            label = future
        elif self.label_method == "change":
            label = future / close - 1
        else:
            label = (future > close).astype(float).where(future.notna())
        return label.rename(f"y_{self.predict_steps}")

    def split_data(self):
        timestamps = self.feature_df.index.get_level_values("timestamp")
        in_test = timestamps >= self.predict_start_timestamp
        testing_X, testing_y = self.feature_df[in_test], self.label_ser[in_test]

        # purge: a training label must not reach into the test period
        position_from_end = by_entity(self.label_ser[~in_test]).cumcount(ascending=False)
        keep = (position_from_end >= self.predict_steps) & self.label_ser[~in_test].notna()
        training_X, training_y = self.feature_df[~in_test][keep], self.label_ser[~in_test][keep]
        return training_X, training_y, testing_X, testing_y

    # -- model ------------------------------------------------------------------------------------

    def default_model(self):
        from sklearn.linear_model import LinearRegression, LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        if self.label_method == "behavior_cls":
            return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        return make_pipeline(StandardScaler(), LinearRegression())

    def train(self, model=None, **params):
        if self.training_X.empty:
            raise LookupError("nothing to train on before predict_start_timestamp")
        self.model = (model if model is not None else self.default_model()).fit(self.training_X, self.training_y, **params)
        return self.model

    def predict(self) -> pd.Series:
        """Predict every test row, including the newest ones whose outcome is not known yet."""
        assert self.model is not None, "train() first"
        self.pred_y = pd.Series(self.model.predict(self.testing_X), index=self.testing_X.index, name="pred")
        return self.pred_y

    def evaluate(self) -> dict:
        """Out-of-sample quality, next to a naive forecast.

        For "raw" the naive forecast is today's close, for "change" the average return of the training
        period, for "behavior_cls" the more common class of the training period. A model that does not beat
        it has learned nothing; in a rising market, beating "no change" would only mean it learned the drift.
        """
        assert self.pred_y is not None, "predict() first"
        known = self.testing_y.notna()
        y, pred = self.testing_y[known], self.pred_y[known]
        if y.empty:
            return {"observations": 0}
        out: dict = {"observations": int(len(y)), "label_method": self.label_method}

        if self.label_method == "behavior_cls":
            majority = float(self.training_y.mean() >= 0.5)
            out["accuracy"] = float((pred == y).mean())
            out["naive_accuracy"] = float((y == majority).mean())
            return out

        close = self.kdata_df["close"].reindex(y.index)
        naive = close if self.label_method == "raw" else pd.Series(float(self.training_y.mean()), index=y.index)
        out["mae"] = float((pred - y).abs().mean())
        out["naive_mae"] = float((naive - y).abs().mean())
        # R2 against the naive forecast: positive only if the model is closer to the outcome than it
        out["r2_vs_naive"] = float(1 - ((pred - y) ** 2).sum() / ((naive - y) ** 2).sum())
        predicted_change = pred / close - 1 if self.label_method == "raw" else pred
        realised_change = y / close - 1 if self.label_method == "raw" else y
        out["hit_rate"] = float((np.sign(predicted_change) == np.sign(realised_change)).mean())
        out["rank_ic"] = float(predicted_change.corr(realised_change, method="spearman"))
        return out

    def draw_result(self, entity_id: str | None = None, code: str | None = None, show: bool = False):
        from osloquant.contract.drawer import draw_prediction

        fig = draw_prediction(self, entity_id=entity_id, code=code)
        if show:
            fig.show()
        return fig


class StockMLMachine(MLMachine):
    def __init__(self, *args, **kwargs) -> None:
        from osloquant.domain.meta import Stock

        self.entity_schema = Stock
        super().__init__(*args, **kwargs)


class MaStockMLMachine(StockMLMachine):
    """Features: moving averages of the close.

    For the "raw" label the averages themselves, as in zvt. For the other labels the close relative to
    each average, because a price level means nothing when comparing one stock with another.
    """

    windows = (5, 10, 120, 250)

    def build_feature(self, entity_ids, start_timestamp, end_timestamp) -> pd.DataFrame:
        transformer = MaTransformer(windows=self.windows)
        df = transformer.transform(self.kdata_df)
        if self.label_method == "raw":
            return df[transformer.indicators]
        return pd.DataFrame({f"close_to_{name}": df["close"] / df[name] - 1 for name in transformer.indicators})
