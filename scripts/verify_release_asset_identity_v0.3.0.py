#!/usr/bin/env python3
"""Verify that prebuilt v0.3.0 release assets describe one exact release commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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


class IdentityError(ValueError):
    """Raised when supplied release assets do not share one release identity."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
