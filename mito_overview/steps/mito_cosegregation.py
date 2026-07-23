"""Mitochondrial variant co-segregation summary for mito-overview."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mito_overview.allele_counting import AlleleFilterPolicy, collect_site_read_calls, policy_rows
from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import (
    load_metric_module_state,
    load_reference_sequence,
    validate_candidate_table,
)

TOP_SITES_LIMIT = 8
MIN_SHARED_READS_THRESHOLD = 25
CONDITIONAL_UNIVERSE = "filtered_reads_spanning_both_sites"
COSEGREGATION_METHOD = "alt_read_set_jaccard_conditioned_on_shared_spanning_reads"
CANONICAL_JACCARD_COLUMN = "alt_jaccard_within_shared_spanning_reads"
LEGACY_JACCARD_COLUMN = "jaccard_alt"
JACCARD_STATUS_COLUMN = "alt_jaccard_status"
FRACTION_I_STATUS_COLUMN = "fraction_alt_i_also_alt_j_status"
FRACTION_J_STATUS_COLUMN = "fraction_alt_j_also_alt_i_status"
SELECTED_SITE_COLUMNS = [
    "site_label",
    "position",
    "ref_base",
    "alt_base",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "callable_depth",
    "depth",
    "covered_reads",
    "alt_reads",
]
PAIRWISE_COLUMNS = [
    "site_i",
    "site_j",
    "conditional_universe",
    "shared_reads",
    "alt_i_shared_reads",
    "alt_j_shared_reads",
    "co_alt_reads",
    "co_alt_fraction_shared",
    CANONICAL_JACCARD_COLUMN,
    LEGACY_JACCARD_COLUMN,
    JACCARD_STATUS_COLUMN,
    "fraction_alt_i_also_alt_j",
    FRACTION_I_STATUS_COLUMN,
    "fraction_alt_j_also_alt_i",
    FRACTION_J_STATUS_COLUMN,
]
READ_BURDEN_COLUMNS = ["alt_selected_sites", "read_count"]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bam", required=True)
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--ref-fasta", required=True)
    parser.add_argument("--min-base-quality", type=int, default=13)
    parser.add_argument("--min-mapping-quality", type=int, default=20)
    parser.add_argument("--min-read-mean-quality", type=float, default=10.0)
    parser.add_argument("--max-depth", type=int, default=0)
    parser.add_argument("--exclude-flags", type=lambda value: int(value, 0), default=3844)
    parser.add_argument("--ignore-overlaps", type=int, choices=(0, 1), default=1)
    return parser


def _empty_selected_sites() -> pd.DataFrame:
    return pd.DataFrame(columns=SELECTED_SITE_COLUMNS)


def _empty_pairwise() -> pd.DataFrame:
    return pd.DataFrame(columns=PAIRWISE_COLUMNS)


def _empty_read_burden() -> pd.DataFrame:
    return pd.DataFrame(columns=READ_BURDEN_COLUMNS)


def _site_label(position: int, ref_base: str, alt_base: str) -> str:
    return f"{position}:{ref_base}>{alt_base}"


def _load_selected_sites(
    summary_dir: Path,
    top_sites_limit: int,
    mt_length: int,
    reference_sequence: str,
) -> tuple[pd.DataFrame, str | None, str | None, str | None]:
    upstream_status, upstream_reason = load_metric_module_state(
        summary_dir / "mito_heteroplasmy_summary.tsv",
        module_name="heteroplasmy",
    )
    if upstream_status != "ok":
        message = (
            "Upstream alternate-allele counting was not successful, so stale candidate rows "
            f"were not evaluated (status={upstream_status}, reason={upstream_reason})."
        )
        print(f"[cosegregation] {message}", flush=True)
        return _empty_selected_sites(), message, upstream_status, upstream_reason

    candidates_path = summary_dir / "mito_heteroplasmy_candidates.tsv"
    if not candidates_path.exists():
        message = (
            "No heteroplasmy candidate table was found, so the co-segregation step wrote stable empty outputs."
        )
        print(f"[cosegregation] {message} path={candidates_path}", flush=True)
        return _empty_selected_sites(), message, None, None

    candidates_df = pd.read_csv(candidates_path, sep="\t")
    filtered = validate_candidate_table(
        candidates_df,
        table_name="mito_heteroplasmy_candidates.tsv",
        mt_length=mt_length,
        reference_sequence=reference_sequence,
    )
    if filtered.empty:
        message = "The heteroplasmy candidate table is present but empty after filtering; stable empty outputs were written."
        print(f"[cosegregation] {message}", flush=True)
        return _empty_selected_sites(), message, None, None

    if filtered.duplicated(subset=["position", "ref_base", "alt_base"]).any():
        raise ValueError("mito_heteroplasmy_candidates.tsv contains duplicate variant keys")
    filtered = filtered.sort_values(
        ["alt_allele_fraction", "callable_depth", "position"],
        ascending=[False, False, True],
    ).head(top_sites_limit)
    filtered = filtered.reset_index(drop=True)
    filtered["site_label"] = [
        _site_label(int(row.position), str(row.ref_base), str(row.alt_base))
        for row in filtered.itertuples(index=False)
    ]
    filtered["covered_reads"] = 0
    filtered["alt_reads"] = 0
    selected_df = filtered[SELECTED_SITE_COLUMNS].copy()
    print(f"[cosegregation] selected_sites={len(selected_df)} from={candidates_path}", flush=True)
    return selected_df, None, None, None


def _collect_read_support(
    bam_path: str | Path,
    contig: str,
    selected_sites: pd.DataFrame,
    policy: AlleleFilterPolicy,
) -> tuple[dict[str, set[str]], dict[str, set[str]], object]:
    coverage_by_site: dict[str, set[str]] = {}
    alt_by_site: dict[str, set[str]] = {}
    if selected_sites.empty:
        _, _, stats = collect_site_read_calls(bam_path=bam_path, contig=contig, sites={}, policy=policy)
        return coverage_by_site, alt_by_site, stats

    sites = {int(row.position): str(row.alt_base) for row in selected_sites.itertuples(index=False)}
    coverage_by_position, alt_by_position, stats = collect_site_read_calls(
        bam_path=bam_path,
        contig=contig,
        sites=sites,
        policy=policy,
    )
    total_sites = len(selected_sites)
    for idx, row in enumerate(selected_sites.itertuples(index=False), start=1):
        position = int(row.position)
        coverage_by_site[str(row.site_label)] = coverage_by_position.get(position, set())
        alt_by_site[str(row.site_label)] = alt_by_position.get(position, set())
        print(
            f"[cosegregation] collected site {idx}/{total_sites} "
            f"label={row.site_label} covered_reads={len(coverage_by_site[str(row.site_label)])} "
            f"alt_reads={len(alt_by_site[str(row.site_label)])}",
            flush=True,
        )
    return coverage_by_site, alt_by_site, stats


def _summarise_pairwise(
    selected_sites: pd.DataFrame,
    coverage_by_site: dict[str, set[str]],
    alt_by_site: dict[str, set[str]],
    min_shared_reads: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Summarize alternate-read overlap within each pair's shared-spanning reads.

    ``jaccard_alt`` is retained as a compatibility alias of the canonical
    ``alt_jaccard_within_shared_spanning_reads`` field. Neither field is a
    Jaccard index over the sites' global alternate-supporting read sets.
    """

    labels = selected_sites["site_label"].astype(str).tolist()
    heatmap = pd.DataFrame(np.nan, index=labels, columns=labels, dtype=float)
    for label in labels:
        heatmap.loc[label, label] = 1.0

    rows: list[dict[str, object]] = []
    for idx, site_i in enumerate(labels):
        coverage_i = coverage_by_site.get(site_i, set())
        alt_i = alt_by_site.get(site_i, set())
        for site_j in labels[idx + 1 :]:
            coverage_j = coverage_by_site.get(site_j, set())
            alt_j = alt_by_site.get(site_j, set())
            shared_reads = coverage_i & coverage_j
            shared_count = len(shared_reads)
            if shared_count < min_shared_reads:
                continue
            alt_i_shared = len(shared_reads & alt_i)
            alt_j_shared = len(shared_reads & alt_j)
            co_alt_reads = len(shared_reads & alt_i & alt_j)
            union_alt = alt_i_shared + alt_j_shared - co_alt_reads
            co_alt_fraction_shared = round((co_alt_reads / shared_count) if shared_count else 0.0, 6)
            conditional_alt_jaccard = (
                round(co_alt_reads / union_alt, 6) if union_alt else float("nan")
            )
            fraction_alt_i_also_alt_j = (
                round(co_alt_reads / alt_i_shared, 6)
                if alt_i_shared
                else float("nan")
            )
            fraction_alt_j_also_alt_i = (
                round(co_alt_reads / alt_j_shared, 6)
                if alt_j_shared
                else float("nan")
            )
            rows.append(
                {
                    "site_i": site_i,
                    "site_j": site_j,
                    "conditional_universe": CONDITIONAL_UNIVERSE,
                    "shared_reads": shared_count,
                    "alt_i_shared_reads": alt_i_shared,
                    "alt_j_shared_reads": alt_j_shared,
                    "co_alt_reads": co_alt_reads,
                    "co_alt_fraction_shared": co_alt_fraction_shared,
                    CANONICAL_JACCARD_COLUMN: conditional_alt_jaccard,
                    LEGACY_JACCARD_COLUMN: conditional_alt_jaccard,
                    JACCARD_STATUS_COLUMN: (
                        "ok" if union_alt else "not_evaluable_zero_alt_union"
                    ),
                    "fraction_alt_i_also_alt_j": fraction_alt_i_also_alt_j,
                    FRACTION_I_STATUS_COLUMN: (
                        "ok" if alt_i_shared else "not_evaluable_zero_alt_i_denominator"
                    ),
                    "fraction_alt_j_also_alt_i": fraction_alt_j_also_alt_i,
                    FRACTION_J_STATUS_COLUMN: (
                        "ok" if alt_j_shared else "not_evaluable_zero_alt_j_denominator"
                    ),
                }
            )
            heatmap.loc[site_i, site_j] = conditional_alt_jaccard
            heatmap.loc[site_j, site_i] = conditional_alt_jaccard

    if rows:
        pairwise_df = pd.DataFrame(rows, columns=PAIRWISE_COLUMNS)
    else:
        pairwise_df = _empty_pairwise()
    return pairwise_df, heatmap


