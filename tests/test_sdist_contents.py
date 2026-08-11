from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path, PurePosixPath

from setuptools import build_meta


REQUIRED_SDIST_PATHS = {
    ".github/workflows/public-validation.yml",
    ".github/workflows/smoke-tests.yml",
    "CITATION.cff",
    "docs/assets/mito_overview_report_native_views.png",
    "examples/expected_reports/TOY-001_output/report/01_mito_qc.html",
    "examples/expected_reports/TOY-SR-001_output/report/01_mito_qc.html",
    "examples/public_validation/GM11906_MERRF_shortread/summary/mito_qc_summary.tsv",
    "examples/public_validation/GM12878_ONT_longread/summary/mito_qc_summary.tsv",
    "examples/synthetic_data/TOY-WGS-001/expected_copy_proxy.tsv",
    "resources/annotations/NC_012920.1.fa",
    "resources/annotations/human_mt_reference.gtf",
    "resources/schemas/mito_overview_config.schema.yaml",
    "scripts/build_validation_packet_v0.3.1.py",
    "scripts/export_public_validation_contracts_v0_3_0.py",
    "scripts/assemble_release_assets_v0.3.1.py",
    "scripts/build_release_validation_report_v0.3.1.py",
    "scripts/check_release_hygiene.py",
    "scripts/hash_validation_inputs.py",
    "scripts/inventory_visual_artifacts.py",
    "scripts/finalize_release_validation_report_v0.3.1.py",
    "scripts/publish_github_release_v0.3.1.py",
    "scripts/refresh_tracked_public_validation_assets_v0.3.0.py",
    "scripts/run_fresh_public_tag_validation_v0.3.1.sh",
    "scripts/verify_release_environment_v0.3.1.py",
    "scripts/run_mito_pipeline.sh",
    "scripts/safe_extract_validation_zip.py",
    "scripts/sanitize_validation_evidence.py",
    "scripts/stage_public_visual_artifacts_v0.3.0.py",
    "scripts/summarize_filter_profiles.py",
    "scripts/validation_fingerprints_v0_3_0.py",
    "scripts/verify_release_asset_identity_v0.3.1.py",
    "scripts/verify_distribution_equivalence_v0.3.1.py",
    "tests/_helpers.py",
    "tests/conftest.py",
    "tests/fixtures/mock_mvtool_annotations.json",
    "tests/fixtures/mock_phymer_vendor/Phy-Mer.py",
    "tests/fixtures/mock_phymer_vendor/resources/Build_16_-_rCRS-based_haplogroup_motifs.csv",
    "tests/fixtures/public_validation_contracts_v0.3.0/gm12878_strict/summary_schema_manifest.tsv",
    "tests/smoke_public_pipeline.sh",
    "tests/test_validation_packet.py",
    "tests/test_sanitize_validation_evidence.py",
}

FORBIDDEN_INTERNAL_PATHS = {
    "analysis_log.md",
    "docs/preprint_hardening_plan_v0.3.0.md",
    "docs/preprint_release_validation_v0.3.0.md",
    "docs/repo_mapping.md",
    "docs/reproducibility_run_ledger.md",
    "optional_checks/README.md",
    "resources/zenodo/mito_overview_v0.3.0_draft.json",
    "scripts/capture_zenodo_reservation.py",
    "scripts/export_preprint_docx.py",
    "scripts/hpc/prep_mito_overview.pl",
    "optional_checks/test_zenodo_reservation_capture.py",
}


def _build_sdist(repo_root: Path, output_dir: Path) -> Path:
    previous = Path.cwd()
    os.chdir(repo_root)
    try:
        filename = build_meta.build_sdist(str(output_dir))
    finally:
        os.chdir(previous)
    return output_dir / filename


def _payload_paths(sdist: Path) -> set[str]:
    with tarfile.open(sdist, "r:gz") as archive:
        members = [PurePosixPath(member.name) for member in archive.getmembers()]
    roots = {member.parts[0] for member in members if member.parts}
    assert roots == {"mito_overview-0.3.1"}
    return {
        PurePosixPath(*member.parts[1:]).as_posix()
        for member in members
        if len(member.parts) > 1
    }


