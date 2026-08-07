#!/usr/bin/env python3
"""Finalize rendered report artifacts and emit an auditable provenance receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image


VERSION = "v0.3.1"
PROFILE = "github_release_validation_v1"
REPOSITORY = "https://github.com/elissonnog/mito-overview"
REPORT_STEM = "MitoOverview_v0.3.1_release_validation_report"
BUILD_PROVENANCE_NAME = "report_build_provenance.json"
FINAL_PROVENANCE_NAME = "report_provenance.json"
ZIP_NAME = "mito-overview-v0.3.1-validation.zip"
PAGE_RE = re.compile(r"^page-(?P<number>[1-9][0-9]*)\.png$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PDF_OBJECT_RE = re.compile(
    rb"(?ms)^\s*(?P<object>[0-9]+)\s+(?P<generation>[0-9]+)\s+obj\b(?P<body>.*?)\bendobj\b"
)


class FinalizationError(ValueError):
    """Raised when report evidence cannot be finalized without ambiguity."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_plain_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise FinalizationError(
            f"{label} must be a non-empty regular non-symlink file: {path}"
        )
    return path.resolve(strict=True)


def require_plain_directory(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise FinalizationError(f"{label} must be a regular non-symlink directory: {path}")
    root = path.resolve(strict=True)
    for entry in root.rglob("*"):
        if entry.is_symlink() or (not entry.is_file() and not entry.is_dir()):
            raise FinalizationError(f"{label} contains a symlink or special file: {entry}")
        if not entry.resolve(strict=True).is_relative_to(root):
            raise FinalizationError(f"{label} entry escapes its source root: {entry}")
    return root


def read_json(path: Path, label: str) -> dict[str, Any]:
    path = require_plain_file(path, label)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalizationError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise FinalizationError(f"{label} must contain a JSON object: {path}")
    return payload


def file_record(path: Path, name: str) -> dict[str, object]:
    path = require_plain_file(path, name)
    return {"name": name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def require_fields(payload: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for field, wanted in expected.items():
        if payload.get(field) != wanted:
            raise FinalizationError(
                f"{label} identity mismatch for {field}: "
                f"{payload.get(field)!r} != {wanted!r}"
            )


def validate_record(record: Any, path: Path, label: str) -> None:
    if not isinstance(record, dict):
        raise FinalizationError(f"{label} provenance record is malformed")
    require_plain_file(path, label)
    if record.get("bytes") != path.stat().st_size:
        raise FinalizationError(f"{label} byte count changed after provenance capture")
    if record.get("sha256") != sha256(path):
        raise FinalizationError(f"{label} SHA-256 changed after provenance capture")


def validate_pdf(path: Path) -> int:
    path = require_plain_file(path, "rendered PDF")
    payload = path.read_bytes()
    if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-1024:]:
        raise FinalizationError("rendered PDF lacks a complete PDF header/trailer")
    if b"startxref" not in payload[-4096:]:
        raise FinalizationError("rendered PDF lacks a startxref marker")

    objects: dict[tuple[int, int], bytes] = {}
    for match in PDF_OBJECT_RE.finditer(payload):
        key = (int(match.group("object")), int(match.group("generation")))
        objects[key] = match.group("body").split(b"stream", 1)[0]
    trailer_roots = re.findall(
        rb"(?ms)\btrailer\s*<<.*?/" + b"Root" + rb"\s+([0-9]+)\s+([0-9]+)\s+R.*?>>",
        payload,
    )
    if trailer_roots:
        root_key = tuple(int(value) for value in trailer_roots[-1])
        catalog = objects.get(root_key)
    else:
        catalogs = [
            body
            for body in objects.values()
            if re.search(rb"/Type\s*/Catalog\b", body)
        ]
        catalog = catalogs[-1] if len(catalogs) == 1 else None
    if catalog is None:
        raise FinalizationError("rendered PDF catalog cannot be resolved")
    pages_ref = re.search(rb"/Pages\s+([0-9]+)\s+([0-9]+)\s+R", catalog)
    if pages_ref is None:
        raise FinalizationError("rendered PDF catalog lacks a Pages reference")
    pages_key = (int(pages_ref.group(1)), int(pages_ref.group(2)))
    pages_root = objects.get(pages_key)
    if pages_root is None or re.search(rb"/Type\s*/Pages\b", pages_root) is None:
        raise FinalizationError("rendered PDF page tree cannot be resolved")
    count_match = re.search(rb"/Count\s+([0-9]+)\b", pages_root)
    if count_match is None or int(count_match.group(1)) < 1:
        raise FinalizationError("rendered PDF page tree lacks a positive page count")
    declared_count = int(count_match.group(1))
    page_object_count = sum(
        1
        for body in objects.values()
        if re.search(rb"/Type\s*/Page(?!s)\b", body)
    )
    if page_object_count != declared_count:
        raise FinalizationError(
            "rendered PDF page tree count does not match its page objects: "
            f"{declared_count} != {page_object_count}"
        )
    return declared_count


def validate_pages(root: Path) -> list[dict[str, object]]:
    root = require_plain_directory(root, "rendered-page directory")
    numbered: list[tuple[int, Path]] = []
    for path in root.iterdir():
        if not path.is_file():
            continue
        match = PAGE_RE.fullmatch(path.name)
        if match:
            numbered.append((int(match.group("number")), path))
    numbered.sort()
    if not numbered:
        raise FinalizationError("rendered-page directory contains no page-<N>.png files")
    observed = [number for number, _ in numbered]
    expected = list(range(1, len(numbered) + 1))
    if observed != expected:
        raise FinalizationError(
            f"rendered page sequence is not contiguous: {observed!r} != {expected!r}"
        )

    rows: list[dict[str, object]] = []
    for number, path in numbered:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
        except Exception as error:
            raise FinalizationError(f"rendered page is not a valid image: {path}") from error
        if width < 100 or height < 100:
            raise FinalizationError(f"rendered page has implausible dimensions: {path}")
        rows.append(
            {
                **file_record(
                    path,
                    f"{REPORT_STEM}_assets/rendered_pages/{path.name}",
                ),
                "page_number": number,
                "width_px": width,
                "height_px": height,
                "visual_review_status": "PASS",
            }
        )
    return rows


def validate_build_provenance(
    report_root: Path, final_sha: str
) -> tuple[dict[str, Any], Path, Path, Path, Path]:
    assets = require_plain_directory(
        report_root / f"{REPORT_STEM}_assets", "report asset directory"
    )
    build_path = assets / BUILD_PROVENANCE_NAME
    build = read_json(build_path, "report build provenance")
    require_fields(
        build,
        {
            "schema_version": "1.0",
            "provenance_type": "mito_overview_release_report_build",
            "repository": REPOSITORY,
            "release_version": VERSION,
            "release_tag": VERSION,
            "git_commit": final_sha,
            "validation_profile": PROFILE,
            "rendered_page_qa_required": True,
        },
        "report build provenance",
    )

    report_md = report_root / f"{REPORT_STEM}.md"
    report_docx = report_root / f"{REPORT_STEM}.docx"
    outputs = build.get("report_outputs")
    if not isinstance(outputs, dict):
        raise FinalizationError("report build provenance lacks report_outputs")
    validate_record(outputs.get("markdown"), report_md, "report Markdown")
    validate_record(outputs.get("docx"), report_docx, "report DOCX")

    manifest = assets / "figure_manifest.tsv"
    validate_record(build.get("figure_manifest"), manifest, "figure manifest")
    figures = build.get("figures")
    if not isinstance(figures, list) or not figures:
        raise FinalizationError("report build provenance contains no figure records")
    for row in figures:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise FinalizationError("report build provenance has a malformed figure record")
        relative = Path(row["name"])
        expected_prefix = f"{REPORT_STEM}_assets"
        if relative.is_absolute() or relative.parts[:1] != (expected_prefix,):
            raise FinalizationError(f"report figure path is outside report assets: {relative}")
        path = report_root / relative
        validate_record(row, path, f"report figure {relative.name}")
        if row.get("sha256") != row.get("packet_sha256"):
            raise FinalizationError(f"report figure is not byte-identical to packet source: {relative}")
        if not isinstance(row.get("packet_path"), str):
            raise FinalizationError(f"report figure lacks packet source path: {relative}")
    return build, build_path, assets, report_md, report_docx


def validate_packet_binding(
    validation_zip: Path,
    packet_verification: Path,
    build: dict[str, Any],
    final_sha: str,
) -> tuple[dict[str, Any], str]:
    validation_zip = require_plain_file(validation_zip, "validation ZIP")
    if validation_zip.name != ZIP_NAME:
        raise FinalizationError(f"validation ZIP must be named {ZIP_NAME}")
    archive_digest = sha256(validation_zip)
    verification = read_json(packet_verification, "packet verification JSON")
    require_fields(
        verification,
        {
            "schema_version": "2.0",
            "validation_profile": PROFILE,
            "evidence_type": "release_validation_archive_verification",
            "verdict": "PASS",
            "release_version": VERSION,
            "git_commit": final_sha,
            "audit_zip": ZIP_NAME,
            "audit_zip_sha256": archive_digest,
            "verifier_runs": ["packet_root", "fresh_audit_zip_extraction"],
        },
        "packet verification JSON",
    )

    with tempfile.TemporaryDirectory(prefix="mito-report-packet-") as temporary:
        packet_root = Path(temporary) / "packet"
        extractor = Path(__file__).with_name("safe_extract_validation_zip.py")
        extracted = subprocess.run(
            [sys.executable, str(extractor), str(validation_zip), str(packet_root)],
            check=False,
            capture_output=True,
            text=True,
        )
        if extracted.returncode != 0:
            detail = extracted.stderr.strip() or extracted.stdout.strip()
            raise FinalizationError(f"validation ZIP extraction failed: {detail}")
        verifier = packet_root / "verify_bundle.sh"
        require_plain_file(verifier, "validation packet verifier")
        checked = subprocess.run(
            ["bash", str(verifier)],
            cwd=packet_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if checked.returncode != 0:
            detail = checked.stderr.strip() or checked.stdout.strip()
            raise FinalizationError(f"validation packet verifier failed: {detail}")

        resolved_packet_root = packet_root.resolve(strict=True)
        packet_identity = build.get("packet_identity")
        if not isinstance(packet_identity, dict):
            raise FinalizationError("report build provenance lacks packet_identity")
        for name in ("run.json", "release_identity.json", "artifacts.sha256"):
            validate_record(
                packet_identity.get(name), packet_root / name, f"packet {name}"
            )
        figures = build.get("figures")
        if not isinstance(figures, list) or not figures:
            raise FinalizationError("report build provenance contains no packet figures")
        for row in figures:
            if not isinstance(row, dict) or not isinstance(row.get("packet_path"), str):
                raise FinalizationError("report build provenance has a malformed packet figure")
            source = packet_root / row["packet_path"]
            try:
                source.resolve(strict=True).relative_to(resolved_packet_root)
            except (FileNotFoundError, ValueError) as error:
                raise FinalizationError(
                    f"report figure packet source is missing or unsafe: {row['packet_path']}"
                ) from error
            if source.is_symlink() or not source.is_file():
                raise FinalizationError(
                    f"report figure packet source is not regular: {row['packet_path']}"
                )
            if sha256(source) != row.get("packet_sha256"):
                raise FinalizationError(
                    f"report figure differs from packet source: {row['packet_path']}"
                )
        run = read_json(packet_root / "run.json", "packet run.json")
        release = read_json(packet_root / "release_identity.json", "packet release_identity.json")
        expected = {
            "schema_version": "2.0",
            "validation_profile": PROFILE,
            "release_version": VERSION,
            "repository": REPOSITORY,
            "git_commit": final_sha,
        }
        require_fields(run, expected, "packet run.json")
        require_fields(release, expected, "packet release_identity.json")
    return verification, archive_digest


def finalize(
    report_root: Path,
    validation_zip: Path,
    packet_verification: Path,
    rendered_pdf: Path,
    rendered_pages: Path,
    final_sha: str,
    reviewer: str,
    *,
    visual_review_pass: bool,
    overwrite: bool = False,
) -> dict[str, Any]:
    if not COMMIT_RE.fullmatch(final_sha):
        raise FinalizationError("FINAL_SHA must be 40 lowercase hexadecimal characters")
    if not visual_review_pass:
        raise FinalizationError("finalization requires an explicit PASS visual review")
    if not reviewer.strip():
        raise FinalizationError("visual-reviewer identifier must not be empty")
    report_root = require_plain_directory(report_root, "report root")
    rendered_pdf = require_plain_file(rendered_pdf, "rendered PDF")
    pdf_page_count = validate_pdf(rendered_pdf)
    page_rows = validate_pages(rendered_pages)
    if len(page_rows) != pdf_page_count:
        raise FinalizationError(
            "rendered PNG page count does not match the PDF page count: "
            f"{len(page_rows)} != {pdf_page_count}"
        )
    build, build_path, assets, report_md, report_docx = validate_build_provenance(
        report_root, final_sha
    )
    verification, archive_digest = validate_packet_binding(
        validation_zip, packet_verification, build, final_sha
    )

    final_pdf = report_root / f"{REPORT_STEM}.pdf"
    final_pages = assets / "rendered_pages"
    final_receipt = assets / FINAL_PROVENANCE_NAME
    occupied = [path for path in (final_pdf, final_pages, final_receipt) if path.exists()]
    if occupied and not overwrite:
        raise FinalizationError(
            "final report artifacts already exist; pass --overwrite to replace: "
            + ", ".join(str(path) for path in occupied)
        )

    pdf_record = file_record(rendered_pdf, final_pdf.name)
    report_outputs = {
        "markdown": file_record(report_md, report_md.name),
        "docx": file_record(report_docx, report_docx.name),
        "pdf": pdf_record,
    }
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "provenance_type": "mito_overview_finalized_release_report",
        "repository": REPOSITORY,
        "release_version": VERSION,
        "release_tag": VERSION,
        "git_commit": final_sha,
        "validation_profile": PROFILE,
        "validation_archive": file_record(validation_zip, ZIP_NAME),
        "packet_verification": file_record(
            packet_verification, packet_verification.name
        ),
        "packet_verification_verdict": verification["verdict"],
        "packet_verifier_executed": True,
        "packet_artifacts_manifest_sha256": build["packet_identity"][
            "artifacts.sha256"
        ]["sha256"],
        "report_build_provenance": file_record(
            build_path, f"{assets.name}/{BUILD_PROVENANCE_NAME}"
        ),
        "report_outputs": report_outputs,
        "figure_manifest": build["figure_manifest"],
        "figures": build["figures"],
        "rendered_page_qa": {
            "status": "PASS",
            "all_pages_inspected": True,
            "reviewer": reviewer.strip(),
            "page_count": len(page_rows),
            "pdf_page_count": pdf_page_count,
            "page_count_matches_pdf": True,
            "source_docx_sha256": report_outputs["docx"]["sha256"],
            "rendered_pdf_sha256": pdf_record["sha256"],
            "pages": page_rows,
        },
    }
    if receipt["validation_archive"]["sha256"] != archive_digest:
        raise FinalizationError("validation archive changed during finalization")

    with tempfile.TemporaryDirectory(prefix=".mito-report-final-", dir=report_root) as temporary:
        stage = Path(temporary)
        stage_pdf = stage / final_pdf.name
        shutil.copyfile(rendered_pdf, stage_pdf)
        stage_pages = stage / "rendered_pages"
        stage_pages.mkdir()
        source_pages = {path.name: path for path in rendered_pages.iterdir() if PAGE_RE.fullmatch(path.name)}
        for row in page_rows:
            name = Path(str(row["name"])).name
            shutil.copyfile(source_pages[name], stage_pages / name)
        stage_receipt = stage / FINAL_PROVENANCE_NAME
        stage_receipt.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        if overwrite:
            if final_pdf.exists():
                final_pdf.unlink()
            if final_pages.exists():
                shutil.rmtree(final_pages)
            if final_receipt.exists():
                final_receipt.unlink()
        os.replace(stage_pdf, final_pdf)
        os.replace(stage_pages, final_pages)
        os.replace(stage_receipt, final_receipt)

    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--validation-zip", type=Path, required=True)
    parser.add_argument("--packet-verification", type=Path, required=True)
    parser.add_argument("--rendered-pdf", type=Path, required=True)
    parser.add_argument("--rendered-pages", type=Path, required=True)
    parser.add_argument("--final-sha", required=True)
    parser.add_argument("--visual-reviewer", required=True)
    parser.add_argument(
        "--visual-review-pass",
        action="store_true",
        help="Assert that every rendered page was inspected and passed visual QA.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        receipt = finalize(
            args.report_root,
            args.validation_zip,
            args.packet_verification,
            args.rendered_pdf,
            args.rendered_pages,
            args.final_sha,
            args.visual_reviewer,
            visual_review_pass=args.visual_review_pass,
            overwrite=args.overwrite,
        )
    except (FinalizationError, OSError) as error:
        raise SystemExit(f"Report finalization failed: {error}") from error
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
