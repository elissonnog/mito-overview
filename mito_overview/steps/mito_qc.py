"""Whole-mitochondrion QC summary for mito-overview."""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bam", required=True)
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--species", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--read-mode", default="long", choices=("long", "short"))
    parser.add_argument("--assay-type", default="wgs", choices=("wgs", "targeted_mt"))
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    return parser


def run_step(
    *,
    bam: str | Path,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    species: str,
    build: str,
    read_mode: str = "long",
    assay_type: str = "wgs",
    mt_contig: str,
    mt_length: int,
) -> dict[str, Path | str]:
    """Run the public mitochondrial QC step."""

    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    bam_handle = pysam.AlignmentFile(str(bam), "rb")
    read_rows = []
    strand_counts = {"forward": 0, "reverse": 0}
    primary = supplementary = secondary = mapped = 0
    primary_full_length = 0
    high_alignment_fraction_reads = 0

    for read in bam_handle.fetch(mt_contig):
        if read.is_unmapped:
            continue
        mapped += 1
        is_primary = (not read.is_secondary) and (not read.is_supplementary)
        if read.is_secondary:
            secondary += 1
        elif read.is_supplementary:
            supplementary += 1
        else:
            primary += 1
        strand_counts["reverse" if read.is_reverse else "forward"] += 1
        read_len = read.query_length or 0
        ref_start = read.reference_start + 1
        ref_end = read.reference_end or ref_start
        reference_span = max(0, ref_end - ref_start + 1)
        aligned_reference_bases = sum(
            length for op, length in (read.cigartuples or []) if op in (0, 7, 8)
        )
        query_aligned_bases = read.query_alignment_length or 0
        aligned_fraction = (aligned_reference_bases / mt_length) if mt_length else 0.0
        query_aligned_fraction = (query_aligned_bases / read_len) if read_len else 0.0
        softclip_bases = 0
        if read.cigartuples:
            for op, length in read.cigartuples:
                if op == 4:
                    softclip_bases += length
        softclip_fraction = (softclip_bases / read_len) if read_len else 0.0
        if is_primary and aligned_reference_bases >= 0.9 * mt_length:
            primary_full_length += 1
        if query_aligned_fraction >= 0.9:
            high_alignment_fraction_reads += 1
        read_rows.append(
            {
                "read_name": read.query_name,
                "mapq": read.mapping_quality,
                "query_length": read_len,
                "read_start": ref_start,
                "read_end": ref_end,
                "reference_span": reference_span,
                "aligned_reference_bases": aligned_reference_bases,
                "aligned_span": aligned_reference_bases,
                "aligned_fraction_mt": round(aligned_fraction, 6),
                "query_aligned_bases": query_aligned_bases,
                "query_aligned_fraction": round(query_aligned_fraction, 6),
                "softclip_bases": softclip_bases,
                "softclip_fraction": round(softclip_fraction, 6),
                "has_sa_tag": int(read.has_tag("SA")),
                "is_primary": int(is_primary),
                "is_supplementary": int(read.is_supplementary),
                "is_secondary": int(read.is_secondary),
                "is_reverse": int(read.is_reverse),
            }
        )

    coverage = bam_handle.count_coverage(mt_contig, 0, mt_length, quality_threshold=0)
    depth = [sum(x) for x in zip(*coverage)]
    bam_handle.close()

    depth_df = pd.DataFrame({"position": list(range(1, mt_length + 1)), "depth": depth})
    reads_df = pd.DataFrame(read_rows)

    mean_depth = round(sum(depth) / len(depth), 3) if depth else 0.0
    median_depth = round(statistics.median(depth), 3) if depth else 0.0
    breadth_1x = round(sum(d >= 1 for d in depth) / len(depth), 4) if depth else 0.0
    breadth_10x = round(sum(d >= 10 for d in depth) / len(depth), 4) if depth else 0.0
    module_status = "ok" if mapped else "not_evaluable"
    module_reason = "" if mapped else "no_mapped_reads"
    if read_mode == "long":
        primary_full_length_reads: int | object = primary_full_length
        primary_full_length_fraction: float | object = (
            round(primary_full_length / primary, 4) if primary else pd.NA
        )
        primary_full_length_status = "ok" if primary else "not_evaluable"
        primary_full_length_reason = "" if primary else "no_primary_reads"
        primary_full_length_denominator: str | object = "primary_alignment_records"
    else:
        primary_full_length_reads = pd.NA
        primary_full_length_fraction = pd.NA
        primary_full_length_status = "not_applicable"
        primary_full_length_reason = "read_mode_short"
        primary_full_length_denominator = pd.NA
    high_alignment_fraction: float | object = (
        round(high_alignment_fraction_reads / mapped, 4) if mapped else pd.NA
    )

    summary_rows = [
        {"metric": "status", "value": module_status},
        {"metric": "reason_code", "value": module_reason},
        {"metric": "mapped_reads", "value": mapped},
        {"metric": "primary_reads", "value": primary},
        {"metric": "primary_full_length_reads", "value": primary_full_length_reads},
        {
            "metric": "primary_full_length_fraction",
            "value": primary_full_length_fraction,
        },
        {
            "metric": "primary_full_length_fraction_status",
            "value": primary_full_length_status,
        },
        {
            "metric": "primary_full_length_fraction_reason_code",
            "value": primary_full_length_reason,
        },
        {
            "metric": "primary_full_length_fraction_denominator",
            "value": primary_full_length_denominator,
        },
        {
            "metric": "primary_full_length_fraction_basis",
            "value": "aligned_reference_bases_excluding_cigar_D_N",
        },
        {
            "metric": "full_length_fraction",
            "value": primary_full_length_fraction,
        },
        {
            "metric": "full_length_fraction_compatibility_alias_of",
            "value": "primary_full_length_fraction",
        },
        {"metric": "supplementary_reads", "value": supplementary},
        {"metric": "secondary_reads", "value": secondary},
        {"metric": "mean_depth", "value": mean_depth},
        {"metric": "median_depth", "value": median_depth},
        {"metric": "breadth_1x", "value": breadth_1x},
        {"metric": "breadth_10x", "value": breadth_10x},
        *(
            []
            if read_mode == "long"
            else [{"metric": "high_query_alignment_fraction", "value": high_alignment_fraction}]
        ),
        {"metric": "forward_reads", "value": strand_counts["forward"]},
        {"metric": "reverse_reads", "value": strand_counts["reverse"]},
    ]
    summary_df = pd.DataFrame(summary_rows)

    depth_path = summary_dir / "mito_depth_per_base.tsv"
    reads_path = summary_dir / "mito_read_stats.tsv"
    summary_path = summary_dir / "mito_qc_summary.tsv"
    report_path = report_dir / "01_mito_qc.html"
    depth_df.to_csv(depth_path, sep="\t", index=False)
    reads_df.to_csv(reads_path, sep="\t", index=False)
    summary_df.to_csv(summary_path, sep="\t", index=False)

    plt.figure(figsize=(12, 4))
    plt.plot(depth_df["position"], depth_df["depth"], linewidth=1.0)
    plt.xlabel("Mitochondrial position")
    plt.ylabel("Depth")
    plt.title(f"{sample_id} mitochondrial depth profile")
    plt.tight_layout()
    depth_fig = figure_dir / "mito_depth_profile.png"
    plt.savefig(depth_fig, dpi=150)
    plt.close()

    readlen_fig = None
    if not reads_df.empty:
        plt.figure(figsize=(8, 4))
        plt.hist(reads_df["query_length"], bins=40, color="#2563eb", alpha=0.85)
        plt.xlabel("Read length")
        plt.ylabel("Read count")
        plt.title(f"{sample_id} mitochondrial read length distribution")
        plt.tight_layout()
        readlen_fig = figure_dir / "mito_read_length_hist.png"
        plt.savefig(readlen_fig, dpi=150)
        plt.close()

    span_metric_label = (
        "Primary near-complete aligned-reference fraction"
        if read_mode == "long"
        else "High query-alignment fraction"
    )
    span_metric_value = (
        primary_full_length_fraction if read_mode == "long" else high_alignment_fraction
    )
    span_metric_display = "NA" if pd.isna(span_metric_value) else span_metric_value
    metrics_html = "".join(
        [
            metric_card("Evaluation status", module_status),
            metric_card("Species", species),
            metric_card("Build", build),
            metric_card("Read mode", read_mode),
            metric_card("Assay type", assay_type),
            metric_card("Mito contig", mt_contig),
            metric_card("Mapped reads", mapped),
            metric_card("Mean depth", mean_depth),
            metric_card(span_metric_label, span_metric_display),
        ]
    )
    structure_phrase = (
        "near-complete aligned-reference coverage and alignment quality"
        if read_mode == "long"
        else "fragment coverage, read-level alignment completeness, and alignment quality"
    )
    intro_html = (
        '<p class="muted">Whole-mitochondrion QC summary from the extracted mitochondrial BAM. '
        f"This page is intended to establish depth, {structure_phrase} "
        "before heteroplasmy or deletion interpretation.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Depth profile</h2>"
        + figure_html(depth_fig, "Mitochondrial depth across the full contig")
        + "</section>",
    ]
    if readlen_fig:
        body_parts.append(
            "<section><h2>Read length distribution</h2>"
            + figure_html(readlen_fig, "Distribution of mitochondrial read lengths")
            + "</section>"
        )
    body_parts.append(
        "<section><h2>QC metrics table</h2>"
        + df_to_html_table(summary_df.fillna("NA"), max_rows=20)
        + "</section>"
    )
    body_parts.append("<section><h2>Read-level table</h2>" + df_to_html_table(reads_df, max_rows=20) + "</section>")

    render_page(
        report_path,
        "Mitochondrial QC",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        "".join(body_parts),
    )
    return {
        "status": module_status,
        "summary_path": summary_path,
        "depth_path": depth_path,
        "reads_path": reads_path,
        "report_path": report_path,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        bam=args.bam,
        summary_dir=args.summary_dir,
        figure_dir=args.figure_dir,
        report_dir=args.report_dir,
        sample_id=args.sample_id,
        species=args.species,
        build=args.build,
        read_mode=args.read_mode,
        assay_type=args.assay_type,
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
