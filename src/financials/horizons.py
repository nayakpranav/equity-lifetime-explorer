"""Display-only fiscal-period filtering; full analytical data is never mutated."""

from __future__ import annotations

import pandas as pd


HORIZONS = ("1Y", "3Y", "5Y", "10Y", "MAX")


def filter_financial_horizon(frame: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if horizon not in HORIZONS:
        raise ValueError("Unknown financial horizon")
    if frame.empty or horizon == "MAX":
        return frame.copy()
    ends = pd.to_datetime(frame["period_end"], errors="coerce")
    if ends.notna().sum() == 0:
        return frame.iloc[0:0].copy()
    cutoff = ends.max() - pd.DateOffset(years=int(horizon[:-1]))
    return frame.loc[ends.ge(cutoff)].copy()
