#!/usr/bin/env python3
"""Assemble and verify the prebuilt MitoOverview v0.3.0 release assets.

This utility closes the handoff between validation-packet construction, report
generation, and fresh-tag validation. It never builds Python distributions;
those are rebuilt from the public tag by ``run_fresh_public_tag_validation``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

VERSION = "v0.3.0"
PROFILE = "github_release_validation_v1"
REPOSITORY = "https://github.com/elissonnog/mito-overview"
REPORT_STEM = "MitoOverview_v0.3.0_release_validation_report"
ZIP_NAME = "mito-overview-v0.3.0-validation.zip"
VERIFICATION_NAME = "mito-overview-v0.3.0-verification.json"
REPORT_ASSET_ARCHIVE = f"{REPORT_STEM}_assets.tar.gz"
BUILD_PROVENANCE_NAME = "report_build_provenance.json"
FINAL_PROVENANCE_NAME = "report_provenance.json"
ENVIRONMENT_NAME = "mito-overview-v0.3.0-environment.txt"
ENVIRONMENT_ARCHIVE = "mito-overview-v0.3.0-environment-locks.tar.gz"
RELEASE_NOTES_NAME = "RELEASE_NOTES_v0.3.0.md"
EXPECTED_LOCK_FILES = {
    f"{platform}/{name}-{platform}.{suffix}"
    for platform in ("linux-64", "osx-64", "osx-arm64")
    for name, suffix in (
        ("conda", "explicit.txt"),
        ("pip", "txt"),
        ("environment", "yml"),
        ("platform", "json"),
        ("python", "txt"),
    )
}


class AssemblyError(ValueError):
    """Raised when release inputs cannot form one auditable asset bundle."""


def load_identity_verifier() -> tuple[type[ValueError], Any]:
    """Load the sibling versioned script without making ``scripts`` a package."""

    path = Path(__file__).with_name("verify_release_asset_identity_v0.3.0.py")
    specification = importlib.util.spec_from_file_location(
        "mito_overview_release_asset_identity_v0_3_0", path
    )
    if specification is None or specification.loader is None:
        raise AssemblyError(f"unable to load release-identity verifier: {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.IdentityError, module.verify


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_plain_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise AssemblyError(f"{label} must be a non-empty regular non-symlink file: {path}")
    return path.resolve(strict=True)


def require_plain_directory(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise AssemblyError(f"{label} must be a regular non-symlink directory: {path}")
    root = path.resolve(strict=True)
    for entry in root.rglob("*"):
        if entry.is_symlink() or (not entry.is_file() and not entry.is_dir()):
            raise AssemblyError(f"{label} contains a symlink or special file: {entry}")
        if not entry.resolve(strict=True).is_relative_to(root):
            raise AssemblyError(f"{label} entry escapes its source root: {entry}")
    return root


def copy_plain_file(source: Path, destination: Path) -> None:
    source = require_plain_file(source, "release source file")
    if destination.exists() or destination.is_symlink():
        raise AssemblyError(f"release destination already exists: {destination}")
    if not hasattr(os, "O_NOFOLLOW"):
        raise AssemblyError("release assembly requires os.O_NOFOLLOW")
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        source_stat = os.fstat(source_fd)
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644,
        )
        try:
            with os.fdopen(source_fd, "rb", closefd=False) as source_handle:
                with os.fdopen(destination_fd, "wb", closefd=False) as destination_handle:
                    shutil.copyfileobj(source_handle, destination_handle, 1024 * 1024)
        finally:
            os.close(destination_fd)
        if destination.stat().st_size != source_stat.st_size:
            raise AssemblyError(f"release copy size mismatch: {destination.name}")
    finally:
        os.close(source_fd)


def deterministic_tar_gz(source_root: Path, output: Path, archive_root: str) -> None:
    source_root = require_plain_directory(source_root, f"{archive_root} source")
    if output.exists() or output.is_symlink():
        raise AssemblyError(f"archive destination already exists: {output}")
    with output.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                entries = [source_root, *sorted(source_root.rglob("*"))]
                for entry in entries:
                    relative = entry.relative_to(source_root)
                    arcname = Path(archive_root) / relative
                    info = archive.gettarinfo(str(entry), arcname=str(arcname))
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    info.mode = 0o755 if entry.is_dir() else 0o644
                    info.pax_headers = {}
                    if entry.is_dir():
                        archive.addfile(info)
                    else:
                        with entry.open("rb") as handle:
                            archive.addfile(info, handle)


def read_json(path: Path, label: str) -> dict[str, Any]:
    path = require_plain_file(path, label)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AssemblyError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise AssemblyError(f"{label} must contain a JSON object: {path}")
    return payload


def require_identity(payload: dict[str, Any], final_sha: str, audit_digest: str) -> None:
    expected = {
        "schema_version": "2.0",
        "validation_profile": PROFILE,
        "evidence_type": "release_validation_archive_verification",
        "verdict": "PASS",
        "release_version": VERSION,
        "git_commit": final_sha,
        "audit_zip": ZIP_NAME,
        "audit_zip_sha256": audit_digest,
        "verifier_runs": ["packet_root", "fresh_audit_zip_extraction"],
    }
    for field, wanted in expected.items():
        if payload.get(field) != wanted:
            raise AssemblyError(
                f"packet verification identity mismatch for {field}: "
                f"{payload.get(field)!r} != {wanted!r}"
            )
    if "report_asset_manifest" in payload:
        raise AssemblyError("packet verification input already contains report_asset_manifest")


def require_text_identity(path: Path, final_sha: str, label: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise AssemblyError(f"{label} is not UTF-8 text: {path}") from error
    required = (VERSION, REPOSITORY, final_sha)
    missing = [value for value in required if value not in text]
    if missing:
        raise AssemblyError(f"{label} lacks release identity values: {missing!r}")


def require_docx_identity(path: Path, final_sha: str) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
    except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise AssemblyError(f"report DOCX is malformed: {path}") from error
    for value in (REPOSITORY, final_sha):
        if value not in document_xml:
            raise AssemblyError(f"report DOCX lacks release identity value: {value}")


def validate_file_record(record: Any, path: Path, label: str) -> None:
    if not isinstance(record, dict):
        raise AssemblyError(f"{label} provenance record is malformed")
    path = require_plain_file(path, label)
    if record.get("bytes") != path.stat().st_size:
        raise AssemblyError(f"{label} byte count does not match report provenance")
    if record.get("sha256") != sha256(path):
        raise AssemblyError(f"{label} SHA-256 does not match report provenance")


def require_report_identity(payload: dict[str, Any], final_sha: str, label: str) -> None:
    expected = {
        "schema_version": "1.0",
        "repository": REPOSITORY,
        "release_version": VERSION,
        "release_tag": VERSION,
        "git_commit": final_sha,
        "validation_profile": PROFILE,
    }
    for field, wanted in expected.items():
        if payload.get(field) != wanted:
            raise AssemblyError(
                f"{label} identity mismatch for {field}: "
                f"{payload.get(field)!r} != {wanted!r}"
            )


def validate_report_provenance(
    report_root: Path,
    report_assets: Path,
    validation_zip: Path,
    packet_verification: Path,
    final_sha: str,
) -> dict[str, Any]:
    """Validate the report-to-packet-to-render chain before asset assembly."""

    build_path = report_assets / BUILD_PROVENANCE_NAME
    final_path = report_assets / FINAL_PROVENANCE_NAME
    build = read_json(build_path, "report build provenance")
    final = read_json(final_path, "final report provenance")
    require_report_identity(build, final_sha, "report build provenance")
    require_report_identity(final, final_sha, "final report provenance")
    if build.get("provenance_type") != "mito_overview_release_report_build":
        raise AssemblyError("report build provenance type is invalid")
    if final.get("provenance_type") != "mito_overview_finalized_release_report":
        raise AssemblyError("final report provenance type is invalid")

    archive_record = final.get("validation_archive")
    validate_file_record(archive_record, validation_zip, "validation ZIP")
    if archive_record.get("name") != ZIP_NAME:
        raise AssemblyError("final report provenance names the wrong validation ZIP")
    validate_file_record(
        final.get("packet_verification"),
        packet_verification,
        "packet verification JSON",
    )
    validate_file_record(
        final.get("report_build_provenance"),
        build_path,
        "report build provenance",
    )

    outputs = final.get("report_outputs")
    if not isinstance(outputs, dict) or set(outputs) != {"markdown", "docx", "pdf"}:
        raise AssemblyError("final report provenance has an incomplete output inventory")
    report_paths = {
        "markdown": report_root / f"{REPORT_STEM}.md",
        "docx": report_root / f"{REPORT_STEM}.docx",
        "pdf": report_root / f"{REPORT_STEM}.pdf",
    }
    for label, path in report_paths.items():
        validate_file_record(outputs[label], path, f"report {label}")
        if outputs[label].get("name") != path.name:
            raise AssemblyError(f"report {label} provenance names an unexpected file")

    build_outputs = build.get("report_outputs")
    if not isinstance(build_outputs, dict):
        raise AssemblyError("report build provenance lacks report_outputs")
    for label in ("markdown", "docx"):
        if build_outputs.get(label) != outputs[label]:
            raise AssemblyError(f"final report {label} is not the recorded build output")

    figure_manifest = report_assets / "figure_manifest.tsv"
    validate_file_record(final.get("figure_manifest"), figure_manifest, "figure manifest")
    if final.get("figure_manifest") != build.get("figure_manifest"):
        raise AssemblyError("final report figure manifest differs from build provenance")
    figures = final.get("figures")
    if not isinstance(figures, list) or not figures or figures != build.get("figures"):
        raise AssemblyError("final report figures differ from build provenance")

    expected_assets = {BUILD_PROVENANCE_NAME, FINAL_PROVENANCE_NAME, "figure_manifest.tsv"}
    for row in figures:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise AssemblyError("final report provenance has a malformed figure record")
        relative = Path(row["name"])
        if relative.is_absolute() or relative.parts[:1] != (report_assets.name,):
            raise AssemblyError(f"report figure path escapes report assets: {relative}")
        path = report_root / relative
        validate_file_record(row, path, f"report figure {relative.name}")
        if row.get("sha256") != row.get("packet_sha256"):
            raise AssemblyError(f"report figure is not byte-identical to packet source: {relative}")
        expected_assets.add(relative.relative_to(report_assets.name).as_posix())

    page_qa = final.get("rendered_page_qa")
    if not isinstance(page_qa, dict):
        raise AssemblyError("final report provenance lacks rendered_page_qa")
    if page_qa.get("status") != "PASS" or page_qa.get("all_pages_inspected") is not True:
        raise AssemblyError("final report rendered-page visual QA did not pass")
    pages = page_qa.get("pages")
    if not isinstance(pages, list) or not pages or page_qa.get("page_count") != len(pages):
        raise AssemblyError("final report rendered-page inventory is incomplete")
    if (
        page_qa.get("pdf_page_count") != len(pages)
        or page_qa.get("page_count_matches_pdf") is not True
    ):
        raise AssemblyError("final report rendered pages are not proven complete for the PDF")
    if page_qa.get("source_docx_sha256") != outputs["docx"]["sha256"]:
        raise AssemblyError("rendered-page QA is bound to a different DOCX")
    if page_qa.get("rendered_pdf_sha256") != outputs["pdf"]["sha256"]:
        raise AssemblyError("rendered-page QA is bound to a different PDF")
    for expected_number, row in enumerate(pages, 1):
        if not isinstance(row, dict) or row.get("page_number") != expected_number:
            raise AssemblyError("rendered-page sequence is malformed")
        if row.get("visual_review_status") != "PASS" or not isinstance(row.get("name"), str):
            raise AssemblyError("rendered-page record lacks a PASS visual review")
        relative = Path(row["name"])
        expected_prefix = (report_assets.name, "rendered_pages")
        if relative.is_absolute() or relative.parts[:2] != expected_prefix:
            raise AssemblyError(f"rendered-page path escapes report assets: {relative}")
        path = report_root / relative
        validate_file_record(row, path, f"rendered page {expected_number}")
        expected_assets.add(relative.relative_to(report_assets.name).as_posix())

    observed_assets = {
        path.relative_to(report_assets).as_posix()
        for path in report_assets.rglob("*")
        if path.is_file()
    }
    if observed_assets != expected_assets:
        raise AssemblyError(
            "report asset inventory mismatch; "
            f"missing={sorted(expected_assets - observed_assets)!r}; "
            f"unexpected={sorted(observed_assets - expected_assets)!r}"
        )
    if final.get("packet_verification_verdict") != "PASS" or final.get(
        "packet_verifier_executed"
    ) is not True:
        raise AssemblyError("final report provenance lacks a successful packet verification")
    return final


def validate_environment_locks(root: Path, final_sha: str) -> None:
    relative_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if relative_files != EXPECTED_LOCK_FILES:
        raise AssemblyError(
            "environment lock inventory mismatch; "
            f"missing={sorted(EXPECTED_LOCK_FILES - relative_files)!r}; "
            f"unexpected={sorted(relative_files - EXPECTED_LOCK_FILES)!r}"
        )
    for platform in ("linux-64", "osx-64", "osx-arm64"):
        record = read_json(root / platform / f"platform-{platform}.json", "platform lock record")
        if record.get("schema_version") != "2.0":
            raise AssemblyError(f"{platform} lock record schema is not 2.0")
        if record.get("git_commit") != final_sha:
            raise AssemblyError(f"{platform} lock record is not bound to FINAL_SHA")
        if record.get("platform_id") != platform or record.get("resolved_environment") is not True:
            raise AssemblyError(f"{platform} lock record lacks resolved platform identity")
        python_text = (root / platform / f"python-{platform}.txt").read_text(
            encoding="utf-8"
        ).strip()
        if python_text != "Python 3.12.13":
            raise AssemblyError(f"{platform} Python evidence is not Python 3.12.13")
        evidence_names = {
            f"conda-{platform}.explicit.txt",
            f"pip-{platform}.txt",
            f"environment-{platform}.yml",
            f"python-{platform}.txt",
        }
        evidence_files = record.get("evidence_files")
        if not isinstance(evidence_files, dict) or set(evidence_files) != evidence_names:
            raise AssemblyError(f"{platform} evidence-file manifest inventory mismatch")
        manifest_lines = []
        for name in sorted(evidence_names):
            payload = (root / platform / name).read_bytes()
            observed_sha256 = hashlib.sha256(payload).hexdigest()
            observed_size = len(payload)
            item = evidence_files.get(name)
            if not isinstance(item, dict):
                raise AssemblyError(f"{platform} evidence-file record is malformed: {name}")
            if item.get("sha256") != observed_sha256 or item.get("size_bytes") != observed_size:
                raise AssemblyError(f"{platform} evidence-file digest mismatch: {name}")
            manifest_lines.append(f"{name}\t{observed_sha256}\t{observed_size}\n")
        observed_manifest = hashlib.sha256("".join(manifest_lines).encode("utf-8")).hexdigest()
        if record.get("evidence_manifest_sha256") != observed_manifest:
            raise AssemblyError(f"{platform} evidence manifest digest mismatch")
        lock_name = f"environment-{platform}.yml"
        if record.get("source_lock_sha256") != evidence_files[lock_name]["sha256"]:
            raise AssemblyError(f"{platform} source-lock digest mismatch")


def populate_and_verify_stage(
    stage_root: Path,
    *,
    validation_zip: Path,
    report_md: Path,
    report_docx: Path,
    report_pdf: Path,
    report_assets: Path,
    release_notes: Path,
    environment_text: Path,
    environment_locks: Path,
    receipt: dict[str, Any],
    report_provenance: dict[str, Any],
    audit_digest: str,
    final_sha: str,
) -> dict[str, Any]:
    """Populate a private staging directory and verify it before publication."""

    stage_root.mkdir()
    copy_plain_file(validation_zip, stage_root / ZIP_NAME)
    copy_plain_file(report_md, stage_root / report_md.name)
    copy_plain_file(report_docx, stage_root / report_docx.name)
    copy_plain_file(report_pdf, stage_root / report_pdf.name)
    copy_plain_file(release_notes, stage_root / RELEASE_NOTES_NAME)
    copy_plain_file(environment_text, stage_root / ENVIRONMENT_NAME)
    deterministic_tar_gz(report_assets, stage_root / REPORT_ASSET_ARCHIVE, report_assets.name)
    deterministic_tar_gz(environment_locks, stage_root / ENVIRONMENT_ARCHIVE, "environment-locks")

    report_asset_names = {
        report_md.name,
        report_docx.name,
        report_pdf.name,
        REPORT_ASSET_ARCHIVE,
        RELEASE_NOTES_NAME,
        ENVIRONMENT_NAME,
        ENVIRONMENT_ARCHIVE,
    }
    rows = [
        {
            "name": name,
            "size": (stage_root / name).stat().st_size,
            "sha256": sha256(stage_root / name),
        }
        for name in sorted(report_asset_names)
    ]
    report_provenance_path = report_assets / FINAL_PROVENANCE_NAME
    receipt["report_build_provenance"] = {
        "schema_version": "1.0",
        "provenance_type": "release_report_provenance_binding",
        "repository": REPOSITORY,
        "release_version": VERSION,
        "release_tag": VERSION,
        "git_commit": final_sha,
        "validation_zip_sha256": audit_digest,
        "report_provenance_archive_path": (
            f"{report_assets.name}/{FINAL_PROVENANCE_NAME}"
        ),
        "report_provenance_sha256": sha256(report_provenance_path),
        "report_asset_archive_sha256": sha256(stage_root / REPORT_ASSET_ARCHIVE),
        "report_outputs": report_provenance["report_outputs"],
        "figure_count": len(report_provenance["figures"]),
        "rendered_page_count": report_provenance["rendered_page_qa"]["page_count"],
        "visual_review_status": report_provenance["rendered_page_qa"]["status"],
    }
    receipt["report_asset_manifest"] = {
        "schema_version": "1.0",
        "manifest_type": "report_asset_manifest",
        "repository": REPOSITORY,
        "repository_slug": "elissonnog/mito-overview",
        "release_version": VERSION,
        "release_tag": VERSION,
        "git_commit": final_sha,
        "validation_zip_sha256": audit_digest,
        "assets": rows,
    }
    verification_output = stage_root / VERIFICATION_NAME
    verification_output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with tempfile.TemporaryDirectory(prefix="mito-release-packet-") as temporary:
        packet_root = Path(temporary) / "packet"
        extractor = Path(__file__).with_name("safe_extract_validation_zip.py")
        completed = subprocess.run(
            [sys.executable, str(extractor), str(stage_root / ZIP_NAME), str(packet_root)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise AssemblyError(f"validation ZIP extraction failed: {detail}")
        verifier = packet_root / "verify_bundle.sh"
        if verifier.is_symlink() or not verifier.is_file():
            raise AssemblyError("validation ZIP lacks a regular verify_bundle.sh")
        verified = subprocess.run(
            ["bash", str(verifier)],
            cwd=packet_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if verified.returncode != 0:
            detail = verified.stderr.strip() or verified.stdout.strip()
            raise AssemblyError(f"validation packet verifier failed: {detail}")
        identity_error, identity_verifier = load_identity_verifier()
        try:
            return identity_verifier(stage_root, packet_root, REPOSITORY, final_sha)
        except identity_error as error:
            raise AssemblyError(str(error)) from error


def assemble(
    output_root: Path,
    validation_zip: Path,
    packet_verification: Path,
    report_root: Path,
    release_notes: Path,
    environment_text: Path,
    environment_locks: Path,
    final_sha: str,
) -> dict[str, Any]:
    if len(final_sha) != 40 or any(character not in "0123456789abcdef" for character in final_sha):
        raise AssemblyError("FINAL_SHA must be 40 lowercase hexadecimal characters")
    validation_zip = require_plain_file(validation_zip, "validation ZIP")
    if validation_zip.name != ZIP_NAME:
        raise AssemblyError(f"validation ZIP must be named {ZIP_NAME}")
    packet_verification = require_plain_file(packet_verification, "packet verification JSON")
    report_root = require_plain_directory(report_root, "report root")
    release_notes = require_plain_file(release_notes, "release notes")
    environment_text = require_plain_file(environment_text, "environment record")
    environment_locks = require_plain_directory(environment_locks, "environment lock root")

    if output_root.exists() or output_root.is_symlink():
        raise AssemblyError("output root must not already exist")
    output_parent = output_root.expanduser().parent
    output_parent.mkdir(parents=True, exist_ok=True)
    if output_parent.is_symlink() or not output_parent.is_dir():
        raise AssemblyError("output parent must be a regular non-symlink directory")
    output_root = output_parent.resolve(strict=True) / output_root.name
    for source_root, label in (
        (report_root, "report root"),
        (environment_locks, "environment lock root"),
    ):
        if output_root.is_relative_to(source_root) or source_root.is_relative_to(output_root):
            raise AssemblyError(f"output root must be disjoint from {label}")

    report_md = require_plain_file(report_root / f"{REPORT_STEM}.md", "report Markdown")
    report_docx = require_plain_file(report_root / f"{REPORT_STEM}.docx", "report DOCX")
    report_pdf = require_plain_file(report_root / f"{REPORT_STEM}.pdf", "report PDF")
    report_assets = require_plain_directory(
        report_root / f"{REPORT_STEM}_assets", "report figure assets"
    )
    if not (report_assets / "figure_manifest.tsv").is_file():
        raise AssemblyError("report figure assets lack figure_manifest.tsv")
    if not any(report_assets.rglob("*.png")):
        raise AssemblyError("report figure assets contain no PNG figures")
    if report_pdf.read_bytes()[:5] != b"%PDF-":
        raise AssemblyError("report PDF does not have a PDF header")
    with report_pdf.open("rb") as handle:
        handle.seek(max(0, report_pdf.stat().st_size - 1024))
        if b"%%EOF" not in handle.read():
            raise AssemblyError("report PDF does not have a PDF trailer")

    audit_digest = sha256(validation_zip)
    receipt = read_json(packet_verification, "packet verification JSON")
    require_identity(receipt, final_sha, audit_digest)
    require_text_identity(report_md, final_sha, "report Markdown")
    require_docx_identity(report_docx, final_sha)
    require_text_identity(release_notes, final_sha, "release notes")
    require_text_identity(environment_text, final_sha, "environment record")
    validate_environment_locks(environment_locks, final_sha)
    report_provenance = validate_report_provenance(
        report_root,
        report_assets,
        validation_zip,
        packet_verification,
        final_sha,
    )

    with tempfile.TemporaryDirectory(
        prefix=f".{output_root.name}.", dir=output_root.parent
    ) as temporary:
        stage_root = Path(temporary) / "assets"
        identity = populate_and_verify_stage(
            stage_root,
            validation_zip=validation_zip,
            report_md=report_md,
            report_docx=report_docx,
            report_pdf=report_pdf,
            report_assets=report_assets,
            release_notes=release_notes,
            environment_text=environment_text,
            environment_locks=environment_locks,
            receipt=receipt,
            report_provenance=report_provenance,
            audit_digest=audit_digest,
            final_sha=final_sha,
        )
        os.replace(stage_root, output_root)
    return identity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("validation_zip", type=Path)
    parser.add_argument("packet_verification", type=Path)
    parser.add_argument("report_root", type=Path)
    parser.add_argument("release_notes", type=Path)
    parser.add_argument("environment_text", type=Path)
    parser.add_argument("environment_locks", type=Path)
    parser.add_argument("final_sha")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = assemble(
            args.output_root,
            args.validation_zip,
            args.packet_verification,
            args.report_root,
            args.release_notes,
            args.environment_text,
            args.environment_locks,
            args.final_sha,
        )
    except (AssemblyError, OSError) as error:
        raise SystemExit(f"Release-asset assembly failed: {error}") from error
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
