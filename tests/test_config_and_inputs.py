from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mito_overview.config import PipelineConfig
from mito_overview.paths import RunPaths
from mito_overview.steps.mito_copy_number import WINDOW_COLUMNS
from mito_overview.steps.mito_cosegregation import PAIRWISE_COLUMNS
from mito_overview.steps.mito_identity_qc import FINGERPRINT_COLUMNS
from mito_overview.workflow import STEP_STATUS_OUTPUTS, run_pipeline, validate_config

from ._helpers import ReadSpec, write_alignment, write_fasta


GRCH38_AUTOSOME_LENGTHS = (
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
)
GRCM39_AUTOSOME_LENGTHS = (
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
)


def complete_reference_contigs(
    autosome_lengths: tuple[int, ...],
    sex_chromosome_lengths: tuple[int, int],
    mt_length: int,
) -> dict[str, int]:
    return {
        "MT": mt_length,
        **{str(index): length for index, length in enumerate(autosome_lengths, 1)},
        "X": sex_chromosome_lengths[0],
        "Y": sex_chromosome_lengths[1],
    }


def write_fai_stub(reference: Path, contig_lengths: dict[str, int]) -> Path:
    reference.write_text(">placeholder\nA\n", encoding="ascii")
    Path(f"{reference}.fai").write_text(
        "".join(f"{name}\t{length}\t0\t1\t2\n" for name, length in contig_lengths.items()),
        encoding="ascii",
    )
    return reference


def minimal_mapping(root: Path, ref: Path, alignment: Path) -> dict[str, str]:
    return {
        "WORK_ROOT": str(root / "runs"),
        "RUN_NAME": "minimal",
        "SAMPLE_ID": "S1",
        "REF_FASTA": str(ref),
        "SOURCE_ALIGN_FILE": str(alignment),
        "MT_CONTIG": "MT",
    }


@pytest.fixture
def minimal_inputs(tmp_path: Path) -> tuple[Path, Path]:
    ref = write_fasta(tmp_path / "minimal.fa", {"MT": "A" * 10})
    bam = write_alignment(
        tmp_path / "minimal.bam",
        {"MT": 10},
        [ReadSpec("read1", "MT", 0, "A" * 10)],
    )
    return ref, bam


def test_minimal_bam_contract_infers_mode_length_and_scope(
    minimal_inputs: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref, bam = minimal_inputs
    config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, ref, bam))
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")
    assert config.source_align_mode == "bam"
    assert config.mt_length == 10
    assert config.detected_species == "unknown"
    assert config.reference_scope == "mt_only"
    assert config.mvtool_mode == "disabled"
    assert validate_config(config) == []


@pytest.mark.parametrize(
    ("expected_species", "autosome_lengths", "sex_chromosome_lengths", "mt_length"),
    [
        pytest.param(
            "human",
            GRCH38_AUTOSOME_LENGTHS,
            (156_040_895, 57_227_415),
            16_569,
            id="human-grch38",
        ),
        pytest.param(
            "mouse",
            GRCM39_AUTOSOME_LENGTHS,
            (169_476_592, 91_455_967),
            16_299,
            id="mouse-grcm39",
        ),
    ],
)
def test_six_key_generic_reference_infers_species_from_complete_profile(
    expected_species: str,
    autosome_lengths: tuple[int, ...],
    sex_chromosome_lengths: tuple[int, int],
    mt_length: int,
    tmp_path: Path,
) -> None:
    contigs = complete_reference_contigs(
        autosome_lengths, sex_chromosome_lengths, mt_length
    )
    ref = write_fai_stub(tmp_path / "reference.fa", contigs)
    mapping = minimal_mapping(tmp_path, ref, tmp_path / "input.bam")

    config = PipelineConfig.from_mapping(mapping)

    assert len(mapping) == 6
    assert config.requested_species == "auto"
    assert config.detected_species == expected_species
    assert config.reference_build_guess == "unknown"
    assert config.reference_scope == "whole_genome"


