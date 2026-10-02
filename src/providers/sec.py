"""Identified, rate-limited SEC Company Facts and submissions client."""

from __future__ import annotations

import hashlib
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
from .financial_base import FinancialDataProvider


class SecConfigurationError(RuntimeError):
    pass


class SecTransportError(RuntimeError):
    pass


class UnsupportedSecIdentity(LookupError):
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


_RATE_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


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
        self._session.headers.update({
            "User-Agent": agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        })

    def _json(self, url: str) -> tuple[dict[str, Any], bytes]:
        global _LAST_REQUEST
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
        del force_refresh  # cache invalidation belongs to the caller's explicit Analyze action
        ticker = metadata.ticker.upper().strip()
        if metadata.security_type and metadata.security_type.upper() in {"ETF", "FUND", "INDEX", "CURRENCY", "CRYPTOCURRENCY"}:
            raise UnsupportedSecIdentity("This security type has no conventional issuer statements.")
        directory, _ = self._json("https://www.sec.gov/files/company_tickers.json")
        candidates = [row for row in directory.values() if str(row.get("ticker", "")).upper() == ticker]
        if len(candidates) != 1:
            raise UnsupportedSecIdentity("No exact SEC ticker-to-issuer match was found.")
        cik = f"{int(candidates[0]['cik_str']):010d}"
        submissions, submissions_raw = self._json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        listed = [str(value).upper() for value in submissions.get("tickers", [])]
        if ticker not in listed:
            raise UnsupportedSecIdentity("SEC submissions do not confirm this listing ticker.")
        fiscal_year_end = str(submissions.get("fiscalYearEnd") or "")
        if len(fiscal_year_end) != 4 or not fiscal_year_end.isdigit():
            raise UnsupportedSecIdentity("SEC issuer fiscal year end is unavailable.")
        listing_index = listed.index(ticker)
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
        )
        facts, raw = self._json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        if str(facts.get("cik", "")).lstrip("0") != str(int(cik)):
            raise SecTransportError("SEC Company Facts issuer identity did not match the submissions issuer")
        filings = submissions.get("filings", {})
        ledger = self._ledger(filings.get("recent", {}))
        older_files = filings.get("files", [])
        if len(older_files) > 20:
            raise SecTransportError("SEC submissions history exceeds the supported complete-ledger limit")
        source_hash = hashlib.sha256()
        source_hash.update(raw)
        source_hash.update(submissions_raw)
        loaded = 0
        for entry in older_files:
            name = entry.get("name", "")
            if not name.startswith(f"CIK{cik}-submissions-") or not name.endswith(".json"):
                continue
            older, older_raw = self._json(f"https://data.sec.gov/submissions/{name}")
            source_hash.update(older_raw)
            ledger.update(self._ledger(older))
            loaded += 1
        return SecFinancialPayload(
            identity=identity,
            facts=facts,
            accession_ledger=ledger,
            retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
            source_sha256=source_hash.hexdigest(),
            older_file_count=len(older_files),
            older_files_loaded=loaded,
        )
