"""Provider-neutral analysis of one verified structured statement snapshot.

Never merges values across providers, currencies or disclosure vintages.
The existing accounting calculations are reused without alternative formulas.
"""

import pandas as pd

from ..financial_models import FundamentalsResult
from .analytics import build_period_table, calculate_fundamentals
from .capital_efficiency import calculate_capital_efficiency
from .eps import add_eps_growth
from .ifrs_concepts import IFRS_MAPPING_VERSION, ifrs_mappings
from .quality import financial_quality, statement_reconciliation
from .quarters import derive_standalone_quarters
from .vintages import select_latest_disclosed


def analyze_structured_snapshot(identity, observations, *, source, retrieved_at_utc,
                                source_sha256, financial_sector=False, diagnostics=None):
    if observations.empty:
        return FundamentalsResult(identity.ticker, "INSUFFICIENT_STRUCTURED_DATA",
            "Verified issuer report contains no compatible standard financial concepts.",
            identity=identity, source=source)
    # This API accepts exactly one document. Unknown disclosure dates are not
    # ordered using repository ingestion timestamps or invented filing dates.
    if observations.source_sha256.nunique() != 1 or observations.issuer_id.nunique() != 1:
        raise ValueError("A coherent single issuer/document snapshot is required")
    selected, decisions = select_latest_disclosed(observations)
    derived, quarter_issues = derive_standalone_quarters(selected)
    annual = build_period_table(selected, derived, frequency="annual")
    quarterly = build_period_table(selected, derived, frequency="quarterly")
    annual, ar = calculate_fundamentals(annual, financial_sector=financial_sector)
    quarterly, qr = calculate_fundamentals(quarterly, financial_sector=financial_sector)
    annual, ae = add_eps_growth(annual, observations, frequency="annual")
    quarterly, qe = add_eps_growth(quarterly, observations, frequency="quarterly")
    annual, cr = calculate_capital_efficiency(annual, financial_sector=financial_sector,
        accounting_framework=identity.accounting_framework)
    coverage = []
    for mapping in ifrs_mappings(identity.reporting_currency):
        for period_type in ("annual", "quarter", "ytd", "instant"):
            raw = observations.loc[observations.normalized_concept.eq(mapping.concept) & observations.period_type.eq(period_type)]
            valid = selected.loc[selected.normalized_concept.eq(mapping.concept) & selected.period_type.eq(period_type)]
            coverage.append(dict(concept=mapping.concept, period_type=period_type,
                mapped_observations=len(raw), valid_periods=valid.period_end.nunique(),
                first_period=valid.period_end.min() if len(valid) else None,
                last_period=valid.period_end.max() if len(valid) else None,
                source_tags=", ".join(sorted(valid.provider_concept.unique())),
                status="AVAILABLE" if len(valid) else "MISSING_INPUT"))
    quality = pd.concat([financial_quality(observations, decisions, quarter_issues),
        statement_reconciliation(annual), statement_reconciliation(quarterly),
        diagnostics if diagnostics is not None else pd.DataFrame()], ignore_index=True)
    latest = annual.iloc[-1] if len(annual) else None
    missing = [name for name in ("revenue", "operating_income", "net_income_parent", "ocf", "capex_ppe")
               if latest is None or pd.isna(latest.get(name))]
    status = "UNAVAILABLE" if annual.empty and quarterly.empty else "PARTIAL" if missing else "AVAILABLE"
    return FundamentalsResult(identity.ticker, status,
        "Latest annual period lacks: " + ", ".join(missing) if missing else "",
        identity=identity, source=source, observations=observations, annual=annual,
        quarterly=quarterly, ratios=pd.concat([ar, qr, ae, qe, cr], ignore_index=True),
        coverage=pd.DataFrame(coverage), quality=quality, retrieved_at_utc=retrieved_at_utc,
        source_sha256=source_sha256, mapping_version=IFRS_MAPPING_VERSION,
        latest_view="Latest repository report comparatives; disclosure timing unverified",
        metadata={"mapping_scope": "Exact standard IFRS concepts; issuer-specific audit not performed",
            "accounting_framework": identity.accounting_framework,
            "source_route": "ESEF", "financial_sector": financial_sector,
            "selection_decisions": decisions, "quarter_diagnostics": quarter_issues})
