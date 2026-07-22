"""Human mtDNA feature annotation for mito-overview."""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.paths import annotation_resource_path
from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import (
    ensure_alt_fraction_columns,
    load_metric_module_state,
    validate_module_state,
)

DLOOP_INTERVALS = ((1, 576), (16024, 16569))
CONTROL_REGION_MODES = frozenset({"auto", "disabled", "synthetic_fixture_override"})
ATTR_RE = re.compile(r'(\w+) "([^"]+)"')
OVERLAP_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "depth",
    "feature_class",
    "feature_label",
]


@dataclass(frozen=True)
class ControlRegionAnnotationDecision:
    """Reference-compatibility decision for canonical human control-region coordinates."""

    status: str
    reason_code: str
    method: str
    mode: str
    configured_sequence_sha256: str = ""
    canonical_sequence_sha256: str = ""
    exact_sequence_match: bool | None = None
    configured_sequence_length: int | None = None
    canonical_sequence_length: int | None = None
    intervals: tuple[tuple[int, int], ...] = ()

    def metadata(self) -> dict[str, str]:
        exact_match = (
            "NA" if self.exact_sequence_match is None else str(int(self.exact_sequence_match))
        )
        return {
            "control_region_annotation_status": self.status,
            "control_region_annotation_reason_code": self.reason_code,
            "control_region_annotation_method": self.method,
            "control_region_annotation_mode": self.mode,
            "control_region_reference_accession": "NC_012920.1",
            "control_region_configured_sequence_sha256": self.configured_sequence_sha256,
            "control_region_canonical_sequence_sha256": self.canonical_sequence_sha256,
            "control_region_exact_sequence_match": exact_match,
            "control_region_configured_sequence_length": (
                ""
                if self.configured_sequence_length is None
                else str(self.configured_sequence_length)
            ),
            "control_region_canonical_sequence_length": (
                ""
                if self.canonical_sequence_length is None
                else str(self.canonical_sequence_length)
            ),
            "control_region_intervals_applied": ";".join(
                f"{start}-{end}" for start, end in self.intervals
            ),
        }


def _sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def _load_single_record_fasta(path: str | Path) -> str:
    records: list[str] = []
    sequence_parts: list[str] = []
    for raw_line in Path(path).read_text(encoding="ascii").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if sequence_parts:
                records.append("".join(sequence_parts).upper())
                sequence_parts = []
            continue
        sequence_parts.append(line)
    if sequence_parts:
        records.append("".join(sequence_parts).upper())
    if len(records) != 1 or not records[0]:
        raise ValueError(f"Expected one nonempty FASTA record in {path}")
    return records[0]


def _load_configured_mt_sequence(ref_fasta: str | Path, mt_contig: str) -> str:
    with pysam.FastaFile(str(ref_fasta)) as reference:
        if mt_contig not in reference.references:
            raise ValueError(f"Reference FASTA does not define mitochondrial contig {mt_contig}")
        sequence = reference.fetch(mt_contig).upper()
    if not sequence:
        raise ValueError(f"Reference FASTA mitochondrial contig {mt_contig} is empty")
    return sequence


