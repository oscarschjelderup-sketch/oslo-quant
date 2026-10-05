"""Financial statements from Yahoo, and the ratios computed from them.

Yahoo gives about four annual and five quarterly reports per company, and not the day each was published.
The publication day is therefore assumed: period end plus ``PUBLICATION_LAG``. That is deliberately late.
Being a few weeks slow costs a backtest little; knowing a result before the market did makes it worthless.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from osloquant.contract.api import get_data, to_pd_timestamp
from osloquant.contract.recorder import RecordSummary, TimeSeriesRecorder
from osloquant.contract.schema import EntityRef
from osloquant.contract.storage import df_to_db
from osloquant.domain.fundamental import BalanceSheet, CashFlowStatement, FinanceFactor, IncomeStatement
from osloquant.domain.meta import Stock
from osloquant.recorders.yahoo import client

#: days from period end until the report is treated as public
PUBLICATION_LAG = {"year": 90, "quarter": 60}

#: a company cannot have a new report this soon after its last period end, so it is not asked again
MIN_DAYS_BETWEEN_REPORTS = 80

# our column -> Yahoo line items, first one present wins
INCOME_ITEMS = {
    "total_revenue": ["Total Revenue", "Operating Revenue"],
    "cost_of_revenue": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "ebit": ["EBIT"],
    "interest_expense": ["Interest Expense"],
    "pretax_income": ["Pretax Income"],
    "tax_provision": ["Tax Provision"],
    "net_income": ["Net Income Common Stockholders", "Net Income"],
    "basic_eps": ["Basic EPS"],
    "diluted_eps": ["Diluted EPS"],
    "diluted_shares": ["Diluted Average Shares"],
}
BALANCE_ITEMS = {
    "total_assets": ["Total Assets"],
    "current_assets": ["Current Assets"],
    "cash_and_equivalents": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "goodwill_and_intangibles": ["Goodwill And Other Intangible Assets"],
    "total_liabilities": ["Total Liabilities Net Minority Interest"],
    "current_liabilities": ["Current Liabilities"],
    "total_debt": ["Total Debt"],
    "net_debt": ["Net Debt"],
    "total_equity": ["Stockholders Equity", "Common Stock Equity"],
    "minority_interest": ["Minority Interest"],
    "shares_outstanding": ["Ordinary Shares Number", "Share Issued"],
}
CASHFLOW_ITEMS = {
    "operating_cash_flow": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capital_expenditure": ["Capital Expenditure"],
    "free_cash_flow": ["Free Cash Flow"],
    "dividends_paid": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "repurchase_of_stock": ["Repurchase Of Capital Stock"],
    "depreciation_and_amortization": ["Depreciation And Amortization", "Depreciation Amortization Depletion"],
}


def statement_to_rows(raw: pd.DataFrame, items: dict[str, list[str]], period: str) -> pd.DataFrame:
    """Yahoo's layout (line items down, period ends across) -> one row per report."""
    columns = ["report_date", "report_period", "timestamp", *items]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=columns)
    out = pd.DataFrame({"report_date": pd.to_datetime(list(raw.columns))})
    for column, candidates in items.items():
        values = np.full(len(out), np.nan)
        for candidate in candidates:
            if candidate in raw.index:
                found = pd.to_numeric(raw.loc[candidate], errors="coerce").to_numpy(dtype=float)
                values = np.where(np.isnan(values), found, values)
        out[column] = values
    out = out.dropna(subset=list(items), how="all")
    out["report_period"] = period
    out["timestamp"] = out["report_date"] + pd.Timedelta(days=PUBLICATION_LAG[period])
    return out[columns].sort_values("report_date").reset_index(drop=True)


def _year_earlier(df: pd.DataFrame, column: str) -> pd.Series:
    """The value of ``column`` in the report one year before each row, NaN when there is none."""
    left = pd.DataFrame({"when": df["report_date"] - pd.DateOffset(years=1), "pos": np.arange(len(df))}).sort_values("when")
    right = df[["report_date", column]].rename(columns={"report_date": "when", column: "prev"}).sort_values("when")
    merged = pd.merge_asof(left, right, on="when", direction="nearest", tolerance=pd.Timedelta(days=20))
    return merged.sort_values("pos")["prev"].reset_index(drop=True)


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """A ratio that is NaN rather than infinite or sign-flipped when the denominator is not positive."""
    return numerator / denominator.where(denominator > 0)


