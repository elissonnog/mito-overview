"""Workflow orchestration for the public mito-overview scaffold."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import PipelineConfig
from .paths import RunPaths

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
    "heteroplasmy": "Compute mitochondrial heteroplasmy summaries.",
    "deletions": "Summarize long-read mtDNA deletion burden.",
    "copy_number": "Estimate the mt:nuclear depth proxy.",
    "feature_annotation": "Annotate mtDNA features and control-region context.",
    "cosegregation": "Summarize co-occurrence of selected mtDNA variants on long reads.",
    "gene_summary": "Aggregate candidate burden at the mitochondrial gene/feature level.",
    "numt_qc": "Assess potential NUMT-related ambiguity signals.",
    "phymer_haplogroup": "Optional human-only haplogroup enrichment.",
    "identity_qc": "Summarize mitochondrial fingerprint and concordance context.",
    "variant_consequence": "Classify candidate consequences and optional overlays.",
    "mvtool_annotation": "Optional human-only external mtDNA annotation enrichment.",
    "circularity_qc": "Evaluate linear-reference edge effects on the circular mtDNA molecule.",
    "methylation_exploratory": "Summarize exploratory whole-molecule methylation context.",
    "sync_bioinfo": "Copy final outputs to the persistent destination.",
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


def validate_config(config: PipelineConfig, strict_files: bool = False) -> list[str]:
    """Return validation issues for the supplied configuration."""

    issues: list[str] = []
    if config.source_align_mode not in {"bam", "cram"}:
        issues.append(f"Unsupported SOURCE_ALIGN_MODE: {config.source_align_mode}")
    if config.mt_length <= 0:
        issues.append("MT_LENGTH must be positive")
    if shutil.which("samtools") is None:
        issues.append("samtools was not found in PATH")
    if strict_files:
        for label, path in (
            ("pipeline_root", config.pipeline_root),
            ("source_sample_dir", config.source_sample_dir),
            ("source_hv_dir", config.source_hv_dir),
            ("ref_fasta", config.ref_fasta),
            ("source_align_file", config.source_align_file),
        ):
            if not path.exists():
                issues.append(f"Missing required path for {label}: {path}")
        if config.source_hv_np_dir and not config.source_hv_np_dir.exists():
            issues.append(f"Missing SOURCE_HV_NP_DIR: {config.source_hv_np_dir}")
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
        (paths.log_dir / f"{step_name}.pending").write_text(note + "\n", encoding="utf-8")
        return StepResult(step_name, "pending", note)

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
        (paths.log_dir / "mito_qc.pending").write_text(note + "\n", encoding="utf-8")
        return StepResult("mito_qc", "pending", note)
    from .steps.mito_qc import run_step

    outputs = run_step(
        bam=paths.mito_bam,
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        species=config.detected_species,
        build=config.reference_build_guess,
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
        (paths.log_dir / "heteroplasmy.pending").write_text(note + "\n", encoding="utf-8")
        return StepResult("heteroplasmy", "pending", note)
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
    )
    (paths.log_dir / "heteroplasmy.done").write_text("ok\n", encoding="utf-8")
    return StepResult("heteroplasmy", "ok", f"Wrote {outputs['report_path']}")


STEP_RUNNERS["mito_qc"] = _run_mito_qc
STEP_RUNNERS["heteroplasmy"] = _run_heteroplasmy


def _run_deletions(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    if not paths.mito_bam.exists():
        note = f"deletions requires an extracted mitochondrial BAM at {paths.mito_bam}"
        (paths.log_dir / "deletions.pending").write_text(note + "\n", encoding="utf-8")
        return StepResult("deletions", "pending", note)
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
        (paths.log_dir / "copy_number.pending").write_text(note + "\n", encoding="utf-8")
        return StepResult("copy_number", "pending", note)
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
        window_size=config.nuclear_window_size,
        window_count=config.nuclear_window_count,
    )
    (paths.log_dir / "copy_number.done").write_text("ok\n", encoding="utf-8")
    return StepResult("copy_number", "ok", f"Wrote {outputs['report_path']}")


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
    (paths.log_dir / "feature_annotation.done").write_text("ok\n", encoding="utf-8")
    return StepResult("feature_annotation", "ok", f"Wrote {outputs['report_path']}")


STEP_RUNNERS["deletions"] = _run_deletions
STEP_RUNNERS["copy_number"] = _run_copy_number
STEP_RUNNERS["feature_annotation"] = _run_feature_annotation


def _run_cosegregation(config: PipelineConfig, paths: RunPaths, strict_files: bool) -> StepResult:
    del strict_files
    if not paths.mito_bam.exists():
        note = f"cosegregation requires an extracted mitochondrial BAM at {paths.mito_bam}"
        (paths.log_dir / "cosegregation.pending").write_text(note + "\n", encoding="utf-8")
        return StepResult("cosegregation", "pending", note)
    from .steps.mito_cosegregation import run_step

    outputs = run_step(
        bam=paths.mito_bam,
        summary_dir=paths.summary_dir,
        figure_dir=paths.figure_dir,
        report_dir=paths.report_dir,
        sample_id=config.sample_id,
        mt_contig=config.mt_contig,
    )
    (paths.log_dir / "cosegregation.done").write_text("ok\n", encoding="utf-8")
    return StepResult("cosegregation", "ok", f"Wrote {outputs['report_path']}")


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
    )
    (paths.log_dir / "numt_qc.done").write_text("ok\n", encoding="utf-8")
    return StepResult("numt_qc", "ok", f"Wrote {outputs['report_path']}")


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
    (paths.log_dir / "gene_summary.done").write_text("ok\n", encoding="utf-8")
    return StepResult("gene_summary", "ok", f"Wrote {outputs['report_path']}")


STEP_RUNNERS["gene_summary"] = _run_gene_summary


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
        np_snp_vcf=paths.np_snp_vcf or "",
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
    (paths.log_dir / "variant_consequence.done").write_text("ok\n", encoding="utf-8")
    return StepResult("variant_consequence", "ok", f"Wrote {outputs['report_path']}")


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
    (paths.log_dir / "circularity_qc.done").write_text("ok\n", encoding="utf-8")
    return StepResult("circularity_qc", "ok", f"Wrote {outputs['report_path']}")


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
    )
    (paths.log_dir / "methylation_exploratory.done").write_text("ok\n", encoding="utf-8")
    return StepResult("methylation_exploratory", "ok", f"Wrote {outputs['report_path']}")


STEP_RUNNERS["identity_qc"] = _run_identity_qc
STEP_RUNNERS["variant_consequence"] = _run_variant_consequence
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
        (paths.log_dir / "sync_bioinfo.pending").write_text(note + "\n", encoding="utf-8")
        return StepResult("sync_bioinfo", "pending", note)
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
    log(f"Run dir: {paths.run_dir}")
    debug(
        f"THREADS={config.threads} HET_MIN_DEPTH={config.het_min_depth} "
        f"HET_MIN_VAF={config.het_min_vaf} DELETION_MIN_SIZE={config.deletion_min_size}",
        config.debug,
    )
    log(f"Requested steps: {','.join(selected)}")

    results: list[StepResult] = []
    if dry_run:
        write_context_files(config, paths)
        for step_name in selected:
            results.append(StepResult(step_name, "planned", STEP_DESCRIPTIONS[step_name]))
        return results

    for step_name in selected:
        log(f"Starting step: {step_name}")
        result = STEP_RUNNERS[step_name](config, paths, strict_files)
        results.append(result)
        if result.status == "failed":
            raise RuntimeError(f"Step {step_name} failed: {result.message}")
        log(f"Completed step: {step_name} ({result.status})")
    return results
