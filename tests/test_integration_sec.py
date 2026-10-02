"""Opt-in live SEC checks; ordinary CI remains deterministic and offline."""

from __future__ import annotations

import os

import pytest

from src.financials.normalization import validate_observation
from src.models import CompanyMetadata
from src.research_service import run_fundamentals_analysis
from src.financial_exports import annual_financial_csv, fundamentals_html


pytestmark = pytest.mark.integration


def _metadata(ticker: str) -> CompanyMetadata:
    return CompanyMetadata(
        requested_ticker=ticker, ticker=ticker, name=ticker,
        exchange="US", currency="USD", country="United States",
        sector="Technology" if ticker != "KO" else "Consumer Defensive",
        industry="", security_type="EQUITY",
    )


@pytest.mark.skipif(
    os.getenv("RUN_SEC_INTEGRATION") != "1" or not os.getenv("SEC_USER_AGENT"),
    reason="set RUN_SEC_INTEGRATION=1 and a private SEC_USER_AGENT",
)
@pytest.mark.parametrize("ticker", ["MSFT", "KO", "AAPL", "NVDA"])
def test_live_sec_pilot_normalization_and_exports(ticker):
    result = run_fundamentals_analysis(_metadata(ticker), force_refresh=True)
    assert result.status in {"AVAILABLE", "PARTIAL"}, result.reason
    assert len(result.observations) > 100
    assert len(result.annual) > 5
    assert result.identity.ticker == ticker
    assert result.identity.reporting_currency == "USD"
    assert result.observations["accession"].notna().any()
    assert result.observations["acceptance_timestamp_utc"].notna().any()
    assert len(result.source_sha256) == 64
    for record in result.observations.to_dict("records"):
        validate_observation(record)
    annual_csv = annual_financial_csv(result)
    assert b"fiscal_year" in annual_csv and b"fcf_status" in annual_csv
    html = fundamentals_html(result, theme="dark", portable=False)
    assert html.count(b"https://cdn.plot.ly/") == 1
    assert result.annual.iloc[-1]["revenue"] > 0
    if ticker == "NVDA":
        # Standard PPE CapEx is not currently available in Company Facts.
        # Do not fill the gap with a present-day estimate or mark FCF valid.
        assert result.annual.iloc[-1]["fcf_status"] == "MISSING_INPUT"