def _summarise_read_burden(
    selected_sites: pd.DataFrame,
    coverage_by_site: dict[str, set[str]],
    alt_by_site: dict[str, set[str]],
) -> tuple[pd.DataFrame, int]:
    read_alt_counts: dict[str, int] = {}
    for label in selected_sites["site_label"].astype(str):
        for read_name in coverage_by_site.get(label, set()):
            read_alt_counts.setdefault(read_name, 0)
        for read_name in alt_by_site.get(label, set()):
            read_alt_counts[read_name] = read_alt_counts.get(read_name, 0) + 1

    reads_with_any_coverage = len(read_alt_counts)
    if not read_alt_counts:
        return _empty_read_burden(), reads_with_any_coverage

    burden_counts = Counter(read_alt_counts.values())
    burden_rows = [
        {
            "alt_selected_sites": alt_selected_sites,
            "read_count": burden_counts.get(alt_selected_sites, 0),
        }
        for alt_selected_sites in range(len(selected_sites) + 1)
    ]
    burden_df = pd.DataFrame(burden_rows, columns=READ_BURDEN_COLUMNS)
    burden_df = burden_df[burden_df["read_count"] > 0].reset_index(drop=True)
    return burden_df, reads_with_any_coverage


def _evaluation_status(
    *,
    selected_site_count: int,
    valid_pair_count: int,
    evaluable_jaccard_pair_count: int,
    upstream_message: str | None,
    upstream_status: str | None = None,
    upstream_reason: str | None = None,
) -> tuple[str, str, str, str | None]:
    if upstream_status:
        return (
            upstream_status,
            "shared-spanning-read conditional co-segregation inherited an upstream status",
            upstream_reason or f"heteroplasmy_status_{upstream_status}",
            upstream_message,
        )
    if upstream_message:
        return (
            "not_evaluable",
            "shared-spanning-read conditional co-segregation was not evaluable",
            "no_candidate_sites_available",
            upstream_message,
        )
    if selected_site_count < 2:
        return (
            "not_evaluable",
            "shared-spanning-read conditional co-segregation requires at least two selected sites",
            "fewer_than_two_selected_sites",
            "Fewer than two candidate sites were selected, so no pairwise statistic was defined.",
        )
    if valid_pair_count == 0:
        return (
            "not_evaluable",
            "no selected-site pair met the shared-read requirement",
            "no_pairs_meet_shared_read_threshold",
            "Pairwise statistics were not reported because no site pair met the configured shared-read floor.",
        )
    if evaluable_jaccard_pair_count == 0:
        return (
            "not_evaluable",
            "shared-spanning read pairs lacked alternate support for a defined Jaccard denominator",
            "no_pairs_with_alt_support",
            "Pairs met the shared-read floor, but no pair had alternate support at either site; "
            "the alt-read Jaccard and strongest pair are therefore undefined.",
        )
    return (
        "ok",
        "shared-spanning-read conditional co-segregation completed",
        "",
        None,
    )


