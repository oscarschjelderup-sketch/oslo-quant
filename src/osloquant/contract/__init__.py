"""The contract: what a schema, a recorder and a factor are, independent of any market or data provider."""

from enum import Enum, StrEnum


class IntervalLevel(StrEnum):
    """Bar size: daily bars for research and backtests, 15-minute bars for the intraday paper accounts."""

    LEVEL_1DAY = "1d"
    LEVEL_15MIN = "15m"

    def to_timedelta(self):
        import pandas as pd

        return {IntervalLevel.LEVEL_1DAY: pd.Timedelta(days=1), IntervalLevel.LEVEL_15MIN: pd.Timedelta(minutes=15)}[self]

    @property
    def intraday(self) -> bool:
        return self != IntervalLevel.LEVEL_1DAY


class AdjustType(StrEnum):
    #: prices as quoted (Yahoo still restates them for splits)
    raw = "raw"
    #: restated for splits and dividends, so that close-to-close changes are total returns
    adj = "adj"


class TargetType(Enum):
    positive = "positive"
    negative = "negative"


from osloquant.contract.context import context  # noqa: E402
from osloquant.contract.schema import EntityRef, Mixin, TradableEntity  # noqa: E402

__all__ = ["AdjustType", "EntityRef", "IntervalLevel", "Mixin", "TargetType", "TradableEntity", "context"]
