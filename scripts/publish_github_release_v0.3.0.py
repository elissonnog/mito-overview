#!/usr/bin/env python3
"""Create and verify the immutable GitHub release for MitoOverview v0.3.0.

The utility has three monotonic phases: create an empty verified draft, upload
and independently verify prepared assets, then explicitly publish the verified
draft. Commands are always passed to ``subprocess`` as argument vectors; no
shell is involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence


EXPECTED_TAG = "v0.3.0"
PUBLICATION_SCHEMA_VERSION = "1.0"
API_VERSION = "2022-11-28"
ACCEPT_HEADER = "application/vnd.github+json"
REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9])?/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9])?$"
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ASSET_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,254}$")
CHECKSUM_LINE_PATTERN = re.compile(
    r"^(?P<digest>[0-9a-f]{64})  (?P<name>[A-Za-z0-9][A-Za-z0-9._+-]{0,254})$"
)
UNSUPPORTED_GH_PATTERNS = (
    "unknown command",
    "unknown flag",
    "not a gh command",
    "accepts 0 arg",
)
PHASES = ("create-draft", "upload-verify", "publish")


class PublicationError(RuntimeError):
    """Raised when a release safety or verification gate fails."""


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def run(self, args: Sequence[str], *, check: bool = True) -> CommandResult:
        """Run one command without invoking a shell."""


class SubprocessRunner:
    """Small, replaceable subprocess boundary used for every gh invocation."""

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
            args=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
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


def _validate_config(config: PublicationConfig) -> PublicationConfig:
    if not REPOSITORY_PATTERN.fullmatch(config.repository):
        raise PublicationError(
            "Repository must be an owner/name GitHub slug containing only safe characters"
        )
    if not SHA_PATTERN.fullmatch(config.final_sha):
        raise PublicationError("FINAL_SHA must be exactly 40 lowercase hexadecimal characters")
    if config.tag != EXPECTED_TAG:
        raise PublicationError(f"This utility publishes only the immutable tag {EXPECTED_TAG}")
    if config.phase not in PHASES:
        raise PublicationError(f"Publication phase must be one of {PHASES!r}")

    asset_directory: Path | None = None
    if config.phase == "create-draft":
        if config.asset_directory is not None:
            raise PublicationError("--create-draft does not accept an asset directory")
    else:
        if config.asset_directory is None:
            raise PublicationError(
                f"--{config.phase} requires --asset-directory"
            )
        asset_directory = config.asset_directory.expanduser()
        if asset_directory.is_symlink() or not asset_directory.is_dir():
            raise PublicationError(
                "Asset directory must be an existing, non-symlink directory"
            )
        asset_directory = asset_directory.resolve(strict=True)

    output_directory = config.output_directory.expanduser()
    if output_directory.exists() and output_directory.is_symlink():
        raise PublicationError("Output directory cannot be a symlink")
    output_directory.mkdir(parents=True, exist_ok=True)
    output_directory = output_directory.resolve(strict=True)

    if asset_directory is not None:
        if output_directory == asset_directory:
            raise PublicationError("Asset and output directories must be different")
        if output_directory.is_relative_to(asset_directory):
            raise PublicationError("Output directory cannot be nested inside the asset directory")
        if asset_directory.is_relative_to(output_directory):
            raise PublicationError("Asset directory cannot be nested inside the output directory")

    return PublicationConfig(
        repository=config.repository,
        final_sha=config.final_sha,
        tag=config.tag,
        output_directory=output_directory,
        phase=config.phase,
        asset_directory=asset_directory,
    )


def inspect_asset_inventory(directory: Path) -> AssetInventory:
    """Validate a flat, SHA256SUMS-governed release-asset directory."""

    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    if not entries:
        raise PublicationError("Asset directory is empty")

    paths: dict[str, Path] = {}
    for path in entries:
        if path.is_symlink():
            raise PublicationError(f"Asset inventory contains a symlink: {path.name}")
        if not path.is_file():
            raise PublicationError(
                f"Asset inventory must be flat and contain regular files only: {path.name}"
            )
        if not ASSET_NAME_PATTERN.fullmatch(path.name):
            raise PublicationError(f"Unsafe or dirty asset filename: {path.name!r}")
        paths[path.name] = path

    manifest_path = paths.get("SHA256SUMS")
    if manifest_path is None:
        raise PublicationError("Asset inventory must contain SHA256SUMS")
    manifest_bytes = manifest_path.read_bytes()
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

    actual_names = set(paths) - {"SHA256SUMS"}
    expected_names = set(expected)
    if expected_names != actual_names:
        missing = sorted(actual_names - expected_names)
        extra = sorted(expected_names - actual_names)
        raise PublicationError(
            "SHA256SUMS inventory mismatch; "
            f"unlisted_files={missing!r}; missing_files={extra!r}"
        )
    if not actual_names:
        raise PublicationError("At least one release asset in addition to SHA256SUMS is required")

    assets: list[Asset] = []
    for name in sorted(paths):
        path = paths[name]
        observed = _sha256_file(path)
        if name != "SHA256SUMS" and observed != expected[name]:
            raise PublicationError(
                f"SHA256 mismatch for {name}: expected {expected[name]}, observed {observed}"
            )
        assets.append(Asset(name=name, size=path.stat().st_size, sha256=observed))

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


def _is_http_404(result: CommandResult) -> bool:
    combined = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode != 0 and (
        re.search(r"\b404\b", combined) is not None or "not found" in combined
    )


def _api(
    runner: Runner,
    repository: str,
    endpoint: str,
    *,
    method: str = "GET",
    fields: Sequence[tuple[str, str, str]] = (),
    allow_not_found: bool = False,
) -> dict[str, Any] | None:
    command = [
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
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PublicationError(
            f"GitHub API {method} {endpoint} returned malformed JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise PublicationError(f"GitHub API {method} {endpoint} did not return an object")
    return payload


def _require_remote_commit(runner: Runner, config: PublicationConfig) -> None:
    payload = _api(runner, config.repository, f"commits/{config.final_sha}")
    if payload is None or payload.get("sha") != config.final_sha:
        raise PublicationError(
            f"Remote commit drift: expected {config.final_sha}, observed {payload!r}"
        )
    main = _api(runner, config.repository, "commits/main")
    if main is None or main.get("sha") != config.final_sha:
        raise PublicationError(
            f"Remote main drift: expected {config.final_sha}, observed {main!r}"
        )


def _remote_tag(
    runner: Runner, config: PublicationConfig
) -> dict[str, Any] | None:
    return _api(
        runner,
        config.repository,
        f"git/ref/tags/{config.tag}",
        allow_not_found=True,
    )


def _remote_release(
    runner: Runner, config: PublicationConfig
) -> dict[str, Any] | None:
    return _api(
        runner,
        config.repository,
        f"releases/tags/{config.tag}",
        allow_not_found=True,
    )


def _verify_tag(
    runner: Runner, config: PublicationConfig
) -> tuple[dict[str, Any], dict[str, Any]]:
    ref_payload = _remote_tag(runner, config)
    if ref_payload is None:
        raise PublicationError(f"Remote tag {config.tag} is missing")
    ref_object = ref_payload.get("object")
    if not isinstance(ref_object, dict):
        raise PublicationError("Remote tag reference has no object")
    if ref_payload.get("ref") != f"refs/tags/{config.tag}":
        raise PublicationError("Remote tag reference name drifted")
    if ref_object.get("type") != "tag" or not SHA_PATTERN.fullmatch(
        str(ref_object.get("sha", ""))
    ):
        raise PublicationError("Remote tag is not an annotated tag object")

    tag_payload = _api(
        runner,
        config.repository,
        f"git/tags/{ref_object['sha']}",
    )
    tag_target = tag_payload.get("object") if tag_payload else None
    if not isinstance(tag_target, dict):
        raise PublicationError("Annotated tag object has no target")
    if tag_payload.get("tag") != config.tag:
        raise PublicationError("Annotated tag name drifted")
    if tag_target.get("type") != "commit" or tag_target.get("sha") != config.final_sha:
        raise PublicationError(
            "Annotated tag peel drift: "
            f"expected commit {config.final_sha}, observed {tag_target!r}"
        )
    return ref_payload, tag_payload


def _create_annotated_tag(
    runner: Runner, config: PublicationConfig
) -> tuple[dict[str, Any], dict[str, Any]]:
    tag_payload = _api(
        runner,
        config.repository,
        "git/tags",
        method="POST",
        fields=(
            ("-f", "tag", config.tag),
            ("-f", "message", f"MitoOverview {config.tag}"),
            ("-f", "object", config.final_sha),
            ("-f", "type", "commit"),
        ),
    )
    tag_object_sha = str((tag_payload or {}).get("sha", ""))
    if not SHA_PATTERN.fullmatch(tag_object_sha):
        raise PublicationError("GitHub did not return a valid annotated-tag object SHA")
    _api(
        runner,
        config.repository,
        "git/refs",
        method="POST",
        fields=(
            ("-f", "ref", f"refs/tags/{config.tag}"),
            ("-f", "sha", tag_object_sha),
        ),
    )
    return _verify_tag(runner, config)


def _immutable_state(runner: Runner, config: PublicationConfig) -> dict[str, Any] | None:
    return _api(
        runner,
        config.repository,
        "immutable-releases",
        allow_not_found=True,
    )


def _ensure_immutable_releases(
    runner: Runner, config: PublicationConfig
) -> dict[str, Any]:
    state = _immutable_state(runner, config)
    if state is not None and state.get("enabled") not in (True, False):
        raise PublicationError("GitHub returned a malformed immutable releases state")
    if state is None or state.get("enabled") is False:
        _api(
            runner,
            config.repository,
            "immutable-releases",
            method="PUT",
        )
        state = _immutable_state(runner, config)
    if state is None or state.get("enabled") is not True:
        raise PublicationError("GitHub immutable releases could not be enabled and verified")
    return {"enabled": True, "api_payload": state}


def _require_immutable_releases(
    runner: Runner, config: PublicationConfig
) -> dict[str, Any]:
    state = _immutable_state(runner, config)
    if state is None or state.get("enabled") is not True:
        raise PublicationError(
            "GitHub immutable releases are no longer enabled; later phases will not mutate this setting"
        )
    return {"enabled": True, "api_payload": state}


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
        "created_at": release.get("created_at"),
        "published_at": release.get("published_at"),
    }


def _require_release_identity(
    release: dict[str, Any],
    config: PublicationConfig,
    *,
    require_draft: bool,
) -> None:
    if not isinstance(release.get("id"), int):
        raise PublicationError("GitHub release has no integer release ID")
    if release.get("tag_name") != config.tag:
        raise PublicationError("GitHub release tag drifted")
    if release.get("target_commitish") != config.final_sha:
        raise PublicationError(
            "GitHub release target drift: "
            f"expected {config.final_sha}, observed {release.get('target_commitish')!r}"
        )
    if require_draft:
        if release.get("draft") is not True or release.get("published_at") is not None:
            raise PublicationError("Expected a verified unpublished draft release")
    elif release.get("draft") is not False or not release.get("published_at"):
        raise PublicationError("Published release state was not confirmed by GitHub")


def _create_draft_release(runner: Runner, config: PublicationConfig) -> dict[str, Any]:
    release = _api(
        runner,
        config.repository,
        "releases",
        method="POST",
        fields=(
            ("-f", "tag_name", config.tag),
            ("-f", "target_commitish", config.final_sha),
            ("-f", "name", f"MitoOverview {config.tag}"),
            ("-f", "body", "Verified MitoOverview v0.3.0 release assets."),
            ("-F", "draft", "true"),
            ("-F", "prerelease", "false"),
            ("-F", "generate_release_notes", "false"),
        ),
    )
    if release is None:
        raise PublicationError("GitHub did not return the created draft release")
    _require_release_identity(release, config, require_draft=True)
    return release


def _query_release_by_id(
    runner: Runner, config: PublicationConfig, release_id: int
) -> dict[str, Any]:
    release = _api(runner, config.repository, f"releases/{release_id}")
    if release is None:
        raise PublicationError(f"GitHub release ID {release_id} disappeared")
    return release


def _remote_assets(
    release: dict[str, Any], expected: AssetInventory
) -> list[dict[str, Any]]:
    raw_assets = release.get("assets")
    if not isinstance(raw_assets, list):
        raise PublicationError("GitHub release response has no asset inventory")
    expected_by_name = expected.by_name
    observed_by_name: dict[str, dict[str, Any]] = {}
    for raw in raw_assets:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise PublicationError("GitHub returned a malformed release asset")
        name = raw["name"]
        if name in observed_by_name:
            raise PublicationError(f"GitHub returned duplicate release asset {name}")
        observed_by_name[name] = raw

    if set(observed_by_name) != set(expected_by_name):
        raise PublicationError(
            "Remote asset inventory mismatch; "
            f"expected={sorted(expected_by_name)!r}; observed={sorted(observed_by_name)!r}"
        )

    normalized: list[dict[str, Any]] = []
    for name in sorted(expected_by_name):
        raw = observed_by_name[name]
        expected_asset = expected_by_name[name]
        if raw.get("size") != expected_asset.size:
            raise PublicationError(
                f"Remote size mismatch for {name}: "
                f"expected {expected_asset.size}, observed {raw.get('size')!r}"
            )
        api_digest = raw.get("digest")
        if api_digest not in (None, "", f"sha256:{expected_asset.sha256}"):
            raise PublicationError(
                f"Remote API digest mismatch for {name}: {api_digest!r}"
            )
        normalized.append(
            {
                "name": name,
                "size": raw.get("size"),
                "asset_id": raw.get("id"),
                "api_url": raw.get("url"),
                "browser_download_url": raw.get("browser_download_url"),
                "api_digest": api_digest,
                "verified_sha256": expected_asset.sha256,
            }
        )
    return normalized


def _upload_assets(runner: Runner, config: PublicationConfig, inventory: AssetInventory) -> None:
    for asset in inventory.assets:
        _assert_inventory_unchanged(inventory)
        runner.run(
            (
                "gh",
                "release",
                "upload",
                config.tag,
                str(inventory.root / asset.name),
                "--repo",
                config.repository,
            )
        )
    _assert_inventory_unchanged(inventory)


def _fresh_download(
    runner: Runner,
    config: PublicationConfig,
    expected: AssetInventory,
    destination_name: str,
) -> dict[str, Any]:
    destination = config.output_directory / destination_name
    if destination.exists() or destination.is_symlink():
        raise PublicationError(f"Fresh verification directory already exists: {destination}")
    destination.mkdir(mode=0o700)
    runner.run(
        (
            "gh",
            "release",
            "download",
            config.tag,
            "--repo",
            config.repository,
            "--dir",
            str(destination),
        )
    )
    downloaded = inspect_asset_inventory(destination)
    if _inventory_signature(downloaded) != _inventory_signature(expected):
        raise PublicationError("Redownloaded release assets are not byte-identical")
    if downloaded.sha256sums_bytes != expected.sha256sums_bytes:
        raise PublicationError("Redownloaded SHA256SUMS is not byte-identical")
    return {
        "path": str(destination),
        "manifest_byte_identical": True,
        "inventory_byte_identical": True,
        "sha256sums_sha256": downloaded.sha256sums_sha256,
        "assets": downloaded.as_list(),
    }


def _safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise PublicationError(f"Refusing to overwrite publication record: {path}")
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


def _replace_verified_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace the already-validated draft receipt."""

    if path.is_symlink() or not path.is_file():
        raise PublicationError(f"Verified draft receipt disappeared before update: {path}")
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


