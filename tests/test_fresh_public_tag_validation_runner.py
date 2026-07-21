from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "scripts" / "run_fresh_public_tag_validation_v0.3.0.sh"


def test_runner_is_valid_shell_and_encodes_all_required_release_gates() -> None:
    subprocess.run(["bash", "-n", str(RUNNER)], check=True)
    text = RUNNER.read_text(encoding="utf-8")

    required_cases = {
        "public_https_tag_clone",
        "annotated_tag_identity",
        "clean_tag_checkout",
        "locked_environment",
        "wheel_sdist_build",
        "installed_cli",
        "unit_tests",
        "smoke_longread",
        "smoke_shortread",
        "smoke_longread_nomethyl",
        "smoke_standalone",
        "example_builders",
    }
    for case_id in required_cases:
        assert f"run_case {case_id} " in text
    for required in (
        "git clone --no-checkout",
        "cat-file -t refs/tags/${TAG}",
        "refs/tags/${TAG}^{commit}",
        "python=3.12.13",
        "samtools=1.23.1",
        "mito_overview-0.3.0.tar.gz",
        "-m pytest -q",
        "smoke_public_pipeline.sh",
        "smoke_public_pipeline_shortread.sh",
        "smoke_public_pipeline_longread_nomethyl.sh",
        "smoke_standalone_minimal.sh",
        "build_public_example_bundle.sh",
        "build_public_shortread_example_bundle.sh",
        "sanitize_validation_evidence.py",
        "evidence.sha256",
        "fresh_public_tag_validation.json",
    ):
        assert required in text
    assert "Zenodo" not in text
    assert "DOI" not in text


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["http://github.com/owner/repo", "1" * 40, "work", "evidence"],
        ["https://github.com/owner/repo", "short", "work", "evidence"],
    ],
)
def test_runner_rejects_invalid_invocations_without_network(
    tmp_path: Path, arguments: list[str]
) -> None:
    resolved = [
        str(tmp_path / value) if value in {"work", "evidence"} else value
        for value in arguments
    ]
    completed = subprocess.run(
        ["bash", str(RUNNER), *resolved],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
