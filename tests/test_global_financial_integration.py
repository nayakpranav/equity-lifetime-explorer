"""Offline SEC IFRS, coherent ESEF, native-currency and export regressions."""

from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest

from src.financial_models import SecurityIdentity
from src.financials.normalization import normalize_sec_facts, validate_observation
from src.financials.eps import add_eps_growth
from src.financials.capital_efficiency import calculate_capital_efficiency
from src.financials.presentation import price_overlay_unavailable_reason
from src.financials.global_analysis import analyze_structured_snapshot
from src.financials.oim import normalize_esef_document
from src.financials.vintages import select_latest_disclosed
from src.providers.sec import SecFinancialPayload
from src.providers.sec import SecFinancialProvider, UnsupportedReportingBasis
from src.providers.sec_ifrs import GlobalSecFinancialProvider
from src.research_service import run_fundamentals_analysis
from src.financial_exports import fundamentals_html, annual_financial_csv, financial_provenance_csv
from test_esef_source import report_document, fact, LEI
from test_financials import _eps_observations, _capital_rows


def ifrs_payload():
    identity = SecurityIdentity("SAP.DE", "0001000184", "SAP SE", "SEC:CIK0001000184",
        "SEC:CIK0001000184:SAP.DE", "XETRA", "EUR", "1231",
        accounting_framework="IFRS", identity_method="verified_cross_listing", share_basis_verified=True)
    rows = [{"start": "2024-01-01", "end": "2024-12-31", "val": 123,
        "form": "20-F", "filed": "2025-02-28", "accn": "0001000184-25-000001"},
        {"start": "2025-01-01", "end": "2025-03-31", "val": 35,
         "form": "6-K", "filed": "2025-04-30", "accn": "interim"}]
    return SecFinancialPayload(identity, {"facts": {"ifrs-full": {
        "Revenue": {"units": {"EUR": rows}},
        "ProfitLoss": {"units": {"EUR": rows}},
    }}}, {"0001000184-25-000001": {"filing_date": "2025-02-28", "acceptance": "2025-02-28T12:00:00Z", "form": "20-F"}},
        "2026-10-05T12:00:00+00:00", "a" * 64, 0, 0, taxonomy="ifrs-full")


def test_ifrs_uses_separate_taxonomy_native_currency_and_verified_forms():
    observations = normalize_sec_facts(ifrs_payload())
    assert len(observations) == 1
    record = observations.iloc[0].to_dict()
    assert record["normalized_concept"] == "revenue"
    assert record["currency"] == record["unit"] == "EUR"
    assert record["form"] == "20-F" and record["taxonomy"] == "ifrs-full"
    validate_observation(record)


def test_sec_ifrs_workspace_and_export_keep_partial_coverage(synthetic_result):
    class Provider:
        def fetch(self, *args, **kwargs):
            return ifrs_payload()
    result = run_fundamentals_analysis(replace(synthetic_result.metadata, ticker="SAP.DE", currency="EUR"), provider=Provider())
    assert result.status == "PARTIAL" and result.available and result.quarterly.empty
    assert result.annual.iloc[0].revenue == Decimal(123)
    text = fundamentals_html(result).decode()
    assert "IFRS" in text and "EUR" in text and "SEC EDGAR" in text
    assert "123" in annual_financial_csv(result).decode()
    assert "ifrs-full" in financial_provenance_csv(result).decode()


def esef_result(document=None):
    document = document or report_document()
    rows, diagnostics = normalize_esef_document(document, ticker="MC.PA", currency="EUR", fiscal_year_end="1231")
    identity = SecurityIdentity("MC.PA", "", "LVMH", "LEI:" + LEI, "LEI:" + LEI + ":MC.PA", "Paris", "EUR", "1231", accounting_framework="IFRS")
    return analyze_structured_snapshot(identity, rows, source="ESEF · IFRS",
        retrieved_at_utc=document.retrieved_at_utc, source_sha256=document.source_sha256, diagnostics=diagnostics)


def test_esef_snapshot_integrates_without_invented_disclosure_dates():
    result = esef_result()
    assert result.status == "PARTIAL" and result.available
    assert result.observations.filing_date.isna().all()
    assert result.annual.iloc[0].revenue == Decimal("331839000000")
    assert result.annual.iloc[0].fcf is None
    text = fundamentals_html(result).decode()
    assert "ESEF" in text and "€331.84B" in text
    assert "disclosure timing unverified" in text


def test_missing_dates_do_not_hide_conflicts():
    rows, _ = normalize_esef_document(report_document(), ticker="MC.PA", currency="EUR", fiscal_year_end="1231")
    conflicting = rows.iloc[0].copy()
    conflicting["observation_id"] = "conflict"; conflicting["value"] = "1"
    selected, decisions = select_latest_disclosed(pd.concat([rows, pd.DataFrame([conflicting])], ignore_index=True))
    assert selected.empty and decisions.reason.eq("CONFLICTING_FACTS").all()


