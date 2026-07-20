"""Small compatibility helpers for stable public TSV contracts."""

from __future__ import annotations

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
