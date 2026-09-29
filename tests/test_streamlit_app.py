from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

import src.service as service


APP = Path(__file__).resolve().parents[1] / "app.py"


def test_workspace_switching_reuses_completed_analysis(monkeypatch, synthetic_result):
    calls: list[str] = []

    def fake_analysis(ticker: str, **_kwargs):
        calls.append(ticker)
        return synthetic_result

    monkeypatch.setattr(service, "run_equity_analysis", fake_analysis)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.text_input[0].set_value("UITEST")
    app.button[0].click().run()
    assert not app.exception
    assert calls == ["UITEST"]
    assert not app.get("status")
    next(control for control in app.radio if control.label == "PRICE VIEW").set_value("Overlay").run()
    assert calls == ["UITEST"]

    workspace = app.get("button_group")[0]
    workspace.set_value("Volume & Liquidity").run()
    assert calls == ["UITEST"]
    assert [heading.value for heading in app.subheader] == ["Volume & Liquidity"]

    app.get("button_group")[0].set_value("Dividends & Total Return").run()
    assert calls == ["UITEST"]
    assert [heading.value for heading in app.subheader] == ["Dividends & Total Return"]
    next(
        control for control in app.get("button_group") if control.label == "Dividend horizon"
    ).set_value("10Y").run()
    assert calls == ["UITEST"]


def test_no_dividend_workspace_is_graceful(synthetic_result):
    no_dividend = copy.deepcopy(synthetic_result)
    no_dividend.dividend_status = "NONE"
    no_dividend.dividend_events = pd.DataFrame()
    no_dividend.annual_dividends = pd.DataFrame()
    no_dividend.dividend_metrics = {}

    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["analysis_result"] = no_dividend
    app.run()
    app.get("button_group")[0].set_value("Dividends & Total Return").run()
    assert not app.exception
    assert any("No cash-dividend history found" in message.value for message in app.info)
    next(button for button in app.button if button.label == "Downloads").click().run()
    choices = {checkbox.label: checkbox for checkbox in app.checkbox}
    assert choices["Dividends & Total Return HTML"].disabled is True
    assert choices["Dividend Annual Summary CSV"].disabled is True


def test_download_center_selection_reuses_analysis(monkeypatch, synthetic_result):
    calls: list[str] = []

    def fake_analysis(ticker: str, **_kwargs):
        calls.append(ticker)
        return synthetic_result

    monkeypatch.setattr(service, "run_equity_analysis", fake_analysis)
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.text_input[0].set_value("DOWNLOADTEST")
    app.button[0].click().run()
    assert calls == ["DOWNLOADTEST"]

    next(button for button in app.button if button.label == "Downloads").click().run()
    assert calls == ["DOWNLOADTEST"]
    assert not app.get("multiselect")
    assert len(app.get("form")) == 1
    choices = {checkbox.label: checkbox for checkbox in app.checkbox}
    assert choices["Price & Ownership HTML"].value is True
    assert choices["Full Historical Data CSV"].value is False
    choices["Full Historical Data CSV"].set_value(True)
    assert calls == ["DOWNLOADTEST"]