def _write_heatmap(
    figure_dir: Path,
    sample_id: str,
    heatmap: pd.DataFrame,
) -> Path | None:
    if heatmap.empty:
        return None

    values = heatmap.to_numpy(dtype=float)
    if values.size == 0:
        return None

    labels = heatmap.index.tolist()
    masked = np.ma.masked_invalid(values)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad(color="#f3f4f6")
    figure_width = max(6.0, len(labels) * 1.1)
    figure_height = max(5.0, len(labels) * 0.95)
    plt.figure(figsize=(figure_width, figure_height))
    image = plt.imshow(masked, vmin=0.0, vmax=1.0, cmap=cmap)
    plt.colorbar(
        image,
        fraction=0.046,
        pad=0.04,
        label="Alt-read Jaccard within shared-spanning reads",
    )
    plt.xticks(range(len(labels)), labels, rotation=90)
    plt.yticks(range(len(labels)), labels)
    plt.title(f"{sample_id} conditional co-segregation\n(shared-spanning reads only)")
    for row_idx in range(len(labels)):
        for col_idx in range(len(labels)):
            value = values[row_idx, col_idx]
            if np.isnan(value):
                continue
            text_color = _heatmap_text_color(value)
            plt.text(col_idx, row_idx, f"{value:.2f}", ha="center", va="center", color=text_color, fontsize=8)
    plt.tight_layout()
    figure_path = figure_dir / "mito_cosegregation_heatmap.png"
    plt.savefig(figure_path, dpi=150)
    plt.close()
    return figure_path


