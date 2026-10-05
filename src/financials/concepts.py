"""Explicit standard concepts and audited issuer overrides; no fuzzy matching."""

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
    priority: int = 0
    basis: str = "standard"


AUDITED_CIKS = {
    "MSFT": "0000789019",
    "KO": "0000021344",
    "AAPL": "0000320193",
    "NVDA": "0001045810",
}

# Backwards-compatible name for the regression matrix, never an eligibility gate.
PILOT_CIKS = AUDITED_CIKS

# These are standard, entity-wide concepts present in the inspected Company Facts
# payloads. Revenue transitions are explicit; differing tags are never summed.
COMMON_MAPPINGS = (
    ConceptMapping("gross_profit", "GrossProfit", "income"),
    ConceptMapping("operating_income", "OperatingIncomeLoss", "income"),
    # The SEC taxonomy labels NetIncomeLoss as attributable to the parent.
    # It must not be described as consolidated profit including non-controlling interests.
    ConceptMapping("net_income_parent", "NetIncomeLoss", "income"),
    ConceptMapping("eps_basic", "EarningsPerShareBasic", "income", "USD/shares"),
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


GENERAL_REVENUE = (
    ConceptMapping("revenue", "RevenueFromContractWithCustomerExcludingAssessedTax", "income", priority=0, basis="net_revenue"),
    ConceptMapping("revenue", "SalesRevenueNet", "income", priority=1, basis="net_revenue"),
    ConceptMapping("revenue", "Revenues", "income", priority=2, basis="reported_revenue"),
    ConceptMapping("revenue", "RevenueFromContractWithCustomerIncludingAssessedTax", "income", priority=3, basis="revenue_including_assessed_tax"),
)

# Components retain their definitions. They are never summed into an assumed
# complete debt total or substituted for parent equity / parent net income.
DEBT_COMPONENTS = (
    ConceptMapping("long_term_debt_noncurrent", "LongTermDebtNoncurrent", "balance_sheet", context="instant"),
    ConceptMapping("long_term_debt_current", "LongTermDebtCurrent", "balance_sheet", context="instant"),
    ConceptMapping("short_term_borrowings", "ShortTermBorrowings", "balance_sheet", context="instant"),
    ConceptMapping("commercial_paper", "CommercialPaper", "balance_sheet", context="instant"),
)


def audited_issuer(cik: str) -> str | None:
    return next((ticker for ticker, value in AUDITED_CIKS.items() if value == cik), None)


def mapping_scope(cik: str) -> str:
    return "Audited issuer override" if audited_issuer(cik) else "General standard-concept mapping; issuer-specific audit not performed"


def mappings_for(ticker: str, cik: str) -> tuple[ConceptMapping, ...]:
    del ticker  # Accounting mappings belong to the verified issuer, not a share class.
    issuer = audited_issuer(cik)
    if issuer is None:
        return (*GENERAL_REVENUE, *COMMON_MAPPINGS, *DEBT_COMPONENTS)
    if issuer == "NVDA":
        # A broader reported productive-asset cash payment, separately named.
        # It includes software/intangibles and is NOT silently substituted for PPE CapEx.
        productive = (ConceptMapping(
            "productive_asset_spending", "PaymentsToAcquireProductiveAssets",
            "cash_flow", sign="positive_outflow", first_end="2019-01-01",
        ),)
    else:
        productive = ()
    return (*REVENUE_MAPPINGS[issuer], *COMMON_MAPPINGS, *productive)
