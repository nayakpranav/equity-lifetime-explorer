"""Opt-in real provider events, reconstructed inputs and dividend/export checks."""

import io
import os
import zipfile

import numpy as np
import pandas as pd
import pytest
import yfinance as yf

from src.corporate_actions import _normalize_provider_actions, actions_to_frame
from src.reconstruction import prepare_price_data
from src.providers.yahoo import _normalize_history_index
from src.service import run_equity_analysis
from src.downloads import prepare_complete_package, prepare_selected_download


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("RUN_YAHOO_INTEGRATION") != "1", reason="set RUN_YAHOO_INTEGRATION=1")]


@pytest.mark.parametrize("ticker", ["ITC.NS","INFY.NS","TCS.NS","HDFCBANK.NS","COST","MC.PA","ASML.AS"])
def test_live_dividends_match_local_history_not_duplicate_endpoint_views(ticker):
    obj = yf.Ticker(ticker)
    raw = obj.history(period="max", auto_adjust=False, actions=True, repair=True)
    assert not raw.empty
    zone = str(raw.index.tz)
    authoritative, _ = _normalize_history_index(raw, zone)
    result = run_equity_analysis(ticker,force_refresh=True)
    native = authoritative.loc[authoritative.Dividends.gt(0),"Dividends"]
    actual = result.dividend_events.set_index("date").provider_dividend
    common = native.index.intersection(actual.index)
    assert len(common) == len(native)
    assert np.allclose(native.loc[common],actual.loc[common])
    # Compare fixed reconstruction with history-only authoritative inputs.
    # No split/no-split/total-return formula is changed by reconciliation.
    actions = actions_to_frame(_normalize_provider_actions(authoritative,result.metadata.currency))
    expected, _, _, _ = prepare_price_data(authoritative,actions)
    overlap = expected.index.intersection(result.prices.index)[:-1]  # latest quote may move intraday
    for column in ("provider_close","adjusted_close","raw_close","no_split_close","cumulative_split_factor"):
        assert np.allclose(expected.loc[overlap,column],result.prices.loc[overlap,column],equal_nan=True), (ticker,column)
    if ticker == "ITC.NS":
        annual = result.annual_dividends.set_index("year")
        assert annual.loc[2025,"annual_dividend"] == pytest.approx(14.35)
        assert annual.loc[2026,"annual_dividend"] == pytest.approx(14.50)
        assert annual.loc[2025,"payment_count"] == annual.loc[2026,"payment_count"] == 2
        checks = result.validation.loc[result.validation.check.eq("dividend_external_reference")]
        assert len(checks) == 8 and checks.severity.eq("PASS").all()
        assert result.metrics["cumulative_share_multiplier"] == 30
    if ticker == "COST":
        # Genuine exceptional cash distribution, not a duplicate to be deleted.
        assert actual.loc["2023-12-27"] == pytest.approx(15.0)
    selected = prepare_selected_download(result,["dividend_html","dividend_csv"],theme="dark")
    with zipfile.ZipFile(io.BytesIO(selected.payload)) as archive:
        assert len(archive.namelist()) == 2
        assert "Dividend Source Validation" in next(archive.read(n).decode() for n in archive.namelist() if n.endswith('.html'))
    complete = prepare_complete_package(result)
    with zipfile.ZipFile(io.BytesIO(complete.payload)) as archive:
        assert any("provider_action_audit" in n for n in archive.namelist())
