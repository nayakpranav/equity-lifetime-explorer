"""Conservative presentation status for the latest daily relative-volume bar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from .formatting import format_multiple
from .models import AnalysisResult


# Yahoo exchange codes are not MICs. XNYS is a regular US-equity-session
# calendar proxy for the listed US venues below; unknown venues stay unverified.
_CALENDARS = {
    "NYQ": ("XNYS", "America/New_York"),
    "NMS": ("XNYS", "America/New_York"),
    "NGM": ("XNYS", "America/New_York"),
    "NCM": ("XNYS", "America/New_York"),
    "NASDAQGS": ("XNYS", "America/New_York"),
    "NASDAQGM": ("XNYS", "America/New_York"),
    "NASDAQCM": ("XNYS", "America/New_York"),
    "NYSE": ("XNYS", "America/New_York"),
    "NASDAQ": ("XNYS", "America/New_York"),
    "XETR": ("XETR", "Europe/Berlin"),
    "XETRA": ("XETR", "Europe/Berlin"),
    "GER": ("XETR", "Europe/Berlin"),
}


@dataclass(frozen=True)
class RvolAssessment:
    status: str  # completed, preliminary, unverified, unavailable
    value: float | None
    session_date: pd.Timestamp | None
    detail: str

    @property
    def headline(self) -> tuple[str, str]:
        if self.status == "preliminary":
            return "Preliminary intraday RVOL", format_multiple(self.value)
        if self.status == "completed":
            return "Latest completed-session RVOL", format_multiple(self.value)
        if self.status == "unverified":
            return "Latest RVOL · status unverified", "Not available"
        return "Latest RVOL", "Not available"


def assess_latest_rvol(
    result: AnalysisResult,
    *,
    calendar_provider: Callable[[str], Any] | None = None,
) -> RvolAssessment:
    """Classify the latest *observed* bar using its retrieval time, not wall time.

    Daily Yahoo bars have no finality flag. A bar is called completed only when
    a recognized calendar confirms its session and retrieval occurred on a
    later local calendar date. Same-session post-close bars remain unverified.
    """
    if result.prices.empty or "relative_volume_20" not in result.prices:
        return RvolAssessment("unavailable", None, None, "RVOL is unavailable from the provider observations.")
    latest = result.prices.iloc[-1].get("relative_volume_20")
    try:
        value = float(latest)
    except (TypeError, ValueError, OverflowError):
        value = float("nan")
    if not np.isfinite(value):
        return RvolAssessment("unavailable", None, result.prices.index[-1], "RVOL is unavailable because volume or its 20-session lookback is missing.")
    session_date = pd.Timestamp(result.prices.index[-1]).normalize()
    exchange = str(result.metadata.exchange or "").upper()
    calendar_spec = _CALENDARS.get(exchange)
    if calendar_spec is None:
        return RvolAssessment("unverified", value, session_date, "The exchange session calendar is not mapped; the latest bar's completeness cannot be verified.")
    retrieved = pd.to_datetime(result.provenance.retrieval_timestamp_utc, errors="coerce", utc=True)
    if pd.isna(retrieved):
        return RvolAssessment("unverified", value, session_date, "The provider retrieval timestamp is unavailable; session completeness cannot be verified.")
    calendar_code, timezone_name = calendar_spec
    try:
        if calendar_provider is None:
            import exchange_calendars as xcals

            calendar_provider = xcals.get_calendar
        calendar = calendar_provider(calendar_code)
        if not calendar.is_session(session_date):
            return RvolAssessment("unverified", value, session_date, "The latest provider date is not a recognized exchange session.")
        local_retrieval_date = retrieved.tz_convert(timezone_name).date()
        if local_retrieval_date > session_date.date():
            return RvolAssessment("completed", value, session_date, "Calendar-inferred completed session; the provider does not certify daily-bar finality.")
        if local_retrieval_date < session_date.date():
            return RvolAssessment("unverified", value, session_date, "The observation date follows its retrieval timestamp.")
        session_open = calendar.session_open(session_date)
        session_close = calendar.session_close(session_date)
        if session_open <= retrieved < session_close:
            return RvolAssessment("preliminary", value, session_date, "The bar was retrieved before the exchange's scheduled session close; RVOL compares partial volume with completed sessions.")
        return RvolAssessment("unverified", value, session_date, "Same-day pre-open or post-close provider data has no finality flag; the latest RVOL is withheld from a completed-session headline.")
    except (ImportError, KeyError, ValueError, TypeError, OverflowError):
        return RvolAssessment("unverified", value, session_date, "The exchange session schedule could not be verified; the latest RVOL is withheld from a completed-session headline.")
