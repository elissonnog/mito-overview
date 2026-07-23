from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mito_overview.steps.mito_numt_qc import run_step

from ._helpers import metric_map


READ_ROWS = [
    {
        "read_name": "primary",
        "mapq": 10,
        "query_length": 8000,
        "read_start": 1,
        "read_end": 7000,
        "reference_span": 7000,
        "aligned_reference_bases": 7000,
        "aligned_span": 7000,
        "aligned_fraction_mt": round(7000 / 16569, 6),
        "softclip_bases": 2000,
        "softclip_fraction": 0.25,
        "has_sa_tag": 1,
        "is_primary": 1,
        "is_supplementary": 0,
        "is_secondary": 0,
        "is_reverse": 0,
    },
    {
        "read_name": "split",
        "mapq": 60,
        "query_length": 8000,
        "read_start": 8001,
        "read_end": 15000,
        "reference_span": 7000,
        "aligned_reference_bases": 7000,
        "aligned_span": 7000,
        "aligned_fraction_mt": round(7000 / 16569, 6),
        "softclip_bases": 0,
        "softclip_fraction": 0.0,
        "has_sa_tag": 0,
        "is_primary": 0,
        "is_supplementary": 1,
        "is_secondary": 0,
        "is_reverse": 0,
    },
]


def write_numt_inputs(
    summary_dir: Path,
    *,
    drop_read_columns: tuple[str, ...] = (),
    include_primary_full_length_fraction: bool = True,
    primary_full_length_fraction: float = 0.0,
) -> None:
    summary_dir.mkdir(parents=True, exist_ok=True)
    reads = pd.DataFrame(READ_ROWS).drop(columns=list(drop_read_columns))
    reads.to_csv(summary_dir / "mito_read_stats.tsv", sep="\t", index=False)
    summary_rows = [{"metric": "mapped_reads", "value": 2}]
    if include_primary_full_length_fraction:
        summary_rows.append(
            {
                "metric": "primary_full_length_fraction",
                "value": primary_full_length_fraction,
            }
        )
    summary_rows.append({"metric": "full_length_fraction", "value": 0.5})
    pd.DataFrame(summary_rows).to_csv(summary_dir / "mito_qc_summary.tsv", sep="\t", index=False)


def run_numt_fixture(tmp_path: Path) -> dict[str, Path | str]:
    return run_step(
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="TOY-NUMT",
        mt_contig="MT",
        mt_length=16569,
        reference_scope="whole_genome",
    )


def test_whole_genome_numt_risk_uses_complete_inputs(tmp_path: Path) -> None:
    write_numt_inputs(tmp_path / "summary")

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "ok"
    assert metrics["reason_code"] == ""
    assert metrics["missing_required_read_columns"] == "none"
    assert metrics["missing_required_summary_metrics"] == "none"
    assert metrics["heuristic_numt_risk"] == "high"
    assert metrics["heuristic_numt_risk_score"] == "6"
    assert metrics["low_mapq_fraction_lt20"] == "1.0"
    assert metrics["supplementary_fraction_all_reads"] == "0.5"
    assert metrics["primary_alignment_records"] == "1"
    assert metrics["primary_full_length_reads"] == "0"
    assert metrics["primary_full_length_fraction"] == "0.0"
    assert metrics["primary_full_length_fraction_denominator"] == "primary_alignment_records"
    assert metrics["primary_full_length_fraction_source"] == "mito_read_stats_primary_alignment_records"
    assert metrics["primary_full_length_fraction_basis"] == "aligned_reference_bases_excluding_cigar_D_N"
    assert metrics["primary_full_length_qc_crosscheck_status"] == "ok"
    assert metrics["full_length_fraction"] == "0.0"
    assert metrics["full_length_fraction_compatibility_alias_of"] == "primary_full_length_fraction"


def test_missing_read_column_suppresses_risk_without_zero_filling(tmp_path: Path) -> None:
    write_numt_inputs(tmp_path / "summary", drop_read_columns=("mapq",))

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == "numt_read_stats_missing_columns"
    assert metrics["missing_required_read_columns"] == "mapq"
    assert metrics["missing_required_summary_metrics"] == "none"
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
    assert metrics["heuristic_numt_risk_score"] == "NA"
    assert metrics["low_mapq_fraction_lt20"] == "NA"
    assert metrics["very_low_mapq_fraction_lt5"] == "NA"
    assert metrics["short_aligned_fraction_lt0.5_mt"] == "1.0"
    assert metrics["heavy_softclip_fraction_gt0.2"] == "1.0"
    assert metrics["primary_full_length_fraction"] == "0.0"
    assert metrics["full_length_fraction"] == "0.0"


def test_missing_qc_primary_fraction_suppresses_categorical_risk(
    tmp_path: Path,
) -> None:
    write_numt_inputs(
        tmp_path / "summary", include_primary_full_length_fraction=False
    )

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == "numt_qc_summary_missing_metrics"
    assert metrics["missing_required_read_columns"] == "none"
    assert metrics["missing_required_summary_metrics"] == "primary_full_length_fraction"
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
    assert metrics["heuristic_numt_risk_score"] == "NA"
    assert metrics["low_mapq_fraction_lt20"] == "1.0"
    assert metrics["supplementary_fraction_all_reads"] == "0.5"
    assert metrics["primary_full_length_fraction"] == "0.0"
    assert metrics["full_length_fraction"] == "0.0"
    assert metrics["primary_full_length_qc_crosscheck_status"] == "not_configured"
    assert (
        metrics["primary_full_length_qc_crosscheck_reason_code"]
        == "primary_full_length_fraction_missing_from_mito_qc"
    )


