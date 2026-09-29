"""Streamlit entry point for Equity Lifetime Explorer."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import streamlit as st

from src.charts import build_dividend_chart, build_lifetime_chart, build_volume_chart
from src.charts.dividends import dividend_summary_display
from src.charts.volume import notable_volume_events
from src.exports import export_bundle, safe_ticker, zip_bytes
from src.formatting import format_money, format_multiple, format_percent, format_quantity
from src.providers.yahoo import clean_ticker
from src.service import run_equity_analysis


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

st.set_page_config(
    page_title="Equity Lifetime Explorer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1600px;}
    [data-testid="stMetric"] {border: 1px solid rgba(120,135,155,.28); border-radius: .55rem; padding: .7rem .85rem;}
    [data-testid="stSidebar"] h1 {font-size: 1.18rem; letter-spacing: .03em;}
    .ele-kicker {letter-spacing:.09em;text-transform:uppercase;font-size:.78rem;color:#718096;font-weight:700}
    .ele-subtle {color:#718096;font-size:.92rem}
    </style>
    """,
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


def metric(value, fallback: str = "N/A") -> str:
    return fallback if value is None or pd.isna(value) else str(value)


def render_company_header(result) -> None:
    metadata = result.metadata
    details = [metadata.ticker, metadata.exchange, metadata.currency]
    if metadata.sector:
        details.append(metadata.sector)
    st.markdown('<div class="ele-kicker">Equity Lifetime Explorer</div>', unsafe_allow_html=True)
    st.title(metadata.name)
    st.markdown(" · ".join(details))
    values = result.metrics
    columns = st.columns(6)
    cards = [
        ("Latest price", format_money(values.get("latest_raw_close"), metadata.currency)),
        ("No-split equivalent", format_money(values.get("latest_no_split_equivalent"), metadata.currency, compact=True)),
        ("Lifetime multiple", format_multiple(values.get("lifetime_price_multiple"))),
        ("Lifetime CAGR", format_percent(values.get("lifetime_cagr"))),
        ("Share multiplier", format_multiple(values.get("cumulative_share_multiplier"))),
        ("Max drawdown", format_percent(values.get("maximum_drawdown"))),
    ]
    for column, (label, value) in zip(columns, cards):
        column.metric(label, value)
    if result.dividend_status != "NONE":
        dividend = result.dividend_metrics
        columns = st.columns(4)
        dividend_cards = [
            ("TTM dividend", format_money(dividend.get("ttm_dividend"), metadata.currency)),
            ("TTM yield", format_percent(dividend.get("current_ttm_dividend_yield"), 2)),
            ("5Y dividend CAGR", format_percent(dividend.get("dividend_cagr_5y"))),
            ("Dividend-paying streak", f"{dividend.get('dividend_paying_streak', 0)} years"),
        ]
        for column, (label, value) in zip(columns, dividend_cards):
            column.metric(label, value)


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
    metrics = result.metrics
    columns = st.columns(4)
    cards = [
        ("Latest volume", format_quantity(metrics.get("latest_volume"))),
        ("Previous 20D average", format_quantity(metrics.get("volume_ma_20"))),
        ("Latest RVOL", format_multiple(metrics.get("latest_relative_volume_20"))),
        ("Latest dollar volume", format_money(metrics.get("latest_dollar_volume"), result.metadata.currency, compact=True)),
    ]
    for column, (label, value) in zip(columns, cards):
        column.metric(label, value)
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
    dividend = result.dividend_metrics
    columns = st.columns(6)
    cards = [
        ("TTM dividend", format_money(dividend.get("ttm_dividend"), result.metadata.currency)),
        ("TTM yield", format_percent(dividend.get("current_ttm_dividend_yield"), 2)),
        ("3Y CAGR", format_percent(dividend.get("dividend_cagr_3y"))),
        ("5Y CAGR", format_percent(dividend.get("dividend_cagr_5y"))),
        ("10Y CAGR", format_percent(dividend.get("dividend_cagr_10y"))),
        ("Paying streak", f"{dividend.get('dividend_paying_streak', 0)} years"),
    ]
    for column, (label, value) in zip(columns, cards):
        column.metric(label, value)
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


EXPORT_LABELS = {
    "lifetime_html": "Lifetime Explorer HTML",
    "volume_html": "Volume & Liquidity HTML",
    "dividend_html": "Dividend & Total Return HTML",
    "history_csv": "Historical Data CSV",
    "actions_csv": "Corporate Actions CSV",
    "dividend_csv": "Dividend Annual Summary CSV",
    "validation_csv": "Validation CSV",
}


