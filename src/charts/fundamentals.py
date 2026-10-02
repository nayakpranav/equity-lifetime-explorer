"""Theme-compatible Release A operating, cash and balance-sheet figures."""

from __future__ import annotations

from collections import OrderedDict

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..config import THEMES
from ..financial_models import FundamentalsResult
from ..formatting import currency_parts


def _plot_values(frame: pd.DataFrame, column: str) -> list[float | None]:
    if column not in frame:
        return [None] * len(frame)
    return [None if value is None or pd.isna(value) else float(value) for value in frame[column]]


def _base_figure(fig: go.Figure, theme: str, *, height: int) -> go.Figure:
    palette = THEMES[theme]
    fig.update_layout(
        template="plotly_dark" if theme == "dark" else "plotly_white",
        paper_bgcolor=palette["paper"], plot_bgcolor=palette["plot"],
        font={"family": "Inter, Arial, sans-serif", "color": palette["text"]},
        height=height, margin={"l": 72, "r": 35, "t": 48, "b": 72},
        legend={"orientation": "h", "y": 1.09, "x": 0, "font": {"size": 10}},
        hovermode="x unified", bargap=0.2,
    )
    fig.update_xaxes(showgrid=False, automargin=True)
    fig.update_yaxes(gridcolor=palette["grid"], automargin=True)
    return fig


def build_fundamentals_figures(
    result: FundamentalsResult, *, theme: str = "dark", frequency: str = "annual",
) -> OrderedDict[str, go.Figure]:
    if theme not in THEMES:
        raise ValueError("theme must be dark or light")
    if frequency not in {"annual", "quarterly"}:
        raise ValueError("frequency must be annual or quarterly")
    frame = result.annual if frequency == "annual" else result.quarterly
    if frame.empty:
        return OrderedDict()
    frame = frame.sort_values(["fiscal_year", "fiscal_quarter"])
    palette = THEMES[theme]
    currency = result.identity.reporting_currency if result.identity else "USD"
    prefix, suffix = currency_parts(currency)
    labels = (
        [f"FY{year}" for year in frame["fiscal_year"]]
        if frequency == "annual" else
        [f"FY{year} Q{quarter}" for year, quarter in zip(frame["fiscal_year"], frame["fiscal_quarter"])]
    )
    dates = frame["period_end"].astype(str).tolist()
    accepted = (
        frame["revenue_acceptance_utc"].fillna("Acceptance unavailable").astype(str).tolist()
        if "revenue_acceptance_utc" in frame else ["Acceptance unavailable"] * len(frame)
    )
    income = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.09,
                           row_heights=[0.43, 0.32, 0.25])
    income.add_trace(go.Bar(
        x=labels, y=_plot_values(frame, "revenue"), name="Revenue",
        marker_color=palette["primary"], customdata=list(zip(dates, accepted)),
        hovertemplate="%{x}<br>Fiscal end: %{customdata[0]}<br>Revenue: "
        + prefix + "%{y:,.0f}" + suffix + "<br>Accepted: %{customdata[1]}<extra></extra>",
    ), row=1, col=1)
    for concept, label, color in (
        ("operating_income", "Operating income", palette["adjusted"]),
        ("net_income_consolidated", "Consolidated net income", palette["dividend"]),
    ):
        income.add_trace(go.Scatter(
            x=labels, y=_plot_values(frame, concept), name=label,
            mode="lines+markers", connectgaps=False, line={"color": color, "width": 2},
            customdata=dates,
            hovertemplate="%{x}<br>Fiscal end: %{customdata}<br>" + label + ": "
            + prefix + "%{y:,.0f}" + suffix + "<extra></extra>",
        ), row=2, col=1)
    for concept, label, color in (
        ("operating_margin", "Operating margin", palette["adjusted"]),
        ("net_margin", "Net margin", palette["dividend"]),
    ):
        income.add_trace(go.Scatter(
            x=labels, y=_plot_values(frame, concept), name=label,
            mode="lines+markers", connectgaps=False, line={"color": color, "width": 1.8},
            customdata=dates,
            hovertemplate="%{x}<br>Fiscal end: %{customdata}<br>" + label + ": %{y:.2%}<extra></extra>",
        ), row=3, col=1)
    _base_figure(income, theme, height=740)
    income.update_yaxes(title_text=f"Revenue ({currency})", tickformat="~s", row=1, col=1)
    income.update_yaxes(title_text=f"Income ({currency})", tickformat="~s", row=2, col=1)
    income.update_yaxes(title_text="Margin", tickformat=".0%", row=3, col=1)

    cash = go.Figure()
    for concept, label, color, kind in (
        ("ocf", "Operating cash flow", palette["primary"], "bar"),
        ("capex_ppe", "PPE capital spending", palette["event"], "bar"),
        ("fcf", "Free cash flow", palette["dividend"], "line"),
    ):
        values = _plot_values(frame, concept)
        hover = "%{x}<br>Fiscal end: %{customdata}<br>" + label + ": " + prefix + "%{y:,.0f}" + suffix + "<extra></extra>"
        if kind == "bar":
            cash.add_trace(go.Bar(x=labels, y=values, name=label, marker_color=color,
                                  customdata=dates, hovertemplate=hover))
        else:
            cash.add_trace(go.Scatter(x=labels, y=values, name=label, mode="lines+markers",
                                      connectgaps=False, line={"color": color, "width": 2.3},
                                      customdata=dates, hovertemplate=hover))
    _base_figure(cash, theme, height=430)
    cash.update_yaxes(title_text=f"Cash flow ({currency})", tickformat="~s")
    cash.update_layout(barmode="group")

    balance = go.Figure()
    for concept, label, color in (
        ("cash_equivalents", "Cash & equivalents", palette["primary"]),
        ("reported_long_term_debt", "Reported long-term debt", palette["event"]),
        ("shareholders_equity", "Shareholders' equity", palette["adjusted"]),
    ):
        balance.add_trace(go.Scatter(
            x=labels, y=_plot_values(frame, concept), name=label,
            mode="lines+markers", connectgaps=False, line={"color": color, "width": 2},
            customdata=dates,
            hovertemplate="%{x}<br>Statement date: %{customdata}<br>" + label + ": "
            + prefix + "%{y:,.0f}" + suffix + "<extra></extra>",
        ))
    _base_figure(balance, theme, height=420)
    balance.update_yaxes(title_text=f"Balance ({currency})", tickformat="~s")
    return OrderedDict((
        ("Growth & Profitability", income),
        ("Cash Generation", cash),
        ("Balance-Sheet Strength", balance),
    ))
