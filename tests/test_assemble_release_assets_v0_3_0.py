from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from docx import Document
from PIL import Image


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


def _record(path: Path, name: str) -> dict[str, object]:
    return {"name": name, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _write_png(path: Path, size: tuple[int, int]) -> None:
    Image.new("RGB", size, "white").save(path)


def _png_bytes(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _write_packet(
    root: Path,
) -> tuple[Path, Path, dict[str, dict[str, object]], bytes]:
    objects = {
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
    source_figure = _png_bytes((800, 450))
    payloads = {
        name: (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        for name, payload in objects.items()
    }
    payloads["figures/source.png"] = source_figure
    payloads["artifacts.sha256"] = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
        for name, payload in sorted(payloads.items())
    ).encode("ascii")
    archive = root / "mito-overview-v0.3.0-validation.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for name, payload in payloads.items():
            handle.writestr(name, payload)
        handle.writestr(
            "verify_bundle.sh",
            "#!/usr/bin/env bash\nset -euo pipefail\ntest -s run.json\ntest -s release_identity.json\ntest -s artifacts.sha256\n",
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
    packet_records = {
        name: {
            "name": name,
            "bytes": len(payloads[name]),
            "sha256": hashlib.sha256(payloads[name]).hexdigest(),
        }
        for name in ("run.json", "release_identity.json", "artifacts.sha256")
    }
    return archive, receipt, packet_records, source_figure


def _write_inputs(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    archive, receipt, packet_records, source_figure = _write_packet(root)
    report = root / "report"
    assets = report / f"{REPORT_STEM}_assets"
    assets.mkdir(parents=True)
    identity = f"v0.3.0\n{REPOSITORY}\n{FINAL_SHA}\n"
    (report / f"{REPORT_STEM}.md").write_text(identity, encoding="utf-8")
    document = Document()
    document.add_paragraph(identity)
    report_docx = report / f"{REPORT_STEM}.docx"
    document.save(report_docx)
    report_pdf = report / f"{REPORT_STEM}.pdf"
    report_pdf.write_bytes(
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    )
    figure = assets / "figure.png"
    figure.write_bytes(source_figure)
    figure_manifest = assets / "figure_manifest.tsv"
    figure_manifest.write_text(
        "figure_number\tdataset\tcase_id\treport_asset\tpacket_path\tsha256\twidth_px\theight_px\tsource_inventory\n"
        f"1\tGM11906\tcase\t{assets.name}/figure.png\tfigures/source.png\t{_sha256(figure)}\t800\t450\tvisual.tsv\n",
        encoding="utf-8",
    )
    report_md = report / f"{REPORT_STEM}.md"
    figure_row = {
        **_record(figure, f"{assets.name}/figure.png"),
        "figure_number": 1,
        "dataset": "GM11906",
        "case_id": "case",
        "packet_path": "figures/source.png",
        "packet_sha256": _sha256(figure),
        "width_px": 800,
        "height_px": 450,
        "source_inventory": "visual.tsv",
    }
    build = {
        "schema_version": "1.0",
        "provenance_type": "mito_overview_release_report_build",
        "repository": REPOSITORY,
        "release_version": "v0.3.0",
        "release_tag": "v0.3.0",
        "git_commit": FINAL_SHA,
        "validation_profile": "github_release_validation_v1",
        "packet_identity": packet_records,
        "publication_input": {"name": "github_prepublication.json", "bytes": 1, "sha256": "0" * 64},
        "report_outputs": {
            "markdown": _record(report_md, report_md.name),
            "docx": _record(report_docx, report_docx.name),
        },
        "figure_manifest": _record(
            figure_manifest, f"{assets.name}/figure_manifest.tsv"
        ),
        "figures": [figure_row],
        "pdf_included": False,
        "rendered_page_qa_required": True,
    }
    build_path = assets / "report_build_provenance.json"
    build_path.write_text(json.dumps(build, indent=2) + "\n", encoding="utf-8")

    rendered_pages = assets / "rendered_pages"
    rendered_pages.mkdir()
    page = rendered_pages / "page-1.png"
    _write_png(page, (1275, 1650))
    page_row = {
        **_record(page, f"{assets.name}/rendered_pages/page-1.png"),
        "page_number": 1,
        "width_px": 1275,
        "height_px": 1650,
        "visual_review_status": "PASS",
    }
    final_provenance = {
        "schema_version": "1.0",
        "provenance_type": "mito_overview_finalized_release_report",
        "repository": REPOSITORY,
        "release_version": "v0.3.0",
        "release_tag": "v0.3.0",
        "git_commit": FINAL_SHA,
        "validation_profile": "github_release_validation_v1",
        "validation_archive": _record(archive, archive.name),
        "packet_verification": _record(receipt, receipt.name),
        "packet_verification_verdict": "PASS",
        "packet_verifier_executed": True,
        "packet_artifacts_manifest_sha256": packet_records["artifacts.sha256"][
            "sha256"
        ],
        "report_build_provenance": _record(
            build_path, f"{assets.name}/report_build_provenance.json"
        ),
        "report_outputs": {
            "markdown": _record(report_md, report_md.name),
            "docx": _record(report_docx, report_docx.name),
            "pdf": _record(report_pdf, report_pdf.name),
        },
        "figure_manifest": build["figure_manifest"],
        "figures": [figure_row],
        "rendered_page_qa": {
            "status": "PASS",
            "all_pages_inspected": True,
            "reviewer": "test-reviewer",
            "page_count": 1,
            "pdf_page_count": 1,
            "page_count_matches_pdf": True,
            "source_docx_sha256": _sha256(report_docx),
            "rendered_pdf_sha256": _sha256(report_pdf),
            "pages": [page_row],
        },
    }
    (assets / "report_provenance.json").write_text(
        json.dumps(final_provenance, indent=2) + "\n", encoding="utf-8"
    )

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
        (target / f"python-{platform}.txt").write_text("Python 3.12.13\n")
        evidence_names = (
            f"conda-{platform}.explicit.txt",
            f"pip-{platform}.txt",
            f"environment-{platform}.yml",
            f"python-{platform}.txt",
        )
        evidence_files = {
            name: {
                "sha256": _sha256(target / name),
                "size_bytes": (target / name).stat().st_size,
            }
            for name in evidence_names
        }
        manifest_payload = "".join(
            f"{name}\t{evidence_files[name]['sha256']}\t{evidence_files[name]['size_bytes']}\n"
            for name in sorted(evidence_files)
        ).encode("utf-8")
        (target / f"platform-{platform}.json").write_text(
            json.dumps(
                {
                    "schema_version": "2.0",
                    "git_commit": FINAL_SHA,
                    "platform_id": platform,
                    "resolved_environment": True,
                    "evidence_files": evidence_files,
                    "evidence_manifest_sha256": hashlib.sha256(
                        manifest_payload
                    ).hexdigest(),
                    "source_lock_sha256": evidence_files[
                        f"environment-{platform}.yml"
                    ]["sha256"],
                }
            )
            + "\n"
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
    assert f"{REPORT_STEM}_assets/report_build_provenance.json" in names
    assert f"{REPORT_STEM}_assets/report_provenance.json" in names
    assert f"{REPORT_STEM}_assets/rendered_pages/page-1.png" in names
    assert result["report_provenance_verified"] is True
    assert result["rendered_page_count"] == 1


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
    record = json.loads(path.read_text(encoding="utf-8"))
    record["git_commit"] = "b" * 40
    path.write_text(json.dumps(record) + "\n")

    completed, _ = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "lock record is not bound to FINAL_SHA" in completed.stderr


def test_assembler_rejects_environment_file_changed_after_ci_manifest(
    tmp_path: Path,
) -> None:
    inputs = _write_inputs(tmp_path)
    path = inputs["locks"] / "linux-64" / "pip-linux-64.txt"
    path.write_text("pysam==0.24.1\n", encoding="utf-8")

    completed, _ = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "evidence-file digest mismatch" in completed.stderr


def test_assembler_rejects_unexpected_environment_lock_file(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    (inputs["locks"] / "linux-64" / "unexpected.txt").write_text("poison\n")

    completed, _ = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "environment lock inventory mismatch" in completed.stderr


def test_assembler_rejects_report_pdf_changed_after_visual_qa(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    pdf = inputs["report"] / f"{REPORT_STEM}.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"\nchanged\n%%EOF\n")

    completed, _ = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "report pdf byte count does not match report provenance" in completed.stderr


def test_assembler_rejects_rendered_page_changed_after_visual_qa(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    page = (
        inputs["report"]
        / f"{REPORT_STEM}_assets"
        / "rendered_pages"
        / "page-1.png"
    )
    _write_png(page, (1276, 1650))

    completed, _ = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "rendered page 1" in completed.stderr


def test_assembler_rejects_false_visual_review_receipt(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    path = inputs["report"] / f"{REPORT_STEM}_assets" / "report_provenance.json"
    payload = json.loads(path.read_text())
    payload["rendered_page_qa"]["status"] = "FAIL"
    path.write_text(json.dumps(payload) + "\n")

    completed, _ = _run(tmp_path, inputs)
    assert completed.returncode != 0
    assert "visual QA did not pass" in completed.stderr


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
