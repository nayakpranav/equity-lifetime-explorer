"""Deterministic source decisions, independent of statement calculations.

This policy does not assert that a source was retrieved or validated. An issuer
identifier must be verified externally before a cross-listing route is allowed.
No fuzzy name matching, aggregator fallback, FX conversion or ADR conversion.
"""

from dataclasses import dataclass
import re

from ..models import CompanyMetadata


@dataclass(frozen=True)
class IssuerEvidence:
    listing: str
    issuer_id: str
    identifier_type: str
    evidence_url: str
    verified: bool = False
    framework: str | None = None
    share_basis_verified: bool = False


@dataclass(frozen=True)
class SourceDecision:
    route: str
    status: str
    reason: str
    issuer_id: str | None = None
    source_type: str | None = None
    retrieval_mode: str = "automatic"
    allow_eps: bool = False
    allow_price_overlay: bool = False


def decide_financial_source(
    metadata: CompanyMetadata, *, evidence: IssuerEvidence | None = None,
    reporting_currency: str | None = None,
) -> SourceDecision:
    """Return a plan; providers must subsequently confirm identity and facts."""
    ticker = metadata.ticker.upper().strip()
    if (metadata.security_type or metadata.quote_type or "").upper() in {
        "ETF", "FUND", "MUTUALFUND", "INDEX", "CURRENCY", "CRYPTOCURRENCY", "FUTURE", "OPTION",
    }:
        return SourceDecision("NONE", "UNSUPPORTED_SECURITY", "Issuer statements do not apply to this security type.")
    if evidence is not None:
        identifier_patterns = {
            "CIK": r"SEC:CIK[0-9]{10}",
            "LEI": r"LEI:[A-Z0-9]{20}",
            "CIN": r"CIN:[A-Z0-9]{21}",
            "ISIN": r"ISIN:[A-Z]{2}[A-Z0-9]{9}[0-9]",
        }
        identifier_pattern = identifier_patterns.get(evidence.identifier_type)
        if (not evidence.verified or evidence.listing.upper().strip() != ticker
                or not identifier_pattern or not re.fullmatch(identifier_pattern, evidence.issuer_id)
                or not evidence.evidence_url.startswith("https://")):
            return SourceDecision("NONE", "UNRESOLVED_ISSUER_IDENTITY", "Listing-to-issuer evidence has not been verified.")
        currencies_match = reporting_currency is not None and reporting_currency == metadata.currency
        overlay = evidence.share_basis_verified and currencies_match
        if evidence.identifier_type == "CIK" and evidence.framework in {"us-gaap", "ifrs-full"}:
            return SourceDecision(
                "SEC_US_GAAP" if evidence.framework == "us-gaap" else "SEC_IFRS",
                "IDENTIFIED", "SEC submissions and facts must confirm the reporting basis.",
                evidence.issuer_id, "PRIMARY_REGULATORY", allow_eps=evidence.share_basis_verified,
                allow_price_overlay=overlay,
            )
        if evidence.identifier_type == "LEI" and evidence.framework == "ifrs-full":
            return SourceDecision("ESEF", "IDENTIFIED", "Exact LEI filing discovery required.",
                                  evidence.issuer_id, "PRIMARY_REGULATORY",
                                  allow_eps=evidence.share_basis_verified, allow_price_overlay=overlay)
        if evidence.identifier_type in {"CIN", "ISIN"} and ticker.endswith((".NS", ".BO")):
            return SourceDecision("OFFICIAL_INDIA_IMPORT", "OFFICIAL_FILING_REQUIRED",
                                  "No terms-approved automated Indian source has been enabled.",
                                  evidence.issuer_id, "USER_SUPPLIED_OFFICIAL_FILING", "user_upload",
                                  evidence.share_basis_verified, overlay)
        return SourceDecision("NONE", "UNSUPPORTED_REPORTING_BASIS", "Verified identity lacks a compatible source route.", evidence.issuer_id)
    if ticker.endswith((".NS", ".BO")):
        return SourceDecision("OFFICIAL_INDIA_IMPORT", "OFFICIAL_FILING_REQUIRED",
                              "An official structured filing and exact issuer evidence are required.",
                              retrieval_mode="user_upload")
    # Single-letter suffixes retain Release A.1's exact SEC share-class handling.
    if "." not in ticker or len(ticker.rsplit(".", 1)[1]) == 1:
        return SourceDecision("SEC_DISCOVERY", "IDENTITY_REQUIRED",
                              "Resolve an exact SEC ticker and verified submissions; inspect taxonomy and forms.")
    return SourceDecision("NONE", "UNRESOLVED_ISSUER_IDENTITY",
                          "A verified CIK or LEI is required; company-name similarity is not identity evidence.")


def automated_source_permitted(provider: str) -> bool:
    """Conservative allowlist of documented public machine interfaces, not sites."""
    return provider in {"SEC_EDGAR", "FILINGS_XBRL_ORG"}
