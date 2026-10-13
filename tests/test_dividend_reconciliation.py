"""Observed ITC regression and generalized session/source accounting guards."""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.providers.action_dates import ACTION_DATA_VERSION, session_dates
from src.providers.yahoo import _normalize_history_index, _merge_dedicated_action_series, YahooFinanceProvider
from src.corporate_actions import _normalize_provider_actions, actions_to_frame
from src.reconstruction import prepare_price_data
from src.dividends import add_dividend_analytics
from src.dividend_validation import validate_declared_dividends
from src.models import CompanyMetadata
import src.dividends as dividends_module


def itc_frames():
    evidence = json.loads((Path(__file__).parent / "fixtures/itc_dividend_observations.json").read_text())
    index = pd.date_range("1996-01-01", "2026-10-13", freq="D", tz=evidence["timezone"])
    history = pd.DataFrame(dict(Close=260.0, Open=260.0, High=261.0, Low=259.0,
        Volume=1000, Dividends=0.0, **{"Adj Close": 250.0, "Stock Splits": 0.0}), index=index)
    for date, amount in evidence["events"]:
        history.loc[pd.Timestamp(date, tz=evidence["timezone"]), "Dividends"] = amount
    for date, ratio in evidence["splits"]:
        history.loc[pd.Timestamp(date, tz=evidence["timezone"]), "Stock Splits"] = ratio
    dedicated = history.loc[history.Dividends.ne(0), "Dividends"].copy()
    dedicated.index += pd.Timedelta(hours=9, minutes=15)
    splits = history.loc[history["Stock Splits"].ne(0), "Stock Splits"].copy()
    splits.index += pd.Timedelta(hours=9, minutes=15)
    return history, SimpleNamespace(dividends=dedicated, splits=splits)


def fixed_frame(history, obj):
    normalized, _ = _normalize_history_index(history, "Asia/Kolkata")
    return _merge_dedicated_action_series(normalized, obj, "Asia/Kolkata")[0]


def itc_analytics(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 13, tzinfo=timezone.utc)
    monkeypatch.setattr(dividends_module, "datetime", Clock)
    history, obj = itc_frames()
    merged = fixed_frame(history, obj)
    actions = actions_to_frame(_normalize_provider_actions(merged, "INR"))
    prices, _, _, _ = prepare_price_data(merged, actions)
    return merged, add_dividend_analytics(prices, currency="INR", adjusted_close_available=True, dividend_observations=merged.Dividends)


def test_itc_observed_utc_bug_is_reproducible_but_fixed_calendar_dates_agree():
    history, obj = itc_frames()
    old_history = pd.to_datetime(history.index, utc=True).tz_convert(None).normalize()
    old_dedicated = pd.to_datetime(obj.dividends.index, utc=True).tz_convert(None).normalize()
    assert old_history[history.Dividends.ne(0)][-2] == pd.Timestamp("2026-02-03")
    assert old_dedicated[-2] == pd.Timestamp("2026-02-04")
    merged = fixed_frame(history, obj)
    assert merged.Dividends.groupby(merged.index.year).sum()[2025] == pytest.approx(14.35)
    assert merged.Dividends.groupby(merged.index.year).sum()[2026] == pytest.approx(14.50)
    assert merged.Dividends.ne(0).sum() == 37
    assert merged["Stock Splits"].ne(0).sum() == 3
    assert merged.attrs["action_audit"][-1]["decision"] == "cross_source_confirmed_once"


def test_itc_annual_ttm_yield_cagr_frequency_and_counts(monkeypatch):
    merged, (prices, events, annual, status, metrics, issues) = itc_analytics(monkeypatch)
    for year, total, count in [(2020,10.15,1),(2021,10.75,2),(2022,11.50,2),
        (2023,15.50,2),(2024,13.75,2),(2025,14.35,2),(2026,14.50,2)]:
        row = annual.loc[annual.year.eq(year)].iloc[0]
        assert row.annual_dividend == pytest.approx(total)
        assert row.payment_count == count
    assert metrics["ttm_dividend"] == pytest.approx(14.5)
    assert metrics["current_ttm_dividend_yield"] == pytest.approx(14.5 / 260.0)
    assert metrics["dividend_growth_1y"] == pytest.approx(14.35 / 13.75 - 1)
    for n, initial in [(3,11.5),(5,10.15),(10,4.166667)]:
        assert metrics[f"dividend_cagr_{n}y"] == pytest.approx((14.35/initial)**(1/n)-1)
    assert metrics["inferred_payment_frequency"] == "Semiannual"
    assert metrics["dividend_event_count"] == 37
    assert metrics["cagr_endpoint_year"] == 2025
    assert metrics["current_year_ytd_dividend"] == pytest.approx(14.5)
    assert metrics["prior_year_same_period_dividend"] == pytest.approx(14.35)
    assert prices.cumulative_split_factor.iloc[-1] == 30
    assert events.loc[events.date.eq(pd.Timestamp("2023-05-30")), "provider_dividend"].iloc[0] == 9.5
    metadata = CompanyMetadata("ITC.NS","ITC.NS","ITC","NSE","INR")
    external = validate_declared_dividends(prices, events, metadata)
    assert len(external) == 8 and all(issue.severity == "PASS" for issue in external)


