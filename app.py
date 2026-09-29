"""Streamlit entry point for Equity Lifetime Explorer."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src.charts import build_dividend_chart, build_lifetime_chart, build_volume_chart
from src.charts.dividends import dividend_summary_display
from src.charts.volume import notable_volume_events
from src.downloads import (
    DATA_EXPORTS,
    REPORT_EXPORTS,
    default_export_selection,
    export_is_available,
    prepare_complete_package,
    prepare_selected_download,
)
from src.providers.yahoo import clean_ticker
from src.service import run_equity_analysis
from src.ui import (
    active_theme_type,
    company_hero_html,
    dividend_kpi_cards,
    dividend_secondary_facts,
    kpi_grid_html,
    lifetime_kpi_cards,
    secondary_facts_html,
    visual_css,
    volume_kpi_cards,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

st.set_page_config(
    page_title="Equity Lifetime Explorer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

active_theme = active_theme_type()
st.markdown(
    f"<style>{visual_css(active_theme)}</style>",
    unsafe_allow_html=True,
)


@st.cache_data(ttl="12h", max_entries=32, show_spinner=False)
def cached_analysis(ticker: str):
    """Cache one canonical result per normalized ticker across UI-only reruns."""
    return run_equity_analysis(ticker, force_refresh=False, cache_hours=12.0)


def analyze(ticker: str, force_refresh: bool):
    symbol, _ = clean_ticker(ticker)
    if force_refresh:
        cached_analysis.clear(symbol)
        return run_equity_analysis(symbol, force_refresh=True, cache_hours=12.0)
    return cached_analysis(symbol)


def render_company_header(result) -> None:
    st.markdown(company_hero_html(result), unsafe_allow_html=True)
    st.markdown(kpi_grid_html(lifetime_kpi_cards(result)), unsafe_allow_html=True)


def render_price_workspace(result, controls: dict) -> None:
    st.subheader("Price & Ownership")
    st.caption("Raw market quotations, provider-adjusted history, and the mechanical ownership-equivalent reconstruction.")
    figure = build_lifetime_chart(
        result,
        price_mode=controls["price_mode"],
        default_scale=controls["price_scale"],
        theme=controls["theme"],
        show_splits=controls["show_splits"],
        show_dividends=controls["show_dividends"],
        show_volume=controls["show_volume"],
        show_drawdown=controls["show_drawdown"],
    )
    st.plotly_chart(figure, width="stretch", theme=None, config={"displaylogo": False, "responsive": True})
    factor = result.metrics["cumulative_share_multiplier"]
    if abs(factor - 1.0) < 1e-10:
        ownership = "No included share-changing action alters the earliest-observation share basis."
    else:
        ownership = f"One share at the earliest provider observation represents {factor:,.6g} current shares after included recorded actions."
    st.info(f"**Ownership-equivalent statement:** {ownership} This is a mechanical reconstruction, not a counterfactual market-price forecast.")


def render_volume_workspace(result, theme: str) -> None:
    st.subheader("Volume & Liquidity")
    if not result.metrics.get("volume_data_available"):
        st.info("Volume data are unavailable from the configured provider.")
        return
    mode_label = st.segmented_control(
        "Volume display",
        ["Share Volume", "Dollar Volume"],
        default="Share Volume",
        key="volume_mode",
    )
    mode = "dollar" if mode_label == "Dollar Volume" else "shares"
    st.markdown(kpi_grid_html(volume_kpi_cards(result)), unsafe_allow_html=True)
    figure = build_volume_chart(result, theme=theme, mode=mode)
    st.plotly_chart(figure, width="stretch", theme=None, config={"displaylogo": False, "responsive": True})
    st.markdown("#### Notable Volume Events")
    events = notable_volume_events(result, top_n=10)
    if events.empty:
        st.caption("No relative-volume events have sufficient lookback history.")
    else:
        st.dataframe(events, width="stretch", hide_index=True)
    st.caption(
        "High volume indicates elevated market participation. It does not identify institutions, retail investors, "
        "or another participant class, and it does not establish accumulation, distribution, or causation."
    )


def render_dividend_workspace(result, theme: str) -> None:
    st.subheader("Dividends & Total Return")
    if result.dividend_status == "NONE":
        st.info(
            "**No cash-dividend history found**\n\n"
            "No positive cash-dividend history is available from the configured market-data provider for this security. "
            "Price, corporate-action and liquidity analysis remain fully available in the other workspaces."
        )
        return
    scale_label = st.segmented_control(
        "Wealth-chart scale", ["Log", "Linear"], default="Log", key="dividend_scale"
    )
    st.markdown(kpi_grid_html(dividend_kpi_cards(result)), unsafe_allow_html=True)
    st.markdown(
        secondary_facts_html(dividend_secondary_facts(result)),
        unsafe_allow_html=True,
    )
    figure = build_dividend_chart(result, theme=theme, wealth_scale=scale_label.lower())
    st.plotly_chart(figure, width="stretch", theme=None, config={"displaylogo": False, "responsive": True})
    st.markdown("#### Annual Dividend Summary")
    st.dataframe(dividend_summary_display(result).tail(15), width="stretch", hide_index=True)
    st.caption(
        "Provider-reported historical dividends may be retrospectively normalized for later splits. "
        "Adjusted Close is used only when genuinely supplied, as a pre-tax and pre-fee total-return proxy."
    )


def render_audit_sections(result) -> None:
    with st.expander("Corporate Action Ledger", expanded=False):
        columns = [
            "date", "event", "ratio", "share_multiplier", "cumulative_multiplier",
            "source", "confidence", "included_in_reconstruction", "notes",
        ]
        st.dataframe(result.actions[columns], width="stretch", hide_index=True)
    with st.expander("Data Quality & Validation", expanded=False):
        st.markdown(f"**Overall confidence: {result.provenance.validation_status}**")
        st.dataframe(result.validation, width="stretch", hide_index=True)
    with st.expander("Data & Methodology", expanded=False):
        provenance = result.provenance
        details = pd.DataFrame(
            [
                ("Primary provider", provenance.provider),
                ("Retrieval timestamp", provenance.retrieval_timestamp_utc),
                ("First observation", provenance.first_available_observation),
                ("Latest observation", provenance.last_available_observation),
                ("Observations", f"{len(result.prices):,}"),
                ("Corporate-action records", f"{len(result.actions):,}"),
                ("Positive dividend events", f"{result.dividend_metrics.get('dividend_event_count', 0):,}"),
                ("Data-quality confidence", provenance.validation_status),
            ],
            columns=["Field", "Value"],
        )
        st.dataframe(details, width="stretch", hide_index=True)
        st.markdown(result.methodology)
        if provenance.notes:
            st.markdown("**Provider notes**")
            for note in provenance.notes:
                st.markdown(f"- {note}")


def _price_export_options(controls: dict) -> dict:
    return {
        "price_mode": controls["price_mode"],
        "default_scale": controls["price_scale"],
        "show_splits": controls["show_splits"],
        "show_dividends": controls["show_dividends"],
        "show_volume": controls["show_volume"],
        "show_drawdown": controls["show_drawdown"],
    }


@st.dialog("Download Center", width="large")
def render_download_center(result, controls: dict) -> None:
    st.caption("Choose focused reports or research data. Nothing is generated until you request it.")
    defaults = default_export_selection(result)
    with st.form("download_selection_form", border=False):
        report_column, data_column = st.columns(2)
        choices: dict[str, bool] = {}
        with report_column:
            st.markdown("#### Reports")
            for key, label in REPORT_EXPORTS:
                available = export_is_available(result, key)
                choices[key] = st.checkbox(
                    label,
                    value=defaults[key],
                    disabled=not available,
                    key=f"export_choice_{key}",
                    help=None if available else "Unavailable because this security has no provider-reported cash-dividend history.",
                )
        with data_column:
            st.markdown("#### Data")
            for key, label in DATA_EXPORTS:
                available = export_is_available(result, key)
                choices[key] = st.checkbox(
                    label,
                    value=defaults[key],
                    disabled=not available,
                    key=f"export_choice_{key}",
                    help=None if available else "Unavailable because this security has no provider-reported cash-dividend history.",
                )
        st.markdown("#### Options")
        portable = st.checkbox(
            "Portable self-contained HTML",
            value=False,
            key="portable_export_html",
            help="Portable HTML embeds Plotly JavaScript and is larger. Standard HTML uses the Plotly CDN and is smaller.",
        )
        st.caption("Portable HTML embeds Plotly JavaScript and is larger. Standard HTML uses the Plotly CDN and is smaller.")
        prepare_selected = st.form_submit_button(
            "PREPARE SELECTED DOWNLOADS",
            type="primary",
            width="stretch",
        )
        st.divider()
        st.markdown("#### Download Complete Analysis Package")
        st.caption("Creates one ZIP containing every applicable specialist report, the combined report, and all research data.")
        prepare_complete = st.form_submit_button(
            "PREPARE COMPLETE ANALYSIS PACKAGE",
            width="stretch",
        )

    price_options = _price_export_options(controls)
    if prepare_selected:
        selected = [key for key, enabled in choices.items() if enabled and export_is_available(result, key)]
        if not selected:
            st.warning("Select at least one report or data export.")
        else:
            with st.spinner("Preparing selected exports…"):
                st.session_state.prepared_download = prepare_selected_download(
                    result,
                    selected,
                    theme=controls["theme"],
                    portable_html=portable,
                    price_options=price_options,
                )
                st.session_state.prepared_export_ticker = result.ticker

    if prepare_complete:
        with st.spinner("Building the complete analysis package…"):
            st.session_state.prepared_download = prepare_complete_package(
                result,
                theme=controls["theme"],
                portable_html=portable,
                price_options=price_options,
            )
            st.session_state.prepared_export_ticker = result.ticker

    prepared = st.session_state.get("prepared_download")
    if st.session_state.get("prepared_export_ticker") != result.ticker:
        prepared = None
    if prepared is not None:
        st.success(prepared.status)
        st.download_button(
            f"DOWNLOAD {prepared.filename}",
            data=prepared.payload,
            file_name=prepared.filename,
            mime=prepared.mime,
            key=f"download_{prepared.filename}",
            type="primary",
            width="stretch",
        )


with st.sidebar:
    st.title("Equity Lifetime Explorer")
    st.caption("Price History · Corporate Actions · Liquidity · Dividends")
    ticker = st.text_input("Ticker", value="KO", max_chars=25, placeholder="NVDA, SAP.DE, RELIANCE.NS")
    st.caption("Examples: NVDA · AAPL · MSFT · GOOG · AMZN · SAP.DE · ASML · RELIANCE.NS")
    price_label = st.selectbox("Price view", ["No-Split Equivalent", "Raw As-Traded", "Provider Adjusted", "Overlay"])
    scale_label = st.radio("Price scale", ["Log", "Linear"], horizontal=True)
    st.markdown("**Chart components**")
    show_splits = st.checkbox("Corporate actions", value=True)
    show_dividends = st.checkbox("Dividend markers", value=True)
    show_volume = st.checkbox("Compact volume", value=True)
    show_drawdown = st.checkbox("Drawdown", value=True)
    force_refresh = st.checkbox("Force fresh retrieval", value=False)
    analyze_clicked = st.button("ANALYZE", type="primary", width="stretch")
    st.caption("Appearance can be changed from Streamlit Settings.")

price_modes = {
    "No-Split Equivalent": "no_split", "Raw As-Traded": "raw",
    "Provider Adjusted": "adjusted", "Overlay": "overlay",
}
controls = {
    "theme": active_theme, "price_mode": price_modes[price_label],
    "price_scale": scale_label.lower(), "show_splits": show_splits,
    "show_dividends": show_dividends, "show_volume": show_volume,
    "show_drawdown": show_drawdown,
}

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if analyze_clicked:
    try:
        clean_ticker(ticker)
        with st.spinner("Retrieving and analyzing maximum available market history…", show_time=True):
            result = analyze(ticker, force_refresh)
            st.session_state.analysis_result = result
            st.session_state.prepared_download = None
            st.session_state.prepared_export_ticker = None
        st.toast(f"{result.metadata.ticker} analysis complete", icon="✅")
    except ValueError as exc:
        st.error(f"Invalid ticker: {exc}")
    except LookupError:
        st.error("No market history was found for this symbol. Please check the ticker and exchange suffix.")
    except Exception:
        logging.getLogger("equity_lifetime_explorer").exception("Analysis failed")
        st.error("Market data could not be retrieved or processed at this time. Please retry shortly.")

result = st.session_state.analysis_result
if result is None:
    st.title("Equity Lifetime Explorer")
    st.markdown("### Long-horizon price, ownership, liquidity, and dividend research")
    st.write("Enter a Yahoo Finance symbol in the sidebar and click **ANALYZE**.")
    st.info("Try **KO** for long dividend history, **NVDA** for multiple splits, **GOOG** for limited dividend history, or **SAP.DE** for EUR-denominated data.")
    st.stop()

render_company_header(result)
navigation, downloads = st.columns([5.4, 1], vertical_alignment="bottom")
with navigation:
    workspace = st.segmented_control(
        "Analytical workspace",
        ["Price & Ownership", "Volume & Liquidity", "Dividends & Total Return"],
        default="Price & Ownership",
        key="workspace",
        width="stretch",
    )
with downloads:
    if st.button("Downloads", icon=":material/download:", width="stretch"):
        render_download_center(result, controls)

with st.container(border=True):
    if workspace == "Price & Ownership":
        render_price_workspace(result, controls)
    elif workspace == "Volume & Liquidity":
        render_volume_workspace(result, controls["theme"])
    else:
        render_dividend_workspace(result, controls["theme"])

render_audit_sections(result)
st.caption(
    "For informational and research purposes only. Market data may be delayed, incomplete, or retrospectively adjusted by the provider."
)
