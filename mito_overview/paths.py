"""Derived run paths for mito-overview."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import PipelineConfig


@dataclass(frozen=True)
class RunPaths:
    """Filesystem layout derived from a :class:`PipelineConfig`."""

    region: str
    region_tag: str
    run_dir: Path
    log_dir: Path
    stage_dir: Path
    output_dir: Path
    subset_dir: Path
    methyl_dir: Path
    summary_dir: Path
    figure_dir: Path
    report_dir: Path
    tmp_dir: Path
    mito_bam: Path
    mito_bai: Path
    mito_region_bed: Path
    mito_mods_np: Path
    mito_mods_hp1: Path
    mito_mods_hp2: Path
    mito_mods_ungrouped: Path
    phased_snp_vcf: Path
    phased_clinvar_vcf: Path
    np_snp_vcf: Path | None
    np_clinvar_vcf: Path | None
    np_bedmethyl_source_gz: Path | None
    hp1_bedmethyl_source_gz: Path
    hp2_bedmethyl_source_gz: Path
    ungrouped_bedmethyl_source_gz: Path
    final_bioinfo_dir: Path

    @classmethod
    def from_config(cls, config: PipelineConfig) -> "RunPaths":
        region = f"{config.mt_contig}:1-{config.mt_length}"
        region_tag = f"{config.mt_contig}_1-{config.mt_length}".replace(":", "_").replace("/", "_").replace(" ", "_")
        run_dir = config.work_root / config.run_name
        log_dir = run_dir / "logs"
        stage_dir = run_dir / "stage"
        output_dir = run_dir / "output"
        subset_dir = output_dir / "subset"
        methyl_dir = output_dir / "methylation"
        summary_dir = output_dir / "summary"
        figure_dir = output_dir / "figures"
        report_dir = output_dir / "report"
        tmp_dir = run_dir / "tmp"
        mito_bam = subset_dir / f"{config.sample_id}.{config.mt_contig}.bam"
        final_bioinfo_dir = config.final_bioinfo_dir or (config.source_sample_dir.parent / "reports" / "mito_overview" / config.run_name)

        np_prefix = config.source_hv_np_dir / config.sample_id if config.source_hv_np_dir else None
        hv_prefix = config.source_hv_dir / config.sample_id
        return cls(
            region=region,
            region_tag=region_tag,
            run_dir=run_dir,
            log_dir=log_dir,
            stage_dir=stage_dir,
            output_dir=output_dir,
            subset_dir=subset_dir,
            methyl_dir=methyl_dir,
            summary_dir=summary_dir,
            figure_dir=figure_dir,
            report_dir=report_dir,
            tmp_dir=tmp_dir,
            mito_bam=mito_bam,
            mito_bai=Path(f"{mito_bam}.bai"),
            mito_region_bed=subset_dir / f"{config.sample_id}.{config.mt_contig}.bed",
            mito_mods_np=methyl_dir / f"{config.sample_id}.{config.mt_contig}.wf_mods.NP.tsv",
            mito_mods_hp1=methyl_dir / f"{config.sample_id}.{config.mt_contig}.wf_mods.1.tsv",
            mito_mods_hp2=methyl_dir / f"{config.sample_id}.{config.mt_contig}.wf_mods.2.tsv",
            mito_mods_ungrouped=methyl_dir / f"{config.sample_id}.{config.mt_contig}.wf_mods.ungrouped.tsv",
            phased_snp_vcf=config.source_hv_dir / f"{config.sample_id}.wf_snp.vcf.gz",
            phased_clinvar_vcf=config.source_hv_dir / f"{config.sample_id}.wf_snp_clinvar.vcf.gz",
            np_snp_vcf=(np_prefix.parent / f"{config.sample_id}.wf_snp.vcf.gz") if np_prefix else None,
            np_clinvar_vcf=(np_prefix.parent / f"{config.sample_id}.wf_snp_clinvar.vcf.gz") if np_prefix else None,
            np_bedmethyl_source_gz=(np_prefix.parent / f"{config.sample_id}.wf_mods.bedmethyl.gz") if np_prefix else None,
            hp1_bedmethyl_source_gz=hv_prefix.parent / f"{config.sample_id}.wf_mods.1.bedmethyl.gz",
            hp2_bedmethyl_source_gz=hv_prefix.parent / f"{config.sample_id}.wf_mods.2.bedmethyl.gz",
            ungrouped_bedmethyl_source_gz=hv_prefix.parent / f"{config.sample_id}.wf_mods.ungrouped.bedmethyl.gz",
            final_bioinfo_dir=final_bioinfo_dir,
        )

    def create_layout(self) -> None:
        """Create the standard run directory structure."""

        for path in (
            self.run_dir,
            self.log_dir,
            self.stage_dir,
            self.output_dir,
            self.subset_dir,
            self.methyl_dir,
            self.summary_dir,
            self.figure_dir,
            self.report_dir,
            self.tmp_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def context_rows(self) -> list[tuple[str, str]]:
        """Return derived path metadata in a table-friendly order."""

        return [
            ("region", self.region),
            ("region_tag", self.region_tag),
            ("run_dir", str(self.run_dir)),
            ("log_dir", str(self.log_dir)),
            ("summary_dir", str(self.summary_dir)),
            ("figure_dir", str(self.figure_dir)),
            ("report_dir", str(self.report_dir)),
            ("mito_bam", str(self.mito_bam)),
            ("mito_mods_np", str(self.mito_mods_np)),
            ("final_bioinfo_dir", str(self.final_bioinfo_dir)),
        ]
