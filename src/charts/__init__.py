"""Plotly analytical workspaces."""

from .dividends import build_dividend_chart
from .lifetime import build_lifetime_chart
from .volume import build_volume_chart

__all__ = ["build_lifetime_chart", "build_volume_chart", "build_dividend_chart"]
