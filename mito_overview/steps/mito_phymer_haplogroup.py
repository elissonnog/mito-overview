"""Optional human mtDNA haplogroup enrichment via a local Phy-Mer vendor tree."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import ensure_alt_fraction_columns

RANKING_COLUMNS = ["rank", "haplogroup", "score", "defining_snps"]
MAJOR_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "depth",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "phymer_input",
]
REQUIRED_ALL_SITE_COLUMNS = {"position", "ref_base", "alt_base", "depth", "alt_allele_fraction"}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--species", required=True)
    parser.add_argument("--ref-fasta", required=True)
    parser.add_argument("--phymer-root", default="")
    parser.add_argument("--min-depth", type=int, default=100)
    parser.add_argument("--major-vaf", type=float, default=0.90)
    return parser


def load_table(path: str | Path, *, columns: list[str] | None = None) -> pd.DataFrame:
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, sep="\t")
    return pd.DataFrame(columns=columns or [])


def parse_phymer_output(text: str) -> tuple[str, pd.DataFrame]:
    sample_label = "NA"
    rows: list[dict[str, object]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                score = float(parts[1])
            except ValueError:
                if sample_label == "NA":
                    sample_label = line
                continue
            defining_snps = parts[2] if len(parts) > 2 else "NA"
            rows.append(
                {
                    "haplogroup": parts[0],
                    "score": score,
                    "defining_snps": defining_snps,
                }
            )
        elif sample_label == "NA":
            sample_label = line
    ranking = pd.DataFrame(rows)
    if not ranking.empty:
        ranking.insert(0, "rank", range(1, len(ranking) + 1))
    else:
        ranking = pd.DataFrame(columns=RANKING_COLUMNS)
    return sample_label, ranking


def build_consensus_fasta(
    *,
    all_sites: pd.DataFrame,
    ref_fasta: str | Path,
    mt_contig: str,
    out_fasta: str | Path,
    min_depth: int,
    major_vaf: float,
) -> pd.DataFrame:
    all_sites = ensure_alt_fraction_columns(all_sites)
    major = all_sites[
        (all_sites["depth"] >= min_depth) & (all_sites["alt_allele_fraction"] >= major_vaf)
    ].copy()
    major = major.sort_values(["position", "alt_allele_fraction"], ascending=[True, False]).drop_duplicates(
        ["position"]
    )
    major["heteroplasmy_fraction"] = major["alt_allele_fraction"]
    major = major[(major["alt_base"] != ".") & (major["ref_base"] != major["alt_base"])].reset_index(drop=True)

    fasta = pysam.FastaFile(str(ref_fasta))
    seq = list(fasta.fetch(mt_contig).upper())
    fasta.close()

    for row in major.itertuples(index=False):
        seq[int(row.position) - 1] = str(row.alt_base)

    out_fasta = Path(out_fasta)
    with out_fasta.open("w", encoding="utf-8") as handle:
        handle.write(f">{out_fasta.stem}\n")
        joined = "".join(seq)
        for idx in range(0, len(joined), 70):
            handle.write(joined[idx : idx + 70] + "\n")

    if not major.empty:
        major["phymer_input"] = [f"m.{int(r.position)}{r.ref_base}>{r.alt_base}" for r in major.itertuples(index=False)]
        return major[MAJOR_COLUMNS]
    return pd.DataFrame(columns=MAJOR_COLUMNS)


def _write_status_outputs(
    *,
    report_path: Path,
    summary_path: Path,
    ranking_path: Path,
    input_path: Path,
    status_rows: list[dict[str, object]],
    message: str,
    sample_id: str,
    region: str,
) -> dict[str, Path | str]:
    status_df = pd.DataFrame(status_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    status_df.to_csv(summary_path, sep="\t", index=False)
    pd.DataFrame(columns=RANKING_COLUMNS).to_csv(ranking_path, sep="\t", index=False)
    pd.DataFrame(columns=MAJOR_COLUMNS).to_csv(input_path, sep="\t", index=False)
    intro_html = f"<p class='muted'>{message}</p>"
    body_html = "<section><h2>Status</h2>" + df_to_html_table(status_df, max_rows=20) + "</section>"
    render_page(report_path, "Mito Phy-Mer Haplogroup", sample_id, region, intro_html, body_html)
    status = next((str(row["value"]) for row in status_rows if row.get("metric") == "status"), "unavailable")
    return {
        "status": status,
        "summary_path": summary_path,
        "ranking_path": ranking_path,
        "input_path": input_path,
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
    species: str,
    ref_fasta: str | Path,
    phymer_root: str | Path | None,
    min_depth: int = 100,
    major_vaf: float = 0.90,
) -> dict[str, Path]:
    """Run the optional Phy-Mer haplogroup enrichment step."""

    print(
        f"[phymer] starting sample={sample_id} species={species} contig={mt_contig} "
        f"min_depth={min_depth} major_vaf={major_vaf}",
        flush=True,
    )
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    region = f"{mt_contig}:1-{mt_length}"
    report_path = report_dir / "13_mito_phymer_haplogroup.html"
    summary_path = summary_dir / "mito_phymer_haplogroup_summary.tsv"
    ranking_path = summary_dir / "mito_phymer_haplogroup_ranking.tsv"
    input_path = summary_dir / "mito_phymer_major_variant_input.tsv"
    raw_output_path = summary_dir / "mito_phymer_raw_output.txt"
    raw_error_path = summary_dir / "mito_phymer_raw_error.txt"
    fasta_path = summary_dir / "mito_phymer_consensus.fasta"

    if species.lower() != "human":
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "not_applicable"},
                {"metric": "reason_code", "value": "non_human_sample"},
            ],
            message="Phy-Mer haplogroup inference is currently enabled only for human mitochondrial samples.",
            sample_id=sample_id,
            region=region,
        )

    all_sites = ensure_alt_fraction_columns(load_table(summary_dir / "mito_heteroplasmy_all_sites.tsv"))
    if all_sites.empty:
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "not_evaluable"},
                {"metric": "reason_code", "value": "no_all_site_table_available"},
            ],
            message="No mitochondrial all-site table was available to build a consensus-style haplogroup input sequence.",
            sample_id=sample_id,
            region=region,
        )
    if not REQUIRED_ALL_SITE_COLUMNS.issubset(all_sites.columns):
        missing = sorted(REQUIRED_ALL_SITE_COLUMNS.difference(all_sites.columns))
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "unavailable"},
                {"metric": "reason_code", "value": "all_site_table_missing_columns"},
                {"metric": "missing_columns", "value": ",".join(missing)},
            ],
            message="The alternate-allele all-site table is missing required columns for consensus haplogroup reconstruction.",
            sample_id=sample_id,
            region=region,
        )

    phymer_root_path = Path(phymer_root) if phymer_root else None
    phymer_script = phymer_root_path / "Phy-Mer.py" if phymer_root_path else None
    phymer_library = phymer_root_path / "PhyloTree_b16_k12.txt" if phymer_root_path else None
    phymer_defs = phymer_root_path / "resources" / "Build_16_-_rCRS-based_haplogroup_motifs.csv" if phymer_root_path else None
    if not (
        phymer_root_path
        and phymer_script
        and phymer_library
        and phymer_defs
        and phymer_script.exists()
        and phymer_library.exists()
        and phymer_defs.exists()
    ):
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "not_configured"},
                {"metric": "reason_code", "value": "phymer_resources_missing"},
                {"metric": "phymer_root", "value": str(phymer_root_path or "")},
            ],
            message="Phy-Mer resources were not available in the configured local vendor directory.",
            sample_id=sample_id,
            region=region,
        )

    major = build_consensus_fasta(
        all_sites=all_sites,
        ref_fasta=ref_fasta,
        mt_contig=mt_contig,
        out_fasta=fasta_path,
        min_depth=min_depth,
        major_vaf=major_vaf,
    )
    major.to_csv(input_path, sep="\t", index=False)
    if major.empty:
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "not_evaluable"},
                {"metric": "reason_code", "value": "no_major_variants_for_consensus"},
                {"metric": "major_variant_threshold", "value": f"depth>={min_depth};vaf>={major_vaf}"},
            ],
            message="No high-fraction mitochondrial variants passed the configured thresholds for Phy-Mer consensus haplogroup inference.",
            sample_id=sample_id,
            region=region,
        )

    cmd = [
        sys.executable,
        str(phymer_script),
        "--print-ranking",
        f"--def-snp={phymer_defs}",
        str(phymer_library),
        str(fasta_path),
    ]
    print(f"[phymer] sample={sample_id} running command in {phymer_root_path}", flush=True)
    print(
        f"[phymer] consensus major variants={len(major)} min_depth={min_depth} major_vaf={major_vaf}",
        flush=True,
    )
    completed = subprocess.run(cmd, cwd=str(phymer_root_path), capture_output=True, text=True)
    raw_output_path.write_text(completed.stdout, encoding="utf-8")
    raw_error_path.write_text(completed.stderr, encoding="utf-8")
    print(f"[phymer] return_code={completed.returncode}", flush=True)
    if completed.stderr.strip():
        print(f"[phymer] stderr={completed.stderr.strip()[:400]}", flush=True)

    if completed.returncode != 0:
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "unavailable"},
                {"metric": "reason_code", "value": "phymer_run_failed"},
                {"metric": "return_code", "value": int(completed.returncode)},
                {"metric": "stderr_preview", "value": completed.stderr.strip()[:200] or "NA"},
            ],
            message="Phy-Mer was invoked but did not return a successful haplogroup result. See the raw output files in the summary directory for debugging context.",
            sample_id=sample_id,
            region=region,
        )

    sample_label, ranking = parse_phymer_output(completed.stdout)
    ranking.to_csv(ranking_path, sep="\t", index=False)
    best_hg = str(ranking.iloc[0]["haplogroup"]) if not ranking.empty else "NA"
    best_score = float(ranking.iloc[0]["score"]) if not ranking.empty else 0.0
    status_df = pd.DataFrame(
        [
            {"metric": "status", "value": "ok" if not ranking.empty else "unavailable"},
            {"metric": "reason_code", "value": "" if not ranking.empty else "no_phymer_ranking_rows"},
            {"metric": "sample_label", "value": sample_label},
            {"metric": "best_haplogroup", "value": best_hg},
            {"metric": "best_score", "value": round(best_score, 6)},
            {"metric": "major_variant_sites_used", "value": int(len(major))},
            {"metric": "phymer_library", "value": phymer_library.name},
            {"metric": "major_variant_threshold", "value": f"depth>={min_depth};vaf>={major_vaf}"},
        ]
    )
    summary_path.write_text(status_df.to_csv(sep="\t", index=False), encoding="utf-8")

    rank_fig = None
    if not ranking.empty:
        rank_fig = figure_dir / "mito_phymer_haplogroup_scores.png"
        plot_df = ranking.head(5).copy()
        plt.figure(figsize=(8, 4))
        plt.bar(plot_df["haplogroup"], plot_df["score"], color="#2563eb")
        plt.ylabel("Phy-Mer score")
        plt.title(f"{sample_id} Phy-Mer top haplogroup ranking")
        plt.tight_layout()
        plt.savefig(rank_fig, dpi=150)
        plt.close()

    metrics_html = "".join(
        [
            metric_card("Best haplogroup", best_hg),
            metric_card("Best score", round(best_score, 6)),
            metric_card("Major variants used", int(len(major))),
            metric_card("Ranking rows", int(len(ranking))),
        ]
    )
    intro_html = (
        '<p class="muted">This page runs a local vendor copy of Phy-Mer on a consensus-style mitochondrial FASTA reconstructed from high alternate-allele-fraction variants. '
        "The goal is to provide a compact haplogroup interpretation layer for human samples without altering the primary alternate-allele screening or deletion logic of the mito_overview workflow.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Phy-Mer run summary</h2>" + df_to_html_table(status_df, max_rows=20) + "</section>",
        "<section><h2>Consensus major-variant input</h2>" + df_to_html_table(major, max_rows=40) + "</section>",
        "<section><h2>Phy-Mer ranking table</h2>" + df_to_html_table(ranking, max_rows=20) + "</section>",
    ]
    if rank_fig:
        body_parts.insert(
            2,
            "<section><h2>Top haplogroup scores</h2>"
            + figure_html(rank_fig, "Top Phy-Mer haplogroup score ranking")
            + "</section>",
        )
    render_page(report_path, "Mito Phy-Mer Haplogroup", sample_id, region, intro_html, "".join(body_parts))
    return {
        "status": "ok" if not ranking.empty else "unavailable",
        "summary_path": summary_path,
        "ranking_path": ranking_path,
        "input_path": input_path,
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
        species=args.species,
        ref_fasta=args.ref_fasta,
        phymer_root=args.phymer_root,
        min_depth=args.min_depth,
        major_vaf=args.major_vaf,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
