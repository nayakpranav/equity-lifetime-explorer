"""Presentation values shared by the live and exported fundamentals views."""

from __future__ import annotations

from .financial_models import FundamentalsResult
from .formatting import format_money
from .ui import KpiCard


def fundamentals_kpi_cards(result: FundamentalsResult) -> list[KpiCard]:
    latest = result.annual.iloc[-1] if not result.annual.empty else None
    currency = result.identity.reporting_currency if result.identity else "USD"
    year = f"FY{int(latest['fiscal_year'])}" if latest is not None else "FY unavailable"

    def money(concept: str) -> str:
        return format_money(latest.get(concept), currency, compact=True) if latest is not None else "Not available"

    return [
        KpiCard(f"Revenue · {year}", money("revenue"), "blue"),
        KpiCard(f"Operating income · {year}", money("operating_income"), "blue"),
        KpiCard(f"Consolidated net income · {year}", money("net_income_consolidated"), "violet"),
        KpiCard(f"Operating cash flow · {year}", money("ocf"), "blue"),
        KpiCard(f"Free cash flow · {year}", money("fcf"), "green"),
        KpiCard(f"Net debt · {year}", money("net_debt"), "violet"),
    ]
