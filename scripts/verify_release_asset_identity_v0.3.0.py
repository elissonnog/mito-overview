#!/usr/bin/env python3
"""Verify that prebuilt v0.3.0 release assets describe one exact release commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path
from typing import Any


VERSION = "v0.3.0"
TAG = "v0.3.0"
PROFILE = "github_release_validation_v1"
ZIP_NAME = "mito-overview-v0.3.0-validation.zip"
VERIFICATION_NAME = "mito-overview-v0.3.0-verification.json"
REPORT_ASSETS = {
    "MitoOverview_v0.3.0_release_validation_report.md",
    "MitoOverview_v0.3.0_release_validation_report.docx",
    "MitoOverview_v0.3.0_release_validation_report.pdf",
    "MitoOverview_v0.3.0_release_validation_report_assets.tar.gz",
    "RELEASE_NOTES_v0.3.0.md",
    "mito-overview-v0.3.0-environment.txt",
    "mito-overview-v0.3.0-environment-locks.tar.gz",
}
REPORT_STEM = "MitoOverview_v0.3.0_release_validation_report"
REPORT_ASSET_ARCHIVE = f"{REPORT_STEM}_assets.tar.gz"


class IdentityError(ValueError):
    """Raised when supplied release assets do not share one release identity."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise IdentityError(f"{label} must be a regular non-symlink file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IdentityError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise IdentityError(f"{label} must contain a JSON object: {path}")
    return value


