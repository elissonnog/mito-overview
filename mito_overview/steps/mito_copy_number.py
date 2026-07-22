"""Experimental within-sample mitochondrial-to-nuclear depth ratio."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page

WINDOW_COLUMNS = [
    "contig",
    "start",
    "end",
    "window_size",
    "mean_depth",
    "valid_for_denominator",
]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--align-file", required=True)
    parser.add_argument("--align-mode", required=True)
    parser.add_argument("--ref-fasta", required=True)
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--species", required=True)
    parser.add_argument("--reference-scope", default="whole_genome", choices=("whole_genome", "mt_only", "custom"))
    parser.add_argument("--window-size", type=int, default=100000)
    parser.add_argument("--window-count", type=int, default=5)
    return parser


def open_alignment(path: str | Path, mode: str, ref_fasta: str | Path) -> pysam.AlignmentFile:
    path = str(path)
    if mode == "cram" or path.endswith(".cram"):
        return pysam.AlignmentFile(path, "rc", reference_filename=str(ref_fasta))
    return pysam.AlignmentFile(path, "rb")


def canonical_autosomes(species: str) -> list[str]:
    species = species.lower()
    if species == "mouse":
        return [str(i) for i in range(1, 20)] + [f"chr{i}" for i in range(1, 20)]
    return [str(i) for i in range(1, 23)] + [f"chr{i}" for i in range(1, 23)]


def contig_window(length: int, window_size: int) -> tuple[int, int]:
    if length <= window_size:
        return 1, length
    start = int((length - window_size) / 2) + 1
    end = start + window_size - 1
    return start, end


def run_step(
    *,
    align_file: str | Path,
    align_mode: str,
    ref_fasta: str | Path,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    species: str,
    reference_scope: str = "whole_genome",
    window_size: int,
    window_count: int,
) -> dict[str, Path | str]:
    """Estimate the mt:nuclear depth proxy from the original alignment source."""

    print(
        f"[copy_number] starting sample={sample_id} species={species} reference_scope={reference_scope} "
        f"window_size={window_size} window_count={window_count}"
    )
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    mito_depth_path = summary_dir / "mito_depth_per_base.tsv"
    mt_mean_depth: float | None = None
    if mito_depth_path.exists() and mito_depth_path.stat().st_size > 0:
        mito_depth_df = pd.read_csv(mito_depth_path, sep="\t")
        if "depth" in mito_depth_df.columns:
            observed_depth = pd.to_numeric(mito_depth_df["depth"], errors="coerce").dropna()
            if not observed_depth.empty:
                mt_mean_depth = float(observed_depth.mean())

    bam_handle = open_alignment(align_file, align_mode, ref_fasta)
    refs = {name: length for name, length in zip(bam_handle.references, bam_handle.lengths)}
    preferred = canonical_autosomes(species)
    selected: list[tuple[str, int]] = []
    if reference_scope == "whole_genome":
        for contig in preferred:
            if contig in refs and contig != mt_contig:
                selected.append((contig, refs[contig]))
            if len(selected) >= window_count:
                break
        if not selected:
            for contig, length in refs.items():
                if contig == mt_contig:
                    continue
                if "_" in contig or "random" in contig.lower() or "un" in contig.lower():
                    continue
                selected.append((contig, length))
                if len(selected) >= window_count:
                    break

    window_rows: list[dict[str, object]] = []
    for idx, (contig, length) in enumerate(selected, start=1):
        start, end = contig_window(length, window_size)
        cov = bam_handle.count_coverage(contig, start - 1, end, quality_threshold=0)
        depth = [sum(x) for x in zip(*cov)]
        mean_depth = float(sum(depth) / len(depth)) if depth else 0.0
        expected_positions = end - start + 1
        window_rows.append(
            {
                "contig": contig,
                "start": start,
                "end": end,
                "window_size": expected_positions,
                "mean_depth": round(mean_depth, 6),
                "valid_for_denominator": int(len(depth) == expected_positions),
            }
        )
        print(f"[copy_number] window {idx}/{len(selected)} contig={contig} mean_depth={mean_depth:.3f}")
    bam_handle.close()

    windows_df = pd.DataFrame(
        window_rows,
        columns=WINDOW_COLUMNS,
    )
    valid_windows_df = windows_df[windows_df["valid_for_denominator"] == 1]
    nuclear_mean = (
        float(valid_windows_df["mean_depth"].mean()) if not valid_windows_df.empty else None
    )
    if mt_mean_depth is None:
        status = "not_evaluable"
        reason_code = "no_mito_depth_evidence"
        ratio = None
    elif reference_scope != "whole_genome":
        status = "not_evaluable"
        reason_code = "no_valid_nuclear_windows"
        ratio = None
    elif nuclear_mean is None:
        status = "not_evaluable"
        reason_code = "no_valid_nuclear_windows"
        ratio = None
    elif nuclear_mean <= 0:
        status = "not_evaluable"
        reason_code = "zero_nuclear_depth_denominator"
        ratio = None
    else:
        status = "ok"
        reason_code = ""
        ratio = mt_mean_depth / nuclear_mean
    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": status},
            {"metric": "reason_code", "value": reason_code},
            {"metric": "reference_scope", "value": reference_scope},
            {"metric": "mt_mean_depth", "value": "" if mt_mean_depth is None else round(mt_mean_depth, 6)},
            {"metric": "nuclear_window_mean_depth", "value": "" if nuclear_mean is None else round(nuclear_mean, 6)},
            {"metric": "mt_to_nuclear_depth_ratio", "value": "" if ratio is None else round(ratio, 6)},
            {"metric": "nuclear_windows_requested", "value": window_count},
            {"metric": "nuclear_windows_valid", "value": len(valid_windows_df)},
            {"metric": "nuclear_windows_used", "value": len(valid_windows_df)},
            {"metric": "window_size_bp", "value": window_size},
        ]
    )

    windows_path = summary_dir / "mito_copy_number_windows.tsv"
    summary_path = summary_dir / "mito_copy_number_summary.tsv"
    windows_df.to_csv(windows_path, sep="\t", index=False)
    summary_df.to_csv(summary_path, sep="\t", index=False)

    fig_path = figure_dir / "mito_copy_number_proxy.png"
    labels = ["mtDNA"] + windows_df["contig"].tolist()
    values = [float("nan") if mt_mean_depth is None else mt_mean_depth] + windows_df["mean_depth"].tolist()
    plt.figure(figsize=(10, 5))
    plt.bar(labels, values, color=["#7c3aed"] + ["#2563eb"] * len(windows_df))
    plt.ylabel("Mean depth")
    plt.title(f"{sample_id} mtDNA:nuclear depth proxy")
    plt.tight_layout()
    plt.savefig(fig_path, dpi=150)
    plt.close()

    metrics_html = "".join(
        [
            metric_card("mt mean depth", "NA" if mt_mean_depth is None else round(mt_mean_depth, 3)),
            metric_card("nuclear mean depth", "NA" if nuclear_mean is None else round(nuclear_mean, 3)),
            metric_card("mt:nuclear ratio", "NA" if ratio is None else round(ratio, 3)),
            metric_card("valid nuclear windows", len(valid_windows_df)),
        ]
    )
    if status != "ok":
        windows_note = (
            '<p class="small-note">The mt:nuclear ratio is not evaluable for this run. '
            f"Reason: {reason_code}. Missing nuclear context is represented as NA, not as zero.</p>"
        )
    else:
        windows_note = ""
    intro_html = (
        '<p class="muted">Experimental within-sample mt:nuclear depth ratio using whole-mitochondrion depth '
        "compared with fixed nuclear windows from canonical autosomes. This ratio is not a calibrated or absolute "
        "mtDNA copy-number measurement. Every successfully measured fixed window contributes to the nuclear "
        "mean, including windows with observed depth zero. An all-zero nuclear mean cannot define a ratio and is "
        "reported as not evaluable rather than as zero or infinity.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>{windows_note}"
    )
    body_html = (
        "<section><h2>Depth proxy figure</h2>"
        + figure_html(fig_path, "Mitochondrial and nuclear reference-window mean depth")
        + "</section>"
        + "<section><h2>Copy-number summary</h2>"
        + df_to_html_table(summary_df, max_rows=20)
        + "</section>"
        + "<section><h2>Nuclear windows used</h2>"
        + df_to_html_table(windows_df, max_rows=20)
        + "</section>"
    )
    report_path = report_dir / "04_mito_copy_number.html"
    render_page(
        report_path,
        "Mitochondrial Copy-Number Proxy",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        body_html,
    )
    return {
        "status": status,
        "summary_path": summary_path,
        "windows_path": windows_path,
        "report_path": report_path,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        align_file=args.align_file,
        align_mode=args.align_mode,
        ref_fasta=args.ref_fasta,
        summary_dir=args.summary_dir,
        figure_dir=args.figure_dir,
        report_dir=args.report_dir,
        sample_id=args.sample_id,
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
        species=args.species,
        reference_scope=args.reference_scope,
        window_size=args.window_size,
        window_count=args.window_count,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
