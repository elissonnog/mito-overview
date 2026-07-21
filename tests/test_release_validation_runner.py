from __future__ import annotations

import os
import subprocess
from pathlib import Path


RUNNER = Path(__file__).parents[1] / "scripts" / "run_release_validation_v0.3.0.sh"


def invoke(tmp_path: Path, *extra: str, environment: dict[str, str] | None = None):
    paths = [
        str(tmp_path / "validation"),
        str(tmp_path / "cache"),
        str(tmp_path / "packet"),
        str(tmp_path / "mito-overview-v0.3.0-validation.zip"),
    ]
    env = os.environ.copy()
    env.pop("MITO_OVERVIEW_ARCHIVE_DOI", None)
    env.pop("MITO_OVERVIEW_ZENODO_RESERVATION_EVIDENCE", None)
    env.update(environment or {})
    return subprocess.run(
        ["bash", str(RUNNER), *paths, *extra],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_runner_requires_exactly_four_paths(tmp_path: Path) -> None:
    completed = invoke(
        tmp_path,
        "10.5281/zenodo.123",
        environment={"MITO_OVERVIEW_GITHUB_RUN_ID": "123"},
    )
    assert completed.returncode == 2
    assert "Legacy fifth/archive input is not supported" in completed.stderr


def test_runner_rejects_legacy_archive_environment(tmp_path: Path) -> None:
    completed = invoke(
        tmp_path,
        environment={
            "MITO_OVERVIEW_GITHUB_RUN_ID": "123",
            "MITO_OVERVIEW_ARCHIVE_DOI": "10.5281/zenodo.123",
        },
    )
    assert completed.returncode == 2
    assert "legacy archive input" in completed.stderr


def test_runner_requires_github_actions_run_id_before_execution(tmp_path: Path) -> None:
    completed = invoke(tmp_path)
    assert completed.returncode == 2
    assert "MITO_OVERVIEW_GITHUB_RUN_ID" in completed.stderr


def test_runner_declares_public_clone_and_isolated_installed_probe() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert 'PUBLIC_REMOTE="${REPOSITORY}.git"' in text
    assert "git clone --no-checkout" in text
    assert "env -i" in text
    assert "python -m venv" not in text  # executable is shell-expanded, not ambient.
    assert "-m venv" in text
    assert "-m build --no-isolation" in text
    assert "-I -m mito_overview.cli --list-steps" in text
    assert "executed_outside_checkout" in text
    assert "--zenodo-reservation-evidence" not in text
    assert "--doi" not in text
