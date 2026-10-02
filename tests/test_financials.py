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
from src.exports import combined_research_html, export_bundle
from src.financial_models import FundamentalsResult, SecurityIdentity
from src.financials.analytics import build_period_table, calculate_fundamentals
from src.financials.normalization import normalize_sec_facts, validate_observation
from src.financials.periods import classify_period
from src.financials.quality import statement_reconciliation
from src.financials.quarters import _new_quarter, derive_standalone_quarters
from src.financials.vintages import select_latest_disclosed
from src.providers.sec import SecFinancialPayload, SecFinancialProvider, SecTransportError, UnsupportedSecIdentity
from src.research_service import run_fundamentals_analysis
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
        "net_income_consolidated": Decimal(60), "ocf": Decimal(90), "capex_ppe": Decimal(30),
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


def test_nonpilot_and_sec_failure_leave_market_analysis_separate(synthetic_result):
    unsupported = run_fundamentals_analysis(synthetic_result.metadata)
    assert unsupported.status == "UNSUPPORTED_SOURCE"
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
                body = {"tickers": ["TEST"], "name": "Synthetic", "fiscalYearEnd": "0630", "filings": {"recent": {}, "files": []}}
            else:
                body = {"cik": 123 if self.wrong_cik else 789019, "facts": {}}
            return SimpleNamespace(status_code=200, content=b"{}", json=lambda: body)

    provider = SecFinancialProvider("Test Research test@example.com", session=FakeSession(wrong_cik=True))
    with pytest.raises(SecTransportError, match="issuer identity"):
        provider.fetch(synthetic_result.metadata)
    provider = SecFinancialProvider("Test Research test@example.com", session=FakeSession())
    assert provider.fetch(synthetic_result.metadata).identity.cik == "0000789019"


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
    assert b"Annual SEC Statement Summary" in combined
    assert combined.count(b"https://cdn.plot.ly/") == 1
    portable = export_bundle(synthetic_result, ["combined_html"], fundamentals=financials, portable_html=True)
    assert next(iter(portable.values())).count(b"plotly.js v") == 1
    keys = complete_export_keys(synthetic_result, financials)
    assert {"financial_annual_csv", "financial_quarterly_csv", "financial_ratios_csv", "financial_provenance_csv", "fundamentals_html"} <= set(keys)
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


def test_financial_workspace_and_download_selection_do_not_retrieve_again(monkeypatch, synthetic_result):
    calls = {"market": 0, "sec": 0}

    def fake_market(ticker, **kwargs):
        calls["market"] += 1
        return synthetic_result

    def fake_sec(metadata, **kwargs):
        calls["sec"] += 1
        return _fundamentals()

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
    next(button for button in app.button if button.label == "Downloads").click().run()
    assert not app.exception
    choices = {control.label: control for control in app.checkbox}
    assert choices["Financial Fundamentals HTML"].disabled is False
    assert choices["SEC Annual Financials CSV"].disabled is False
    assert calls == {"market": 1, "sec": 1}
