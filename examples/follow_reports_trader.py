"""A solo strategy: no factors, just your own reading of the events in ``on_time``.

    python examples/follow_reports_trader.py

"When the annual report comes out, I read it. If the company earned more than 15 % on its equity and its
profit grew, I buy. If a later report shows less than 8 %, I sell."

The only rule the framework cannot enforce for you here: on day t, use what was known on day t. That is why
the reports are filtered on ``timestamp`` (when a report is assumed public), not on ``report_date``.

Yahoo keeps about four annual reports per company, so this can only be run over the last few years. It
shows the mechanics; it is far too short to say anything about the idea.
"""

import pandas as pd

from osloquant.domain import FinanceFactor
from osloquant.trader import StockTrader


class FollowReportsTrader(StockTrader):
    def on_init(self) -> None:
        self.reports = FinanceFactor.query_data(
            filters=[FinanceFactor.report_period == "year"],
            columns=["entity_id", "timestamp", "roe", "net_profit_growth_yoy"],
        )
        self.seen = pd.Timestamp.min

    def on_time(self, timestamp: pd.Timestamp) -> None:
        new = self.reports[(self.reports["timestamp"] > self.seen) & (self.reports["timestamp"] <= timestamp)]
        self.seen = timestamp
        if new.empty:
            return
        good = new[(new["roe"] > 0.15) & (new["net_profit_growth_yoy"] > 0)]
        weak = new[new["roe"] < 0.08]
        self.trade_the_targets(
            happen_timestamp=timestamp,
            long_selected=set(good["entity_id"]),
            short_selected=set(weak["entity_id"]),
        )


if __name__ == "__main__":
    trader = FollowReportsTrader(
        start_timestamp="2023-01-01", end_timestamp="2026-10-02", trader_name="follow_reports", max_positions=15, profit_threshold=None
    ).run()
    for key, value in trader.stats().items():
        print(f"{key:28}{value}")
