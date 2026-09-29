"""Corporate-action normalization, manual augmentation, and reconciliation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from .config import KNOWN_ACTION_TYPES, PROVIDER_NAME, SHARE_CHANGING_TYPES
from .models import CorporateAction, ValidationIssue

def _ratio_label(multiplier: float, action_type: str) -> str:
    if not np.isfinite(multiplier) or multiplier <= 0:
        return "Unverified"
    if action_type == "bonus_issue":
        additional = multiplier - 1.0
        if additional > 0:
            return f"{additional:g}:1 bonus"
    if multiplier >= 1:
        return f"{multiplier:g}:1"
    return f"1:{1 / multiplier:g}"


def _normalize_provider_actions(
    history: pd.DataFrame, currency: str
) -> list[CorporateAction]:
    actions: list[CorporateAction] = []
    if "Stock Splits" in history.columns:
        split_series = pd.to_numeric(history["Stock Splits"], errors="coerce").fillna(0)
        for date, multiplier in split_series[split_series != 0].items():
            multiplier = float(multiplier)
            action_type = "stock_split" if multiplier >= 1 else "reverse_split"
            actions.append(
                CorporateAction(
                    date=pd.Timestamp(date).normalize(),
                    action_type=action_type,
                    ratio_numerator=multiplier if multiplier >= 1 else 1.0,
                    ratio_denominator=1.0 if multiplier >= 1 else 1.0 / multiplier,
                    share_multiplier=multiplier,
                    currency=currency,
                    source=PROVIDER_NAME,
                    source_description="Reported as a split-equivalent corporate action by Yahoo Finance.",
                    confidence="MEDIUM",
                    notes="Provider does not reliably distinguish bonus issues from conventional splits.",
                    include_in_reconstruction=True,
                )
            )
    if "Dividends" in history.columns:
        dividend_series = pd.to_numeric(history["Dividends"], errors="coerce").fillna(0)
        for date, cash_amount in dividend_series[dividend_series != 0].items():
            actions.append(
                CorporateAction(
                    date=pd.Timestamp(date).normalize(),
                    action_type="cash_dividend",
                    cash_amount=float(cash_amount),
                    currency=currency,
                    source=PROVIDER_NAME,
                    source_description="Provider-reported cash distribution; regular/special classification unavailable.",
                    confidence="MEDIUM",
                    notes="Cash dividends never alter the no-split multiplier.",
                    include_in_reconstruction=False,
                )
            )
    return actions


def load_manual_actions(
    ticker: str,
    path: Optional[str | Path] = None,
    records: Optional[Sequence[Mapping[str, Any]]] = None,
) -> list[CorporateAction]:
    """Load optional, explicitly labelled manual actions without overwriting provider rows."""
    frames: list[pd.DataFrame] = []
    if path:
        manual_path = Path(path)
        if manual_path.exists():
            frames.append(pd.read_csv(manual_path))
        else:
            raise FileNotFoundError(f"Manual corporate-action file not found: {manual_path}")
    if records:
        frames.append(pd.DataFrame(list(records)))
    if not frames:
        return []
    frame = pd.concat(frames, ignore_index=True, sort=False)
    if "ticker" in frame.columns:
        frame = frame[frame["ticker"].astype(str).str.upper() == ticker.upper()]
    output: list[CorporateAction] = []
    for row_number, (_, row) in enumerate(frame.iterrows(), start=2):
        date = pd.to_datetime(row.get("date"), errors="coerce")
        action_type = str(row.get("action_type", "other")).strip().lower()
        if pd.isna(date):
            raise ValueError(f"Manual action row {row_number}: invalid date.")
        if action_type not in KNOWN_ACTION_TYPES:
            action_type = "other"
        numerator = pd.to_numeric(row.get("ratio_numerator"), errors="coerce")
        denominator = pd.to_numeric(row.get("ratio_denominator"), errors="coerce")
        explicit = pd.to_numeric(row.get("share_multiplier"), errors="coerce")
        multiplier: Optional[float] = None
        if pd.notna(explicit):
            multiplier = float(explicit)
        elif pd.notna(numerator) and pd.notna(denominator) and float(denominator) != 0:
            ratio = float(numerator) / float(denominator)
            multiplier = 1.0 + ratio if action_type == "bonus_issue" else ratio
        cash = pd.to_numeric(row.get("cash_amount"), errors="coerce")
        include_value = row.get("include_in_reconstruction", action_type in SHARE_CHANGING_TYPES)
        if isinstance(include_value, str):
            include = include_value.strip().lower() in {"1", "true", "yes", "y"}
        else:
            include = bool(include_value)
        output.append(
            CorporateAction(
                date=pd.Timestamp(date).tz_localize(None).normalize(),
                action_type=action_type,
                ratio_numerator=float(numerator) if pd.notna(numerator) else None,
                ratio_denominator=float(denominator) if pd.notna(denominator) else None,
                share_multiplier=multiplier,
                cash_amount=float(cash) if pd.notna(cash) else None,
                currency=str(row.get("currency") or "") or None,
                source="Manual verified input",
                source_description=str(row.get("source") or "User-supplied manual record"),
                confidence=str(row.get("confidence") or "MEDIUM").upper(),
                notes=str(row.get("notes") or "Explicit manual entry; not a provider fact."),
                include_in_reconstruction=include,
            )
        )
    return output


def reconcile_actions(
    provider_actions: Sequence[CorporateAction],
    manual_actions: Sequence[CorporateAction],
) -> tuple[list[CorporateAction], list[ValidationIssue]]:
    """Merge exact confirmations; retain and flag conflicts instead of silently selecting one."""
    combined = list(provider_actions)
    issues: list[ValidationIssue] = []
    for manual in manual_actions:
        candidates = [
            action
            for action in combined
            if action.action_type in SHARE_CHANGING_TYPES
            and manual.action_type in SHARE_CHANGING_TYPES
            and abs((action.date - manual.date).days) <= 3
        ]
        if candidates and manual.share_multiplier is not None:
            matching = [
                action
                for action in candidates
                if action.share_multiplier is not None
                and math.isclose(action.share_multiplier, manual.share_multiplier, rel_tol=1e-6)
            ]
            if matching:
                original = matching[0]
                original.source = f"{original.source}; {manual.source}"
                original.source_description += f" Confirmed by: {manual.source_description}."
                original.confidence = "HIGH"
                original.notes = (original.notes + " Manual record agrees on date/ratio.").strip()
                continue
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "corporate_action_conflict",
                    f"Manual/provider split conflict near {manual.date.date()}; conflicting rows were retained, not silently reconciled.",
                    manual.date,
                )
            )
            for action in candidates:
                action.include_in_reconstruction = False
                action.confidence = "LOW"
                action.notes = (
                    action.notes
                    + (
                        " Excluded in favor of an explicitly included manual verified record; conflict remains disclosed."
                        if manual.include_in_reconstruction
                        else " Excluded because the provider/manual conflict is unresolved."
                    )
                ).strip()
        combined.append(manual)
    combined.sort(key=lambda action: (action.date, action.action_type, action.source))
    return combined, issues


def actions_to_frame(actions: Sequence[CorporateAction]) -> pd.DataFrame:
    columns = [
        "date",
        "action_type",
        "event",
        "ratio",
        "ratio_numerator",
        "ratio_denominator",
        "share_multiplier",
        "cumulative_multiplier",
        "cash_amount",
        "currency",
        "source",
        "source_description",
        "confidence",
        "included_in_reconstruction",
        "notes",
    ]
    rows = []
    for action in actions:
        multiplier = action.share_multiplier
        ratio = _ratio_label(multiplier, action.action_type) if multiplier else "—"
        event_names = {
            "stock_split": "Stock split",
            "reverse_split": "Reverse split",
            "bonus_issue": "Bonus issue",
            "cash_dividend": "Cash dividend",
            "special_dividend": "Special dividend",
            "stock_dividend": "Stock dividend",
            "rights_issue": "Rights issue",
            "spin_off": "Spin-off",
            "symbol_change": "Symbol change",
            "merger": "Merger",
            "other": "Other / uncertain",
        }
        rows.append(
            {
                "date": pd.Timestamp(action.date).normalize(),
                "action_type": action.action_type,
                "event": event_names.get(action.action_type, "Other / uncertain"),
                "ratio": ratio,
                "ratio_numerator": action.ratio_numerator,
                "ratio_denominator": action.ratio_denominator,
                "share_multiplier": multiplier,
                "cumulative_multiplier": np.nan,
                "cash_amount": action.cash_amount,
                "currency": action.currency,
                "source": action.source,
                "source_description": action.source_description,
                "confidence": action.confidence,
                "included_in_reconstruction": bool(action.include_in_reconstruction),
                "notes": action.notes,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("date", ignore_index=True)
