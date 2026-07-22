from __future__ import annotations

from pathlib import Path

import pandas as pd

from mito_overview.steps.mito_identity_qc import FINGERPRINT_COLUMNS, run_step

from ._helpers import metric_map


def test_populated_fingerprint_uses_the_same_canonical_schema_as_empty_states(
    tmp_path: Path,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    pd.DataFrame(
        [
            {
                "position": 10,
                "ref_base": "A",
                "alt_base": "C",
                "callable_depth": 120,
                "depth": 120,
                "alt_count": 114,
                "alt_allele_fraction": 0.95,
                "heteroplasmy_fraction": 0.95,
                "alt_forward": 57,
                "alt_reverse": 57,
                "A": 6,
                "C": 114,
                "G": 0,
                "T": 0,
            }
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_all_sites.tsv", sep="\t", index=False)
    pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "reason_code", "value": ""},
            {"metric": "callable_positions", "value": 1},
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)

    outputs = run_step(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="TOY-ID",
        mt_contig="MT",
        phased_snp_vcf=None,
        np_snp_vcf=None,
    )
    fingerprint = pd.read_csv(outputs["fingerprint_path"], sep="\t")

    assert fingerprint.columns.tolist() == FINGERPRINT_COLUMNS
    assert fingerprint.to_dict("records") == [
        {
            "position": 10,
            "ref_base": "A",
            "alt_base": "C",
            "alt_allele_fraction": 0.95,
            "heteroplasmy_fraction": 0.95,
            "depth": 120,
        }
    ]
    assert outputs["status"] == "ok"
    summary = metric_map(Path(outputs["summary_path"]))
    assert summary["heteroplasmy_summary_status"] == "ok"
    assert summary["heteroplasmy_summary_reason_code"] == ""


def test_identity_qc_without_any_evidence_is_not_evaluable(tmp_path: Path) -> None:
    outputs = run_step(
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="NO-ID-EVIDENCE",
        mt_contig="MT",
        phased_snp_vcf=None,
        np_snp_vcf=None,
    )
    summary = metric_map(Path(outputs["summary_path"]))

    assert outputs["status"] == "not_evaluable"
    assert summary["status"] == "not_evaluable"
    assert summary["reason_code"] == "no_evaluable_identity_evidence"
    assert summary["fingerprint_status"] == "not_evaluable"
    assert summary["variant_comparison_status"] == "not_configured"
    assert summary["formal_haplogroup_assignment_status"] == "not_configured"
    assert summary["major_fingerprint_sites"] == ""
    assert summary["shared_mt_variant_records"] == ""


def test_identity_qc_header_only_legacy_input_without_summary_is_observed_zero(
    tmp_path: Path,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    pd.DataFrame(columns=FINGERPRINT_COLUMNS).to_csv(
        summary_dir / "mito_heteroplasmy_all_sites.tsv", sep="\t", index=False
    )

    outputs = run_step(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="ZERO-ID-EVIDENCE",
        mt_contig="MT",
        phased_snp_vcf=None,
        np_snp_vcf=None,
    )
    summary = metric_map(Path(outputs["summary_path"]))

    assert outputs["status"] == "ok"
    assert summary["status"] == "ok"
    assert summary["fingerprint_status"] == "ok"
    assert summary["major_fingerprint_sites"] == "0"
    assert summary["heteroplasmy_summary_status"] == "not_configured"
    assert summary["heteroplasmy_summary_reason_code"] == "heteroplasmy_summary_missing"


def test_identity_qc_propagates_no_callable_positions_from_heteroplasmy(
    tmp_path: Path,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    pd.DataFrame(columns=FINGERPRINT_COLUMNS).to_csv(
        summary_dir / "mito_heteroplasmy_all_sites.tsv", sep="\t", index=False
    )
    pd.DataFrame(
        [
            {"metric": "status", "value": "not_evaluable"},
            {"metric": "reason_code", "value": "no_callable_positions"},
            {"metric": "callable_positions", "value": 0},
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)

    outputs = run_step(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="NO-CALLABLE-ID",
        mt_contig="MT",
        phased_snp_vcf=None,
        np_snp_vcf=None,
    )
    summary = metric_map(Path(outputs["summary_path"]))
    fingerprint = pd.read_csv(outputs["fingerprint_path"], sep="\t")

    assert outputs["status"] == "not_evaluable"
    assert summary["fingerprint_status"] == "not_evaluable"
    assert summary["fingerprint_reason_code"] == "no_callable_positions"
    assert summary["heteroplasmy_summary_status"] == "not_evaluable"
    assert summary["heteroplasmy_summary_reason_code"] == "no_callable_positions"
    assert summary["major_fingerprint_sites"] == ""
    assert fingerprint.columns.tolist() == FINGERPRINT_COLUMNS
    assert fingerprint.empty


def test_identity_qc_rejects_invalid_upstream_status_deterministically(
    tmp_path: Path,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    pd.DataFrame(columns=FINGERPRINT_COLUMNS).to_csv(
        summary_dir / "mito_heteroplasmy_all_sites.tsv", sep="\t", index=False
    )
    pd.DataFrame([{"metric": "status", "value": "unknown"}]).to_csv(
        summary_dir / "mito_heteroplasmy_summary.tsv", sep="\t", index=False
    )

    outputs = run_step(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="INVALID-HET-STATUS",
        mt_contig="MT",
        phased_snp_vcf=None,
        np_snp_vcf=None,
    )
    summary = metric_map(Path(outputs["summary_path"]))

    assert outputs["status"] == "not_evaluable"
    assert summary["fingerprint_status"] == "not_evaluable"
    assert summary["fingerprint_reason_code"] == "heteroplasmy_summary_status_invalid"
    assert summary["major_fingerprint_sites"] == ""


def test_identity_qc_rejects_ok_summary_without_measured_observations(
    tmp_path: Path,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    pd.DataFrame(columns=FINGERPRINT_COLUMNS).to_csv(
        summary_dir / "mito_heteroplasmy_all_sites.tsv", sep="\t", index=False
    )
    pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "reason_code", "value": ""},
            {"metric": "callable_positions", "value": 1},
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)

    outputs = run_step(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="INCONSISTENT-HET-EVIDENCE",
        mt_contig="MT",
        phased_snp_vcf=None,
        np_snp_vcf=None,
    )
    summary = metric_map(Path(outputs["summary_path"]))

    assert outputs["status"] == "not_evaluable"
    assert summary["heteroplasmy_summary_status"] == "ok"
    assert summary["fingerprint_status"] == "not_evaluable"
    assert (
        summary["fingerprint_reason_code"]
        == "heteroplasmy_all_sites_no_measured_observations"
    )
    assert summary["major_fingerprint_sites"] == ""