def _load_draft_record(
    config: PublicationConfig,
    *,
    require_uploaded_assets: bool,
    inventory: AssetInventory | None = None,
) -> dict[str, Any]:
    path = config.output_directory / "github_publication.draft.json"
    if path.is_symlink() or not path.is_file():
        raise PublicationError(
            f"--{config.phase} requires github_publication.draft.json from --create-draft"
        )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError("Draft publication record is unreadable or malformed") from exc
    if not isinstance(record, dict):
        raise PublicationError("Draft publication record must be a JSON object")
    required = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "mode": "draft",
        "verified": True,
        "repository": config.repository,
        "final_sha": config.final_sha,
        "tag": config.tag,
    }
    for key, expected_value in required.items():
        if record.get(key) != expected_value:
            raise PublicationError(
                f"Draft publication record mismatch for {key}: "
                f"expected {expected_value!r}, observed {record.get(key)!r}"
            )
    immutable = record.get("immutable_releases")
    if not isinstance(immutable, dict) or immutable.get("enabled") is not True:
        raise PublicationError("Draft receipt does not attest immutable releases")
    tag_ref = record.get("tag_ref")
    tag_object = record.get("tag_object")
    if not isinstance(tag_ref, dict) or not isinstance(tag_object, dict):
        raise PublicationError("Draft receipt has no verified annotated-tag identity")
    if (
        tag_ref.get("ref") != f"refs/tags/{config.tag}"
        or tag_ref.get("object_type") != "tag"
        or not SHA_PATTERN.fullmatch(str(tag_ref.get("object_sha", "")))
        or tag_object.get("tag") != config.tag
        or tag_object.get("tag_object_sha") != tag_ref.get("object_sha")
        or tag_object.get("target_type") != "commit"
        or tag_object.get("peeled_target_sha") != config.final_sha
    ):
        raise PublicationError("Draft receipt annotated-tag identity is invalid")
    release = record.get("release")
    if not isinstance(release, dict):
        raise PublicationError("Draft receipt has no queried release metadata")
    if (
        not isinstance(release.get("id"), int)
        or release.get("tag_name") != config.tag
        or release.get("target_commitish") != config.final_sha
        or release.get("draft") is not True
        or release.get("published_at") is not None
    ):
        raise PublicationError("Draft receipt release identity or state is invalid")
    if require_uploaded_assets:
        if record.get("verification_state") != "verified_draft_assets":
            raise PublicationError(
                "Publication is blocked until --upload-verify completes successfully"
            )
        if record.get("asset_upload_verified") is not True:
            raise PublicationError("Draft receipt does not attest a verified asset upload")
        if inventory is None:
            raise PublicationError("Internal error: upload verification requires an inventory")
        local = record.get("local_asset_manifest")
        if not isinstance(local, dict):
            raise PublicationError("Draft record has no local asset manifest")
        if local.get("sha256sums_sha256") != inventory.sha256sums_sha256:
            raise PublicationError("Prepared SHA256SUMS differs from the verified draft")
        if local.get("assets") != inventory.as_list():
            raise PublicationError("Prepared asset inventory differs from the verified draft")
    else:
        if record.get("verification_state") != "verified_empty_draft":
            raise PublicationError(
                "--upload-verify requires the unmodified empty-draft receipt"
            )
        if record.get("asset_upload_verified") is not False:
            raise PublicationError("Empty-draft receipt has an invalid upload state")
        if record.get("remote_assets") != []:
            raise PublicationError("Empty-draft receipt unexpectedly records remote assets")
    return record


