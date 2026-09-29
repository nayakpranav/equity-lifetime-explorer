import copy

import numpy as np
import pandas as pd

from src.charts import build_dividend_chart, build_lifetime_chart, build_volume_chart
from src.charts.common import display_result
from src.charts.dividends import dividend_display_result
from src.charts.volume import _rvol_axis_upper


def _long_dividend_result(synthetic_result):
    result = copy.deepcopy(synthetic_result)
    price_rows = []
    annual_rows = []
    event_rows = []
    for year in range(2010, 2022):
        price_row = result.prices.iloc[[0]].copy()
        price_row.index = pd.DatetimeIndex([pd.Timestamp(year, 12, 31)])
        price_rows.append(price_row)
        annual_row = result.annual_dividends.iloc[[0]].copy()
        annual_row.loc[:, "year"] = year
        annual_row.loc[:, "year_label"] = str(year)
        annual_row.loc[:, "annual_dividend"] = 0.5 + (year - 2010) * 0.03
        annual_row.loc[:, "yoy_growth"] = np.nan if year == 2010 else 0.04
        annual_rows.append(annual_row)
        event_row = result.dividend_events.iloc[[0]].copy()
        event_row.loc[:, "date"] = pd.Timestamp(year, 3, 15)
        event_row.loc[:, "calendar_year"] = year
        event_rows.append(event_row)
    result.prices = pd.concat([*price_rows, result.prices]).sort_index()
    result.annual_dividends = pd.concat([*annual_rows, result.annual_dividends], ignore_index=True)
    result.dividend_events = pd.concat([*event_rows, result.dividend_events], ignore_index=True)
    return result


def test_themes_native_controls_and_three_workspaces(synthetic_result):
    for theme in ("dark", "light"):
        lifetime = build_lifetime_chart(synthetic_result, theme=theme)
        volume = build_volume_chart(synthetic_result, theme=theme, mode="dollar")
        dividend = build_dividend_chart(synthetic_result, theme=theme, wealth_scale="linear")
        assert not lifetime.layout.updatemenus
        assert not volume.layout.updatemenus
        assert not dividend.layout.updatemenus
        assert lifetime.layout.paper_bgcolor
        assert volume.layout.yaxis2.title.text == "Dollar Volume (EUR)"
        assert dividend.layout.yaxis5.type == "linear"
        assert lifetime.layout.template.layout.paper_bgcolor
        assert volume.layout.template.layout.paper_bgcolor
        assert dividend.layout.template.layout.paper_bgcolor


def test_dividend_legend_band_and_compact_labels(synthetic_result):
    figure = build_dividend_chart(synthetic_result, theme="dark")
    names = {trace.name for trace in figure.data if trace.name}
    assert {
        "Annual DPS", "YoY Growth", "TTM DPS", "TTM Yield",
        "Price Only", "Total Return",
    } <= names
    assert names <= {
        "Annual DPS", "Current YTD", "YoY Growth", "TTM DPS",
        "TTM Yield", "Price Only", "Total Return", "Dividend Calendar",
    }
    assert figure.layout.legend.orientation == "h"
    assert figure.layout.legend.y > 1
    assert figure.layout.margin.t >= 120
    titles = {annotation.text for annotation in figure.layout.annotations}
    assert {
        "Annual Dividends & Growth",
        "TTM Dividend & Historical Yield",
        "10,000 Price vs Total Return",
        "Dividend Calendar Heatmap",
    } <= titles


def test_dividend_annual_bar_dates_use_year_end_and_latest_observation(synthetic_result):
    result = copy.deepcopy(synthetic_result)
    latest_observation = pd.Timestamp("2025-10-17")
    result.prices = result.prices.loc[result.prices.index <= latest_observation].copy()

    current_year = int(result.annual_dividends["year"].max())
    current_mask = result.annual_dividends["year"].eq(current_year)
    result.annual_dividends.loc[current_mask, "completed_year"] = False
    result.annual_dividends.loc[current_mask, "ytd"] = True
    result.annual_dividends.loc[current_mask, "year_label"] = f"{current_year} YTD"

    figure = build_dividend_chart(result, theme="dark")
    traces = {trace.name: trace for trace in figure.data if trace.name}
    completed_dates = pd.DatetimeIndex(pd.to_datetime(traces["Annual DPS"].x))
    ytd_dates = pd.DatetimeIndex(pd.to_datetime(traces["Current YTD"].x))

    assert all((date.month, date.day) == (12, 31) for date in completed_dates)
    assert list(ytd_dates) == [result.prices.index.max()]
    assert ytd_dates[0] != pd.Timestamp(f"{current_year}-12-31")
    assert figure.layout.xaxis.tickformat == "%Y"


def test_dividend_horizon_filters_all_visual_sections(synthetic_result):
    result = _long_dividend_result(synthetic_result)
    full = dividend_display_result(result, "MAX")
    ten_year = dividend_display_result(result, "10Y")
    start = result.prices.index.max() - pd.DateOffset(years=10)
    assert len(full.prices) == len(result.prices)
    assert full.annual_dividends["year"].min() == 2010
    assert ten_year.prices.index.min() >= start
    assert ten_year.annual_dividends["year"].min() >= start.year
    assert pd.to_datetime(ten_year.dividend_events["date"]).min() >= start

    figure = build_dividend_chart(result, theme="dark", horizon="10Y")
    traces = {trace.name: trace for trace in figure.data if trace.name}
    assert pd.to_datetime(traces["Annual DPS"].x).min().year >= start.year
    assert pd.to_datetime(traces["TTM DPS"].x).min() >= start
    assert pd.to_datetime(traces["Price Only"].x).min() >= start
    assert min(int(year) for year in traces["Dividend Calendar"].y) >= start.year
    assert not figure.layout.xaxis3.rangeselector.buttons


def test_rvol_axis_has_dynamic_headroom_and_panel_gap(synthetic_result):
    values = pd.Series([np.nan, np.inf, 1.0, 8.0])
    assert _rvol_axis_upper(values) > 8.0
    assert _rvol_axis_upper(pd.Series([np.nan, np.inf])) == 2.2
    figure = build_volume_chart(synthetic_result, theme="dark")
    finite = pd.to_numeric(
        synthetic_result.prices["relative_volume_20"], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan).dropna()
    assert figure.layout.yaxis3.range[1] > finite.max()
    assert figure.layout.yaxis2.domain[0] - figure.layout.yaxis3.domain[1] >= 0.055


def test_display_downsampling_preserves_canonical_data_and_events(synthetic_result):
    original_count = len(synthetic_result.prices)
    displayed = display_result(synthetic_result, max_points=200)
    assert len(synthetic_result.prices) == original_count
    assert len(displayed.prices) <= 220
    action_dates = set(pd.to_datetime(synthetic_result.actions["date"]))
    assert action_dates <= set(displayed.prices.index)
