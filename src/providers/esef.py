"""Bounded, cached access to the documented public filings.xbrl.org API.

An exact, independently verified listing-to-LEI link is required by the caller.
Repository ingestion timestamps are NOT financial-disclosure timestamps.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import requests


ROOT = "https://filings.xbrl.org"
MAX_BYTES = 30 * 1024 * 1024
_CACHE: dict[str, tuple[float, dict, str]] = {}
_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


class EsefSourceError(RuntimeError):
    """Provider access or a nonconforming source response."""


@dataclass(frozen=True)
class EsefDocument:
    lei: str
    filing: dict
    report: dict
    source_url: str
    source_sha256: str
    retrieved_at_utc: str


def repository_url(value: str) -> str:
    url = urljoin(ROOT + "/", value)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "filings.xbrl.org" or parsed.username or parsed.fragment:
        raise EsefSourceError("Repository response contained an unapproved source URL")
    return url


class EsefFinancialProvider:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def _json(self, url: str, *, force_refresh: bool = False) -> tuple[dict, str]:
        global _LAST_REQUEST
        url = repository_url(url)
        with _LOCK:
            cached = _CACHE.get(url)
            if not force_refresh and cached and time.monotonic() - cached[0] < 43200:
                return copy.deepcopy(cached[1]), cached[2]
            time.sleep(max(0, 0.5 - (time.monotonic() - _LAST_REQUEST)))
            _LAST_REQUEST = time.monotonic()
            try:
                response = self.session.get(url, timeout=(8, 35), stream=True, allow_redirects=False)
                try:
                    if response.status_code != 200:
                        raise EsefSourceError(f"ESEF repository HTTP {response.status_code}")
                    content = bytearray()
                    for chunk in response.iter_content(65536):
                        content.extend(chunk)
                        if len(content) > MAX_BYTES:
                            raise EsefSourceError("ESEF document exceeds the configured size limit")
                    document = json.loads(content)
                    if not isinstance(document, dict):
                        raise EsefSourceError("ESEF response is not an object")
                finally:
                    response.close()
            except (requests.RequestException, ValueError) as exc:
                raise EsefSourceError("ESEF repository document could not be retrieved") from exc
            digest = hashlib.sha256(content).hexdigest()
            if len(_CACHE) >= 64:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[url] = (time.monotonic(), document, digest)
            return copy.deepcopy(document), digest

    def filings(self, lei: str, *, force_refresh: bool = False) -> list[dict]:
        if not re.fullmatch(r"[A-Z0-9]{20}", lei):
            raise ValueError("An exact 20-character LEI is required")
        url = f"{ROOT}/api/entities/{lei}/filings"
        self._verify_entity(lei, force_refresh=force_refresh)
        result: list[dict] = []
        visited: set[str] = set()
        for _ in range(10):
            if url in visited:
                raise EsefSourceError("ESEF pagination cycle detected")
            visited.add(url)
            page, _ = self._json(url, force_refresh=force_refresh)
            rows = page.get("data")
            if not isinstance(rows, list):
                raise EsefSourceError("ESEF filing list is malformed")
            for row in rows:
                self._verify_relationship(lei, row)
                result.append(row)
            next_url = page.get("links", {}).get("next")
            if not next_url:
                return sorted(result, key=lambda row: (
                    row.get("attributes", {}).get("period_end", ""),
                    row.get("attributes", {}).get("date_added", ""),
                ))
            url = repository_url(next_url)
        raise EsefSourceError("ESEF filing pagination exceeds the configured limit")

    def _verify_entity(self, lei: str, *, force_refresh: bool = False) -> None:
        entity, _ = self._json(f"{ROOT}/api/entities/{lei}", force_refresh=force_refresh)
        row = entity.get("data", {})
        if row.get("type") != "entity" or row.get("attributes", {}).get("identifier") != lei:
            raise EsefSourceError("Repository entity does not match the verified LEI")

    @staticmethod
    def _verify_relationship(lei: str, filing: dict) -> None:
        # JSON:API uses an internal numeric entity ID; the documented related
        # resource URL carries the LEI. Never equate the numeric ID with a LEI.
        related = filing.get("relationships", {}).get("entity", {}).get("links", {}).get("related")
        if not isinstance(related, str) or repository_url(related) != f"{ROOT}/api/entities/{lei}":
            raise EsefSourceError("ESEF filing issuer differs from the requested LEI")

    def fetch_document(self, lei: str, filing: dict, *, force_refresh: bool = False) -> EsefDocument:
        if not re.fullmatch(r"[A-Z0-9]{20}", lei):
            raise ValueError("An exact 20-character LEI is required")
        self._verify_entity(lei, force_refresh=force_refresh)
        self._verify_relationship(lei, filing)
        attributes = filing.get("attributes", {})
        if attributes.get("error_count") is None or attributes["error_count"] != 0:
            raise EsefSourceError("ESEF report has unresolved validation errors")
        if attributes.get("inconsistency_count") is None or attributes["inconsistency_count"] != 0:
            raise EsefSourceError("ESEF report has inconsistent duplicate facts")
        value = attributes.get("json_url")
        if not isinstance(value, str) or not value:
            raise EsefSourceError("ESEF filing has no structured JSON report")
        url = repository_url(value)
        report, digest = self._json(url, force_refresh=force_refresh)
        return EsefDocument(lei, copy.deepcopy(filing), report, url, digest,
                            datetime.now(timezone.utc).isoformat())
