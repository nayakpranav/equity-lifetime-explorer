"""Dividends & Total Return Plotly workspace."""

from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..config import THEMES
from ..formatting import currency_parts
from ..models import AnalysisResult
from .common import display_result


DIVIDEND_HORIZONS = {"1Y": 1, "5Y": 5, "10Y": 10, "MAX": None}


def dividend_display_result(
    result: AnalysisResult,
    horizon: str = "MAX",
    *,
    max_points: int = 5000,
) -> AnalysisResult:
    """Return a display-only horizon slice while preserving structural metrics."""
    selected = str(horizon).upper()
    if selected not in DIVIDEND_HORIZONS:
        raise ValueError("horizon must be 1Y, 5Y, 10Y, or MAX")
    if selected == "MAX" or result.prices.empty:
        return display_result(result, max_points=max_points)
    latest = pd.Timestamp(result.prices.index.max())
    start = latest - pd.DateOffset(years=DIVIDEND_HORIZONS[selected])
    filtered = copy.copy(result)
    filtered.prices = result.prices.loc[result.prices.index >= start].copy()
    if not result.annual_dividends.empty:
        years = pd.to_numeric(result.annual_dividends["year"], errors="coerce")
        filtered.annual_dividends = result.annual_dividends.loc[years >= start.year].copy()
    if not result.dividend_events.empty:
        event_dates = pd.to_datetime(result.dividend_events["date"], errors="coerce")
        filtered.dividend_events = result.dividend_events.loc[event_dates >= start].copy()
    return display_result(filtered, max_points=max_points)

def _empty_dividend_figure(result: AnalysisResult, theme: str) -> go.Figure:
    palette = THEMES[theme]
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark" if theme == "dark" else "plotly_white",
        height=420, paper_bgcolor=palette["paper"], plot_bgcolor=palette["plot"],
        font={"family": "Inter, Arial, sans-serif", "color": palette["text"]},
        title=f"<b>{result.metadata.name.upper()} — DIVIDEND & TOTAL RETURN EXPLORER</b>",
    )
    fig.add_annotation(
        x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
        text="No provider-reported cash-dividend history is available for this security.",
        font={"size": 16, "color": palette["muted"]},
    )
    return fig


