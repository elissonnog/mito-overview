"""Derived run paths for mito-overview."""

from __future__ import annotations

import sysconfig
from dataclasses import dataclass
from pathlib import Path

from .config import PipelineConfig


ANNOTATION_RESOURCE_NAMES = frozenset(
    {
        "human_mt_reference.gtf",
        "NC_012920.1.fa",
    }
)


def annotation_resource_path(name: str) -> Path:
    """Resolve a bundled annotation resource in a checkout or installed wheel."""

    if name not in ANNOTATION_RESOURCE_NAMES:
        allowed = ", ".join(sorted(ANNOTATION_RESOURCE_NAMES))
        raise ValueError(f"Unknown annotation resource {name!r}; allowed values: {allowed}")

    source_path = Path(__file__).resolve().parents[1] / "resources" / "annotations" / name
    if source_path.is_file():
        return source_path

    installed_path = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "mito-overview"
        / "annotations"
        / name
    )
    if installed_path.is_file():
        return installed_path
    raise FileNotFoundError(
        f"Bundled annotation resource {name!r} was not found at {installed_path}"
    )


def _legacy_sidecar(directory: Path | None, sample_id: str, suffix: str) -> Path | None:
    return directory / f"{sample_id}.{suffix}" if directory else None


def _prefer_explicit(explicit: Path | None, legacy: Path | None) -> tuple[Path | None, str]:
    if explicit is not None:
        return explicit, "explicit" if explicit.exists() else "explicit_missing"
    if legacy is not None and legacy.exists():
        return legacy, "legacy_discovery"
    return None, "absent"


@dataclass(frozen=True)
class RunPaths:
    """Filesystem layout and resolved optional inputs for one run."""

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
    phased_snp_vcf: Path | None
    phased_clinvar_vcf: Path | None
    np_snp_vcf: Path | None
    np_clinvar_vcf: Path | None
    np_bedmethyl_source_gz: Path | None
    hp1_bedmethyl_source_gz: Path | None
    hp2_bedmethyl_source_gz: Path | None
    ungrouped_bedmethyl_source_gz: Path | None
    final_bioinfo_dir: Path
    sidecar_resolution: dict[str, str]

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
        final_bioinfo_dir = config.final_bioinfo_dir or (config.work_root / f"{config.run_name}_final")

        phased_snp_vcf, phased_snp_resolution = _prefer_explicit(
            config.source_variant_vcf,
            _legacy_sidecar(config.source_hv_dir, config.sample_id, "wf_snp.vcf.gz"),
        )
        phased_clinvar_vcf, phased_clinvar_resolution = _prefer_explicit(
            config.source_clinvar_vcf,
            _legacy_sidecar(config.source_hv_dir, config.sample_id, "wf_snp_clinvar.vcf.gz"),
        )
        np_snp_vcf, np_snp_resolution = _prefer_explicit(
            config.source_variant_vcf_unphased,
            _legacy_sidecar(config.source_hv_np_dir, config.sample_id, "wf_snp.vcf.gz"),
        )
        np_clinvar_vcf, np_clinvar_resolution = _prefer_explicit(
            config.source_clinvar_vcf_unphased,
            _legacy_sidecar(config.source_hv_np_dir, config.sample_id, "wf_snp_clinvar.vcf.gz"),
        )
        np_bedmethyl, np_bedmethyl_resolution = _prefer_explicit(
            config.source_bedmethyl,
            _legacy_sidecar(config.source_hv_np_dir, config.sample_id, "wf_mods.bedmethyl.gz"),
        )
        hp1_bedmethyl, hp1_resolution = _prefer_explicit(
            config.source_bedmethyl_hp1,
            _legacy_sidecar(config.source_hv_dir, config.sample_id, "wf_mods.1.bedmethyl.gz"),
        )
        hp2_bedmethyl, hp2_resolution = _prefer_explicit(
            config.source_bedmethyl_hp2,
            _legacy_sidecar(config.source_hv_dir, config.sample_id, "wf_mods.2.bedmethyl.gz"),
        )
        ungrouped_bedmethyl, ungrouped_resolution = _prefer_explicit(
            config.source_bedmethyl_ungrouped,
            _legacy_sidecar(config.source_hv_dir, config.sample_id, "wf_mods.ungrouped.bedmethyl.gz"),
        )
        resolution = {
            "source_variant_vcf": phased_snp_resolution,
            "source_clinvar_vcf": phased_clinvar_resolution,
            "source_variant_vcf_unphased": np_snp_resolution,
            "source_clinvar_vcf_unphased": np_clinvar_resolution,
            "source_bedmethyl": np_bedmethyl_resolution,
            "source_bedmethyl_hp1": hp1_resolution,
            "source_bedmethyl_hp2": hp2_resolution,
            "source_bedmethyl_ungrouped": ungrouped_resolution,
        }

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
            phased_snp_vcf=phased_snp_vcf,
            phased_clinvar_vcf=phased_clinvar_vcf,
            np_snp_vcf=np_snp_vcf,
            np_clinvar_vcf=np_clinvar_vcf,
            np_bedmethyl_source_gz=np_bedmethyl,
            hp1_bedmethyl_source_gz=hp1_bedmethyl,
            hp2_bedmethyl_source_gz=hp2_bedmethyl,
            ungrouped_bedmethyl_source_gz=ungrouped_bedmethyl,
            final_bioinfo_dir=final_bioinfo_dir,
            sidecar_resolution=resolution,
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
        """Return derived paths and sidecar resolution metadata."""

        rows = [
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
        rows.extend((f"{key}_resolution", value) for key, value in sorted(self.sidecar_resolution.items()))
        return rows
