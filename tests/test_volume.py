import math

import numpy as np
import pandas as pd

from src.volume import add_volume_analytics
from src.session_status import assess_latest_rvol
from src.exports import historical_csv
from src.charts.volume import build_volume_liquidity_figure


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


def test_latest_rvol_respects_exchange_session_and_original_retrieval_time(synthetic_result):
    result = synthetic_result
    result.metadata.exchange = "NasdaqGS"
    result.provenance.retrieval_timestamp_utc = "2025-12-31T16:00:00+00:00"
    preliminary = assess_latest_rvol(result)
    assert preliminary.status == "preliminary"
    assert "Preliminary" in preliminary.headline[0]
    assert "preliminary" in historical_csv(result).decode().splitlines()[-1]
    figure = build_volume_liquidity_figure(result)
    assert any("PRELIMINARY RVOL" in str(annotation.text) for annotation in figure.layout.annotations)

    result.provenance.retrieval_timestamp_utc = "2025-12-31T22:00:00+00:00"
    ambiguous = assess_latest_rvol(result)
    assert ambiguous.status == "unverified"
    assert ambiguous.headline[1] == "Not available"

    result.provenance.retrieval_timestamp_utc = "2026-01-01T17:00:00+00:00"
    completed = assess_latest_rvol(result)
    assert completed.status == "completed"
    assert completed.headline[1].endswith("×")

    result.metadata.exchange = "XETRA"
    result.prices = result.prices.iloc[:-1].copy()  # 30 Dec is an XETRA session; 31 Dec is not.
    assert assess_latest_rvol(result).status == "completed"

    result.metadata.exchange = "Unknown Exchange"
    assert assess_latest_rvol(result).status == "unverified"
    result.prices.loc[result.prices.index[-1], "relative_volume_20"] = np.nan
    assert assess_latest_rvol(result).status == "unavailable"
