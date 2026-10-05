"""A formal strategy: the factors pick the targets, the trader does the rest.

    python examples/ma_trader.py

Hold a stock while its 20-day average is above its 60-day average and the close is above the 200-day one.
"""

from osloquant.factors import AboveMaFactor, CrossMaFactor
from osloquant.trader import StockTrader


class SlowMaTrader(StockTrader):
    def init_factors(self, entity_ids, entity_schema, start_timestamp, end_timestamp, adjust_type=None, provider=None):
        common = {"entity_ids": entity_ids, "start_timestamp": start_timestamp, "end_timestamp": end_timestamp}
        # with factor_mode="and" (the default) a stock is bought when both agree and sold when either turns
        return [CrossMaFactor(windows=(20, 60), **common), AboveMaFactor(window=200, **common)]


if __name__ == "__main__":
    trader = SlowMaTrader(start_timestamp="2015-01-01", end_timestamp="2026-10-02", trader_name="slow_ma", max_positions=10).run()
    for key, value in trader.stats().items():
        print(f"{key:28}{value}")
    # trader.draw(show=True) opens the account curve; `oq ui` shows it next to the other runs
