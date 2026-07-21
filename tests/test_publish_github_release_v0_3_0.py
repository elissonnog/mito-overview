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
REPOSITORY = "elissonnog/mito-overview"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_assets(root: Path) -> dict[str, bytes]:
    root.mkdir(parents=True)
    payloads = {
        "mito_overview-0.3.0-py3-none-any.whl": b"wheel-v0.3.0\n",
        "mito_overview-0.3.0.tar.gz": b"sdist-v0.3.0\n",
        "mito-overview-v0.3.0-validation.zip": b"validation-v0.3.0\n",
    }
    for name, payload in payloads.items():
        (root / name).write_bytes(payload)
    manifest = "".join(
        f"{_sha256(payloads[name])}  {name}\n" for name in sorted(payloads)
    ).encode("ascii")
    (root / "SHA256SUMS").write_bytes(manifest)
    return {**payloads, "SHA256SUMS": manifest}


class FakeGhRunner:
    def __init__(
        self,
        *,
        final_sha: str = FINAL_SHA,
        main_sha: str = FINAL_SHA,
        immutable_enables: bool = True,
    ) -> None:
        self.final_sha = final_sha
        self.main_sha = main_sha
        self.immutable_enables = immutable_enables
        self.immutable = False
        self.immutable_payload: dict[str, Any] = {"enabled": True}
        self.tag_ref: dict[str, Any] | None = None
        self.tag_object: dict[str, Any] | None = None
        self.release: dict[str, Any] | None = None
        self.remote_payloads: dict[str, bytes] = {}
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

    def _fields(self, args: Sequence[str]) -> dict[str, str]:
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
        payload["assets"] = [
            {
                "id": index + 100,
                "name": name,
                "size": len(content),
                "digest": f"sha256:{_sha256(content)}",
                "url": f"https://api.github.test/assets/{index + 100}",
                "browser_download_url": f"https://github.test/download/{name}",
            }
            for index, (name, content) in enumerate(sorted(self.remote_payloads.items()))
        ]
        return payload

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
                return self._result(
                    args, returncode=1, stderr="gh: Not Found (HTTP 404)"
                )
            return self._result(args, self.tag_ref)
        if route == "git/tags" and method == "POST":
            self.mutations.append("create_tag_object")
            self.tag_object = {
                "sha": TAG_OBJECT_SHA,
                "tag": fields["tag"],
                "message": fields["message"],
                "url": "https://api.github.test/tag-object",
                "object": {"type": fields["type"], "sha": fields["object"]},
            }
            return self._result(args, self.tag_object)
        if route == "git/refs" and method == "POST":
            self.mutations.append("create_tag_ref")
            self.tag_ref = {
                "ref": fields["ref"],
                "url": "https://api.github.test/tag-ref",
                "object": {"type": "tag", "sha": fields["sha"]},
            }
            return self._result(args, self.tag_ref)
        if route == f"git/tags/{TAG_OBJECT_SHA}" and method == "GET":
            assert self.tag_object is not None
            return self._result(args, self.tag_object)
        if route == "immutable-releases" and method == "GET":
            if not self.immutable:
                return self._result(
                    args, returncode=1, stderr="gh: Not Found (HTTP 404)"
                )
            return self._result(args, self.immutable_payload)
        if route == "immutable-releases" and method == "PUT":
            self.mutations.append("enable_immutable")
            if self.immutable_enables:
                self.immutable = True
                self.immutable_payload = {"enabled": True}
            return self._result(args, {})
        if route == f"releases/tags/{publication.EXPECTED_TAG}" and method == "GET":
            if self.release is None:
                return self._result(
                    args, returncode=1, stderr="gh: Not Found (HTTP 404)"
                )
            return self._result(args, self._release_payload())
        if route == "releases" and method == "POST":
            self.mutations.append("create_release")
            self.release = {
                "id": 7,
                "url": "https://api.github.test/releases/7",
                "html_url": "https://github.test/releases/v0.3.0",
                "tag_name": fields["tag_name"],
                "target_commitish": fields["target_commitish"],
                "name": fields["name"],
                "draft": fields["draft"] == "true",
                "prerelease": fields["prerelease"] == "true",
                "created_at": "2026-07-21T12:00:00Z",
                "published_at": None,
            }
            return self._result(args, self._release_payload())
        if route == "releases/7" and method == "GET":
            if self.release is None:
                return self._result(
                    args, returncode=1, stderr="gh: Not Found (HTTP 404)"
                )
            return self._result(args, self._release_payload())
        if route == "releases/7" and method == "PATCH":
            assert self.release is not None
            self.mutations.append("publish_release")
            self.release["draft"] = False
            self.release["published_at"] = "2026-07-21T13:00:00Z"
            return self._result(args, self._release_payload())
        raise AssertionError(f"Unexpected fake GitHub API call: {method} {route}")

    def _release_command(self, args: Sequence[str]) -> Any:
        action = args[2]
        if action == "upload":
            path = Path(args[4])
            self.mutations.append(f"upload:{path.name}")
            assert path.name not in self.remote_payloads
            self.remote_payloads[path.name] = path.read_bytes()
            return self._result(args)
        if action == "download":
            destination = Path(args[args.index("--dir") + 1])
            for name, payload in self.remote_payloads.items():
                (destination / name).write_bytes(payload)
            return self._result(args)
        if action == "verify":
            return self._result(args, {"verified": True, "tag": publication.EXPECTED_TAG})
        if action == "verify-asset":
            path = Path(args[4])
            return self._result(
                args, {"verified": True, "name": path.name, "sha256": _sha256(path.read_bytes())}
            )
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
    return publication.PublicationConfig(
        repository=REPOSITORY,
        final_sha=FINAL_SHA,
        tag=publication.EXPECTED_TAG,
        output_directory=output_dir,
        phase=phase,
        asset_directory=asset_dir,
    )


