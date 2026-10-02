"""Financial Fundamentals workspace, rendered from the in-memory SEC snapshot."""

from __future__ import annotations

import streamlit as st

from ..charts.fundamentals import build_fundamentals_figures
from ..financial_models import FundamentalsResult
from ..financial_ui import fundamentals_kpi_cards
from ..ui import kpi_grid_html


def render_fundamentals_workspace(result: FundamentalsResult, *, theme: str) -> None:
    st.subheader("Financial Fundamentals")
    st.caption("Operating performance, cash generation and financial position from SEC filings.")
    if not result.available:
        st.info(result.reason or f"Financial Fundamentals are unavailable ({result.status}).")
        st.caption(f"Status: {result.status}. Price, volume and dividend analysis remain available.")
        return
    identity = result.identity
    st.caption(
        f"Source: {result.source} · {identity.issuer_name} · CIK {identity.cik} · "
        f"Reporting currency {identity.reporting_currency} · {result.latest_view} · "
        f"latest annual fiscal end {result.annual.iloc[-1]['period_end']}"
    )
    if result.status == "PARTIAL":
        st.warning(result.reason)
    frequency = st.segmented_control(
        "Statement view", ["Annual", "Quarterly"], default="Annual",
        key="fundamentals_frequency",
    )
    selected = "quarterly" if frequency == "Quarterly" else "annual"
    frame = result.quarterly if selected == "quarterly" else result.annual
    if frame.empty:
        st.info(f"No verified {selected} SEC statement periods are available.")
        return
    st.markdown(kpi_grid_html(fundamentals_kpi_cards(result)), unsafe_allow_html=True)
    st.caption("Headline cards use the latest completed annual fiscal period. Net debt remains unavailable until a complete non-overlapping debt definition is verified.")
    for heading, figure in build_fundamentals_figures(result, theme=theme, frequency=selected).items():
        st.markdown(f"#### {heading}")
        st.plotly_chart(figure, width="stretch", theme=None, config={"displaylogo": False, "responsive": True})
    with st.expander("Normalized statement table", expanded=False):
        columns = [column for column in (
            "fiscal_year", "fiscal_quarter", "period_end", "currency", "revenue",
            "operating_income", "net_income_consolidated", "eps_diluted", "ocf",
            "capex_ppe", "fcf", "cash_equivalents", "reported_long_term_debt",
            "shareholders_equity", "operating_margin", "net_margin", "fcf_margin",
        ) if column in frame]
        st.dataframe(frame[columns], width="stretch", hide_index=True)
    with st.expander("Coverage, source lineage and data quality", expanded=False):
        st.caption("Company Facts is an entity-wide standard-concept aggregate. Figures are latest-disclosed and may include later revisions; they are not point-in-time valuation inputs.")
        st.dataframe(result.coverage, width="stretch", hide_index=True)
        if not result.quality.empty:
            st.dataframe(result.quality.head(100), width="stretch", hide_index=True)
        st.caption(f"SEC retrieval: {result.retrieved_at_utc} · mapped observations: {len(result.observations):,} · SHA-256: {result.source_sha256}")
        st.caption("PPE cash payments are positive outflows. FCF = operating cash flow − verified PPE payments. Acquisitions are excluded. Missing components are not zero. Reported long-term debt is a partial debt measure, so net debt is withheld.")
