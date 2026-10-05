"""Opt-in documented public ESEF API validation; ordinary CI stays offline."""

import os

import pytest

from src.financials.normalization import validate_observation
from src.financials.oim import normalize_esef_document
from src.providers.esef import EsefFinancialProvider


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_ESEF_INTEGRATION") != "1", reason="set RUN_ESEF_INTEGRATION=1")
def test_live_lvmh_entity_linked_ifrs_extraction():
    provider = EsefFinancialProvider()
    lei = "IOG4E947OATN0KJYSD45"
    filings = provider.filings(lei)
    assert filings
    document = provider.fetch_document(lei, filings[-1])
    rows, issues = normalize_esef_document(
        document, ticker="MC.PA", currency="EUR", fiscal_year_end="1231",
    )
    assert not rows.empty
    assert rows.issuer_id.eq("LEI:" + lei).all()
    assert rows.currency.eq("EUR").all()
    assert len(document.source_sha256) == 64
    assert rows.filing_date.isna().all()
    assert rows.acceptance_timestamp_utc.isna().all()
    valid_revenue = rows.loc[rows.normalized_concept.eq("revenue") & rows.quality_status.ne("invalid")]
    assert not valid_revenue.empty
    for row in rows.to_dict("records"):
        validate_observation(row)
    # Coverage changes with new disclosures; no fixed current amounts or counts.
    assert not issues.empty or rows.quality_status.isin(["warning", "invalid"]).all()
