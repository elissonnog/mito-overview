"""Local mitochondrial variant consequence annotation for mito-overview."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import (
    ensure_alt_fraction_columns,
    validate_candidate_table,
    validate_module_state,
    validate_variant_key_table,
)

SUMMARY_COLUMNS = ["metric", "value"]
VARIANT_KEY_COLUMNS = ["position", "ref_base", "alt_base"]
CANDIDATE_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "depth",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
]
OVERLAP_COLUMNS = ["position", "ref_base", "alt_base", "feature_class", "feature_label"]
ANNOTATION_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "depth",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "feature_label",
    "feature_class",
    "consequence_class",
    "codon_ref",
    "codon_alt",
    "protein_change",
    "clinvar_significance",
    "clinvar_disease",
]
CLASS_SUMMARY_COLUMNS = [
    "consequence_class",
    "candidate_sites",
    "candidate_variants",
    "annotation_rows",
    "mean_alt_allele_fraction",
    "mean_heteroplasmy",
]
CLINVAR_SUMMARY_COLUMNS = [
    "clinvar_significance",
    "candidate_sites",
    "candidate_variants",
    "annotation_rows",
]
MT_CODE = {
    "TTT": "F",
    "TTC": "F",
    "TTA": "L",
    "TTG": "L",
    "TCT": "S",
    "TCC": "S",
    "TCA": "S",
    "TCG": "S",
    "TAT": "Y",
    "TAC": "Y",
    "TAA": "*",
    "TAG": "*",
    "TGT": "C",
    "TGC": "C",
    "TGA": "W",
    "TGG": "W",
    "CTT": "L",
    "CTC": "L",
    "CTA": "L",
    "CTG": "L",
    "CCT": "P",
    "CCC": "P",
    "CCA": "P",
    "CCG": "P",
    "CAT": "H",
    "CAC": "H",
    "CAA": "Q",
    "CAG": "Q",
    "CGT": "R",
    "CGC": "R",
    "CGA": "R",
    "CGG": "R",
    "ATT": "I",
    "ATC": "I",
    "ATA": "M",
    "ATG": "M",
    "ACT": "T",
    "ACC": "T",
    "ACA": "T",
    "ACG": "T",
    "AAT": "N",
    "AAC": "N",
    "AAA": "K",
    "AAG": "K",
    "AGT": "S",
    "AGC": "S",
    "AGA": "*",
    "AGG": "*",
    "GTT": "V",
    "GTC": "V",
    "GTA": "V",
    "GTG": "V",
    "GCT": "A",
    "GCC": "A",
    "GCA": "A",
    "GCG": "A",
    "GAT": "D",
    "GAC": "D",
    "GAA": "E",
    "GAG": "E",
    "GGT": "G",
    "GGC": "G",
    "GGA": "G",
    "GGG": "G",
}
COMPLEMENT = str.maketrans("ACGTN", "TGCAN")
MT_INITIATOR_CODONS = frozenset({"ATT", "ATC", "ATA", "ATG", "GTG"})


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int)
    parser.add_argument("--ref-fasta", required=True)
    parser.add_argument("--np-clinvar-vcf")
    parser.add_argument("--feature-annotation-status")
    parser.add_argument("--feature-annotation-reason-code")
    return parser


def region_label(mt_contig: str, mt_length: int | None) -> str:
    """Return a report-friendly mitochondrial region label."""

    if mt_length and mt_length > 0:
        return f"{mt_contig}:1-{mt_length}"
    return f"{mt_contig}:whole_mito"


def reverse_complement(seq: str) -> str:
    """Return the reverse complement of a DNA sequence."""

    return seq.translate(COMPLEMENT)[::-1]


def translate_codon(codon: str) -> str:
    """Translate a mitochondrial codon with the vertebrate mtDNA code."""

    return MT_CODE.get(codon.upper(), "X")


def load_table(path: str | Path, columns: list[str] | None = None) -> pd.DataFrame:
    """Load a TSV table if present, otherwise return an empty schema."""

    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=columns or [])
    try:
        df = pd.read_csv(path, sep="\t")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns or [])
    if df.empty:
        return pd.DataFrame(columns=list(df.columns) if len(df.columns) else (columns or []))
    return df


def _empty_annotation_df() -> pd.DataFrame:
    return pd.DataFrame(columns=ANNOTATION_COLUMNS)


def _empty_class_summary_df() -> pd.DataFrame:
    return pd.DataFrame(columns=CLASS_SUMMARY_COLUMNS)


def _empty_clinvar_summary_df() -> pd.DataFrame:
    return pd.DataFrame(columns=CLINVAR_SUMMARY_COLUMNS)


def _unique_variant_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return one row per stable position/ref/alt variant key."""

    return frame.drop_duplicates(subset=VARIANT_KEY_COLUMNS)


