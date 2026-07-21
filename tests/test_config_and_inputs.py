from __future__ import annotations

from pathlib import Path

import pytest

from mito_overview.config import PipelineConfig
from mito_overview.paths import RunPaths
from mito_overview.workflow import run_pipeline, validate_config

from ._helpers import ReadSpec, write_alignment, write_fasta


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
    assert config.reference_scope == "mt_only"
    assert config.mvtool_mode == "disabled"
    assert validate_config(config) == []


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
