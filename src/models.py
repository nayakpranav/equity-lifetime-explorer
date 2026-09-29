"""Typed canonical data models extracted from Colab v5."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go

from .config import PROVIDER_NAME

@dataclass
class DataSourceRecord:
    provider: str
    retrieval_timestamp_utc: str
    ticker_requested: str
    ticker_resolved: str
    exchange: Optional[str]
    currency: Optional[str]
    first_available_observation: Optional[str]
    last_available_observation: Optional[str]
    repair_requested: bool
    repaired_observations: Optional[int]
    validation_status: str = "PENDING"
    cache_hit: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class CompanyMetadata:
    requested_ticker: str
    ticker: str
    name: str
    exchange: str
    currency: str
    country: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    security_type: Optional[str] = None
    website: Optional[str] = None
    market_cap: Optional[float] = None
    quote_type: Optional[str] = None


@dataclass
class CorporateAction:
    date: pd.Timestamp
    action_type: str
    ratio_numerator: Optional[float] = None
    ratio_denominator: Optional[float] = None
    share_multiplier: Optional[float] = None
    cash_amount: Optional[float] = None
    currency: Optional[str] = None
    source: str = PROVIDER_NAME
    source_description: str = ""
    confidence: str = "MEDIUM"
    notes: str = ""
    include_in_reconstruction: bool = False


@dataclass
class ValidationIssue:
    severity: str
    check: str
    message: str
    date: Optional[pd.Timestamp] = None


@dataclass
class ProviderPayload:
    requested_ticker: str
    resolved_ticker: str
    history: pd.DataFrame
    metadata: CompanyMetadata
    info: dict[str, Any]
    provenance: DataSourceRecord


@dataclass
class AnalysisResult:
    ticker: str
    metadata: CompanyMetadata
    prices: pd.DataFrame
    actions: pd.DataFrame
    metrics: dict[str, Any]
    validation: pd.DataFrame
    provenance: DataSourceRecord
    methodology: str
    volume_events: pd.DataFrame = field(default_factory=pd.DataFrame)
    dividend_events: pd.DataFrame = field(default_factory=pd.DataFrame)
    annual_dividends: pd.DataFrame = field(default_factory=pd.DataFrame)
    dividend_status: str = "NONE"
    dividend_metrics: dict[str, Any] = field(default_factory=dict)
    figure: Optional[go.Figure] = None
    volume_figure: Optional[go.Figure] = None
    dividend_figure: Optional[go.Figure] = None
