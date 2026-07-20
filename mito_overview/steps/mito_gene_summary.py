"""Mitochondrial gene and feature summary for mito-overview."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import ensure_alt_fraction_columns, validate_module_state

CONTROL_REGION_LABEL = "D-loop/control region"
CONTROL_REGION_INTERVALS = [(1, 576), (16024, 16569)]
FEATURE_SUMMARY_COLUMNS = [
    "feature_label",
    "feature_class",
    "feature_intervals",
    "candidate_sites",
    "selected_coseg_sites",
    "max_alt_allele_fraction",
    "mean_alt_allele_fraction",
    "max_heteroplasmy",
    "mean_heteroplasmy",
    "median_depth",
    "deletion_event_overlaps",
    "deletion_cluster_overlaps",
    "max_cluster_support_fraction_primary",
    "top_site",
]
SITE_DETAIL_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "depth",
    "feature_class",
    "feature_label",
]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    return parser


def _empty_feature_summary_df() -> pd.DataFrame:
    return pd.DataFrame(columns=FEATURE_SUMMARY_COLUMNS)


def _empty_site_detail_df() -> pd.DataFrame:
    return pd.DataFrame(columns=SITE_DETAIL_COLUMNS)


def _status_page(
    *,
    summary_dir: Path,
    report_dir: Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    status: str,
    reason_code: str,
    message: str,
) -> dict[str, Path | str]:
    summary_path = summary_dir / "mito_gene_summary.tsv"
    site_details_path = summary_dir / "mito_gene_summary_site_details.tsv"
    run_summary_path = summary_dir / "mito_gene_summary_run_summary.tsv"
    report_path = report_dir / "07_mito_gene_summary.html"

    status = validate_module_state(status)
    status_df = pd.DataFrame(
        [
            {"metric": "status", "value": status},
            {"metric": "reason_code", "value": reason_code},
            {"metric": "message", "value": message},
        ]
    )
    _empty_feature_summary_df().to_csv(summary_path, sep="\t", index=False)
    _empty_site_detail_df().to_csv(site_details_path, sep="\t", index=False)
    status_df.to_csv(run_summary_path, sep="\t", index=False)

    intro_html = f'<p class="muted">{message}</p>'
    body_html = "<section><h2>Status</h2>" + df_to_html_table(status_df, max_rows=20) + "</section>"
    render_page(
        report_path,
        "Mitochondrial Gene Summary",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        body_html,
    )
    return {
        "status": status,
        "summary_path": summary_path,
        "site_details_path": site_details_path,
        "run_summary_path": run_summary_path,
        "report_path": report_path,
    }


def _normalize_label(value, default: str = "NA") -> str:
    if pd.isna(value):
        return default
    text = str(value).strip()
    return text if text else default


def _format_intervals(intervals: list[tuple[int, int]]) -> str:
    unique = sorted({(int(start), int(end)) for start, end in intervals})
    if not unique:
        return "NA"
    return "; ".join(f"{start}-{end}" for start, end in unique)


def _first_existing(summary_dir: Path, names: list[str], patterns: list[str]) -> Path | None:
    for name in names:
        candidate = summary_dir / name
        if candidate.exists():
            return candidate
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(summary_dir.glob(pattern))
    if not matches:
        return None
    unique = sorted({match.resolve() for match in matches})
    return unique[0]


def _extract_selected_positions(selected_df: pd.DataFrame) -> set[int]:
    positions: set[int] = set()
    if selected_df.empty:
        return positions
    if "position" in selected_df.columns:
        values = selected_df["position"]
    elif "site_label" in selected_df.columns:
        values = selected_df["site_label"].astype(str).str.split(":", n=1).str[0]
    else:
        return positions
    for value in values:
        number = pd.to_numeric(value, errors="coerce")
        if pd.notna(number):
            positions.add(int(number))
    return positions


def _extract_interval_table(
    frame: pd.DataFrame,
    *,
    start_candidates: list[str],
    end_candidates: list[str],
    support_column: str | None = None,
) -> pd.DataFrame:
    start_col = next((column for column in start_candidates if column in frame.columns), None)
    end_col = next((column for column in end_candidates if column in frame.columns), None)
    columns = ["start", "end"]
    if support_column:
        columns.append("support_fraction_primary")
    if start_col is None or end_col is None or frame.empty:
        return pd.DataFrame(columns=columns)

    temp = frame[[start_col, end_col]].copy()
    temp["start"] = pd.to_numeric(temp[start_col], errors="coerce")
    temp["end"] = pd.to_numeric(temp[end_col], errors="coerce")
    temp = temp.dropna(subset=["start", "end"]).copy()
    if temp.empty:
        return pd.DataFrame(columns=columns)

    temp["start"] = temp["start"].astype(int)
    temp["end"] = temp["end"].astype(int)
    smaller = temp[["start", "end"]].min(axis=1)
    larger = temp[["start", "end"]].max(axis=1)
    temp["start"] = smaller
    temp["end"] = larger

    if support_column and support_column in frame.columns:
        temp["support_fraction_primary"] = pd.to_numeric(
            frame.loc[temp.index, support_column],
            errors="coerce",
        ).fillna(0.0)
    elif support_column:
        temp["support_fraction_primary"] = 0.0

    if support_column:
        temp = (
            temp.groupby(["start", "end"], as_index=False)
            .agg(support_fraction_primary=("support_fraction_primary", "max"))
            .sort_values(["start", "end"])
            .reset_index(drop=True)
        )
        return temp[["start", "end", "support_fraction_primary"]]

    temp = temp[["start", "end"]].drop_duplicates().sort_values(["start", "end"]).reset_index(drop=True)
    return temp


def _intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return max(start_a, start_b) <= min(end_a, end_b)


def _count_overlapping_intervals(intervals_df: pd.DataFrame, feature_intervals: list[tuple[int, int]]) -> tuple[int, float]:
    if intervals_df.empty or not feature_intervals:
        return 0, 0.0

    overlap_count = 0
    max_support = 0.0
    has_support = "support_fraction_primary" in intervals_df.columns
    for interval in intervals_df.itertuples(index=False):
        if any(_intervals_overlap(int(interval.start), int(interval.end), start, end) for start, end in feature_intervals):
            overlap_count += 1
            if has_support:
                max_support = max(max_support, float(interval.support_fraction_primary))
    return overlap_count, max_support


def _format_top_site(row: pd.Series) -> str:
    position = pd.to_numeric(row.get("position"), errors="coerce")
    ref_base = _normalize_label(row.get("ref_base"), default=".")
    alt_base = _normalize_label(row.get("alt_base"), default=".")
    if pd.isna(position):
        return "NA"
    return f"{int(position)}:{ref_base}>{alt_base}"


def _build_feature_specs(catalog_df: pd.DataFrame, overlap_df: pd.DataFrame) -> list[dict[str, object]]:
    specs: dict[str, dict[str, object]] = {}

    for row in catalog_df.itertuples(index=False):
        label = _normalize_label(getattr(row, "gene_name", "NA"))
        if label == "NA":
            continue
        feature_class = _normalize_label(getattr(row, "gene_biotype", "unknown"), default="unknown")
        spec = specs.setdefault(
            label,
            {
                "feature_label": label,
                "feature_class": feature_class,
                "intervals": [],
            },
        )
        if spec["feature_class"] == "unknown" and feature_class != "unknown":
            spec["feature_class"] = feature_class
        start = pd.to_numeric(getattr(row, "start", None), errors="coerce")
        end = pd.to_numeric(getattr(row, "end", None), errors="coerce")
        if pd.notna(start) and pd.notna(end):
            spec["intervals"].append((int(start), int(end)))

    specs[CONTROL_REGION_LABEL] = {
        "feature_label": CONTROL_REGION_LABEL,
        "feature_class": "control_region",
        "intervals": list(CONTROL_REGION_INTERVALS),
    }
    specs["intergenic"] = {
        "feature_label": "intergenic",
        "feature_class": "intergenic",
        "intervals": [],
    }

    if not overlap_df.empty:
        for row in overlap_df.itertuples(index=False):
            label = _normalize_label(getattr(row, "feature_label", "NA"))
            if label in {"NA", CONTROL_REGION_LABEL, "intergenic"}:
                continue
            if label not in specs:
                specs[label] = {
                    "feature_label": label,
                    "feature_class": _normalize_label(getattr(row, "feature_class", "unknown"), default="unknown"),
                    "intervals": [],
                }

    return list(specs.values())


def _prepare_overlap_df(overlap_df: pd.DataFrame) -> pd.DataFrame:
    if overlap_df.empty:
        return _empty_site_detail_df()

    prepared = ensure_alt_fraction_columns(overlap_df)
    for column in SITE_DETAIL_COLUMNS:
        if column not in prepared.columns:
            prepared[column] = pd.NA

    prepared["position"] = pd.to_numeric(prepared["position"], errors="coerce")
    prepared["alt_allele_fraction"] = pd.to_numeric(
        prepared["alt_allele_fraction"], errors="coerce"
    ).fillna(0.0)
    prepared["heteroplasmy_fraction"] = prepared["alt_allele_fraction"]
    prepared["depth"] = pd.to_numeric(prepared["depth"], errors="coerce").fillna(0.0)
    prepared["feature_label"] = prepared["feature_label"].apply(_normalize_label)
    prepared["feature_class"] = prepared["feature_class"].apply(_normalize_label)
    prepared["ref_base"] = prepared["ref_base"].apply(lambda value: _normalize_label(value, default="."))
    prepared["alt_base"] = prepared["alt_base"].apply(lambda value: _normalize_label(value, default="."))
    prepared = prepared.dropna(subset=["position"]).copy()
    prepared["position"] = prepared["position"].astype(int)
    prepared = prepared.drop_duplicates(subset=["position", "feature_label"])
    return prepared


def _candidate_stats_by_feature(overlap_df: pd.DataFrame) -> dict[str, dict[str, object]]:
    stats: dict[str, dict[str, object]] = {}
    if overlap_df.empty:
        return stats

    for feature_label, feature_rows in overlap_df.groupby("feature_label", sort=False):
        ordered = feature_rows.sort_values(
            ["alt_allele_fraction", "depth", "position"],
            ascending=[False, False, True],
        )
        top_row = ordered.iloc[0]
        stats[str(feature_label)] = {
            "candidate_sites": int(feature_rows["position"].nunique()),
            "max_alt_allele_fraction": round(float(feature_rows["alt_allele_fraction"].max()), 6),
            "mean_alt_allele_fraction": round(float(feature_rows["alt_allele_fraction"].mean()), 6),
            "median_depth": round(float(feature_rows["depth"].median()), 1),
            "top_site": _format_top_site(top_row),
        }
    return stats


def _selected_counts_by_feature(overlap_df: pd.DataFrame, selected_positions: set[int]) -> dict[str, int]:
    if overlap_df.empty or not selected_positions:
        return {}
    selected_rows = overlap_df[overlap_df["position"].isin(selected_positions)]
    if selected_rows.empty:
        return {}
    counts = selected_rows.groupby("feature_label")["position"].nunique()
    return {str(label): int(count) for label, count in counts.items()}


def _build_site_detail_df(overlap_df: pd.DataFrame) -> pd.DataFrame:
    if overlap_df.empty:
        return _empty_site_detail_df()

    site_detail_df = overlap_df[SITE_DETAIL_COLUMNS].copy()
    site_detail_df = site_detail_df.sort_values(
        ["feature_label", "alt_allele_fraction", "depth", "position"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)
    return site_detail_df


def run_step(
    *,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
) -> dict[str, Path]:
    """Summarize candidate burden across mitochondrial genes and features."""

    print(
        f"[gene_summary] starting sample={sample_id} contig={mt_contig} length={mt_length}",
        flush=True,
    )
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    summary_path = summary_dir / "mito_gene_summary.tsv"
    site_details_path = summary_dir / "mito_gene_summary_site_details.tsv"
    run_summary_path = summary_dir / "mito_gene_summary_run_summary.tsv"
    report_path = report_dir / "07_mito_gene_summary.html"

    catalog_path = summary_dir / "mito_feature_catalog.tsv"
    overlap_path = summary_dir / "mito_feature_overlap_candidates.tsv"
    if not catalog_path.exists():
        return _status_page(
            summary_dir=summary_dir,
            report_dir=report_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            status="not_evaluable",
            reason_code="feature_annotation_outputs_missing",
            message=(
                "Gene summary requires feature-annotation outputs, including "
                "mito_feature_catalog.tsv and mito_feature_overlap_candidates.tsv."
            ),
        )

    catalog_df = pd.read_csv(catalog_path, sep="\t")
    required_catalog_columns = {"gene_name", "gene_biotype", "start", "end"}
    if catalog_df.empty or not required_catalog_columns.issubset(catalog_df.columns):
        return _status_page(
            summary_dir=summary_dir,
            report_dir=report_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            status="not_evaluable",
            reason_code="feature_catalog_unusable",
            message=(
                "Gene summary could not load a usable mitochondrial feature catalog from "
                "mito_feature_catalog.tsv."
            ),
        )

    if overlap_path.exists():
        overlap_df = pd.read_csv(overlap_path, sep="\t")
    else:
        overlap_df = _empty_site_detail_df()
    overlap_df = _prepare_overlap_df(overlap_df)

    selected_sites_path = _first_existing(
        summary_dir,
        names=[
            "mito_cosegregation_selected_sites.tsv",
            "mito_cosegregation_sites.tsv",
            "mito_coseg_selected_sites.tsv",
            "mito_coseg_sites.tsv",
        ],
        patterns=[
            "*cosegreg*selected*site*.tsv",
            "*cosegreg*site*.tsv",
            "*coseg*selected*site*.tsv",
            "*coseg*site*.tsv",
        ],
    )
    if selected_sites_path is None:
        selected_df = pd.DataFrame()
        selected_positions: set[int] = set()
        print(
            "[gene_summary] no co-segregation selected-sites table found; continuing with zero selected-site counts",
            flush=True,
        )
    else:
        selected_df = pd.read_csv(selected_sites_path, sep="\t")
        selected_positions = _extract_selected_positions(selected_df)
        print(
            f"[gene_summary] loaded selected sites file={selected_sites_path.name} positions={len(selected_positions)}",
            flush=True,
        )

    deletion_events_path = summary_dir / "mito_deletion_events.tsv"
    deletion_clusters_path = summary_dir / "mito_deletion_clusters.tsv"
    deletion_events_df = pd.read_csv(deletion_events_path, sep="\t") if deletion_events_path.exists() else pd.DataFrame()
    deletion_clusters_df = (
        pd.read_csv(deletion_clusters_path, sep="\t") if deletion_clusters_path.exists() else pd.DataFrame()
    )
    deletion_event_intervals = _extract_interval_table(
        deletion_events_df,
        start_candidates=["event_start", "event_bin_start"],
        end_candidates=["event_end", "event_bin_end"],
    )
    deletion_cluster_intervals = _extract_interval_table(
        deletion_clusters_df,
        start_candidates=["event_bin_start", "event_start"],
        end_candidates=["event_bin_end", "event_end"],
        support_column="support_fraction_primary",
    )
    print(
        "[gene_summary] loaded "
        f"feature_rows={len(catalog_df)} candidate_rows={len(overlap_df)} "
        f"deletion_events={len(deletion_event_intervals)} deletion_clusters={len(deletion_cluster_intervals)}",
        flush=True,
    )

    feature_specs = _build_feature_specs(catalog_df, overlap_df)
    candidate_stats = _candidate_stats_by_feature(overlap_df)
    selected_counts = _selected_counts_by_feature(overlap_df, selected_positions)

    summary_rows: list[dict[str, object]] = []
    total_features = len(feature_specs)
    for idx, spec in enumerate(feature_specs, start=1):
        feature_label = str(spec["feature_label"])
        feature_class = str(spec["feature_class"])
        feature_intervals = list(spec["intervals"])
        candidate_stat = candidate_stats.get(
            feature_label,
            {
                "candidate_sites": 0,
                "max_alt_allele_fraction": 0.0,
                "mean_alt_allele_fraction": 0.0,
                "median_depth": 0.0,
                "top_site": "NA",
            },
        )
        if feature_label == "intergenic":
            deletion_event_overlaps = 0
            deletion_cluster_overlaps = 0
            max_cluster_support = 0.0
            interval_text = "non-feature candidate positions"
        else:
            deletion_event_overlaps, _ = _count_overlapping_intervals(deletion_event_intervals, feature_intervals)
            deletion_cluster_overlaps, max_cluster_support = _count_overlapping_intervals(
                deletion_cluster_intervals,
                feature_intervals,
            )
            interval_text = _format_intervals(feature_intervals)

        summary_rows.append(
            {
                "feature_label": feature_label,
                "feature_class": feature_class,
                "feature_intervals": interval_text,
                "candidate_sites": int(candidate_stat["candidate_sites"]),
                "selected_coseg_sites": int(selected_counts.get(feature_label, 0)),
                "max_alt_allele_fraction": round(
                    float(candidate_stat["max_alt_allele_fraction"]), 6
                ),
                "mean_alt_allele_fraction": round(
                    float(candidate_stat["mean_alt_allele_fraction"]), 6
                ),
                "max_heteroplasmy": round(float(candidate_stat["max_alt_allele_fraction"]), 6),
                "mean_heteroplasmy": round(float(candidate_stat["mean_alt_allele_fraction"]), 6),
                "median_depth": round(float(candidate_stat["median_depth"]), 1),
                "deletion_event_overlaps": int(deletion_event_overlaps),
                "deletion_cluster_overlaps": int(deletion_cluster_overlaps),
                "max_cluster_support_fraction_primary": round(float(max_cluster_support), 6),
                "top_site": str(candidate_stat["top_site"]),
            }
        )
        if idx % 10 == 0 or idx == total_features:
            print(f"[gene_summary] summarized features {idx}/{total_features}", flush=True)

    summary_df = pd.DataFrame(summary_rows, columns=FEATURE_SUMMARY_COLUMNS)
    summary_df = summary_df.sort_values(
        [
            "candidate_sites",
            "selected_coseg_sites",
            "deletion_cluster_overlaps",
            "max_alt_allele_fraction",
            "feature_label",
        ],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)

    site_detail_df = _build_site_detail_df(overlap_df)
    run_summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "reason_code", "value": ""},
            {"metric": "features_summarized", "value": len(summary_df)},
            {
                "metric": "features_with_candidate_sites",
                "value": int((summary_df["candidate_sites"] > 0).sum()),
            },
            {
                "metric": "features_with_deletion_cluster_overlap",
                "value": int((summary_df["deletion_cluster_overlaps"] > 0).sum()),
            },
            {
                "metric": "features_with_cosegregation_selected_sites",
                "value": int((summary_df["selected_coseg_sites"] > 0).sum()),
            },
            {"metric": "candidate_site_rows", "value": len(site_detail_df)},
            {"metric": "selected_coseg_positions_loaded", "value": len(selected_positions)},
            {"metric": "deletion_event_intervals_loaded", "value": len(deletion_event_intervals)},
            {"metric": "deletion_cluster_intervals_loaded", "value": len(deletion_cluster_intervals)},
        ]
    )

    summary_df.to_csv(summary_path, sep="\t", index=False)
    site_detail_df.to_csv(site_details_path, sep="\t", index=False)
    run_summary_df.to_csv(run_summary_path, sep="\t", index=False)

    fig_path: Path | None = None
    overview_df = summary_df[
        (
            (summary_df["candidate_sites"] > 0)
            | (summary_df["selected_coseg_sites"] > 0)
            | (summary_df["deletion_cluster_overlaps"] > 0)
        )
    ].head(20)
    if not overview_df.empty:
        plot_df = overview_df.iloc[::-1].copy()
        y_positions = list(range(len(plot_df)))
        fig_height = max(4.0, 0.38 * len(plot_df) + 1.8)
        plt.figure(figsize=(12, fig_height))
        candidate_y = [position - 0.24 for position in y_positions]
        selected_y = y_positions
        deletion_y = [position + 0.24 for position in y_positions]
        plt.barh(candidate_y, plot_df["candidate_sites"], height=0.22, color="#2563eb", label="Candidate sites")
        plt.barh(
            selected_y,
            plot_df["selected_coseg_sites"],
            height=0.22,
            color="#f59e0b",
            label="Selected co-seg sites",
        )
        plt.barh(
            deletion_y,
            plot_df["deletion_cluster_overlaps"],
            height=0.22,
            color="#dc2626",
            label="Deletion-cluster overlaps",
        )
        plt.yticks(y_positions, plot_df["feature_label"])
        plt.xlabel("Count")
        plt.title(f"{sample_id} mitochondrial feature-level burden summary")
        plt.legend(loc="lower right")
        plt.tight_layout()
        fig_path = figure_dir / "mito_gene_summary_overview.png"
        plt.savefig(fig_path, dpi=150)
        plt.close()

    metrics_html = "".join(
        [
            metric_card("Features summarized", len(summary_df)),
            metric_card("Features with candidate sites", int((summary_df["candidate_sites"] > 0).sum())),
            metric_card(
                "Features with deletion-cluster overlap",
                int((summary_df["deletion_cluster_overlaps"] > 0).sum()),
            ),
            metric_card(
                "Features with co-segregation-selected sites",
                int((summary_df["selected_coseg_sites"] > 0).sum()),
            ),
        ]
    )
    intro_html = (
        '<p class="muted">This page aggregates mitochondrial candidate-site burden at the feature level. '
        "It highlights which genes or control-region features concentrate alternate-allele candidates, "
        "whether selected co-segregation sites cluster in the same features, and whether deletion "
        "intervals overlap those features.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )

    body_parts: list[str] = []
    if fig_path is not None:
        body_parts.append(
            "<section><h2>Feature-level overview</h2>"
            + figure_html(
                fig_path,
                "Candidate-site, co-segregation, and deletion-cluster summary by mitochondrial feature",
            )
            + "</section>"
        )
    body_parts.append(
        "<section><h2>Gene/feature summary</h2>" + df_to_html_table(summary_df, max_rows=30) + "</section>"
    )
    body_parts.append(
        "<section><h2>Site-level details by feature</h2>"
        + df_to_html_table(site_detail_df, max_rows=40)
        + "</section>"
    )
    render_page(
        report_path,
        "Mitochondrial Gene Summary",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        "".join(body_parts),
    )
    print(
        "[gene_summary] finished "
        f"features={len(summary_df)} candidate_features={(summary_df['candidate_sites'] > 0).sum()} "
        f"selected_features={(summary_df['selected_coseg_sites'] > 0).sum()} "
        f"deletion_features={(summary_df['deletion_cluster_overlaps'] > 0).sum()}",
        flush=True,
    )
    return {
        "status": "ok",
        "summary_path": summary_path,
        "site_details_path": site_details_path,
        "run_summary_path": run_summary_path,
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
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
