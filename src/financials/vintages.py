"""Latest-disclosed selection retaining all reported versions and decisions."""

from __future__ import annotations

import pandas as pd


PERIOD_KEY = ["normalized_concept", "period_start", "period_end", "period_type", "unit"]


def select_latest_disclosed(observations: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if observations.empty:
        return observations.copy(), pd.DataFrame(columns=["observation_id", "decision", "reason"])
    valid = observations.loc[
        observations["quality_status"].ne("invalid")
        & observations["value"].notna()
        & observations["period_type"].ne("unknown")
    ].copy()
    selected_ids: set[str] = set()
    decisions: list[dict] = []
    for _, group in valid.groupby(PERIOD_KEY, dropna=False, sort=False):
        order = group.sort_values(
            ["filing_date", "acceptance_timestamp_utc", "observation_id"],
            na_position="first", kind="stable",
        )
        newest = order.iloc[-1]
        peer = order.loc[
            order["filing_date"].eq(newest["filing_date"])
            & order["acceptance_timestamp_utc"].eq(newest["acceptance_timestamp_utc"])
        ]
        # Equal alternatives use the declared priority; conflicting alternatives
        # at the newest disclosure are withheld, never summed. Same-day facts
        # without acceptance timestamps still form one comparison group.
        if pd.isna(newest["acceptance_timestamp_utc"]):
            peer = order.loc[order["filing_date"].eq(newest["filing_date"])
                             & order["acceptance_timestamp_utc"].isna()]
        if peer["value"].nunique() > 1:
            for row in group.itertuples():
                decisions.append({"observation_id": row.observation_id, "decision": "excluded", "reason": "CONFLICTING_FACTS"})
            continue
        if "mapping_priority" in peer and len(peer) > 1:
            newest = peer.sort_values(["mapping_priority", "observation_id"], kind="stable").iloc[0]
        selected_ids.add(newest["observation_id"])
    for row in observations.itertuples():
        if row.observation_id in selected_ids:
            decision, reason = "selected", "latest comparable disclosure"
        elif row.quality_status == "invalid":
            decision, reason = "excluded", ",".join(row.quality_flags)
        elif row.period_type == "unknown":
            decision, reason = "excluded", "UNKNOWN_FISCAL_PERIOD"
        else:
            decision, reason = "not_selected", "earlier or incompatible disclosure"
        decisions.append({"observation_id": row.observation_id, "decision": decision, "reason": reason})
    decisions_frame = pd.DataFrame(decisions).drop_duplicates(subset=["observation_id"], keep="first")
    return observations.loc[observations["observation_id"].isin(selected_ids)].copy(), decisions_frame
