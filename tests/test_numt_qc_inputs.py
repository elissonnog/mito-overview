from __future__ import annotations

from pathlib import Path

import pandas as pd

from mito_overview.steps.mito_numt_qc import run_step

from ._helpers import metric_map


READ_ROWS = [
    {
        "read_name": "primary",
        "mapq": 10,
        "query_length": 8000,
        "read_start": 1,
        "read_end": 7000,
        "aligned_span": 7000,
        "aligned_fraction_mt": 0.4,
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
        "aligned_span": 7000,
        "aligned_fraction_mt": 0.4,
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
    include_full_length_fraction: bool = True,
) -> None:
    summary_dir.mkdir(parents=True, exist_ok=True)
    reads = pd.DataFrame(READ_ROWS).drop(columns=list(drop_read_columns))
    reads.to_csv(summary_dir / "mito_read_stats.tsv", sep="\t", index=False)
    summary_rows = [{"metric": "mapped_reads", "value": 2}]
    if include_full_length_fraction:
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
    assert metrics["heuristic_numt_risk_score"] == "5"
    assert metrics["low_mapq_fraction_lt20"] == "1.0"
    assert metrics["supplementary_fraction_all_reads"] == "0.5"
    assert metrics["full_length_fraction"] == "0.5"


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
    assert metrics["full_length_fraction"] == "0.5"


def test_missing_summary_metric_suppresses_risk_but_retains_read_metrics(tmp_path: Path) -> None:
    write_numt_inputs(tmp_path / "summary", include_full_length_fraction=False)

    outputs = run_numt_fixture(tmp_path)
    metrics = metric_map(outputs["summary_path"])

    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == "numt_qc_summary_missing_metrics"
    assert metrics["missing_required_read_columns"] == "none"
    assert metrics["missing_required_summary_metrics"] == "full_length_fraction"
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
    assert metrics["heuristic_numt_risk_score"] == "NA"
    assert metrics["low_mapq_fraction_lt20"] == "1.0"
    assert metrics["supplementary_fraction_all_reads"] == "0.5"
    assert metrics["full_length_fraction"] == "NA"


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
