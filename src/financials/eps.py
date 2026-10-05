"""Reported EPS and split-basis-safe growth from same-filing comparatives."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd


EPS_CONCEPTS = ("eps_basic", "eps_diluted")


def _same_filing_pair(
    observations: pd.DataFrame, concept: str, fiscal_year: int, quarter: int,
    period_type: str,
) -> tuple[pd.Series, pd.Series] | None:
    eligible = observations.loc[
        observations["normalized_concept"].eq(concept)
        & observations["period_type"].eq(period_type)
        & observations["fiscal_quarter"].eq(quarter)
        & observations["fiscal_year"].isin([fiscal_year - 1, fiscal_year])
        & observations["quality_status"].ne("invalid")
        & observations["unit"].str.fullmatch(r"[A-Z]{3}/shares", na=False)
        & observations["accession"].notna()
        & observations["acceptance_timestamp_utc"].notna()
    ]
    candidates = []
    for accession, group in eligible.groupby("accession"):
        current = group.loc[group["fiscal_year"].eq(fiscal_year)]
        prior = group.loc[group["fiscal_year"].eq(fiscal_year - 1)]
        if current.empty or prior.empty or current.value.nunique() != 1 or prior.value.nunique() != 1:
            continue
        current_row, prior_row = current.iloc[-1], prior.iloc[-1]
        if (current_row["issuer_id"] != prior_row["issuer_id"]
            or current_row["provider_concept"] != prior_row["provider_concept"]
            or current_row["unit"] != prior_row["unit"]
            or current_row["currency"] != prior_row["currency"]
            or current_row["taxonomy"] != prior_row["taxonomy"]):
            continue
        days = (pd.Timestamp(current_row["period_end"]) - pd.Timestamp(prior_row["period_end"])).days
        if not 340 <= days <= 385:
            continue
        candidates.append((current_row["acceptance_timestamp_utc"], accession, current_row, prior_row))
    if not candidates:
        return None
    _, _, current_row, prior_row = max(candidates, key=lambda item: (item[0], item[1]))
    return current_row, prior_row


def add_eps_growth(
    frame: pd.DataFrame, observations: pd.DataFrame, *, frequency: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Only compare EPS observations disclosed together on a filing's share basis.

    Multiyear CAGR is chain-linked from complete adjacent same-filing YoY pairs.
    This avoids comparing raw absolute EPS across unverified split bases.
    """
    if frame.empty:
        return frame.copy(), pd.DataFrame()
    if frequency not in {"annual", "quarterly"}:
        raise ValueError("frequency must be annual or quarterly")
    output = frame.copy()
    for concept in EPS_CONCEPTS:
        output[f"{concept}_yoy_parent_observation_ids"] = pd.Series(
            [None] * len(output), index=output.index, dtype=object,
        )
    records: list[dict] = []
    for index, row in output.iterrows():
        year, quarter = int(row["fiscal_year"]), int(row["fiscal_quarter"])
        period_type = "annual" if frequency == "annual" else "quarter"
        for concept in EPS_CONCEPTS:
            pair = _same_filing_pair(observations, concept, year, quarter, period_type)
            status, growth, parents, accession = "UNVERIFIED_SHARE_BASIS", None, [], None
            if pair is not None:
                current, prior = pair
                parents = [current["observation_id"], prior["observation_id"]]
                accession = current["accession"]
                current_value, prior_value = Decimal(current["value"]), Decimal(prior["value"])
                if current_value > 0 and prior_value > 0:
                    growth, status = current_value / prior_value - 1, "VALID_SAME_FILING_COMPARATIVE"
                else:
                    status = "NONPOSITIVE_EPS_BASE"
            output.at[index, f"{concept}_yoy"] = growth
            output.at[index, f"{concept}_yoy_status"] = status
            output.at[index, f"{concept}_yoy_parent_observation_ids"] = parents
            output.at[index, f"{concept}_yoy_accession"] = accession
            records.append({
                "frequency": frequency, "fiscal_year": year, "fiscal_quarter": quarter,
                "period_end": row["period_end"], "metric": f"{concept}_yoy",
                "value": growth, "status": status, "currency": None, "unit": "ratio",
                "parent_observation_ids": parents, "source_accession": accession,
                "method": "same_filing_reported_eps_comparative",
            })
    if frequency == "annual":
        for index, row in output.iterrows():
            year = int(row["fiscal_year"])
            for concept in EPS_CONCEPTS:
                for years in (3, 5):
                    span = output.loc[output["fiscal_year"].between(year - years + 1, year)]
                    contiguous = set(span["fiscal_year"]) == set(range(year - years + 1, year + 1))
                    valid = contiguous and span[f"{concept}_yoy_status"].eq("VALID_SAME_FILING_COMPARATIVE").all()
                    if valid:
                        factor = Decimal(1)
                        parent_ids = []
                        for _, member in span.iterrows():
                            factor *= Decimal(1) + member[f"{concept}_yoy"]
                            parent_ids.extend(member[f"{concept}_yoy_parent_observation_ids"])
                        value = factor ** (Decimal(1) / Decimal(years)) - 1
                        status = "VALID_CHAINED_COMPARATIVES"
                    else:
                        value, status, parent_ids = None, "INSUFFICIENT_COMPARABLE_HISTORY", []
                    output.at[index, f"{concept}_cagr_{years}y"] = value
                    output.at[index, f"{concept}_cagr_{years}y_status"] = status
                    records.append({
                        "frequency": "annual", "fiscal_year": year, "fiscal_quarter": 4,
                        "period_end": row["period_end"], "metric": f"{concept}_cagr_{years}y",
                        "value": value, "status": status, "currency": None, "unit": "ratio",
                        "parent_observation_ids": parent_ids, "source_accession": None,
                        "method": "chain_linked_same_filing_eps_comparatives",
                    })
    return output, pd.DataFrame.from_records(records)
