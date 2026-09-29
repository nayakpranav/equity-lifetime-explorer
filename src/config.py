"""Application and financial-engine constants."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

PROVIDER_NAME = "Yahoo Finance / yfinance"
CACHE_DIR = Path(os.getenv("ELE_CACHE_DIR", str(Path(tempfile.gettempdir()) / "equity-lifetime-explorer-cache")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = 365.2425
SHARE_CHANGING_TYPES = {
    "stock_split",
    "reverse_split",
    "bonus_issue",
    "stock_dividend",
}
KNOWN_ACTION_TYPES = SHARE_CHANGING_TYPES | {
    "cash_dividend",
    "special_dividend",
    "rights_issue",
    "spin_off",
    "symbol_change",
    "merger",
    "other",
}
THEMES = {
    "dark": {
        "paper": "#0B111B",
        "plot": "#0B111B",
        "text": "#E7EEF8",
        "muted": "#93A4B8",
        "grid": "rgba(147,164,184,0.15)",
        "primary": "#62D9FF",
        "raw": "#FFB454",
        "adjusted": "#A78BFA",
        "volume": "rgba(111,135,159,0.42)",
        "volume_up": "rgba(80,160,145,0.58)",
        "volume_down": "rgba(190,112,120,0.55)",
        "volume_flat": "rgba(111,135,159,0.46)",
        "volume_ma20": "#62D9FF",
        "volume_ma50": "#D8A7FF",
        "dollar_volume": "rgba(232,193,90,0.48)",
        "rvol": "#E8C15A",
        "drawdown": "#F07178",
        "event": "#E8C15A",
        "dividend": "#63D3A6",
        "card": "rgba(255,255,255,0.045)",
        "control_bg": "#182235",
        "control_text": "#F8FAFC",
        "control_border": "#52627A",
        "control_active": "#2563EB",
    },
    "light": {
        "paper": "#F8FAFC",
        "plot": "#F8FAFC",
        "text": "#182230",
        "muted": "#64748B",
        "grid": "rgba(71,85,105,0.16)",
        "primary": "#0077A8",
        "raw": "#B55D00",
        "adjusted": "#7048B6",
        "volume": "rgba(100,116,139,0.34)",
        "volume_up": "rgba(45,125,111,0.52)",
        "volume_down": "rgba(172,91,99,0.50)",
        "volume_flat": "rgba(100,116,139,0.38)",
        "volume_ma20": "#0077A8",
        "volume_ma50": "#7048B6",
        "dollar_volume": "rgba(154,107,0,0.42)",
        "rvol": "#9A6B00",
        "drawdown": "#C2414B",
        "event": "#9A6B00",
        "dividend": "#178F68",
        "card": "rgba(15,23,42,0.045)",
        "control_bg": "#FFFFFF",
        "control_text": "#172033",
        "control_border": "#94A3B8",
        "control_active": "#BFDBFE",
    },
}

LOGGER = logging.getLogger("equity_lifetime_explorer")
