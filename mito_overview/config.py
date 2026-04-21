"""Configuration loading and normalization for the public mito-overview package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_KEYS = (
    "PIPELINE_ROOT",
    "WORK_ROOT",
    "RUN_NAME",
    "SAMPLE_ID",
    "SOURCE_SAMPLE_DIR",
    "SOURCE_HV_DIR",
    "REF_FASTA",
    "SOURCE_ALIGN_FILE",
    "SOURCE_ALIGN_MODE",
    "MT_CONTIG",
    "MT_LENGTH",
)

DEFAULTS: dict[str, Any] = {
    "DEBUG": "0",
    "THREADS": "4",
    "SPECIES": "auto",
    "READ_MODE": "long",
    "ASSAY_TYPE": "wgs",
    "CONDA_BASE": "",
    "CONDA_ENV_PREFIX": "",
    "SOURCE_HV_NP_DIR": "",
    "FINAL_BIOINFO_DIR": "",
    "HET_MIN_DEPTH": "100",
    "HET_MIN_VAF": "0.02",
    "DELETION_MIN_SIZE": "100",
    "NUCLEAR_WINDOW_SIZE": "100000",
    "NUCLEAR_WINDOW_COUNT": "5",
    "PHYMER_ROOT": "",
    "HUMAN_MT_GTF": "",
    "PHYMER_MIN_DEPTH": "100",
    "PHYMER_MAJOR_VAF": "0.90",
    "MVTOOL_API_URL": "https://mseqdr.org/mtannotapi.php?format=hgvs",
    "MSEQDR_TIMEOUT": "120",
}


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse a shell-style KEY=VALUE configuration file."""

    path = Path(path)
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _strip_quotes(value)
    return values


def detect_reference_build(reference_fasta: str | Path) -> str:
    """Guess the reference build from the FASTA name."""

    ref_name = Path(reference_fasta).name.lower()
    if any(token in ref_name for token in ("mm39", "grcm39")):
        return "mm39"
    if any(token in ref_name for token in ("mm10", "grcm38")):
        return "mm10"
    if any(token in ref_name for token in ("hg38", "grch38")):
        return "hg38"
    if any(token in ref_name for token in ("hg19", "grch37")):
        return "hg19"
    return "unknown"


def detect_species(reference_fasta: str | Path, requested_species: str = "auto") -> str:
    """Infer species from the requested value and reference name."""

    requested = (requested_species or "auto").strip().lower()
    build = detect_reference_build(reference_fasta)
    ref_name = Path(reference_fasta).name.lower()
    if requested not in {"", "auto"}:
        return requested
    if build in {"mm10", "mm39"} or "mouse" in ref_name or "mus" in ref_name:
        return "mouse"
    if build in {"hg19", "hg38"} or "human" in ref_name or "grch" in ref_name:
        return "human"
    return "unknown"


def _config_base_dir(config_file: str | Path) -> Path | None:
    config_path = Path(config_file)
    if str(config_path).startswith("<"):
        return None
    return config_path.expanduser().resolve().parent


