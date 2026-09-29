import copy
import io
import zipfile
from datetime import date

from src.downloads import (
    DATA_EXPORTS,
    REPORT_EXPORTS,
    complete_export_keys,
    default_export_selection,
    prepare_complete_package,
    prepare_selected_download,
)
from src.exports import export_bundle, historical_csv, zip_bytes


def test_html_csv_and_zip_are_in_memory(synthetic_result):
    files = export_bundle(
        synthetic_result,
        [
            "lifetime_html", "volume_html", "dividend_html", "combined_html",
            "history_csv", "actions_csv", "dividend_csv", "validation_csv",
        ],
        theme="dark",
    )
    assert len(files) == 8
    assert any(name.endswith(".html") and payload.startswith(b"<!doctype html>") for name, payload in files.items())
    history = next(payload for name, payload in files.items() if "lifetime_history" in name)
    assert b"relative_volume_20" in history and b"ttm_dividend_yield" in history
    package = zip_bytes(files)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert set(archive.namelist()) == set(files)


def test_cdn_and_portable_modes(synthetic_result):
    small = export_bundle(synthetic_result, ["lifetime_html"], portable_html=False)
    portable = export_bundle(synthetic_result, ["lifetime_html"], portable_html=True)
    assert len(next(iter(small.values()))) < len(next(iter(portable.values())))


def test_combined_report_sections_and_single_plotly_payload(synthetic_result):
    cdn = next(iter(export_bundle(synthetic_result, ["combined_html"]).values())).decode("utf-8")
    portable = next(iter(export_bundle(
        synthetic_result, ["combined_html"], portable_html=True
    ).values())).decode("utf-8")
    for heading in (
        "Price &amp; Ownership",
        "Volume &amp; Liquidity",
        "Dividends &amp; Total Return",
        "Corporate Actions",
        "Data Quality",
        "Methodology &amp; Provenance",
    ):
        assert heading in cdn
    assert cdn.count("https://cdn.plot.ly/") == 1
    assert portable.count("plotly.js v") == 1
    assert len(cdn) < len(portable)
    light = next(iter(export_bundle(
        synthetic_result, ["combined_html"], theme="light"
    ).values())).decode("utf-8")
    assert "#F4F7FC" in light and "#172033" in light


def test_combined_report_no_dividend_empty_state(synthetic_result):
    result = copy.deepcopy(synthetic_result)
    result.dividend_status = "NONE"
    result.dividend_events = result.dividend_events.iloc[0:0]
    result.annual_dividends = result.annual_dividends.iloc[0:0]
    result.dividend_metrics = {}
    report = next(iter(export_bundle(result, ["combined_html"]).values())).decode("utf-8")
    assert "Dividends &amp; Total Return" in report
    assert "No provider-reported cash-dividend history is available for this security." in report


def test_download_selection_mapping_and_packaging(synthetic_result):
    defaults = default_export_selection(synthetic_result)
    assert set(defaults) == {key for key, _ in (*REPORT_EXPORTS, *DATA_EXPORTS)}
    assert [key for key, selected in defaults.items() if selected] == ["lifetime_html"]
    stamp = date(2026, 9, 29)
    direct = prepare_selected_download(synthetic_result, ["lifetime_html"], stamp=stamp)
    assert direct.filename == "TEST_lifetime_chart_2026-09-29.html"
    assert direct.mime == "text/html" and direct.status == "1 download ready"
    packaged = prepare_selected_download(
        synthetic_result,
        ["lifetime_html", "history_csv"],
        stamp=stamp,
    )
    assert packaged.filename == "TEST_selected_exports_2026-09-29.zip"
    assert packaged.status == "2 selected exports packaged"
    with zipfile.ZipFile(io.BytesIO(packaged.payload)) as archive:
        assert len(archive.namelist()) == 2
        assert any(name.endswith(".html") for name in archive.namelist())
        assert any(name.endswith(".csv") for name in archive.namelist())


def test_complete_packages_include_only_applicable_exports(synthetic_result):
    stamp = date(2026, 9, 29)
    complete = prepare_complete_package(synthetic_result, stamp=stamp)
    assert complete.filename == "TEST_Equity_Lifetime_Explorer_2026-09-29.zip"
    assert complete.status == "Complete analysis package ready"
    with zipfile.ZipFile(io.BytesIO(complete.payload)) as archive:
        names = archive.namelist()
    assert len(names) == 8
    assert any("complete_research_report" in name for name in names)
    assert any("dividend_total_return" in name for name in names)
    assert any("dividend_summary" in name for name in names)

    result = copy.deepcopy(synthetic_result)
    result.dividend_status = "NONE"
    result.dividend_events = result.dividend_events.iloc[0:0]
    result.annual_dividends = result.annual_dividends.iloc[0:0]
    result.dividend_metrics = {}
    assert "dividend_html" not in complete_export_keys(result)
    assert "dividend_csv" not in complete_export_keys(result)
    no_dividend = prepare_complete_package(result, stamp=stamp)
    with zipfile.ZipFile(io.BytesIO(no_dividend.payload)) as archive:
        names = archive.namelist()
    assert len(names) == 6
    assert not any("dividend_total_return" in name for name in names)
    assert not any("dividend_summary" in name for name in names)
    assert any("complete_research_report" in name for name in names)
