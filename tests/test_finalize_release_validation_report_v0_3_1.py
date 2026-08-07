from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from docx import Document
from PIL import Image


ROOT = Path(__file__).parents[1]
FINALIZER = ROOT / "scripts" / "finalize_release_validation_report_v0.3.1.py"
FINAL_SHA = "a" * 40
REPOSITORY = "https://github.com/elissonnog/mito-overview"
REPORT_STEM = "MitoOverview_v0.3.1_release_validation_report"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(path: Path, name: str) -> dict[str, object]:
    return {"name": name, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _write_png(path: Path, size: tuple[int, int]) -> None:
    Image.new("RGB", size, "white").save(path)


def _write_pdf(path: Path, pages: int) -> None:
    kids = " ".join(f"{number} 0 R" for number in range(3, 3 + pages))
    objects = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {pages} >>\nendobj\n",
    ]
    objects.extend(
        f"{number} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        for number in range(3, 3 + pages)
    )
    path.write_bytes(
        (
            "%PDF-1.4\n"
            + "".join(objects)
            + "trailer\n<< /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
        ).encode("ascii")
    )


def _write_fixture(root: Path) -> dict[str, Path]:
    packet = root / "packet"
    packet.mkdir(parents=True)
    common = {
        "schema_version": "2.0",
        "validation_profile": "github_release_validation_v1",
        "release_version": "v0.3.1",
        "repository": REPOSITORY,
        "git_commit": FINAL_SHA,
    }
    (packet / "run.json").write_text(json.dumps(common) + "\n")
    (packet / "release_identity.json").write_text(
        json.dumps(
            {
                **common,
                "package_name": "mito-overview",
                "package_version": "0.3.1",
            }
        )
        + "\n"
    )
    (packet / "verify_bundle.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\ntest -s run.json\ntest -s release_identity.json\ntest -s artifacts.sha256\n"
    )
    source_figure = packet / "figures" / "source.png"
    source_figure.parent.mkdir()
    _write_png(source_figure, (800, 450))
    manifest_rows = [
        f"{_sha256(path)}  {path.relative_to(packet).as_posix()}"
        for path in sorted(packet.rglob("*"))
        if path.is_file() and path.name != "artifacts.sha256"
    ]
    (packet / "artifacts.sha256").write_text("\n".join(manifest_rows) + "\n")

    archive = root / "mito-overview-v0.3.1-validation.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(packet.rglob("*")):
            if path.is_file():
                handle.write(path, path.relative_to(packet).as_posix())
    verification = root / "mito-overview-v0.3.1-verification-input.json"
    verification.write_text(
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
            }
        )
        + "\n"
    )

    report = root / "report"
    assets = report / f"{REPORT_STEM}_assets"
    assets.mkdir(parents=True)
    identity = f"v0.3.1\n{REPOSITORY}\n{FINAL_SHA}\n"
    report_md = report / f"{REPORT_STEM}.md"
    report_md.write_text(identity)
    report_docx = report / f"{REPORT_STEM}.docx"
    document = Document()
    document.add_paragraph(identity)
    document.save(report_docx)
    figure = assets / "figure.png"
    figure.write_bytes(source_figure.read_bytes())
    figure_manifest = assets / "figure_manifest.tsv"
    figure_manifest.write_text(
        "figure_number\tdataset\tcase_id\treport_asset\tpacket_path\tsha256\twidth_px\theight_px\tsource_inventory\n"
        f"1\tGM11906\tcase\t{assets.name}/figure.png\tfigures/source.png\t{_sha256(figure)}\t800\t450\tvisual.tsv\n"
    )
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
        "packet_identity": {
            name: _record(packet / name, name)
            for name in ("run.json", "release_identity.json", "artifacts.sha256")
        },
        "publication_input": {
            "name": "github_prepublication.json",
            "bytes": 1,
            "sha256": "0" * 64,
        },
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
    build_path.write_text(json.dumps(build, indent=2) + "\n")

    rendered = root / "rendered"
    rendered.mkdir()
    rendered_pdf = rendered / f"{REPORT_STEM}.pdf"
    _write_pdf(rendered_pdf, 1)
    _write_png(rendered / "page-1.png", (1275, 1650))
    return {
        "packet": packet,
        "archive": archive,
        "verification": verification,
        "report": report,
        "assets": assets,
        "rendered": rendered,
        "rendered_pdf": rendered_pdf,
        "figure": figure,
        "build": build_path,
    }


