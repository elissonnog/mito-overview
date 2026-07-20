from __future__ import annotations

import pandas as pd
import pytest

from mito_overview.table_contracts import (
    MODULE_STATES,
    ensure_alt_fraction_columns,
    validate_module_state,
)


def test_legacy_fraction_is_promoted_without_dropping_alias() -> None:
    table = ensure_alt_fraction_columns(pd.DataFrame({"heteroplasmy_fraction": [0.25]}))
    assert table.loc[0, "alt_allele_fraction"] == pytest.approx(0.25)
    assert table.loc[0, "heteroplasmy_fraction"] == pytest.approx(0.25)


def test_conflicting_fraction_columns_fail() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        ensure_alt_fraction_columns(
            pd.DataFrame(
                {
                    "alt_allele_fraction": [0.25],
                    "heteroplasmy_fraction": [0.30],
                }
            )
        )


def test_module_state_vocabulary_is_closed() -> None:
    assert MODULE_STATES == {
        "ok",
        "not_configured",
        "not_applicable",
        "not_evaluable",
        "unavailable",
        "failed",
    }
    for state in MODULE_STATES:
        assert validate_module_state(state) == state
    with pytest.raises(ValueError, match="Unsupported module state"):
        validate_module_state("pending")
