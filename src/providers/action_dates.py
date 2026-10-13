"""Exchange-calendar dates and auditable, exact-session action reconciliation.

No adjacent-date/amount heuristics: regular and special cash components on one
session may be distinct, and identical amounts on different dates stay distinct.
"""

import math
from zoneinfo import ZoneInfo

import pandas as pd

from ..models import ValidationIssue


ACTION_DATA_VERSION = "exchange-session-actions-v2"


def session_dates(values, exchange_timezone=None):
    """Strip timezone only AFTER conversion to the security's exchange timezone.

    Without a timezone hint, aware timestamps retain their own wall-clock date;
    naive daily labels remain date labels, never silently interpreted as UTC.
    """
    if exchange_timezone:
        ZoneInfo(str(exchange_timezone))  # Invalid configuration must not guess.
    dates = []
    for value in values:
        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.isna(timestamp):
            dates.append(pd.NaT)
            continue
        if timestamp.tzinfo is not None:
            if exchange_timezone:
                timestamp = timestamp.tz_convert(str(exchange_timezone))
            timestamp = timestamp.tz_localize(None)
        dates.append(timestamp.normalize())
    return pd.DatetimeIndex(dates, name="date")


def action_rows(frame, dates, source):
    records = []
    for column in ("Dividends", "Stock Splits"):
        if column not in frame:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        for timestamp, date, value in zip(frame.index, dates, values):
            if pd.isna(value) or value == 0:
                continue
            records.append(dict(source=source, action=column, raw_timestamp=str(timestamp),
                session_date=None if pd.isna(date) else date.date().isoformat(),
                value=float(value), decision="invalid_withheld" if pd.isna(date) else "history_retained" if source == "history" else "pending"))
    return records


def reconcile_dedicated_actions(history, obj, exchange_timezone=None):
    result = history.copy()
    notes, issues = [], list(history.attrs.get("action_issues", []))
    audit = [dict(row) for row in history.attrs.get("action_audit", [])]
    if not exchange_timezone:
        issues.append(ValidationIssue("WARNING", "action_timezone_unverified",
            "Exchange timezone is unavailable. Provider wall-clock date labels were retained; cross-source date equivalence is not independently verified."))
    for attribute, column in (("splits", "Stock Splits"), ("dividends", "Dividends")):
        try:
            series = getattr(obj, attribute)
            if not isinstance(series, pd.Series):
                raise TypeError("Unexpected dedicated action response")
            if series.empty:
                if column in result and pd.to_numeric(result[column],errors="coerce").fillna(0).ne(0).any():
                    issues.append(ValidationIssue("WARNING", "dedicated_action_unavailable",
                        f"Ticker.{attribute} returned no observations despite history actions. History retained; cross-source coverage is unconfirmed."))
                continue
            dates = session_dates(series.index, exchange_timezone)
            rows = action_rows(series.to_frame(column), dates, "Ticker." + attribute)
            audit.extend(rows)
            if column not in result:
                result[column] = 0.0
            by_date = {}
            for row in rows:
                if row["session_date"] is None or not math.isfinite(row["value"]) or (column == "Stock Splits" and row["value"] <= 0):
                    row["decision"] = "invalid_withheld"
                    issues.append(ValidationIssue("WARNING", "invalid_dedicated_action", f"Invalid Ticker.{attribute} observation was withheld."))
                    continue
                by_date.setdefault(pd.Timestamp(row["session_date"]), []).append(row)
            for date, group in by_date.items():
                raw_keys = [(row["raw_timestamp"], row["value"]) for row in group]
                ambiguous = len(raw_keys) != len(set(raw_keys)) or (column == "Stock Splits" and len(group) > 1)
                if ambiguous:
                    for row in group:
                        row["decision"] = "ambiguous_withheld"
                    issues.append(ValidationIssue("WARNING", "action_source_conflict",
                        f"Ticker.{attribute} contains ambiguous same-session observations; dedicated values were withheld, history was retained.", date))
                    continue
                # Preserve distinct cash components (e.g. final + special).
                value = sum(row["value"] for row in group) if column == "Dividends" else group[0]["value"]
                if date not in result.index:
                    result = result.reindex(result.index.union(pd.DatetimeIndex([date])).sort_values())
                existing = pd.to_numeric(pd.Series([result.at[date, column]]), errors="coerce").iloc[0]
                if pd.isna(existing) or existing == 0:
                    result.at[date, column] = value
                    decision = "dedicated_fallback"
                elif math.isclose(float(existing), value, rel_tol=1e-8, abs_tol=1e-12):
                    decision = "cross_source_confirmed_once"
                else:
                    decision = "conflict_history_retained"
                    issues.append(ValidationIssue("WARNING", "action_source_conflict",
                        f"History and Ticker.{attribute} disagree on {date.date()}: history={existing:g}, dedicated={value:g}. History retained; no automatic averaging, summing or adjustment.", date))
                for row in group:
                    row["decision"] = decision
            notes.append(f"Reconciled Ticker.{attribute} on exchange-local session dates; raw observations and decisions retained in the action audit.")
        except Exception as exc:
            issues.append(ValidationIssue("WARNING", "dedicated_action_unavailable",
                f"Ticker.{attribute} cross-check unavailable ({type(exc).__name__}); no independent provider-source agreement is claimed."))
            notes.append(f"Dedicated Ticker.{attribute} endpoint unavailable ({type(exc).__name__}).")
    result.sort_index(inplace=True)
    result.attrs["action_audit"] = audit
    result.attrs["action_issues"] = issues
    result.attrs["action_data_version"] = ACTION_DATA_VERSION
    return result, notes
