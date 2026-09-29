import pandas as pd

from src.charts import build_dividend_chart, build_lifetime_chart, build_volume_chart
from src.charts.common import display_result


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


def test_display_downsampling_preserves_canonical_data_and_events(synthetic_result):
    original_count = len(synthetic_result.prices)
    displayed = display_result(synthetic_result, max_points=200)
    assert len(synthetic_result.prices) == original_count
    assert len(displayed.prices) <= 220
    action_dates = set(pd.to_datetime(synthetic_result.actions["date"]))
    assert action_dates <= set(displayed.prices.index)
