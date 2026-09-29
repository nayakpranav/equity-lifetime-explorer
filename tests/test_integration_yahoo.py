import os

import pytest

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
