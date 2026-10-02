"""Separate provider boundary for financial filings."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import CompanyMetadata


class FinancialDataProvider(ABC):
    @abstractmethod
    def fetch(self, metadata: CompanyMetadata, *, force_refresh: bool = False):
        raise NotImplementedError
