from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from mito_overview.paths import ANNOTATION_RESOURCE_NAMES, annotation_resource_path


REPO_ROOT = Path(__file__).parents[1]
LOCKS = {
    "linux-64": REPO_ROOT / "locks" / "environment-linux-64.yml",
    "osx-64": REPO_ROOT / "locks" / "environment-osx-64.yml",
    "osx-arm64": REPO_ROOT / "locks" / "environment-osx-arm64.yml",
}
ARTIFACT_LOCKS = {
    platform: REPO_ROOT / "locks" / f"environment-{platform}.explicit.txt"
    for platform in LOCKS
}
EXPECTED_CONDA_SPECS = {
    "biopython=1.87",
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
EXPECTED_ANNOTATION_SHA256 = {
    "NC_012920.1.fa": "fc392cde8e63b4d2e3a870bb97cc0626dea33d46dfb8abdebffada040f42ec92",
    "human_mt_reference.gtf": "6c8db180f5dd7999ae70bf9e3c7e5020c6c99b4cefd935d621eedcb1fc5408d9",
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
        "biopython==1.87",
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
        "locks/environment-linux-64.explicit.txt",
        "locks/environment-osx-64.explicit.txt",
        "locks/environment-osx-arm64.explicit.txt",
        "locks/requirements-release-tools.txt",
    }
    assert set(
        project["tool"]["setuptools"]["data-files"][
            "share/mito-overview/annotations"
        ]
    ) == {
        "resources/annotations/NC_012920.1.fa",
        "resources/annotations/human_mt_reference.gtf",
    }
    assert "Programming Language :: Python :: 3.11" not in metadata["classifiers"]
    assert "Programming Language :: Python :: 3.12" in metadata["classifiers"]


@pytest.fixture(scope="module")
def release_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("release-wheel")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(output),
            str(REPO_ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(output.glob("mito_overview-0.3.0-py3-none-any.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_wheel_contains_annotation_resources_at_stable_location(
    release_wheel: Path,
) -> None:
    prefix = "mito_overview-0.3.0.data/data/share/mito-overview/annotations/"
    with zipfile.ZipFile(release_wheel) as archive:
        members = set(archive.namelist())
        for name, expected_sha256 in EXPECTED_ANNOTATION_SHA256.items():
            member = f"{prefix}{name}"
            assert member in members
            assert hashlib.sha256(archive.read(member)).hexdigest() == expected_sha256


def test_installed_wheel_resolves_annotation_resources_outside_checkout(
    tmp_path: Path,
    release_wheel: Path,
) -> None:
    environment = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(environment)],
        check=True,
        capture_output=True,
        text=True,
    )
    python = environment / "bin" / "python"
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--force-reinstall",
            str(release_wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    probe = tmp_path / "probe"
    probe.mkdir()
    code = """
import hashlib
import json
import sys
from pathlib import Path

from mito_overview.paths import annotation_resource_path

expected = json.loads(sys.argv[1])
expected_root = Path(sys.prefix) / "share" / "mito-overview" / "annotations"
for name, expected_sha256 in expected.items():
    path = annotation_resource_path(name)
    assert path == expected_root / name, (path, expected_root / name)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256
"""
    subprocess.run(
        [str(python), "-I", "-c", code, json.dumps(EXPECTED_ANNOTATION_SHA256)],
        cwd=probe,
        check=True,
        capture_output=True,
        text=True,
    )


def test_annotation_resource_lookup_is_allowlisted() -> None:
    assert ANNOTATION_RESOURCE_NAMES == frozenset(EXPECTED_ANNOTATION_SHA256)
    for name, expected_sha256 in EXPECTED_ANNOTATION_SHA256.items():
        path = annotation_resource_path(name)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256
    with pytest.raises(ValueError, match="Unknown annotation resource"):
        annotation_resource_path("../README.md")


def test_generic_environment_and_platform_solver_specs_are_synchronized() -> None:
    canonical_specs = _environment_specs(REPO_ROOT / "environment.yml")
    assert canonical_specs == (EXPECTED_CONDA_SPECS, EXPECTED_PIP_SPECS)

    for platform, lock_path in LOCKS.items():
        text = lock_path.read_text(encoding="utf-8")
        assert f"# platform: {platform}" in text
        assert _environment_specs(lock_path) == canonical_specs


def test_platform_artifact_locks_are_explicit_and_complete() -> None:
    required_fragments = {
        "python-3.12.13-",
        "htslib-1.23.1-",
        "samtools-1.23.1-",
        "minimap2-2.31-",
        "bwa-0.7.19-",
        "biopython-1.87-",
        "matplotlib-3.11.0-",
        "numpy-2.5.1-",
        "pandas-3.0.3-",
        "pysam-0.24.0-",
        "requests-2.34.2-",
        "setuptools-82.0.1-",
        "wheel-0.47.0-",
        "pip-26.1.2-",
    }
    for platform, path in ARTIFACT_LOCKS.items():
        lines = path.read_text(encoding="utf-8").splitlines()
        assert f"# platform: {platform}" in lines
        assert "@EXPLICIT" in lines
        urls = [
            line
            for line in lines
            if line and not line.startswith("#") and line != "@EXPLICIT"
        ]
        assert urls
        assert len(urls) == len(set(urls))
        assert all(
            len(urlsplit(url).fragment) == 64
            and set(urlsplit(url).fragment) <= set("0123456789abcdef")
            for url in urls
        )
        assert all(
            url.startswith(
                (
                    "https://conda.anaconda.org/conda-forge/",
                    "https://conda.anaconda.org/bioconda/",
                )
            )
            for url in urls
        )
        for fragment in required_fragments:
            assert any(fragment in url for url in urls), (platform, fragment)


def test_release_tool_requirements_are_hash_locked() -> None:
    path = REPO_ROOT / "locks" / "requirements-release-tools.txt"
    text = path.read_text(encoding="utf-8")
    for requirement in (
        "build==1.5.0",
        "pytest==9.1.1",
        "python-docx==1.2.0",
        "lxml==6.1.1",
    ):
        assert requirement in text
    assert "--hash=sha256:" in text
    assert "--index-url" not in text
    assert "git+" not in text


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


@pytest.mark.parametrize(
    "script_name",
    (
        "public_alignment_provenance.py",
        "select_deterministic_fastq_subset.py",
        "select_deterministic_bam_subset.py",
    ),
)
def test_public_helpers_use_external_package_in_installed_mode(
    tmp_path: Path,
    script_name: str,
) -> None:
    site = tmp_path / "external-site"
    package = site / "mito_overview"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "validation_provenance.py").write_text(
        """
class ProvenanceError(Exception):
    pass

def placeholder(*args, **kwargs):
    return None

create_alignment_provenance = placeholder
parse_key_values = placeholder
parse_labeled_paths = placeholder
verify_alignment_provenance = placeholder
create_deterministic_fastq_subset = placeholder
verify_deterministic_fastq_subset = placeholder
create_deterministic_subset = placeholder
verify_deterministic_subset = placeholder
""".lstrip(),
        encoding="utf-8",
    )
    probe = """
import runpy
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
runpy.run_path(sys.argv[2], run_name="audit_probe")
import mito_overview.validation_provenance as module
print(Path(module.__file__).resolve())
"""
    environment = os.environ.copy()
    environment["MITO_OVERVIEW_REQUIRE_INSTALLED"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            probe,
            str(site),
            str(REPO_ROOT / "scripts" / script_name),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).is_relative_to(package)


def test_standalone_smoke_direct_cli_probes_use_isolated_mode() -> None:
    smoke = (REPO_ROOT / "tests" / "smoke_standalone_minimal.sh").read_text(
        encoding="utf-8"
    )
    invocation = '"${MITO_OVERVIEW_PYTHON:-python3}" -I -m mito_overview.cli'
    assert smoke.count(invocation) == 2


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
    assert "report_artifacts/outputs" in public
    assert "inventory_visual_artifacts.py" in public
    assert "outside the v0.3.0 HTML/PNG evidence contract" in public
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
