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


def _int_or_na(value: object) -> int | object:
    number = pd.to_numeric(value, errors="coerce")
    return pd.NA if pd.isna(number) else int(number)


def _round_or_na(value: object, digits: int) -> float | object:
    number = pd.to_numeric(value, errors="coerce")
    return pd.NA if pd.isna(number) else round(float(number), digits)


def _positive_count(frame: pd.DataFrame, column: str, *, evaluable: bool) -> int | object:
    if not evaluable:
        return pd.NA
    values = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return int((values > 0).sum())


def _read_module_status(
    path: Path,
    *,
    default_status: str,
    default_reason: str,
) -> tuple[str, str]:
    if not path.exists():
        return default_status, default_reason
    try:
        frame = pd.read_csv(path, sep="\t")
    except pd.errors.EmptyDataError:
        return "not_evaluable", "module_summary_empty"
    if not {"metric", "value"}.issubset(frame.columns):
        return default_status, default_reason
    metrics = dict(zip(frame["metric"].astype(str), frame["value"]))
    raw_status = str(metrics.get("status", default_status))
    try:
        status = validate_module_state(raw_status)
    except ValueError:
        return "not_evaluable", "module_summary_status_invalid"
    raw_reason = metrics.get("reason_code", default_reason)
    reason = default_reason if pd.isna(raw_reason) else str(raw_reason).strip()
    return status, reason


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


