"""Small compatibility helpers for stable public TSV contracts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


MODULE_STATES = frozenset(
    {
        "ok",
        "not_configured",
        "not_applicable",
        "not_evaluable",
        "unavailable",
        "failed",
    }
)


def ensure_alt_fraction_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with canonical and deprecated alternate-fraction columns.

    ``alt_allele_fraction`` is canonical from v0.3.0. The historical
    ``heteroplasmy_fraction`` alias remains available throughout the 0.x series.
    When both are present, disagreement is an error rather than a silent choice.
    """

    normalized = frame.copy()
    canonical = "alt_allele_fraction"
    legacy = "heteroplasmy_fraction"
    if canonical not in normalized.columns and legacy in normalized.columns:
        normalized[canonical] = normalized[legacy]
    if legacy not in normalized.columns and canonical in normalized.columns:
        normalized[legacy] = normalized[canonical]
    if canonical in normalized.columns and legacy in normalized.columns:
        canonical_values = pd.to_numeric(normalized[canonical], errors="coerce")
        legacy_values = pd.to_numeric(normalized[legacy], errors="coerce")
        comparable = canonical_values.notna() & legacy_values.notna()
        if comparable.any() and not (
            (canonical_values.loc[comparable] - legacy_values.loc[comparable]).abs() <= 1e-9
        ).all():
            raise ValueError("alt_allele_fraction conflicts with heteroplasmy_fraction")
    return normalized


def validate_module_state(status: str) -> str:
    """Validate and return one controlled module state."""

    if status not in MODULE_STATES:
        allowed = ", ".join(sorted(MODULE_STATES))
        raise ValueError(f"Unsupported module state {status!r}; expected one of: {allowed}")
    return status


def load_metric_module_state(
    path: str | Path,
    *,
    module_name: str,
    missing_status: str = "not_evaluable",
) -> tuple[str, str]:
    """Read one metric/value module summary without inventing evidence."""

    path = Path(path)
    missing_status = validate_module_state(missing_status)
    if not path.is_file():
        return missing_status, f"{module_name}_summary_missing"
    try:
        frame = pd.read_csv(path, sep="\t")
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return "not_evaluable", f"{module_name}_summary_unusable"
    if frame.empty or not {"metric", "value"}.issubset(frame.columns):
        return "not_evaluable", f"{module_name}_summary_unusable"

    status_values = frame.loc[frame["metric"].astype(str) == "status", "value"]
    if len(status_values) != 1 or pd.isna(status_values.iloc[0]):
        return "not_evaluable", f"{module_name}_summary_status_invalid"
    try:
        status = validate_module_state(str(status_values.iloc[0]).strip())
    except ValueError:
        return "not_evaluable", f"{module_name}_summary_status_invalid"

    reason_values = frame.loc[frame["metric"].astype(str) == "reason_code", "value"]
    reason = ""
    if len(reason_values) == 1 and not pd.isna(reason_values.iloc[0]):
        reason = str(reason_values.iloc[0]).strip()
    if status != "ok" and not reason:
        reason = f"{module_name}_status_{status}"
    return status, reason
