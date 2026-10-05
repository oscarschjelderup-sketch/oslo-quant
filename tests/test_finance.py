"""Statements in Yahoo's layout -> report rows -> ratios."""

import numpy as np
import pandas as pd
import pytest

from osloquant.domain import FinanceFactor, IncomeStatement
from osloquant.recorders.yahoo import client
from osloquant.recorders.yahoo.finance_recorder import (
    BALANCE_ITEMS,
    CASHFLOW_ITEMS,
    INCOME_ITEMS,
    PUBLICATION_LAG,
    compute_finance_factors,
    statement_to_rows,
)
from tests.helpers import store_stocks

YEARS = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31"])  # newest first, as Yahoo gives them
QUARTERS = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"])


def yahoo_frame(columns, items: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(items, index=columns).T


INCOME_YEAR = yahoo_frame(
    YEARS,
    {
        "Total Revenue": [1210.0, 1100.0, 1000.0],
        "Gross Profit": [605.0, 440.0, 400.0],
        "Operating Income": [242.0, 165.0, 150.0],
        "Net Income Common Stockholders": [150.0, 100.0, -50.0],
        "Net Income": [999.0, 999.0, 999.0],  # the first candidate must win
        "Basic EPS": [1.5, 1.0, -0.5],
    },
)
BALANCE_YEAR = yahoo_frame(
    YEARS,
    {
        "Total Assets": [2200.0, 2000.0, 1800.0],
        "Total Liabilities Net Minority Interest": [1100.0, 1200.0, 1000.0],
        "Stockholders Equity": [1100.0, 900.0, 800.0],
    },
)
CASHFLOW_YEAR = yahoo_frame(YEARS, {"Operating Cash Flow": [180.0, 90.0, 10.0], "Free Cash Flow": [121.0, 55.0, -20.0]})
INCOME_QUARTER = yahoo_frame(
    QUARTERS,
    {"Total Revenue": [330.0, 300.0, 310.0, 290.0, 300.0], "Net Income Common Stockholders": [44.0, 30.0, 40.0, 35.0, 40.0]},
)
BALANCE_QUARTER = yahoo_frame(QUARTERS, {"Total Assets": [2300.0] * 5, "Stockholders Equity": [1200.0, 1000.0, 1100.0, 1050.0, 1000.0]})


def rows(year, quarter, items):
    parts = [statement_to_rows(year, items, "year"), statement_to_rows(quarter, items, "quarter")]
    return pd.concat([p for p in parts if not p.empty], ignore_index=True)


def at(df: pd.DataFrame, date: str) -> pd.Series:
    return df.loc[pd.Timestamp(date)]


@pytest.fixture
def factors() -> pd.DataFrame:
    return compute_finance_factors(
        rows(INCOME_YEAR, INCOME_QUARTER, INCOME_ITEMS),
        rows(BALANCE_YEAR, BALANCE_QUARTER, BALANCE_ITEMS),
        rows(CASHFLOW_YEAR, pd.DataFrame(), CASHFLOW_ITEMS),
    )


def test_statement_rows_are_oldest_first_with_a_late_publication_date():
    out = statement_to_rows(INCOME_YEAR, INCOME_ITEMS, "year")
    assert out["report_date"].tolist() == sorted(YEARS)
    assert out["net_income"].tolist() == [-50.0, 100.0, 150.0]
    assert (out["timestamp"] - out["report_date"]).dt.days.unique().tolist() == [PUBLICATION_LAG["year"]]
    assert out["cost_of_revenue"].isna().all()  # a line Yahoo did not give is missing, not zero


def test_an_empty_statement_gives_no_rows():
    assert statement_to_rows(pd.DataFrame(), INCOME_ITEMS, "year").empty
    assert statement_to_rows(None, INCOME_ITEMS, "quarter").empty


def test_annual_ratios(factors):
    year = factors[factors["report_period"] == "year"].set_index("report_date")
    latest, first = at(year, "2025-12-31"), at(year, "2023-12-31")

    assert latest["revenue_growth_yoy"] == pytest.approx(0.10)
    assert latest["net_profit_growth_yoy"] == pytest.approx(0.50)
    assert latest["roe"] == pytest.approx(150 / 1000)  # on the average of opening and closing equity
    assert latest["rota"] == pytest.approx(150 / 2100)
    assert latest["gross_profit_margin"] == pytest.approx(0.5)
    assert latest["operating_margin"] == pytest.approx(0.2)
    assert latest["net_margin"] == pytest.approx(150 / 1210)
    assert latest["debt_asset_ratio"] == pytest.approx(0.5)
    assert latest["cash_conversion"] == pytest.approx(1.2)
    assert latest["fcf_margin"] == pytest.approx(0.1)

    # the first report has nothing to grow from, and its return is on closing equity
    assert np.isnan(first["revenue_growth_yoy"]) and np.isnan(first["net_profit_growth_yoy"])
    assert first["roe"] == pytest.approx(-50 / 800)


def test_growth_from_a_loss_is_measured_against_its_size_not_its_sign(factors):
    year = factors[factors["report_period"] == "year"].set_index("report_date")
    # from -50 to +100 is an improvement of 150 on a base of 50: +300 %, not -300 %
    assert at(year, "2024-12-31")["net_profit_growth_yoy"] == pytest.approx(3.0)
    # cash conversion against a loss would be a meaningless sign flip
    assert np.isnan(at(year, "2023-12-31")["cash_conversion"])


def test_quarterly_ratios_compare_with_the_same_quarter_last_year_and_are_annualised(factors):
    quarter = factors[factors["report_period"] == "quarter"].set_index("report_date")
    latest = at(quarter, "2026-06-30")

    assert latest["revenue_growth_yoy"] == pytest.approx(0.10)  # against 2025-06-30, not the previous quarter
    assert latest["net_profit_growth_yoy"] == pytest.approx(0.10)
    assert latest["roe"] == pytest.approx(4 * 44 / 1100)
    assert np.isnan(at(quarter, "2026-03-31")["revenue_growth_yoy"])  # no quarter a year earlier
    assert (quarter["timestamp"] - quarter.index).dt.days.unique().tolist() == [PUBLICATION_LAG["quarter"]]


def test_the_recorders_store_reports_with_one_row_per_period_and_date(monkeypatch):
    statements = {
        ("income", "year"): INCOME_YEAR,
        ("income", "quarter"): INCOME_QUARTER,
        ("balance", "year"): BALANCE_YEAR,
        ("balance", "quarter"): BALANCE_QUARTER,
        ("cashflow", "year"): CASHFLOW_YEAR,
        ("cashflow", "quarter"): pd.DataFrame(),
    }
    calls = []

    def fetch_statement(symbol, kind, period):
        calls.append((symbol, kind, period))
        return statements[(kind, period)]

    monkeypatch.setattr(client, "fetch_statement", fetch_statement)
    store_stocks(["AAA"])

    assert FinanceFactor.record_data(sleeping_time=0, force_update=True).rows == 8
    assert IncomeStatement.record_data(sleeping_time=0, force_update=True).rows == 8

    stored = FinanceFactor.query_data(code="AAA")
    assert stored["id"].is_unique and "stock_ol_AAA_year_2025-12-31" in stored["id"].tolist()
    # year end has both an annual and a quarterly row
    assert sorted(stored.loc[stored["report_date"] == "2025-12-31", "report_period"]) == ["quarter", "year"]
    best = FinanceFactor.query_data(filters=[FinanceFactor.report_period == "year", FinanceFactor.roe > 0.1], columns=["code", "roe"])
    assert len(best) == 2

    # the newest report is far in the past relative to today, so a normal run asks Yahoo again
    calls.clear()
    FinanceFactor.record_data(sleeping_time=0)
    assert calls