def _attestation_unsupported(result: CommandResult) -> bool:
    message = f"{result.stdout}\n{result.stderr}".lower()
    return any(pattern in message for pattern in UNSUPPORTED_GH_PATTERNS)


def _parse_optional_json(output: str) -> Any:
    if not output.strip():
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"text": output.strip()}


def _verify_attestation_command(
    runner: Runner,
    command: Sequence[str],
    *,
    attempts: int = 6,
    delay_seconds: float = 2.0,
) -> dict[str, Any]:
    last: CommandResult | None = None
    for attempt in range(1, attempts + 1):
        result = runner.run(command, check=False)
        last = result
        if result.returncode == 0:
            return {
                "supported": True,
                "verified": True,
                "attempts": attempt,
                "result": _parse_optional_json(result.stdout),
            }
        if _attestation_unsupported(result):
            return {
                "supported": False,
                "verified": None,
                "attempts": attempt,
                "reason": (result.stderr.strip() or result.stdout.strip()),
            }
        if attempt < attempts:
            time.sleep(delay_seconds)
    assert last is not None
    detail = last.stderr.strip() or last.stdout.strip() or "no command output"
    raise PublicationError(f"GitHub release attestation verification failed: {detail}")


def _verify_release_attestations(
    runner: Runner,
    config: PublicationConfig,
    downloaded: dict[str, Any],
) -> dict[str, Any]:
    release_result = _verify_attestation_command(
        runner,
        (
            "gh",
            "release",
            "verify",
            config.tag,
            "--repo",
            config.repository,
            "--format",
            "json",
        ),
    )
    asset_results: list[dict[str, Any]] = []
    for asset in downloaded["assets"]:
        path = Path(downloaded["path"]) / asset["name"]
        result = _verify_attestation_command(
            runner,
            (
                "gh",
                "release",
                "verify-asset",
                config.tag,
                str(path),
                "--repo",
                config.repository,
                "--format",
                "json",
            ),
        )
        asset_results.append({"name": asset["name"], "path": str(path), **result})
    return {"release": release_result, "assets": asset_results}


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