@pytest.mark.parametrize(
    "contigs",
    [
        pytest.param(
            {
                "MT": 16_569,
                "1": GRCH38_AUTOSOME_LENGTHS[0],
                "X": 156_040_895,
                "Y": 57_227_415,
            },
            id="reduced-human-reference",
        ),
        pytest.param(
            complete_reference_contigs(
                GRCH38_AUTOSOME_LENGTHS,
                (156_040_895, 57_227_415),
                16_570,
            ),
            id="wrong-mt-length",
        ),
        pytest.param(
            {
                name: length if name == "MT" else length * 99 // 100
                for name, length in complete_reference_contigs(
                    GRCH38_AUTOSOME_LENGTHS,
                    (156_040_895, 57_227_415),
                    16_569,
                ).items()
            },
            id="scaled-human-profile",
        ),
        pytest.param(
            {
                **complete_reference_contigs(
                    GRCH38_AUTOSOME_LENGTHS,
                    (156_040_895, 57_227_415),
                    16_569,
                ),
                "chrUn_hybrid": 10_000,
            },
            id="extra-hybrid-contig",
        ),
    ],
)
def test_six_key_generic_reference_does_not_infer_species_from_ambiguous_profile(
    contigs: dict[str, int], tmp_path: Path
) -> None:
    ref = write_fai_stub(tmp_path / "human_reference.fa", contigs)
    mapping = minimal_mapping(tmp_path, ref, tmp_path / "input.bam")

    config = PipelineConfig.from_mapping(mapping)

    assert len(mapping) == 6
    assert config.detected_species == "unknown"
    assert config.reference_scope == "custom"


def test_explicit_species_overrides_complete_profile_inference(tmp_path: Path) -> None:
    contigs = complete_reference_contigs(
        GRCH38_AUTOSOME_LENGTHS,
        (156_040_895, 57_227_415),
        16_569,
    )
    ref = write_fai_stub(tmp_path / "reference.fa", contigs)
    mapping = minimal_mapping(tmp_path, ref, tmp_path / "input.bam")
    mapping["SPECIES"] = "mouse"

    config = PipelineConfig.from_mapping(mapping)

    assert config.requested_species == "mouse"
    assert config.detected_species == "mouse"
    assert config.reference_scope == "custom"


def test_status_only_table_schemas_match_active_module_contracts() -> None:
    empty_tables = {
        step: spec["empty_tables"]  # type: ignore[index]
        for step, spec in STEP_STATUS_OUTPUTS.items()
    }
    assert empty_tables["copy_number"]["mito_copy_number_windows.tsv"] == WINDOW_COLUMNS
    assert empty_tables["cosegregation"]["mito_cosegregation_pairwise.tsv"] == PAIRWISE_COLUMNS
    assert empty_tables["identity_qc"]["mito_identity_major_variant_fingerprint.tsv"] == (
        FINGERPRINT_COLUMNS
    )


def test_minimal_cram_contract_opens_with_reference(
    minimal_inputs: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref, _ = minimal_inputs
    cram = write_alignment(
        tmp_path / "minimal.cram",
        {"MT": 10},
        [ReadSpec("read1", "MT", 0, "A" * 10)],
        reference_fasta=ref,
    )
    config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, ref, cram))
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")
    assert config.source_align_mode == "cram"
    assert validate_config(config) == []


@pytest.mark.parametrize(
    ("extension", "requested_mode"),
    [
        pytest.param(".bam", "cram", id="bam-declared-cram"),
        pytest.param(".cram", "bam", id="cram-declared-bam"),
    ],
)
def test_explicit_alignment_mode_cannot_conflict_with_recognized_extension(
    minimal_inputs: tuple[Path, Path],
    tmp_path: Path,
    extension: str,
    requested_mode: str,
) -> None:
    ref, bam = minimal_inputs
    alignment = bam
    if extension == ".cram":
        alignment = write_alignment(
            tmp_path / "minimal.cram",
            {"MT": 10},
            [ReadSpec("read1", "MT", 0, "A" * 10)],
            reference_fasta=ref,
        )
    mapping = minimal_mapping(tmp_path, ref, alignment)
    mapping["SOURCE_ALIGN_MODE"] = requested_mode

    with pytest.raises(
        ValueError,
        match=rf"SOURCE_ALIGN_MODE={requested_mode} conflicts with .*{extension}",
    ):
        PipelineConfig.from_mapping(mapping)


@pytest.mark.parametrize(
    ("source_format", "disguised_name", "requested_mode", "expected_encoded"),
    [
        pytest.param("cram", "disguised.bam", "bam", "CRAM", id="cram-as-bam"),
        pytest.param("bam", "disguised.cram", "cram", "BAM", id="bam-as-cram"),
        pytest.param("cram", "disguised.dat", "bam", "CRAM", id="cram-as-generic-bam"),
    ],
)
def test_resolved_alignment_mode_must_match_encoded_container(
    minimal_inputs: tuple[Path, Path],
    tmp_path: Path,
    source_format: str,
    disguised_name: str,
    requested_mode: str,
    expected_encoded: str,
) -> None:
    ref, bam = minimal_inputs
    source = bam
    if source_format == "cram":
        source = write_alignment(
            tmp_path / "source.cram",
            {"MT": 10},
            [ReadSpec("read1", "MT", 0, "A" * 10)],
            reference_fasta=ref,
        )
    disguised = tmp_path / disguised_name
    shutil.copyfile(source, disguised)
    mapping = minimal_mapping(tmp_path, ref, disguised)
    mapping["SOURCE_ALIGN_MODE"] = requested_mode

    with pytest.raises(
        ValueError,
        match=rf"SOURCE_ALIGN_FILE content is {expected_encoded}.*{requested_mode}",
    ):
        PipelineConfig.from_mapping(mapping)