def _resolve_path(value: str, base_dir: Path | None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute() or base_dir is None:
        return path
    return (base_dir / path).resolve()


def _optional_path(value: str, base_dir: Path | None) -> Path | None:
    value = (value or "").strip()
    return _resolve_path(value, base_dir) if value else None


@dataclass(frozen=True)
class PipelineConfig:
    """Normalized portable representation of a mito-overview run configuration."""

    config_file: Path
    pipeline_root: Path
    work_root: Path
    run_name: str
    sample_id: str
    source_sample_dir: Path
    source_hv_dir: Path
    source_hv_np_dir: Path | None
    ref_fasta: Path
    source_align_file: Path
    source_align_mode: str
    mt_contig: str
    mt_length: int
    threads: int
    requested_species: str
    detected_species: str
    reference_build_guess: str
    read_mode: str
    assay_type: str
    conda_base: str
    conda_env_prefix: str
    final_bioinfo_dir: Path | None
    debug: bool
    het_min_depth: int
    het_min_vaf: float
    deletion_min_size: int
    nuclear_window_size: int
    nuclear_window_count: int
    phymer_root: Path | None
    human_mt_gtf: Path | None
    phymer_min_depth: int
    phymer_major_vaf: float
    mvtool_api_url: str
    mseqdr_timeout: int

    @classmethod
    def from_env_file(cls, path: str | Path) -> "PipelineConfig":
        return cls.from_mapping(parse_env_file(path), config_file=path)

    @classmethod
    def from_mapping(cls, mapping: dict[str, str], config_file: str | Path = "<mapping>") -> "PipelineConfig":
        merged = {**DEFAULTS, **mapping}
        missing = [key for key in REQUIRED_KEYS if not merged.get(key)]
        if missing:
            missing_str = ", ".join(missing)
            raise ValueError(f"Missing required config keys: {missing_str}")

        base_dir = _config_base_dir(config_file)
        ref_fasta = _resolve_path(merged["REF_FASTA"], base_dir)
        requested_species = merged["SPECIES"]
        read_mode = merged["READ_MODE"].strip().lower()
        assay_type = merged["ASSAY_TYPE"].strip().lower()
        if read_mode not in {"long", "short"}:
            raise ValueError(f"Unsupported READ_MODE: {read_mode}")
        if assay_type not in {"wgs", "targeted_mt"}:
            raise ValueError(f"Unsupported ASSAY_TYPE: {assay_type}")
        return cls(
            config_file=Path(config_file),
            pipeline_root=_resolve_path(merged["PIPELINE_ROOT"], base_dir),
            work_root=_resolve_path(merged["WORK_ROOT"], base_dir),
            run_name=merged["RUN_NAME"],
            sample_id=merged["SAMPLE_ID"],
            source_sample_dir=_resolve_path(merged["SOURCE_SAMPLE_DIR"], base_dir),
            source_hv_dir=_resolve_path(merged["SOURCE_HV_DIR"], base_dir),
            source_hv_np_dir=_optional_path(merged["SOURCE_HV_NP_DIR"], base_dir),
            ref_fasta=ref_fasta,
            source_align_file=_resolve_path(merged["SOURCE_ALIGN_FILE"], base_dir),
            source_align_mode=merged["SOURCE_ALIGN_MODE"],
            mt_contig=merged["MT_CONTIG"],
            mt_length=int(merged["MT_LENGTH"]),
            threads=int(merged["THREADS"]),
            requested_species=requested_species,
            detected_species=detect_species(ref_fasta, requested_species),
            reference_build_guess=detect_reference_build(ref_fasta),
            read_mode=read_mode,
            assay_type=assay_type,
            conda_base=merged["CONDA_BASE"],
            conda_env_prefix=merged["CONDA_ENV_PREFIX"],
            final_bioinfo_dir=_optional_path(merged["FINAL_BIOINFO_DIR"], base_dir),
            debug=merged["DEBUG"] in {"1", "true", "TRUE", "yes", "YES"},
            het_min_depth=int(merged["HET_MIN_DEPTH"]),
            het_min_vaf=float(merged["HET_MIN_VAF"]),
            deletion_min_size=int(merged["DELETION_MIN_SIZE"]),
            nuclear_window_size=int(merged["NUCLEAR_WINDOW_SIZE"]),
            nuclear_window_count=int(merged["NUCLEAR_WINDOW_COUNT"]),
            phymer_root=_optional_path(merged["PHYMER_ROOT"], base_dir),
            human_mt_gtf=_optional_path(merged["HUMAN_MT_GTF"], base_dir),
            phymer_min_depth=int(merged["PHYMER_MIN_DEPTH"]),
            phymer_major_vaf=float(merged["PHYMER_MAJOR_VAF"]),
            mvtool_api_url=merged["MVTOOL_API_URL"],
            mseqdr_timeout=int(merged["MSEQDR_TIMEOUT"]),
        )

    def context_rows(self) -> list[tuple[str, str]]:
        """Return key run metadata in a table-friendly order."""

        return [
            ("config_file", str(self.config_file)),
            ("run_name", self.run_name),
            ("sample_id", self.sample_id),
            ("source_sample_dir", str(self.source_sample_dir)),
            ("source_hv_dir", str(self.source_hv_dir)),
            ("source_hv_np_dir", str(self.source_hv_np_dir or "")),
            ("reference_fasta", str(self.ref_fasta)),
            ("source_align_file", str(self.source_align_file)),
            ("source_align_mode", self.source_align_mode),
            ("read_mode", self.read_mode),
            ("assay_type", self.assay_type),
            ("species_requested", self.requested_species),
            ("species_detected", self.detected_species),
            ("reference_build_guess", self.reference_build_guess),
            ("mt_contig", self.mt_contig),
            ("mt_length", str(self.mt_length)),
            ("threads", str(self.threads)),
            ("het_min_depth", str(self.het_min_depth)),
            ("het_min_vaf", str(self.het_min_vaf)),
            ("deletion_min_size", str(self.deletion_min_size)),
            ("human_mt_gtf", str(self.human_mt_gtf or "")),
            ("mvtool_api_url", self.mvtool_api_url),
        ]

    @property
    def is_short_read(self) -> bool:
        return self.read_mode == "short"

    @property
    def is_long_read(self) -> bool:
        return self.read_mode == "long"

    @property
    def is_wgs(self) -> bool:
        return self.assay_type == "wgs"

    @property
    def is_targeted_mt(self) -> bool:
        return self.assay_type == "targeted_mt"
