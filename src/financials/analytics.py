"""Release A statement views and conservative, status-bearing fundamentals."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd


FLOW_CONCEPTS = {
    "revenue", "gross_profit", "operating_income", "net_income_parent",
    "eps_basic", "eps_diluted", "ocf", "capex_ppe", "productive_asset_spending",
    "investing_cash_flow", "financing_cash_flow",
}


def _money(value) -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    return Decimal(str(value))


def build_period_table(selected: pd.DataFrame, derived: pd.DataFrame, *, frequency: str) -> pd.DataFrame:
    if selected.empty:
        return pd.DataFrame()
    eligible = pd.concat([selected, derived], ignore_index=True) if not derived.empty else selected
    if frequency == "annual":
        eligible = eligible.loc[
            eligible["period_type"].eq("annual")
            | (eligible["period_type"].eq("instant") & eligible["fiscal_quarter"].eq(4))
        ]
    elif frequency == "quarterly":
        eligible = eligible.loc[eligible["period_type"].isin(["quarter", "instant"])]
    else:
        raise ValueError("frequency must be annual or quarterly")
    records: list[dict] = []
    for (year, quarter), group in eligible.groupby(["fiscal_year", "fiscal_quarter"], dropna=True, sort=True):
        if frequency == "annual" and int(quarter) != 4:
            continue
        # An opening balance-sheet comparative is not a completed annual or
        # standalone quarterly income/cash-flow statement.
        required_type = "annual" if frequency == "annual" else "quarter"
        if not group["period_type"].eq(required_type).any():
            continue
        # A fiscal period must have one coherent end date. Do not combine shifted
        # contexts merely because their issuer FY/quarter labels happen to match.
        date_counts = group["period_end"].value_counts()
        period_end = date_counts.index[0]
        group = group.loc[group["period_end"].eq(period_end)]
        currencies = group["currency"].dropna().unique().tolist()
        if len(currencies) > 1:
            continue
        row: dict = {
            "fiscal_year": int(year), "fiscal_quarter": int(quarter),
            "period_end": period_end, "currency": currencies[0] if currencies else None,
            "frequency": frequency,
        }
        for concept, facts in group.groupby("normalized_concept"):
            if len(facts) != 1:
                continue
            observation = facts.iloc[0]
            row[concept] = _money(observation["value"])
            row[f"{concept}_observation_id"] = observation["observation_id"]
            row[f"{concept}_filing_date"] = observation["filing_date"]
            row[f"{concept}_acceptance_utc"] = observation["acceptance_timestamp_utc"]
            row[f"{concept}_source_tag"] = observation["provider_concept"]
            row[f"{concept}_quality_flags"] = observation["quality_flags"]
            row[f"{concept}_revision_status"] = observation["revision_status"]
            if concept.startswith("eps_"):
                row[f"{concept}_share_basis_status"] = observation["share_basis_status"]
        records.append(row)
    return pd.DataFrame(records).sort_values(["fiscal_year", "fiscal_quarter"]).reset_index(drop=True) if records else pd.DataFrame()


def _ratio(value: Decimal | None, denominator: Decimal | None) -> tuple[Decimal | None, str]:
    if value is None or denominator is None:
        return None, "MISSING_INPUT"
    if denominator <= 0:
        return None, "NONPOSITIVE_DENOMINATOR"
    return value / denominator, "VALID"


def calculate_fundamentals(frame: pd.DataFrame, *, financial_sector: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        return frame.copy(), pd.DataFrame()
    output = frame.copy()
    ratios: list[dict] = []
    for index, row in output.iterrows():
        year = int(row["fiscal_year"])
        quarter = int(row["fiscal_quarter"])
        end = row["period_end"]
        revenue = _money(row.get("revenue"))
        ocf = _money(row.get("ocf"))
        capex = _money(row.get("capex_ppe"))
        capex_flags = row.get("capex_ppe_quality_flags")
        anomalous_capex = isinstance(capex_flags, list) and "CAPEX_SIGN_ANOMALY" in capex_flags
        if financial_sector:
            fcf, fcf_status = None, "NOT_APPLICABLE"
        elif ocf is None or capex is None:
            fcf, fcf_status = None, "MISSING_INPUT"
        elif capex < 0 or anomalous_capex:
            fcf, fcf_status = None, "CAPEX_SIGN_ANOMALY"
        else:
            fcf, fcf_status = ocf - capex, "VALID"
        output.at[index, "fcf"] = fcf
        output.at[index, "fcf_status"] = fcf_status
        for name, numerator, denominator in (
            ("operating_margin", _money(row.get("operating_income")), revenue),
            ("net_margin", _money(row.get("net_income_parent")), revenue),
            ("fcf_margin", fcf, revenue),
            ("ocf_to_income", ocf, _money(row.get("net_income_parent"))),
        ):
            value, status = _ratio(numerator, denominator)
            if financial_sector and name in {"fcf_margin", "ocf_to_income"}:
                value, status = None, "NOT_APPLICABLE"
            output.at[index, name] = value
            ratios.append({
                "frequency": row["frequency"], "fiscal_year": year,
                "fiscal_quarter": quarter, "period_end": end,
                "metric": name, "value": value, "status": status,
                "currency": None, "unit": "ratio",
            })
        debt = _money(row.get("reported_long_term_debt"))
        cash = _money(row.get("cash_equivalents"))
        output.at[index, "total_debt"] = None
        output.at[index, "net_debt"] = None
        output.at[index, "debt_status"] = "PARTIAL_DEBT" if debt is not None else "MISSING_INPUT"
        output.at[index, "net_debt_status"] = "PARTIAL_DEBT" if debt is not None and cash is not None else "MISSING_INPUT"
        ratios.append({
            "frequency": row["frequency"], "fiscal_year": year,
            "fiscal_quarter": quarter, "period_end": end,
            "metric": "fcf", "value": fcf, "status": fcf_status,
            "currency": row["currency"], "unit": row["currency"],
        })
    for index, row in output.iterrows():
        prior = output.loc[
            output["fiscal_year"].eq(int(row["fiscal_year"]) - 1)
            & output["fiscal_quarter"].eq(row["fiscal_quarter"])
        ]
        for concept in ("revenue", "operating_income", "net_income_parent", "ocf", "fcf"):
            current = _money(row.get(concept))
            previous = _money(prior.iloc[-1].get(concept)) if len(prior) else None
            if current is not None and previous is not None and current > 0 and previous > 0:
                value, status = current / previous - 1, "VALID"
            else:
                value, status = None, "MISSING_INPUT" if current is None or previous is None else "NONPOSITIVE_GROWTH_BASE"
            output.at[index, f"{concept}_yoy"] = value
            ratios.append({
                "frequency": row["frequency"], "fiscal_year": int(row["fiscal_year"]),
                "fiscal_quarter": int(row["fiscal_quarter"]), "period_end": row["period_end"],
                "metric": f"{concept}_yoy", "value": value, "status": status,
                "currency": None, "unit": "ratio",
            })
        if row["frequency"] == "annual":
            for years in (3, 5):
                span = output.loc[
                    output["fiscal_year"].between(int(row["fiscal_year"]) - years, int(row["fiscal_year"]))
                    & output["fiscal_quarter"].eq(4)
                ]
                for concept in ("revenue", "operating_income", "net_income_parent", "ocf", "fcf"):
                    complete = set(span["fiscal_year"]) == set(range(int(row["fiscal_year"]) - years, int(row["fiscal_year"]) + 1))
                    first = _money(span.iloc[0].get(concept)) if complete else None
                    last = _money(span.iloc[-1].get(concept)) if complete else None
                    value = (last / first) ** (Decimal(1) / Decimal(years)) - 1 if first is not None and last is not None and first > 0 and last > 0 else None
                    status = "VALID" if value is not None else "MISSING_OR_NONPOSITIVE_SPAN"
                    output.at[index, f"{concept}_cagr_{years}y"] = value
                    ratios.append({
                        "frequency": "annual", "fiscal_year": int(row["fiscal_year"]),
                        "fiscal_quarter": 4, "period_end": row["period_end"],
                        "metric": f"{concept}_cagr_{years}y", "value": value,
                        "status": status, "currency": None, "unit": "ratio",
                    })
    return output, pd.DataFrame(ratios)
