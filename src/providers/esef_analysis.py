"""Verified European listing crosswalk and bounded ESEF analysis integration."""

from ..financial_models import FundamentalsResult, SecurityIdentity
from ..financials.global_analysis import analyze_structured_snapshot
from ..financials.oim import normalize_esef_document
from .esef import EsefFinancialProvider, EsefSourceError


# Identity references, not concept/amount overrides. Additional exact LEI
# evidence can be supplied to the same adapter without adding a concept parser.
ESEF_LISTINGS = {
    "MC.PA": ("IOG4E947OATN0KJYSD45", "LVMH", "EUR", "1231",
        "https://filings.xbrl.org/entity/IOG4E947OATN0KJYSD45"),
    "NOKIA.HE": ("549300A0JPRWG1KI7U06", "Nokia Corporation", "EUR", "1231",
        "https://www.nokia.com/newsroom/nokia-corporation-repurchase-of-own-shares-on-17052024/"),
    "ASML.AS": ("724500Y6DUVHQD6OXN27", "ASML Holding N.V.", "EUR", "1231",
        "https://api.gleif.org/api/v1/lei-records/724500Y6DUVHQD6OXN27"),
}


def run_esef_analysis(metadata, *, force_refresh=False, provider=None):
    ticker = metadata.ticker.upper().strip()
    if ticker not in ESEF_LISTINGS:
        return FundamentalsResult(ticker, "UNRESOLVED_ISSUER_IDENTITY", "Verified listing-to-LEI evidence is required.")
    lei, name, currency, year_end, evidence = ESEF_LISTINGS[ticker]
    identity = SecurityIdentity(ticker, "", name, "LEI:" + lei, "LEI:" + lei + ":" + ticker,
        metadata.exchange, currency, year_end, identity_method="verified_lei_listing",
        accounting_framework="IFRS", identity_evidence_url=evidence, share_basis_verified=False)
    try:
        source = provider or EsefFinancialProvider()
        filings = source.filings(lei, force_refresh=force_refresh)
        if not filings:
            return FundamentalsResult(ticker, "INSUFFICIENT_STRUCTURED_DATA", "No structured repository filing is available.", identity=identity, source="ESEF · IFRS")
        # Keep one coherent latest repository document and its reported
        # comparatives. Do not fill gaps from older unverified disclosure dates.
        document = source.fetch_document(lei, filings[-1], force_refresh=force_refresh)
        rows, diagnostics = normalize_esef_document(document, ticker=ticker,
            currency=currency, fiscal_year_end=year_end)
        return analyze_structured_snapshot(identity, rows, source="ESEF · IFRS · filings.xbrl.org",
            retrieved_at_utc=document.retrieved_at_utc, source_sha256=document.source_sha256,
            financial_sector=(metadata.sector or "").lower() in {"financial services", "banks", "insurance"},
            diagnostics=diagnostics)
    except EsefSourceError:
        return FundamentalsResult(ticker, "TRANSPORT_BLOCKED", "The ESEF source is unavailable or its report failed validation.", identity=identity, source="ESEF · IFRS")
    except (ValueError, TypeError, KeyError):
        return FundamentalsResult(ticker, "FINANCIAL_ERROR", "The structured ESEF document could not be normalized safely.", identity=identity, source="ESEF · IFRS")
