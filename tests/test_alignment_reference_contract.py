from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from mito_overview.config import PipelineConfig
from mito_overview.workflow import run_pipeline, validate_config

from ._helpers import ReadSpec, write_alignment, write_fasta
from .test_config_and_inputs import (
    GRCH38_AUTOSOME_LENGTHS,
    complete_reference_contigs,
    minimal_mapping,
    write_fai_stub,
)
from .test_reference_scope_and_bed import (
    GRCH37_AUTOSOME_LENGTHS,
    GRCH37_SEX_CHROMOSOME_LENGTHS,
    reference_contigs,
)


def grch38_contigs() -> dict[str, int]:
    return complete_reference_contigs(
        GRCH38_AUTOSOME_LENGTHS,
        (156_040_895, 57_227_415),
        16_569,
    )


def read_run_context(config: PipelineConfig) -> dict[str, str]:
    path = config.work_root / config.run_name / "stage" / "run_context.json"
    return json.loads(path.read_text(encoding="utf-8"))["config"]


def fake_scope_step(
    name: str, captured: dict[str, str]
) -> Callable[..., dict[str, Path | str]]:
    def run_step(**kwargs: object) -> dict[str, Path | str]:
        captured[name] = str(kwargs["reference_scope"])
        return {
            "status": "not_evaluable",
            "report_path": Path(str(kwargs["report_dir"])) / f"{name}.html",
        }

    return run_step


def test_mt_only_bam_with_complete_fasta_is_effectively_custom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = write_fai_stub(tmp_path / "grch38.fa", grch38_contigs())
    bam = write_alignment(tmp_path / "mt_only.bam", {"MT": 16_569}, [])
    mapping = minimal_mapping(tmp_path, ref, bam)
    config = PipelineConfig.from_mapping(mapping)
    captured: dict[str, str] = {}

    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")
    monkeypatch.setattr(
        "mito_overview.steps.mito_copy_number.run_step",
        fake_scope_step("copy_number", captured),
    )
    monkeypatch.setattr(
        "mito_overview.steps.mito_numt_qc.run_step",
        fake_scope_step("numt_qc", captured),
    )

    assert len(mapping) == 6
    assert config.reference_scope == "whole_genome"
    assert validate_config(config) == []
    run_pipeline(config, steps=["stage", "copy_number", "numt_qc"])

    context = read_run_context(config)
    assert context["reference_scope_fasta"] == "whole_genome"
    assert context["reference_profile_fasta"] == "human:GRCh38"
    assert context["reference_scope_alignment_header"] == "mt_only"
    assert context["reference_profile_alignment_header"] == "unrecognized"
    assert context["reference_scope_effective"] == "custom"
    assert context["reference_scope_resolved"] == "custom"
    assert captured == {"copy_number": "custom", "numt_qc": "custom"}


def test_matching_complete_bam_preserves_whole_genome_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contigs = grch38_contigs()
    ref = write_fai_stub(tmp_path / "grch38.fa", contigs)
    bam = write_alignment(tmp_path / "whole_genome.bam", contigs, [])
    config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, ref, bam))
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")

    assert validate_config(config) == []
    run_pipeline(config, steps=["stage"])

    context = read_run_context(config)
    assert context["reference_scope_fasta"] == "whole_genome"
    assert context["reference_scope_alignment_header"] == "whole_genome"
    assert context["reference_profile_fasta"] == "human:GRCh38"
    assert context["reference_profile_alignment_header"] == "human:GRCh38"
    assert context["reference_scope_effective"] == "whole_genome"


def test_different_recognized_fasta_and_bam_profiles_are_effectively_custom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = write_fai_stub(tmp_path / "grch38.fa", grch38_contigs())
    grch37 = reference_contigs(
        GRCH37_AUTOSOME_LENGTHS,
        prefix="",
        mt_contig="MT",
        sex_chromosome_lengths=GRCH37_SEX_CHROMOSOME_LENGTHS,
    )
    bam = write_alignment(tmp_path / "grch37.bam", grch37, [])
    config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, ref, bam))
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")

    assert validate_config(config) == []
    run_pipeline(config, steps=["stage"])

    context = read_run_context(config)
    assert context["reference_profile_fasta"] == "human:GRCh38"
    assert context["reference_profile_alignment_header"] == "human:GRCh37"
    assert context["reference_scope_fasta"] == "whole_genome"
    assert context["reference_scope_alignment_header"] == "whole_genome"
    assert context["reference_scope_effective"] == "custom"


def test_cram_md5_validates_without_mt_records_and_rejects_wrong_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    correct_ref = write_fasta(
        tmp_path / "correct.fa",
        {"MT": "A" * 10, "1": "C" * 20},
    )
    cram = write_alignment(
        tmp_path / "no_mt_records.cram",
        {"MT": 10, "1": 20},
        [ReadSpec("nuclear", "1", 0, "C" * 10)],
        reference_fasta=correct_ref,
    )
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")

    valid_config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, correct_ref, cram))
    assert validate_config(valid_config) == []
    run_pipeline(valid_config, steps=["stage"])
    valid_context = read_run_context(valid_config)
    assert valid_context["cram_reference_compatibility"] == "verified_m5"

    wrong_ref = write_fasta(
        tmp_path / "wrong_same_length.fa",
        {"MT": "T" * 10, "1": "C" * 20},
    )
    wrong_config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, wrong_ref, cram))
    issues = validate_config(wrong_config)

    assert any("CRAM/reference sequence mismatch" in issue for issue in issues)
    assert any("alignment SQ M5=" in issue and "REF_FASTA MD5=" in issue for issue in issues)


@pytest.mark.parametrize("m5_value", [None, "   "])
def test_cram_missing_mt_sq_m5_fails_even_when_mt_record_decodes(
    m5_value: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = write_fasta(tmp_path / "reference.fa", {"MT": "A" * 10})
    cram = tmp_path / "missing_m5.cram"
    cram.write_bytes(b"mock CRAM")
    Path(f"{cram}.crai").write_bytes(b"mock CRAI")
    config = PipelineConfig.from_mapping(minimal_mapping(tmp_path, ref, cram))
    fetch_calls: list[tuple[object, ...]] = []

    class HeaderWithoutUsableM5:
        def to_dict(self) -> dict[str, list[dict[str, object]]]:
            sq_record: dict[str, object] = {"SN": "MT", "LN": 10}
            if m5_value is not None:
                sq_record["M5"] = m5_value
            return {"SQ": [sq_record]}

    class DecodableCram:
        references = ("MT",)
        lengths = (10,)
        header = HeaderWithoutUsableM5()

        def __enter__(self) -> "DecodableCram":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def fetch(self, *args: object) -> object:
            fetch_calls.append(args)
            return iter([object()])

    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")
    monkeypatch.setattr(
        "mito_overview.workflow.pysam.AlignmentFile",
        lambda *args, **kwargs: DecodableCram(),
    )

    issues = validate_config(config)

    assert fetch_calls == [("MT", 0, 10)]
    assert any("alignment MT SQ M5 is missing or blank" in issue for issue in issues)
    assert any("M5-to-FASTA identity is required" in issue for issue in issues)
