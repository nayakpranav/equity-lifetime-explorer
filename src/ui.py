"""Presentation-only helpers for the Streamlit application shell."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Iterable

import pandas as pd

from .formatting import format_money, format_multiple, format_percent, format_quantity
from .models import AnalysisResult


@dataclass(frozen=True)
class KpiCard:
    label: str
    value: str
    accent: str = "blue"


def active_theme_type(context: Any | None = None) -> str:
    """Return Streamlit's active native theme, defaulting safely to dark."""
    if context is None:
        try:
            import streamlit as st

            context = st.context
        except Exception:
            return "dark"
    try:
        theme_type = str(context.theme.type).lower()
    except (AttributeError, KeyError, RuntimeError, TypeError):
        return "dark"
    return theme_type if theme_type in {"dark", "light"} else "dark"


def _years(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    years = int(value)
    return f"{years} year" if years == 1 else f"{years} years"


def _growth_accent(value: Any) -> str:
    """Use presentation semantics without changing the underlying metric."""
    try:
        return "red" if pd.notna(value) and float(value) < 0 else "green"
    except (TypeError, ValueError):
        return "green"


def lifetime_kpi_cards(result: AnalysisResult) -> list[KpiCard]:
    values = result.metrics
    currency = result.metadata.currency
    return [
        KpiCard("Latest price", format_money(values.get("latest_raw_close"), currency), "blue"),
        KpiCard(
            "No-split equivalent",
            format_money(values.get("latest_no_split_equivalent"), currency, compact=True),
            "violet",
        ),
        KpiCard("Lifetime multiple", format_multiple(values.get("lifetime_price_multiple")), "blue"),
        KpiCard(
            "Lifetime CAGR",
            format_percent(values.get("lifetime_cagr")),
            _growth_accent(values.get("lifetime_cagr")),
        ),
        KpiCard("Share multiplier", format_multiple(values.get("cumulative_share_multiplier")), "violet"),
        KpiCard("Maximum drawdown", format_percent(values.get("maximum_drawdown")), "red"),
    ]


def volume_kpi_cards(result: AnalysisResult) -> list[KpiCard]:
    values = result.metrics
    return [
        KpiCard("Latest volume", format_quantity(values.get("latest_volume")), "blue"),
        KpiCard("Previous 20D average", format_quantity(values.get("volume_ma_20")), "blue"),
        KpiCard("Latest RVOL", format_multiple(values.get("latest_relative_volume_20")), "violet"),
        KpiCard(
            "Latest dollar volume",
            format_money(values.get("latest_dollar_volume"), result.metadata.currency, compact=True),
            "green",
        ),
    ]


def dividend_kpi_cards(result: AnalysisResult) -> list[KpiCard]:
    """Format existing validated dividend metrics without recalculating them."""
    values = result.dividend_metrics
    currency = result.metadata.currency
    return [
        KpiCard("TTM dividend", format_money(values.get("ttm_dividend"), currency), "violet"),
        KpiCard("TTM yield", format_percent(values.get("current_ttm_dividend_yield"), 2), "blue"),
        KpiCard(
            "Latest annual dividend growth",
            format_percent(values.get("dividend_growth_1y")),
            _growth_accent(values.get("dividend_growth_1y")),
        ),
        KpiCard(
            "3Y dividend CAGR",
            format_percent(values.get("dividend_cagr_3y")),
            _growth_accent(values.get("dividend_cagr_3y")),
        ),
        KpiCard(
            "5Y dividend CAGR",
            format_percent(values.get("dividend_cagr_5y")),
            _growth_accent(values.get("dividend_cagr_5y")),
        ),
        KpiCard(
            "10Y dividend CAGR",
            format_percent(values.get("dividend_cagr_10y")),
            _growth_accent(values.get("dividend_cagr_10y")),
        ),
        KpiCard("Dividend-paying streak", _years(values.get("dividend_paying_streak")), "violet"),
    ]


def dividend_secondary_facts(result: AnalysisResult) -> list[tuple[str, str]]:
    values = result.dividend_metrics
    frequency = values.get("inferred_payment_frequency") or "N/A"
    return [
        ("Increase streak", _years(values.get("dividend_increase_streak"))),
        ("No-cut streak", _years(values.get("dividend_no_cut_streak"))),
        ("Payment frequency", str(frequency)),
    ]


def kpi_grid_html(cards: Iterable[KpiCard]) -> str:
    rendered = []
    allowed = {"blue", "green", "red", "violet", "warning"}
    for card in cards:
        accent = card.accent if card.accent in allowed else "blue"
        rendered.append(
            "<div class='ele-kpi ele-accent-{accent}'>"
            "<div class='ele-kpi-label'>{label}</div>"
            "<div class='ele-kpi-value'>{value}</div>"
            "</div>".format(
                accent=accent,
                label=escape(card.label.upper()),
                value=escape(card.value),
            )
        )
    return "<div class='ele-kpi-grid'>" + "".join(rendered) + "</div>"


def secondary_facts_html(facts: Iterable[tuple[str, str]]) -> str:
    rendered = "".join(
        f"<div class='ele-fact'><span>{escape(label)}</span><strong>{escape(value)}</strong></div>"
        for label, value in facts
    )
    return f"<div class='ele-facts'>{rendered}</div>"


def company_hero_html(result: AnalysisResult) -> str:
    metadata = result.metadata
    name = metadata.name or metadata.ticker
    details = [metadata.ticker, metadata.exchange, metadata.currency]
    if metadata.sector:
        details.append(metadata.sector)
    detail_text = " · ".join(escape(str(value)) for value in details if value)
    return (
        "<section class='ele-hero'>"
        "<div class='ele-kicker'>Equity Lifetime Explorer</div>"
        f"<h1>{escape(str(name))}</h1>"
        f"<div class='ele-company-meta'>{detail_text}</div>"
        "</section>"
    )


def visual_css(theme: str) -> str:
    """Return styling for app-owned elements; native shell colors come from config.toml."""
    dark = theme == "dark"
    hero_bg = (
        "linear-gradient(115deg, rgba(14,28,56,.97), rgba(54,28,70,.82))"
        if dark else
        "linear-gradient(115deg, rgba(230,241,255,.98), rgba(240,234,255,.94))"
    )
    card_bg = (
        "linear-gradient(135deg, rgba(21,35,66,.96), rgba(42,23,61,.86))"
        if dark else
        "linear-gradient(135deg, rgba(255,255,255,.98), rgba(242,246,255,.96))"
    )
    border = "#263757" if dark else "#C8D5E8"
    text = "#F7FBFF" if dark else "#172033"
    muted = "#AAB6CA" if dark else "#5B6B82"
    shadow = "0 12px 34px rgba(0,0,0,.24)" if dark else "0 10px 28px rgba(39,65,104,.11)"
    return f"""
    .block-container {{padding-top:1.25rem;padding-bottom:3rem;max-width:1580px;}}
    [data-testid="stSidebar"] h1 {{font-size:1.16rem;letter-spacing:.025em;}}
    .ele-hero {{background:{hero_bg};border:1px solid {border};border-radius:18px;
        padding:1.25rem 1.45rem 1.2rem;margin:.1rem 0 1rem;box-shadow:{shadow};}}
    .ele-hero h1 {{margin:.12rem 0 .22rem;font-size:clamp(1.8rem,3vw,2.75rem);line-height:1.08;
        color:{text};letter-spacing:-.025em;}}
    .ele-kicker {{letter-spacing:.11em;text-transform:uppercase;font-size:.72rem;color:#3AA7FF;font-weight:750;}}
    .ele-company-meta {{color:{muted};font-size:.92rem;font-weight:520;}}
    .ele-kpi-grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:.72rem;
        margin:.2rem 0 1.15rem;}}
    .ele-kpi {{position:relative;overflow:hidden;min-height:92px;background:{card_bg};border:1px solid {border};
        border-radius:17px;padding:.92rem 1rem .88rem 1.12rem;box-shadow:{shadow};}}
    .ele-kpi::before {{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:#3AA7FF;}}
    .ele-kpi.ele-accent-green::before {{background:#25E0A3;}}
    .ele-kpi.ele-accent-red::before {{background:#FF6B5A;}}
    .ele-kpi.ele-accent-violet::before {{background:#A78BFA;}}
    .ele-kpi.ele-accent-warning::before {{background:#FFD84D;}}
    .ele-kpi-label {{color:{muted};font-size:.66rem;font-weight:750;letter-spacing:.075em;line-height:1.25;
        margin-bottom:.54rem;}}
    .ele-kpi-value {{color:{text};font-size:clamp(1.18rem,1.7vw,1.55rem);font-weight:760;
        line-height:1.12;font-variant-numeric:tabular-nums;letter-spacing:-.018em;}}
    .ele-facts {{display:flex;flex-wrap:wrap;gap:.55rem;margin:.15rem 0 1rem;}}
    .ele-fact {{display:flex;gap:.5rem;align-items:center;border:1px solid {border};border-radius:999px;
        padding:.42rem .72rem;color:{muted};font-size:.78rem;}}
    .ele-fact strong {{color:{text};font-weight:680;}}
    .ele-section-label {{color:{muted};font-size:.78rem;letter-spacing:.07em;text-transform:uppercase;font-weight:720;}}
    @media (max-width:700px) {{
        .ele-hero {{padding:1rem 1.05rem;}}
        .ele-kpi-grid {{grid-template-columns:repeat(2,minmax(0,1fr));gap:.58rem;}}
        .ele-kpi {{min-height:84px;padding:.78rem .82rem .76rem .95rem;}}
        .ele-kpi-value {{font-size:1.08rem;}}
    }}
    """