def _annotation_counts(frame: pd.DataFrame) -> tuple[int, int, int]:
    """Count unique genomic sites, unique variants, and annotation rows."""

    return (
        int(frame["position"].nunique()),
        int(len(_unique_variant_rows(frame))),
        int(len(frame)),
    )


def resolve_feature_annotation_state(
    summary_dir: str | Path,
    *,
    explicit_status: str | None = None,
    explicit_reason_code: str | None = None,
) -> tuple[str, str]:
    """Resolve the upstream feature-annotation state without inferring biology from missing data."""

    if explicit_status is not None:
        return validate_module_state(explicit_status), explicit_reason_code or ""

    summary_dir = Path(summary_dir)
    summary_path = summary_dir / "mito_feature_annotation_summary.tsv"
    feature_summary = load_table(summary_path)
    if {"metric", "value"}.issubset(feature_summary.columns):
        metrics = {
            str(row.metric): str(row.value)
            for row in feature_summary[["metric", "value"]].itertuples(index=False)
        }
        if metrics.get("status"):
            return validate_module_state(metrics["status"]), metrics.get("reason_code", "")

    successful_summary_columns = {
        "feature_class",
        "feature_label",
        "candidate_sites",
        "mean_alt_allele_fraction",
    }
    if successful_summary_columns.issubset(feature_summary.columns):
        return "ok", ""

    return "not_evaluable", "feature_annotation_status_unavailable"


def status_page(
    *,
    summary_dir: Path,
    report_dir: Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int | None,
    status: str,
    reason_code: str,
    message: str,
) -> dict[str, Path | str]:
    """Write stable empty outputs and a status-only report page."""

    annot_path = summary_dir / "mito_variant_consequence_candidates.tsv"
    class_path = summary_dir / "mito_variant_consequence_class_summary.tsv"
    clinvar_path = summary_dir / "mito_variant_consequence_clinvar_summary.tsv"
    summary_path = summary_dir / "mito_variant_consequence_summary.tsv"
    report_path = report_dir / "10_mito_variant_consequence.html"

    status = validate_module_state(status)
    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": status},
            {"metric": "reason_code", "value": reason_code},
            {"metric": "message", "value": message},
        ],
        columns=SUMMARY_COLUMNS,
    )
    _empty_annotation_df().to_csv(annot_path, sep="\t", index=False)
    _empty_class_summary_df().to_csv(class_path, sep="\t", index=False)
    _empty_clinvar_summary_df().to_csv(clinvar_path, sep="\t", index=False)
    summary_df.to_csv(summary_path, sep="\t", index=False)

    intro_html = f'<p class="muted">{message}</p>'
    body_html = "<section><h2>Status</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>"
    render_page(
        report_path,
        "Mito Variant Consequence",
        sample_id,
        region_label(mt_contig, mt_length),
        intro_html,
        body_html,
    )
    return {
        "status": status,
        "annot_path": annot_path,
        "class_path": class_path,
        "clinvar_path": clinvar_path,
        "summary_path": summary_path,
        "report_path": report_path,
    }