def require_fields(value: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for field, wanted in expected.items():
        observed = value.get(field)
        if observed != wanted:
            raise IdentityError(
                f"{label} identity mismatch for {field}: {observed!r} != {wanted!r}"
            )


def read_report_archive(path: Path) -> dict[str, bytes]:
    """Read only regular, canonical report-asset members from the release archive."""

    files: dict[str, bytes] = {}
    try:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                pure = Path(member.name)
                if pure.is_absolute() or ".." in pure.parts:
                    raise IdentityError(f"report asset archive has unsafe path: {member.name}")
                if member.issym() or member.islnk() or member.isdev():
                    raise IdentityError(
                        f"report asset archive has a link or special member: {member.name}"
                    )
                if member.isdir():
                    continue
                if not member.isfile() or member.name in files:
                    raise IdentityError(
                        f"report asset archive has an invalid member: {member.name}"
                    )
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise IdentityError(f"unable to read report asset: {member.name}")
                files[member.name] = extracted.read()
    except (tarfile.TarError, OSError) as error:
        raise IdentityError(f"report asset archive is malformed: {path}") from error
    return files


def verify_report_provenance(
    asset_root: Path,
    packet_root: Path,
    verification: dict[str, Any],
    archive_digest: str,
    repository_url: str,
    final_sha: str,
) -> dict[str, Any]:
    binding = verification.get("report_build_provenance")
    if not isinstance(binding, dict):
        raise IdentityError("adjacent verification JSON lacks report_build_provenance")
    require_fields(
        binding,
        {
            "schema_version": "1.0",
            "provenance_type": "release_report_provenance_binding",
            "repository": repository_url,
            "release_version": VERSION,
            "release_tag": TAG,
            "git_commit": final_sha,
            "validation_zip_sha256": archive_digest,
            "visual_review_status": "PASS",
        },
        "report_build_provenance",
    )
    report_archive = asset_root / REPORT_ASSET_ARCHIVE
    if binding.get("report_asset_archive_sha256") != sha256(report_archive):
        raise IdentityError("report provenance is bound to a different asset archive")
    files = read_report_archive(report_archive)
    provenance_name = binding.get("report_provenance_archive_path")
    if not isinstance(provenance_name, str) or provenance_name not in files:
        raise IdentityError("report provenance receipt is absent from report asset archive")
    provenance_bytes = files[provenance_name]
    if binding.get("report_provenance_sha256") != sha256_bytes(provenance_bytes):
        raise IdentityError("report provenance receipt SHA-256 mismatch")
    try:
        provenance = json.loads(provenance_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IdentityError("report provenance receipt is not valid JSON") from error
    if not isinstance(provenance, dict):
        raise IdentityError("report provenance receipt must be a JSON object")
    require_fields(
        provenance,
        {
            "schema_version": "1.0",
            "provenance_type": "mito_overview_finalized_release_report",
            "repository": repository_url,
            "release_version": VERSION,
            "release_tag": TAG,
            "git_commit": final_sha,
            "validation_profile": PROFILE,
            "packet_verification_verdict": "PASS",
            "packet_verifier_executed": True,
        },
        "archived report provenance",
    )
    validation_archive = provenance.get("validation_archive")
    if not isinstance(validation_archive, dict) or validation_archive.get(
        "sha256"
    ) != archive_digest:
        raise IdentityError("archived report provenance is bound to another validation ZIP")

    build_name = f"{REPORT_STEM}_assets/report_build_provenance.json"
    build_bytes = files.get(build_name)
    build_record = provenance.get("report_build_provenance")
    if build_bytes is None or not isinstance(build_record, dict):
        raise IdentityError("archived report build provenance is absent")
    if build_record.get("bytes") != len(build_bytes) or build_record.get(
        "sha256"
    ) != sha256_bytes(build_bytes):
        raise IdentityError("archived report build provenance hash/size mismatch")
    try:
        build = json.loads(build_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IdentityError("report build provenance is not valid JSON") from error
    if not isinstance(build, dict):
        raise IdentityError("report build provenance must be a JSON object")
    require_fields(
        build,
        {
            "schema_version": "1.0",
            "provenance_type": "mito_overview_release_report_build",
            "repository": repository_url,
            "release_version": VERSION,
            "release_tag": TAG,
            "git_commit": final_sha,
            "validation_profile": PROFILE,
            "rendered_page_qa_required": True,
        },
        "archived report build provenance",
    )
    packet_identity = build.get("packet_identity")
    if not isinstance(packet_identity, dict):
        raise IdentityError("report build provenance lacks packet_identity")
    for name in ("run.json", "release_identity.json", "artifacts.sha256"):
        row = packet_identity.get(name)
        path = packet_root / name
        if not isinstance(row, dict) or path.is_symlink() or not path.is_file():
            raise IdentityError(f"report build provenance lacks packet record: {name}")
        if row.get("bytes") != path.stat().st_size or row.get("sha256") != sha256(path):
            raise IdentityError(f"report build provenance packet hash/size mismatch: {name}")
    if provenance.get("packet_artifacts_manifest_sha256") != sha256(
        packet_root / "artifacts.sha256"
    ):
        raise IdentityError("final report provenance names another packet manifest")

    outputs = provenance.get("report_outputs")
    if not isinstance(outputs, dict) or outputs != binding.get("report_outputs"):
        raise IdentityError("report output inventory differs between provenance receipts")
    output_paths = {
        "markdown": asset_root / f"{REPORT_STEM}.md",
        "docx": asset_root / f"{REPORT_STEM}.docx",
        "pdf": asset_root / f"{REPORT_STEM}.pdf",
    }
    for label, path in output_paths.items():
        row = outputs.get(label)
        if not isinstance(row, dict):
            raise IdentityError(f"report provenance lacks {label} output")
        if row.get("name") != path.name:
            raise IdentityError(f"report provenance names the wrong {label} output")
        if row.get("bytes") != path.stat().st_size or row.get("sha256") != sha256(path):
            raise IdentityError(f"report provenance {label} output hash/size mismatch")
    build_outputs = build.get("report_outputs")
    if not isinstance(build_outputs, dict):
        raise IdentityError("report build provenance lacks report_outputs")
    for label in ("markdown", "docx"):
        if build_outputs.get(label) != outputs[label]:
            raise IdentityError(f"report {label} differs from recorded build output")

    root_name = f"{REPORT_STEM}_assets"
    expected_files = {
        f"{root_name}/figure_manifest.tsv",
        f"{root_name}/report_build_provenance.json",
        f"{root_name}/report_provenance.json",
    }
    figures = provenance.get("figures")
    if (
        not isinstance(figures, list)
        or figures != build.get("figures")
        or len(figures) != binding.get("figure_count")
    ):
        raise IdentityError("report provenance figure inventory is incomplete")
    manifest_record = provenance.get("figure_manifest")
    manifest_name = f"{root_name}/figure_manifest.tsv"
    manifest_content = files.get(manifest_name)
    if (
        manifest_record != build.get("figure_manifest")
        or not isinstance(manifest_record, dict)
        or manifest_content is None
        or manifest_record.get("bytes") != len(manifest_content)
        or manifest_record.get("sha256") != sha256_bytes(manifest_content)
    ):
        raise IdentityError("report figure manifest differs from build provenance")
    for row in figures:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise IdentityError("report provenance has a malformed figure record")
        name = row["name"]
        if name not in files:
            raise IdentityError(f"report provenance figure is absent: {name}")
        content = files[name]
        if row.get("bytes") != len(content) or row.get("sha256") != sha256_bytes(content):
            raise IdentityError(f"report provenance figure hash/size mismatch: {name}")
        if row.get("sha256") != row.get("packet_sha256"):
            raise IdentityError(f"report figure is not packet-native: {name}")
        packet_relative = row.get("packet_path")
        if not isinstance(packet_relative, str):
            raise IdentityError(f"report figure lacks packet source path: {name}")
        packet_source = packet_root / packet_relative
        try:
            packet_source.resolve(strict=True).relative_to(packet_root)
        except (FileNotFoundError, ValueError) as error:
            raise IdentityError(
                f"report figure packet source is missing or unsafe: {packet_relative}"
            ) from error
        if packet_source.is_symlink() or not packet_source.is_file():
            raise IdentityError(f"report figure packet source is not regular: {packet_relative}")
        if sha256(packet_source) != row.get("packet_sha256"):
            raise IdentityError(f"report figure differs from packet source: {packet_relative}")
        expected_files.add(name)

    page_qa = provenance.get("rendered_page_qa")
    if not isinstance(page_qa, dict):
        raise IdentityError("report provenance lacks rendered-page QA")
    if page_qa.get("status") != "PASS" or page_qa.get("all_pages_inspected") is not True:
        raise IdentityError("report provenance rendered-page QA did not pass")
    pages = page_qa.get("pages")
    if not isinstance(pages, list) or len(pages) != binding.get("rendered_page_count"):
        raise IdentityError("report provenance rendered-page inventory is incomplete")
    if page_qa.get("source_docx_sha256") != outputs["docx"]["sha256"]:
        raise IdentityError("rendered pages are bound to another DOCX")
    if page_qa.get("rendered_pdf_sha256") != outputs["pdf"]["sha256"]:
        raise IdentityError("rendered pages are bound to another PDF")
    for number, row in enumerate(pages, 1):
        if not isinstance(row, dict) or row.get("page_number") != number:
            raise IdentityError("report provenance page sequence is malformed")
        name = row.get("name")
        if not isinstance(name, str) or name not in files:
            raise IdentityError(f"rendered report page is absent: {name!r}")
        content = files[name]
        if row.get("bytes") != len(content) or row.get("sha256") != sha256_bytes(content):
            raise IdentityError(f"rendered report page hash/size mismatch: {name}")
        if row.get("visual_review_status") != "PASS":
            raise IdentityError(f"rendered report page lacks PASS review: {name}")
        expected_files.add(name)
    if set(files) != expected_files:
        raise IdentityError(
            "report asset archive inventory mismatch; "
            f"missing={sorted(expected_files - set(files))!r}; "
            f"unexpected={sorted(set(files) - expected_files)!r}"
        )
    return provenance


def verify(
    asset_root: Path,
    packet_root: Path,
    repository_url: str,
    final_sha: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", final_sha):
        raise IdentityError("FINAL_SHA must be 40 lowercase hexadecimal characters")
    repository_url = repository_url.rstrip("/")
    repository_slug = repository_url.removeprefix("https://github.com/")
    if repository_slug == repository_url or repository_slug.count("/") != 1:
        raise IdentityError("repository must be a canonical GitHub HTTPS URL")

    if asset_root.is_symlink() or not asset_root.is_dir():
        raise IdentityError("asset root must be a regular non-symlink directory")
    if packet_root.is_symlink() or not packet_root.is_dir():
        raise IdentityError("packet root must be a regular non-symlink directory")
    asset_root = asset_root.resolve(strict=True)
    packet_root = packet_root.resolve(strict=True)
    run = read_object(packet_root / "run.json", "packet run.json")
    identity = read_object(
        packet_root / "release_identity.json", "packet release_identity.json"
    )
    expected_packet = {
        "schema_version": "2.0",
        "validation_profile": PROFILE,
        "release_version": VERSION,
        "git_commit": final_sha,
        "repository": repository_url,
    }
    require_fields(run, expected_packet, "packet run.json")
    require_fields(identity, expected_packet, "packet release_identity.json")
    if identity.get("package_name") != "mito-overview":
        raise IdentityError("packet package_name is not mito-overview")
    if identity.get("package_version") != VERSION.removeprefix("v"):
        raise IdentityError("packet package_version does not match v0.3.0")

    archive = asset_root / ZIP_NAME
    if archive.is_symlink() or not archive.is_file():
        raise IdentityError("validation archive must be a regular non-symlink file")
    verification = read_object(
        asset_root / VERIFICATION_NAME, "adjacent verification JSON"
    )
    archive_digest = sha256(archive)
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
        },
        "adjacent verification JSON",
    )
    verifier_runs = verification.get("verifier_runs")
    if verifier_runs != ["packet_root", "fresh_audit_zip_extraction"]:
        raise IdentityError("adjacent verification JSON lacks both packet verifier runs")

    manifest = verification.get("report_asset_manifest")
    if not isinstance(manifest, dict):
        raise IdentityError("adjacent verification JSON lacks report_asset_manifest")
    require_fields(
        manifest,
        {
            "schema_version": "1.0",
            "manifest_type": "report_asset_manifest",
            "repository": repository_url,
            "repository_slug": repository_slug,
            "release_version": VERSION,
            "release_tag": TAG,
            "git_commit": final_sha,
        },
        "report_asset_manifest",
    )
    rows = manifest.get("assets")
    if not isinstance(rows, list):
        raise IdentityError("report_asset_manifest assets must be a list")
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise IdentityError("report_asset_manifest contains a malformed asset entry")
        name = row["name"]
        if name in by_name:
            raise IdentityError(f"report_asset_manifest duplicates asset: {name}")
        by_name[name] = row
    if set(by_name) != REPORT_ASSETS:
        raise IdentityError(
            "report_asset_manifest inventory mismatch; "
            f"missing={sorted(REPORT_ASSETS - set(by_name))!r}; "
            f"unexpected={sorted(set(by_name) - REPORT_ASSETS)!r}"
        )
    for name in sorted(REPORT_ASSETS):
        path = asset_root / name
        if path.is_symlink() or not path.is_file():
            raise IdentityError(f"report asset must be a regular non-symlink file: {name}")
        row = by_name[name]
        if row.get("size") != path.stat().st_size:
            raise IdentityError(f"report asset size mismatch: {name}")
        if row.get("sha256") != sha256(path):
            raise IdentityError(f"report asset SHA-256 mismatch: {name}")

    report_provenance = verify_report_provenance(
        asset_root,
        packet_root,
        verification,
        archive_digest,
        repository_url,
        final_sha,
    )

    return {
        "schema_version": "1.0",
        "evidence_type": "release_asset_semantic_identity",
        "repository": repository_url,
        "repository_slug": repository_slug,
        "release_version": VERSION,
        "release_tag": TAG,
        "git_commit": final_sha,
        "validation_zip": ZIP_NAME,
        "validation_zip_sha256": archive_digest,
        "packet_verifier_executed": True,
        "report_asset_count": len(REPORT_ASSETS),
        "report_assets": [by_name[name] for name in sorted(by_name)],
        "report_provenance_verified": True,
        "report_figure_count": len(report_provenance["figures"]),
        "rendered_page_count": report_provenance["rendered_page_qa"]["page_count"],
        "verified": True,
        "verdict": "PASS",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_root", type=Path)
    parser.add_argument("packet_root", type=Path)
    parser.add_argument("repository_url")
    parser.add_argument("final_sha")
    parser.add_argument("output_json", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = verify(
            args.asset_root, args.packet_root, args.repository_url, args.final_sha
        )
    except (IdentityError, OSError) as error:
        raise SystemExit(f"Release-asset semantic identity verification failed: {error}") from error
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
