"""Volume & Liquidity Plotly workspace."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..config import SHARE_CHANGING_TYPES, THEMES
from ..formatting import currency_parts, format_money, format_multiple, format_quantity
from ..models import AnalysisResult
from .common import (
    _volume_available, _volume_bar_colors, _volume_customdata, _volume_hovertemplate,
    display_result, downsample_for_plot,
)

def _empty_volume_figure(result: AnalysisResult, theme: str) -> go.Figure:
    palette = THEMES[theme]
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark" if theme == "dark" else "plotly_white",
        height=420, paper_bgcolor=palette["paper"], plot_bgcolor=palette["plot"],
        font={"family": "Inter, Arial, sans-serif", "color": palette["text"]},
        title=f"<b>{result.metadata.name.upper()} — VOLUME & LIQUIDITY EXPLORER</b>",
    )
    fig.add_annotation(
        x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
        text="Volume data unavailable from configured provider",
        font={"size": 16, "color": palette["muted"]},
    )
    return fig


def build_volume_liquidity_figure(
    result: AnalysisResult,
    *,
    theme: str = "dark",
    max_annotations: int = 5,
) -> go.Figure:
    theme = theme.lower()
    if theme not in THEMES:
        raise ValueError("theme must be dark or light")
    if not _volume_available(result.prices):
        return _empty_volume_figure(result, theme)
    palette = THEMES[theme]
    prices = result.prices
    currency = result.metadata.currency
    prefix, suffix = currency_parts(currency)

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.035,
        row_heights=[0.35, 0.30, 0.20, 0.15],
        specs=[[{}], [{}], [{}], [{}]],
    )
    price_frame = downsample_for_plot(prices, result.actions["date"], max_points=6000)
    fig.add_trace(
        go.Scattergl(
            x=price_frame.index, y=price_frame["raw_close"], name="Raw As-Traded Price",
            mode="lines", line={"color": palette["raw"], "width": 1.8},
            customdata=price_frame[["no_split_close"]].to_numpy(),
            hovertemplate=(
                "<b>%{x|%d %b %Y}</b>"
                f"<br>Raw close: {prefix}%{{y:,.2f}}{suffix}"
                f"<br>No-split context: {prefix}%{{customdata[0]:,.2f}}{suffix}"
                "<extra></extra>"
            ),
        ),
        row=1, col=1,
    )

    share_indices: list[int] = []
    dollar_indices: list[int] = []
    share_indices.append(len(fig.data))
    fig.add_trace(
        go.Bar(
            x=prices.index, y=prices["volume"], name="Daily Share Volume",
            marker={"color": _volume_bar_colors(prices, palette), "line": {"width": 0}},
            customdata=_volume_customdata(prices),
            hovertemplate=_volume_hovertemplate(currency), visible=True,
        ),
        row=2, col=1,
    )
    for column, name, color, width in (
        ("volume_ma_20", "20D Avg Volume", palette["volume_ma20"], 1.8),
        ("volume_ma_50", "50D Avg Volume", palette["volume_ma50"], 1.4),
    ):
        share_indices.append(len(fig.data))
        fig.add_trace(
            go.Scattergl(
                x=prices.index, y=prices[column], name=name, mode="lines",
                line={"color": color, "width": width}, visible=True,
                hovertemplate=f"<b>%{{x|%d %b %Y}}</b><br>{name}: %{{y:,.4s}}<extra></extra>",
            ),
            row=2, col=1,
        )
    dollar_indices.append(len(fig.data))
    fig.add_trace(
        go.Bar(
            x=prices.index, y=prices["dollar_volume"], name="Daily Dollar Volume",
            marker={"color": palette["dollar_volume"], "line": {"width": 0}}, visible=False,
            customdata=_volume_customdata(prices),
            hovertemplate=(
                "<b>%{x|%d %b %Y}</b>"
                f"<br>Dollar volume: {prefix}%{{y:,.4s}}{suffix}"
                "<br>Share volume: %{customdata[0]:,.4s}"
                "<br>Relative volume: %{customdata[3]:.2f}×"
                f"<br>Raw close: {prefix}%{{customdata[5]:,.2f}}{suffix}"
                "<extra></extra>"
            ),
        ),
        row=2, col=1,
    )
    dollar_indices.append(len(fig.data))
    fig.add_trace(
        go.Scattergl(
            x=prices.index, y=prices["dollar_volume_ma_20"], name="20D Avg Dollar Volume",
            mode="lines", line={"color": palette["volume_ma20"], "width": 1.8}, visible=False,
            hovertemplate=(
                "<b>%{x|%d %b %Y}</b>"
                f"<br>Previous 20D avg dollar volume: {prefix}%{{y:,.4s}}{suffix}<extra></extra>"
            ),
        ),
        row=2, col=1,
    )

    fig.add_trace(
        go.Scattergl(
            x=prices.index, y=prices["relative_volume_20"], name="Relative Volume (20D)",
            mode="lines", line={"color": palette["rvol"], "width": 1.5},
            fill="tozeroy", fillcolor="rgba(232,193,90,0.10)",
            customdata=prices[["volume", "volume_ma_20", "daily_return"]].to_numpy(),
            hovertemplate=(
                "<b>%{x|%d %b %Y}</b><br>RVOL: %{y:.2f}×"
                "<br>Share volume: %{customdata[0]:,.4s}"
                "<br>Previous 20D avg: %{customdata[1]:,.4s}"
                "<br>Daily return: %{customdata[2]:+.2%}<extra></extra>"
            ),
        ),
        row=3, col=1,
    )
    fig.add_hline(y=1.0, line={"color": palette["muted"], "width": 1, "dash": "dot"}, row=3, col=1)
    fig.add_hline(y=2.0, line={"color": palette["event"], "width": 1, "dash": "dot"}, row=3, col=1)

    fig.add_trace(
        go.Scattergl(
            x=prices.index, y=prices["dollar_volume_ma_20"], name="20D Avg Dollar Liquidity",
            mode="lines", line={"color": palette["primary"], "width": 1.7},
            hovertemplate=(
                "<b>%{x|%d %b %Y}</b>"
                f"<br>Previous 20D avg dollar volume: {prefix}%{{y:,.4s}}{suffix}<extra></extra>"
            ),
        ),
        row=4, col=1,
    )

    eligible = result.volume_events.dropna(subset=["relative_volume_20"]).nsmallest(
        max(0, int(max_annotations)), "relative_volume_rank"
    ) if not result.volume_events.empty else pd.DataFrame()
    if not eligible.empty:
        event_colors = np.where(
            eligible["direction"].eq("Advance"), palette["volume_up"],
            np.where(eligible["direction"].eq("Decline"), palette["volume_down"], palette["volume_flat"]),
        )
        event_text = [
            f"<b>{row.context}</b><br>{row.date:%d %b %Y}"
            f"<br>RVOL: {row.relative_volume_20:.2f}×"
            f"<br>Volume: {format_quantity(row.volume)}"
            f"<br>Dollar volume: {format_money(row.dollar_volume, currency, compact=True)}"
            f"<br>Daily return: {row.daily_return:+.2%}"
            for row in eligible.itertuples()
        ]
        fig.add_trace(
            go.Scattergl(
                x=eligible["date"], y=eligible["relative_volume_20"],
                name="Top RVOL Events", mode="markers+text",
                marker={"size": 9, "color": event_colors, "line": {"width": 1, "color": palette["paper"]}},
                text=[f"{value:.1f}×" for value in eligible["relative_volume_20"]],
                textposition="top center", textfont={"size": 9, "color": palette["event"]},
                hovertext=event_text, hovertemplate="%{hovertext}<extra></extra>",
            ),
            row=3, col=1,
        )

    split_actions = result.actions[
        result.actions["action_type"].isin(SHARE_CHANGING_TYPES)
        & result.actions["included_in_reconstruction"].fillna(False)
    ]
    for _, action in split_actions.iterrows():
        fig.add_vline(
            x=action["date"], line={"color": palette["event"], "width": 0.8, "dash": "dot"},
            opacity=0.30,
        )

    trace_count = len(fig.data)
    share_visibility = [True] * trace_count
    dollar_visibility = [True] * trace_count
    for index in dollar_indices:
        share_visibility[index] = False
    for index in share_indices:
        dollar_visibility[index] = False
    mode_buttons = [
        {
            "label": "SHARES", "method": "update",
            "args": [{"visible": share_visibility}, {"yaxis2.title.text": "Share Volume", "yaxis2.tickprefix": "", "yaxis2.ticksuffix": ""}],
        },
        {
            "label": "DOLLAR VOLUME", "method": "update",
            "args": [{"visible": dollar_visibility}, {"yaxis2.title.text": f"Dollar Volume ({currency})", "yaxis2.tickprefix": prefix, "yaxis2.ticksuffix": suffix}],
        },
    ]

    first_date, last_date = prices.index[0], prices.index[-1]
    title = (
        f"<b>{result.metadata.name.upper()} — VOLUME & LIQUIDITY EXPLORER</b>"
        f"<br><span style='font-size:13px;color:{palette['muted']}'>{first_date:%b %Y} – {last_date:%b %Y} | "
        "Share volume · dollar volume · relative activity</span>"
        f"<br><span style='font-size:11px;color:{palette['muted']}'>{result.metadata.exchange}: "
        f"{result.metadata.ticker} | {currency} | {len(prices):,} observations</span>"
    )
    fig.update_layout(
        template="plotly_dark" if theme == "dark" else "plotly_white",
        title={"text": title, "x": 0.01, "xanchor": "left", "y": 0.99, "yanchor": "top"},
        height=1120, paper_bgcolor=palette["paper"], plot_bgcolor=palette["plot"],
        font={"family": "Inter, Arial, sans-serif", "color": palette["text"], "size": 12},
        hovermode="x unified",
        hoverlabel={"bgcolor": palette["paper"], "font": {"color": palette["text"]}},
        margin={"l": 86, "r": 42, "t": 220, "b": 170}, bargap=0,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.005, "xanchor": "right", "x": 1, "bgcolor": "rgba(0,0,0,0)"},
        updatemenus=[{
            "type": "buttons", "direction": "right", "buttons": mode_buttons,
            "x": 0.0, "y": 1.14, "xanchor": "left", "yanchor": "top",
            "showactive": False, "active": 0,
            "bgcolor": palette["control_bg"], "bordercolor": palette["control_border"],
            "borderwidth": 1, "font": {"size": 10, "color": palette["control_text"]},
        }],
    )
    summary = [
        ("LATEST VOLUME", format_quantity(result.metrics.get("latest_volume"))),
        ("20D AVG", format_quantity(result.metrics.get("volume_ma_20"))),
        ("LATEST RVOL", format_multiple(result.metrics.get("latest_relative_volume_20"))),
        ("LATEST DOLLAR VOL", format_money(result.metrics.get("latest_dollar_volume"), currency, compact=True)),
        ("HIGHEST RVOL", format_multiple(result.metrics.get("highest_relative_volume_20"))),
        ("HIGHEST DOLLAR VOL", format_money(result.metrics.get("highest_dollar_volume"), currency, compact=True)),
    ]
    for index, (label, value) in enumerate(summary):
        fig.add_annotation(
            x=index / (len(summary) - 1), y=1.095, xref="paper", yref="paper",
            xanchor="left" if index == 0 else ("right" if index == len(summary) - 1 else "center"),
            yanchor="top", showarrow=False, align="left",
            text=f"<span style='font-size:8px;color:{palette['muted']}'>{label}</span><br><b>{value}</b>",
            bgcolor=palette["card"], bordercolor=palette["grid"], borderpad=5,
        )
    fig.add_annotation(
        x=0, y=-0.16, xref="paper", yref="paper", xanchor="left", showarrow=False, align="left",
        font={"size": 10, "color": palette["muted"]},
        text=(
            "<b>Methodology:</b> Historical raw share volume can be affected by stock splits because the number of outstanding and traded shares changes mechanically. "
            "Dollar Volume (raw close × share volume) and Relative Volume (current volume ÷ previous 20-session average) provide complementary measures across share structures."
        ),
    )
    fig.add_annotation(
        x=0, y=-0.225, xref="paper", yref="paper", xanchor="left", showarrow=False, align="left",
        font={"size": 10, "color": palette["muted"]},
        text=(
            "High trading volume indicates elevated market participation. It does not identify institutions, retail investors, or another participant class, "
            "and does not establish accumulation, distribution, or causation. Dollar Volume is approximate, not exact exchange turnover."
        ),
    )
    fig.update_yaxes(title_text=f"Raw Price ({currency})", type="log", showgrid=True, gridcolor=palette["grid"], zeroline=False, row=1, col=1)
    fig.update_yaxes(title_text="Share Volume", type="linear", tickformat="~s", rangemode="tozero", showgrid=False, zeroline=False, row=2, col=1)
    fig.update_yaxes(title_text="RVOL (20D)", type="linear", ticksuffix="×", rangemode="tozero", showgrid=True, gridcolor=palette["grid"], row=3, col=1)
    fig.update_yaxes(title_text=f"20D Avg Value ({currency})", type="linear", tickformat="~s", tickprefix=prefix, ticksuffix=suffix, rangemode="tozero", showgrid=True, gridcolor=palette["grid"], row=4, col=1)
    fig.update_xaxes(
        showgrid=True, gridcolor=palette["grid"], rangeslider={"visible": False},
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikecolor=palette["muted"], spikethickness=1,
    )
    fig.update_xaxes(
        title_text="Date",
        rangeselector={
            "buttons": [
                {"count": 1, "label": "1Y", "step": "year", "stepmode": "backward"},
                {"count": 5, "label": "5Y", "step": "year", "stepmode": "backward"},
                {"count": 10, "label": "10Y", "step": "year", "stepmode": "backward"},
                {"step": "all", "label": "MAX"},
            ],
            "x": 0, "y": -0.27, "bgcolor": palette["control_bg"],
            "activecolor": palette["control_active"], "bordercolor": palette["control_border"],
            "borderwidth": 1, "font": {"size": 10, "color": palette["control_text"]},
        },
        row=4, col=1,
    )
    return fig


def notable_volume_events(result: AnalysisResult, top_n: int = 10) -> pd.DataFrame:
    if result.volume_events.empty:
        return pd.DataFrame()
    events = result.volume_events.dropna(subset=["relative_volume_20"]).nsmallest(
        int(top_n), "relative_volume_rank"
    ).copy()
    return events[
        [
            "date", "raw_close", "daily_return", "volume", "volume_ma_20",
            "relative_volume_20", "dollar_volume", "direction", "context",
            "relative_volume_rank", "share_volume_rank", "dollar_volume_rank",
        ]
    ].rename(columns={
        "date": "Date", "raw_close": "Close", "daily_return": "Daily Return",
        "volume": "Volume", "volume_ma_20": "20D Avg", "relative_volume_20": "RVOL",
        "dollar_volume": "Dollar Volume", "direction": "Direction", "context": "Context",
        "relative_volume_rank": "RVOL Rank", "share_volume_rank": "Share Volume Rank",
        "dollar_volume_rank": "Dollar Volume Rank",
    })


def build_volume_chart(result: AnalysisResult, *, theme: str = "dark", mode: str = "shares") -> go.Figure:
    """Build one native-control-driven volume view from cached analysis data."""
    rendered = display_result(result, max_points=5000)
    fig = build_volume_liquidity_figure(rendered, theme=theme)
    if mode not in {"shares", "dollar"}:
        raise ValueError("mode must be shares or dollar")
    for trace in fig.data:
        name = str(trace.name or "")
        if name in {"Daily Share Volume", "20D Avg Volume", "50D Avg Volume"}:
            trace.visible = mode == "shares"
        elif name in {"Daily Dollar Volume", "20D Avg Dollar Volume"}:
            trace.visible = mode == "dollar"
    title = "Share Volume" if mode == "shares" else f"Dollar Volume ({result.metadata.currency})"
    fig.update_yaxes(title_text=title, row=2, col=1)
    fig.update_layout(title=None, margin={"l": 78, "r": 34, "t": 28, "b": 70})
    fig.layout.updatemenus = ()
    fig.layout.annotations = tuple(
        annotation for annotation in fig.layout.annotations
        if getattr(annotation, "xref", None) != "paper"
    )
    return fig
