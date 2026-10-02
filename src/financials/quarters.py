"""Standalone quarterly monetary flows from compatible reported cumulative facts."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal

import pandas as pd

from . import METHODOLOGY_VERSION


ADDITIVE_FLOWS = {
    "revenue", "gross_profit", "operating_income", "net_income_parent",
    "ocf", "capex_ppe", "productive_asset_spending",
    "investing_cash_flow", "financing_cash_flow",
}


def _incompatibility_reason(later: pd.Series, earlier: pd.Series) -> str | None:
    if later["normalized_concept"] not in ADDITIVE_FLOWS:
        return "NONADDITIVE_CONCEPT"
    # A revised cumulative parent may be from a later accounting vintage than
    # the other parent. Without matching restatement evidence, subtraction is
    # not a defensible standalone quarter.
    if later.get("revision_status") == "revision_candidate" or earlier.get("revision_status") == "revision_candidate":
        return "REVISED_PARENT_REVIEW"
    keys = ("issuer_id", "normalized_concept", "provider_concept", "unit", "currency", "fiscal_year", "period_start")
    different = [key for key in keys if later[key] != earlier[key]]
    if different:
        return "INCOMPATIBLE_" + "_".join(different).upper()
    if not later["acceptance_timestamp_utc"] or not earlier["acceptance_timestamp_utc"]:
        return "MISSING_ACCEPTANCE_TIMESTAMP"
    if later["acceptance_timestamp_utc"] < earlier["acceptance_timestamp_utc"]:
        return "MIXED_DISCLOSURE_VINTAGES"
    earlier_end = pd.Timestamp(earlier["period_end"])
    later_end = pd.Timestamp(later["period_end"])
    days = (later_end - earlier_end).days
    if not 75 <= days <= 110:
        return "NONADJACENT_PERIODS"
    return None


def _new_quarter(later: pd.Series, earlier: pd.Series, quarter: int) -> dict | None:
    if _incompatibility_reason(later, earlier) is not None:
        return None
    earlier_end = pd.Timestamp(earlier["period_end"])
    value = Decimal(later["value"]) - Decimal(earlier["value"])
    parent_ids = [earlier["observation_id"], later["observation_id"]]
    record = later.to_dict()
    record.update({
        "observation_id": "derived:" + hashlib.sha256("|".join(parent_ids).encode()).hexdigest()[:24],
        "provider": "DERIVED", "taxonomy": None, "provider_concept": None,
        "period_start": (earlier_end + timedelta(days=1)).date().isoformat(),
        "period_type": "quarter", "reporting_frequency": "quarterly", "fiscal_quarter": quarter,
        "value": format(value, "f"), "original_value": None,
        "acceptance_timestamp_utc": later["acceptance_timestamp_utc"],
        "filing_date": later["filing_date"], "availability_precision": "timestamp",
        "accession": None, "form": None, "source_url": None, "source_record_locator": None,
        "source_sha256": None, "filing_status": "not_applicable",
        "revision_status": "not_applicable", "vintage_role": "derived",
        "sign_convention": "derived", "parent_observation_ids": parent_ids,
        "derivation": {
            "method": "compatible_cumulative_subtraction_v1",
            "expression": "later cumulative monetary flow - earlier cumulative monetary flow",
            "available_from_rule": "maximum parent acceptance timestamp",
        },
        "quality_status": "valid", "quality_flags": [],
        "methodology_version": METHODOLOGY_VERSION,
    })
    return record


def derive_standalone_quarters(selected: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if selected.empty:
        return pd.DataFrame(), pd.DataFrame(columns=["concept", "fiscal_year", "quarter", "status"])
    derived: list[dict] = []
    diagnostics: list[dict] = []
    for (concept, fiscal_year), group in selected.groupby(["normalized_concept", "fiscal_year"], dropna=True):
        if concept not in ADDITIVE_FLOWS:
            continue
        by_type_quarter = {
            (row["period_type"], row["fiscal_quarter"]): row
            for _, row in group.iterrows()
        }
        for quarter in (2, 3, 4):
            direct = by_type_quarter.get(("quarter", quarter))
            later = by_type_quarter.get(("annual" if quarter == 4 else "ytd", quarter))
            earlier = by_type_quarter.get(("quarter" if quarter == 2 else "ytd", quarter - 1))
            if later is None or earlier is None:
                if direct is None:
                    diagnostics.append({
                        "concept": concept, "fiscal_year": int(fiscal_year), "quarter": quarter,
                        "status": "MISSING_PARENT_PERIOD",
                        "reason": "MISSING_LATER" if later is None else "MISSING_EARLIER",
                        "parent_observation_ids": [item["observation_id"] for item in (earlier, later) if item is not None],
                    })
                continue
            incompatibility = _incompatibility_reason(later, earlier)
            if incompatibility is not None:
                diagnostics.append({
                    "concept": concept, "fiscal_year": int(fiscal_year), "quarter": quarter,
                    "status": "INCOMPATIBLE_VINTAGES", "reason": incompatibility,
                    "parent_observation_ids": [earlier["observation_id"], later["observation_id"]],
                })
                continue
            candidate = _new_quarter(later, earlier, quarter)
            if direct is None:
                derived.append(candidate)
            elif Decimal(direct["value"]) != Decimal(candidate["value"]):
                difference = abs(Decimal(direct["value"]) - Decimal(candidate["value"]))
                scale = max(abs(Decimal(direct["value"])), abs(Decimal(candidate["value"])), Decimal(1))
                diagnostics.append({
                    "concept": concept, "fiscal_year": int(fiscal_year), "quarter": quarter,
                    "status": "DIRECT_DERIVED_DIFFERENCE",
                    "reason": "UNRESOLVED_REPORTED_VS_COMPATIBLE_CUMULATIVE",
                    "direct_value": direct["value"], "derived_value": candidate["value"],
                    "absolute_difference": format(difference, "f"),
                    "relative_difference": format(difference / scale, "f"),
                    "classification": (
                        "SMALL_REPORTED_DIFFERENCE_UNRESOLVED" if difference / scale <= Decimal("0.001")
                        else "MATERIAL_REPORTED_DIFFERENCE_UNRESOLVED"
                    ),
                    "direct_observation_id": direct["observation_id"],
                    "direct_accession": direct["accession"],
                    "parent_accessions": [earlier["accession"], later["accession"]],
                    "parent_observation_ids": candidate["parent_observation_ids"],
                })
    return pd.DataFrame.from_records(derived), pd.DataFrame.from_records(diagnostics)
