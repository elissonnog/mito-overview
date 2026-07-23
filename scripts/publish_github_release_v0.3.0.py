#!/usr/bin/env python3
"""Publish the tag-bound MitoOverview v0.3.0 GitHub release safely."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence


EXPECTED_TAG = "v0.3.0"
PUBLICATION_SCHEMA_VERSION = "1.0"
TAG_VALIDATION_SCHEMA_VERSION = "2.0"
TAG_VALIDATION_PROFILE = "fresh_public_tag_validation_v2"
TRUSTED_ASSET_MANIFEST_SCHEMA_VERSION = "1.0"
TRUSTED_ASSET_MANIFEST_NAME = "trusted_release_assets.json"
API_VERSION = "2026-03-10"
ACCEPT_HEADER = "application/vnd.github+json"
PHASES = ("verify-prepublication", "create-draft", "upload-verify", "publish")
REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9])?/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9])?$"
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ASSET_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,254}$")
CHECKSUM_LINE_PATTERN = re.compile(
    r"^(?P<digest>[0-9a-f]{64})  (?P<name>[A-Za-z0-9][A-Za-z0-9._+-]{0,254})$"
)
EVIDENCE_CHECKSUM_LINE_PATTERN = re.compile(
    r"^(?P<digest>[0-9a-f]{64})  (?P<path>[A-Za-z0-9][A-Za-z0-9._+/-]{0,1023})$"
)
REQUIRED_TAG_VALIDATION_CASES = frozenset(
    {
        "public_https_tag_clone",
        "annotated_tag_identity",
        "clean_tag_checkout",
        "locked_environment",
        "wheel_sdist_build",
        "installed_cli",
        "installed_sdist_cli",
        "unit_tests",
        "smoke_longread",
        "smoke_shortread",
        "smoke_longread_nomethyl",
        "smoke_standalone",
        "example_builders",
        "release_asset_semantic_identity",
        "trusted_release_assets",
    }
)
CANONICAL_ASSET_NAMES = frozenset(
    {
        "mito_overview-0.3.0-py3-none-any.whl",
        "mito_overview-0.3.0.tar.gz",
        "mito-overview-v0.3.0-validation.zip",
        "MitoOverview_v0.3.0_release_validation_report.md",
        "MitoOverview_v0.3.0_release_validation_report.docx",
        "MitoOverview_v0.3.0_release_validation_report.pdf",
        "MitoOverview_v0.3.0_release_validation_report_assets.tar.gz",
        "mito-overview-v0.3.0-verification.json",
        "RELEASE_NOTES_v0.3.0.md",
        "mito-overview-v0.3.0-environment.txt",
        "mito-overview-v0.3.0-environment-locks.tar.gz",
        "SHA256SUMS",
    }
)


class PublicationError(RuntimeError):
    """Raised when a publication safety or verification gate fails."""


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def run(self, args: Sequence[str], *, check: bool = True) -> CommandResult:
        """Run one command without a shell."""


class SubprocessRunner:
    def run(self, args: Sequence[str], *, check: bool = True) -> CommandResult:
        command = tuple(str(value) for value in args)
        if not command or any("\x00" in value for value in command):
            raise PublicationError("Refusing an empty command or an argument containing NUL")
        completed = subprocess.run(
            command,
            check=False,
            shell=False,
            text=True,
            capture_output=True,
        )
        result = CommandResult(
            command,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no command output"
            raise PublicationError(
                f"Command failed ({result.returncode}): {command!r}: {detail}"
            )
        return result


@dataclass(frozen=True)
class Asset:
    name: str
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "size": self.size, "sha256": self.sha256}


@dataclass(frozen=True)
class AssetInventory:
    root: Path
    assets: tuple[Asset, ...]
    sha256sums_sha256: str
    sha256sums_bytes: bytes

    @property
    def by_name(self) -> dict[str, Asset]:
        return {asset.name: asset for asset in self.assets}

    def as_list(self) -> list[dict[str, Any]]:
        return [asset.as_dict() for asset in self.assets]


@dataclass(frozen=True)
class PublicationConfig:
    repository: str
    final_sha: str
    tag: str
    output_directory: Path
    phase: str
    github_actions_run_id: int
    tag_validation_receipt: Path | None = None
    asset_directory: Path | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repository_url(config: PublicationConfig) -> str:
    return f"https://github.com/{config.repository}"


def _release_url(config: PublicationConfig) -> str:
    return f"{_repository_url(config)}/releases/tag/{config.tag}"


def _validate_config(config: PublicationConfig) -> PublicationConfig:
    if not REPOSITORY_PATTERN.fullmatch(config.repository):
        raise PublicationError("Repository must be a safe owner/name GitHub slug")
    if not SHA_PATTERN.fullmatch(config.final_sha):
        raise PublicationError("FINAL_SHA must be exactly 40 lowercase hexadecimal characters")
    if config.tag != EXPECTED_TAG:
        raise PublicationError(f"This utility publishes only tag {EXPECTED_TAG}")
    if config.phase not in PHASES:
        raise PublicationError(f"Publication phase must be one of {PHASES!r}")
    if (
        isinstance(config.github_actions_run_id, bool)
        or not isinstance(config.github_actions_run_id, int)
        or config.github_actions_run_id <= 0
    ):
        raise PublicationError("GitHub Actions run ID must be a positive integer")
    prepublication = config.phase == "verify-prepublication"
    tag_validation_receipt: Path | None = None
    asset_directory: Path | None = None
    if prepublication:
        if config.tag_validation_receipt is not None or config.asset_directory is not None:
            raise PublicationError(
                "--verify-prepublication does not accept tag-validation or asset inputs"
            )
    else:
        if config.tag_validation_receipt is None:
            raise PublicationError("Fresh public-tag validation receipt is required")
        receipt_candidate = config.tag_validation_receipt.expanduser()
        if receipt_candidate.is_symlink() or not receipt_candidate.is_file():
            raise PublicationError("Fresh public-tag validation receipt is required")
        tag_validation_receipt = receipt_candidate.resolve(strict=True)

        if config.asset_directory is None:
            raise PublicationError("Release mutation phases require --asset-directory")
        candidate = config.asset_directory.expanduser()
        if candidate.is_symlink() or not candidate.is_dir():
            raise PublicationError("Asset directory must be an existing non-symlink directory")
        asset_directory = candidate.resolve(strict=True)

    output_directory = config.output_directory.expanduser()
    if output_directory.exists() and output_directory.is_symlink():
        raise PublicationError("Output directory cannot be a symlink")
    output_directory.mkdir(parents=True, exist_ok=True)
    output_directory = output_directory.resolve(strict=True)
    if asset_directory is not None:
        if output_directory == asset_directory:
            raise PublicationError("Asset and output directories must be different")
        if output_directory.is_relative_to(asset_directory):
            raise PublicationError("Output directory cannot be inside the asset directory")
        if asset_directory.is_relative_to(output_directory):
            raise PublicationError("Asset directory cannot be inside the output directory")

    return PublicationConfig(
        repository=config.repository,
        final_sha=config.final_sha,
        tag=config.tag,
        output_directory=output_directory,
        phase=config.phase,
        github_actions_run_id=config.github_actions_run_id,
        tag_validation_receipt=tag_validation_receipt,
        asset_directory=asset_directory,
    )


def inspect_asset_inventory(directory: Path) -> AssetInventory:
    """Validate the exact flat v0.3.0 release inventory and its checksums."""

    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    paths: dict[str, Path] = {}
    for path in entries:
        if path.is_symlink():
            raise PublicationError(f"Asset inventory contains a symlink: {path.name}")
        if not path.is_file():
            raise PublicationError(
                f"Asset inventory must contain regular files only: {path.name}"
            )
        if not ASSET_NAME_PATTERN.fullmatch(path.name):
            raise PublicationError(f"Unsafe asset filename: {path.name!r}")
        paths[path.name] = path

    observed_names = set(paths)
    if observed_names != CANONICAL_ASSET_NAMES:
        raise PublicationError(
            "Canonical v0.3.0 asset inventory mismatch; "
            f"missing={sorted(CANONICAL_ASSET_NAMES - observed_names)!r}; "
            f"unexpected={sorted(observed_names - CANONICAL_ASSET_NAMES)!r}"
        )

    manifest_bytes = paths["SHA256SUMS"].read_bytes()
    try:
        manifest_text = manifest_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise PublicationError("SHA256SUMS must be ASCII") from exc
    if not manifest_text.endswith("\n"):
        raise PublicationError("SHA256SUMS must end with a newline")

    expected: dict[str, str] = {}
    for line_number, line in enumerate(manifest_text.splitlines(), start=1):
        match = CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise PublicationError(
                f"Malformed SHA256SUMS line {line_number}; expected '<sha256>  <filename>'"
            )
        name = match.group("name")
        if name == "SHA256SUMS":
            raise PublicationError("SHA256SUMS must not list itself")
        if name in expected:
            raise PublicationError(f"Duplicate SHA256SUMS entry: {name}")
        expected[name] = match.group("digest")

    expected_names = CANONICAL_ASSET_NAMES - {"SHA256SUMS"}
    if set(expected) != expected_names:
        raise PublicationError(
            "SHA256SUMS inventory mismatch; "
            f"missing={sorted(expected_names - set(expected))!r}; "
            f"unexpected={sorted(set(expected) - expected_names)!r}"
        )

    assets: list[Asset] = []
    for name in sorted(paths):
        path = paths[name]
        observed = _sha256_file(path)
        if name != "SHA256SUMS" and observed != expected[name]:
            raise PublicationError(
                f"SHA256 mismatch for {name}: expected {expected[name]}, observed {observed}"
            )
        assets.append(Asset(name, path.stat().st_size, observed))
    return AssetInventory(
        root=directory,
        assets=tuple(assets),
        sha256sums_sha256=_sha256_bytes(manifest_bytes),
        sha256sums_bytes=manifest_bytes,
    )


def _inventory_signature(inventory: AssetInventory) -> tuple[tuple[str, int, str], ...]:
    return tuple((asset.name, asset.size, asset.sha256) for asset in inventory.assets)


def _assert_inventory_unchanged(expected: AssetInventory) -> None:
    observed = inspect_asset_inventory(expected.root)
    if _inventory_signature(observed) != _inventory_signature(expected):
        raise PublicationError("Prepared asset inventory changed during publication")
    if observed.sha256sums_bytes != expected.sha256sums_bytes:
        raise PublicationError("SHA256SUMS changed during publication")


def _api_command(repository: str, endpoint: str, method: str) -> list[str]:
    return [
        "gh",
        "api",
        f"repos/{repository}/{endpoint}",
        "--method",
        method,
        "-H",
        f"Accept: {ACCEPT_HEADER}",
        "-H",
        f"X-GitHub-Api-Version: {API_VERSION}",
    ]


def _is_http_404(result: CommandResult) -> bool:
    message = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode != 0 and (
        re.search(r"\b404\b", message) is not None or "not found" in message
    )


def _api_json(
    runner: Runner,
    repository: str,
    endpoint: str,
    *,
    method: str = "GET",
    fields: Sequence[tuple[str, str, str]] = (),
    allow_not_found: bool = False,
) -> Any:
    command = _api_command(repository, endpoint, method)
    for flag, key, value in fields:
        if flag not in {"-f", "-F"}:
            raise PublicationError(f"Unsupported gh API field flag: {flag}")
        command.extend((flag, f"{key}={value}"))
    result = runner.run(command, check=False)
    if result.returncode != 0:
        if allow_not_found and _is_http_404(result):
            return None
        detail = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise PublicationError(
            f"GitHub API {method} {endpoint} failed ({result.returncode}): {detail}"
        )
    if not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PublicationError(
            f"GitHub API {method} {endpoint} returned malformed JSON"
        ) from exc


def _api_object(
    runner: Runner,
    repository: str,
    endpoint: str,
    *,
    method: str = "GET",
    fields: Sequence[tuple[str, str, str]] = (),
    allow_not_found: bool = False,
) -> dict[str, Any] | None:
    payload = _api_json(
        runner,
        repository,
        endpoint,
        method=method,
        fields=fields,
        allow_not_found=allow_not_found,
    )
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise PublicationError(f"GitHub API {method} {endpoint} did not return an object")
    return payload


def _require_remote_commit(runner: Runner, config: PublicationConfig) -> None:
    commit = _api_object(runner, config.repository, f"commits/{config.final_sha}")
    if commit is None or commit.get("sha") != config.final_sha:
        raise PublicationError(
            f"Remote commit drift: expected {config.final_sha}, observed {commit!r}"
        )
    main = _api_object(runner, config.repository, "commits/main")
    if main is None or main.get("sha") != config.final_sha:
        raise PublicationError(
            f"Remote main drift: expected {config.final_sha}, observed {main!r}"
        )


def _verify_tag(
    runner: Runner, config: PublicationConfig
) -> tuple[dict[str, Any], dict[str, Any]]:
    ref_payload = _api_object(
        runner,
        config.repository,
        f"git/ref/tags/{config.tag}",
        allow_not_found=True,
    )
    if ref_payload is None:
        raise PublicationError(
            f"Existing annotated tag {config.tag} is required before creating a release"
        )
    ref_object = ref_payload.get("object")
    if not isinstance(ref_object, dict):
        raise PublicationError("Remote tag reference has no object")
    if ref_payload.get("ref") != f"refs/tags/{config.tag}":
        raise PublicationError("Remote tag reference name drifted")
    object_sha = str(ref_object.get("sha", ""))
    if ref_object.get("type") != "tag" or not SHA_PATTERN.fullmatch(object_sha):
        raise PublicationError("Remote v0.3.0 tag must be an annotated tag object")
    tag_payload = _api_object(runner, config.repository, f"git/tags/{object_sha}")
    target = tag_payload.get("object") if tag_payload else None
    if not isinstance(target, dict):
        raise PublicationError("Annotated tag object has no target")
    if tag_payload.get("sha") not in (None, object_sha):
        raise PublicationError("Annotated tag object SHA drifted")
    if tag_payload.get("tag") != config.tag:
        raise PublicationError("Annotated tag name drifted")
    if target.get("type") != "commit" or target.get("sha") != config.final_sha:
        raise PublicationError(
            "Annotated tag peel drift: "
            f"expected commit {config.final_sha}, observed {target!r}"
        )
    return ref_payload, tag_payload


def _tag_record(
    ref_payload: dict[str, Any], tag_payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    ref_object = ref_payload["object"]
    target = tag_payload["object"]
    return (
        {
            "ref": ref_payload.get("ref"),
            "object_type": ref_object.get("type"),
            "object_sha": ref_object.get("sha"),
            "api_url": ref_payload.get("url"),
        },
        {
            "tag": tag_payload.get("tag"),
            "tag_object_sha": ref_object.get("sha"),
            "message": tag_payload.get("message"),
            "target_type": target.get("type"),
            "peeled_target_sha": target.get("sha"),
            "api_url": tag_payload.get("url"),
        },
    )


def _find_release(runner: Runner, config: PublicationConfig) -> dict[str, Any] | None:
    """Enumerate authenticated releases because tag lookup omits drafts."""

    matches: list[dict[str, Any]] = []
    page = 1
    while True:
        endpoint = f"releases?per_page=100&page={page}"
        payload = _api_json(runner, config.repository, endpoint)
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise PublicationError("GitHub release enumeration returned malformed JSON")
        matches.extend(item for item in payload if item.get("tag_name") == config.tag)
        if len(payload) < 100:
            break
        page += 1
        if page > 10000:
            raise PublicationError("GitHub release enumeration exceeded the safety limit")
    if len(matches) > 1:
        raise PublicationError(f"GitHub returned duplicate releases for tag {config.tag}")
    return matches[0] if matches else None


def _query_release_by_id(
    runner: Runner, config: PublicationConfig, release_id: int
) -> dict[str, Any]:
    release = _api_object(runner, config.repository, f"releases/{release_id}")
    if release is None:
        raise PublicationError(f"GitHub release ID {release_id} disappeared")
    return release


def _release_record(release: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": release.get("id"),
        "api_url": release.get("url"),
        "url": release.get("html_url"),
        "tag_name": release.get("tag_name"),
        "target_commitish": release.get("target_commitish"),
        "name": release.get("name"),
        "draft": release.get("draft"),
        "prerelease": release.get("prerelease"),
        "immutable": release.get("immutable"),
        "created_at": release.get("created_at"),
        "published_at": release.get("published_at"),
    }


def _require_release_identity(
    release: dict[str, Any],
    config: PublicationConfig,
    *,
    state: str,
    require_immutable: bool = True,
) -> None:
    if not isinstance(release.get("id"), int):
        raise PublicationError("GitHub release has no integer release ID")
    if release.get("prerelease") is not False:
        raise PublicationError("GitHub release must explicitly report prerelease=false")
    if release.get("tag_name") != config.tag:
        raise PublicationError("GitHub release tag drifted")
    if release.get("target_commitish") != config.final_sha:
        raise PublicationError(
            "GitHub release target drift: "
            f"expected {config.final_sha}, observed {release.get('target_commitish')!r}"
        )
    if state == "draft":
        if release.get("draft") is not True or release.get("published_at") is not None:
            raise PublicationError("Expected an unpublished draft release")
        if require_immutable and release.get("immutable") is not False:
            raise PublicationError("Draft release must explicitly report immutable=false")
    elif state == "published":
        if release.get("draft") is not False or not release.get("published_at"):
            raise PublicationError("Published release state was not confirmed")
        if require_immutable and release.get("immutable") is not True:
            raise PublicationError("Published release did not report immutable=true")
    elif state != "either":
        raise PublicationError(f"Internal error: unsupported release state {state!r}")
    else:
        expected_immutable = release.get("draft") is False
        if require_immutable and release.get("immutable") is not expected_immutable:
            raise PublicationError("Release immutable state is inconsistent with draft state")


def _create_draft_release(runner: Runner, config: PublicationConfig) -> dict[str, Any]:
    release = _api_object(
        runner,
        config.repository,
        "releases",
        method="POST",
        fields=(
            ("-f", "tag_name", config.tag),
            ("-f", "target_commitish", config.final_sha),
            ("-f", "name", f"MitoOverview {config.tag}"),
            ("-f", "body", "MitoOverview v0.3.0 release assets and validation evidence."),
            ("-F", "draft", "true"),
            ("-F", "prerelease", "false"),
            ("-F", "generate_release_notes", "false"),
        ),
    )
    if release is None:
        raise PublicationError("GitHub did not return the created draft release")
    _require_release_identity(release, config, state="draft")
    return release


def _query_hosting_protection_state(
    runner: Runner, config: PublicationConfig
) -> dict[str, Any]:
    command = _api_command(config.repository, "immutable-releases", "GET")
    result = runner.run(command, check=False)
    if _is_http_404(result):
        return {
            "supported": True,
            "enabled": False,
            "reason": "disabled",
        }
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise PublicationError(f"Unable to query immutable releases: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
        return {
            "supported": True,
            "enabled": None,
            "reason": "state_unavailable",
        }
    return {
        "supported": True,
        "enabled": payload["enabled"],
        "reason": "queried",
        "api_payload": payload,
    }


def _require_hosting_protection_state(
    runner: Runner, config: PublicationConfig
) -> dict[str, Any]:
    state = _query_hosting_protection_state(runner, config)
    if state.get("enabled") is not True:
        raise PublicationError("Immutable releases must remain enabled for v0.3.0 publication")
    return state


def _ensure_hosting_protection_state(
    runner: Runner, config: PublicationConfig
) -> dict[str, Any]:
    state = _query_hosting_protection_state(runner, config)
    if state.get("enabled") is True:
        return {**state, "enabled_by_publisher": False}
    command = _api_command(config.repository, "immutable-releases", "PUT")
    result = runner.run(command, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise PublicationError(f"Unable to enable immutable releases: {detail}")
    enabled = _query_hosting_protection_state(runner, config)
    if enabled.get("enabled") is not True:
        raise PublicationError("Immutable releases did not become enabled after PUT")
    return {**enabled, "enabled_by_publisher": True}


def _normalized_remote_assets(
    release: dict[str, Any], expected: AssetInventory, *, allow_subset: bool
) -> list[dict[str, Any]]:
    raw_assets = release.get("assets")
    if not isinstance(raw_assets, list):
        raise PublicationError("GitHub release response has no asset inventory")
    expected_by_name = expected.by_name
    observed: dict[str, dict[str, Any]] = {}
    for raw in raw_assets:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise PublicationError("GitHub returned a malformed release asset")
        name = raw["name"]
        if name in observed:
            raise PublicationError(f"GitHub returned duplicate release asset {name}")
        if name not in expected_by_name:
            raise PublicationError(f"Remote release contains unexpected asset {name}")
        expected_asset = expected_by_name[name]
        if raw.get("size") != expected_asset.size:
            raise PublicationError(
                f"Remote size mismatch for {name}: expected {expected_asset.size}, "
                f"observed {raw.get('size')!r}"
            )
        api_digest = raw.get("digest")
        if api_digest not in (None, "", f"sha256:{expected_asset.sha256}"):
            raise PublicationError(f"Remote API digest mismatch for {name}: {api_digest!r}")
        observed[name] = raw
    if not allow_subset and set(observed) != set(expected_by_name):
        raise PublicationError(
            "Remote asset inventory mismatch; "
            f"missing={sorted(set(expected_by_name) - set(observed))!r}"
        )
    return [
        {
            "name": name,
            "size": observed[name].get("size"),
            "asset_id": observed[name].get("id"),
            "api_url": observed[name].get("url"),
            "browser_download_url": observed[name].get("browser_download_url"),
            "api_digest": observed[name].get("digest"),
            "verified_sha256": expected_by_name[name].sha256,
        }
        for name in sorted(observed)
    ]


def _download_assets(
    runner: Runner,
    config: PublicationConfig,
    expected: AssetInventory,
    names: Sequence[str],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="github-release-download-", dir=config.output_directory
    ) as temporary_name:
        destination = Path(temporary_name)
        for name in sorted(names):
            runner.run(
                (
                    "gh",
                    "release",
                    "download",
                    config.tag,
                    "--repo",
                    config.repository,
                    "--pattern",
                    name,
                    "--dir",
                    str(destination),
                )
            )
        observed_names = {
            path.name for path in destination.iterdir() if path.is_file() and not path.is_symlink()
        }
        if observed_names != set(names):
            raise PublicationError(
                "Downloaded asset inventory mismatch; "
                f"expected={sorted(names)!r}; observed={sorted(observed_names)!r}"
            )
        verified: list[dict[str, Any]] = []
        for name in sorted(names):
            path = destination / name
            asset = expected.by_name[name]
            observed_hash = _sha256_file(path)
            if path.stat().st_size != asset.size or observed_hash != asset.sha256:
                raise PublicationError(f"Downloaded release asset differs from prepared {name}")
            verified.append(asset.as_dict())
    return {
        "method": "authenticated_redownload_sha256",
        "verified": True,
        "manifest_byte_identical": "SHA256SUMS" not in names
        or expected.by_name["SHA256SUMS"].sha256
        == next(item["sha256"] for item in verified if item["name"] == "SHA256SUMS"),
        "assets": verified,
    }


def _local_manifest_record(inventory: AssetInventory) -> dict[str, Any]:
    return {
        "manifest_name": "SHA256SUMS",
        "sha256sums_sha256": inventory.sha256sums_sha256,
        "assets": inventory.as_list(),
    }


def _base_receipt(
    config: PublicationConfig,
    *,
    phase: str,
    publication_state: str,
    verification_state: str,
    verified: bool,
    release: dict[str, Any],
    tag_ref: dict[str, Any],
    tag_object: dict[str, Any],
    hosting_state: dict[str, Any],
) -> dict[str, Any]:
    repository_url = _repository_url(config)
    payload: dict[str, Any] = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "release_version": config.tag,
        "git_commit": config.final_sha,
        "repository": repository_url,
        "repository_url": repository_url,
        "release_tag": config.tag,
        "github_release_url": _release_url(config),
        "github_actions_run_id": config.github_actions_run_id,
        "publication_state": publication_state,
        "repository_slug": config.repository,
        "final_sha": config.final_sha,
        "tag": config.tag,
        "mode": publication_state,
        "phase": phase,
        "verification_state": verification_state,
        "verified": verified,
        "generated_at": _utc_now(),
        "hosting_protection": hosting_state,
        "immutable_releases": hosting_state,
        "tag_ref": tag_ref,
        "tag_object": tag_object,
        "release": _release_record(release),
        "fresh_public_tag_validation": _validate_tag_validation_receipt(config),
    }
    if publication_state == "published":
        payload["published_at"] = release.get("published_at")
        payload["published_utc"] = release.get("published_at")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise PublicationError(f"Publication receipt cannot be a symlink: {path.name}")
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PublicationError(f"{label} is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"{label} is unreadable or malformed") from exc
    if not isinstance(payload, dict):
        raise PublicationError(f"{label} must contain a JSON object")
    return payload


def _safe_evidence_path(value: str) -> Path:
    path = Path(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PublicationError(f"Unsafe fresh-tag evidence path: {value!r}")
    return path


def _validate_tag_validation_receipt(
    config: PublicationConfig,
) -> dict[str, Any]:
    if config.tag_validation_receipt is None:
        raise PublicationError("Fresh public-tag validation receipt is required")
    receipt_path = config.tag_validation_receipt
    payload = _load_json(receipt_path, "fresh public-tag validation receipt")
    expected = {
        "schema_version": TAG_VALIDATION_SCHEMA_VERSION,
        "validation_profile": TAG_VALIDATION_PROFILE,
        "evidence_type": "fresh_public_tag_validation",
        "repository": _repository_url(config),
        "repository_slug": config.repository,
        "release_tag": config.tag,
        "git_commit": config.final_sha,
        "checked_out_commit": config.final_sha,
        "public_https_clone": True,
        "detached_head": True,
        "clean_worktree": True,
        "verdict": "PASS",
        "verified": True,
        "cases_path": "cases.tsv",
        "environment_path": "environment.txt",
        "tag_identity_path": "tag_identity.json",
        "evidence_manifest_path": "evidence.sha256",
        "trusted_asset_manifest_path": TRUSTED_ASSET_MANIFEST_NAME,
        "trusted_asset_count": len(CANONICAL_ASSET_NAMES),
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise PublicationError(
                f"Fresh public-tag validation mismatch for {field}: "
                f"expected {value!r}, observed {payload.get(field)!r}"
            )
    tag_object_sha = str(payload.get("tag_object_sha", ""))
    if SHA_PATTERN.fullmatch(tag_object_sha) is None:
        raise PublicationError("Fresh public-tag validation has no annotated tag object SHA")

    root = receipt_path.parent
    manifest_path = root / "evidence.sha256"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PublicationError("Fresh public-tag evidence manifest is missing")
    manifest: dict[str, str] = {}
    for line_number, line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        match = EVIDENCE_CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise PublicationError(
                f"Malformed fresh-tag evidence manifest line {line_number}: {line!r}"
            )
        relative = _safe_evidence_path(match.group("path")).as_posix()
        if relative in {receipt_path.name, manifest_path.name} or relative in manifest:
            raise PublicationError("Fresh-tag evidence manifest is duplicate or self-referential")
        manifest[relative] = match.group("digest")
    if not manifest:
        raise PublicationError("Fresh public-tag evidence manifest is empty")
    actual: set[str] = set()
    for candidate in root.rglob("*"):
        if candidate.is_symlink() or (
            not candidate.is_file() and not candidate.is_dir()
        ):
            raise PublicationError(
                "Fresh public-tag evidence contains a symlink or special file"
            )
        if candidate.is_file() and candidate not in {receipt_path, manifest_path}:
            actual.add(candidate.relative_to(root).as_posix())
    if set(manifest) != actual:
        raise PublicationError("Fresh public-tag evidence manifest inventory differs")
    for relative, expected_digest in manifest.items():
        if _sha256_file(root / relative) != expected_digest:
            raise PublicationError(f"Fresh public-tag evidence hash mismatch: {relative}")
    manifest_sha = _sha256_file(manifest_path)
    if payload.get("evidence_manifest_sha256") != manifest_sha:
        raise PublicationError("Fresh public-tag evidence manifest digest differs")

    trusted_path = root / TRUSTED_ASSET_MANIFEST_NAME
    if trusted_path.is_symlink() or not trusted_path.is_file():
        raise PublicationError("Trusted release-asset manifest is missing")
    trusted_digest = _sha256_file(trusted_path)
    if payload.get("trusted_asset_manifest_sha256") != trusted_digest:
        raise PublicationError("Trusted release-asset manifest digest differs")
    trusted = _load_json(trusted_path, "trusted release-asset manifest")
    trusted_identity = {
        "schema_version": TRUSTED_ASSET_MANIFEST_SCHEMA_VERSION,
        "manifest_type": "trusted_release_asset_manifest",
        "validation_profile": TAG_VALIDATION_PROFILE,
        "repository": _repository_url(config),
        "repository_slug": config.repository,
        "release_tag": config.tag,
        "git_commit": config.final_sha,
        "checked_out_commit": config.final_sha,
        "tag_object_sha": tag_object_sha,
        "asset_count": len(CANONICAL_ASSET_NAMES),
    }
    for field, value in trusted_identity.items():
        if trusted.get(field) != value:
            raise PublicationError(
                f"Trusted release-asset manifest mismatch for {field}: "
                f"expected {value!r}, observed {trusted.get(field)!r}"
            )
    raw_assets = trusted.get("assets")
    if not isinstance(raw_assets, list) or len(raw_assets) != len(CANONICAL_ASSET_NAMES):
        raise PublicationError("Trusted release-asset manifest inventory is incomplete")
    trusted_assets: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in raw_assets:
        if not isinstance(item, dict) or set(item) != {"name", "size", "sha256"}:
            raise PublicationError("Trusted release-asset manifest entry is malformed")
        name = item.get("name")
        size = item.get("size")
        digest = item.get("sha256")
        if (
            not isinstance(name, str)
            or name not in CANONICAL_ASSET_NAMES
            or name in seen_names
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(digest, str)
            or DIGEST_PATTERN.fullmatch(digest) is None
        ):
            raise PublicationError("Trusted release-asset manifest entry is invalid")
        seen_names.add(name)
        trusted_assets.append({"name": name, "size": size, "sha256": digest})
    if seen_names != set(CANONICAL_ASSET_NAMES):
        raise PublicationError("Trusted release-asset manifest inventory differs")
    if [item["name"] for item in trusted_assets] != sorted(CANONICAL_ASSET_NAMES):
        raise PublicationError("Trusted release-asset manifest inventory is not canonical")
    trusted_sha256sums = next(
        item for item in trusted_assets if item["name"] == "SHA256SUMS"
    )
    if trusted.get("sha256sums_sha256") != trusted_sha256sums["sha256"]:
        raise PublicationError("Trusted release-asset SHA256SUMS identity differs")

    cases_path = root / "cases.tsv"
    with cases_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != ("case_id", "verdict", "detail"):
            raise PublicationError("Fresh public-tag case table schema differs")
        rows = list(reader)
    case_ids = [row["case_id"] for row in rows]
    if (
        len(case_ids) != len(set(case_ids))
        or set(case_ids) != set(REQUIRED_TAG_VALIDATION_CASES)
        or any(row["verdict"] != "PASS" or not row["detail"] for row in rows)
    ):
        raise PublicationError("Fresh public-tag validation cases are incomplete or non-PASS")
    if payload.get("case_count") != len(rows):
        raise PublicationError("Fresh public-tag validation case count differs")

    tag_identity = _load_json(root / "tag_identity.json", "fresh-tag identity evidence")
    if tag_identity != {
        "annotated_tag": True,
        "checked_out_commit": config.final_sha,
        "git_commit": config.final_sha,
        "release_tag": config.tag,
        "tag_object_sha": tag_object_sha,
    }:
        raise PublicationError("Fresh public-tag annotated-tag identity differs")
    environment = (root / "environment.txt").read_text(encoding="utf-8")
    for required_line in (
        "python=3.12.13",
        "samtools=1.23.1",
        "htslib=1.23.1",
        "minimap2=2.31-r1302",
        "bwa=0.7.19-r1273",
        "threads=4",
    ):
        if required_line not in environment.splitlines():
            raise PublicationError(
                f"Fresh public-tag environment lacks required identity: {required_line}"
            )
    forbidden_paths = re.compile(
        r"/Users/[^/\s]+|/home/[^/\s]+|/private/tmp(?:/[^\s]*)?"
    )
    for relative in manifest:
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if forbidden_paths.search(text):
            raise PublicationError(
                f"Fresh public-tag evidence contains an absolute user path: {relative}"
            )
    return {
        "schema_version": TAG_VALIDATION_SCHEMA_VERSION,
        "validation_profile": TAG_VALIDATION_PROFILE,
        "receipt_sha256": _sha256_file(receipt_path),
        "evidence_manifest_sha256": manifest_sha,
        "trusted_asset_manifest_sha256": trusted_digest,
        "trusted_asset_manifest": {
            "manifest_name": TRUSTED_ASSET_MANIFEST_NAME,
            "sha256sums_sha256": trusted["sha256sums_sha256"],
            "assets": trusted_assets,
        },
        "tag_object_sha": tag_object_sha,
        "case_count": len(rows),
        "verdict": "PASS",
        "verified": True,
    }


def _assert_inventory_matches_trusted_manifest(
    inventory: AssetInventory, validation: dict[str, Any]
) -> None:
    """Require prepared bytes to equal the tag-bound fresh-validation inventory."""

    trusted = validation.get("trusted_asset_manifest")
    if not isinstance(trusted, dict) or not isinstance(trusted.get("assets"), list):
        raise PublicationError("Fresh public-tag evidence has no trusted asset inventory")
    expected = {
        item["name"]: (item["size"], item["sha256"])
        for item in trusted["assets"]
    }
    observed = {
        asset.name: (asset.size, asset.sha256) for asset in inventory.assets
    }
    if set(expected) != set(observed):
        raise PublicationError("Trusted release-asset inventory differs from prepared assets")
    comparison_order = sorted(set(expected) - {"SHA256SUMS"}) + ["SHA256SUMS"]
    for name in comparison_order:
        if observed[name] != expected[name]:
            raise PublicationError(
                f"Trusted release-asset hash or size mismatch for {name}"
            )
    if inventory.sha256sums_sha256 != trusted.get("sha256sums_sha256"):
        raise PublicationError("Trusted release-asset SHA256SUMS digest differs")


def _verify_prepublication_mode(runner: Runner, config: PublicationConfig) -> Path:
    """Capture read-only tag/repository identity before the report becomes an asset."""

    output = config.output_directory / "github_prepublication.json"
    if output.exists() or output.is_symlink():
        raise PublicationError("github_prepublication.json must not already exist")
    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    tag_ref, tag_object = _tag_record(ref_payload, tag_payload)
    if _find_release(runner, config) is not None:
        raise PublicationError(
            "Prepublication identity must be captured before a GitHub release exists"
        )
    hosting_state = _query_hosting_protection_state(runner, config)
    payload: dict[str, Any] = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "release_version": config.tag,
        "git_commit": config.final_sha,
        "repository": _repository_url(config),
        "repository_url": _repository_url(config),
        "repository_slug": config.repository,
        "release_tag": config.tag,
        "github_release_url": _release_url(config),
        "github_actions_run_id": config.github_actions_run_id,
        "publication_state": "prepublication",
        "verification_state": "verified_prepublication_identity",
        "verified": True,
        "phase": "verify-prepublication",
        "mode": "prepublication",
        "generated_at": _utc_now(),
        "github_api_read_only": True,
        "mutations_performed": False,
        "asset_publication_verified": False,
        "release_absent": True,
        "hosting_protection": hosting_state,
        "immutable_releases": hosting_state,
        "tag_ref": tag_ref,
        "tag_object": tag_object,
        "release": {
            "id": None,
            "api_url": None,
            "url": _release_url(config),
            "tag_name": config.tag,
            "target_commitish": config.final_sha,
            "name": f"MitoOverview {config.tag}",
            "draft": None,
            "prerelease": False,
            "immutable": None,
            "created_at": None,
            "published_at": None,
        },
    }
    _atomic_write_json(output, payload)
    return output


def _validate_receipt_identity(record: dict[str, Any], config: PublicationConfig) -> None:
    required = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "release_version": config.tag,
        "git_commit": config.final_sha,
        "repository": _repository_url(config),
        "repository_url": _repository_url(config),
        "release_tag": config.tag,
        "github_release_url": _release_url(config),
        "github_actions_run_id": config.github_actions_run_id,
        "repository_slug": config.repository,
        "final_sha": config.final_sha,
        "tag": config.tag,
    }
    for key, expected in required.items():
        if record.get(key) != expected:
            raise PublicationError(
                f"Publication receipt mismatch for {key}: expected {expected!r}, "
                f"observed {record.get(key)!r}"
            )
    tag_ref = record.get("tag_ref")
    tag_object = record.get("tag_object")
    if not isinstance(tag_ref, dict) or not isinstance(tag_object, dict):
        raise PublicationError("Publication receipt has no annotated-tag identity")
    if (
        tag_ref.get("ref") != f"refs/tags/{config.tag}"
        or tag_ref.get("object_type") != "tag"
        or not SHA_PATTERN.fullmatch(str(tag_ref.get("object_sha", "")))
        or tag_object.get("tag") != config.tag
        or tag_object.get("tag_object_sha") != tag_ref.get("object_sha")
        or tag_object.get("target_type") != "commit"
        or tag_object.get("peeled_target_sha") != config.final_sha
    ):
        raise PublicationError("Publication receipt annotated-tag identity is invalid")


def _load_draft_record(
    config: PublicationConfig,
    *,
    require_uploaded_assets: bool,
    inventory: AssetInventory | None = None,
) -> dict[str, Any]:
    path = config.output_directory / "github_publication.draft.json"
    record = _load_json(path, "github_publication.draft.json")
    _validate_receipt_identity(record, config)
    if record.get("publication_state") != "draft":
        raise PublicationError("Draft receipt has an invalid publication state")
    if require_uploaded_assets:
        if record.get("verification_state") != "verified_draft_assets":
            raise PublicationError("Publication is blocked until --upload-verify succeeds")
        if record.get("asset_upload_verified") is not True or inventory is None:
            raise PublicationError("Draft receipt has no verified asset inventory")
        if record.get("local_asset_manifest") != _local_manifest_record(inventory):
            raise PublicationError("Prepared assets differ from the verified draft receipt")
    return record


def _assert_tag_matches_receipt(
    receipt: dict[str, Any], ref_payload: dict[str, Any], tag_payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    tag_ref, tag_object = _tag_record(ref_payload, tag_payload)
    if tag_ref != receipt.get("tag_ref") or tag_object != receipt.get("tag_object"):
        raise PublicationError("Remote annotated tag object drifted from the receipt")
    return tag_ref, tag_object


def _assert_tag_matches_validation_receipt(
    config: PublicationConfig, tag_ref: dict[str, Any]
) -> None:
    """Bind fresh-tag evidence to the currently advertised annotated tag object."""

    validation = _validate_tag_validation_receipt(config)
    if validation["tag_object_sha"] != tag_ref.get("object_sha"):
        raise PublicationError(
            "Fresh public-tag validation tag object differs from the current "
            "remote annotated tag"
        )


def _assert_release_matches_receipt(
    receipt: dict[str, Any], release: dict[str, Any]
) -> None:
    recorded = receipt.get("release")
    if not isinstance(recorded, dict) or release.get("id") != recorded.get("id"):
        raise PublicationError("Remote release ID differs from the receipt")


def _write_draft_receipt(
    config: PublicationConfig,
    release: dict[str, Any],
    tag_ref: dict[str, Any],
    tag_object: dict[str, Any],
    hosting_state: dict[str, Any],
    *,
    phase: str,
    verification_state: str,
    verified: bool,
    remote_assets: list[dict[str, Any]],
    inventory: AssetInventory | None = None,
    download_verification: dict[str, Any] | None = None,
    uploaded_asset_names: Sequence[str] | None = None,
) -> Path:
    payload = _base_receipt(
        config,
        phase=phase,
        publication_state="draft",
        verification_state=verification_state,
        verified=verified,
        release=release,
        tag_ref=tag_ref,
        tag_object=tag_object,
        hosting_state=hosting_state,
    )
    payload["asset_upload_verified"] = verification_state == "verified_draft_assets"
    payload["remote_assets"] = remote_assets
    if uploaded_asset_names is not None:
        payload["uploaded_asset_names"] = sorted(uploaded_asset_names)
    if inventory is not None:
        payload["local_asset_manifest"] = _local_manifest_record(inventory)
    if download_verification is not None:
        payload["redownload_verification"] = download_verification
    path = config.output_directory / "github_publication.draft.json"
    _atomic_write_json(path, payload)
    return path


def _create_draft_mode(
    runner: Runner, config: PublicationConfig, inventory: AssetInventory
) -> Path:
    _assert_inventory_unchanged(inventory)
    final_path = config.output_directory / "github_publication.json"
    if final_path.exists() or final_path.is_symlink():
        record = _load_json(final_path, "github_publication.json")
        _validate_receipt_identity(record, config)
        if record.get("publication_state") == "published":
            if record.get("local_asset_manifest") != _local_manifest_record(inventory):
                raise PublicationError("Prepared assets differ from the published receipt")
            return final_path
        raise PublicationError("Existing final publication receipt is invalid")

    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    tag_ref, tag_object = _tag_record(ref_payload, tag_payload)
    _assert_tag_matches_validation_receipt(config, tag_ref)
    _assert_inventory_unchanged(inventory)
    hosting_state = _ensure_hosting_protection_state(runner, config)
    release = _find_release(runner, config)
    existing_draft_path = config.output_directory / "github_publication.draft.json"
    if release is not None:
        _require_release_identity(release, config, state="either")
        if release.get("draft") is not True:
            raise PublicationError("The v0.3.0 release is already published")
        if existing_draft_path.exists():
            prior = _load_draft_record(config, require_uploaded_assets=False)
            if prior.get("local_asset_manifest") != _local_manifest_record(inventory):
                raise PublicationError("Prepared assets differ from the draft receipt")
            _assert_release_matches_receipt(prior, release)
            _assert_tag_matches_receipt(prior, ref_payload, tag_payload)
            if prior.get("verification_state") == "verified_draft_assets":
                return existing_draft_path
        if release.get("assets"):
            raise PublicationError(
                "An existing draft has assets but no verified local upload receipt"
            )
    else:
        _assert_inventory_unchanged(inventory)
        release = _create_draft_release(runner, config)
        # Persist the transition before any follow-up query can fail.
        _write_draft_receipt(
            config,
            release,
            tag_ref,
            tag_object,
            hosting_state,
            phase="create-draft",
            verification_state="draft_transition_recorded",
            verified=False,
            remote_assets=[],
            inventory=inventory,
        )

    _require_release_identity(release, config, state="draft")
    if release.get("assets") != []:
        raise PublicationError("Draft release must be empty before upload verification")
    release = _query_release_by_id(runner, config, int(release["id"]))
    _require_release_identity(release, config, state="draft")
    if release.get("assets") != []:
        raise PublicationError("Queried draft release is not empty")
    ref_payload, tag_payload = _verify_tag(runner, config)
    queried_ref, queried_object = _tag_record(ref_payload, tag_payload)
    _assert_tag_matches_validation_receipt(config, queried_ref)
    if queried_ref != tag_ref or queried_object != tag_object:
        raise PublicationError("Annotated tag changed while creating the draft")
    confirmed_hosting_state = _require_hosting_protection_state(runner, config)
    confirmed_hosting_state["enabled_by_publisher"] = bool(
        hosting_state.get("enabled_by_publisher")
    )
    return _write_draft_receipt(
        config,
        release,
        tag_ref,
        tag_object,
        confirmed_hosting_state,
        phase="create-draft",
        verification_state="verified_empty_draft",
        verified=True,
        remote_assets=[],
        inventory=inventory,
    )


def _upload_verify_mode(
    runner: Runner, config: PublicationConfig, inventory: AssetInventory
) -> Path:
    final_path = config.output_directory / "github_publication.json"
    if final_path.exists() or final_path.is_symlink():
        record = _load_json(final_path, "github_publication.json")
        _validate_receipt_identity(record, config)
        if record.get("local_asset_manifest") != _local_manifest_record(inventory):
            raise PublicationError("Prepared assets differ from the published receipt")
        return final_path
    draft = _load_draft_record(config, require_uploaded_assets=False)
    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    tag_ref, tag_object = _assert_tag_matches_receipt(draft, ref_payload, tag_payload)
    _assert_tag_matches_validation_receipt(config, tag_ref)
    release = _find_release(runner, config)
    if release is None:
        raise PublicationError("The recorded draft release no longer exists")
    _require_release_identity(release, config, state="draft")
    _assert_release_matches_receipt(draft, release)

    remote_assets = _normalized_remote_assets(release, inventory, allow_subset=True)
    existing_names = [item["name"] for item in remote_assets]
    if existing_names:
        _download_assets(runner, config, inventory, existing_names)
    missing_names = sorted(set(inventory.by_name) - set(existing_names))
    hosting_state = _require_hosting_protection_state(runner, config)
    uploaded_names = list(existing_names)
    for name in missing_names:
        _assert_inventory_unchanged(inventory)
        runner.run(
            (
                "gh",
                "release",
                "upload",
                config.tag,
                str(inventory.root / name),
                "--repo",
                config.repository,
            )
        )
        uploaded_names.append(name)
        _write_draft_receipt(
            config,
            release,
            tag_ref,
            tag_object,
            hosting_state,
            phase="upload-verify",
            verification_state="upload_in_progress",
            verified=False,
            remote_assets=remote_assets,
            inventory=inventory,
            uploaded_asset_names=uploaded_names,
        )
        release = _query_release_by_id(runner, config, int(release["id"]))
        _require_release_identity(release, config, state="draft")
        remote_assets = _normalized_remote_assets(release, inventory, allow_subset=True)
        if set(uploaded_names) != {item["name"] for item in remote_assets}:
            raise PublicationError("Uploaded asset was not reflected in the draft inventory")

    remote_assets = _normalized_remote_assets(release, inventory, allow_subset=False)
    redownload = _download_assets(
        runner, config, inventory, sorted(inventory.by_name)
    )
    _assert_inventory_unchanged(inventory)
    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    tag_ref, tag_object = _assert_tag_matches_receipt(draft, ref_payload, tag_payload)
    _assert_tag_matches_validation_receipt(config, tag_ref)
    return _write_draft_receipt(
        config,
        release,
        tag_ref,
        tag_object,
        _require_hosting_protection_state(runner, config),
        phase="upload-verify",
        verification_state="verified_draft_assets",
        verified=True,
        remote_assets=remote_assets,
        inventory=inventory,
        download_verification=redownload,
        uploaded_asset_names=sorted(inventory.by_name),
    )


def _published_transition_receipt(
    config: PublicationConfig,
    release: dict[str, Any],
    tag_ref: dict[str, Any],
    tag_object: dict[str, Any],
    hosting_state: dict[str, Any],
    inventory: AssetInventory,
    remote_assets: list[dict[str, Any]],
    prepublish_download: dict[str, Any],
) -> dict[str, Any]:
    payload = _base_receipt(
        config,
        phase="publish",
        publication_state="published",
        verification_state="published_transition_recorded",
        verified=False,
        release=release,
        tag_ref=tag_ref,
        tag_object=tag_object,
        hosting_state=hosting_state,
    )
    payload.update(
        {
            "asset_upload_verified": True,
            "remote_assets": remote_assets,
            "local_asset_manifest": _local_manifest_record(inventory),
            "prepublish_redownload_verification": prepublish_download,
            "post_publish_verification": {
                "complete": False,
                "reason": "pending_remote_queries",
            },
        }
    )
    return payload


def _publish_mode(
    runner: Runner, config: PublicationConfig, inventory: AssetInventory
) -> Path:
    final_path = config.output_directory / "github_publication.json"
    draft = _load_draft_record(
        config, require_uploaded_assets=True, inventory=inventory
    )
    existing_final: dict[str, Any] | None = None
    if final_path.exists() or final_path.is_symlink():
        existing_final = _load_json(final_path, "github_publication.json")
        _validate_receipt_identity(existing_final, config)
        if existing_final.get("publication_state") != "published":
            raise PublicationError("Final receipt does not record a published release")

    # Complete every fallible local and remote check before the irreversible PATCH.
    _assert_inventory_unchanged(inventory)
    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    tag_ref, tag_object = _assert_tag_matches_receipt(draft, ref_payload, tag_payload)
    release = _find_release(runner, config)
    if release is None:
        raise PublicationError("The recorded release no longer exists")
    _require_release_identity(release, config, state="either")
    _assert_release_matches_receipt(draft, release)
    remote_assets = _normalized_remote_assets(release, inventory, allow_subset=False)
    if remote_assets != draft.get("remote_assets"):
        raise PublicationError("Remote release assets drifted from the draft receipt")
    prepublish_download = _download_assets(
        runner, config, inventory, sorted(inventory.by_name)
    )
    hosting_before = _require_hosting_protection_state(runner, config)
    _assert_inventory_unchanged(inventory)
    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    queried_tag_ref, _ = _assert_tag_matches_receipt(draft, ref_payload, tag_payload)
    _assert_tag_matches_validation_receipt(config, queried_tag_ref)

    if release.get("draft") is True:
        release_id = int(release["id"])
        updated = _api_object(
            runner,
            config.repository,
            f"releases/{release_id}",
            method="PATCH",
            fields=(("-F", "draft", "false"),),
        )
        if updated is None:
            raise PublicationError("GitHub did not return the published release transition")
        _require_release_identity(
            updated,
            config,
            state="published",
            require_immutable=False,
        )
        _assert_release_matches_receipt(draft, updated)
        release = updated
        # This receipt survives any failure in the optional post-publish queries.
        _atomic_write_json(
            final_path,
            _published_transition_receipt(
                config,
                release,
                tag_ref,
                tag_object,
                hosting_before,
                inventory,
                remote_assets,
                prepublish_download,
            ),
        )
        _require_release_identity(release, config, state="published")
    else:
        _require_release_identity(release, config, state="published")
        if existing_final is None:
            _atomic_write_json(
                final_path,
                _published_transition_receipt(
                    config,
                    release,
                    tag_ref,
                    tag_object,
                    hosting_before,
                    inventory,
                    remote_assets,
                    prepublish_download,
                ),
            )

    release = _query_release_by_id(runner, config, int(release["id"]))
    _require_release_identity(release, config, state="published")
    enumerated = _find_release(runner, config)
    if enumerated is None or enumerated.get("id") != release.get("id"):
        raise PublicationError("Published release enumeration did not return the same release")
    _require_release_identity(enumerated, config, state="published")
    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    tag_ref, tag_object = _assert_tag_matches_receipt(draft, ref_payload, tag_payload)
    _assert_tag_matches_validation_receipt(config, tag_ref)
    remote_assets = _normalized_remote_assets(release, inventory, allow_subset=False)
    published_download = _download_assets(
        runner, config, inventory, sorted(inventory.by_name)
    )
    hosting_after = _require_hosting_protection_state(runner, config)

    payload = _base_receipt(
        config,
        phase="publish",
        publication_state="published",
        verification_state="verified_published",
        verified=True,
        release=release,
        tag_ref=tag_ref,
        tag_object=tag_object,
        hosting_state=hosting_after,
    )
    payload.update(
        {
            "asset_upload_verified": True,
            "remote_assets": remote_assets,
            "local_asset_manifest": _local_manifest_record(inventory),
            "prepublish_redownload_verification": prepublish_download,
            "published_redownload_verification": published_download,
            "post_publish_verification": {
                "complete": True,
                "release_requeried": True,
                "release_enumerated": True,
                "annotated_tag_requeried": True,
                "assets_redownloaded": True,
            },
        }
    )
    _atomic_write_json(final_path, payload)
    return final_path


def publish_github_release(
    config: PublicationConfig, runner: Runner | None = None
) -> Path:
    """Execute one resumable publication phase and return its JSON receipt."""

    validated = _validate_config(config)
    command_runner = runner or SubprocessRunner()
    if validated.phase == "verify-prepublication":
        return _verify_prepublication_mode(command_runner, validated)
    validation = _validate_tag_validation_receipt(validated)
    assert validated.asset_directory is not None
    inventory = inspect_asset_inventory(validated.asset_directory)
    _assert_inventory_matches_trusted_manifest(inventory, validation)
    if validated.phase == "create-draft":
        return _create_draft_mode(command_runner, validated, inventory)
    if validated.phase == "upload-verify":
        return _upload_verify_mode(command_runner, validated, inventory)
    return _publish_mode(command_runner, validated, inventory)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture read-only prepublication identity, create or resume a tag-bound "
            "GitHub draft, verify canonical assets, or publish the same release."
        )
    )
    parser.add_argument("repository", help="GitHub repository slug, for example owner/repo")
    parser.add_argument("final_sha", help="Exact 40-character FINAL_SHA")
    parser.add_argument("tag", help=f"Existing annotated release tag; must be {EXPECTED_TAG}")
    parser.add_argument("output_directory", type=Path, help="Publication receipt directory")
    parser.add_argument(
        "--github-actions-run-id",
        type=int,
        required=True,
        help="Exact successful FINAL_SHA GitHub Actions run ID",
    )
    parser.add_argument(
        "--tag-validation-receipt",
        type=Path,
        help=(
            "Hash-manifested PASS receipt from a fresh public v0.3.0 tag clone; "
            "required for release mutation phases"
        ),
    )
    phases = parser.add_mutually_exclusive_group(required=True)
    phases.add_argument(
        "--verify-prepublication",
        dest="phase",
        action="store_const",
        const="verify-prepublication",
        help=(
            "Write read-only exact-main/tag metadata for report generation before "
            "any GitHub release exists"
        ),
    )
    phases.add_argument(
        "--create-draft",
        dest="phase",
        action="store_const",
        const="create-draft",
        help="Create or resume an empty draft for the existing annotated tag",
    )
    phases.add_argument(
        "--upload-verify",
        dest="phase",
        action="store_const",
        const="upload-verify",
        help="Resume missing uploads and redownload-verify canonical assets",
    )
    phases.add_argument(
        "--publish",
        dest="phase",
        action="store_const",
        const="publish",
        help="Publish or resume verification of the verified draft",
    )
    parser.add_argument(
        "--asset-directory",
        type=Path,
        help="Flat tag-bound canonical release asset directory; required for mutation phases",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = PublicationConfig(
        repository=args.repository,
        final_sha=args.final_sha,
        tag=args.tag,
        output_directory=args.output_directory,
        phase=args.phase,
        github_actions_run_id=args.github_actions_run_id,
        tag_validation_receipt=args.tag_validation_receipt,
        asset_directory=args.asset_directory,
    )
    try:
        record = publish_github_release(config)
    except PublicationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] {args.phase}: {record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