def test_esef_snapshots_cannot_mix_document_vintages():
    document = report_document({"a": fact(), "b": fact("GrossProfit")})
    rows, _ = normalize_esef_document(document, ticker="MC.PA", currency="EUR", fiscal_year_end="1231")
    rows.loc[1, "source_sha256"] = "b" * 64
    identity = esef_result().identity
    with pytest.raises(ValueError, match="coherent"):
        analyze_structured_snapshot(identity, rows, source="ESEF", retrieved_at_utc=document.retrieved_at_utc, source_sha256=document.source_sha256)


def test_foreign_overlay_withheld_for_currency_and_share_basis(synthetic_result):
    result = esef_result()
    market = replace(synthetic_result, ticker="MC.PA", metadata=replace(synthetic_result.metadata, currency="USD"))
    assert "currencies differ" in price_overlay_unavailable_reason(result, market)
    market.metadata = replace(market.metadata, currency="EUR")
    assert "share-basis" in price_overlay_unavailable_reason(result, market)
    result.identity = replace(result.identity, share_basis_verified=True)
    assert price_overlay_unavailable_reason(result, market) is None


def test_native_currency_eps_same_filing_growth():
    observations = _eps_observations().assign(currency="EUR", unit="EUR/shares", taxonomy="ifrs-full")
    frame = pd.DataFrame({"fiscal_year": [2025], "fiscal_quarter": [4], "period_end": ["2025-06-30"]})
    output, _ = add_eps_growth(frame, observations, frequency="annual")
    assert output.iloc[0].eps_basic_yoy == Decimal("0.2")
    observations.loc[observations.fiscal_year.eq(2024), "currency"] = "DKK"
    output, _ = add_eps_growth(frame, observations, frequency="annual")
    assert output.iloc[0].eps_basic_yoy is None


def test_ifrs_capital_tags_require_explicit_framework_and_sector_guard():
    frame = _capital_rows()
    for column, value in {"net_income_parent_source_tag": "ProfitLossAttributableToOwnersOfParent",
        "shareholders_equity_source_tag": "EquityAttributableToOwnersOfParent",
        "operating_income_source_tag": "ProfitLossFromOperatingActivities",
        "current_liabilities_source_tag": "CurrentLiabilities"}.items():
        frame[column] = value
    result, _ = calculate_capital_efficiency(frame, accounting_framework="IFRS")
    assert result.iloc[-1].roe_status == result.iloc[-1].roce_status == "VALID"
    result, _ = calculate_capital_efficiency(frame)
    assert result.iloc[-1].roe_status == "UNVERIFIED_ATTRIBUTION"
    result, _ = calculate_capital_efficiency(frame, accounting_framework="IFRS", financial_sector=True)
    assert result.iloc[-1].roce_status == "NOT_APPLICABLE_SECTOR"


@pytest.mark.parametrize("case", ["normal", "ambiguous_currency", "no_revenue"])
def test_latest_foreign_form_cannot_fall_back_to_old_gaap(monkeypatch, synthetic_result, case):
    payload = ifrs_payload()
    payload.facts["cik"] = 1000184
    payload.facts["facts"]["us-gaap"] = {"Assets": {"units": {"USD": []}}}
    if case == "ambiguous_currency":
        payload.facts["facts"]["ifrs-full"]["Revenue"]["units"]["USD"] = payload.facts["facts"]["ifrs-full"]["Revenue"]["units"]["EUR"]
    elif case == "no_revenue":
        payload.facts["facts"]["ifrs-full"]["CashFlowsFromUsedInOperatingActivities"] = payload.facts["facts"]["ifrs-full"].pop("Revenue")
    # Simulate a previous reporting framework coexisting with latest 20-F.
    monkeypatch.setattr(SecFinancialProvider, "fetch", lambda *args, **kwargs: replace(payload, taxonomy="us-gaap"))
    provider = GlobalSecFinancialProvider.__new__(GlobalSecFinancialProvider)
    facts_url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001000184.json"
    provider._response_times = {facts_url: payload.retrieved_at_utc}
    submissions = {"cik": "1000184", "name": "SAP SE", "tickers": ["SAP"], "fiscalYearEnd": "1231",
        "filings": {"recent": {"accessionNumber": ["0001000184-25-000001"], "filingDate": ["2025-02-28"],
            "acceptanceDateTime": ["2025-02-28T12:00:00Z"], "form": ["20-F"]}, "files": []}}
    def response(url):
        if url.endswith("company_tickers.json"):
            return {"0": {"ticker": "SAP", "cik_str": 1000184}}, b"directory"
        return (payload.facts, b"facts") if url == facts_url else (submissions, b"submissions")
    provider._json = response
    metadata = replace(synthetic_result.metadata, ticker="SAP.DE", currency="EUR")
    if case == "ambiguous_currency":
        with pytest.raises(UnsupportedReportingBasis, match="ambiguous"):
            provider.fetch(metadata)
    else:
        result = provider.fetch(metadata)
        assert result.taxonomy == "ifrs-full" and result.identity.reporting_currency == "EUR"
        assert result.identity.ticker == "SAP.DE"