def _create_draft_mode(runner: Runner, config: PublicationConfig) -> Path:
    draft_record_path = config.output_directory / "github_publication.draft.json"
    final_record_path = config.output_directory / "github_publication.json"
    if draft_record_path.exists() or final_record_path.exists():
        raise PublicationError("Publication output already contains a release record")

    _require_remote_commit(runner, config)
    existing_tag = _remote_tag(runner, config)
    existing_release = _remote_release(runner, config)
    if existing_tag is not None or existing_release is not None:
        raise PublicationError(
            "Refusing to modify a pre-existing remote tag or release; "
            f"tag_exists={existing_tag is not None}, release_exists={existing_release is not None}"
        )

    immutable = _ensure_immutable_releases(runner, config)
    ref_payload, tag_payload = _create_annotated_tag(runner, config)
    _require_remote_commit(runner, config)
    _verify_tag(runner, config)
    release = _create_draft_release(runner, config)
    if release.get("assets") != []:
        raise PublicationError("New draft release unexpectedly contains assets")
    release = _query_release_by_id(runner, config, int(release["id"]))
    _require_release_identity(release, config, require_draft=True)
    if release.get("assets") != []:
        raise PublicationError("Queried draft release is not empty")
    ref_payload, tag_payload = _verify_tag(runner, config)
    immutable = _require_immutable_releases(runner, config)
    tag_ref, tag_object = _tag_record(ref_payload, tag_payload)

    payload = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "mode": "draft",
        "phase": "create-draft",
        "verification_state": "verified_empty_draft",
        "verified": True,
        "asset_upload_verified": False,
        "generated_at": _utc_now(),
        "repository": config.repository,
        "final_sha": config.final_sha,
        "tag": config.tag,
        "immutable_releases": immutable,
        "tag_ref": tag_ref,
        "tag_object": tag_object,
        "release": _release_record(release),
        "remote_assets": [],
    }
    _safe_write_json(draft_record_path, payload)
    return draft_record_path