def _heatmap_text_color(value: float) -> str:
    """Keep annotations legible across the dark-to-bright viridis scale."""
    return "black" if value >= 0.6 else "white"


def run_step(
    *,
    bam: str | Path,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    reference_sequence: str,
    min_base_quality: int = 13,
    min_mapping_quality: int = 20,
    min_read_mean_quality: float = 10.0,
    max_depth: int = 0,
    exclude_flags: int = 3844,
    ignore_overlaps: bool = True,
) -> dict[str, Path | str]:
    """Summarize co-occurrence of selected mtDNA heteroplasmy candidates."""

    print(
        f"[cosegregation] starting sample={sample_id} contig={mt_contig} "
        f"top_sites_limit={TOP_SITES_LIMIT} min_shared_reads_threshold={MIN_SHARED_READS_THRESHOLD}",
        flush=True,
    )
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
    selected_df, status_message, upstream_status, upstream_reason = _load_selected_sites(
        summary_dir,
        TOP_SITES_LIMIT,
        mt_length,
        reference_sequence,
    )
    coverage_by_site, alt_by_site, filter_stats = _collect_read_support(bam, mt_contig, selected_df, policy)
    if not selected_df.empty:
        selected_df = selected_df.copy()
        selected_df["covered_reads"] = [
            len(coverage_by_site.get(label, set())) for label in selected_df["site_label"].astype(str)
        ]
        selected_df["alt_reads"] = [
            len(alt_by_site.get(label, set())) for label in selected_df["site_label"].astype(str)
        ]

    pairwise_df, heatmap_df = _summarise_pairwise(
        selected_df,
        coverage_by_site,
        alt_by_site,
        MIN_SHARED_READS_THRESHOLD,
    )
    read_burden_df, reads_with_any_coverage = _summarise_read_burden(
        selected_df,
        coverage_by_site,
        alt_by_site,
    )
    print(
        f"[cosegregation] pairwise_edges={len(pairwise_df)} "
        f"reads_with_any_selected_site_coverage={reads_with_any_coverage}",
        flush=True,
    )

    evaluable_pairwise_df = pairwise_df[
        pd.to_numeric(pairwise_df[CANONICAL_JACCARD_COLUMN], errors="coerce").notna()
    ]
    strongest_pair = "NA"
    strongest_pair_conditional_alt_jaccard: float | str = "NA"
    if not evaluable_pairwise_df.empty:
        strongest_row = evaluable_pairwise_df.sort_values(
            [CANONICAL_JACCARD_COLUMN, "co_alt_reads", "shared_reads", "site_i", "site_j"],
            ascending=[False, False, False, True, True],
        ).iloc[0]
        strongest_pair = f"{strongest_row['site_i']} | {strongest_row['site_j']}"
        strongest_pair_conditional_alt_jaccard = round(float(strongest_row[CANONICAL_JACCARD_COLUMN]), 6)

    status, status_detail, reason_code, evaluation_message = _evaluation_status(
        selected_site_count=len(selected_df),
        valid_pair_count=len(pairwise_df),
        evaluable_jaccard_pair_count=len(evaluable_pairwise_df),
        upstream_message=status_message,
        upstream_status=upstream_status,
        upstream_reason=upstream_reason,
    )
    summary_rows = [
        {"metric": "status", "value": status},
        {"metric": "status_detail", "value": status_detail},
        {"metric": "reason_code", "value": reason_code},
        {"metric": "method", "value": COSEGREGATION_METHOD},
        {"metric": "conditional_universe", "value": CONDITIONAL_UNIVERSE},
        {
            "metric": "jaccard_alt_compatibility_alias_of",
            "value": CANONICAL_JACCARD_COLUMN,
        },
        {"metric": "selected_sites", "value": len(selected_df)},
        {
            "metric": "pairwise_edges_meeting_shared_threshold",
            "value": len(pairwise_df),
        },
        {
            "metric": "pairwise_edges_with_evaluable_alt_jaccard",
            "value": len(evaluable_pairwise_df),
        },
        {
            "metric": "pairwise_edges_with_undefined_alt_jaccard",
            "value": len(pairwise_df) - len(evaluable_pairwise_df),
        },
        {
            "metric": "reads_with_any_selected_site_coverage",
            "value": reads_with_any_coverage,
        },
        {
            "metric": "min_shared_reads_threshold",
            "value": MIN_SHARED_READS_THRESHOLD,
        },
        {"metric": "top_sites_limit", "value": TOP_SITES_LIMIT},
        {"metric": "strongest_pair", "value": strongest_pair},
        {
            "metric": "strongest_pair_alt_jaccard_within_shared_spanning_reads",
            "value": strongest_pair_conditional_alt_jaccard,
        },
        {
            "metric": "strongest_pair_jaccard_alt",
            "value": strongest_pair_conditional_alt_jaccard,
        },
    ]
    summary_rows.extend(policy_rows(policy, filter_stats))
    summary_df = pd.DataFrame(summary_rows)

    selected_path = summary_dir / "mito_cosegregation_selected_sites.tsv"
    pairwise_path = summary_dir / "mito_cosegregation_pairwise.tsv"
    read_burden_path = summary_dir / "mito_cosegregation_read_burden.tsv"
    summary_path = summary_dir / "mito_cosegregation_summary.tsv"
    report_path = report_dir / "06_mito_cosegregation.html"
    selected_df.to_csv(selected_path, sep="\t", index=False)
    pairwise_df.to_csv(pairwise_path, sep="\t", index=False, na_rep="NA")
    read_burden_df.to_csv(read_burden_path, sep="\t", index=False)
    summary_df.to_csv(summary_path, sep="\t", index=False)

    heatmap_path = _write_heatmap(figure_dir, sample_id, heatmap_df) if status == "ok" else None

    metrics_html = "".join(
        [
            metric_card("Selected sites", len(selected_df)),
            metric_card("Pairs above shared-read floor", len(pairwise_df)),
            metric_card("Jaccard-evaluable pairs", len(evaluable_pairwise_df)),
            metric_card("Reads represented", reads_with_any_coverage),
            metric_card(
                "Strongest alt Jaccard within shared-spanning reads",
                strongest_pair_conditional_alt_jaccard,
            ),
        ]
    )
    if evaluation_message:
        status_html = (
            f"<p class='small-note'><strong>Method/status:</strong> {status_detail}. "
            f"{evaluation_message}</p>"
        )
    else:
        status_html = (
            "<p class='small-note'><strong>Method/status:</strong> Analysis completed. "
            "For each site pair, alternate-support sets were first restricted to filtered reads "
            "spanning both positions.</p>"
        )
    intro_html = (
        '<p class="muted">This page summarizes whether selected mitochondrial candidate sites '
        "tend to occur on the same long reads. The analysis uses the same read and base filters as "
        "the heteroplasmy step. Every pairwise quantity, including the alt-read Jaccard, is conditional "
        "on reads that span both positions; it is not a Jaccard index over each site's global "
        "alternate-supporting read set. The legacy jaccard_alt field is an exact compatibility alias "
        f"of {CANONICAL_JACCARD_COLUMN}.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>{status_html}"
    )
    body_parts = [
        "<section><h2>Selected candidate sites</h2>"
        + df_to_html_table(selected_df, max_rows=20)
        + "</section>",
    ]
    if heatmap_path is not None:
        body_parts.append(
            "<section><h2>Conditional co-segregation within shared-spanning reads</h2>"
            + figure_html(
                heatmap_path,
                "Alt-read Jaccard after restricting both sets to filtered reads spanning both positions; "
                "this is not a global-set Jaccard",
            )
            + "</section>"
        )
    body_parts.extend(
        [
            "<section><h2>Pairwise summary (conditional on shared-spanning reads)</h2>"
            + df_to_html_table(pairwise_df, max_rows=40)
            + "</section>",
            "<section><h2>Read burden summary</h2>"
            + df_to_html_table(read_burden_df, max_rows=20)
            + "</section>",
            "<section><h2>Run summary</h2>"
            + df_to_html_table(summary_df, max_rows=20)
            + "</section>",
        ]
    )

    render_page(
        report_path,
        "Mitochondrial Variant Co-segregation (Shared-Spanning Reads)",
        sample_id,
        f"{mt_contig}:1-pairwise_selected_sites",
        intro_html,
        "".join(body_parts),
    )
    return {
        "status": status,
        "selected_path": selected_path,
        "pairwise_path": pairwise_path,
        "read_burden_path": read_burden_path,
        "summary_path": summary_path,
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
        reference_sequence=load_reference_sequence(
            args.ref_fasta,
            args.mt_contig,
            args.mt_length,
        ),
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
