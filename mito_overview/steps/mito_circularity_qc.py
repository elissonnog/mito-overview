"""Circularity-aware mitochondrial QC for mito-overview."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import load_metric_module_state, validate_candidate_table

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
    "callable_depth",
    "depth",
    "alt_count",
    "alt_allele_fraction",
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


def load_candidate_table(path: Path) -> pd.DataFrame:
    """Load candidates without manufacturing a valid schema for malformed files."""

    if not path.exists():
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)
    try:
        return pd.read_csv(path, sep="\t")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def render_status_page(
    *,
    summary_path: Path,
    report_path: Path,
    sample_id: str,
    mt_contig: str,
    message: str,
) -> dict[str, Path | str]:
    """Write a status-only page when circularity inputs are unavailable."""

    print(f"[circularity_qc] {message}", flush=True)
    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": "not_evaluable"},
            {"metric": "reason_code", "value": "no_depth_profile_available"},
        ],
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
        "status": "not_evaluable",
        "summary_path": summary_path,
        "report_path": report_path,
    }


def _metric_status(denominator: int, reason_code: str) -> tuple[str, str]:
    """Return controlled evaluability metadata for a denominator-backed metric."""

    if denominator > 0:
        return "ok", ""
    return "not_evaluable", reason_code


def _summary_value(value: object) -> object:
    """Represent undefined numeric metrics explicitly in TSV and HTML outputs."""

    return "NA" if pd.isna(value) else value


def _display_value(value: float, digits: int = 4) -> float | str:
    """Format report cards without presenting undefined values as zero."""

    return "NA" if pd.isna(value) else round(float(value), digits)


def _valid_coordinate_series(
    df: pd.DataFrame,
    column: str,
    mt_length: int,
) -> pd.Series | None:
    """Return a complete one-based coordinate column or fail the metric closed."""

    if df.empty or column not in df.columns:
        return None
    series = pd.to_numeric(df[column], errors="coerce")
    values = series.to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        valid = (
            np.isfinite(values)
            & (values == np.floor(values))
            & (values >= 1)
            & (values <= mt_length)
        )
    return series if bool(valid.all()) else None


def _valid_unit_interval_series(df: pd.DataFrame, column: str) -> pd.Series | None:
    """Return a complete finite fraction column constrained to zero through one."""

    if df.empty or column not in df.columns:
        return None
    series = pd.to_numeric(df[column], errors="coerce")
    values = series.to_numpy(dtype=float)
    valid = np.isfinite(values) & (values >= 0) & (values <= 1)
    return series if bool(valid.all()) else None


def _valid_binary_series(df: pd.DataFrame, column: str) -> pd.Series | None:
    """Return a complete exact binary indicator column."""

    if df.empty or column not in df.columns:
        return None
    series = pd.to_numeric(df[column], errors="coerce")
    values = series.to_numpy(dtype=float)
    valid = np.isfinite(values) & np.isin(values, (0, 1))
    return series if bool(valid.all()) else None


def run_step(
    *,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    edge_window: int = 500,
) -> dict[str, Path | str]:
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
    heteroplasmy_summary_path = summary_dir / "mito_heteroplasmy_summary.tsv"
    summary_path = summary_dir / "mito_circularity_qc_summary.tsv"
    report_path = report_dir / "11_mito_circularity_qc.html"
    depth_fig = figure_dir / "mito_circularity_edge_depth.png"
    edge_fig = figure_dir / "mito_circularity_edge_metrics.png"

    depth_df = load_depth_table(depth_path)
    reads_df = load_optional_table(reads_path, READ_COLUMNS)
    heteroplasmy_status, heteroplasmy_reason = load_metric_module_state(
        heteroplasmy_summary_path,
        module_name="heteroplasmy",
    )
    candidate_table_exists = candidates_path.is_file()
    candidate_evidence_trusted = heteroplasmy_status == "ok" and candidate_table_exists
    candidates_df = pd.DataFrame(columns=CANDIDATE_COLUMNS)
    if candidate_evidence_trusted:
        candidates_df = validate_candidate_table(
            load_candidate_table(candidates_path),
            table_name="mito_heteroplasmy_candidates.tsv",
            mt_length=mt_length,
        )
    print(
        f"[circularity_qc] loaded depth_rows={len(depth_df)} reads_rows={len(reads_df)} "
        f"candidate_rows={len(candidates_df)} depth_exists={depth_path.exists()} "
        f"reads_exists={reads_path.exists()} candidates_exists={candidate_table_exists} "
        f"heteroplasmy_status={heteroplasmy_status} "
        f"candidate_evidence_trusted={int(candidate_evidence_trusted)}",
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

    position_values = depth_df["position"].to_numpy(dtype=float)
    depth_values = depth_df["depth"].to_numpy(dtype=float)
    finite_position_mask = np.isfinite(position_values)
    with np.errstate(invalid="ignore"):
        integer_position_mask = finite_position_mask & (
            position_values == np.floor(position_values)
        )
    in_range_mask = pd.Series(
        integer_position_mask
        & (position_values >= 1)
        & (position_values <= mt_length),
        index=depth_df.index,
    )
    valid_depth_mask = pd.Series(
        np.isfinite(depth_values) & (depth_values >= 0),
        index=depth_df.index,
    )
    depth_in_range = depth_df.loc[in_range_mask].copy()
    depth_in_range.loc[
        ~valid_depth_mask.loc[depth_in_range.index], "depth"
    ] = np.nan
    depth_unique_positions = int(depth_in_range["position"].nunique())
    depth_duplicate_rows = int(len(depth_in_range) - depth_unique_positions)
    depth_out_of_range_rows = int((~in_range_mask).sum())
    depth_missing_positions = int(max(mt_length - depth_unique_positions, 0))
    coordinate_profile_complete = (
        len(depth_df) == mt_length
        and depth_unique_positions == mt_length
        and depth_duplicate_rows == 0
        and depth_out_of_range_rows == 0
    )

    edge = min(edge_window, max(1, mt_length // 10))
    first_edge = depth_in_range[depth_in_range["position"] <= edge].copy()
    last_edge = depth_in_range[depth_in_range["position"] > (mt_length - edge)].copy()
    interior = depth_in_range[
        (depth_in_range["position"] > edge)
        & (depth_in_range["position"] <= (mt_length - edge))
    ].copy()

    regional_depth_means: list[float] = []
    if coordinate_profile_complete and bool(valid_depth_mask.all()):
        with np.errstate(over="ignore", invalid="ignore"):
            regional_depth_means = [
                float(region["depth"].mean())
                for region in (first_edge, last_edge, interior)
                if not region.empty
            ]
    depth_profile_complete = (
        coordinate_profile_complete
        and bool(valid_depth_mask.all())
        and bool(regional_depth_means)
        and all(np.isfinite(value) for value in regional_depth_means)
    )

    edge_candidates = pd.DataFrame(columns=candidates_df.columns)
    candidate_edge_fraction = np.nan
    candidate_position_denominator = 0
    candidate_positions = _valid_coordinate_series(
        candidates_df, "position", mt_length
    )
    if candidate_positions is not None:
        candidate_position_denominator = int(len(candidate_positions))
        if candidate_position_denominator:
            edge_mask = (candidate_positions <= edge) | (
                candidate_positions > (mt_length - edge)
            )
            edge_candidates = candidates_df.loc[edge_mask].copy()
            candidate_edge_fraction = float(
                len(edge_candidates) / candidate_position_denominator
            )
    if heteroplasmy_status != "ok":
        candidate_status = heteroplasmy_status
        candidate_reason = f"upstream_heteroplasmy_{heteroplasmy_status}"
    elif not candidate_table_exists:
        candidate_status = "not_evaluable"
        candidate_reason = "candidate_table_missing"
    elif candidates_df.empty:
        candidate_status = "not_applicable"
        candidate_reason = "no_candidate_sites_observed"
    elif candidate_positions is None:
        candidate_status, candidate_reason = (
            "not_evaluable",
            "invalid_candidate_positions",
        )
    else:
        candidate_status, candidate_reason = _metric_status(
            candidate_position_denominator,
            "no_usable_candidate_positions",
        )

    primary_indicator = _valid_binary_series(reads_df, "is_primary")
    primary_indicator_invalid = not reads_df.empty and primary_indicator is None
    if primary_indicator is not None:
        reads_eval = reads_df.loc[primary_indicator == 1].copy()
    else:
        reads_eval = reads_df.iloc[0:0].copy()

    edge_start_fraction = np.nan
    read_start_denominator = 0
    read_start = _valid_coordinate_series(reads_eval, "read_start", mt_length)
    read_end = _valid_coordinate_series(reads_eval, "read_end", mt_length)
    coordinate_pairs_valid = (
        read_start is not None
        and read_end is not None
        and len(read_start) == len(read_end)
        and bool((read_end >= read_start).all())
    )
    if coordinate_pairs_valid:
        read_start_denominator = int(len(read_start))
        if not read_start.empty:
            edge_start_fraction = float((read_start <= edge).mean())
    if primary_indicator_invalid:
        read_start_status, read_start_reason = (
            "not_evaluable",
            "invalid_primary_read_indicator",
        )
    elif not reads_eval.empty and not coordinate_pairs_valid:
        read_start_status, read_start_reason = (
            "not_evaluable",
            "invalid_primary_read_coordinate_pairs",
        )
    else:
        read_start_status, read_start_reason = _metric_status(
            read_start_denominator,
            "no_usable_primary_read_starts",
        )

    edge_end_fraction = np.nan
    read_end_denominator = 0
    if coordinate_pairs_valid:
        read_end_denominator = int(len(read_end))
        if not read_end.empty:
            edge_end_fraction = float((read_end > (mt_length - edge)).mean())
    if primary_indicator_invalid:
        read_end_status, read_end_reason = (
            "not_evaluable",
            "invalid_primary_read_indicator",
        )
    elif not reads_eval.empty and not coordinate_pairs_valid:
        read_end_status, read_end_reason = (
            "not_evaluable",
            "invalid_primary_read_coordinate_pairs",
        )
    else:
        read_end_status, read_end_reason = _metric_status(
            read_end_denominator,
            "no_usable_primary_read_ends",
        )

    edge_softclip_fraction = np.nan
    softclip_denominator = 0
    softclip_values = _valid_unit_interval_series(reads_eval, "softclip_fraction")
    softclip_input_valid = (
        coordinate_pairs_valid
        and softclip_values is not None
    )
    if softclip_input_valid:
        softclip_df = pd.DataFrame(
            {
                "read_start": read_start,
                "read_end": read_end,
                "softclip_fraction": softclip_values,
            }
        )
        softclip_denominator = int(len(softclip_df))
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
    if primary_indicator_invalid:
        softclip_status, softclip_reason = (
            "not_evaluable",
            "invalid_primary_read_indicator",
        )
    elif not reads_eval.empty and not softclip_input_valid:
        softclip_status, softclip_reason = (
            "not_evaluable",
            (
                "invalid_primary_read_coordinate_pairs"
                if not coordinate_pairs_valid
                else "invalid_primary_read_softclip_records"
            ),
        )
    else:
        softclip_status, softclip_reason = _metric_status(
            softclip_denominator,
            "no_usable_primary_read_softclip_records",
        )

    first_edge_denominator = int(len(first_edge))
    last_edge_denominator = int(len(last_edge))
    interior_denominator = int(len(interior))
    if depth_profile_complete:
        mean_depth_first_edge = (
            round(float(first_edge["depth"].mean()), 3)
            if first_edge_denominator
            else np.nan
        )
        mean_depth_last_edge = (
            round(float(last_edge["depth"].mean()), 3)
            if last_edge_denominator
            else np.nan
        )
        mean_depth_interior = (
            round(float(interior["depth"].mean()), 3)
            if interior_denominator
            else np.nan
        )
        first_depth_status, first_depth_reason = _metric_status(
            first_edge_denominator,
            "no_positions_in_first_edge_window",
        )
        last_depth_status, last_depth_reason = _metric_status(
            last_edge_denominator,
            "no_positions_in_last_edge_window",
        )
        interior_depth_status, interior_depth_reason = _metric_status(
            interior_denominator,
            "no_positions_in_interior_window",
        )
    else:
        mean_depth_first_edge = np.nan
        mean_depth_last_edge = np.nan
        mean_depth_interior = np.nan
        first_depth_status = last_depth_status = interior_depth_status = "not_evaluable"
        first_depth_reason = last_depth_reason = interior_depth_reason = "incomplete_depth_profile"
    module_status = "ok" if depth_profile_complete else "not_evaluable"
    module_reason = "" if depth_profile_complete else "incomplete_depth_profile"
    candidate_sites_total = int(len(candidates_df)) if candidate_evidence_trusted else "NA"
    candidate_position_denominator_summary = (
        candidate_position_denominator if candidate_evidence_trusted else "NA"
    )
    candidate_sites_in_edges = int(len(edge_candidates)) if candidate_evidence_trusted else "NA"
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
            {"metric": "status", "value": module_status},
            {"metric": "reason_code", "value": module_reason},
            {"metric": "edge_window_bp", "value": int(edge)},
            {"metric": "depth_positions_total", "value": int(len(depth_df))},
            {"metric": "depth_positions_expected", "value": int(mt_length)},
            {"metric": "depth_unique_positions_in_range", "value": depth_unique_positions},
            {"metric": "depth_missing_positions", "value": depth_missing_positions},
            {"metric": "depth_duplicate_rows", "value": depth_duplicate_rows},
            {"metric": "depth_out_of_range_rows", "value": depth_out_of_range_rows},
            {"metric": "depth_profile_complete", "value": int(depth_profile_complete)},
            {"metric": "mean_depth_first_edge", "value": _summary_value(mean_depth_first_edge)},
            {"metric": "mean_depth_first_edge_denominator_positions", "value": first_edge_denominator},
            {"metric": "mean_depth_first_edge_status", "value": first_depth_status},
            {"metric": "mean_depth_first_edge_reason_code", "value": first_depth_reason},
            {"metric": "mean_depth_last_edge", "value": _summary_value(mean_depth_last_edge)},
            {"metric": "mean_depth_last_edge_denominator_positions", "value": last_edge_denominator},
            {"metric": "mean_depth_last_edge_status", "value": last_depth_status},
            {"metric": "mean_depth_last_edge_reason_code", "value": last_depth_reason},
            {"metric": "mean_depth_interior", "value": _summary_value(mean_depth_interior)},
            {"metric": "mean_depth_interior_denominator_positions", "value": interior_denominator},
            {"metric": "mean_depth_interior_status", "value": interior_depth_status},
            {"metric": "mean_depth_interior_reason_code", "value": interior_depth_reason},
            {"metric": "upstream_heteroplasmy_status", "value": heteroplasmy_status},
            {"metric": "upstream_heteroplasmy_reason_code", "value": heteroplasmy_reason},
            {"metric": "candidate_table_present", "value": int(candidate_table_exists)},
            {"metric": "candidate_evidence_trusted", "value": int(candidate_evidence_trusted)},
            {"metric": "candidate_sites_total", "value": candidate_sites_total},
            {"metric": "candidate_edge_fraction_denominator_positions", "value": candidate_position_denominator_summary},
            {"metric": "candidate_sites_in_edges", "value": candidate_sites_in_edges},
            {"metric": "candidate_edge_fraction", "value": _summary_value(round(candidate_edge_fraction, 6))},
            {"metric": "candidate_edge_fraction_status", "value": candidate_status},
            {"metric": "candidate_edge_fraction_reason_code", "value": candidate_reason},
            {"metric": "primary_read_rows", "value": int(len(reads_eval))},
            {"metric": "primary_read_start_in_edge_fraction_denominator_reads", "value": read_start_denominator},
            {"metric": "primary_read_start_in_edge_fraction", "value": _summary_value(round(edge_start_fraction, 6))},
            {"metric": "primary_read_start_in_edge_fraction_status", "value": read_start_status},
            {"metric": "primary_read_start_in_edge_fraction_reason_code", "value": read_start_reason},
            {"metric": "primary_read_end_in_edge_fraction_denominator_reads", "value": read_end_denominator},
            {"metric": "primary_read_end_in_edge_fraction", "value": _summary_value(round(edge_end_fraction, 6))},
            {"metric": "primary_read_end_in_edge_fraction_status", "value": read_end_status},
            {"metric": "primary_read_end_in_edge_fraction_reason_code", "value": read_end_reason},
            {"metric": "edge_read_heavy_softclip_fraction_denominator_reads", "value": softclip_denominator},
            {"metric": "edge_read_heavy_softclip_fraction", "value": _summary_value(round(edge_softclip_fraction, 6))},
            {"metric": "edge_read_heavy_softclip_fraction_status", "value": softclip_status},
            {"metric": "edge_read_heavy_softclip_fraction_reason_code", "value": softclip_reason},
        ],
        columns=SUMMARY_COLUMNS,
    )
    summary_df.to_csv(summary_path, sep="\t", index=False, na_rep="NA")
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
            metric_card("Edge candidate fraction", _display_value(candidate_edge_fraction)),
            metric_card("Edge read-start fraction", _display_value(edge_start_fraction)),
            metric_card("Edge read-end fraction", _display_value(edge_end_fraction)),
            metric_card("Edge heavy-softclip fraction", _display_value(edge_softclip_fraction)),
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
        + df_to_html_table(summary_df, max_rows=60)
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
        "status": module_status,
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
