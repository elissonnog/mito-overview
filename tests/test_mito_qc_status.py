from __future__ import annotations

from pathlib import Path

import pandas as pd

from mito_overview.steps.mito_qc import run_step

from ._helpers import ReadSpec, metric_map, write_alignment


def run_qc_fixture(
    tmp_path: Path,
    reads: list[ReadSpec],
    *,
    read_mode: str = "long",
    assay_type: str = "wgs",
) -> dict[str, Path | str]:
    bam = write_alignment(tmp_path / "qc.bam", {"MT": 100}, reads)
    return run_step(
        bam=bam,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="TOY-QC",
        species="human",
        build="hg38",
        read_mode=read_mode,
        assay_type=assay_type,
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


def test_full_length_fraction_excludes_cigar_deletion_bases(tmp_path: Path) -> None:
    outputs = run_qc_fixture(
        tmp_path,
        [
            ReadSpec(
                "deletion-spanning",
                "MT",
                0,
                "A" * 20,
                cigar=((0, 10), (2, 80), (0, 10)),
            )
        ],
    )
    summary = metric_map(Path(outputs["summary_path"]))
    reads = pd.read_csv(outputs["reads_path"], sep="\t")

    assert summary["primary_full_length_reads"] == "0"
    assert float(summary["primary_full_length_fraction"]) == 0.0
    assert summary["primary_full_length_fraction_basis"] == "aligned_reference_bases_excluding_cigar_D_N"
    assert reads.loc[0, "reference_span"] == 100
    assert reads.loc[0, "aligned_reference_bases"] == 20
    assert reads.loc[0, "aligned_span"] == 20
    assert reads.loc[0, "aligned_fraction_mt"] == 0.2


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


def test_short_read_full_length_metric_is_not_applicable(tmp_path: Path) -> None:
    outputs = run_qc_fixture(
        tmp_path,
        [ReadSpec("short-read", "MT", 0, "A" * 50)],
        read_mode="short",
        assay_type="targeted_mt",
    )
    summary = metric_map(Path(outputs["summary_path"]))

    assert outputs["status"] == "ok"
    assert summary["primary_full_length_reads"] == ""
    assert summary["primary_full_length_fraction"] == ""
    assert summary["primary_full_length_fraction_status"] == "not_applicable"
    assert summary["primary_full_length_fraction_reason_code"] == "read_mode_short"
    assert summary["primary_full_length_fraction_denominator"] == ""
    assert summary["full_length_fraction"] == ""
    assert float(summary["high_query_alignment_fraction"]) == 1.0
