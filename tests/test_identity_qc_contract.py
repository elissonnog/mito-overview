from __future__ import annotations

from pathlib import Path

import pandas as pd
import pysam
import pytest

from mito_overview.steps.mito_identity_qc import (
    FINGERPRINT_COLUMNS,
    SNP_SELECTION_CONTRACT,
    load_mt_variants,
    run_step,
)

from ._helpers import metric_map


def write_vcf(path: Path, records: list[tuple[int, str, str]]) -> None:
    lines = [
        "##fileformat=VCFv4.2",
        "##contig=<ID=MT,length=60>",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    ]
    lines.extend(f"MT\t{pos}\t.\t{ref}\t{alt}\t60\tPASS\t." for pos, ref, alt in records)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mixed_sample_vcf(path: Path) -> None:
    lines = [
        "##fileformat=VCFv4.2",
        "##contig=<ID=MT,length=60>",
        "##contig=<ID=chr1,length=60>",
        '##FILTER=<ID=LowQual,Description="Low quality">',
        '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">',
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\tS2",
        "MT\t10\t.\tA\tC\t60\tPASS\t.\tGT\t0/1\t0/0",
        "MT\t11\t.\tG\tA\t60\tLowQual\t.\tGT\t0/1\t0/0",
        "MT\t12\t.\tT\tC\t60\tPASS\t.\tGT\t./.\t0/0",
        "MT\t13\t.\tA\tAT\t60\tPASS\t.\tGT\t0/1\t0/0",
        "MT\t14\t.\tN\tC\t60\tPASS\t.\tGT\t0/1\t0/0",
        "MT\t15\t.\tA\t<DEL>\t60\tPASS\t.\tGT\t0/1\t0/0",
        "MT\t16\t.\tA\tC,G\t60\tPASS\t.\tGT\t0/2\t0/0",
        "MT\t17\t.\tC\tT,G\t60\t.\t.\tGT\t1/.\t0/0",
        "MT\t18\t.\tG\tA,C\t60\tPASS\t.\tGT\t1/2\t0/0",
        "MT\t19\t.\tA\tA\t60\tPASS\t.\tGT\t0/1\t0/0",
        "MT\t20\t.\tAC\tGT\t60\tPASS\t.\tGT\t0/1\t0/0",
        "MT\t21\t.\tA\t.\t60\tPASS\t.\tGT\t./.\t0/0",
        "chr1\t10\t.\tA\tC\t60\tPASS\t.\tGT\t0/1\t0/0",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mixed_site_only_vcf(path: Path) -> None:
    lines = [
        "##fileformat=VCFv4.2",
        "##contig=<ID=MT,length=60>",
        '##FILTER=<ID=LowQual,Description="Low quality">',
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        "MT\t10\t.\tA\tC\t60\tPASS\t.",
        "MT\t20\t.\tG\tT\t60\t.\t.",
        "MT\t30\t.\tA\tAT\t60\tPASS\t.",
        "MT\t40\t.\tC\tG\t60\tLowQual\t.",
        "MT\t50\t.\tN\tA\t60\tPASS\t.",
        "MT\t55\t.\tT\tA,C\t60\tPASS\t.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_sample_vcf_retains_only_called_pass_canonical_snvs(tmp_path: Path) -> None:
    vcf = tmp_path / "mixed_sample.vcf"
    write_mixed_sample_vcf(vcf)

    variants, status, reason, counts = load_mt_variants(vcf, "MT")

    assert status == "ok"
    assert reason == ""
    assert variants.to_dict("records") == [
        {"position": 10, "ref": "A", "alt": "C"},
        {"position": 16, "ref": "A", "alt": "G"},
        {"position": 17, "ref": "C", "alt": "T"},
        {"position": 18, "ref": "G", "alt": "A"},
        {"position": 18, "ref": "G", "alt": "C"},
    ]
    assert counts.mt_records_total == 12
    assert counts.records_without_alt == 1
    assert counts.sample_columns == 2
    assert counts.alt_alleles_total == 14
    assert counts.retained_alt_alleles == 5
    assert counts.unique_retained_snvs == 5
    assert counts.excluded_filtered_alt_alleles == 1
    assert counts.excluded_non_snv_alt_alleles == 2
    assert counts.excluded_noncanonical_alt_alleles == 2
    assert counts.excluded_reference_equal_alt_alleles == 1
    assert counts.excluded_uncalled_alt_alleles == 3
    assert (
        counts.retained_alt_alleles
        + counts.excluded_filtered_alt_alleles
        + counts.excluded_non_snv_alt_alleles
        + counts.excluded_noncanonical_alt_alleles
        + counts.excluded_reference_equal_alt_alleles
        + counts.excluded_uncalled_alt_alleles
        == counts.alt_alleles_total
    )


def test_site_only_vcf_retains_pass_canonical_snvs_without_genotypes(
    tmp_path: Path,
) -> None:
    vcf = tmp_path / "mixed_site_only.vcf"
    write_mixed_site_only_vcf(vcf)

    variants, status, reason, counts = load_mt_variants(vcf, "MT")

    assert status == "ok"
    assert reason == ""
    assert variants.to_dict("records") == [
        {"position": 10, "ref": "A", "alt": "C"},
        {"position": 20, "ref": "G", "alt": "T"},
        {"position": 55, "ref": "T", "alt": "A"},
        {"position": 55, "ref": "T", "alt": "C"},
    ]
    assert counts.mt_records_total == 6
    assert counts.sample_columns == 0
    assert counts.alt_alleles_total == 7
    assert counts.retained_alt_alleles == 4
    assert counts.unique_retained_snvs == 4
    assert counts.excluded_filtered_alt_alleles == 1
    assert counts.excluded_non_snv_alt_alleles == 1
    assert counts.excluded_noncanonical_alt_alleles == 1
    assert counts.excluded_uncalled_alt_alleles == 0


def test_identity_summary_records_selection_counts_and_exact_retained_snv_overlap(
    tmp_path: Path,
) -> None:
    phased = tmp_path / "phased_mixed.vcf"
    unphased = tmp_path / "unphased_site_only.vcf"
    write_mixed_sample_vcf(phased)
    write_mixed_site_only_vcf(unphased)

    outputs = run_step(
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="MIXED-VCF",
        mt_contig="MT",
        phased_snp_vcf=phased,
        np_snp_vcf=unphased,
    )
    summary = metric_map(Path(outputs["summary_path"]))
    comparison = pd.read_csv(outputs["compare_path"], sep="\t")
    report = Path(outputs["report_path"]).read_text(encoding="utf-8")

    expected_metrics = {
        "variant_comparison_status": "ok",
        "identity_snp_selection_contract": SNP_SELECTION_CONTRACT,
        "phased_mt_vcf_records_total": "12",
        "phased_mt_vcf_records_without_alt": "1",
        "phased_mt_vcf_sample_columns": "2",
        "phased_mt_vcf_alt_alleles_total": "14",
        "phased_mt_vcf_alt_alleles_retained": "5",
        "phased_mt_vcf_unique_retained_snvs": "5",
        "phased_mt_vcf_alt_alleles_excluded_filtered": "1",
        "phased_mt_vcf_alt_alleles_excluded_non_snv": "2",
        "phased_mt_vcf_alt_alleles_excluded_noncanonical": "2",
        "phased_mt_vcf_alt_alleles_excluded_reference_equal": "1",
        "phased_mt_vcf_alt_alleles_excluded_uncalled": "3",
        "unphased_mt_vcf_records_total": "6",
        "unphased_mt_vcf_sample_columns": "0",
        "unphased_mt_vcf_alt_alleles_total": "7",
        "unphased_mt_vcf_alt_alleles_retained": "4",
        "unphased_mt_vcf_unique_retained_snvs": "4",
        "unphased_mt_vcf_alt_alleles_excluded_filtered": "1",
        "unphased_mt_vcf_alt_alleles_excluded_non_snv": "1",
        "unphased_mt_vcf_alt_alleles_excluded_noncanonical": "1",
        "unphased_mt_vcf_alt_alleles_excluded_uncalled": "0",
        "shared_retained_mt_snvs": "1",
        "phased_only_retained_mt_snvs": "4",
        "unphased_only_retained_mt_snvs": "3",
    }
    assert {key: summary[key] for key in expected_metrics} == expected_metrics
    assert comparison.to_dict("records") == [
        {"membership": "shared", "position": 10, "ref": "A", "alt": "C"},
        {"membership": "phased_only", "position": 16, "ref": "A", "alt": "G"},
        {"membership": "phased_only", "position": 17, "ref": "C", "alt": "T"},
        {"membership": "phased_only", "position": 18, "ref": "G", "alt": "A"},
        {"membership": "phased_only", "position": 18, "ref": "G", "alt": "C"},
        {"membership": "unphased_only", "position": 20, "ref": "G", "alt": "T"},
        {"membership": "unphased_only", "position": 55, "ref": "T", "alt": "A"},
        {"membership": "unphased_only", "position": 55, "ref": "T", "alt": "C"},
    ]
    assert "exact overlap between retained canonical mtDNA SNVs" in report
    assert "FILTER PASS or '.'" in report


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


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("position", 10.5, "invalid position"),
        ("depth", 120.5, "invalid position, depth"),
        ("alt_allele_fraction", 1.1, "invalid position, depth, or allele-fraction"),
        ("alt_base", "A", "REF-equal-ALT"),
    ],
)
def test_identity_fingerprint_rejects_malformed_internal_allele_evidence(
    tmp_path: Path,
    column: str,
    value: object,
    message: str,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    row = {
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
    row[column] = value
    if column == "alt_allele_fraction":
        row["heteroplasmy_fraction"] = value
    pd.DataFrame([row]).to_csv(
        summary_dir / "mito_heteroplasmy_all_sites.tsv", sep="\t", index=False
    )
    pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "reason_code", "value": ""},
            {"metric": "callable_positions", "value": 1},
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)

    with pytest.raises(ValueError, match=message):
        run_step(
            summary_dir=summary_dir,
            figure_dir=tmp_path / "figures",
            report_dir=tmp_path / "report",
            sample_id="MALFORMED-ID",
            mt_contig="MT",
            phased_snp_vcf=None,
            np_snp_vcf=None,
        )


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
    assert summary["shared_retained_mt_snvs"] == ""


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
        "phased_mt_vcf_unique_retained_snvs": "2",
        "unphased_mt_vcf_unique_retained_snvs": "2",
        "shared_retained_mt_snvs": "1",
        "phased_only_retained_mt_snvs": "1",
        "unphased_only_retained_mt_snvs": "1",
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
    assert summary["phased_mt_vcf_unique_retained_snvs"] == ""
    assert summary["shared_retained_mt_snvs"] == ""
    stdout = capsys.readouterr().out
    assert "variant comparison unavailable status=not_evaluable" in stdout
    assert "vcf_overlap shared=0" not in stdout
