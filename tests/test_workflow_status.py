from __future__ import annotations

import pytest

from mito_overview.workflow import StepResult


def test_step_result_accepts_controlled_module_states() -> None:
    for status in (
        "ok",
        "not_configured",
        "not_applicable",
        "not_evaluable",
        "unavailable",
        "failed",
    ):
        assert StepResult("example", status, "message").status == status


def test_step_result_allows_planned_only_as_dry_run_state() -> None:
    assert StepResult("example", "planned", "message").status == "planned"


def test_step_result_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="Unsupported module state"):
        StepResult("example", "skipped", "message")
