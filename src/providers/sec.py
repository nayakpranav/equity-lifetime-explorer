"""Identified, rate-limited SEC Company Facts and submissions client."""

from __future__ import annotations

import hashlib
import copy
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from ..financial_models import SecurityIdentity
from ..models import CompanyMetadata
from ..financials.concepts import mappings_for
from .financial_base import FinancialDataProvider


class SecConfigurationError(RuntimeError):
    pass


class SecTransportError(RuntimeError):
    pass


class UnsupportedSecIdentity(LookupError):
    pass


class UnsupportedReportingBasis(LookupError):
    pass


class MissingStructuredData(LookupError):
    pass


@dataclass(frozen=True)
class SecFinancialPayload:
    identity: SecurityIdentity
    facts: dict[str, Any]
    accession_ledger: dict[str, dict[str, str | None]]
    retrieved_at_utc: str
    source_sha256: str
    older_file_count: int
    older_files_loaded: int
    taxonomy: str = "us-gaap"


_RATE_LOCK = threading.Lock()
_LAST_REQUEST = 0.0
_JSON_CACHE: dict[str, tuple[float, dict, bytes, str]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 12 * 60 * 60


def listing_key(ticker: str) -> str:
    """Only the documented dot/dash share-class spelling equivalence."""
    return ticker.upper().strip().replace(".", "-")


def configured_sec_user_agent() -> str | None:
    """Read the real operator identity at runtime, never from source defaults."""
    agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not agent:
        try:
            import streamlit as st

            agent = str(st.secrets.get("SEC_USER_AGENT", "")).strip()
        except (AttributeError, FileNotFoundError, KeyError):
            return None
    return agent if "@" in agent and " " in agent else None


class SecFinancialProvider(FinancialDataProvider):
    def __init__(self, user_agent: str | None = None, *, session: requests.Session | None = None):
        agent = user_agent or configured_sec_user_agent()
        if not agent or "@" not in agent or " " not in agent:
            raise SecConfigurationError("A real SEC_USER_AGENT contact is required.")
        self._session = session or requests.Session()
        self._cache_enabled = session is None
        self._force_refresh = False
        self._response_times: dict[str, str] = {}
        self._session.headers.update({
            "User-Agent": agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        })

    def _json(self, url: str) -> tuple[dict[str, Any], bytes]:
        global _LAST_REQUEST
        if self._cache_enabled and not self._force_refresh:
            with _CACHE_LOCK:
                cached = _JSON_CACHE.get(url)
                if cached and time.monotonic() - cached[0] < _CACHE_TTL:
                    self._response_times[url] = cached[3]
                    return copy.deepcopy(cached[1]), cached[2]
        for attempt in range(3):
            with _RATE_LOCK:
                delay = 0.5 - (time.monotonic() - _LAST_REQUEST)
                if delay > 0:
                    time.sleep(delay)
                _LAST_REQUEST = time.monotonic()
            try:
                response = self._session.get(url, timeout=(8, 35))
            except requests.RequestException as exc:
                if attempt == 2:
                    raise SecTransportError("SEC transport failed") from exc
                time.sleep(min(4.0, 0.5 * 2**attempt + random.random() * 0.2))
                continue
            if response.status_code in {403, 429}:
                raise SecTransportError(f"SEC access restricted ({response.status_code})")
            if response.status_code == 404:
                if "/companyfacts/" in url:
                    raise MissingStructuredData("Verified SEC issuer has no Company Facts structured financial history.")
                raise UnsupportedSecIdentity("SEC structured data is unavailable for this verified issuer.")
            if response.status_code >= 500 and attempt < 2:
                time.sleep(min(5.0, 0.5 * 2**attempt + random.random() * 0.2))
                continue
            if response.status_code != 200:
                raise SecTransportError(f"SEC returned HTTP {response.status_code}")
            if len(response.content) > 25_000_000:
                raise SecTransportError("SEC response exceeded size limit")
            try:
                value = response.json()
            except ValueError as exc:
                raise SecTransportError("SEC returned invalid JSON") from exc
            if not isinstance(value, dict):
                raise SecTransportError("SEC response was not an object")
            self._response_times[url] = datetime.now(timezone.utc).isoformat()
            if self._cache_enabled:
                with _CACHE_LOCK:
                    if len(_JSON_CACHE) >= 128:
                        _JSON_CACHE.pop(next(iter(_JSON_CACHE)))
                    _JSON_CACHE[url] = (time.monotonic(), copy.deepcopy(value), response.content, self._response_times[url])
            return value, response.content
        raise SecTransportError("SEC transport failed after retries")

    @staticmethod
    def _ledger(columns: dict[str, list]) -> dict[str, dict[str, str | None]]:
        count = min(len(columns.get("accessionNumber", [])), len(columns.get("filingDate", [])))
        output: dict[str, dict[str, str | None]] = {}
        for index in range(count):
            accession = columns["accessionNumber"][index]
            if not accession:
                continue
            accepted = columns.get("acceptanceDateTime", [])
            forms = columns.get("form", [])
            output[accession] = {
                "filing_date": columns["filingDate"][index],
                "acceptance": accepted[index] if index < len(accepted) else None,
                "form": forms[index] if index < len(forms) else None,
            }
        return output

    def fetch(self, metadata: CompanyMetadata, *, force_refresh: bool = False) -> SecFinancialPayload:
        self._force_refresh = force_refresh
        ticker = metadata.ticker.upper().strip()
        if metadata.security_type and metadata.security_type.upper() in {"ETF", "FUND", "INDEX", "CURRENCY", "CRYPTOCURRENCY"}:
            raise UnsupportedSecIdentity("This security type has no conventional issuer statements.")
        directory, _ = self._json("https://www.sec.gov/files/company_tickers.json")
        candidates = [row for row in directory.values() if listing_key(str(row.get("ticker", ""))) == listing_key(ticker)]
        if len(candidates) != 1:
            raise UnsupportedSecIdentity("No exact SEC ticker-to-issuer match was found.")
        cik = f"{int(candidates[0]['cik_str']):010d}"
        submissions, submissions_raw = self._json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        if str(submissions.get("cik", "")).lstrip("0") != str(int(cik)):
            raise UnsupportedSecIdentity("SEC submissions issuer identity does not match the ticker directory.")
        listed = [str(value).upper() for value in submissions.get("tickers", [])]
        matches = [index for index, value in enumerate(listed) if listing_key(value) == listing_key(ticker)]
        if len(matches) != 1:
            raise UnsupportedSecIdentity("SEC submissions do not confirm this listing ticker.")
        fiscal_year_end = str(submissions.get("fiscalYearEnd") or "")
        if len(fiscal_year_end) != 4 or not fiscal_year_end.isdigit():
            raise UnsupportedSecIdentity("SEC issuer fiscal year end is unavailable.")
        listing_index = matches[0]
        exchanges = submissions.get("exchanges", [])
        identity = SecurityIdentity(
            ticker=ticker,
            cik=cik,
            issuer_name=str(submissions.get("name") or candidates[0].get("title") or ticker),
            issuer_id=f"SEC:CIK{cik}",
            security_id=f"SEC:CIK{cik}:{ticker}",
            exchange=str(exchanges[listing_index]) if listing_index < len(exchanges) else None,
            reporting_currency="USD",
            fiscal_year_end=fiscal_year_end,
            sec_ticker=listed[listing_index],
            identity_method="exact_ticker" if listed[listing_index] == ticker else "verified_share_class_alias",
            sic=str(submissions.get("sic") or "") or None,
            sic_description=submissions.get("sicDescription"),
        )
        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        facts, raw = self._json(facts_url)
        if str(facts.get("cik", "")).lstrip("0") != str(int(cik)):
            raise SecTransportError("SEC Company Facts issuer identity did not match the submissions issuer")
        filings = submissions.get("filings", {})
        ledger = self._ledger(filings.get("recent", {}))
        older_files = filings.get("files", [])
        # Load only blocks containing dates of mapped 10-K/10-Q facts whose
        # accession is absent from the recent ledger. Large insider-filing
        # histories must not prevent otherwise compatible company coverage.
        needed: dict[str, str] = {}
        for mapping in mappings_for(ticker, cik):
            for row in facts.get("facts", {}).get("us-gaap", {}).get(mapping.tag, {}).get("units", {}).get(mapping.unit, []):
                end = row.get("end", "")
                if (row.get("form") in {"10-K", "10-K/A", "10-Q", "10-Q/A"}
                        and row.get("accn") not in ledger and row.get("filed")
                        and (not mapping.first_end or end >= mapping.first_end)
                        and (not mapping.last_end or end <= mapping.last_end)):
                    needed[row["accn"]] = row["filed"]
        source_hash = hashlib.sha256()
        source_hash.update(raw)
        source_hash.update(submissions_raw)
        loaded = 0
        for entry in older_files:
            missing_dates = [date for accession, date in needed.items() if accession not in ledger]
            if not missing_dates:
                break
            if not any(entry.get("filingFrom", "") <= date <= entry.get("filingTo", "9999") for date in missing_dates):
                continue
            if loaded >= 64:
                break  # Remaining acceptance gaps stay explicitly flagged.
            name = entry.get("name", "")
            if not name.startswith(f"CIK{cik}-submissions-") or not name.endswith(".json"):
                continue
            older, older_raw = self._json(f"https://data.sec.gov/submissions/{name}")
            source_hash.update(older_raw)
            ledger.update(self._ledger(older))
            loaded += 1
        forms = {str(row.get("form") or "").upper() for row in ledger.values()}
        if not forms.intersection({"10-K", "10-K/A", "10-Q", "10-Q/A"}):
            raise UnsupportedReportingBasis("This issuer lacks verified 10-K/10-Q reporting; foreign-private-issuer/IFRS coverage is not supported.")
        if not facts.get("facts", {}).get("us-gaap"):
            if facts.get("facts", {}).get("ifrs-full"):
                raise UnsupportedReportingBasis("IFRS Company Facts require a separately validated mapping module.")
            raise MissingStructuredData("No compatible structured U.S. GAAP facts are available for this issuer.")
        return SecFinancialPayload(
            identity=identity,
            facts=facts,
            accession_ledger=ledger,
            retrieved_at_utc=self._response_times[facts_url],
            source_sha256=source_hash.hexdigest(),
            older_file_count=len(older_files),
            older_files_loaded=loaded,
        )
