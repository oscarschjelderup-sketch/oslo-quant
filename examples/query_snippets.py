"""What data is there, how is it recorded, how is it queried. Run `oq record --finance` first.

    python examples/query_snippets.py
"""

import pandas as pd

from osloquant.contract import context
from osloquant.domain import FinanceFactor, Future1dKdata, Stock, Stock1dAdjKdata

pd.set_option("display.width", 200, "display.max_columns", 20)

# every tradable entity type, and every schema (table)
print(context.tradable_schema_map)
print([schema.__name__ for schema in context.schemas])

# the stock list, indexed by code
print(Stock.query_data(index="code", columns=["code", "name", "sector"]).head())

# bars for one stock; adjusted for splits and dividends
print(Stock1dAdjKdata.query_data(code="EQNR", start_timestamp="2026-09-01", columns=["timestamp", "open", "close", "volume", "change_pct"]))

# the fields of a schema
FinanceFactor.help()

# market-wide selection in one query: the ten highest returns on equity in the latest annual reports,
# among companies that also grew their revenue
best = FinanceFactor.query_data(
    filters=[FinanceFactor.report_period == "year", FinanceFactor.roe > 0.15, FinanceFactor.revenue_growth_yoy > 0],
    start_timestamp="2026-01-01",
    order=FinanceFactor.roe.desc(),
    limit=10,
    columns=["code", "name", "report_date", "roe", "revenue_growth_yoy", "net_margin"],
    index="code",
)
print(best)

# anything Yahoo quotes can sit in the same store: Brent in dollars
print(Future1dKdata.query_data(code="BRENT", columns=["timestamp", "close"]).tail(3))