def _upload_verify_mode(
    runner: Runner, config: PublicationConfig, inventory: AssetInventory
) -> Path:
    draft_record_path = config.output_directory / "github_publication.draft.json"
    if (config.output_directory / "github_publication.json").exists():
        raise PublicationError("A published-release receipt already exists")
    draft_record = _load_draft_record(
        config, require_uploaded_assets=False
    )

    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    queried_tag_ref, queried_tag_object = _tag_record(ref_payload, tag_payload)
    if queried_tag_ref != draft_record.get("tag_ref") or queried_tag_object != draft_record.get(
        "tag_object"
    ):
        raise PublicationError("Remote annotated tag drifted from the empty-draft receipt")
    immutable = _require_immutable_releases(runner, config)
    release = _remote_release(runner, config)
    if release is None:
        raise PublicationError("The verified empty draft release no longer exists")
    _require_release_identity(release, config, require_draft=True)
    if release.get("id") != draft_record.get("release", {}).get("id"):
        raise PublicationError("Remote draft release ID differs from the local receipt")
    if _release_record(release) != draft_record.get("release"):
        raise PublicationError("Remote draft metadata drifted from the local receipt")
    if release.get("assets") != []:
        raise PublicationError(
            "Remote draft is no longer empty; refusing to overwrite or append assets"
        )

    _assert_inventory_unchanged(inventory)
    _upload_assets(runner, config, inventory)
    release = _query_release_by_id(runner, config, int(release["id"]))
    _require_release_identity(release, config, require_draft=True)
    remote_assets = _remote_assets(release, inventory)
    downloaded = _fresh_download(
        runner,
        config,
        inventory,
        "github_release_draft_redownload",
    )
    _assert_inventory_unchanged(inventory)
    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    queried_tag_ref, queried_tag_object = _tag_record(ref_payload, tag_payload)
    if queried_tag_ref != draft_record.get("tag_ref") or queried_tag_object != draft_record.get(
        "tag_object"
    ):
        raise PublicationError("Remote annotated tag drifted from the upload receipt")
    immutable = _require_immutable_releases(runner, config)
    tag_ref, tag_object = _tag_record(ref_payload, tag_payload)

    payload = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "mode": "draft",
        "phase": "upload-verify",
        "verification_state": "verified_draft_assets",
        "verified": True,
        "asset_upload_verified": True,
        "generated_at": _utc_now(),
        "empty_draft_verified_at": draft_record.get("generated_at"),
        "repository": config.repository,
        "final_sha": config.final_sha,
        "tag": config.tag,
        "immutable_releases": immutable,
        "tag_ref": tag_ref,
        "tag_object": tag_object,
        "release": _release_record(release),
        "remote_assets": remote_assets,
        "local_asset_manifest": {
            "path": str(inventory.root / "SHA256SUMS"),
            "sha256sums_sha256": inventory.sha256sums_sha256,
            "assets": inventory.as_list(),
        },
        "redownload_verification": downloaded,
    }
    _replace_verified_json(draft_record_path, payload)
    return draft_record_path


