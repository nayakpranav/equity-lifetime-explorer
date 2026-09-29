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
        "paper": "#070D1B",
        "plot": "#0A1326",
        "text": "#F7FBFF",
        "muted": "#AAB6CA",
        "grid": "rgba(38,55,87,0.62)",
        "primary": "#3AA7FF",
        "raw": "#FFB454",
        "adjusted": "#A78BFA",
        "volume": "rgba(111,135,159,0.42)",
        "volume_up": "rgba(80,160,145,0.58)",
        "volume_down": "rgba(190,112,120,0.55)",
        "volume_flat": "rgba(111,135,159,0.46)",
        "volume_ma20": "#3AA7FF",
        "volume_ma50": "#A78BFA",
        "dollar_volume": "rgba(232,193,90,0.48)",
        "rvol": "#E8C15A",
        "drawdown": "#FF6B5A",
        "event": "#FFD84D",
        "dividend": "#25E0A3",
        "card": "rgba(16,26,49,0.92)",
        "control_bg": "#101A31",
        "control_text": "#F7FBFF",
        "control_border": "#263757",
        "control_active": "#1E5F91",
    },
    "light": {
        "paper": "#F4F7FC",
        "plot": "#FFFFFF",
        "text": "#172033",
        "muted": "#5B6B82",
        "grid": "rgba(151,169,196,0.34)",
        "primary": "#1878B8",
        "raw": "#B55D00",
        "adjusted": "#7048B6",
        "volume": "rgba(100,116,139,0.34)",
        "volume_up": "rgba(45,125,111,0.52)",
        "volume_down": "rgba(172,91,99,0.50)",
        "volume_flat": "rgba(100,116,139,0.38)",
        "volume_ma20": "#1878B8",
        "volume_ma50": "#7254B8",
        "dollar_volume": "rgba(154,107,0,0.42)",
        "rvol": "#9A6B00",
        "drawdown": "#C2414B",
        "event": "#9A6B00",
        "dividend": "#128665",
        "card": "rgba(241,245,252,0.96)",
        "control_bg": "#F8FAFE",
        "control_text": "#172033",
        "control_border": "#C8D5E8",
        "control_active": "#D9ECFF",
    },
}

LOGGER = logging.getLogger("equity_lifetime_explorer")
