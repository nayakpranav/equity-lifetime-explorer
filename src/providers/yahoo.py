"""Yahoo Finance provider; retrieval behavior is preserved from Colab v5."""

from __future__ import annotations

import hashlib
import math
import pickle
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from ..config import CACHE_DIR, LOGGER, PROVIDER_NAME
from ..models import CompanyMetadata, DataSourceRecord, ProviderPayload
from .base import MarketDataProvider

def _clean_ticker(ticker: str) -> tuple[str, list[str]]:
    requested = str(ticker).strip().upper()
    if not requested:
        raise ValueError("Ticker cannot be empty.")
    aliases = {"BRK.B": "BRK-B", "BF.B": "BF-B"}
    resolved = aliases.get(requested, requested)
    if not re.fullmatch(r"[A-Z0-9^=][A-Z0-9.\-^=]{0,24}", resolved):
        raise ValueError(
            "Ticker contains unsupported characters. Use the provider symbol, "
            "including exchange suffixes such as SAP.DE or RELIANCE.NS."
        )
    notes = []
    if resolved != requested:
        notes.append(f"Applied explicit ticker alias {requested} → {resolved}.")
    return resolved, notes


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return default


def _safe_fast_info(ticker_obj: yf.Ticker) -> dict[str, Any]:
    try:
        fast = ticker_obj.fast_info
        keys = (
            "currency",
            "exchange",
            "market_cap",
            "last_price",
            "timezone",
            "quote_type",
        )
        return {key: getattr(fast, key, None) for key in keys}
    except Exception as exc:
        LOGGER.warning("fast_info unavailable: %s", exc)
        return {}


def _safe_info(ticker_obj: yf.Ticker) -> dict[str, Any]:
    try:
        value = ticker_obj.info
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        LOGGER.warning("info unavailable; continuing with fast_info/history: %s", exc)
        return {}


