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
from ..models import CompanyMetadata, DataSourceRecord, ProviderPayload, ValidationIssue
from .base import MarketDataProvider
from .action_dates import ACTION_DATA_VERSION, action_rows, session_dates, reconcile_dedicated_actions

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


def _normalize_history_index(frame: pd.DataFrame, exchange_timezone=None) -> tuple[pd.DataFrame, int]:
    result = frame.copy()
    if exchange_timezone is None and isinstance(frame.index, pd.DatetimeIndex) and frame.index.tz is not None:
        exchange_timezone = str(frame.index.tz)
    index = session_dates(result.index, exchange_timezone)
    result.attrs["action_audit"] = action_rows(frame, index, "history")
    invalid = int(index.isna().sum())
    action_issues = [ValidationIssue("WARNING", "invalid_history_date",
        f"{invalid} invalid history timestamps were excluded; any raw action values remain in the audit.")] if invalid else []
    result = result.loc[~index.isna()].copy()
    index = index[~index.isna()]
    result.index = pd.DatetimeIndex(index, name="date")
    duplicate_count = int(result.index.duplicated(keep=False).sum())
    audit = result.attrs.get("action_audit", [])
    if duplicate_count:
        action_issues.append(ValidationIssue("WARNING", "action_source_conflict",
            f"{duplicate_count} history rows share an exchange-local session. Last daily price row retained; duplicate raw action observations remain in the audit and require review."))
        result = result.groupby(level=0).last()
    result.attrs["action_issues"] = action_issues
    result.attrs["action_audit"] = audit
    result.attrs["exchange_timezone"] = exchange_timezone
    result.sort_index(inplace=True)
    return result, duplicate_count + invalid


def _merge_dedicated_action_series(history: pd.DataFrame, obj: yf.Ticker, exchange_timezone=None) -> tuple[pd.DataFrame, list[str]]:
    """Use dedicated yfinance action endpoints as a defensive fallback/cross-check."""
    return reconcile_dedicated_actions(history, obj, exchange_timezone or history.attrs.get("exchange_timezone"))


class YahooFinanceProvider(MarketDataProvider):
    def __init__(self, cache_dir: Path = CACHE_DIR, cache_hours: float = 12.0):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_hours = float(cache_hours)

    def _cache_path(self, ticker: str) -> Path:
        safe = re.sub(r"[^A-Z0-9_.-]", "_", ticker)
        digest = hashlib.sha256(ticker.encode("utf-8")).hexdigest()[:10]
        return self.cache_dir / f"yahoo_{safe}_{digest}_{ACTION_DATA_VERSION}_max_daily.pkl"

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

        exchange_timezone = str(history.index.tz) if isinstance(history.index, pd.DatetimeIndex) and history.index.tz else None
        try:
            exchange_timezone = obj.history_metadata.get("exchangeTimezoneName") or exchange_timezone
        except Exception:
            pass  # Unverified timezone gets an explicit reconciliation warning.
        history, normalized_issues = _normalize_history_index(history, exchange_timezone)
        history, action_endpoint_notes = _merge_dedicated_action_series(history, obj, exchange_timezone)
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
        notes.append(f"Provider library version: yfinance {yf.__version__}.")
        notes.append(f"Action date convention: exchange-local session date; timezone={exchange_timezone or 'unverified'}; version={ACTION_DATA_VERSION}.")
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
            action_audit=pd.DataFrame(history.attrs.get("action_audit", [])),
            action_issues=history.attrs.get("action_issues", []),
        )
        try:
            with cache_path.open("wb") as handle:
                pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:
            LOGGER.warning("Could not write cache %s: %s", cache_path, exc)
        return payload

clean_ticker = _clean_ticker
