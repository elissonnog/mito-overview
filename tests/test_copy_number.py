from __future__ import annotations

from pathlib import Path
import shutil

import pandas as pd
import pytest
import pysam

from mito_overview.config import PipelineConfig
from mito_overview.steps.mito_copy_number import run_step
from mito_overview.workflow import run_pipeline

from ._helpers import ReadSpec, bam_from_sam, metric_map, write_alignment, write_fasta


def write_mito_depth(summary_dir: Path, depth: int, length: int = 10) -> None:
    summary_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"position": range(1, length + 1), "depth": [depth] * length}).to_csv(
        summary_dir / "mito_depth_per_base.tsv",
        sep="\t",
        index=False,
    )


def test_known_100_over_10_depth_ratio_is_10(tmp_path: Path) -> None:
    fixture = Path(__file__).parents[1] / "examples" / "synthetic_data" / "TOY-WGS-001"
    ref = tmp_path / "tiny_GRCh38_wgs.fa"
    shutil.copyfile(fixture / "tiny_GRCh38_wgs.fa", ref)
    pysam.faidx(str(ref))
    bam = bam_from_sam(fixture / "tiny_wgs.sam", tmp_path / "known_wgs.bam")
    summary = tmp_path / "summary"
    write_mito_depth(summary, 100)
    outputs = run_step(
        align_file=bam,
        align_mode="bam",
        ref_fasta=ref,
        summary_dir=summary,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="TOY-WGS-001",
        mt_contig="MT",
        mt_length=10,
        species="human",
        reference_scope="whole_genome",
        window_size=10,
        window_count=5,
    )
    metrics = metric_map(outputs["summary_path"])
    assert outputs["status"] == "ok"
    assert float(metrics["mt_mean_depth"]) == 100.0
    assert float(metrics["nuclear_window_mean_depth"]) == 10.0
    assert float(metrics["mt_to_nuclear_depth_ratio"]) == 10.0
    assert metrics["nuclear_windows_requested"] == "5"
    assert metrics["nuclear_windows_valid"] == "5"
    expected = metric_map(fixture / "expected_copy_proxy.tsv")
    for metric, value in expected.items():
        assert metrics[metric] == value


@pytest.mark.parametrize("scope", ["mt_only", "custom"])
def test_missing_nuclear_context_is_na_not_zero(scope: str, tmp_path: Path) -> None:
    case = tmp_path / scope
    case.mkdir()
    ref = write_fasta(case / "mt.fa", {"MT": "A" * 10})
    bam = write_alignment(case / "mt.bam", {"MT": 10}, [ReadSpec("mt", "MT", 0, "A" * 10)])
    summary = case / "summary"
    write_mito_depth(summary, 100)
    outputs = run_step(
        align_file=bam,
        align_mode="bam",
        ref_fasta=ref,
        summary_dir=summary,
        figure_dir=case / "figures",
        report_dir=case / "reports",
        sample_id="S1",
        mt_contig="MT",
        mt_length=10,
        species="human",
        reference_scope=scope,
        window_size=10,
        window_count=5,
    )
    metrics = metric_map(outputs["summary_path"])
    assert outputs["status"] == "not_evaluable"
    assert metrics["reason_code"] == "no_valid_nuclear_windows"
    assert metrics["mt_to_nuclear_depth_ratio"] == ""
    assert metrics["nuclear_windows_valid"] == "0"


def test_zero_nuclear_denominator_is_na(tmp_path: Path) -> None:
    contigs = {"MT": "A" * 10, **{f"chr{i}": "A" * 10 for i in range(1, 23)}}
    ref = write_fasta(tmp_path / "zero_GRCh38.fa", contigs)
    bam = write_alignment(
        tmp_path / "zero.bam",
        {key: 10 for key in contigs},
        [ReadSpec("mt", "MT", 0, "A" * 10)],
    )
    summary = tmp_path / "summary"
    write_mito_depth(summary, 100)
    outputs = run_step(
        align_file=bam,
        align_mode="bam",
        ref_fasta=ref,
        summary_dir=summary,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="S1",
        mt_contig="MT",
        mt_length=10,
        species="human",
        reference_scope="whole_genome",
        window_size=10,
        window_count=5,
    )
    metrics = metric_map(outputs["summary_path"])
    assert outputs["status"] == "not_evaluable"
    assert metrics["reason_code"] == "no_valid_nuclear_windows"
    assert metrics["nuclear_window_mean_depth"] == ""
    assert metrics["mt_to_nuclear_depth_ratio"] == ""
    assert metrics["nuclear_windows_valid"] == "0"


def test_missing_mito_depth_evidence_is_na_not_zero(tmp_path: Path) -> None:
    contigs = {"MT": "A" * 10, **{f"chr{i}": "A" * 10 for i in range(1, 23)}}
    ref = write_fasta(tmp_path / "missing_depth_GRCh38.fa", contigs)
    reads = [
        ReadSpec(f"nuclear-{index}", "chr1", 0, "A" * 10)
        for index in range(10)
    ]
    bam = write_alignment(
        tmp_path / "missing_depth.bam",
        {key: 10 for key in contigs},
        reads,
    )
    outputs = run_step(
        align_file=bam,
        align_mode="bam",
        ref_fasta=ref,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="S1",
        mt_contig="MT",
        mt_length=10,
        species="human",
        reference_scope="whole_genome",
        window_size=10,
        window_count=1,
    )
    metrics = metric_map(outputs["summary_path"])
    assert outputs["status"] == "not_evaluable"
    assert metrics["reason_code"] == "no_mito_depth_evidence"
    assert metrics["mt_mean_depth"] == ""
    assert metrics["nuclear_window_mean_depth"] == "10.0"
    assert metrics["mt_to_nuclear_depth_ratio"] == ""


def test_targeted_mt_profile_remains_not_applicable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = write_fasta(tmp_path / "mt.fa", {"MT": "A" * 10})
    bam = write_alignment(tmp_path / "mt.bam", {"MT": 10}, [ReadSpec("mt", "MT", 0, "A" * 10)])
    config = PipelineConfig.from_mapping(
        {
            "WORK_ROOT": str(tmp_path / "runs"),
            "RUN_NAME": "targeted",
            "SAMPLE_ID": "S1",
            "REF_FASTA": str(ref),
            "SOURCE_ALIGN_FILE": str(bam),
            "MT_CONTIG": "MT",
            "ASSAY_TYPE": "targeted_mt",
        }
    )
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")
    result = run_pipeline(config, steps=["copy_number"])
    assert result[0].status == "not_applicable"
    summary = metric_map(tmp_path / "runs" / "targeted" / "output" / "summary" / "mito_copy_number_summary.tsv")
    assert summary["status"] == "not_applicable"
