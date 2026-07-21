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


def test_empty_alignment_preserves_all_deletion_table_schemas(tmp_path: Path) -> None:
    outputs = run_deletion_fixture(tmp_path, [])

    expected_columns = {
        "events_path": (
            "read_name",
            "event_start",
            "event_end",
            "deletion_size",
            "event_bin_start",
            "event_bin_end",
            "is_primary_read",
            "has_sa_tag",
        ),
        "clusters_path": (
            "event_bin_start",
            "event_bin_end",
            "supporting_reads",
            "median_deletion_size",
            "min_deletion_size",
            "max_deletion_size",
            "support_fraction_primary",
        ),
        "reads_path": (
            "read_name",
            "has_large_deletion",
            "is_supplementary",
            "has_sa_tag",
        ),
    }
    for output_name, columns in expected_columns.items():
        table = pd.read_csv(outputs[output_name], sep="\t")
        assert tuple(table.columns) == columns
        assert table.empty


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
    clusters = pd.read_csv(outputs["clusters_path"], sep="\t")
    report = outputs["report_path"].read_text(encoding="utf-8")

    assert int(float(summary["primary_reads"])) == 2
    assert int(float(summary["reads_with_supplementary_or_SA"])) == 1
    assert int(float(summary["reads_with_large_deletion"])) == 0
    assert int(float(summary["candidate_deletion_clusters"])) == 0
    assert pd.read_csv(outputs["events_path"], sep="\t").empty
    read_flags = pd.read_csv(outputs["reads_path"], sep="\t")
    assert tuple(read_flags.columns) == (
        "read_name",
        "has_large_deletion",
        "is_supplementary",
        "has_sa_tag",
    )
    assert clusters.empty
    assert "Only CIGAR deletion operations meeting the configured minimum size" in report
    assert "Supplementary-alignment status and SA tags are summarized separately" in report
    assert "do not create bin support on their own" in report


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
    assert events[
        [
            "event_start",
            "event_end",
            "deletion_size",
            "event_bin_start",
            "event_bin_end",
        ]
    ].drop_duplicates().to_dict("records") == [
        {
            "event_start": 6,
            "event_end": 105,
            "deletion_size": 100,
            "event_bin_start": 0,
            "event_bin_end": 100,
        }
    ]
    assert clusters["supporting_reads"].tolist() == [1]
    assert "Qualifying CIGAR-deletion bins" in report
    assert "Supplementary-alignment status and SA tags are summarized separately" in report
    assert "structural screen" in report
    assert "rather than a finalized SV caller output" in report


def test_primary_support_fraction_excludes_supplementary_only_read_names(tmp_path: Path) -> None:
    deletion_cigar = ((0, 5), (2, 100), (0, 5))
    outputs = run_deletion_fixture(
        tmp_path,
        [
            ReadSpec("primary-support", "MT", 0, "A" * 10, cigar=deletion_cigar),
            ReadSpec("supplementary-only-a", "MT", 0, "A" * 10, flag=2048, cigar=deletion_cigar),
            ReadSpec("supplementary-only-b", "MT", 0, "A" * 10, flag=2048, cigar=deletion_cigar),
        ],
    )
    summary = metric_map(outputs["summary_path"])
    events = pd.read_csv(outputs["events_path"], sep="\t")
    clusters = pd.read_csv(outputs["clusters_path"], sep="\t")
    report = outputs["report_path"].read_text(encoding="utf-8")

    assert int(float(summary["primary_reads"])) == 1
    assert int(float(summary["reads_with_large_deletion"])) == 3
    assert len(events) == 3
    assert clusters["supporting_reads"].tolist() == [3]
    assert clusters["support_fraction_primary"].tolist() == [1.0]
    assert clusters["support_fraction_primary"].between(0.0, 1.0).all()
    assert float(summary["max_support_fraction_primary"]) == 1.0
    assert "supplementary-only records remain in the event evidence" in report
    assert "cannot make this fraction exceed one" in report
