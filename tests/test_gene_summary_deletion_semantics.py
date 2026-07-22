from __future__ import annotations

from pathlib import Path

import pandas as pd

from mito_overview.steps.mito_gene_summary import SITE_DETAIL_COLUMNS, run_step

from ._helpers import metric_map


def test_cluster_overlap_uses_exact_member_events_not_bin_anchors(tmp_path: Path) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    pd.DataFrame(
        [
            {
                "feature_type": "gene",
                "gene_name": "MT-INSIDE-EVENT",
                "gene_biotype": "protein_coding",
                "start": 5,
                "end": 8,
                "strand": "+",
                "phase": ".",
            },
            {
                "feature_type": "gene",
                "gene_name": "MT-BIN-ONLY",
                "gene_biotype": "protein_coding",
                "start": 95,
                "end": 100,
                "strand": "+",
                "phase": ".",
            },
        ]
    ).to_csv(summary_dir / "mito_feature_catalog.tsv", sep="\t", index=False)
    pd.DataFrame(columns=SITE_DETAIL_COLUMNS).to_csv(
        summary_dir / "mito_feature_overlap_candidates.tsv", sep="\t", index=False
    )
    pd.DataFrame(
        [
            {
                "read_name": "event-1",
                "event_start": 1,
                "event_end": 10,
                "deletion_size": 10,
                "event_bin_start": 0,
                "event_bin_end": 100,
                "is_primary_read": 1,
                "has_sa_tag": 0,
            }
        ]
    ).to_csv(summary_dir / "mito_deletion_events.tsv", sep="\t", index=False)
    pd.DataFrame(
        [
            {
                "event_bin_start": 0,
                "event_bin_end": 100,
                "supporting_reads": 1,
                "median_deletion_size": 10,
                "min_deletion_size": 10,
                "max_deletion_size": 10,
                "support_fraction_primary": 0.25,
            }
        ]
    ).to_csv(summary_dir / "mito_deletion_clusters.tsv", sep="\t", index=False)

    outputs = run_step(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="DELETION-SEMANTICS",
        mt_contig="MT",
        mt_length=200,
    )

    summary = pd.read_csv(outputs["summary_path"], sep="\t").set_index("feature_label")
    run_summary = metric_map(Path(outputs["run_summary_path"]))

    inside = summary.loc["MT-INSIDE-EVENT"]
    bin_only = summary.loc["MT-BIN-ONLY"]
    assert inside["deletion_event_overlaps"] == 1
    assert inside["deletion_cluster_overlaps"] == 1
    assert inside["max_cluster_support_fraction_primary"] == 0.25
    assert bin_only["deletion_event_overlaps"] == 0
    assert bin_only["deletion_cluster_overlaps"] == 0
    assert bin_only["max_cluster_support_fraction_primary"] == 0.0
    assert run_summary["deletion_cluster_overlap_method"] == "exact_member_event_intervals"
    assert run_summary["deletion_cluster_member_intervals_loaded"] == "1"
    assert run_summary["deletion_clusters_evaluable"] == "1"
    report = Path(outputs["report_path"]).read_text(encoding="utf-8")
    assert "breakpoint-bin anchors are not treated as biological deletion intervals" in report
