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
from mito_overview.table_contracts import ensure_alt_fraction_columns, validate_module_state

SUMMARY_COLUMNS = ["metric", "value"]
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
    "mean_alt_allele_fraction",
    "mean_heteroplasmy",
]
CLINVAR_SUMMARY_COLUMNS = ["clinvar_significance", "candidate_sites"]
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

    gene_hits = cds_rows[cds_rows["gene_name"].astype(str) == str(gene_name)].sort_values(["start", "end"]).head(1)
    if gene_hits.empty:
        return "protein_coding_unspecified", "NA", "NA", "NA"

    row = gene_hits.iloc[0]
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
    aa_ref = translate_codon(codon_ref)
    aa_alt = translate_codon(codon_alt_text)
    aa_position = codon_index + 1
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
) -> dict[str, Path]:
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
    print(
        f"[variant_consequence] loaded candidates_rows={len(candidates_df)} "
        f"overlap_rows={len(overlap_df)} catalog_rows={len(feature_catalog)} "
        f"candidates_exists={candidates_path.exists()} overlap_exists={overlap_path.exists()} "
        f"catalog_exists={catalog_path.exists()}",
        flush=True,
    )

    required_candidate_cols = {"position", "ref_base", "alt_base", "depth", "alt_allele_fraction"}
    missing_candidate_cols = sorted(required_candidate_cols - set(candidates_df.columns))
    if missing_candidate_cols:
        message = (
            "The alternate-allele candidate table is missing required columns "
            + ",".join(missing_candidate_cols)
            + "; stable empty outputs were written."
        )
        print(f"[variant_consequence] {message}", flush=True)
        return status_page(
            summary_dir=summary_dir,
            report_dir=report_dir,
            sample_id=sample_id,
            mt_contig=mt_contig,
            mt_length=mt_length,
            status="failed",
            reason_code="candidate_table_missing_columns",
            message=message,
        )

    filtered = candidates_df.copy()
    filtered["position"] = pd.to_numeric(filtered["position"], errors="coerce")
    filtered["depth"] = pd.to_numeric(filtered["depth"], errors="coerce")
    filtered["alt_allele_fraction"] = pd.to_numeric(filtered["alt_allele_fraction"], errors="coerce")
    filtered["ref_base"] = filtered["ref_base"].astype(str).str.upper()
    filtered["alt_base"] = filtered["alt_base"].astype(str).str.upper()
    filtered = filtered.dropna(subset=["position", "depth", "alt_allele_fraction"]).copy()
    filtered = filtered[filtered["ref_base"].isin(["A", "C", "G", "T"])]
    filtered = filtered[filtered["alt_base"].isin(["A", "C", "G", "T"])]
    filtered["position"] = filtered["position"].astype(int)
    filtered["depth"] = filtered["depth"].astype(int)
    filtered["alt_allele_fraction"] = filtered["alt_allele_fraction"].astype(float).round(6)
    filtered["heteroplasmy_fraction"] = filtered["alt_allele_fraction"]
    filtered = filtered.drop_duplicates(subset=["position", "ref_base", "alt_base"]).reset_index(drop=True)
    print(f"[variant_consequence] retained candidate rows={len(filtered)} after filtering", flush=True)

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

    fasta = pysam.FastaFile(str(ref_fasta))
    try:
        resolved_mt_length = int(mt_length) if mt_length and mt_length > 0 else int(fasta.get_reference_length(mt_contig))
        ref_seq = fasta.fetch(mt_contig, 0, resolved_mt_length).upper()
    finally:
        fasta.close()
    print(
        f"[variant_consequence] loaded reference sequence length={resolved_mt_length} from={Path(ref_fasta).name}",
        flush=True,
    )

    missing_overlap_cols = sorted(set(OVERLAP_COLUMNS) - set(overlap_df.columns))
    if missing_overlap_cols:
        print(
            "[variant_consequence] feature-overlap table missing columns="
            + ",".join(missing_overlap_cols)
            + "; defaulting missing feature labels to intergenic",
            flush=True,
        )
        overlap_lookup = pd.DataFrame(columns=OVERLAP_COLUMNS)
    else:
        overlap_lookup = overlap_df[OVERLAP_COLUMNS].copy()
        overlap_lookup["position"] = pd.to_numeric(overlap_lookup["position"], errors="coerce")
        overlap_lookup["ref_base"] = overlap_lookup["ref_base"].astype(str).str.upper()
        overlap_lookup["alt_base"] = overlap_lookup["alt_base"].astype(str).str.upper()
        overlap_lookup = overlap_lookup.dropna(subset=["position"]).copy()
        overlap_lookup["position"] = overlap_lookup["position"].astype(int)
        overlap_lookup = overlap_lookup.drop_duplicates(subset=["position", "ref_base", "alt_base"]).reset_index(drop=True)

    merged = filtered.merge(
        overlap_lookup,
        on=["position", "ref_base", "alt_base"],
        how="left",
    )
    merged["feature_class"] = (
        merged["feature_class"]
        .fillna("intergenic")
        .astype(str)
        .str.strip()
        .replace({"": "intergenic", "NA": "intergenic", "nan": "intergenic"})
    )
    merged["feature_label"] = (
        merged["feature_label"]
        .fillna("intergenic")
        .astype(str)
        .str.strip()
        .replace({"": "intergenic", "NA": "intergenic", "nan": "intergenic"})
    )

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
    annot_df = annot_df.sort_values(
        ["alt_allele_fraction", "depth", "position"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    annot_df.to_csv(annot_path, sep="\t", index=False)
    print(f"[variant_consequence] wrote candidate annotations {annot_path}", flush=True)

    if annot_df.empty:
        class_summary = _empty_class_summary_df()
    else:
        class_summary = (
            annot_df.groupby("consequence_class", as_index=False)
            .agg(
                candidate_sites=("position", "count"),
                mean_alt_allele_fraction=("alt_allele_fraction", "mean"),
            )
            .sort_values(["candidate_sites", "mean_alt_allele_fraction"], ascending=[False, False])
            .reset_index(drop=True)
        )
        class_summary["mean_alt_allele_fraction"] = class_summary[
            "mean_alt_allele_fraction"
        ].round(6)
        class_summary["mean_heteroplasmy"] = class_summary["mean_alt_allele_fraction"]
    class_summary.to_csv(class_path, sep="\t", index=False)

    clinvar_hits = annot_df[annot_df["clinvar_significance"] != "NA"].copy()
    if clinvar_hits.empty:
        clinvar_summary = _empty_clinvar_summary_df()
    else:
        clinvar_summary = (
            clinvar_hits.groupby("clinvar_significance", as_index=False)
            .agg(candidate_sites=("position", "count"))
            .sort_values(["candidate_sites", "clinvar_significance"], ascending=[False, True])
            .reset_index(drop=True)
        )
    clinvar_summary.to_csv(clinvar_path, sep="\t", index=False)

    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "reason_code", "value": ""},
            {"metric": "candidate_sites_annotated", "value": int(len(annot_df))},
            {"metric": "distinct_consequence_classes", "value": int(annot_df["consequence_class"].nunique())},
            {"metric": "sites_with_clinvar_annotation", "value": int((annot_df["clinvar_significance"] != "NA").sum())},
            {"metric": "protein_coding_sites", "value": int((annot_df["feature_class"] == "protein_coding").sum())},
            {"metric": "tRNA_sites", "value": int((annot_df["feature_class"] == "Mt_tRNA").sum())},
            {"metric": "rRNA_sites", "value": int((annot_df["feature_class"] == "Mt_rRNA").sum())},
            {"metric": "control_region_sites", "value": int((annot_df["feature_class"] == "control_region").sum())},
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
        plt.ylabel("Candidate sites")
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
        plt.ylabel("Candidate sites")
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
            metric_card("Annotated candidate sites", int(len(annot_df))),
            metric_card("Consequence classes", int(annot_df["consequence_class"].nunique())),
            metric_card("ClinVar-linked sites", int((annot_df["clinvar_significance"] != "NA").sum())),
            metric_card("Protein-coding candidates", int((annot_df["feature_class"] == "protein_coding").sum())),
        ]
    )
    intro_html = (
        '<p class="muted">This page assigns a local biological consequence class to mitochondrial alternate-allele '
        "candidate sites. Protein-coding sites are annotated against mitochondrial CDS intervals and the "
        "vertebrate mitochondrial genetic code, while tRNA, rRNA, control-region, and intergenic sites are "
        f"classified by feature context. {clinvar_note}</p>"
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
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
