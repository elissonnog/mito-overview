from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ._helpers import metric_map


REPO_ROOT = Path(__file__).parents[1]
EXPECTED_ROOT = REPO_ROOT / "examples" / "expected_reports"
PUBLIC_ROOT = REPO_ROOT / "examples" / "public_validation"


@pytest.mark.parametrize(
    ("bundle", "sample_id"),
    [("TOY-001_output", "TOY-001"), ("TOY-SR-001_output", "TOY-SR-001")],
)
def test_tracked_mito_bed_is_zero_based_half_open(bundle: str, sample_id: str) -> None:
    bed = EXPECTED_ROOT / bundle / "subset" / f"{sample_id}.MT.bed"
    assert bed.read_bytes() == b"MT\t0\t60\n"


def test_tracked_long_read_bundle_uses_v030_status_and_allele_contracts() -> None:
    root = EXPECTED_ROOT / "TOY-001_output"
    copy_metrics = metric_map(root / "summary" / "mito_copy_number_summary.tsv")
    assert copy_metrics["status"] == "not_evaluable"
    assert copy_metrics["reason_code"] == "no_valid_nuclear_windows"
    assert copy_metrics["mt_to_nuclear_depth_ratio"] == ""
    assert copy_metrics["nuclear_windows_requested"] == "5"
    assert copy_metrics["nuclear_windows_valid"] == "0"

    numt_metrics = metric_map(root / "summary" / "mito_numt_qc_summary.tsv")
    assert numt_metrics["reference_scope"] == "mt_only"
    assert numt_metrics["numt_interpretation_status"] == "not_evaluable"
    assert numt_metrics["reason_code"] == "reference_scope_mt_only"
    assert numt_metrics["heuristic_numt_risk"] == "not_evaluable"

    allele_metrics = metric_map(root / "summary" / "mito_heteroplasmy_summary.tsv")
    assert allele_metrics["allele_counting_method"] == "pysam_pileup_shared_filter_v1"
    assert allele_metrics["allele_max_depth"] == "0"
    candidates = pd.read_csv(root / "summary" / "mito_heteroplasmy_candidates.tsv", sep="\t")
    assert "alt_allele_fraction" in candidates.columns
    assert "heteroplasmy_fraction" in candidates.columns
    assert (candidates["alt_count"] == candidates["alt_forward"] + candidates["alt_reverse"]).all()


def test_tracked_short_read_bundle_preserves_not_applicable_states() -> None:
    root = EXPECTED_ROOT / "TOY-SR-001_output" / "summary"
    for filename in (
        "mito_copy_number_summary.tsv",
        "mito_deletion_summary.tsv",
        "mito_numt_qc_summary.tsv",
        "mito_methylation_exploratory_summary.tsv",
    ):
        assert metric_map(root / filename)["status"] == "not_applicable"


@pytest.mark.parametrize("bundle", ["TOY-001_output", "TOY-SR-001_output"])
def test_tracked_bundle_keeps_complete_fourteen_page_pattern(bundle: str) -> None:
    report_dir = EXPECTED_ROOT / bundle / "report"
    pages = sorted(report_dir.glob("*.html"))
    assert len(pages) == 14
    assert {int(page.name.split("_", 1)[0]) for page in pages} == set(range(1, 15))
    assert all(page.read_text(encoding="utf-8").endswith("</html>\n") for page in pages)


def test_tracked_gm12878_absent_methylation_tracks_are_not_reported_present() -> None:
    summary = (
        PUBLIC_ROOT
        / "GM12878_ONT_longread"
        / "summary"
        / "mito_methylation_exploratory_summary.tsv"
    )
    metrics = metric_map(summary)
    assert metrics["status"] == "not_configured"
    assert metrics["reason_code"] == "no_bedmethyl_sidecars_configured"
    for key in (
        "np_track_input_present",
        "hp1_track_input_present",
        "hp2_track_input_present",
        "ungrouped_track_input_present",
    ):
        assert metrics[key] == "0"


def test_tracked_gm12878_deletion_screen_scope_is_explicit() -> None:
    findings = pd.read_csv(
        PUBLIC_ROOT / "GM12878_ONT_longread" / "GM12878_ONT_longread_key_findings.tsv",
        sep="\t",
        dtype=str,
        keep_default_na=False,
    )
    values = dict(zip(findings["metric"], findings["value"], strict=True))
    assert values["deletion_screen_method"] == (
        "CIGAR-deletion candidate screen; supplementary/SA evidence summarized separately"
    )
