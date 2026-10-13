"""Independent declared-dividend benchmarks: validation ONLY, never corrections.

Scoped reviewed intervals, exact listing/currency and compatible share basis.
Adding a reference for another issuer requires no reconciliation-engine change.
"""

import json
import math
from importlib.resources import files

import pandas as pd

from .models import ValidationIssue


def validate_declared_dividends(prices, events, metadata, references=None):
    references = references if references is not None else json.loads(
        files("src").joinpath("data/dividend_references.json").read_text(encoding="utf-8"))
    rows = [row for row in references if row["ticker"] == metadata.ticker]
    issues = []
    if not rows:
        return [ValidationIssue("INFO", "dividend_external_reference",
            "No independently reviewed issuer dividend benchmark is configured. Yahoo endpoint agreement and internal arithmetic do not establish external dividend accuracy.")]
    for row in rows:
        start, end, last_event = map(pd.Timestamp, (row["period_start"], row["period_end"], row["last_ex_date"]))
        if prices.index.min() > start or prices.index.max() < last_event:
            continue  # Incomplete observed reference window is not a mismatch.
        cutoff = min(end, prices.index.max())
        selected = events.loc[pd.to_datetime(events.date).between(start, cutoff)]
        if metadata.currency != row["currency"] or row["basis"] != "declared_per_share":
            issues.append(ValidationIssue("WARNING", "dividend_external_basis",
                f"Independent reference unit/basis incompatible for {start.year}; no inferred currency conversion or amount repair."))
            continue
        factors = prices.cumulative_split_factor
        within = factors.loc[(factors.index >= start) & (factors.index <= cutoff)]
        before = factors.loc[factors.index < start]
        if within.empty:
            continue
        initial = before.iloc[-1] if len(before) else within.iloc[0]
        if within.ne(initial).any():
            issues.append(ValidationIssue("INFO", "dividend_external_basis",
                f"Share structure changed inside reference interval {start.date()}–{cutoff.date()}; aggregate comparison withheld pending event-level share-basis evidence."))
            continue
        expected = float(row["amount"]) * float(within.iloc[-1]) / float(factors.iloc[-1])
        observed = pd.to_numeric(selected.provider_dividend, errors="coerce")
        amount = float(observed.sum())
        count = int(observed.gt(0).sum())
        finite = observed.notna().all() and all(math.isfinite(value) for value in observed)
        matches = finite and math.isclose(amount, expected, rel_tol=1e-6, abs_tol=1e-5) and count == row["event_sessions"]
        issues.append(ValidationIssue("PASS" if matches else "ERROR", "dividend_external_reference",
            f"{start.date()}–{cutoff.date()}: provider {amount:g} {metadata.currency} across {count} ex-date sessions; independent declared reference {expected:g} across {row['event_sessions']} sessions. "
            f"Reference reviewed {row['reviewed_on']}: {row['source_url']}. Validation only; provider values are not overwritten."))
    if not issues:
        issues.append(ValidationIssue("INFO", "dividend_external_reference", "No complete independent reference interval falls within the available observations."))
    return issues


def dividend_diagnostics(result):
    if result.validation.empty:
        return result.validation
    return result.validation.loc[result.validation.check.isin([
        "dividend_external_reference", "dividend_external_basis", "action_source_conflict",
        "action_timezone_unverified", "dedicated_action_unavailable", "dividend_event_without_price",
        "invalid_dedicated_action", "invalid_history_date",
    ])]
