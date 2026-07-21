from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_validation_packet_v0.3.0.py"
SPEC = importlib.util.spec_from_file_location("build_validation_packet_v030", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
packet_builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packet_builder)

REPOSITORY = "https://github.com/elissonnog/mito-overview"
GITHUB_REPOSITORY = "elissonnog/mito-overview"
GITHUB_RUN_ID = 123456
TEST_DOI = "10.5281/zenodo.12345678"


def write_cases(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "case_id",
                "category",
                "input_available",
                "expected_available",
                "verdict",
                "detail",
            ),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def required_pass_rows() -> list[dict[str, str]]:
    return [
        {
            "case_id": case_id,
            "category": "test",
            "input_available": "1",
            "expected_available": "1",
            "verdict": "PASS",
            "detail": "known-answer evidence available",
        }
        for case_id in sorted(packet_builder.REQUIRED_PASS_CASES)
    ]


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def create_release_repo(
    tmp_path: Path,
    version: str = "0.3.0",
    doi: str = TEST_DOI,
) -> tuple[Path, str]:
    repo = tmp_path / "release-repo"
    (repo / "mito_overview").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "mito-overview"',
                f'version = "{version}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "mito_overview" / "__init__.py").write_text(
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )
    (repo / "CITATION.cff").write_text(
        (
            "cff-version: 1.2.0\n"
            "title: mito-overview\n"
            f"version: {version}\n"
            f"doi: {doi}\n"
        ),
        encoding="utf-8",
    )
    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.name", "Validation Test"], repo)
    run(["git", "config", "user.email", "validation@example.org"], repo)
    run(["git", "add", "."], repo)
    run(["git", "commit", "-q", "-m", "release fixture"], repo)
    return repo, run(["git", "rev-parse", "HEAD"], repo)


def write_distribution_artifacts(dist_root: Path, version: str = "0.3.0") -> None:
    dist_root.mkdir(parents=True)
    metadata = f"Metadata-Version: 2.1\nName: mito-overview\nVersion: {version}\n"
    wheel = dist_root / f"mito_overview-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"mito_overview-{version}.dist-info/METADATA", metadata)

    sdist = dist_root / f"mito_overview-{version}.tar.gz"
    payload = metadata.encode("utf-8")
    member = tarfile.TarInfo(f"mito_overview-{version}/PKG-INFO")
    member.size = len(payload)
    with tarfile.open(sdist, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload))


