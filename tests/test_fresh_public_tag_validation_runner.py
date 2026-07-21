from __future__ import annotations

import csv
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "scripts" / "run_fresh_public_tag_validation_v0.3.0.sh"
PUBLIC_FIXTURE_URL = "https://github.com/fixture/mito-overview"


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _build_fixture_repository(root: Path, *, report_pages: int) -> tuple[Path, str, str]:
    repository = root / "fixture-source"
    repository.mkdir(parents=True)
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)

    smoke = "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n"
    for name in (
        "smoke_public_pipeline.sh",
        "smoke_public_pipeline_shortread.sh",
        "smoke_public_pipeline_longread_nomethyl.sh",
        "smoke_standalone_minimal.sh",
    ):
        _write_executable(repository / "tests" / name, smoke)

    builder = f"""\
#!/usr/bin/env bash
set -euo pipefail
target="$1"
mkdir -p "${{target}}/report"
for index in $(seq 1 {report_pages}); do
  if [[ "${{index}}" -eq 1 ]]; then
    name="01_mito_qc.html"
  elif [[ "${{index}}" -eq 14 ]]; then
    name="14_mito_mvtool_annotation.html"
  else
    name="$(printf '%02d_fixture.html' "${{index}}")"
  fi
  printf '<html><body>fixture %s</body></html>\n' "${{index}}" > "${{target}}/report/${{name}}"
done
"""
    _write_executable(repository / "scripts" / "build_public_example_bundle.sh", builder)
    _write_executable(
        repository / "scripts" / "build_public_shortread_example_bundle.sh", builder
    )
    _write_executable(
        repository / "scripts" / "run_mito_pipeline.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\nprintf 'validate\\n'\n",
    )
    shutil.copyfile(
        ROOT / "scripts" / "sanitize_validation_evidence.py",
        repository / "scripts" / "sanitize_validation_evidence.py",
    )

    _git(repository, "add", ".")
    _git(
        repository,
        "-c",
        "user.name=MitoOverview fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "release validation fixture",
    )
    _git(repository, "branch", "-M", "main")
    _git(
        repository,
        "-c",
        "user.name=MitoOverview fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "tag",
        "-a",
        "v0.3.0",
        "-m",
        "MitoOverview v0.3.0 fixture",
    )
    return (
        repository,
        _git(repository, "rev-parse", "HEAD"),
        _git(repository, "rev-parse", "refs/tags/v0.3.0^{tag}"),
    )


def _build_command_shims(root: Path, fixture_repository: Path) -> Path:
    shim_root = root / "shims"
    shim_root.mkdir()
    real_git = shutil.which("git")
    assert real_git is not None
    _write_executable(
        shim_root / "git",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "${{1:-}}" == clone && "${{2:-}}" == --no-checkout && "${{3:-}}" == {shlex.quote(PUBLIC_FIXTURE_URL)} ]]; then
              {shlex.quote(real_git)} clone --no-checkout {shlex.quote(str(fixture_repository))} "$4"
              {shlex.quote(real_git)} -C "$4" remote set-url origin "$3"
              exit 0
            fi
            exec {shlex.quote(real_git)} "$@"
            """
        ),
    )

    fake_python = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import os
        import sys
        import tarfile
        from pathlib import Path

        REAL_PYTHON = {sys.executable!r}
        args = sys.argv[1:]
        if args == ["-"]:
            sys.stdin.read()
            raise SystemExit(0)
        if args[:2] == ["-m", "build"]:
            output = Path(args[args.index("--outdir") + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / "mito_overview-0.3.0-py3-none-any.whl").write_bytes(b"fixture wheel\\n")
            with tarfile.open(output / "mito_overview-0.3.0.tar.gz", "w:gz") as archive:
                directory = tarfile.TarInfo("mito_overview-0.3.0")
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o755
                archive.addfile(directory)
            raise SystemExit(0)
        if args[:2] == ["-m", "venv"]:
            target = Path(args[-1]) / "bin" / "python"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(Path(__file__).resolve())
            raise SystemExit(0)
        if args[:2] in (["-m", "pip"], ["-m", "pytest"]):
            raise SystemExit(0)
        if "mito_overview.cli" in args and "--list-steps" in args:
            print("validate")
            raise SystemExit(0)
        if "-c" in args:
            raise SystemExit(0)
        os.execv(REAL_PYTHON, [REAL_PYTHON, *args])
        """
    )
    _write_executable(shim_root / "fixture-python", fake_python)
    _write_executable(
        shim_root / "samtools",
        "#!/usr/bin/env bash\nprintf 'samtools 1.23.1\\nUsing htslib 1.23.1\\n'\n",
    )
    _write_executable(
        shim_root / "minimap2",
        "#!/usr/bin/env bash\nprintf '2.31-r1302\\n'\n",
    )
    _write_executable(
        shim_root / "bwa",
        "#!/usr/bin/env bash\nprintf 'Version: 0.7.19-r1273\\n' >&2\n",
    )
    return shim_root


