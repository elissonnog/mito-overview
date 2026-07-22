from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from docx import Document


ROOT = Path(__file__).parents[1]
ASSEMBLER = ROOT / "scripts" / "assemble_release_assets_v0.3.0.py"
REPOSITORY = "https://github.com/elissonnog/mito-overview"
FINAL_SHA = "a" * 40
REPORT_STEM = "MitoOverview_v0.3.0_release_validation_report"
EXPECTED_ASSETS = {
    "mito-overview-v0.3.0-validation.zip",
    f"{REPORT_STEM}.md",
    f"{REPORT_STEM}.docx",
    f"{REPORT_STEM}.pdf",
    f"{REPORT_STEM}_assets.tar.gz",
    "mito-overview-v0.3.0-verification.json",
    "RELEASE_NOTES_v0.3.0.md",
    "mito-overview-v0.3.0-environment.txt",
    "mito-overview-v0.3.0-environment-locks.tar.gz",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_packet(root: Path) -> tuple[Path, Path]:
    packet = {
        "run.json": {
            "schema_version": "2.0",
            "validation_profile": "github_release_validation_v1",
            "release_version": "v0.3.0",
            "git_commit": FINAL_SHA,
            "repository": REPOSITORY,
        },
        "release_identity.json": {
            "schema_version": "2.0",
            "validation_profile": "github_release_validation_v1",
            "release_version": "v0.3.0",
            "git_commit": FINAL_SHA,
            "repository": REPOSITORY,
            "package_name": "mito-overview",
            "package_version": "0.3.0",
        },
    }
    archive = root / "mito-overview-v0.3.0-validation.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for name, payload in packet.items():
            handle.writestr(name, json.dumps(payload, sort_keys=True) + "\n")
        handle.writestr(
            "verify_bundle.sh",
            "#!/usr/bin/env bash\nset -euo pipefail\ntest -s run.json\ntest -s release_identity.json\n",
        )
    receipt = root / "packet.verification.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "validation_profile": "github_release_validation_v1",
                "evidence_type": "release_validation_archive_verification",
                "verdict": "PASS",
                "release_version": "v0.3.0",
                "git_commit": FINAL_SHA,
                "audit_zip": archive.name,
                "audit_zip_sha256": _sha256(archive),
                "verifier_runs": ["packet_root", "fresh_audit_zip_extraction"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return archive, receipt


def _write_inputs(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    archive, receipt = _write_packet(root)
    report = root / "report"
    assets = report / f"{REPORT_STEM}_assets"
    assets.mkdir(parents=True)
    identity = f"v0.3.0\n{REPOSITORY}\n{FINAL_SHA}\n"
    (report / f"{REPORT_STEM}.md").write_text(identity, encoding="utf-8")
    document = Document()
    document.add_paragraph(identity)
    document.save(report / f"{REPORT_STEM}.docx")
    (report / f"{REPORT_STEM}.pdf").write_bytes(b"%PDF-1.4\nfixture\n")
    (assets / "figure_manifest.tsv").write_text(
        "figure_number\treport_asset\n1\tfigure.png\n", encoding="utf-8"
    )
    (assets / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")

    notes = root / "release-notes.md"
    notes.write_text(identity, encoding="utf-8")
    environment = root / "environment.txt"
    environment.write_text(
        f"release_version=v0.3.0\nrepository={REPOSITORY}\ngit_commit={FINAL_SHA}\n",
        encoding="utf-8",
    )
    locks = root / "locks"
    for platform in ("linux-64", "osx-64", "osx-arm64"):
        target = locks / platform
        target.mkdir(parents=True)
        (target / f"conda-{platform}.explicit.txt").write_text("@EXPLICIT\n")
        (target / f"pip-{platform}.txt").write_text("pysam==0.24.0\n")
        (target / f"environment-{platform}.yml").write_text("name: fixture\n")
        (target / f"platform-{platform}.json").write_text(
            json.dumps({"git_commit": FINAL_SHA, "platform_id": platform}) + "\n"
        )
    return {
        "archive": archive,
        "receipt": receipt,
        "report": report,
        "notes": notes,
        "environment": environment,
        "locks": locks,
    }


def _run(root: Path, inputs: dict[str, Path], *, final_sha: str = FINAL_SHA):
    output = root / "assembled"
    completed = subprocess.run(
        [
            sys.executable,
            str(ASSEMBLER),
            str(output),
            str(inputs["archive"]),
            str(inputs["receipt"]),
            str(inputs["report"]),
            str(inputs["notes"]),
            str(inputs["environment"]),
            str(inputs["locks"]),
            final_sha,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, output


def test_assembler_builds_exact_semantically_bound_inventory(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    completed, output = _run(tmp_path, inputs)

    assert completed.returncode == 0, completed.stderr
    assert {path.name for path in output.iterdir()} == EXPECTED_ASSETS
    result = json.loads(completed.stdout)
    assert result["verified"] is True
    assert result["git_commit"] == FINAL_SHA
    receipt = json.loads(
        (output / "mito-overview-v0.3.0-verification.json").read_text()
    )
    manifest = receipt["report_asset_manifest"]
    assert manifest["git_commit"] == FINAL_SHA
    assert manifest["validation_zip_sha256"] == _sha256(inputs["archive"])
    assert {row["name"] for row in manifest["assets"]} == EXPECTED_ASSETS - {
        "mito-overview-v0.3.0-validation.zip",
        "mito-overview-v0.3.0-verification.json",
    }
    for row in manifest["assets"]:
        path = output / row["name"]
        assert row["size"] == path.stat().st_size
        assert row["sha256"] == _sha256(path)

    with tarfile.open(output / f"{REPORT_STEM}_assets.tar.gz", "r:gz") as handle:
        names = set(handle.getnames())
    assert f"{REPORT_STEM}_assets/figure_manifest.tsv" in names
    assert f"{REPORT_STEM}_assets/figure.png" in names


def test_assembler_archives_are_deterministic(tmp_path: Path) -> None:
    first_inputs = _write_inputs(tmp_path / "first")
    second_inputs = _write_inputs(tmp_path / "second")
    first, first_output = _run(tmp_path / "first", first_inputs)
    second, second_output = _run(tmp_path / "second", second_inputs)
    assert first.returncode == second.returncode == 0
    for name in (
        f"{REPORT_STEM}_assets.tar.gz",
        "mito-overview-v0.3.0-environment-locks.tar.gz",
    ):
        assert _sha256(first_output / name) == _sha256(second_output / name)


@pytest.mark.parametrize("target", ["report", "notes", "environment"])
def test_assembler_rejects_stale_text_identity(tmp_path: Path, target: str) -> None:
    inputs = _write_inputs(tmp_path)
    if target == "report":
        path = inputs[target] / f"{REPORT_STEM}.md"
    else:
        path = inputs[target]
    path.write_text("v0.3.0\nstale release evidence\n", encoding="utf-8")

    completed, output = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "lacks release identity values" in completed.stderr
    assert not output.exists()


def test_assembler_rejects_stale_environment_lock(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    path = inputs["locks"] / "linux-64" / "platform-linux-64.json"
    path.write_text(json.dumps({"git_commit": "b" * 40}) + "\n")

    completed, _ = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "lock record is not bound to FINAL_SHA" in completed.stderr


def test_assembler_rejects_symlinked_report_asset(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    target = inputs["report"] / f"{REPORT_STEM}_assets" / "figure.png"
    target.unlink()
    target.symlink_to(inputs["notes"])

    completed, _ = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "contains a symlink or special file" in completed.stderr


def test_assembler_rejects_receipt_bound_to_other_commit(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    payload = json.loads(inputs["receipt"].read_text())
    payload["git_commit"] = "b" * 40
    inputs["receipt"].write_text(json.dumps(payload) + "\n")

    completed, _ = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "packet verification identity mismatch for git_commit" in completed.stderr
