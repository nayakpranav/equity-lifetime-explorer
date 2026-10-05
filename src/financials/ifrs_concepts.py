"""Separate IFRS registry. Exact taxonomy concepts, never inferred subtotals.

Currency is supplied by verified statement evidence, never by listing currency.
This registry requires provider/filing validation before production integration.
"""

import re

from .concepts import ConceptMapping


IFRS_MAPPING_VERSION = "ifrs-exact-2026-10-05"
IFRS_ANNUAL_FORMS = frozenset({"20-F", "20-F/A", "40-F", "40-F/A"})


def ifrs_mappings(currency: str) -> tuple[ConceptMapping, ...]:
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("A verified native reporting currency is required")
    specs = (
        ("revenue", "Revenue", "income", "duration", False),
        ("gross_profit", "GrossProfit", "income", "duration", False),
        ("operating_income", "ProfitLossFromOperatingActivities", "income", "duration", False),
        ("net_income_parent", "ProfitLossAttributableToOwnersOfParent", "income", "duration", False),
        ("eps_basic", "BasicEarningsLossPerShare", "income", "duration", False),
        ("eps_diluted", "DilutedEarningsLossPerShare", "income", "duration", False),
        ("ocf", "CashFlowsFromUsedInOperatingActivities", "cash_flow", "duration", False),
        ("capex_ppe", "PurchaseOfPropertyPlantAndEquipment", "cash_flow", "duration", True),
        ("cash_equivalents", "CashAndCashEquivalents", "balance_sheet", "instant", False),
        ("assets", "Assets", "balance_sheet", "instant", False),
        ("liabilities", "Liabilities", "balance_sheet", "instant", False),
        ("current_assets", "CurrentAssets", "balance_sheet", "instant", False),
        ("current_liabilities", "CurrentLiabilities", "balance_sheet", "instant", False),
        ("shareholders_equity", "EquityAttributableToOwnersOfParent", "balance_sheet", "instant", False),
    )
    return tuple(ConceptMapping(
        concept, tag, statement, currency + "/shares" if concept.startswith("eps_") else currency,
        context, "positive_outflow" if outflow else "as_reported", basis="ifrs_exact_standard",
    ) for concept, tag, statement, context, outflow in specs)
