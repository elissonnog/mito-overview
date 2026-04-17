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

SUMMARY_COLUMNS = ["metric", "value"]
VARIANT_COLUMNS = ["position", "ref", "alt"]
FINGERPRINT_COLUMNS = ["position", "ref_base", "alt_base", "heteroplasmy_fraction", "depth"]
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


def load_mt_variants(vcf_path: str | Path, contig: str) -> pd.DataFrame:
    """Load unique mitochondrial variant records from a VCF/BCF."""

    path = Path(vcf_path)
    if not path.exists():
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
    phased_snp_vcf: str | Path,
    np_snp_vcf: str | Path,
    fingerprint_depth: int = 100,
    major_vaf: float = 0.90,
) -> dict[str, Path]:
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
    phymer_path = summary_dir / "mito_phymer_haplogroup_summary.tsv"
    fingerprint_path = summary_dir / "mito_identity_major_variant_fingerprint.tsv"
    compare_path = summary_dir / "mito_identity_vcf_comparison.tsv"
    summary_path = summary_dir / "mito_identity_qc_summary.tsv"
    overlap_fig = figure_dir / "mito_identity_vcf_overlap.png"
    report_path = report_dir / "09_mito_identity_qc.html"

    hetero_df = load_table(hetero_path, columns=FINGERPRINT_COLUMNS)
    phased_df = load_mt_variants(phased_snp_vcf, mt_contig)
    np_df = load_mt_variants(np_snp_vcf, mt_contig)
    phymer_summary = load_table(phymer_path, columns=SUMMARY_COLUMNS)
    print(
        f"[identity_qc] loaded heteroplasmy_rows={len(hetero_df)} "
        f"phased_rows={len(phased_df)} np_rows={len(np_df)} "
        f"phymer_rows={len(phymer_summary)}",
        flush=True,
    )

    major_df = pd.DataFrame(columns=FINGERPRINT_COLUMNS)
    required_fingerprint = {"position", "ref_base", "alt_base", "heteroplasmy_fraction", "depth"}
    if not hetero_df.empty and required_fingerprint.issubset(hetero_df.columns):
        major_df = hetero_df.copy()
        major_df["position"] = pd.to_numeric(major_df["position"], errors="coerce")
        major_df["depth"] = pd.to_numeric(major_df["depth"], errors="coerce")
        major_df["heteroplasmy_fraction"] = pd.to_numeric(major_df["heteroplasmy_fraction"], errors="coerce")
        major_df = major_df.dropna(subset=["position", "depth", "heteroplasmy_fraction"])
        major_df = major_df[
            (major_df["depth"] >= fingerprint_depth) & (major_df["heteroplasmy_fraction"] >= major_vaf)
        ].copy()
        major_df = major_df.sort_values(
            ["heteroplasmy_fraction", "depth", "position"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        major_df["position"] = major_df["position"].astype(int)
    elif hetero_path.exists():
        print(
            "[identity_qc] heteroplasmy table did not include the expected fingerprint columns; "
            "writing an empty fingerprint table",
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

    phymer_best = "not_run"
    phymer_status = "not_run"
    if not phymer_summary.empty and {"metric", "value"}.issubset(phymer_summary.columns):
        metric_map = dict(zip(phymer_summary["metric"], phymer_summary["value"]))
        phymer_best = str(metric_map.get("best_haplogroup", "not_run"))
        phymer_status = str(metric_map.get("status", "not_run"))

    summary_df = pd.DataFrame(
        [
            {"metric": "major_fingerprint_sites", "value": int(len(major_df))},
            {"metric": "phased_mt_variant_records", "value": int(len(phased_df))},
            {"metric": "np_mt_variant_records", "value": int(len(np_df))},
            {"metric": "shared_mt_variant_records", "value": int(len(shared_keys))},
            {"metric": "phased_only_mt_variant_records", "value": int(len(phased_only_keys))},
            {"metric": "np_only_mt_variant_records", "value": int(len(np_only_keys))},
            {"metric": "formal_haplogroup_assignment_status", "value": phymer_status},
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
    plt.bar(overlap_plot_df["class"], overlap_plot_df["count"], color=["#0f766e", "#2563eb", "#f59e0b"])
    plt.ylabel("Variant records")
    plt.title(f"{sample_id} phased vs NP mtDNA variant overlap")
    plt.tight_layout()
    plt.savefig(overlap_fig, dpi=150)
    plt.close()
    print(f"[identity_qc] wrote overlap figure {overlap_fig}", flush=True)

    fingerprint_fig = None
    if not major_df.empty:
        top = major_df.head(20).copy()
        fingerprint_fig = figure_dir / "mito_identity_major_variants.png"
        plt.figure(figsize=(10, 4))
        plt.bar(top["position"].astype(str), top["heteroplasmy_fraction"], color="#dc2626")
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
            metric_card("Major fingerprint sites", int(len(major_df))),
            metric_card("Shared phased/NP calls", int(len(shared_keys))),
            metric_card("Phased-only calls", int(len(phased_only_keys))),
            metric_card("NP-only calls", int(len(np_only_keys))),
            metric_card("Best haplogroup", phymer_best),
        ]
    )
    intro_html = (
        '<p class="muted">This page summarizes sample-identity style mitochondrial QC using two '
        "complementary signals: a major-variant fingerprint derived from high-fraction mitochondrial "
        "sites, and concordance between phased and no-phased mitochondrial SNP callsets. When "
        "available, the best haplogroup match from the dedicated Phy-Mer page is also reported here "
        "as a compact identity-style label.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Identity/QC summary</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>",
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