def render_downloads(result, controls: dict) -> None:
    with st.expander("Downloads", expanded=False):
        st.caption("Exports are generated in memory only when requested. CDN-backed HTML is smaller; portable HTML embeds Plotly JavaScript.")
        available = ["lifetime_html", "volume_html", "history_csv", "actions_csv", "validation_csv"]
        if result.dividend_status != "NONE":
            available.extend(["dividend_html", "dividend_csv"])
        selected = st.multiselect(
            "Select reports and data",
            available,
            default=["lifetime_html", "history_csv"],
            format_func=lambda key: EXPORT_LABELS[key],
        )
        portable = st.checkbox("Portable self-contained HTML", value=False, help="Larger files that work without loading Plotly from a CDN.")
        first, second = st.columns(2)
        if first.button("Prepare selected downloads", type="primary", disabled=not selected, width="stretch"):
            with st.spinner("Generating selected exports…"):
                st.session_state.prepared_exports = export_bundle(
                    result,
                    selected,
                    theme=controls["theme"],
                    portable_html=portable,
                    price_options={
                        "price_mode": controls["price_mode"], "default_scale": controls["price_scale"],
                        "show_splits": controls["show_splits"], "show_dividends": controls["show_dividends"],
                        "show_volume": controls["show_volume"], "show_drawdown": controls["show_drawdown"],
                    },
                )
                st.session_state.prepared_export_ticker = result.ticker
        if second.button("Prepare complete analysis ZIP", width="stretch"):
            with st.spinner("Building the complete analysis package…"):
                package_keys = list(available)
                files = export_bundle(result, package_keys, theme=controls["theme"], portable_html=portable)
                stamp = date.today().isoformat()
                filename = f"{safe_ticker(result.ticker)}_Equity_Lifetime_Explorer_{stamp}.zip"
                st.session_state.prepared_exports = {filename: zip_bytes(files)}
                st.session_state.prepared_export_ticker = result.ticker
        prepared = st.session_state.get("prepared_exports", {})
        if st.session_state.get("prepared_export_ticker") != result.ticker:
            prepared = {}
        if prepared:
            st.success(f"{len(prepared)} download{'s' if len(prepared) != 1 else ''} ready.")
            for filename, payload in prepared.items():
                mime = "application/zip" if filename.endswith(".zip") else (
                    "text/html" if filename.endswith(".html") else "text/csv"
                )
                st.download_button(
                    f"Download {filename}", data=payload, file_name=filename, mime=mime,
                    key=f"download_{filename}", width="stretch",
                )


with st.sidebar:
    st.title("Equity Lifetime Explorer")
    st.caption("Price History · Corporate Actions · Liquidity · Dividends")
    ticker = st.text_input("Ticker", value="KO", max_chars=25, placeholder="NVDA, SAP.DE, RELIANCE.NS")
    st.caption("Examples: NVDA · AAPL · MSFT · GOOG · AMZN · SAP.DE · ASML · RELIANCE.NS")
    theme_label = st.radio("Theme", ["Dark", "Light"], horizontal=True)
    price_label = st.selectbox("Price view", ["No-Split Equivalent", "Raw As-Traded", "Provider Adjusted", "Overlay"])
    scale_label = st.radio("Price scale", ["Log", "Linear"], horizontal=True)
    st.markdown("**Chart components**")
    show_splits = st.checkbox("Corporate actions", value=True)
    show_dividends = st.checkbox("Dividend markers", value=True)
    show_volume = st.checkbox("Compact volume", value=True)
    show_drawdown = st.checkbox("Drawdown", value=True)
    force_refresh = st.checkbox("Force fresh retrieval", value=False)
    analyze_clicked = st.button("ANALYZE", type="primary", width="stretch")

price_modes = {
    "No-Split Equivalent": "no_split", "Raw As-Traded": "raw",
    "Provider Adjusted": "adjusted", "Overlay": "overlay",
}
controls = {
    "theme": theme_label.lower(), "price_mode": price_modes[price_label],
    "price_scale": scale_label.lower(), "show_splits": show_splits,
    "show_dividends": show_dividends, "show_volume": show_volume,
    "show_drawdown": show_drawdown,
}

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if analyze_clicked:
    try:
        clean_ticker(ticker)
        with st.status("Analyzing lifetime history…", expanded=True) as status:
            st.write("Retrieving maximum available market history…")
            result = analyze(ticker, force_refresh)
            st.write("Corporate actions, reconstruction, analytics and validation complete.")
            st.session_state.analysis_result = result
            st.session_state.prepared_exports = {}
            st.session_state.prepared_export_ticker = None
            status.update(label=f"{result.metadata.name} analysis complete", state="complete", expanded=False)
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
workspace = st.segmented_control(
    "Analytical workspace",
    ["Price & Ownership", "Volume & Liquidity", "Dividends & Total Return"],
    default="Price & Ownership",
    key="workspace",
    width="stretch",
)
if workspace == "Price & Ownership":
    render_price_workspace(result, controls)
elif workspace == "Volume & Liquidity":
    render_volume_workspace(result, controls["theme"])
else:
    render_dividend_workspace(result, controls["theme"])

render_audit_sections(result)
render_downloads(result, controls)
st.caption(
    "For informational and research purposes only. Market data may be delayed, incomplete, or retrospectively adjusted by the provider."
)
