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
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_validation_packet_v0.3.0.py"
SPEC = importlib.util.spec_from_file_location("build_validation_packet_v030", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
packet_builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packet_builder)

REPOSITORY = "https://github.com/elissonnog/mito-overview"


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


def create_release_repo(tmp_path: Path, version: str = "0.3.0") -> tuple[Path, str]:
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
        f"cff-version: 1.2.0\ntitle: mito-overview\nversion: {version}\n",
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


def create_validation_root(
    tmp_path: Path,
    commit: str,
    *,
    environment_commit: str | None = None,
    dist_version: str = "0.3.0",
) -> tuple[Path, str]:
    root = tmp_path / "validation"
    for relative in (
        "commands",
        "logs",
        "expected",
        "public/commands",
        "public/logs",
        "public/observed_normalized/gm11906_default_run1",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    rows = required_pass_rows()
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
        doi="UNRESERVED",
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
    assert len(list((packet / "dist").glob("*.whl"))) == 1
    assert len(list((packet / "dist").glob("*.tar.gz"))) == 1

    identity = json.loads((packet / "release_identity.json").read_text(encoding="utf-8"))
    run_record = json.loads((packet / "run.json").read_text(encoding="utf-8"))
    assert identity["git_commit"] == commit
    assert run_record["git_commit"] == commit
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
