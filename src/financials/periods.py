"""Issuer fiscal-period classification from actual dates and stated year end."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd


@dataclass(frozen=True)
class FiscalPeriod:
    fiscal_year: int | None
    fiscal_quarter: int | None
    period_type: str
    reporting_frequency: str


def _quarter_anchor(end: pd.Timestamp, fiscal_year_end: str) -> tuple[int, int, pd.Timestamp] | None:
    month, day = int(fiscal_year_end[:2]), int(fiscal_year_end[2:])
    candidates: list[tuple[int, int, pd.Timestamp]] = []
    for fiscal_year in range(end.year - 1, end.year + 3):
        try:
            year_end = pd.Timestamp(fiscal_year, month, day)
        except ValueError:
            year_end = pd.Timestamp(fiscal_year, month, 1) + pd.offsets.MonthEnd(0)
        for quarter in (1, 2, 3, 4):
            anchor = year_end - pd.DateOffset(months=3 * (4 - quarter))
            candidates.append((fiscal_year, quarter, anchor))
    best = min(candidates, key=lambda item: abs((end - item[2]).days))
    return best if abs((end - best[2]).days) <= 14 else None


def classify_period(start: str | None, end: str, fiscal_year_end: str, form: str | None) -> FiscalPeriod:
    end_date = pd.Timestamp(end)
    nearest = _quarter_anchor(end_date, fiscal_year_end)
    if nearest is None:
        return FiscalPeriod(None, None, "unknown", "unknown")
    fiscal_year, quarter, _ = nearest
    if not start:
        frequency = "annual" if form in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "ESEF"} else "quarterly"
        return FiscalPeriod(fiscal_year, quarter, "instant", frequency)
    start_date = pd.Timestamp(start)
    days = (end_date - start_date).days + 1
    quarter_end = nearest[2]
    year_end = quarter_end + pd.DateOffset(months=3 * (4 - quarter))
    fiscal_start = year_end - pd.DateOffset(years=1) + timedelta(days=1)
    if quarter == 4 and 340 <= days <= 380 and abs((start_date - fiscal_start).days) <= 16:
        return FiscalPeriod(fiscal_year, quarter, "annual", "annual")
    if 75 <= days <= 110:
        previous_end = quarter_end - pd.DateOffset(months=3)
        if abs((start_date - (previous_end + timedelta(days=1))).days) <= 16:
            return FiscalPeriod(fiscal_year, quarter, "quarter", "quarterly")
    if quarter in {2, 3} and abs((start_date - fiscal_start).days) <= 16:
        if (quarter == 2 and 145 <= days <= 210) or (quarter == 3 and 235 <= days <= 305):
            return FiscalPeriod(fiscal_year, quarter, "ytd", "quarterly")
    return FiscalPeriod(fiscal_year, quarter, "unknown", "unknown")
