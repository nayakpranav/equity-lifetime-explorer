"""Strict IFRS xBRL-JSON extraction without taxonomy downloads or inference.

The supported subset is entity-wide, midnight-bounded monetary facts. Extension
concepts, dimensional segments and ambiguous currency/context data are withheld.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd

from ..providers.esef import EsefDocument
from .ifrs_concepts import IFRS_MAPPING_VERSION, ifrs_mappings
from .normalization import validate_observation
from .periods import classify_period


def _midnight(value: str) -> datetime:
    # Do not silently truncate an intraday/timezone-specific financial context.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00", value):
        raise ValueError("Only unambiguous midnight XBRL periods are supported")
    return datetime.fromisoformat(value)


def oim_period(value: str) -> tuple[str | None, str]:
    if not isinstance(value, str):
        raise ValueError("Missing XBRL period")
    parts = value.split("/")
    if len(parts) == 1:
        return None, (_midnight(parts[0]) - timedelta(days=1)).date().isoformat()
    if len(parts) != 2:
        raise ValueError("Invalid XBRL period")
    start, exclusive_end = map(_midnight, parts)
    if exclusive_end <= start:
        raise ValueError("Nonpositive XBRL duration")
    return start.date().isoformat(), (exclusive_end - timedelta(days=1)).date().isoformat()


def normalize_esef_document(
    document: EsefDocument, *, ticker: str, currency: str, fiscal_year_end: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    info = document.report.get("documentInfo", {})
    if info.get("documentType") != "https://xbrl.org/2021/xbrl-json":
        raise ValueError("Unsupported structured report format")
    namespaces = info.get("namespaces", {})
    registry = {item.tag: item for item in ifrs_mappings(currency)}
    records, diagnostics = [], []
    for locator, fact in document.report.get("facts", {}).items():
        dims = fact.get("dimensions", {})
        concept = dims.get("concept", "")
        prefix, separator, tag = concept.partition(":")
        namespace = namespaces.get(prefix, "")
        if not separator or not re.fullmatch(r"https?://xbrl\.ifrs\.org/taxonomy/\d{4}-\d{2}-\d{2}/ifrs-full", namespace) or tag not in registry:
            continue
        mapping = registry[tag]
        reason = None
        entity_prefix, _, entity = dims.get("entity", "").partition(":")
        if namespaces.get(entity_prefix) != "http://standards.iso.org/iso/17442" or entity != document.lei:
            reason = "ISSUER_IDENTITY_MISMATCH"
        elif set(dims) - {"concept", "entity", "period", "unit"}:
            reason = "UNVERIFIED_DIMENSIONAL_CONTEXT"
        unit = dims.get("unit", "")
        numerator, slash, denominator = unit.partition("/")
        money_prefix, _, money_code = numerator.partition(":")
        if namespaces.get(money_prefix) != "http://www.xbrl.org/2003/iso4217" or money_code != currency:
            reason = reason or "INCOMPATIBLE_UNIT_OR_CURRENCY"
        if mapping.concept.startswith("eps_"):
            share_prefix, colon, share_name = denominator.partition(":")
            if not slash or not colon or share_name != "shares" or namespaces.get(share_prefix) != "http://www.xbrl.org/2003/instance":
                reason = reason or "UNVERIFIED_SHARE_UNIT"
        elif slash:
            reason = reason or "INCOMPATIBLE_UNIT_OR_CURRENCY"
        try:
            start, end = oim_period(dims.get("period", ""))
            if (start is None) != (mapping.context == "instant"):
                raise ValueError("Context period does not match concept")
            value = Decimal(str(fact.get("value")))
            if not value.is_finite():
                raise ValueError("Non-finite value")
        except (ValueError, TypeError, InvalidOperation):
            reason = reason or "INVALID_VALUE_OR_PERIOD"
        if reason:
            diagnostics.append({"source_record_locator": locator, "concept": mapping.concept,
                                "status": "withheld", "reason": reason})
            continue
        period = classify_period(start, end, fiscal_year_end, "20-F")
        flags = ["DISCLOSURE_TIMESTAMP_UNVERIFIED", "AUDIT_STATUS_UNVERIFIED", "CONSOLIDATION_BASIS_UNVERIFIED"]
        if period.period_type == "unknown":
            flags.append("UNKNOWN_FISCAL_PERIOD")
        if mapping.sign == "positive_outflow" and value < 0:
            flags.append("CAPEX_SIGN_ANOMALY")
        identifier = hashlib.sha256(f"{document.source_sha256}:{locator}".encode()).hexdigest()[:24]
        record = {
            "schema_version": "1.0.0", "observation_id": "esef:" + identifier,
            "issuer_id": "LEI:" + document.lei, "security_id": None, "ticker": ticker,
            "accounting_framework": "IFRS", "consolidation_basis": "unknown",
            "audit_status": "unknown", "source_type": "PRIMARY_REGULATORY",
            "source_version": namespace,
            "provider": "FILINGS_XBRL_ORG", "taxonomy": "ifrs-full",
            "provider_concept": tag, "normalized_concept": mapping.concept,
            "statement_type": mapping.statement, "mapping_version": IFRS_MAPPING_VERSION,
            "mapping_priority": mapping.priority, "mapping_basis": mapping.basis,
            "mapping_scope": "exact_standard_ifrs_not_issuer_audited",
            "context_type": mapping.context, "context_id": locator,
            "dimensions_status": "verified_entity_wide", "dimensions": None,
            "period_start": start, "period_end": end, "fiscal_year": period.fiscal_year,
            "fiscal_quarter": period.fiscal_quarter, "raw_fiscal_year": None,
            "raw_fiscal_period": None, "period_type": period.period_type,
            "reporting_frequency": period.reporting_frequency, "filing_date": None,
            "acceptance_timestamp_utc": None, "public_availability_timestamp_utc": None,
            "availability_session": None, "availability_precision": "unknown",
            "availability_policy": "repository_ingestion_is_not_disclosure",
            "currency": currency, "unit": mapping.unit, "value": format(value, "f"),
            "original_value": format(value, "f"), "scale": 0,
            "reported_decimals": str(fact["decimals"]) if "decimals" in fact else None,
            "sign_convention": mapping.sign, "accession": None, "form": "ESEF",
            "source_url": document.source_url, "source_record_locator": "/facts/" + locator,
            "source_sha256": document.source_sha256, "retrieved_at_utc": document.retrieved_at_utc,
            "filing_status": "unknown", "revision_status": "unknown", "vintage_role": "reported",
            "share_class": None, "share_basis_date": None,
            "share_basis_status": "unknown" if mapping.concept.startswith("eps_") else "not_applicable",
            "share_basis_evidence": None, "quality_status": "warning", "quality_flags": flags,
            "derivation": None, "parent_observation_ids": [],
            "methodology_version": "global-fundamentals-2026-10-05",
        }
        validate_observation(record)
        records.append(record)
    observations = pd.DataFrame(records)
    if not observations.empty:
        observations["period_start"] = observations["period_start"].astype(object).where(observations["period_start"].notna(), None)
        keys = ["normalized_concept", "period_start", "period_end", "unit"]
        for _, group in observations.groupby(keys, dropna=False):
            if group["value"].map(Decimal).nunique() > 1:
                for index in group.index:
                    observations.at[index, "quality_status"] = "invalid"
                    observations.at[index, "quality_flags"] = [*observations.at[index, "quality_flags"], "CONFLICTING_FACTS"]
            elif len(group) > 1:
                # Equal duplicates retain lineage but exactly one enters analysis.
                for index in group.index[1:]:
                    observations.at[index, "quality_status"] = "invalid"
                    observations.at[index, "quality_flags"] = [*observations.at[index, "quality_flags"], "DUPLICATE_EQUAL_FACT"]
    return observations, pd.DataFrame(diagnostics)
