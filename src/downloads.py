"""Pure selection and packaging helpers for the Streamlit Download Center."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .exports import export_bundle, safe_ticker, zip_bytes
from .models import AnalysisResult


REPORT_EXPORTS = (
    ("lifetime_html", "Price & Ownership HTML"),
    ("volume_html", "Volume & Liquidity HTML"),
    ("dividend_html", "Dividends & Total Return HTML"),
    ("combined_html", "Complete Combined Research HTML"),
)

DATA_EXPORTS = (
    ("history_csv", "Full Historical Data CSV"),
    ("actions_csv", "Corporate Actions Ledger CSV"),
    ("dividend_csv", "Dividend Annual Summary CSV"),
    ("validation_csv", "Data Quality / Validation CSV"),
)


@dataclass(frozen=True)
class PreparedDownload:
    filename: str
    payload: bytes
    mime: str
    status: str


def export_is_available(result: AnalysisResult, key: str) -> bool:
    if key in {"dividend_html", "dividend_csv"}:
        return result.dividend_status != "NONE"
    return True


def default_export_selection(result: AnalysisResult) -> dict[str, bool]:
    """Return the visually scannable initial checkbox state."""
    keys = [key for key, _ in (*REPORT_EXPORTS, *DATA_EXPORTS)]
    return {key: key == "lifetime_html" and export_is_available(result, key) for key in keys}


def complete_export_keys(result: AnalysisResult) -> list[str]:
    """Return every applicable report and data export in a stable order."""
    return [
        key
        for key, _ in (*REPORT_EXPORTS, *DATA_EXPORTS)
        if export_is_available(result, key)
    ]


def prepare_selected_download(
    result: AnalysisResult,
    selections: list[str],
    *,
    theme: str = "dark",
    portable_html: bool = False,
    price_options: dict | None = None,
    stamp: date | None = None,
) -> PreparedDownload:
    """Build one direct file or one ZIP containing only the chosen exports."""
    if not selections:
        raise ValueError("Select at least one export.")
    files = export_bundle(
        result,
        selections,
        theme=theme,
        portable_html=portable_html,
        price_options=price_options,
        stamp=stamp,
    )
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
    stamp: date | None = None,
) -> PreparedDownload:
    """Build the complete applicable research package on demand."""
    report_date = (stamp or date.today()).isoformat()
    files = export_bundle(
        result,
        complete_export_keys(result),
        theme=theme,
        portable_html=portable_html,
        price_options=price_options,
        stamp=stamp,
    )
    filename = f"{safe_ticker(result.ticker)}_Equity_Lifetime_Explorer_{report_date}.zip"
    return PreparedDownload(
        filename,
        zip_bytes(files),
        "application/zip",
        "Complete analysis package ready",
    )