def resolve_control_region_annotation(
    *,
    ref_fasta: str | Path,
    mt_contig: str,
    mode: str = "auto",
) -> ControlRegionAnnotationDecision:
    """Gate rCRS control-region coordinates using full-sequence identity only."""

    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in CONTROL_REGION_MODES:
        allowed = ", ".join(sorted(CONTROL_REGION_MODES))
        raise ValueError(
            f"Unsupported CONTROL_REGION_ANNOTATION_MODE={mode!r}; expected one of {allowed}"
        )
    if normalized_mode == "disabled":
        return ControlRegionAnnotationDecision(
            status="not_configured",
            reason_code="control_region_annotation_disabled",
            method="disabled_by_configuration",
            mode=normalized_mode,
        )

    try:
        canonical_sequence = _load_single_record_fasta(
            annotation_resource_path("NC_012920.1.fa")
        )
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return ControlRegionAnnotationDecision(
            status="not_configured",
            reason_code="canonical_reference_resource_unavailable",
            method="exact_full_sequence_identity",
            mode=normalized_mode,
        )

    canonical_sha256 = _sequence_sha256(canonical_sequence)
    try:
        configured_sequence = _load_configured_mt_sequence(ref_fasta, mt_contig)
    except (OSError, ValueError) as error:
        print(f"[feature_annotation] configured mtDNA sequence unavailable: {error}", flush=True)
        return ControlRegionAnnotationDecision(
            status="not_configured",
            reason_code="configured_mt_sequence_unavailable",
            method="exact_full_sequence_identity",
            mode=normalized_mode,
            canonical_sequence_sha256=canonical_sha256,
            canonical_sequence_length=len(canonical_sequence),
        )

    configured_sha256 = _sequence_sha256(configured_sequence)
    exact_match = configured_sequence == canonical_sequence
    common = {
        "mode": normalized_mode,
        "configured_sequence_sha256": configured_sha256,
        "canonical_sequence_sha256": canonical_sha256,
        "exact_sequence_match": exact_match,
        "configured_sequence_length": len(configured_sequence),
        "canonical_sequence_length": len(canonical_sequence),
    }
    if normalized_mode == "synthetic_fixture_override":
        return ControlRegionAnnotationDecision(
            status="ok",
            reason_code="synthetic_fixture_override",
            method="explicit_synthetic_fixture_override",
            intervals=DLOOP_INTERVALS,
            **common,
        )
    if exact_match:
        return ControlRegionAnnotationDecision(
            status="ok",
            reason_code="reference_sequence_exact_match",
            method="exact_full_sequence_identity",
            intervals=DLOOP_INTERVALS,
            **common,
        )
    return ControlRegionAnnotationDecision(
        status="not_evaluable",
        reason_code="reference_sequence_not_nc_012920_1",
        method="exact_full_sequence_identity",
        **common,
    )


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
    parser.add_argument("--ref-fasta", required=True)
    parser.add_argument("--human-mt-gtf", required=True)
    parser.add_argument(
        "--control-region-annotation-mode",
        choices=sorted(CONTROL_REGION_MODES),
        default="auto",
    )
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
            seqname, _, feature_type, start, end, _, strand, phase, attrs = parts
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
                    "phase": phase,
                }
            )
    return pd.DataFrame(rows)


def classify_position(
    pos: int,
    features_df: pd.DataFrame,
    *,
    control_region_intervals: tuple[tuple[int, int], ...] = (),
) -> list[tuple[str, str]]:
    """Return every feature at a position in deterministic genomic order."""

    for start, end in control_region_intervals:
        if start <= pos <= end:
            return [("control_region", "D-loop/control region")]
    hits = features_df[(features_df["start"] <= pos) & (features_df["end"] >= pos)]
    if hits.empty:
        return [("intergenic", "intergenic")]
    selected = hits.sort_values(
        ["start", "end", "gene_name", "gene_biotype", "feature_type"],
        kind="stable",
    )

    annotations: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in selected.itertuples(index=False):
        annotation = (str(row.gene_biotype), str(row.gene_name))
        if annotation not in seen:
            annotations.append(annotation)
            seen.add(annotation)
    return annotations


