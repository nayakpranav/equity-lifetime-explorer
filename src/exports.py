"""In-memory CSV, HTML, and ZIP exports for Streamlit and tests."""

from __future__ import annotations

import html
import io
import json
import re
import zipfile
from datetime import date
from typing import Callable

import pandas as pd
import plotly.graph_objects as go

from .charts import build_dividend_chart, build_lifetime_chart, build_volume_chart
from .config import THEMES
from .formatting import format_money, format_multiple, format_percent
from .models import AnalysisResult


HISTORY_COLUMNS = [
    "open", "high", "low", "raw_close", "adjusted_close", "volume",
    "volume_ma_20", "volume_ma_50", "relative_volume_20", "dollar_volume",
    "dollar_volume_ma_20", "volume_direction", "volume_event", "dividend",
    "provider_dividend", "split_adjusted_price_current_share", "ttm_dividend",
    "ttm_dividend_yield", "split_factor", "cumulative_split_factor",
    "no_split_close", "drawdown",
]


def safe_ticker(ticker: str) -> str:
    return re.sub(r"[^A-Z0-9_.-]", "_", ticker.upper())


def csv_bytes(frame: pd.DataFrame, *, index: bool = False) -> bytes:
    return frame.to_csv(index=index, date_format="%Y-%m-%d").encode("utf-8")


def historical_csv(result: AnalysisResult) -> bytes:
    frame = result.prices[[column for column in HISTORY_COLUMNS if column in result.prices]].copy()
    frame.index.name = "date"
    return csv_bytes(frame, index=True)


def actions_csv(result: AnalysisResult) -> bytes:
    return csv_bytes(result.actions)


def validation_csv(result: AnalysisResult) -> bytes:
    return csv_bytes(result.validation)


def dividend_summary_csv(result: AnalysisResult) -> bytes:
    if result.dividend_status == "NONE" or result.annual_dividends.empty:
        raise ValueError("No positive provider-reported dividend history is available.")
    columns = ["year", "annual_dividend", "payment_count", "yoy_growth", "completed_year", "ytd"]
    return csv_bytes(result.annual_dividends[columns])


def _kpi_cards(result: AnalysisResult, report: str) -> list[tuple[str, str]]:
    metrics = result.metrics
    currency = result.metadata.currency
    if report == "lifetime":
        return [
            ("Latest price", format_money(metrics.get("latest_raw_close"), currency)),
            ("No-split equivalent", format_money(metrics.get("latest_no_split_equivalent"), currency, compact=True)),
            ("Lifetime multiple", format_multiple(metrics.get("lifetime_price_multiple"))),
            ("Lifetime CAGR", format_percent(metrics.get("lifetime_cagr"))),
            ("Share multiplier", format_multiple(metrics.get("cumulative_share_multiplier"))),
            ("Maximum drawdown", format_percent(metrics.get("maximum_drawdown"))),
        ]
    if report == "volume":
        return [
            ("Latest volume", f"{metrics.get('latest_volume'):,.4g}" if metrics.get("latest_volume") is not None else "N/A"),
            ("20D average", f"{metrics.get('volume_ma_20'):,.4g}" if metrics.get("volume_ma_20") is not None else "N/A"),
            ("Latest RVOL", format_multiple(metrics.get("latest_relative_volume_20"))),
            ("Latest dollar volume", format_money(metrics.get("latest_dollar_volume"), currency, compact=True)),
        ]
    dividend = result.dividend_metrics
    return [
        ("TTM dividend", format_money(dividend.get("ttm_dividend"), currency)),
        ("TTM yield", format_percent(dividend.get("current_ttm_dividend_yield"), 2)),
        ("Latest annual dividend growth", format_percent(dividend.get("dividend_growth_1y"))),
        ("3Y dividend CAGR", format_percent(dividend.get("dividend_cagr_3y"))),
        ("5Y dividend CAGR", format_percent(dividend.get("dividend_cagr_5y"))),
        ("10Y dividend CAGR", format_percent(dividend.get("dividend_cagr_10y"))),
        ("Paying streak", f"{dividend.get('dividend_paying_streak', 0)} years"),
    ]


def standalone_html(
    result: AnalysisResult,
    figure: go.Figure,
    *,
    report: str,
    title: str,
    theme: str = "dark",
    include_plotlyjs: str | bool = "cdn",
) -> bytes:
    """Create a professional report shell around a focused Plotly visualization."""
    cards = "".join(
        f"<div class='card'><small>{html.escape(label.upper())}</small><strong>{html.escape(value)}</strong></div>"
        for label, value in _kpi_cards(result, report)
    )
    supporting = ""
    if report == "volume" and not result.volume_events.empty:
        table = result.volume_events.dropna(subset=["relative_volume_rank"]).nsmallest(10, "relative_volume_rank")
        supporting = "<h2>Notable Volume Events</h2>" + table[[
            "date", "raw_close", "daily_return", "volume", "relative_volume_20", "dollar_volume", "direction"
        ]].to_html(index=False, border=0, classes="data-table")
    elif report == "dividend" and not result.annual_dividends.empty:
        supporting = "<h2>Annual Dividend Summary</h2>" + result.annual_dividends.tail(15).to_html(
            index=False, border=0, classes="data-table"
        )
    figure_html = figure.to_html(full_html=False, include_plotlyjs=include_plotlyjs, config={"displaylogo": False, "responsive": True})
    portable_note = (
        "Self-contained Plotly JavaScript is embedded."
        if include_plotlyjs is True else
        "Plotly JavaScript loads from a CDN; an internet connection is required when opening this report."
    )
    metadata = result.metadata
    palette = THEMES[theme]
    panel = "#0A1326" if theme == "dark" else "#FFFFFF"
    line = "#263757" if theme == "dark" else "#C8D5E8"
    card_background = (
        "linear-gradient(135deg,rgba(21,35,66,.96),rgba(42,23,61,.86))"
        if theme == "dark" else
        "linear-gradient(135deg,rgba(255,255,255,.98),rgba(242,246,255,.96))"
    )
    shadow = "0 10px 28px rgba(0,0,0,.24)" if theme == "dark" else "0 10px 26px rgba(39,65,104,.11)"
    document = f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{html.escape(title)}</title>
