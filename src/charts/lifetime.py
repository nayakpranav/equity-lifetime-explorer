"""Price & Ownership Plotly workspace."""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..config import SHARE_CHANGING_TYPES, THEMES
from ..formatting import format_money
from ..models import AnalysisResult
from .common import (
    _event_points, _price_trace, _volume_available, _volume_bar_colors,
    _volume_customdata, _volume_hovertemplate, display_result, downsample_for_plot,
)

def build_lifetime_figure(
    result: AnalysisResult,
    *,
    price_mode: str = "no_split",
    default_scale: str = "log",
    theme: str = "dark",
    show_splits: bool = True,
    show_dividends: bool = True,
    show_volume: bool = True,
    show_drawdown: bool = True,
    max_render_points: int = 6000,
) -> go.Figure:
    if price_mode not in {"no_split", "raw", "adjusted", "overlay"}:
        raise ValueError("price_mode must be no_split, raw, adjusted, or overlay")
    if default_scale not in {"log", "linear"}:
        raise ValueError("default_scale must be log or linear")
    palette = THEMES.get(theme.lower())
    if palette is None:
        raise ValueError("theme must be dark or light")

    prices = result.prices
    volume_enabled = bool(show_volume and _volume_available(prices))
    panel_names = ["price"]
    if volume_enabled:
        panel_names.append("volume")
    if show_drawdown:
        panel_names.append("drawdown")
    row_for = {name: index + 1 for index, name in enumerate(panel_names)}
    if volume_enabled and show_drawdown:
        row_heights = [0.73, 0.16, 0.11]
    elif volume_enabled:
        row_heights = [0.82, 0.18]
    elif show_drawdown:
        row_heights = [0.86, 0.14]
    else:
        row_heights = [1.0]
    spacing = 0.035 if len(panel_names) == 3 else (0.045 if len(panel_names) == 2 else 0.0)

    split_actions = result.actions[
        result.actions["action_type"].isin(SHARE_CHANGING_TYPES)
        & result.actions["included_in_reconstruction"].fillna(False)
    ]
    plot_frame = downsample_for_plot(prices, result.actions["date"], max_render_points)
    fig = make_subplots(
        rows=len(panel_names), cols=1, shared_xaxes=True,
        vertical_spacing=spacing, row_heights=row_heights,
        specs=[[{}] for _ in panel_names],
    )

    mode_specs = [
        ("no_split", "no_split_close", "No-Split Equivalent", palette["primary"]),
        ("raw", "raw_close", "Raw As-Traded Price", palette["raw"]),
        ("adjusted", "adjusted_close", "Provider Adjusted Price", palette["adjusted"]),
    ]
    grouped_trace_indices: dict[str, list[int]] = {key: [] for key, *_ in mode_specs}
    for key, column, label, color in mode_specs:
        mode_visible = price_mode == key or price_mode == "overlay"
        grouped_trace_indices[key].append(len(fig.data))
        fig.add_trace(
            _price_trace(plot_frame, column, label, color, result.metadata.currency, mode_visible),
            row=1, col=1,
        )
        div_x, div_y, div_text = _event_points(
            prices, result.actions, column, {"cash_dividend", "special_dividend"}
        )
        grouped_trace_indices[key].append(len(fig.data))
        fig.add_trace(
            go.Scattergl(
                x=div_x, y=div_y, name=f"Dividends · {label}", mode="markers",
                marker={"symbol": "triangle-up", "size": 5, "color": palette["dividend"], "opacity": 0.62},
                text=div_text, hovertemplate="%{text}<extra></extra>",
                visible=bool(mode_visible and show_dividends and len(div_x)), showlegend=False,
            ),
            row=1, col=1,
        )
        split_x, split_y, split_text = _event_points(
            prices, split_actions, column, SHARE_CHANGING_TYPES
        )
        grouped_trace_indices[key].append(len(fig.data))
        fig.add_trace(
            go.Scattergl(
                x=split_x, y=split_y, name=f"Share actions · {label}", mode="markers",
                marker={
                    "symbol": "diamond", "size": 8, "color": palette["event"],
                    "line": {"width": 1, "color": palette["paper"]},
                },
                text=split_text, hovertemplate="%{text}<extra></extra>",
                visible=bool(mode_visible and show_splits and len(split_x)), showlegend=False,
            ),
            row=1, col=1,
        )

    volume_trace_indices: list[int] = []
    if volume_enabled:
        volume_row = row_for["volume"]
        volume_trace_indices.append(len(fig.data))
        fig.add_trace(
            go.Bar(
                x=prices.index, y=prices["volume"], name="Daily Share Volume",
                marker={"color": _volume_bar_colors(prices, palette), "line": {"width": 0}},
                customdata=_volume_customdata(prices),
                hovertemplate=_volume_hovertemplate(result.metadata.currency),
            ),
            row=volume_row, col=1,
        )
        volume_trace_indices.append(len(fig.data))
        fig.add_trace(
            go.Scattergl(
                x=prices.index, y=prices["volume_ma_20"], name="20D Avg Volume",
                mode="lines", line={"color": palette["volume_ma20"], "width": 1.5},
                hovertemplate="<b>%{x|%d %b %Y}</b><br>Previous 20D avg: %{y:,.4s}<extra></extra>",
            ),
            row=volume_row, col=1,
        )

    drawdown_trace_indices: list[int] = []
    if show_drawdown:
        drawdown_trace_indices.append(len(fig.data))
        fig.add_trace(
            go.Scattergl(
                x=plot_frame.index, y=plot_frame["drawdown"], name="Drawdown", mode="lines",
                line={"color": palette["drawdown"], "width": 1.5}, fill="tozeroy",
                fillcolor="rgba(194,65,75,0.15)" if theme == "light" else "rgba(240,113,120,0.18)",
                hovertemplate="<b>%{x|%d %b %Y}</b><br>Drawdown: %{y:.1%}<extra></extra>",
            ),
            row=row_for["drawdown"], col=1,
        )

    price_domain = tuple(fig.layout.yaxis.domain)
    if show_splits:
        for _, action in split_actions.iterrows():
            fig.add_shape(
                type="line", x0=action["date"], x1=action["date"],
                y0=price_domain[0], y1=price_domain[1], xref="x", yref="paper",
                line={"color": palette["event"], "width": 1, "dash": "dot"},
                opacity=0.45, layer="below",
            )
    if show_splits and len(split_actions):
        if len(split_actions) <= 8:
            annotated = split_actions
        else:
            importance = split_actions["share_multiplier"].astype(float).map(lambda value: abs(math.log(value)))
            selected = set(importance.nlargest(6).index) | {split_actions.index[0], split_actions.index[-1]}
            annotated = split_actions.loc[sorted(selected)]
        for counter, (_, action) in enumerate(annotated.iterrows()):
            fig.add_annotation(
                x=action["date"], y=price_domain[1] - 0.035 * (counter % 3),
                xref="x", yref="paper", text=f"{action['ratio']} {action['event']}",
                showarrow=False, textangle=-35, xanchor="left",
                font={"size": 9, "color": palette["event"]}, bgcolor="rgba(0,0,0,0)",
            )

    metrics = result.metrics
    period = f"{metrics['first_available_date']:%b %Y} – {metrics['latest_available_date']:%b %Y}"
    split_count = metrics["forward_split_count"] + metrics["reverse_split_count"] + metrics["bonus_issue_count"]
    title = (
        f"<b>{result.metadata.name.upper()} — LIFETIME SHARE-PRICE EVOLUTION</b>"
        f"<br><span style='font-size:13px;color:{palette['muted']}'>{period} | "
        "Corporate actions reconstructed | Mechanical no-split equivalent</span>"
        f"<br><span style='font-size:11px;color:{palette['muted']}'>{result.metadata.exchange}: "
        f"{result.metadata.ticker} | {result.metadata.currency} | "
        f"{metrics['years_of_history']:.1f} years | {split_count} share actions | "
        f"cumulative factor {metrics['cumulative_share_multiplier']:,.6g}×</span>"
    )

    total_traces = len(fig.data)
    def visibility_for(mode: str) -> list[bool]:
        visible = [False] * total_traces
        selected_modes = {"no_split", "raw", "adjusted"} if mode == "overlay" else {mode}
        for selected_mode in selected_modes:
            indices = grouped_trace_indices[selected_mode]
            visible[indices[0]] = True
            visible[indices[1]] = bool(show_dividends and len(fig.data[indices[1]].x))
            visible[indices[2]] = bool(show_splits and len(fig.data[indices[2]].x))
        for index in volume_trace_indices + drawdown_trace_indices:
            visible[index] = True
        return visible

    price_buttons = [
        {"label": "NO-SPLIT", "method": "restyle", "args": [{"visible": visibility_for("no_split")}]},
        {"label": "RAW", "method": "restyle", "args": [{"visible": visibility_for("raw")}]},
        {"label": "ADJUSTED", "method": "restyle", "args": [{"visible": visibility_for("adjusted")}]},
        {"label": "OVERLAY", "method": "restyle", "args": [{"visible": visibility_for("overlay")}]},
    ]
    scale_buttons = [
        {"label": "LOG", "method": "relayout", "args": [{"yaxis.type": "log"}]},
        {"label": "LINEAR", "method": "relayout", "args": [{"yaxis.type": "linear"}]},
    ]
    fig.update_layout(
        template="plotly_dark" if theme == "dark" else "plotly_white",
        title={"text": title, "x": 0.01, "xanchor": "left", "y": 0.985, "yanchor": "top"},
        height={1: 760, 2: 840, 3: 920}[len(panel_names)],
        paper_bgcolor=palette["paper"], plot_bgcolor=palette["plot"],
        font={"family": "Inter, Arial, sans-serif", "color": palette["text"], "size": 12},
        hovermode="x unified",
        hoverlabel={"bgcolor": palette["paper"], "font": {"color": palette["text"]}},
        margin={"l": 78, "r": 38, "t": 190, "b": 60},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.005, "xanchor": "right", "x": 1, "bgcolor": "rgba(0,0,0,0)"},
        bargap=0,
        updatemenus=[
            {
                "type": "buttons", "direction": "right", "buttons": price_buttons,
                "x": 0.0, "y": 1.135, "xanchor": "left", "yanchor": "top",
                "showactive": False,
                "active": {"no_split": 0, "raw": 1, "adjusted": 2, "overlay": 3}[price_mode],
                "bgcolor": palette["control_bg"], "bordercolor": palette["control_border"],
                "borderwidth": 1, "font": {"size": 10, "color": palette["control_text"]},
            },
            {
                "type": "buttons", "direction": "right", "buttons": scale_buttons,
                "x": 0.56, "y": 1.135, "xanchor": "left", "yanchor": "top",
                "showactive": False, "active": 0 if default_scale == "log" else 1,
                "bgcolor": palette["control_bg"], "bordercolor": palette["control_border"],
                "borderwidth": 1, "font": {"size": 10, "color": palette["control_text"]},
            },
        ],
    )
    fig.add_annotation(
        x=0.72, y=1.145, xref="paper", yref="paper", xanchor="left", yanchor="top",
        showarrow=False, align="left",
        text=(f"<span style='font-size:9px;color:{palette['muted']}'>CURRENT QUOTED PRICE</span><br>"
              f"<b>{format_money(metrics['latest_raw_close'], result.metadata.currency)}</b>"),
        bgcolor=palette["card"], bordercolor=palette["grid"], borderpad=7,
    )
    fig.add_annotation(
        x=0.855, y=1.145, xref="paper", yref="paper", xanchor="left", yanchor="top",
        showarrow=False, align="left",
        text=(f"<span style='font-size:9px;color:{palette['muted']}'>MECHANICAL NO-SPLIT EQUIVALENT</span><br>"
              f"<b>{format_money(metrics['latest_no_split_equivalent'], result.metadata.currency, compact=True)}</b> "
              f"<span style='font-size:10px'>({metrics['cumulative_share_multiplier']:,.6g}×)</span>"),
        bgcolor=palette["card"], bordercolor=palette["grid"], borderpad=7,
    )
    fig.update_yaxes(
        type=default_scale, title_text=f"Price ({result.metadata.currency})",
        showgrid=True, gridcolor=palette["grid"], zeroline=False, row=1, col=1,
    )
    if volume_enabled:
        fig.update_yaxes(
            type="linear", title_text="Share Volume", showgrid=False, zeroline=False,
            tickformat="~s", rangemode="tozero", row=row_for["volume"], col=1,
        )
    if show_drawdown:
        fig.update_yaxes(
            type="linear", title_text="Drawdown", showgrid=True, gridcolor=palette["grid"],
            zeroline=True, zerolinecolor=palette["grid"], tickformat=".0%",
            range=[max(-1.0, min(-0.05, float(prices["drawdown"].min()) * 1.08)), 0.02],
            row=row_for["drawdown"], col=1,
        )
    fig.update_xaxes(
        showgrid=True, gridcolor=palette["grid"], rangeslider={"visible": False},
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikecolor=palette["muted"], spikethickness=1,
    )
    bottom_row = len(panel_names)
    fig.update_xaxes(
        title_text="Date",
        rangeselector={
            "buttons": [
                {"count": 1, "label": "1Y", "step": "year", "stepmode": "backward"},
                {"count": 5, "label": "5Y", "step": "year", "stepmode": "backward"},
                {"count": 10, "label": "10Y", "step": "year", "stepmode": "backward"},
                {"step": "all", "label": "MAX"},
            ],
            "x": 0, "y": -0.24, "bgcolor": palette["control_bg"],
            "activecolor": palette["control_active"], "bordercolor": palette["control_border"],
            "borderwidth": 1, "font": {"size": 10, "color": palette["control_text"]},
        },
        row=bottom_row, col=1,
    )
    return fig


def build_lifetime_chart(result: AnalysisResult, **kwargs) -> go.Figure:
    """Build the v5 chart with page-level chrome delegated to Streamlit."""
    rendered = display_result(result, max_points=int(kwargs.pop("max_render_points", 5000)))
    fig = build_lifetime_figure(rendered, max_render_points=5000, **kwargs)
    fig.update_layout(title=None, margin={"l": 72, "r": 28, "t": 28, "b": 66})
    fig.layout.updatemenus = ()
    fig.layout.annotations = tuple(
        annotation for annotation in fig.layout.annotations
        if getattr(annotation, "xref", None) != "paper"
    )
    return fig
