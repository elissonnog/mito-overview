from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
LOCKS = {
    "linux-64": REPO_ROOT / "locks" / "environment-linux-64.yml",
    "osx-64": REPO_ROOT / "locks" / "environment-osx-64.yml",
    "osx-arm64": REPO_ROOT / "locks" / "environment-osx-arm64.yml",
}
EXPECTED_CONDA_SPECS = {
    "python=3.12.13",
    "htslib=1.23.1",
    "samtools=1.23.1",
    "minimap2=2.31",
    "bwa=0.7.19",
    "matplotlib=3.11.0",
    "numpy=2.5.1",
    "pandas=3.0.3",
    "pysam=0.24.0",
    "requests=2.34.2",
    "setuptools=82.0.1",
    "wheel=0.47.0",
    "pip=26.1.2",
}
EXPECTED_PIP_SPECS = {
    "pytest==9.1.1",
    "build==1.5.0",
    "python-docx==1.2.0",
}


def _environment_specs(path: Path) -> tuple[set[str], set[str]]:
    conda_specs: set[str] = set()
    pip_specs: set[str] = set()
    in_dependencies = False
    in_pip = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "dependencies:":
            in_dependencies = True
            continue
        if not in_dependencies:
            continue
        if line == "  - pip:":
            in_pip = True
            continue
        if in_pip and line.startswith("      - "):
            pip_specs.add(line.removeprefix("      - "))
            continue
        if line.startswith("  - "):
            conda_specs.add(line.removeprefix("  - "))
    return conda_specs, pip_specs


def test_release_python_and_python_dependencies_are_exactly_bounded() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    metadata = project["project"]

    assert metadata["requires-python"] == ">=3.12,<3.13"
    assert metadata["dependencies"] == [
        "matplotlib==3.11.0",
        "numpy==2.5.1",
        "pandas==3.0.3",
        "pysam==0.24.0",
        "requests==2.34.2",
    ]
    assert metadata["optional-dependencies"]["dev"] == [
        "build==1.5.0",
        "pytest==9.1.1",
        "python-docx==1.2.0",
    ]
    assert project["build-system"]["requires"] == [
        "setuptools==82.0.1",
        "wheel==0.47.0",
    ]
    assert set(project["tool"]["setuptools"]["data-files"]["share/mito-overview/locks"]) == {
        "locks/environment-linux-64.yml",
        "locks/environment-osx-64.yml",
        "locks/environment-osx-arm64.yml",
    }
    assert "Programming Language :: Python :: 3.11" not in metadata["classifiers"]
    assert "Programming Language :: Python :: 3.12" in metadata["classifiers"]


def test_generic_environment_and_platform_solver_specs_are_synchronized() -> None:
    canonical_specs = _environment_specs(REPO_ROOT / "environment.yml")
    assert canonical_specs == (EXPECTED_CONDA_SPECS, EXPECTED_PIP_SPECS)

    for platform, lock_path in LOCKS.items():
        text = lock_path.read_text(encoding="utf-8")
        assert f"# platform: {platform}" in text
        assert _environment_specs(lock_path) == canonical_specs


def _fake_python(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "python-calls.log"
    executable = tmp_path / "python"
    executable.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'PYTHONPATH=%s\\tARGS=%s\\n' "${PYTHONPATH-<unset>}" "$*" >> "$FAKE_PYTHON_LOG"
if [[ "${1:-}" == "-I" && "${2:-}" == "-c" ]]; then
  if [[ "${FAKE_IMPORT_MODE:-installed}" == "unavailable" ]]; then
    exit 1
  fi
  printf '%s\\n' "$FAKE_IMPORT_PATH"
fi
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable, log


def _run_launcher(
    tmp_path: Path,
    *,
    import_mode: str,
    import_path: Path,
    require_installed: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    executable, log = _fake_python(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "FAKE_IMPORT_MODE": import_mode,
            "FAKE_IMPORT_PATH": str(import_path),
            "FAKE_PYTHON_LOG": str(log),
            "MITO_OVERVIEW_PYTHON": str(executable),
            "PYTHONPATH": "/ambient/pythonpath",
        }
    )
    if require_installed:
        environment["MITO_OVERVIEW_REQUIRE_INSTALLED"] = "1"
    else:
        environment.pop("MITO_OVERVIEW_REQUIRE_INSTALLED", None)
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "run_mito_pipeline.sh"), "--list-steps"],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )
    calls = log.read_text(encoding="utf-8").splitlines()
    return result, calls


