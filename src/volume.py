"""Volume and liquidity analytics preserved from Colab v5."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .models import ValidationIssue

def add_volume_analytics(
    prices: pd.DataFrame,
) -> tuple[pd.DataFrame, list[ValidationIssue]]:
    """Attach split-aware liquidity measures without altering provider volume observations."""
    frame = prices.copy()
    issues: list[ValidationIssue] = []
    if "volume" not in frame.columns:
        frame["volume"] = np.nan

    provider_volume = pd.to_numeric(frame["volume"], errors="coerce")
    frame["volume"] = provider_volume
    finite = pd.Series(np.isfinite(provider_volume.to_numpy(dtype=float)), index=frame.index)
    negative = provider_volume.lt(0).fillna(False)
    missing = provider_volume.isna()
    nonfinite = provider_volume.notna() & ~finite
    valid_volume = provider_volume.where(finite & ~negative)

    # Compare each session with the previous completed trading sessions. This avoids
    # allowing today's observation to dilute its own relative-volume denominator.
    frame["volume_ma_20"] = valid_volume.shift(1).rolling(20, min_periods=20).mean()
    frame["volume_ma_50"] = valid_volume.shift(1).rolling(50, min_periods=50).mean()
    denominator = frame["volume_ma_20"].where(frame["volume_ma_20"].gt(0))
    frame["relative_volume_20"] = valid_volume / denominator
    frame["dollar_volume"] = frame["raw_close"] * valid_volume
    frame["dollar_volume_ma_20"] = frame["dollar_volume"].shift(1).rolling(20, min_periods=20).mean()

    returns = pd.to_numeric(frame.get("daily_return"), errors="coerce")
    frame["volume_direction"] = np.select(
        [returns.gt(0), returns.lt(0)],
        ["Advance", "Decline"],
        default="Flat",
    )
    elevated = frame["relative_volume_20"].ge(2.0).fillna(False)
    frame["volume_event"] = np.select(
        [elevated & returns.gt(0), elevated & returns.lt(0), elevated],
        ["High-volume advance", "High-volume decline", "Extreme-volume session"],
        default="Normal participation",
    )

    valid_count = int(valid_volume.notna().sum())
    if valid_count == 0:
        issues.append(ValidationIssue(
            "INFO", "volume_availability",
            "Volume data unavailable from configured provider; volume panels and analytics are disabled.",
        ))
        return frame, issues

    issues.append(ValidationIssue(
        "PASS", "volume_availability",
        f"Provider volume is available for {valid_count:,} observations.",
    ))
    if missing.any():
        issues.append(ValidationIssue(
            "INFO", "missing_volume",
            f"{int(missing.sum()):,} observations have missing provider volume; rolling measures remain unavailable across incomplete lookbacks.",
        ))
    else:
        issues.append(ValidationIssue("PASS", "missing_volume", "No provider volume observations are missing."))
    if negative.any():
        issues.append(ValidationIssue(
            "WARNING", "negative_volume",
            f"{int(negative.sum()):,} negative provider volume observations were excluded from derived volume measures.",
        ))
    else:
        issues.append(ValidationIssue("PASS", "negative_volume", "No negative provider volume observations were found."))
    if nonfinite.any():
        issues.append(ValidationIssue(
            "WARNING", "nonfinite_volume",
            f"{int(nonfinite.sum()):,} non-finite provider volume observations were excluded from derived volume measures.",
        ))
    else:
        issues.append(ValidationIssue("PASS", "nonfinite_volume", "No infinite provider volume observations were found."))

    expected_ma20 = valid_volume.shift(1).rolling(20, min_periods=20).mean()
    rolling_ok = np.allclose(
        frame["volume_ma_20"].to_numpy(dtype=float),
        expected_ma20.to_numpy(dtype=float),
        equal_nan=True,
    )
    issues.append(ValidationIssue(
        "PASS" if rolling_ok else "ERROR",
        "volume_rolling_integrity",
        "20-session average volume uses only the previous 20 completed trading sessions."
        if rolling_ok else "20-session average volume failed its deterministic integrity check.",
    ))
    expected_dollar = frame["raw_close"] * valid_volume
    dollar_ok = np.allclose(
        frame["dollar_volume"].to_numpy(dtype=float),
        expected_dollar.to_numpy(dtype=float),
        equal_nan=True,
    )
    issues.append(ValidationIssue(
        "PASS" if dollar_ok else "ERROR",
        "dollar_volume_integrity",
        "Dollar Volume equals reconstructed raw as-traded close multiplied by provider share volume."
        if dollar_ok else "Dollar Volume failed its raw-close × provider-volume integrity check.",
    ))
    zero_count = int(valid_volume.eq(0).sum())
    if zero_count:
        issues.append(ValidationIssue(
            "INFO", "zero_volume",
            f"{zero_count:,} zero-volume observations were retained as provider facts; zeros are not automatically treated as errors.",
        ))
    return frame, issues


def build_volume_event_table(prices: pd.DataFrame) -> pd.DataFrame:
    """Create a rank-explicit analytical table; no ranking dimensions are mixed."""
    columns = [
        "date", "raw_close", "daily_return", "volume", "volume_ma_20",
        "volume_ma_50", "relative_volume_20", "dollar_volume",
        "dollar_volume_ma_20", "direction", "context",
        "relative_volume_rank", "share_volume_rank", "dollar_volume_rank",
    ]
    if "volume" not in prices.columns or prices["volume"].notna().sum() == 0:
        return pd.DataFrame(columns=columns)
    events = prices[
        [
            "raw_close", "daily_return", "volume", "volume_ma_20", "volume_ma_50",
            "relative_volume_20", "dollar_volume", "dollar_volume_ma_20",
            "volume_direction", "volume_event",
        ]
    ].copy()
    events.index.name = "date"
    events = events.reset_index().rename(
        columns={"volume_direction": "direction", "volume_event": "context"}
    )
    events["relative_volume_rank"] = events["relative_volume_20"].rank(
        method="min", ascending=False, na_option="keep"
    ).astype("Int64")
    events["share_volume_rank"] = events["volume"].rank(
        method="min", ascending=False, na_option="keep"
    ).astype("Int64")
    events["dollar_volume_rank"] = events["dollar_volume"].rank(
        method="min", ascending=False, na_option="keep"
    ).astype("Int64")
    return events[columns]


def calculate_volume_metrics(prices: pd.DataFrame) -> dict[str, Any]:
    if "volume" not in prices.columns or prices["volume"].notna().sum() == 0:
        return {
            "volume_data_available": False,
            "latest_volume": None,
            "volume_ma_20": None,
            "latest_relative_volume_20": None,
            "latest_dollar_volume": None,
            "highest_relative_volume_20": None,
            "highest_dollar_volume": None,
        }
    latest = prices.iloc[-1]
    return {
        "volume_data_available": True,
        "latest_volume": latest.get("volume"),
        "volume_ma_20": latest.get("volume_ma_20"),
        "latest_relative_volume_20": latest.get("relative_volume_20"),
        "latest_dollar_volume": latest.get("dollar_volume"),
        "highest_relative_volume_20": prices["relative_volume_20"].max(skipna=True),
        "highest_dollar_volume": prices["dollar_volume"].max(skipna=True),
    }