def _normalize_history_index(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    result = frame.copy()
    index = pd.to_datetime(result.index, errors="coerce", utc=True)
    invalid = int(index.isna().sum())
    result = result.loc[~index.isna()].copy()
    index = index[~index.isna()].tz_convert(None).normalize()
    result.index = pd.DatetimeIndex(index, name="date")
    duplicate_count = int(result.index.duplicated(keep=False).sum())
    if duplicate_count:
        result = result.groupby(level=0).last()
    result.sort_index(inplace=True)
    return result, duplicate_count + invalid


def _merge_dedicated_action_series(history: pd.DataFrame, obj: yf.Ticker) -> tuple[pd.DataFrame, list[str]]:
    """Use dedicated yfinance action endpoints as a defensive fallback/cross-check."""
    result = history.copy()
    notes: list[str] = []
    for attribute, column in (("splits", "Stock Splits"), ("dividends", "Dividends")):
        try:
            series = getattr(obj, attribute)
            if not isinstance(series, pd.Series) or series.empty:
                continue
            index = pd.to_datetime(series.index, errors="coerce", utc=True)
            valid = ~index.isna()
            dedicated = pd.Series(
                pd.to_numeric(series.loc[valid], errors="coerce").to_numpy(),
                index=pd.DatetimeIndex(index[valid]).tz_convert(None).normalize(),
            ).dropna()
            dedicated = dedicated[dedicated != 0].groupby(level=0).last()
            if dedicated.empty:
                continue
            if column not in result.columns:
                result[column] = 0.0
            missing_dates = dedicated.index.difference(result.index)
            if len(missing_dates):
                result = result.reindex(result.index.union(missing_dates).sort_values())
            existing = pd.to_numeric(result.loc[dedicated.index, column], errors="coerce").fillna(0.0)
            fill_mask = existing.eq(0.0)
            if fill_mask.any():
                dates_to_fill = dedicated.index[fill_mask.to_numpy()]
                result.loc[dates_to_fill, column] = dedicated.loc[dates_to_fill].to_numpy()
                notes.append(
                    f"Filled {len(dates_to_fill)} {column} records from the dedicated Ticker.{attribute} endpoint."
                )
            conflicting = (~fill_mask) & ~np.isclose(existing.to_numpy(), dedicated.to_numpy(), rtol=1e-8, atol=1e-12)
            if np.any(conflicting):
                notes.append(
                    f"Detected {int(np.sum(conflicting))} differences between history and Ticker.{attribute}; history values were retained for review."
                )
        except Exception as exc:
            notes.append(f"Dedicated Ticker.{attribute} endpoint unavailable: {exc}")
    result.sort_index(inplace=True)
    return result, notes


class YahooFinanceProvider(MarketDataProvider):
    def __init__(self, cache_dir: Path = CACHE_DIR, cache_hours: float = 12.0):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_hours = float(cache_hours)

    def _cache_path(self, ticker: str) -> Path:
        safe = re.sub(r"[^A-Z0-9_.-]", "_", ticker)
        digest = hashlib.sha256(ticker.encode("utf-8")).hexdigest()[:10]
        return self.cache_dir / f"yahoo_{safe}_{digest}_max_daily.pkl"

    def _read_cache(self, path: Path) -> Optional[ProviderPayload]:
        if not path.exists():
            return None
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if age_hours > self.cache_hours:
            return None
        try:
            with path.open("rb") as handle:
                payload = pickle.load(handle)
            if isinstance(payload, ProviderPayload):
                payload.provenance.cache_hit = True
                payload.provenance.notes.append(
                    f"Loaded a {age_hours:.1f}-hour-old local cache entry."
                )
                return payload
        except Exception as exc:
            LOGGER.warning("Ignoring unreadable cache %s: %s", path, exc)
        return None

    def fetch(self, ticker: str, force_refresh: bool = False) -> ProviderPayload:
        symbol, alias_notes = _clean_ticker(ticker)
        cache_path = self._cache_path(symbol)
        if not force_refresh:
            cached = self._read_cache(cache_path)
            if cached is not None:
                return cached

        obj = yf.Ticker(symbol)
        last_error: Optional[Exception] = None
        history = pd.DataFrame()
        repair_requested = True
        for attempt in range(3):
            try:
                try:
                    history = obj.history(
                        period="max",
                        interval="1d",
                        auto_adjust=False,
                        actions=True,
                        repair=True,
                    )
                except TypeError:
                    repair_requested = False
                    history = obj.history(
                        period="max",
                        interval="1d",
                        auto_adjust=False,
                        actions=True,
                    )
                except ModuleNotFoundError as exc:
                    repair_requested = False
                    LOGGER.warning(
                        "yfinance repair dependency %s is unavailable in this runtime; retrying without repair.",
                        exc.name,
                    )
                    history = obj.history(
                        period="max",
                        interval="1d",
                        auto_adjust=False,
                        actions=True,
                    )
                if history is not None and not history.empty:
                    break
            except Exception as exc:
                last_error = exc
                LOGGER.warning("History attempt %d/3 failed: %s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))

        if history is None or history.empty:
            detail = f" Provider error: {last_error}" if last_error else ""
            raise LookupError(
                f"No daily history was returned for {symbol}. Verify the provider "
                f"symbol, delisting status, network access, or rate limits.{detail}"
            )

        history, normalized_issues = _normalize_history_index(history)
        history, action_endpoint_notes = _merge_dedicated_action_series(history, obj)
        if "Close" not in history.columns or history["Close"].notna().sum() == 0:
            raise ValueError(f"{symbol} history has no usable Close observations.")

        info = _safe_info(obj)
        fast = _safe_fast_info(obj)
        resolved = str(_first(info, "symbol", default=symbol)).upper()
        if resolved != symbol:
            raise LookupError(
                f"Provider returned symbol {resolved} for requested symbol {symbol}. "
                "Automatic ambiguous resolution is disabled; use the exact Yahoo ticker."
            )
        exchange = str(
            _first(info, "fullExchangeName", "exchange", default=fast.get("exchange") or "Unknown")
        )
        currency = str(_first(info, "currency", default=fast.get("currency") or "Unknown"))
        name = str(_first(info, "longName", "shortName", default=resolved))
        quote_type = _first(info, "quoteType", default=fast.get("quote_type"))

        metadata = CompanyMetadata(
            requested_ticker=str(ticker).strip().upper(),
            ticker=resolved,
            name=name,
            exchange=exchange,
            currency=currency,
            country=_first(info, "country"),
            sector=_first(info, "sector"),
            industry=_first(info, "industry"),
            security_type=quote_type,
            website=_first(info, "website"),
            market_cap=_first(info, "marketCap", default=fast.get("market_cap")),
            quote_type=quote_type,
        )
        repaired_count = None
        for col in ("Repaired?", "repaired"):
            if col in history.columns:
                repaired_count = int(history[col].fillna(False).astype(bool).sum())
                break
        notes = alias_notes.copy()
        notes.extend(action_endpoint_notes)
        if normalized_issues:
            notes.append(
                f"Normalized the date index; {normalized_issues} invalid/duplicate rows were encountered."
            )
        if repair_requested:
            notes.append("Requested yfinance repair logic; repaired-row count may be unavailable.")
        else:
            notes.append(
                "yfinance repair was unsupported or lacked an optional dependency in this runtime; retrieval completed without repair."
            )
        notes.append("No paid API key is required; corporate actions use the primary source only.")
        provenance = DataSourceRecord(
            provider=PROVIDER_NAME,
            retrieval_timestamp_utc=datetime.now(timezone.utc).isoformat(),
            ticker_requested=str(ticker).strip().upper(),
            ticker_resolved=resolved,
            exchange=exchange,
            currency=currency,
            first_available_observation=history.index.min().date().isoformat(),
            last_available_observation=history.index.max().date().isoformat(),
            repair_requested=repair_requested,
            repaired_observations=repaired_count,
            cache_hit=False,
            notes=notes,
        )
        payload = ProviderPayload(
            requested_ticker=str(ticker).strip().upper(),
            resolved_ticker=resolved,
            history=history,
            metadata=metadata,
            info=info,
            provenance=provenance,
        )
        try:
            with cache_path.open("wb") as handle:
                pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:
            LOGGER.warning("Could not write cache %s: %s", cache_path, exc)
        return payload

clean_ticker = _clean_ticker
