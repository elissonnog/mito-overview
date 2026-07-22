from __future__ import annotations

from pathlib import Path

from mito_overview.steps.mito_qc import run_step

from ._helpers import ReadSpec, metric_map, write_alignment


def run_qc_fixture(tmp_path: Path, reads: list[ReadSpec]) -> dict[str, Path | str]:
    bam = write_alignment(tmp_path / "qc.bam", {"MT": 100}, reads)
    return run_step(
        bam=bam,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="TOY-QC",
        species="human",
        build="hg38",
        read_mode="long",
        assay_type="wgs",
        mt_contig="MT",
        mt_length=100,
    )


def test_zero_mapped_read_denominator_is_not_evaluable_and_fraction_is_na(
    tmp_path: Path,
) -> None:
    outputs = run_qc_fixture(tmp_path, [])
    summary = metric_map(Path(outputs["summary_path"]))

    assert outputs["status"] == "not_evaluable"
    assert summary["status"] == "not_evaluable"
    assert summary["reason_code"] == "no_mapped_reads"
    assert summary["mapped_reads"] == "0"
    assert summary["primary_full_length_fraction"] == ""
    assert summary["primary_full_length_fraction_status"] == "not_evaluable"
    assert summary["primary_full_length_fraction_reason_code"] == "no_primary_reads"
    assert summary["full_length_fraction"] == ""


def test_available_mapped_read_denominator_preserves_observed_zero_fraction(
    tmp_path: Path,
) -> None:
    outputs = run_qc_fixture(tmp_path, [ReadSpec("short-span", "MT", 0, "A" * 10)])
    summary = metric_map(Path(outputs["summary_path"]))

    assert outputs["status"] == "ok"
    assert summary["status"] == "ok"
    assert summary["reason_code"] == ""
    assert summary["mapped_reads"] == "1"
    assert float(summary["primary_full_length_fraction"]) == 0.0
    assert summary["primary_full_length_fraction_denominator"] == "primary_alignment_records"
    assert float(summary["full_length_fraction"]) == 0.0
    assert summary["full_length_fraction_compatibility_alias_of"] == "primary_full_length_fraction"


def test_full_length_fraction_excludes_supplementary_alignment_records(
    tmp_path: Path,
) -> None:
    outputs = run_qc_fixture(
        tmp_path,
        [
            ReadSpec("primary-short", "MT", 0, "A" * 10),
            ReadSpec("supplementary-full", "MT", 0, "A" * 100, flag=2048),
        ],
    )
    summary = metric_map(Path(outputs["summary_path"]))

    assert summary["mapped_reads"] == "2"
    assert summary["primary_reads"] == "1"
    assert summary["supplementary_reads"] == "1"
    assert summary["primary_full_length_reads"] == "0"
    assert float(summary["primary_full_length_fraction"]) == 0.0
    assert float(summary["full_length_fraction"]) == 0.0


def test_supplementary_only_qc_keeps_primary_fraction_unavailable(
    tmp_path: Path,
) -> None:
    outputs = run_qc_fixture(
        tmp_path,
        [ReadSpec("supplementary-full", "MT", 0, "A" * 100, flag=2048)],
    )
    summary = metric_map(Path(outputs["summary_path"]))

    assert outputs["status"] == "ok"
    assert summary["mapped_reads"] == "1"
    assert summary["primary_reads"] == "0"
    assert summary["primary_full_length_fraction"] == ""
    assert summary["full_length_fraction"] == ""
    assert summary["primary_full_length_fraction_status"] == "not_evaluable"
    assert summary["primary_full_length_fraction_reason_code"] == "no_primary_reads"
