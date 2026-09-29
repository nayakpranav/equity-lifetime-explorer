"""Lifetime price, return, CAGR, volatility, and drawdown analytics."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from .config import CALENDAR_DAYS_PER_YEAR, SHARE_CHANGING_TYPES, TRADING_DAYS_PER_YEAR
from .models import CompanyMetadata

def _period_return(series: pd.Series, years: int) -> Optional[float]:
    clean = series.dropna().sort_index()
    if clean.empty:
        return None
    end_date = clean.index[-1]
    target = end_date - pd.DateOffset(years=years)
    if target < clean.index[0]:
        return None
    position = clean.index.searchsorted(target, side="left")
    if position >= len(clean):
        return None
    start_date = clean.index[position]
    elapsed = (end_date - start_date).days / CALENDAR_DAYS_PER_YEAR
    if elapsed <= 0 or clean.iloc[position] <= 0:
        return None
    return float((clean.iloc[-1] / clean.iloc[position]) ** (1.0 / elapsed) - 1.0)


def _drawdown_episode_metrics(drawdown: pd.Series) -> tuple[Optional[int], int]:
    longest = 0
    start: Optional[pd.Timestamp] = None
    episodes_20 = 0
    in_20 = False
    for date, value in drawdown.items():
        if value < 0 and start is None:
            start = date
        if value >= 0 and start is not None:
            longest = max(longest, (date - start).days)
            start = None
        if value <= -0.20 and not in_20:
            episodes_20 += 1
            in_20 = True
        elif value > -0.20:
            in_20 = False
    if start is not None:
        longest = max(longest, (drawdown.index[-1] - start).days)
    return (longest if longest else None), episodes_20


def calculate_metrics(
    prices: pd.DataFrame, actions: pd.DataFrame, metadata: CompanyMetadata
) -> dict[str, Any]:
    series = prices["no_split_close"].dropna()
    raw = prices["raw_close"].dropna()
    adjusted = prices["adjusted_close"].dropna()
    first_date, last_date = series.index[0], series.index[-1]
    years = (last_date - first_date).days / CALENDAR_DAYS_PER_YEAR
    lifetime_multiple = float(series.iloc[-1] / series.iloc[0]) if series.iloc[0] > 0 else None
    cagr = (
        float(lifetime_multiple ** (1 / years) - 1)
        if lifetime_multiple is not None and lifetime_multiple > 0 and years > 0
        else None
    )
    drawdown = prices["drawdown"].dropna()
    trough_date = drawdown.idxmin()
    peak_date = series.loc[:trough_date].idxmax()
    peak_value = float(series.loc[peak_date])
    recovered = series.loc[trough_date:]
    recovered = recovered[recovered >= peak_value]
    recovery_date = recovered.index[0] if len(recovered) else None
    annual_returns = series.groupby(series.index.year).last().pct_change(fill_method=None).dropna()
    daily_returns = prices["daily_return"].replace([np.inf, -np.inf], np.nan).dropna()
    annualized_vol = float(daily_returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(daily_returns) > 1 else None
    all_time_high_date = raw.idxmax()
    all_time_low_slice = raw.iloc[1:] if len(raw) > 1 else raw
    all_time_low_date = all_time_low_slice.idxmin()
    no_split_high_date = series.idxmax()
    share_actions = actions[
        actions["included_in_reconstruction"].fillna(False)
        & actions["action_type"].isin(SHARE_CHANGING_TYPES)
        & actions["date"].between(first_date, last_date)
    ]
    final_factor = float(prices["cumulative_split_factor"].iloc[-1])
    dividends = prices["dividend"].fillna(0.0)
    ttm_start = last_date - pd.DateOffset(years=1)
    ttm_dividend = float(dividends.loc[dividends.index > ttm_start].sum())
    recent_year = int(last_date.year)
    recent_annual_dividend = float(dividends.loc[dividends.index.year == recent_year].sum())
    if recent_annual_dividend == 0 and recent_year - 1 in set(dividends.index.year):
        recent_annual_dividend = float(dividends.loc[dividends.index.year == recent_year - 1].sum())
    high_52_start = last_date - pd.Timedelta(365, unit="D")
    high_52 = float(raw.loc[raw.index >= high_52_start].max())
    longest_drawdown_days, drawdown_20_count = _drawdown_episode_metrics(drawdown)
    total_return_multiple = (
        float(adjusted.iloc[-1] / adjusted.iloc[0])
        if len(adjusted) and adjusted.iloc[0] > 0
        else None
    )
    return {
        "company_name": metadata.name,
        "ticker": metadata.ticker,
        "exchange": metadata.exchange,
        "currency": metadata.currency,
        "first_available_date": first_date,
        "latest_available_date": last_date,
        "years_of_history": years,
        "first_raw_close": float(raw.iloc[0]),
        "latest_raw_close": float(raw.iloc[-1]),
        "latest_no_split_equivalent": float(series.iloc[-1]),
        "first_no_split_close": float(series.iloc[0]),
        "cumulative_share_multiplier": final_factor,
        "original_share_equivalent_current_shares": final_factor,
        "lifetime_price_return": lifetime_multiple - 1 if lifetime_multiple is not None else None,
        "lifetime_price_multiple": lifetime_multiple,
        "lifetime_cagr": cagr,
        "provider_adjusted_total_return_multiple": total_return_multiple,
        "all_time_high_raw": float(raw.max()),
        "all_time_high_raw_date": all_time_high_date,
        "all_time_low_raw_after_first": float(all_time_low_slice.min()),
        "all_time_low_raw_date": all_time_low_date,
        "all_time_high_no_split": float(series.max()),
        "all_time_high_no_split_date": no_split_high_date,
        "maximum_drawdown": float(drawdown.min()),
        "maximum_drawdown_peak": peak_date,
        "maximum_drawdown_trough": trough_date,
        "maximum_drawdown_recovery": recovery_date,
        "annualized_volatility": annualized_vol,
        "best_calendar_year": int(annual_returns.idxmax()) if len(annual_returns) else None,
        "best_calendar_year_return": float(annual_returns.max()) if len(annual_returns) else None,
        "worst_calendar_year": int(annual_returns.idxmin()) if len(annual_returns) else None,
        "worst_calendar_year_return": float(annual_returns.min()) if len(annual_returns) else None,
        "return_1y": _period_return(series, 1),
        "cagr_3y": _period_return(series, 3),
        "cagr_5y": _period_return(series, 5),
        "cagr_10y": _period_return(series, 10),
        "cagr_20y": _period_return(series, 20),
        "high_52_week": high_52,
        "percent_from_52_week_high": float(raw.iloc[-1] / high_52 - 1) if high_52 > 0 else None,
        "longest_drawdown_days": longest_drawdown_days,
        "drawdowns_over_20_percent": drawdown_20_count,
        "forward_split_count": int((share_actions["action_type"] == "stock_split").sum()),
        "reverse_split_count": int((share_actions["action_type"] == "reverse_split").sum()),
        "bonus_issue_count": int((share_actions["action_type"] == "bonus_issue").sum()),
        "lifetime_cash_dividends_per_current_share": float(dividends.sum()),
        "recent_annual_dividend": recent_annual_dividend,
        "trailing_12_month_dividend": ttm_dividend,
        "indicated_yield_from_ttm": ttm_dividend / float(raw.iloc[-1]) if raw.iloc[-1] > 0 else None,
    }
