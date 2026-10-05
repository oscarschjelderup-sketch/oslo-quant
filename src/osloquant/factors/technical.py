"""Factors computed from bars."""

from __future__ import annotations

import pandas as pd

from osloquant.contract import IntervalLevel
from osloquant.contract.api import get_kdata_schema
from osloquant.contract.factor import Factor, RankScorer, ScoreFactor, filter_result
from osloquant.factors.transformers import BollTransformer, MacdTransformer, MaTransformer, MomentumTransformer


class TechnicalFactor(Factor):
    """A factor on the bars of an entity type. Adjusted bars for stocks unless told otherwise."""

    columns = ["open", "high", "low", "close", "volume", "turnover"]

    def __init__(self, entity_schema: type | None = None, level=IntervalLevel.LEVEL_1DAY, adjust_type=None, **kwargs) -> None:
        if entity_schema is None:
            from osloquant.domain.meta import Stock

            entity_schema = Stock
        self.adjust_type = adjust_type
        self.data_schema = get_kdata_schema(entity_schema, level=level, adjust_type=adjust_type)
        super().__init__(entity_schema=entity_schema, level=level, **kwargs)


class CrossMaFactor(TechnicalFactor):
    """Positive while the moving averages are stacked short above long (ma5 > ma10 > ...), negative otherwise."""

    def __init__(self, windows: tuple[int, ...] | list[int] = (5, 10), **kwargs) -> None:
        self.windows = list(windows)
        self.overlay_cols = [f"ma{w}" for w in self.windows]
        super().__init__(transformer=MaTransformer(windows=self.windows), **kwargs)

    def compute_result(self) -> None:
        df = self.factor_df
        if df.empty:
            return
        condition = pd.Series(True, index=df.index)
        for short, long in zip(self.overlay_cols[:-1], self.overlay_cols[1:], strict=True):
            condition &= df[short] > df[long]
        self.result_df = filter_result(condition, valid=df[self.overlay_cols].notna().all(axis=1))


class AboveMaFactor(TechnicalFactor):
    """Positive while the close is above its moving average: the plain trend filter."""

    def __init__(self, window: int = 200, **kwargs) -> None:
        self.window = window
        self.overlay_cols = [f"ma{window}"]
        super().__init__(transformer=MaTransformer(windows=[window]), **kwargs)

    def compute_result(self) -> None:
        df = self.factor_df
        if df.empty:
            return
        ma = df[self.overlay_cols[0]]
        self.result_df = filter_result(df["close"] > ma, valid=ma.notna())


class BullFactor(TechnicalFactor):
    """Positive while MACD's diff and dea are both above zero."""

    sub_cols = ["diff", "dea", "macd"]

    def __init__(self, fast: int = 12, slow: int = 26, n: int = 9, **kwargs) -> None:
        super().__init__(transformer=MacdTransformer(fast=fast, slow=slow, n=n), **kwargs)

    def compute_result(self) -> None:
        df = self.factor_df
        if df.empty:
            return
        self.result_df = filter_result((df["diff"] > 0) & (df["dea"] > 0), valid=df["dea"].notna())


class GoldCrossFactor(TechnicalFactor):
    """Positive while MACD's diff is above its signal line (after a golden cross), negative after a dead cross."""

    sub_cols = ["diff", "dea", "macd"]

    def __init__(self, fast: int = 12, slow: int = 26, n: int = 9, **kwargs) -> None:
        super().__init__(transformer=MacdTransformer(fast=fast, slow=slow, n=n), **kwargs)

    def compute_result(self) -> None:
        df = self.factor_df
        if df.empty:
            return
        self.result_df = filter_result(df["diff"] > df["dea"], valid=df["dea"].notna())


class BollFactor(TechnicalFactor):
    """Mean reversion: positive below the lower band, negative back above the middle, no opinion in between."""

    overlay_cols = ["bb_upper", "bb_mid", "bb_lower"]

    def __init__(self, window: int = 20, window_dev: float = 2.0, **kwargs) -> None:
        super().__init__(transformer=BollTransformer(window=window, window_dev=window_dev), **kwargs)

    def compute_result(self) -> None:
        df = self.factor_df
        if df.empty:
            return
        verdict = pd.Series(pd.NA, index=df.index, dtype="boolean")
        verdict = verdict.mask((df["close"] < df["bb_lower"]).fillna(False), True)
        verdict = verdict.mask((df["close"] > df["bb_mid"]).fillna(False), False)
        self.result_df = verdict.to_frame("filter_result")


class MomentumFactor(TechnicalFactor, ScoreFactor):
    """Cross-sectional momentum: each day the stocks are ranked on their 12-1 month return.

    The top fifth (score >= 0.8) are positive targets. A holding becomes a negative target only when it
    falls into the bottom half, so that a stock hovering around the cut-off is not traded back and forth.
    """

    long_threshold = 0.8
    short_threshold = 0.5
    sub_cols = ["momentum"]

    def __init__(self, lookback: int = 252, skip: int = 21, min_entities: int = 5, **kwargs) -> None:
        super().__init__(
            transformer=MomentumTransformer(lookback=lookback, skip=skip),
            scorer=RankScorer("momentum", min_entities=min_entities),
            **kwargs,
        )
