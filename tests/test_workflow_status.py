from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mito_overview.workflow import StepResult, _run_deletions, _run_identity_qc, _run_mito_qc


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


def test_workflow_preserves_non_evaluable_status_from_reporting_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mito_bam = tmp_path / "mito.bam"
    mito_bam.touch()
    paths = SimpleNamespace(
        mito_bam=mito_bam,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        log_dir=tmp_path / "logs",
        phased_snp_vcf=None,
        np_snp_vcf=None,
    )
    for directory in (paths.summary_dir, paths.figure_dir, paths.report_dir, paths.log_dir):
        directory.mkdir()
    config = SimpleNamespace(
        sample_id="STATUS-TEST",
        detected_species="human",
        reference_build_guess="hg38",
        read_mode="long",
        assay_type="wgs",
        mt_contig="MT",
        mt_length=100,
        deletion_min_size=100,
    )

    def not_evaluable_step(**kwargs: object) -> dict[str, Path | str]:
        return {
            "status": "not_evaluable",
            "report_path": Path(str(kwargs["report_dir"])) / "status.html",
        }

    monkeypatch.setattr("mito_overview.steps.mito_qc.run_step", not_evaluable_step)
    monkeypatch.setattr("mito_overview.steps.mito_deletions.run_step", not_evaluable_step)
    monkeypatch.setattr("mito_overview.steps.mito_identity_qc.run_step", not_evaluable_step)

    results = [
        _run_mito_qc(config, paths, False),
        _run_deletions(config, paths, False),
        _run_identity_qc(config, paths, False),
    ]

    assert [result.status for result in results] == ["not_evaluable"] * 3
    for step_name in ("mito_qc", "deletions", "identity_qc"):
        assert (paths.log_dir / f"{step_name}.not_evaluable").read_text() == "not_evaluable\n"
        assert not (paths.log_dir / f"{step_name}.done").exists()
