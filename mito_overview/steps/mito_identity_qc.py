"""Mitochondrial fingerprint and concordance QC for mito-overview."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import ensure_alt_fraction_columns, validate_module_state

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


def load_heteroplasmy_status(path: Path) -> tuple[str | None, str]:
    """Load the upstream heteroplasmy state without inventing callable evidence."""

    if not path.exists():
        return None, "heteroplasmy_summary_missing"
    frame = load_table(path, columns=SUMMARY_COLUMNS)
    if frame.empty or not {"metric", "value"}.issubset(frame.columns):
        return "not_evaluable", "heteroplasmy_summary_unusable"
    status_values = frame.loc[frame["metric"].astype(str) == "status", "value"]
    if len(status_values) != 1 or pd.isna(status_values.iloc[0]):
        return "not_evaluable", "heteroplasmy_summary_status_invalid"
    try:
        status = validate_module_state(str(status_values.iloc[0]).strip())
    except ValueError:
        return "not_evaluable", "heteroplasmy_summary_status_invalid"
    reason_values = frame.loc[frame["metric"].astype(str) == "reason_code", "value"]
    reason = ""
    if len(reason_values) == 1 and not pd.isna(reason_values.iloc[0]):
        reason = str(reason_values.iloc[0]).strip()
    if status != "ok" and not reason:
        reason = f"heteroplasmy_status_{status}"
    return status, reason


def load_mt_variants(vcf_path: str | Path | None, contig: str) -> pd.DataFrame:
    """Load unique mitochondrial variant records from a VCF/BCF."""

    if not vcf_path:
        return pd.DataFrame(columns=VARIANT_COLUMNS)
    path = Path(vcf_path)
    if not path.is_file():
        return pd.DataFrame(columns=VARIANT_COLUMNS)

    rows: list[dict[str, object]] = []
    variant_file = pysam.VariantFile(str(path))
    try:
        try:
            iterator = variant_file.fetch(contig)
        except ValueError:
            iterator = []
        for record in iterator:
            for alt in record.alts or []:
                rows.append({"position": int(record.pos), "ref": record.ref, "alt": alt})
    finally:
        variant_file.close()

    df = pd.DataFrame(rows, columns=VARIANT_COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=VARIANT_COLUMNS)
    return df.drop_duplicates().sort_values(["position", "ref", "alt"]).reset_index(drop=True)


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
    phased_df = load_mt_variants(phased_snp_vcf, mt_contig)
    np_df = load_mt_variants(np_snp_vcf, mt_contig)
    phymer_summary = load_table(phymer_path, columns=SUMMARY_COLUMNS)
    print(
        f"[identity_qc] loaded heteroplasmy_rows={len(hetero_df)} "
        f"phased_rows={len(phased_df)} np_rows={len(np_df)} "
        f"phymer_rows={len(phymer_summary)}",
        flush=True,
    )

    required_fingerprint = {"position", "ref_base", "alt_base", "alt_allele_fraction", "depth"}
    fingerprint_input_present = hetero_path.is_file()
    fingerprint_input_usable = fingerprint_input_present and required_fingerprint.issubset(
        hetero_df.columns
    )
    fingerprint_status = "ok"
    fingerprint_reason = ""
    if heteroplasmy_status is not None and heteroplasmy_status != "ok":
        fingerprint_status = heteroplasmy_status
        fingerprint_reason = heteroplasmy_reason
    elif not fingerprint_input_present:
        fingerprint_status = "not_evaluable"
        fingerprint_reason = "heteroplasmy_all_sites_missing"
    elif not fingerprint_input_usable:
        fingerprint_status = "not_evaluable"
        fingerprint_reason = "heteroplasmy_all_sites_unusable"
    elif heteroplasmy_status == "ok" and hetero_df.empty:
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
        major_df = major_df.dropna(subset=["position", "depth", "alt_allele_fraction"])
        if major_df.empty and heteroplasmy_status == "ok":
            fingerprint_status = "not_evaluable"
            fingerprint_reason = "heteroplasmy_all_sites_no_measured_observations"
        major_df = major_df[
            (major_df["depth"] >= fingerprint_depth) & (major_df["alt_allele_fraction"] >= major_vaf)
        ].copy()
        major_df = major_df.sort_values(
            ["alt_allele_fraction", "depth", "position"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        major_df["heteroplasmy_fraction"] = major_df["alt_allele_fraction"]
        major_df["position"] = major_df["position"].astype(int)
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

    phased_keys = set(map(tuple, phased_df[VARIANT_COLUMNS].itertuples(index=False, name=None))) if not phased_df.empty else set()
    np_keys = set(map(tuple, np_df[VARIANT_COLUMNS].itertuples(index=False, name=None))) if not np_df.empty else set()
    shared_keys = phased_keys & np_keys
    phased_only_keys = phased_keys - np_keys
    np_only_keys = np_keys - phased_keys

    compare_rows: list[dict[str, object]] = []
    for label, keys in (
        ("shared", shared_keys),
        ("phased_only", phased_only_keys),
        ("np_only", np_only_keys),
    ):
        for pos, ref, alt in sorted(keys):
            compare_rows.append({"membership": label, "position": pos, "ref": ref, "alt": alt})
    compare_df = pd.DataFrame(compare_rows, columns=COMPARE_COLUMNS)
    compare_df.to_csv(compare_path, sep="\t", index=False)
    print(
        f"[identity_qc] vcf_overlap shared={len(shared_keys)} phased_only={len(phased_only_keys)} "
        f"np_only={len(np_only_keys)} wrote={compare_path}",
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
    comparison_status = "ok" if phased_vcf_present and np_vcf_present else "not_configured"
    comparison_reason = "" if comparison_status == "ok" else "paired_variant_vcfs_not_configured"

    evidence_statuses = (fingerprint_status, comparison_status, phymer_status)
    evaluable_sources = sum(source_status == "ok" for source_status in evidence_statuses)
    if evaluable_sources == 0:
        module_status = "not_evaluable"
        module_reason = "no_evaluable_identity_evidence"
    else:
        module_status = "ok"
        module_reason = "" if evaluable_sources == len(evidence_statuses) else "partial_identity_evidence"

    major_fingerprint_sites: int | object = len(major_df) if fingerprint_status == "ok" else pd.NA
    phased_record_count: int | object = len(phased_df) if phased_vcf_present else pd.NA
    np_record_count: int | object = len(np_df) if np_vcf_present else pd.NA
    shared_record_count: int | object = len(shared_keys) if comparison_status == "ok" else pd.NA
    phased_only_count: int | object = len(phased_only_keys) if comparison_status == "ok" else pd.NA
    np_only_count: int | object = len(np_only_keys) if comparison_status == "ok" else pd.NA

    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": module_status},
            {"metric": "reason_code", "value": module_reason},
            {"metric": "fingerprint_status", "value": fingerprint_status},
            {"metric": "fingerprint_reason_code", "value": fingerprint_reason},
            {
                "metric": "heteroplasmy_summary_status",
                "value": heteroplasmy_status or "not_configured",
            },
            {
                "metric": "heteroplasmy_summary_reason_code",
                "value": heteroplasmy_reason,
            },
            {"metric": "variant_comparison_status", "value": comparison_status},
            {"metric": "variant_comparison_reason_code", "value": comparison_reason},
            {"metric": "phased_variant_vcf_present", "value": int(phased_vcf_present)},
            {"metric": "unphased_variant_vcf_present", "value": int(np_vcf_present)},
            {"metric": "major_fingerprint_sites", "value": major_fingerprint_sites},
            {"metric": "phased_mt_variant_records", "value": phased_record_count},
            {"metric": "np_mt_variant_records", "value": np_record_count},
            {"metric": "shared_mt_variant_records", "value": shared_record_count},
            {"metric": "phased_only_mt_variant_records", "value": phased_only_count},
            {"metric": "np_only_mt_variant_records", "value": np_only_count},
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
            "class": ["shared", "phased_only", "np_only"],
            "count": [len(shared_keys), len(phased_only_keys), len(np_only_keys)],
        }
    )
    plt.figure(figsize=(6, 4))
    if comparison_status == "ok":
        plt.bar(
            overlap_plot_df["class"],
            overlap_plot_df["count"],
            color=["#0f766e", "#2563eb", "#f59e0b"],
        )
        plt.ylabel("Variant records")
        plt.title(f"{sample_id} phased vs NP mtDNA variant overlap")
    else:
        plt.axis("off")
        plt.text(
            0.5,
            0.5,
            "Paired phased and unphased VCFs were not configured",
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
                "Shared phased/NP calls",
                "NA" if pd.isna(shared_record_count) else shared_record_count,
            ),
            metric_card(
                "Phased-only calls", "NA" if pd.isna(phased_only_count) else phased_only_count
            ),
            metric_card("NP-only calls", "NA" if pd.isna(np_only_count) else np_only_count),
            metric_card("Best haplogroup", phymer_best),
        ]
    )
    intro_html = (
        '<p class="muted">This page summarizes sample-identity style mitochondrial QC using two '
        "complementary signals: a major-variant fingerprint derived from high alternate-allele-fraction mitochondrial "
        "sites, and concordance between phased and no-phased mitochondrial SNP callsets. When "
        "available, the best haplogroup match from the dedicated Phy-Mer page is also reported here "
        "as a compact identity-style label.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Identity/QC summary</h2>"
        + df_to_html_table(summary_df.fillna("NA"), max_rows=20)
        + "</section>",
        "<section><h2>Phased vs no-phased variant overlap</h2>"
        + figure_html(overlap_fig, "Concordance of mtDNA SNP records between phased and no-phased workflows")
        + "</section>",
        "<section><h2>Variant comparison table</h2>" + df_to_html_table(compare_df, max_rows=40) + "</section>",
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
