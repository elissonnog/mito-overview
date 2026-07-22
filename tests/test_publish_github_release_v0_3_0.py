from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import pytest


REPO_ROOT = Path(__file__).parents[1]
SCRIPT = REPO_ROOT / "scripts" / "publish_github_release_v0.3.0.py"
SPEC = importlib.util.spec_from_file_location("publish_github_release_v030", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
publication = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publication
SPEC.loader.exec_module(publication)

FINAL_SHA = "1" * 40
OTHER_SHA = "2" * 40
TAG_OBJECT_SHA = "a" * 40
OTHER_TAG_OBJECT_SHA = "b" * 40
REPOSITORY = "elissonnog/mito-overview"
RUN_ID = 28819232067


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_assets(root: Path) -> dict[str, bytes]:
    root.mkdir(parents=True)
    payloads = {
        name: f"fixture:{name}\n".encode("ascii")
        for name in publication.CANONICAL_ASSET_NAMES
        if name != "SHA256SUMS"
    }
    for name, payload in payloads.items():
        (root / name).write_bytes(payload)
    manifest = "".join(
        f"{_sha256(payloads[name])}  {name}\n" for name in sorted(payloads)
    ).encode("ascii")
    (root / "SHA256SUMS").write_bytes(manifest)
    return {**payloads, "SHA256SUMS": manifest}


def _rewrite_sha256sums(root: Path) -> bytes:
    payloads = {
        name: (root / name).read_bytes()
        for name in publication.CANONICAL_ASSET_NAMES
        if name != "SHA256SUMS"
    }
    manifest = "".join(
        f"{_sha256(payloads[name])}  {name}\n" for name in sorted(payloads)
    ).encode("ascii")
    (root / "SHA256SUMS").write_bytes(manifest)
    return manifest


def _write_tag_validation_evidence(root: Path, asset_root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    receipt = root / "fresh_public_tag_validation.json"
    if receipt.exists():
        return receipt
    cases = root / "cases.tsv"
    cases.write_text(
        "case_id\tverdict\tdetail\n"
        + "".join(
            f"{case_id}\tPASS\tverified fixture evidence\n"
            for case_id in sorted(publication.REQUIRED_TAG_VALIDATION_CASES)
        ),
        encoding="utf-8",
    )
    (root / "environment.txt").write_text(
        "\n".join(
            (
                "python=3.12.13",
                "samtools=1.23.1",
                "htslib=1.23.1",
                "minimap2=2.31-r1302",
                "bwa=0.7.19-r1273",
                "threads=4",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "tag_identity.json").write_text(
        json.dumps(
            {
                "annotated_tag": True,
                "checked_out_commit": FINAL_SHA,
                "git_commit": FINAL_SHA,
                "release_tag": publication.EXPECTED_TAG,
                "tag_object_sha": TAG_OBJECT_SHA,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "commands").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    (root / "commands/run.sh").write_text("pytest -q\n", encoding="utf-8")
    (root / "logs/run.log").write_text("all checks passed\n", encoding="utf-8")
    trusted_manifest = root / publication.TRUSTED_ASSET_MANIFEST_NAME
    trusted_assets = []
    for name in sorted(publication.CANONICAL_ASSET_NAMES):
        path = asset_root / name
        trusted_assets.append(
            {"name": name, "sha256": _sha256(path.read_bytes()), "size": path.stat().st_size}
        )
    trusted_manifest.write_text(
        json.dumps(
            {
                "schema_version": publication.TRUSTED_ASSET_MANIFEST_SCHEMA_VERSION,
                "manifest_type": "trusted_release_asset_manifest",
                "validation_profile": publication.TAG_VALIDATION_PROFILE,
                "repository": f"https://github.com/{REPOSITORY}",
                "repository_slug": REPOSITORY,
                "release_tag": publication.EXPECTED_TAG,
                "git_commit": FINAL_SHA,
                "checked_out_commit": FINAL_SHA,
                "tag_object_sha": TAG_OBJECT_SHA,
                "asset_count": len(trusted_assets),
                "sha256sums_sha256": next(
                    item["sha256"]
                    for item in trusted_assets
                    if item["name"] == "SHA256SUMS"
                ),
                "assets": trusted_assets,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = root / "evidence.sha256"
    evidence_files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path not in {manifest, receipt}
    )
    manifest.write_text(
        "".join(
            f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}\n"
            for path in evidence_files
        ),
        encoding="utf-8",
    )
    receipt.write_text(
        json.dumps(
            {
                "schema_version": publication.TAG_VALIDATION_SCHEMA_VERSION,
                "validation_profile": publication.TAG_VALIDATION_PROFILE,
                "evidence_type": "fresh_public_tag_validation",
                "repository": f"https://github.com/{REPOSITORY}",
                "repository_slug": REPOSITORY,
                "release_tag": publication.EXPECTED_TAG,
                "git_commit": FINAL_SHA,
                "checked_out_commit": FINAL_SHA,
                "tag_object_sha": TAG_OBJECT_SHA,
                "public_https_clone": True,
                "detached_head": True,
                "clean_worktree": True,
                "verdict": "PASS",
                "verified": True,
                "case_count": len(publication.REQUIRED_TAG_VALIDATION_CASES),
                "cases_path": "cases.tsv",
                "environment_path": "environment.txt",
                "tag_identity_path": "tag_identity.json",
                "evidence_manifest_path": "evidence.sha256",
                "evidence_manifest_sha256": _sha256(manifest.read_bytes()),
                "trusted_asset_manifest_path": publication.TRUSTED_ASSET_MANIFEST_NAME,
                "trusted_asset_manifest_sha256": _sha256(trusted_manifest.read_bytes()),
                "trusted_asset_count": len(publication.CANONICAL_ASSET_NAMES),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return receipt


def _reseal_tag_validation_evidence(receipt: Path) -> None:
    root = receipt.parent
    manifest = root / "evidence.sha256"
    evidence_files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path not in {manifest, receipt}
    )
    manifest.write_text(
        "".join(
            f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}\n"
            for path in evidence_files
        ),
        encoding="utf-8",
    )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["evidence_manifest_sha256"] = _sha256(manifest.read_bytes())
    payload["trusted_asset_manifest_sha256"] = _sha256(
        (root / publication.TRUSTED_ASSET_MANIFEST_NAME).read_bytes()
    )
    receipt.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


class FakeGhRunner:
    def __init__(
        self,
        *,
        final_sha: str = FINAL_SHA,
        main_sha: str = FINAL_SHA,
        immutable_payload: dict[str, Any] | None = None,
    ) -> None:
        self.final_sha = final_sha
        self.main_sha = main_sha
        self.immutable_payload = immutable_payload
        self.tag_ref: dict[str, Any] | None = {
            "ref": f"refs/tags/{publication.EXPECTED_TAG}",
            "url": "https://api.github.test/tag-ref",
            "object": {"type": "tag", "sha": TAG_OBJECT_SHA},
        }
        self.tag_object: dict[str, Any] | None = {
            "sha": TAG_OBJECT_SHA,
            "tag": publication.EXPECTED_TAG,
            "message": "MitoOverview v0.3.0",
            "url": "https://api.github.test/tag-object",
            "object": {"type": "commit", "sha": FINAL_SHA},
        }
        self.release: dict[str, Any] | None = None
        self.remote_payloads: dict[str, bytes] = {}
        self.enumeration_pages: dict[int, list[dict[str, Any]]] | None = None
        self.fail_next_release_id_get = False
        self.immutable_after_publish = True
        self.calls: list[tuple[str, ...]] = []
        self.mutations: list[str] = []

    def _result(
        self,
        args: Sequence[str],
        payload: Any = None,
        *,
        returncode: int = 0,
        stderr: str = "",
    ) -> Any:
        stdout = "" if payload is None else json.dumps(payload)
        return publication.CommandResult(tuple(args), returncode, stdout, stderr)

    @staticmethod
    def _fields(args: Sequence[str]) -> dict[str, str]:
        fields: dict[str, str] = {}
        index = 0
        while index < len(args):
            if args[index] in {"-f", "-F"}:
                key, value = args[index + 1].split("=", 1)
                fields[key] = value
                index += 2
            else:
                index += 1
        return fields

    def _release_payload(self) -> dict[str, Any]:
        assert self.release is not None
        payload = dict(self.release)
        payload.setdefault("immutable", payload.get("draft") is False)
        payload["assets"] = [
            {
                "id": index + 100,
                "name": name,
                "size": len(content),
                "digest": f"sha256:{_sha256(content)}",
                "url": f"https://api.github.test/assets/{index + 100}",
                "browser_download_url": (
                    f"https://github.com/{REPOSITORY}/releases/download/"
                    f"{publication.EXPECTED_TAG}/{name}"
                ),
            }
            for index, (name, content) in enumerate(sorted(self.remote_payloads.items()))
        ]
        return payload

    def _enumerated_page(self, page: int) -> list[dict[str, Any]]:
        if self.enumeration_pages is not None:
            return self.enumeration_pages.get(page, [])
        return [] if self.release is None else [self._release_payload()]

    def _api(self, args: Sequence[str]) -> Any:
        endpoint = args[2]
        method = args[args.index("--method") + 1]
        fields = self._fields(args)
        prefix = f"repos/{REPOSITORY}/"
        assert endpoint.startswith(prefix)
        route = endpoint.removeprefix(prefix)

        if route == f"commits/{FINAL_SHA}" and method == "GET":
            return self._result(args, {"sha": self.final_sha})
        if route == "commits/main" and method == "GET":
            return self._result(args, {"sha": self.main_sha})
        if route == f"git/ref/tags/{publication.EXPECTED_TAG}" and method == "GET":
            if self.tag_ref is None:
                return self._result(args, returncode=1, stderr="Not Found (HTTP 404)")
            return self._result(args, self.tag_ref)
        if route.startswith("git/tags/") and method == "GET":
            expected_object = None if self.tag_ref is None else self.tag_ref["object"]["sha"]
            if route != f"git/tags/{expected_object}" or self.tag_object is None:
                return self._result(args, returncode=1, stderr="Not Found (HTTP 404)")
            return self._result(args, self.tag_object)
        if route.startswith("git/") and method != "GET":
            raise AssertionError("Publisher must never create or move a tag")
        if route == "immutable-releases" and method == "GET":
            if self.immutable_payload is None:
                return self._result(args, returncode=1, stderr="Not Found (HTTP 404)")
            return self._result(args, self.immutable_payload)
        if route == "immutable-releases" and method == "PUT":
            self.mutations.append("enable_immutable_releases")
            self.immutable_payload = {
                "enabled": True,
                "enforced_by_owner": False,
            }
            return self._result(args)
        if route.startswith("releases?per_page=100&page=") and method == "GET":
            page = int(route.rsplit("=", 1)[1])
            return self._result(args, self._enumerated_page(page))
        if route == "releases" and method == "POST":
            self.mutations.append("create_release")
            self.release = {
                "id": 7,
                "url": "https://api.github.test/releases/7",
                "html_url": (
                    f"https://github.com/{REPOSITORY}/releases/tag/"
                    f"{publication.EXPECTED_TAG}"
                ),
                "tag_name": fields["tag_name"],
                "target_commitish": fields["target_commitish"],
                "name": fields["name"],
                "draft": fields["draft"] == "true",
                "immutable": False,
                "prerelease": fields["prerelease"] == "true",
                "created_at": "2026-07-21T12:00:00Z",
                "published_at": None,
            }
            return self._result(args, self._release_payload())
        if route == "releases/7" and method == "GET":
            if self.fail_next_release_id_get:
                self.fail_next_release_id_get = False
                return self._result(args, returncode=1, stderr="temporary API failure")
            if self.release is None:
                return self._result(args, returncode=1, stderr="Not Found (HTTP 404)")
            return self._result(args, self._release_payload())
        if route == "releases/7" and method == "PATCH":
            assert self.release is not None
            self.mutations.append("publish_release")
            self.release["draft"] = False
            self.release["immutable"] = self.immutable_after_publish
            self.release["published_at"] = "2026-07-21T13:00:00Z"
            return self._result(args, self._release_payload())
        raise AssertionError(f"Unexpected fake GitHub API call: {method} {route}")

    def _release_command(self, args: Sequence[str]) -> Any:
        action = args[2]
        if action == "upload":
            path = Path(args[4])
            self.mutations.append(f"upload:{path.name}")
            if path.name in self.remote_payloads:
                raise AssertionError(f"Duplicate upload attempted for {path.name}")
            self.remote_payloads[path.name] = path.read_bytes()
            return self._result(args)
        if action == "download":
            destination = Path(args[args.index("--dir") + 1])
            pattern = args[args.index("--pattern") + 1]
            if pattern in self.remote_payloads:
                (destination / pattern).write_bytes(self.remote_payloads[pattern])
            return self._result(args)
        raise AssertionError(f"Unexpected fake gh release command: {args!r}")

    def run(self, args: Sequence[str], *, check: bool = True) -> Any:
        command = tuple(str(value) for value in args)
        self.calls.append(command)
        if command[:2] == ("gh", "api"):
            result = self._api(command)
        elif command[:2] == ("gh", "release"):
            result = self._release_command(command)
        else:
            raise AssertionError(f"Unexpected command: {command!r}")
        if check and result.returncode != 0:
            raise publication.PublicationError(result.stderr)
        return result


def _config(
    output_dir: Path,
    phase: str,
    *,
    asset_dir: Path | None = None,
) -> Any:
    selected_asset_dir = asset_dir or output_dir.parent / "assets"
    if not selected_asset_dir.exists():
        _write_assets(selected_asset_dir)
    tag_receipt = _write_tag_validation_evidence(
        output_dir.parent / "fresh-tag-validation", selected_asset_dir
    )
    return publication.PublicationConfig(
        repository=REPOSITORY,
        final_sha=FINAL_SHA,
        tag=publication.EXPECTED_TAG,
        output_directory=output_dir,
        phase=phase,
        github_actions_run_id=RUN_ID,
        tag_validation_receipt=tag_receipt,
        asset_directory=selected_asset_dir,
    )


def _prepublication_config(output_dir: Path) -> Any:
    return publication.PublicationConfig(
        repository=REPOSITORY,
        final_sha=FINAL_SHA,
        tag=publication.EXPECTED_TAG,
        output_directory=output_dir,
        phase="verify-prepublication",
        github_actions_run_id=RUN_ID,
    )


def _create_and_upload(
    tmp_path: Path, runner: FakeGhRunner
) -> tuple[Path, Path, dict[str, bytes]]:
    asset_dir = tmp_path / "assets"
    payloads = _write_assets(asset_dir)
    output_dir = tmp_path / "publication"
    publication.publish_github_release(
        _config(output_dir, "create-draft", asset_dir=asset_dir), runner
    )
    publication.publish_github_release(
        _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
    )
    return asset_dir, output_dir, payloads


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _all_strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _all_strings(item)]
    return []


def test_prepublication_receipt_is_read_only_and_precedes_release_assets(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()

    output = publication.publish_github_release(
        _prepublication_config(tmp_path / "publication"), runner
    )

    assert output.name == "github_prepublication.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["publication_state"] == "prepublication"
    assert payload["verification_state"] == "verified_prepublication_identity"
    assert payload["github_api_read_only"] is True
    assert payload["mutations_performed"] is False
    assert payload["asset_publication_verified"] is False
    assert payload["release_absent"] is True
    assert payload["git_commit"] == FINAL_SHA
    assert payload["tag_object"]["peeled_target_sha"] == FINAL_SHA
    assert payload["release"]["id"] is None
    assert runner.calls
    assert runner.mutations == []
    assert all(
        command[:2] == ("gh", "api")
        and command[command.index("--method") + 1] == "GET"
        for command in runner.calls
    )


def test_prepublication_receipt_rejects_an_existing_release_without_mutation(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    runner.release = {
        "id": 7,
        "url": "https://api.github.test/releases/7",
        "html_url": f"https://github.com/{REPOSITORY}/releases/tag/v0.3.0",
        "tag_name": publication.EXPECTED_TAG,
        "target_commitish": FINAL_SHA,
        "name": "MitoOverview v0.3.0",
        "draft": True,
        "immutable": False,
        "prerelease": False,
        "created_at": "2026-07-21T12:00:00Z",
        "published_at": None,
    }

    with pytest.raises(
        publication.PublicationError,
        match="before a GitHub release exists",
    ):
        publication.publish_github_release(
            _prepublication_config(tmp_path / "publication"), runner
        )
    assert runner.mutations == []


def test_prepublication_rejects_asset_or_tag_receipt_inputs_before_calls(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path / "publication", "create-draft")
    invalid = publication.PublicationConfig(
        repository=config.repository,
        final_sha=config.final_sha,
        tag=config.tag,
        output_directory=config.output_directory,
        phase="verify-prepublication",
        github_actions_run_id=config.github_actions_run_id,
        tag_validation_receipt=config.tag_validation_receipt,
        asset_directory=config.asset_directory,
    )
    runner = FakeGhRunner()

    with pytest.raises(publication.PublicationError, match="does not accept"):
        publication.publish_github_release(invalid, runner)
    assert runner.calls == []
    assert runner.mutations == []


def test_create_draft_requires_existing_annotated_tag_and_records_report_identity(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "publication"
    runner = FakeGhRunner()

    record_path = publication.publish_github_release(
        _config(output_dir, "create-draft"), runner
    )

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record_path.name == "github_publication.draft.json"
    assert record["release_version"] == publication.EXPECTED_TAG
    assert record["git_commit"] == FINAL_SHA
    assert record["repository"] == f"https://github.com/{REPOSITORY}"
    assert record["repository_url"] == f"https://github.com/{REPOSITORY}"
    assert record["release_tag"] == publication.EXPECTED_TAG
    assert record["github_release_url"] == (
        f"https://github.com/{REPOSITORY}/releases/tag/{publication.EXPECTED_TAG}"
    )
    assert record["github_actions_run_id"] == RUN_ID
    assert record["publication_state"] == "draft"
    assert record["tag_ref"]["object_sha"] == TAG_OBJECT_SHA
    assert record["tag_object"]["peeled_target_sha"] == FINAL_SHA
    assert record["fresh_public_tag_validation"]["verdict"] == "PASS"
    assert record["fresh_public_tag_validation"]["case_count"] == len(
        publication.REQUIRED_TAG_VALIDATION_CASES
    )
    assert record["fresh_public_tag_validation"]["trusted_asset_manifest"][
        "manifest_name"
    ] == publication.TRUSTED_ASSET_MANIFEST_NAME
    assert record["local_asset_manifest"]["assets"]
    assert record["hosting_protection"] == {
        "supported": True,
        "enabled": True,
        "reason": "queried",
        "api_payload": {"enabled": True, "enforced_by_owner": False},
        "enabled_by_publisher": True,
    }
    assert runner.mutations == ["enable_immutable_releases", "create_release"]
    assert not any("releases/tags/" in " ".join(call) for call in runner.calls)
    assert not any(call[2].endswith("git/tags") for call in runner.calls if len(call) > 2)


def test_missing_or_tampered_fresh_tag_evidence_blocks_before_github_mutation(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    config = _config(tmp_path / "publication", "create-draft")
    (config.tag_validation_receipt.parent / "logs/run.log").write_text(
        "tampered\n", encoding="utf-8"
    )

    with pytest.raises(publication.PublicationError, match="hash mismatch"):
        publication.publish_github_release(config, runner)
    assert runner.calls == []

    config.tag_validation_receipt.unlink()
    with pytest.raises(publication.PublicationError, match="receipt is required"):
        publication.publish_github_release(config, runner)
    assert runner.calls == []


def test_remote_tag_object_must_match_fresh_tag_evidence_before_mutation(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    assert runner.tag_ref is not None and runner.tag_object is not None
    runner.tag_ref["object"]["sha"] = OTHER_TAG_OBJECT_SHA
    runner.tag_object["sha"] = OTHER_TAG_OBJECT_SHA

    with pytest.raises(
        publication.PublicationError,
        match="Fresh public-tag validation tag object differs",
    ):
        publication.publish_github_release(
            _config(tmp_path / "publication", "create-draft"), runner
        )

    assert runner.mutations == []


def test_trusted_manifest_is_bound_to_fresh_evidence_and_tag_object(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    config = _config(tmp_path / "publication", "create-draft")
    trusted_path = (
        config.tag_validation_receipt.parent / publication.TRUSTED_ASSET_MANIFEST_NAME
    )
    trusted = json.loads(trusted_path.read_text(encoding="utf-8"))
    trusted["tag_object_sha"] = OTHER_TAG_OBJECT_SHA
    trusted_path.write_text(
        json.dumps(trusted, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _reseal_tag_validation_evidence(config.tag_validation_receipt)

    with pytest.raises(
        publication.PublicationError,
        match="Trusted release-asset manifest mismatch for tag_object_sha",
    ):
        publication.publish_github_release(config, runner)
    assert runner.calls == []
    assert runner.mutations == []


@pytest.mark.parametrize("tag_problem", ["missing", "lightweight"])
def test_missing_or_lightweight_tag_blocks_draft_without_mutation(
    tmp_path: Path, tag_problem: str
) -> None:
    runner = FakeGhRunner()
    if tag_problem == "missing":
        runner.tag_ref = None
    else:
        assert runner.tag_ref is not None
        runner.tag_ref["object"]["type"] = "commit"

    with pytest.raises(publication.PublicationError, match="annotated tag"):
        publication.publish_github_release(
            _config(tmp_path / "publication", "create-draft"), runner
        )
    assert runner.mutations == []


def test_draft_lookup_enumerates_authenticated_release_pages(tmp_path: Path) -> None:
    runner = FakeGhRunner()
    filler = [
        {"id": index, "tag_name": f"v0.0.{index}", "draft": True}
        for index in range(100)
    ]
    target = {
        "id": 7,
        "url": "https://api.github.test/releases/7",
        "html_url": f"https://github.com/{REPOSITORY}/releases/tag/v0.3.0",
        "tag_name": publication.EXPECTED_TAG,
        "target_commitish": FINAL_SHA,
        "name": "existing",
        "draft": True,
        "immutable": False,
        "prerelease": False,
        "created_at": "2026-07-21T12:00:00Z",
        "published_at": None,
        "assets": [],
    }
    runner.release = dict(target)
    runner.enumeration_pages = {1: filler, 2: [target]}

    record = publication.publish_github_release(
        _config(tmp_path / "publication", "create-draft"), runner
    )

    assert record.exists()
    assert runner.mutations == ["enable_immutable_releases"]
    enumerations = [call[2] for call in runner.calls if "releases?per_page" in call[2]]
    assert any("page=1" in endpoint for endpoint in enumerations)
    assert any("page=2" in endpoint for endpoint in enumerations)
    assert not any("releases/tags/" in endpoint for endpoint in enumerations)


def test_create_draft_transition_receipt_survives_followup_failure_and_resumes(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "publication"
    runner = FakeGhRunner()
    runner.fail_next_release_id_get = True

    with pytest.raises(publication.PublicationError, match="temporary API failure"):
        publication.publish_github_release(_config(output_dir, "create-draft"), runner)

    receipt = output_dir / "github_publication.draft.json"
    assert receipt.exists()
    transition = json.loads(receipt.read_text(encoding="utf-8"))
    assert transition["verification_state"] == "draft_transition_recorded"
    assert runner.mutations.count("create_release") == 1

    publication.publish_github_release(_config(output_dir, "create-draft"), runner)
    resumed = json.loads(receipt.read_text(encoding="utf-8"))
    assert resumed["verification_state"] == "verified_empty_draft"
    assert runner.mutations.count("create_release") == 1


def test_existing_matching_draft_is_reused_without_release_mutation(tmp_path: Path) -> None:
    runner = FakeGhRunner()
    runner.release = {
        "id": 7,
        "url": "https://api.github.test/releases/7",
        "html_url": f"https://github.com/{REPOSITORY}/releases/tag/v0.3.0",
        "tag_name": publication.EXPECTED_TAG,
        "target_commitish": FINAL_SHA,
        "name": "existing",
        "draft": True,
        "prerelease": False,
        "created_at": "2026-07-21T12:00:00Z",
        "published_at": None,
    }

    publication.publish_github_release(
        _config(tmp_path / "publication", "create-draft"), runner
    )

    assert runner.mutations == ["enable_immutable_releases"]


def test_upload_resumes_partial_assets_and_redownloads_existing_assets(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    asset_dir = tmp_path / "assets"
    payloads = _write_assets(asset_dir)
    output_dir = tmp_path / "publication"
    publication.publish_github_release(_config(output_dir, "create-draft"), runner)
    existing = sorted(payloads)[:4]
    runner.remote_payloads.update({name: payloads[name] for name in existing})

    publication.publish_github_release(
        _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
    )

    uploaded = {item.split(":", 1)[1] for item in runner.mutations if item.startswith("upload:")}
    assert uploaded == set(payloads) - set(existing)
    assert not uploaded.intersection(existing)
    download_patterns = {
        call[call.index("--pattern") + 1]
        for call in runner.calls
        if call[:3] == ("gh", "release", "download")
    }
    assert set(existing).issubset(download_patterns)
    record = json.loads(
        (output_dir / "github_publication.draft.json").read_text(encoding="utf-8")
    )
    assert record["verification_state"] == "verified_draft_assets"
    assert record["asset_upload_verified"] is True
    assert set(record["uploaded_asset_names"]) == set(payloads)
    assert {item["name"] for item in record["remote_assets"]} == set(payloads)


@pytest.mark.parametrize("remote_problem", ["unexpected", "hash", "size"])
def test_unexpected_or_mismatched_remote_assets_fail_before_upload(
    tmp_path: Path, remote_problem: str
) -> None:
    runner = FakeGhRunner()
    asset_dir = tmp_path / "assets"
    payloads = _write_assets(asset_dir)
    output_dir = tmp_path / "publication"
    publication.publish_github_release(_config(output_dir, "create-draft"), runner)
    if remote_problem == "unexpected":
        runner.remote_payloads["unexpected.bin"] = b"unexpected\n"
    else:
        name = next(iter(sorted(payloads)))
        runner.remote_payloads[name] = (
            payloads[name] + b"x"
            if remote_problem == "size"
            else bytes([payloads[name][0] ^ 1]) + payloads[name][1:]
        )

    with pytest.raises(publication.PublicationError, match="unexpected|mismatch"):
        publication.publish_github_release(
            _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
        )
    assert not any(item.startswith("upload:") for item in runner.mutations)


@pytest.mark.parametrize("inventory_problem", ["missing", "extra", "renamed"])
def test_canonical_asset_inventory_is_enforced_before_github_calls(
    tmp_path: Path, inventory_problem: str
) -> None:
    asset_dir = tmp_path / "assets"
    payloads = _write_assets(asset_dir)
    config = _config(
        tmp_path / "publication", "upload-verify", asset_dir=asset_dir
    )
    if inventory_problem == "missing":
        (asset_dir / "RELEASE_NOTES_v0.3.0.md").unlink()
    elif inventory_problem == "extra":
        (asset_dir / "extra.txt").write_text("extra\n", encoding="ascii")
    else:
        source = asset_dir / "mito-overview-v0.3.0-environment.txt"
        source.rename(asset_dir / "environment.txt")
    runner = FakeGhRunner()

    with pytest.raises(publication.PublicationError, match="Canonical v0.3.0"):
        publication.publish_github_release(
            config,
            runner,
        )
    assert runner.calls == []
    assert set(payloads) == publication.CANONICAL_ASSET_NAMES


@pytest.mark.parametrize(
    "target",
    sorted(publication.CANONICAL_ASSET_NAMES - {"SHA256SUMS"}),
)
def test_trusted_manifest_blocks_each_asset_substitution_before_github_calls(
    tmp_path: Path, target: str
) -> None:
    asset_dir = tmp_path / "assets"
    _write_assets(asset_dir)
    config = _config(
        tmp_path / "publication", "create-draft", asset_dir=asset_dir
    )
    path = asset_dir / target
    path.write_bytes(path.read_bytes() + b"substituted\n")
    _rewrite_sha256sums(asset_dir)
    runner = FakeGhRunner()

    with pytest.raises(
        publication.PublicationError,
        match=rf"Trusted release-asset hash or size mismatch for {target}",
    ):
        publication.publish_github_release(config, runner)
    assert runner.calls == []
    assert runner.mutations == []


def test_exact_annotated_tag_object_is_bound_across_phases(tmp_path: Path) -> None:
    runner = FakeGhRunner()
    asset_dir = tmp_path / "assets"
    _write_assets(asset_dir)
    output_dir = tmp_path / "publication"
    publication.publish_github_release(_config(output_dir, "create-draft"), runner)
    assert runner.tag_ref is not None and runner.tag_object is not None
    runner.tag_ref["object"]["sha"] = OTHER_TAG_OBJECT_SHA
    runner.tag_object["sha"] = OTHER_TAG_OBJECT_SHA

    with pytest.raises(publication.PublicationError, match="tag object drifted"):
        publication.publish_github_release(
            _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
        )
    assert not any(item.startswith("upload:") for item in runner.mutations)


def test_publisher_enables_and_records_immutable_release_protection(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    record_path = publication.publish_github_release(
        _config(tmp_path / "publication", "create-draft"), runner
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))

    assert record["hosting_protection"]["supported"] is True
    assert record["hosting_protection"]["enabled"] is True
    assert record["hosting_protection"]["enabled_by_publisher"] is True
    assert "release_attestations" not in record
    assert runner.mutations.count("enable_immutable_releases") == 1


def test_publish_validates_then_patches_once_and_writes_report_ready_receipt(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner(immutable_payload={"enabled": True})
    asset_dir, output_dir, payloads = _create_and_upload(tmp_path, runner)

    record_path = publication.publish_github_release(
        _config(output_dir, "publish", asset_dir=asset_dir), runner
    )

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["verification_state"] == "verified_published"
    assert record["verified"] is True
    assert record["publication_state"] == "published"
    assert record["published_utc"] == "2026-07-21T13:00:00Z"
    assert record["github_actions_run_id"] == RUN_ID
    assert record["tag_ref"]["object_sha"] == TAG_OBJECT_SHA
    assert record["tag_object"]["tag_object_sha"] == TAG_OBJECT_SHA
    assert record["post_publish_verification"]["complete"] is True
    assert {item["name"] for item in record["remote_assets"]} == set(payloads)
    assert "release_attestations" not in record
    assert runner.mutations.count("publish_release") == 1


def test_published_transition_receipt_survives_query_failure_and_resumes_without_patch(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    asset_dir, output_dir, _ = _create_and_upload(tmp_path, runner)
    runner.fail_next_release_id_get = True

    with pytest.raises(publication.PublicationError, match="temporary API failure"):
        publication.publish_github_release(
            _config(output_dir, "publish", asset_dir=asset_dir), runner
        )

    final_path = output_dir / "github_publication.json"
    assert final_path.exists()
    transition = json.loads(final_path.read_text(encoding="utf-8"))
    assert transition["publication_state"] == "published"
    assert transition["verification_state"] == "published_transition_recorded"
    assert transition["post_publish_verification"]["complete"] is False
    assert runner.mutations.count("publish_release") == 1

    publication.publish_github_release(
        _config(output_dir, "publish", asset_dir=asset_dir), runner
    )
    final = json.loads(final_path.read_text(encoding="utf-8"))
    assert final["verification_state"] == "verified_published"
    assert runner.mutations.count("publish_release") == 1


def test_published_transition_receipt_survives_delayed_immutable_state(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    asset_dir, output_dir, _ = _create_and_upload(tmp_path, runner)
    runner.immutable_after_publish = False

    with pytest.raises(publication.PublicationError, match="immutable=true"):
        publication.publish_github_release(
            _config(output_dir, "publish", asset_dir=asset_dir), runner
        )

    final_path = output_dir / "github_publication.json"
    transition = json.loads(final_path.read_text(encoding="utf-8"))
    assert transition["verification_state"] == "published_transition_recorded"
    assert transition["release"]["immutable"] is False
    assert runner.mutations.count("publish_release") == 1

    assert runner.release is not None
    runner.release["immutable"] = True
    runner.immutable_after_publish = True
    publication.publish_github_release(
        _config(output_dir, "publish", asset_dir=asset_dir), runner
    )
    final = json.loads(final_path.read_text(encoding="utf-8"))
    assert final["release"]["immutable"] is True
    assert final["verification_state"] == "verified_published"
    assert runner.mutations.count("publish_release") == 1


def test_upload_and_publish_are_idempotent_after_success(tmp_path: Path) -> None:
    runner = FakeGhRunner()
    asset_dir, output_dir, _ = _create_and_upload(tmp_path, runner)
    uploads = list(item for item in runner.mutations if item.startswith("upload:"))

    publication.publish_github_release(
        _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
    )
    assert [item for item in runner.mutations if item.startswith("upload:")] == uploads
    publication.publish_github_release(
        _config(output_dir, "publish", asset_dir=asset_dir), runner
    )
    publication.publish_github_release(
        _config(output_dir, "publish", asset_dir=asset_dir), runner
    )
    assert runner.mutations.count("publish_release") == 1


def test_upload_after_publication_rejects_changed_local_bytes(tmp_path: Path) -> None:
    runner = FakeGhRunner()
    asset_dir, output_dir, payloads = _create_and_upload(tmp_path, runner)
    publication.publish_github_release(
        _config(output_dir, "publish", asset_dir=asset_dir), runner
    )
    target = "RELEASE_NOTES_v0.3.0.md"
    changed = payloads[target] + b"changed\n"
    (asset_dir / target).write_bytes(changed)
    manifest_payloads = {
        name: (asset_dir / name).read_bytes()
        for name in publication.CANONICAL_ASSET_NAMES
        if name != "SHA256SUMS"
    }
    manifest = "".join(
        f"{_sha256(manifest_payloads[name])}  {name}\n"
        for name in sorted(manifest_payloads)
    ).encode("ascii")
    (asset_dir / "SHA256SUMS").write_bytes(manifest)

    with pytest.raises(publication.PublicationError, match="Trusted release-asset"):
        publication.publish_github_release(
            _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
        )


def test_receipts_contain_no_absolute_local_paths(tmp_path: Path) -> None:
    runner = FakeGhRunner()
    asset_dir, output_dir, _ = _create_and_upload(tmp_path, runner)
    publication.publish_github_release(
        _config(output_dir, "publish", asset_dir=asset_dir), runner
    )

    for name in ("github_publication.draft.json", "github_publication.json"):
        record = json.loads((output_dir / name).read_text(encoding="utf-8"))
        strings = _all_strings(record)
        assert str(tmp_path) not in json.dumps(record)
        assert all(not text.startswith("/private/") for text in strings)
        assert all(not text.startswith("/Users/") for text in strings)
        assert all("path" not in key.lower() for key in record if key != "repository_url")


def test_main_and_tag_drift_fail_before_remote_mutation(tmp_path: Path) -> None:
    for problem in ("main", "peel"):
        runner = FakeGhRunner(main_sha=OTHER_SHA if problem == "main" else FINAL_SHA)
        if problem == "peel":
            assert runner.tag_object is not None
            runner.tag_object["object"]["sha"] = OTHER_SHA
        with pytest.raises(publication.PublicationError, match="drift"):
            publication.publish_github_release(
                _config(tmp_path / problem / "publication", "create-draft"), runner
            )
        assert runner.mutations == []


def test_cli_requires_phase_assets_run_id_and_tag_validation_receipt() -> None:
    parser = publication._parser()
    base = [REPOSITORY, FINAL_SHA, publication.EXPECTED_TAG, "output"]
    with pytest.raises(SystemExit):
        parser.parse_args([*base, "--create-draft"])
    common = [
        *base,
        "--github-actions-run-id",
        str(RUN_ID),
        "--tag-validation-receipt",
        "fresh-tag-validation/fresh_public_tag_validation.json",
        "--asset-directory",
        "assets",
    ]
    assert parser.parse_args([*common, "--create-draft"]).phase == "create-draft"
    upload = parser.parse_args([*common, "--upload-verify"])
    assert upload.asset_directory == Path("assets")
    publish = parser.parse_args([*common, "--publish"])
    assert publish.phase == "publish"
    prepublication = parser.parse_args(
        [
            *base,
            "--github-actions-run-id",
            str(RUN_ID),
            "--verify-prepublication",
        ]
    )
    assert prepublication.phase == "verify-prepublication"
    assert prepublication.tag_validation_receipt is None
    assert prepublication.asset_directory is None