def build_dividend_total_return_figure(
    result: AnalysisResult,
    *,
    theme: str = "dark",
) -> go.Figure:
    theme = theme.lower()
    if theme not in THEMES:
        raise ValueError("theme must be dark or light")
    if result.dividend_status == "NONE" or result.dividend_events.empty:
        return _empty_dividend_figure(result, theme)
    palette = THEMES[theme]
    prices = result.prices
    annual = result.annual_dividends.copy()
    events = result.dividend_events.copy()
    metrics = result.dividend_metrics
    currency = result.metadata.currency
    prefix, suffix = currency_parts(currency)

    fig = make_subplots(
        rows=4, cols=1, vertical_spacing=0.09,
        row_heights=[0.28, 0.22, 0.27, 0.23],
        specs=[
            [{"secondary_y": True}],
            [{"secondary_y": True}],
            [{}],
            [{"type": "heatmap"}],
        ],
        subplot_titles=(
            "Annual Dividends & Growth",
            "TTM Dividend & Historical Yield",
            "10,000 Price vs Total Return",
            "Dividend Calendar Heatmap",
        ),
    )

    completed = annual[annual["completed_year"].fillna(False)]
    ytd = annual[annual["ytd"].fillna(False)]
    annual_categories = (
        annual[annual["completed_year"].fillna(False) | annual["ytd"].fillna(False)]
        .sort_values("year")["year_label"].astype(str).tolist()
    )
    tick_step = max(1, math.ceil(len(annual_categories) / 12))
    visible_year_ticks = annual_categories[::tick_step]
    if annual_categories and visible_year_ticks[-1] != annual_categories[-1]:
        visible_year_ticks.append(annual_categories[-1])
    fig.add_trace(
        go.Bar(
            x=completed["year_label"].astype(str), y=completed["annual_dividend"],
            name="Annual DPS", marker={"color": palette["dividend"], "opacity": 0.82},
            customdata=completed[["year_label", "payment_count"]].to_numpy(),
            hovertemplate=(
                "<b>%{customdata[0]}</b>"
                f"<br>Provider dividend: {prefix}%{{y:,.4f}}{suffix}"
                "<br>Dividend events: %{customdata[1]}"
                "<br>Basis: current-share-equivalent<extra></extra>"
            ),
        ),
        row=1, col=1, secondary_y=False,
    )
    if len(ytd):
        latest_observation = pd.Timestamp(prices.index.max())
        fig.add_trace(
            go.Bar(
                x=ytd["year_label"].astype(str), y=ytd["annual_dividend"], name="Current YTD",
                marker={"color": palette["dividend"], "opacity": 0.35},
                customdata=ytd[["year_label", "payment_count"]].to_numpy(),
                hovertemplate=(
                    "<b>%{customdata[0]}</b>"
                    f"<br>Provider dividend YTD: {prefix}%{{y:,.4f}}{suffix}"
                    "<br>Dividend events: %{customdata[1]}"
                    f"<br>Latest market observation: {latest_observation:%d %b %Y}"
                    "<br>Incomplete year — excluded from structural growth metrics<extra></extra>"
                ),
            ),
            row=1, col=1, secondary_y=False,
        )
    exact_growth = pd.to_numeric(completed["yoy_growth"], errors="coerce")
    plotted_growth = exact_growth.clip(lower=-1.0, upper=2.0)
    fig.add_trace(
        go.Scatter(
            x=completed["year_label"].astype(str), y=plotted_growth, name="YoY Growth",
            mode="lines+markers", line={"color": palette["adjusted"], "width": 1.6},
            marker={"size": 5},
            customdata=np.column_stack([completed["year_label"].to_numpy(), exact_growth.to_numpy()]),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Exact completed-year growth: %{customdata[1]:+.2%}"
                "<br>Display axis is clipped to −100% / +200%<extra></extra>"
            ),
        ),
        row=1, col=1, secondary_y=True,
    )

    dividend_custom = np.column_stack([
        prices["ttm_dividend"].to_numpy(), prices["ttm_dividend_yield"].to_numpy(),
        prices["split_adjusted_price_current_share"].to_numpy(),
    ])
    fig.add_trace(
        go.Scattergl(
            x=prices.index, y=prices["ttm_dividend"], name="TTM DPS",
            mode="lines", line={"color": palette["dividend"], "width": 1.9},
            customdata=dividend_custom,
            hovertemplate=(
                "<b>%{x|%d %b %Y}</b>"
                f"<br>TTM dividend: {prefix}%{{customdata[0]:,.4f}}{suffix}"
                "<br>TTM yield: %{customdata[1]:.2%}"
                f"<br>Split-adjusted price basis: {prefix}%{{customdata[2]:,.2f}}{suffix}"
                "<extra></extra>"
            ),
        ),
        row=2, col=1, secondary_y=False,
    )
    fig.add_trace(
        go.Scattergl(
            x=prices.index, y=prices["ttm_dividend_yield"], name="TTM Yield",
            mode="lines", line={"color": palette["event"], "width": 1.5},
            customdata=dividend_custom,
            hovertemplate=(
                "<b>%{x|%d %b %Y}</b><br>TTM yield: %{y:.2%}"
                f"<br>TTM dividend: {prefix}%{{customdata[0]:,.4f}}{suffix}"
                f"<br>Split-adjusted price basis: {prefix}%{{customdata[2]:,.2f}}{suffix}"
                "<extra></extra>"
            ),
        ),
        row=2, col=1, secondary_y=True,
    )

    wealth_custom = np.column_stack([
        prices["price_wealth_10000"].to_numpy(),
        prices["provider_total_return_wealth_10000"].to_numpy(),
        prices["total_return_uplift"].to_numpy(),
    ])
    fig.add_trace(
        go.Scattergl(
            x=prices.index, y=prices["price_wealth_10000"], name="Price Only",
            mode="lines", line={"color": palette["raw"], "width": 1.8},
            customdata=wealth_custom,
            hovertemplate=(
                "<b>%{x|%d %b %Y}</b>"
                f"<br>Price-only value: {prefix}%{{customdata[0]:,.2f}}{suffix}"
                f"<br>Total-return proxy: {prefix}%{{customdata[1]:,.2f}}{suffix}"
                "<br>Compounded uplift: %{customdata[2]:+.2%}<extra></extra>"
            ),
        ),
        row=3, col=1,
    )
    if metrics.get("adjusted_close_total_return_available"):
        fig.add_trace(
            go.Scattergl(
                x=prices.index, y=prices["provider_total_return_wealth_10000"],
                name="Total Return", mode="lines",
                line={"color": palette["adjusted"], "width": 2.0}, customdata=wealth_custom,
                hovertemplate=(
                    "<b>%{x|%d %b %Y}</b>"
                    f"<br>Provider-adjusted value: {prefix}%{{customdata[1]:,.2f}}{suffix}"
                    f"<br>Price-only value: {prefix}%{{customdata[0]:,.2f}}{suffix}"
                    "<br>Compounded uplift: %{customdata[2]:+.2%}"
                    "<br>Pre-tax, pre-fee analytical proxy<extra></extra>"
                ),
            ),
            row=3, col=1,
        )
    else:
        fig.add_annotation(
            x=0.5, y=0.5, xref="x3 domain", yref="y5 domain", showarrow=False,
            text="Price vs total-return comparison unavailable — genuine provider Adjusted Close was not supplied.",
            font={"size": 11, "color": palette["muted"]},
        )

    first_year = int(prices.index[0].year)
    last_year = int(prices.index[-1].year)
    heat_years = list(range(first_year, last_year + 1))
    if events.empty:
        heat_values = pd.DataFrame(0.0, index=heat_years, columns=range(1, 13))
        heat_counts = pd.DataFrame(0, index=heat_years, columns=range(1, 13))
    else:
        heat_values = events.pivot_table(
            index="calendar_year", columns="calendar_month", values="provider_dividend",
            aggfunc="sum", fill_value=0.0,
        ).reindex(index=heat_years, columns=range(1, 13), fill_value=0.0)
        heat_counts = events.assign(event_count=1).pivot_table(
            index="calendar_year", columns="calendar_month", values="event_count",
            aggfunc="sum", fill_value=0,
        ).reindex(index=heat_years, columns=range(1, 13), fill_value=0)
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    custom_heat = np.dstack([
        np.repeat(np.asarray(heat_years)[:, None], 12, axis=1),
        np.repeat(np.asarray(month_labels)[None, :], len(heat_years), axis=0),
        heat_counts.to_numpy(dtype=int),
    ])
    colorscale = [
        [0.0, palette["paper"]], [0.2, palette["card"]],
        [0.55, palette["primary"]], [1.0, palette["dividend"]],
    ]
    fig.add_trace(
        go.Heatmap(
            x=month_labels, y=[str(year) for year in heat_years], z=heat_values.to_numpy(),
            customdata=custom_heat, colorscale=colorscale, colorbar={"title": f"DPS<br>({currency})", "len": 0.20, "y": 0.09},
            hovertemplate=(
                "<b>%{customdata[1]} %{customdata[0]}</b>"
                f"<br>Provider dividend: {prefix}%{{z:,.4f}}{suffix}"
                "<br>Dividend events: %{customdata[2]}"
                "<br>Basis: current-share-equivalent<extra></extra>"
            ),
            name="Dividend Calendar",
        ),
        row=4, col=1,
    )

    fig.update_layout(
        template="plotly_dark" if theme == "dark" else "plotly_white",
        title=None,
        height=1320, paper_bgcolor=palette["paper"], plot_bgcolor=palette["plot"],
        font={"family": "Inter, Arial, sans-serif", "color": palette["text"], "size": 12},
        hovermode="closest", hoverlabel={"bgcolor": palette["paper"], "font": {"color": palette["text"]}},
        margin={"l": 90, "r": 70, "t": 140, "b": 95}, bargap=0.18,
        legend={
            "orientation": "h", "yanchor": "bottom", "y": 1.075,
            "xanchor": "left", "x": 0, "bgcolor": palette["card"],
            "bordercolor": palette["grid"], "borderwidth": 1,
            "font": {"size": 10, "color": palette["text"]},
            "entrywidth": 102, "entrywidthmode": "pixels",
        },
    )
    fig.update_yaxes(title_text=f"Annual Dividend ({currency})", tickprefix=prefix, ticksuffix=suffix, rangemode="tozero", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="YoY Growth", tickformat=".0%", range=[-1.05, 2.05], row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text=f"TTM Dividend ({currency})", tickprefix=prefix, ticksuffix=suffix, rangemode="tozero", row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="TTM Yield", tickformat=".1%", rangemode="tozero", row=2, col=1, secondary_y=True)
    fig.update_yaxes(title_text=f"Value ({currency})", type="log", row=3, col=1)
    fig.update_xaxes(
        type="category", categoryorder="array", categoryarray=annual_categories,
        tickmode="array", tickvals=visible_year_ticks, ticktext=visible_year_ticks,
        row=1, col=1,
    )
    fig.update_xaxes(matches="x3", showgrid=True, gridcolor=palette["grid"], row=2, col=1)
    fig.update_xaxes(
        title_text="Date", showgrid=True, gridcolor=palette["grid"],
        row=3, col=1,
    )
    fig.update_xaxes(title_text="Month", row=4, col=1)
    fig.update_yaxes(title_text="Calendar Year", autorange="reversed", row=4, col=1)
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True, title_standoff=10)
    subplot_titles = {
        "Annual Dividends & Growth",
        "TTM Dividend & Historical Yield",
        "10,000 Price vs Total Return",
        "Dividend Calendar Heatmap",
    }
    for annotation in fig.layout.annotations:
        if annotation.text in subplot_titles:
            annotation.update(font={"size": 13, "color": palette["text"]}, yshift=10)
    return fig


