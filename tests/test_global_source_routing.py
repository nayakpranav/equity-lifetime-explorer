"""Source-policy foundation; no live data or financial-engine changes."""

from dataclasses import replace

import pytest

from src.financials.source_routing import (
    IssuerEvidence, automated_source_permitted, decide_financial_source,
)
from src.financials.ifrs_concepts import ifrs_mappings


@pytest.mark.parametrize("ticker", ["MSFT", "MELI", "CAT", "JPM", "BRK.B", "UNSEEN"])
def test_sec_remains_dynamic(synthetic_result, ticker):
    meta = replace(synthetic_result.metadata, ticker=ticker)
    assert decide_financial_source(meta).route == "SEC_DISCOVERY"


@pytest.mark.parametrize("ticker", ["ITC.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ITC.BO"])
def test_india_requires_official_filing_not_scraping(synthetic_result, ticker):
    decision = decide_financial_source(replace(synthetic_result.metadata, ticker=ticker))
    assert decision.status == "OFFICIAL_FILING_REQUIRED"
    assert not decision.allow_eps and not decision.allow_price_overlay


def test_cross_listing_needs_exact_evidence_and_currency(synthetic_result):
    meta = replace(synthetic_result.metadata, ticker="SAP.DE", currency="EUR")
    assert decide_financial_source(meta).status == "UNRESOLVED_ISSUER_IDENTITY"
    evidence = IssuerEvidence("SAP.DE", "SEC:CIK0001000184", "CIK", "https://www.sec.gov/", True, "ifrs-full")
    decision = decide_financial_source(meta, evidence=evidence, reporting_currency="EUR")
    assert decision.route == "SEC_IFRS" and not decision.allow_eps
    verified = replace(evidence, share_basis_verified=True)
    assert decide_financial_source(meta, evidence=verified, reporting_currency="EUR").allow_price_overlay
    assert not decide_financial_source(meta, evidence=verified, reporting_currency="USD").allow_price_overlay
    assert decide_financial_source(meta, evidence=replace(verified, listing="SAP")).status == "UNRESOLVED_ISSUER_IDENTITY"
    assert decide_financial_source(meta, evidence=replace(verified, verified=False)).status == "UNRESOLVED_ISSUER_IDENTITY"


def test_exact_lei_route_and_security_exclusions(synthetic_result):
    meta = replace(synthetic_result.metadata, ticker="EXAMPLE.AS")
    evidence = IssuerEvidence(meta.ticker, "LEI:IOG4E947OATN0KJYSD45", "LEI", "https://filings.xbrl.org/", True, "ifrs-full")
    assert decide_financial_source(meta, evidence=evidence).route == "ESEF"
    assert decide_financial_source(replace(meta, security_type="ETF"), evidence=evidence).status == "UNSUPPORTED_SECURITY"
    assert decide_financial_source(meta, evidence=replace(evidence, issuer_id="LEI:invalid")).status == "UNRESOLVED_ISSUER_IDENTITY"


def test_terms_gate_has_no_aggregator_fallback():
    assert automated_source_permitted("SEC_EDGAR")
    assert automated_source_permitted("FILINGS_XBRL_ORG")
    for name in ("NSE_WEBSITE", "BSE_WEBSITE", "SCREENER", "MACROTRENDS", "FINVIZ", "YAHOO_FINANCIALS", "UNKNOWN"):
        assert not automated_source_permitted(name)


def test_ifrs_is_separate_native_currency_and_no_false_substitutes():
    mappings = ifrs_mappings("EUR")
    tags = {m.tag for m in mappings}
    assert "ProfitLossAttributableToOwnersOfParent" in tags
    assert "ProfitLoss" not in tags and "Equity" not in tags
    assert "PurchaseOfPropertyPlantAndEquipment" in tags
    assert not any("Investing" in tag for tag in tags)
    assert all(m.unit == ("EUR/shares" if m.concept.startswith("eps_") else "EUR") for m in mappings)
    with pytest.raises(ValueError):
        ifrs_mappings("unverified")
