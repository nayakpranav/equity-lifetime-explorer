"""Theme-compatible Release A operating, cash and balance-sheet figures."""

from __future__ import annotations

from collections import OrderedDict

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..config import THEMES
from ..financial_models import FundamentalsResult
from ..financials.horizons import filter_financial_horizon
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


def _display_frame(frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
    """Insert visual gaps for undisclosed fiscal periods, without adding facts."""
    if frame.empty:
        return frame.copy()
    if frequency == "annual":
        indexed = frame.set_index("fiscal_year")
        output = indexed.reindex(range(int(indexed.index.min()), int(indexed.index.max()) + 1))
        output["fiscal_year"] = output.index
        output["fiscal_quarter"] = 4
    else:
        indexed = frame.assign(_ordinal=frame["fiscal_year"] * 4 + frame["fiscal_quarter"]).set_index("_ordinal")
        output = indexed.reindex(range(int(indexed.index.min()), int(indexed.index.max()) + 1))
        output["fiscal_year"] = (output.index - 1) // 4
        output["fiscal_quarter"] = (output.index - 1) % 4 + 1
    output["period_end"] = output["period_end"].fillna("Unavailable")
    return output.reset_index(drop=True)


def build_fundamentals_figures(
    result: FundamentalsResult, *, theme: str = "dark", frequency: str = "annual",
    horizon: str = "MAX",
) -> OrderedDict[str, go.Figure]:
    if theme not in THEMES:
        raise ValueError("theme must be dark or light")
    if frequency not in {"annual", "quarterly"}:
        raise ValueError("frequency must be annual or quarterly")
    frame = filter_financial_horizon(
        result.annual if frequency == "annual" else result.quarterly, horizon,
    )
    if frame.empty:
        return OrderedDict()
    frame = _display_frame(frame.sort_values(["fiscal_year", "fiscal_quarter"]), frequency)
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
        ("net_income_parent", "Net income attributable to parent", palette["dividend"]),
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
        ("productive_asset_spending", "Productive-asset spending · broader basis", palette["adjusted"], "bar"),
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
    figures = OrderedDict((
        ("Growth & Profitability", income),
        ("Cash Generation", cash),
        ("Balance-Sheet Strength", balance),
    ))

    eps = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
                        row_heights=[0.6, 0.4])
    for concept, name, color in (
        ("eps_basic", "Basic EPS", palette["primary"]),
        ("eps_diluted", "Diluted EPS", palette["adjusted"]),
    ):
        eps.add_trace(go.Bar(
            x=labels, y=_plot_values(frame, concept), name=name,
            marker_color=color,
            customdata=list(zip(
                dates,
                frame.get(f"{concept}_source_tag", pd.Series([None] * len(frame))).fillna("Unavailable"),
                frame.get(f"{concept}_share_basis_status", pd.Series([None] * len(frame))).fillna("unknown"),
            )),
            hovertemplate="%{x}<br>Fiscal end: %{customdata[0]}<br>Reported " + name + ": "
            + prefix + "%{y:.3f}" + suffix
            + "<br>Source tag: %{customdata[1]}<br>Share basis: %{customdata[2]}<extra></extra>",
        ), row=1, col=1)
        growth_column = f"{concept}_yoy"
        eps.add_trace(go.Scatter(
            x=labels, y=_plot_values(frame, growth_column),
            name=name + " YoY", mode="markers", marker={"color": color, "size": 7},
            customdata=frame.get(
                f"{concept}_yoy_status", pd.Series(["Unavailable"] * len(frame))
            ).fillna("Unavailable"),
            hovertemplate="%{x}<br>Same-filing comparative " + name
            + " growth: %{y:.2%}<br>Status: %{customdata}<extra></extra>",
        ), row=2, col=1)
    _base_figure(eps, theme, height=570)
    eps.update_layout(barmode="group")
    eps.update_yaxes(title_text=f"Reported EPS ({currency}/share)", row=1, col=1)
    eps.update_yaxes(title_text="Comparable YoY", tickformat=".0%", row=2, col=1)
    figures["Reported EPS & Comparable Growth"] = eps

    annual = filter_financial_horizon(result.annual, horizon)
    if not annual.empty:
        annual = _display_frame(annual.sort_values("fiscal_year"), "annual")
        annual_labels = [f"FY{year}" for year in annual["fiscal_year"]]
        capital = go.Figure()
        for concept, name, color in (
            ("roe", "Parent ROE", palette["primary"]),
            ("roce", "ROCE · operating-income basis", palette["adjusted"]),
        ):
            capital.add_trace(go.Bar(
                x=annual_labels, y=_plot_values(annual, concept), name=name,
                marker_color=color,
                customdata=list(zip(
                    annual["period_end"].astype(str),
                    annual.get(f"{concept}_status", pd.Series(["Unavailable"] * len(annual))).fillna("Unavailable"),
                )),
                hovertemplate="%{x}<br>Fiscal end: %{customdata[0]}<br>Calculated "
                + name + ": %{y:.2%}<br>Status: %{customdata[1]}<extra></extra>",
            ))
        _base_figure(capital, theme, height=410)
        capital.update_layout(barmode="group")
        capital.update_yaxes(title_text="Annual return on capital", tickformat=".0%")
        figures["Capital Efficiency (Annual)"] = capital
    return figures
