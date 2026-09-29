"""Dividend and provider-adjusted total-return analytics preserved from Colab v5."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from .config import CALENDAR_DAYS_PER_YEAR
from .models import ValidationIssue

def _provider_adjusted_close_available(history: pd.DataFrame) -> bool:
    """True only when Adjusted Close was genuinely supplied by the provider."""
    if "Adj Close" not in history.columns:
        return False
    adjusted = pd.to_numeric(history["Adj Close"], errors="coerce")
    finite_positive = adjusted.notna() & np.isfinite(adjusted.to_numpy(dtype=float)) & adjusted.gt(0)
    return int(finite_positive.sum()) >= 2


def _annual_dividend_cagr(annual: pd.DataFrame, years: int) -> Optional[float]:
    if annual.empty or years <= 0:
        return None
    completed = annual[annual["completed_year"].fillna(False)].copy()
    if completed.empty:
        return None
    end_year = int(completed["year"].max())
    start_year = end_year - int(years)
    end_rows = completed[completed["year"] == end_year]
    start_rows = completed[completed["year"] == start_year]
    if len(end_rows) != 1 or len(start_rows) != 1:
        return None
    ending = float(end_rows.iloc[0]["annual_dividend"])
    beginning = float(start_rows.iloc[0]["annual_dividend"])
    if not np.isfinite(beginning) or not np.isfinite(ending) or beginning <= 0 or ending <= 0:
        return None
    return float((ending / beginning) ** (1.0 / years) - 1.0)


def _dividend_streaks(annual: pd.DataFrame) -> tuple[int, int, int]:
    required = {"year", "annual_dividend", "completed_year"}
    if annual.empty or not required.issubset(annual.columns):
        return 0, 0, 0
    completed = annual[annual["completed_year"].fillna(False)].sort_values("year")
    if completed.empty:
        return 0, 0, 0
    values = completed.set_index("year")["annual_dividend"].astype(float)
    paying_streak = 0
    for value in values.iloc[::-1]:
        if np.isfinite(value) and value > 0:
            paying_streak += 1
        else:
            break
    increase_streak = 0
    no_cut_streak = 0
    years = list(values.index.astype(int))
    for position in range(len(years) - 1, 0, -1):
        current_year, prior_year = years[position], years[position - 1]
        if current_year - prior_year != 1:
            break
        current, prior = float(values.loc[current_year]), float(values.loc[prior_year])
        if not (np.isfinite(current) and np.isfinite(prior) and current > 0 and prior > 0):
            break
        if current > prior:
            increase_streak += 1
        else:
            break
    for position in range(len(years) - 1, 0, -1):
        current_year, prior_year = years[position], years[position - 1]
        if current_year - prior_year != 1:
            break
        current, prior = float(values.loc[current_year]), float(values.loc[prior_year])
        if not (np.isfinite(current) and np.isfinite(prior) and current > 0 and prior > 0):
            break
        if current >= prior:
            no_cut_streak += 1
        else:
            break
    return paying_streak, increase_streak, no_cut_streak


def _infer_dividend_frequency(events: pd.DataFrame, annual: pd.DataFrame) -> str:
    if events.empty:
        return "Insufficient history"
    positive = events[pd.to_numeric(events["provider_dividend"], errors="coerce").gt(0)].copy()
    if len(positive) < 2:
        return "Insufficient history"
    completed_years = annual.loc[annual["completed_year"].fillna(False), "year"].astype(int)
    recent_years = set(completed_years.nlargest(3).tolist())
    recent = positive[positive["calendar_year"].isin(recent_years)] if recent_years else positive
    counts = recent.groupby("calendar_year").size()
    median_count = float(counts.median()) if len(counts) else np.nan
    dates = pd.DatetimeIndex(recent["date"].sort_values())
    median_gap = float(pd.Series(dates).diff().dt.days.dropna().median()) if len(dates) > 1 else np.nan
    if np.isfinite(median_count):
        if median_count >= 10:
            return "Monthly"
        if 3 <= median_count <= 5:
            return "Quarterly"
        if median_count == 2:
            return "Semiannual"
        if median_count == 1 and len(counts) >= 2:
            return "Annual"
    if np.isfinite(median_gap):
        if median_gap <= 45:
            return "Monthly"
        if median_gap <= 120:
            return "Quarterly"
        if median_gap <= 240:
            return "Semiannual"
        if median_gap <= 430:
            return "Annual"
    return "Irregular"


def add_dividend_analytics(
    prices: pd.DataFrame,
    *,
    currency: str,
    adjusted_close_available: bool,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    str,
    dict[str, Any],
    list[ValidationIssue],
]:
    """Layer dividend analytics onto reconstructed prices without rewriting provider facts."""
    frame = prices.copy()
    issues: list[ValidationIssue] = []
    provider_dividend = pd.to_numeric(
        frame.get("dividend", pd.Series(np.nan, index=frame.index)), errors="coerce"
    )
    frame["provider_dividend"] = provider_dividend
    finite_mask = pd.Series(
        np.isfinite(provider_dividend.to_numpy(dtype=float)), index=frame.index
    )
    finite_dividend = provider_dividend.where(finite_mask)
    positive_mask = finite_dividend.gt(0).fillna(False)
    nonzero_mask = finite_dividend.ne(0).fillna(False)

    final_factor = float(frame["cumulative_split_factor"].iloc[-1])
    future_factor = final_factor / frame["cumulative_split_factor"].where(
        frame["cumulative_split_factor"].gt(0)
    )
    frame["split_adjusted_price_current_share"] = frame["raw_close"] / future_factor

    rolling_input = finite_dividend.fillna(0.0)
    positive_observation = positive_mask.astype(float)
    ttm = rolling_input.rolling("365D", min_periods=1).sum()
    ttm_positive_count = positive_observation.rolling("365D", min_periods=1).sum()
    frame["ttm_dividend"] = ttm.where(ttm_positive_count.gt(0))
    denominator = frame["split_adjusted_price_current_share"].where(
        frame["split_adjusted_price_current_share"].gt(0)
    )
    frame["ttm_dividend_yield"] = (frame["ttm_dividend"] / denominator).where(
        frame["ttm_dividend"].ge(0) & denominator.notna()
    )

    price_series = frame["no_split_close"].where(frame["no_split_close"].gt(0))
    first_price = price_series.first_valid_index()
    wealth_start = first_price
    frame["price_wealth_10000"] = np.nan
    if first_price is not None:
        frame.loc[first_price:, "price_wealth_10000"] = (
            10_000.0 * price_series.loc[first_price:] / float(price_series.loc[first_price])
        )
    frame["provider_total_return_wealth_10000"] = np.nan
    frame["total_return_uplift"] = np.nan
    adjusted_valid = pd.to_numeric(frame["adjusted_close"], errors="coerce").where(
        pd.to_numeric(frame["adjusted_close"], errors="coerce").gt(0)
    )
    total_return_available = bool(adjusted_close_available and adjusted_valid.notna().sum() >= 2)
    common = frame["no_split_close"].gt(0) & adjusted_valid.notna()
    common_index = frame.index[common]
    if total_return_available and len(common_index) >= 2:
        common_start = common_index[0]
        wealth_start = common_start
        price_base = float(frame.loc[common_start, "no_split_close"])
        adjusted_base = float(adjusted_valid.loc[common_start])
        frame["price_wealth_10000"] = np.nan
        frame.loc[common_start:, "price_wealth_10000"] = (
            10_000.0 * frame.loc[common_start:, "no_split_close"] / price_base
        )
        frame.loc[common_start:, "provider_total_return_wealth_10000"] = (
            10_000.0 * adjusted_valid.loc[common_start:] / adjusted_base
        )
        frame["total_return_uplift"] = (
            frame["provider_total_return_wealth_10000"] / frame["price_wealth_10000"] - 1.0
        )

    event_mask = finite_mask & nonzero_mask
    event_columns = [
        "date", "provider_dividend", "currency", "split_adjusted_price_current_share",
        "ttm_dividend", "ttm_dividend_yield", "calendar_year", "calendar_month",
        "calendar_quarter", "date_basis",
    ]
    events = pd.DataFrame(index=frame.index[event_mask])
    if len(events):
        events["provider_dividend"] = frame.loc[event_mask, "provider_dividend"].to_numpy()
        events["currency"] = currency
        events["split_adjusted_price_current_share"] = frame.loc[
            event_mask, "split_adjusted_price_current_share"
        ].to_numpy()
        events["ttm_dividend"] = frame.loc[event_mask, "ttm_dividend"].to_numpy()
        events["ttm_dividend_yield"] = frame.loc[event_mask, "ttm_dividend_yield"].to_numpy()
        events["calendar_year"] = events.index.year.astype(int)
        events["calendar_month"] = events.index.month.astype(int)
        events["calendar_quarter"] = [f"Q{quarter}" for quarter in events.index.quarter]
        events["date_basis"] = "Provider dividend date / effective date"
        events.index.name = "date"
        events = events.reset_index()[event_columns]
    else:
        events = pd.DataFrame(columns=event_columns)

    current_calendar_year = datetime.now(timezone.utc).year
    event_dates = frame.index[event_mask]
    annual_columns = [
        "year", "annual_dividend", "payment_count", "yoy_growth",
        "completed_year", "ytd", "year_label",
    ]
    if len(event_dates):
        first_year = int(event_dates.min().year)
        last_year = int(frame.index.max().year)
        years = pd.Index(range(first_year, last_year + 1), name="year")
        annual_sum = finite_dividend.groupby(frame.index.year).sum(min_count=1).reindex(years).fillna(0.0)
        payment_count = positive_mask.groupby(frame.index.year).sum().reindex(years).fillna(0).astype(int)
        annual = pd.DataFrame(
            {
                "year": np.asarray(years, dtype=int),
                "annual_dividend": annual_sum.to_numpy(),
                "payment_count": payment_count.to_numpy(),
            }
        )
        annual["completed_year"] = annual["year"].lt(current_calendar_year)
        annual["ytd"] = ~annual["completed_year"]
        annual["yoy_growth"] = np.nan
        for index in range(1, len(annual)):
            current = annual.iloc[index]
            prior = annual.iloc[index - 1]
            if (
                bool(current["completed_year"])
                and bool(prior["completed_year"])
                and int(current["year"]) - int(prior["year"]) == 1
                and float(current["annual_dividend"]) > 0
                and float(prior["annual_dividend"]) > 0
            ):
                annual.loc[index, "yoy_growth"] = (
                    float(current["annual_dividend"]) / float(prior["annual_dividend"]) - 1.0
                )
        annual["year_label"] = annual["year"].astype(str) + np.where(annual["ytd"], " YTD", "")
        annual = annual[annual_columns]
    else:
        annual = pd.DataFrame(columns=annual_columns)

    completed_paying_years = int(
        (annual["completed_year"].fillna(False) & annual["annual_dividend"].gt(0)).sum()
    ) if not annual.empty else 0
    if int(positive_mask.sum()) == 0:
        status = "NONE"
    elif completed_paying_years < 3:
        status = "LIMITED"
    else:
        status = "ESTABLISHED"

    paying_streak, increase_streak, no_cut_streak = _dividend_streaks(annual)
    completed_growth = annual.loc[
        annual["completed_year"].fillna(False), "yoy_growth"
    ].dropna() if not annual.empty else pd.Series(dtype=float)
    latest_date = frame.index[-1]
    latest_year = int(latest_date.year)
    current_year_is_partial = latest_year == current_calendar_year
    current_year_ytd = None
    prior_year_same_period = None
    ytd_growth = None
    if current_year_is_partial:
        same_period_key = latest_date.month * 100 + latest_date.day
        current_mask = (
            (frame.index.year == latest_year)
            & ((frame.index.month * 100 + frame.index.day) <= same_period_key)
        )
        prior_mask = (
            (frame.index.year == latest_year - 1)
            & ((frame.index.month * 100 + frame.index.day) <= same_period_key)
        )
        current_year_ytd = float(finite_dividend.loc[current_mask].fillna(0.0).sum())
        if prior_mask.any():
            prior_year_same_period = float(finite_dividend.loc[prior_mask].fillna(0.0).sum())
            if prior_year_same_period > 0 and current_year_ytd >= 0:
                ytd_growth = float(current_year_ytd / prior_year_same_period - 1.0)

    positive_events = events[pd.to_numeric(events["provider_dividend"], errors="coerce").gt(0)]
    latest_event = positive_events.iloc[-1] if len(positive_events) else None
    latest_ttm = frame["ttm_dividend"].iloc[-1]
    latest_raw = frame["raw_close"].iloc[-1]
    current_ttm_yield = (
        float(latest_ttm / latest_raw)
        if pd.notna(latest_ttm) and np.isfinite(latest_ttm) and latest_ttm >= 0 and latest_raw > 0
        else None
    )
    completed = annual[annual["completed_year"].fillna(False)] if not annual.empty else annual
    cagr_endpoint_year = int(completed["year"].max()) if len(completed) else None
    wealth = frame[["price_wealth_10000", "provider_total_return_wealth_10000"]].dropna(
        subset=["price_wealth_10000"]
    )
    ending_price_wealth = float(wealth["price_wealth_10000"].iloc[-1]) if len(wealth) else None
    ending_total_wealth = (
        float(frame["provider_total_return_wealth_10000"].dropna().iloc[-1])
        if total_return_available and frame["provider_total_return_wealth_10000"].notna().any()
        else None
    )
    elapsed_years = (
        (frame.index[-1] - wealth_start).days / CALENDAR_DAYS_PER_YEAR
        if wealth_start is not None else 0.0
    )
    price_multiple = ending_price_wealth / 10_000.0 if ending_price_wealth is not None else None
    total_multiple = ending_total_wealth / 10_000.0 if ending_total_wealth is not None else None
    metrics = {
        "status": status,
        "provider_dividend_basis": "Provider-reported split-adjusted dividend per current-share-equivalent basis",
        "first_dividend_date": pd.Timestamp(positive_events["date"].min()) if len(positive_events) else None,
        "latest_dividend_date": pd.Timestamp(latest_event["date"]) if latest_event is not None else None,
        "latest_dividend_amount": float(latest_event["provider_dividend"]) if latest_event is not None else None,
        "dividend_event_count": int(len(positive_events)),
        "years_with_dividends": int(positive_events["calendar_year"].nunique()) if len(positive_events) else 0,
        "ttm_dividend": float(latest_ttm) if pd.notna(latest_ttm) and np.isfinite(latest_ttm) else None,
        "current_ttm_dividend_yield": current_ttm_yield,
        "dividend_growth_1y": _annual_dividend_cagr(annual, 1),
        "dividend_cagr_3y": _annual_dividend_cagr(annual, 3),
        "dividend_cagr_5y": _annual_dividend_cagr(annual, 5),
        "dividend_cagr_10y": _annual_dividend_cagr(annual, 10),
        "completed_year_average_growth": float(completed_growth.mean()) if len(completed_growth) else None,
        "dividend_paying_streak": paying_streak,
        "dividend_increase_streak": increase_streak,
        "dividend_no_cut_streak": no_cut_streak,
        "inferred_payment_frequency": _infer_dividend_frequency(events, annual),
        "current_year_ytd_dividend": current_year_ytd,
        "prior_year_same_period_dividend": prior_year_same_period,
        "ytd_dividend_growth": ytd_growth,
        "cagr_endpoint_year": cagr_endpoint_year,
        "adjusted_close_total_return_available": total_return_available,
        "price_only_lifetime_multiple": price_multiple,
        "provider_adjusted_total_return_multiple": total_multiple,
        "price_only_cagr": (
            float(price_multiple ** (1.0 / elapsed_years) - 1.0)
            if price_multiple is not None and price_multiple > 0 and elapsed_years > 0 else None
        ),
        "provider_adjusted_total_return_cagr": (
            float(total_multiple ** (1.0 / elapsed_years) - 1.0)
            if total_multiple is not None and total_multiple > 0 and elapsed_years > 0 else None
        ),
        "ending_price_wealth_10000": ending_price_wealth,
        "ending_total_return_wealth_10000": ending_total_wealth,
        "compounded_total_return_uplift": (
            float(total_multiple / price_multiple - 1.0)
            if total_multiple is not None and price_multiple is not None and price_multiple > 0 else None
        ),
    }

    negative_count = int(provider_dividend.lt(0).fillna(False).sum())
    nonfinite_count = int((provider_dividend.notna() & ~finite_mask).sum())
    availability_message = {
        "NONE": "No positive provider-reported cash-dividend observations exist within available price history.",
        "LIMITED": "Provider-reported dividends exist, but fewer than three completed dividend-paying calendar years are available.",
        "ESTABLISHED": "Sufficient completed provider-reported dividend history exists for multi-year analysis.",
    }[status]
    issues.append(ValidationIssue("PASS" if status == "ESTABLISHED" else "INFO", "dividend_availability", availability_message))
    issues.append(ValidationIssue(
        "WARNING" if negative_count else "PASS", "negative_dividend_values",
        f"{negative_count} negative provider dividend observations were retained and reported without repair."
        if negative_count else "No negative provider dividend observations were found.",
    ))
    issues.append(ValidationIssue(
        "WARNING" if nonfinite_count else "PASS", "nonfinite_dividend_values",
        f"{nonfinite_count} non-finite provider dividend observations were excluded from derived calculations and remain reported by validation."
        if nonfinite_count else "No non-finite provider dividend observations were found.",
    ))
    if len(events):
        event_sum = float(pd.to_numeric(events["provider_dividend"], errors="coerce").sum())
        annual_sum_check = float(pd.to_numeric(annual["annual_dividend"], errors="coerce").sum())
        aggregation_ok = math.isclose(event_sum, annual_sum_check, rel_tol=1e-10, abs_tol=1e-12)
    else:
        aggregation_ok = True
    issues.append(ValidationIssue(
        "PASS" if aggregation_ok else "ERROR", "annual_dividend_aggregation",
        "Annual dividend totals reconcile to finite event-level provider observations."
        if aggregation_ok else "Annual dividend totals do not reconcile to event-level provider observations.",
    ))
    expected_ttm = rolling_input.rolling("365D", min_periods=1).sum().where(ttm_positive_count.gt(0))
    ttm_ok = np.allclose(frame["ttm_dividend"], expected_ttm, equal_nan=True)
    issues.append(ValidationIssue(
        "PASS" if ttm_ok else "ERROR", "ttm_dividend_integrity",
        "TTM dividend uses a date-aware trailing 365-day window."
        if ttm_ok else "TTM dividend failed its date-aware rolling integrity check.",
    ))
    expected_yield = (expected_ttm / denominator).where(expected_ttm.ge(0) & denominator.notna())
    yield_ok = np.allclose(frame["ttm_dividend_yield"], expected_yield, equal_nan=True)
    issues.append(ValidationIssue(
        "PASS" if yield_ok else "ERROR", "historical_yield_integrity",
        "Historical yield uses provider dividends and a split-consistent current-share price denominator."
        if yield_ok else "Historical dividend yield failed its split-consistent denominator check.",
    ))
    partial_ok = annual.empty or not bool(
        annual.loc[annual["year"].eq(current_calendar_year), "completed_year"].fillna(False).any()
    )
    partial_ok = partial_ok and (cagr_endpoint_year is None or cagr_endpoint_year < current_calendar_year)
    issues.append(ValidationIssue(
        "PASS" if partial_ok else "ERROR", "partial_year_exclusion",
        "The current partial calendar year is excluded from structural CAGRs and streaks."
        if partial_ok else "A partial calendar year was incorrectly included in structural metrics.",
    ))
    issues.append(ValidationIssue(
        "PASS" if total_return_available else "INFO", "adjusted_close_total_return_availability",
        "Genuine provider Adjusted Close is available for the total-return proxy."
        if total_return_available else "Price vs total-return comparison unavailable because genuine provider Adjusted Close was not supplied.",
    ))
    return frame, events, annual, status, metrics, issues