def test_inconsistent_qc_primary_fraction_suppresses_categorical_risk(
    tmp_path: Path,
) -> None:
    write_numt_inputs(
        tmp_path / "summary", primary_full_length_fraction=0.5
    )

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == "numt_primary_full_length_fraction_mismatch"
    assert metrics["primary_full_length_fraction"] == "0.0"
    assert metrics["full_length_fraction"] == "0.0"
    assert metrics["primary_full_length_qc_crosscheck_status"] == "not_evaluable"
    assert (
        metrics["primary_full_length_qc_crosscheck_reason_code"]
        == "primary_full_length_fraction_mismatch"
    )
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
    assert metrics["heuristic_numt_risk_score"] == "NA"


def test_invalid_primary_indicator_cannot_produce_categorical_risk(tmp_path: Path) -> None:
    write_numt_inputs(tmp_path / "summary")
    reads_path = tmp_path / "summary" / "mito_read_stats.tsv"
    reads = pd.read_csv(reads_path, sep="\t")
    reads["is_primary"] = reads["is_primary"].astype(object)
    reads.loc[0, "is_primary"] = "invalid"
    reads.to_csv(reads_path, sep="\t", index=False)

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == "numt_primary_indicator_invalid"
    assert metrics["primary_indicator_valid"] == "0"
    assert metrics["primary_evidence_available"] == "0"
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
    assert metrics["heuristic_numt_risk_score"] == "NA"


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("mapq", float("nan")),
        ("mapq", float("inf")),
        ("mapq", -1),
        ("mapq", 1.5),
        ("mapq", 255),
        ("aligned_fraction_mt", float("nan")),
        ("aligned_fraction_mt", float("inf")),
        ("aligned_fraction_mt", -0.01),
        ("aligned_fraction_mt", 1.01),
        ("aligned_reference_bases", float("nan")),
        ("aligned_reference_bases", float("inf")),
        ("aligned_reference_bases", -1),
        ("aligned_reference_bases", 1.5),
        ("softclip_fraction", float("nan")),
        ("softclip_fraction", float("-inf")),
        ("softclip_fraction", -0.01),
        ("softclip_fraction", 1.01),
        ("has_sa_tag", float("nan")),
        ("has_sa_tag", 2),
        ("is_supplementary", float("nan")),
        ("is_supplementary", 2),
    ),
)
def test_invalid_required_read_domains_suppress_categorical_risk(
    tmp_path: Path,
    column: str,
    value: float,
) -> None:
    write_numt_inputs(tmp_path / "summary")
    reads_path = tmp_path / "summary" / "mito_read_stats.tsv"
    reads = pd.read_csv(reads_path, sep="\t")
    reads[column] = reads[column].astype(object)
    reads.loc[0, column] = value
    reads.to_csv(reads_path, sep="\t", index=False)

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == "numt_read_stats_invalid_values"
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
    assert metrics["heuristic_numt_risk_score"] == "NA"


def test_combined_malformed_numt_row_cannot_report_low_risk(tmp_path: Path) -> None:
    write_numt_inputs(tmp_path / "summary")
    reads_path = tmp_path / "summary" / "mito_read_stats.tsv"
    reads = pd.read_csv(reads_path, sep="\t")
    for column in (
        "mapq",
        "aligned_fraction_mt",
        "aligned_reference_bases",
        "softclip_fraction",
        "has_sa_tag",
        "is_supplementary",
    ):
        reads[column] = reads[column].astype(object)
    reads.loc[0, "mapq"] = float("inf")
    reads.loc[0, "aligned_fraction_mt"] = float("inf")
    reads.loc[0, "aligned_reference_bases"] = -1
    reads.loc[0, "softclip_fraction"] = -1
    reads.loc[0, "has_sa_tag"] = 2
    reads.loc[0, "is_supplementary"] = 2
    reads.to_csv(reads_path, sep="\t", index=False)

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == "numt_read_stats_invalid_values"
    assert metrics["low_mapq_fraction_lt20"] == "NA"
    assert metrics["short_aligned_fraction_lt0.5_mt"] == "NA"
    assert metrics["heavy_softclip_fraction_gt0.2"] == "NA"
    assert metrics["sa_tag_fraction"] == "NA"
    assert metrics["supplementary_fraction_all_reads"] == "NA"
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
    assert metrics["heuristic_numt_risk_score"] == "NA"


def test_inconsistent_aligned_bases_and_fraction_suppress_categorical_risk(
    tmp_path: Path,
) -> None:
    write_numt_inputs(tmp_path / "summary")
    reads_path = tmp_path / "summary" / "mito_read_stats.tsv"
    reads = pd.read_csv(reads_path, sep="\t")
    reads.loc[0, "aligned_fraction_mt"] = 0.99
    reads.to_csv(reads_path, sep="\t", index=False)

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == "numt_read_stats_invalid_values"
    assert metrics["aligned_span_fraction_consistent"] == "0"
    assert "aligned_reference_bases_vs_aligned_fraction_mt" in metrics[
        "invalid_required_read_values"
    ]
    assert metrics["heuristic_numt_risk"] == "not_evaluable"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_required_qc_fraction_suppresses_categorical_risk(
    tmp_path: Path,
    value: float,
) -> None:
    write_numt_inputs(tmp_path / "summary")
    qc_path = tmp_path / "summary" / "mito_qc_summary.tsv"
    qc = pd.read_csv(qc_path, sep="\t")
    qc.loc[qc["metric"] == "primary_full_length_fraction", "value"] = value
    qc.to_csv(qc_path, sep="\t", index=False)

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == "numt_qc_summary_invalid_values"
    assert metrics["invalid_required_summary_values"] == "primary_full_length_fraction"
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