def dividend_summary_display(result: AnalysisResult) -> pd.DataFrame:
    if result.annual_dividends.empty:
        return pd.DataFrame()
    return result.annual_dividends.rename(columns={
        "year_label": "Year", "annual_dividend": "Dividend Per Share",
        "payment_count": "Payment Count", "yoy_growth": "YoY Dividend Growth",
        "completed_year": "Completed Year?", "ytd": "YTD?",
    })[["Year", "Dividend Per Share", "Payment Count", "YoY Dividend Growth", "Completed Year?", "YTD?"]]


def build_dividend_chart(
    result: AnalysisResult,
    *,
    theme: str = "dark",
    wealth_scale: str = "log",
    horizon: str = "MAX",
) -> go.Figure:
    """Build the dividend workspace while keeping page content in Streamlit."""
    if wealth_scale not in {"log", "linear"}:
        raise ValueError("wealth_scale must be log or linear")
    rendered = dividend_display_result(result, horizon=horizon, max_points=5000)
    fig = build_dividend_total_return_figure(rendered, theme=theme)
    if result.dividend_status != "NONE":
        fig.update_yaxes(type=wealth_scale, row=3, col=1)
    fig.update_layout(title=None, height=1320, margin={"l": 82, "r": 62, "t": 140, "b": 90})
    fig.layout.updatemenus = ()
    return fig
