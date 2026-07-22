"""Whole-mitochondrion alternate-allele summary for mito-overview."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.allele_counting import (
    AlleleFilterPolicy,
    AlleleFilterStats,
    count_contig_alleles,
    policy_rows,
)
from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page


OUTPUT_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "callable_depth",
    "depth",
    "alt_count",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "alt_forward",
    "alt_reverse",
    "A",
    "C",
    "G",
    "T",
]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bam", required=True)
    parser.add_argument("--ref-fasta", required=True)
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--min-depth", type=int, default=100)
    parser.add_argument("--min-vaf", type=float, default=0.02)
    parser.add_argument("--min-base-quality", type=int, default=13)
    parser.add_argument("--min-mapping-quality", type=int, default=20)
    parser.add_argument("--min-read-mean-quality", type=float, default=10.0)
    parser.add_argument("--max-depth", type=int, default=0)
    parser.add_argument("--exclude-flags", type=lambda value: int(value, 0), default=3844)
    parser.add_argument("--ignore-overlaps", type=int, choices=(0, 1), default=1)
    return parser


def run_step(
    *,
    bam: str | Path,
    ref_fasta: str | Path,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    min_depth: int = 100,
    min_vaf: float = 0.02,
    min_base_quality: int = 13,
    min_mapping_quality: int = 20,
    min_read_mean_quality: float = 10.0,
    max_depth: int = 0,
    exclude_flags: int = 3844,
    ignore_overlaps: bool = True,
) -> dict[str, Path]:
    """Count and report observed mtDNA alternate-allele fractions."""

    start_time = time.time()
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    policy = AlleleFilterPolicy(
        min_base_quality=min_base_quality,
        min_mapping_quality=min_mapping_quality,
        min_read_mean_quality=min_read_mean_quality,
        max_depth=max_depth,
        exclude_flags=exclude_flags,
        ignore_overlaps=ignore_overlaps,
    )
    print(
        f"[heteroplasmy] starting sample={sample_id} contig={mt_contig} length={mt_length} "
        f"min_callable_depth={min_depth} min_alt_fraction={min_vaf} "
        f"baseq={min_base_quality} mapq={min_mapping_quality} readq={min_read_mean_quality} "
        f"max_depth={max_depth} exclude_flags={exclude_flags} ignore_overlaps={int(ignore_overlaps)}",
        flush=True,
    )

    with pysam.FastaFile(str(ref_fasta)) as fasta:
        ref_seq = fasta.fetch(mt_contig, 0, mt_length).upper()
    print("[heteroplasmy] counting filtered observations across mitochondrial genome", flush=True)

    def report_counting_progress(position: int, length: int, stats: AlleleFilterStats) -> None:
        accepted = stats.accepted_observations
        seen = stats.pileup_observations_seen
        print(
            f"[heteroplasmy] counted positions {position}/{length} "
            f"accepted_observations={accepted} excluded_observations_accounted={seen - accepted} "
            f"elapsed_sec={round(time.time() - start_time, 1)}",
            flush=True,
        )

    counting = count_contig_alleles(
        bam_path=bam,
        contig=mt_contig,
        length=mt_length,
        policy=policy,
        progress_callback=report_counting_progress,
    )
    print(
        f"[heteroplasmy] observation counting complete accepted={counting.stats.accepted_observations} "
        f"elapsed_sec={round(time.time() - start_time, 1)}",
        flush=True,
    )

    canonical_bases = {"A", "C", "G", "T"}
    all_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    skipped_noncanonical_candidates = 0
    for position in range(1, mt_length + 1):
        base_counts = counting.base_counts[position - 1]
        callable_depth = sum(base_counts.values())
        ref_base = ref_seq[position - 1]
        non_ref = {
            base: count
            for base, count in base_counts.items()
            if base != ref_base and count > 0
        }
        alt_base, alt_count = max(non_ref.items(), key=lambda item: item[1]) if non_ref else (None, 0)
        # A zero-depth position has no observed allele fraction; it is not an
        # observed reference-only site and must not be serialized as 0/0 = 0.
        alt_fraction = (alt_count / callable_depth) if callable_depth else float("nan")
        alt_forward = counting.forward_counts[position - 1].get(alt_base or "", 0)
        alt_reverse = counting.reverse_counts[position - 1].get(alt_base or "", 0)
        row = {
            "position": position,
            "ref_base": ref_base,
            "alt_base": alt_base or ".",
            "callable_depth": callable_depth,
            "depth": callable_depth,
            "alt_count": alt_count,
            "alt_allele_fraction": round(alt_fraction, 6),
            "heteroplasmy_fraction": round(alt_fraction, 6),
            "alt_forward": alt_forward,
            "alt_reverse": alt_reverse,
            "A": base_counts["A"],
            "C": base_counts["C"],
            "G": base_counts["G"],
            "T": base_counts["T"],
        }
        all_rows.append(row)
        if (
            callable_depth >= min_depth
            and alt_base
            and alt_count > 0
            and pd.notna(alt_fraction)
            and alt_fraction >= min_vaf
        ):
            if ref_base in canonical_bases and alt_base in canonical_bases:
                candidate_rows.append(row.copy())
            else:
                skipped_noncanonical_candidates += 1
        if position % 4000 == 0 or position == mt_length:
            print(
                f"[heteroplasmy] summarised positions {position}/{mt_length} "
                f"elapsed_sec={round(time.time() - start_time, 1)}",
                flush=True,
            )

    all_df = pd.DataFrame(all_rows, columns=OUTPUT_COLUMNS)
    if candidate_rows:
        cand_df = pd.DataFrame(candidate_rows, columns=OUTPUT_COLUMNS).sort_values(
            ["alt_allele_fraction", "callable_depth", "position"],
            ascending=[False, False, True],
        )
    else:
        cand_df = pd.DataFrame(columns=OUTPUT_COLUMNS)

    callable_positions = int((all_df["callable_depth"] > 0).sum())
    uncallable_positions = int(len(all_df) - callable_positions)
    observed_fractions = pd.to_numeric(
        all_df["alt_allele_fraction"], errors="coerce"
    ).dropna()
    max_alt_fraction = (
        round(float(observed_fractions.max()), 6)
        if not observed_fractions.empty
        else float("nan")
    )
    module_status = "ok" if callable_positions else "not_evaluable"
    module_reason = "" if callable_positions else "no_callable_positions"
    summary_rows: list[dict[str, object]] = [
        {"metric": "status", "value": module_status},
        {"metric": "reason_code", "value": module_reason},
        {"metric": "positions_tested", "value": len(all_df)},
        {"metric": "callable_positions", "value": callable_positions},
        {"metric": "uncallable_positions", "value": uncallable_positions},
        {"metric": "candidate_sites", "value": len(cand_df)},
        {"metric": "min_callable_depth", "value": min_depth},
        {"metric": "min_alt_allele_fraction", "value": min_vaf},
        {"metric": "sites_alt_fraction_ge_0.10", "value": int((all_df["alt_allele_fraction"] >= 0.10).sum())},
        {"metric": "sites_alt_fraction_ge_0.05", "value": int((all_df["alt_allele_fraction"] >= 0.05).sum())},
        {"metric": "sites_alt_fraction_ge_0.02", "value": int((all_df["alt_allele_fraction"] >= 0.02).sum())},
        {"metric": "max_alt_allele_fraction", "value": max_alt_fraction},
        {"metric": "skipped_noncanonical_candidates", "value": skipped_noncanonical_candidates},
    ]
    summary_rows.extend(policy_rows(policy, counting.stats))
    summary_df = pd.DataFrame(summary_rows)

    all_path = summary_dir / "mito_heteroplasmy_all_sites.tsv"
    cand_path = summary_dir / "mito_heteroplasmy_candidates.tsv"
    summary_path = summary_dir / "mito_heteroplasmy_summary.tsv"
    report_path = report_dir / "02_mito_heteroplasmy.html"
    all_df.to_csv(all_path, sep="\t", index=False, na_rep="NA")
    cand_df.to_csv(cand_path, sep="\t", index=False, na_rep="NA")
    summary_df.to_csv(summary_path, sep="\t", index=False, na_rep="NA")

    plt.figure(figsize=(12, 4))
    plt.scatter(all_df["position"], all_df["alt_allele_fraction"], s=8, alpha=0.6)
    plt.axhline(min_vaf, color="red", linestyle="--", linewidth=1)
    plt.xlabel("Mitochondrial position")
    plt.ylabel("Observed alternate allele fraction")
    plt.title(f"{sample_id} mitochondrial alternate-allele landscape")
    plt.tight_layout()
    landscape_figure = figure_dir / "mito_heteroplasmy_landscape.png"
    plt.savefig(landscape_figure, dpi=150)
    plt.close()

    candidate_figure = None
    if not cand_df.empty:
        top = cand_df.head(20).copy()
        plt.figure(figsize=(10, 5))
        plt.bar(top["position"].astype(str), top["alt_allele_fraction"], color="#dc2626")
        plt.xticks(rotation=90)
        plt.ylabel("Observed alternate allele fraction")
        plt.title(f"{sample_id} top candidate sites")
        plt.tight_layout()
        candidate_figure = figure_dir / "mito_heteroplasmy_top_candidates.png"
        plt.savefig(candidate_figure, dpi=150)
        plt.close()

    metrics_html = "".join(
        [
            metric_card("Candidate sites", len(cand_df)),
            metric_card(
                "Maximum alt fraction",
                "NA" if pd.isna(max_alt_fraction) else round(max_alt_fraction, 4),
            ),
            metric_card("Minimum callable depth", min_depth),
            metric_card("Minimum alt fraction", min_vaf),
        ]
    )
    intro_html = (
        '<p class="muted">This page reports observed alternate allele fractions after explicit read, '
        "mapping, and base-quality filters. Candidate sites are screening results, not independently "
        "confirmed heteroplasmies or clinical variant calls.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Alternate-allele landscape</h2>"
        + figure_html(landscape_figure, "Observed alternate-allele fraction across mitochondrial positions")
        + "</section>",
        "<section><h2>Method and filter summary</h2>" + df_to_html_table(summary_df, max_rows=40) + "</section>",
        "<section><h2>Candidate sites</h2>" + df_to_html_table(cand_df, max_rows=30) + "</section>",
    ]
    if candidate_figure:
        body_parts.insert(
            1,
            "<section><h2>Top candidate sites</h2>"
            + figure_html(candidate_figure, "Candidate sites with the highest observed alternate fractions")
            + "</section>",
        )
    render_page(
        report_path,
        "Mitochondrial Alternate-Allele Screening",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        "".join(body_parts),
    )
    print(
        f"[heteroplasmy] finished sample={sample_id} candidates={len(cand_df)} "
        f"elapsed_sec={round(time.time() - start_time, 1)}",
        flush=True,
    )
    return {
        "status": module_status,
        "summary_path": summary_path,
        "candidate_path": cand_path,
        "all_sites_path": all_path,
        "report_path": report_path,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        bam=args.bam,
        ref_fasta=args.ref_fasta,
        summary_dir=args.summary_dir,
        figure_dir=args.figure_dir,
        report_dir=args.report_dir,
        sample_id=args.sample_id,
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
        min_depth=args.min_depth,
        min_vaf=args.min_vaf,
        min_base_quality=args.min_base_quality,
        min_mapping_quality=args.min_mapping_quality,
        min_read_mean_quality=args.min_read_mean_quality,
        max_depth=args.max_depth,
        exclude_flags=args.exclude_flags,
        ignore_overlaps=bool(args.ignore_overlaps),
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
