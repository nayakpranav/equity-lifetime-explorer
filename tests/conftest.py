from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.analytics import calculate_metrics
from src.corporate_actions import _normalize_provider_actions, actions_to_frame
from src.dividends import add_dividend_analytics
from src.models import AnalysisResult, CompanyMetadata, DataSourceRecord
from src.reconstruction import prepare_price_data
from src.validation import _assessment, validate_analysis, validation_to_frame
from src.volume import add_volume_analytics, build_volume_event_table, calculate_volume_metrics


@pytest.fixture
def synthetic_result() -> AnalysisResult:
    dates = pd.date_range("2022-01-03", "2025-12-31", freq="B")
    split_date = pd.Timestamp("2024-06-03")
    economic = np.linspace(50.0, 130.0, len(dates))
    raw = economic.copy()
    raw[dates >= split_date] /= 2.0
    history = pd.DataFrame(
        {
            "Open": raw * 0.995,
            "High": raw * 1.01,
            "Low": raw * 0.99,
            "Close": raw,
            "Adj Close": np.linspace(42.0, 78.0, len(dates)),
            "Volume": np.linspace(1_000_000, 2_000_000, len(dates)),
            "Dividends": 0.0,
            "Stock Splits": 0.0,
        },
        index=dates,
    )
    history.loc[split_date, "Stock Splits"] = 2.0
    for year, annual in ((2022, 1.0), (2023, 1.1), (2024, 1.21), (2025, 1.331)):
        for month in (3, 6, 9, 12):
            target = pd.Timestamp(year, month, 15)
            position = dates.searchsorted(target)
            history.iloc[position, history.columns.get_loc("Dividends")] = annual / 4
    metadata = CompanyMetadata(
        requested_ticker="TEST", ticker="TEST", name="Synthetic Company",
        exchange="Test Exchange", currency="EUR", country="Testland",
        sector="Industrials", industry="Testing", security_type="EQUITY",
    )
    actions = actions_to_frame(_normalize_provider_actions(history, metadata.currency))
    prices, _, diagnostics, preparation = prepare_price_data(history, actions)
    prices, volume_issues = add_volume_analytics(prices)
    prices, dividend_events, annual, status, dividend_metrics, dividend_issues = add_dividend_analytics(
        prices, currency=metadata.currency, adjusted_close_available=True
    )
    metrics = calculate_metrics(prices, actions, metadata)
    metrics.update(calculate_volume_metrics(prices))
    issues = validate_analysis(
        prices, actions, metadata, [*preparation, *volume_issues, *dividend_issues], diagnostics
    )
    validation = validation_to_frame(issues)
    provenance = DataSourceRecord(
        provider="Synthetic", retrieval_timestamp_utc=datetime.now(timezone.utc).isoformat(),
        ticker_requested="TEST", ticker_resolved="TEST", exchange=metadata.exchange,
        currency=metadata.currency, first_available_observation=str(dates.min().date()),
        last_available_observation=str(dates.max().date()), repair_requested=False,
        repaired_observations=0, validation_status=_assessment(validation),
    )
    return AnalysisResult(
        ticker="TEST", metadata=metadata, prices=prices, actions=actions,
        metrics=metrics, validation=validation, provenance=provenance,
        methodology="Synthetic deterministic methodology.",
        volume_events=build_volume_event_table(prices), dividend_events=dividend_events,
        annual_dividends=annual, dividend_status=status, dividend_metrics=dividend_metrics,
    )
