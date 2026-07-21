from __future__ import annotations

import csv
import hashlib
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


REPO_ROOT = Path(__file__).parents[1]
PUBLIC_ROOT = REPO_ROOT / "examples/public_validation"
SCRIPT = REPO_ROOT / "scripts/refresh_tracked_public_validation_assets_v0.3.0.py"
SPEC = importlib.util.spec_from_file_location("tracked_public_refresher", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
refresher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresher)


def write_cases(path: Path, verdicts: dict[str, str] | None = None) -> None:
    verdicts = verdicts or {}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "category",
                "input_available",
                "expected_available",
                "verdict",
                "detail",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for case_id in refresher.REQUIRED_CASE_IDS:
            writer.writerow(
                {
                    "case_id": case_id,
                    "category": "focused_fixture",
                    "input_available": "1",
                    "expected_available": "1",
                    "verdict": verdicts.get(case_id, "PASS"),
                    "detail": "fixture evidence passed",
                }
            )


def write_heteroplasmy_summary(
    path: Path,
    *,
    depth: int,
    fraction: float,
    unique_reads: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "metric\tvalue\n"
        "status\tok\n"
        f"min_callable_depth\t{depth}\n"
        f"min_alt_allele_fraction\t{fraction}\n"
        "allele_counting_method\tpysam_pileup_shared_filter_v1\n"
        f"unique_reads_seen\t{unique_reads}\n",
        encoding="utf-8",
    )


def make_matrix(root: Path) -> Path:
    for source_relative, destination_relative in refresher.COPY_SPECS:
        source = root / source_relative
        tracked = PUBLIC_ROOT / destination_relative
        assert tracked.is_file(), destination_relative
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tracked, source)

    write_cases(root / "cases.tsv")
    (root / "oracle_assertions.tsv").write_text(
        "assertion_id\tverdict\texpected\tobserved\tdetail\n"
        "fixture.oracle\tPASS\tmatched\tmatched\tall frozen assertions passed\n",
        encoding="utf-8",
    )
    write_heteroplasmy_summary(
        root / refresher.SHORT_CASE / "summary/mito_heteroplasmy_summary.tsv",
        depth=10,
        fraction=0.2,
        unique_reads=682_063,
    )
    write_heteroplasmy_summary(
        root / refresher.LONG_CASE / "summary/mito_heteroplasmy_summary.tsv",
        depth=100,
        fraction=0.1,
        unique_reads=728,
    )

    # A completed matrix contains much more than the tracked public inventory.
    pollutants = {
        "logs/default.log": b"workdir=/Users/private/matrix-work\n",
        "commands/default.sh": b"#!/bin/sh\necho replay\n",
        "environment/pip-freeze.txt": b"private-package==1.0\n",
        f"{refresher.SHORT_CASE}/provenance/GM11906_MERRF_shortread.source_libraries.tsv": (
            b"run\tsource\nSRR1\tprivate\n"
        ),
        f"{refresher.SHORT_CASE}/subset/sample.bam": b"BAM payload",
        f"{refresher.SHORT_CASE}/subset/sample.bam.bai": b"BAM index",
        f"{refresher.LONG_CASE}/subset/raw.fastq.gz": b"raw FASTQ payload",
    }
    for relative, payload in pollutants.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return root


def run_refresher(
    matrix: Path,
    destination: Path,
    *,
    supply_preserved: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--matrix-root",
        str(matrix),
        "--destination",
        str(destination),
    ]
    if supply_preserved:
        command.extend(
            [
                "--oracle",
                str(PUBLIC_ROOT / refresher.ORACLE_DEST),
                "--gm11906-readme",
                str(PUBLIC_ROOT / refresher.SHORT_README_DEST),
            ]
        )
    return subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)


def file_inventory(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in sorted(file_inventory(root))
    }


def test_refreshes_exact_deterministic_inventory_and_preserves_frozen_inputs(
    tmp_path: Path,
) -> None:
    assert file_inventory(PUBLIC_ROOT) == set(refresher.EXPECTED_FILES)
    matrix = make_matrix(tmp_path / "matrix")
    destination = tmp_path / "staged-public-validation"

    first = run_refresher(matrix, destination)

    assert first.returncode == 0, first.stderr
    assert "PASS files=56" in first.stdout
    assert file_inventory(destination) == set(refresher.EXPECTED_FILES)
    assert len(file_inventory(destination)) == 56
    assert (destination / refresher.ORACLE_DEST).read_bytes() == (
        PUBLIC_ROOT / refresher.ORACLE_DEST
    ).read_bytes()
    assert (destination / refresher.SHORT_README_DEST).read_bytes() == (
        PUBLIC_ROOT / refresher.SHORT_README_DEST
    ).read_bytes()

    for source_relative, destination_relative in refresher.COPY_SPECS:
        assert (destination / destination_relative).read_bytes() == (
            matrix / source_relative
        ).read_bytes()
    for path in destination.rglob("*"):
        if path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) == 0o644
    short_findings = (destination / refresher.SHORT_DEST / "GM11906_MERRF_shortread_key_findings.tsv")
    assert "source_library_strategy\tATAC-seq\n" in short_findings.read_text(encoding="utf-8")
    long_findings = destination / refresher.LONG_DEST / "GM12878_ONT_longread_key_findings.tsv"
    assert "allele_engine_unique_query_names_seen\t728\n" in long_findings.read_text(
        encoding="utf-8"
    )
    assert "minimum callable depth: `100`" in (
        destination / refresher.LONG_DEST / "README.md"
    ).read_text(encoding="utf-8")
    assert not any(
        path.name.endswith((".bam", ".bai", ".fastq.gz"))
        or "source_libraries" in path.name
        or path.name == "oracle_assertions.tsv"
        for path in destination.rglob("*")
    )

    for relative in (
        f"{refresher.SHORT_DEST}/figures/GM11906_MERRF_shortread_montage.png",
        f"{refresher.LONG_DEST}/figures/GM12878_ONT_longread_montage.png",
    ):
        with Image.open(destination / relative) as montage:
            montage.load()
            assert montage.size == (1775, 1457)

    first_hashes = tree_hashes(destination)
    second = run_refresher(matrix, destination, supply_preserved=False)

    assert second.returncode == 0, second.stderr
    assert tree_hashes(destination) == first_hashes


