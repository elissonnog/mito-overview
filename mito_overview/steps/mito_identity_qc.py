"""Mitochondrial fingerprint and concordance QC for mito-overview."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import (
    ensure_alt_fraction_columns,
    load_metric_module_state,
    validate_candidate_table,
    validate_module_state,
)

SUMMARY_COLUMNS = ["metric", "value"]
VARIANT_COLUMNS = ["position", "ref", "alt"]
FINGERPRINT_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "depth",
]
COMPARE_COLUMNS = ["membership", "position", "ref", "alt"]
CANONICAL_BASES = frozenset("ACGT")
SNP_SELECTION_CONTRACT = (
    "canonical_single_nucleotide_ref_alt;filter_pass_or_dot;"
    "called_alt_if_samples_present;site_only_pass_snv_allowed"
)


@dataclass
class VariantSelectionCounts:
    """Auditable per-ALT accounting for one mitochondrial VCF input."""

    mt_records_total: int = 0
    records_without_alt: int = 0
    sample_columns: int = 0
    alt_alleles_total: int = 0
    retained_alt_alleles: int = 0
    unique_retained_snvs: int = 0
    excluded_filtered_alt_alleles: int = 0
    excluded_non_snv_alt_alleles: int = 0
    excluded_noncanonical_alt_alleles: int = 0
    excluded_reference_equal_alt_alleles: int = 0
    excluded_uncalled_alt_alleles: int = 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--phased-snp-vcf", required=True)
    parser.add_argument("--np-snp-vcf", required=True)
    parser.add_argument("--fingerprint-depth", type=int, default=100)
    parser.add_argument("--major-vaf", type=float, default=0.90)
    return parser


def load_table(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    """Load a TSV if present, otherwise return an empty table with the requested schema."""

    if not path.exists():
        return pd.DataFrame(columns=columns or [])
    try:
        df = pd.read_csv(path, sep="\t")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns or [])
    if df.empty and columns is not None:
        return pd.DataFrame(columns=columns)
    return df


def load_heteroplasmy_status(path: Path) -> tuple[str, str]:
    """Load the upstream heteroplasmy state without inventing callable evidence."""

    return load_metric_module_state(path, module_name="heteroplasmy")


def _record_passes_filter(record: pysam.VariantRecord) -> bool:
    """Accept only VCF FILTER values PASS or the unset `.` representation."""

    filter_keys = {str(value) for value in record.filter.keys()}
    return not filter_keys or filter_keys.issubset({"PASS", "."})


def _called_alt_indexes(record: pysam.VariantRecord) -> set[int]:
    """Return 1-based ALT indexes explicitly called by at least one sample GT."""

    called: set[int] = set()
    for sample in record.samples.values():
        try:
            genotype = sample.get("GT")
        except (KeyError, TypeError, ValueError):
            genotype = None
        if genotype is None:
            continue
        for allele_index in genotype:
            if isinstance(allele_index, int) and allele_index > 0:
                called.add(allele_index)
    return called


def _select_mt_snvs(
    records: Iterable[pysam.VariantRecord],
    *,
    contig: str,
    sample_columns: int,
) -> tuple[list[dict[str, object]], VariantSelectionCounts]:
    """Apply the identity-QC SNP contract and retain one row per called ALT."""

    rows: list[dict[str, object]] = []
    counts = VariantSelectionCounts(sample_columns=sample_columns)
    for record in records:
        if record.contig != contig:
            continue
        counts.mt_records_total += 1
        alts = tuple(record.alts or ())
        if not alts:
            counts.records_without_alt += 1
            continue

        record_passes_filter = _record_passes_filter(record)
        called_alt_indexes = _called_alt_indexes(record) if sample_columns else set()
        ref = "" if record.ref is None else str(record.ref).upper()

        for alt_index, raw_alt in enumerate(alts, start=1):
            counts.alt_alleles_total += 1
            alt = "" if raw_alt is None else str(raw_alt).upper()

            # Reasons are mutually exclusive and evaluated in this fixed order so
            # retained + excluded counts equal the number of ALT alleles examined.
            if not record_passes_filter:
                counts.excluded_filtered_alt_alleles += 1
                continue
            if not ref or not alt or not set(ref + alt).issubset(CANONICAL_BASES):
                counts.excluded_noncanonical_alt_alleles += 1
                continue
            if len(ref) != 1 or len(alt) != 1:
                counts.excluded_non_snv_alt_alleles += 1
                continue
            if ref == alt:
                counts.excluded_reference_equal_alt_alleles += 1
                continue
            if sample_columns and alt_index not in called_alt_indexes:
                counts.excluded_uncalled_alt_alleles += 1
                continue

            counts.retained_alt_alleles += 1
            rows.append({"position": int(record.pos), "ref": ref, "alt": alt})

    return rows, counts


def load_mt_variants(
    vcf_path: str | Path | None, contig: str
) -> tuple[pd.DataFrame, str, str, VariantSelectionCounts]:
    """Load unique mtDNA SNVs under the explicit identity-QC selection contract."""

    empty = pd.DataFrame(columns=VARIANT_COLUMNS)
    empty_counts = VariantSelectionCounts()
    if not vcf_path:
        return empty, "not_configured", "variant_vcf_not_configured", empty_counts
    path = Path(vcf_path)
    if not path.is_file():
        return empty, "not_configured", "variant_vcf_missing", empty_counts

    try:
        variant_file = pysam.VariantFile(str(path))
        try:
            sample_columns = len(variant_file.header.samples)
            try:
                rows, counts = _select_mt_snvs(
                    variant_file.fetch(contig),
                    contig=contig,
                    sample_columns=sample_columns,
                )
            except (OSError, ValueError):
                # Generic standalone VCF inputs are allowed to be unindexed. Reopen the
                # stream because a failed regional fetch may leave backend state unclear.
                variant_file.close()
                variant_file = pysam.VariantFile(str(path))
                rows, counts = _select_mt_snvs(
                    variant_file,
                    contig=contig,
                    sample_columns=len(variant_file.header.samples),
                )
        finally:
            variant_file.close()
    except (OSError, TypeError, ValueError):
        return empty, "not_evaluable", "variant_vcf_unreadable", empty_counts

    df = pd.DataFrame(rows, columns=VARIANT_COLUMNS)
    if df.empty:
        return empty, "ok", "", counts
    df = df.drop_duplicates().sort_values(["position", "ref", "alt"]).reset_index(drop=True)
    counts.unique_retained_snvs = len(df)
    return df, "ok", "", counts


def run_step(
    *,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    phased_snp_vcf: str | Path | None,
    np_snp_vcf: str | Path | None,
    fingerprint_depth: int = 100,
    major_vaf: float = 0.90,
) -> dict[str, Path | str]:
    """Run the public mitochondrial identity-QC step."""

    if (
        not isinstance(fingerprint_depth, int)
        or isinstance(fingerprint_depth, bool)
        or fingerprint_depth < 0
    ):
        raise ValueError("fingerprint_depth must be a nonnegative integer")
    if not math.isfinite(major_vaf) or not 0 <= major_vaf <= 1:
        raise ValueError("major_vaf must be finite and between 0 and 1")

    print(
        f"[identity_qc] starting sample={sample_id} contig={mt_contig} "
        f"fingerprint_depth={fingerprint_depth} major_vaf={major_vaf}",
        flush=True,
    )
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    hetero_path = summary_dir / "mito_heteroplasmy_all_sites.tsv"
    hetero_summary_path = summary_dir / "mito_heteroplasmy_summary.tsv"
    phymer_path = summary_dir / "mito_phymer_haplogroup_summary.tsv"
    fingerprint_path = summary_dir / "mito_identity_major_variant_fingerprint.tsv"
    compare_path = summary_dir / "mito_identity_vcf_comparison.tsv"
    summary_path = summary_dir / "mito_identity_qc_summary.tsv"
    overlap_fig = figure_dir / "mito_identity_vcf_overlap.png"
    report_path = report_dir / "09_mito_identity_qc.html"

    hetero_df = ensure_alt_fraction_columns(load_table(hetero_path, columns=FINGERPRINT_COLUMNS))
    heteroplasmy_status, heteroplasmy_reason = load_heteroplasmy_status(
        hetero_summary_path
    )
    phased_df, phased_vcf_status, phased_vcf_reason, phased_selection = load_mt_variants(
        phased_snp_vcf, mt_contig
    )
    np_df, np_vcf_status, np_vcf_reason, np_selection = load_mt_variants(
        np_snp_vcf, mt_contig
    )
    phymer_summary = load_table(phymer_path, columns=SUMMARY_COLUMNS)
    print(
        f"[identity_qc] loaded heteroplasmy_rows={len(hetero_df)} "
        f"phased_retained_snvs={len(phased_df)} "
        f"unphased_retained_snvs={len(np_df)} "
        f"phymer_rows={len(phymer_summary)}",
        flush=True,
    )
    if phased_vcf_status == "ok":
        print(
            "[identity_qc] phased SNP selection "
            f"records={phased_selection.mt_records_total} "
            f"alt_alleles={phased_selection.alt_alleles_total} "
            f"retained={phased_selection.retained_alt_alleles} "
            f"unique={phased_selection.unique_retained_snvs} "
            f"excluded_filtered={phased_selection.excluded_filtered_alt_alleles} "
            f"excluded_non_snv={phased_selection.excluded_non_snv_alt_alleles} "
            f"excluded_noncanonical={phased_selection.excluded_noncanonical_alt_alleles} "
            f"excluded_reference_equal={phased_selection.excluded_reference_equal_alt_alleles} "
            f"excluded_uncalled={phased_selection.excluded_uncalled_alt_alleles}",
            flush=True,
        )
    if np_vcf_status == "ok":
        print(
            "[identity_qc] unphased SNP selection "
            f"records={np_selection.mt_records_total} "
            f"alt_alleles={np_selection.alt_alleles_total} "
            f"retained={np_selection.retained_alt_alleles} "
            f"unique={np_selection.unique_retained_snvs} "
            f"excluded_filtered={np_selection.excluded_filtered_alt_alleles} "
            f"excluded_non_snv={np_selection.excluded_non_snv_alt_alleles} "
            f"excluded_noncanonical={np_selection.excluded_noncanonical_alt_alleles} "
            f"excluded_reference_equal={np_selection.excluded_reference_equal_alt_alleles} "
            f"excluded_uncalled={np_selection.excluded_uncalled_alt_alleles}",
            flush=True,
        )

    required_fingerprint = {"position", "ref_base", "alt_base", "alt_allele_fraction", "depth"}
    fingerprint_input_present = hetero_path.is_file()
    fingerprint_input_usable = fingerprint_input_present and required_fingerprint.issubset(
        hetero_df.columns
    )
    fingerprint_status = "ok"
    fingerprint_reason = ""
    if heteroplasmy_status != "ok":
        fingerprint_status = heteroplasmy_status
        fingerprint_reason = heteroplasmy_reason
    elif not fingerprint_input_present:
        fingerprint_status = "not_evaluable"
        fingerprint_reason = "heteroplasmy_all_sites_missing"
    elif not fingerprint_input_usable:
        fingerprint_status = "not_evaluable"
        fingerprint_reason = "heteroplasmy_all_sites_unusable"
    elif hetero_df.empty:
        fingerprint_status = "not_evaluable"
        fingerprint_reason = "heteroplasmy_all_sites_no_measured_observations"

    major_df = pd.DataFrame(columns=FINGERPRINT_COLUMNS)
    if fingerprint_status == "ok" and fingerprint_input_usable and not hetero_df.empty:
        major_df = hetero_df.copy()
        major_df["position"] = pd.to_numeric(major_df["position"], errors="coerce")
        major_df["depth"] = pd.to_numeric(major_df["depth"], errors="coerce")
        major_df["alt_allele_fraction"] = pd.to_numeric(
            major_df["alt_allele_fraction"], errors="coerce"
        )
        positions = major_df["position"].to_numpy(dtype=float)
        depths = major_df["depth"].to_numpy(dtype=float)
        fractions = major_df["alt_allele_fraction"].to_numpy(dtype=float)
        valid_fraction = (
            ((depths == 0) & np.isnan(fractions))
            | (
                (depths > 0)
                & np.isfinite(fractions)
                & (fractions >= 0)
                & (fractions <= 1)
            )
        )
        if not (
            np.isfinite(positions).all()
            and (positions == np.floor(positions)).all()
            and (positions >= 1).all()
            and np.isfinite(depths).all()
            and (depths == np.floor(depths)).all()
            and (depths >= 0).all()
            and valid_fraction.all()
        ):
            raise ValueError(
                "mito_heteroplasmy_all_sites.tsv contains invalid position, depth, "
                "or allele-fraction evidence"
            )
        major_df["position"] = major_df["position"].astype("int64")
        major_df["depth"] = major_df["depth"].astype("int64")
        major_df = major_df[
            (major_df["depth"] >= fingerprint_depth)
            & (major_df["alt_allele_fraction"] >= major_vaf)
        ].copy()
        major_df = validate_candidate_table(
            major_df,
            table_name="mito_heteroplasmy_all_sites.tsv major-fingerprint rows",
        )
        major_df = major_df.sort_values(
            ["alt_allele_fraction", "depth", "position"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        major_df["heteroplasmy_fraction"] = major_df["alt_allele_fraction"]
        major_df = major_df.loc[:, FINGERPRINT_COLUMNS]
    elif fingerprint_input_present and not fingerprint_input_usable:
        print(
            "[identity_qc] heteroplasmy table did not include the expected fingerprint columns; "
            "writing an empty fingerprint table",
            flush=True,
        )
    elif fingerprint_status != "ok":
        print(
            f"[identity_qc] fingerprint evidence unavailable status={fingerprint_status} "
            f"reason={fingerprint_reason}",
            flush=True,
        )
    else:
        print("[identity_qc] no heteroplasmy all-sites table available; fingerprint table will be empty", flush=True)
    major_df.to_csv(fingerprint_path, sep="\t", index=False)
    print(f"[identity_qc] fingerprint sites={len(major_df)} wrote={fingerprint_path}", flush=True)

    paired_variant_evidence_ok = phased_vcf_status == "ok" and np_vcf_status == "ok"
    phased_keys = (
        set(map(tuple, phased_df[VARIANT_COLUMNS].itertuples(index=False, name=None)))
        if paired_variant_evidence_ok and not phased_df.empty
        else set()
    )
    np_keys = (
        set(map(tuple, np_df[VARIANT_COLUMNS].itertuples(index=False, name=None)))
        if paired_variant_evidence_ok and not np_df.empty
        else set()
    )
    shared_keys = phased_keys & np_keys
    phased_only_keys = phased_keys - np_keys
    unphased_only_keys = np_keys - phased_keys
    if paired_variant_evidence_ok:
        comparison_status = "ok"
        comparison_reason = ""
    elif "not_evaluable" in (phased_vcf_status, np_vcf_status):
        comparison_status = "not_evaluable"
        failed_sources = []
        if phased_vcf_status == "not_evaluable":
            failed_sources.append(f"phased:{phased_vcf_reason}")
        if np_vcf_status == "not_evaluable":
            failed_sources.append(f"unphased:{np_vcf_reason}")
        comparison_reason = "paired_variant_vcf_unreadable[" + ",".join(failed_sources) + "]"
    else:
        comparison_status = "not_configured"
        comparison_reason = "paired_variant_vcfs_not_configured"

    compare_rows: list[dict[str, object]] = []
    for label, keys in (
        ("shared", shared_keys),
        ("phased_only", phased_only_keys),
        ("unphased_only", unphased_only_keys),
    ):
        for pos, ref, alt in sorted(keys):
            compare_rows.append({"membership": label, "position": pos, "ref": ref, "alt": alt})
    compare_df = pd.DataFrame(compare_rows, columns=COMPARE_COLUMNS)
    compare_df.to_csv(compare_path, sep="\t", index=False)
    if comparison_status == "ok":
        print(
            f"[identity_qc] vcf_overlap shared={len(shared_keys)} "
            f"phased_only={len(phased_only_keys)} "
            f"unphased_only={len(unphased_only_keys)} "
            f"wrote={compare_path}",
            flush=True,
        )
    else:
        print(
            f"[identity_qc] variant comparison unavailable status={comparison_status} "
            f"reason={comparison_reason} wrote={compare_path}",
            flush=True,
        )

    fingerprint_string = "NA"
    if not major_df.empty:
        fingerprint_string = "; ".join(
            f"{int(row.position)}:{row.ref_base}>{row.alt_base}"
            for row in major_df.head(20).itertuples(index=False)
        )

    phymer_best = "NA"
    phymer_status = "not_configured"
    phymer_reason = "phymer_summary_missing"
    if not phymer_summary.empty and {"metric", "value"}.issubset(phymer_summary.columns):
        metric_map = dict(zip(phymer_summary["metric"], phymer_summary["value"]))
        phymer_best = str(metric_map.get("best_haplogroup", "NA"))
        raw_phymer_status = str(metric_map.get("status", "not_configured"))
        try:
            phymer_status = validate_module_state(raw_phymer_status)
            raw_phymer_reason = metric_map.get("reason_code", "")
            phymer_reason = "" if pd.isna(raw_phymer_reason) else str(raw_phymer_reason).strip()
        except ValueError:
            phymer_status = "not_evaluable"
            phymer_reason = "phymer_summary_status_invalid"

    phased_vcf_present = bool(phased_snp_vcf and Path(phased_snp_vcf).is_file())
    np_vcf_present = bool(np_snp_vcf and Path(np_snp_vcf).is_file())
    evidence_statuses = (fingerprint_status, comparison_status, phymer_status)
    evaluable_sources = sum(source_status == "ok" for source_status in evidence_statuses)
    if evaluable_sources == 0:
        module_status = "not_evaluable"
        module_reason = "no_evaluable_identity_evidence"
    else:
        module_status = "ok"
        module_reason = "" if evaluable_sources == len(evidence_statuses) else "partial_identity_evidence"

    major_fingerprint_sites: int | object = len(major_df) if fingerprint_status == "ok" else pd.NA
    shared_snv_count: int | object = len(shared_keys) if comparison_status == "ok" else pd.NA
    phased_only_snv_count: int | object = (
        len(phased_only_keys) if comparison_status == "ok" else pd.NA
    )
    unphased_only_snv_count: int | object = (
        len(unphased_only_keys) if comparison_status == "ok" else pd.NA
    )

    def selection_value(
        status: str, counts: VariantSelectionCounts, attribute: str
    ) -> int | object:
        return getattr(counts, attribute) if status == "ok" else pd.NA

    def selection_summary_rows(
        prefix: str, status: str, counts: VariantSelectionCounts
    ) -> list[dict[str, object]]:
        metric_attributes = (
            ("mt_vcf_records_total", "mt_records_total"),
            ("mt_vcf_records_without_alt", "records_without_alt"),
            ("mt_vcf_sample_columns", "sample_columns"),
            ("mt_vcf_alt_alleles_total", "alt_alleles_total"),
            ("mt_vcf_alt_alleles_retained", "retained_alt_alleles"),
            ("mt_vcf_unique_retained_snvs", "unique_retained_snvs"),
            (
                "mt_vcf_alt_alleles_excluded_filtered",
                "excluded_filtered_alt_alleles",
            ),
            (
                "mt_vcf_alt_alleles_excluded_non_snv",
                "excluded_non_snv_alt_alleles",
            ),
            (
                "mt_vcf_alt_alleles_excluded_noncanonical",
                "excluded_noncanonical_alt_alleles",
            ),
            (
                "mt_vcf_alt_alleles_excluded_reference_equal",
                "excluded_reference_equal_alt_alleles",
            ),
            (
                "mt_vcf_alt_alleles_excluded_uncalled",
                "excluded_uncalled_alt_alleles",
            ),
        )
        return [
            {
                "metric": f"{prefix}_{metric_suffix}",
                "value": selection_value(status, counts, attribute),
            }
            for metric_suffix, attribute in metric_attributes
        ]

    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": module_status},
            {"metric": "reason_code", "value": module_reason},
            {"metric": "fingerprint_status", "value": fingerprint_status},
            {"metric": "fingerprint_reason_code", "value": fingerprint_reason},
            {
                "metric": "heteroplasmy_summary_status",
                "value": heteroplasmy_status,
            },
            {
                "metric": "heteroplasmy_summary_reason_code",
                "value": heteroplasmy_reason,
            },
            {"metric": "variant_comparison_status", "value": comparison_status},
            {"metric": "variant_comparison_reason_code", "value": comparison_reason},
            {"metric": "identity_snp_selection_contract", "value": SNP_SELECTION_CONTRACT},
            {"metric": "phased_variant_vcf_present", "value": int(phased_vcf_present)},
            {"metric": "unphased_variant_vcf_present", "value": int(np_vcf_present)},
            {"metric": "major_fingerprint_sites", "value": major_fingerprint_sites},
            *selection_summary_rows("phased", phased_vcf_status, phased_selection),
            *selection_summary_rows("unphased", np_vcf_status, np_selection),
            {"metric": "shared_retained_mt_snvs", "value": shared_snv_count},
            {"metric": "phased_only_retained_mt_snvs", "value": phased_only_snv_count},
            {
                "metric": "unphased_only_retained_mt_snvs",
                "value": unphased_only_snv_count,
            },
            {"metric": "formal_haplogroup_assignment_status", "value": phymer_status},
            {"metric": "formal_haplogroup_reason_code", "value": phymer_reason},
            {"metric": "formal_haplogroup_best_match", "value": phymer_best},
            {"metric": "major_variant_fingerprint", "value": fingerprint_string},
        ],
        columns=SUMMARY_COLUMNS,
    )
    summary_df.to_csv(summary_path, sep="\t", index=False)
    print(f"[identity_qc] wrote summary table {summary_path}", flush=True)

    overlap_plot_df = pd.DataFrame(
        {
            "class": ["shared", "phased only", "unphased only"],
            "count": [len(shared_keys), len(phased_only_keys), len(unphased_only_keys)],
        }
    )
    plt.figure(figsize=(6, 4))
    if comparison_status == "ok":
        plt.bar(
            overlap_plot_df["class"],
            overlap_plot_df["count"],
            color=["#0f766e", "#2563eb", "#f59e0b"],
        )
        plt.ylabel("Unique retained mtDNA SNVs")
        plt.title(f"{sample_id} exact retained-SNV overlap")
    else:
        plt.axis("off")
        comparison_label = (
            "Paired VCF comparison was not evaluable"
            if comparison_status == "not_evaluable"
            else "Paired phased and unphased VCFs were not configured"
        )
        plt.text(
            0.5,
            0.5,
            f"{comparison_label}\n{comparison_reason}",
            ha="center",
            va="center",
            wrap=True,
        )
    plt.tight_layout()
    plt.savefig(overlap_fig, dpi=150)
    plt.close()
    print(f"[identity_qc] wrote overlap figure {overlap_fig}", flush=True)

    fingerprint_fig = None
    if not major_df.empty:
        top = major_df.head(20).copy()
        fingerprint_fig = figure_dir / "mito_identity_major_variants.png"
        plt.figure(figsize=(10, 4))
        plt.bar(top["position"].astype(str), top["alt_allele_fraction"], color="#dc2626")
        plt.xticks(rotation=90)
        plt.ylabel("Alt fraction")
        plt.title(f"{sample_id} major mitochondrial fingerprint variants")
        plt.tight_layout()
        plt.savefig(fingerprint_fig, dpi=150)
        plt.close()
        print(f"[identity_qc] wrote fingerprint figure {fingerprint_fig}", flush=True)
    else:
        print("[identity_qc] skipped fingerprint figure because no major-variant fingerprint sites were found", flush=True)

    metrics_html = "".join(
        [
            metric_card("Evaluation status", module_status),
            metric_card(
                "Major fingerprint sites",
                "NA" if pd.isna(major_fingerprint_sites) else major_fingerprint_sites,
            ),
            metric_card(
                "Shared retained SNVs",
                "NA" if pd.isna(shared_snv_count) else shared_snv_count,
            ),
            metric_card(
                "Phased-only retained SNVs",
                "NA" if pd.isna(phased_only_snv_count) else phased_only_snv_count,
            ),
            metric_card(
                "Unphased-only retained SNVs",
                "NA" if pd.isna(unphased_only_snv_count) else unphased_only_snv_count,
            ),
            metric_card("Best haplogroup", phymer_best),
        ]
    )
    intro_html = (
        '<p class="muted">This page summarizes sample-identity style mitochondrial QC using two '
        "complementary signals: a major-variant fingerprint derived from high alternate-allele-fraction mitochondrial "
        "sites, and exact overlap between retained canonical mtDNA SNVs from phased and unphased "
        "VCFs. Retained alleles require single-base A/C/G/T REF and ALT values plus FILTER PASS or '.'; "
        "when sample columns exist, at least one sample GT must call that ALT allele. When "
        "available, the best haplogroup match from the dedicated Phy-Mer page is also reported here "
        "as a compact identity-style label.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Identity/QC summary</h2>"
        + df_to_html_table(summary_df.fillna("NA"), max_rows=60)
        + "</section>",
        "<section><h2>Exact phased vs unphased retained-SNV overlap</h2>"
        + figure_html(
            overlap_fig,
            "Exact overlap of unique retained mtDNA SNVs between phased and unphased VCF inputs",
        )
        + "</section>",
        "<section><h2>Retained-SNV comparison table</h2>"
        + df_to_html_table(compare_df, max_rows=40)
        + "</section>",
        "<section><h2>Major-variant fingerprint table</h2>" + df_to_html_table(major_df, max_rows=30) + "</section>",
    ]
    if fingerprint_fig:
        body_parts.insert(
            3,
            "<section><h2>Major-variant fingerprint</h2>"
            + figure_html(fingerprint_fig, "High-fraction mitochondrial variants used as a sample-level fingerprint")
            + "</section>",
        )

    render_page(
        report_path,
        "Mito Identity QC",
        sample_id,
        f"{mt_contig}:whole_mito",
        intro_html,
        "".join(body_parts),
    )
    print(f"[identity_qc] wrote report {report_path}", flush=True)

    outputs = {
        "status": module_status,
        "fingerprint_path": fingerprint_path,
        "compare_path": compare_path,
        "summary_path": summary_path,
        "overlap_figure_path": overlap_fig,
        "report_path": report_path,
    }
    if fingerprint_fig:
        outputs["fingerprint_figure_path"] = fingerprint_fig
    return outputs


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        summary_dir=args.summary_dir,
        figure_dir=args.figure_dir,
        report_dir=args.report_dir,
        sample_id=args.sample_id,
        mt_contig=args.mt_contig,
        phased_snp_vcf=args.phased_snp_vcf,
        np_snp_vcf=args.np_snp_vcf,
        fingerprint_depth=args.fingerprint_depth,
        major_vaf=args.major_vaf,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
