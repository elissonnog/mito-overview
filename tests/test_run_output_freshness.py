from __future__ import annotations

from pathlib import Path

import pytest

from mito_overview.config import PipelineConfig
from mito_overview.steps.sync_bioinfo import run_step as sync_run_step
from mito_overview.workflow import run_pipeline

from ._helpers import ReadSpec, write_alignment, write_fasta


def make_config(tmp_path: Path, *, final_dir: Path | None = None) -> PipelineConfig:
    reference = write_fasta(tmp_path / "reference.fa", {"MT": "A" * 10})
    alignment = write_alignment(
        tmp_path / "input.bam",
        {"MT": 10},
        [ReadSpec("read1", "MT", 0, "A" * 10)],
    )
    mapping = {
        "WORK_ROOT": str(tmp_path / "runs"),
        "RUN_NAME": "fresh-run",
        "SAMPLE_ID": "S1",
        "REF_FASTA": str(reference),
        "SOURCE_ALIGN_FILE": str(alignment),
        "MT_CONTIG": "MT",
    }
    if final_dir is not None:
        mapping["FINAL_BIOINFO_DIR"] = str(final_dir)
    return PipelineConfig.from_mapping(mapping)


def test_dry_run_is_non_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")

    results = run_pipeline(
        config, steps=["validate", "stage"], dry_run=True, strict_files=True
    )

    assert [result.status for result in results] == ["planned", "planned"]
    assert not (config.work_root / config.run_name).exists()


def test_existing_run_directory_fails_before_modification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    run_dir = config.work_root / config.run_name
    run_dir.mkdir(parents=True)
    sentinel = run_dir / "stale-result.txt"
    sentinel.write_text("do not modify\n", encoding="utf-8")
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")

    with pytest.raises(ValueError, match="RUN_NAME is a single-use output namespace"):
        run_pipeline(config, steps=["stage"])

    assert sentinel.read_text(encoding="utf-8") == "do not modify\n"
    assert sorted(path.name for path in run_dir.iterdir()) == ["stale-result.txt"]


def test_existing_final_destination_fails_before_run_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final_dir = tmp_path / "published"
    final_dir.mkdir()
    sentinel = final_dir / "stale-report.txt"
    sentinel.write_text("do not modify\n", encoding="utf-8")
    config = make_config(tmp_path, final_dir=final_dir)
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")

    with pytest.raises(ValueError, match="Final output directory already exists"):
        run_pipeline(config, steps=["stage", "sync_bioinfo"])

    assert sentinel.read_text(encoding="utf-8") == "do not modify\n"
    assert not (config.work_root / config.run_name).exists()


def test_overlapping_run_and_final_paths_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "runs" / "fresh-run"
    config = make_config(tmp_path, final_dir=run_dir / "final")
    monkeypatch.setattr("mito_overview.workflow.shutil.which", lambda _: "/usr/bin/samtools")

    with pytest.raises(ValueError, match="must not equal, contain, or be contained"):
        run_pipeline(config, steps=["sync_bioinfo"])

    assert not run_dir.exists()


def test_direct_sync_entry_point_refuses_existing_destination(tmp_path: Path) -> None:
    final_dir = tmp_path / "existing-final"
    final_dir.mkdir()
    sentinel = final_dir / "sentinel.txt"
    sentinel.write_text("preserve\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="will not be overwritten"):
        sync_run_step(
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
            mito_bam=tmp_path / "mito.bam",
            mito_bai=tmp_path / "mito.bam.bai",
            config_file=tmp_path / "config.env",
            final_dir=final_dir,
            sample_id="S1",
            run_name="run1",
            mt_contig="MT",
            mt_length=10,
            species="human",
            build="unknown",
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve\n"