def _publish_mode(
    runner: Runner, config: PublicationConfig, inventory: AssetInventory
) -> Path:
    final_record_path = config.output_directory / "github_publication.json"
    if final_record_path.exists() or final_record_path.is_symlink():
        raise PublicationError("Refusing to overwrite github_publication.json")
    draft_record = _load_draft_record(
        config, require_uploaded_assets=True, inventory=inventory
    )

    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    immutable = _require_immutable_releases(runner, config)
    release = _remote_release(runner, config)
    if release is None:
        raise PublicationError("The locally attested draft release no longer exists")
    _require_release_identity(release, config, require_draft=True)
    if release.get("id") != draft_record.get("release", {}).get("id"):
        raise PublicationError("Remote draft release ID differs from the local attestation")
    if _release_record(release) != draft_record.get("release"):
        raise PublicationError("Remote draft metadata drifted from the local attestation")
    remote_assets_before = _remote_assets(release, inventory)
    if remote_assets_before != draft_record.get("remote_assets"):
        raise PublicationError("Remote draft assets drifted from the local attestation")
    prepublish_download = _fresh_download(
        runner,
        config,
        inventory,
        "github_release_publish_precheck",
    )
    _assert_inventory_unchanged(inventory)
    _require_remote_commit(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)

    release_id = int(release["id"])
    updated = _api(
        runner,
        config.repository,
        f"releases/{release_id}",
        method="PATCH",
        fields=(("-F", "draft", "false"),),
    )
    if updated is None:
        raise PublicationError("GitHub did not return the published release")
    release = _query_release_by_id(runner, config, release_id)
    _require_release_identity(release, config, require_draft=False)
    immutable = _require_immutable_releases(runner, config)
    ref_payload, tag_payload = _verify_tag(runner, config)
    remote_assets = _remote_assets(release, inventory)
    published_download = _fresh_download(
        runner,
        config,
        inventory,
        "github_release_published_redownload",
    )
    attestations = _verify_release_attestations(
        runner, config, published_download
    )
    tag_ref, tag_object = _tag_record(ref_payload, tag_payload)

    payload = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "mode": "published",
        "phase": "publish",
        "verification_state": "verified_published",
        "verified": True,
        "generated_at": _utc_now(),
        "repository": config.repository,
        "final_sha": config.final_sha,
        "tag": config.tag,
        "published_at": release.get("published_at"),
        "immutable_releases": immutable,
        "tag_ref": tag_ref,
        "tag_object": tag_object,
        "release": _release_record(release),
        "remote_assets": remote_assets,
        "local_asset_manifest": {
            "path": str(inventory.root / "SHA256SUMS"),
            "sha256sums_sha256": inventory.sha256sums_sha256,
            "assets": inventory.as_list(),
        },
        "draft_attestation_path": str(
            config.output_directory / "github_publication.draft.json"
        ),
        "prepublish_redownload_verification": prepublish_download,
        "published_redownload_verification": published_download,
        "release_attestations": attestations,
    }
    _safe_write_json(final_record_path, payload)
    return final_record_path


