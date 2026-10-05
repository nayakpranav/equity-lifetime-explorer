"""Deterministic identity, unit, period and context safeguards for ESEF."""

import copy

import pytest

from src.financials.oim import normalize_esef_document, oim_period
from src.providers.esef import EsefDocument, EsefFinancialProvider, EsefSourceError, repository_url


LEI = "IOG4E947OATN0KJYSD45"


def report_document(facts=None):
    return EsefDocument(LEI, {}, {
        "documentInfo": {
            "documentType": "https://xbrl.org/2021/xbrl-json",
            "namespaces": {
                "ifrs": "https://xbrl.ifrs.org/taxonomy/2022-03-24/ifrs-full",
                "scheme": "http://standards.iso.org/iso/17442",
                "iso": "http://www.xbrl.org/2003/iso4217",
                "xbrli": "http://www.xbrl.org/2003/instance",
            },
        },
        "facts": facts or {"a": fact()},
    }, "https://filings.xbrl.org/example.json", "a" * 64, "2026-10-05T12:00:00+00:00")


def fact(tag="Revenue", value="331839000000", period="2024-01-01T00:00:00/2025-01-01T00:00:00"):
    return {"value": value, "decimals": -6, "dimensions": {
        "concept": "ifrs:" + tag, "entity": "scheme:" + LEI,
        "period": period, "unit": "iso:EUR",
    }}


def normalize(document):
    return normalize_esef_document(document, ticker="MC.PA", currency="EUR", fiscal_year_end="1231")


def test_oim_dates_exclusive_end_and_instant():
    assert oim_period("2024-01-01T00:00:00/2025-01-01T00:00:00") == ("2024-01-01", "2024-12-31")
    assert oim_period("2025-01-01T00:00:00") == (None, "2024-12-31")
    with pytest.raises(ValueError):
        oim_period("2024-01-01T12:00:00/2025-01-01T00:00:00")


def test_value_not_rescaled_by_decimals_and_timestamp_not_invented():
    rows, issues = normalize(report_document())
    row = rows.iloc[0]
    assert row.value == "331839000000"
    assert row.scale == 0 and row.reported_decimals == "-6"
    assert row.currency == "EUR" and row.unit == "EUR"
    assert row.fiscal_year == 2024 and row.period_end == "2024-12-31"
    assert row.filing_date is None and row.acceptance_timestamp_utc is None
    assert row.availability_precision == "unknown"
    assert issues.empty


@pytest.mark.parametrize("change,reason", [
    ({"entity": "scheme:" + "0" * 20}, "ISSUER_IDENTITY_MISMATCH"),
    ({"segment:axis": "segment:member"}, "UNVERIFIED_DIMENSIONAL_CONTEXT"),
    ({"unit": "iso:USD"}, "INCOMPATIBLE_UNIT_OR_CURRENCY"),
    ({"period": "2024-01-01T00:00:00/2025-01-01T12:00:00"}, "INVALID_VALUE_OR_PERIOD"),
])
def test_unsafe_contexts_withheld(change, reason):
    document = report_document()
    document.report["facts"]["a"]["dimensions"].update(change)
    rows, issues = normalize(document)
    assert rows.empty
    assert issues.iloc[0].reason == reason


def test_parent_income_not_replaced_with_all_interests_profit():
    rows, _ = normalize(report_document({"a": fact("ProfitLoss")}))
    assert rows.empty


def test_eps_resolves_unit_namespace_not_literal_prefix():
    observation = fact("BasicEarningsLossPerShare", "2.55")
    observation["dimensions"]["unit"] = "iso:EUR/sh:shares"
    document = report_document({"a": observation})
    document.report["documentInfo"]["namespaces"]["sh"] = "http://www.xbrl.org/2003/instance"
    rows, issues = normalize(document)
    assert issues.empty and rows.iloc[0].unit == "EUR/shares"
    assert rows.iloc[0].share_basis_status == "unknown"


def test_extension_tag_not_mapped_by_local_name():
    document = report_document()
    document.report["documentInfo"]["namespaces"]["ifrs"] = "https://issuer.example/taxonomy"
    rows, _ = normalize(document)
    assert rows.empty


def test_conflicting_duplicate_withheld_equal_duplicate_retains_lineage():
    first = fact()
    rows, _ = normalize(report_document({"a": first, "b": fact(value="99")}))
    assert rows.quality_status.eq("invalid").all()
    rows, _ = normalize(report_document({"a": first, "b": copy.deepcopy(first)}))
    assert len(rows) == 2
    assert rows.quality_status.eq("invalid").sum() == 1


def test_equal_decimal_values_with_different_lexical_precision_are_not_conflicts():
    rows, _ = normalize(report_document({"a": fact(value="1.0"), "b": fact(value="1.00")}))
    assert rows.quality_status.eq("invalid").sum() == 1
    assert not any("CONFLICTING_FACTS" in flags for flags in rows.quality_flags)


def test_missing_and_zero_financial_values_remain_distinct():
    rows, issues = normalize(report_document({"a": fact(value="0"), "b": fact("GrossProfit", None)}))
    assert len(rows) == 1 and rows.iloc[0].value == "0"
    assert issues.iloc[0].reason == "INVALID_VALUE_OR_PERIOD"


@pytest.mark.parametrize("url", ["https://evil.example/x", "//evil.example/x", "http://filings.xbrl.org/x", "https://filings.xbrl.org@evil.example/x"])
def test_repository_url_rejects_external_or_insecure_locations(url):
    with pytest.raises(EsefSourceError):
        repository_url(url)


def test_relative_repository_url():
    assert repository_url("/api/filings") == "https://filings.xbrl.org/api/filings"


def test_real_api_relationship_is_link_not_lei_database_id():
    row = {"relationships": {"entity": {"links": {"related": "/api/entities/" + LEI}}}}
    EsefFinancialProvider._verify_relationship(LEI, row)
    row["relationships"]["entity"]["links"]["related"] = "/api/entities/" + "0" * 20
    with pytest.raises(EsefSourceError):
        EsefFinancialProvider._verify_relationship(LEI, row)
