"""Lossless SEC fact extraction with fiscal, accession and revision lineage."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from typing import Any

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

from ..providers.sec import SecFinancialPayload
from . import MAPPING_VERSION, METHODOLOGY_VERSION
from .concepts import ConceptMapping, mappings_for
from .periods import classify_period


def _decimal_text(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return format(number, "f") if number.is_finite() else None


def _record(payload: SecFinancialPayload, mapping: ConceptMapping, unit: str, row: dict, position: int) -> dict:
    identity = payload.identity
    accession = row.get("accn")
    ledger = payload.accession_ledger.get(accession, {})
    filing_date = row.get("filed") or ledger.get("filing_date")
    accepted = ledger.get("acceptance")
    if accepted:
        try:
            accepted = datetime.fromisoformat(accepted.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except ValueError:
            accepted = None
    start = row.get("start")
    end = row["end"]
    form = row.get("form") or ledger.get("form")
    period = classify_period(start, end, identity.fiscal_year_end, form)
    value = _decimal_text(row.get("val"))
    flags: list[str] = []
    if period.period_type == "unknown":
        flags.append("UNKNOWN_FISCAL_PERIOD")
    if not accepted:
        flags.append("MISSING_ACCEPTANCE_TIMESTAMP")
    if ledger and ledger.get("filing_date") != row.get("filed"):
        flags.append("FILING_DATE_MISMATCH")
    if mapping.sign == "positive_outflow" and value is not None and Decimal(value) < 0:
        flags.append("CAPEX_SIGN_ANOMALY")
    quality = "invalid" if value is None else "warning" if flags else "valid"
    locator = f"/facts/us-gaap/{mapping.tag}/units/{unit}/{position}"
    identity_key = json.dumps(
        [identity.cik, mapping.tag, unit, position, row], sort_keys=True, separators=(",", ":")
    )
    observation_id = "sec:" + hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:24]
    source_url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(identity.cik)}/{accession.replace('-', '')}/"
        if accession else f"https://data.sec.gov/api/xbrl/companyfacts/CIK{identity.cik}.json"
    )
    return {
        "schema_version": "1.0.0", "observation_id": observation_id,
        "issuer_id": identity.issuer_id, "security_id": None, "ticker": identity.ticker,
        "provider": "SEC_EDGAR", "taxonomy": "us-gaap", "provider_concept": mapping.tag,
        "normalized_concept": mapping.concept, "statement_type": mapping.statement,
        "mapping_version": MAPPING_VERSION, "context_type": mapping.context,
        "context_id": None, "dimensions_status": "omitted_by_provider", "dimensions": None,
        "period_start": start, "period_end": end, "fiscal_year": period.fiscal_year,
        "fiscal_quarter": period.fiscal_quarter, "raw_fiscal_year": row.get("fy"),
        "raw_fiscal_period": row.get("fp"), "period_type": period.period_type,
        "reporting_frequency": period.reporting_frequency,
        "filing_date": filing_date, "acceptance_timestamp_utc": accepted,
        "public_availability_timestamp_utc": None, "availability_session": None,
        "availability_precision": "timestamp" if accepted else "date" if filing_date else "unknown",
        "availability_policy": "not_computed_release_a",
        "currency": identity.reporting_currency if unit.startswith(identity.reporting_currency) else None,
        "unit": unit, "value": value, "original_value": value,
        "scale": 0, "reported_decimals": None, "sign_convention": mapping.sign,
        "accession": accession, "form": form, "source_url": source_url,
        "source_record_locator": locator, "source_sha256": payload.source_sha256,
        "retrieved_at_utc": payload.retrieved_at_utc,
        "filing_status": "amended" if form and form.endswith("/A") else "original" if form else "unknown",
        "revision_status": "unknown", "vintage_role": "reported",
        "share_class": None, "share_basis_date": None,
        "share_basis_status": "unknown" if mapping.concept.startswith("eps_") else "not_applicable",
        "share_basis_evidence": None,
        "quality_status": quality, "quality_flags": flags,
        "derivation": None, "parent_observation_ids": [],
        "methodology_version": METHODOLOGY_VERSION,
    }


def normalize_sec_facts(payload: SecFinancialPayload) -> pd.DataFrame:
    mappings = mappings_for(payload.identity.ticker, payload.identity.cik)
    if not mappings:
        return pd.DataFrame()
    gaap = payload.facts.get("facts", {}).get("us-gaap", {})
    records: list[dict] = []
    for mapping in mappings:
        concept = gaap.get(mapping.tag, {})
        rows = concept.get("units", {}).get(mapping.unit, [])
        for position, row in enumerate(rows):
            if row.get("form") not in {"10-K", "10-Q", "10-K/A", "10-Q/A"}:
                continue
            end = row.get("end")
            if not end or (mapping.first_end and end < mapping.first_end) or (mapping.last_end and end > mapping.last_end):
                continue
            records.append(_record(payload, mapping, mapping.unit, row, position))
    by_period: dict[tuple, list[dict]] = defaultdict(list)
    for record in records:
        key = (
            record["normalized_concept"], record["provider_concept"],
            record["period_start"], record["period_end"], record["unit"],
        )
        by_period[key].append(record)
    for group in by_period.values():
        group.sort(key=lambda record: (record["filing_date"] or "", record["acceptance_timestamp_utc"] or ""))
        prior_value: str | None = None
        by_accession: dict[str | None, set[str | None]] = defaultdict(set)
        for record in group:
            by_accession[record["accession"]].add(record["value"])
        for index, record in enumerate(group):
            if len(by_accession[record["accession"]]) > 1:
                record["quality_status"] = "invalid"
                record["quality_flags"] = sorted(set([*record["quality_flags"], "CONFLICTING_FACTS"]))
            if index == 0:
                record["revision_status"] = "unknown"
            elif record["value"] == prior_value:
                record["revision_status"] = "unchanged_repeat"
            else:
                record["revision_status"] = "revision_candidate"
            prior_value = record["value"]
    return pd.DataFrame.from_records(records)


_SCHEMA = json.loads(files("src.financials").joinpath("financial_observation.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = Draft202012Validator(_SCHEMA, format_checker=FormatChecker())


def validate_observation(record: dict) -> None:
    """Check the proposed structural contract plus cross-field monetary rules."""
    _VALIDATOR.validate(record)
    if record["context_type"] == "duration" and record["period_start"] > record["period_end"]:
        raise ValueError("Duration start exceeds period end")
    if record["unit"] == "USD/shares" and record["normalized_concept"] not in {"eps_basic", "eps_diluted"}:
        raise ValueError("Per-share unit on non-EPS concept")
    if record["unit"] == "USD" and record["currency"] != "USD":
        raise ValueError("Money unit/currency mismatch")
    if record["value"] is not None and not Decimal(record["value"]).is_finite():
        raise ValueError("Non-finite financial value")
