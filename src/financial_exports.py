"""On-demand, in-memory SEC Fundamentals reports and provenance-rich CSVs."""

from __future__ import annotations

import html

import pandas as pd

from .charts.fundamentals import build_fundamentals_figures
from .config import THEMES
from .financial_models import FundamentalsResult
from .financial_ui import fundamentals_kpi_cards


def _safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if column in {"value", "original_value"} or column.endswith("_value"):
            continue
        if output[column].dtype != object:
            continue
        output[column] = output[column].map(
            lambda value: "'" + value if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}
            else value
        )
    return output


def financial_csv(frame: pd.DataFrame) -> bytes:
    return _safe_frame(frame).to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")


def annual_financial_csv(result: FundamentalsResult) -> bytes:
    if not result.available:
        raise ValueError("Financial annual statements are unavailable")
    return financial_csv(result.annual)


def quarterly_financial_csv(result: FundamentalsResult) -> bytes:
    if result.quarterly.empty:
        raise ValueError("Standalone quarterly statements are unavailable")
    return financial_csv(result.quarterly)


def financial_ratios_csv(result: FundamentalsResult) -> bytes:
    if result.ratios.empty:
        raise ValueError("Financial ratios are unavailable")
    return financial_csv(result.ratios)


def financial_provenance_csv(result: FundamentalsResult) -> bytes:
    if result.observations.empty:
        raise ValueError("SEC observation provenance is unavailable")
    columns = [
        "observation_id", "issuer_id", "ticker", "provider", "taxonomy", "provider_concept",
        "normalized_concept", "context_type", "period_start", "period_end", "fiscal_year",
        "fiscal_quarter", "period_type", "filing_date", "acceptance_timestamp_utc",
        "currency", "unit", "value", "accession", "form", "source_url",
        "source_record_locator", "source_sha256", "retrieved_at_utc",
        "revision_status", "quality_status", "quality_flags", "mapping_version",
    ]
    frame = result.observations[[column for column in columns if column in result.observations]].copy()
    decisions = result.metadata.get("selection_decisions")
    if isinstance(decisions, pd.DataFrame) and not decisions.empty:
        frame = frame.merge(decisions, on="observation_id", how="left")
    return financial_csv(frame)


def fundamentals_html(result: FundamentalsResult, *, theme: str = "dark", portable: bool = False) -> bytes:
    if not result.available:
        raise ValueError("Financial Fundamentals report is unavailable")
    if theme not in THEMES:
        raise ValueError("theme must be dark or light")
    identity = result.identity
    palette = THEMES[theme]
    figures = build_fundamentals_figures(result, theme=theme)
    include_js: str | bool = True if portable else "cdn"
    chart_sections = []
    for index, (heading, figure) in enumerate(figures.items()):
        chart_sections.append(
            f"<section class='panel'><h2>{html.escape(heading)}</h2>"
            + figure.to_html(full_html=False, include_plotlyjs=include_js if index == 0 else False,
                             config={"displaylogo": False, "responsive": True})
            + "</section>"
        )
    cards = "".join(
        f"<div class='card'><small>{html.escape(card.label.upper())}</small>"
        f"<strong>{html.escape(card.value)}</strong></div>"
        for card in fundamentals_kpi_cards(result)
    )
    annual_table = result.annual[[column for column in (
        "fiscal_year", "period_end", "currency", "revenue", "operating_income",
        "net_income_consolidated", "ocf", "capex_ppe", "fcf", "cash_equivalents",
        "reported_long_term_debt", "fcf_status", "net_debt_status",
    ) if column in result.annual]].tail(15).to_html(index=False, escape=True, classes="data-table", border=0)
    coverage_table = result.coverage.to_html(index=False, escape=True, classes="data-table", border=0)
    quality_table = result.quality.head(50).to_html(index=False, escape=True, classes="data-table", border=0)
    page = "#060913" if theme == "dark" else "#F4F7FC"
    panel = "#0A1326" if theme == "dark" else "#FFFFFF"
    border = "#263757" if theme == "dark" else "#C8D5E8"
    document = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{html.escape(identity.issuer_name)} — Financial Fundamentals</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:{page};color:{palette['text']};font-family:Inter,Arial,sans-serif}}
main{{max-width:1450px;margin:auto;padding:30px clamp(16px,4vw,56px)}}
h1{{font-size:clamp(27px,4vw,42px);margin:4px 0}}h2{{font-size:21px}}p,small{{color:{palette['muted']}}}
.hero,.panel,.card{{background:{panel};border:1px solid {border};border-radius:17px;box-shadow:0 12px 34px rgba(0,0,0,.12)}}
.hero,.panel{{padding:20px;margin:0 0 20px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:10px;margin:18px 0}}
.card{{padding:15px;border-left:4px solid {palette['primary']}}}.card small{{display:block;font-size:10px;letter-spacing:.06em;margin-bottom:8px}}.card strong{{font-size:20px}}
.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{padding:8px;border-bottom:1px solid {border};text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}
</style></head><body><main><header class='hero'><small>EQUITY LIFETIME EXPLORER · SEC EDGAR</small>
<h1>{html.escape(identity.issuer_name)}</h1><p>Financial Fundamentals · {html.escape(identity.ticker)} · CIK {identity.cik} · {identity.reporting_currency} · {html.escape(result.latest_view)}</p></header>
<div class='cards'>{cards}</div>{''.join(chart_sections)}
<section class='panel'><h2>Annual Statement Summary</h2><div class='table-wrap'>{annual_table}</div></section>
<section class='panel'><h2>Coverage and Data Quality</h2><div class='table-wrap'>{coverage_table}</div><h2>Quality Flags</h2><div class='table-wrap'>{quality_table}</div></section>
<section class='panel'><h2>Methodology and Provenance</h2><p>Company Facts supplies standard entity-wide reported facts. This is latest-disclosed history and may include later revisions. It is not point-in-time historical valuation data. Monetary quarterly cash flows are reconstructed only from compatible cumulative filings. Missing values are unavailable, not zero. PPE cash payments are positive outflows; ordinary FCF equals OCF less those payments. Acquisitions are excluded. Reported long-term debt is not a verified complete debt total, so net debt is unavailable.</p>
<p>Source: SEC EDGAR Company Facts and submissions · Retrieved {html.escape(result.retrieved_at_utc or '')} · Mapping {html.escape(result.mapping_version)} · Source SHA-256 {html.escape(result.source_sha256 or '')}</p>
<p>For informational and research purposes only. No historical valuation multiples are calculated in this release.</p></section>
</main></body></html>"""
    return document.encode("utf-8")
