"""Workflow orchestration for the public mito-overview scaffold."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd
import pysam

from .config import PipelineConfig
from .paths import RunPaths
from .report_common import render_status_page

DEFAULT_STEP_ORDER = [
    "validate",
    "stage",
    "extract",
    "mito_qc",
    "heteroplasmy",
    "deletions",
    "copy_number",
    "feature_annotation",
    "cosegregation",
    "gene_summary",
    "numt_qc",
    "phymer_haplogroup",
    "identity_qc",
    "variant_consequence",
    "mvtool_annotation",
    "circularity_qc",
    "methylation_exploratory",
    "sync_bioinfo",
]

STEP_DESCRIPTIONS = {
    "validate": "Validate the configuration and input contract.",
    "stage": "Write provenance/context files and initialize run layout.",
    "extract": "Extract mitochondrial read and methylation assets.",
    "mito_qc": "Summarize read-level mitochondrial QC metrics.",
    "heteroplasmy": "Compute filtered mitochondrial alternate-allele summaries.",
    "deletions": "Summarize long-read mtDNA deletion burden.",
    "copy_number": "Estimate the mt:nuclear depth proxy.",
    "feature_annotation": "Annotate mtDNA features and control-region context.",
    "cosegregation": "Summarize co-occurrence of selected mtDNA variants on long reads.",
    "gene_summary": "Aggregate candidate burden at the mitochondrial gene/feature level.",
    "numt_qc": "Report alignment-ambiguity metrics and scope-gated NUMT warnings.",
    "phymer_haplogroup": "Optional human-only haplogroup enrichment.",
    "identity_qc": "Summarize mitochondrial fingerprint and concordance context.",
    "variant_consequence": "Classify candidate consequences and optional overlays.",
    "mvtool_annotation": "Optional human-only external mtDNA annotation enrichment.",
    "circularity_qc": "Evaluate linear-reference edge effects on the circular mtDNA molecule.",
    "methylation_exploratory": "Summarize exploratory whole-molecule methylation context.",
    "sync_bioinfo": "Copy final outputs to the persistent destination.",
}

STEP_STATUS_OUTPUTS: dict[str, dict[str, object]] = {
    "deletions": {
        "title": "Mitochondrial Deletions",
        "report_filename": "03_mito_deletions.html",
        "status_files": ["mito_deletion_summary.tsv"],
        "empty_tables": {
            "mito_deletion_events.tsv": [
                "read_name",
                "event_start",
                "event_end",
                "deletion_size",
                "event_bin_start",
                "event_bin_end",
                "is_primary_read",
                "has_sa_tag",
            ],
            "mito_deletion_clusters.tsv": [
                "event_bin_start",
                "event_bin_end",
                "supporting_reads",
                "median_deletion_size",
                "min_deletion_size",
                "max_deletion_size",
                "support_fraction_primary",
            ],
            "mito_deletion_read_flags.tsv": [
                "read_name",
                "has_large_deletion",
                "is_supplementary",
                "has_sa_tag",
            ],
        },
    },
    "copy_number": {
        "title": "Mitochondrial Copy-number Proxy",
        "report_filename": "04_mito_copy_number.html",
        "status_files": ["mito_copy_number_summary.tsv"],
        "empty_tables": {
            "mito_copy_number_windows.tsv": ["contig", "start", "end", "window_size", "mean_depth"],
        },
    },
    "cosegregation": {
        "title": "Mitochondrial Co-segregation",
        "report_filename": "06_mito_cosegregation.html",
        "status_files": ["mito_cosegregation_summary.tsv"],
        "empty_tables": {
            "mito_cosegregation_selected_sites.tsv": [
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
            ],
            "mito_cosegregation_pairwise.tsv": [
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
            ],
            "mito_cosegregation_read_burden.tsv": ["alt_selected_sites", "read_count"],
        },
    },
    "numt_qc": {
        "title": "Mito Alignment-Ambiguity QC",
        "report_filename": "08_mito_numt_qc.html",
        "status_files": ["mito_numt_qc_summary.tsv"],
        "empty_tables": {},
    },
    "phymer_haplogroup": {
        "title": "Mito Phy-Mer Haplogroup",
        "report_filename": "13_mito_phymer_haplogroup.html",
        "status_files": ["mito_phymer_haplogroup_summary.tsv"],
        "empty_tables": {
            "mito_phymer_haplogroup_ranking.tsv": ["rank", "haplogroup", "score", "defining_snps"],
            "mito_phymer_major_variant_input.tsv": [
                "position",
                "ref_base",
                "alt_base",
                "depth",
                "alt_allele_fraction",
                "heteroplasmy_fraction",
                "phymer_input",
            ],
        },
    },
    "identity_qc": {
        "title": "Mitochondrial Identity QC",
        "report_filename": "09_mito_identity_qc.html",
        "status_files": ["mito_identity_qc_summary.tsv"],
        "empty_tables": {
            "mito_identity_major_variant_fingerprint.tsv": [
                "position",
                "ref_base",
                "alt_base",
                "alt_allele_fraction",
                "heteroplasmy_fraction",
                "depth",
            ],
            "mito_identity_vcf_comparison.tsv": ["membership", "position", "ref", "alt"],
        },
    },
    "circularity_qc": {
        "title": "Mitochondrial Circularity QC",
        "report_filename": "11_mito_circularity_qc.html",
        "status_files": ["mito_circularity_qc_summary.tsv"],
        "empty_tables": {},
    },
    "methylation_exploratory": {
        "title": "Mitochondrial Methylation (Exploratory)",
        "report_filename": "12_mito_methylation_exploratory.html",
        "status_files": [
            "mito_methylation_exploratory_summary.tsv",
            "mito_methylation_np_vs_proxy_summary.tsv",
        ],
        "empty_tables": {
            "mito_methylation_track_rows.tsv": [
                "track",
                "position",
                "valid_coverage",
                "percent_modified",
                "modified_count",
                "canonical_count",
            ],
            "mito_methylation_np_vs_proxy.tsv": [
                "position",
                "percent_modified_np",
                "percent_modified_proxy",
                "abs_difference",
            ],
        },
    },
}


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    print(f"[{_timestamp()}] [INFO] {message}")


def debug(message: str, enabled: bool) -> None:
    if enabled:
        print(f"[{_timestamp()}] [DEBUG] {message}")


@dataclass(frozen=True)
class StepResult:
    """Lightweight structured result for a workflow step."""

    step_name: str
    status: str
    message: str


def list_steps() -> list[str]:
    """Return the canonical workflow step order."""

    return list(DEFAULT_STEP_ORDER)


def _ensure_known_steps(steps: list[str]) -> None:
    unknown = [step for step in steps if step not in STEP_DESCRIPTIONS]
    if unknown:
        unknown_str = ", ".join(unknown)
        raise ValueError(f"Unknown workflow steps: {unknown_str}")


def _step_not_applicable_message(config: PipelineConfig, step_name: str) -> str | None:
    if config.is_short_read:
        short_read_messages = {
            "deletions": (
                "The current deletion screen is long-read-specific and is skipped in short-read mode. "
                "Short-read deletion calling has not yet been implemented in the public profile."
            ),
            "cosegregation": (
                "Co-segregation is defined on the same long molecules and is skipped in short-read mode."
            ),
            "numt_qc": (
                "The current NUMT-aware QC heuristics are tuned for long-read molecule structure and are "
                "skipped in short-read mode."
            ),
            "identity_qc": (
                "The current identity-QC page compares phased and no-phased mitochondrial SNP callsets from "
                "the long-read workflow and is skipped in short-read mode."
            ),
            "circularity_qc": (
                "The current circularity-QC heuristics are tuned for long-read edge-context signals and are "
                "skipped in short-read mode."
            ),
            "methylation_exploratory": (
                "Exploratory methylation requires ONT bedmethyl-style inputs and is skipped in short-read mode."
            ),
        }
        if step_name in short_read_messages:
            return short_read_messages[step_name]
    if config.is_targeted_mt:
        targeted_messages = {
            "copy_number": (
                "Copy-number proxy is only interpreted for whole-genome data and is skipped for targeted mtDNA assays."
            ),
            "phymer_haplogroup": (
                "Phy-Mer haplogroup inference assumes full-mitochondrion sequence context and is skipped for targeted "
                "mtDNA assays that may not cover the complete mitochondrial genome."
            ),
        }
        if step_name in targeted_messages:
            return targeted_messages[step_name]
    return None


def _write_not_applicable_step(
    config: PipelineConfig,
    paths: RunPaths,
    step_name: str,
    message: str,
) -> StepResult:
    spec = STEP_STATUS_OUTPUTS.get(step_name)
    if spec is None:
        note = f"{step_name} was not applicable for this run profile: {message}"
        (paths.log_dir / f"{step_name}.not_applicable").write_text(note + "\n", encoding="utf-8")
        return StepResult(step_name, "not_applicable", note)

    status_df = pd.DataFrame(
        [
            {"metric": "status", "value": "not_applicable"},
            {"metric": "step", "value": step_name},
            {"metric": "read_mode", "value": config.read_mode},
            {"metric": "assay_type", "value": config.assay_type},
            {"metric": "message", "value": message},
        ]
    )
    for filename in spec.get("status_files", []):
        output_path = paths.summary_dir / str(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        status_df.to_csv(output_path, sep="\t", index=False)
    for filename, columns in spec.get("empty_tables", {}).items():
        output_path = paths.summary_dir / str(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=list(columns)).to_csv(output_path, sep="\t", index=False)

    report_path = paths.report_dir / str(spec["report_filename"])
    render_status_page(
        report_path,
        str(spec["title"]),
        config.sample_id,
        f"{config.mt_contig}:1-{config.mt_length}",
        message,
        status_df,
    )
    note = f"{step_name} is not applicable for read_mode={config.read_mode} assay_type={config.assay_type}"
    (paths.log_dir / f"{step_name}.not_applicable").write_text(note + "\n", encoding="utf-8")
    return StepResult(step_name, "not_applicable", note)


def validate_config(config: PipelineConfig, strict_files: bool = False) -> list[str]:
    """Return validation issues for the supplied configuration."""

    issues: list[str] = []
    if config.source_align_mode not in {"bam", "cram"}:
        issues.append(f"Unsupported SOURCE_ALIGN_MODE: {config.source_align_mode}")
    if shutil.which("samtools") is None:
        issues.append("samtools was not found in PATH")
    for label, path in (("ref_fasta", config.ref_fasta), ("source_align_file", config.source_align_file)):
        if not path.exists():
            issues.append(f"Missing required path for {label}: {path}")

    fai_path = Path(f"{config.ref_fasta}.fai")
    if config.ref_fasta.exists() and not fai_path.exists():
        issues.append(f"Missing FASTA index: {fai_path}")
    elif fai_path.exists():
        fai_lengths: dict[str, int] = {}
        for raw_line in fai_path.read_text(encoding="utf-8").splitlines():
            fields = raw_line.split("\t")
            if len(fields) >= 2:
                fai_lengths[fields[0]] = int(fields[1])
        if config.mt_contig not in fai_lengths:
            issues.append(f"Reference index does not contain MT_CONTIG={config.mt_contig}")
        elif fai_lengths[config.mt_contig] != config.mt_length:
            issues.append(
                f"MT_LENGTH={config.mt_length} does not match reference index length "
                f"{fai_lengths[config.mt_contig]} for {config.mt_contig}"
            )

    alignment_index_available = False
    if config.source_align_file.exists():
        if config.source_align_mode == "bam":
            candidates = [Path(f"{config.source_align_file}.bai"), config.source_align_file.with_suffix(".bai")]
            alignment_index_available = any(path.exists() for path in candidates)
            if not alignment_index_available:
                issues.append(f"Missing BAM index for {config.source_align_file}")
        else:
            candidates = [Path(f"{config.source_align_file}.crai"), config.source_align_file.with_suffix(".crai")]
            alignment_index_available = any(path.exists() for path in candidates)
            if not alignment_index_available:
                issues.append(f"Missing CRAM index for {config.source_align_file}")
            if not config.ref_fasta.exists():
                issues.append("CRAM input requires an available REF_FASTA")

    if config.source_align_file.exists() and config.ref_fasta.exists() and alignment_index_available:
        mode = "rc" if config.source_align_mode == "cram" else "rb"
        kwargs = {"reference_filename": str(config.ref_fasta)} if mode == "rc" else {}
        try:
            with pysam.AlignmentFile(str(config.source_align_file), mode, **kwargs) as alignment:
                header_lengths = dict(zip(alignment.references, alignment.lengths, strict=True))
                if config.mt_contig not in header_lengths:
                    issues.append(f"Alignment header does not contain MT_CONTIG={config.mt_contig}")
                elif header_lengths[config.mt_contig] != config.mt_length:
                    issues.append(
                        f"Alignment header length {header_lengths[config.mt_contig]} for {config.mt_contig} "
                        f"does not match MT_LENGTH={config.mt_length}"
                    )
                else:
                    # Decode one indexed record when present; this catches CRAM/reference incompatibility early.
                    next(alignment.fetch(config.mt_contig, 0, config.mt_length), None)
        except (OSError, ValueError) as exc:
            input_label = "CRAM/reference pair" if mode == "rc" else "BAM input"
            issues.append(f"Could not open indexed {input_label}: {exc}")

    if config.mvtool_mode == "fixture" and config.mvtool_fixture_json is None:
        issues.append("MVTOOL_MODE=fixture requires MVTOOL_FIXTURE_JSON")

    if strict_files:
        optional_paths = (
            ("SOURCE_HV_DIR", config.source_hv_dir),
            ("SOURCE_HV_NP_DIR", config.source_hv_np_dir),
            ("SOURCE_VARIANT_VCF", config.source_variant_vcf),
            ("SOURCE_CLINVAR_VCF", config.source_clinvar_vcf),
            ("SOURCE_VARIANT_VCF_UNPHASED", config.source_variant_vcf_unphased),
            ("SOURCE_CLINVAR_VCF_UNPHASED", config.source_clinvar_vcf_unphased),
            ("SOURCE_BEDMETHYL", config.source_bedmethyl),
            ("SOURCE_BEDMETHYL_HP1", config.source_bedmethyl_hp1),
            ("SOURCE_BEDMETHYL_HP2", config.source_bedmethyl_hp2),
            ("SOURCE_BEDMETHYL_UNGROUPED", config.source_bedmethyl_ungrouped),
            ("MVTOOL_FIXTURE_JSON", config.mvtool_fixture_json),
        )
        for label, path in optional_paths:
            if path is not None and not path.exists():
                issues.append(f"Configured optional path does not exist for {label}: {path}")
    return issues


def write_context_files(config: PipelineConfig, paths: RunPaths) -> None:
    """Write portable provenance files for the run."""

    stage_context_tsv = paths.stage_dir / "run_context.tsv"
    stage_context_json = paths.stage_dir / "run_context.json"
    rows = config.context_rows() + paths.context_rows()
    stage_context_tsv.write_text(
        "field\tvalue\n" + "\n".join(f"{field}\t{value}" for field, value in rows) + "\n",
        encoding="utf-8",
    )
    payload = {
        "config": {field: value for field, value in config.context_rows()},
        "paths": {field: value for field, value in paths.context_rows()},
    }
    stage_context_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_validate(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    issues = validate_config(config, strict_files=strict_files)
    report_path = paths.log_dir / "validate.done"
    if issues:
        report_path.write_text("\n".join(issues) + "\n", encoding="utf-8")
        return StepResult("validate", "failed", "; ".join(issues))
    report_path.write_text("ok\n", encoding="utf-8")
    return StepResult("validate", "ok", "Configuration checks passed.")


def _run_stage(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files  # unused but kept for a uniform step signature
    paths.create_layout()
    write_context_files(config, paths)
    (paths.log_dir / "stage.done").write_text("ok\n", encoding="utf-8")
    return StepResult("stage", "ok", "Run layout and provenance files created.")


def _run_extract(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.extract_mito_assets import run_step

    outputs = run_step(
        source_align_file=config.source_align_file,
        align_mode=config.source_align_mode,
        ref_fasta=config.ref_fasta,
        mito_bam=paths.mito_bam,
        mito_region_bed=paths.mito_region_bed,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
        threads=config.threads,
        read_mode=config.read_mode,
        np_bedmethyl_source_gz=paths.np_bedmethyl_source_gz,
        hp1_bedmethyl_source_gz=paths.hp1_bedmethyl_source_gz,
        hp2_bedmethyl_source_gz=paths.hp2_bedmethyl_source_gz,
        ungrouped_bedmethyl_source_gz=paths.ungrouped_bedmethyl_source_gz,
        mito_mods_np=paths.mito_mods_np,
        mito_mods_hp1=paths.mito_mods_hp1,
        mito_mods_hp2=paths.mito_mods_hp2,
        mito_mods_ungrouped=paths.mito_mods_ungrouped,
    )
    (paths.log_dir / "extract.done").write_text("ok\n", encoding="utf-8")
    return StepResult(
        "extract",
        "ok",
        f"Wrote {outputs['mito_bam']} and mitochondrial methylation subsets.",
    )


def _pending_step(step_name: str) -> Callable[[PipelineConfig, RunPaths, bool], StepResult]:
    def runner(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
        del config, strict_files
        note = (
            f"{step_name} is not ported into the public package yet. "
            "Use --dry-run to plan the step order, or port the validated internal module next."
        )
        (paths.log_dir / f"{step_name}.not_configured").write_text(note + "\n", encoding="utf-8")
        return StepResult(step_name, "not_configured", note)

    return runner


STEP_RUNNERS: dict[str, Callable[[PipelineConfig, RunPaths, bool], StepResult]] = {
    "validate": _run_validate,
    "stage": _run_stage,
    "extract": _run_extract,
}
for _step_name in DEFAULT_STEP_ORDER:
    STEP_RUNNERS.setdefault(_step_name, _pending_step(_step_name))


def _run_mito_qc(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    if not paths.mito_bam.exists():
        note = (
            f"mito_qc requires an extracted mitochondrial BAM at {paths.mito_bam}. "
            "Port the extract step or provide the subset BAM before running this step."
        )
        (paths.log_dir / "mito_qc.not_evaluable").write_text(note + "\n", encoding="utf-8")
        return StepResult("mito_qc", "not_evaluable", note)
    from .steps.mito_qc import run_step

    outputs = run_step(
        bam=paths.mito_bam,
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        species=config.detected_species,
        build=config.reference_build_guess,
        read_mode=config.read_mode,
        assay_type=config.assay_type,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
    )
    (paths.log_dir / "mito_qc.done").write_text("ok\n", encoding="utf-8")
    return StepResult("mito_qc", "ok", f"Wrote {outputs['report_path']}")


def _run_heteroplasmy(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    missing_inputs = [str(path) for path in (paths.mito_bam, config.ref_fasta) if not Path(path).exists()]
    if missing_inputs:
        note = (
            "heteroplasmy requires the extracted mitochondrial BAM and reference FASTA. "
            f"Missing inputs: {', '.join(missing_inputs)}"
        )
        (paths.log_dir / "heteroplasmy.not_evaluable").write_text(note + "\n", encoding="utf-8")
        return StepResult("heteroplasmy", "not_evaluable", note)
    from .steps.mito_heteroplasmy import run_step

    outputs = run_step(
        bam=paths.mito_bam,
        ref_fasta=config.ref_fasta,
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
        min_depth=config.het_min_depth,
        min_vaf=config.het_min_vaf,
        min_base_quality=config.allele_min_base_quality,
        min_mapping_quality=config.allele_min_mapping_quality,
        min_read_mean_quality=config.allele_min_read_mean_quality,
        max_depth=config.allele_max_depth,
        exclude_flags=config.allele_exclude_flags,
        ignore_overlaps=config.allele_ignore_overlaps,
    )
    (paths.log_dir / "heteroplasmy.done").write_text("ok\n", encoding="utf-8")
    return StepResult("heteroplasmy", "ok", f"Wrote {outputs['report_path']}")


STEP_RUNNERS["mito_qc"] = _run_mito_qc
STEP_RUNNERS["heteroplasmy"] = _run_heteroplasmy


def _run_deletions(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    if not paths.mito_bam.exists():
        note = f"deletions requires an extracted mitochondrial BAM at {paths.mito_bam}"
        (paths.log_dir / "deletions.not_evaluable").write_text(note + "\n", encoding="utf-8")
        return StepResult("deletions", "not_evaluable", note)
    from .steps.mito_deletions import run_step

    outputs = run_step(
        bam=paths.mito_bam,
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
        min_deletion_size=config.deletion_min_size,
    )
    (paths.log_dir / "deletions.done").write_text("ok\n", encoding="utf-8")
    return StepResult("deletions", "ok", f"Wrote {outputs['report_path']}")


def _run_copy_number(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    missing_inputs = [str(path) for path in (config.source_align_file, config.ref_fasta) if not Path(path).exists()]
    if missing_inputs:
        note = f"copy_number requires the original alignment file and reference FASTA. Missing inputs: {', '.join(missing_inputs)}"
        (paths.log_dir / "copy_number.not_evaluable").write_text(note + "\n", encoding="utf-8")
        return StepResult("copy_number", "not_evaluable", note)
    from .steps.mito_copy_number import run_step

    outputs = run_step(
        align_file=config.source_align_file,
        align_mode=config.source_align_mode,
        ref_fasta=config.ref_fasta,
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
        species=config.detected_species,
        reference_scope=config.reference_scope,
        window_size=config.nuclear_window_size,
        window_count=config.nuclear_window_count,
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"copy_number.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("copy_number", status, f"Wrote {outputs['report_path']}")


def _run_feature_annotation(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.mito_feature_annotation import run_step

    outputs = run_step(
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        species=config.detected_species,
        build=config.reference_build_guess,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
        human_mt_gtf=config.human_mt_gtf,
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"feature_annotation.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("feature_annotation", status, f"Wrote {outputs['report_path']}")


STEP_RUNNERS["deletions"] = _run_deletions
STEP_RUNNERS["copy_number"] = _run_copy_number
STEP_RUNNERS["feature_annotation"] = _run_feature_annotation


def _run_cosegregation(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    if not paths.mito_bam.exists():
        note = f"cosegregation requires an extracted mitochondrial BAM at {paths.mito_bam}"
        (paths.log_dir / "cosegregation.not_evaluable").write_text(note + "\n", encoding="utf-8")
        return StepResult("cosegregation", "not_evaluable", note)
    from .steps.mito_cosegregation import run_step

    outputs = run_step(
        bam=paths.mito_bam,
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        min_base_quality=config.allele_min_base_quality,
        min_mapping_quality=config.allele_min_mapping_quality,
        min_read_mean_quality=config.allele_min_read_mean_quality,
        max_depth=config.allele_max_depth,
        exclude_flags=config.allele_exclude_flags,
        ignore_overlaps=config.allele_ignore_overlaps,
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"cosegregation.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("cosegregation", status, f"Wrote {outputs['report_path']}")


def _run_numt_qc(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.mito_numt_qc import run_step

    outputs = run_step(
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
        reference_scope=config.reference_scope,
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"numt_qc.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("numt_qc", status, f"Wrote {outputs['report_path']}")


STEP_RUNNERS["cosegregation"] = _run_cosegregation
STEP_RUNNERS["numt_qc"] = _run_numt_qc


def _run_gene_summary(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.mito_gene_summary import run_step

    outputs = run_step(
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"gene_summary.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("gene_summary", status, f"Wrote {outputs['report_path']}")


STEP_RUNNERS["gene_summary"] = _run_gene_summary


def _run_phymer_haplogroup(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.mito_phymer_haplogroup import run_step

    outputs = run_step(
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
        species=config.detected_species,
        ref_fasta=config.ref_fasta,
        phymer_root=config.phymer_root,
        min_depth=config.phymer_min_depth,
        major_vaf=config.phymer_major_vaf,
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"phymer_haplogroup.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("phymer_haplogroup", status, f"Wrote {outputs['report_path']}")


def _run_identity_qc(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.mito_identity_qc import run_step

    outputs = run_step(
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        phased_snp_vcf=paths.phased_snp_vcf,
        np_snp_vcf=paths.np_snp_vcf,
    )
    (paths.log_dir / "identity_qc.done").write_text("ok\n", encoding="utf-8")
    return StepResult("identity_qc", "ok", f"Wrote {outputs['report_path']}")


def _run_variant_consequence(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.mito_variant_consequence import run_step

    outputs = run_step(
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
        ref_fasta=config.ref_fasta,
        np_clinvar_vcf=paths.np_clinvar_vcf,
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"variant_consequence.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("variant_consequence", status, f"Wrote {outputs['report_path']}")


def _run_circularity_qc(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.mito_circularity_qc import run_step

    outputs = run_step(
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"circularity_qc.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("circularity_qc", status, f"Wrote {outputs['report_path']}")


def _run_methylation_exploratory(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.mito_methylation_exploratory import run_step

    outputs = run_step(
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
        mito_mods_np=paths.mito_mods_np if paths.mito_mods_np.exists() else None,
        mito_mods_hp1=paths.mito_mods_hp1,
        mito_mods_hp2=paths.mito_mods_hp2,
        mito_mods_ungrouped=paths.mito_mods_ungrouped,
        inputs_configured=any(
            source is not None and source.exists()
            for source in (
                paths.np_bedmethyl_source_gz,
                paths.hp1_bedmethyl_source_gz,
                paths.hp2_bedmethyl_source_gz,
                paths.ungrouped_bedmethyl_source_gz,
            )
        ),
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"methylation_exploratory.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("methylation_exploratory", status, f"Wrote {outputs['report_path']}")


STEP_RUNNERS["identity_qc"] = _run_identity_qc


def _run_mvtool_annotation(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    from .steps.mito_mvtool_annotation import run_step

    outputs = run_step(
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        species=config.detected_species,
        mode=config.mvtool_mode,
        api_url=config.mvtool_api_url,
        fixture_json=config.mvtool_fixture_json,
        timeout=config.mseqdr_timeout,
    )
    status = str(outputs.get("status", "ok"))
    (paths.log_dir / f"mvtool_annotation.{status}").write_text(status + "\n", encoding="utf-8")
    return StepResult("mvtool_annotation", status, f"Wrote {outputs['report_path']}")


STEP_RUNNERS["phymer_haplogroup"] = _run_phymer_haplogroup
STEP_RUNNERS["variant_consequence"] = _run_variant_consequence
STEP_RUNNERS["mvtool_annotation"] = _run_mvtool_annotation
STEP_RUNNERS["circularity_qc"] = _run_circularity_qc
STEP_RUNNERS["methylation_exploratory"] = _run_methylation_exploratory


def _run_sync_bioinfo(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    missing_inputs = [
        str(path)
        for path in (paths.output_dir, paths.log_dir, paths.mito_bam, paths.mito_bai)
        if not Path(path).exists()
    ]
    if missing_inputs:
        note = (
            "sync_bioinfo requires the output/log directories and extracted BAM artifacts. "
            f"Missing inputs: {', '.join(missing_inputs)}"
        )
        (paths.log_dir / "sync_bioinfo.not_evaluable").write_text(note + "\n", encoding="utf-8")
        return StepResult("sync_bioinfo", "not_evaluable", note)
    from .steps.sync_bioinfo import run_step

    outputs = run_step(
        output_dir=paths.output_dir,
        log_dir=paths.log_dir,
        mito_bam=paths.mito_bam,
        mito_bai=paths.mito_bai,
        config_file=config.config_file,
        final_dir=paths.final_bioinfo_dir,
        sample_id=config.sample_id,
        run_name=config.run_name,
        mt_contig=config.mt_contig,
        mt_length=config.mt_length,
        species=config.detected_species,
        build=config.reference_build_guess,
    )
    (paths.log_dir / "sync_bioinfo.done").write_text("ok\n", encoding="utf-8")
    return StepResult("sync_bioinfo", "ok", f"Synced outputs to {outputs['final_dir']}")


STEP_RUNNERS["sync_bioinfo"] = _run_sync_bioinfo


def plan_steps(steps: list[str] | None = None) -> list[tuple[str, str]]:
    """Return the selected steps with their descriptions."""

    selected = steps or list_steps()
    _ensure_known_steps(selected)
    return [(step, STEP_DESCRIPTIONS[step]) for step in selected]


def run_pipeline(
    config: PipelineConfig,
    steps: list[str] | None = None,
    *,
    dry_run: bool = False,
    strict_files: bool = False,
) -> list[StepResult]:
    """Run the portable scaffold workflow for the selected steps."""

    selected = steps or list_steps()
    _ensure_known_steps(selected)
    paths = RunPaths.from_config(config)
    paths.create_layout()
    log(f"Run name: {config.run_name}")
    log(f"Sample: {config.sample_id}")
    log(f"Species: {config.detected_species}")
    log(f"Build: {config.reference_build_guess}")
    log(f"Read mode: {config.read_mode}")
    log(f"Assay type: {config.assay_type}")
    log(f"Run dir: {paths.run_dir}")
    debug(
        f"THREADS={config.threads} MIN_CALLABLE_DEPTH={config.min_callable_depth} "
        f"MIN_ALT_ALLELE_FRACTION={config.min_alt_allele_fraction} "
        f"ALLELE_BQ={config.allele_min_base_quality} ALLELE_MAPQ={config.allele_min_mapping_quality} "
        f"ALLELE_READQ={config.allele_min_read_mean_quality} DELETION_MIN_SIZE={config.deletion_min_size}",
        config.debug,
    )
    log(f"Requested steps: {','.join(selected)}")

    results: list[StepResult] = []
    if dry_run:
        if strict_files:
            issues = validate_config(config, strict_files=True)
            if issues:
                raise ValueError("; ".join(issues))
        write_context_files(config, paths)
        for step_name in selected:
            results.append(StepResult(step_name, "planned", STEP_DESCRIPTIONS[step_name]))
        return results

    preflight_issues = validate_config(config, strict_files=False)
    if preflight_issues:
        raise ValueError("Preflight failed: " + "; ".join(preflight_issues))

    for step_name in selected:
        log(f"Starting step: {step_name}")
        skip_message = _step_not_applicable_message(config, step_name)
        if skip_message is not None:
            result = _write_not_applicable_step(config, paths, step_name, skip_message)
            results.append(result)
            log(f"Completed step: {step_name} ({result.status})")
            continue
        result = STEP_RUNNERS[step_name](config, paths, strict_files)
        results.append(result)
        if result.status == "failed":
            raise RuntimeError(f"Step {step_name} failed: {result.message}")
        log(f"Completed step: {step_name} ({result.status})")
    return results
