"""Configuration loading and normalization for the public mito-overview package."""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar


REQUIRED_KEYS = (
    "WORK_ROOT",
    "RUN_NAME",
    "SAMPLE_ID",
    "REF_FASTA",
    "SOURCE_ALIGN_FILE",
    "MT_CONTIG",
)

DEFAULTS: dict[str, Any] = {
    "DEBUG": "0",
    "THREADS": "4",
    "SPECIES": "auto",
    "READ_MODE": "long",
    "ASSAY_TYPE": "wgs",
    "REFERENCE_SCOPE": "auto",
    "CONDA_BASE": "",
    "CONDA_ENV_PREFIX": "",
    "PIPELINE_ROOT": "",
    "SOURCE_SAMPLE_DIR": "",
    "SOURCE_HV_DIR": "",
    "SOURCE_HV_NP_DIR": "",
    "SOURCE_ALIGN_MODE": "",
    "MT_LENGTH": "",
    "FINAL_BIOINFO_DIR": "",
    "MIN_CALLABLE_DEPTH": "100",
    "MIN_ALT_ALLELE_FRACTION": "0.02",
    "ALLELE_MIN_BASE_QUALITY": "13",
    "ALLELE_MIN_MAPPING_QUALITY": "20",
    "ALLELE_MIN_READ_MEAN_QUALITY": "10",
    "ALLELE_MAX_DEPTH": "0",
    "ALLELE_EXCLUDE_FLAGS": "3844",
    "ALLELE_IGNORE_OVERLAPS": "1",
    "DELETION_MIN_SIZE": "100",
    "NUCLEAR_WINDOW_SIZE": "100000",
    "NUCLEAR_WINDOW_COUNT": "5",
    "PHYMER_ROOT": "",
    "HUMAN_MT_GTF": "",
    "PHYMER_MIN_DEPTH": "100",
    "PHYMER_MAJOR_VAF": "0.90",
    "MVTOOL_MODE": "disabled",
    "MVTOOL_API_URL": "",
    "MVTOOL_FIXTURE_JSON": "",
    "MSEQDR_TIMEOUT": "120",
    "SOURCE_VARIANT_VCF": "",
    "SOURCE_CLINVAR_VCF": "",
    "SOURCE_VARIANT_VCF_UNPHASED": "",
    "SOURCE_CLINVAR_VCF_UNPHASED": "",
    "SOURCE_BEDMETHYL": "",
    "SOURCE_BEDMETHYL_HP1": "",
    "SOURCE_BEDMETHYL_HP2": "",
    "SOURCE_BEDMETHYL_UNGROUPED": "",
}

T = TypeVar("T")


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


def detect_species(
    reference_fasta: str | Path,
    requested_species: str = "auto",
    *,
    contig_lengths: dict[str, int] | None = None,
    mt_contig: str = "",
) -> str:
    """Infer species from an explicit value, a complete profile, or the reference name."""

    requested = (requested_species or "auto").strip().lower()
    if requested not in {"", "auto"}:
        return requested
    if contig_lengths and mt_contig:
        # A present index is stronger evidence than a potentially misleading filename.
        return _infer_species_from_reference_profile(contig_lengths, mt_contig)

    build = detect_reference_build(reference_fasta)
    ref_name = Path(reference_fasta).name.lower()
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


