"""Provider abstraction."""

from abc import ABC, abstractmethod

from ..models import ProviderPayload

class MarketDataProvider(ABC):
    """Small provider boundary designed for future Alpha Vantage/FMP adapters."""

    @abstractmethod
    def fetch(self, ticker: str, force_refresh: bool = False) -> ProviderPayload:
        raise NotImplementedError
