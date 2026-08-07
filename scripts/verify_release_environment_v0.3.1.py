#!/usr/bin/env python3
"""Verify the active release environment against a platform artifact lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


SHA256_RE = re.compile(r"[0-9a-f]{64}")
PLATFORM_MAP = {
    ("Linux", "x86_64"): "linux-64",
    ("Darwin", "x86_64"): "osx-64",
    ("Darwin", "arm64"): "osx-arm64",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def platform_id() -> str:
    identity = (platform.system(), platform.machine())
    try:
        return PLATFORM_MAP[identity]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported release platform: system={identity[0]!r}, "
            f"machine={identity[1]!r}"
        ) from exc


def artifact_urls(text: str, *, label: str, expected_platform: str) -> set[str]:
    lines = text.splitlines()
    if lines.count("@EXPLICIT") != 1:
        raise ValueError(f"{label} must contain exactly one @EXPLICIT marker")
    platform_markers = {
        line.removeprefix("# platform: ").strip()
        for line in lines
        if line.startswith("# platform: ")
    }
    if platform_markers and platform_markers != {expected_platform}:
        raise ValueError(
            f"{label} platform marker does not match {expected_platform}: "
            f"{sorted(platform_markers)}"
        )
    records = [
        line.strip()
        for line in lines
        if line.strip()
        and not line.startswith("#")
        and line.strip() != "@EXPLICIT"
    ]
    if not records:
        raise ValueError(f"{label} contains no Conda artifact URLs")
    if len(records) != len(set(records)):
        raise ValueError(f"{label} contains duplicate Conda artifact URLs")
    for url in records:
        parsed = urlsplit(url)
        path_parts = parsed.path.split("/")
        if (
            parsed.scheme != "https"
            or parsed.hostname != "conda.anaconda.org"
            or parsed.netloc != "conda.anaconda.org"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or not SHA256_RE.fullmatch(parsed.fragment)
            or len(path_parts) != 4
            or path_parts[0] != ""
            or path_parts[1] not in {"conda-forge", "bioconda"}
            or path_parts[2] not in {expected_platform, "noarch"}
            or not re.fullmatch(
                r"[A-Za-z0-9_.+-]+\.(?:conda|tar\.bz2)", path_parts[3]
            )
        ):
            raise ValueError(
                f"{label} contains an unapproved or unhashed Conda artifact URL"
            )
    return set(records)


def conda_metadata_artifact_urls(
    prefix: Path, *, expected_platform: str
) -> set[str]:
    """Read the active prefix's package records without invoking child Python."""

    metadata_root = prefix / "conda-meta"
    if not metadata_root.is_dir() or metadata_root.is_symlink():
        raise ValueError(f"Conda package metadata directory is invalid: {metadata_root}")
    records: list[str] = []
    metadata_paths = sorted(metadata_root.glob("*.json"))
    if not metadata_paths:
        raise ValueError("Active Conda prefix has no package metadata records")
    for path in metadata_paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Conda package metadata record is not regular: {path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Conda package metadata record is unreadable: {path.name}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Conda package metadata record is malformed: {path.name}")
        url = payload.get("url")
        digest = payload.get("sha256")
        filename = payload.get("fn")
        if (
            not isinstance(url, str)
            or not isinstance(digest, str)
            or SHA256_RE.fullmatch(digest) is None
            or not isinstance(filename, str)
            or Path(urlsplit(url).path).name != filename
        ):
            raise ValueError(
                f"Conda package metadata lacks exact URL/hash identity: {path.name}"
            )
        records.append(f"{url}#{digest}")
    return artifact_urls(
        "@EXPLICIT\n" + "\n".join(records) + "\n",
        label=f"Active-prefix {expected_platform} package metadata",
        expected_platform=expected_platform,
    )


def verify(
    repo_root: Path, python_executable: Path, expected_commit: str
) -> dict[str, object]:
    repo_root = repo_root.resolve(strict=True)
    python_executable = Path(os.path.abspath(python_executable))
    observed_executable = Path(os.path.abspath(sys.executable))
    if (
        not python_executable.exists()
        or not python_executable.is_file()
        or python_executable != observed_executable
    ):
        raise ValueError(
            "The verifier must run with the exact Python path supplied to it"
        )
    observed_platform = platform_id()
    lock_path = repo_root / "locks" / f"environment-{observed_platform}.explicit.txt"
    if not lock_path.is_file() or lock_path.is_symlink():
        raise ValueError(f"Missing regular platform artifact lock: {lock_path}")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("Expected release commit must be 40 lowercase hexadecimal characters")
    observed_commit = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    observed_tree = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD^{tree}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    worktree_status = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if observed_commit != expected_commit:
        raise ValueError(
            f"Release repository commit mismatch: {observed_commit} != {expected_commit}"
        )
    if worktree_status:
        raise ValueError("Release repository worktree is not clean")

    if python_executable.parent.name != "bin":
        raise ValueError(
            f"Release Python must be located under an environment bin directory: "
            f"{python_executable}"
        )
    lexical_prefix = python_executable.parent.parent
    prefix = lexical_prefix.resolve(strict=True)
    resolved_executable = python_executable.resolve(strict=True)
    if not resolved_executable.is_relative_to(prefix):
        raise ValueError(
            "Release Python resolves outside its declared environment prefix: "
            f"{python_executable} -> {resolved_executable}"
        )
    if not (prefix / "conda-meta").is_dir():
        raise ValueError(
            f"Release Python is not inside a Conda prefix: {python_executable}"
        )

    expected_text = lock_path.read_text(encoding="utf-8")
    expected_urls = artifact_urls(
        expected_text,
        label=f"Tracked {observed_platform} artifact lock",
        expected_platform=observed_platform,
    )
    observed_urls = conda_metadata_artifact_urls(
        prefix,
        expected_platform=observed_platform,
    )
    if observed_urls != expected_urls:
        missing = sorted(expected_urls - observed_urls)
        unexpected = sorted(observed_urls - expected_urls)
        raise ValueError(
            "Runtime Conda artifacts do not match the tracked release lock: "
            f"missing={missing!r}; unexpected={unexpected!r}"
        )

    if tuple(sys.version_info[:3]) != (3, 12, 13):
        raise ValueError(
            f"Release Python must be 3.12.13, observed {platform.python_version()}"
        )

    return {
        "schema_version": "1.0",
        "platform_id": observed_platform,
        "python": platform.python_version(),
        "artifact_count": len(expected_urls),
        "tracked_artifact_lock": lock_path.name,
        "tracked_artifact_lock_sha256": sha256(lock_path),
        "runtime_artifact_set_sha256": hashlib.sha256(
            ("\n".join(sorted(observed_urls)) + "\n").encode("utf-8")
        ).hexdigest(),
        "repository_commit": observed_commit,
        "repository_tree": observed_tree,
        "repository_clean": True,
        "verified": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        record = verify(
            args.repo_root, Path(sys.executable), args.expected_commit
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(f"Release environment verification failed: {exc}") from exc
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
