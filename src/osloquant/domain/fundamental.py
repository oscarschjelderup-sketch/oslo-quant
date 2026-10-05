"""Fundamentals: the three statements and the ratios computed from them.

Two dates matter and they are not the same:

``report_date``  the period end the numbers describe (31 December, 30 June, ...)
``timestamp``    when the numbers are assumed to have been public

A backtest may only use a row from its ``timestamp`` on. Levels are in the company's reporting currency,
which is not always NOK (Equinor reports in USD, Mowi in EUR); ratios are unaffected.
"""

from sqlalchemy import Column, DateTime, Float, String
from sqlalchemy.orm import DeclarativeBase

from osloquant.contract.register import register_schema
from osloquant.contract.schema import Mixin


class FinanceBase(DeclarativeBase):
    pass


class ReportMixin(Mixin):
    provider = Column(String(32))
    code = Column(String(32), index=True)
    name = Column(String(128))
    #: "year" or "quarter"
    report_period = Column(String(16))
    report_date = Column(DateTime, index=True)


class IncomeStatement(FinanceBase, ReportMixin):
    __tablename__ = "income_statement"

    total_revenue = Column(Float)
    cost_of_revenue = Column(Float)
    gross_profit = Column(Float)
    operating_income = Column(Float)
    ebitda = Column(Float)
    ebit = Column(Float)
    interest_expense = Column(Float)
    pretax_income = Column(Float)
    tax_provision = Column(Float)
    #: attributable to the shareholders of the parent
    net_income = Column(Float)
    basic_eps = Column(Float)
    diluted_eps = Column(Float)
    diluted_shares = Column(Float)


class BalanceSheet(FinanceBase, ReportMixin):
    __tablename__ = "balance_sheet"

    total_assets = Column(Float)
    current_assets = Column(Float)
    cash_and_equivalents = Column(Float)
    goodwill_and_intangibles = Column(Float)
    total_liabilities = Column(Float)
    current_liabilities = Column(Float)
    total_debt = Column(Float)
    net_debt = Column(Float)
    #: equity attributable to the shareholders of the parent
    total_equity = Column(Float)
    minority_interest = Column(Float)
    shares_outstanding = Column(Float)


class CashFlowStatement(FinanceBase, ReportMixin):
    __tablename__ = "cash_flow_statement"

    operating_cash_flow = Column(Float)
    capital_expenditure = Column(Float)
    free_cash_flow = Column(Float)
    dividends_paid = Column(Float)
    repurchase_of_stock = Column(Float)
    depreciation_and_amortization = Column(Float)


class FinanceFactor(FinanceBase, ReportMixin):
    """Ratios per report. For quarter rows the returns on equity and assets are annualised (times four)."""

    __tablename__ = "finance_factor"

    basic_eps = Column(Float)
    total_revenue = Column(Float)
    net_profit = Column(Float)
    #: against the same period one year earlier
    revenue_growth_yoy = Column(Float)
    net_profit_growth_yoy = Column(Float)
    #: net profit over average equity (ending equity when the previous balance is missing)
    roe = Column(Float)
    #: net profit over average total assets
    rota = Column(Float)
    gross_profit_margin = Column(Float)
    operating_margin = Column(Float)
    net_margin = Column(Float)
    #: total liabilities over total assets
    debt_asset_ratio = Column(Float)
    #: operating cash flow over net profit
    cash_conversion = Column(Float)
    fcf_margin = Column(Float)

    @classmethod
    def important_cols(cls) -> list[str]:
        return [
            "basic_eps",
            "total_revenue",
            "net_profit",
            "revenue_growth_yoy",
            "net_profit_growth_yoy",
            "roe",
            "rota",
            "gross_profit_margin",
            "net_margin",
            "timestamp",
        ]


register_schema(providers=["yahoo"], db_name="finance", schema_base=FinanceBase)

__all__ = ["BalanceSheet", "CashFlowStatement", "FinanceFactor", "IncomeStatement"]