def _create_and_upload(
    tmp_path: Path, runner: FakeGhRunner
) -> tuple[Path, Path, dict[str, bytes]]:
    asset_dir = tmp_path / "assets"
    payloads = _write_assets(asset_dir)
    output_dir = tmp_path / "publication"
    publication.publish_github_release(
        _config(output_dir, "create-draft"), runner
    )
    publication.publish_github_release(
        _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
    )
    return asset_dir, output_dir, payloads


def test_create_draft_requires_no_assets_and_records_empty_remote_release(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "publication"
    runner = FakeGhRunner()

    record_path = publication.publish_github_release(
        _config(output_dir, "create-draft"), runner
    )

    assert record_path.name == "github_publication.draft.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["phase"] == "create-draft"
    assert record["verification_state"] == "verified_empty_draft"
    assert record["verified"] is True
    assert record["asset_upload_verified"] is False
    assert record["final_sha"] == FINAL_SHA
    assert record["tag_object"]["peeled_target_sha"] == FINAL_SHA
    assert record["immutable_releases"]["enabled"] is True
    assert record["release"]["draft"] is True
    assert record["release"]["published_at"] is None
    assert record["remote_assets"] == []
    assert not (output_dir / "github_publication.json").exists()
    assert runner.release is not None and runner.release["draft"] is True
    assert not any(mutation.startswith("upload:") for mutation in runner.mutations)
    assert "publish_release" not in runner.mutations
    assert all(";" not in argument for call in runner.calls for argument in call)


def test_create_draft_enables_explicitly_disabled_immutable_releases(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    runner.immutable = True
    runner.immutable_payload = {"enabled": False}

    publication.publish_github_release(
        _config(tmp_path / "publication", "create-draft"), runner
    )

    assert runner.mutations[0] == "enable_immutable"
    assert runner.mutations.count("enable_immutable") == 1
    assert "create_tag_object" in runner.mutations


def test_upload_verify_requires_empty_draft_and_atomically_upgrades_receipt(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "assets"
    expected_payloads = _write_assets(asset_dir)
    output_dir = tmp_path / "publication"
    runner = FakeGhRunner()
    publication.publish_github_release(_config(output_dir, "create-draft"), runner)

    record_path = publication.publish_github_release(
        _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
    )

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record_path.name == "github_publication.draft.json"
    assert record["phase"] == "upload-verify"
    assert record["verification_state"] == "verified_draft_assets"
    assert record["asset_upload_verified"] is True
    assert {entry["name"] for entry in record["remote_assets"]} == set(
        expected_payloads
    )
    assert record["redownload_verification"]["manifest_byte_identical"] is True
    assert runner.release is not None and runner.release["draft"] is True
    assert "publish_release" not in runner.mutations
    assert runner.mutations.count("create_tag_ref") == 1
    assert runner.mutations.count("create_tag_object") == 1


def test_publish_mode_publishes_only_upload_verified_draft_and_attests_assets(
    tmp_path: Path,
) -> None:
    runner = FakeGhRunner()
    asset_dir, output_dir, expected_payloads = _create_and_upload(tmp_path, runner)

    record_path = publication.publish_github_release(
        _config(output_dir, "publish", asset_dir=asset_dir), runner
    )

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record_path.name == "github_publication.json"
    assert record["phase"] == "publish"
    assert record["verification_state"] == "verified_published"
    assert record["published_at"] == "2026-07-21T13:00:00Z"
    assert record["release"]["draft"] is False
    assert record["immutable_releases"]["enabled"] is True
    assert record["tag_object"]["peeled_target_sha"] == FINAL_SHA
    assert record["release_attestations"]["release"]["verified"] is True
    assert {
        item["name"] for item in record["release_attestations"]["assets"]
    } == set(expected_payloads)
    assert runner.mutations.count("publish_release") == 1
    assert runner.release is not None and runner.release["draft"] is False


def test_phase_order_blocks_upload_without_draft_and_publish_before_upload(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "assets"
    _write_assets(asset_dir)
    output_dir = tmp_path / "publication"
    runner = FakeGhRunner()

    with pytest.raises(publication.PublicationError, match="requires github_publication"):
        publication.publish_github_release(
            _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
        )
    assert runner.calls == []

    publication.publish_github_release(_config(output_dir, "create-draft"), runner)
    mutations_before = list(runner.mutations)
    with pytest.raises(publication.PublicationError, match="upload-verify"):
        publication.publish_github_release(
            _config(output_dir, "publish", asset_dir=asset_dir), runner
        )
    assert runner.mutations == mutations_before
    assert runner.release is not None and runner.release["draft"] is True


def test_remote_commit_sha_drift_fails_before_any_mutation(tmp_path: Path) -> None:
    runner = FakeGhRunner(final_sha=OTHER_SHA)

    with pytest.raises(publication.PublicationError, match="Remote commit drift"):
        publication.publish_github_release(
            _config(tmp_path / "publication", "create-draft"), runner
        )

    assert runner.mutations == []


def test_remote_main_sha_drift_fails_before_any_mutation(tmp_path: Path) -> None:
    runner = FakeGhRunner(main_sha=OTHER_SHA)

    with pytest.raises(publication.PublicationError, match="Remote main drift"):
        publication.publish_github_release(
            _config(tmp_path / "publication", "create-draft"), runner
        )

    assert runner.mutations == []


def test_annotated_tag_peel_drift_blocks_publication_without_mutation(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "assets"
    _write_assets(asset_dir)
    output_dir = tmp_path / "publication"
    runner = FakeGhRunner()
    publication.publish_github_release(_config(output_dir, "create-draft"), runner)
    assert runner.tag_object is not None
    runner.tag_object["object"]["sha"] = OTHER_SHA
    mutations_before = list(runner.mutations)

    with pytest.raises(publication.PublicationError, match="tag peel drift"):
        publication.publish_github_release(
            _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
        )

    assert runner.mutations == mutations_before
    assert runner.release is not None and runner.release["draft"] is True


@pytest.mark.parametrize("inventory_error", ["extra", "missing"])
def test_extra_or_missing_asset_fails_before_gh(
    tmp_path: Path, inventory_error: str
) -> None:
    asset_dir = tmp_path / "assets"
    payloads = _write_assets(asset_dir)
    if inventory_error == "extra":
        (asset_dir / "unlisted.bin").write_bytes(b"dirty\n")
    else:
        victim = next(name for name in payloads if name != "SHA256SUMS")
        (asset_dir / victim).unlink()
    runner = FakeGhRunner()
    output_dir = tmp_path / "publication"
    publication.publish_github_release(_config(output_dir, "create-draft"), runner)
    calls_before = list(runner.calls)
    mutations_before = list(runner.mutations)

    with pytest.raises(publication.PublicationError, match="inventory mismatch"):
        publication.publish_github_release(
            _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
        )

    assert runner.calls == calls_before
    assert runner.mutations == mutations_before


def test_symlink_and_nested_directory_are_refused_before_gh(tmp_path: Path) -> None:
    for violation in ("symlink", "nested"):
        case = tmp_path / violation
        asset_dir = case / "assets"
        _write_assets(asset_dir)
        if violation == "symlink":
            target = case / "outside.bin"
            target.write_bytes(b"outside\n")
            (asset_dir / "linked.bin").symlink_to(target)
        else:
            (asset_dir / "nested").mkdir()
        runner = FakeGhRunner()
        output_dir = case / "publication"
        publication.publish_github_release(
            _config(output_dir, "create-draft"), runner
        )
        calls_before = list(runner.calls)
        with pytest.raises(publication.PublicationError):
            publication.publish_github_release(
                _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
            )
        assert runner.calls == calls_before


def test_immutable_disabled_blocks_release_creation(tmp_path: Path) -> None:
    runner = FakeGhRunner(immutable_enables=False)

    with pytest.raises(publication.PublicationError, match="immutable releases"):
        publication.publish_github_release(
            _config(tmp_path / "publication", "create-draft"), runner
        )

    assert runner.tag_ref is None
    assert runner.release is None
    assert "create_release" not in runner.mutations


def test_malformed_immutable_state_blocks_tag_and_release_creation(tmp_path: Path) -> None:
    runner = FakeGhRunner()
    runner.immutable = True
    runner.immutable_payload = {}

    with pytest.raises(publication.PublicationError, match="immutable releases"):
        publication.publish_github_release(
            _config(tmp_path / "publication", "create-draft"), runner
        )

    assert runner.tag_ref is None
    assert runner.release is None
    assert runner.mutations == []


def test_existing_tag_and_release_are_never_mutated(tmp_path: Path) -> None:
    runner = FakeGhRunner()
    runner.tag_object = {
        "sha": TAG_OBJECT_SHA,
        "tag": publication.EXPECTED_TAG,
        "message": "existing",
        "url": "https://api.github.test/tag-object",
        "object": {"type": "commit", "sha": FINAL_SHA},
    }
    runner.tag_ref = {
        "ref": f"refs/tags/{publication.EXPECTED_TAG}",
        "url": "https://api.github.test/tag-ref",
        "object": {"type": "tag", "sha": TAG_OBJECT_SHA},
    }
    runner.release = {
        "id": 7,
        "url": "https://api.github.test/releases/7",
        "html_url": "https://github.test/releases/v0.3.0",
        "tag_name": publication.EXPECTED_TAG,
        "target_commitish": FINAL_SHA,
        "name": "Existing release",
        "draft": False,
        "prerelease": False,
        "created_at": "2026-07-20T12:00:00Z",
        "published_at": "2026-07-20T13:00:00Z",
    }

    with pytest.raises(publication.PublicationError, match="pre-existing"):
        publication.publish_github_release(
            _config(tmp_path / "publication", "create-draft"), runner
        )

    assert runner.mutations == []


def test_published_release_cannot_be_republished(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets"
    _write_assets(asset_dir)
    output_dir = tmp_path / "publication"
    runner = FakeGhRunner()
    publication.publish_github_release(_config(output_dir, "create-draft"), runner)
    publication.publish_github_release(
        _config(output_dir, "upload-verify", asset_dir=asset_dir), runner
    )
    assert runner.release is not None
    runner.release["draft"] = False
    runner.release["published_at"] = "2026-07-21T12:30:00Z"
    mutations_before = list(runner.mutations)

    with pytest.raises(publication.PublicationError, match="unpublished draft"):
        publication.publish_github_release(
            _config(output_dir, "publish", asset_dir=asset_dir), runner
        )

    assert runner.mutations == mutations_before
    assert runner.mutations.count("publish_release") == 0


def test_cli_requires_one_explicit_phase_and_assets_for_later_phases() -> None:
    parser = publication._parser()
    base = [REPOSITORY, FINAL_SHA, publication.EXPECTED_TAG, "output"]
    with pytest.raises(SystemExit):
        parser.parse_args(base)
    assert parser.parse_args([*base, "--create-draft"]).phase == "create-draft"
    upload = parser.parse_args(
        [*base, "--upload-verify", "--asset-directory", "assets"]
    )
    assert upload.phase == "upload-verify"
    assert upload.asset_directory == Path("assets")
    publish = parser.parse_args(
        [*base, "--publish", "--asset-directory", "assets"]
    )
    assert publish.phase == "publish"
