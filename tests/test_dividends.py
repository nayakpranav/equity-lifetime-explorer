import math

import numpy as np
import pandas as pd

from src.dividends import _annual_dividend_cagr, _dividend_streaks, add_dividend_analytics


def test_annual_ttm_cagr_and_streaks():
    annual = pd.DataFrame({
        "year": [2022, 2023, 2024, 2025, 2026],
        "annual_dividend": [1.0, 1.1, 1.21, 1.331, 9.0],
        "completed_year": [True, True, True, True, False],
    })
    assert math.isclose(_annual_dividend_cagr(annual, 3), 0.10, rel_tol=1e-9)
    assert _dividend_streaks(annual) == (4, 3, 3)


def test_split_consistent_yield_and_no_dividend_fallback():
    frame = pd.DataFrame({
        "raw_close": [200.0, 100.0], "no_split_close": [200.0, 200.0],
        "adjusted_close": [100.0, 100.0], "cumulative_split_factor": [1.0, 2.0],
        "dividend": [1.0, 0.0],
    }, index=pd.to_datetime(["2020-01-02", "2020-01-03"]))
    result, events, annual, status, metrics, issues = add_dividend_analytics(
        frame, currency="USD", adjusted_close_available=True
    )
    assert math.isclose(result["split_adjusted_price_current_share"].iloc[0], 100)
    assert math.isclose(result["ttm_dividend_yield"].iloc[0], 0.01)
    assert result["provider_dividend"].equals(frame["dividend"])

    no_dividend = frame.assign(dividend=0.0)
    result, _, _, status, metrics, _ = add_dividend_analytics(
        no_dividend, currency="USD", adjusted_close_available=False
    )
    assert status == "NONE"
    assert not metrics["adjusted_close_total_return_available"]
    assert result["provider_total_return_wealth_10000"].isna().all()