def load_clinvar_map(vcf_path: str | Path | None, contig: str) -> dict[tuple[int, str, str], dict[str, str]]:
    """Load exact position/ref/alt ClinVar mappings for the mtDNA contig."""

    result: dict[tuple[int, str, str], dict[str, str]] = {}
    if not vcf_path:
        print("[variant_consequence] no ClinVar VCF configured; ClinVar columns will be NA", flush=True)
        return result

    path = Path(vcf_path)
    if not path.exists():
        print(f"[variant_consequence] ClinVar VCF missing path={path}; ClinVar columns will be NA", flush=True)
        return result

    variant_file = pysam.VariantFile(str(path))
    try:
        try:
            iterator = variant_file.fetch(contig)
        except (ValueError, OSError):
            try:
                iterator = variant_file.fetch()
            except (ValueError, OSError):
                iterator = variant_file
        for record in iterator:
            if getattr(record, "contig", None) != contig:
                continue
            clnsig = record.info.get("CLNSIG")
            clndn = record.info.get("CLNDN")
            clnsig_text = "|".join(map(str, clnsig)) if clnsig else "NA"
            clndn_text = "|".join(map(str, clndn)) if clndn else "NA"
            for alt in record.alts or []:
                result[(int(record.pos), str(record.ref).upper(), str(alt).upper())] = {
                    "clinvar_significance": clnsig_text,
                    "clinvar_disease": clndn_text,
                }
    finally:
        variant_file.close()

    print(
        f"[variant_consequence] loaded ClinVar exact matches={len(result)} source={path.name}",
        flush=True,
    )
    return result


def annotate_protein_change(
    pos: int,
    alt_base: str,
    gene_name: str,
    cds_rows: pd.DataFrame,
    ref_seq: str,
) -> tuple[str, str, str, str]:
    """Infer a local amino-acid consequence for a protein-coding mtDNA site."""

    gene_hits = cds_rows[
        cds_rows["gene_name"].astype(str) == str(gene_name)
    ].sort_values(["start", "end"])
    # The local consequence model is deliberately limited to one contiguous,
    # phase-zero mitochondrial CDS. Never guess across split/phase-shifted CDSs.
    if len(gene_hits) != 1:
        return "protein_coding_unspecified", "NA", "NA", "NA"

    row = gene_hits.iloc[0]
    phase = str(row.get("phase", "0"))
    if phase not in {"0", "0.0"}:
        return "protein_coding_unspecified", "NA", "NA", "NA"
    start = int(row["start"])
    end = int(row["end"])
    strand = str(row.get("strand", "+"))
    if strand == "+":
        cds_offset = pos - start
        gene_seq = ref_seq[start - 1 : end]
        alt_gene_base = alt_base
    else:
        cds_offset = end - pos
        gene_seq = reverse_complement(ref_seq[start - 1 : end])
        alt_gene_base = reverse_complement(alt_base)

    if len(alt_gene_base) != 1 or cds_offset < 0 or cds_offset >= len(gene_seq):
        return "protein_coding_unspecified", "NA", "NA", "NA"

    codon_index = cds_offset // 3
    codon_offset = cds_offset % 3
    codon_start = codon_index * 3
    codon_ref = gene_seq[codon_start : codon_start + 3]
    if len(codon_ref) != 3:
        return "protein_coding_unspecified", "NA", "NA", "NA"

    codon_alt = list(codon_ref)
    codon_alt[codon_offset] = alt_gene_base
    codon_alt_text = "".join(codon_alt)
    aa_position = codon_index + 1

    if aa_position == 1 and codon_ref in MT_INITIATOR_CODONS:
        if codon_alt_text not in MT_INITIATOR_CODONS:
            return "start_lost", codon_ref, codon_alt_text, "p.M1?"
        aa_ref = "M"
        aa_alt = "M"
    else:
        aa_ref = translate_codon(codon_ref)
        aa_alt = translate_codon(codon_alt_text)
    protein_change = f"p.{aa_ref}{aa_position}{aa_alt}"

    if aa_ref == aa_alt:
        consequence = "synonymous_variant"
    elif aa_ref != "*" and aa_alt == "*":
        consequence = "stop_gained"
    elif aa_ref == "*" and aa_alt != "*":
        consequence = "stop_lost"
    else:
        consequence = "missense_variant"
    return consequence, codon_ref, codon_alt_text, protein_change


