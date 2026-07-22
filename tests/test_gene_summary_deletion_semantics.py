from __future__ import annotations

from pathlib import Path

import pandas as pd

from mito_overview.steps.mito_gene_summary import SITE_DETAIL_COLUMNS, run_step

from ._helpers import metric_map


def write_minimal_feature_inputs(summary_dir: Path, *, include_overlap: bool = True) -> None:
    pd.DataFrame(
        [
            {
                "feature_type": "gene",
                "gene_name": "MT-TEST",
                "gene_biotype": "protein_coding",
                "start": 1,
                "end": 100,
                "strand": "+",
                "phase": ".",
            }
        ]
    ).to_csv(summary_dir / "mito_feature_catalog.tsv", sep="\t", index=False)
    if include_overlap:
        pd.DataFrame(columns=SITE_DETAIL_COLUMNS).to_csv(
            summary_dir / "mito_feature_overlap_candidates.tsv", sep="\t", index=False
        )


def test_missing_cosegregation_is_na_but_header_only_table_is_observed_zero(
    tmp_path: Path,
) -> None:
    missing_dir = tmp_path / "missing" / "summary"
    missing_dir.mkdir(parents=True)
    write_minimal_feature_inputs(missing_dir)
    missing_outputs = run_step(
        summary_dir=missing_dir,
        figure_dir=tmp_path / "missing" / "figures",
        report_dir=tmp_path / "missing" / "reports",
        sample_id="COSEG-MISSING",
        mt_contig="MT",
        mt_length=200,
    )
    missing_summary = pd.read_csv(missing_outputs["summary_path"], sep="\t")
    missing_run = metric_map(Path(missing_outputs["run_summary_path"]))

    assert missing_outputs["status"] == "ok"
    assert missing_run["cosegregation_evidence_status"] == "not_configured"
    assert missing_run["cosegregation_evidence_reason_code"] == "cosegregation_selected_sites_missing"
    assert missing_run["selected_coseg_positions_loaded"] == ""
    assert missing_summary["selected_coseg_sites"].isna().all()

    observed_dir = tmp_path / "observed" / "summary"
    observed_dir.mkdir(parents=True)
    write_minimal_feature_inputs(observed_dir)
    pd.DataFrame(columns=["site_label", "position"]).to_csv(
        observed_dir / "mito_cosegregation_selected_sites.tsv", sep="\t", index=False
    )
    observed_outputs = run_step(
        summary_dir=observed_dir,
        figure_dir=tmp_path / "observed" / "figures",
        report_dir=tmp_path / "observed" / "reports",
        sample_id="COSEG-ZERO",
        mt_contig="MT",
        mt_length=200,
    )
    observed_summary = pd.read_csv(observed_outputs["summary_path"], sep="\t")
    observed_run = metric_map(Path(observed_outputs["run_summary_path"]))

    assert observed_outputs["status"] == "ok"
    assert observed_run["cosegregation_evidence_status"] == "ok"
    assert observed_run["selected_coseg_positions_loaded"] == "0"
    assert observed_summary["selected_coseg_sites"].eq(0).all()


def test_gene_summary_without_any_analytical_evidence_is_not_evaluable(
    tmp_path: Path,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    write_minimal_feature_inputs(summary_dir, include_overlap=False)

    outputs = run_step(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="GENE-NO-EVIDENCE",
        mt_contig="MT",
        mt_length=200,
    )
    summary = pd.read_csv(outputs["summary_path"], sep="\t")
    run_summary = metric_map(Path(outputs["run_summary_path"]))

    assert outputs["status"] == "not_evaluable"
    assert run_summary["status"] == "not_evaluable"
    assert run_summary["reason_code"] == "no_evaluable_gene_summary_evidence"
    assert summary["candidate_sites"].isna().all()
    assert summary["selected_coseg_sites"].isna().all()
    assert summary["deletion_event_overlaps"].isna().all()


def test_gene_summary_propagates_non_evaluable_deletion_denominator(
    tmp_path: Path,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    write_minimal_feature_inputs(summary_dir)
    pd.DataFrame(
        [
            {"metric": "status", "value": "not_evaluable"},
            {"metric": "reason_code", "value": "no_primary_reads"},
        ]
    ).to_csv(summary_dir / "mito_deletion_summary.tsv", sep="\t", index=False)
    pd.DataFrame(
        [
            {
                "read_name": "supplementary-only",
                "event_start": 5,
                "event_end": 104,
                "deletion_size": 100,
                "event_bin_start": 0,
                "event_bin_end": 100,
                "is_primary_read": 0,
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
                "median_deletion_size": 100,
                "min_deletion_size": 100,
                "max_deletion_size": 100,
                "support_fraction_primary": pd.NA,
            }
        ]
    ).to_csv(summary_dir / "mito_deletion_clusters.tsv", sep="\t", index=False)

    outputs = run_step(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="DELETION-NO-DENOMINATOR",
        mt_contig="MT",
        mt_length=200,
    )
    summary = pd.read_csv(outputs["summary_path"], sep="\t")
    run_summary = metric_map(Path(outputs["run_summary_path"]))

    assert run_summary["deletion_evidence_status"] == "not_evaluable"
    assert run_summary["deletion_evidence_reason_code"] == "no_primary_reads"
    assert summary["deletion_event_overlaps"].isna().all()
    assert summary["deletion_cluster_overlaps"].isna().all()
    assert summary["max_cluster_support_fraction_primary"].isna().all()


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
