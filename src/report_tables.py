"""Reader-facing HTML table formatting; canonical data and CSVs stay untouched."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from .formatting import format_money, format_multiple, format_percent, format_quantity


MONEY_COLUMNS = {
    "revenue", "operating_income", "net_income_parent", "gross_profit", "ocf",
    "capex_ppe", "productive_asset_spending", "fcf", "cash_equivalents",
    "reported_long_term_debt", "total_debt", "net_debt", "shareholders_equity",
    "assets", "liabilities", "current_assets", "current_liabilities", "dollar_volume", "dollar_volume_ma_20",
    "long_term_debt_noncurrent", "long_term_debt_current", "short_term_borrowings", "commercial_paper",
}
PER_SHARE_COLUMNS = {"eps_basic", "eps_diluted", "raw_close", "annual_dividend"}
PERCENT_COLUMNS = {
    "operating_margin", "net_margin", "fcf_margin", "eps_basic_yoy",
    "eps_diluted_yoy", "eps_basic_cagr_3y", "eps_diluted_cagr_3y", "roe",
    "roce", "ocf_to_income", "daily_return", "yoy_growth", "ttm_dividend_yield",
}
QUANTITY_COLUMNS = {"volume", "volume_ma_20", "volume_ma_50"}


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _per_share(value: Any, currency: str) -> str:
    if _missing(value):
        return "—"
    number = float(value)
    # Extra precision matters for sub-unit EPS and historical dividend amounts.
    from .formatting import currency_parts

    prefix, suffix = currency_parts(currency)
    decimals = 4 if abs(number) < 1 else 3
    return f"{prefix}{number:,.{decimals}f}{suffix}"


def display_cell(value: Any, column: str, currency: str) -> str:
    """Format a scalar by *column meaning*, never by its numeric magnitude alone."""
    if _missing(value):
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if column in {"year", "fiscal_year", "raw_fiscal_year"}:
        return str(int(value))
    if column in PER_SHARE_COLUMNS:
        return _per_share(value, currency)
    if column in MONEY_COLUMNS:
        return format_money(value, currency, compact=True)
    if column in PERCENT_COLUMNS or column.endswith("_yoy") or "_cagr_" in column:
        return format_percent(value, decimals=2 if abs(float(value)) < 0.01 else 1)
    if column == "relative_volume_20":
        return format_multiple(value)
    if column in QUANTITY_COLUMNS:
        return format_quantity(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.4g}"
    return str(value)


def display_frame(frame: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Create a presentation-only copy, including explicit missing-value markers."""
    output = frame.copy()
    for column in output.columns:
        output[column] = output[column].map(lambda value, name=column: display_cell(value, name, currency))
    return output


def _header(column: str) -> str:
    parts = str(column).split("_")
    acronyms = {"eps": "EPS", "fcf": "FCF", "ocf": "OCF", "roe": "ROE", "roce": "ROCE", "yoy": "YoY", "cagr": "CAGR", "rvol": "RVOL", "utc": "UTC"}
    return " ".join(acronyms.get(part, part.capitalize()) for part in parts)


def report_table_html(frame: pd.DataFrame, currency: str, *, columns: list[str] | None = None) -> str:
    selected = [column for column in (columns or list(frame.columns)) if column in frame.columns]
    if not selected or frame.empty:
        return "<div class='empty-state'>No records are available for this section.</div>"
    return display_frame(frame[selected], currency).rename(columns=_header).to_html(
        index=False, border=0, classes="data-table", escape=True,
    )