def _execute_fixture_runner(
    tmp_path: Path, *, report_pages: int
) -> tuple[subprocess.CompletedProcess[str], Path, Path, str, str]:
    fixture, final_sha, tag_object_sha = _build_fixture_repository(
        tmp_path, report_pages=report_pages
    )
    shim_root = _build_command_shims(tmp_path, fixture)
    work_root = tmp_path / "release-work"
    evidence_root = tmp_path / "release-evidence"
    environment = os.environ.copy()
    environment["PATH"] = f"{shim_root}{os.pathsep}{environment['PATH']}"
    environment["MITO_OVERVIEW_PYTHON"] = "fixture-python"
    completed = subprocess.run(
        [
            "bash",
            str(RUNNER),
            PUBLIC_FIXTURE_URL,
            final_sha,
            str(work_root),
            str(evidence_root),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return completed, work_root, evidence_root, final_sha, tag_object_sha


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
        "longread/report/01_mito_qc.html",
        "longread/report/14_mito_mvtool_annotation.html",
        "shortread/report/01_mito_qc.html",
        "shortread/report/14_mito_mvtool_annotation.html",
        "sanitize_validation_evidence.py",
        "evidence.sha256",
        "fresh_public_tag_validation.json",
    ):
        assert required in text
    assert "Zenodo" not in text
    assert "DOI" not in text
    assert "report/index.html" not in text


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


def test_runner_success_path_emits_hash_verified_tag_bound_evidence(tmp_path: Path) -> None:
    completed, work_root, evidence_root, final_sha, tag_object_sha = (
        _execute_fixture_runner(tmp_path, report_pages=14)
    )
    assert completed.returncode == 0, completed.stderr

    with (evidence_root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 12
    assert len({row["case_id"] for row in rows}) == 12
    assert {row["verdict"] for row in rows} == {"PASS"}

    receipt = json.loads(
        (evidence_root / "fresh_public_tag_validation.json").read_text(encoding="utf-8")
    )
    assert receipt["verified"] is True
    assert receipt["verdict"] == "PASS"
    assert receipt["case_count"] == 12
    assert receipt["git_commit"] == final_sha
    assert receipt["tag_object_sha"] == tag_object_sha
    environment_lines = (evidence_root / "environment.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    assert any(line.startswith("operating_system=") for line in environment_lines)
    assert any(line.startswith("architecture=") for line in environment_lines)

    manifest = evidence_root / "evidence.sha256"
    assert receipt["evidence_manifest_sha256"] == hashlib.sha256(
        manifest.read_bytes()
    ).hexdigest()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        evidence_file = evidence_root / relative
        assert hashlib.sha256(evidence_file.read_bytes()).hexdigest() == expected
        try:
            evidence_text = evidence_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert str(work_root) not in evidence_text
        assert str(evidence_root) not in evidence_text


def test_runner_rejects_incomplete_example_inventory_without_pass_receipt(
    tmp_path: Path,
) -> None:
    completed, _, evidence_root, _, _ = _execute_fixture_runner(
        tmp_path, report_pages=13
    )
    assert completed.returncode != 0
    assert not (evidence_root / "fresh_public_tag_validation.json").exists()
    with (evidence_root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[-1]["case_id"] == "example_builders"
    assert rows[-1]["verdict"] == "FAIL"
