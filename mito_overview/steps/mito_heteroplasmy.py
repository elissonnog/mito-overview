"""Whole-mitochondrion heteroplasmy summary for mito-overview."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page


def candidate_strand_support(bam_path: str | Path, contig: str, positions: dict[int, str]) -> dict[int, tuple[int, int]]:
    """Compute forward/reverse alt support for candidate sites."""

    support: dict[int, tuple[int, int]] = {}
    if not positions:
        return support
    bam = pysam.AlignmentFile(str(bam_path), "rb")
    total = len(positions)
    start_time = time.time()
    for idx, pos in enumerate(sorted(positions), start=1):
        alt_forward = 0
        alt_reverse = 0
        alt_base = positions[pos]
        for pileupcolumn in bam.pileup(
            contig,
            pos - 1,
            pos,
            truncate=True,
            stepper="all",
            min_base_quality=0,
        ):
            if pileupcolumn.reference_pos != pos - 1:
                continue
            for pileupread in pileupcolumn.pileups:
                if pileupread.is_del or pileupread.is_refskip:
                    continue
                qpos = pileupread.query_position
                if qpos is None:
                    continue
                base = pileupread.alignment.query_sequence[qpos].upper()
                if base != alt_base:
                    continue
                if pileupread.alignment.is_reverse:
                    alt_reverse += 1
                else:
                    alt_forward += 1
        support[pos] = (alt_forward, alt_reverse)
        if idx % 25 == 0 or idx == total:
            print(
                f"[heteroplasmy] candidate strand support {idx}/{total} "
                f"elapsed_sec={round(time.time() - start_time, 1)}",
                flush=True,
            )
    bam.close()
    return support


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
) -> dict[str, Path]:
    """Run the public mitochondrial heteroplasmy step."""

    start_time = time.time()
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    fasta = pysam.FastaFile(str(ref_fasta))
    ref_seq = fasta.fetch(mt_contig, 0, mt_length).upper()
    bam_handle = pysam.AlignmentFile(str(bam), "rb")
    print(
        f"[heteroplasmy] starting sample={sample_id} contig={mt_contig} "
        f"length={mt_length} min_depth={min_depth} min_vaf={min_vaf}",
        flush=True,
    )

    print("[heteroplasmy] counting base coverage across mitochondrial genome", flush=True)
    cov_a, cov_c, cov_g, cov_t = bam_handle.count_coverage(
        mt_contig,
        0,
        mt_length,
        quality_threshold=0,
        read_callback="nofilter",
    )
    bam_handle.close()
    fasta.close()
    print(
        f"[heteroplasmy] coverage counting complete "
        f"elapsed_sec={round(time.time() - start_time, 1)}",
        flush=True,
    )

    all_rows = []
    candidate_rows = []
    for pos in range(1, mt_length + 1):
        base_counts = {
            "A": int(cov_a[pos - 1]),
            "C": int(cov_c[pos - 1]),
            "G": int(cov_g[pos - 1]),
            "T": int(cov_t[pos - 1]),
        }
        depth = sum(base_counts.values())
        ref_base = ref_seq[pos - 1]
        non_ref = {base: count for base, count in base_counts.items() if base != ref_base}
        alt_base, alt_count = max(non_ref.items(), key=lambda item: item[1]) if non_ref else (None, 0)
        vaf = (alt_count / depth) if depth else 0.0
        row = {
            "position": pos,
            "ref_base": ref_base,
            "alt_base": alt_base or ".",
            "depth": depth,
            "alt_count": alt_count,
            "heteroplasmy_fraction": round(vaf, 6),
            "A": base_counts["A"],
            "C": base_counts["C"],
            "G": base_counts["G"],
            "T": base_counts["T"],
        }
        all_rows.append(row)
        if depth >= min_depth and alt_base and vaf >= min_vaf:
            candidate_rows.append(row.copy())
        if pos % 4000 == 0 or pos == mt_length:
            print(
                f"[heteroplasmy] summarised positions {pos}/{mt_length} "
                f"elapsed_sec={round(time.time() - start_time, 1)}",
                flush=True,
            )

    if candidate_rows:
        strand_support = candidate_strand_support(
            bam,
            mt_contig,
            {row["position"]: row["alt_base"] for row in candidate_rows},
        )
        for row in candidate_rows:
            alt_forward, alt_reverse = strand_support.get(row["position"], (0, 0))
            row["alt_forward"] = alt_forward
            row["alt_reverse"] = alt_reverse

    all_df = pd.DataFrame(all_rows)
    if candidate_rows:
        cand_df = pd.DataFrame(candidate_rows).sort_values(
            ["heteroplasmy_fraction", "depth"],
            ascending=[False, False],
        )
    else:
        cand_df = pd.DataFrame(
            columns=[
                "position",
                "ref_base",
                "alt_base",
                "depth",
                "alt_count",
                "heteroplasmy_fraction",
                "alt_forward",
                "alt_reverse",
            ]
        )

    summary_df = pd.DataFrame(
        [
            {"metric": "positions_tested", "value": len(all_df)},
            {"metric": f"candidate_sites_vaf>={min_vaf}", "value": len(cand_df)},
            {"metric": "sites_vaf>=0.10", "value": int((all_df["heteroplasmy_fraction"] >= 0.10).sum())},
            {"metric": "sites_vaf>=0.05", "value": int((all_df["heteroplasmy_fraction"] >= 0.05).sum())},
            {"metric": "sites_vaf>=0.02", "value": int((all_df["heteroplasmy_fraction"] >= 0.02).sum())},
            {"metric": "max_heteroplasmy_fraction", "value": round(float(all_df["heteroplasmy_fraction"].max()), 6)},
        ]
    )

    all_path = summary_dir / "mito_heteroplasmy_all_sites.tsv"
    cand_path = summary_dir / "mito_heteroplasmy_candidates.tsv"
    summary_path = summary_dir / "mito_heteroplasmy_summary.tsv"
    report_path = report_dir / "02_mito_heteroplasmy.html"
    all_df.to_csv(all_path, sep="\t", index=False)
    cand_df.to_csv(cand_path, sep="\t", index=False)
    summary_df.to_csv(summary_path, sep="\t", index=False)

    plt.figure(figsize=(12, 4))
    plt.scatter(all_df["position"], all_df["heteroplasmy_fraction"], s=8, alpha=0.6)
    plt.axhline(min_vaf, color="red", linestyle="--", linewidth=1)
    plt.xlabel("Mitochondrial position")
    plt.ylabel("Alt fraction")
    plt.title(f"{sample_id} mitochondrial heteroplasmy landscape")
    plt.tight_layout()
    fig1 = figure_dir / "mito_heteroplasmy_landscape.png"
    plt.savefig(fig1, dpi=150)
    plt.close()

    fig2 = None
    if not cand_df.empty:
        top = cand_df.head(20).copy()
        plt.figure(figsize=(10, 5))
        plt.bar(top["position"].astype(str), top["heteroplasmy_fraction"], color="#dc2626")
        plt.xticks(rotation=90)
        plt.ylabel("Alt fraction")
        plt.title(f"{sample_id} top candidate heteroplasmies")
        plt.tight_layout()
        fig2 = figure_dir / "mito_heteroplasmy_top_candidates.png"
        plt.savefig(fig2, dpi=150)
        plt.close()

    metrics_html = "".join(
        [
            metric_card("Candidate sites", len(cand_df)),
            metric_card("Max heteroplasmy", round(float(all_df["heteroplasmy_fraction"].max()), 4)),
            metric_card("Min depth threshold", min_depth),
            metric_card("Min VAF threshold", min_vaf),
        ]
    )
    intro_html = (
        '<p class="muted">Site-wise mitochondrial heteroplasmy summary based on all mitochondrial reads. '
        "Candidate sites are reported conservatively using user-level depth and VAF thresholds.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Heteroplasmy landscape</h2>"
        + figure_html(fig1, "Alt-fraction across mitochondrial positions")
        + "</section>",
        "<section><h2>Summary metrics</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>",
        "<section><h2>Candidate heteroplasmy sites</h2>" + df_to_html_table(cand_df, max_rows=30) + "</section>",
    ]
    if fig2:
        body_parts.insert(
            1,
            "<section><h2>Top candidate sites</h2>"
            + figure_html(fig2, "Highest-confidence mitochondrial heteroplasmy candidates")
            + "</section>",
        )

    render_page(
        report_path,
        "Mitochondrial Heteroplasmy",
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
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
