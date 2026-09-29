"""Canonical analysis orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .analytics import calculate_metrics
from .corporate_actions import _normalize_provider_actions, actions_to_frame, load_manual_actions, reconcile_actions
from .dividends import _provider_adjusted_close_available, add_dividend_analytics
from .models import AnalysisResult
from .providers.yahoo import YahooFinanceProvider
from .reconstruction import prepare_price_data
from .validation import _assessment, validate_analysis, validation_to_frame
from .volume import add_volume_analytics, build_volume_event_table, calculate_volume_metrics
from .config import LOGGER

def run_equity_analysis(
    ticker: str,
    *,
    force_refresh: bool = False,
    cache_hours: float = 12.0,
    manual_actions_csv: Optional[str | Path] = None,
    manual_actions: Optional[Sequence[Mapping[str, Any]]] = None,
) -> AnalysisResult:
    provider = YahooFinanceProvider(cache_hours=cache_hours)
    payload = provider.fetch(ticker, force_refresh=force_refresh)
    provider_actions = _normalize_provider_actions(payload.history, payload.metadata.currency)
    manual = load_manual_actions(
        payload.metadata.ticker,
        path=manual_actions_csv,
        records=manual_actions,
    )
    reconciled, reconciliation_issues = reconcile_actions(provider_actions, manual)
    actions = actions_to_frame(reconciled)
    adjusted_close_available = _provider_adjusted_close_available(payload.history)
    prices, basis, basis_diagnostics, preparation_issues = prepare_price_data(payload.history, actions)
    prices, volume_issues = add_volume_analytics(prices)
    volume_events = build_volume_event_table(prices)
    (
        prices, dividend_events, annual_dividends, dividend_status,
        dividend_metrics, dividend_issues,
    ) = add_dividend_analytics(
        prices, currency=payload.metadata.currency,
        adjusted_close_available=adjusted_close_available,
    )
    metrics = calculate_metrics(prices, actions, payload.metadata)
    metrics.update(calculate_volume_metrics(prices))
    issues = validate_analysis(
        prices,
        actions,
        payload.metadata,
        [*reconciliation_issues, *preparation_issues, *volume_issues, *dividend_issues],
        basis_diagnostics,
    )
    validation = validation_to_frame(issues)
    payload.provenance.validation_status = _assessment(validation)
    payload.provenance.notes.append(f"Detected provider Close basis: {basis}.")
    payload.provenance.notes.append(
        "IPO offer price is not independently verified; earliest provider observation is used."
    )
    methodology = (
        "Mechanical no-split equivalent reconstructs the nominal ownership-equivalent value "
        "of one share at the earliest available observation. Each reconstructed as-traded raw "
        "close is multiplied by the cumulative verified share multiplier effective on or before "
        "that date. Cash dividends and rights issues do not alter this multiplier. Yahoo Close "
        "may be retrospectively split-normalized, so the engine tests split boundaries and, when "
        "necessary, restores as-traded OHLC using future split factors before reconstruction. "
        "This is a mathematical ownership-equivalent, not a prediction of the price that would "
        "have prevailed without splits; liquidity, accessibility, options, index mechanics, and "
        "investor behavior could differ. Share Volume is the provider-reported number of shares "
        "traded. The 20-session and 50-session averages use previous completed trading sessions; "
        "Relative Volume divides the current observation by the previous 20-session mean. Dollar "
        "Volume is raw as-traded closing price multiplied by reported share volume and is an "
        "approximation, not exact exchange turnover. Historical share volume can change mechanically "
        "around stock splits; Dollar Volume and Relative Volume are complementary comparisons. High "
        "volume indicates elevated participation but cannot identify participant type, accumulation, "
        "distribution, or causation. Provider-reported historical dividends may be retrospectively "
        "adjusted for stock splits. Dividend growth therefore uses the consistent provider/current-share-"
        "equivalent basis, and historical yield uses a split-consistent price denominator. Provider "
        "dividend dates are treated as effective/ex-dividend dates unless payment-date data is explicitly "
        "available. Provider Adjusted Close, when genuinely supplied, is used only as a pre-tax, pre-fee "
        "total-return proxy."
    )
    LOGGER.info(
        "%s | %d prices | %d actions | %s to %s | validation %s",
        payload.metadata.ticker,
        len(prices),
        len(actions),
        prices.index.min().date(),
        prices.index.max().date(),
        payload.provenance.validation_status,
    )
    return AnalysisResult(
        ticker=payload.metadata.ticker,
        metadata=payload.metadata,
        prices=prices,
        actions=actions,
        metrics=metrics,
        validation=validation,
        provenance=payload.provenance,
        methodology=methodology,
        volume_events=volume_events,
        dividend_events=dividend_events,
        annual_dividends=annual_dividends,
        dividend_status=dividend_status,
        dividend_metrics=dividend_metrics,
    )
