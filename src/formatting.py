"""Currency-aware presentation helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

def currency_parts(currency: str) -> tuple[str, str]:
    code = (currency or "").upper()
    symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "INR": "₹",
        "JPY": "¥",
        "CHF": "CHF ",
        "CAD": "C$",
        "AUD": "A$",
        "DKK": "DKK ",
        "SEK": "SEK ",
        "NOK": "NOK ",
        "HKD": "HK$",
        "CNY": "CN¥",
        "KRW": "₩",
    }
    if code in {"GBX", "GBPENCE"}:
        return "", "p"
    return (symbols.get(code, f"{currency} " if currency else ""), "")


def format_money(value: Any, currency: str, compact: bool = False) -> str:
    if value is None or pd.isna(value):
        return "Not available"
    prefix, suffix = currency_parts(currency)
    number = float(value)
    if compact:
        magnitude = abs(number)
        for scale, label in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if magnitude >= scale:
                return f"{prefix}{number / scale:,.2f}{label}{suffix}"
    decimals = 4 if abs(number) < 1 else 2
    return f"{prefix}{number:,.{decimals}f}{suffix}"


def format_percent(value: Any, decimals: int = 1) -> str:
    return "Not available" if value is None or pd.isna(value) else f"{float(value):.{decimals}%}"


def format_multiple(value: Any) -> str:
    if value is None or pd.isna(value):
        return "Not available"
    number = float(value)
    return f"{number:,.4g}×"


def format_quantity(value: Any, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "Not available"
    number = float(value)
    magnitude = abs(number)
    for scale, label in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if magnitude >= scale:
            return f"{number / scale:,.{decimals}f}{label}"
    return f"{number:,.{decimals}f}"