def run_step(
    *,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    ref_fasta: str | Path,
    np_clinvar_vcf: str | Path | None = None,
    mt_length: int | None = None,
    feature_annotation_status: str | None = None,
    feature_annotation_reason_code: str | None = None,
) -> dict[str, Path | str]:
    """Run the public mitochondrial variant consequence step."""

    print(
        f"[variant_consequence] starting sample={sample_id} contig={mt_contig} "
        f"mt_length={mt_length if mt_length else 'auto'}",
        flush=True,
    )
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    candidates_path = summary_dir / "mito_heteroplasmy_candidates.tsv"
    overlap_path = summary_dir / "mito_feature_overlap_candidates.tsv"
    catalog_path = summary_dir / "mito_feature_catalog.tsv"
    annot_path = summary_dir / "mito_variant_consequence_candidates.tsv"
    class_path = summary_dir / "mito_variant_consequence_class_summary.tsv"
    clinvar_path = summary_dir / "mito_variant_consequence_clinvar_summary.tsv"
    summary_path = summary_dir / "mito_variant_consequence_summary.tsv"
    report_path = report_dir / "10_mito_variant_consequence.html"

    candidates_df = ensure_alt_fraction_columns(load_table(candidates_path, CANDIDATE_COLUMNS))
    overlap_df = load_table(overlap_path, OVERLAP_COLUMNS)
    feature_catalog = load_table(catalog_path)
    upstream_status, upstream_reason = resolve_feature_annotation_state(
        summary_dir,
        explicit_status=feature_annotation_status,
        explicit_reason_code=feature_annotation_reason_code,
    )
    print(
        f"[variant_consequence] loaded candidates_rows={len(candidates_df)} "
        f"overlap_rows={len(overlap_df)} catalog_rows={len(feature_catalog)} "
        f"candidates_exists={candidates_path.exists()} overlap_exists={overlap_path.exists()} "
        f"catalog_exists={catalog_path.exists()} feature_annotation_status={upstream_status} "
        f"feature_annotation_reason={upstream_reason or 'none'}",
        flush=True,
    )

    if upstream_status != "ok":
        reason_code = upstream_reason or f"feature_annotation_{upstream_status}"
        message = (
            "Mitochondrial variant consequences were not interpreted because upstream feature annotation "
            f"reported status={upstream_status} (reason={reason_code})."
        )
        print(f"[variant_consequence] {message}", flush=True)
        return status_page(
            summary_dir=summary_dir,
            report_dir=report_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            status=upstream_status,
            reason_code=reason_code,
            message=message,
        )

    fasta = pysam.FastaFile(str(ref_fasta))
    try:
        resolved_mt_length = (
            int(mt_length)
            if mt_length and mt_length > 0
            else int(fasta.get_reference_length(mt_contig))
        )
        ref_seq = fasta.fetch(mt_contig, 0, resolved_mt_length).upper()
    finally:
        fasta.close()
    print(
        f"[variant_consequence] loaded reference sequence length={resolved_mt_length} from={Path(ref_fasta).name}",
        flush=True,
    )

    filtered = validate_candidate_table(
        candidates_df,
        table_name="mito_heteroplasmy_candidates.tsv",
        mt_length=resolved_mt_length,
        reference_sequence=ref_seq,
    )
    if filtered.duplicated(subset=VARIANT_KEY_COLUMNS).any():
        raise ValueError("mito_heteroplasmy_candidates.tsv contains duplicate variant keys")
    filtered = filtered.reset_index(drop=True)
    print(f"[variant_consequence] validated candidate rows={len(filtered)}", flush=True)

    if filtered.empty:
        message = "No alternate-allele candidate sites were available for mitochondrial consequence annotation."
        print(f"[variant_consequence] {message}", flush=True)
        return status_page(
            summary_dir=summary_dir,
            report_dir=report_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            status="not_evaluable",
            reason_code="no_candidate_sites_available",
            message=message,
        )

    missing_overlap_cols = sorted(set(OVERLAP_COLUMNS) - set(overlap_df.columns))
    if missing_overlap_cols:
        message = (
            "The upstream feature-overlap table is missing required columns "
            + ",".join(missing_overlap_cols)
            + "; no consequence interpretation was assigned."
        )
        print(f"[variant_consequence] {message}", flush=True)
        return status_page(
            summary_dir=summary_dir,
            report_dir=report_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=resolved_mt_length,
            status="not_evaluable",
            reason_code="feature_overlap_table_missing_columns",
            message=message,
        )

    overlap_lookup = validate_variant_key_table(
        overlap_df[OVERLAP_COLUMNS].copy(),
        table_name="mito_feature_overlap_candidates.tsv",
        mt_length=resolved_mt_length,
        reference_sequence=ref_seq,
    )
    overlap_lookup = overlap_lookup.drop_duplicates(subset=OVERLAP_COLUMNS).reset_index(drop=True)
    invalid_feature_rows = (
        overlap_lookup["feature_class"].isna()
        | overlap_lookup["feature_label"].isna()
        | overlap_lookup["feature_class"].astype(str).str.strip().isin({"", "NA", "nan"})
        | overlap_lookup["feature_label"].astype(str).str.strip().isin({"", "NA", "nan"})
    )
    if invalid_feature_rows.any():
        message = (
            "The upstream feature-overlap table contains candidate rows without explicit feature "
            "annotations; no consequence interpretation was assigned."
        )
        print(f"[variant_consequence] {message}", flush=True)
        return status_page(
            summary_dir=summary_dir,
            report_dir=report_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=resolved_mt_length,
            status="not_evaluable",
            reason_code="feature_overlap_annotations_missing",
            message=message,
        )

    candidate_keys = set(filtered[VARIANT_KEY_COLUMNS].itertuples(index=False, name=None))
    overlap_keys = set(overlap_lookup[VARIANT_KEY_COLUMNS].itertuples(index=False, name=None))
    if candidate_keys != overlap_keys:
        message = (
            "Candidate and feature-overlap variant keys are inconsistent; no consequence "
            "interpretation was assigned."
        )
        print(
            f"[variant_consequence] {message} missing_overlap_keys={len(candidate_keys - overlap_keys)} "
            f"unexpected_overlap_keys={len(overlap_keys - candidate_keys)}",
            flush=True,
        )
        return status_page(
            summary_dir=summary_dir,
            report_dir=report_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=resolved_mt_length,
            status="not_evaluable",
            reason_code="feature_overlap_candidate_key_mismatch",
            message=message,
        )

    overlap_lookup["_overlap_order"] = overlap_lookup.groupby(
        VARIANT_KEY_COLUMNS,
        sort=False,
    ).cumcount()

    merged = filtered.merge(
        overlap_lookup,
        on=VARIANT_KEY_COLUMNS,
        how="inner",
    )
    merged["feature_class"] = merged["feature_class"].astype(str).str.strip()
    merged["feature_label"] = merged["feature_label"].astype(str).str.strip()

    if {"feature_type", "gene_name", "start", "end"}.issubset(feature_catalog.columns):
        cds_rows = feature_catalog[feature_catalog["feature_type"] == "CDS"].copy()
        cds_rows["start"] = pd.to_numeric(cds_rows["start"], errors="coerce")
        cds_rows["end"] = pd.to_numeric(cds_rows["end"], errors="coerce")
        cds_rows = cds_rows.dropna(subset=["gene_name", "start", "end"]).copy()
        cds_rows["start"] = cds_rows["start"].astype(int)
        cds_rows["end"] = cds_rows["end"].astype(int)
    else:
        if not feature_catalog.empty:
            print(
                "[variant_consequence] feature catalog missing CDS columns; protein-coding sites may be unspecified",
                flush=True,
            )
        cds_rows = pd.DataFrame(columns=["gene_name", "start", "end", "strand"])

    clinvar_map = load_clinvar_map(np_clinvar_vcf, mt_contig)
    annot_rows: list[dict[str, object]] = []
    total = len(merged)
    for idx, row in enumerate(merged.itertuples(index=False), start=1):
        feature_class = str(row.feature_class)
        feature_label = str(row.feature_label)
        if feature_class == "protein_coding":
            consequence, codon_ref, codon_alt, protein_change = annotate_protein_change(
                int(row.position),
                str(row.alt_base),
                feature_label,
                cds_rows,
                ref_seq,
            )
        elif feature_class == "Mt_tRNA":
            consequence, codon_ref, codon_alt, protein_change = "tRNA_variant", "NA", "NA", "NA"
        elif feature_class == "Mt_rRNA":
            consequence, codon_ref, codon_alt, protein_change = "rRNA_variant", "NA", "NA", "NA"
        elif feature_class == "control_region":
            consequence, codon_ref, codon_alt, protein_change = "control_region_variant", "NA", "NA", "NA"
        else:
            consequence, codon_ref, codon_alt, protein_change = "intergenic_variant", "NA", "NA", "NA"

        clinvar = clinvar_map.get((int(row.position), str(row.ref_base), str(row.alt_base)), {})
        annot_rows.append(
            {
                "position": int(row.position),
                "ref_base": str(row.ref_base),
                "alt_base": str(row.alt_base),
                "depth": int(row.depth),
                "alt_allele_fraction": round(float(row.alt_allele_fraction), 6),
                "heteroplasmy_fraction": round(float(row.alt_allele_fraction), 6),
                "feature_label": feature_label,
                "feature_class": feature_class,
                "consequence_class": consequence,
                "codon_ref": codon_ref,
                "codon_alt": codon_alt,
                "protein_change": protein_change,
                "clinvar_significance": clinvar.get("clinvar_significance", "NA"),
                "clinvar_disease": clinvar.get("clinvar_disease", "NA"),
            }
        )
        if idx % 50 == 0 or idx == total:
            print(f"[variant_consequence] annotated candidates {idx}/{total}", flush=True)

    annot_df = pd.DataFrame(annot_rows, columns=ANNOTATION_COLUMNS)
    annot_df["_overlap_order"] = (
        pd.to_numeric(merged["_overlap_order"], errors="coerce").fillna(0).astype(int).to_numpy()
    )
    annot_df = annot_df.sort_values(
        ["alt_allele_fraction", "depth", "position", "_overlap_order", "feature_label"],
        ascending=[False, False, True, True, True],
        kind="stable",
    ).drop(columns="_overlap_order").reset_index(drop=True)
    annot_df.to_csv(annot_path, sep="\t", index=False)
    print(f"[variant_consequence] wrote candidate annotations {annot_path}", flush=True)

    if annot_df.empty:
        class_summary = _empty_class_summary_df()
    else:
        class_rows: list[dict[str, object]] = []
        for consequence_class, group in annot_df.groupby("consequence_class", sort=False):
            unique_variants = _unique_variant_rows(group)
            candidate_sites, candidate_variants, annotation_rows = _annotation_counts(group)
            class_rows.append(
                {
                    "consequence_class": str(consequence_class),
                    "candidate_sites": candidate_sites,
                    "candidate_variants": candidate_variants,
                    "annotation_rows": annotation_rows,
                    "mean_alt_allele_fraction": round(
                        float(unique_variants["alt_allele_fraction"].mean()),
                        6,
                    ),
                }
            )
        class_summary = pd.DataFrame(class_rows, columns=CLASS_SUMMARY_COLUMNS[:-1])
        class_summary["mean_heteroplasmy"] = class_summary["mean_alt_allele_fraction"]
        class_summary = class_summary.sort_values(
            [
                "candidate_sites",
                "candidate_variants",
                "mean_alt_allele_fraction",
                "consequence_class",
            ],
            ascending=[False, False, False, True],
        ).reset_index(drop=True)
    class_summary.to_csv(class_path, sep="\t", index=False)

    clinvar_hits = annot_df[annot_df["clinvar_significance"] != "NA"].copy()
    if clinvar_hits.empty:
        clinvar_summary = _empty_clinvar_summary_df()
    else:
        clinvar_rows: list[dict[str, object]] = []
        for clinvar_significance, group in clinvar_hits.groupby("clinvar_significance", sort=False):
            candidate_sites, candidate_variants, annotation_rows = _annotation_counts(group)
            clinvar_rows.append(
                {
                    "clinvar_significance": str(clinvar_significance),
                    "candidate_sites": candidate_sites,
                    "candidate_variants": candidate_variants,
                    "annotation_rows": annotation_rows,
                }
            )
        clinvar_summary = pd.DataFrame(clinvar_rows, columns=CLINVAR_SUMMARY_COLUMNS)
        clinvar_summary = clinvar_summary.sort_values(
            ["candidate_sites", "candidate_variants", "clinvar_significance"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
    clinvar_summary.to_csv(clinvar_path, sep="\t", index=False)

    candidate_sites, candidate_variants, annotation_rows = _annotation_counts(annot_df)
    clinvar_sites, clinvar_variants, clinvar_annotation_rows = _annotation_counts(clinvar_hits)

    def feature_counts(feature_class: str) -> tuple[int, int, int]:
        return _annotation_counts(annot_df[annot_df["feature_class"] == feature_class])

    protein_sites, protein_variants, protein_rows = feature_counts("protein_coding")
    trna_sites, trna_variants, trna_rows = feature_counts("Mt_tRNA")
    rrna_sites, rrna_variants, rrna_rows = feature_counts("Mt_rRNA")
    control_sites, control_variants, control_rows = feature_counts("control_region")

    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "reason_code", "value": ""},
            {"metric": "candidate_sites_annotated", "value": candidate_sites},
            {"metric": "candidate_variants_annotated", "value": candidate_variants},
            {"metric": "annotation_rows", "value": annotation_rows},
            {"metric": "distinct_consequence_classes", "value": int(annot_df["consequence_class"].nunique())},
            {"metric": "sites_with_clinvar_annotation", "value": clinvar_sites},
            {"metric": "variants_with_clinvar_annotation", "value": clinvar_variants},
            {"metric": "clinvar_annotation_rows", "value": clinvar_annotation_rows},
            {"metric": "protein_coding_sites", "value": protein_sites},
            {"metric": "protein_coding_variants", "value": protein_variants},
            {"metric": "protein_coding_annotation_rows", "value": protein_rows},
            {"metric": "tRNA_sites", "value": trna_sites},
            {"metric": "tRNA_variants", "value": trna_variants},
            {"metric": "tRNA_annotation_rows", "value": trna_rows},
            {"metric": "rRNA_sites", "value": rrna_sites},
            {"metric": "rRNA_variants", "value": rrna_variants},
            {"metric": "rRNA_annotation_rows", "value": rrna_rows},
            {"metric": "control_region_sites", "value": control_sites},
            {"metric": "control_region_variants", "value": control_variants},
            {"metric": "control_region_annotation_rows", "value": control_rows},
        ],
        columns=SUMMARY_COLUMNS,
    )
    summary_df.to_csv(summary_path, sep="\t", index=False)

    class_fig = None
    if not class_summary.empty:
        class_fig = figure_dir / "mito_variant_consequence_classes.png"
        plt.figure(figsize=(8, 4))
        plt.bar(class_summary["consequence_class"], class_summary["candidate_sites"], color="#0f766e")
        plt.xticks(rotation=30, ha="right")
        plt.ylabel("Unique genomic sites")
        plt.title(f"{sample_id} mitochondrial consequence classes")
        plt.tight_layout()
        plt.savefig(class_fig, dpi=150)
        plt.close()

    clinvar_fig = None
    if not clinvar_summary.empty:
        clinvar_fig = figure_dir / "mito_variant_consequence_clinvar.png"
        plt.figure(figsize=(8, 4))
        plt.bar(clinvar_summary["clinvar_significance"], clinvar_summary["candidate_sites"], color="#7c3aed")
        plt.xticks(rotation=30, ha="right")
        plt.ylabel("Unique genomic sites")
        plt.title(f"{sample_id} ClinVar-linked mitochondrial candidates")
        plt.tight_layout()
        plt.savefig(clinvar_fig, dpi=150)
        plt.close()

    clinvar_note = (
        "ClinVar annotations are shown only when an exact local position/ref/alt match is present in the configured "
        "mitochondrial ClinVar callset."
        if np_clinvar_vcf and Path(np_clinvar_vcf).exists()
        else "No ClinVar VCF was configured for this run, so ClinVar columns are reported as NA."
    )
    metrics_html = "".join(
        [
            metric_card("Annotated genomic sites", candidate_sites),
            metric_card("Annotated variants", candidate_variants),
            metric_card("Annotation rows", annotation_rows),
            metric_card("Consequence classes", int(annot_df["consequence_class"].nunique())),
            metric_card("ClinVar-linked variants", clinvar_variants),
            metric_card("Protein-coding variants", protein_variants),
        ]
    )
    intro_html = (
        '<p class="muted">This page assigns a local biological consequence class to mitochondrial alternate-allele '
        "candidate sites. Protein-coding sites are annotated against mitochondrial CDS intervals and the "
        "vertebrate mitochondrial genetic code, while tRNA, rRNA, control-region, and intergenic sites are "
        "classified by feature context. The annotation table retains one row per variant-feature consequence; "
        "site counts deduplicate genomic positions, variant counts deduplicate position/ref/alt keys, and row "
        f"counts retain overlapping annotations. {clinvar_note}</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )

    body_parts = [
        "<section><h2>Consequence summary</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>",
        "<section><h2>Consequence-class table</h2>" + df_to_html_table(class_summary, max_rows=20) + "</section>",
        "<section><h2>Candidate-site annotations</h2>" + df_to_html_table(annot_df, max_rows=40) + "</section>",
    ]
    if class_fig:
        body_parts.insert(
            1,
            "<section><h2>Consequence classes</h2>"
            + figure_html(class_fig, "Distribution of local mitochondrial consequence classes")
            + "</section>",
        )
    if clinvar_fig:
        body_parts.insert(
            3,
            "<section><h2>ClinVar-linked candidates</h2>"
            + figure_html(clinvar_fig, "ClinVar significance among exact-match candidate sites")
            + "</section>",
        )
        body_parts.append(
            "<section><h2>ClinVar summary table</h2>" + df_to_html_table(clinvar_summary, max_rows=20) + "</section>"
        )

    render_page(
        report_path,
        "Mito Variant Consequence",
        sample_id,
        region_label(mt_contig, resolved_mt_length),
        intro_html,
        "".join(body_parts),
    )
    print(f"[variant_consequence] wrote summary table {summary_path}", flush=True)
    return {
        "status": "ok",
        "annot_path": annot_path,
        "class_path": class_path,
        "clinvar_path": clinvar_path,
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
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
        ref_fasta=args.ref_fasta,
        np_clinvar_vcf=args.np_clinvar_vcf,
        feature_annotation_status=args.feature_annotation_status,
        feature_annotation_reason_code=args.feature_annotation_reason_code,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
