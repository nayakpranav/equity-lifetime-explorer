"""Offline Release A contract, accounting and export regression cases."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from pathlib import Path

import pandas as pd
import pytest

from src.downloads import complete_export_keys, prepare_complete_package, prepare_selected_download
from src.charts.fundamentals import align_split_adjusted_price, build_fundamentals_figures
from src.exports import combined_research_html, export_bundle
from src.financial_exports import annual_financial_csv, fundamentals_html
from src.financial_models import FundamentalsResult, SecurityIdentity
from src.financials.analytics import build_period_table, calculate_fundamentals
from src.financials.capital_efficiency import calculate_capital_efficiency
from src.financials.eps import add_eps_growth
from src.financials.horizons import HORIZONS, filter_financial_horizon
from src.financials.normalization import normalize_sec_facts, validate_observation
from src.financials.periods import classify_period
from src.financials.quality import financial_coverage, statement_reconciliation
from src.financials.quarters import _new_quarter, derive_standalone_quarters
from src.financials.concepts import mappings_for
from src.financials.vintages import select_latest_disclosed
from src.providers.sec import SecFinancialPayload, SecFinancialProvider, SecTransportError, UnsupportedSecIdentity
from src.research_service import run_fundamentals_analysis
from src.report_tables import display_cell
import src.research_service as research_service
import src.service as market_service
from streamlit.testing.v1 import AppTest


def _identity() -> SecurityIdentity:
    return SecurityIdentity("MSFT", "0000789019", "Microsoft Corporation", "SEC:CIK0000789019",
                            "SEC:CIK0000789019:MSFT", "Nasdaq", "USD", "0630")


def _fact(start: str | None, end: str, value: int, accession: str, filed: str, form: str = "10-K") -> dict:
    row = {"end": end, "val": value, "accn": accession, "filed": filed, "form": form}
    if start:
        row["start"] = start
    return row


def _payload() -> SecFinancialPayload:
    first, second, interim = "0000789019-24-000101", "0000789019-25-000102", "0000789019-25-000103"
    facts = {"cik": 789019, "facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            _fact("2023-07-01", "2024-06-30", 100, first, "2024-07-31"),
            _fact("2024-07-01", "2025-06-30", 200, second, "2025-07-31"),
        ]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            _fact("2024-07-01", "2024-09-30", 20, first, "2024-10-31", "10-Q"),
            _fact("2024-07-01", "2024-12-31", 50, interim, "2025-01-31", "10-Q"),
            _fact("2024-07-01", "2025-06-30", 90, second, "2025-07-31"),
        ]}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
            _fact("2024-07-01", "2025-06-30", 30, second, "2025-07-31"),
        ]}},
    }}}
    ledger = {
        first: {"filing_date": "2024-07-31", "acceptance": "2024-07-31T16:30:00Z", "form": "10-K"},
        second: {"filing_date": "2025-07-31", "acceptance": "2025-07-31T16:30:00Z", "form": "10-K"},
        interim: {"filing_date": "2025-01-31", "acceptance": "2025-01-31T16:30:00Z", "form": "10-Q"},
    }
    return SecFinancialPayload(_identity(), facts, ledger, "2026-10-02T00:00:00+00:00", "a" * 64, 0, 0)


def _fundamentals() -> FundamentalsResult:
    annual = pd.DataFrame([{
        "fiscal_year": 2025, "fiscal_quarter": 4, "period_end": "2025-06-30", "currency": "USD",
        "frequency": "annual", "revenue": Decimal(200), "operating_income": Decimal(80),
        "net_income_parent": Decimal(60), "ocf": Decimal(90), "capex_ppe": Decimal(30),
        "fcf": Decimal(60), "cash_equivalents": Decimal(40),
        "reported_long_term_debt": Decimal(20), "net_debt": None,
        "fcf_status": "VALID", "net_debt_status": "PARTIAL_DEBT",
    }])
    observations = normalize_sec_facts(_payload())
    return FundamentalsResult(
        "MSFT", "AVAILABLE", identity=_identity(), annual=annual,
        quarterly=annual.assign(frequency="quarterly", fiscal_quarter=1),
        ratios=pd.DataFrame([{"metric": "operating_margin", "value": Decimal("0.4")}]),
        observations=observations,
        coverage=pd.DataFrame([{"concept": "revenue", "status": "AVAILABLE"}]),
        quality=pd.DataFrame(columns=["check", "concept", "period_end", "accession", "status"]),
        retrieved_at_utc="2026-10-02T00:00:00+00:00", source_sha256="a" * 64,
    )


def test_fiscal_year_boundaries_and_quarterly_cumulative_classification():
    assert classify_period("2024-07-01", "2025-06-30", "0630", "10-K").period_type == "annual"
    q1 = classify_period("2024-07-01", "2024-09-30", "0630", "10-Q")
    q2 = classify_period("2024-07-01", "2024-12-31", "0630", "10-Q")
    assert (q1.fiscal_year, q1.fiscal_quarter, q1.period_type) == (2025, 1, "quarter")
    assert (q2.fiscal_year, q2.fiscal_quarter, q2.period_type) == (2025, 2, "ytd")
    assert classify_period("2024-09-29", "2025-09-27", "0930", "10-K").period_type == "annual"


def test_no_arbitrary_twenty_year_limit_or_opening_balance_only_statement():
    tags = mappings_for("MSFT", "0000789019")
    assert any(item.concept == "eps_basic" for item in tags)
    assert any(item.concept == "net_income_parent" and item.tag == "NetIncomeLoss" for item in tags)
    assert all(item.first_end is None or item.first_end < "2020" for item in tags)
    rows = pd.DataFrame([
        {"fiscal_year": 2007, "fiscal_quarter": 4, "period_end": "2007-06-30", "period_type": "instant",
         "currency": "USD", "normalized_concept": "cash_equivalents", "value": "10",
         "observation_id": "opening", "filing_date": "2008-01-01", "acceptance_timestamp_utc": "2008-01-01T00:00:00Z",
         "provider_concept": "CashAndCashEquivalentsAtCarryingValue", "quality_flags": [], "revision_status": "unknown"},
        {"fiscal_year": 2008, "fiscal_quarter": 4, "period_end": "2008-06-30", "period_type": "annual",
         "currency": "USD", "normalized_concept": "revenue", "value": "100",
         "observation_id": "annual", "filing_date": "2008-08-01", "acceptance_timestamp_utc": "2008-08-01T00:00:00Z",
         "provider_concept": "SalesRevenueNet", "quality_flags": [], "revision_status": "unknown"},
    ])
    annual = build_period_table(rows, pd.DataFrame(), frequency="annual")
    assert list(annual.fiscal_year) == [2008]


def test_canonical_fact_schema_provenance_and_conservative_quarter_derivation():
    observations = normalize_sec_facts(_payload())
    assert not observations.empty
    for record in observations.to_dict("records"):
        validate_observation(record)
    selected, decisions = select_latest_disclosed(observations)
    assert set(decisions.decision) >= {"selected"}
    derived, diagnostics = derive_standalone_quarters(selected)
    q2 = derived.loc[derived.normalized_concept.eq("ocf") & derived.fiscal_quarter.eq(2)].iloc[0]
    assert Decimal(q2.value) == 30
    assert q2.period_start == "2024-10-01"
    assert q2.acceptance_timestamp_utc == "2025-01-31T16:30:00+00:00"
    assert len(q2.parent_observation_ids) == 2
    assert not diagnostics.empty
    annual = build_period_table(selected, derived, frequency="annual")
    assert annual.iloc[-1].currency == "USD"
    assert annual.iloc[-1].fiscal_year == 2025


def test_instant_fact_missing_start_remains_schema_null_after_dataframe_materialization():
    payload = _payload()
    accession = "0000789019-25-000102"
    payload.facts["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"] = {
        "units": {"USD": [_fact(None, "2025-06-30", 40, accession, "2025-07-31")]}
    }
    observations = normalize_sec_facts(payload)
    instant = observations.loc[observations["normalized_concept"].eq("cash_equivalents")].iloc[0]
    assert instant["period_start"] is None
    for record in observations.to_dict("records"):
        validate_observation(record)


def test_coverage_distinguishes_raw_source_from_mapped_selected_periods():
    payload = _payload()
    observations = normalize_sec_facts(payload)
    selected, _ = select_latest_disclosed(observations)
    coverage = financial_coverage(
        observations, selected, mappings_for("MSFT", payload.identity.cik),
        source_facts=payload.facts, fiscal_year_end=payload.identity.fiscal_year_end,
    )
    revenue = coverage.loc[
        coverage.concept.eq("revenue") & coverage.period_type.eq("annual")
    ].iloc[0]
    assert revenue.raw_source_periods == 2
    assert revenue.valid_periods == 2
    assert revenue.raw_source_first_period == "2024-06-30"
    assert revenue.first_period == "2024-06-30"
    assert "mapped_observations" in coverage


def test_revised_or_mismatched_cumulative_parents_are_not_subtracted():
    parent = {
        "issuer_id": "SEC:CIK0000789019", "normalized_concept": "ocf", "provider_concept": "NetCashProvidedByUsedInOperatingActivities",
        "unit": "USD", "currency": "USD", "fiscal_year": 2025, "period_start": "2024-07-01",
        "period_end": "2024-09-30", "acceptance_timestamp_utc": "2024-10-30T20:00:00+00:00",
        "value": "100", "observation_id": "q1", "revision_status": "unknown",
        "filing_date": "2024-10-30",
    }
    later = {**parent, "period_end": "2024-12-31", "acceptance_timestamp_utc": "2025-01-30T20:00:00+00:00",
             "value": "200", "observation_id": "q2"}
    assert Decimal(_new_quarter(pd.Series(later), pd.Series(parent), 2)["value"]) == 100
    assert _new_quarter(pd.Series({**later, "revision_status": "revision_candidate"}), pd.Series(parent), 2) is None
    assert _new_quarter(pd.Series({**later, "unit": "EUR"}), pd.Series(parent), 2) is None


def test_quarter_diagnostics_retain_incompatibility_reason_and_lineage():
    observations = normalize_sec_facts(_payload())
    selected, _ = select_latest_disclosed(observations)
    _, diagnostics = derive_standalone_quarters(selected)
    assert {"reason", "parent_observation_ids"} <= set(diagnostics)
    assert "MISSING_PARENT_PERIOD" in set(diagnostics.status)
    assert diagnostics.parent_observation_ids.map(lambda ids: isinstance(ids, list)).all()


def test_missing_nine_month_parent_never_invents_fourth_quarter():
    observations = normalize_sec_facts(_payload())
    selected, _ = select_latest_disclosed(observations)
    derived, diagnostics = derive_standalone_quarters(selected)
    assert derived.loc[derived.fiscal_quarter.eq(4)].empty
    assert "MISSING_PARENT_PERIOD" in set(diagnostics.status)


def test_instant_balance_fact_is_not_summed_across_periods():
    payload = _payload()
    payload.facts["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"] = {
        "units": {"USD": [
            _fact(None, "2024-09-30", 12, "0000789019-24-000101", "2024-07-31", "10-Q"),
            _fact(None, "2025-06-30", 40, "0000789019-25-000102", "2025-07-31"),
        ]}
    }
    selected, _ = select_latest_disclosed(normalize_sec_facts(payload))
    annual = build_period_table(selected, pd.DataFrame(), frequency="annual")
    assert annual.iloc[-1].cash_equivalents == Decimal(40)
    assert "cash_equivalents" not in set(derive_standalone_quarters(selected)[0].get("normalized_concept", []))


def test_repeated_fact_is_not_restatement_but_conflict_is_excluded():
    payload = _payload()
    revenue_rows = payload.facts["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
    later = {**revenue_rows[-1], "accn": "0000789019-26-000104", "filed": "2026-01-31", "form": "10-Q"}
    payload.accession_ledger[later["accn"]] = {"filing_date": later["filed"], "acceptance": "2026-01-31T12:00:00Z", "form": later["form"]}
    revenue_rows.append(later)
    observations = normalize_sec_facts(payload)
    repeated = observations.loc[observations.accession.eq(later["accn"])].iloc[0]
    assert repeated.revision_status == "unchanged_repeat"
    revenue_rows.append({**later, "val": 999})
    conflicted = normalize_sec_facts(payload)
    peers = conflicted.loc[conflicted.accession.eq(later["accn"])]
    assert peers.quality_status.eq("invalid").all()
    selected, _ = select_latest_disclosed(conflicted)
    assert not selected.observation_id.isin(peers.observation_id).any()


def test_fifty_three_week_fiscal_year_is_classified():
    fiscal = classify_period("2023-10-01", "2024-10-05", "0930", "10-K")
    assert fiscal.period_type == "annual"


def test_negative_income_zero_crossing_and_growth_bases_are_not_fabricated():
    rows = pd.DataFrame([
        {"frequency": "annual", "fiscal_year": 2021, "fiscal_quarter": 4, "period_end": "2021-06-30", "currency": "USD", "revenue": Decimal(100), "operating_income": Decimal(-20), "ocf": Decimal(-5), "capex_ppe": Decimal(0)},
        {"frequency": "annual", "fiscal_year": 2022, "fiscal_quarter": 4, "period_end": "2022-06-30", "currency": "USD", "revenue": Decimal(120), "operating_income": Decimal(0), "ocf": Decimal(5), "capex_ppe": Decimal(0)},
        {"frequency": "annual", "fiscal_year": 2023, "fiscal_quarter": 4, "period_end": "2023-06-30", "currency": "USD", "revenue": Decimal(150), "operating_income": Decimal(15), "ocf": Decimal(10), "capex_ppe": Decimal(0)},
        {"frequency": "annual", "fiscal_year": 2024, "fiscal_quarter": 4, "period_end": "2024-06-30", "currency": "USD", "revenue": Decimal(200), "operating_income": Decimal(30), "ocf": Decimal(20), "capex_ppe": Decimal(0)},
    ])
    calculated, _ = calculate_fundamentals(rows)
    assert calculated.iloc[0].operating_margin == Decimal("-0.2")
    assert pd.isna(calculated.iloc[2].operating_income_yoy)
    assert calculated.iloc[-1].revenue_cagr_3y == Decimal(2) ** (Decimal(1) / Decimal(3)) - 1
    assert pd.isna(calculated.iloc[-1].operating_income_cagr_3y)
    financial, _ = calculate_fundamentals(rows, financial_sector=True)
    assert financial.iloc[-1].fcf_status == "NOT_APPLICABLE"


def test_statement_reconciliation_flags_material_differences_and_preserves_missing():
    frame = pd.DataFrame([
        {"period_end": "2025-06-30", "assets": Decimal(100), "liabilities": Decimal(40),
         "shareholders_equity": Decimal(60), "ocf": Decimal(20), "capex_ppe": Decimal(5),
         "fcf": Decimal(15), "fcf_status": "VALID"},
        {"period_end": "2026-06-30", "assets": Decimal(200000000), "liabilities": Decimal(50000000),
         "shareholders_equity": Decimal(100000000), "ocf": Decimal(20), "capex_ppe": Decimal(5),
         "fcf": Decimal(14), "fcf_status": "VALID"},
        {"period_end": "2027-06-30", "assets": None, "liabilities": Decimal(4),
         "shareholders_equity": Decimal(6), "ocf": None, "capex_ppe": None,
         "fcf": None, "fcf_status": "MISSING_INPUT"},
    ])
    issues = statement_reconciliation(frame)
    assert set(issues.check) == {"BALANCE_IDENTITY_DIFFERENCE", "FCF_RECONCILIATION_FAILURE"}
    assert set(issues.period_end) == {"2026-06-30"}


def _capital_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {"frequency": "annual", "fiscal_year": year, "fiscal_quarter": 4,
         "period_end": f"{year}-06-30", "currency": "USD",
         "net_income_parent": Decimal(income), "net_income_parent_source_tag": "NetIncomeLoss",
         "net_income_parent_observation_id": f"income-{year}",
         "operating_income": Decimal(operating), "operating_income_source_tag": "OperatingIncomeLoss",
         "operating_income_observation_id": f"operating-{year}",
         "shareholders_equity": Decimal(equity), "shareholders_equity_source_tag": "StockholdersEquity",
         "shareholders_equity_observation_id": f"equity-{year}",
         "assets": Decimal(assets), "assets_source_tag": "Assets",
         "assets_observation_id": f"assets-{year}",
         "current_liabilities": Decimal(liabilities), "current_liabilities_source_tag": "LiabilitiesCurrent",
         "current_liabilities_observation_id": f"current-liabilities-{year}"}
        for year, income, operating, equity, assets, liabilities in (
            (2024, "10", "20", "50", "200", "50"),
            (2025, "20", "30", "70", "240", "60"),
        )
    ])


def test_roe_and_roce_use_average_compatible_beginning_and_ending_bases():
    annual, ratios = calculate_capital_efficiency(_capital_rows())
    assert annual.iloc[0].roe is None and annual.iloc[0].roe_status == "MISSING_BEGINNING_PERIOD"
    assert annual.iloc[-1].roe == Decimal(20) / Decimal(60)
    assert annual.iloc[-1].roce == Decimal(30) / Decimal(165)
    assert annual.iloc[-1].roe_parent_observation_ids == ["income-2025", "equity-2025", "equity-2024"]
    assert set(ratios.metric) == {"roe", "roce"}


def test_capital_efficiency_withholds_incompatible_or_misleading_ratios():
    rows = _capital_rows()
    rows.loc[0, "shareholders_equity"] = Decimal(-50)
    result, _ = calculate_capital_efficiency(rows)
    assert result.iloc[-1].roe is None and result.iloc[-1].roe_status == "NONPOSITIVE_EQUITY"
    rows = _capital_rows()
    rows.loc[0, "current_liabilities"] = Decimal(201)
    result, _ = calculate_capital_efficiency(rows)
    assert result.iloc[-1].roce is None and result.iloc[-1].roce_status == "NONPOSITIVE_CAPITAL_EMPLOYED"
    rows = _capital_rows()
    rows.loc[0, "currency"] = "EUR"
    result, _ = calculate_capital_efficiency(rows)
    assert result.iloc[-1].roe_status == "INCOMPATIBLE_CURRENCY"
    rows = _capital_rows()
    rows.loc[1, "shareholders_equity_revision_status"] = "revision_candidate"
    result, _ = calculate_capital_efficiency(rows)
    assert result.iloc[-1].roe_status == "REVISED_INPUT_REVIEW"
    rows = _capital_rows().drop(columns="current_liabilities")
    result, _ = calculate_capital_efficiency(rows)
    assert result.iloc[-1].roce_status == "MISSING_INPUT"
    result, _ = calculate_capital_efficiency(_capital_rows(), financial_sector=True)
    assert result.iloc[-1].roce_status == "NOT_APPLICABLE_SECTOR"


def _eps_observations() -> pd.DataFrame:
    records = []
    # FY2024 is restated from 10 to 5 after a split in the FY2025 filing.
    # The only defensible growth pair is the two values in the same accession.
    for accession, current_year, previous, current in (
        ("filing-2024", 2024, "8", "10"),
        ("filing-2025", 2025, "5", "6"),
        ("filing-2026", 2026, "6", "7"),
    ):
        for concept, tag in (("eps_basic", "EarningsPerShareBasic"), ("eps_diluted", "EarningsPerShareDiluted")):
            for year, value in ((current_year - 1, previous), (current_year, current)):
                records.append({
                    "observation_id": f"{accession}-{concept}-{year}", "issuer_id": "SEC:CIK0000789019",
                    "normalized_concept": concept, "provider_concept": tag,
                    "period_type": "annual", "fiscal_year": year, "fiscal_quarter": 4,
                    "period_end": f"{year}-06-30", "quality_status": "valid",
                    "unit": "USD/shares", "currency": "USD", "taxonomy": "us-gaap", "accession": accession,
                    "acceptance_timestamp_utc": f"{current_year}-08-01T16:00:00+00:00",
                    "value": value,
                })
    return pd.DataFrame(records)


def test_eps_growth_uses_same_filing_split_comparatives_and_chained_cagr():
    annual = pd.DataFrame({"fiscal_year": [2023, 2024, 2025, 2026], "fiscal_quarter": 4,
                           "period_end": [f"{year}-06-30" for year in range(2023, 2027)],
                           "eps_basic": [Decimal(8), Decimal(10), Decimal(6), Decimal(7)],
                           "eps_diluted": [Decimal(8), Decimal(10), Decimal(6), Decimal(7)]})
    calculated, ratios = add_eps_growth(annual, _eps_observations(), frequency="annual")
    assert calculated.loc[2, "eps_diluted_yoy"] == Decimal("0.2")
    assert calculated.loc[3, "eps_diluted_yoy"] == Decimal(7) / Decimal(6) - 1
    assert calculated.loc[2, "eps_diluted_yoy_accession"] == "filing-2025"
    assert calculated.loc[0, "eps_diluted_yoy_status"] == "UNVERIFIED_SHARE_BASIS"
    assert calculated.loc[3, "eps_diluted_cagr_3y_status"] == "VALID_CHAINED_COMPARATIVES"
    assert calculated.loc[3, "eps_diluted_cagr_5y_status"] == "INSUFFICIENT_COMPARABLE_HISTORY"
    assert "eps_basic_yoy" in set(ratios.metric)


def test_eps_negative_and_quarterly_values_are_not_subtracted_or_forced_to_growth():
    observations = _eps_observations()
    observations.loc[observations.accession.eq("filing-2026") & observations.fiscal_year.eq(2026), "value"] = "-1"
    quarterly = pd.DataFrame({"fiscal_year": [2025, 2026], "fiscal_quarter": [2, 2],
                              "period_end": ["2024-12-31", "2025-12-31"],
                              "eps_basic": [Decimal("0.5"), Decimal("-0.2")],
                              "eps_diluted": [Decimal("0.5"), Decimal("-0.2")]})
    annual = pd.DataFrame({"fiscal_year": [2025, 2026], "fiscal_quarter": [4, 4],
                           "period_end": ["2025-06-30", "2026-06-30"],
                           "eps_basic": [Decimal(6), Decimal(-1)], "eps_diluted": [Decimal(6), Decimal(-1)]})
    annual, _ = add_eps_growth(annual, observations, frequency="annual")
    assert annual.iloc[-1].eps_diluted == Decimal(-1)
    assert annual.iloc[-1].eps_diluted_yoy is None
    assert annual.iloc[-1].eps_diluted_yoy_status == "NONPOSITIVE_EPS_BASE"
    quarterly, _ = add_eps_growth(quarterly, observations, frequency="quarterly")
    assert quarterly.iloc[-1].eps_basic == Decimal("-0.2")
    assert quarterly.iloc[-1].eps_basic_yoy_status == "UNVERIFIED_SHARE_BASIS"


@pytest.mark.parametrize("horizon,expected", [("1Y", 2), ("3Y", 4), ("5Y", 6), ("10Y", 11), ("MAX", 20)])
def test_financial_horizon_filters_display_only(horizon, expected):
    frame = pd.DataFrame({"fiscal_year": range(2007, 2027),
                          "fiscal_quarter": [4] * 20,
                          "period_end": [f"{year}-06-30" for year in range(2007, 2027)],
                          "revenue": range(20)})
    displayed = filter_financial_horizon(frame, horizon)
    assert len(displayed) == expected
    assert len(frame) == 20
    assert displayed.iloc[-1].fiscal_year == 2026
    assert HORIZONS == ("1Y", "3Y", "5Y", "10Y", "MAX")


def test_fcf_capex_sign_growth_and_incomplete_debt_are_status_bearing():
    rows = pd.DataFrame([
        {"frequency": "annual", "fiscal_year": 2024, "fiscal_quarter": 4, "period_end": "2024-06-30", "currency": "USD", "revenue": Decimal(100), "ocf": Decimal(50), "capex_ppe": Decimal(20), "cash_equivalents": Decimal(5), "reported_long_term_debt": Decimal(30)},
        {"frequency": "annual", "fiscal_year": 2025, "fiscal_quarter": 4, "period_end": "2025-06-30", "currency": "USD", "revenue": Decimal(200), "ocf": Decimal(90), "capex_ppe": Decimal(30), "cash_equivalents": Decimal(10), "reported_long_term_debt": Decimal(40)},
    ])
    calculated, ratios = calculate_fundamentals(rows)
    assert calculated.iloc[-1].fcf == Decimal(60)
    assert calculated.iloc[-1].revenue_yoy == Decimal(1)
    assert calculated.iloc[-1].net_debt is None
    assert calculated.iloc[-1].net_debt_status == "PARTIAL_DEBT"
    assert not ratios.empty
    missing, _ = calculate_fundamentals(rows.drop(columns="capex_ppe"))
    assert missing.iloc[-1].fcf is None and missing.iloc[-1].fcf_status == "MISSING_INPUT"
    negative, _ = calculate_fundamentals(rows.assign(capex_ppe=Decimal(-30)))
    assert negative.iloc[-1].fcf is None and negative.iloc[-1].fcf_status == "CAPEX_SIGN_ANOMALY"


def test_non_sec_source_leaves_market_analysis_separate(synthetic_result):
    from dataclasses import replace
    unsupported = run_fundamentals_analysis(replace(synthetic_result.metadata, ticker="UNKNOWN.DE"))
    assert unsupported.status == "NON_SEC_SOURCE"
    assert unsupported.annual.empty
    assert synthetic_result.metrics


def test_sec_provider_checks_companyfacts_identity_and_exact_ticker(synthetic_result):
    class FakeSession:
        def __init__(self, wrong_cik=False):
            self.headers = {}
            self.wrong_cik = wrong_cik

        def get(self, url, timeout):
            if url.endswith("company_tickers.json"):
                body = {"0": {"ticker": "TEST", "cik_str": 789019, "title": "Synthetic"}}
            elif "/submissions/" in url:
                body = {"cik": 789019, "tickers": ["TEST"], "name": "Synthetic", "fiscalYearEnd": "0630", "filings": {"recent": {"accessionNumber": ["test"], "filingDate": ["2025-07-31"], "form": ["10-K"]}, "files": []}}
            else:
                body = {"cik": 123 if self.wrong_cik else 789019, "facts": {"us-gaap": {"Assets": {"units": {}}}}}
            return SimpleNamespace(status_code=200, content=b"{}", json=lambda: body)

    provider = SecFinancialProvider("Test Research test@example.com", session=FakeSession(wrong_cik=True))
    with pytest.raises(SecTransportError, match="issuer identity"):
        provider.fetch(synthetic_result.metadata)
    provider = SecFinancialProvider("Test Research test@example.com", session=FakeSession())
    assert provider.fetch(synthetic_result.metadata).identity.cik == "0000789019"


@pytest.mark.parametrize("code", [403, 429])
def test_sec_provider_rejects_access_restrictions_without_leaking_contact(code):
    class RestrictedSession:
        def __init__(self):
            self.headers = {}

        def get(self, url, timeout):
            return SimpleNamespace(status_code=code, content=b"", json=lambda: {})

    provider = SecFinancialProvider("Test Research test@example.com", session=RestrictedSession())
    with pytest.raises(SecTransportError, match=str(code)) as error:
        provider._json("https://www.sec.gov/files/company_tickers.json")
    assert "test@example.com" not in str(error.value)


def test_missing_sec_contact_has_clean_unavailable_state(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.setattr("src.providers.sec.configured_sec_user_agent", lambda: None)
    from src.models import CompanyMetadata
    metadata = CompanyMetadata("MSFT", "MSFT", "Microsoft", "Nasdaq", "USD",
                               sector="Technology", security_type="EQUITY")
    result = run_fundamentals_analysis(metadata)
    assert result.status == "MISSING_SEC_IDENTITY"
    assert result.annual.empty


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_financial_html_combined_csv_and_packages(synthetic_result, theme):
    financials = _fundamentals()
    selected = prepare_selected_download(
        synthetic_result, ["fundamentals_html"], fundamentals=financials, theme=theme,
        stamp=date(2026, 10, 2),
    )
    assert selected.filename.endswith("financial_fundamentals_2026-10-02.html")
    assert selected.payload.count(b"https://cdn.plot.ly/") == 1
    assert b"Financial Fundamentals" in selected.payload
    combined = combined_research_html(synthetic_result, fundamentals=financials, theme=theme)
    assert b"id='fundamentals'" in combined
    assert b"Annual Statement Summary" in combined
    assert combined.count(b"https://cdn.plot.ly/") == 1
    portable = export_bundle(synthetic_result, ["combined_html"], fundamentals=financials, portable_html=True)
    assert next(iter(portable.values())).count(b"plotly.js v") == 1
    keys = complete_export_keys(synthetic_result, financials)
    assert {"financial_annual_csv", "financial_quarterly_csv", "financial_ratios_csv", "financial_provenance_csv", "financial_quality_csv", "fundamentals_html"} <= set(keys)
    packed = prepare_selected_download(
        synthetic_result, ["fundamentals_html", "financial_annual_csv"], fundamentals=financials,
        stamp=date(2026, 10, 2),
    )
    with zipfile.ZipFile(io.BytesIO(packed.payload)) as archive:
        assert len(archive.namelist()) == 2
    complete = prepare_complete_package(synthetic_result, fundamentals=financials, stamp=date(2026, 10, 2))
    with zipfile.ZipFile(io.BytesIO(complete.payload)) as archive:
        assert len(archive.namelist()) >= len(keys)
        assert any(name.endswith("financial_status_2026-10-02.txt") for name in archive.namelist())


def test_missing_sec_fundamentals_hide_specialist_exports_but_keep_combined(synthetic_result):
    unavailable = FundamentalsResult("TEST", "UNSUPPORTED_SOURCE", "No audited SEC mapping")
    keys = complete_export_keys(synthetic_result, unavailable)
    assert "combined_html" in keys and "fundamentals_html" not in keys
    assert "No audited SEC mapping" in combined_research_html(synthetic_result, fundamentals=unavailable).decode()


def test_eps_and_capital_charts_use_fiscal_categories_and_horizon():
    financials = _fundamentals()
    rows = []
    for year in range(2021, 2026):
        item = financials.annual.iloc[0].copy()
        item["fiscal_year"] = year
        item["period_end"] = f"{year}-06-30"
        item["eps_basic"] = Decimal(year - 2020)
        item["eps_diluted"] = Decimal(year - 2020) - Decimal("0.1")
        item["eps_basic_yoy"] = Decimal("0.1")
        item["eps_diluted_yoy"] = Decimal("0.1")
        item["roe"] = Decimal("0.2")
        item["roce"] = Decimal("0.15")
        item["roe_status"] = "VALID"
        item["roce_status"] = "VALID"
        rows.append(item)
    financials.annual = pd.DataFrame(rows).reset_index(drop=True)
    figures = build_fundamentals_figures(financials, horizon="3Y")
    assert list(figures) == [
        "Growth & Profitability", "Cash Generation", "Balance-Sheet Strength",
        "Reported EPS & Comparable Growth", "Capital Efficiency (Annual)",
    ]
    eps = figures["Reported EPS & Comparable Growth"]
    assert list(eps.data[0].x) == ["FY2022", "FY2023", "FY2024", "FY2025"]
    assert list(figures["Capital Efficiency (Annual)"].data[0].x) == list(eps.data[0].x)
    assert len(financials.annual) == 5  # Display selector did not mutate full data.
    assert all("FY" in str(value) for value in eps.data[0].x)


def test_financial_workspace_and_download_selection_do_not_retrieve_again(monkeypatch, synthetic_result):
    synthetic_result.metadata.currency = "USD"
    calls = {"market": 0, "sec": 0}

    def fake_market(ticker, **kwargs):
        calls["market"] += 1
        return synthetic_result

    def fake_sec(metadata, **kwargs):
        calls["sec"] += 1
        result = _fundamentals()
        result.ticker = metadata.ticker
        return result

    monkeypatch.setattr(market_service, "run_equity_analysis", fake_market)
    monkeypatch.setattr(research_service, "run_fundamentals_analysis", fake_sec)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.text_input[0].set_value("TEST")
    next(button for button in app.button if button.label == "ANALYZE").click().run()
    assert not app.exception
    assert calls == {"market": 1, "sec": 1}
    next(control for control in app.get("button_group") if control.label == "Analytical workspace").set_value("Financial Fundamentals").run()
    assert not app.exception
    assert calls == {"market": 1, "sec": 1}
    assert any(heading.value == "Financial Fundamentals" for heading in app.subheader)
    next(control for control in app.get("button_group") if control.label == "History shown").set_value("5Y").run()
    assert not app.exception
    assert calls == {"market": 1, "sec": 1}
    next(control for control in app.checkbox if control.label.startswith("Overlay split-adjusted share price")).set_value(True).run()
    assert not app.exception
    assert calls == {"market": 1, "sec": 1}
    next(button for button in app.button if button.label == "Downloads").click().run()
    assert not app.exception
    choices = {control.label: control for control in app.checkbox}
    assert choices["Financial Fundamentals HTML"].disabled is False
    assert choices["Annual Financials CSV"].disabled is False
    assert choices["Financial Quality CSV"].disabled is False
    assert calls == {"market": 1, "sec": 1}


def test_sec_failure_does_not_break_market_workspace_or_remain_cached(monkeypatch, synthetic_result):
    calls = {"market": 0, "sec": 0}
    synthetic_result.ticker = "SECFAILTEST"
    synthetic_result.metadata.ticker = "SECFAILTEST"

    def fake_market(ticker, **kwargs):
        calls["market"] += 1
        return synthetic_result

    def fake_sec(metadata, **kwargs):
        calls["sec"] += 1
        return (
            FundamentalsResult("TEST", "TRANSPORT_BLOCKED", "SEC temporarily unavailable")
            if calls["sec"] == 1 else _fundamentals()
        )

    monkeypatch.setattr(market_service, "run_equity_analysis", fake_market)
    monkeypatch.setattr(research_service, "run_fundamentals_analysis", fake_sec)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    app.text_input[0].set_value("SECFAILTEST")
    next(button for button in app.button if button.label == "ANALYZE").click().run()
    assert not app.exception
    assert calls == {"market": 1, "sec": 1}
    assert any("Price & Ownership" in heading.value for heading in app.subheader)
    next(button for button in app.button if button.label == "ANALYZE").click().run()
    assert not app.exception
    assert calls["sec"] == 2  # A transient SEC failure was not cached for 24 hours.
    next(control for control in app.get("button_group") if control.label == "Analytical workspace").set_value("Financial Fundamentals").run()
    assert not app.exception
    assert calls["market"] == 1 and calls["sec"] == 2


def test_reader_facing_financial_tables_format_without_changing_csv(synthetic_result):
    financials = _fundamentals()
    financials.annual.loc[0, "revenue"] = Decimal("331839000000")
    financials.annual.loc[0, "roe"] = Decimal("0.340386274504")
    financials.annual.loc[0, "eps_diluted"] = Decimal("17.95321")
    financials.annual.loc[0, "fcf"] = None
    specialist = fundamentals_html(financials).decode()
    combined = combined_research_html(synthetic_result, fundamentals=financials).decode()
    for report in (specialist, combined):
        assert "$331.84B" in report
        assert "34.0%" in report
        assert "$17.953" in report
        assert "<td>2025</td>" in report
        assert ">—</td>" in report
        assert "<td>NaN</td>" not in report and "<td>None</td>" not in report
        assert "Financial Data Quality" in report
    assert "Market Data Quality" in combined
    assert "Overall confidence" not in combined
    csv = annual_financial_csv(financials).decode()
    assert "331839000000" in csv and "0.340386274504" in csv
    assert "—" not in csv


def test_reader_facing_zero_and_missing_are_distinct_and_units_are_semantic():
    assert display_cell(None, "revenue", "USD") == "—"
    assert display_cell(0, "revenue", "USD") != "—"
    assert display_cell(Decimal("0.340386274504"), "roe", "USD") == "34.0%"
    assert display_cell(Decimal("331839000000"), "revenue", "USD") == "$331.84B"
    assert display_cell(Decimal("1.25"), "eps_diluted", "USD") == "$1.250"
    assert display_cell(2025, "fiscal_year", "USD") == "2025"


def test_fiscal_end_overlay_uses_existing_split_adjusted_close_without_lookahead(synthetic_result):
    market = synthetic_result
    frame = pd.DataFrame({"period_end": ["2024-05-31", "2024-06-04", "2026-01-31", "2021-01-01", None]})
    values, dates = align_split_adjusted_price(frame, market)
    for position in (0, 1):
        observed = pd.Timestamp(dates[position])
        assert observed <= pd.Timestamp(frame.loc[position, "period_end"])
        assert values[position] == pytest.approx(market.prices.loc[observed, "split_adjusted_price_current_share"])
    assert values[0] != pytest.approx(market.prices.loc[pd.Timestamp(dates[0]), "raw_close"])
    assert values[2:] == [None, None, None]


def test_financial_price_overlay_is_optional_and_propagates_to_reports(synthetic_result):
    synthetic_result.metadata.currency = "USD"
    financials = _fundamentals()
    financials.ticker = synthetic_result.ticker
    base = build_fundamentals_figures(financials)
    assert all("Split-adjusted share price" not in [trace.name for trace in figure.data] for figure in base.values())
    overlaid = build_fundamentals_figures(financials, market=synthetic_result, price_overlay=True)
    for heading in ("Growth & Profitability", "Cash Generation"):
        assert "Split-adjusted share price" in [trace.name for trace in overlaid[heading].data]
    financials.annual.loc[0, "eps_diluted"] = Decimal("1.25")
    overlaid = build_fundamentals_figures(financials, market=synthetic_result, price_overlay=True)
    assert "Split-adjusted share price" in [trace.name for trace in overlaid["Reported EPS & Comparable Growth"].data]
    assert "Split-adjusted share price" not in [trace.name for trace in overlaid["Balance-Sheet Strength"].data]
    assert all("Split-adjusted share price" not in [trace.name for trace in figure.data]
               for figure in build_fundamentals_figures(financials, market=synthetic_result, price_overlay=False).values())
    financials.annual.loc[0, "fcf"] = None
    no_fcf = build_fundamentals_figures(financials, market=synthetic_result, price_overlay=True)
    assert "Split-adjusted share price" not in [trace.name for trace in no_fcf["Cash Generation"].data]

    files = export_bundle(
        synthetic_result, ["fundamentals_html", "combined_html"],
        fundamentals=financials, financial_price_overlay=True,
    )
    for payload in files.values():
        text = payload.decode()
        assert "Split-adjusted share price" in text
        assert "not an as-known-at-date comparison" in text
