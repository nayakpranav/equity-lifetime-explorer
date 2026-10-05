"""Independent Release A financial-data results; market AnalysisResult is unchanged."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .models import AnalysisResult


@dataclass(frozen=True)
class SecurityIdentity:
    ticker: str
    cik: str
    issuer_name: str
    issuer_id: str
    security_id: str
    exchange: str | None
    reporting_currency: str
    fiscal_year_end: str
    sec_ticker: str | None = None
    identity_method: str = "exact_ticker"
    sic: str | None = None
    sic_description: str | None = None
    accounting_framework: str = "US_GAAP"
    consolidation_basis: str = "unknown"
    identity_evidence_url: str | None = None
    share_basis_verified: bool = False


@dataclass
class FundamentalsResult:
    ticker: str
    status: str
    reason: str = ""
    identity: SecurityIdentity | None = None
    observations: pd.DataFrame = field(default_factory=pd.DataFrame)
    annual: pd.DataFrame = field(default_factory=pd.DataFrame)
    quarterly: pd.DataFrame = field(default_factory=pd.DataFrame)
    ratios: pd.DataFrame = field(default_factory=pd.DataFrame)
    coverage: pd.DataFrame = field(default_factory=pd.DataFrame)
    quality: pd.DataFrame = field(default_factory=pd.DataFrame)
    retrieved_at_utc: str | None = None
    source_sha256: str | None = None
    mapping_version: str = "sec-general-2026-10-05"
    latest_view: str = "Latest-disclosed history"
    source: str = "SEC EDGAR Company Facts and submissions"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.status in {"AVAILABLE", "PARTIAL"} and (not self.annual.empty or not self.quarterly.empty)


@dataclass(frozen=True)
class ResearchResult:
    market: AnalysisResult
    fundamentals: FundamentalsResult
