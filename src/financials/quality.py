"""Coverage and anomaly summaries for the independent SEC statement layer."""

from __future__ import annotations

import pandas as pd
from decimal import Decimal

from .concepts import ConceptMapping


def financial_coverage(selected: pd.DataFrame, mappings: tuple[ConceptMapping, ...]) -> pd.DataFrame:
    records: list[dict] = []
    for concept in sorted({mapping.concept for mapping in mappings}):
        facts = selected.loc[selected["normalized_concept"].eq(concept)] if not selected.empty else pd.DataFrame()
        for period_type in ("annual", "quarter", "ytd", "instant"):
            subset = facts.loc[facts["period_type"].eq(period_type)] if not facts.empty else pd.DataFrame()
            records.append({
                "concept": concept, "period_type": period_type,
                "first_period": subset["period_end"].min() if not subset.empty else None,
                "last_period": subset["period_end"].max() if not subset.empty else None,
                "valid_periods": int(subset["period_end"].nunique()) if not subset.empty else 0,
                "acceptance_joined": int(subset["acceptance_timestamp_utc"].notna().sum()) if not subset.empty else 0,
                "source_tags": ", ".join(sorted(subset["provider_concept"].dropna().unique())) if not subset.empty else "",
                "status": "AVAILABLE" if not subset.empty else "MISSING_INPUT",
            })
    return pd.DataFrame(records)


def financial_quality(observations: pd.DataFrame, decisions: pd.DataFrame, quarter_issues: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for observation in observations.itertuples():
        if observation.quality_flags:
            rows.append({
                "check": ",".join(observation.quality_flags), "concept": observation.normalized_concept,
                "period_end": observation.period_end, "accession": observation.accession,
                "status": observation.quality_status,
            })
    if not decisions.empty:
        for decision in decisions.loc[decisions["reason"].eq("CONFLICTING_FACTS")].itertuples():
            rows.append({"check": "CONFLICTING_FACTS", "concept": None, "period_end": None,
                         "accession": None, "status": "invalid"})
    if not quarter_issues.empty:
        for issue in quarter_issues.itertuples():
            rows.append({"check": issue.status, "concept": issue.concept,
                         "period_end": f"FY{issue.fiscal_year} Q{issue.quarter}",
                         "accession": None, "status": "warning"})
    return pd.DataFrame(rows, columns=["check", "concept", "period_end", "accession", "status"])


def statement_reconciliation(frame: pd.DataFrame) -> pd.DataFrame:
    """Flag material mismatches without assuming missing components are zero.

    Assets versus liabilities plus stockholders' equity is an advisory check:
    non-controlling interests can legitimately prevent exact equality.
    """
    issues: list[dict] = []
    for row in frame.itertuples(index=False):
        values = row._asdict()
        end = values.get("period_end")
        assets, liabilities, equity = (
            values.get("assets"), values.get("liabilities"), values.get("shareholders_equity")
        )
        if all(value is not None and not pd.isna(value) for value in (assets, liabilities, equity)):
            a, l, e = (Decimal(str(value)) for value in (assets, liabilities, equity))
            difference = abs(a - l - e)
            if difference > max(Decimal("1000000"), abs(a) * Decimal("0.01")):
                issues.append({
                    "check": "BALANCE_IDENTITY_DIFFERENCE", "concept": "assets/liabilities/equity",
                    "period_end": end, "accession": None, "status": "warning",
                })
        if values.get("fcf_status") == "VALID":
            ocf, capex, fcf = (values.get(name) for name in ("ocf", "capex_ppe", "fcf"))
            if any(value is None or pd.isna(value) for value in (ocf, capex, fcf)) or Decimal(str(ocf)) - Decimal(str(capex)) != Decimal(str(fcf)):
                issues.append({
                    "check": "FCF_RECONCILIATION_FAILURE", "concept": "fcf",
                    "period_end": end, "accession": None, "status": "invalid",
                })
    return pd.DataFrame(issues, columns=["check", "concept", "period_end", "accession", "status"])
