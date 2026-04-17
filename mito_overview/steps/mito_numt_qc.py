"""NUMT-aware mitochondrial QC summary for mito-overview."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page

SUMMARY_COLUMNS = ["metric", "value"]
READ_TABLE_COLUMNS = [
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
FRACTION_PLOT_COLUMNS = ["metric", "fraction"]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    return parser


def risk_label(score: int) -> str:
    """Convert a heuristic risk score to a label."""

    if score >= 4:
        return "high"
    if score >= 2:
        return "moderate"
    return "low"


def load_summary_table(path: Path) -> pd.DataFrame:
    """Load a TSV summary table if present, otherwise return an empty schema."""

    if not path.exists():
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    try:
        df = pd.read_csv(path, sep="\t")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    return df


def load_reads_table(path: Path) -> pd.DataFrame:
    """Load read-level mitochondrial stats if present."""

    if not path.exists():
        return pd.DataFrame(columns=READ_TABLE_COLUMNS)
    try:
        df = pd.read_csv(path, sep="\t")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=READ_TABLE_COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=READ_TABLE_COLUMNS)
    return df


def column_fraction(df: pd.DataFrame, column: str, predicate) -> float:
    """Return the fraction of rows matching a predicate for a column."""

    if df.empty or column not in df.columns:
        return 0.0
    series = df[column]
    return float(predicate(series).mean()) if not series.empty else 0.0


def extract_metric_value(summary_df: pd.DataFrame, metric: str) -> float:
    """Extract a numeric metric from a metric/value summary table."""

    if summary_df.empty or "metric" not in summary_df.columns or "value" not in summary_df.columns:
        return 0.0
    hit = summary_df.loc[summary_df["metric"] == metric, "value"]
    if hit.empty:
        return 0.0
    value = pd.to_numeric(hit, errors="coerce").dropna()
    if value.empty:
        return 0.0
    return float(value.iloc[0])


def render_no_reads_report(
    *,
    summary_path: Path,
    report_path: Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
) -> dict[str, Path]:
    """Write outputs for runs without mitochondrial read-level stats."""

    print("[numt_qc] no mito_read_stats.tsv available; writing status-only outputs", flush=True)
    summary_df = pd.DataFrame(
        [{"metric": "status", "value": "no_read_stats_available"}],
        columns=SUMMARY_COLUMNS,
    )
    summary_df.to_csv(summary_path, sep="\t", index=False)
    intro_html = (
        '<p class="muted">NUMT-aware QC could not be computed because read-level mitochondrial '
        "alignment statistics were not available.</p>"
    )
    body_html = "<section><h2>Status</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>"
    render_page(
        report_path,
        "Mito NUMT-aware QC",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
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
) -> dict[str, Path]:
    """Run the public NUMT-aware mitochondrial QC step."""

    print(f"[numt_qc] starting sample={sample_id} contig={mt_contig} length={mt_length}", flush=True)
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    reads_path = summary_dir / "mito_read_stats.tsv"
    qc_path = summary_dir / "mito_qc_summary.tsv"
    summary_path = summary_dir / "mito_numt_qc_summary.tsv"
    report_path = report_dir / "08_mito_numt_qc.html"
    scatter_fig = figure_dir / "mito_numt_qc_mapq_vs_span.png"
    metrics_fig = figure_dir / "mito_numt_qc_metric_bars.png"

    reads_df = load_reads_table(reads_path)
    qc_df = load_summary_table(qc_path)
    print(
        f"[numt_qc] loaded reads_rows={len(reads_df)} qc_rows={len(qc_df)} "
        f"reads_source_exists={reads_path.exists()} qc_source_exists={qc_path.exists()}",
        flush=True,
    )

    if reads_df.empty:
        return render_no_reads_report(
            summary_path=summary_path,
            report_path=report_path,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
        )

    if "is_primary" in reads_df.columns:
        primary_df = reads_df[reads_df["is_primary"] == 1].copy()
    else:
        primary_df = reads_df.copy()
    eval_df = primary_df if not primary_df.empty else reads_df.copy()
    print(
        f"[numt_qc] evaluating reads_rows={len(eval_df)} primary_rows={len(primary_df)} "
        f"fallback_to_all_reads={int(primary_df.empty)}",
        flush=True,
    )

    low_mapq_fraction = column_fraction(eval_df, "mapq", lambda s: s < 20)
    very_low_mapq_fraction = column_fraction(eval_df, "mapq", lambda s: s < 5)
    short_span_fraction = column_fraction(eval_df, "aligned_fraction_mt", lambda s: s < 0.50)
    heavy_softclip_fraction = column_fraction(eval_df, "softclip_fraction", lambda s: s > 0.20)
    sa_fraction = column_fraction(eval_df, "has_sa_tag", lambda s: s == 1)
    supplementary_fraction = column_fraction(reads_df, "is_supplementary", lambda s: s == 1)
    full_length_fraction = extract_metric_value(qc_df, "full_length_fraction")

    risk_score = 0
    risk_score += 1 if low_mapq_fraction > 0.10 else 0
    risk_score += 1 if very_low_mapq_fraction > 0.02 else 0
    risk_score += 1 if short_span_fraction > 0.35 else 0
    risk_score += 1 if heavy_softclip_fraction > 0.10 else 0
    risk_score += 1 if sa_fraction > 0.05 else 0
    risk_score += 1 if supplementary_fraction > 0.15 else 0
    risk_score += 1 if full_length_fraction < 0.01 else 0
    risk = risk_label(risk_score)
    print(
        f"[numt_qc] fractions low_mapq={low_mapq_fraction:.4f} very_low_mapq={very_low_mapq_fraction:.4f} "
        f"short_span={short_span_fraction:.4f} heavy_softclip={heavy_softclip_fraction:.4f} "
        f"sa={sa_fraction:.4f} supplementary={supplementary_fraction:.4f} "
        f"full_length={full_length_fraction:.4f} risk={risk} score={risk_score}",
        flush=True,
    )

    summary_df = pd.DataFrame(
        [
            {"metric": "reads_evaluated", "value": int(len(eval_df))},
            {"metric": "low_mapq_fraction_lt20", "value": round(low_mapq_fraction, 6)},
            {"metric": "very_low_mapq_fraction_lt5", "value": round(very_low_mapq_fraction, 6)},
            {"metric": "short_aligned_fraction_lt0.5_mt", "value": round(short_span_fraction, 6)},
            {"metric": "heavy_softclip_fraction_gt0.2", "value": round(heavy_softclip_fraction, 6)},
            {"metric": "sa_tag_fraction", "value": round(sa_fraction, 6)},
            {"metric": "supplementary_fraction_all_reads", "value": round(supplementary_fraction, 6)},
            {"metric": "full_length_fraction", "value": round(full_length_fraction, 6)},
            {"metric": "heuristic_numt_risk", "value": risk},
            {"metric": "heuristic_numt_risk_score", "value": int(risk_score)},
        ],
        columns=SUMMARY_COLUMNS,
    )
    summary_df.to_csv(summary_path, sep="\t", index=False)
    print(f"[numt_qc] wrote summary table {summary_path}", flush=True)

    metric_plot_df = pd.DataFrame(
        {
            "metric": [
                "low_mapq",
                "very_low_mapq",
                "short_span",
                "heavy_softclip",
                "sa_tag",
                "supplementary",
            ],
            "fraction": [
                low_mapq_fraction,
                very_low_mapq_fraction,
                short_span_fraction,
                heavy_softclip_fraction,
                sa_fraction,
                supplementary_fraction,
            ],
        },
        columns=FRACTION_PLOT_COLUMNS,
    )

    scatter_fig_created = False
    if not eval_df.empty and {"aligned_fraction_mt", "mapq"}.issubset(eval_df.columns):
        plt.figure(figsize=(8, 5))
        plt.scatter(eval_df["aligned_fraction_mt"], eval_df["mapq"], s=8, alpha=0.4, color="#2563eb")
        plt.axvline(0.50, color="#dc2626", linestyle="--", linewidth=1)
        plt.axhline(20, color="#dc2626", linestyle="--", linewidth=1)
        plt.xlabel("Aligned fraction of mitochondrial contig")
        plt.ylabel("MAPQ")
        plt.title(f"{sample_id} mito alignment span vs MAPQ")
        plt.tight_layout()
        plt.savefig(scatter_fig, dpi=150)
        plt.close()
        scatter_fig_created = True
        print(f"[numt_qc] wrote scatter figure {scatter_fig}", flush=True)
    else:
        print("[numt_qc] skipped scatter figure because aligned span or MAPQ columns were unavailable", flush=True)

    plt.figure(figsize=(8, 4))
    plt.bar(metric_plot_df["metric"], metric_plot_df["fraction"], color="#7c3aed")
    plt.xticks(rotation=20)
    plt.ylabel("Fraction of reads")
    plt.title(f"{sample_id} mito QC fractions used for NUMT-aware warning")
    plt.tight_layout()
    plt.savefig(metrics_fig, dpi=150)
    plt.close()
    print(f"[numt_qc] wrote metric figure {metrics_fig}", flush=True)

    metrics_html = "".join(
        [
            metric_card("Heuristic NUMT risk", risk),
            metric_card("Risk score", int(risk_score)),
            metric_card("Low MAPQ fraction", round(low_mapq_fraction, 4)),
            metric_card("Short-span fraction", round(short_span_fraction, 4)),
            metric_card("Heavy soft-clip fraction", round(heavy_softclip_fraction, 4)),
            metric_card("Full-length fraction", round(full_length_fraction, 4)),
        ]
    )
    intro_html = (
        '<p class="muted">This page provides a conservative, heuristic warning layer for '
        "mitochondrial reads that may be more vulnerable to NUMT-like interpretation issues. "
        "The summary is based on read-level alignment structure, including MAPQ, mitochondrial "
        "span coverage, soft clipping, supplementary alignments, and SA-tag frequency. "
        "It is intended as QC context rather than a formal NUMT classifier.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )

    body_parts = [
        "<section><h2>NUMT-aware QC summary</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>",
        "<section><h2>QC-fraction overview</h2>"
        + figure_html(metrics_fig, "Fractions contributing to the heuristic NUMT-risk score")
        + "</section>",
        "<section><h2>Read-level mitochondrial alignment table</h2>"
        + df_to_html_table(eval_df, max_rows=30)
        + "</section>",
    ]
    if scatter_fig_created:
        body_parts.insert(
            1,
            "<section><h2>MAPQ vs aligned mitochondrial span</h2>"
            + figure_html(scatter_fig, "Primary-read mitochondrial span fraction against MAPQ")
            + "</section>",
        )
    else:
        body_parts.insert(
            1,
            "<section><h2>MAPQ vs aligned mitochondrial span</h2>"
            "<p class='muted'>Scatter plot unavailable because the required aligned-span or MAPQ "
            "columns were not present in the input read table.</p>"
            "</section>",
        )

    render_page(
        report_path,
        "Mito NUMT-aware QC",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        "".join(body_parts),
    )
    print(f"[numt_qc] wrote report {report_path}", flush=True)
    outputs = {
        "summary_path": summary_path,
        "metrics_figure_path": metrics_fig,
        "report_path": report_path,
    }
    if scatter_fig_created:
        outputs["scatter_figure_path"] = scatter_fig
    return outputs


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        summary_dir=args.summary_dir,
        figure_dir=args.figure_dir,
        report_dir=args.report_dir,
        sample_id=args.sample_id,
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