def _extract_cluster_member_intervals(
    deletion_events_df: pd.DataFrame,
    deletion_clusters_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join breakpoint clusters to their exact one-based member-event spans."""

    columns = [
        "cluster_bin_start",
        "cluster_bin_end",
        "start",
        "end",
        "support_fraction_primary",
    ]
    event_columns = {"event_start", "event_end", "event_bin_start", "event_bin_end"}
    cluster_columns = {"event_bin_start", "event_bin_end"}
    if (
        deletion_events_df.empty
        or deletion_clusters_df.empty
        or not event_columns.issubset(deletion_events_df.columns)
        or not cluster_columns.issubset(deletion_clusters_df.columns)
    ):
        return pd.DataFrame(columns=columns)

    events = deletion_events_df[list(event_columns)].copy()
    clusters = deletion_clusters_df[list(cluster_columns)].copy()
    if "support_fraction_primary" in deletion_clusters_df.columns:
        clusters["support_fraction_primary"] = pd.to_numeric(
            deletion_clusters_df["support_fraction_primary"], errors="coerce"
        ).fillna(0.0)
    else:
        clusters["support_fraction_primary"] = 0.0

    for frame in (events, clusters):
        for column in cluster_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    events["event_start"] = pd.to_numeric(events["event_start"], errors="coerce")
    events["event_end"] = pd.to_numeric(events["event_end"], errors="coerce")
    events = events.dropna(subset=list(event_columns)).copy()
    clusters = clusters.dropna(subset=list(cluster_columns)).copy()
    if events.empty or clusters.empty:
        return pd.DataFrame(columns=columns)

    for column in event_columns:
        events[column] = events[column].astype(int)
    for column in cluster_columns:
        clusters[column] = clusters[column].astype(int)
    clusters = (
        clusters.groupby(["event_bin_start", "event_bin_end"], as_index=False)
        .agg(support_fraction_primary=("support_fraction_primary", "max"))
    )
    members = events.merge(
        clusters,
        on=["event_bin_start", "event_bin_end"],
        how="inner",
        validate="many_to_one",
    )
    if members.empty:
        return pd.DataFrame(columns=columns)

    members["start"] = members[["event_start", "event_end"]].min(axis=1)
    members["end"] = members[["event_start", "event_end"]].max(axis=1)
    members = members.rename(
        columns={
            "event_bin_start": "cluster_bin_start",
            "event_bin_end": "cluster_bin_end",
        }
    )
    return members[columns].drop_duplicates().reset_index(drop=True)


def _count_overlapping_clusters(
    cluster_members_df: pd.DataFrame,
    feature_intervals: list[tuple[int, int]],
) -> tuple[int, float]:
    """Count clusters when at least one exact member event overlaps a feature."""

    if cluster_members_df.empty or not feature_intervals:
        return 0, 0.0
    overlap_count = 0
    max_support = 0.0
    for _, members in cluster_members_df.groupby(
        ["cluster_bin_start", "cluster_bin_end"], sort=False
    ):
        overlaps = any(
            _intervals_overlap(int(row.start), int(row.end), start, end)
            for row in members.itertuples(index=False)
            for start, end in feature_intervals
        )
        if overlaps:
            overlap_count += 1
            max_support = max(
                max_support,
                float(members["support_fraction_primary"].max()),
            )
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
    )
    prepared["heteroplasmy_fraction"] = prepared["alt_allele_fraction"]
    prepared["depth"] = pd.to_numeric(prepared["depth"], errors="coerce")
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
            kind="mergesort",
        )
        top_row = ordered.iloc[0]
        alt_fractions = pd.to_numeric(
            feature_rows["alt_allele_fraction"], errors="coerce"
        )
        depths = pd.to_numeric(feature_rows["depth"], errors="coerce")
        alt_fraction_complete = bool(not alt_fractions.isna().any())
        depth_complete = bool(not depths.isna().any())
        stats[str(feature_label)] = {
            "candidate_sites": int(feature_rows["position"].nunique()),
            "max_alt_allele_fraction": (
                round(float(alt_fractions.max()), 6)
                if alt_fraction_complete
                else pd.NA
            ),
            "mean_alt_allele_fraction": (
                round(float(alt_fractions.mean()), 6)
                if alt_fraction_complete
                else pd.NA
            ),
            "median_depth": (
                round(float(depths.median()), 1) if depth_complete else pd.NA
            ),
            "top_site": _format_top_site(top_row),
        }
    return stats


def _candidate_quantitative_evidence(
    overlap_df: pd.DataFrame,
    *,
    candidate_evidence_evaluable: bool,
    upstream_status: str,
    upstream_reason: str,
) -> tuple[str, str, int | object, int | object]:
    """Describe whether every retained candidate row has AF and depth evidence."""

    if not candidate_evidence_evaluable:
        return upstream_status, upstream_reason, pd.NA, pd.NA
    if overlap_df.empty:
        return "not_applicable", "no_candidate_rows", 0, 0

    alt_measured = int(overlap_df["alt_allele_fraction"].notna().sum())
    depth_measured = int(overlap_df["depth"].notna().sum())
    row_count = len(overlap_df)
    missing_alt = alt_measured != row_count
    missing_depth = depth_measured != row_count
    if not missing_alt and not missing_depth:
        return "ok", "", alt_measured, depth_measured
    if missing_alt and missing_depth:
        reason = "candidate_alt_fraction_and_depth_incomplete"
    elif missing_alt:
        reason = "candidate_alt_fraction_incomplete"
    else:
        reason = "candidate_depth_incomplete"
    return "not_evaluable", reason, alt_measured, depth_measured


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
) -> dict[str, Path | str]:
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

    candidate_output_present = overlap_path.exists()
    if candidate_output_present:
        candidate_evidence_status, candidate_evidence_reason = _read_module_status(
            summary_dir / "mito_feature_annotation_summary.tsv",
            default_status="ok",
            default_reason="",
        )
    else:
        candidate_evidence_status = "not_evaluable"
        candidate_evidence_reason = "feature_overlap_candidates_missing"
    candidate_evidence_evaluable = (
        candidate_output_present and candidate_evidence_status == "ok"
    )
    if candidate_output_present:
        overlap_df = pd.read_csv(overlap_path, sep="\t")
    else:
        overlap_df = _empty_site_detail_df()
    overlap_df = _prepare_overlap_df(overlap_df)
    (
        candidate_quantitative_status,
        candidate_quantitative_reason,
        candidate_rows_with_alt_fraction,
        candidate_rows_with_depth,
    ) = _candidate_quantitative_evidence(
        overlap_df,
        candidate_evidence_evaluable=candidate_evidence_evaluable,
        upstream_status=candidate_evidence_status,
        upstream_reason=candidate_evidence_reason,
    )

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
        cosegregation_evidence_status = "not_configured"
        cosegregation_evidence_reason = "cosegregation_selected_sites_missing"
        print(
            "[gene_summary] no co-segregation selected-sites table found; selected-site counts are unavailable",
            flush=True,
        )
    else:
        selected_df = pd.read_csv(selected_sites_path, sep="\t")
        selected_positions = _extract_selected_positions(selected_df)
        cosegregation_evidence_status, cosegregation_evidence_reason = _read_module_status(
            summary_dir / "mito_cosegregation_summary.tsv",
            default_status="ok",
            default_reason="",
        )
        print(
            f"[gene_summary] loaded selected sites file={selected_sites_path.name} positions={len(selected_positions)}",
            flush=True,
        )

    deletion_events_path = summary_dir / "mito_deletion_events.tsv"
    deletion_clusters_path = summary_dir / "mito_deletion_clusters.tsv"
    if deletion_events_path.exists() and deletion_clusters_path.exists():
        deletion_evidence_status = "ok"
        deletion_evidence_reason = ""
    elif deletion_events_path.exists() or deletion_clusters_path.exists():
        deletion_evidence_status = "not_evaluable"
        deletion_evidence_reason = "incomplete_deletion_outputs"
    else:
        deletion_evidence_status = "not_configured"
        deletion_evidence_reason = "deletion_outputs_missing"
    if deletion_events_path.exists() and deletion_clusters_path.exists():
        deletion_evidence_status, deletion_evidence_reason = _read_module_status(
            summary_dir / "mito_deletion_summary.tsv",
            default_status=deletion_evidence_status,
            default_reason=deletion_evidence_reason,
        )
    deletion_events_df = pd.read_csv(deletion_events_path, sep="\t") if deletion_events_path.exists() else pd.DataFrame()
    deletion_clusters_df = (
        pd.read_csv(deletion_clusters_path, sep="\t") if deletion_clusters_path.exists() else pd.DataFrame()
    )
    deletion_event_intervals = _extract_interval_table(
        deletion_events_df,
        start_candidates=["event_start", "event_bin_start"],
        end_candidates=["event_end", "event_bin_end"],
    )
    deletion_cluster_members = _extract_cluster_member_intervals(
        deletion_events_df,
        deletion_clusters_df,
    )
    evaluable_deletion_clusters = (
        deletion_cluster_members[["cluster_bin_start", "cluster_bin_end"]]
        .drop_duplicates()
        .shape[0]
    )
    source_statuses = (
        candidate_evidence_status,
        cosegregation_evidence_status,
        deletion_evidence_status,
    )
    evaluable_source_count = sum(status == "ok" for status in source_statuses)
    if evaluable_source_count == 0:
        module_status = "not_evaluable"
        module_reason = "no_evaluable_gene_summary_evidence"
    else:
        module_status = "ok"
        module_reason = "" if evaluable_source_count == len(source_statuses) else "partial_upstream_evidence"
    selected_feature_mapping_evaluable = (
        candidate_evidence_evaluable and cosegregation_evidence_status == "ok"
    )
    print(
        "[gene_summary] loaded "
        f"feature_rows={len(catalog_df)} candidate_rows={len(overlap_df)} "
        f"deletion_events={len(deletion_event_intervals)} "
        f"deletion_cluster_members={len(deletion_cluster_members)} "
        f"evaluable_deletion_clusters={evaluable_deletion_clusters}",
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
        if candidate_evidence_evaluable:
            candidate_default = {
                "candidate_sites": 0,
                "max_alt_allele_fraction": pd.NA,
                "mean_alt_allele_fraction": pd.NA,
                "median_depth": pd.NA,
                "top_site": "NA",
            }
        else:
            candidate_default = {
                "candidate_sites": pd.NA,
                "max_alt_allele_fraction": pd.NA,
                "mean_alt_allele_fraction": pd.NA,
                "median_depth": pd.NA,
                "top_site": "NA",
            }
        candidate_stat = candidate_stats.get(feature_label, candidate_default)
        interval_text = (
            "non-feature candidate positions"
            if feature_label == "intergenic"
            else _format_intervals(feature_intervals)
        )
        if deletion_evidence_status != "ok":
            deletion_event_overlaps = pd.NA
            deletion_cluster_overlaps = pd.NA
            max_cluster_support = pd.NA
        elif feature_label == "intergenic":
            deletion_event_overlaps = 0
            deletion_cluster_overlaps = 0
            max_cluster_support = 0.0
        else:
            deletion_event_overlaps, _ = _count_overlapping_intervals(deletion_event_intervals, feature_intervals)
            deletion_cluster_overlaps, max_cluster_support = _count_overlapping_clusters(
                deletion_cluster_members,
                feature_intervals,
            )

        summary_rows.append(
            {
                "feature_label": feature_label,
                "feature_class": feature_class,
                "feature_intervals": interval_text,
                "candidate_sites": _int_or_na(candidate_stat["candidate_sites"]),
                "selected_coseg_sites": (
                    int(selected_counts.get(feature_label, 0))
                    if selected_feature_mapping_evaluable
                    else pd.NA
                ),
                "max_alt_allele_fraction": _round_or_na(
                    candidate_stat["max_alt_allele_fraction"], 6
                ),
                "mean_alt_allele_fraction": _round_or_na(
                    candidate_stat["mean_alt_allele_fraction"], 6
                ),
                "max_heteroplasmy": _round_or_na(candidate_stat["max_alt_allele_fraction"], 6),
                "mean_heteroplasmy": _round_or_na(candidate_stat["mean_alt_allele_fraction"], 6),
                "median_depth": _round_or_na(candidate_stat["median_depth"], 1),
                "deletion_event_overlaps": _int_or_na(deletion_event_overlaps),
                "deletion_cluster_overlaps": _int_or_na(deletion_cluster_overlaps),
                "max_cluster_support_fraction_primary": _round_or_na(max_cluster_support, 6),
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
    candidate_feature_count = _positive_count(
        summary_df, "candidate_sites", evaluable=candidate_evidence_evaluable
    )
    selected_feature_count = _positive_count(
        summary_df,
        "selected_coseg_sites",
        evaluable=selected_feature_mapping_evaluable,
    )
    deletion_feature_count = _positive_count(
        summary_df,
        "deletion_cluster_overlaps",
        evaluable=deletion_evidence_status == "ok",
    )
    run_summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": module_status},
            {"metric": "reason_code", "value": module_reason},
            {"metric": "candidate_evidence_status", "value": candidate_evidence_status},
            {"metric": "candidate_evidence_reason_code", "value": candidate_evidence_reason},
            {
                "metric": "candidate_quantitative_evidence_status",
                "value": candidate_quantitative_status,
            },
            {
                "metric": "candidate_quantitative_evidence_reason_code",
                "value": candidate_quantitative_reason,
            },
            {
                "metric": "candidate_rows_with_alt_allele_fraction",
                "value": candidate_rows_with_alt_fraction,
            },
            {
                "metric": "candidate_rows_with_depth",
                "value": candidate_rows_with_depth,
            },
            {"metric": "cosegregation_evidence_status", "value": cosegregation_evidence_status},
            {
                "metric": "cosegregation_evidence_reason_code",
                "value": cosegregation_evidence_reason,
            },
            {"metric": "deletion_evidence_status", "value": deletion_evidence_status},
            {"metric": "deletion_evidence_reason_code", "value": deletion_evidence_reason},
            {"metric": "features_summarized", "value": len(summary_df)},
            {
                "metric": "features_with_candidate_sites",
                "value": candidate_feature_count,
            },
            {
                "metric": "features_with_deletion_cluster_overlap",
                "value": deletion_feature_count,
            },
            {
                "metric": "features_with_cosegregation_selected_sites",
                "value": selected_feature_count,
            },
            {
                "metric": "candidate_site_rows",
                "value": len(site_detail_df) if candidate_evidence_evaluable else pd.NA,
            },
            {
                "metric": "selected_coseg_positions_loaded",
                "value": len(selected_positions) if cosegregation_evidence_status == "ok" else pd.NA,
            },
            {
                "metric": "deletion_event_intervals_loaded",
                "value": len(deletion_event_intervals) if deletion_evidence_status == "ok" else pd.NA,
            },
            {
                "metric": "deletion_cluster_overlap_method",
                "value": "exact_member_event_intervals",
            },
            {
                "metric": "deletion_cluster_member_intervals_loaded",
                "value": len(deletion_cluster_members) if deletion_evidence_status == "ok" else pd.NA,
            },
            {
                "metric": "deletion_clusters_evaluable",
                "value": evaluable_deletion_clusters if deletion_evidence_status == "ok" else pd.NA,
            },
        ]
    )

    summary_df.to_csv(summary_path, sep="\t", index=False)
    site_detail_df.to_csv(site_details_path, sep="\t", index=False)
    run_summary_df.to_csv(run_summary_path, sep="\t", index=False)

    fig_path: Path | None = None
    candidate_positive = pd.to_numeric(summary_df["candidate_sites"], errors="coerce").fillna(0) > 0
    selected_positive = pd.to_numeric(summary_df["selected_coseg_sites"], errors="coerce").fillna(0) > 0
    deletion_positive = pd.to_numeric(summary_df["deletion_cluster_overlaps"], errors="coerce").fillna(0) > 0
    overview_df = summary_df[candidate_positive | selected_positive | deletion_positive].head(20)
    if not overview_df.empty:
        plot_df = overview_df.iloc[::-1].copy()
        for column in ("candidate_sites", "selected_coseg_sites", "deletion_cluster_overlaps"):
            plot_df[column] = pd.to_numeric(plot_df[column], errors="coerce").fillna(0)
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
            metric_card("Evaluation status", module_status),
            metric_card("Features summarized", len(summary_df)),
            metric_card(
                "Features with candidate sites",
                "NA" if pd.isna(candidate_feature_count) else candidate_feature_count,
            ),
            metric_card(
                "Features with deletion-cluster overlap",
                "NA" if pd.isna(deletion_feature_count) else deletion_feature_count,
            ),
            metric_card(
                "Features with co-segregation-selected sites",
                "NA" if pd.isna(selected_feature_count) else selected_feature_count,
            ),
        ]
    )
    intro_html = (
        '<p class="muted">This page aggregates mitochondrial candidate-site burden at the feature level. '
        "It highlights which genes or control-region features concentrate alternate-allele candidates, "
        "whether selected co-segregation sites cluster in the same features, and whether exact "
        "one-based deletion-event spans overlap those features. Cluster-level overlap is counted "
        "only when at least one exact member event overlaps; zero-based breakpoint-bin anchors are "
        "not treated as biological deletion intervals. Metrics whose upstream evidence is unavailable "
        "are reported as NA rather than as observed zeros.</p>"
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
        "<section><h2>Gene/feature summary</h2>"
        + df_to_html_table(summary_df.fillna("NA"), max_rows=30)
        + "</section>"
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
        f"status={module_status} features={len(summary_df)} candidate_features={candidate_feature_count} "
        f"selected_features={selected_feature_count} deletion_features={deletion_feature_count}",
        flush=True,
    )
    return {
        "status": module_status,
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
