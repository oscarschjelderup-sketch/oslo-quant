"""Factors computed from reports."""

from __future__ import annotations

import pandas as pd

from osloquant.contract.factor import Factor, by_entity, filter_result
from osloquant.domain.fundamental import FinanceFactor


class GoodCompanyFactor(Factor):
    """Positive when each of the last ``count`` annual reports clears every threshold.

    The default asks for a return on equity of at least 10 %, growing revenue, and profits that are
    backed by cash. A verdict is dated at the report's ``timestamp`` (when it was public, not the period
    end) and carried forward until the next report, for at most ``fill_gap_limit`` business days.
    """

    data_schema = FinanceFactor
    fill_gap = True

    def __init__(
        self,
        thresholds: dict[str, float] | None = None,
        count: int = 2,
        report_period: str = "year",
        **kwargs,
    ) -> None:
        self.thresholds = thresholds or {"roe": 0.10, "revenue_growth_yoy": 0.0, "cash_conversion": 0.7}
        self.count = count
        kwargs.setdefault("columns", ["report_date", *self.thresholds])
        kwargs.setdefault("filters", [FinanceFactor.report_period == report_period])
        super().__init__(**kwargs)

    def compute_result(self) -> None:
        df = self.factor_df
        if df.empty:
            return
        cleared = pd.Series(True, index=df.index)
        for column, threshold in self.thresholds.items():
            cleared &= (df[column] >= threshold).fillna(False)
        streak = by_entity(cleared.astype(int)).transform(lambda s: s.rolling(self.count).sum())
        self.result_df = filter_result(streak == self.count, valid=streak.notna())
