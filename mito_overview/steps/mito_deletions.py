"""Whole-mitochondrion deletion summary for mito-overview."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page

CIGAR_DEL = 2
EVENT_COLUMNS = [
    "read_name",
    "event_start",
    "event_end",
    "deletion_size",
    "event_bin_start",
    "event_bin_end",
    "is_primary_read",
    "has_sa_tag",
]
CLUSTER_COLUMNS = [
    "event_bin_start",
    "event_bin_end",
    "supporting_reads",
    "median_deletion_size",
    "min_deletion_size",
    "max_deletion_size",
    "support_fraction_primary",
]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bam", required=True)
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--min-deletion-size", type=int, default=100)
    return parser


def run_step(
    *,
    bam: str | Path,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    min_deletion_size: int,
) -> dict[str, Path]:
    """Run the public mitochondrial deletion screen."""

    print(
        f"[deletions] starting sample={sample_id} contig={mt_contig} "
        f"length={mt_length} min_deletion_size={min_deletion_size}"
    )
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    bam_handle = pysam.AlignmentFile(str(bam), "rb")
    event_rows: list[dict[str, object]] = []
    read_rows: list[dict[str, object]] = []
    primary_read_names: set[str] = set()
    read_names_with_large_deletion: set[str] = set()
    read_names_with_supplementary_or_sa: set[str] = set()
    processed_reads = 0
    event_counter = Counter()

    for read in bam_handle.fetch(mt_contig):
        if read.is_unmapped or read.is_secondary:
            continue
        processed_reads += 1
        if processed_reads % 5000 == 0:
            print(
                f"[deletions] scanned alignment_records={processed_reads} "
                f"events={len(event_rows)}"
            )
        if not read.is_supplementary:
            primary_read_names.add(read.query_name)
        if read.has_tag("SA") or read.is_supplementary:
            read_names_with_supplementary_or_sa.add(read.query_name)

        has_large = False
        ref_pos = read.reference_start + 1
        for op, length in (read.cigartuples or []):
            if op in (0, 7, 8, 2, 3):
                if op == CIGAR_DEL and length >= min_deletion_size:
                    start = ref_pos
                    end = ref_pos + length - 1
                    key = (int(start / 10) * 10, int(end / 10) * 10)
                    event_counter[key] += 1
                    event_rows.append(
                        {
                            "read_name": read.query_name,
                            "event_start": start,
                            "event_end": end,
                            "deletion_size": length,
                            "event_bin_start": key[0],
                            "event_bin_end": key[1],
                            "is_primary_read": int(not read.is_supplementary),
                            "has_sa_tag": int(read.has_tag("SA")),
                        }
                    )
                    has_large = True
                ref_pos += length
            elif op in (1, 4, 5, 6):
                continue
        if has_large:
            read_names_with_large_deletion.add(read.query_name)
        read_rows.append(
            {
                "read_name": read.query_name,
                "has_large_deletion": int(has_large),
                "is_supplementary": int(read.is_supplementary),
                "has_sa_tag": int(read.has_tag("SA")),
            }
        )
    bam_handle.close()
    primary_reads = len(primary_read_names)
    reads_with_large_deletion = len(read_names_with_large_deletion)
    reads_with_supplementary = len(read_names_with_supplementary_or_sa)
    print(f"[deletions] finished scanning primary_reads={primary_reads} candidate_events={len(event_rows)}")

    event_df = pd.DataFrame(event_rows, columns=EVENT_COLUMNS)
    read_df = pd.DataFrame(read_rows)
    if not event_df.empty:
        cluster_df = (
            event_df.groupby(["event_bin_start", "event_bin_end"], as_index=False)
            .agg(
                supporting_reads=("read_name", "nunique"),
                median_deletion_size=("deletion_size", "median"),
                min_deletion_size=("deletion_size", "min"),
                max_deletion_size=("deletion_size", "max"),
            )
            .sort_values(["supporting_reads", "median_deletion_size"], ascending=[False, False])
        )
        supporting_primary_reads = (
            event_df.assign(
                has_primary_alignment=event_df["read_name"].isin(primary_read_names).astype(int)
            )
            .loc[lambda frame: frame["has_primary_alignment"] == 1]
            .groupby(["event_bin_start", "event_bin_end"])["read_name"]
            .nunique()
        )
        cluster_keys = pd.MultiIndex.from_frame(cluster_df[["event_bin_start", "event_bin_end"]])
        primary_support_counts = supporting_primary_reads.reindex(cluster_keys, fill_value=0).to_numpy()
        cluster_df["support_fraction_primary"] = [
            round(int(count) / primary_reads, 6) if primary_reads else 0.0
            for count in primary_support_counts
        ]
    else:
        cluster_df = pd.DataFrame(columns=CLUSTER_COLUMNS)

    summary_df = pd.DataFrame(
        [
            {"metric": "primary_reads", "value": primary_reads},
            {"metric": "reads_with_large_deletion", "value": reads_with_large_deletion},
            {"metric": "reads_with_supplementary_or_SA", "value": reads_with_supplementary},
            {"metric": "candidate_deletion_clusters", "value": len(cluster_df)},
            {
                "metric": "largest_median_deletion",
                "value": float(cluster_df["median_deletion_size"].max()) if not cluster_df.empty else 0,
            },
            {
                "metric": "max_support_fraction_primary",
                "value": float(cluster_df["support_fraction_primary"].max()) if not cluster_df.empty else 0,
            },
        ]
    )

    summary_path = summary_dir / "mito_deletion_summary.tsv"
    events_path = summary_dir / "mito_deletion_events.tsv"
    clusters_path = summary_dir / "mito_deletion_clusters.tsv"
    reads_path = summary_dir / "mito_deletion_read_flags.tsv"
    summary_df.to_csv(summary_path, sep="\t", index=False)
    event_df.to_csv(events_path, sep="\t", index=False)
    cluster_df.to_csv(clusters_path, sep="\t", index=False)
    read_df.to_csv(reads_path, sep="\t", index=False)

    fig_path = None
    if not cluster_df.empty:
        top = cluster_df.head(15).copy()
        labels = [f"{int(r.event_bin_start)}-{int(r.event_bin_end)}" for r in top.itertuples()]
        plt.figure(figsize=(10, 5))
        plt.bar(labels, top["supporting_reads"], color="#b91c1c")
        plt.xticks(rotation=90)
        plt.ylabel("Supporting reads")
        plt.title(f"{sample_id} qualifying CIGAR-deletion bins")
        plt.tight_layout()
        fig_path = figure_dir / "mito_deletion_clusters.png"
        plt.savefig(fig_path, dpi=150)
        plt.close()

    metrics_html = "".join(
        [
            metric_card("Primary reads", primary_reads),
            metric_card("Reads with qualifying CIGAR deletion", reads_with_large_deletion),
            metric_card("CIGAR-deletion bins", len(cluster_df)),
            metric_card("Min deletion size", min_deletion_size),
        ]
    )
    intro_html = (
        '<p class="muted">Only CIGAR deletion operations meeting the configured minimum size of '
        f"{min_deletion_size} bp create or support candidate bins, whether they occur on retained primary or "
        "supplementary alignment records. Supplementary-alignment status and SA tags are summarized separately "
        "as alignment-structure evidence and do not create bin support on their own. This page is intended as a "
        "structural screen rather than a finalized SV caller output. The supporting_reads field counts all unique "
        "read names with qualifying CIGAR-deletion evidence in a bin. The compatibility field "
        "support_fraction_primary uses only those supporting read names that also have a retained primary "
        "mitochondrial alignment as its numerator and all unique retained primary mitochondrial read names as "
        "its denominator; supplementary-only records remain in the event evidence but cannot make this fraction "
        "exceed one.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Deletion summary</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>",
        "<section><h2>Qualifying CIGAR-deletion bins</h2>"
        + df_to_html_table(cluster_df, max_rows=25)
        + "</section>",
        "<section><h2>Qualifying CIGAR-deletion events</h2>"
        + df_to_html_table(event_df, max_rows=30)
        + "</section>",
    ]
    if fig_path:
        body_parts.insert(
            1,
            "<section><h2>Top CIGAR-deletion bins</h2>"
            + figure_html(fig_path, "Top mitochondrial CIGAR-deletion bins")
            + "</section>",
        )

    report_path = report_dir / "03_mito_deletions.html"
    render_page(
        report_path,
        "Mitochondrial Deletions",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        "".join(body_parts),
    )
    return {
        "summary_path": summary_path,
        "events_path": events_path,
        "clusters_path": clusters_path,
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
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
        min_deletion_size=args.min_deletion_size,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
