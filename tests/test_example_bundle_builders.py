from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pysam
import pytest


REPO_ROOT = Path(__file__).parents[1]
SANITIZER = REPO_ROOT / "scripts" / "lib" / "sanitize_synthetic_subset_bam.sh"


def alignment_records(path: Path) -> list[str]:
    completed = subprocess.run(
        ["samtools", "view", "--no-PG", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.splitlines()


def write_pg_bam(path: Path) -> None:
    header = {
        "HD": {"VN": "1.6", "SO": "coordinate"},
        "SQ": [{"SN": "MT", "LN": 60}],
        "PG": [
            {
                "ID": "fixture-builder",
                "PN": "samtools",
                "CL": "/private/tmp/checkout/scripts/build --input /private/tmp/input.sam",
            }
        ],
    }
    with pysam.AlignmentFile(path, "wb", header=header) as output:
        for index, start in enumerate((2, 12, 22), start=1):
            record = pysam.AlignedSegment(output.header)
            record.query_name = f"read-{index}"
            record.query_sequence = "A" * 10
            record.flag = 0
            record.reference_id = 0
            record.reference_start = start
            record.mapping_quality = 60
            record.cigarstring = "10M"
            record.query_qualities = pysam.qualitystring_to_array("I" * 10)
            output.write(record)
    pysam.index(str(path))


def run_sanitizer(path: Path, contig: str = "MT") -> subprocess.CompletedProcess[str]:
    command = (
        "set -euo pipefail; "
        f"source {shlex_quote(SANITIZER)}; "
        f"sanitize_synthetic_subset_bam {shlex_quote(path)} {shlex_quote(contig)}"
    )
    return subprocess.run(
        ["bash", "-c", command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def shlex_quote(value: object) -> str:
    import shlex

    return shlex.quote(str(value))


def test_sanitizer_removes_pg_without_changing_alignment_records(tmp_path: Path) -> None:
    bam = tmp_path / "fixture.MT.bam"
    write_pg_bam(bam)
    before = alignment_records(bam)

    completed = run_sanitizer(bam)

    assert completed.returncode == 0, completed.stderr
    assert alignment_records(bam) == before
    with pysam.AlignmentFile(bam, "rb") as alignment:
        assert alignment.header.to_dict().get("PG", []) == []
        assert alignment.has_index()
        assert len(list(alignment.fetch("MT", 0, 60))) == 3
    assert pysam.quickcheck(str(bam)) == ""


def test_sanitizer_fails_closed_when_target_contig_is_absent(tmp_path: Path) -> None:
    bam = tmp_path / "fixture.MT.bam"
    write_pg_bam(bam)
    before_bam = bam.read_bytes()
    before_bai = Path(f"{bam}.bai").read_bytes()

    completed = run_sanitizer(bam, "chrM")

    assert completed.returncode != 0
    assert "does not define mitochondrial contig chrM" in completed.stderr
    assert bam.read_bytes() == before_bam
    assert Path(f"{bam}.bai").read_bytes() == before_bai


@pytest.mark.parametrize(
    ("builder", "sample_id"),
    [
        ("build_public_example_bundle.sh", "TOY-001"),
        ("build_public_shortread_example_bundle.sh", "TOY-SR-001"),
    ],
)
def test_generated_example_bundle_has_path_free_indexed_mt_bam(
    tmp_path: Path,
    builder: str,
    sample_id: str,
) -> None:
    if shutil.which("samtools") is None:
        pytest.skip("samtools is required for the example builders")

    output = tmp_path / f"{sample_id}_output"
    env = os.environ.copy()
    env["MITO_OVERVIEW_PYTHON"] = sys.executable
    subprocess.run(
        [str(REPO_ROOT / "scripts" / builder), str(output)],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    bam = output / "subset" / f"{sample_id}.MT.bam"
    assert Path(f"{bam}.bai").is_file()
    assert pysam.quickcheck(str(bam)) == ""
    with pysam.AlignmentFile(bam, "rb") as alignment:
        assert alignment.header.to_dict().get("PG", []) == []
        assert alignment.has_index()
        records = list(alignment.fetch("MT", 0, 60))
    assert records
