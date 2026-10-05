"""Opt-in live IFRS/ESEF provider-neutral results and export validation."""

import os
from dataclasses import replace
import io
import zipfile
import re

import pytest

from src.research_service import run_fundamentals_analysis
from src.downloads import prepare_complete_package, prepare_selected_download
from src.exports import export_bundle


@pytest.mark.integration
@pytest.mark.parametrize("ticker,currency,provider", [
    ("SAP.DE", "EUR", "SEC"), ("NVO", "DKK", "SEC"),
    ("MC.PA", "EUR", "ESEF"), ("NOKIA.HE", "EUR", "ESEF"), ("ASML.AS", "EUR", "ESEF"),
])
def test_live_global_financial_reports(ticker, currency, provider, synthetic_result):
    if provider == "SEC" and (os.getenv("RUN_SEC_INTEGRATION") != "1" or not os.getenv("SEC_USER_AGENT")):
        pytest.skip("Set live SEC flag and private operator identity")
    if provider == "ESEF" and os.getenv("RUN_ESEF_INTEGRATION") != "1":
        pytest.skip("Set live ESEF flag")
    metadata = replace(synthetic_result.metadata, ticker=ticker, currency=currency)
    result = run_fundamentals_analysis(metadata)
    assert result.available, (ticker, result.status, result.reason)
    assert result.identity.reporting_currency == currency
    market = replace(synthetic_result, ticker=ticker, metadata=metadata)
    files = export_bundle(market, ["fundamentals_html", "combined_html", "financial_annual_csv", "financial_provenance_csv"], fundamentals=result)
    assert len(files) == 4
    htmls = [content.decode() for name, content in files.items() if name.endswith(".html")]
    assert all(provider in text and currency in text for text in htmls)
    selected = prepare_selected_download(market, ["fundamentals_html", "financial_annual_csv"], fundamentals=result)
    assert len(zipfile.ZipFile(io.BytesIO(selected.payload)).namelist()) == 2
    complete = prepare_complete_package(market, fundamentals=result)
    assert len(zipfile.ZipFile(io.BytesIO(complete.payload)).namelist()) >= 7
    for portable in (False, True):
        combined = next(iter(export_bundle(market, ["combined_html"], fundamentals=result, portable_html=portable).values())).decode()
        assert combined.count('id="fundamentals"') + combined.count("id='fundamentals'") == 1
        external_scripts = re.findall(r"<script[^>]+src=[\"']https://cdn\.plot\.ly/[^\"']+[\"']", combined)
        assert len(external_scripts) == (0 if portable else 1)
        assert combined.count("plotly.js v") == (1 if portable else 0)