@pytest.mark.parametrize("mutation", ["missing", "failed"])
def test_rejects_missing_or_failed_cases_without_creating_destination(
    tmp_path: Path,
    mutation: str,
) -> None:
    matrix = make_matrix(tmp_path / "matrix")
    cases = matrix / "cases.tsv"
    if mutation == "missing":
        lines = cases.read_text(encoding="utf-8").splitlines()
        cases.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    else:
        write_cases(cases, {refresher.REQUIRED_CASE_IDS[0]: "FAIL"})
    destination = tmp_path / "destination"

    completed = run_refresher(matrix, destination)

    assert completed.returncode == 1
    assert "cases.tsv" in completed.stderr
    assert not destination.exists()


def test_rejects_failed_oracle_assertion_without_creating_destination(tmp_path: Path) -> None:
    matrix = make_matrix(tmp_path / "matrix")
    (matrix / "oracle_assertions.tsv").write_text(
        "assertion_id\tverdict\texpected\tobserved\tdetail\n"
        "fixture.oracle\tFAIL\tmatched\tdifferent\toracle mismatch\n",
        encoding="utf-8",
    )
    destination = tmp_path / "destination"

    completed = run_refresher(matrix, destination)

    assert completed.returncode == 1
    assert "oracle_assertions.tsv contains non-PASS assertions" in completed.stderr
    assert not destination.exists()


def test_rejects_unexpected_destination_inventory_without_modifying_it(tmp_path: Path) -> None:
    matrix = make_matrix(tmp_path / "matrix")
    destination = tmp_path / "destination"
    readme = destination / refresher.SHORT_README_DEST
    readme.parent.mkdir(parents=True)
    shutil.copyfile(PUBLIC_ROOT / refresher.ORACLE_DEST, destination / refresher.ORACLE_DEST)
    shutil.copyfile(PUBLIC_ROOT / refresher.SHORT_README_DEST, readme)
    unexpected = destination / "commands/replay.sh"
    unexpected.parent.mkdir()
    unexpected.write_text("echo should-not-be-here\n", encoding="utf-8")
    before = tree_hashes(destination)

    completed = run_refresher(matrix, destination, supply_preserved=False)

    assert completed.returncode == 1
    assert "Destination has unexpected inventory" in completed.stderr
    assert tree_hashes(destination) == before


def test_rejects_symlink_in_matrix(tmp_path: Path) -> None:
    matrix = make_matrix(tmp_path / "matrix")
    linked = matrix / "filter_profile_results.tsv"
    target = tmp_path / "filter_profile_results.tsv"
    shutil.copyfile(linked, target)
    linked.unlink()
    linked.symlink_to(target)
    destination = tmp_path / "destination"

    completed = run_refresher(matrix, destination)

    assert completed.returncode == 1
    assert "contains a symlink" in completed.stderr
    assert not destination.exists()


def test_rejects_symlink_in_existing_destination(tmp_path: Path) -> None:
    matrix = make_matrix(tmp_path / "matrix")
    destination = tmp_path / "destination"
    destination.mkdir()
    shutil.copyfile(PUBLIC_ROOT / refresher.ORACLE_DEST, destination / refresher.ORACLE_DEST)
    readme = destination / refresher.SHORT_README_DEST
    readme.parent.mkdir(parents=True)
    readme.symlink_to(PUBLIC_ROOT / refresher.SHORT_README_DEST)

    completed = run_refresher(matrix, destination, supply_preserved=False)

    assert completed.returncode == 1
    assert "contains a symlink" in completed.stderr
    assert readme.is_symlink()


@pytest.mark.parametrize(
    "absolute_path",
    ["/Users/private/research/output.tsv", r"C:\\Users\\private\\output.tsv"],
)
def test_rejects_local_absolute_paths_in_allowlisted_assets(
    tmp_path: Path,
    absolute_path: str,
) -> None:
    matrix = make_matrix(tmp_path / "matrix")
    summary = matrix / refresher.SHORT_CASE / "summary/mito_qc_summary.tsv"
    with summary.open("a", encoding="utf-8") as handle:
        handle.write(f"private_output\t{absolute_path}\n")
    destination = tmp_path / "destination"

    completed = run_refresher(matrix, destination)

    assert completed.returncode == 1
    assert "contains a local absolute path" in completed.stderr
    assert not destination.exists()
