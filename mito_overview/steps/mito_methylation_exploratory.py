"""Exploratory mitochondrial methylation summary for mito-overview."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page

ROW_COLUMNS = [
    "track",
    "position",
    "valid_coverage",
    "percent_modified",
    "modified_count",
    "canonical_count",
]
PROXY_TRACKS = {"HP1", "HP2", "Ungrouped"}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mito-mods-np", required=True)
    parser.add_argument("--mito-mods-hp1", required=True)
    parser.add_argument("--mito-mods-hp2", required=True)
    parser.add_argument("--mito-mods-ungrouped", required=True)
    return parser


def empty_rows_df() -> pd.DataFrame:
    return pd.DataFrame(columns=ROW_COLUMNS)


def collapse_track_positions(df: pd.DataFrame) -> pd.DataFrame:
    """Pool duplicate bedMethyl rows into one count-weighted track-position row."""

    if df.empty:
        return empty_rows_df()
    pooled = (
        df.groupby(["track", "position"], as_index=False, sort=False)
        .agg(
            valid_coverage=("valid_coverage", "sum"),
            modified_count=("modified_count", "sum"),
            canonical_count=("canonical_count", "sum"),
        )
        .reset_index(drop=True)
    )
    total_calls = pooled["modified_count"] + pooled["canonical_count"]
    pooled["percent_modified"] = pd.Series(np.nan, index=pooled.index, dtype=float)
    evaluable = total_calls > 0
    pooled.loc[evaluable, "percent_modified"] = (
        100.0
        * pooled.loc[evaluable, "modified_count"]
        / total_calls.loc[evaluable]
    ).to_numpy(dtype=float)
    return pooled[ROW_COLUMNS]


def track_input_present(path: str | Path | None) -> int:
    """Return whether a configured track path points to an existing file."""

    return int(path is not None and Path(path).is_file())


def load_bedmethyl_table(path: str | Path | None, track_label: str) -> pd.DataFrame:
    """Load a mitochondrial bedmethyl subset into a normalized table."""

    if not path:
        return empty_rows_df()
    src = Path(path)
    if not src.exists() or src.stat().st_size == 0:
        return empty_rows_df()

    rows: list[dict[str, object]] = []
    with src.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 13:
                continue
            try:
                rows.append(
                    {
                        "track": track_label,
                        "position": int(parts[1]) + 1,
                        "valid_coverage": float(parts[9]),
                        "percent_modified": float(parts[10]),
                        "modified_count": float(parts[11]),
                        "canonical_count": float(parts[12]),
                    }
                )
            except ValueError:
                continue
    if not rows:
        return empty_rows_df()
    return collapse_track_positions(pd.DataFrame(rows, columns=ROW_COLUMNS))


def track_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for track, sub in df.groupby("track", sort=False):
        percent_modified = pd.to_numeric(sub["percent_modified"], errors="coerce")
        valid_coverage = pd.to_numeric(sub["valid_coverage"], errors="coerce")
        coverage_evaluable_rows = percent_modified.notna() & valid_coverage.notna() & (valid_coverage > 0)
        total_cov = float(valid_coverage.loc[coverage_evaluable_rows].sum())
        total_calls = float((sub["modified_count"] + sub["canonical_count"]).sum())
        coverage_evaluable = total_cov > 0
        calls_evaluable = total_calls > 0
        rows.append(
            {
                "track": track,
                "site_count": int(len(sub)),
                "mean_percent_modified": round(float(percent_modified.mean()), 6),
                "median_percent_modified": round(float(percent_modified.median()), 6),
                "coverage_weighted_percent_modified": round(
                    float(
                        (
                            percent_modified.loc[coverage_evaluable_rows]
                            * valid_coverage.loc[coverage_evaluable_rows]
                        ).sum()
                        / total_cov
                    ),
                    6,
                )
                if coverage_evaluable
                else np.nan,
                "coverage_weighted_denominator_valid_coverage": round(total_cov, 6),
                "coverage_weighted_status": "ok" if coverage_evaluable else "not_evaluable",
                "coverage_weighted_reason_code": "" if coverage_evaluable else "zero_valid_coverage",
                "count_weighted_percent_modified": round(
                    float(100.0 * sub["modified_count"].sum() / total_calls),
                    6,
                )
                if calls_evaluable
                else np.nan,
                "count_weighted_denominator_calls": round(total_calls, 6),
                "count_weighted_status": "ok" if calls_evaluable else "not_evaluable",
                "count_weighted_reason_code": "" if calls_evaluable else "zero_modified_plus_canonical_count",
                "mean_valid_coverage": round(float(valid_coverage.mean()), 6),
                "median_valid_coverage": round(float(valid_coverage.median()), 6),
            }
        )
    return pd.DataFrame(rows)


def build_proxy(df: pd.DataFrame) -> pd.DataFrame:
    phased = df[df["track"].isin(PROXY_TRACKS)].copy()
    if phased.empty:
        return empty_rows_df()

    proxy = phased.groupby("position", as_index=False).agg(
        valid_coverage=("valid_coverage", "sum"),
        modified_count=("modified_count", "sum"),
        canonical_count=("canonical_count", "sum"),
    )
    modified_count = pd.to_numeric(proxy["modified_count"], errors="coerce")
    canonical_count = pd.to_numeric(proxy["canonical_count"], errors="coerce")
    total_calls = modified_count + canonical_count
    proxy["percent_modified"] = pd.Series(np.nan, index=proxy.index, dtype=float)
    evaluable = total_calls > 0
    proxy.loc[evaluable, "percent_modified"] = (
        100.0 * modified_count.loc[evaluable] / total_calls.loc[evaluable]
    ).to_numpy(dtype=float)
    proxy["track"] = "Phased_proxy_all_reads"
    return proxy[ROW_COLUMNS]


def np_proxy_comparison_summary(
    comparison_df: pd.DataFrame,
    *,
    tracks_available: int,
    np_rows: int,
    proxy_rows: int,
) -> pd.DataFrame:
    """Summarize NP/proxy agreement without converting undefined statistics to zero."""

    shared_positions = int(len(comparison_df))
    comparable = comparison_df.copy()
    for column in ["percent_modified_np", "percent_modified_proxy"]:
        if column not in comparable.columns:
            comparable[column] = np.nan
        comparable[column] = pd.to_numeric(comparable[column], errors="coerce")
    comparable = comparable.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["percent_modified_np", "percent_modified_proxy"]
    )
    evaluable_positions = int(len(comparable))

    if evaluable_positions:
        mean_abs_difference = round(
            float(
                (
                    comparable["percent_modified_np"]
                    - comparable["percent_modified_proxy"]
                )
                .abs()
                .mean()
            ),
            6,
        )
        mean_status = "ok"
        mean_reason = ""
    else:
        mean_abs_difference = np.nan
        mean_status = "not_evaluable"
        mean_reason = "no_shared_positions" if shared_positions == 0 else "no_evaluable_shared_positions"

    correlation = np.nan
    correlation_status = "not_evaluable"
    if evaluable_positions < 2:
        correlation_reason = "fewer_than_two_evaluable_shared_positions"
    elif (
        comparable["percent_modified_np"].nunique(dropna=True) < 2
        or comparable["percent_modified_proxy"].nunique(dropna=True) < 2
    ):
        correlation_reason = "undefined_zero_variance"
    else:
        corr_value = comparable["percent_modified_np"].corr(comparable["percent_modified_proxy"])
        if pd.notna(corr_value):
            correlation = round(float(corr_value), 6)
            correlation_status = "ok"
            correlation_reason = ""
        else:
            correlation_reason = "undefined_zero_variance"

    if evaluable_positions:
        status = "ok"
        reason_code = ""
    else:
        status = "not_evaluable"
        reason_code = "no_shared_positions" if shared_positions == 0 else "no_evaluable_shared_positions"

    return pd.DataFrame(
        [
            {"metric": "status", "value": status},
            {"metric": "reason_code", "value": reason_code},
            {"metric": "tracks_available", "value": int(tracks_available)},
            {"metric": "np_rows", "value": int(np_rows)},
            {"metric": "proxy_rows", "value": int(proxy_rows)},
            {"metric": "shared_np_proxy_positions", "value": shared_positions},
            {"metric": "evaluable_np_proxy_positions", "value": evaluable_positions},
            {"metric": "np_proxy_mean_abs_difference", "value": mean_abs_difference},
            {
                "metric": "np_proxy_mean_abs_difference_denominator_positions",
                "value": evaluable_positions,
            },
            {"metric": "np_proxy_mean_abs_difference_status", "value": mean_status},
            {"metric": "np_proxy_mean_abs_difference_reason_code", "value": mean_reason},
            {"metric": "np_proxy_correlation", "value": correlation},
            {"metric": "np_proxy_correlation_denominator_positions", "value": evaluable_positions},
            {"metric": "np_proxy_correlation_status", "value": correlation_status},
            {"metric": "np_proxy_correlation_reason_code", "value": correlation_reason},
        ]
    )


def render_no_data_report(
    *,
    summary_path: Path,
    combined_path: Path,
    cmp_path: Path,
    cmp_summary_path: Path,
    report_path: Path,
    sample_id: str,
    mt_contig: str,
    track_paths: dict[str, str | Path | None],
    track_inputs_configured: dict[str, bool],
    inputs_configured: bool,
) -> dict[str, Path | str]:
    """Write a status-only report when no mitochondrial bedmethyl rows are present."""

    status = "not_evaluable" if inputs_configured else "not_configured"
    reason_code = "no_mt_bedmethyl_rows_available" if inputs_configured else "no_bedmethyl_sidecars_configured"
    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": status},
            {"metric": "reason_code", "value": reason_code},
            {
                "metric": "message",
                "value": "No mitochondrial bedmethyl rows were available after mitochondrial subsetting.",
            },
            {"metric": "np_track_input_present", "value": int(track_inputs_configured["NP_real_all_reads"])},
            {"metric": "hp1_track_input_present", "value": int(track_inputs_configured["HP1"])},
            {"metric": "hp2_track_input_present", "value": int(track_inputs_configured["HP2"])},
            {"metric": "ungrouped_track_input_present", "value": int(track_inputs_configured["Ungrouped"])},
        ]
    )
    summary_df.to_csv(summary_path, sep="\t", index=False)
    empty_rows_df().to_csv(combined_path, sep="\t", index=False)
    pd.DataFrame(
        columns=["position", "percent_modified_np", "percent_modified_proxy", "abs_difference"]
    ).to_csv(cmp_path, sep="\t", index=False)
    cmp_summary = np_proxy_comparison_summary(
        pd.DataFrame(),
        tracks_available=0,
        np_rows=0,
        proxy_rows=0,
    )
    cmp_summary.loc[cmp_summary["metric"] == "status", "value"] = status
    cmp_summary.loc[cmp_summary["metric"] == "reason_code", "value"] = reason_code
    cmp_summary.to_csv(cmp_summary_path, sep="\t", index=False, na_rep="NA")
    intro_html = '<p class="muted">No mitochondrial bedmethyl rows were available for the exploratory methylation summary.</p>'
    body_html = "<section><h2>Status</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>"
    render_page(
        report_path,
        "Mito Methylation Exploratory",
        sample_id,
        f"{mt_contig}:whole_mito",
        intro_html,
        body_html,
    )
    return {
        "status": status,
        "summary_path": summary_path,
        "combined_path": combined_path,
        "cmp_path": cmp_path,
        "cmp_summary_path": cmp_summary_path,
        "report_path": report_path,
    }


def run_step(
    *,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    mito_mods_np: str | Path | None,
    mito_mods_hp1: str | Path,
    mito_mods_hp2: str | Path,
    mito_mods_ungrouped: str | Path,
    inputs_configured: bool = True,
    track_inputs_configured: dict[str, bool] | None = None,
) -> dict[str, Path | str]:
    """Run the public exploratory mitochondrial methylation step."""

    print(f"[methylation] starting sample={sample_id} contig={mt_contig}", flush=True)
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    track_paths = {
        "NP_real_all_reads": mito_mods_np,
        "HP1": mito_mods_hp1,
        "HP2": mito_mods_hp2,
        "Ungrouped": mito_mods_ungrouped,
    }
    if track_inputs_configured is None:
        track_inputs_configured = {
            label: bool(track_input_present(path)) for label, path in track_paths.items()
        }
    elif set(track_inputs_configured) != set(track_paths):
        raise ValueError("track_inputs_configured must define exactly the four methylation tracks")
    frames: list[pd.DataFrame] = []
    for track_label, path in track_paths.items():
        frame = load_bedmethyl_table(path, track_label)
        frames.append(frame)
        print(
            f"[methylation] loaded track={track_label} rows={len(frame)} "
            f"path={Path(path) if path else 'None'}",
            flush=True,
        )
    base_df = pd.concat(frames, ignore_index=True) if any(not frame.empty for frame in frames) else empty_rows_df()

    proxy_df = build_proxy(base_df)
    print(f"[methylation] phased proxy rows={len(proxy_df)}", flush=True)
    combined_df = pd.concat([base_df, proxy_df], ignore_index=True) if not proxy_df.empty else base_df.copy()

    summary_path = summary_dir / "mito_methylation_exploratory_summary.tsv"
    combined_path = summary_dir / "mito_methylation_track_rows.tsv"
    cmp_path = summary_dir / "mito_methylation_np_vs_proxy.tsv"
    cmp_summary_path = summary_dir / "mito_methylation_np_vs_proxy_summary.tsv"
    report_path = report_dir / "12_mito_methylation_exploratory.html"
    if combined_df.empty:
        print("[methylation] no mitochondrial bedmethyl rows available; writing status-only report", flush=True)
        return render_no_data_report(
            summary_path=summary_path,
            combined_path=combined_path,
            cmp_path=cmp_path,
            cmp_summary_path=cmp_summary_path,
            report_path=report_path,
            sample_id=sample_id,
            mt_contig=mt_contig,
            track_paths=track_paths,
            track_inputs_configured=track_inputs_configured,
            inputs_configured=inputs_configured,
        )

    combined_df.to_csv(combined_path, sep="\t", index=False, na_rep="NA")
    print(f"[methylation] wrote combined rows {combined_path}", flush=True)

    summary_df = track_summary(combined_df)
    summary_df.to_csv(summary_path, sep="\t", index=False, na_rep="NA")
    print(f"[methylation] wrote track summary {summary_path}", flush=True)

    np_proxy_cmp = pd.DataFrame(
        columns=["position", "percent_modified_np", "percent_modified_proxy", "abs_difference"]
    )
    np_real = combined_df[combined_df["track"] == "NP_real_all_reads"][["position", "percent_modified"]].rename(
        columns={"percent_modified": "percent_modified_np"}
    )
    proxy = combined_df[combined_df["track"] == "Phased_proxy_all_reads"][["position", "percent_modified"]].rename(
        columns={"percent_modified": "percent_modified_proxy"}
    )
    if not np_real.empty and not proxy.empty:
        np_proxy_cmp = pd.merge(np_real, proxy, on="position", how="inner")
        if not np_proxy_cmp.empty:
            np_proxy_cmp["abs_difference"] = (
                np_proxy_cmp["percent_modified_np"] - np_proxy_cmp["percent_modified_proxy"]
            ).abs()
    np_proxy_cmp.to_csv(cmp_path, sep="\t", index=False, na_rep="NA")
    print(f"[methylation] wrote NP vs proxy table {cmp_path}", flush=True)

    cmp_summary = np_proxy_comparison_summary(
        np_proxy_cmp,
        tracks_available=int(summary_df["track"].nunique()),
        np_rows=int((combined_df["track"] == "NP_real_all_reads").sum()),
        proxy_rows=int((combined_df["track"] == "Phased_proxy_all_reads").sum()),
    )
    cmp_summary.to_csv(cmp_summary_path, sep="\t", index=False, na_rep="NA")
    print(f"[methylation] wrote NP vs proxy summary {cmp_summary_path}", flush=True)

    summary_fig = figure_dir / "mito_methylation_weighted_summary.png"
    plot_df = summary_df.copy()
    plt.figure(figsize=(9, 4))
    plt.bar(plot_df["track"], plot_df["coverage_weighted_percent_modified"], color="#0f766e")
    plt.xticks(rotation=30, ha="right")
    plt.ylabel("Coverage-weighted percent modified")
    plt.title(f"{sample_id} mitochondrial methylation track summary")
    plt.tight_layout()
    plt.savefig(summary_fig, dpi=150)
    plt.close()
    print(f"[methylation] wrote weighted-summary figure {summary_fig}", flush=True)

    profile_fig = figure_dir / "mito_methylation_profiles.png"
    plt.figure(figsize=(12, 4))
    for track, sub in combined_df.groupby("track", sort=False):
        sub = sub.sort_values("position").copy()
        smooth = sub["percent_modified"].rolling(window=25, min_periods=1, center=True).mean()
        plt.plot(sub["position"], smooth, linewidth=1.2, label=track)
    plt.xlabel("Mitochondrial position")
    plt.ylabel("Rolling mean percent modified")
    plt.title(f"{sample_id} mitochondrial methylation profiles")
    plt.legend(loc="upper right", fontsize=8)
    plt.tight_layout()
    plt.savefig(profile_fig, dpi=150)
    plt.close()
    print(f"[methylation] wrote profile figure {profile_fig}", flush=True)

    cmp_fig = None
    evaluable_cmp = np_proxy_cmp.dropna(
        subset=["percent_modified_np", "percent_modified_proxy"]
    )
    if not evaluable_cmp.empty:
        cmp_fig = figure_dir / "mito_methylation_np_vs_proxy.png"
        plt.figure(figsize=(5, 5))
        plt.scatter(
            evaluable_cmp["percent_modified_np"],
            evaluable_cmp["percent_modified_proxy"],
            s=8,
            alpha=0.4,
            color="#2563eb",
        )
        plt.xlabel("NP real all-reads % modified")
        plt.ylabel("Phased proxy all-reads % modified")
        plt.title(f"{sample_id} NP vs phased-proxy methylation")
        plt.tight_layout()
        plt.savefig(cmp_fig, dpi=150)
        plt.close()
        print(f"[methylation] wrote NP vs proxy figure {cmp_fig}", flush=True)

    metrics_html = "".join(
        [
            metric_card("Tracks available", int(summary_df["track"].nunique())),
            metric_card("NP rows", int((combined_df["track"] == "NP_real_all_reads").sum())),
            metric_card("Proxy rows", int((combined_df["track"] == "Phased_proxy_all_reads").sum())),
            metric_card("NP/proxy shared positions", int(len(np_proxy_cmp))),
        ]
    )
    intro_html = (
        '<p class="muted">This page provides an exploratory mitochondrial methylation summary using real '
        "mitochondrial bedmethyl rows from both the phased and no-phased workflows. The phased tracks are shown "
        "separately, a phased-derived all-read proxy is reconstructed from the phased tracks, and that proxy is "
        "compared against the real no-phased all-read mitochondrial bedmethyl track. This page is intended for "
        "pattern-finding and QC context rather than strong biological claims about mtDNA methylation.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Track summary</h2>" + df_to_html_table(summary_df.fillna("NA"), max_rows=20) + "</section>",
        "<section><h2>Weighted methylation summary</h2>"
        + figure_html(summary_fig, "Coverage-weighted mitochondrial methylation across tracks")
        + "</section>",
        "<section><h2>Methylation profiles</h2>"
        + figure_html(profile_fig, "Rolling mean methylation profiles across the mitochondrial genome")
        + "</section>",
        "<section><h2>NP vs phased-proxy comparison summary</h2>"
        + df_to_html_table(cmp_summary.fillna("NA"), max_rows=20)
        + "</section>",
        "<section><h2>NP vs phased-proxy shared-position table</h2>"
        + df_to_html_table(np_proxy_cmp.fillna("NA"), max_rows=30)
        + "</section>",
    ]
    if cmp_fig:
        body_parts.insert(
            4,
            "<section><h2>NP vs phased-proxy scatter</h2>"
            + figure_html(
                cmp_fig,
                "Shared-position mitochondrial methylation between real NP all-reads and phased-derived all-read proxy",
            )
            + "</section>",
        )
    render_page(
        report_path,
        "Mito Methylation Exploratory",
        sample_id,
        f"{mt_contig}:whole_mito",
        intro_html,
        "".join(body_parts),
    )
    print(f"[methylation] wrote report {report_path}", flush=True)
    return {
        "status": "ok",
        "track_rows_path": combined_path,
        "summary_path": summary_path,
        "cmp_path": cmp_path,
        "cmp_summary_path": cmp_summary_path,
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
        mito_mods_np=args.mito_mods_np,
        mito_mods_hp1=args.mito_mods_hp1,
        mito_mods_hp2=args.mito_mods_hp2,
        mito_mods_ungrouped=args.mito_mods_ungrouped,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
