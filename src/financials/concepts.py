"""Explicit pilot-issuer SEC tags; absence is a gap, never a fuzzy fallback."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConceptMapping:
    concept: str
    tag: str
    statement: str
    unit: str = "USD"
    context: str = "duration"
    sign: str = "as_reported"
    first_end: str | None = None
    last_end: str | None = None


PILOT_CIKS = {
    "MSFT": "0000789019",
    "KO": "0000021344",
    "AAPL": "0000320193",
    "NVDA": "0001045810",
}

# These are standard, entity-wide concepts present in the inspected Company Facts
# payloads. Revenue transitions are explicit; differing tags are never summed.
COMMON_MAPPINGS = (
    ConceptMapping("gross_profit", "GrossProfit", "income"),
    ConceptMapping("operating_income", "OperatingIncomeLoss", "income"),
    ConceptMapping("net_income_consolidated", "NetIncomeLoss", "income"),
    ConceptMapping("eps_diluted", "EarningsPerShareDiluted", "income", "USD/shares"),
    ConceptMapping("ocf", "NetCashProvidedByUsedInOperatingActivities", "cash_flow"),
    ConceptMapping("capex_ppe", "PaymentsToAcquirePropertyPlantAndEquipment", "cash_flow", sign="positive_outflow"),
    ConceptMapping("investing_cash_flow", "NetCashProvidedByUsedInInvestingActivities", "cash_flow"),
    ConceptMapping("financing_cash_flow", "NetCashProvidedByUsedInFinancingActivities", "cash_flow"),
    ConceptMapping("cash_equivalents", "CashAndCashEquivalentsAtCarryingValue", "balance_sheet", context="instant"),
    ConceptMapping("reported_long_term_debt", "LongTermDebt", "balance_sheet", context="instant"),
    ConceptMapping("assets", "Assets", "balance_sheet", context="instant"),
    ConceptMapping("liabilities", "Liabilities", "balance_sheet", context="instant"),
    ConceptMapping("shareholders_equity", "StockholdersEquity", "balance_sheet", context="instant"),
    ConceptMapping("current_assets", "AssetsCurrent", "balance_sheet", context="instant"),
    ConceptMapping("current_liabilities", "LiabilitiesCurrent", "balance_sheet", context="instant"),
)

REVENUE_MAPPINGS = {
    "MSFT": (
        ConceptMapping("revenue", "SalesRevenueNet", "income", last_end="2015-12-31"),
        ConceptMapping("revenue", "RevenueFromContractWithCustomerExcludingAssessedTax", "income", first_end="2016-01-01"),
    ),
    "KO": (ConceptMapping("revenue", "Revenues", "income"),),
    "AAPL": (
        ConceptMapping("revenue", "SalesRevenueNet", "income", last_end="2016-12-31"),
        ConceptMapping("revenue", "RevenueFromContractWithCustomerExcludingAssessedTax", "income", first_end="2017-01-01"),
    ),
    "NVDA": (ConceptMapping("revenue", "Revenues", "income"),),
}


def mappings_for(ticker: str, cik: str) -> tuple[ConceptMapping, ...]:
    if PILOT_CIKS.get(ticker) != cik:
        return ()
    return (*REVENUE_MAPPINGS[ticker], *COMMON_MAPPINGS)
