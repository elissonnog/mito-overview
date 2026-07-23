#!/usr/bin/env python3
"""Compare packet-bound v0.3.0 distributions with clean tag rebuilds."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


EXPECTED = {
    "mito_overview-0.3.0-py3-none-any.whl": "wheel",
    "mito_overview-0.3.0.tar.gz": "sdist",
}
EXPECTED_NAME = "mito-overview"
EXPECTED_VERSION = "0.3.0"
EXPECTED_WHEEL_DIST_INFO = "mito_overview-0.3.0.dist-info"
EXPECTED_SDIST_ROOT = "mito_overview-0.3.0"
MAX_ARCHIVE_MEMBERS = 100_000
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024


class DistributionError(ValueError):
    """Raised when distribution identity or member payloads differ."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_member_name(name: str) -> str:
    if "\x00" in name or "\\" in name:
        raise DistributionError(f"unsafe distribution member path: {name!r}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise DistributionError(f"unsafe distribution member path: {name!r}")
    if pure.as_posix() != name.rstrip("/"):
        raise DistributionError(f"noncanonical distribution member path: {name!r}")
    return pure.as_posix()


def parse_metadata(text: str, source: str) -> tuple[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"Name", "Version"} and key not in fields:
            fields[key] = value.strip()
    if set(fields) != {"Name", "Version"}:
        raise DistributionError(f"distribution metadata is incomplete: {source}")
    return fields["Name"], fields["Version"]


def normalized_project_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def wheel_members(path: Path) -> tuple[dict[str, tuple[bytes, bool]], str]:
    members: dict[str, tuple[bytes, bool]] = {}
    casefold_names: set[str] = set()
    expanded_bytes = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                name = safe_member_name(entry.filename)
                mode = (entry.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise DistributionError(f"wheel contains a symlink: {name}")
                if entry.flag_bits & 0x1:
                    raise DistributionError(f"wheel contains an encrypted member: {name}")
                if entry.is_dir():
                    continue
                folded = name.casefold()
                if name in members or folded in casefold_names:
                    raise DistributionError(
                        f"wheel contains a duplicate or case-colliding member: {name}"
                    )
                if entry.file_size > MAX_MEMBER_BYTES:
                    raise DistributionError(f"wheel member exceeds size limit: {name}")
                expanded_bytes += entry.file_size
                if len(members) + 1 > MAX_ARCHIVE_MEMBERS or expanded_bytes > MAX_EXPANDED_BYTES:
                    raise DistributionError("wheel exceeds expanded archive limits")
                payload = archive.read(entry)
                if len(payload) != entry.file_size:
                    raise DistributionError(f"wheel member size differs after decoding: {name}")
                members[name] = (payload, bool(mode & 0o111))
                casefold_names.add(folded)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise DistributionError(f"unable to read wheel {path}") from error
    metadata_name = f"{EXPECTED_WHEEL_DIST_INFO}/METADATA"
    required = {
        metadata_name,
        f"{EXPECTED_WHEEL_DIST_INFO}/WHEEL",
        f"{EXPECTED_WHEEL_DIST_INFO}/RECORD",
    }
    metadata_members = {name for name in members if name.endswith(".dist-info/METADATA")}
    wheel_members_found = {name for name in members if name.endswith(".dist-info/WHEEL")}
    record_members = {name for name in members if name.endswith(".dist-info/RECORD")}
    if not required.issubset(members) or any(
        len(found) != 1
        for found in (metadata_members, wheel_members_found, record_members)
    ):
        raise DistributionError(
            "wheel must contain exactly one canonical METADATA, WHEEL, and RECORD member"
        )
    return members, metadata_name


def sdist_members(path: Path) -> tuple[dict[str, tuple[bytes, bool]], str]:
    members: dict[str, tuple[bytes, bool]] = {}
    casefold_names: set[str] = set()
    expanded_bytes = 0
    try:
        with tarfile.open(path, "r:gz") as archive:
            for entry in archive.getmembers():
                name = safe_member_name(entry.name)
                if name != EXPECTED_SDIST_ROOT and not name.startswith(
                    f"{EXPECTED_SDIST_ROOT}/"
                ):
                    raise DistributionError(
                        f"sdist member is outside canonical project root: {name}"
                    )
                if entry.isdir():
                    continue
                if not entry.isfile() or entry.issym() or entry.islnk() or entry.isdev():
                    raise DistributionError(f"sdist contains a link or special member: {name}")
                folded = name.casefold()
                if name in members or folded in casefold_names:
                    raise DistributionError(
                        f"sdist contains a duplicate or case-colliding member: {name}"
                    )
                if entry.size > MAX_MEMBER_BYTES:
                    raise DistributionError(f"sdist member exceeds size limit: {name}")
                expanded_bytes += entry.size
                if len(members) + 1 > MAX_ARCHIVE_MEMBERS or expanded_bytes > MAX_EXPANDED_BYTES:
                    raise DistributionError("sdist exceeds expanded archive limits")
                handle = archive.extractfile(entry)
                if handle is None:
                    raise DistributionError(f"unable to read sdist member: {name}")
                payload = handle.read()
                if len(payload) != entry.size:
                    raise DistributionError(f"sdist member size differs after decoding: {name}")
                members[name] = (payload, bool(entry.mode & 0o111))
                casefold_names.add(folded)
    except (OSError, tarfile.TarError) as error:
        raise DistributionError(f"unable to read sdist {path}") from error
    metadata_name = f"{EXPECTED_SDIST_ROOT}/PKG-INFO"
    if metadata_name not in members:
        raise DistributionError("sdist must contain the canonical root PKG-INFO member")
    return members, metadata_name


def inspect_distribution(
    path: Path, kind: str
) -> tuple[dict[str, tuple[bytes, bool]], str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise DistributionError(f"distribution must be a non-empty regular file: {path}")
    if kind == "wheel":
        members, metadata_name = wheel_members(path)
    elif kind == "sdist":
        members, metadata_name = sdist_members(path)
    else:
        raise DistributionError(f"unsupported distribution kind: {kind}")
    name, version = parse_metadata(
        members[metadata_name][0].decode("utf-8"), metadata_name
    )
    if normalized_project_name(name) != normalized_project_name(EXPECTED_NAME):
        raise DistributionError(f"distribution project name differs: {name!r}")
    if version != EXPECTED_VERSION:
        raise DistributionError(f"distribution version differs: {version!r}")
    return members, name, version


def require_inventory(
    root: Path, label: str, *, allow_unrelated_files: bool = False
) -> dict[str, Path]:
    if root.is_symlink() or not root.is_dir():
        raise DistributionError(f"{label} must be a regular directory: {root}")
    direct_entries = list(root.iterdir())
    folded_names = [path.name.casefold() for path in direct_entries]
    if len(folded_names) != len(set(folded_names)):
        raise DistributionError(f"{label} contains case-colliding artifact names")
    entries = {path.name: path for path in direct_entries}
    missing = set(EXPECTED) - set(entries)
    unexpected = set(entries) - set(EXPECTED)
    if missing or (unexpected and not allow_unrelated_files):
        raise DistributionError(
            f"{label} inventory differs; missing={sorted(missing)!r}; "
            f"unexpected={sorted(unexpected)!r}"
        )
    return {name: entries[name] for name in EXPECTED}


def member_manifest(
    members: dict[str, tuple[bytes, bool]]
) -> tuple[list[dict[str, Any]], str]:
    rows = [
        {
            "path": name,
            "bytes": len(members[name][0]),
            "sha256": sha256_bytes(members[name][0]),
            "executable": members[name][1],
        }
        for name in sorted(members)
    ]
    encoded = "".join(
        f"{row['path']}\t{row['bytes']}\t{row['sha256']}\t"
        f"{int(row['executable'])}\n"
        for row in rows
    ).encode("utf-8")
    return rows, sha256_bytes(encoded)


def verify(canonical_root: Path, rebuilt_root: Path) -> dict[str, Any]:
    canonical = require_inventory(
        canonical_root,
        "canonical release-asset root",
        allow_unrelated_files=True,
    )
    rebuilt = require_inventory(rebuilt_root, "rebuilt distribution root")
    records: list[dict[str, Any]] = []
    for filename, kind in sorted(EXPECTED.items()):
        canonical_members, canonical_name, canonical_version = inspect_distribution(
            canonical[filename], kind
        )
        rebuilt_members, rebuilt_name, rebuilt_version = inspect_distribution(
            rebuilt[filename], kind
        )
        canonical_rows, canonical_manifest = member_manifest(canonical_members)
        rebuilt_rows, rebuilt_manifest = member_manifest(rebuilt_members)
        if canonical_rows != rebuilt_rows:
            canonical_by_name = {row["path"]: row for row in canonical_rows}
            rebuilt_by_name = {row["path"]: row for row in rebuilt_rows}
            missing = sorted(set(canonical_by_name) - set(rebuilt_by_name))
            unexpected = sorted(set(rebuilt_by_name) - set(canonical_by_name))
            changed = sorted(
                name
                for name in set(canonical_by_name) & set(rebuilt_by_name)
                if canonical_by_name[name] != rebuilt_by_name[name]
            )
            raise DistributionError(
                f"{filename} member payloads differ; missing={missing!r}; "
                f"unexpected={unexpected!r}; changed={changed!r}"
            )
        records.append(
            {
                "filename": filename,
                "kind": kind,
                "name": canonical_name,
                "version": canonical_version,
                "rebuilt_name": rebuilt_name,
                "rebuilt_version": rebuilt_version,
                "canonical_sha256": sha256_file(canonical[filename]),
                "rebuilt_sha256": sha256_file(rebuilt[filename]),
                "archive_bytes_identical": sha256_file(canonical[filename])
                == sha256_file(rebuilt[filename]),
                "member_count": len(canonical_rows),
                "expanded_bytes": sum(row["bytes"] for row in canonical_rows),
                "member_manifest_sha256": canonical_manifest,
                "rebuilt_member_manifest_sha256": rebuilt_manifest,
                "member_payloads_identical": True,
            }
        )
    return {
        "schema_version": "1.0",
        "evidence_type": "distribution_payload_equivalence",
        "release_version": "v0.3.0",
        "comparison": (
            "exact member paths, sizes, executable state, and SHA-256 payloads; "
            "container timestamps and compression metadata ignored"
        ),
        "distributions": records,
        "verified": True,
        "verdict": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("canonical_root", type=Path)
    parser.add_argument("rebuilt_root", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.canonical_root, args.rebuilt_root)
    except (DistributionError, OSError, UnicodeDecodeError) as error:
        raise SystemExit(f"Distribution equivalence failed: {error}") from error
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
