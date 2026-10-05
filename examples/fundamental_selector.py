"""Selecting without backtesting: which stocks pass several factors today?

    python examples/fundamental_selector.py

Good companies (return on equity of 10 % or more, growing revenue, profits backed by cash, two years running)
that are also in an uptrend.
"""

import pandas as pd

from osloquant.domain import Stock, Stock1dAdjKdata
from osloquant.factors import AboveMaFactor, GoodCompanyFactor, TargetSelector

latest = Stock1dAdjKdata.query_data(columns=["timestamp"], order=Stock1dAdjKdata.timestamp.desc(), limit=1)["timestamp"].iloc[0]

quality = GoodCompanyFactor(end_timestamp=latest)
trend = AboveMaFactor(window=200, start_timestamp=latest - pd.DateOffset(years=2), end_timestamp=latest)
selector = TargetSelector(factors=[quality, trend])

names = Stock.query_data(index="entity_id", columns=["entity_id", "code", "name", "sector"])
print(f"Good companies on {latest:%Y-%m-%d}: {len(quality.get_targets(latest))}")
print(f"Above their 200-day average:      {len(trend.get_targets(latest))}")
print("Both:")
print(names.loc[selector.get_open_long_targets(latest), ["code", "name", "sector"]].to_string(index=False))
