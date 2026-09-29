import ast
from pathlib import Path
from types import SimpleNamespace

from src.formatting import format_percent
from src.ui import active_theme_type, dividend_kpi_cards, kpi_grid_html, visual_css


ROOT = Path(__file__).resolve().parents[1]


def test_native_dark_and_light_theme_configuration():
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'base = "dark"' in config
    assert "[theme.dark]" in config
    assert "[theme.light]" in config
    assert "[theme.dark.sidebar]" in config
    assert "[theme.light.sidebar]" in config
    assert '#060913' in config and '#F4F7FC' in config


def test_active_native_theme_resolution_and_safe_default():
    dark = SimpleNamespace(theme=SimpleNamespace(type="dark"))
    light = SimpleNamespace(theme=SimpleNamespace(type="light"))
    unavailable = SimpleNamespace()
    assert active_theme_type(dark) == "dark"
    assert active_theme_type(light) == "light"
    assert active_theme_type(unavailable) == "dark"
    assert "#F7FBFF" in visual_css("dark")
    assert "#172033" in visual_css("light")


def test_dividend_growth_kpi_reuses_validated_metric(synthetic_result):
    cards = dividend_kpi_cards(synthetic_result)
    by_label = {card.label: card.value for card in cards}
    expected = format_percent(synthetic_result.dividend_metrics["dividend_growth_1y"])
    assert by_label["Latest annual dividend growth"] == expected
    assert {"3Y dividend CAGR", "5Y dividend CAGR", "10Y dividend CAGR"} <= set(by_label)
    assert "Dividend-paying streak" in by_label
    assert "LATEST ANNUAL DIVIDEND GROWTH" in kpi_grid_html(cards)


def test_app_uses_transient_progress_native_theme_and_lazy_workspace_flow():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'st.radio("Theme"' not in source
    assert "st.status(" not in source
    assert "st.spinner(" in source and "st.toast(" in source
    assert "active_theme_type()" in source
    assert "render_downloads_popover" in source
    assert 'with st.expander("Downloads"' not in source
    assert "No cash-dividend history found" in source

    tree = ast.parse(source)
    analyze_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "analyze"
    ]
    assert len(analyze_calls) == 1
    guarded = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "analyze_clicked"
    ]
    assert len(guarded) == 1
    assert analyze_calls[0] in list(ast.walk(guarded[0]))