def test_launcher_prefers_isolated_installed_distribution(tmp_path: Path) -> None:
    result, calls = _run_launcher(
        tmp_path,
        import_mode="installed",
        import_path=Path("/opt/mito-overview/mito_overview/__init__.py"),
    )

    assert result.returncode == 0, result.stderr
    assert len(calls) == 2
    assert "ARGS=-I -c " in calls[0]
    assert calls[1] == "PYTHONPATH=<unset>\tARGS=-I -m mito_overview.cli --list-steps"


def test_launcher_falls_back_to_checkout_only_when_import_is_unavailable(
    tmp_path: Path,
) -> None:
    result, calls = _run_launcher(
        tmp_path,
        import_mode="unavailable",
        import_path=Path("/unused"),
    )

    assert result.returncode == 0, result.stderr
    assert len(calls) == 2
    expected_path = f"PYTHONPATH={REPO_ROOT}:/ambient/pythonpath"
    assert calls[1] == f"{expected_path}\tARGS=-m mito_overview.cli --list-steps"


def test_launcher_validation_mode_rejects_missing_or_shadowed_install(
    tmp_path: Path,
) -> None:
    unavailable, unavailable_calls = _run_launcher(
        tmp_path / "unavailable",
        import_mode="unavailable",
        import_path=Path("/unused"),
        require_installed=True,
    )
    shadowed, shadowed_calls = _run_launcher(
        tmp_path / "shadowed",
        import_mode="installed",
        import_path=REPO_ROOT / "mito_overview" / "__init__.py",
        require_installed=True,
    )

    assert unavailable.returncode == 1
    assert "not importable from the installed environment" in unavailable.stderr
    assert len(unavailable_calls) == 1
    assert shadowed.returncode == 1
    assert "rejected checkout import" in shadowed.stderr
    assert len(shadowed_calls) == 1


def test_ci_uses_fixed_runners_and_public_artifacts_exclude_raw_inputs() -> None:
    smoke = (REPO_ROOT / ".github" / "workflows" / "smoke-tests.yml").read_text(
        encoding="utf-8"
    )
    public = (REPO_ROOT / ".github" / "workflows" / "public-validation.yml").read_text(
        encoding="utf-8"
    )

    for runner in ("ubuntu-24.04", "macos-15-intel", "macos-15"):
        assert f"os: {runner}" in smoke
    assert "ubuntu-latest" not in smoke
    assert "macos-latest" not in smoke
    for lock in LOCKS.values():
        assert lock.relative_to(REPO_ROOT).as_posix() in smoke

    assert "workflow_dispatch:" in public
    assert "^[0-9a-f]{40}$" in public
    assert "ref: ${{ inputs.commit_sha }}" in public
    assert "runs-on: ubuntu-24.04" in public
    assert "--mode offline" in public
    assert "public_validation_oracle_v0.3.0.tsv" in public
    assert "prepare_public_validation_cache_v0.3.0.sh" in public
    assert "actions/cache" not in public
    assert "public-validation-derived-evidence" in public
    assert "Raw genomic input or alignment entered artifact staging" in public
    assert 'MITO_OVERVIEW_REQUIRE_INSTALLED: "1"' in public
    assert "MITO_OVERVIEW_EXPECTED_PLATFORM=linux-64" in public
    assert "run_network_isolated_v0.3.0.sh" in public
    assert "sudo -n true" in public
    assert "command -v unshare" in public
    assert "command -v setpriv" in public
    assert "network_isolation.tsv" in public
    assert "offline_isolation" in public
    assert "runtime_versions.json" not in public  # staged through the results/environment tree.
    assert "oracle_assertions.tsv" in public
    assert "raw_inputs.tsv" in public
    assert "CACHE_SEAL.sha256" in public
    assert "shasum -a 256 -c SHA256SUMS" in public
    assert "sanitize_validation_evidence.py" in public
    assert "--replace \"$RUNNER_TEMP=\\${RUNNER_TEMP}\"" in public
    assert 'f"platform-{os.environ[' in smoke
    assert '"EXPECTED_PLATFORM"' in smoke