@pytest.mark.parametrize("zone", ["Asia/Kolkata","Europe/Berlin","America/New_York","Asia/Tokyo"])
def test_midnight_and_market_open_preserve_same_session_in_all_timezones(zone):
    midnight = pd.Timestamp("2025-02-12", tz=zone)
    opening = midnight + pd.Timedelta(hours=9, minutes=30)
    assert session_dates([midnight],zone).equals(session_dates([opening],zone))
    assert session_dates([midnight.tz_convert("UTC")],zone)[0] == pd.Timestamp("2025-02-12")
    assert session_dates(["2025-02-12"])[0] == pd.Timestamp("2025-02-12")


def test_dst_and_new_year_exchange_dates_not_utc_dates():
    assert session_dates(pd.DatetimeIndex(["2025-01-01T00:00:00+05:30"]),"Asia/Kolkata")[0].year == 2025
    instants = pd.to_datetime(["2025-03-28T23:00:00Z","2025-03-30T22:00:00Z"])
    assert list(session_dates(instants,"Europe/Berlin")) == [pd.Timestamp("2025-03-29"),pd.Timestamp("2025-03-31")]


def test_genuine_cash_components_and_adjacent_identical_amounts_not_dropped():
    index = pd.date_range("2025-05-28", periods=3)
    history = pd.DataFrame({"Close":100.0,"Dividends":[0.0,9.5,0.0]},index=index)
    obj = SimpleNamespace(splits=pd.Series(dtype=float), dividends=pd.Series([6.75,2.75,9.5],
        index=pd.DatetimeIndex(["2025-05-29T09:00:00+05:30","2025-05-29T09:00:00+05:30","2025-05-30T09:00:00+05:30"])))
    result = fixed_frame(history,obj)
    assert result.loc["2025-05-29","Dividends"] == result.loc["2025-05-30","Dividends"] == 9.5
    assert not any(issue.check == "action_source_conflict" for issue in result.attrs["action_issues"])


def test_conflicting_amounts_and_ambiguous_duplicates_are_flagged_not_repaired():
    history = pd.DataFrame({"Close":[100,100],"Dividends":[6.5,0]},index=pd.date_range("2025-02-12",periods=2))
    obj = SimpleNamespace(splits=pd.Series(dtype=float),dividends=pd.Series([7.0,2.0,2.0],
        index=pd.DatetimeIndex(["2025-02-12T09:15:00+05:30","2025-02-13T09:15:00+05:30","2025-02-13T09:15:00+05:30"])))
    result = fixed_frame(history,obj)
    assert result.Dividends.tolist() == [6.5,0.0]
    assert len(result.attrs["action_issues"]) == 2
    assert {row["decision"] for row in result.attrs["action_audit"]} >= {"conflict_history_retained","ambiguous_withheld"}


def test_missing_price_event_is_retained_without_inventing_a_close():
    index = pd.to_datetime(["2025-01-02","2025-01-06"])
    prices = pd.DataFrame({"raw_close":100.,"no_split_close":100.,"adjusted_close":90.,"cumulative_split_factor":1.,"dividend":0.},index=index)
    cash = pd.Series([2.],index=pd.to_datetime(["2025-01-03"]))
    frame, events, annual, _, metrics, issues = add_dividend_analytics(prices,currency="USD",adjusted_close_available=True,dividend_observations=cash)
    assert frame.index.equals(index)
    assert len(events) == 1 and annual.annual_dividend.iloc[0] == 2
    assert pd.isna(events.split_adjusted_price_current_share.iloc[0])
    assert metrics["ttm_dividend"] == 2
    assert any(issue.check == "dividend_event_without_price" for issue in issues)


def test_external_validation_detects_double_values_despite_internal_reconciliation(monkeypatch):
    _, (prices, events, _, _, _, _) = itc_analytics(monkeypatch)
    doubled = events.copy(); doubled.provider_dividend *= 2
    before = doubled.copy(deep=True)
    issues = validate_declared_dividends(prices,doubled,CompanyMetadata("ITC.NS","ITC.NS","ITC","NSE","INR"))
    assert all(issue.severity == "ERROR" for issue in issues)
    pd.testing.assert_frame_equal(before,doubled)


def test_cache_version_does_not_reuse_pre_fix_payload(tmp_path):
    provider = YahooFinanceProvider(cache_dir=tmp_path)
    assert ACTION_DATA_VERSION in provider._cache_path("ITC.NS").name