def _status_page(
    *,
    report_dir: Path,
    summary_dir: Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    status: str,
    reason_code: str,
    message: str,
    control_region_decision: ControlRegionAnnotationDecision | None = None,
) -> dict[str, Path | str]:
    status = validate_module_state(status)
    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": status},
            {"metric": "reason_code", "value": reason_code},
            {"metric": "message", "value": message},
        ]
    )
    if control_region_decision is not None:
        summary_df = pd.concat(
            [
                summary_df,
                pd.DataFrame(
                    [
                        {"metric": metric, "value": value}
                        for metric, value in control_region_decision.metadata().items()
                    ]
                ),
            ],
            ignore_index=True,
        )
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
    outputs: dict[str, Path | str] = {
        "status": status,
        "summary_path": summary_path,
        "report_path": report_path,
    }
    if control_region_decision is not None:
        outputs.update(
            {
                "control_region_annotation_status": control_region_decision.status,
                "control_region_annotation_reason_code": control_region_decision.reason_code,
            }
        )
    return outputs


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
    ref_fasta: str | Path,
    human_mt_gtf: str | Path | None,
    control_region_annotation_mode: str = "auto",
) -> dict[str, Path | str]:
    """Annotate alternate-allele candidate sites against human mtDNA features."""

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
            status="not_applicable",
            reason_code="non_human_sample",
            message="Feature annotation is currently implemented only for human mitochondrial reports.",
        )
    control_region_decision = resolve_control_region_annotation(
        ref_fasta=ref_fasta,
        mt_contig=mt_contig,
        mode=control_region_annotation_mode,
    )
    print(
        "[feature_annotation] control-region "
        f"status={control_region_decision.status} "
        f"reason={control_region_decision.reason_code} "
        f"mode={control_region_decision.mode}",
        flush=True,
    )
    if not human_mt_gtf or not Path(human_mt_gtf).exists():
        return _status_page(
            report_dir=report_dir,
            summary_dir=summary_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            status="not_configured",
            reason_code="human_mt_gtf_not_configured",
            message="Human mtDNA feature annotation requires a configured HUMAN_MT_GTF file.",
            control_region_decision=control_region_decision,
        )

    features_df = load_human_mt_features(human_mt_gtf, mt_contig)
    if features_df.empty:
        raise RuntimeError(f"No mitochondrial features found in {human_mt_gtf} for contig {mt_contig}")

    feature_catalog = (
        features_df.drop_duplicates(["gene_name", "feature_type", "start", "end"])
        .sort_values(["start", "end", "gene_name"])
        .reset_index(drop=True)
    )
    control_region_metadata = control_region_decision.metadata()
    for column, value in control_region_metadata.items():
        feature_catalog[column] = value
    catalog_path = summary_dir / "mito_feature_catalog.tsv"
    feature_catalog.to_csv(catalog_path, sep="\t", index=False)
    overlap_path = summary_dir / "mito_feature_overlap_candidates.tsv"

    heteroplasmy_status, heteroplasmy_reason = load_metric_module_state(
        summary_dir / "mito_heteroplasmy_summary.tsv",
        module_name="heteroplasmy",
    )
    if heteroplasmy_status != "ok":
        pd.DataFrame(columns=OVERLAP_COLUMNS).to_csv(overlap_path, sep="\t", index=False)
        outputs = _status_page(
            report_dir=report_dir,
            summary_dir=summary_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            status=heteroplasmy_status,
            reason_code=heteroplasmy_reason,
            message=(
                "Feature annotation could not be evaluated because upstream alternate-allele "
                f"counting reported status={heteroplasmy_status} "
                f"(reason={heteroplasmy_reason})."
            ),
            control_region_decision=control_region_decision,
        )
        return {**outputs, "catalog_path": catalog_path, "overlap_path": overlap_path}

    candidates_path = summary_dir / "mito_heteroplasmy_candidates.tsv"
    if not candidates_path.is_file():
        pd.DataFrame(columns=OVERLAP_COLUMNS).to_csv(overlap_path, sep="\t", index=False)
        outputs = _status_page(
            report_dir=report_dir,
            summary_dir=summary_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            status="not_evaluable",
            reason_code="heteroplasmy_candidates_missing",
            message="Feature annotation could not be evaluated because the candidate-site table is missing.",
            control_region_decision=control_region_decision,
        )
        return {**outputs, "catalog_path": catalog_path, "overlap_path": overlap_path}
    try:
        candidates_df = ensure_alt_fraction_columns(pd.read_csv(candidates_path, sep="\t"))
        required = {"position", "ref_base", "alt_base", "alt_allele_fraction", "depth"}
        if not required.issubset(candidates_df.columns):
            raise ValueError("candidate table lacks required columns")
    except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        print(f"[feature_annotation] candidate table is unusable: {error}", flush=True)
        pd.DataFrame(columns=OVERLAP_COLUMNS).to_csv(overlap_path, sep="\t", index=False)
        outputs = _status_page(
            report_dir=report_dir,
            summary_dir=summary_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            status="not_evaluable",
            reason_code="heteroplasmy_candidates_unusable",
            message="Feature annotation could not be evaluated because the candidate-site table is unusable.",
            control_region_decision=control_region_decision,
        )
        return {**outputs, "catalog_path": catalog_path, "overlap_path": overlap_path}

    overlap_rows: list[dict[str, object]] = []
    for idx, row in enumerate(candidates_df.itertuples(index=False), start=1):
        if idx % 50 == 0:
            print(f"[feature_annotation] annotated candidate sites={idx}")
        for biotype, label in classify_position(
            int(row.position),
            features_df,
            control_region_intervals=control_region_decision.intervals,
        ):
            overlap_rows.append(
                {
                    "position": int(row.position),
                    "ref_base": row.ref_base,
                    "alt_base": row.alt_base,
                    "alt_allele_fraction": row.alt_allele_fraction,
                    "heteroplasmy_fraction": row.alt_allele_fraction,
                    "depth": row.depth,
                    "feature_class": biotype,
                    "feature_label": label,
                }
            )
    overlap_df = pd.DataFrame(
        overlap_rows,
        columns=OVERLAP_COLUMNS,
    )
    overlap_df.to_csv(overlap_path, sep="\t", index=False)

    if not overlap_df.empty:
        summary_feature_df = (
            overlap_df.groupby(["feature_class", "feature_label"], as_index=False)
            .agg(
                candidate_sites=("position", "count"),
                mean_alt_allele_fraction=("alt_allele_fraction", "mean"),
            )
            .sort_values(["candidate_sites", "mean_alt_allele_fraction"], ascending=[False, False])
        )
        summary_feature_df["mean_alt_allele_fraction"] = summary_feature_df[
            "mean_alt_allele_fraction"
        ].round(6)
        summary_feature_df["mean_heteroplasmy"] = summary_feature_df["mean_alt_allele_fraction"]
    else:
        summary_feature_df = pd.DataFrame(
            columns=[
                "feature_class",
                "feature_label",
                "candidate_sites",
                "mean_alt_allele_fraction",
                "mean_heteroplasmy",
            ]
        )
    for column, value in control_region_metadata.items():
        summary_feature_df[column] = value
    summary_path = summary_dir / "mito_feature_annotation_summary.tsv"
    summary_feature_df.to_csv(summary_path, sep="\t", index=False)

    fig_path = None
    if not summary_feature_df.empty:
        top = summary_feature_df.head(15).copy()
        labels = top["feature_label"].astype(str).tolist()
        plt.figure(figsize=(10, 5))
        plt.bar(labels, top["candidate_sites"], color="#0f766e")
        plt.xticks(rotation=90)
        plt.ylabel("Candidate sites")
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
            metric_card("Control-region annotation", control_region_decision.status),
        ]
    )
    control_region_status_df = pd.DataFrame(
        [
            {"metric": metric, "value": value}
            for metric, value in control_region_metadata.items()
        ]
    )
    intro_html = (
        '<p class="muted">Mitochondrial alternate-allele candidate sites are mapped to the human mitochondrial gene '
        "catalog. Canonical rCRS control-region intervals are added only when the configured mitochondrial sequence "
        "matches bundled NC_012920.1 exactly, or when a recorded synthetic-fixture override is used. This provides "
        "biological context for whether observed variation "
        "falls in protein-coding, rRNA, tRNA, or control-region sequence. The annotation source can be used with "
        "references whose gene-annotation coordinates match the configured sequence.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Control-region coordinate applicability</h2>"
        + df_to_html_table(control_region_status_df, max_rows=20)
        + "</section>",
        "<section><h2>Feature catalog</h2>" + df_to_html_table(feature_catalog, max_rows=40) + "</section>",
        "<section><h2>Candidate-site overlaps</h2>" + df_to_html_table(overlap_df, max_rows=40) + "</section>",
        "<section><h2>Feature summary</h2>" + df_to_html_table(summary_feature_df, max_rows=25) + "</section>",
    ]
    if fig_path:
        body_parts.insert(
            1,
            "<section><h2>Feature-overlap summary</h2>"
            + figure_html(fig_path, "Alternate-allele candidate sites by mitochondrial feature")
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
        "status": "ok",
        "control_region_annotation_status": control_region_decision.status,
        "control_region_annotation_reason_code": control_region_decision.reason_code,
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
        ref_fasta=args.ref_fasta,
        human_mt_gtf=args.human_mt_gtf,
        control_region_annotation_mode=args.control_region_annotation_mode,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
