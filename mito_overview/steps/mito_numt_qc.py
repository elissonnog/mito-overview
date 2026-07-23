"""NUMT-aware mitochondrial QC summary for mito-overview."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page

SUMMARY_COLUMNS = ["metric", "value"]
READ_TABLE_COLUMNS = [
    "read_name",
    "mapq",
    "query_length",
    "read_start",
    "read_end",
    "reference_span",
    "aligned_reference_bases",
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
REQUIRED_NUMT_READ_COLUMNS = frozenset(
    {
        "mapq",
        "aligned_fraction_mt",
        "aligned_reference_bases",
        "softclip_fraction",
        "has_sa_tag",
        "is_primary",
        "is_supplementary",
    }
)
REQUIRED_NUMT_SUMMARY_METRICS = frozenset()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--reference-scope", default="custom", choices=("whole_genome", "mt_only", "custom"))
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


def validated_numeric_series(
    df: pd.DataFrame,
    column: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    integer: bool = False,
    allowed_values: tuple[float, ...] | None = None,
) -> pd.Series | None:
    """Return numeric evidence only when every row satisfies its declared domain."""

    if df.empty or column not in df.columns:
        return None
    series = pd.to_numeric(df[column], errors="coerce")
    values = series.to_numpy(dtype=float)
    valid = np.isfinite(values)
    if minimum is not None:
        valid &= values >= minimum
    if maximum is not None:
        valid &= values <= maximum
    if integer:
        with np.errstate(invalid="ignore"):
            valid &= values == np.floor(values)
    if allowed_values is not None:
        valid &= np.isin(values, allowed_values)
    if series.empty or not bool(valid.all()):
        return None
    return series


NUMT_READ_DOMAINS = {
    "mapq": {"minimum": 0, "maximum": 255, "integer": True},
    "aligned_fraction_mt": {"minimum": 0, "maximum": 1},
    "aligned_reference_bases": {"minimum": 0, "integer": True},
    "softclip_fraction": {"minimum": 0, "maximum": 1},
    "has_sa_tag": {"integer": True, "allowed_values": (0, 1)},
    "is_primary": {"integer": True, "allowed_values": (0, 1)},
    "is_supplementary": {"integer": True, "allowed_values": (0, 1)},
}


def column_fraction(
    df: pd.DataFrame,
    column: str,
    predicate,
    **domain,
) -> float | None:
    """Return a fraction only when every row has valid in-domain evidence."""

    series = validated_numeric_series(df, column, **domain)
    if series is None:
        return None
    return float(predicate(series).mean())


def extract_metric_value(summary_df: pd.DataFrame, metric: str) -> float | None:
    """Extract one numeric metric without manufacturing a missing value."""

    if summary_df.empty or "metric" not in summary_df.columns or "value" not in summary_df.columns:
        return None
    hit = summary_df.loc[summary_df["metric"] == metric, "value"]
    if len(hit) != 1:
        return None
    value = pd.to_numeric(hit, errors="coerce").iloc[0]
    if pd.isna(value) or not np.isfinite(float(value)):
        return None
    return float(value)


def rounded_or_na(value: float | None, digits: int = 6) -> float | str:
    """Represent unavailable numeric metrics explicitly in public summary tables."""

    return "NA" if value is None else round(value, digits)


def display_metric(value: float | None, digits: int = 4) -> float | str:
    """Format an optional metric for report cards and progress messages."""

    return "unavailable" if value is None else round(value, digits)


def render_no_reads_report(
    *,
    summary_path: Path,
    report_path: Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    reference_scope: str,
) -> dict[str, Path]:
    """Write outputs for runs without mitochondrial read-level stats."""

    print("[numt_qc] no mito_read_stats.tsv available; writing status-only outputs", flush=True)
    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": "not_evaluable"},
            {"metric": "reason_code", "value": "no_read_stats_available"},
            {"metric": "reference_scope", "value": reference_scope},
            {"metric": "numt_interpretation_status", "value": "not_evaluable"},
        ],
        columns=SUMMARY_COLUMNS,
    )
    summary_df.to_csv(summary_path, sep="\t", index=False)
    intro_html = (
        '<p class="muted">Alignment-ambiguity QC could not be computed because read-level mitochondrial '
        "alignment statistics were not available.</p>"
    )
    body_html = "<section><h2>Status</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>"
    render_page(
        report_path,
        "Mito Alignment-Ambiguity QC",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        body_html,
    )
    return {
        "status": "not_evaluable",
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
    reference_scope: str = "custom",
) -> dict[str, Path | str]:
    """Run the public NUMT-aware mitochondrial QC step."""

    print(
        f"[numt_qc] starting sample={sample_id} contig={mt_contig} length={mt_length} "
        f"reference_scope={reference_scope}",
        flush=True,
    )
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
            reference_scope=reference_scope,
        )

    invalid_read_columns = sorted(
        column
        for column in REQUIRED_NUMT_READ_COLUMNS.intersection(reads_df.columns)
        if validated_numeric_series(
            reads_df,
            column,
            **NUMT_READ_DOMAINS[column],
        )
        is None
    )

    is_primary = validated_numeric_series(
        reads_df,
        "is_primary",
        **NUMT_READ_DOMAINS["is_primary"],
    )
    primary_indicator_valid = is_primary is not None
    if primary_indicator_valid:
        primary_df = reads_df[is_primary == 1].copy()
    else:
        primary_df = reads_df.iloc[0:0]
    primary_evidence_available = primary_indicator_valid and not primary_df.empty
    eval_df = primary_df if primary_evidence_available else reads_df.copy()
    print(
        f"[numt_qc] evaluating reads_rows={len(eval_df)} primary_rows={len(primary_df)} "
        f"fallback_to_all_reads={int(not primary_evidence_available)}",
        f"primary_indicator_valid={int(primary_indicator_valid)}",
        flush=True,
    )

    low_mapq_fraction = column_fraction(
        eval_df, "mapq", lambda s: s < 20, **NUMT_READ_DOMAINS["mapq"]
    )
    very_low_mapq_fraction = column_fraction(
        eval_df, "mapq", lambda s: s < 5, **NUMT_READ_DOMAINS["mapq"]
    )
    short_span_fraction = column_fraction(
        eval_df,
        "aligned_fraction_mt",
        lambda s: s < 0.50,
        **NUMT_READ_DOMAINS["aligned_fraction_mt"],
    )
    heavy_softclip_fraction = column_fraction(
        eval_df,
        "softclip_fraction",
        lambda s: s > 0.20,
        **NUMT_READ_DOMAINS["softclip_fraction"],
    )
    sa_fraction = column_fraction(
        eval_df, "has_sa_tag", lambda s: s == 1, **NUMT_READ_DOMAINS["has_sa_tag"]
    )
    supplementary_fraction = column_fraction(
        reads_df,
        "is_supplementary",
        lambda s: s == 1,
        **NUMT_READ_DOMAINS["is_supplementary"],
    )
    primary_full_length_fraction = column_fraction(
        primary_df,
        "aligned_fraction_mt",
        lambda s: s >= 0.90,
        **NUMT_READ_DOMAINS["aligned_fraction_mt"],
    )
    primary_full_length_reads: int | None = None
    if primary_full_length_fraction is not None:
        primary_full_length_reads = int(
            (pd.to_numeric(primary_df["aligned_fraction_mt"], errors="coerce") >= 0.90).sum()
        )
    qc_primary_full_length_fraction = extract_metric_value(
        qc_df, "primary_full_length_fraction"
    )
    qc_fraction_mismatch = bool(
        primary_full_length_fraction is not None
        and qc_primary_full_length_fraction is not None
        and abs(primary_full_length_fraction - qc_primary_full_length_fraction) > 0.0001
    )
    if primary_full_length_fraction is None:
        qc_fraction_crosscheck_status = "not_evaluable"
        qc_fraction_crosscheck_reason = "primary_full_length_fraction_unavailable"
    elif qc_primary_full_length_fraction is None:
        qc_fraction_crosscheck_status = "not_configured"
        qc_fraction_crosscheck_reason = "primary_full_length_fraction_missing_from_mito_qc"
    elif qc_fraction_mismatch:
        qc_fraction_crosscheck_status = "not_evaluable"
        qc_fraction_crosscheck_reason = "primary_full_length_fraction_mismatch"
    else:
        qc_fraction_crosscheck_status = "ok"
        qc_fraction_crosscheck_reason = ""

    missing_read_columns = sorted(REQUIRED_NUMT_READ_COLUMNS - set(reads_df.columns))
    if "metric" in qc_df.columns:
        available_summary_metrics = set(qc_df["metric"].dropna().astype(str))
    else:
        available_summary_metrics = set()
    missing_summary_metrics = sorted(REQUIRED_NUMT_SUMMARY_METRICS - available_summary_metrics)
    evidence_values = (
        low_mapq_fraction,
        very_low_mapq_fraction,
        short_span_fraction,
        heavy_softclip_fraction,
        sa_fraction,
        supplementary_fraction,
        primary_full_length_fraction,
    )
    evidence_complete = (
        not missing_read_columns
        and not invalid_read_columns
        and not missing_summary_metrics
        and primary_evidence_available
        and not qc_fraction_mismatch
        and all(value is not None for value in evidence_values)
    )

    risk_score: int | None = None
    risk: str | None = None
    if evidence_complete:
        risk_score = 0
        risk_score += 1 if low_mapq_fraction > 0.10 else 0
        risk_score += 1 if very_low_mapq_fraction > 0.02 else 0
        risk_score += 1 if short_span_fraction > 0.35 else 0
        risk_score += 1 if heavy_softclip_fraction > 0.10 else 0
        risk_score += 1 if sa_fraction > 0.05 else 0
        risk_score += 1 if supplementary_fraction > 0.15 else 0
        risk_score += 1 if primary_full_length_fraction < 0.01 else 0
        risk = risk_label(risk_score)

    if reference_scope != "whole_genome":
        interpretation_status = "not_evaluable"
        reason_code = f"reference_scope_{reference_scope}"
        reported_risk = "not_evaluable"
        reported_risk_score: int | str = "NA"
    elif not evidence_complete:
        interpretation_status = "not_evaluable"
        if "is_primary" in reads_df.columns and not primary_indicator_valid:
            reason_code = "numt_primary_indicator_invalid"
        elif invalid_read_columns:
            reason_code = "numt_read_stats_invalid_values"
        elif primary_indicator_valid and primary_df.empty:
            reason_code = "numt_primary_reads_unavailable"
        elif missing_read_columns and not missing_summary_metrics:
            reason_code = "numt_read_stats_missing_columns"
        elif missing_summary_metrics and not missing_read_columns:
            reason_code = "numt_qc_summary_missing_metrics"
        elif qc_fraction_mismatch:
            reason_code = "numt_primary_full_length_fraction_mismatch"
        else:
            reason_code = "numt_required_evidence_unavailable"
        reported_risk = "not_evaluable"
        reported_risk_score = "NA"
    else:
        interpretation_status = "ok"
        reason_code = ""
        reported_risk = risk
        reported_risk_score = risk_score
    print(
        f"[numt_qc] fractions low_mapq={display_metric(low_mapq_fraction)} "
        f"very_low_mapq={display_metric(very_low_mapq_fraction)} "
        f"short_span={display_metric(short_span_fraction)} "
        f"heavy_softclip={display_metric(heavy_softclip_fraction)} "
        f"sa={display_metric(sa_fraction)} supplementary={display_metric(supplementary_fraction)} "
        f"primary_near_complete_alignment={display_metric(primary_full_length_fraction)} "
        f"risk={reported_risk} "
        f"score={reported_risk_score} "
        f"missing_read_columns={','.join(missing_read_columns) or 'none'} "
        f"invalid_read_columns={','.join(invalid_read_columns) or 'none'} "
        f"missing_summary_metrics={','.join(missing_summary_metrics) or 'none'}",
        flush=True,
    )

    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "reference_scope", "value": reference_scope},
            {"metric": "numt_interpretation_status", "value": interpretation_status},
            {"metric": "reason_code", "value": reason_code},
            {
                "metric": "missing_required_read_columns",
                "value": ",".join(missing_read_columns) or "none",
            },
            {
                "metric": "missing_required_summary_metrics",
                "value": ",".join(missing_summary_metrics) or "none",
            },
            {"metric": "primary_indicator_valid", "value": int(primary_indicator_valid)},
            {"metric": "primary_evidence_available", "value": int(primary_evidence_available)},
            {"metric": "reads_evaluated", "value": int(len(eval_df))},
            {
                "metric": "primary_alignment_records",
                "value": int(len(primary_df)) if primary_indicator_valid else "NA",
            },
            {
                "metric": "primary_full_length_reads",
                "value": primary_full_length_reads if primary_full_length_reads is not None else "NA",
            },
            {"metric": "low_mapq_fraction_lt20", "value": rounded_or_na(low_mapq_fraction)},
            {"metric": "very_low_mapq_fraction_lt5", "value": rounded_or_na(very_low_mapq_fraction)},
            {"metric": "short_aligned_fraction_lt0.5_mt", "value": rounded_or_na(short_span_fraction)},
            {"metric": "heavy_softclip_fraction_gt0.2", "value": rounded_or_na(heavy_softclip_fraction)},
            {"metric": "sa_tag_fraction", "value": rounded_or_na(sa_fraction)},
            {"metric": "supplementary_fraction_all_reads", "value": rounded_or_na(supplementary_fraction)},
            {
                "metric": "primary_full_length_fraction",
                "value": rounded_or_na(primary_full_length_fraction),
            },
            {
                "metric": "primary_full_length_fraction_denominator",
                "value": "primary_alignment_records",
            },
            {
                "metric": "primary_full_length_fraction_source",
                "value": "mito_read_stats_primary_alignment_records",
            },
            {
                "metric": "primary_full_length_fraction_basis",
                "value": "aligned_reference_bases_excluding_cigar_D_N",
            },
            {
                "metric": "primary_full_length_qc_crosscheck_status",
                "value": qc_fraction_crosscheck_status,
            },
            {
                "metric": "primary_full_length_qc_crosscheck_reason_code",
                "value": qc_fraction_crosscheck_reason,
            },
            {
                "metric": "full_length_fraction",
                "value": rounded_or_na(primary_full_length_fraction),
            },
            {
                "metric": "full_length_fraction_compatibility_alias_of",
                "value": "primary_full_length_fraction",
            },
            {"metric": "heuristic_numt_risk", "value": reported_risk},
            {"metric": "heuristic_numt_risk_score", "value": reported_risk_score},
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
    ).dropna(subset=["fraction"])

    scatter_fig_created = False
    scatter_span = validated_numeric_series(
        eval_df,
        "aligned_fraction_mt",
        **NUMT_READ_DOMAINS["aligned_fraction_mt"],
    )
    scatter_mapq = validated_numeric_series(
        eval_df,
        "mapq",
        **NUMT_READ_DOMAINS["mapq"],
    )
    if scatter_span is not None and scatter_mapq is not None:
        scatter_df = pd.DataFrame(
            {"aligned_fraction_mt": scatter_span, "mapq": scatter_mapq}
        )
        if not scatter_df.empty:
            plt.figure(figsize=(8, 5))
            plt.scatter(
                scatter_df["aligned_fraction_mt"],
                scatter_df["mapq"],
                s=8,
                alpha=0.4,
                color="#2563eb",
            )
            plt.axvline(0.50, color="#dc2626", linestyle="--", linewidth=1)
            plt.axhline(20, color="#dc2626", linestyle="--", linewidth=1)
            plt.xlabel("Aligned reference bases / mitochondrial length")
            plt.ylabel("MAPQ")
            plt.title(f"{sample_id} aligned-reference fraction vs MAPQ")
            plt.tight_layout()
            plt.savefig(scatter_fig, dpi=150)
            plt.close()
            scatter_fig_created = True
            print(f"[numt_qc] wrote scatter figure {scatter_fig}", flush=True)
    else:
        print(
            "[numt_qc] skipped scatter figure because aligned-reference fraction or MAPQ "
            "columns were unavailable",
            flush=True,
        )

    metrics_fig_created = False
    if not metric_plot_df.empty:
        plt.figure(figsize=(8, 4))
        plt.bar(metric_plot_df["metric"], metric_plot_df["fraction"], color="#7c3aed")
        plt.xticks(rotation=20)
        plt.ylabel("Fraction of reads")
        plt.title(f"{sample_id} mitochondrial alignment-ambiguity QC fractions")
        plt.tight_layout()
        plt.savefig(metrics_fig, dpi=150)
        plt.close()
        metrics_fig_created = True
        print(f"[numt_qc] wrote metric figure {metrics_fig}", flush=True)
    else:
        print("[numt_qc] skipped metric figure because no QC fractions were available", flush=True)

    metrics_html = "".join(
        [
            metric_card("NUMT interpretation", interpretation_status),
            metric_card("Heuristic risk", reported_risk),
            metric_card("Low MAPQ fraction", display_metric(low_mapq_fraction)),
            metric_card("Short-span fraction", display_metric(short_span_fraction)),
            metric_card("Heavy soft-clip fraction", display_metric(heavy_softclip_fraction)),
            metric_card(
                "Primary near-complete aligned-reference fraction",
                display_metric(primary_full_length_fraction),
            ),
        ]
    )
    intro_html = (
        '<p class="muted">This page reports mitochondrial alignment-structure and ambiguity metrics. '
        "A categorical NUMT warning is shown only when reads were aligned against a recognized whole-genome reference. "
        "The summary is based on read-level alignment structure, including MAPQ, mitochondrial "
        "aligned-reference coverage, soft clipping, supplementary alignments, and SA-tag frequency. "
        "The compatibility field primary_full_length_fraction is a near-complete alignment metric: "
        "its numerator contains primary records with M, =, and X CIGAR bases covering at least 90% of the "
        "mitochondrial reference length, while D and N bases are excluded. Supplementary and secondary "
        "records do not contribute. It is not a direct measure of intact molecule length. "
        f"The resolved reference scope is {reference_scope}; NUMT interpretation status is {interpretation_status}. "
        "This remains QC context rather than a formal NUMT classifier.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )

    body_parts = [
        "<section><h2>NUMT-aware QC summary</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>",
        "<section><h2>Read-level mitochondrial alignment table</h2>"
        + df_to_html_table(eval_df, max_rows=30)
        + "</section>",
    ]
    if metrics_fig_created:
        body_parts.insert(
            1,
            "<section><h2>QC-fraction overview</h2>"
            + figure_html(metrics_fig, "Available fractions used by the heuristic NUMT-risk score")
            + "</section>",
        )
    else:
        body_parts.insert(
            1,
            "<section><h2>QC-fraction overview</h2>"
            "<p class='muted'>No read-level QC fractions could be computed from the available columns.</p>"
            "</section>",
        )
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
        "Mito Alignment-Ambiguity QC",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        "".join(body_parts),
    )
    print(f"[numt_qc] wrote report {report_path}", flush=True)
    outputs = {
        "status": "ok",
        "summary_path": summary_path,
        "report_path": report_path,
    }
    if metrics_fig_created:
        outputs["metrics_figure_path"] = metrics_fig
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
        reference_scope=args.reference_scope,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
