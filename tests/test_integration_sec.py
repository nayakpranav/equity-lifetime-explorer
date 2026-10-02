"""Opt-in live SEC checks; ordinary CI remains deterministic and offline."""

from __future__ import annotations

import os
import io
import zipfile

import pytest

from src.financials.normalization import validate_observation
from src.models import CompanyMetadata
from src.research_service import run_fundamentals_analysis
from src.financial_exports import annual_financial_csv, fundamentals_html
from src.downloads import prepare_complete_package, prepare_selected_download
from src.service import run_equity_analysis


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
    assert b"Financial Data Quality" in html
    assert b"<td>NaN</td>" not in html and b"<td>None</td>" not in html
    assert result.annual.iloc[-1]["revenue"] > 0
    if ticker == "KO":
        early = result.annual[result.annual["fiscal_year"] < 2016]
        assert early["revenue"].isna().all()
        assert result.annual.loc[result.annual["fiscal_year"].eq(2016), "revenue"].notna().any()
    if ticker == "NVDA":
        # Standard PPE CapEx is not currently available in Company Facts.
        # Do not fill the gap with a present-day estimate or mark FCF valid.
        assert result.annual.iloc[-1]["fcf_status"] == "MISSING_INPUT"


@pytest.mark.skipif(
    os.getenv("RUN_SEC_INTEGRATION") != "1"
    or os.getenv("RUN_YAHOO_INTEGRATION") != "1"
    or not os.getenv("SEC_USER_AGENT"),
    reason="set both live integration flags and a private SEC_USER_AGENT",
)
def test_live_combined_research_and_complete_zip():
    market = run_equity_analysis("MSFT")
    financials = run_fundamentals_analysis(market.metadata, force_refresh=True)
    assert financials.available
    selected = prepare_selected_download(
        market, ["combined_html", "financial_annual_csv", "financial_ratios_csv"],
        fundamentals=financials, theme="dark", financial_price_overlay=True,
    )
    with zipfile.ZipFile(io.BytesIO(selected.payload)) as archive:
        names = archive.namelist()
        assert len(names) == 3
        combined = archive.read(next(name for name in names if "complete_research_report" in name))
        annual = archive.read(next(name for name in names if "sec_annual_financials" in name))
        assert combined.count(b"https://cdn.plot.ly/") == 1
        assert b"Reported EPS &amp; Comparable Growth" in combined or b"Reported EPS & Comparable Growth" in combined
        assert b"Capital Efficiency" in combined
        assert b"Split-adjusted share price" in combined
        assert b"Market Data Quality" in combined and b"Financial Data Quality" in combined
        assert b"<td>NaN</td>" not in combined and b"<td>None</td>" not in combined
        assert b"roe_status" in annual and b"eps_diluted_yoy_status" in annual
    complete = prepare_complete_package(market, fundamentals=financials, theme="dark")
    with zipfile.ZipFile(io.BytesIO(complete.payload)) as archive:
        names = archive.namelist()
        assert any("financial_fundamentals" in name for name in names)
        assert any("sec_financial_quality" in name for name in names)
        assert any("sec_financial_provenance" in name for name in names)