def test_sdist_contains_runnable_release_tests_and_only_public_expected_bundles(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).parents[1]
    payload = _payload_paths(_build_sdist(repo_root, tmp_path))

    assert REQUIRED_SDIST_PATHS <= payload

    expected_bundles = {
        PurePosixPath(path).parts[2]
        for path in payload
        if len(PurePosixPath(path).parts) > 2
        and PurePosixPath(path).parts[:2] == ("examples", "expected_reports")
    }
    assert expected_bundles == {"TOY-001_output", "TOY-SR-001_output"}
    assert FORBIDDEN_INTERNAL_PATHS.isdisjoint(payload)
    assert not any(
        path.startswith(("paper/", "optional_checks/", "resources/zenodo/", "scripts/hpc/"))
        for path in payload
    )
    assert not any("__pycache__" in path or path.endswith((".pyc", ".pyo")) for path in payload)


def test_sdist_excludes_internal_canaries_if_they_exist_locally(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[1]
    candidate = tmp_path / "candidate"
    shutil.copytree(
        repo_root,
        candidate,
        ignore=shutil.ignore_patterns(
            ".git",
            ".conda-release-check",
            ".pytest_cache",
            "build",
            "dist",
            "mito_overview.egg-info",
            "paper",
            "__pycache__",
        ),
    )
    canaries = {
        "analysis_log.md": "internal log\n",
        "paper/preprint_draft.md": "internal manuscript\n",
        "docs/preprint_release_validation_v0.3.0.md": "internal plan\n",
        "optional_checks/test_internal.py": "raise AssertionError\n",
        "resources/zenodo/internal.json": "{}\n",
        "scripts/capture_zenodo_reservation.py": "raise AssertionError\n",
        "scripts/export_preprint_docx.py": "raise AssertionError\n",
        "scripts/hpc/prep_mito_overview.pl": "die;\n",
    }
    for relative, content in canaries.items():
        path = candidate / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    output = tmp_path / "dist"
    output.mkdir()
    payload = _payload_paths(_build_sdist(candidate, output))

    assert set(canaries).isdisjoint(payload)
    assert not any(
        path.startswith(("paper/", "optional_checks/", "resources/zenodo/", "scripts/hpc/"))
        for path in payload
    )


def test_default_pytest_scope_is_limited_to_public_tests() -> None:
    configuration = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert configuration["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_sdist_readme_contains_no_internal_manuscript_references(
    tmp_path: Path,
) -> None:
    sdist = _build_sdist(Path(__file__).parents[1], tmp_path)
    with tarfile.open(sdist, "r:gz") as archive:
        readme_member = next(
            member for member in archive.getmembers() if member.name.endswith("/README.md")
        )
        handle = archive.extractfile(readme_member)
        assert handle is not None
        readme = handle.read().decode("utf-8")

    assert "paper/" not in readme
    assert "preprint_draft" not in readme
    assert "docs/assets/mito_overview_report_native_views.png" in readme


def test_extracted_sdist_runs_the_standalone_oracle_checker_in_isolated_mode(
    tmp_path: Path,
) -> None:
    build_root = tmp_path / "build"
    build_root.mkdir()
    sdist = _build_sdist(Path(__file__).parents[1], build_root)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(sdist, "r:gz") as archive:
        archive.extractall(extracted, filter="data")
    source_root = next(extracted.iterdir())
    checker = source_root / "scripts/assert_public_validation_oracle_v0.3.0.py"
    outside = tmp_path / "outside"
    outside.mkdir()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "/forbidden-checkout-path"

    completed = subprocess.run(
        [sys.executable, "-I", str(checker), "--help"],
        cwd=outside,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Assert the frozen v0.3.0 public-validation" in completed.stdout


def test_extracted_sdist_runs_the_contract_exporter_in_isolated_mode(
    tmp_path: Path,
) -> None:
    build_root = tmp_path / "build"
    build_root.mkdir()
    sdist = _build_sdist(Path(__file__).parents[1], build_root)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(sdist, "r:gz") as archive:
        archive.extractall(extracted, filter="data")
    source_root = next(extracted.iterdir())
    exporter = source_root / "scripts/export_public_validation_contracts_v0_3_0.py"
    outside = tmp_path / "outside"
    outside.mkdir()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "/forbidden-checkout-path"

    completed = subprocess.run(
        [sys.executable, "-I", str(exporter), "--help"],
        cwd=outside,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Export exact candidate tables" in completed.stdout
