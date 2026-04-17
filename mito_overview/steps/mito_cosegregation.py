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
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page

TOP_SITES_LIMIT = 8
MIN_SHARED_READS_THRESHOLD = 25
SELECTED_SITE_COLUMNS = [
    "site_label",
    "position",
    "ref_base",
    "alt_base",
    "heteroplasmy_fraction",
    "depth",
    "covered_reads",
    "alt_reads",
]
PAIRWISE_COLUMNS = [
    "site_i",
    "site_j",
    "shared_reads",
    "alt_i_shared_reads",
    "alt_j_shared_reads",
    "co_alt_reads",
    "co_alt_fraction_shared",
    "jaccard_alt",
    "fraction_alt_i_also_alt_j",
    "fraction_alt_j_also_alt_i",
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
    return parser


def _empty_selected_sites() -> pd.DataFrame:
    return pd.DataFrame(columns=SELECTED_SITE_COLUMNS)


def _empty_pairwise() -> pd.DataFrame:
    return pd.DataFrame(columns=PAIRWISE_COLUMNS)


def _empty_read_burden() -> pd.DataFrame:
    return pd.DataFrame(columns=READ_BURDEN_COLUMNS)


def _site_label(position: int, ref_base: str, alt_base: str) -> str:
    return f"{position}:{ref_base}>{alt_base}"


def _load_selected_sites(summary_dir: Path, top_sites_limit: int) -> tuple[pd.DataFrame, str | None]:
    candidates_path = summary_dir / "mito_heteroplasmy_candidates.tsv"
    if not candidates_path.exists():
        message = (
            "No heteroplasmy candidate table was found, so the co-segregation step wrote stable empty outputs."
        )
        print(f"[cosegregation] {message} path={candidates_path}", flush=True)
        return _empty_selected_sites(), message

    candidates_df = pd.read_csv(candidates_path, sep="\t")
    required = {"position", "ref_base", "alt_base", "heteroplasmy_fraction", "depth"}
    missing = sorted(required - set(candidates_df.columns))
    if missing:
        message = (
            "The heteroplasmy candidate table is missing required columns "
            + ",".join(missing)
            + "; stable empty outputs were written."
        )
        print(f"[cosegregation] {message}", flush=True)
        return _empty_selected_sites(), message

    filtered = candidates_df.copy()
    filtered = filtered.dropna(subset=["position", "ref_base", "alt_base", "heteroplasmy_fraction", "depth"])
    filtered["alt_base"] = filtered["alt_base"].astype(str).str.upper()
    filtered["ref_base"] = filtered["ref_base"].astype(str).str.upper()
    filtered = filtered[filtered["alt_base"] != "."]
    if filtered.empty:
        message = "The heteroplasmy candidate table is present but empty after filtering; stable empty outputs were written."
        print(f"[cosegregation] {message}", flush=True)
        return _empty_selected_sites(), message

    filtered["position"] = filtered["position"].astype(int)
    filtered["depth"] = filtered["depth"].astype(int)
    filtered["heteroplasmy_fraction"] = filtered["heteroplasmy_fraction"].astype(float).round(6)
    filtered = filtered.drop_duplicates(subset=["position", "alt_base"])
    filtered = filtered.sort_values(
        ["heteroplasmy_fraction", "depth", "position"],
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
    return selected_df, None


def _collect_read_support(
    bam_path: str | Path,
    contig: str,
    selected_sites: pd.DataFrame,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    coverage_by_site: dict[str, set[str]] = {}
    alt_by_site: dict[str, set[str]] = {}
    if selected_sites.empty:
        return coverage_by_site, alt_by_site

    bam = pysam.AlignmentFile(str(bam_path), "rb")
    total_sites = len(selected_sites)
    for idx, row in enumerate(selected_sites.itertuples(index=False), start=1):
        site_calls: dict[str, bool] = {}
        for pileupcolumn in bam.pileup(
            contig,
            int(row.position) - 1,
            int(row.position),
            truncate=True,
            stepper="all",
            min_base_quality=0,
        ):
            if pileupcolumn.reference_pos != int(row.position) - 1:
                continue
            for pileupread in pileupcolumn.pileups:
                alignment = pileupread.alignment
                if alignment.is_unmapped or alignment.is_secondary:
                    continue
                if pileupread.is_del or pileupread.is_refskip:
                    continue
                query_position = pileupread.query_position
                if query_position is None or alignment.query_sequence is None:
                    continue
                read_name = alignment.query_name
                base = alignment.query_sequence[query_position].upper()
                site_calls[read_name] = site_calls.get(read_name, False) or base == str(row.alt_base)
        coverage_by_site[str(row.site_label)] = set(site_calls)
        alt_by_site[str(row.site_label)] = {
            read_name for read_name, is_alt in site_calls.items() if is_alt
        }
        print(
            f"[cosegregation] collected site {idx}/{total_sites} "
            f"label={row.site_label} covered_reads={len(coverage_by_site[str(row.site_label)])} "
            f"alt_reads={len(alt_by_site[str(row.site_label)])}",
            flush=True,
        )
    bam.close()
    return coverage_by_site, alt_by_site


def _summarise_pairwise(
    selected_sites: pd.DataFrame,
    coverage_by_site: dict[str, set[str]],
    alt_by_site: dict[str, set[str]],
    min_shared_reads: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
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
            jaccard_alt = round((co_alt_reads / union_alt) if union_alt else 0.0, 6)
            fraction_alt_i_also_alt_j = round((co_alt_reads / alt_i_shared) if alt_i_shared else 0.0, 6)
            fraction_alt_j_also_alt_i = round((co_alt_reads / alt_j_shared) if alt_j_shared else 0.0, 6)
            rows.append(
                {
                    "site_i": site_i,
                    "site_j": site_j,
                    "shared_reads": shared_count,
                    "alt_i_shared_reads": alt_i_shared,
                    "alt_j_shared_reads": alt_j_shared,
                    "co_alt_reads": co_alt_reads,
                    "co_alt_fraction_shared": co_alt_fraction_shared,
                    "jaccard_alt": jaccard_alt,
                    "fraction_alt_i_also_alt_j": fraction_alt_i_also_alt_j,
                    "fraction_alt_j_also_alt_i": fraction_alt_j_also_alt_i,
                }
            )
            heatmap.loc[site_i, site_j] = jaccard_alt
            heatmap.loc[site_j, site_i] = jaccard_alt

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
    plt.colorbar(image, fraction=0.046, pad=0.04, label="Jaccard index")
    plt.xticks(range(len(labels)), labels, rotation=90)
    plt.yticks(range(len(labels)), labels)
    plt.title(f"{sample_id} mitochondrial variant co-segregation")
    for row_idx in range(len(labels)):
        for col_idx in range(len(labels)):
            value = values[row_idx, col_idx]
            if np.isnan(value):
                continue
            text_color = "white" if value >= 0.6 else "black"
            plt.text(col_idx, row_idx, f"{value:.2f}", ha="center", va="center", color=text_color, fontsize=8)
    plt.tight_layout()
    figure_path = figure_dir / "mito_cosegregation_heatmap.png"
    plt.savefig(figure_path, dpi=150)
    plt.close()
    return figure_path


def run_step(
    *,
    bam: str | Path,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
) -> dict[str, Path]:
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

    selected_df, status_message = _load_selected_sites(summary_dir, TOP_SITES_LIMIT)
    coverage_by_site, alt_by_site = _collect_read_support(bam, mt_contig, selected_df)
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

    strongest_pair = "NA"
    strongest_pair_jaccard_alt = 0.0
    if not pairwise_df.empty:
        strongest_row = pairwise_df.sort_values(
            ["jaccard_alt", "co_alt_reads", "shared_reads", "site_i", "site_j"],
            ascending=[False, False, False, True, True],
        ).iloc[0]
        strongest_pair = f"{strongest_row['site_i']} | {strongest_row['site_j']}"
        strongest_pair_jaccard_alt = round(float(strongest_row["jaccard_alt"]), 6)

    summary_df = pd.DataFrame(
        [
            {"metric": "selected_sites", "value": len(selected_df)},
            {
                "metric": "pairwise_edges_meeting_shared_threshold",
                "value": len(pairwise_df),
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
                "metric": "strongest_pair_jaccard_alt",
                "value": strongest_pair_jaccard_alt,
            },
        ]
    )

    selected_path = summary_dir / "mito_cosegregation_selected_sites.tsv"
    pairwise_path = summary_dir / "mito_cosegregation_pairwise.tsv"
    read_burden_path = summary_dir / "mito_cosegregation_read_burden.tsv"
    summary_path = summary_dir / "mito_cosegregation_summary.tsv"
    report_path = report_dir / "06_mito_cosegregation.html"
    selected_df.to_csv(selected_path, sep="\t", index=False)
    pairwise_df.to_csv(pairwise_path, sep="\t", index=False)
    read_burden_df.to_csv(read_burden_path, sep="\t", index=False)
    summary_df.to_csv(summary_path, sep="\t", index=False)

    heatmap_path = _write_heatmap(figure_dir, sample_id, heatmap_df)

    metrics_html = "".join(
        [
            metric_card("Selected sites", len(selected_df)),
            metric_card("Valid pairs", len(pairwise_df)),
            metric_card("Reads represented", reads_with_any_coverage),
            metric_card("Strongest Jaccard", strongest_pair_jaccard_alt),
        ]
    )
    if status_message:
        status_html = f"<p class='small-note'>{status_message}</p>"
    else:
        status_html = ""
    intro_html = (
        '<p class="muted">This page summarizes whether the strongest candidate mitochondrial '
        "heteroplasmy sites tend to occur on the same long reads. The analysis is based on the "
        "top candidate sites from the heteroplasmy step and reports pairwise co-occurrence among "
        "reads that span both positions.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>{status_html}"
    )
    body_parts = [
        "<section><h2>Selected candidate sites</h2>"
        + df_to_html_table(selected_df, max_rows=20)
        + "</section>",
    ]
    if heatmap_path is not None:
        body_parts.append(
            "<section><h2>Co-segregation heatmap</h2>"
            + figure_html(heatmap_path, "Pairwise Jaccard index for alt-supporting read sets")
            + "</section>"
        )
    body_parts.extend(
        [
            "<section><h2>Pairwise co-segregation summary</h2>"
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
        "Mitochondrial Variant Co-segregation",
        sample_id,
        f"{mt_contig}:1-pairwise_selected_sites",
        intro_html,
        "".join(body_parts),
    )
    return {
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
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
