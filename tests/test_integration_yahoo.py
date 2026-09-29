import io
import os
import zipfile
from html.parser import HTMLParser

import pytest

from src.downloads import prepare_complete_package, prepare_selected_download
from src.service import run_equity_analysis


pytestmark = pytest.mark.integration


@pytest.mark.skipif(os.getenv("RUN_YAHOO_INTEGRATION") != "1", reason="set RUN_YAHOO_INTEGRATION=1")
@pytest.mark.parametrize("ticker", ["NVDA", "GOOG", "AAPL", "MSFT", "KO", "BRK-B", "SAP.DE", "RELIANCE.NS"])
def test_live_provider_symbols(ticker):
    result = run_equity_analysis(ticker)
    assert len(result.prices) > 100
    assert result.ticker == ticker
    assert result.provenance.validation_status in {"HIGH", "MEDIUM", "LOW"}
    if ticker == "GOOG":
        assert abs(result.metrics["cumulative_share_multiplier"] - 40.1499) < 0.01
    if ticker == "KO":
        assert result.dividend_status == "ESTABLISHED"
    if ticker == "BRK-B":
        assert result.dividend_status == "NONE"
    if ticker == "SAP.DE":
        assert result.metadata.currency == "EUR"


@pytest.mark.skipif(os.getenv("RUN_YAHOO_INTEGRATION") != "1", reason="set RUN_YAHOO_INTEGRATION=1")
@pytest.mark.parametrize("ticker", ["AVGO", "BRK-B"])
def test_live_export_pipeline(ticker):
    result = run_equity_analysis(ticker)
    focused = prepare_selected_download(result, ["lifetime_html"], theme="dark")
    assert focused.payload.startswith(b"<!doctype html>")

    combined = prepare_selected_download(result, ["combined_html"], theme="dark")
    combined_text = combined.payload.decode("utf-8")
    HTMLParser().feed(combined_text)
    assert combined_text.count("https://cdn.plot.ly/") == 1
    assert all(
        section in combined_text
        for section in ("id='price'", "id='volume'", "id='dividends'", "id='actions'", "id='validation'")
    )

    selected = prepare_selected_download(
        result, ["lifetime_html", "combined_html"], theme="dark"
    )
    with zipfile.ZipFile(io.BytesIO(selected.payload)) as archive:
        assert len(archive.namelist()) == 2

    complete = prepare_complete_package(result, theme="dark")
    with zipfile.ZipFile(io.BytesIO(complete.payload)) as archive:
        names = archive.namelist()
    if ticker == "BRK-B":
        assert result.dividend_status == "NONE"
        assert not any("dividend_total_return" in name for name in names)
        assert not any("dividend_summary" in name for name in names)
        assert "No provider-reported cash-dividend history" in combined_text
    else:
        assert any("dividend_total_return" in name for name in names)
        portable = prepare_selected_download(
            result, ["combined_html"], theme="dark", portable_html=True
        )
        assert portable.payload.count(b"plotly.js v") == 1
