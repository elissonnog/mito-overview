from __future__ import annotations

import csv
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parents[1]
STAGER = REPO_ROOT / "scripts" / "stage_public_visual_artifacts_v0.3.0.py"
FIELDS = [
    "relative_path",
    "artifact_type",
    "bytes",
    "sha256",
    "width_px",
    "height_px",
    "integrity_status",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_inventory(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def inventory_row(root: Path, relative: str, artifact_type: str) -> dict[str, str]:
    source = root / relative
    return {
        "relative_path": relative,
        "artifact_type": artifact_type,
        "bytes": str(source.stat().st_size),
        "sha256": digest(source),
        "width_px": "" if artifact_type == "html" else "1",
        "height_px": "" if artifact_type == "html" else "1",
        "integrity_status": "ok",
    }


def build_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    results = tmp_path / "results"
    artifact = tmp_path / "artifact"
    case_root = results / "outputs/gm11906_default_run1"
    (case_root / "report").mkdir(parents=True)
    (case_root / "figures").mkdir()
    (case_root / "report/01.html").write_text(
        "<html><body>report</body></html>\n", encoding="utf-8"
    )
    (case_root / "figures/01.png").write_bytes(b"fixture-png")
    write_inventory(
        results
        / "observed_normalized/gm11906_default_run1/visual_artifact_inventory.tsv",
        [
            inventory_row(case_root, "report/01.html", "html"),
            inventory_row(case_root, "figures/01.png", "png"),
        ],
    )
    return results, artifact, case_root


def run_stager(results: Path, artifact: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(STAGER), str(results), str(artifact)],
        text=True,
        capture_output=True,
        check=False,
    )


def staged_files(artifact: Path) -> set[str]:
    root = artifact / "results/report_artifacts/outputs"
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_stager_copies_exact_inventory_and_ignores_unbound_outputs(
    tmp_path: Path,
) -> None:
    results, artifact, case_root = build_fixture(tmp_path)
    (case_root / "report/unbound.html").write_text("extra", encoding="utf-8")
    nested = case_root / "nested"
    nested.mkdir()
    (nested / "unbound.png").write_bytes(b"extra")
    profile = results / "outputs/gm11906_lenient/report"
    profile.mkdir(parents=True)
    (profile / "profile.html").write_text("extra", encoding="utf-8")

    completed = run_stager(results, artifact)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "staged_public_visual_artifacts=2"
    assert staged_files(artifact) == {
        "gm11906_default_run1/figures/01.png",
        "gm11906_default_run1/report/01.html",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("hash", "SHA-256 mismatch"),
        ("duplicate", "Duplicate visual artifact path"),
        ("missing", "missing or not a regular file"),
    ],
)
def test_stager_rejects_invalid_inventory_bindings(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    results, artifact, case_root = build_fixture(tmp_path)
    inventory = (
        results
        / "observed_normalized/gm11906_default_run1/visual_artifact_inventory.tsv"
    )
    rows = list(csv.DictReader(inventory.open(encoding="utf-8"), delimiter="\t"))
    if mutation == "hash":
        rows[0]["sha256"] = "0" * 64
    elif mutation == "duplicate":
        rows.append(dict(rows[0]))
    else:
        (case_root / rows[0]["relative_path"]).unlink()
    write_inventory(inventory, rows)

    completed = run_stager(results, artifact)

    assert completed.returncode != 0
    assert message in completed.stderr


def test_stager_rejects_unsafe_case_and_symlinked_source(tmp_path: Path) -> None:
    results, artifact, case_root = build_fixture(tmp_path)
    original = (
        results
        / "observed_normalized/gm11906_default_run1/visual_artifact_inventory.tsv"
    )
    unsafe = results / "observed_normalized/bad case/visual_artifact_inventory.tsv"
    unsafe.parent.mkdir(parents=True)
    original.rename(unsafe)
    completed = run_stager(results, artifact)
    assert completed.returncode != 0
    assert "case ID is unsafe" in completed.stderr

    unsafe.rename(original)
    source = case_root / "report/01.html"
    target = tmp_path / "outside.html"
    target.write_text("<html><body>outside</body></html>\n", encoding="utf-8")
    source.unlink()
    source.symlink_to(target)
    rows = list(csv.DictReader(original.open(encoding="utf-8"), delimiter="\t"))
    rows[0] = inventory_row(case_root, "report/01.html", "html")
    write_inventory(original, rows)

    completed = run_stager(results, artifact)
    assert completed.returncode != 0
    assert "missing or not a regular file" in completed.stderr