def test_uploaded_report_21_ytd_path_reproduces_with_utc_shift_and_action_only_row():
    history, obj = itc_frames()
    # Uploaded chart jumps May26->May28 without a May27 trading observation.
    # Local May28's missing bar becomes UTC May27 under the production defect.
    history = history.drop(pd.Timestamp("2026-05-28",tz="Asia/Kolkata"))
    old = history.copy()
    old.index = pd.to_datetime(old.index,utc=True).tz_convert(None).normalize()
    dedicated = obj.dividends.copy()
    dedicated.index = pd.to_datetime(dedicated.index,utc=True).tz_convert(None).normalize()
    old = old.reindex(old.index.union(dedicated.index).sort_values())
    for date, amount in dedicated.items():
        if pd.isna(old.loc[date,"Dividends"]) or old.loc[date,"Dividends"] == 0:
            old.loc[date,"Dividends"] = amount
    old_prices = old.loc[old.Close.notna()]
    assert old_prices.loc[old_prices.index.year == 2026,"Dividends"].sum() == 21
    assert old.loc["2026-05-27","Dividends"] == 8 and pd.isna(old.loc["2026-05-27","Close"])
    corrected = fixed_frame(history,obj)
    assert corrected.loc[corrected.index.year == 2026,"Dividends"].sum() == 14.5


def test_external_reference_is_currency_and_share_basis_safe(monkeypatch):
    _, (prices, events, _, _, _, _) = itc_analytics(monkeypatch)
    metadata = CompanyMetadata("ITC.NS","ITC.NS","ITC","NSE","USD")
    assert all(issue.check == "dividend_external_basis" for issue in validate_declared_dividends(prices,events,metadata))
    metadata.currency = "INR"
    # A genuine new split changes reference units, not provider facts.
    shifted = prices.copy(); shifted.loc[shifted.index >= "2026-08-01","cumulative_split_factor"] *= 2
    later = events.copy()
    later.provider_dividend /= float(shifted.cumulative_split_factor.iloc[-1] / prices.cumulative_split_factor.iloc[-1])
    checks = validate_declared_dividends(shifted,later,metadata)
    assert all(issue.severity == "PASS" for issue in checks if "2025-12-31" in issue.message)
    assert any(issue.check == "dividend_external_basis" for issue in checks)


def test_missing_timezone_and_history_duplicates_are_not_silently_certified():
    h=pd.DataFrame({"Close":[100,101],"Dividends":[1,2]},index=pd.to_datetime(["2025-02-12","2025-02-12"]))
    normalized,count = _normalize_history_index(h)
    assert count == 2
    result,_ = _merge_dedicated_action_series(normalized,SimpleNamespace(splits=pd.Series(dtype=float),dividends=pd.Series(dtype=float)))
    assert {issue.check for issue in result.attrs["action_issues"]} >= {"action_source_conflict","action_timezone_unverified","dedicated_action_unavailable"}
    assert len(result.attrs["action_audit"]) == 2


@pytest.mark.parametrize("ratio", [0.1,1.5,2.0,10.0])
def test_split_reverse_split_bonus_equivalent_counted_once(ratio):
    midnight = pd.Timestamp("2025-06-02",tz="Europe/Berlin")
    history = pd.DataFrame({"Close":[100.],"Dividends":[0.],"Stock Splits":[ratio]},index=[midnight])
    normalized,_ = _normalize_history_index(history)
    obj = SimpleNamespace(dividends=pd.Series(dtype=float),splits=pd.Series([ratio],index=[midnight+pd.Timedelta(hours=9)]))
    result,_ = _merge_dedicated_action_series(normalized,obj)
    assert result['Stock Splits'].tolist() == [ratio]
    assert result.attrs['action_audit'][-1]['decision'] == 'cross_source_confirmed_once'


def test_dividend_conflict_is_visible_in_ui_and_both_reports(monkeypatch,synthetic_result):
    from streamlit.testing.v1 import AppTest
    from src.financial_models import FundamentalsResult
    from src.exports import report_html,combined_research_html
    import src.service as service
    import src.research_service as research
    synthetic_result.ticker = synthetic_result.metadata.ticker = 'DIVTEST'
    synthetic_result.validation.loc[len(synthetic_result.validation)] = {
        'severity':'ERROR','check':'dividend_external_reference','date':pd.NaT,
        'message':'Independent issuer mismatch — inspect source evidence.'}
    monkeypatch.setattr(service,'run_equity_analysis',lambda *args,**kwargs:synthetic_result)
    monkeypatch.setattr(research,'run_fundamentals_analysis',lambda *args,**kwargs:FundamentalsResult('DIVTEST','UNAVAILABLE','Offline test'))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
    app.text_input[0].set_value('DIVTEST')
    next(button for button in app.button if button.label=='ANALYZE').click().run()
    next(control for control in app.get('button_group') if control.label=='Analytical workspace').set_value('Dividends & Total Return').run()
    assert not app.exception
    assert any('Dividend/action source validation needs review' in warning.value for warning in app.warning)
    for payload in [report_html(synthetic_result,'dividend'),combined_research_html(synthetic_result)]:
        assert b'Independent issuer mismatch' in payload


def test_hot_reload_invalidates_legacy_session_results_and_downloads(synthetic_result):
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
    app.session_state['analysis_result']=synthetic_result
    app.session_state['action_data_version']='legacy-utc-dates'
    app.session_state['prepared_download']='stale export'
    app.run()
    assert not app.exception
    assert app.session_state['analysis_result'] is None
    assert app.session_state['prepared_download'] is None
    assert app.session_state['action_data_version'] == ACTION_DATA_VERSION
    assert any('Run ANALYZE again' in info.value for info in app.info)
