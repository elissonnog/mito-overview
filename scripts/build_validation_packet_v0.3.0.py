#!/usr/bin/env python3
"""Build the self-checking mito-overview v0.3.0 validation packet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import stat
import subprocess
import tarfile
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_RELEASE_VERSION = "v0.3.0"
EXPECTED_PACKAGE_NAME = "mito-overview"

REQUIRED_TOP_LEVEL = (
    "run.json",
    "release_identity.json",
    "cases.tsv",
    "claim_evidence_matrix.tsv",
    "public_data_sources.tsv",
    "environment.txt",
    "commands",
    "logs",
    "dist",
    "expected",
    "observed_normalized",
    "filter_profile_results.tsv",
    "inputs.sha256",
    "artifacts.sha256",
    "verify_bundle.sh",
)

REQUIRED_PASS_CASES = {
    "unit_known_answer",
    "cli_step_listing",
    "strict_generic_dry_run",
    "synthetic_longread_smoke",
    "synthetic_shortread_smoke",
    "synthetic_longread_nomethyl_smoke",
    "standalone_minimal_smoke",
    "package_build",
    "public_validation_matrix",
    "gm11906_default_run1",
    "gm11906_default_run2",
    "gm11906_lenient",
    "gm11906_strict",
    "gm12878_default_run1",
    "gm12878_default_run2",
    "gm12878_lenient",
    "gm12878_strict",
    "gm11906_repeatability",
    "gm12878_repeatability",
    "gm11906_visual_integrity",
    "gm12878_visual_integrity",
    "filter_profiles",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("validation_root", type=Path)
    parser.add_argument("packet_root", type=Path)
    parser.add_argument("zip_path", type=Path)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Clean Git repository whose HEAD and metadata define the release identity",
    )
    parser.add_argument(
        "--commit",
        help="Deprecated identity assertion; when supplied it must equal repository HEAD",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--version", default=EXPECTED_RELEASE_VERSION)
    parser.add_argument("--repository", default="https://github.com/elissonnog/mito-overview")
    parser.add_argument("--doi", default="UNRESERVED")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Required directory not found: {source}")
    if not any(path.is_file() for path in source.rglob("*")):
        raise ValueError(f"Required directory contains no evidence files: {source}")
    shutil.copytree(source, destination)


def git_output(repo_root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise ValueError(f"Unable to inspect release repository: {detail.strip()}") from error
    return result.stdout.strip()


def normalize_project_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def parse_environment_identity(path: Path) -> dict[str, str]:
    required = {"release_version", "git_commit", "repository"}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in required:
            continue
        if key in values:
            raise ValueError(f"environment.txt contains duplicate identity key: {key}")
        values[key] = value.strip()
    missing = sorted(required - values.keys())
    if missing:
        raise ValueError(f"environment.txt is missing release identity keys: {', '.join(missing)}")
    return values


def read_release_metadata(repo_root: Path) -> tuple[str, dict[str, str], dict[str, str]]:
    metadata_paths = {
        "pyproject.toml": repo_root / "pyproject.toml",
        "mito_overview/__init__.py": repo_root / "mito_overview" / "__init__.py",
        "CITATION.cff": repo_root / "CITATION.cff",
    }
    for label, path in metadata_paths.items():
        if not path.is_file():
            raise ValueError(f"Release metadata file is missing: {label}")

    project = tomllib.loads(metadata_paths["pyproject.toml"].read_text(encoding="utf-8"))
    project_table = project.get("project", {})
    package_name = str(project_table.get("name", "")).strip()
    pyproject_version = str(project_table.get("version", "")).strip()

    init_text = metadata_paths["mito_overview/__init__.py"].read_text(encoding="utf-8")
    init_match = re.search(
        r"(?m)^__version__\s*=\s*['\"]([^'\"]+)['\"]\s*$",
        init_text,
    )
    if init_match is None:
        raise ValueError("mito_overview/__init__.py does not define a literal __version__")

    citation_text = metadata_paths["CITATION.cff"].read_text(encoding="utf-8")
    citation_match = re.search(r"(?m)^version:\s*([^\s#]+)", citation_text)
    if citation_match is None:
        raise ValueError("CITATION.cff does not define a top-level version")
    citation_version = citation_match.group(1).strip("'\"")

    versions = {
        "pyproject.toml": pyproject_version,
        "mito_overview/__init__.py": init_match.group(1),
        "CITATION.cff": citation_version,
    }
    hashes = {label: sha256(path) for label, path in metadata_paths.items()}
    return package_name, versions, hashes


def parse_distribution_metadata(text: str, source: Path) -> tuple[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"Name", "Version"} and key not in fields:
            fields[key] = value.strip()
    if not fields.get("Name") or not fields.get("Version"):
        raise ValueError(f"Distribution metadata lacks Name or Version: {source}")
    return fields["Name"], fields["Version"]


def inspect_distribution(path: Path) -> tuple[str, str, str]:
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            members = sorted(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            )
            if len(members) != 1:
                raise ValueError(f"Wheel must contain exactly one METADATA file: {path}")
            text = archive.read(members[0]).decode("utf-8")
        kind = "wheel"
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = sorted(
                (member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")),
                key=lambda member: member.name,
            )
            if len(members) != 1:
                raise ValueError(f"Source archive must contain exactly one PKG-INFO file: {path}")
            handle = archive.extractfile(members[0])
            if handle is None:
                raise ValueError(f"Unable to read PKG-INFO from source archive: {path}")
            text = handle.read().decode("utf-8")
        kind = "sdist"
    else:
        raise ValueError(f"Unsupported distribution artifact: {path}")
    name, version = parse_distribution_metadata(text, path)
    return kind, name, version


def validate_distributions(
    dist_root: Path,
    expected_name: str,
    expected_version: str,
) -> list[dict[str, str]]:
    if not dist_root.is_dir():
        raise FileNotFoundError(f"Required distribution directory not found: {dist_root}")
    files = sorted(path for path in dist_root.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"Distribution directory contains no artifacts: {dist_root}")

    artifacts: list[dict[str, str]] = []
    kinds: set[str] = set()
    for path in files:
        if path.stat().st_size == 0:
            raise ValueError(f"Distribution artifact is empty: {path}")
        kind, name, version = inspect_distribution(path)
        if normalize_project_name(name) != normalize_project_name(expected_name):
            raise ValueError(f"Distribution name mismatch in {path}: {name!r}")
        if version != expected_version:
            raise ValueError(
                f"Distribution version mismatch in {path}: {version!r} != {expected_version!r}"
            )
        kinds.add(kind)
        artifacts.append(
            {
                "path": f"dist/{path.relative_to(dist_root).as_posix()}",
                "kind": kind,
                "name": name,
                "version": version,
                "sha256": sha256(path),
            }
        )
    missing_kinds = sorted({"wheel", "sdist"} - kinds)
    if missing_kinds:
        raise ValueError(f"Distribution evidence is missing: {', '.join(missing_kinds)}")
    return artifacts


def validate_hash_manifest(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Required {label} not found: {path}")
    entries: set[str] = set()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        raise ValueError(f"{label} contains no hashes")
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise ValueError(f"Malformed line in {label}: {line!r}")
        evidence_path = match.group(2)
        if evidence_path in entries:
            raise ValueError(f"Duplicate path in {label}: {evidence_path}")
        entries.add(evidence_path)


def resolve_release_identity(
    repo_root: Path,
    environment_path: Path,
    release_version: str,
    repository: str,
    asserted_commit: str | None,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    if release_version != EXPECTED_RELEASE_VERSION:
        raise ValueError(
            f"This packet builder is release-locked to {EXPECTED_RELEASE_VERSION}, got {release_version}"
        )
    package_version = release_version.removeprefix("v")
    head = git_output(repo_root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError(f"Repository HEAD is not a full Git commit: {head!r}")
    if git_output(repo_root, "status", "--porcelain"):
        raise ValueError("Release repository has uncommitted or untracked files")
    if asserted_commit is not None and asserted_commit != head:
        raise ValueError(f"--commit does not match repository HEAD: {asserted_commit} != {head}")

    environment = parse_environment_identity(environment_path)
    if environment["release_version"] != release_version:
        raise ValueError(
            "environment.txt release_version does not match requested release: "
            f"{environment['release_version']} != {release_version}"
        )
    if environment["git_commit"] != head:
        raise ValueError(
            "environment.txt git_commit does not match repository HEAD: "
            f"{environment['git_commit']} != {head}"
        )
    if environment["repository"] != repository:
        raise ValueError(
            "environment.txt repository does not match packet repository: "
            f"{environment['repository']} != {repository}"
        )

    package_name, versions, metadata_hashes = read_release_metadata(repo_root)
    if normalize_project_name(package_name) != normalize_project_name(EXPECTED_PACKAGE_NAME):
        raise ValueError(f"Unexpected project name in pyproject.toml: {package_name!r}")
    mismatches = [
        f"{label}={version}"
        for label, version in versions.items()
        if version != package_version
    ]
    if mismatches:
        raise ValueError(
            f"Release metadata mismatch for {release_version}: {', '.join(mismatches)}; "
            f"update pyproject.toml, mito_overview/__init__.py, and CITATION.cff to {package_version}"
        )

    return {
        "schema_version": "1.0",
        "release_version": release_version,
        "package_name": package_name,
        "package_version": package_version,
        "repository": repository,
        "git_commit": head,
        "environment_release_version": environment["release_version"],
        "environment_git_commit": environment["git_commit"],
        "metadata_versions": versions,
        "metadata_sha256": metadata_hashes,
        "source_worktree_clean": True,
    }


def write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def validate_cases(path: Path) -> tuple[int, dict[str, int]]:
    allowed = {"PASS", "FAIL", "XFAIL", "SKIP", "BLOCKED"}
    counts = {value: 0 for value in allowed}
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise ValueError("cases.tsv contains no validation cases")
    case_ids: set[str] = set()
    for row in rows:
        case_id = row.get("case_id", "")
        if not case_id:
            raise ValueError("Validation case is missing case_id")
        if case_id in case_ids:
            raise ValueError(f"Duplicate validation case_id: {case_id}")
        case_ids.add(case_id)
        verdict = row.get("verdict", "")
        if verdict not in allowed:
            raise ValueError(f"Unsupported case verdict: {verdict}")
        if verdict == "PASS" and (
            row.get("input_available") != "1" or row.get("expected_available") != "1"
        ):
            raise ValueError(f"PASS case lacks input or expected evidence: {row.get('case_id')}")
        counts[verdict] += 1
    missing_required = sorted(REQUIRED_PASS_CASES - case_ids)
    if missing_required:
        raise ValueError(f"Required release cases are missing: {', '.join(missing_required)}")
    nonpassing_required = sorted(
        row["case_id"] for row in rows if row["case_id"] in REQUIRED_PASS_CASES and row["verdict"] != "PASS"
    )
    if nonpassing_required:
        raise ValueError(f"Required release cases did not pass: {', '.join(nonpassing_required)}")
    release_blockers = sorted(
        f"{row['case_id']}={row['verdict']}"
        for row in rows
        if row["verdict"] in {"FAIL", "BLOCKED"}
    )
    if release_blockers:
        raise ValueError(
            f"Validation cases contain release-blocking verdicts: {', '.join(release_blockers)}"
        )
    return len(rows), counts


def write_verifier(path: Path) -> None:
    script = r'''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 - "${ROOT}" <<'PY'
import csv
import hashlib
import json
import re
import sys
import tarfile
import zipfile
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1])
required_top_level = {
    "run.json", "release_identity.json", "cases.tsv", "claim_evidence_matrix.tsv",
    "public_data_sources.tsv", "environment.txt", "commands", "logs", "dist",
    "expected", "observed_normalized", "filter_profile_results.tsv", "inputs.sha256",
    "artifacts.sha256", "verify_bundle.sh",
}
missing = sorted(name for name in required_top_level if not (root / name).exists())
if missing:
    raise SystemExit(f"missing required evidence: {missing}")

for relative in ("commands", "commands/public", "logs", "logs/public", "dist"):
    evidence_root = root / relative
    if not evidence_root.is_dir() or not any(path.is_file() for path in evidence_root.rglob("*")):
        raise SystemExit(f"required evidence directory is empty: {relative}")

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def parse_manifest(path, *, packet_paths):
    entries = {}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        raise SystemExit(f"empty hash manifest: {path.name}")
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise SystemExit(f"invalid hash manifest line in {path.name}: {line!r}")
        relative = match.group(2)
        if relative in entries:
            raise SystemExit(f"duplicate manifest path in {path.name}: {relative}")
        if packet_paths:
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise SystemExit(f"unsafe packet artifact path: {relative}")
        entries[relative] = match.group(1)
    return entries

artifact_hashes = parse_manifest(root / "artifacts.sha256", packet_paths=True)
actual_artifacts = {
    path.relative_to(root).as_posix()
    for path in root.rglob("*")
    if path.is_file() and path.name != "artifacts.sha256"
}
if set(artifact_hashes) != actual_artifacts:
    missing_hashes = sorted(actual_artifacts - set(artifact_hashes))
    stale_hashes = sorted(set(artifact_hashes) - actual_artifacts)
    raise SystemExit(
        f"artifact manifest inventory mismatch; missing={missing_hashes}, stale={stale_hashes}"
    )
for relative, expected in artifact_hashes.items():
    observed = digest(root / relative)
    if observed != expected:
        raise SystemExit(f"artifact hash mismatch: {relative}")

parse_manifest(root / "inputs.sha256", packet_paths=False)

def parse_environment(path):
    wanted = {"release_version", "git_commit", "repository"}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in wanted:
            if key in values:
                raise SystemExit(f"duplicate environment identity key: {key}")
            values[key] = value.strip()
    missing_keys = sorted(wanted - values.keys())
    if missing_keys:
        raise SystemExit(f"environment identity keys missing: {missing_keys}")
    return values

run = json.loads((root / "run.json").read_text(encoding="utf-8"))
identity = json.loads((root / "release_identity.json").read_text(encoding="utf-8"))
environment = parse_environment(root / "environment.txt")
if run.get("release_version") != "v0.3.0" or identity.get("release_version") != "v0.3.0":
    raise SystemExit("release identity mismatch")
if identity.get("package_version") != "0.3.0":
    raise SystemExit("package version mismatch")
if identity.get("package_name") != "mito-overview":
    raise SystemExit("package name mismatch")
if not re.fullmatch(r"[0-9a-f]{40}", str(identity.get("git_commit", ""))):
    raise SystemExit("invalid release commit")
if len({run.get("git_commit"), identity.get("git_commit"), environment.get("git_commit"), identity.get("environment_git_commit")}) != 1:
    raise SystemExit("release commit is inconsistent across packet evidence")
if len({run.get("repository"), identity.get("repository"), environment.get("repository")}) != 1:
    raise SystemExit("repository identity is inconsistent across packet evidence")
if identity.get("environment_release_version") != "v0.3.0" or environment.get("release_version") != "v0.3.0":
    raise SystemExit("environment release version mismatch")
if identity.get("source_worktree_clean") is not True:
    raise SystemExit("release identity was not built from a clean worktree")
metadata_versions = identity.get("metadata_versions", {})
required_metadata = {"pyproject.toml", "mito_overview/__init__.py", "CITATION.cff"}
if set(metadata_versions) != required_metadata or set(metadata_versions.values()) != {"0.3.0"}:
    raise SystemExit("release metadata versions are incomplete or inconsistent")
metadata_hashes = identity.get("metadata_sha256", {})
if set(metadata_hashes) != required_metadata or any(
    not re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in metadata_hashes.values()
):
    raise SystemExit("release metadata hashes are incomplete or malformed")
if run.get("diagnostic_validation_claimed") is not False:
    raise SystemExit("packet exceeds its bounded non-diagnostic claim scope")

verdicts = {"PASS", "FAIL", "XFAIL", "SKIP", "BLOCKED"}
required_pass = {
    "unit_known_answer", "cli_step_listing", "strict_generic_dry_run",
    "synthetic_longread_smoke", "synthetic_shortread_smoke",
    "synthetic_longread_nomethyl_smoke", "standalone_minimal_smoke", "package_build",
    "public_validation_matrix", "gm11906_default_run1", "gm11906_default_run2",
    "gm11906_lenient", "gm11906_strict", "gm12878_default_run1",
    "gm12878_default_run2", "gm12878_lenient", "gm12878_strict",
    "gm11906_repeatability", "gm12878_repeatability",
    "gm11906_visual_integrity", "gm12878_visual_integrity", "filter_profiles",
}
with (root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
    cases = list(csv.DictReader(handle, delimiter="\t"))
if not cases:
    raise SystemExit("no validation cases")
case_ids = set()
for case in cases:
    case_id = case.get("case_id", "")
    if not case_id or case_id in case_ids:
        raise SystemExit(f"missing or duplicate case_id: {case_id!r}")
    case_ids.add(case_id)
    if case.get("verdict") not in verdicts:
        raise SystemExit(f"invalid verdict: {case}")
    if case.get("verdict") == "PASS" and (
        case.get("input_available") != "1" or case.get("expected_available") != "1"
    ):
        raise SystemExit(f"unsupported PASS verdict: {case.get('case_id')}")
blockers = sorted(
    f"{case['case_id']}={case['verdict']}"
    for case in cases
    if case["verdict"] in {"FAIL", "BLOCKED"}
)
if blockers:
    raise SystemExit(f"release-blocking validation verdicts: {blockers}")
missing_required = sorted(required_pass - case_ids)
if missing_required:
    raise SystemExit(f"missing required release cases: {missing_required}")
nonpassing = sorted(
    case["case_id"] for case in cases
    if case["case_id"] in required_pass and case["verdict"] != "PASS"
)
if nonpassing:
    raise SystemExit(f"required release cases did not pass: {nonpassing}")
observed_counts = Counter(case["verdict"] for case in cases)
expected_counts = {verdict: observed_counts.get(verdict, 0) for verdict in verdicts}
if run.get("case_count") != len(cases) or run.get("verdict_counts") != expected_counts:
    raise SystemExit("run.json case counts do not match cases.tsv")

def normalize_name(value):
    return re.sub(r"[-_.]+", "-", value).lower()

def metadata_fields(text, source):
    fields = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"Name", "Version"} and key not in fields:
            fields[key] = value.strip()
    if not fields.get("Name") or not fields.get("Version"):
        raise SystemExit(f"distribution metadata is incomplete: {source}")
    return fields["Name"], fields["Version"]

def inspect_dist(path):
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            members = sorted(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
            if len(members) != 1:
                raise SystemExit(f"invalid wheel metadata inventory: {path.name}")
            text = archive.read(members[0]).decode("utf-8")
        kind = "wheel"
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = sorted(
                (member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")),
                key=lambda member: member.name,
            )
            if len(members) != 1:
                raise SystemExit(f"invalid sdist metadata inventory: {path.name}")
            handle = archive.extractfile(members[0])
            if handle is None:
                raise SystemExit(f"unreadable sdist metadata: {path.name}")
            text = handle.read().decode("utf-8")
        kind = "sdist"
    else:
        raise SystemExit(f"unsupported distribution artifact: {path.name}")
    name, version = metadata_fields(text, path)
    return kind, name, version

dist_files = sorted(path for path in (root / "dist").rglob("*") if path.is_file())
declared_dist = identity.get("dist_artifacts", [])
declared_paths = {entry.get("path") for entry in declared_dist}
actual_dist_paths = {path.relative_to(root).as_posix() for path in dist_files}
if declared_paths != actual_dist_paths or len(declared_paths) != len(declared_dist):
    raise SystemExit("distribution inventory does not match release identity")
dist_kinds = set()
for entry in declared_dist:
    dist_path = root / entry["path"]
    kind, name, version = inspect_dist(dist_path)
    if (
        entry.get("kind") != kind
        or normalize_name(name) != "mito-overview"
        or entry.get("name") != name
        or version != "0.3.0"
        or entry.get("version") != version
        or entry.get("sha256") != digest(dist_path)
    ):
        raise SystemExit(f"distribution identity mismatch: {entry.get('path')}")
    dist_kinds.add(kind)
if dist_kinds != {"wheel", "sdist"}:
    raise SystemExit("release packet requires both wheel and sdist evidence")

states = {"ok", "not_configured", "not_applicable", "not_evaluable", "unavailable", "failed"}
for path in (root / "observed_normalized").rglob("*.tsv"):
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    if not rows or rows[0][:2] != ["metric", "value"]:
        continue
    for row in rows[1:]:
        if len(row) >= 2 and row[0] == "status" and row[1] not in states:
            raise SystemExit(f"invalid module status {row[1]!r} in {path}")
print(f"verified mito-overview {run['release_version']} packet at commit {run['git_commit']}")
PY
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_packet(args: argparse.Namespace) -> Path:
    if not args.validation_root.is_dir():
        raise SystemExit(f"Validation root not found: {args.validation_root}")
    if args.packet_root.exists() and any(args.packet_root.iterdir()):
        raise SystemExit(f"Packet root must be absent or empty: {args.packet_root}")

    public_root = args.validation_root / "public"
    case_count, verdict_counts = validate_cases(args.validation_root / "cases.tsv")
    validate_hash_manifest(public_root / "inputs.sha256", "public/inputs.sha256")
    release_identity = resolve_release_identity(
        args.repo_root,
        args.validation_root / "environment.txt",
        args.version,
        args.repository,
        args.commit,
    )
    dist_artifacts = validate_distributions(
        args.validation_root / "dist",
        str(release_identity["package_name"]),
        str(release_identity["package_version"]),
    )
    for source in (
        args.validation_root / "commands",
        public_root / "commands",
        args.validation_root / "logs",
        public_root / "logs",
        args.validation_root / "expected",
        public_root / "observed_normalized",
    ):
        if not source.is_dir() or not any(path.is_file() for path in source.rglob("*")):
            raise ValueError(f"Required evidence directory is missing or empty: {source}")

    args.packet_root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(args.validation_root / "cases.tsv", args.packet_root / "cases.tsv")
    shutil.copy2(args.validation_root / "environment.txt", args.packet_root / "environment.txt")
    copy_tree(args.validation_root / "commands", args.packet_root / "commands")
    copy_tree(public_root / "commands", args.packet_root / "commands" / "public")
    copy_tree(args.validation_root / "logs", args.packet_root / "logs")
    copy_tree(public_root / "logs", args.packet_root / "logs" / "public")
    copy_tree(args.validation_root / "dist", args.packet_root / "dist")
    copy_tree(args.validation_root / "expected", args.packet_root / "expected")
    copy_tree(
        public_root / "observed_normalized",
        args.packet_root / "observed_normalized",
    )
    shutil.copy2(
        public_root / "filter_profile_results.tsv",
        args.packet_root / "filter_profile_results.tsv",
    )
    shutil.copy2(public_root / "inputs.sha256", args.packet_root / "inputs.sha256")

    release_identity["dist_artifacts"] = dist_artifacts
    (args.packet_root / "release_identity.json").write_text(
        json.dumps(release_identity, indent=2) + "\n",
        encoding="utf-8",
    )
    run = {
        "schema_version": "1.1",
        "release_version": release_identity["release_version"],
        "git_commit": release_identity["git_commit"],
        "repository": release_identity["repository"],
        "archive_doi": args.doi,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": case_count,
        "verdict_counts": verdict_counts,
        "claim_scope": "reproducible mode-gated mtDNA reporting workflow/resource",
        "diagnostic_validation_claimed": False,
    }
    (args.packet_root / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

    write_tsv(
        args.packet_root / "claim_evidence_matrix.tsv",
        ["claim_id", "bounded_claim", "evidence", "limitation"],
        [
            [
                "C1",
                "Shared filtered allele counting is deterministic on known-answer fixtures",
                "unit_known_answer; synthetic_longread_smoke; expected/TOY-SR-001.expected_alleles.tsv",
                "Reporting thresholds are not clinically calibrated",
            ],
            [
                "C2",
                "mvTool is offline by default with deterministic fixture coverage",
                "unit_known_answer; synthetic_longread_smoke",
                "No claim of live service availability",
            ],
            [
                "C3",
                "Minimal standalone BAM and CRAM contracts are preflighted",
                "unit_known_answer; strict_generic_dry_run; standalone_minimal_smoke",
                "Optional sidecars remain user supplied",
            ],
            [
                "C4",
                "The WGS fixture reports a 100/10 mt:nuclear depth ratio of 10.0",
                "unit_known_answer; expected/TOY-WGS-001.expected_copy_proxy.tsv",
                "Experimental depth proxy, not absolute copies per diploid cell",
            ],
            [
                "C5",
                "mt-only references suppress categorical NUMT interpretation",
                "unit_known_answer; gm12878_default_run1; gm12878_repeatability",
                "Alignment-ambiguity QC is not a formal NUMT classifier",
            ],
            [
                "C6",
                "Public proof-of-principle workflows reproduce normalized TSVs",
                "gm11906_repeatability; gm12878_repeatability; filter_profile_results.tsv",
                "Not a sensitivity, specificity, deletion-truth, or diagnostic benchmark",
            ],
        ],
    )
    write_tsv(
        args.packet_root / "public_data_sources.tsv",
        [
            "dataset",
            "run_accession",
            "study_accession",
            "sample_accession",
            "cell_line",
            "platform",
            "instrument_model",
            "library_strategy",
            "fastq_url",
            "fastq_md5",
            "fastq_bytes",
            "metadata_checked_utc",
            "role",
            "redistribution",
        ],
        [
            [
                "GM11906 reduced short-read proof-of-principle",
                "SRR10804585",
                "PRJNA598179",
                "SAMN13699362",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_2.fastq.gz",
                "3f5ea26a5791894071462d4970bc9e5a;c5b408425612f63b33cefd2d49c157d1",
                "8795676;8817420",
                "2026-07-20",
                "default repeatability, m.8344A>G release gate, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
            [
                "GM11906 reduced short-read proof-of-principle",
                "SRR10804590",
                "PRJNA598179",
                "SAMN13699398",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_2.fastq.gz",
                "e8b5132a8be8c179bfc6dbc0f3e1bee9;4d6977526136739de2d90baa8d45b484",
                "1006749;795885",
                "2026-07-20",
                "default repeatability, m.8344A>G release gate, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
            [
                "GM11906 reduced short-read proof-of-principle",
                "SRR10804657",
                "PRJNA598179",
                "SAMN13699338",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_2.fastq.gz",
                "8f082f73cb64bf56ea8a053fe80eeb06;62b7d1b2294a580c021f5fa1f52609be",
                "21510555;21573731",
                "2026-07-20",
                "default repeatability, m.8344A>G release gate, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
            [
                "GM12878 ONT targeted-mt proof-of-principle",
                "SRR18110025",
                "PRJNA809571",
                "SAMN26195906",
                "GM12878",
                "OXFORD_NANOPORE",
                "GridION",
                "OTHER",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR181/025/SRR18110025/SRR18110025_1.fastq.gz",
                "d5bfb9aeba04cae5f3dd79462a42e5b0",
                "2033558460",
                "2026-07-20",
                "long-read repeatability, mt-only scope gating, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
        ],
    )

    write_verifier(args.packet_root / "verify_bundle.sh")
    artifact_rows: list[str] = []
    for path in sorted(args.packet_root.rglob("*")):
        if not path.is_file() or path.name == "artifacts.sha256":
            continue
        artifact_rows.append(f"{sha256(path)}  {path.relative_to(args.packet_root).as_posix()}")
    (args.packet_root / "artifacts.sha256").write_text(
        "\n".join(artifact_rows) + "\n", encoding="utf-8"
    )

    missing = [name for name in REQUIRED_TOP_LEVEL if not (args.packet_root / name).exists()]
    if missing:
        raise SystemExit(f"Packet is missing required entries: {missing}")

    args.zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(args.packet_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(args.packet_root).as_posix())
    print(args.zip_path)
    return args.zip_path


def main() -> None:
    build_packet(parse_args())


if __name__ == "__main__":
    main()
