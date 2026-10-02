"""In-memory CSV, HTML, and ZIP exports for Streamlit and tests."""

from __future__ import annotations

import html
import io
import re
import zipfile
from datetime import date
from typing import Callable

import pandas as pd
import plotly.graph_objects as go

from .charts import build_dividend_chart, build_lifetime_chart, build_volume_chart
from .config import THEMES
from .financial_exports import (
    annual_financial_csv, financial_provenance_csv, financial_ratios_csv, financial_quality_csv,
    fundamentals_html, quarterly_financial_csv,
)
from .financial_models import FundamentalsResult
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


def _report_cards(cards: list[tuple[str, str]]) -> str:
    return "".join(
        "<div class='card'><small>{}</small><strong>{}</strong></div>".format(
            html.escape(label.upper()), html.escape(value)
        )
        for label, value in cards
    )


def _report_table(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    if frame.empty:
        return "<div class='empty-state'>No records are available for this section.</div>"
    selected = [column for column in (columns or list(frame.columns)) if column in frame.columns]
    return "<div class='table-wrap'>" + frame[selected].to_html(
        index=False,
        border=0,
        classes="data-table",
        escape=True,
    ) + "</div>"


def combined_research_html(
    result: AnalysisResult,
    *,
    theme: str = "dark",
    portable: bool = False,
    price_options: dict | None = None,
    fundamentals: FundamentalsResult | None = None,
) -> bytes:
    """Compose one navigable research report with a single Plotly.js payload."""
    if theme not in THEMES:
        raise ValueError("theme must be dark or light")
    metadata = result.metadata
    palette = THEMES[theme]
    include_js: str | bool = True if portable else "cdn"
    chart_config = {"displaylogo": False, "responsive": True}
    price_figure = build_lifetime_chart(result, theme=theme, **(price_options or {}))
    volume_figure = build_volume_chart(result, theme=theme)
    price_chart = price_figure.to_html(
        full_html=False,
        include_plotlyjs=include_js,
        config=chart_config,
        div_id="price-ownership-chart",
    )
    volume_chart = volume_figure.to_html(
        full_html=False,
        include_plotlyjs=False,
        config=chart_config,
        div_id="volume-liquidity-chart",
    )
    if result.dividend_status == "NONE":
        dividend_chart = (
            "<div class='empty-state dividend-empty'>"
            "<strong>No provider-reported cash-dividend history is available for this security.</strong>"
            "<span>Price, ownership and liquidity analysis remain available elsewhere in this report.</span>"
            "</div>"
        )
        dividend_cards = ""
        dividend_table = ""
    else:
        dividend_figure = build_dividend_chart(result, theme=theme)
        dividend_chart = dividend_figure.to_html(
            full_html=False,
            include_plotlyjs=False,
            config=chart_config,
            div_id="dividend-total-return-chart",
        )
        dividend_cards = f"<div class='cards'>{_report_cards(_kpi_cards(result, 'dividend'))}</div>"
        dividend_table = "<h3>Annual Dividend Summary</h3>" + _report_table(
            result.annual_dividends.tail(15)
        )

    if fundamentals is not None and fundamentals.available:
        from .charts.fundamentals import build_fundamentals_figures
        from .financial_ui import fundamentals_kpi_cards

        financial_cards = "<div class='cards'>" + _report_cards([
            (card.label, card.value) for card in fundamentals_kpi_cards(fundamentals)
        ]) + "</div>"
        financial_charts = "".join(
            f"<h3>{html.escape(heading)}</h3><div class='chart'>"
            + figure.to_html(full_html=False, include_plotlyjs=False, config=chart_config)
            + "</div>"
            for heading, figure in build_fundamentals_figures(fundamentals, theme=theme).items()
        )
        financial_content = (
            financial_cards + financial_charts
            + "<h3>Annual SEC Statement Summary</h3>" + _report_table(fundamentals.annual, [
                "fiscal_year", "period_end", "currency", "revenue", "operating_income",
                "net_income_parent", "eps_basic", "eps_diluted", "eps_diluted_yoy",
                "roe", "roe_status", "roce", "roce_status", "ocf", "capex_ppe",
                "productive_asset_spending", "fcf", "fcf_status",
            ])
            + "<h3>Concept Coverage</h3>" + _report_table(fundamentals.coverage)
            + "<div class='section-copy'>Latest-disclosed SEC history may contain later revisions. "
            "SEC NetIncomeLoss is parent-attributable income. Reported EPS retains its original share basis; "
            "growth uses same-filing comparatives only. ROE uses average parent equity; ROCE uses average "
            "assets less current liabilities with operating income as an EBIT proxy. "
            "PPE purchases are positive outflows; ordinary FCF is OCF less PPE purchases. "
            "NVIDIA's broader productive-asset spending is separately labelled. "
            "Reported long-term debt is partial, so net debt is withheld. "
            "This is not a point-in-time historical valuation series.</div>"
        )
    else:
        reason = fundamentals.reason if fundamentals is not None else "SEC financial analysis has not been run for this result."
        financial_content = (
            "<div class='empty-state'><strong>Financial Fundamentals unavailable.</strong>"
            f"<span>{html.escape(reason)}</span></div>"
        )

    factor = result.metrics.get("cumulative_share_multiplier")
    if factor is None or abs(float(factor) - 1.0) < 1e-10:
        ownership = "No included share-changing action alters the earliest-observation share basis."
    else:
        ownership = (
            f"One share at the earliest provider observation represents {float(factor):,.6g} current shares "
            "after included recorded actions."
        )

    volume_events = result.volume_events
    if not volume_events.empty and "relative_volume_rank" in volume_events:
        volume_events = volume_events.dropna(subset=["relative_volume_rank"]).nsmallest(
            10, "relative_volume_rank"
        )
    volume_columns = [
        "date", "raw_close", "daily_return", "volume", "volume_ma_20",
        "relative_volume_20", "dollar_volume", "direction",
    ]
    action_columns = [
        "date", "event", "ratio", "share_multiplier", "cumulative_multiplier",
        "source", "confidence", "included_in_reconstruction", "notes",
    ]
    provenance = result.provenance
    provenance_frame = pd.DataFrame(
        [
            ("Primary provider", provenance.provider),
            ("Retrieval timestamp", provenance.retrieval_timestamp_utc),
            ("First observation", provenance.first_available_observation),
            ("Latest observation", provenance.last_available_observation),
            ("Observations", f"{len(result.prices):,}"),
            ("Corporate-action records", f"{len(result.actions):,}"),
            ("Data-quality confidence", provenance.validation_status),
        ],
        columns=["Field", "Value"],
    )
    notes = "".join(f"<li>{html.escape(str(note))}</li>" for note in provenance.notes)
    methodology = html.escape(result.methodology).replace("\n", "<br>")
    portable_note = (
        "Self-contained Plotly JavaScript is embedded once for all charts."
        if portable else
        "Plotly JavaScript loads once from the CDN; internet access is required when opening this report."
    )
    panel = "#0A1326" if theme == "dark" else "#FFFFFF"
    page = "#060913" if theme == "dark" else "#F4F7FC"
    line = "#263757" if theme == "dark" else "#C8D5E8"
    nav = "rgba(7,13,27,.94)" if theme == "dark" else "rgba(244,247,252,.94)"
    card_background = (
        "linear-gradient(135deg,rgba(21,35,66,.97),rgba(42,23,61,.88))"
        if theme == "dark" else
        "linear-gradient(135deg,rgba(255,255,255,.99),rgba(242,246,255,.97))"
    )
    title = f"{metadata.name or metadata.ticker} — Complete Equity Research Report"
    document = f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{html.escape(title)}</title>
<style>
:root{{--page:{page};--panel:{panel};--ink:{palette['text']};--muted:{palette['muted']};--line:{line};--blue:{palette['primary']};--green:{palette['dividend']};--red:{palette['drawdown']};--violet:{palette['adjusted']};--nav:{nav}}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth;scroll-padding-top:76px}}body{{margin:0;background:var(--page);color:var(--ink);font-family:Inter,Arial,sans-serif}}
.topnav{{position:sticky;top:0;z-index:50;display:flex;gap:6px;align-items:center;overflow-x:auto;padding:11px max(16px,calc((100vw - 1500px)/2));background:var(--nav);backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}}
.topnav a{{white-space:nowrap;color:var(--muted);text-decoration:none;padding:8px 11px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.025em}}.topnav a:hover{{color:var(--ink);background:var(--panel)}}
main{{max-width:1500px;margin:auto;padding:28px clamp(16px,4vw,58px) 60px}}.hero{{padding:24px clamp(20px,3vw,36px);border:1px solid var(--line);border-radius:20px;background:linear-gradient(115deg,{panel},rgba(66,35,92,.70));box-shadow:0 16px 42px rgba(0,0,0,.20)}}
.eyebrow{{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}}h1{{font-size:clamp(30px,4vw,48px);letter-spacing:-.035em;margin:7px 0 6px}}.meta,.section-copy,footer{{color:var(--muted);line-height:1.55}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:11px;margin:18px 0}}.card{{position:relative;overflow:hidden;min-height:88px;padding:15px 16px;border:1px solid var(--line);border-radius:17px;background:{card_background};box-shadow:0 10px 28px rgba(0,0,0,.15)}}
.card:before{{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--blue)}}.card small{{display:block;color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.075em;margin-bottom:8px}}.card strong{{font-size:20px;font-variant-numeric:tabular-nums}}
.report-section{{margin-top:30px;padding:22px;border:1px solid var(--line);border-radius:19px;background:var(--panel);box-shadow:0 12px 34px rgba(0,0,0,.12)}}h2{{margin:0 0 7px;font-size:clamp(22px,2.4vw,31px)}}h3{{margin:24px 0 10px}}.chart{{margin-top:16px;overflow:hidden;border:1px solid var(--line);border-radius:16px}}
.callout,.empty-state{{display:flex;flex-direction:column;gap:7px;padding:16px 18px;border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:14px;background:{card_background};line-height:1.5}}.dividend-empty{{border-left-color:var(--violet);margin-top:16px}}.dividend-empty span{{color:var(--muted)}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:14px;margin-top:12px}}.data-table{{width:100%;border-collapse:collapse;font-size:12px}}.data-table th,.data-table td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}.data-table th{{color:var(--muted);background:{card_background};position:sticky;top:0}}.data-table th:first-child,.data-table td:first-child{{text-align:left}}
.method-copy{{line-height:1.65}}footer{{padding:28px 4px 0;font-size:12px}}@media(max-width:760px){{.report-section{{padding:16px}}.topnav{{padding:9px 12px}}.cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}.card strong{{font-size:17px}}}}
</style></head><body>
<nav class='topnav' aria-label='Report sections'><a href='#overview'>Overview</a><a href='#price'>Price &amp; Ownership</a><a href='#volume'>Volume &amp; Liquidity</a><a href='#dividends'>Dividends &amp; Total Return</a><a href='#fundamentals'>Financial Fundamentals</a><a href='#actions'>Corporate Actions</a><a href='#validation'>Data Quality</a><a href='#methodology'>Methodology</a></nav>
<main><header class='hero' id='overview'><div class='eyebrow'>Equity Lifetime Explorer</div><h1>{html.escape(metadata.name or metadata.ticker)}</h1><div class='meta'>{html.escape(metadata.ticker)} · {html.escape(metadata.exchange)} · {html.escape(metadata.currency)}{(' · ' + html.escape(metadata.sector)) if metadata.sector else ''} · {len(result.prices):,} observations</div></header>
<section class='cards'>{_report_cards(_kpi_cards(result, 'lifetime'))}</section>
<section class='report-section' id='price'><h2>Price &amp; Ownership</h2><div class='section-copy'>Raw market quotations, provider-adjusted history and the mechanical ownership-equivalent reconstruction.</div><div class='chart'>{price_chart}</div><div class='callout'><strong>Ownership-equivalent interpretation</strong><span>{html.escape(ownership)} This is a mechanical reconstruction, not a counterfactual market-price forecast.</span></div></section>
<section class='report-section' id='volume'><h2>Volume &amp; Liquidity</h2><div class='section-copy'>Long-run share volume, dollar volume, relative activity and unusual participation.</div><div class='cards'>{_report_cards(_kpi_cards(result, 'volume'))}</div><div class='chart'>{volume_chart}</div><h3>Notable Volume Events</h3>{_report_table(volume_events, volume_columns)}<div class='section-copy'>High volume indicates elevated participation; it does not identify participant classes or establish accumulation, distribution or causation.</div></section>
<section class='report-section' id='dividends'><h2>Dividends &amp; Total Return</h2><div class='section-copy'>Provider-reported dividends, completed-year growth, historical yield and total-return context.</div>{dividend_cards}<div class='chart'>{dividend_chart}</div>{dividend_table}</section>
<section class='report-section' id='fundamentals'><h2>Financial Fundamentals</h2><div class='section-copy'>SEC-reported operating performance, cash generation and financial position.</div>{financial_content}</section>
<section class='report-section' id='actions'><h2>Corporate Actions</h2><div class='section-copy'>Provider and researched share-changing events used by the existing validated reconstruction.</div>{_report_table(result.actions, action_columns)}</section>
<section class='report-section' id='validation'><h2>Data Quality</h2><div class='section-copy'>Overall confidence: <strong>{html.escape(provenance.validation_status)}</strong></div>{_report_table(result.validation)}</section>
<section class='report-section' id='methodology'><h2>Methodology &amp; Provenance</h2>{_report_table(provenance_frame)}<h3>Methodological notes</h3><div class='method-copy'>{methodology}</div>{('<h3>Provider notes</h3><ul>' + notes + '</ul>') if notes else ''}<div class='callout'><strong>Limitations</strong><span>Market data may be delayed, incomplete or retrospectively adjusted. Mechanical no-split values are ownership-equivalent reconstructions and are not estimates of prices that would necessarily have prevailed without corporate actions. {portable_note}</span></div></section>
<footer>For informational and research purposes only. This report is not investment advice.</footer></main></body></html>"""
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
    fundamentals: FundamentalsResult | None = None,
    stamp: date | None = None,
) -> dict[str, bytes]:
    """Generate only selected exports; no persistent filesystem is required."""
    report_date = (stamp or date.today()).isoformat()
    ticker = safe_ticker(result.ticker)
    builders: dict[str, tuple[str, Callable[[], bytes]]] = {
        "lifetime_html": (f"{ticker}_lifetime_chart_{report_date}.html", lambda: report_html(result, "lifetime", theme=theme, portable=portable_html, price_options=price_options)),
        "volume_html": (f"{ticker}_volume_liquidity_{report_date}.html", lambda: report_html(result, "volume", theme=theme, portable=portable_html)),
        "combined_html": (f"{ticker}_complete_research_report_{report_date}.html", lambda: combined_research_html(result, theme=theme, portable=portable_html, price_options=price_options, fundamentals=fundamentals)),
        "history_csv": (f"{ticker}_lifetime_history_{report_date}.csv", lambda: historical_csv(result)),
        "actions_csv": (f"{ticker}_corporate_actions_{report_date}.csv", lambda: actions_csv(result)),
        "validation_csv": (f"{ticker}_validation_{report_date}.csv", lambda: validation_csv(result)),
    }
    if result.dividend_status != "NONE":
        builders.update({
            "dividend_html": (f"{ticker}_dividend_total_return_{report_date}.html", lambda: report_html(result, "dividend", theme=theme, portable=portable_html)),
            "dividend_csv": (f"{ticker}_dividend_summary_{report_date}.csv", lambda: dividend_summary_csv(result)),
        })
    if fundamentals is not None and fundamentals.available:
        builders.update({
            "fundamentals_html": (f"{ticker}_financial_fundamentals_{report_date}.html", lambda: fundamentals_html(fundamentals, theme=theme, portable=portable_html)),
            "financial_annual_csv": (f"{ticker}_sec_annual_financials_{report_date}.csv", lambda: annual_financial_csv(fundamentals)),
            "financial_ratios_csv": (f"{ticker}_financial_ratios_{report_date}.csv", lambda: financial_ratios_csv(fundamentals)),
            "financial_provenance_csv": (f"{ticker}_sec_financial_provenance_{report_date}.csv", lambda: financial_provenance_csv(fundamentals)),
            "financial_quality_csv": (f"{ticker}_sec_financial_quality_{report_date}.csv", lambda: financial_quality_csv(fundamentals)),
        })
        if not fundamentals.quarterly.empty:
            builders["financial_quarterly_csv"] = (f"{ticker}_sec_quarterly_financials_{report_date}.csv", lambda: quarterly_financial_csv(fundamentals))
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
