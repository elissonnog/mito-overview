#!/usr/bin/env python3
"""Verify that prebuilt v0.3.1 release assets describe one exact release commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path
from typing import Any


VERSION = "v0.3.1"
TAG = "v0.3.1"
SCIENTIFIC_PROTOCOL_VERSION = "v0.3.0"
PROFILE = "github_release_validation_v1"
ZIP_NAME = "mito-overview-v0.3.1-validation.zip"
VERIFICATION_NAME = "mito-overview-v0.3.1-verification.json"
REPORT_ASSETS = {
    "MitoOverview_v0.3.1_release_validation_report.md",
    "MitoOverview_v0.3.1_release_validation_report.docx",
    "MitoOverview_v0.3.1_release_validation_report.pdf",
    "MitoOverview_v0.3.1_release_validation_report_assets.tar.gz",
    "RELEASE_NOTES_v0.3.1.md",
    "mito-overview-v0.3.1-environment.txt",
    "mito-overview-v0.3.1-environment-locks.tar.gz",
}
DISTRIBUTION_ASSETS = {
    "mito_overview-0.3.1-py3-none-any.whl": "wheel",
    "mito_overview-0.3.1.tar.gz": "sdist",
}
REPORT_STEM = "MitoOverview_v0.3.1_release_validation_report"
REPORT_ASSET_ARCHIVE = f"{REPORT_STEM}_assets.tar.gz"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA256_LINE_RE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)$")


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


def read_sha256_manifest(path: Path) -> dict[str, str]:
    """Read a strict SHA256SUMS file or one-line SHA-256 sidecar."""

    if path.is_symlink() or not path.is_file():
        raise IdentityError(f"SHA-256 source must be a regular non-symlink file: {path}")
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise IdentityError(f"SHA-256 source is not ASCII text: {path}") from error
    if not lines:
        raise IdentityError(f"SHA-256 source is empty: {path}")
    records: dict[str, str] = {}
    for line in lines:
        match = SHA256_LINE_RE.fullmatch(line)
        if match is None or match.group(2) in records:
            raise IdentityError(f"SHA-256 source is malformed or duplicated: {path}")
        records[match.group(2)] = match.group(1)
    return records


def release_identity_archive_digest(
    path: Path,
    archive_name: str,
    *,
    repository_url: str | None,
    final_sha: str | None,
) -> str:
    """Resolve the archive digest from a separately supplied release identity."""

    payload = read_object(path, "external release identity")
    repository_url = repository_url.rstrip("/") if repository_url else None
    if payload.get("evidence_type") == "release_validation_archive_verification":
        expected: dict[str, Any] = {
            "schema_version": "2.0",
            "validation_profile": PROFILE,
            "release_version": VERSION,
            "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
            "audit_zip": archive_name,
        }
        if final_sha is not None:
            expected["git_commit"] = final_sha
        require_fields(payload, expected, "external release identity")
        recorded_repository = payload.get("repository")
        if recorded_repository is None:
            manifest = payload.get("report_asset_manifest")
            if isinstance(manifest, dict):
                recorded_repository = manifest.get("repository")
        if repository_url is not None and recorded_repository != repository_url:
            raise IdentityError(
                "external release identity repository mismatch: "
                f"{recorded_repository!r} != {repository_url!r}"
            )
        digest = payload.get("audit_zip_sha256")
    elif payload.get("manifest_type") == "trusted_release_asset_manifest":
        expected = {
            "release_version": VERSION,
            "release_tag": TAG,
            "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
        }
        if final_sha is not None:
            expected["git_commit"] = final_sha
        if repository_url is not None:
            expected["repository"] = repository_url
        require_fields(payload, expected, "external release identity")
        rows = payload.get("assets")
        if not isinstance(rows, list):
            raise IdentityError("external release identity assets must be a list")
        matches = [
            row
            for row in rows
            if isinstance(row, dict) and row.get("name") == archive_name
        ]
        if len(matches) != 1:
            raise IdentityError(
                "external release identity must contain exactly one validation ZIP asset"
            )
        digest = matches[0].get("sha256")
    else:
        raise IdentityError("unsupported external release identity type")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise IdentityError("external release identity has an invalid archive SHA-256")
    return digest


def verify_archive_digest(
    archive: Path,
    *,
    expected_sha256: str | None = None,
    sha256_sidecar: Path | None = None,
    release_identity: Path | None = None,
    repository_url: str | None = None,
    final_sha: str | None = None,
) -> dict[str, Any]:
    """Verify a ZIP against exactly one digest source located outside the ZIP."""

    sources = sum(
        value is not None
        for value in (expected_sha256, sha256_sidecar, release_identity)
    )
    if sources != 1:
        raise IdentityError(
            "exactly one external digest source is required: expected SHA-256, "
            "sidecar/SHA256SUMS, or release identity"
        )
    if archive.is_symlink() or not archive.is_file():
        raise IdentityError(f"validation archive must be a regular non-symlink file: {archive}")
    if archive.name != ZIP_NAME:
        raise IdentityError(f"validation archive name must be {ZIP_NAME}")

    source_type: str
    source_name: str
    if expected_sha256 is not None:
        expected = expected_sha256.lower()
        if SHA256_RE.fullmatch(expected) is None:
            raise IdentityError("expected archive SHA-256 must be 64 lowercase hexadecimal characters")
        source_type = "expected_sha256"
        source_name = "command_line_expected_sha256"
    elif sha256_sidecar is not None:
        records = read_sha256_manifest(sha256_sidecar)
        if archive.name not in records:
            raise IdentityError(
                f"SHA-256 source does not contain the validation archive: {archive.name}"
            )
        expected = records[archive.name]
        source_type = "sha256_sidecar_or_manifest"
        source_name = sha256_sidecar.name
    else:
        assert release_identity is not None
        expected = release_identity_archive_digest(
            release_identity,
            archive.name,
            repository_url=repository_url,
            final_sha=final_sha,
        )
        source_type = "release_identity"
        source_name = release_identity.name

    observed = sha256(archive)
    if observed != expected:
        raise IdentityError(
            "external archive SHA-256 mismatch: "
            f"observed {observed}, expected {expected} from {source_name}"
        )
    return {
        "schema_version": "1.0",
        "evidence_type": "external_archive_digest_verification",
        "release_version": VERSION,
        "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
        "archive_name": archive.name,
        "archive_sha256": observed,
        "digest_source_type": source_type,
        "digest_source_name": source_name,
        "trust_boundary": (
            "This verifies archive bytes against a digest supplied outside the ZIP; "
            "the digest source must be authenticated independently."
        ),
        "verified": True,
        "verdict": "PASS",
    }


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
            "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
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
            "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
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
            "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
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
    if (
        page_qa.get("pdf_page_count") != len(pages)
        or page_qa.get("page_count_matches_pdf") is not True
    ):
        raise IdentityError("report provenance does not prove complete PDF page rendering")
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


def verify_distribution_assets(
    asset_root: Path,
    packet_root: Path,
    verification: dict[str, Any],
    release_identity: dict[str, Any],
    repository_url: str,
    final_sha: str,
) -> list[dict[str, Any]]:
    """Require release distributions to be the exact packet-validated bytes."""

    declared = release_identity.get("dist_artifacts")
    if not isinstance(declared, list) or not all(isinstance(row, dict) for row in declared):
        raise IdentityError("packet release identity lacks distribution artifacts")
    declared_by_name: dict[str, dict[str, Any]] = {}
    expected_fields = {
        "path",
        "kind",
        "name",
        "version",
        "bytes",
        "sha256",
        "direct_url_archive_sha256",
    }
    for row in declared:
        if set(row) != expected_fields:
            raise IdentityError("packet distribution artifact fields differ from schema")
        path = row.get("path")
        if not isinstance(path, str) or not path.startswith("dist/"):
            raise IdentityError("packet distribution artifact path is invalid")
        name = Path(path).name
        if name in declared_by_name:
            raise IdentityError(f"packet distribution artifact is duplicated: {name}")
        declared_by_name[name] = row
    if set(declared_by_name) != set(DISTRIBUTION_ASSETS):
        raise IdentityError("packet distribution artifact inventory differs")

    manifest = verification.get("distribution_asset_manifest")
    if not isinstance(manifest, dict):
        raise IdentityError("adjacent verification JSON lacks distribution_asset_manifest")
    require_fields(
        manifest,
        {
            "schema_version": "1.0",
            "manifest_type": "distribution_asset_manifest",
            "repository": repository_url,
            "release_version": VERSION,
            "release_tag": TAG,
            "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
            "git_commit": final_sha,
        },
        "distribution_asset_manifest",
    )
    manifest_rows = manifest.get("assets")
    if not isinstance(manifest_rows, list):
        raise IdentityError("distribution_asset_manifest assets must be a list")
    manifest_by_name: dict[str, dict[str, Any]] = {}
    for row in manifest_rows:
        if not isinstance(row, dict) or set(row) != {"name", "bytes", "sha256"}:
            raise IdentityError("distribution_asset_manifest contains a malformed entry")
        name = row.get("name")
        if not isinstance(name, str) or name in manifest_by_name:
            raise IdentityError("distribution_asset_manifest contains a duplicate or unnamed entry")
        manifest_by_name[name] = row
    if set(manifest_by_name) != set(DISTRIBUTION_ASSETS):
        raise IdentityError("distribution_asset_manifest inventory differs")

    verified: list[dict[str, Any]] = []
    for name, kind in sorted(DISTRIBUTION_ASSETS.items()):
        packet_path = packet_root / "dist" / name
        asset_path = asset_root / name
        for path, label in ((packet_path, "packet"), (asset_path, "release")):
            if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
                raise IdentityError(f"{label} distribution is not a regular file: {name}")
        packet_sha256 = sha256(packet_path)
        asset_sha256 = sha256(asset_path)
        if packet_sha256 != asset_sha256 or packet_path.stat().st_size != asset_path.stat().st_size:
            raise IdentityError(f"release distribution bytes differ from packet: {name}")
        declared_row = declared_by_name[name]
        if (
            declared_row.get("path") != f"dist/{name}"
            or declared_row.get("kind") != kind
            or declared_row.get("version") != VERSION.removeprefix("v")
            or str(declared_row.get("name", "")).lower().replace("_", "-")
            != "mito-overview"
            or declared_row.get("bytes") != packet_path.stat().st_size
            or declared_row.get("sha256") != packet_sha256
            or declared_row.get("direct_url_archive_sha256") != packet_sha256
        ):
            raise IdentityError(f"packet distribution identity mismatch: {name}")
        manifest_row = manifest_by_name[name]
        if manifest_row != {
            "name": name,
            "bytes": asset_path.stat().st_size,
            "sha256": asset_sha256,
        }:
            raise IdentityError(f"distribution asset manifest mismatch: {name}")
        verified.append(dict(declared_row))
    return verified


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

    archive = asset_root / ZIP_NAME
    verification_path = asset_root / VERIFICATION_NAME
    verify_archive_digest(
        archive,
        release_identity=verification_path,
        repository_url=repository_url,
        final_sha=final_sha,
    )
    verification = read_object(verification_path, "adjacent verification JSON")

    run = read_object(packet_root / "run.json", "packet run.json")
    identity = read_object(
        packet_root / "release_identity.json", "packet release_identity.json"
    )
    expected_packet = {
        "schema_version": "2.0",
        "validation_profile": PROFILE,
        "release_version": VERSION,
        "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
        "git_commit": final_sha,
        "repository": repository_url,
    }
    require_fields(run, expected_packet, "packet run.json")
    require_fields(identity, expected_packet, "packet release_identity.json")
    if identity.get("package_name") != "mito-overview":
        raise IdentityError("packet package_name is not mito-overview")
    if identity.get("package_version") != VERSION.removeprefix("v"):
        raise IdentityError("packet package_version does not match v0.3.1")

    archive_digest = sha256(archive)
    require_fields(
        verification,
        {
            "schema_version": "2.0",
            "validation_profile": PROFILE,
            "evidence_type": "release_validation_archive_verification",
            "verdict": "PASS",
            "release_version": VERSION,
            "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
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
            "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
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

    distributions = verify_distribution_assets(
        asset_root,
        packet_root,
        verification,
        identity,
        repository_url,
        final_sha,
    )
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
        "scientific_protocol_version": SCIENTIFIC_PROTOCOL_VERSION,
        "git_commit": final_sha,
        "validation_zip": ZIP_NAME,
        "validation_zip_sha256": archive_digest,
        "packet_verifier_executed": True,
        "report_asset_count": len(REPORT_ASSETS),
        "report_assets": [by_name[name] for name in sorted(by_name)],
        "distribution_asset_count": len(distributions),
        "distribution_assets": distributions,
        "distribution_bytes_match_packet": True,
        "report_provenance_verified": True,
        "report_figure_count": len(report_provenance["figures"]),
        "rendered_page_count": report_provenance["rendered_page_qa"]["page_count"],
        "verified": True,
        "verdict": "PASS",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["archive-digest"]:
        parser = argparse.ArgumentParser(
            description=(
                "Verify the v0.3.1 validation ZIP against one expected digest "
                "supplied outside the archive."
            )
        )
        parser.set_defaults(command="archive-digest")
        parser.add_argument("command_token", choices=("archive-digest",))
        parser.add_argument("archive", type=Path)
        sources = parser.add_mutually_exclusive_group(required=True)
        sources.add_argument("--expected-sha256")
        sources.add_argument("--sha256-sidecar", type=Path)
        sources.add_argument("--release-identity", type=Path)
        parser.add_argument("--repository-url")
        parser.add_argument("--final-sha")
        parser.add_argument("--output-json", type=Path)
        return parser.parse_args(arguments)

    parser = argparse.ArgumentParser()
    parser.set_defaults(command="semantic-identity")
    parser.add_argument("asset_root", type=Path)
    parser.add_argument("packet_root", type=Path)
    parser.add_argument("repository_url")
    parser.add_argument("final_sha")
    parser.add_argument("output_json", type=Path)
    return parser.parse_args(arguments)


def main() -> None:
    args = parse_args()
    if args.command == "archive-digest":
        if args.final_sha is not None and re.fullmatch(r"[0-9a-f]{40}", args.final_sha) is None:
            raise SystemExit("External archive-digest verification failed: invalid FINAL_SHA")
        try:
            result = verify_archive_digest(
                args.archive,
                expected_sha256=args.expected_sha256,
                sha256_sidecar=args.sha256_sidecar,
                release_identity=args.release_identity,
                repository_url=args.repository_url,
                final_sha=args.final_sha,
            )
        except (IdentityError, OSError) as error:
            raise SystemExit(f"External archive-digest verification failed: {error}") from error
        if args.output_json is not None:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        else:
            print(
                "verified external archive digest: "
                f"{result['archive_name']} {result['archive_sha256']}"
            )
        return
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
