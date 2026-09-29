"""Raw-price restoration and mechanical ownership-equivalent reconstruction."""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

from .config import SHARE_CHANGING_TYPES
from .models import ValidationIssue

def _event_cumulative_factor(index: pd.DatetimeIndex, actions: pd.DataFrame) -> pd.Series:
    valid = actions[
        actions["included_in_reconstruction"].fillna(False)
        & actions["action_type"].isin(SHARE_CHANGING_TYPES)
        & pd.to_numeric(actions["share_multiplier"], errors="coerce").gt(0)
        & actions["date"].between(index.min(), index.max())
    ].copy()
    if valid.empty:
        return pd.Series(1.0, index=index, name="cumulative_split_factor")
    event_factors = valid.groupby("date")["share_multiplier"].prod().astype(float)
    union = index.union(pd.DatetimeIndex(event_factors.index)).sort_values()
    daily_events = pd.Series(1.0, index=union)
    daily_events.loc[event_factors.index] = event_factors.values
    cumulative = daily_events.cumprod().reindex(index, method="ffill").fillna(1.0)
    cumulative.name = "cumulative_split_factor"
    return cumulative


def _nearest_trade_pair(index: pd.DatetimeIndex, event_date: pd.Timestamp) -> tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    before = index[index < event_date]
    after = index[index >= event_date]
    return (before.max() if len(before) else None, after.min() if len(after) else None)


def detect_provider_close_basis(
    provider_close: pd.Series, split_actions: pd.DataFrame
) -> tuple[str, dict[str, Any]]:
    """Infer whether provider Close is already normalized for splits.

    Yahoo commonly normalizes historical Close for later splits even with
    auto_adjust=False.  We compare observed jumps with both hypotheses.
    """
    samples = []
    for _, action in split_actions.iterrows():
        multiplier = float(action["share_multiplier"])
        if not np.isfinite(multiplier) or multiplier <= 0 or math.isclose(multiplier, 1.0):
            continue
        pre_date, post_date = _nearest_trade_pair(provider_close.index, pd.Timestamp(action["date"]))
        if pre_date is None or post_date is None:
            continue
        pre = float(provider_close.loc[pre_date])
        post = float(provider_close.loc[post_date])
        if pre <= 0 or post <= 0:
            continue
        observed_ratio = post / pre
        adjusted_error = abs(math.log(observed_ratio))
        as_traded_error = abs(math.log(observed_ratio * multiplier))
        samples.append(
            {
                "date": pd.Timestamp(action["date"]),
                "multiplier": multiplier,
                "observed_ratio": observed_ratio,
                "adjusted_error": adjusted_error,
                "as_traded_error": as_traded_error,
            }
        )
    if not samples:
        return "indeterminate_no_splits", {"samples": [], "reason": "No usable split boundary."}
    adjusted_score = float(np.median([sample["adjusted_error"] for sample in samples]))
    as_traded_score = float(np.median([sample["as_traded_error"] for sample in samples]))
    basis = "split_adjusted" if adjusted_score <= as_traded_score else "as_traded"
    return basis, {
        "samples": samples,
        "adjusted_score": adjusted_score,
        "as_traded_score": as_traded_score,
    }


def prepare_price_data(
    history: pd.DataFrame, actions: pd.DataFrame
) -> tuple[pd.DataFrame, str, dict[str, Any], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    renamed = {
        "Open": "provider_open",
        "High": "provider_high",
        "Low": "provider_low",
        "Close": "provider_close",
        "Adj Close": "adjusted_close",
        "Volume": "volume",
        "Dividends": "dividend",
        "Stock Splits": "provider_split_factor",
    }
    frame = history.rename(columns=renamed).copy()
    for column in renamed.values():
        if column not in frame.columns:
            frame[column] = np.nan if column != "provider_split_factor" else 0.0
    for column in (
        "provider_open",
        "provider_high",
        "provider_low",
        "provider_close",
        "adjusted_close",
        "volume",
        "dividend",
        "provider_split_factor",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    missing_close = int(frame["provider_close"].isna().sum())
    invalid_close = int((frame["provider_close"] <= 0).fillna(False).sum())
    if missing_close or invalid_close:
        issues.append(
            ValidationIssue(
                "WARNING",
                "excluded_price_rows",
                f"Excluded {missing_close} missing and {invalid_close} non-positive Close rows from calculations.",
            )
        )
    frame = frame[frame["provider_close"].notna() & frame["provider_close"].gt(0)].copy()
    if frame.empty:
        raise ValueError("No positive provider Close observations remain after validation.")

    split_actions = actions[
        actions["included_in_reconstruction"].fillna(False)
        & actions["action_type"].isin(SHARE_CHANGING_TYPES)
        & pd.to_numeric(actions["share_multiplier"], errors="coerce").gt(0)
    ].copy()
    cumulative = _event_cumulative_factor(frame.index, split_actions)
    final_factor = float(cumulative.iloc[-1])
    basis, diagnostics = detect_provider_close_basis(frame["provider_close"], split_actions)
    if basis == "split_adjusted":
        future_factor = final_factor / cumulative
        issues.append(
            ValidationIssue(
                "INFO",
                "provider_close_basis",
                "Provider Close behaves as retrospectively split-normalized; as-traded OHLC was reconstructed with future split factors.",
            )
        )
    else:
        future_factor = pd.Series(1.0, index=frame.index)
        message = (
            "No split boundary was available; provider Close is used as the as-traded series."
            if basis.startswith("indeterminate")
            else "Provider Close behaves as an as-traded series around recorded splits."
        )
        issues.append(ValidationIssue("INFO", "provider_close_basis", message))

    for source, target in (
        ("provider_open", "open"),
        ("provider_high", "high"),
        ("provider_low", "low"),
        ("provider_close", "raw_close"),
    ):
        frame[target] = frame[source] * future_factor
    if frame["adjusted_close"].notna().sum() == 0:
        frame["adjusted_close"] = frame["provider_close"]
        issues.append(
            ValidationIssue(
                "WARNING",
                "adjusted_close_missing",
                "Provider-adjusted Close was unavailable; provider Close is shown in its place and total-return interpretation is disabled.",
            )
        )
    frame["split_factor"] = 1.0
    for date, factor in split_actions.groupby("date")["share_multiplier"].prod().items():
        matching = frame.index[frame.index >= pd.Timestamp(date)]
        if len(matching):
            frame.loc[matching[0], "split_factor"] *= float(factor)
    frame["cumulative_split_factor"] = cumulative
    frame["no_split_close"] = frame["raw_close"] * frame["cumulative_split_factor"]
    frame["daily_return"] = frame["no_split_close"].pct_change(fill_method=None)
    running_max = frame["no_split_close"].cummax()
    frame["drawdown"] = frame["no_split_close"] / running_max - 1.0
    frame["future_split_factor_used"] = future_factor

    cumulative_by_action = 1.0
    for idx in actions.sort_values("date").index:
        row = actions.loc[idx]
        if (
            bool(row["included_in_reconstruction"])
            and row["action_type"] in SHARE_CHANGING_TYPES
            and pd.notna(row["share_multiplier"])
            and frame.index.min() <= row["date"] <= frame.index.max()
        ):
            cumulative_by_action *= float(row["share_multiplier"])
        actions.loc[idx, "cumulative_multiplier"] = cumulative_by_action
    return frame, basis, diagnostics, issues
