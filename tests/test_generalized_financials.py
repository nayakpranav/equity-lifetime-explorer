"""Release A.1 exact identity, conservative selection and partial-coverage cases."""
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
import io
import zipfile
import pandas as pd
import pytest

from src.financials.concepts import mappings_for, mapping_scope
from src.financials.normalization import normalize_sec_facts
from src.financials.vintages import select_latest_disclosed
from src.financials.analytics import calculate_fundamentals
from src.providers.sec import SecFinancialProvider, UnsupportedSecIdentity, UnsupportedReportingBasis, MissingStructuredData, SecTransportError
from src.research_service import run_fundamentals_analysis
from src.downloads import prepare_complete_package, complete_export_keys
from src.financial_exports import fundamentals_html, financial_provenance_csv
from test_financials import _payload


def generic_payload(*, sic="3571"):
    pilot = _payload()
    identity = replace(pilot.identity, ticker="NEW", cik="0000000123", issuer_id="SEC:CIK0000000123", sic=sic)
    return replace(pilot, identity=identity)


class PayloadProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def fetch(self, metadata, *, force_refresh=False):
        self.calls.append(force_refresh)
        return self.payload


def test_arbitrary_issuer_partial_coverage_and_general_scope(synthetic_result):
    provider = PayloadProvider(generic_payload())
    result = run_fundamentals_analysis(replace(synthetic_result.metadata, ticker="NEW"), provider=provider, force_refresh=True)
    assert result.status == "PARTIAL" and result.available
    assert result.annual.iloc[-1].revenue == Decimal(200)
    assert result.annual.iloc[-1].fcf == Decimal(60)
    assert result.annual.iloc[-1].net_debt is None
    assert "issuer-specific audit not performed" in result.metadata["mapping_scope"]
    assert provider.calls == [True]
    assert b"mapping_scope" in financial_provenance_csv(result)
    assert mapping_scope(result.identity.cik) != mapping_scope("0000789019")


def test_audited_mappings_belong_to_cik_not_security_symbol():
    assert mappings_for("ANY_SHARE_CLASS", "0001045810") == mappings_for("NVDA", "0001045810")
    assert any(m.concept == "revenue" for m in mappings_for("NEVER_SEEN_TICKER", "0000000123"))


@pytest.mark.parametrize("conflicting", [False, True])
def test_alternative_concepts_equal_priority_or_conflict_withheld(conflicting):
    payload = generic_payload()
    gaap = payload.facts["facts"]["us-gaap"]
    import copy
    gaap["SalesRevenueNet"] = copy.deepcopy(gaap["RevenueFromContractWithCustomerExcludingAssessedTax"])
    if conflicting:
        gaap["SalesRevenueNet"]["units"]["USD"][-1]["val"] = 999
    selected, decisions = select_latest_disclosed(normalize_sec_facts(payload))
    current = selected.loc[selected.normalized_concept.eq("revenue") & selected.period_end.eq("2025-06-30")]
    if conflicting:
        assert current.empty
        assert "CONFLICTING_FACTS" in set(decisions.reason)
    else:
        assert len(current) == 1
        assert current.iloc[0].provider_concept == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_missing_units_and_custom_tags_never_manufacture_revenue(synthetic_result):
    payload = generic_payload()
    payload.facts["facts"]["us-gaap"] = {"RevenueishCustom": {"units": {"USD": []}},
        "Revenues": {"units": {"EUR": [{"val": 100}]}}}
    result = run_fundamentals_analysis(synthetic_result.metadata, provider=PayloadProvider(payload))
    assert result.status == "MISSING_INPUT" and not result.available


def test_generalized_revenue_growth_withholds_incompatible_accounting_basis():
    frame = pd.DataFrame([{"frequency": "annual", "fiscal_year": year, "fiscal_quarter": 4,
        "period_end": f"{year}-12-31", "currency": "USD", "revenue": Decimal(value),
        "revenue_mapping_basis": basis} for year, value, basis in
        [(2024, 100, "net_revenue"), (2025, 120, "revenue_including_assessed_tax")]])
    calculated, ratios = calculate_fundamentals(frame)
    assert pd.isna(calculated.iloc[-1].revenue_yoy)
    assert "INCOMPATIBLE_MAPPING_BASIS" in set(ratios.status)


def test_sic_sector_exclusion_does_not_depend_on_yahoo_sector(synthetic_result):
    result = run_fundamentals_analysis(synthetic_result.metadata, provider=PayloadProvider(generic_payload(sic="6021")))
    assert result.metadata["financial_sector"]
    assert result.annual.iloc[-1].fcf_status == "NOT_APPLICABLE"
    assert result.annual.iloc[-1].roce_status == "NOT_APPLICABLE_SECTOR"


def test_quarter_only_results_and_exports(synthetic_result):
    payload = generic_payload()
    for body in payload.facts["facts"]["us-gaap"].values():
        body["units"]["USD"] = [row for row in body["units"]["USD"] if row["form"] == "10-Q"]
    result = run_fundamentals_analysis(synthetic_result.metadata, provider=PayloadProvider(payload))
    assert result.available and result.annual.empty and not result.quarterly.empty
    assert "financial_annual_csv" not in complete_export_keys(synthetic_result, result)
    assert "financial_quarterly_csv" in complete_export_keys(synthetic_result, result)
    assert b"Financial Fundamentals" in fundamentals_html(result)
    package = prepare_complete_package(synthetic_result, fundamentals=result)
    with zipfile.ZipFile(io.BytesIO(package.payload)) as archive:
        assert any("sec_quarterly_financials" in name for name in archive.namelist())
        assert not any("sec_annual_financials" in name for name in archive.namelist())


