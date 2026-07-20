from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mito_overview.config import detect_reference_scope
from mito_overview.steps.extract_mito_assets import write_mito_region_bed
from mito_overview.steps.mito_numt_qc import run_step

from ._helpers import metric_map


def test_reference_scope_auto_resolution() -> None:
    assert detect_reference_scope(
        requested="auto", contig_lengths={"MT": 16569}, mt_contig="MT", species="human"
    ) == "mt_only"
    complete_human = {"MT": 16569, **{f"chr{i}": 1000 for i in range(1, 23)}}
    assert detect_reference_scope(
        requested="auto", contig_lengths=complete_human, mt_contig="MT", species="human"
    ) == "whole_genome"
    assert detect_reference_scope(
        requested="auto", contig_lengths={"MT": 16569, "chr1": 1000}, mt_contig="MT", species="human"
    ) == "custom"


@pytest.mark.parametrize(
    "contigs",
    [
        {"MT": 16569},
        {"MT": 16569, "chr1": 1000},
    ],
)
def test_whole_genome_scope_cannot_override_incomplete_reference(
    contigs: dict[str, int],
) -> None:
    with pytest.raises(ValueError, match="requires a recognized complete nuclear reference"):
        detect_reference_scope(
            requested="whole_genome",
            contig_lengths=contigs,
            mt_contig="MT",
            species="human",
        )


def test_mito_bed_is_exact_zero_based_half_open(tmp_path: Path) -> None:
    path = write_mito_region_bed(tmp_path / "mt.bed", "MT", 16569)
    assert path.read_bytes() == b"MT\t0\t16569\n"


def write_numt_inputs(summary_dir: Path) -> None:
    summary_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "read_name": "r1",
                "mapq": 60,
                "query_length": 16000,
                "read_start": 1,
                "read_end": 16000,
                "aligned_span": 16000,
                "aligned_fraction_mt": 0.966,
                "softclip_bases": 0,
                "softclip_fraction": 0.0,
                "has_sa_tag": 0,
                "is_primary": 1,
                "is_supplementary": 0,
                "is_secondary": 0,
                "is_reverse": 0,
            }
        ]
    ).to_csv(summary_dir / "mito_read_stats.tsv", sep="\t", index=False)
    pd.DataFrame([{"metric": "full_length_fraction", "value": 1.0}]).to_csv(
        summary_dir / "mito_qc_summary.tsv", sep="\t", index=False
    )


@pytest.mark.parametrize(
    ("scope", "reason"),
    [("mt_only", "reference_scope_mt_only"), ("custom", "reference_scope_custom")],
)
def test_numt_interpretation_is_suppressed_without_whole_genome_scope(
    scope: str, reason: str, tmp_path: Path
) -> None:
    root = tmp_path / scope
    summary = root / "summary"
    write_numt_inputs(summary)
    outputs = run_step(
        summary_dir=summary,
        figure_dir=root / "figures",
        report_dir=root / "reports",
        sample_id="S1",
        mt_contig="MT",
        mt_length=16569,
        reference_scope=scope,
    )
    metrics = metric_map(outputs["summary_path"])
    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == reason
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
    assert metrics["heuristic_numt_risk_score"] == ""
    assert metrics["reads_evaluated"] == "1"


def test_whole_genome_scope_permits_bounded_warning_calculation(tmp_path: Path) -> None:
    summary = tmp_path / "summary"
    write_numt_inputs(summary)
    outputs = run_step(
        summary_dir=summary,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="S1",
        mt_contig="MT",
        mt_length=16569,
        reference_scope="whole_genome",
    )
    metrics = metric_map(outputs["summary_path"])
    assert metrics["numt_interpretation_status"] == "ok"
    assert metrics["heuristic_numt_risk"] in {"low", "moderate", "high"}
    assert "formal NUMT classifier" in outputs["report_path"].read_text(encoding="utf-8")
