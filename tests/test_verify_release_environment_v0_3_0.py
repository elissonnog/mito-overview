from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_environment_v0.3.0.py"
SPEC = importlib.util.spec_from_file_location("verify_release_environment", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)

HASH_A = "a" * 64
HASH_B = "b" * 64
COMMIT = "c" * 40
TREE = "d" * 40


def manifest(package: str, digest: str = HASH_A) -> str:
    return (
        "# platform: linux-64\n"
        "@EXPLICIT\n"
        f"https://conda.anaconda.org/conda-forge/linux-64/{package}#{digest}\n"
    )


def test_artifact_urls_require_sha256_fragments() -> None:
    text = (
        "@EXPLICIT\n"
        "https://conda.anaconda.org/conda-forge/linux-64/python-3.12.13-0.conda\n"
    )
    with pytest.raises(ValueError, match="unapproved or unhashed"):
        verifier.artifact_urls(
            text, label="fixture", expected_platform="linux-64"
        )


def test_artifact_urls_reject_non_https_records() -> None:
    text = (
        "@EXPLICIT\n"
        f"https://conda.anaconda.org/conda-forge/linux-64/pkg-1.0-0.conda#{HASH_A}\n"
        f"file:///private/tmp/substituted-1.0-0.conda#{HASH_A}\n"
    )
    with pytest.raises(ValueError, match="unapproved or unhashed"):
        verifier.artifact_urls(
            text, label="fixture", expected_platform="linux-64"
        )


@pytest.mark.parametrize(
    "url",
    (
        f"https://conda.anaconda.org:443/conda-forge/linux-64/pkg-1.0-0.conda#{HASH_A}",
        f"https://conda.anaconda.org/conda-forge/linux-64/../osx-arm64/pkg-1.0-0.conda#{HASH_A}",
        f"https://conda.anaconda.org/conda-forge/linux-64/%2e%2e/pkg-1.0-0.conda#{HASH_A}",
        f"https://conda.anaconda.org/conda-forge/linux-64/subdir/pkg-1.0-0.conda#{HASH_A}",
    ),
)
def test_artifact_urls_reject_noncanonical_paths(url: str) -> None:
    with pytest.raises(ValueError, match="unapproved or unhashed"):
        verifier.artifact_urls(
            f"@EXPLICIT\n{url}\n",
            label="fixture",
            expected_platform="linux-64",
        )


def test_artifact_urls_reject_wrong_platform_and_duplicate_records() -> None:
    wrong_platform = (
        "@EXPLICIT\n"
        f"https://conda.anaconda.org/conda-forge/osx-arm64/pkg-1.0-0.conda#{HASH_A}\n"
    )
    with pytest.raises(ValueError, match="unapproved or unhashed"):
        verifier.artifact_urls(
            wrong_platform, label="fixture", expected_platform="linux-64"
        )

    record = (
        f"https://conda.anaconda.org/conda-forge/linux-64/pkg-1.0-0.conda#{HASH_A}"
    )
    with pytest.raises(ValueError, match="duplicate"):
        verifier.artifact_urls(
            f"@EXPLICIT\n{record}\n{record}\n",
            label="fixture",
            expected_platform="linux-64",
        )


def test_verify_rejects_same_version_from_different_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    locks = repo / "locks"
    locks.mkdir(parents=True)
    (locks / "environment-linux-64.explicit.txt").write_text(
        manifest("python-3.12.13-approved_0.conda"), encoding="utf-8"
    )
    prefix = tmp_path / "conda-prefix"
    (prefix / "conda-meta").mkdir(parents=True)

    monkeypatch.setattr(verifier, "platform_id", lambda: "linux-64")
    monkeypatch.setattr(verifier.sys, "prefix", str(prefix))
    monkeypatch.setattr(
        verifier.sys, "version_info", (3, 12, 13, "final", 0)
    )
    monkeypatch.setattr(
        verifier.platform, "python_version", lambda: "3.12.13"
    )
    monkeypatch.setattr(verifier.shutil, "which", lambda _: "/fixture/conda")
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "git":
            stdout = TREE + "\n" if command[-1] == "HEAD^{tree}" else COMMIT + "\n"
            if command[-1] == "--untracked-files=all":
                stdout = ""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=manifest("python-3.12.13-other_0.conda", HASH_B),
            stderr="",
        )

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="do not match"):
        verifier.verify(repo, Path(sys.executable), COMMIT)


def test_verify_accepts_exact_url_and_hash_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    locks = repo / "locks"
    locks.mkdir(parents=True)
    locked = manifest("python-3.12.13-approved_0.conda")
    lock_path = locks / "environment-linux-64.explicit.txt"
    lock_path.write_text(locked, encoding="utf-8")
    prefix = tmp_path / "conda-prefix"
    (prefix / "conda-meta").mkdir(parents=True)

    monkeypatch.setattr(verifier, "platform_id", lambda: "linux-64")
    monkeypatch.setattr(verifier.sys, "prefix", str(prefix))
    monkeypatch.setattr(
        verifier.sys, "version_info", (3, 12, 13, "final", 0)
    )
    monkeypatch.setattr(
        verifier.platform, "python_version", lambda: "3.12.13"
    )
    monkeypatch.setattr(verifier.shutil, "which", lambda _: "/fixture/conda")
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "git":
            stdout = TREE + "\n" if command[-1] == "HEAD^{tree}" else COMMIT + "\n"
            if command[-1] == "--untracked-files=all":
                stdout = ""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        return subprocess.CompletedProcess(command, 0, stdout=locked, stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    record = verifier.verify(repo, Path(sys.executable), COMMIT)
    assert record["verified"] is True
    assert record["platform_id"] == "linux-64"
    assert record["artifact_count"] == 1
    assert record["repository_commit"] == COMMIT
    assert record["repository_tree"] == TREE
    assert record["repository_clean"] is True
