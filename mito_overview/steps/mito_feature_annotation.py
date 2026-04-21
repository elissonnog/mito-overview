"""Human mtDNA feature annotation for mito-overview."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page

DLOOP_INTERVALS = [(1, 576), (16024, 16569)]
ATTR_RE = re.compile(r'(\w+) "([^"]+)"')


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--species", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, default=16569)
    parser.add_argument("--human-mt-gtf", required=True)
    return parser


def parse_attrs(field: str) -> dict[str, str]:
    return dict(ATTR_RE.findall(field))


def load_human_mt_features(gtf_path: str | Path, contig: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    with Path(gtf_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9:
                continue
            seqname, _, feature_type, start, end, _, strand, _, attrs = parts
            if seqname != contig or feature_type not in {"gene", "CDS"}:
                continue
            attr_map = parse_attrs(attrs)
            rows.append(
                {
                    "feature_type": feature_type,
                    "gene_name": attr_map.get("gene_name", attr_map.get("gene_id", "NA")),
                    "gene_biotype": attr_map.get("gene_biotype", "NA"),
                    "start": int(start),
                    "end": int(end),
                    "strand": strand,
                }
            )
    return pd.DataFrame(rows)


def classify_position(pos: int, features_df: pd.DataFrame) -> tuple[str, str]:
    for start, end in DLOOP_INTERVALS:
        if start <= pos <= end:
            return "control_region", "D-loop/control region"
    hits = features_df[(features_df["start"] <= pos) & (features_df["end"] >= pos)]
    if hits.empty:
        return "intergenic", "intergenic"
    cds_hits = hits[hits["feature_type"] == "CDS"]
    if not cds_hits.empty:
        row = cds_hits.iloc[0]
        return str(row["gene_biotype"]), str(row["gene_name"])
    row = hits.iloc[0]
    return str(row["gene_biotype"]), str(row["gene_name"])


def _status_page(
    *,
    report_dir: Path,
    summary_dir: Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    message: str,
) -> dict[str, Path]:
    summary_df = pd.DataFrame([{"metric": "status", "value": message}])
    summary_path = summary_dir / "mito_feature_annotation_summary.tsv"
    summary_df.to_csv(summary_path, sep="\t", index=False)
    intro_html = f'<p class="muted">{message}</p>'
    body_html = "<section><h2>Status</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>"
    report_path = report_dir / "05_mito_feature_annotation.html"
    render_page(
        report_path,
        "Mitochondrial Feature Annotation",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        body_html,
    )
    return {"summary_path": summary_path, "report_path": report_path}


def run_step(
    *,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    species: str,
    build: str,
    mt_contig: str,
    mt_length: int,
    human_mt_gtf: str | Path | None,
) -> dict[str, Path]:
    """Annotate heteroplasmy candidates against human mtDNA features."""

    print(
        f"[feature_annotation] starting sample={sample_id} species={species} "
        f"build={build} contig={mt_contig}"
    )
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    if species.lower() != "human":
        return _status_page(
            report_dir=report_dir,
            summary_dir=summary_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            message="Feature annotation is currently implemented only for human mitochondrial reports.",
        )
    if not human_mt_gtf or not Path(human_mt_gtf).exists():
        return _status_page(
            report_dir=report_dir,
            summary_dir=summary_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            message="Human mtDNA feature annotation requires a configured HUMAN_MT_GTF file.",
        )

    features_df = load_human_mt_features(human_mt_gtf, mt_contig)
    if features_df.empty:
        raise RuntimeError(f"No mitochondrial features found in {human_mt_gtf} for contig {mt_contig}")

    candidates_path = summary_dir / "mito_heteroplasmy_candidates.tsv"
    if candidates_path.exists():
        candidates_df = pd.read_csv(candidates_path, sep="\t")
    else:
        candidates_df = pd.DataFrame(columns=["position", "ref_base", "alt_base", "heteroplasmy_fraction", "depth"])

    feature_catalog = (
        features_df.drop_duplicates(["gene_name", "feature_type", "start", "end"])
        .sort_values(["start", "end", "gene_name"])
        .reset_index(drop=True)
    )
    catalog_path = summary_dir / "mito_feature_catalog.tsv"
    feature_catalog.to_csv(catalog_path, sep="\t", index=False)

    overlap_rows: list[dict[str, object]] = []
    for idx, row in enumerate(candidates_df.itertuples(index=False), start=1):
        if idx % 50 == 0:
            print(f"[feature_annotation] annotated candidate sites={idx}")
        biotype, label = classify_position(int(row.position), features_df)
        overlap_rows.append(
            {
                "position": int(row.position),
                "ref_base": row.ref_base,
                "alt_base": row.alt_base,
                "heteroplasmy_fraction": row.heteroplasmy_fraction,
                "depth": row.depth,
                "feature_class": biotype,
                "feature_label": label,
            }
        )
    overlap_df = pd.DataFrame(overlap_rows)
    overlap_path = summary_dir / "mito_feature_overlap_candidates.tsv"
    overlap_df.to_csv(overlap_path, sep="\t", index=False)

    if not overlap_df.empty:
        summary_feature_df = (
            overlap_df.groupby(["feature_class", "feature_label"], as_index=False)
            .agg(candidate_sites=("position", "count"), mean_heteroplasmy=("heteroplasmy_fraction", "mean"))
            .sort_values(["candidate_sites", "mean_heteroplasmy"], ascending=[False, False])
        )
        summary_feature_df["mean_heteroplasmy"] = summary_feature_df["mean_heteroplasmy"].round(6)
    else:
        summary_feature_df = pd.DataFrame(
            columns=["feature_class", "feature_label", "candidate_sites", "mean_heteroplasmy"]
        )
    summary_path = summary_dir / "mito_feature_annotation_summary.tsv"
    summary_feature_df.to_csv(summary_path, sep="\t", index=False)

    fig_path = None
    if not summary_feature_df.empty:
        top = summary_feature_df.head(15).copy()
        labels = top["feature_label"].astype(str).tolist()
        plt.figure(figsize=(10, 5))
        plt.bar(labels, top["candidate_sites"], color="#0f766e")
        plt.xticks(rotation=90)
        plt.ylabel("Candidate heteroplasmy sites")
        plt.title(f"{sample_id} mitochondrial feature overlap")
        plt.tight_layout()
        fig_path = figure_dir / "mito_feature_annotation.png"
        plt.savefig(fig_path, dpi=150)
        plt.close()

    metrics_html = "".join(
        [
            metric_card("Features cataloged", len(feature_catalog)),
            metric_card("Candidate sites annotated", len(overlap_df)),
            metric_card("Distinct feature labels", overlap_df["feature_label"].nunique() if not overlap_df.empty else 0),
            metric_card("Annotation source", Path(human_mt_gtf).name),
        ]
    )
    intro_html = (
        '<p class="muted">Mitochondrial candidate heteroplasmy sites are mapped to the human mitochondrial gene '
        "catalog and the control-region interval. This provides biological context for whether candidate variation "
        "falls in protein-coding, rRNA, tRNA, or control-region sequence. The annotation source can be used with "
        "standard mitochondrial references that share the canonical human mitochondrial coordinate system.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Feature catalog</h2>" + df_to_html_table(feature_catalog, max_rows=40) + "</section>",
        "<section><h2>Candidate-site overlaps</h2>" + df_to_html_table(overlap_df, max_rows=40) + "</section>",
        "<section><h2>Feature summary</h2>" + df_to_html_table(summary_feature_df, max_rows=25) + "</section>",
    ]
    if fig_path:
        body_parts.insert(
            1,
            "<section><h2>Feature-overlap summary</h2>"
            + figure_html(fig_path, "Candidate heteroplasmy sites by mitochondrial feature")
            + "</section>",
        )

    report_path = report_dir / "05_mito_feature_annotation.html"
    render_page(
        report_path,
        "Mitochondrial Feature Annotation",
        sample_id,
        f"{mt_contig}:1-{mt_length}",
        intro_html,
        "".join(body_parts),
    )
    return {
        "catalog_path": catalog_path,
        "overlap_path": overlap_path,
        "summary_path": summary_path,
        "report_path": report_path,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        summary_dir=args.summary_dir,
        figure_dir=args.figure_dir,
        report_dir=args.report_dir,
        sample_id=args.sample_id,
        species=args.species,
        build=args.build,
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
        human_mt_gtf=args.human_mt_gtf,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
