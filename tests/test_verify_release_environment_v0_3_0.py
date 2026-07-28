from __future__ import annotations

import importlib.util
import json
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


def test_all_release_verifier_entrypoints_isolate_python_startup() -> None:
    entrypoints = (
        ROOT / ".github/workflows/smoke-tests.yml",
        ROOT / ".github/workflows/public-validation.yml",
        ROOT / "scripts/run_release_validation_v0.3.0.sh",
        ROOT / "scripts/run_fresh_public_tag_validation_v0.3.0.sh",
    )
    invocation_count = 0
    for path in entrypoints:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "verify_release_environment_v0.3.0.py" not in line:
                continue
            invocation_count += 1
            assert "-I -S" in line, f"unisolated verifier invocation in {path}: {line}"
    assert invocation_count == 6


def manifest(package: str, digest: str = HASH_A) -> str:
    return (
        "# platform: linux-64\n"
        "@EXPLICIT\n"
        f"https://conda.anaconda.org/conda-forge/linux-64/{package}#{digest}\n"
    )


def write_conda_metadata(prefix: Path, record: str) -> None:
    metadata = prefix / "conda-meta"
    metadata.mkdir(parents=True, exist_ok=True)
    url, digest = record.rsplit("#", 1)
    filename = Path(verifier.urlsplit(url).path).name
    payload = {
        "name": filename.split("-", 1)[0],
        "version": "1.0",
        "build": "0",
        "fn": filename,
        "url": url,
        "sha256": digest,
    }
    (metadata / f"{filename}.json").write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def configure_runtime_python(
    prefix: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    python = prefix / "bin" / "python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o755)
    monkeypatch.setattr(verifier.sys, "executable", str(python))
    return python


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
    wrong = manifest("python-3.12.13-other_0.conda", HASH_B)
    write_conda_metadata(
        prefix,
        next(line for line in wrong.splitlines() if line.startswith("https://")),
    )
    runtime_python = configure_runtime_python(prefix, monkeypatch)

    monkeypatch.setattr(verifier, "platform_id", lambda: "linux-64")
    monkeypatch.setattr(
        verifier.sys, "version_info", (3, 12, 13, "final", 0)
    )
    monkeypatch.setattr(
        verifier.platform, "python_version", lambda: "3.12.13"
    )
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[0] == "git"
        stdout = TREE + "\n" if command[-1] == "HEAD^{tree}" else COMMIT + "\n"
        if command[-1] == "--untracked-files=all":
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="do not match"):
        verifier.verify(repo, runtime_python, COMMIT)


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
    write_conda_metadata(
        prefix,
        next(line for line in locked.splitlines() if line.startswith("https://")),
    )
    runtime_python = configure_runtime_python(prefix, monkeypatch)

    monkeypatch.setattr(verifier, "platform_id", lambda: "linux-64")
    monkeypatch.setattr(
        verifier.sys, "version_info", (3, 12, 13, "final", 0)
    )
    monkeypatch.setattr(
        verifier.platform, "python_version", lambda: "3.12.13"
    )
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[0] == "git"
        stdout = TREE + "\n" if command[-1] == "HEAD^{tree}" else COMMIT + "\n"
        if command[-1] == "--untracked-files=all":
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    record = verifier.verify(repo, runtime_python, COMMIT)
    assert record["verified"] is True
    assert record["platform_id"] == "linux-64"
    assert record["artifact_count"] == 1
    assert record["repository_commit"] == COMMIT
    assert record["repository_tree"] == TREE
    assert record["repository_clean"] is True


