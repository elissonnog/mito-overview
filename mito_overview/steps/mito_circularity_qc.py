"""Circularity-aware mitochondrial QC for mito-overview."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page

SUMMARY_COLUMNS = ["metric", "value"]
DEPTH_COLUMNS = ["position", "depth"]
READ_COLUMNS = [
    "read_name",
    "mapq",
    "query_length",
    "read_start",
    "read_end",
    "aligned_span",
    "aligned_fraction_mt",
    "softclip_bases",
    "softclip_fraction",
    "has_sa_tag",
    "is_primary",
    "is_supplementary",
    "is_secondary",
    "is_reverse",
]
CANDIDATE_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "depth",
    "alt_count",
    "heteroplasmy_fraction",
    "A",
    "C",
    "G",
    "T",
    "alt_forward",
    "alt_reverse",
]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--edge-window", type=int, default=500)
    return parser


def load_depth_table(path: Path) -> pd.DataFrame:
    """Load depth-per-base output if present and well formed."""

    if not path.exists():
        return pd.DataFrame(columns=DEPTH_COLUMNS)
    try:
        df = pd.read_csv(path, sep="\t")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=DEPTH_COLUMNS)
    if df.empty or not {"position", "depth"}.issubset(df.columns):
        return pd.DataFrame(columns=DEPTH_COLUMNS)
    df = df.copy()
    df["position"] = pd.to_numeric(df["position"], errors="coerce")
    df["depth"] = pd.to_numeric(df["depth"], errors="coerce")
    df = df.dropna(subset=["position", "depth"]).copy()
    if df.empty:
        return pd.DataFrame(columns=DEPTH_COLUMNS)
    df["position"] = df["position"].astype(int)
    return df


def load_optional_table(path: Path, columns: list[str]) -> pd.DataFrame:
    """Load an optional TSV and preserve a predictable schema."""

    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, sep="\t")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)
    if df.empty:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in df.columns:
            df[column] = pd.NA
    return df


def render_status_page(
    *,
    summary_path: Path,
    report_path: Path,
    sample_id: str,
    mt_contig: str,
    message: str,
) -> dict[str, Path]:
    """Write a status-only page when circularity inputs are unavailable."""

    print(f"[circularity_qc] {message}", flush=True)
    summary_df = pd.DataFrame(
        [{"metric": "status", "value": "no_depth_profile_available"}],
        columns=SUMMARY_COLUMNS,
    )
    summary_df.to_csv(summary_path, sep="\t", index=False)
    intro_html = (
        "<p class=\"muted\">Circularity QC could not be computed because the "
        "mitochondrial depth profile was unavailable.</p>"
    )
    body_html = "<section><h2>Status</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>"
    render_page(
        report_path,
        "Mito Circularity QC",
        sample_id,
        f"{mt_contig}:whole_mito",
        intro_html,
        body_html,
    )
    return {
        "summary_path": summary_path,
        "report_path": report_path,
    }


def run_step(
    *,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    edge_window: int = 500,
) -> dict[str, Path]:
    """Run the public mitochondrial circularity QC step."""

    print(
        f"[circularity_qc] starting sample={sample_id} contig={mt_contig} "
        f"length={mt_length} edge_window={edge_window}",
        flush=True,
    )
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    depth_path = summary_dir / "mito_depth_per_base.tsv"
    reads_path = summary_dir / "mito_read_stats.tsv"
    candidates_path = summary_dir / "mito_heteroplasmy_candidates.tsv"
    summary_path = summary_dir / "mito_circularity_qc_summary.tsv"
    report_path = report_dir / "11_mito_circularity_qc.html"
    depth_fig = figure_dir / "mito_circularity_edge_depth.png"
    edge_fig = figure_dir / "mito_circularity_edge_metrics.png"

    depth_df = load_depth_table(depth_path)
    reads_df = load_optional_table(reads_path, READ_COLUMNS)
    candidates_df = load_optional_table(candidates_path, CANDIDATE_COLUMNS)
    print(
        f"[circularity_qc] loaded depth_rows={len(depth_df)} reads_rows={len(reads_df)} "
        f"candidate_rows={len(candidates_df)} depth_exists={depth_path.exists()} "
        f"reads_exists={reads_path.exists()} candidates_exists={candidates_path.exists()}",
        flush=True,
    )

    if depth_df.empty:
        return render_status_page(
            summary_path=summary_path,
            report_path=report_path,
            sample_id=sample_id,
            mt_contig=mt_contig,
            message="no mito_depth_per_base.tsv available; writing status-only outputs",
        )

    edge = min(edge_window, max(1, mt_length // 10))
    first_edge = depth_df[depth_df["position"] <= edge].copy()
    last_edge = depth_df[depth_df["position"] > (mt_length - edge)].copy()
    interior = depth_df[
        (depth_df["position"] > edge) & (depth_df["position"] <= (mt_length - edge))
    ].copy()

    edge_candidates = pd.DataFrame(columns=candidates_df.columns)
    candidate_edge_fraction = 0.0
    if not candidates_df.empty and "position" in candidates_df.columns:
        candidate_positions = pd.to_numeric(candidates_df["position"], errors="coerce")
        edge_mask = (candidate_positions <= edge) | (candidate_positions > (mt_length - edge))
        edge_candidates = candidates_df.loc[edge_mask.fillna(False)].copy()
        candidate_edge_fraction = float(len(edge_candidates) / len(candidates_df)) if len(candidates_df) else 0.0

    if "is_primary" in reads_df.columns:
        primary_mask = pd.to_numeric(reads_df["is_primary"], errors="coerce") == 1
        reads_eval = reads_df.loc[primary_mask.fillna(False)].copy()
    else:
        reads_eval = reads_df.copy()

    edge_start_fraction = 0.0
    if not reads_eval.empty and "read_start" in reads_eval.columns:
        read_start = pd.to_numeric(reads_eval["read_start"], errors="coerce")
        read_start = read_start.dropna()
        if not read_start.empty:
            edge_start_fraction = float((read_start <= edge).mean())

    edge_end_fraction = 0.0
    if not reads_eval.empty and "read_end" in reads_eval.columns:
        read_end = pd.to_numeric(reads_eval["read_end"], errors="coerce")
        read_end = read_end.dropna()
        if not read_end.empty:
            edge_end_fraction = float((read_end > (mt_length - edge)).mean())

    edge_softclip_fraction = 0.0
    softclip_columns = {"read_start", "read_end", "softclip_fraction"}
    if not reads_eval.empty and softclip_columns.issubset(reads_eval.columns):
        softclip_df = reads_eval.loc[:, ["read_start", "read_end", "softclip_fraction"]].copy()
        for column in softclip_df.columns:
            softclip_df[column] = pd.to_numeric(softclip_df[column], errors="coerce")
        softclip_df = softclip_df.dropna()
        if not softclip_df.empty:
            edge_softclip_fraction = float(
                (
                    (
                        (softclip_df["read_start"] <= edge)
                        | (softclip_df["read_end"] > (mt_length - edge))
                    )
                    & (softclip_df["softclip_fraction"] > 0.20)
                ).mean()
            )

    mean_depth_first_edge = round(float(first_edge["depth"].mean()), 3) if not first_edge.empty else 0.0
    mean_depth_last_edge = round(float(last_edge["depth"].mean()), 3) if not last_edge.empty else 0.0
    mean_depth_interior = round(float(interior["depth"].mean()), 3) if not interior.empty else 0.0
    print(
        f"[circularity_qc] edge_bp={edge} first_edge_mean={mean_depth_first_edge:.3f} "
        f"last_edge_mean={mean_depth_last_edge:.3f} interior_mean={mean_depth_interior:.3f} "
        f"candidate_edge_fraction={candidate_edge_fraction:.4f} "
        f"edge_start_fraction={edge_start_fraction:.4f} edge_end_fraction={edge_end_fraction:.4f} "
        f"edge_softclip_fraction={edge_softclip_fraction:.4f}",
        flush=True,
    )

    summary_df = pd.DataFrame(
        [
            {"metric": "edge_window_bp", "value": int(edge)},
            {"metric": "mean_depth_first_edge", "value": mean_depth_first_edge},
            {"metric": "mean_depth_last_edge", "value": mean_depth_last_edge},
            {"metric": "mean_depth_interior", "value": mean_depth_interior},
            {"metric": "candidate_sites_total", "value": int(len(candidates_df))},
            {"metric": "candidate_sites_in_edges", "value": int(len(edge_candidates))},
            {"metric": "candidate_edge_fraction", "value": round(candidate_edge_fraction, 6)},
            {"metric": "primary_read_start_in_edge_fraction", "value": round(edge_start_fraction, 6)},
            {"metric": "primary_read_end_in_edge_fraction", "value": round(edge_end_fraction, 6)},
            {"metric": "edge_read_heavy_softclip_fraction", "value": round(edge_softclip_fraction, 6)},
        ],
        columns=SUMMARY_COLUMNS,
    )
    summary_df.to_csv(summary_path, sep="\t", index=False)
    print(f"[circularity_qc] wrote summary table {summary_path}", flush=True)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(first_edge["position"], first_edge["depth"], color="#2563eb")
    axes[0].set_title(f"{sample_id} first {edge} bp depth")
    axes[0].set_xlabel("Position")
    axes[0].set_ylabel("Depth")
    axes[1].plot(last_edge["position"], last_edge["depth"], color="#dc2626")
    axes[1].set_title(f"{sample_id} last {edge} bp depth")
    axes[1].set_xlabel("Position")
    axes[1].set_ylabel("Depth")
    plt.tight_layout()
    plt.savefig(depth_fig, dpi=150)
    plt.close(fig)

    edge_metric_df = pd.DataFrame(
        {
            "metric": [
                "candidate_edge_fraction",
                "edge_read_start_fraction",
                "edge_read_end_fraction",
                "edge_softclip_fraction",
            ],
            "value": [
                candidate_edge_fraction,
                edge_start_fraction,
                edge_end_fraction,
                edge_softclip_fraction,
            ],
        }
    )
    plt.figure(figsize=(8, 4))
    plt.bar(edge_metric_df["metric"], edge_metric_df["value"], color="#f59e0b")
    plt.xticks(rotation=25, ha="right")
    plt.ylabel("Fraction")
    plt.title(f"{sample_id} circularity edge-context fractions")
    plt.tight_layout()
    plt.savefig(edge_fig, dpi=150)
    plt.close()

    metrics_html = "".join(
        [
            metric_card("Edge window (bp)", int(edge)),
            metric_card("Edge candidate fraction", round(candidate_edge_fraction, 4)),
            metric_card("Edge read-start fraction", round(edge_start_fraction, 4)),
            metric_card("Edge read-end fraction", round(edge_end_fraction, 4)),
            metric_card("Edge heavy-softclip fraction", round(edge_softclip_fraction, 4)),
        ]
    )
    intro_html = (
        '<p class="muted">This page checks whether linear-reference edge effects could be contributing to the '
        "mitochondrial signal. The first and last edge windows of the mitochondrial contig are evaluated for "
        "depth behavior, candidate-site concentration, and read-boundary enrichment. The goal is to flag patterns "
        "that may deserve caution near the artificial break in the linearized mitochondrial reference.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_html = (
        "<section><h2>Circularity QC summary</h2>"
        + df_to_html_table(summary_df, max_rows=20)
        + "</section>"
        + "<section><h2>Depth near mitochondrial reference edges</h2>"
        + figure_html(depth_fig, "Depth across the first and last mitochondrial edge windows")
        + "</section>"
        + "<section><h2>Edge-context fractions</h2>"
        + figure_html(edge_fig, "Candidate-site and read-boundary fractions near linear-reference edges")
        + "</section>"
        + "<section><h2>Candidate sites in edge windows</h2>"
        + df_to_html_table(edge_candidates, max_rows=25)
        + "</section>"
    )
    render_page(
        report_path,
        "Mito Circularity QC",
        sample_id,
        f"{mt_contig}:whole_mito",
        intro_html,
        body_html,
    )
    print(f"[circularity_qc] wrote report {report_path}", flush=True)
    return {
        "summary_path": summary_path,
        "depth_figure_path": depth_fig,
        "edge_figure_path": edge_fig,
        "report_path": report_path,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        summary_dir=args.summary_dir,
        figure_dir=args.figure_dir,
        report_dir=args.report_dir,
        sample_id=args.sample_id,
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
        edge_window=args.edge_window,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