def test_unrecognized_alignment_container_fails_before_execution(
    minimal_inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    ref, _ = minimal_inputs
    invalid = tmp_path / "invalid.bam"
    invalid.write_bytes(b"not-an-hts-container")
    mapping = minimal_mapping(tmp_path, ref, invalid)

    with pytest.raises(ValueError, match="not a recognizable BAM or CRAM container"):
        PipelineConfig.from_mapping(mapping)


def test_canonical_and_legacy_threshold_conflict_fails(minimal_inputs: tuple[Path, Path], tmp_path: Path) -> None:
    ref, bam = minimal_inputs
    mapping = minimal_mapping(tmp_path, ref, bam)
    mapping.update({"MIN_CALLABLE_DEPTH": "100", "HET_MIN_DEPTH": "99"})
    with pytest.raises(ValueError, match="Conflicting config values"):
        PipelineConfig.from_mapping(mapping)


def test_matching_legacy_thresholds_remain_compatible(minimal_inputs: tuple[Path, Path], tmp_path: Path) -> None:
    ref, bam = minimal_inputs
    mapping = minimal_mapping(tmp_path, ref, bam)
    mapping.update(
        {
            "MIN_CALLABLE_DEPTH": "25",
            "HET_MIN_DEPTH": "25",
            "MIN_ALT_ALLELE_FRACTION": "0.05",
            "HET_MIN_VAF": "0.05",
        }
    )
    config = PipelineConfig.from_mapping(mapping)
    assert config.min_callable_depth == 25
    assert config.min_alt_allele_fraction == pytest.approx(0.05)


def test_explicit_sidecar_overrides_legacy_and_missing_is_nonfatal(
    minimal_inputs: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref, bam = minimal_inputs
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    legacy = legacy_dir / "S1.wf_snp.vcf.gz"
    legacy.write_bytes(b"legacy")
    explicit = tmp_path / "explicit.vcf.gz"
    explicit.write_bytes(b"explicit")
    mapping = minimal_mapping(tmp_path, ref, bam)
    mapping.update({"SOURCE_HV_DIR": str(legacy_dir), "SOURCE_VARIANT_VCF": str(explicit)})
    paths = RunPaths.from_config(PipelineConfig.from_mapping(mapping))
    assert paths.phased_snp_vcf == explicit
    assert paths.sidecar_resolution["source_variant_vcf"] == "explicit"

    mapping["SOURCE_VARIANT_VCF"] = str(tmp_path / "missing.vcf.gz")
    config = PipelineConfig.from_mapping(mapping)
    paths = RunPaths.from_config(config)
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")
    assert paths.sidecar_resolution["source_variant_vcf"] == "explicit_missing"
    assert validate_config(config, strict_files=False) == []
    assert any("SOURCE_VARIANT_VCF" in issue for issue in validate_config(config, strict_files=True))


@pytest.mark.parametrize(
    ("config_key", "path_attribute", "resolution_key", "legacy_dir_key", "legacy_suffix"),
    [
        ("SOURCE_VARIANT_VCF", "phased_snp_vcf", "source_variant_vcf", "SOURCE_HV_DIR", "wf_snp.vcf.gz"),
        (
            "SOURCE_CLINVAR_VCF",
            "phased_clinvar_vcf",
            "source_clinvar_vcf",
            "SOURCE_HV_DIR",
            "wf_snp_clinvar.vcf.gz",
        ),
        (
            "SOURCE_VARIANT_VCF_UNPHASED",
            "np_snp_vcf",
            "source_variant_vcf_unphased",
            "SOURCE_HV_NP_DIR",
            "wf_snp.vcf.gz",
        ),
        (
            "SOURCE_CLINVAR_VCF_UNPHASED",
            "np_clinvar_vcf",
            "source_clinvar_vcf_unphased",
            "SOURCE_HV_NP_DIR",
            "wf_snp_clinvar.vcf.gz",
        ),
        (
            "SOURCE_BEDMETHYL",
            "np_bedmethyl_source_gz",
            "source_bedmethyl",
            "SOURCE_HV_NP_DIR",
            "wf_mods.bedmethyl.gz",
        ),
        (
            "SOURCE_BEDMETHYL_HP1",
            "hp1_bedmethyl_source_gz",
            "source_bedmethyl_hp1",
            "SOURCE_HV_DIR",
            "wf_mods.1.bedmethyl.gz",
        ),
        (
            "SOURCE_BEDMETHYL_HP2",
            "hp2_bedmethyl_source_gz",
            "source_bedmethyl_hp2",
            "SOURCE_HV_DIR",
            "wf_mods.2.bedmethyl.gz",
        ),
        (
            "SOURCE_BEDMETHYL_UNGROUPED",
            "ungrouped_bedmethyl_source_gz",
            "source_bedmethyl_ungrouped",
            "SOURCE_HV_DIR",
            "wf_mods.ungrouped.bedmethyl.gz",
        ),
    ],
)
def test_explicit_precedence_for_every_generic_sidecar(
    config_key: str,
    path_attribute: str,
    resolution_key: str,
    legacy_dir_key: str,
    legacy_suffix: str,
    minimal_inputs: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    ref, bam = minimal_inputs
    legacy_dir = tmp_path / f"legacy-{config_key.lower()}"
    legacy_dir.mkdir()
    legacy = legacy_dir / f"S1.{legacy_suffix}"
    legacy.write_bytes(b"legacy")
    explicit = tmp_path / f"explicit-{config_key.lower()}.dat"
    explicit.write_bytes(b"explicit")
    mapping = minimal_mapping(tmp_path, ref, bam)
    mapping.update({legacy_dir_key: str(legacy_dir), config_key: str(explicit)})

    paths = RunPaths.from_config(PipelineConfig.from_mapping(mapping))

    assert getattr(paths, path_attribute) == explicit
    assert paths.sidecar_resolution[resolution_key] == "explicit"


def test_legacy_sidecar_discovery_requires_an_existing_file(
    minimal_inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    ref, bam = minimal_inputs
    legacy_dir = tmp_path / "legacy_only"
    legacy_dir.mkdir()
    mapping = minimal_mapping(tmp_path, ref, bam)
    mapping["SOURCE_HV_DIR"] = str(legacy_dir)
    paths = RunPaths.from_config(PipelineConfig.from_mapping(mapping))
    assert paths.phased_snp_vcf is None
    assert paths.sidecar_resolution["source_variant_vcf"] == "absent"

    legacy = legacy_dir / "S1.wf_snp.vcf.gz"
    legacy.write_bytes(b"legacy")
    paths = RunPaths.from_config(PipelineConfig.from_mapping(mapping))
    assert paths.phased_snp_vcf == legacy
    assert paths.sidecar_resolution["source_variant_vcf"] == "legacy_discovery"


def test_cram_reference_removal_fails_preflight(
    minimal_inputs: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref, _ = minimal_inputs
    cram = write_alignment(
        tmp_path / "reference_required.cram",
        {"MT": 10},
        [ReadSpec("read1", "MT", 0, "A" * 10)],
        reference_fasta=ref,
    )
    config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, ref, cram))
    ref.unlink()
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")
    issues = validate_config(config)
    assert any("Missing required path for ref_fasta" in issue for issue in issues)
    assert any("CRAM input requires" in issue for issue in issues)


def test_normal_execution_cannot_bypass_preflight_when_validate_is_omitted(
    minimal_inputs: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref, _ = minimal_inputs
    bam = write_alignment(tmp_path / "unindexed.bam", {"MT": 10}, [ReadSpec("r", "MT", 0, "A")])
    Path(f"{bam}.bai").unlink()
    config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, ref, bam))
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")
    with pytest.raises(ValueError, match="Preflight failed: Missing BAM index"):
        run_pipeline(config, steps=["stage"])


@pytest.mark.parametrize("failure", ["missing_index", "missing_contig", "length_mismatch"])
def test_alignment_preflight_failures_are_clear(
    failure: str, minimal_inputs: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref, _ = minimal_inputs
    if failure == "missing_index":
        bam = write_alignment(tmp_path / "missing_index.bam", {"MT": 10}, [ReadSpec("r", "MT", 0, "A")])
        Path(f"{bam}.bai").unlink()
    elif failure == "missing_contig":
        bam = write_alignment(tmp_path / "missing_contig.bam", {"chrM": 10}, [ReadSpec("r", "chrM", 0, "A")])
    else:
        bam = write_alignment(tmp_path / "length_mismatch.bam", {"MT": 11}, [ReadSpec("r", "MT", 0, "A")])
    config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, ref, bam))
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")
    issues = validate_config(config)
    expected = {
        "missing_index": "Missing BAM index",
        "missing_contig": "Alignment header does not contain",
        "length_mismatch": "Alignment header length",
    }[failure]
    assert any(expected in issue for issue in issues)