def test_verify_ignores_hostile_python_hooks_and_conda_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    locks = repo / "locks"
    locks.mkdir(parents=True)
    locked = manifest("python-3.12.13-approved_0.conda")
    (locks / "environment-linux-64.explicit.txt").write_text(
        locked, encoding="utf-8"
    )
    prefix = tmp_path / "conda-prefix"
    write_conda_metadata(
        prefix,
        next(line for line in locked.splitlines() if line.startswith("https://")),
    )
    runtime_python = configure_runtime_python(prefix, monkeypatch)

    hostile = tmp_path / "hostile"
    hostile.mkdir()
    startup_marker = tmp_path / "sitecustomize-loaded"
    (hostile / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(startup_marker)!r}).write_text('loaded', encoding='utf-8')\n",
        encoding="utf-8",
    )
    conda_marker = tmp_path / "hostile-conda-ran"
    fake_conda = tmp_path / "conda"
    fake_conda.write_text(
        "#!/bin/sh\n"
        f"printf ran > {str(conda_marker)!r}\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_conda.chmod(0o755)
    monkeypatch.setenv("PYTHONPATH", str(hostile))
    monkeypatch.setenv("PYTHONHOME", str(hostile))
    monkeypatch.setenv("CONDA_EXE", str(fake_conda))
    monkeypatch.setattr(verifier, "platform_id", lambda: "linux-64")
    monkeypatch.setattr(
        verifier.sys, "version_info", (3, 12, 13, "final", 0)
    )
    monkeypatch.setattr(
        verifier.platform, "python_version", lambda: "3.12.13"
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[0] == "git"
        stdout = TREE + "\n" if command[-1] == "HEAD^{tree}" else COMMIT + "\n"
        if command[-1] == "--untracked-files=all":
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    record = verifier.verify(repo, runtime_python, COMMIT)

    assert record["verified"] is True
    assert not startup_marker.exists()
    assert not conda_marker.exists()


def test_verify_rejects_package_empty_venv_over_conda_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    locks = repo / "locks"
    locks.mkdir(parents=True)
    locked = manifest("python-3.12.13-approved_0.conda")
    (locks / "environment-linux-64.explicit.txt").write_text(
        locked, encoding="utf-8"
    )
    conda_base = tmp_path / "conda-base"
    write_conda_metadata(
        conda_base,
        next(line for line in locked.splitlines() if line.startswith("https://")),
    )
    empty_venv = tmp_path / "empty-venv"
    runtime_python = configure_runtime_python(empty_venv, monkeypatch)
    monkeypatch.setattr(verifier.sys, "prefix", str(conda_base))
    monkeypatch.setattr(verifier, "platform_id", lambda: "linux-64")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[0] == "git"
        stdout = TREE + "\n" if command[-1] == "HEAD^{tree}" else COMMIT + "\n"
        if command[-1] == "--untracked-files=all":
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="not inside a Conda prefix"):
        verifier.verify(repo, runtime_python, COMMIT)


def test_verify_rejects_symlinked_venv_python_targeting_conda_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    locks = repo / "locks"
    locks.mkdir(parents=True)
    locked = manifest("python-3.12.13-approved_0.conda")
    (locks / "environment-linux-64.explicit.txt").write_text(
        locked, encoding="utf-8"
    )
    conda_base = tmp_path / "conda-base"
    write_conda_metadata(
        conda_base,
        next(line for line in locked.splitlines() if line.startswith("https://")),
    )
    base_python = conda_base / "bin" / "python3.12"
    base_python.parent.mkdir(parents=True, exist_ok=True)
    base_python.write_text("#!/bin/sh\n", encoding="utf-8")
    base_python.chmod(0o755)

    overlay_python = tmp_path / "overlay-venv" / "bin" / "python"
    overlay_python.parent.mkdir(parents=True)
    overlay_python.symlink_to(base_python)
    monkeypatch.setattr(verifier.sys, "executable", str(overlay_python))
    monkeypatch.setattr(verifier, "platform_id", lambda: "linux-64")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[0] == "git"
        stdout = TREE + "\n" if command[-1] == "HEAD^{tree}" else COMMIT + "\n"
        if command[-1] == "--untracked-files=all":
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="resolves outside"):
        verifier.verify(repo, overlay_python, COMMIT)