<style>
:root{{--ink:{palette['text']};--muted:{palette['muted']};--line:{line};--panel:{panel};--accent:{palette['primary']};--page:{palette['paper']}}}
*{{box-sizing:border-box}}body{{font-family:Inter,Arial,sans-serif;color:var(--ink);margin:0;background:var(--page)}}
main{{max-width:1500px;margin:auto;padding:30px clamp(16px,4vw,58px)}}
h1{{margin:0 0 6px;font-size:clamp(25px,4vw,42px)}}h2{{margin-top:34px}}.meta{{color:var(--muted);margin-bottom:22px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:11px;margin:20px 0}}
.card{{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:17px;padding:14px 15px;background:{card_background};box-shadow:{shadow}}}
.card:before{{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent)}}
.card small{{display:block;color:var(--muted);font-size:11px;margin-bottom:6px}}.card strong{{font-size:19px}}
.chart{{margin-top:18px;border:1px solid var(--line);border-radius:18px;overflow:hidden;background:var(--panel)}}.data-table{{border-collapse:collapse;width:100%;font-size:13px;overflow:auto}}
.data-table th,.data-table td{{padding:7px;border-bottom:1px solid var(--line);text-align:right}}.data-table th:first-child,.data-table td:first-child{{text-align:left}}
.method{{margin-top:30px;padding:16px;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:14px;background:var(--panel);line-height:1.55}}
footer{{margin-top:28px;color:var(--muted);font-size:12px;line-height:1.5}}
</style></head><body><main>
<h1>{html.escape(title)}</h1>
<div class='meta'>{html.escape(metadata.name)} · {html.escape(metadata.ticker)} · {html.escape(metadata.exchange)} · {html.escape(metadata.currency)} · {len(result.prices):,} observations</div>
<section class='cards'>{cards}</section><section class='chart'>{figure_html}</section>{supporting}
<section class='method'><strong>Data & methodology</strong><br>{html.escape(result.methodology)}</section>
<footer>Provider: {html.escape(result.provenance.provider)} · Retrieved {html.escape(result.provenance.retrieval_timestamp_utc)} · Quality {html.escape(result.provenance.validation_status)}.<br>
For informational and research purposes only. Market data may be delayed, incomplete or retrospectively adjusted by the provider. Mechanical no-split values are ownership-equivalent reconstructions and are not estimates of the price that would necessarily have prevailed without corporate actions.<br>{portable_note}</footer>
</main></body></html>"""
    return document.encode("utf-8")


def report_html(
    result: AnalysisResult,
    report: str,
    *,
    theme: str = "dark",
    portable: bool = False,
    price_options: dict | None = None,
) -> bytes:
    include_js: str | bool = True if portable else "cdn"
    if report == "lifetime":
        figure = build_lifetime_chart(result, theme=theme, **(price_options or {}))
        title = f"{result.metadata.name} — Price & Ownership"
    elif report == "volume":
        figure = build_volume_chart(result, theme=theme)
        title = f"{result.metadata.name} — Volume & Liquidity"
    elif report == "dividend":
        if result.dividend_status == "NONE":
            raise ValueError("No positive provider-reported dividend history is available.")
        figure = build_dividend_chart(result, theme=theme)
        title = f"{result.metadata.name} — Dividends & Total Return"
    else:
        raise ValueError("Unknown report type")
    return standalone_html(result, figure, report=report, title=title, theme=theme, include_plotlyjs=include_js)


def export_bundle(
    result: AnalysisResult,
    selections: list[str],
    *,
    theme: str = "dark",
    portable_html: bool = False,
    price_options: dict | None = None,
) -> dict[str, bytes]:
    """Generate only selected exports; no persistent filesystem is required."""
    stamp = date.today().isoformat()
    ticker = safe_ticker(result.ticker)
    builders: dict[str, tuple[str, Callable[[], bytes]]] = {
        "lifetime_html": (f"{ticker}_lifetime_chart_{stamp}.html", lambda: report_html(result, "lifetime", theme=theme, portable=portable_html, price_options=price_options)),
        "volume_html": (f"{ticker}_volume_liquidity_{stamp}.html", lambda: report_html(result, "volume", theme=theme, portable=portable_html)),
        "history_csv": (f"{ticker}_lifetime_history_{stamp}.csv", lambda: historical_csv(result)),
        "actions_csv": (f"{ticker}_corporate_actions_{stamp}.csv", lambda: actions_csv(result)),
        "validation_csv": (f"{ticker}_validation_{stamp}.csv", lambda: validation_csv(result)),
    }
    if result.dividend_status != "NONE":
        builders.update({
            "dividend_html": (f"{ticker}_dividend_total_return_{stamp}.html", lambda: report_html(result, "dividend", theme=theme, portable=portable_html)),
            "dividend_csv": (f"{ticker}_dividend_summary_{stamp}.csv", lambda: dividend_summary_csv(result)),
        })
    output: dict[str, bytes] = {}
    for key in selections:
        if key not in builders:
            raise ValueError(f"Export {key!r} is unavailable for this analysis.")
        filename, builder = builders[key]
        output[filename] = builder()
    return output


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, payload in files.items():
            archive.writestr(filename, payload)
    return buffer.getvalue()
