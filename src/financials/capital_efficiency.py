"""Conservative annual parent ROE and operating-income-basis ROCE."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd


def _number(value) -> Decimal | None:
    return None if value is None or pd.isna(value) else Decimal(str(value))


def _compatible_years(current: pd.Series, prior: pd.Series | None) -> bool:
    if prior is None:
        return False
    if int(current["fiscal_year"]) != int(prior["fiscal_year"]) + 1:
        return False
    if current.get("currency") != prior.get("currency") or not current.get("currency"):
        return False
    days = (pd.Timestamp(current["period_end"]) - pd.Timestamp(prior["period_end"])).days
    return 340 <= days <= 385


def _status_for_inputs(current: pd.Series, prior: pd.Series, names: tuple[str, ...]) -> str | None:
    if current.get("currency") != prior.get("currency"):
        return "INCOMPATIBLE_CURRENCY"
    if not _compatible_years(current, prior):
        return "INCOMPATIBLE_PERIODS"
    if any(current.get(f"{name}_revision_status") == "revision_candidate" for name in names):
        return "REVISED_INPUT_REVIEW"
    if any(prior.get(f"{name}_revision_status") == "revision_candidate" for name in names if name != "net_income_parent" and name != "operating_income"):
        return "REVISED_INPUT_REVIEW"
    return None


def calculate_capital_efficiency(
    annual: pd.DataFrame, *, financial_sector: bool = False, accounting_framework: str = "US_GAAP",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use adjacent completed annual periods; never infer opening balances.

    ROE is parent-attributable net income / average parent-attributable equity.
    ROCE uses operating income as an EBIT proxy / average (assets-current
    liabilities). It is a labelled approximation, not a universal definition.
    """
    if annual.empty:
        return annual.copy(), pd.DataFrame()
    if accounting_framework not in {"US_GAAP", "IFRS"}:
        raise ValueError("Capital efficiency requires a verified accounting framework")
    income_tag, equity_tag, operating_tag, liabilities_tag = (
        ("NetIncomeLoss", "StockholdersEquity", "OperatingIncomeLoss", "LiabilitiesCurrent")
        if accounting_framework == "US_GAAP" else
        ("ProfitLossAttributableToOwnersOfParent", "EquityAttributableToOwnersOfParent",
         "ProfitLossFromOperatingActivities", "CurrentLiabilities")
    )
    output = annual.copy()
    for metric in ("roe", "roce"):
        output[f"{metric}_parent_observation_ids"] = pd.Series(
            [None] * len(output), index=output.index, dtype=object,
        )
    records: list[dict] = []
    for index, current in output.iterrows():
        earlier = output.loc[output["fiscal_year"].eq(int(current["fiscal_year"]) - 1)]
        prior = earlier.iloc[-1] if len(earlier) else None
        for metric, names in (
            ("roe", ("net_income_parent", "shareholders_equity")),
            ("roce", ("operating_income", "assets", "current_liabilities")),
        ):
            value: Decimal | None = None
            status = "MISSING_BEGINNING_PERIOD" if prior is None else "MISSING_INPUT"
            if metric == "roce" and financial_sector:
                status = "NOT_APPLICABLE_SECTOR"
            elif prior is not None:
                guard = _status_for_inputs(current, prior, names)
                if guard:
                    status = guard
                elif metric == "roe":
                    income = _number(current.get("net_income_parent"))
                    start = _number(prior.get("shareholders_equity"))
                    end = _number(current.get("shareholders_equity"))
                    if all(item is not None for item in (income, start, end)):
                        if current.get("net_income_parent_source_tag") != income_tag or any(
                            item.get("shareholders_equity_source_tag") != equity_tag
                            for item in (current, prior)
                        ):
                            status = "UNVERIFIED_ATTRIBUTION"
                        elif start <= 0 or end <= 0:
                            status = "NONPOSITIVE_EQUITY"
                        else:
                            value, status = income / ((start + end) / 2), "VALID"
                else:
                    operating_income = _number(current.get("operating_income"))
                    current_assets = _number(current.get("assets"))
                    prior_assets = _number(prior.get("assets"))
                    current_liabilities = _number(current.get("current_liabilities"))
                    prior_liabilities = _number(prior.get("current_liabilities"))
                    if all(item is not None for item in (
                        operating_income, current_assets, prior_assets,
                        current_liabilities, prior_liabilities,
                    )):
                        if current.get("operating_income_source_tag") != operating_tag or any(
                            item.get("assets_source_tag") != "Assets"
                            or item.get("current_liabilities_source_tag") != liabilities_tag
                            for item in (current, prior)
                        ):
                            status = "UNVERIFIED_CAPITAL_BASIS"
                        else:
                            start = prior_assets - prior_liabilities
                            end = current_assets - current_liabilities
                            if start <= 0 or end <= 0:
                                status = "NONPOSITIVE_CAPITAL_EMPLOYED"
                            else:
                                value, status = operating_income / ((start + end) / 2), "VALID"
            parent_names = (
                ("net_income_parent", "shareholders_equity", "prior:shareholders_equity")
                if metric == "roe" else
                ("operating_income", "assets", "current_liabilities", "prior:assets", "prior:current_liabilities")
            )
            parent_ids = []
            for name in parent_names:
                source, key = (prior, name[6:]) if name.startswith("prior:") else (current, name)
                if source is not None and source.get(f"{key}_observation_id"):
                    parent_ids.append(source[f"{key}_observation_id"])
            output.at[index, metric] = value
            output.at[index, f"{metric}_status"] = status
            output.at[index, f"{metric}_parent_observation_ids"] = parent_ids
            records.append({
                "frequency": "annual", "fiscal_year": int(current["fiscal_year"]),
                "fiscal_quarter": 4, "period_end": current["period_end"],
                "metric": metric, "value": value, "status": status,
                "unit": "ratio", "currency": None,
                "parent_observation_ids": parent_ids,
                "method": (
                    "parent_income_over_average_parent_equity"
                    if metric == "roe" else
                    "operating_income_proxy_over_average_assets_less_current_liabilities"
                ),
            })
    return output, pd.DataFrame.from_records(records)
