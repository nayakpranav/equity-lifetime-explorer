"""Pure selection and packaging helpers for the Streamlit Download Center."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .exports import export_bundle, safe_ticker, zip_bytes
from .financial_models import FundamentalsResult
from .models import AnalysisResult


REPORT_EXPORTS = (
    ("lifetime_html", "Price & Ownership HTML"),
    ("volume_html", "Volume & Liquidity HTML"),
    ("dividend_html", "Dividends & Total Return HTML"),
    ("fundamentals_html", "Financial Fundamentals HTML"),
    ("combined_html", "Complete Combined Research HTML"),
)

DATA_EXPORTS = (
    ("history_csv", "Full Historical Data CSV"),
    ("actions_csv", "Corporate Actions Ledger CSV"),
    ("dividend_csv", "Dividend Annual Summary CSV"),
    ("validation_csv", "Data Quality / Validation CSV"),
    ("financial_annual_csv", "SEC Annual Financials CSV"),
    ("financial_quarterly_csv", "SEC Standalone Quarterly Financials CSV"),
    ("financial_ratios_csv", "Financial Ratios CSV"),
    ("financial_provenance_csv", "SEC Financial Provenance CSV"),
    ("financial_quality_csv", "SEC Financial Quality CSV"),
)


@dataclass(frozen=True)
class PreparedDownload:
    filename: str
    payload: bytes
    mime: str
    status: str


def export_unavailability_reason(
    result: AnalysisResult, key: str, fundamentals: FundamentalsResult | None = None,
) -> str | None:
    if key in {"dividend_html", "dividend_csv"}:
        return None if result.dividend_status != "NONE" else "No provider-reported cash-dividend history."
    if key.startswith("financial_") or key == "fundamentals_html":
        if fundamentals is None:
            return "Run ANALYZE to check SEC financial availability."
        if key == "financial_provenance_csv" and fundamentals.available and not fundamentals.observations.empty:
            return None
        if key == "financial_quality_csv" and fundamentals.available:
            return None
        if key == "financial_quarterly_csv" and fundamentals.available and not fundamentals.quarterly.empty:
            return None
        if key == "financial_ratios_csv" and fundamentals.available and not fundamentals.ratios.empty:
            return None
        if fundamentals.available and key in {"fundamentals_html", "financial_annual_csv"}:
            return None
        return fundamentals.reason or f"Financial Fundamentals unavailable ({fundamentals.status})."
    return None


def export_is_available(result: AnalysisResult, key: str, fundamentals: FundamentalsResult | None = None) -> bool:
    return export_unavailability_reason(result, key, fundamentals) is None


def default_export_selection(result: AnalysisResult, fundamentals: FundamentalsResult | None = None) -> dict[str, bool]:
    """Return the visually scannable initial checkbox state."""
    keys = [key for key, _ in (*REPORT_EXPORTS, *DATA_EXPORTS)]
    return {key: key == "lifetime_html" and export_is_available(result, key, fundamentals) for key in keys}


def complete_export_keys(result: AnalysisResult, fundamentals: FundamentalsResult | None = None) -> list[str]:
    """Return every applicable report and data export in a stable order."""
    return [
        key
        for key, _ in (*REPORT_EXPORTS, *DATA_EXPORTS)
        if export_is_available(result, key, fundamentals)
    ]


def prepare_selected_download(
    result: AnalysisResult,
    selections: list[str],
    *,
    theme: str = "dark",
    portable_html: bool = False,
    price_options: dict | None = None,
    fundamentals: FundamentalsResult | None = None,
    financial_price_overlay: bool = False,
    stamp: date | None = None,
) -> PreparedDownload:
    """Build one direct file or one ZIP containing only the chosen exports."""
    if not selections:
        raise ValueError("Select at least one export.")
    export_options = {
        "theme": theme,
        "portable_html": portable_html,
        "price_options": price_options,
    }
    if fundamentals is not None:
        export_options["fundamentals"] = fundamentals
    if financial_price_overlay:
        export_options["financial_price_overlay"] = True
    if stamp is not None:
        export_options["stamp"] = stamp
    files = export_bundle(result, selections, **export_options)
    if len(files) == 1:
        filename, payload = next(iter(files.items()))
        mime = "text/html" if filename.endswith(".html") else "text/csv"
        return PreparedDownload(filename, payload, mime, "1 download ready")
    report_date = (stamp or date.today()).isoformat()
    filename = f"{safe_ticker(result.ticker)}_selected_exports_{report_date}.zip"
    return PreparedDownload(
        filename,
        zip_bytes(files),
        "application/zip",
        f"{len(files)} selected exports packaged",
    )


def prepare_complete_package(
    result: AnalysisResult,
    *,
    theme: str = "dark",
    portable_html: bool = False,
    price_options: dict | None = None,
    fundamentals: FundamentalsResult | None = None,
    financial_price_overlay: bool = False,
    stamp: date | None = None,
) -> PreparedDownload:
    """Build the complete applicable research package on demand."""
    report_date = (stamp or date.today()).isoformat()
    export_options = {
        "theme": theme,
        "portable_html": portable_html,
        "price_options": price_options,
    }
    if fundamentals is not None:
        export_options["fundamentals"] = fundamentals
    if financial_price_overlay:
        export_options["financial_price_overlay"] = True
    if stamp is not None:
        export_options["stamp"] = stamp
    files = export_bundle(result, complete_export_keys(result, fundamentals), **export_options)
    if fundamentals is not None:
        excluded = [
            f"{label}: {export_unavailability_reason(result, key, fundamentals)}"
            for key, label in (*REPORT_EXPORTS, *DATA_EXPORTS)
            if key.startswith("financial_") or key == "fundamentals_html"
            if not export_is_available(result, key, fundamentals)
        ]
        files[f"{safe_ticker(result.ticker)}_financial_status_{report_date}.txt"] = (
            f"Financial Fundamentals status: {fundamentals.status}\n"
            f"Source: {fundamentals.source}\n"
            f"Retrieved: {fundamentals.retrieved_at_utc or 'unavailable'}\n"
            + ("Excluded: \n" + "\n".join(excluded) if excluded else "All available SEC outputs included.")
        ).encode("utf-8")
    filename = f"{safe_ticker(result.ticker)}_Equity_Lifetime_Explorer_{report_date}.zip"
    return PreparedDownload(
        filename,
        zip_bytes(files),
        "application/zip",
        "Complete analysis package ready",
    )
