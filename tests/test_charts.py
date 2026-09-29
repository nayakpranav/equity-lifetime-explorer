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


def test_display_downsampling_preserves_canonical_data_and_events(synthetic_result):
    original_count = len(synthetic_result.prices)
    displayed = display_result(synthetic_result, max_points=200)
    assert len(synthetic_result.prices) == original_count
    assert len(displayed.prices) <= 220
    action_dates = set(pd.to_datetime(synthetic_result.actions["date"]))
    assert action_dates <= set(displayed.prices.index)