def publish_github_release(
    config: PublicationConfig, runner: Runner | None = None
) -> Path:
    """Execute one publication phase and return its verified JSON receipt."""

    validated = _validate_config(config)
    command_runner = runner or SubprocessRunner()
    if validated.phase == "create-draft":
        return _create_draft_mode(command_runner, validated)
    assert validated.asset_directory is not None
    inventory = inspect_asset_inventory(validated.asset_directory)
    if validated.phase == "upload-verify":
        return _upload_verify_mode(command_runner, validated, inventory)
    return _publish_mode(command_runner, validated, inventory)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create an empty verified GitHub draft, verify prepared uploads, or "
            "explicitly publish the same attested v0.3.0 release."
        )
    )
    parser.add_argument("repository", help="GitHub repository slug, for example owner/repo")
    parser.add_argument("final_sha", help="Exact 40-character FINAL_SHA")
    parser.add_argument("tag", help=f"Release tag; must be {EXPECTED_TAG}")
    parser.add_argument("output_directory", type=Path, help="Publication attestation output directory")
    phases = parser.add_mutually_exclusive_group(required=True)
    phases.add_argument(
        "--create-draft",
        dest="phase",
        action="store_const",
        const="create-draft",
        help="Create and attest a new empty immutable draft release",
    )
    phases.add_argument(
        "--upload-verify",
        dest="phase",
        action="store_const",
        const="upload-verify",
        help="Upload and redownload-verify assets for the attested empty draft",
    )
    phases.add_argument(
        "--publish",
        dest="phase",
        action="store_const",
        const="publish",
        help="Publish only a draft with a verified upload receipt",
    )
    parser.add_argument(
        "--asset-directory",
        type=Path,
        help="Flat prepared asset directory; required after --create-draft",
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
