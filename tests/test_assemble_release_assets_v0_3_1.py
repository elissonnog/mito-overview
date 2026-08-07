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
ASSEMBLER = ROOT / "scripts" / "assemble_release_assets_v0.3.1.py"
REPOSITORY = "https://github.com/elissonnog/mito-overview"
FINAL_SHA = "a" * 40
REPORT_STEM = "MitoOverview_v0.3.1_release_validation_report"
EXPECTED_ASSETS = {
    "mito-overview-v0.3.1-validation.zip",
    f"{REPORT_STEM}.md",
    f"{REPORT_STEM}.docx",
    f"{REPORT_STEM}.pdf",
    f"{REPORT_STEM}_assets.tar.gz",
    "mito-overview-v0.3.1-verification.json",
    "RELEASE_NOTES_v0.3.1.md",
    "mito-overview-v0.3.1-environment.txt",
    "mito-overview-v0.3.1-environment-locks.tar.gz",
    "mito_overview-0.3.1-py3-none-any.whl",
    "mito_overview-0.3.1.tar.gz",
}
REPORT_ASSETS = EXPECTED_ASSETS - {
    "mito-overview-v0.3.1-validation.zip",
    "mito-overview-v0.3.1-verification.json",
    "mito_overview-0.3.1-py3-none-any.whl",
    "mito_overview-0.3.1.tar.gz",
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
) -> tuple[Path, Path, dict[str, dict[str, object]], bytes, dict[str, bytes]]:
    distributions = {
        "mito_overview-0.3.1-py3-none-any.whl": b"fixture wheel bytes\n",
        "mito_overview-0.3.1.tar.gz": b"fixture source distribution bytes\n",
    }
    distribution_kinds = {
        "mito_overview-0.3.1-py3-none-any.whl": "wheel",
        "mito_overview-0.3.1.tar.gz": "sdist",
    }
    objects = {
        "run.json": {
            "schema_version": "2.0",
            "validation_profile": "github_release_validation_v1",
            "release_version": "v0.3.1",
            "git_commit": FINAL_SHA,
            "repository": REPOSITORY,
        },
        "release_identity.json": {
            "schema_version": "2.0",
            "validation_profile": "github_release_validation_v1",
            "release_version": "v0.3.1",
            "git_commit": FINAL_SHA,
            "repository": REPOSITORY,
            "package_name": "mito-overview",
            "package_version": "0.3.1",
            "dist_artifacts": [
                {
                    "path": f"dist/{name}",
                    "kind": distribution_kinds[name],
                    "name": "mito-overview",
                    "version": "0.3.1",
                    "bytes": len(distributions[name]),
                    "sha256": hashlib.sha256(distributions[name]).hexdigest(),
                    "direct_url_archive_sha256": hashlib.sha256(
                        distributions[name]
                    ).hexdigest(),
                }
                for name in sorted(distributions)
            ],
        },
    }
    source_figure = _png_bytes((800, 450))
    payloads = {
        name: (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        for name, payload in objects.items()
    }
    for platform in ("linux-64", "osx-64", "osx-arm64"):
        prefix = f"acceptance/resolved_ci_environments/{platform}"
        environment_payloads = {
            f"conda-{platform}.explicit.txt": b"@EXPLICIT\n",
            f"pip-{platform}.txt": b"pysam==0.24.0\n",
            f"environment-{platform}.yml": b"name: fixture\n",
            f"artifact-lock-{platform}.explicit.txt": (
                b"@EXPLICIT\nhttps://example.invalid/pinned.conda\n"
            ),
            "requirements-release-tools.txt": (
                b"pytest==9.1.1 --hash=sha256:"
                + b"a" * 64
                + b"\n"
            ),
            f"python-{platform}.txt": b"Python 3.12.13\n",
        }
        evidence_files = {
            name: {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
            for name, payload in environment_payloads.items()
        }
        manifest_payload = "".join(
            f"{name}\t{evidence_files[name]['sha256']}\t"
            f"{evidence_files[name]['size_bytes']}\n"
            for name in sorted(evidence_files)
        ).encode("utf-8")
        environment_payloads[f"platform-{platform}.json"] = (
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
                    "source_solver_spec_sha256": evidence_files[
                        f"environment-{platform}.yml"
                    ]["sha256"],
                    "source_artifact_lock_sha256": evidence_files[
                        f"artifact-lock-{platform}.explicit.txt"
                    ]["sha256"],
                    "source_release_tools_lock_sha256": evidence_files[
                        "requirements-release-tools.txt"
                    ]["sha256"],
                },
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        payloads.update(
            {f"{prefix}/{name}": payload for name, payload in environment_payloads.items()}
        )
    payloads["figures/source.png"] = source_figure
    payloads.update({f"dist/{name}": payload for name, payload in distributions.items()})
    payloads["artifacts.sha256"] = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
        for name, payload in sorted(payloads.items())
    ).encode("ascii")
    archive = root / "mito-overview-v0.3.1-validation.zip"
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
                "release_version": "v0.3.1",
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
    return archive, receipt, packet_records, source_figure, distributions


def _write_inputs(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    archive, receipt, packet_records, source_figure, distributions = _write_packet(root)
    report = root / "report"
    assets = report / f"{REPORT_STEM}_assets"
    assets.mkdir(parents=True)
    identity = f"v0.3.1\n{REPOSITORY}\n{FINAL_SHA}\n"
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
        "release_version": "v0.3.1",
        "release_tag": "v0.3.1",
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
        "release_version": "v0.3.1",
        "release_tag": "v0.3.1",
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
        f"release_version=v0.3.1\nrepository={REPOSITORY}\ngit_commit={FINAL_SHA}\n",
        encoding="utf-8",
    )
    locks = root / "locks"
    with zipfile.ZipFile(archive) as handle:
        prefix = "acceptance/resolved_ci_environments/"
        for name in handle.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            relative = Path(name.removeprefix(prefix))
            destination = locks / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(handle.read(name))
    dist = root / "dist"
    dist.mkdir()
    for name, payload in distributions.items():
        (dist / name).write_bytes(payload)
    return {
        "archive": archive,
        "receipt": receipt,
        "report": report,
        "notes": notes,
        "environment": environment,
        "locks": locks,
        "dist": dist,
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
            str(inputs["dist"]),
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
        (output / "mito-overview-v0.3.1-verification.json").read_text()
    )
    manifest = receipt["report_asset_manifest"]
    assert manifest["git_commit"] == FINAL_SHA
    assert manifest["validation_zip_sha256"] == _sha256(inputs["archive"])
    assert {row["name"] for row in manifest["assets"]} == REPORT_ASSETS
    for row in manifest["assets"]:
        path = output / row["name"]
        assert row["size"] == path.stat().st_size
        assert row["sha256"] == _sha256(path)
    distribution_manifest = receipt["distribution_asset_manifest"]
    assert {row["name"] for row in distribution_manifest["assets"]} == {
        "mito_overview-0.3.1-py3-none-any.whl",
        "mito_overview-0.3.1.tar.gz",
    }
    assert result["distribution_bytes_match_packet"] is True

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
    # DOCX and ZIP writers may embed creation timestamps. Determinism therefore
    # means reproducing an archive from the same immutable input bytes, not from
    # two independently generated containers with different internal metadata.
    inputs = _write_inputs(tmp_path / "inputs")
    first, first_output = _run(tmp_path / "first", inputs)
    second, second_output = _run(tmp_path / "second", inputs)
    assert first.returncode == second.returncode == 0
    for name in (
        f"{REPORT_STEM}_assets.tar.gz",
        "mito-overview-v0.3.1-environment-locks.tar.gz",
    ):
        assert _sha256(first_output / name) == _sha256(second_output / name)


@pytest.mark.parametrize(
    "name",
    [
        "mito_overview-0.3.1-py3-none-any.whl",
        "mito_overview-0.3.1.tar.gz",
    ],
)
def test_assembler_rejects_distribution_bytes_not_bound_in_packet(
    tmp_path: Path, name: str
) -> None:
    inputs = _write_inputs(tmp_path)
    path = inputs["dist"] / name
    path.write_bytes(path.read_bytes() + b"substituted\n")

    completed, output = _run(tmp_path, inputs)

    assert completed.returncode != 0
    assert "release distribution bytes differ from packet" in completed.stderr
    assert not output.exists()


def test_assembler_rejects_extra_distribution_file(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    (inputs["dist"] / "poison.txt").write_text("poison\n", encoding="ascii")

    completed, output = _run(tmp_path, inputs)

    assert completed.returncode != 0
    assert "distribution root inventory mismatch" in completed.stderr
    assert not output.exists()


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


def test_assembler_rejects_fully_resealed_environment_lock_substitution(
    tmp_path: Path,
) -> None:
    inputs = _write_inputs(tmp_path)
    platform = "linux-64"
    root = inputs["locks"] / platform
    artifact_name = f"artifact-lock-{platform}.explicit.txt"
    (root / artifact_name).write_text(
        "@EXPLICIT\n"
        "https://conda.anaconda.org/conda-forge/linux-64/substituted-1.0-0.conda\n",
        encoding="utf-8",
    )
    record_path = root / f"platform-{platform}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    for name in sorted(record["evidence_files"]):
        payload = (root / name).read_bytes()
        record["evidence_files"][name] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
    manifest_payload = "".join(
        f"{name}\t{record['evidence_files'][name]['sha256']}\t"
        f"{record['evidence_files'][name]['size_bytes']}\n"
        for name in sorted(record["evidence_files"])
    ).encode("utf-8")
    record["evidence_manifest_sha256"] = hashlib.sha256(manifest_payload).hexdigest()
    record["source_artifact_lock_sha256"] = record["evidence_files"][
        artifact_name
    ]["sha256"]
    record_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    completed, output = _run(tmp_path, inputs)

    assert completed.returncode != 0
    assert "differs from packet evidence" in completed.stderr
    assert not output.exists()


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
