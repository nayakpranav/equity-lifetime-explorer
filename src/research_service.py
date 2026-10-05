"""Financial analysis orchestrated separately from validated market calculations."""

from __future__ import annotations

import logging

import pandas as pd

from .financial_models import FundamentalsResult, ResearchResult
from .financials.analytics import build_period_table, calculate_fundamentals
from .financials.capital_efficiency import calculate_capital_efficiency
from .financials.concepts import AUDITED_CIKS, mappings_for, mapping_scope
from .financials.normalization import normalize_sec_facts
from .financials.eps import add_eps_growth
from .financials.quality import financial_coverage, financial_quality, statement_reconciliation
from .financials.quarters import derive_standalone_quarters
from .financials.vintages import select_latest_disclosed
from .models import AnalysisResult, CompanyMetadata
from .providers.sec import (
    SecConfigurationError, SecFinancialProvider, SecTransportError, UnsupportedSecIdentity, UnsupportedReportingBasis, MissingStructuredData,
)


LOGGER = logging.getLogger("equity_lifetime_explorer.financials")


def run_fundamentals_analysis(
    metadata: CompanyMetadata,
    *,
    force_refresh: bool = False,
    provider: SecFinancialProvider | None = None,
) -> FundamentalsResult:
    ticker = metadata.ticker.upper().strip()
    if metadata.security_type and metadata.security_type.upper() in {"ETF", "FUND", "INDEX", "CURRENCY", "CRYPTOCURRENCY"}:
        return FundamentalsResult(ticker, "UNSUPPORTED_SECURITY", "Corporate statements do not apply to this security type.")
    if "." in ticker and len(ticker.rsplit(".", 1)[1]) > 1:
        return FundamentalsResult(ticker, "NON_SEC_SOURCE", "This foreign listing requires a financial source outside the current SEC implementation.")
    try:
        source = provider or SecFinancialProvider()
        payload = source.fetch(metadata, force_refresh=force_refresh)
    except SecConfigurationError:
        return FundamentalsResult(ticker, "MISSING_SEC_IDENTITY", "SEC operator contact is not configured for this deployment.")
    except UnsupportedSecIdentity as exc:
        return FundamentalsResult(ticker, "UNRESOLVED_SEC_IDENTITY", str(exc))
    except UnsupportedReportingBasis as exc:
        return FundamentalsResult(ticker, "UNSUPPORTED_REPORTING_BASIS", str(exc))
    except MissingStructuredData as exc:
        return FundamentalsResult(ticker, "INSUFFICIENT_STRUCTURED_DATA", str(exc))
    except SecTransportError:
        LOGGER.exception("SEC financial retrieval failed for %s", ticker)
        return FundamentalsResult(ticker, "TRANSPORT_BLOCKED", "SEC financial data could not be retrieved at this time.")
    except Exception:
        LOGGER.exception("Unexpected SEC retrieval failure for %s", ticker)
        return FundamentalsResult(ticker, "FINANCIAL_ERROR", "Financial data processing is temporarily unavailable.")

    if ticker in AUDITED_CIKS and payload.identity.cik != AUDITED_CIKS[ticker]:
        return FundamentalsResult(ticker, "UNRESOLVED_SEC_IDENTITY", "SEC issuer mapping differs from the audited pilot identity.")
    try:
        observations = normalize_sec_facts(payload)
        if observations.empty:
            return FundamentalsResult(ticker, "MISSING_INPUT", "Verified SEC issuer, but no compatible mapped USD financial facts were available.", identity=payload.identity,
                coverage=financial_coverage(observations, observations, mappings_for(ticker, payload.identity.cik), source_facts=payload.facts, fiscal_year_end=payload.identity.fiscal_year_end),
                metadata={"mapping_scope": mapping_scope(payload.identity.cik)})
        selected, decisions = select_latest_disclosed(observations)
        derived, quarter_issues = derive_standalone_quarters(selected)
        annual = build_period_table(selected, derived, frequency="annual")
        quarterly = build_period_table(selected, derived, frequency="quarterly")
        sic = payload.identity.sic or ""
        is_financial = (metadata.sector or "").lower() in {"financial services", "banks", "insurance"} or (sic.isdigit() and 6000 <= int(sic) <= 6799)
        annual, annual_ratios = calculate_fundamentals(annual, financial_sector=is_financial)
        quarterly, quarter_ratios = calculate_fundamentals(quarterly, financial_sector=is_financial)
        annual, annual_eps_ratios = add_eps_growth(annual, observations, frequency="annual")
        quarterly, quarter_eps_ratios = add_eps_growth(quarterly, observations, frequency="quarterly")
        annual, capital_ratios = calculate_capital_efficiency(annual, financial_sector=is_financial)
        ratios = pd.concat(
            [annual_ratios, quarter_ratios, annual_eps_ratios, quarter_eps_ratios, capital_ratios],
            ignore_index=True,
        )
        mappings = mappings_for(ticker, payload.identity.cik)
        coverage = financial_coverage(
            observations, selected, mappings,
            source_facts=payload.facts, fiscal_year_end=payload.identity.fiscal_year_end,
        )
        quality = financial_quality(observations, decisions, quarter_issues)
        quality = pd.concat(
            [quality, statement_reconciliation(annual), statement_reconciliation(quarterly)],
            ignore_index=True,
        )
        latest = annual.iloc[-1] if not annual.empty else None
        required = ("revenue", "operating_income", "net_income_parent", "ocf", "capex_ppe")
        missing = [name for name in required if latest is None or name not in latest or pd.isna(latest[name])]
        status = "UNAVAILABLE" if annual.empty and quarterly.empty else "PARTIAL" if missing else "AVAILABLE"
        reason = (
            "Only verified quarterly observations are available." if annual.empty and not quarterly.empty else
            "No compatible annual or quarterly statement period was available." if annual.empty else
            "Latest annual period lacks: " + ", ".join(missing) if missing else ""
        )
        return FundamentalsResult(
            ticker=ticker, status=status, reason=reason, identity=payload.identity,
            observations=observations, annual=annual, quarterly=quarterly, ratios=ratios,
            coverage=coverage, quality=quality,
            retrieved_at_utc=payload.retrieved_at_utc, source_sha256=payload.source_sha256,
            metadata={
                "acceptance_ledger_entries": len(payload.accession_ledger),
                "older_submissions_loaded": payload.older_files_loaded,
                "older_submissions_available": payload.older_file_count,
                "selected_observations": len(selected),
                "derived_quarters": len(derived),
                "selection_decisions": decisions,
                "quarter_diagnostics": quarter_issues,
                "mapping_scope": mapping_scope(payload.identity.cik),
                "financial_sector": is_financial,
            },
        )
    except Exception:
        LOGGER.exception("SEC financial normalization failed for %s", ticker)
        return FundamentalsResult(ticker, "FINANCIAL_ERROR", "Financial facts could not be normalized safely.")


def compose_research(market: AnalysisResult, fundamentals: FundamentalsResult) -> ResearchResult:
    return ResearchResult(market=market, fundamentals=fundamentals)