class IdentitySession:
    def __init__(self, *, ambiguous=False, wrong_cik=False, form="10-K"):
        self.headers = {}
        self.ambiguous, self.wrong_cik, self.form = ambiguous, wrong_cik, form
        self.calls = []

    def get(self, url, timeout):
        self.calls.append(url)
        if url.endswith("company_tickers.json"):
            body = {"0": {"ticker": "BRK-B", "cik_str": 123}}
            if self.ambiguous:
                body["1"] = {"ticker": "BRK.B", "cik_str": 456}
        elif "/submissions/" in url:
            body = {"cik": 999 if self.wrong_cik else 123, "tickers": ["BRK-B"], "fiscalYearEnd": "1231",
                "filings": {"recent": {"accessionNumber": ["test"], "filingDate": ["2025-01-01"], "form": [self.form]}}}
        else:
            body = {"cik": 123, "facts": {"us-gaap": {"Assets": {}}}}
        return SimpleNamespace(status_code=200, content=b"{}", json=lambda: body)


def test_exact_verified_share_class_alias(synthetic_result):
    provider = SecFinancialProvider("Tests test@example.com", session=IdentitySession())
    identity = provider.fetch(replace(synthetic_result.metadata, ticker="BRK.B")).identity
    assert identity.sec_ticker == "BRK-B" and identity.identity_method == "verified_share_class_alias"


@pytest.mark.parametrize("kwargs", [{"ambiguous": True}, {"wrong_cik": True}])
def test_identity_ambiguity_and_submissions_mismatch_fail_closed(synthetic_result, kwargs):
    provider = SecFinancialProvider("Tests test@example.com", session=IdentitySession(**kwargs))
    with pytest.raises(UnsupportedSecIdentity):
        provider.fetch(replace(synthetic_result.metadata, ticker="BRK.B"))


def test_foreign_private_filer_not_assumed_us_gaap_compatible(synthetic_result):
    provider = SecFinancialProvider("Tests test@example.com", session=IdentitySession(form="20-F"))
    with pytest.raises(UnsupportedReportingBasis):
        provider.fetch(replace(synthetic_result.metadata, ticker="BRK.B"))


def test_sec_cache_reuses_payload_and_explicit_refresh_bypasses(monkeypatch, synthetic_result):
    from src.providers import sec
    monkeypatch.setattr(sec, "_JSON_CACHE", {})
    session = IdentitySession()
    provider = SecFinancialProvider("Tests test@example.com", session=session)
    provider._cache_enabled = True
    metadata = replace(synthetic_result.metadata, ticker="BRK-B")
    provider.fetch(metadata)
    assert len(session.calls) == 3
    first = provider.fetch(metadata)
    second = provider.fetch(metadata)
    assert len(session.calls) == 3
    assert first.retrieved_at_utc == second.retrieved_at_utc
    second.facts["facts"].clear()
    assert provider.fetch(metadata).facts["facts"]  # Caller cannot poison cache.
    provider.fetch(metadata, force_refresh=True)
    assert len(session.calls) == 6


@pytest.mark.parametrize("error,status", [
    (UnsupportedSecIdentity("No exact ticker"), "UNRESOLVED_SEC_IDENTITY"),
    (UnsupportedReportingBasis("20-F unavailable"), "UNSUPPORTED_REPORTING_BASIS"),
    (MissingStructuredData("No Company Facts"), "INSUFFICIENT_STRUCTURED_DATA"),
    (SecTransportError("SEC access restricted (403)"), "TRANSPORT_BLOCKED"),
])
def test_unavailable_states_distinguish_identity_data_basis_and_transport(synthetic_result, error, status):
    class FailedProvider:
        def fetch(self, metadata, **kwargs):
            raise error
    result = run_fundamentals_analysis(synthetic_result.metadata, provider=FailedProvider())
    assert result.status == status and not result.available


def test_foreign_listing_and_fund_do_not_call_sec(synthetic_result):
    provider = PayloadProvider(generic_payload())
    assert run_fundamentals_analysis(replace(synthetic_result.metadata, ticker="UNKNOWN.DE"), provider=provider).status == "NON_SEC_SOURCE"
    assert run_fundamentals_analysis(replace(synthetic_result.metadata, security_type="ETF"), provider=provider).status == "UNSUPPORTED_SECURITY"
    assert not provider.calls


def test_large_submissions_history_targets_only_needed_blocks(synthetic_result):
    class LargeHistory(IdentitySession):
        def get(self, url, timeout):
            response = super().get(url, timeout)
            body = response.json()
            if url.endswith("CIK0000000123.json") and "/submissions/" in url:
                body["filings"]["files"] = [{"name": f"CIK0000000123-submissions-{i:03}.json",
                    "filingFrom": "2000-01-01", "filingTo": "2000-12-31"} for i in range(25)]
            return SimpleNamespace(status_code=200, content=b"{}", json=lambda: body)
    session = LargeHistory()
    provider = SecFinancialProvider("Tests test@example.com", session=session)
    result = provider.fetch(replace(synthetic_result.metadata, ticker="BRK-B"))
    assert result.older_file_count == 25 and result.older_files_loaded == 0
    assert len(session.calls) == 3
