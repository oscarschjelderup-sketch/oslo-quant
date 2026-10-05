"""Sample strategies. They show how little a strategy is once the framework holds the data and the account.

None of them is a recommendation. They are the textbook rules, there to be measured and argued with.
"""

from __future__ import annotations

from osloquant.factors import AboveMaFactor, CrossMaFactor, GoldCrossFactor, MomentumFactor
from osloquant.trader.trader import StockTrader


class MaTrader(StockTrader):
    """Hold a stock while its 5-day average is above its 10-day average."""

    windows = (5, 10)

    def init_factors(self, entity_ids, entity_schema, start_timestamp, end_timestamp, adjust_type=None, provider=None):
        return [
            CrossMaFactor(
                windows=self.windows,
                entity_schema=entity_schema,
                entity_ids=entity_ids,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                adjust_type=adjust_type,
                provider=provider,
            )
        ]


class MacdTrader(StockTrader):
    """Hold a stock between MACD's golden cross and its dead cross."""

    def init_factors(self, entity_ids, entity_schema, start_timestamp, end_timestamp, adjust_type=None, provider=None):
        return [
            GoldCrossFactor(
                entity_schema=entity_schema,
                entity_ids=entity_ids,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                adjust_type=adjust_type,
                provider=provider,
            )
        ]


class TrendTrader(StockTrader):
    """Hold a stock while it trades above its 200-day average.

    Usually more stocks qualify than there are slots. The ones furthest above their average come first;
    without a rule here the slots would go to whatever sorts first in the alphabet.
    """

    window = 200

    def rank_targets(self, timestamp, entity_ids):
        if not hasattr(self, "_strength"):
            df = self.factors[0].factor_df
            self._strength = (df["close"] / df[f"ma{self.window}"] - 1).unstack("entity_id")
        strength = self._strength.loc[timestamp] if timestamp in self._strength.index else {}
        return sorted(entity_ids, key=lambda e: (-strength.get(e, float("-inf")), e))

    def init_factors(self, entity_ids, entity_schema, start_timestamp, end_timestamp, adjust_type=None, provider=None):
        return [
            AboveMaFactor(
                window=self.window,
                entity_schema=entity_schema,
                entity_ids=entity_ids,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                adjust_type=adjust_type,
                provider=provider,
            )
        ]


class MomentumTrader(StockTrader):
    """Once a month, hold the stocks with the best 12-1 month return, as long as they are in an uptrend.

    Two factors, combined with "and": the momentum rank picks the winners, the 200-day average keeps the
    trader out of winners that have already rolled over.
    """

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("rebalance", "monthly")
        kwargs.setdefault("profit_threshold", None)
        kwargs.setdefault("pre_load_days", 500)
        super().__init__(*args, **kwargs)

    def init_factors(self, entity_ids, entity_schema, start_timestamp, end_timestamp, adjust_type=None, provider=None):
        common = {
            "entity_schema": entity_schema,
            "entity_ids": entity_ids,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "adjust_type": adjust_type,
            "provider": provider,
        }
        return [MomentumFactor(**common), AboveMaFactor(window=200, **common)]


SAMPLE_TRADERS = {
    "ma": MaTrader,
    "macd": MacdTrader,
    "trend": TrendTrader,
    "momentum": MomentumTrader,
}
