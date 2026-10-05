"""Every schema the framework knows. ``from osloquant.domain import *`` gives you all of them."""

# importing the recorders is what connects the schemas to their data providers
import osloquant.recorders  # noqa: E402, F401, I001
from osloquant.domain.actions import StockAction
from osloquant.domain.fundamental import BalanceSheet, CashFlowStatement, FinanceFactor, IncomeStatement
from osloquant.domain.meta import Currency, Future, Index, Stock
from osloquant.domain.quotes import Currency1dKdata, Future1dKdata, Index1dKdata, Stock1dAdjKdata, Stock1dKdata, Stock15mKdata

__all__ = [
    "BalanceSheet",
    "CashFlowStatement",
    "Currency",
    "Currency1dKdata",
    "FinanceFactor",
    "Future",
    "Future1dKdata",
    "IncomeStatement",
    "Index",
    "Index1dKdata",
    "Stock",
    "Stock1dAdjKdata",
    "StockAction",
    "Stock1dKdata",
    "Stock15mKdata",
]
