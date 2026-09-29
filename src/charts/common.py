"""Shared chart helpers and event-preserving display optimization."""

from __future__ import annotations

import copy
from typing import Iterable, Mapping

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ..config import PROVIDER_NAME
from ..formatting import currency_parts
from ..models import AnalysisResult

def downsample_for_plot(
    prices: pd.DataFrame,
    action_dates: Iterable[pd.Timestamp],
    max_points: int = 6000,
) -> pd.DataFrame:
    """Min/max envelope sampling that preserves endpoints and action dates.

    The canonical daily frame remains untouched and is always used for analytics/export.
    """
    if len(prices) <= max_points:
        return prices.copy()
    bucket_count = max(1, max_points // 4)
    positions = np.arange(len(prices))
    selected: set[int] = {0, len(prices) - 1}
    for bucket in np.array_split(positions, bucket_count):
        if len(bucket) == 0:
            continue
        block = prices.iloc[bucket]
        selected.update(
            {
                int(bucket[0]),
                int(bucket[-1]),
                int(prices.index.get_loc(block["no_split_close"].idxmin())),
                int(prices.index.get_loc(block["no_split_close"].idxmax())),
            }
        )
    for event_date in action_dates:
        position = prices.index.searchsorted(pd.Timestamp(event_date), side="left")
        if position < len(prices):
            selected.add(int(position))
        if position > 0:
            selected.add(int(position - 1))
    return prices.iloc[sorted(selected)].copy()


def _event_points(
    plot_frame: pd.DataFrame,
    actions: pd.DataFrame,
    value_column: str,
    action_types: set[str],
) -> tuple[list[pd.Timestamp], list[float], list[str]]:
    xs: list[pd.Timestamp] = []
    ys: list[float] = []
    labels: list[str] = []
    relevant = actions[actions["action_type"].isin(action_types)].copy()
    for _, action in relevant.iterrows():
        date = pd.Timestamp(action["date"])
        position = plot_frame.index.searchsorted(date, side="left")
        if position >= len(plot_frame):
            continue
        trade_date = plot_frame.index[position]
        y = plot_frame.iloc[position][value_column]
        if pd.isna(y) or y <= 0:
            continue
        cash_text = ""
        if pd.notna(action.get("cash_amount")):
            if action.get("action_type") in {"cash_dividend", "special_dividend"} and PROVIDER_NAME in str(action.get("source")):
                cash_text = (
                    f"<br>Provider-reported dividend: {action['cash_amount']:,.4g} "
                    f"{action.get('currency') or ''} per current-share-equivalent basis"
                )
            else:
                cash_text = f"<br>Cash amount: {action['cash_amount']:,.4g} {action.get('currency') or ''}"
        multiplier_text = ""
        if pd.notna(action.get("share_multiplier")):
            multiplier_text = (
                f"<br>Share multiplier: ×{action['share_multiplier']:,.6g}"
                f"<br>Cumulative multiplier: ×{action['cumulative_multiplier']:,.6g}"
            )
        labels.append(
            f"<b>{action['event']}</b><br>Effective: {date:%d %b %Y}"
            f"<br>Ratio: {action['ratio']}{multiplier_text}{cash_text}"
            f"<br>Source: {action['source']}<br>Confidence: {action['confidence']}"
            f"<br>{action['notes']}"
        )
        xs.append(trade_date)
        ys.append(float(y))
    return xs, ys, labels


def _price_trace(
    frame: pd.DataFrame,
    column: str,
    name: str,
    color: str,
    currency: str,
    visible: bool,
) -> go.Scatter:
    custom = np.column_stack(
        [
            frame["raw_close"].to_numpy(),
            frame["no_split_close"].to_numpy(),
            frame["adjusted_close"].to_numpy(),
            frame["daily_return"].to_numpy(),
            frame["cumulative_split_factor"].to_numpy(),
            frame["volume"].to_numpy(),
        ]
    )
    return go.Scattergl(
        x=frame.index,
        y=frame[column],
        name=name,
        mode="lines",
        line={"color": color, "width": 2.2},
        customdata=custom,
        visible=visible,
        hovertemplate=(
            "<b>%{x|%d %b %Y}</b>"
            f"<br>Raw as-traded: {currency} %{{customdata[0]:,.2f}}"
            f"<br>No-split equivalent: {currency} %{{customdata[1]:,.2f}}"
            f"<br>Provider adjusted: {currency} %{{customdata[2]:,.2f}}"
            "<br>Daily price return: %{customdata[3]:+.2%}"
            "<br>Cumulative factor: %{customdata[4]:,.6g}×"
            "<br>Volume: %{customdata[5]:,.4s}<extra>" + name + "</extra>"
        ),
    )


def _volume_available(prices: pd.DataFrame) -> bool:
    return "volume" in prices.columns and bool(pd.to_numeric(prices["volume"], errors="coerce").notna().any())


def _volume_bar_colors(frame: pd.DataFrame, palette: Mapping[str, str]) -> np.ndarray:
    returns = pd.to_numeric(frame.get("daily_return"), errors="coerce")
    return np.where(
        returns.gt(0), palette["volume_up"],
        np.where(returns.lt(0), palette["volume_down"], palette["volume_flat"]),
    )


def _volume_customdata(frame: pd.DataFrame) -> np.ndarray:
    fields = [
        "volume", "volume_ma_20", "volume_ma_50", "relative_volume_20",
        "dollar_volume", "raw_close", "daily_return",
    ]
    return np.column_stack([
        pd.to_numeric(frame.get(field, pd.Series(np.nan, index=frame.index)), errors="coerce").to_numpy()
        for field in fields
    ])


def _volume_hovertemplate(currency: str, name: str = "Daily Share Volume") -> str:
    prefix, suffix = currency_parts(currency)
    return (
        "<b>%{x|%d %b %Y}</b>"
        "<br>Share volume: %{customdata[0]:,.4s}"
        "<br>20D avg: %{customdata[1]:,.4s}"
        "<br>50D avg: %{customdata[2]:,.4s}"
        "<br>Relative volume: %{customdata[3]:.2f}×"
        f"<br>Dollar volume: {prefix}%{{customdata[4]:,.4s}}{suffix}"
        f"<br>Raw close: {prefix}%{{customdata[5]:,.2f}}{suffix}"
        "<br>Daily price return: %{customdata[6]:+.2%}"
        f"<extra>{name}</extra>"
    )


def display_result(result: AnalysisResult, max_points: int = 5000) -> AnalysisResult:
    """Return a shallow result copy with event-preserving display data only."""
    if len(result.prices) <= max_points:
        return result
    dates = list(pd.to_datetime(result.actions.get("date", pd.Series(dtype="datetime64[ns]"))).dropna())
    if not result.volume_events.empty and "relative_volume_rank" in result.volume_events:
        top = result.volume_events.dropna(subset=["relative_volume_rank"]).nsmallest(15, "relative_volume_rank")
        dates.extend(pd.to_datetime(top["date"]).tolist())
    for key in (
        "all_time_high_raw_date", "all_time_low_raw_date", "all_time_high_no_split_date",
        "maximum_drawdown_peak", "maximum_drawdown_trough", "maximum_drawdown_recovery",
    ):
        value = result.metrics.get(key)
        if value is not None and not pd.isna(value):
            dates.append(pd.Timestamp(value))
    rendered = copy.copy(result)
    rendered.prices = downsample_for_plot(result.prices, dates, max_points=max_points)
    return rendered