def write_acceptance_evidence(root: Path, commit: str) -> None:
    fresh_case = packet_builder.FRESH_CLONE_CASE_ID
    (root / "commands" / f"{fresh_case}.sh").write_text(
        f"git clone --no-local . fresh-clone\ngit checkout --detach {commit}\npytest -q\n",
        encoding="utf-8",
    )
    (root / "logs" / f"{fresh_case}.log").write_text(
        f"checked_out_commit={commit}\nfresh_clone_validation=PASS\n",
        encoding="utf-8",
    )
    (root / "acceptance" / "fresh_clone.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "evidence_type": "fresh_clone_validation",
                "case_id": fresh_case,
                "verdict": "PASS",
                "repository": REPOSITORY,
                "candidate_commit": commit,
                "checked_out_commit": commit,
                "detached_head": True,
                "clone_worktree_clean": True,
                "command_path": f"commands/{fresh_case}.sh",
                "log_path": f"logs/{fresh_case}.log",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    run_url = f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}"
    (root / "commands" / "github_actions_candidate_commit.sh").write_text(
        f"gh api repos/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}\n",
        encoding="utf-8",
    )
    (root / "logs" / "github_actions_candidate_commit.log").write_text(
        f"github_actions_run_id={GITHUB_RUN_ID}\ngithub_actions_metadata_ingestion=PASS\n",
        encoding="utf-8",
    )
    (root / "acceptance" / "github_actions_run.json").write_text(
        json.dumps(
            {
                "id": GITHUB_RUN_ID,
                "run_attempt": 1,
                "name": packet_builder.EXPECTED_GITHUB_WORKFLOW,
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
                "html_url": run_url,
                "repository": {"full_name": GITHUB_REPOSITORY},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    jobs = []
    for index, expectation in enumerate(packet_builder.EXPECTED_GITHUB_JOBS.values(), start=1):
        job_id = 9000 + index
        jobs.append(
            {
                "id": job_id,
                "run_id": GITHUB_RUN_ID,
                "run_attempt": 1,
                "workflow_name": packet_builder.EXPECTED_GITHUB_WORKFLOW,
                "head_sha": commit,
                "name": expectation["name"],
                "status": "completed",
                "conclusion": "success",
                "labels": [expectation["label"]],
                "html_url": f"{run_url}/job/{job_id}",
            }
        )
    (root / "acceptance" / "github_actions_jobs.json").write_text(
        json.dumps({"total_count": len(jobs), "jobs": jobs}, indent=2) + "\n",
        encoding="utf-8",
    )


def rewrite_json(path: Path, update: Callable[[dict[str, object]], None]) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    update(value)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def create_validation_root(
    tmp_path: Path,
    commit: str,
    *,
    environment_commit: str | None = None,
    archive_doi: str = TEST_DOI,
    dist_version: str = "0.3.0",
) -> tuple[Path, str]:
    root = tmp_path / "validation"
    for relative in (
        "acceptance",
        "commands",
        "logs",
        "expected",
        "public/commands",
        "public/logs",
        "public/observed_normalized/gm11906_default_run1",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    write_acceptance_evidence(root, commit)
    rows = [
        row
        for row in required_pass_rows()
        if row["case_id"] not in packet_builder.ACCEPTANCE_CASE_IDS
    ]
    rows.extend(packet_builder.validate_acceptance_evidence(root, commit, REPOSITORY))
    rows.append(
        {
            "case_id": "optional_documentation_check",
            "category": "optional",
            "input_available": "0",
            "expected_available": "0",
            "verdict": "SKIP",
            "detail": "optional evidence not required for release",
        }
    )
    write_cases(root / "cases.tsv", rows)
    (root / "environment.txt").write_text(
        "\n".join(
            [
                "release_version=v0.3.0",
                f"git_commit={environment_commit or commit}",
                f"repository={REPOSITORY}",
                f"archive_doi={archive_doi}",
                "python=3.12",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "commands" / "unit_known_answer.sh").write_text("pytest -q\n", encoding="utf-8")
    (root / "logs" / "unit_known_answer.log").write_text("tests passed\n", encoding="utf-8")
    (root / "public" / "commands" / "gm11906_default_run1.sh").write_text(
        "run-public-gm11906\n",
        encoding="utf-8",
    )
    (root / "public" / "logs" / "gm11906_default_run1.log").write_text(
        "public run passed\n",
        encoding="utf-8",
    )
    (root / "expected" / "TOY-SR-001.expected_alleles.tsv").write_text(
        "position\talt_count\n1\t1\n",
        encoding="utf-8",
    )
    (root / "public" / "observed_normalized" / "gm11906_default_run1" / "summary.tsv").write_text(
        "metric\tvalue\nstatus\tok\n",
        encoding="utf-8",
    )
    (root / "public" / "filter_profile_results.tsv").write_text(
        "dataset\tprofile\tcandidate_count\nGM11906\tdefault\t1\n",
        encoding="utf-8",
    )
    input_manifest = f"{'a' * 64}  GM11906/downloads/SRR10804585_1.fastq.gz\n"
    (root / "public" / "inputs.sha256").write_text(input_manifest, encoding="utf-8")
    write_distribution_artifacts(root / "dist", dist_version)
    return root, input_manifest


def packet_args(
    validation_root: Path,
    repo_root: Path,
    output_root: Path,
    *,
    asserted_commit: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        validation_root=validation_root,
        packet_root=output_root / "packet",
        zip_path=output_root / "mito-overview-v0.3.0-validation.zip",
        repo_root=repo_root,
        commit=asserted_commit,
        cache_root=None,
        version="v0.3.0",
        repository=REPOSITORY,
        doi=TEST_DOI,
    )


def rewrite_artifact_manifest(packet_root: Path) -> None:
    rows = []
    for path in sorted(packet_root.rglob("*")):
        if not path.is_file() or path.name == "artifacts.sha256":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {path.relative_to(packet_root).as_posix()}")
    (packet_root / "artifacts.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_release_case_gate_accepts_complete_pass_set(tmp_path: Path) -> None:
    path = tmp_path / "cases.tsv"
    rows = required_pass_rows()
    write_cases(path, rows)
    count, verdicts = packet_builder.validate_cases(path)
    assert count == len(rows)
    assert verdicts["PASS"] == len(rows)


def test_release_case_gate_rejects_missing_required_case(tmp_path: Path) -> None:
    path = tmp_path / "cases.tsv"
    rows = required_pass_rows()[1:]
    write_cases(path, rows)
    with pytest.raises(ValueError, match="Required release cases are missing"):
        packet_builder.validate_cases(path)


def test_release_case_gate_rejects_nonpassing_required_case(tmp_path: Path) -> None:
    path = tmp_path / "cases.tsv"
    rows = required_pass_rows()
    rows[0]["verdict"] = "FAIL"
    write_cases(path, rows)
    with pytest.raises(ValueError, match="Required release cases did not pass"):
        packet_builder.validate_cases(path)


@pytest.mark.parametrize("verdict", ["FAIL", "BLOCKED"])
def test_release_case_gate_rejects_any_release_blocker(tmp_path: Path, verdict: str) -> None:
    path = tmp_path / "cases.tsv"
    rows = required_pass_rows()
    rows.append(
        {
            "case_id": "optional_but_failed",
            "category": "optional",
            "input_available": "1",
            "expected_available": "1",
            "verdict": verdict,
            "detail": "must block a release packet",
        }
    )
    write_cases(path, rows)
    with pytest.raises(ValueError, match=f"optional_but_failed={verdict}"):
        packet_builder.validate_cases(path)


def test_release_case_gate_rejects_unsupported_pass(tmp_path: Path) -> None:
    path = tmp_path / "cases.tsv"
    rows = required_pass_rows()
    rows[0]["input_available"] = "0"
    write_cases(path, rows)
    with pytest.raises(ValueError, match="PASS case lacks input or expected evidence"):
        packet_builder.validate_cases(path)


def test_packet_copies_runtime_evidence_and_self_verifies(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, input_manifest = create_validation_root(tmp_path, commit)
    output_root = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation_root, repo, output_root))
    packet = output_root / "packet"

    assert (packet / "inputs.sha256").read_text(encoding="utf-8") == input_manifest
    assert (packet / "commands" / "public" / "gm11906_default_run1.sh").is_file()
    assert (packet / "logs" / "public" / "gm11906_default_run1.log").is_file()
    assert (packet / "acceptance" / "fresh_clone.json").is_file()
    assert (packet / "acceptance" / "github_actions_run.json").is_file()
    assert (packet / "acceptance" / "github_actions_jobs.json").is_file()
    assert len(list((packet / "dist").glob("*.whl"))) == 1
    assert len(list((packet / "dist").glob("*.tar.gz"))) == 1

    identity = json.loads((packet / "release_identity.json").read_text(encoding="utf-8"))
    run_record = json.loads((packet / "run.json").read_text(encoding="utf-8"))
    assert identity["git_commit"] == commit
    assert run_record["git_commit"] == commit
    assert identity["archive_doi"] == TEST_DOI
    assert identity["citation_doi"] == TEST_DOI
    assert identity["environment_archive_doi"] == TEST_DOI
    assert run_record["archive_doi"] == TEST_DOI
    assert set(identity["acceptance_cases"]) == packet_builder.ACCEPTANCE_CASE_IDS
    assert set(identity["metadata_versions"].values()) == {"0.3.0"}
    assert {entry["kind"] for entry in identity["dist_artifacts"]} == {"wheel", "sdist"}

    verification = subprocess.run(
        [str(packet / "verify_bundle.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert verification.returncode == 0, verification.stderr
    assert f"packet at commit {commit}" in verification.stdout
    with zipfile.ZipFile(output_root / "mito-overview-v0.3.0-validation.zip") as archive:
        names = set(archive.namelist())
    assert "release_identity.json" in names
    assert "commands/public/gm11906_default_run1.sh" in names
    assert any(name.startswith("dist/") and name.endswith(".whl") for name in names)


@pytest.mark.parametrize(
    "relative",
    [
        "acceptance/fresh_clone.json",
        "acceptance/github_actions_run.json",
        "acceptance/github_actions_jobs.json",
    ],
)
def test_packet_rejects_missing_acceptance_evidence(tmp_path: Path, relative: str) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    (validation_root / relative).unlink()

    with pytest.raises(FileNotFoundError, match="Required .* evidence not found"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


@pytest.mark.parametrize("target", ["fresh_clone", "workflow", "linux_job", "macos_job"])
def test_packet_rejects_nonpassing_acceptance_evidence(
    tmp_path: Path,
    target: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    if target == "fresh_clone":
        rewrite_json(
            validation_root / "acceptance" / "fresh_clone.json",
            lambda value: value.__setitem__("verdict", "FAIL"),
        )
    elif target == "workflow":
        rewrite_json(
            validation_root / "acceptance" / "github_actions_run.json",
            lambda value: value.__setitem__("conclusion", "failure"),
        )
    else:
        job_index = 0 if target == "linux_job" else 1

        def fail_job(value: dict[str, object]) -> None:
            jobs = value["jobs"]
            assert isinstance(jobs, list) and isinstance(jobs[job_index], dict)
            jobs[job_index]["conclusion"] = "failure"

        rewrite_json(
            validation_root / "acceptance" / "github_actions_jobs.json",
            fail_job,
        )

    with pytest.raises(ValueError, match="nonpassing"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


@pytest.mark.parametrize("target", ["fresh_clone", "workflow", "linux_job", "macos_job"])
def test_packet_rejects_acceptance_evidence_for_another_commit(
    tmp_path: Path,
    target: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    wrong_commit = "f" * 40
    if target == "fresh_clone":
        rewrite_json(
            validation_root / "acceptance" / "fresh_clone.json",
            lambda value: value.__setitem__("checked_out_commit", wrong_commit),
        )
    elif target == "workflow":
        rewrite_json(
            validation_root / "acceptance" / "github_actions_run.json",
            lambda value: value.__setitem__("head_sha", wrong_commit),
        )
    else:
        job_index = 0 if target == "linux_job" else 1

        def change_job_commit(value: dict[str, object]) -> None:
            jobs = value["jobs"]
            assert isinstance(jobs, list) and isinstance(jobs[job_index], dict)
            jobs[job_index]["head_sha"] = wrong_commit

        rewrite_json(
            validation_root / "acceptance" / "github_actions_jobs.json",
            change_job_commit,
        )

    with pytest.raises(ValueError, match="commit mismatch"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


def test_packet_rejects_missing_github_actions_platform_evidence(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)

    def remove_linux_job(value: dict[str, object]) -> None:
        jobs = value["jobs"]
        assert isinstance(jobs, list)
        value["jobs"] = jobs[1:]
        value["total_count"] = len(jobs) - 1

    rewrite_json(
        validation_root / "acceptance" / "github_actions_jobs.json",
        remove_linux_job,
    )
    with pytest.raises(ValueError, match="platform evidence is missing.*linux"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


def test_packet_rejects_mismatched_github_actions_platform_evidence(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)

    def relabel_linux_job(value: dict[str, object]) -> None:
        jobs = value["jobs"]
        assert isinstance(jobs, list) and isinstance(jobs[0], dict)
        jobs[0]["labels"] = ["macos-latest"]

    rewrite_json(
        validation_root / "acceptance" / "github_actions_jobs.json",
        relabel_linux_job,
    )
    with pytest.raises(ValueError, match="platform mismatch for linux"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


def test_packet_rejects_handwritten_acceptance_pass_row(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    with (validation_root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    fresh_row = next(
        row for row in rows if row["case_id"] == packet_builder.FRESH_CLONE_CASE_ID
    )
    fresh_row["detail"] = "claimed PASS without provenance"
    write_cases(validation_root / "cases.tsv", rows)

    with pytest.raises(ValueError, match="Acceptance case does not match validated evidence"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


@pytest.mark.parametrize("relative", ["public/commands", "public/logs", "dist"])
def test_packet_requires_nested_and_distribution_evidence(tmp_path: Path, relative: str) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    target = validation_root / relative
    for path in target.rglob("*"):
        if path.is_file():
            path.unlink()
    with pytest.raises((ValueError, FileNotFoundError), match="missing|contains no|no artifacts"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


def test_packet_requires_runtime_input_manifest(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    (validation_root / "public" / "inputs.sha256").unlink()
    with pytest.raises(FileNotFoundError, match="public/inputs.sha256"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


def test_packet_rejects_environment_commit_not_at_head(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit, environment_commit="f" * 40)
    with pytest.raises(ValueError, match="environment.txt git_commit does not match repository HEAD"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


def test_packet_rejects_environment_doi_mismatch(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(
        tmp_path,
        commit,
        archive_doi="10.5281/zenodo.87654321",
    )
    with pytest.raises(ValueError, match="environment.txt archive_doi does not match"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


def test_packet_rejects_citation_doi_mismatch(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path, doi="10.5281/zenodo.87654321")
    validation_root, _ = create_validation_root(tmp_path, commit)
    with pytest.raises(ValueError, match="CITATION.cff DOI does not match"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


def test_packet_rejects_unreserved_doi(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    args = packet_args(validation_root, repo, tmp_path / "output")
    args.doi = "UNRESERVED"
    with pytest.raises(ValueError, match="canonical reserved Zenodo DOI"):
        packet_builder.build_packet(args)


def test_packet_rejects_arbitrary_commit_assertion(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    args = packet_args(validation_root, repo, tmp_path / "output", asserted_commit="f" * 40)
    with pytest.raises(ValueError, match="--commit does not match repository HEAD"):
        packet_builder.build_packet(args)


def test_packet_explicitly_blocks_stale_release_metadata(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path, version="0.2.1")
    validation_root, _ = create_validation_root(tmp_path, commit)
    with pytest.raises(ValueError, match=r"Release metadata mismatch for v0\.3\.0.*0\.2\.1"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


def test_packet_rejects_distribution_with_wrong_internal_version(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit, dist_version="0.2.1")
    with pytest.raises(ValueError, match="Distribution version mismatch"):
        packet_builder.build_packet(packet_args(validation_root, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    ("target", "expected_error"),
    [
        ("nonpassing", "fresh-clone acceptance mismatch"),
        ("commit", "GitHub Actions linux commit mismatch"),
        ("platform", "GitHub Actions linux platform mismatch"),
        ("missing_platform", "missing or ambiguous GitHub Actions linux evidence"),
    ],
)
def test_verifier_rejects_invalid_acceptance_evidence(
    tmp_path: Path,
    target: str,
    expected_error: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    output_root = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation_root, repo, output_root))
    packet = output_root / "packet"

    if target == "nonpassing":
        rewrite_json(
            packet / "acceptance" / "fresh_clone.json",
            lambda value: value.__setitem__("verdict", "FAIL"),
        )
    else:

        def alter_jobs(value: dict[str, object]) -> None:
            jobs = value["jobs"]
            assert isinstance(jobs, list) and isinstance(jobs[0], dict)
            if target == "commit":
                jobs[0]["head_sha"] = "f" * 40
            elif target == "platform":
                jobs[0]["labels"] = ["macos-latest"]
            else:
                value["jobs"] = jobs[1:]
                value["total_count"] = len(jobs) - 1

        rewrite_json(packet / "acceptance" / "github_actions_jobs.json", alter_jobs)
    rewrite_artifact_manifest(packet)

    verification = subprocess.run(
        [str(packet / "verify_bundle.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert verification.returncode != 0
    assert expected_error in verification.stderr


def test_verifier_rejects_tampered_release_identity(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    output_root = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation_root, repo, output_root))
    packet = output_root / "packet"
    identity_path = packet / "release_identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["git_commit"] = "f" * 40
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    rewrite_artifact_manifest(packet)

    verification = subprocess.run(
        [str(packet / "verify_bundle.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert verification.returncode != 0
    assert "release commit is inconsistent" in verification.stderr


def test_verifier_rejects_tampered_archive_doi(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    output_root = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation_root, repo, output_root))
    packet = output_root / "packet"
    rewrite_json(
        packet / "run.json",
        lambda value: value.__setitem__("archive_doi", "10.5281/zenodo.87654321"),
    )
    rewrite_artifact_manifest(packet)

    verification = subprocess.run(
        [str(packet / "verify_bundle.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert verification.returncode != 0
    assert "archive DOI is inconsistent" in verification.stderr


def test_verifier_rejects_unmanifested_artifact(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation_root, _ = create_validation_root(tmp_path, commit)
    output_root = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation_root, repo, output_root))
    packet = output_root / "packet"
    (packet / "unmanifested.txt").write_text("not audited\n", encoding="utf-8")

    verification = subprocess.run(
        [str(packet / "verify_bundle.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert verification.returncode != 0
    assert "artifact manifest inventory mismatch" in verification.stderr
