from __future__ import annotations

from pathlib import Path

import pandas as pd

from mito_overview.steps.mito_deletions import run_step

from ._helpers import ReadSpec, metric_map, write_alignment


def run_deletion_fixture(tmp_path: Path, reads: list[ReadSpec]) -> dict[str, Path]:
    bam = write_alignment(tmp_path / "deletions.bam", {"MT": 500}, reads)
    return run_step(
        bam=bam,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="TOY-DEL",
        mt_contig="MT",
        mt_length=500,
        min_deletion_size=100,
    )


def test_split_alignment_summary_counts_unique_read_names(tmp_path: Path) -> None:
    outputs = run_deletion_fixture(
        tmp_path,
        [
            ReadSpec("ordinary", "MT", 0, "A" * 10),
            ReadSpec(
                "split",
                "MT",
                20,
                "A" * 10,
                tags=(("SA", "MT,51,+,10M,60,0;"),),
            ),
            ReadSpec("split", "MT", 50, "A" * 10, flag=2048),
            ReadSpec("split", "MT", 100, "A" * 10, flag=2048),
        ],
    )
    summary = metric_map(outputs["summary_path"])
    assert int(float(summary["primary_reads"])) == 2
    assert int(float(summary["reads_with_supplementary_or_SA"])) == 1
    assert int(float(summary["reads_with_large_deletion"])) == 0
    assert pd.read_csv(outputs["events_path"], sep="\t").empty


def test_large_deletion_read_count_deduplicates_alignment_segments(tmp_path: Path) -> None:
    deletion_cigar = ((0, 5), (2, 100), (0, 5))
    outputs = run_deletion_fixture(
        tmp_path,
        [
            ReadSpec(
                "split-deletion",
                "MT",
                0,
                "A" * 10,
                cigar=deletion_cigar,
                tags=(("SA", "MT,1,+,5M100D5M,60,0;"),),
            ),
            ReadSpec(
                "split-deletion",
                "MT",
                0,
                "A" * 10,
                flag=2048,
                cigar=deletion_cigar,
            ),
        ],
    )
    summary = metric_map(outputs["summary_path"])
    events = pd.read_csv(outputs["events_path"], sep="\t")
    clusters = pd.read_csv(outputs["clusters_path"], sep="\t")
    report = outputs["report_path"].read_text(encoding="utf-8")

    assert int(float(summary["primary_reads"])) == 1
    assert int(float(summary["reads_with_large_deletion"])) == 1
    assert int(float(summary["reads_with_supplementary_or_SA"])) == 1
    assert len(events) == 2
    assert clusters["supporting_reads"].tolist() == [1]
    assert "structural screen" in report
    assert "rather than a finalized SV caller output" in report