def _run(inputs: dict[str, Path], *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(FINALIZER),
            "--report-root",
            str(inputs["report"]),
            "--validation-zip",
            str(inputs["archive"]),
            "--packet-verification",
            str(inputs["verification"]),
            "--rendered-pdf",
            str(inputs["rendered_pdf"]),
            "--rendered-pages",
            str(inputs["rendered"]),
            "--final-sha",
            FINAL_SHA,
            "--visual-reviewer",
            "test-reviewer",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_finalizer_binds_packet_report_pdf_and_pages(tmp_path: Path) -> None:
    inputs = _write_fixture(tmp_path)
    completed = _run(inputs, "--visual-review-pass")

    assert completed.returncode == 0, completed.stderr
    receipt_path = inputs["assets"] / "report_provenance.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["git_commit"] == FINAL_SHA
    assert receipt["validation_archive"]["sha256"] == _sha256(inputs["archive"])
    assert receipt["report_outputs"]["pdf"]["sha256"] == _sha256(
        inputs["report"] / f"{REPORT_STEM}.pdf"
    )
    assert receipt["rendered_page_qa"]["status"] == "PASS"
    assert receipt["rendered_page_qa"]["page_count"] == 1
    assert receipt["rendered_page_qa"]["pdf_page_count"] == 1
    assert receipt["rendered_page_qa"]["page_count_matches_pdf"] is True
    assert (inputs["assets"] / "rendered_pages" / "page-1.png").is_file()


def test_finalizer_requires_explicit_visual_review_pass(tmp_path: Path) -> None:
    inputs = _write_fixture(tmp_path)
    completed = _run(inputs)

    assert completed.returncode != 0
    assert "explicit PASS visual review" in completed.stderr


def test_finalizer_rejects_figure_changed_after_report_build(tmp_path: Path) -> None:
    inputs = _write_fixture(tmp_path)
    _write_png(inputs["figure"], (801, 450))
    completed = _run(inputs, "--visual-review-pass")

    assert completed.returncode != 0
    assert "report figure figure.png" in completed.stderr


def test_finalizer_rejects_stale_packet_verification(tmp_path: Path) -> None:
    inputs = _write_fixture(tmp_path)
    with inputs["archive"].open("ab") as handle:
        handle.write(b"changed")
    completed = _run(inputs, "--visual-review-pass")

    assert completed.returncode != 0
    assert "audit_zip_sha256" in completed.stderr


def test_finalizer_rejects_report_figure_different_from_packet_source(
    tmp_path: Path,
) -> None:
    inputs = _write_fixture(tmp_path)
    replacement = tmp_path / "replacement.zip"
    with zipfile.ZipFile(inputs["archive"], "r") as source:
        with zipfile.ZipFile(replacement, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename == "figures/source.png":
                    payload += b"changed"
                target.writestr(info, payload)
    replacement.replace(inputs["archive"])
    receipt = json.loads(inputs["verification"].read_text())
    receipt["audit_zip_sha256"] = _sha256(inputs["archive"])
    inputs["verification"].write_text(json.dumps(receipt) + "\n")

    completed = _run(inputs, "--visual-review-pass")
    assert completed.returncode != 0
    assert "report figure differs from packet source" in completed.stderr


def test_finalizer_rejects_noncontiguous_rendered_pages(tmp_path: Path) -> None:
    inputs = _write_fixture(tmp_path)
    (inputs["rendered"] / "page-1.png").rename(inputs["rendered"] / "page-2.png")
    completed = _run(inputs, "--visual-review-pass")

    assert completed.returncode != 0
    assert "not contiguous" in completed.stderr


def test_finalizer_rejects_missing_rendered_page_for_multipage_pdf(tmp_path: Path) -> None:
    inputs = _write_fixture(tmp_path)
    _write_pdf(inputs["rendered_pdf"], 2)
    completed = _run(inputs, "--visual-review-pass")

    assert completed.returncode != 0
    assert "PNG page count does not match the PDF page count" in completed.stderr
