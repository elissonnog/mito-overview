from __future__ import annotations

from pathlib import Path

import pandas as pd
import pysam

from mito_overview.steps.mito_identity_qc import FINGERPRINT_COLUMNS, run_step

from ._helpers import metric_map


def write_vcf(path: Path, records: list[tuple[int, str, str]]) -> None:
    lines = [
        "##fileformat=VCFv4.2",
        "##contig=<ID=MT,length=60>",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    ]
    lines.extend(f"MT\t{pos}\t.\t{ref}\t{alt}\t60\tPASS\t." for pos, ref, alt in records)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def test_identity_qc_header_only_input_without_summary_is_not_evaluable(
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

    assert outputs["status"] == "not_evaluable"
    assert summary["status"] == "not_evaluable"
    assert summary["fingerprint_status"] == "not_evaluable"
    assert summary["fingerprint_reason_code"] == "heteroplasmy_summary_missing"
    assert summary["major_fingerprint_sites"] == ""
    assert summary["heteroplasmy_summary_status"] == "not_evaluable"
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


def test_identity_qc_unindexed_and_indexed_vcfs_have_the_same_known_answer(
    tmp_path: Path,
) -> None:
    phased_plain = tmp_path / "phased.vcf"
    unphased_plain = tmp_path / "unphased.vcf"
    write_vcf(phased_plain, [(10, "A", "C"), (20, "G", "A")])
    write_vcf(unphased_plain, [(10, "A", "C"), (30, "T", "G")])

    expected = {
        "variant_comparison_status": "ok",
        "phased_mt_variant_records": "2",
        "np_mt_variant_records": "2",
        "shared_mt_variant_records": "1",
        "phased_only_mt_variant_records": "1",
        "np_only_mt_variant_records": "1",
    }

    plain = run_step(
        summary_dir=tmp_path / "plain" / "summary",
        figure_dir=tmp_path / "plain" / "figures",
        report_dir=tmp_path / "plain" / "report",
        sample_id="UNINDEXED-VCF",
        mt_contig="MT",
        phased_snp_vcf=phased_plain,
        np_snp_vcf=unphased_plain,
    )
    assert {key: metric_map(Path(plain["summary_path"]))[key] for key in expected} == expected

    phased_indexed = Path(
        pysam.tabix_index(str(phased_plain), preset="vcf", force=True, keep_original=True)
    )
    unphased_indexed = Path(
        pysam.tabix_index(str(unphased_plain), preset="vcf", force=True, keep_original=True)
    )
    indexed = run_step(
        summary_dir=tmp_path / "indexed" / "summary",
        figure_dir=tmp_path / "indexed" / "figures",
        report_dir=tmp_path / "indexed" / "report",
        sample_id="INDEXED-VCF",
        mt_contig="MT",
        phased_snp_vcf=phased_indexed,
        np_snp_vcf=unphased_indexed,
    )
    assert {key: metric_map(Path(indexed["summary_path"]))[key] for key in expected} == expected


def test_identity_qc_malformed_vcf_is_not_a_successful_zero_comparison(
    tmp_path: Path,
    capsys,
) -> None:
    malformed = tmp_path / "malformed.vcf"
    malformed.write_text("this is not a VCF\n", encoding="utf-8")
    valid = tmp_path / "valid.vcf"
    write_vcf(valid, [(10, "A", "C")])

    outputs = run_step(
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="MALFORMED-VCF",
        mt_contig="MT",
        phased_snp_vcf=malformed,
        np_snp_vcf=valid,
    )
    summary = metric_map(Path(outputs["summary_path"]))

    assert summary["variant_comparison_status"] == "not_evaluable"
    assert summary["variant_comparison_reason_code"].startswith(
        "paired_variant_vcf_unreadable[phased:variant_vcf_unreadable"
    )
    assert summary["phased_mt_variant_records"] == ""
    assert summary["shared_mt_variant_records"] == ""
    stdout = capsys.readouterr().out
    assert "variant comparison unavailable status=not_evaluable" in stdout
    assert "vcf_overlap shared=0" not in stdout
