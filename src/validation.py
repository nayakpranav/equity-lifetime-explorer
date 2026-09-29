"""Financial and provider-data validation."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd

from .config import SHARE_CHANGING_TYPES
from .models import CompanyMetadata, ValidationIssue
from .reconstruction import _nearest_trade_pair

def validate_analysis(
    prices: pd.DataFrame,
    actions: pd.DataFrame,
    metadata: CompanyMetadata,
    initial_issues: Sequence[ValidationIssue],
    basis_diagnostics: Mapping[str, Any],
) -> list[ValidationIssue]:
    issues = list(initial_issues)
    if prices.index.has_duplicates:
        issues.append(ValidationIssue("ERROR", "duplicate_dates", "Duplicate price dates remain after normalization."))
    else:
        issues.append(ValidationIssue("PASS", "duplicate_dates", "No duplicate price dates remain."))
    if prices["raw_close"].isna().any():
        issues.append(ValidationIssue("WARNING", "missing_close", "Missing reconstructed raw Close values remain."))
    else:
        issues.append(ValidationIssue("PASS", "missing_close", "No missing reconstructed raw Close values."))
    if (prices["raw_close"] <= 0).any():
        issues.append(ValidationIssue("ERROR", "nonpositive_price", "Zero or negative reconstructed prices found."))
    else:
        issues.append(ValidationIssue("PASS", "nonpositive_price", "All reconstructed raw closes are positive."))
    extreme = prices["daily_return"].abs().gt(0.50)
    extreme_dates = prices.index[extreme.fillna(False)]
    if len(extreme_dates):
        sample = ", ".join(date.date().isoformat() for date in extreme_dates[:5])
        issues.append(
            ValidationIssue(
                "WARNING",
                "extreme_daily_moves",
                f"{len(extreme_dates)} split-adjusted one-session moves exceeded 50% (first: {sample}). Review for genuine events or data anomalies.",
            )
        )
    else:
        issues.append(ValidationIssue("PASS", "extreme_daily_moves", "No split-adjusted one-session move exceeded 50%."))
    calendar_gaps = prices.index.to_series().diff().dt.days.dropna()
    max_gap = int(calendar_gaps.max()) if len(calendar_gaps) else 0
    severity = "WARNING" if max_gap > 14 else "PASS"
    issues.append(
        ValidationIssue(
            severity,
            "date_gaps",
            f"Largest gap between observations is {max_gap} calendar days; holidays, suspensions, or provider gaps may contribute.",
        )
    )
    share_actions = actions[
        actions["action_type"].isin(SHARE_CHANGING_TYPES)
        & actions["included_in_reconstruction"].fillna(False)
    ]
    invalid = share_actions[
        pd.to_numeric(share_actions["share_multiplier"], errors="coerce").isna()
        | pd.to_numeric(share_actions["share_multiplier"], errors="coerce").le(0)
    ]
    if len(invalid):
        issues.append(ValidationIssue("ERROR", "malformed_split_ratio", f"{len(invalid)} included share-changing actions have invalid multipliers."))
    else:
        issues.append(ValidationIssue("PASS", "malformed_split_ratio", "All included share-changing action multipliers are positive."))
    duplicate_key = actions.duplicated(subset=["date", "action_type", "share_multiplier", "cash_amount", "source"], keep=False)
    if duplicate_key.any():
        issues.append(ValidationIssue("WARNING", "duplicate_actions", f"{int(duplicate_key.sum())} potentially duplicate corporate-action rows found."))
    else:
        issues.append(ValidationIssue("PASS", "duplicate_actions", "No exact duplicate corporate-action rows found."))
    outside = actions[~actions["date"].between(prices.index.min(), prices.index.max())]
    if len(outside):
        issues.append(ValidationIssue("WARNING", "actions_outside_history", f"{len(outside)} actions fall outside available price history and do not affect reconstruction."))
    split_warning_count = 0
    for _, action in share_actions.iterrows():
        event_date = pd.Timestamp(action["date"])
        pre_date, post_date = _nearest_trade_pair(prices.index, event_date)
        if pre_date is None or post_date is None:
            issues.append(ValidationIssue("WARNING", "split_boundary_missing", f"Could not bracket split on {event_date.date()} with trading observations.", event_date))
            split_warning_count += 1
            continue
        economic_move = float(prices.loc[post_date, "no_split_close"] / prices.loc[pre_date, "no_split_close"] - 1)
        if abs(economic_move) > 0.35:
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "split_continuity",
                    f"No-split series moved {economic_move:+.1%} across {event_date.date()} (tolerance ±35%).",
                    event_date,
                )
            )
            split_warning_count += 1
        else:
            issues.append(
                ValidationIssue(
                    "PASS",
                    "split_continuity",
                    f"No-split series continuity passed for {event_date.date()} ({economic_move:+.1%}).",
                    event_date,
                )
            )
    if share_actions.empty:
        issues.append(ValidationIssue("INFO", "split_continuity", "No included split-equivalent actions to test."))
    missing_meta = [
        label
        for label, value in {
            "exchange": metadata.exchange,
            "currency": metadata.currency,
            "name": metadata.name,
        }.items()
        if not value or value == "Unknown"
    ]
    if missing_meta:
        issues.append(ValidationIssue("WARNING", "missing_metadata", f"Missing or unknown metadata: {', '.join(missing_meta)}."))
    else:
        issues.append(ValidationIssue("PASS", "missing_metadata", "Core company metadata is present."))
    currency = metadata.currency.upper()
    if currency in {"GBX", "GBP", "GBP", "GBPENCE", "GBP."}:
        issues.append(ValidationIssue("INFO", "currency_units", f"Currency is reported as {metadata.currency}; no pence/pound conversion was applied."))
    elif currency == "UNKNOWN":
        issues.append(ValidationIssue("WARNING", "currency_units", "Currency is unavailable; displayed values have no inferred symbol."))
    else:
        issues.append(ValidationIssue("PASS", "currency_units", f"Single provider currency reported as {metadata.currency}; no currency conversion was applied."))
    issues.append(ValidationIssue("INFO", "ipo_offer_price", "IPO offer price not independently verified; chart begins at the earliest provider market observation."))
    issues.append(ValidationIssue("INFO", "provider_validation", "Corporate-action validation used the primary provider only unless a manual record explicitly confirms an event."))
    return issues


def validation_to_frame(issues: Sequence[ValidationIssue]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "severity": issue.severity,
                "check": issue.check,
                "date": issue.date,
                "message": issue.message,
            }
            for issue in issues
        ]
    )


def _assessment(validation: pd.DataFrame) -> str:
    error_count = int((validation["severity"] == "ERROR").sum())
    warning_count = int((validation["severity"] == "WARNING").sum())
    if error_count:
        return "LOW"
    if warning_count > 3:
        return "MEDIUM"
    return "HIGH"