def compute_finance_factors(income: pd.DataFrame, balance: pd.DataFrame, cashflow: pd.DataFrame) -> pd.DataFrame:
    """Ratios per report, from statement rows as :func:`statement_to_rows` returns them."""
    frames = []
    for period in ("year", "quarter"):
        inc = income[income["report_period"] == period]
        if inc.empty:
            continue
        keep_balance = ["report_date", "total_assets", "total_liabilities", "total_equity"]
        keep_cashflow = ["report_date", "operating_cash_flow", "free_cash_flow"]
        df = inc.merge(balance.loc[balance["report_period"] == period, keep_balance], on="report_date", how="left")
        df = df.merge(cashflow.loc[cashflow["report_period"] == period, keep_cashflow], on="report_date", how="left")
        df = df.sort_values("report_date").reset_index(drop=True)

        revenue, profit = df["total_revenue"], df["net_income"]
        previous_revenue, previous_profit = _year_earlier(df, "total_revenue"), _year_earlier(df, "net_income")

        # the balance one period back: last year's for annual reports, last quarter's for quarterly ones
        gap = df["report_date"].diff().dt.days
        max_gap = 380 if period == "year" else 100
        contiguous = gap <= max_gap
        opening_equity = df["total_equity"].shift(1).where(contiguous)
        opening_assets = df["total_assets"].shift(1).where(contiguous)
        average_equity = pd.concat([df["total_equity"], opening_equity], axis=1).mean(axis=1)
        average_assets = pd.concat([df["total_assets"], opening_assets], axis=1).mean(axis=1)
        annualise = 1.0 if period == "year" else 4.0

        frames.append(
            pd.DataFrame(
                {
                    "report_date": df["report_date"],
                    "report_period": period,
                    "timestamp": df["timestamp"],
                    "basic_eps": df["basic_eps"],
                    "total_revenue": revenue,
                    "net_profit": profit,
                    "revenue_growth_yoy": _ratio(revenue, previous_revenue) - 1,
                    "net_profit_growth_yoy": (profit - previous_profit) / previous_profit.abs().where(previous_profit != 0),
                    "roe": annualise * _ratio(profit, average_equity),
                    "rota": annualise * _ratio(profit, average_assets),
                    "gross_profit_margin": _ratio(df["gross_profit"], revenue),
                    "operating_margin": _ratio(df["operating_income"], revenue),
                    "net_margin": _ratio(profit, revenue),
                    "debt_asset_ratio": _ratio(df["total_liabilities"], df["total_assets"]),
                    "cash_conversion": _ratio(df["operating_cash_flow"], profit),
                    "fcf_margin": _ratio(df["free_cash_flow"], revenue),
                }
            )
        )
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_statement_rows(symbol: str, kind: str) -> pd.DataFrame:
    items = {"income": INCOME_ITEMS, "balance": BALANCE_ITEMS, "cashflow": CASHFLOW_ITEMS}[kind]
    parts = [statement_to_rows(client.fetch_statement(symbol, kind, period), items, period) for period in ("year", "quarter")]
    parts = [p for p in parts if not p.empty]
    return pd.concat(parts, ignore_index=True) if parts else statement_to_rows(pd.DataFrame(), items, "year")


class YahooReportRecorder(TimeSeriesRecorder):
    """Shared by the statement and ratio recorders: whole reports are fetched and upserted."""

    provider = "yahoo"
    entity_schema = Stock

    def __init__(self, sleeping_time: float = 0.3, **kwargs) -> None:
        super().__init__(sleeping_time=sleeping_time, **kwargs)

    def fetch_rows(self, entity: EntityRef) -> pd.DataFrame:
        raise NotImplementedError

    def generate_report_id(self, entity: EntityRef, period: str, report_date: pd.Timestamp) -> str:
        return f"{entity.id}_{period}_{report_date.strftime('%Y-%m-%d')}"

    def is_fresh(self, entity: EntityRef) -> bool:
        saved = get_data(
            self.data_schema,
            provider=self.provider,
            entity_id=entity.id,
            columns=["report_date"],
            order=self.data_schema.report_date.desc(),
            limit=1,
        )
        if saved.empty:
            return False
        age = pd.Timestamp.now().normalize() - to_pd_timestamp(saved["report_date"].iloc[0])
        return age.days < MIN_DAYS_BETWEEN_REPORTS

    def record_entity(self, entity: EntityRef, summary: RecordSummary) -> int:
        if not self.force_update and self.is_fresh(entity):
            return 0
        df = self.fetch_rows(entity)
        if df is None or df.empty:
            return 0
        df = self.finalize(entity, df)
        df["id"] = [self.generate_report_id(entity, p, d) for p, d in zip(df["report_period"], df["report_date"], strict=True)]
        return df_to_db(df, self.data_schema, self.provider, force_update=True)


class YahooIncomeStatementRecorder(YahooReportRecorder):
    data_schema = IncomeStatement

    def fetch_rows(self, entity: EntityRef) -> pd.DataFrame:
        return fetch_statement_rows(entity.symbol, "income")


class YahooBalanceSheetRecorder(YahooReportRecorder):
    data_schema = BalanceSheet

    def fetch_rows(self, entity: EntityRef) -> pd.DataFrame:
        return fetch_statement_rows(entity.symbol, "balance")


class YahooCashFlowStatementRecorder(YahooReportRecorder):
    data_schema = CashFlowStatement

    def fetch_rows(self, entity: EntityRef) -> pd.DataFrame:
        return fetch_statement_rows(entity.symbol, "cashflow")


class YahooFinanceFactorRecorder(YahooReportRecorder):
    data_schema = FinanceFactor

    def fetch_rows(self, entity: EntityRef) -> pd.DataFrame:
        return compute_finance_factors(
            fetch_statement_rows(entity.symbol, "income"),
            fetch_statement_rows(entity.symbol, "balance"),
            fetch_statement_rows(entity.symbol, "cashflow"),
        )
