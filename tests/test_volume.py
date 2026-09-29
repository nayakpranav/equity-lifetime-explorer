import math

import numpy as np
import pandas as pd

from src.volume import add_volume_analytics


def test_previous_completed_sessions_and_dollar_volume():
    frame = pd.DataFrame(
        {"raw_close": [50.0] * 51, "volume": [100.0] * 50 + [200.0], "daily_return": [np.nan] + [0.0] * 50},
        index=pd.date_range("2024-01-02", periods=51, freq="B"),
    )
    result, issues = add_volume_analytics(frame)
    assert result["volume_ma_20"].iloc[:20].isna().all()
    assert result["volume_ma_50"].iloc[:50].isna().all()
    assert math.isclose(result["volume_ma_20"].iloc[-1], 100)
    assert math.isclose(result["relative_volume_20"].iloc[-1], 2)
    assert math.isclose(result["dollar_volume"].iloc[-1], 10_000)
    assert {issue.check for issue in issues} >= {"volume_rolling_integrity", "dollar_volume_integrity"}


def test_missing_negative_and_nonfinite_volume_are_safe():
    frame = pd.DataFrame(
        {"raw_close": [10.0] * 4, "volume": [np.nan, -1.0, np.inf, 0.0], "daily_return": [np.nan] * 4},
        index=pd.date_range("2024-01-02", periods=4, freq="B"),
    )
    result, issues = add_volume_analytics(frame)
    assert result["dollar_volume"].notna().sum() == 1
    checks = {issue.check: issue.severity for issue in issues}
    assert checks["negative_volume"] == "WARNING"
    assert checks["nonfinite_volume"] == "WARNING"