def _parse_bool(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Expected a boolean value, received: {value}")


def _resolve_alias(
    mapping: dict[str, str],
    canonical: str,
    legacy: str,
    default: str,
    cast: Callable[[str], T],
) -> T:
    canonical_present = canonical in mapping and str(mapping[canonical]).strip() != ""
    legacy_present = legacy in mapping and str(mapping[legacy]).strip() != ""
    canonical_raw = str(mapping[canonical]).strip() if canonical_present else default
    legacy_raw = str(mapping[legacy]).strip() if legacy_present else canonical_raw
    canonical_value = cast(canonical_raw)
    legacy_value = cast(legacy_raw)
    if canonical_present and legacy_present and canonical_value != legacy_value:
        raise ValueError(
            f"Conflicting config values: {canonical}={canonical_raw} and {legacy}={legacy_raw}"
        )
    return canonical_value if canonical_present else legacy_value


def _read_fai_lengths(reference_fasta: Path) -> dict[str, int]:
    fai_path = Path(f"{reference_fasta}.fai")
    if not fai_path.exists():
        return {}
    lengths: dict[str, int] = {}
    for raw_line in fai_path.read_text(encoding="utf-8").splitlines():
        fields = raw_line.split("\t")
        if len(fields) >= 2:
            lengths[fields[0]] = int(fields[1])
    return lengths


def _detect_alignment_container(path: Path) -> str | None:
    """Return the encoded HTS container for an existing local alignment."""

    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            prefix = handle.read(4)
        if prefix == b"CRAM":
            return "cram"
        if prefix[:2] == b"\x1f\x8b":
            with gzip.open(path, "rb") as handle:
                if handle.read(4) == b"BAM\x01":
                    return "bam"
    except (EOFError, OSError):
        pass
    return "unknown"


def _infer_alignment_mode(path: Path, requested: str) -> str:
    requested = requested.strip().lower()
    suffix = path.suffix.lower()
    inferred = {".bam": "bam", ".cram": "cram"}.get(suffix)
    if requested:
        if requested not in {"bam", "cram"}:
            raise ValueError(f"Unsupported SOURCE_ALIGN_MODE: {requested}")
        if inferred is not None and requested != inferred:
            raise ValueError(
                f"SOURCE_ALIGN_MODE={requested} conflicts with "
                f"SOURCE_ALIGN_FILE extension {suffix}"
            )
        resolved = requested
    elif inferred is not None:
        resolved = inferred
    else:
        raise ValueError(
            "SOURCE_ALIGN_MODE is required when SOURCE_ALIGN_FILE is not .bam or .cram"
        )

    encoded = _detect_alignment_container(path)
    if encoded == "unknown":
        raise ValueError(f"SOURCE_ALIGN_FILE is not a recognizable BAM or CRAM container: {path}")
    if encoded is not None and encoded != resolved:
        raise ValueError(
            f"SOURCE_ALIGN_FILE content is {encoded.upper()} but resolved "
            f"SOURCE_ALIGN_MODE={resolved}"
        )
    return resolved


@dataclass(frozen=True)
class _ReferenceProfile:
    species: str
    build: str
    autosome_lengths: tuple[int, ...]
    sex_chromosome_lengths: tuple[int, int]
    mt_length: int


_REFERENCE_PROFILES = (
    _ReferenceProfile(
        species="human",
        build="GRCh37",
        autosome_lengths=(
            249_250_621,
            243_199_373,
            198_022_430,
            191_154_276,
            180_915_260,
            171_115_067,
            159_138_663,
            146_364_022,
            141_213_431,
            135_534_747,
            135_006_516,
            133_851_895,
            115_169_878,
            107_349_540,
            102_531_392,
            90_354_753,
            81_195_210,
            78_077_248,
            59_128_983,
            63_025_520,
            48_129_895,
            51_304_566,
        ),
        sex_chromosome_lengths=(155_270_560, 59_373_566),
        mt_length=16_569,
    ),
    _ReferenceProfile(
        species="human",
        build="GRCh38",
        autosome_lengths=(
            248_956_422,
            242_193_529,
            198_295_559,
            190_214_555,
            181_538_259,
            170_805_979,
            159_345_973,
            145_138_636,
            138_394_717,
            133_797_422,
            135_086_622,
            133_275_309,
            114_364_328,
            107_043_718,
            101_991_189,
            90_338_345,
            83_257_441,
            80_373_285,
            58_617_616,
            64_444_167,
            46_709_983,
            50_818_468,
        ),
        sex_chromosome_lengths=(156_040_895, 57_227_415),
        mt_length=16_569,
    ),
    _ReferenceProfile(
        species="mouse",
        build="GRCm38",
        autosome_lengths=(
            195_471_971,
            182_113_224,
            160_039_680,
            156_508_116,
            151_834_684,
            149_736_546,
            145_441_459,
            129_401_213,
            124_595_110,
            130_694_993,
            122_082_543,
            120_129_022,
            120_421_639,
            124_902_244,
            104_043_685,
            98_207_768,
            94_987_271,
            90_702_639,
            61_431_566,
        ),
        sex_chromosome_lengths=(171_031_299, 91_744_698),
        mt_length=16_299,
    ),
    _ReferenceProfile(
        species="mouse",
        build="GRCm39",
        autosome_lengths=(
            195_154_279,
            181_755_017,
            159_745_316,
            156_860_686,
            151_758_149,
            149_588_044,
            144_995_196,
            130_127_694,
            124_359_700,
            130_530_862,
            121_973_369,
            120_092_757,
            120_883_175,
            125_139_656,
            104_073_951,
            98_008_968,
            95_294_699,
            90_720_763,
            61_420_004,
        ),
        sex_chromosome_lengths=(169_476_592, 91_455_967),
        mt_length=16_299,
    ),
)


def _matches_reference_profile(
    contig_lengths: dict[str, int], mt_contig: str, profile: _ReferenceProfile
) -> bool:
    expected_nuclear_lengths = tuple(
        (str(index), length) for index, length in enumerate(profile.autosome_lengths, 1)
    ) + tuple(zip(("X", "Y"), profile.sex_chromosome_lengths, strict=True))

    # Assembly profiles are exact; standard chromosome prefixes are the only aliases.
    return any(
        contig_lengths
        == {
            mt_contig: profile.mt_length,
            **{f"{prefix}{name}": length for name, length in expected_nuclear_lengths},
        }
        for prefix in ("", "chr")
    )


def _matching_reference_profiles(
    contig_lengths: dict[str, int], mt_contig: str
) -> tuple[_ReferenceProfile, ...]:
    return tuple(
        profile
        for profile in _REFERENCE_PROFILES
        if _matches_reference_profile(contig_lengths, mt_contig, profile)
    )


def detect_reference_profile(contig_lengths: dict[str, int], mt_contig: str) -> str:
    """Return the unique exact assembly profile represented by a contig map."""

    matches = _matching_reference_profiles(contig_lengths, mt_contig)
    if len(matches) != 1:
        return "unrecognized"
    return f"{matches[0].species}:{matches[0].build}"


def detect_physical_reference_scope(contig_lengths: dict[str, int], mt_contig: str) -> str:
    """Classify a FASTA index or alignment header without configuration overrides."""

    if set(contig_lengths) == {mt_contig}:
        return "mt_only"
    if detect_reference_profile(contig_lengths, mt_contig) != "unrecognized":
        return "whole_genome"
    return "custom"


def _infer_species_from_reference_profile(
    contig_lengths: dict[str, int], mt_contig: str
) -> str:
    matched_species = {
        profile.species for profile in _matching_reference_profiles(contig_lengths, mt_contig)
    }
    return matched_species.pop() if len(matched_species) == 1 else "unknown"


def _has_recognized_nuclear_chromosome_profile(
    contig_lengths: dict[str, int], mt_contig: str, species: str
) -> bool:
    normalized_species = (species or "").strip().lower()
    return any(
        profile.species == normalized_species
        and _matches_reference_profile(contig_lengths, mt_contig, profile)
        for profile in _REFERENCE_PROFILES
    )


def detect_reference_scope(
    *,
    requested: str,
    contig_lengths: dict[str, int],
    mt_contig: str,
    species: str,
) -> str:
    """Resolve whether the supplied reference supports nuclear-context interpretation."""

    requested = (requested or "auto").strip().lower()
    allowed = {"auto", "mt_only", "whole_genome", "custom"}
    if requested not in allowed:
        raise ValueError(f"Unsupported REFERENCE_SCOPE: {requested}")
    contigs = set(contig_lengths)
    physically_inferred = "custom"
    if contigs == {mt_contig}:
        physically_inferred = "mt_only"
    elif mt_contig in contigs and _has_recognized_nuclear_chromosome_profile(
        contig_lengths, mt_contig, species
    ):
        physically_inferred = "whole_genome"
    if requested == "auto":
        return physically_inferred
    if requested == "whole_genome" and physically_inferred != "whole_genome":
        raise ValueError(
            "REFERENCE_SCOPE=whole_genome requires a recognized complete nuclear reference; "
            f"the supplied FASTA resolved as {physically_inferred}"
        )
    return requested


@dataclass(frozen=True)
class PipelineConfig:
    """Normalized portable representation of a mito-overview run configuration."""

    config_file: Path
    pipeline_root: Path
    work_root: Path
    run_name: str
    sample_id: str
    source_sample_dir: Path
    source_hv_dir: Path | None
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
    fasta_reference_scope: str
    fasta_reference_profile: str
    requested_reference_scope: str
    reference_scope: str
    read_mode: str
    assay_type: str
    conda_base: str
    conda_env_prefix: str
    final_bioinfo_dir: Path | None
    debug: bool
    min_callable_depth: int
    min_alt_allele_fraction: float
    allele_min_base_quality: int
    allele_min_mapping_quality: int
    allele_min_read_mean_quality: float
    allele_max_depth: int
    allele_exclude_flags: int
    allele_ignore_overlaps: bool
    deletion_min_size: int
    nuclear_window_size: int
    nuclear_window_count: int
    phymer_root: Path | None
    human_mt_gtf: Path | None
    phymer_min_depth: int
    phymer_major_vaf: float
    mvtool_mode: str
    mvtool_api_url: str
    mvtool_fixture_json: Path | None
    mseqdr_timeout: int
    source_variant_vcf: Path | None
    source_clinvar_vcf: Path | None
    source_variant_vcf_unphased: Path | None
    source_clinvar_vcf_unphased: Path | None
    source_bedmethyl: Path | None
    source_bedmethyl_hp1: Path | None
    source_bedmethyl_hp2: Path | None
    source_bedmethyl_ungrouped: Path | None

    @classmethod
    def from_env_file(cls, path: str | Path) -> "PipelineConfig":
        return cls.from_mapping(parse_env_file(path), config_file=path)

    @classmethod
    def from_mapping(cls, mapping: dict[str, str], config_file: str | Path = "<mapping>") -> "PipelineConfig":
        merged = {**DEFAULTS, **mapping}
        missing = [key for key in REQUIRED_KEYS if not merged.get(key)]
        if missing:
            raise ValueError(f"Missing required config keys: {', '.join(missing)}")

        base_dir = _config_base_dir(config_file)
        ref_fasta = _resolve_path(str(merged["REF_FASTA"]), base_dir)
        source_align_file = _resolve_path(str(merged["SOURCE_ALIGN_FILE"]), base_dir)
        source_align_mode = _infer_alignment_mode(source_align_file, str(merged["SOURCE_ALIGN_MODE"]))
        mt_contig = str(merged["MT_CONTIG"]).strip()
        fai_lengths = _read_fai_lengths(ref_fasta)
        mt_length_raw = str(merged["MT_LENGTH"]).strip()
        if mt_length_raw:
            mt_length = int(mt_length_raw)
        elif mt_contig in fai_lengths:
            mt_length = fai_lengths[mt_contig]
        else:
            raise ValueError(
                f"MT_LENGTH was omitted and {ref_fasta}.fai does not define contig {mt_contig}"
            )

        requested_species = str(merged["SPECIES"])
        detected_species = detect_species(
            ref_fasta,
            requested_species,
            contig_lengths=fai_lengths,
            mt_contig=mt_contig,
        )
        reference_scope = detect_reference_scope(
            requested=str(merged["REFERENCE_SCOPE"]),
            contig_lengths=fai_lengths,
            mt_contig=mt_contig,
            species=detected_species,
        )
        fasta_reference_scope = detect_physical_reference_scope(fai_lengths, mt_contig)
        fasta_reference_profile = detect_reference_profile(fai_lengths, mt_contig)
        read_mode = str(merged["READ_MODE"]).strip().lower()
        assay_type = str(merged["ASSAY_TYPE"]).strip().lower()
        mvtool_mode = str(merged["MVTOOL_MODE"]).strip().lower()
        if read_mode not in {"long", "short"}:
            raise ValueError(f"Unsupported READ_MODE: {read_mode}")
        if assay_type not in {"wgs", "targeted_mt"}:
            raise ValueError(f"Unsupported ASSAY_TYPE: {assay_type}")
        if mvtool_mode not in {"disabled", "fixture", "network"}:
            raise ValueError(f"Unsupported MVTOOL_MODE: {mvtool_mode}")
        if mvtool_mode == "network" and not str(merged["MVTOOL_API_URL"]).strip():
            raise ValueError("MVTOOL_MODE=network requires a nonempty MVTOOL_API_URL")

        pipeline_default = Path(__file__).resolve().parents[1]
        pipeline_root = _optional_path(str(merged["PIPELINE_ROOT"]), base_dir) or pipeline_default
        source_sample_dir = _optional_path(str(merged["SOURCE_SAMPLE_DIR"]), base_dir) or source_align_file.parent
        min_callable_depth = _resolve_alias(
            mapping,
            "MIN_CALLABLE_DEPTH",
            "HET_MIN_DEPTH",
            str(DEFAULTS["MIN_CALLABLE_DEPTH"]),
            int,
        )
        min_alt_allele_fraction = _resolve_alias(
            mapping,
            "MIN_ALT_ALLELE_FRACTION",
            "HET_MIN_VAF",
            str(DEFAULTS["MIN_ALT_ALLELE_FRACTION"]),
            float,
        )

        config = cls(
            config_file=Path(config_file),
            pipeline_root=pipeline_root,
            work_root=_resolve_path(str(merged["WORK_ROOT"]), base_dir),
            run_name=str(merged["RUN_NAME"]),
            sample_id=str(merged["SAMPLE_ID"]),
            source_sample_dir=source_sample_dir,
            source_hv_dir=_optional_path(str(merged["SOURCE_HV_DIR"]), base_dir),
            source_hv_np_dir=_optional_path(str(merged["SOURCE_HV_NP_DIR"]), base_dir),
            ref_fasta=ref_fasta,
            source_align_file=source_align_file,
            source_align_mode=source_align_mode,
            mt_contig=mt_contig,
            mt_length=mt_length,
            threads=int(merged["THREADS"]),
            requested_species=requested_species,
            detected_species=detected_species,
            reference_build_guess=detect_reference_build(ref_fasta),
            fasta_reference_scope=fasta_reference_scope,
            fasta_reference_profile=fasta_reference_profile,
            requested_reference_scope=str(merged["REFERENCE_SCOPE"]).strip().lower(),
            reference_scope=reference_scope,
            read_mode=read_mode,
            assay_type=assay_type,
            conda_base=str(merged["CONDA_BASE"]),
            conda_env_prefix=str(merged["CONDA_ENV_PREFIX"]),
            final_bioinfo_dir=_optional_path(str(merged["FINAL_BIOINFO_DIR"]), base_dir),
            debug=_parse_bool(str(merged["DEBUG"])),
            min_callable_depth=min_callable_depth,
            min_alt_allele_fraction=min_alt_allele_fraction,
            allele_min_base_quality=int(merged["ALLELE_MIN_BASE_QUALITY"]),
            allele_min_mapping_quality=int(merged["ALLELE_MIN_MAPPING_QUALITY"]),
            allele_min_read_mean_quality=float(merged["ALLELE_MIN_READ_MEAN_QUALITY"]),
            allele_max_depth=int(merged["ALLELE_MAX_DEPTH"]),
            allele_exclude_flags=int(str(merged["ALLELE_EXCLUDE_FLAGS"]), 0),
            allele_ignore_overlaps=_parse_bool(str(merged["ALLELE_IGNORE_OVERLAPS"])),
            deletion_min_size=int(merged["DELETION_MIN_SIZE"]),
            nuclear_window_size=int(merged["NUCLEAR_WINDOW_SIZE"]),
            nuclear_window_count=int(merged["NUCLEAR_WINDOW_COUNT"]),
            phymer_root=_optional_path(str(merged["PHYMER_ROOT"]), base_dir),
            human_mt_gtf=_optional_path(str(merged["HUMAN_MT_GTF"]), base_dir),
            phymer_min_depth=int(merged["PHYMER_MIN_DEPTH"]),
            phymer_major_vaf=float(merged["PHYMER_MAJOR_VAF"]),
            mvtool_mode=mvtool_mode,
            mvtool_api_url=str(merged["MVTOOL_API_URL"]).strip(),
            mvtool_fixture_json=_optional_path(str(merged["MVTOOL_FIXTURE_JSON"]), base_dir),
            mseqdr_timeout=int(merged["MSEQDR_TIMEOUT"]),
            source_variant_vcf=_optional_path(str(merged["SOURCE_VARIANT_VCF"]), base_dir),
            source_clinvar_vcf=_optional_path(str(merged["SOURCE_CLINVAR_VCF"]), base_dir),
            source_variant_vcf_unphased=_optional_path(str(merged["SOURCE_VARIANT_VCF_UNPHASED"]), base_dir),
            source_clinvar_vcf_unphased=_optional_path(str(merged["SOURCE_CLINVAR_VCF_UNPHASED"]), base_dir),
            source_bedmethyl=_optional_path(str(merged["SOURCE_BEDMETHYL"]), base_dir),
            source_bedmethyl_hp1=_optional_path(str(merged["SOURCE_BEDMETHYL_HP1"]), base_dir),
            source_bedmethyl_hp2=_optional_path(str(merged["SOURCE_BEDMETHYL_HP2"]), base_dir),
            source_bedmethyl_ungrouped=_optional_path(str(merged["SOURCE_BEDMETHYL_UNGROUPED"]), base_dir),
        )
        config._validate_numeric_values()
        return config

    def _validate_numeric_values(self) -> None:
        if self.mt_length <= 0:
            raise ValueError("MT_LENGTH must be positive")
        if self.min_callable_depth < 0:
            raise ValueError("MIN_CALLABLE_DEPTH cannot be negative")
        if not 0 <= self.min_alt_allele_fraction <= 1:
            raise ValueError("MIN_ALT_ALLELE_FRACTION must be between 0 and 1")
        for label, value in (
            ("ALLELE_MIN_BASE_QUALITY", self.allele_min_base_quality),
            ("ALLELE_MIN_MAPPING_QUALITY", self.allele_min_mapping_quality),
            ("ALLELE_MIN_READ_MEAN_QUALITY", self.allele_min_read_mean_quality),
            ("ALLELE_MAX_DEPTH", self.allele_max_depth),
        ):
            if value < 0:
                raise ValueError(f"{label} cannot be negative")
        if self.threads <= 0 or self.nuclear_window_size <= 0 or self.nuclear_window_count <= 0:
            raise ValueError("THREADS and nuclear window settings must be positive")

    @property
    def het_min_depth(self) -> int:
        """Compatibility alias for the former configuration name."""

        return self.min_callable_depth

    @property
    def het_min_vaf(self) -> float:
        """Compatibility alias for the former configuration name."""

        return self.min_alt_allele_fraction

    def context_rows(self) -> list[tuple[str, str]]:
        """Return key run metadata in a table-friendly order."""

        return [
            ("config_file", str(self.config_file)),
            ("run_name", self.run_name),
            ("sample_id", self.sample_id),
            ("source_sample_dir", str(self.source_sample_dir)),
            ("source_hv_dir", str(self.source_hv_dir or "")),
            ("source_hv_np_dir", str(self.source_hv_np_dir or "")),
            ("reference_fasta", str(self.ref_fasta)),
            ("source_align_file", str(self.source_align_file)),
            ("source_align_mode", self.source_align_mode),
            ("read_mode", self.read_mode),
            ("assay_type", self.assay_type),
            ("species_requested", self.requested_species),
            ("species_detected", self.detected_species),
            ("reference_build_guess", self.reference_build_guess),
            ("reference_scope_requested", self.requested_reference_scope),
            ("reference_scope_fasta", self.fasta_reference_scope),
            ("reference_profile_fasta", self.fasta_reference_profile),
            ("reference_scope_configured", self.reference_scope),
            ("reference_scope_resolved", self.reference_scope),
            ("mt_contig", self.mt_contig),
            ("mt_length", str(self.mt_length)),
            ("threads", str(self.threads)),
            ("min_callable_depth", str(self.min_callable_depth)),
            ("min_alt_allele_fraction", str(self.min_alt_allele_fraction)),
            ("allele_min_base_quality", str(self.allele_min_base_quality)),
            ("allele_min_mapping_quality", str(self.allele_min_mapping_quality)),
            ("allele_min_read_mean_quality", str(self.allele_min_read_mean_quality)),
            ("allele_max_depth", str(self.allele_max_depth)),
            ("allele_exclude_flags", str(self.allele_exclude_flags)),
            ("allele_ignore_overlaps", str(int(self.allele_ignore_overlaps))),
            ("deletion_min_size", str(self.deletion_min_size)),
            ("human_mt_gtf", str(self.human_mt_gtf or "")),
            ("mvtool_mode", self.mvtool_mode),
            ("mvtool_api_url", self.mvtool_api_url if self.mvtool_mode == "network" else ""),
            ("mvtool_fixture_json", str(self.mvtool_fixture_json or "")),
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
