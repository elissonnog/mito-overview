from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import zipfile
import zlib
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_validation_packet_v0.3.0.py"
SPEC = importlib.util.spec_from_file_location("build_validation_packet_v030", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
packet_builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packet_builder)

ORACLE_SCRIPT_PATH = ROOT / "scripts" / "assert_public_validation_oracle_v0.3.0.py"
ORACLE_SPEC = importlib.util.spec_from_file_location(
    "assert_public_validation_oracle_v030", ORACLE_SCRIPT_PATH
)
assert ORACLE_SPEC is not None and ORACLE_SPEC.loader is not None
oracle_checker = importlib.util.module_from_spec(ORACLE_SPEC)
sys.modules[ORACLE_SPEC.name] = oracle_checker
ORACLE_SPEC.loader.exec_module(oracle_checker)

SAFE_EXTRACT_PATH = ROOT / "scripts" / "safe_extract_validation_zip.py"
SAFE_SPEC = importlib.util.spec_from_file_location(
    "safe_extract_validation_zip", SAFE_EXTRACT_PATH
)
assert SAFE_SPEC is not None and SAFE_SPEC.loader is not None
safe_extract = importlib.util.module_from_spec(SAFE_SPEC)
SAFE_SPEC.loader.exec_module(safe_extract)

REPOSITORY = "https://github.com/elissonnog/mito-overview"
GITHUB_REPOSITORY = "elissonnog/mito-overview"
GITHUB_RUN_ID = 123456
PULL_REQUEST_NUMBER = 3
PULL_REQUEST_RUN_ID = 123455
PUBLIC_VALIDATION_RUN_ID = 123457
PUBLIC_VALIDATION_ARTIFACT_ID = 7654321
PULL_REQUEST_HEAD_REF = "codex/preprint-hardening-v0.3.0"


def audit_comment_body(payload: dict[str, object]) -> str:
    return (
        f"{packet_builder.READ_ONLY_AUDIT_MARKER}\n"
        "```json\n"
        f"{json.dumps(payload, indent=2)}\n"
        "```"
    )


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


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


def create_release_repo(tmp_path: Path, version: str = "0.3.0") -> tuple[Path, str]:
    repo = tmp_path / "release-repo"
    (repo / "mito_overview").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "mito-overview"',
                f'version = "{version}"',
                'license = "MIT"',
                'authors = [{name = "Elisson Lopes"}, {name = "Xiaowu Gai"}]',
                "",
                "[project.urls]",
                f'Repository = "{REPOSITORY}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "mito_overview" / "__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    (repo / "README.md").write_text(
        f"# mito-overview\n\nVersion `{version}` defines the workflow/resource release described here.\n",
        encoding="utf-8",
    )
    (repo / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## v{version}\n- release fixture\n",
        encoding="utf-8",
    )
    # Deliberately no release date, DOI, manuscript, or archive metadata.
    (repo / "CITATION.cff").write_text(
        (
            "cff-version: 1.2.0\n"
            "title: mito-overview\n"
            "authors:\n"
            "  - family-names: Lopes\n"
            "    given-names: Elisson\n"
            "  - family-names: Gai\n"
            "    given-names: Xiaowu\n"
            f"version: {version}\n"
            "license: MIT\n"
            f"repository-code: {REPOSITORY}\n"
        ),
        encoding="utf-8",
    )
    oracle = repo / packet_builder.FROZEN_ORACLE_REPOSITORY_PATH
    oracle.parent.mkdir(parents=True, exist_ok=True)
    oracle.write_bytes(
        (ROOT / packet_builder.FROZEN_ORACLE_REPOSITORY_PATH).read_bytes()
    )
    source_metadata = repo / packet_builder.GM11906_SOURCE_METADATA_REPOSITORY_PATH
    source_metadata.parent.mkdir(parents=True, exist_ok=True)
    source_metadata.write_bytes(
        (ROOT / packet_builder.GM11906_SOURCE_METADATA_REPOSITORY_PATH).read_bytes()
    )
    locks = repo / "locks"
    locks.mkdir()
    for platform_id in packet_builder.RESOLVED_CI_PLATFORMS:
        name = f"environment-{platform_id}.yml"
        (locks / name).write_bytes((ROOT / "locks" / name).read_bytes())
    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.name", "Validation Test"], repo)
    run(["git", "config", "user.email", "validation@example.org"], repo)
    run(["git", "add", "."], repo)
    run(["git", "commit", "-q", "-m", "base fixture"], repo)
    run(["git", "branch", "-M", "main"], repo)
    run(["git", "checkout", "-q", "-b", PULL_REQUEST_HEAD_REF], repo)
    (repo / "RELEASE_CANDIDATE").write_text("v0.3.0\n", encoding="utf-8")
    run(["git", "add", "RELEASE_CANDIDATE"], repo)
    run(["git", "commit", "-q", "-m", "release fixture"], repo)
    run(["git", "checkout", "-q", "main"], repo)
    run(
        [
            "git",
            "merge",
            "-q",
            "--no-ff",
            PULL_REQUEST_HEAD_REF,
            "-m",
            "Merge release fixture",
        ],
        repo,
    )
    return repo, run(["git", "rev-parse", "HEAD"], repo)


@pytest.mark.parametrize(
    ("relative_path", "old", "new", "expected_message"),
    (
        (
            "README.md",
            "Version `0.3.0`",
            "Version `0.3.1`",
            "README.md=0.3.1",
        ),
        (
            "CHANGELOG.md",
            "## v0.3.0",
            "## v0.3.1",
            "CHANGELOG.md=0.3.1",
        ),
    ),
)
def test_release_metadata_rejects_readme_or_changelog_version_drift(
    tmp_path: Path,
    relative_path: str,
    old: str,
    new: str,
    expected_message: str,
) -> None:
    repo, _ = create_release_repo(tmp_path)
    path = repo / relative_path
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    with pytest.raises(ValueError, match=re.escape(expected_message)):
        packet_builder.read_release_metadata(repo)


def write_distribution_artifacts(dist_root: Path, version: str = "0.3.0") -> None:
    dist_root.mkdir(parents=True)
    metadata = f"Metadata-Version: 2.1\nName: mito-overview\nVersion: {version}\n"
    wheel = dist_root / f"mito_overview-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"mito_overview-{version}.dist-info/METADATA", metadata)
    sdist = dist_root / f"mito_overview-{version}.tar.gz"
    payload = metadata.encode()
    member = tarfile.TarInfo(f"mito_overview-{version}/PKG-INFO")
    member.size = len(payload)
    with tarfile.open(sdist, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload))


def replace_distribution_with_same_identity(path: Path) -> None:
    """Replace archive bytes while preserving package name and version metadata."""

    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("replacement-marker.txt", "different wheel bytes\n")
        return
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            pkg_info = next(
                member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")
            )
            handle = archive.extractfile(pkg_info)
            assert handle is not None
            metadata = handle.read()
        with tarfile.open(path, "w:gz") as archive:
            pkg_info.size = len(metadata)
            archive.addfile(pkg_info, io.BytesIO(metadata))
            payload = b"different sdist bytes\n"
            marker = tarfile.TarInfo("mito_overview-0.3.0/replacement-marker.txt")
            marker.size = len(payload)
            archive.addfile(marker, io.BytesIO(payload))
        return
    raise AssertionError(f"Unsupported distribution fixture: {path}")


@pytest.mark.parametrize(
    "mutation",
    ("extra_file", "extra_wheel", "nested_file", "renamed_wheel", "symlink_wheel"),
)
def test_distribution_inventory_requires_exact_canonical_files(
    tmp_path: Path, mutation: str
) -> None:
    dist_root = tmp_path / "dist"
    write_distribution_artifacts(dist_root)
    wheel = dist_root / "mito_overview-0.3.0-py3-none-any.whl"
    if mutation == "extra_file":
        (dist_root / "notes.txt").write_text("unexpected\n", encoding="ascii")
    elif mutation == "extra_wheel":
        shutil.copy2(wheel, dist_root / "mito_overview-0.3.0-py2-none-any.whl")
    elif mutation == "nested_file":
        nested = dist_root / "nested"
        nested.mkdir()
        (nested / "payload.txt").write_text("unexpected\n", encoding="ascii")
    elif mutation == "renamed_wheel":
        wheel.rename(dist_root / "mito-overview-0.3.0-py3-none-any.whl")
    elif mutation == "symlink_wheel":
        external = tmp_path / "external.whl"
        shutil.copy2(wheel, external)
        wheel.unlink()
        wheel.symlink_to(external)
    else:
        raise AssertionError(mutation)

    with pytest.raises((FileNotFoundError, ValueError), match="Distribution"):
        packet_builder.validate_distributions(
            dist_root,
            packet_builder.EXPECTED_PACKAGE_NAME,
            packet_builder.EXPECTED_RELEASE_VERSION.removeprefix("v"),
        )


def provenance_record(name: str, content: bytes | None = None) -> dict[str, object]:
    payload = content if content is not None else name.encode()
    return {
        "name": name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def file_provenance_record(
    path: Path,
    source_name: str,
    *,
    include_md5: bool = False,
) -> dict[str, object]:
    record = provenance_record(source_name, path.read_bytes())
    if include_md5:
        record["md5"] = hashlib.md5(path.read_bytes()).hexdigest()
    return record


def frozen_input_record(filename: str) -> dict[str, object]:
    row = next(
        item for item in packet_builder.FROZEN_PUBLIC_INPUTS if item["filename"] == filename
    )
    return {
        "name": filename,
        "bytes": int(row["bytes"]),
        "md5": row["md5"],
        "sha256": row["sha256"],
    }


def write_public_provenance(public_root: Path) -> None:
    paths = {
        key: public_root / str(spec["source"])
        for key, spec in packet_builder.PUBLIC_PROVENANCE_FILES.items()
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    paths["shortread_source_metadata"].write_bytes(
        (ROOT / packet_builder.GM11906_SOURCE_METADATA_REPOSITORY_PATH).read_bytes()
    )
    source_metadata = json.loads(
        paths["shortread_source_metadata"].read_text(encoding="utf-8")
    )
    source_metadata_sha256 = hashlib.sha256(
        paths["shortread_source_metadata"].read_bytes()
    ).hexdigest()
    source_metadata_by_run = {
        record["run_accession"]: record for record in source_metadata["records"]
    }

    short = {
        "schema_version": "1.0",
        "provenance_type": "public_alignment",
        "dataset_id": "GM11906_pooled_scATAC",
        "alignment": provenance_record("GM11906_MERRF_shortread.mt.bam"),
        "alignment_index": provenance_record("GM11906_MERRF_shortread.mt.bam.bai"),
        "reference": provenance_record("GM11906_reference.fa"),
        "reference_index": provenance_record("GM11906_reference.fa.fai"),
        "public_inputs": [
            {
                **frozen_input_record("SRR10804585_1.fastq.gz"),
                "label": "SRR10804585_R1",
            },
            {
                **frozen_input_record("SRR10804585_2.fastq.gz"),
                "label": "SRR10804585_R2",
            },
            {
                **frozen_input_record("SRR10804590_1.fastq.gz"),
                "label": "SRR10804590_R1",
            },
            {
                **frozen_input_record("SRR10804590_2.fastq.gz"),
                "label": "SRR10804590_R2",
            },
            {
                **frozen_input_record("SRR10804657_1.fastq.gz"),
                "label": "SRR10804657_R1",
            },
            {
                **frozen_input_record("SRR10804657_2.fastq.gz"),
                "label": "SRR10804657_R2",
            },
            {
                "name": "GM11906_MERRF_R1.fastq.gz",
                "bytes": sum(
                    frozen_input_record(name)["bytes"]
                    for name in (
                        "SRR10804585_1.fastq.gz",
                        "SRR10804590_1.fastq.gz",
                        "SRR10804657_1.fastq.gz",
                    )
                ),
                "md5": "1" * 32,
                "sha256": "2" * 64,
                "label": "combined_R1",
            },
            {
                "name": "GM11906_MERRF_R2.fastq.gz",
                "bytes": sum(
                    frozen_input_record(name)["bytes"]
                    for name in (
                        "SRR10804585_2.fastq.gz",
                        "SRR10804590_2.fastq.gz",
                        "SRR10804657_2.fastq.gz",
                    )
                ),
                "md5": "3" * 32,
                "sha256": "4" * 64,
                "label": "combined_R2",
            },
        ],
        "derivation": packet_builder.PUBLIC_ALIGNMENT_DERIVATIONS[
            "GM11906_pooled_scATAC"
        ],
    }
    paths["shortread_alignment"].write_text(
        json.dumps(short, indent=2) + "\n", encoding="utf-8"
    )
    with paths["shortread_source_libraries"].open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fields = (
            "run_accession",
            "geo_accession",
            "source_sample_id",
            "library_strategy",
            "library_unit",
            "combination_role",
            "source_record_url",
            "metadata_snapshot_sha256",
            "metadata_record_sha256",
        )
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for run_accession in ("SRR10804585", "SRR10804590", "SRR10804657"):
            record = source_metadata_by_run[run_accession]
            record_sha256 = hashlib.sha256(
                json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("ascii")
            ).hexdigest()
            writer.writerow(
                {
                    "run_accession": run_accession,
                    "geo_accession": record["geo_accession"],
                    "source_sample_id": record["cell_line"],
                    "library_strategy": record["library_strategy"],
                    "library_unit": "single_cell_library",
                    "combination_role": "pooled_pseudobulk",
                    "source_record_url": (
                        "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc="
                        + record["geo_accession"]
                    ),
                    "metadata_snapshot_sha256": source_metadata_sha256,
                    "metadata_record_sha256": record_sha256,
                }
            )

    paths["selected_query_names"].write_bytes(
        (
            ROOT
            / "examples/public_validation/GM12878_ONT_longread/provenance/"
            "GM12878_ONT_longread.selected_qnames.txt"
        ).read_bytes()
    )
    source_fastq = frozen_input_record("SRR18110025.fastq.gz")
    subset_fastq = dict(packet_builder.FROZEN_GM12878_SUBSET_FASTQ_RECORD)
    selected_names = file_provenance_record(
        paths["selected_query_names"],
        "SRR18110025.deterministic-qnames-1000.fastq.gz.selected_qnames.txt",
        include_md5=True,
    )
    subset = {
        "schema_version": "1.0",
        "provenance_type": "deterministic_fastq_query_name_subset",
        "dataset_id": "GM12878_SRR18110025_ONT",
        "source_fastq": source_fastq,
        "subset_fastq": subset_fastq,
        "selected_query_names": selected_names,
        "selection": dict(packet_builder.FROZEN_GM12878_SUBSET_SELECTION),
    }
    paths["longread_subset"].write_text(
        json.dumps(subset, indent=2) + "\n", encoding="utf-8"
    )
    subset_record = file_provenance_record(
        paths["longread_subset"],
        "SRR18110025.deterministic-qnames-1000.fastq.gz.provenance.json",
        include_md5=True,
    )
    long = {
        "schema_version": "1.0",
        "provenance_type": "public_alignment",
        "dataset_id": "GM12878_SRR18110025_ONT_reduced_qn1000",
        "alignment": provenance_record("GM12878_ONT_longread.mt.bam"),
        "alignment_index": provenance_record("GM12878_ONT_longread.mt.bam.bai"),
        "reference": provenance_record("NC_012920.1.fa"),
        "reference_index": provenance_record("NC_012920.1.fa.fai"),
        "public_inputs": [
            {**source_fastq, "label": "SRR18110025_full_fastq"},
            {**subset_fastq, "label": "deterministic_subset_fastq"},
            {**subset_record, "label": "deterministic_subset_manifest"},
            {**selected_names, "label": "selected_query_names"},
        ],
        "derivation": packet_builder.PUBLIC_ALIGNMENT_DERIVATIONS[
            "GM12878_SRR18110025_ONT_reduced_qn1000"
        ],
    }
    paths["longread_alignment"].write_text(
        json.dumps(long, indent=2) + "\n", encoding="utf-8"
    )


def write_resolved_ci_environments(root: Path, repo: Path, commit: str) -> None:
    evidence_root = root / packet_builder.RESOLVED_CI_ENVIRONMENTS_RELATIVE
    for platform_id in packet_builder.RESOLVED_CI_PLATFORMS:
        platform_root = evidence_root / platform_id
        platform_root.mkdir(parents=True, exist_ok=True)
        files = {
            f"conda-{platform_id}.explicit.txt": (
                f"# platform: {platform_id}\n@EXPLICIT\n"
                "https://example.invalid/pinned-package.conda\n"
            ).encode("utf-8"),
            f"pip-{platform_id}.txt": b"mito-overview==0.3.0\n",
            f"environment-{platform_id}.yml": (
                repo / "locks" / f"environment-{platform_id}.yml"
            ).read_bytes(),
            f"python-{platform_id}.txt": b"Python 3.12.13\n",
        }
        evidence_files = {}
        for name, payload in files.items():
            (platform_root / name).write_bytes(payload)
            evidence_files[name] = {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        manifest_payload = "".join(
            f"{name}\t{evidence_files[name]['sha256']}\t"
            f"{evidence_files[name]['size_bytes']}\n"
            for name in sorted(evidence_files)
        ).encode("utf-8")
        runner = packet_builder.RESOLVED_CI_RUNNER_IDENTITY[platform_id]
        record = {
            "schema_version": "2.0",
            "git_commit": commit,
            "github_run_id": GITHUB_RUN_ID,
            "job": "Unit and synthetic tests",
            "platform_id": platform_id,
            "runner_os": runner["runner_os"],
            "runner_arch": runner["runner_arch"],
            "machine": packet_builder.PUBLIC_RUNTIME_PLATFORMS[platform_id]["machine"],
            "python": "3.12.13",
            "resolved_environment": True,
            "evidence_files": evidence_files,
            "evidence_manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
            "source_lock_sha256": evidence_files[
                f"environment-{platform_id}.yml"
            ]["sha256"],
        }
        (platform_root / f"platform-{platform_id}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def write_acceptance_evidence(
    root: Path,
    repo: Path,
    commit: str,
    *,
    include_public_evidence: bool = True,
) -> None:
    parent_fields = run(
        ["git", "rev-list", "--parents", "-n", "1", commit], repo
    ).split()
    assert len(parent_fields) == 3
    base_sha, head_sha = parent_fields[1:]
    final_tree = run(["git", "rev-parse", f"{commit}^{{tree}}"], repo)
    repository_api = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
    repository_object = {
        "full_name": GITHUB_REPOSITORY,
        "html_url": REPOSITORY,
        "url": repository_api,
    }
    distributions: list[dict[str, object]] = []
    if (root / "dist").is_dir():
        distributions = packet_builder.validate_distributions(
            root / "dist", "mito-overview", "0.3.0"
        )
        for artifact in distributions:
            artifact["direct_url_archive_sha256"] = artifact["sha256"]

    fresh_case = packet_builder.FRESH_CLONE_CASE_ID
    (root / "commands" / f"{fresh_case}.sh").write_text(
        f"git clone {REPOSITORY}.git\ngit checkout --detach {commit}\n",
        encoding="utf-8",
    )
    (root / "logs" / f"{fresh_case}.log").write_text(
        f"checked_out_commit={commit}\nfresh_clone_validation=PASS\n",
        encoding="utf-8",
    )
    (root / "acceptance" / "fresh_clone.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "validation_profile": "github_release_validation_v1",
                "evidence_type": "fresh_clone_validation",
                "case_id": fresh_case,
                "verdict": "PASS",
                "repository": REPOSITORY,
                "source_remote": REPOSITORY + ".git",
                "candidate_commit": commit,
                "checked_out_commit": commit,
                "public_main_commit": commit,
                "detached_head": True,
                "clone_worktree_clean": True,
                "public_https_clone": True,
                "isolated_home": True,
                "isolated_tmpdir": True,
                "built_wheel": True,
                "built_sdist": True,
                "installed_wheel": True,
                "installed_sdist": True,
                "separate_distribution_environments": True,
                "executed_outside_checkout": True,
                "distributions": distributions,
                "command_path": f"commands/{fresh_case}.sh",
                "log_path": f"logs/{fresh_case}.log",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    pull_api_url = f"{repository_api}/pulls/{PULL_REQUEST_NUMBER}"
    pull_html_url = f"{REPOSITORY}/pull/{PULL_REQUEST_NUMBER}"
    issue_api_url = f"{repository_api}/issues/{PULL_REQUEST_NUMBER}"
    (root / "acceptance" / "pull_request.json").write_text(
        json.dumps(
            {
                "url": pull_api_url,
                "html_url": pull_html_url,
                "issue_url": issue_api_url,
                "comments_url": f"{issue_api_url}/comments",
                "number": PULL_REQUEST_NUMBER,
                "state": "closed",
                "merged": True,
                "merged_at": "2026-07-21T12:00:00Z",
                "merge_commit_sha": commit,
                "base": {
                    "ref": "main",
                    "sha": base_sha,
                    "repo": repository_object,
                },
                "head": {
                    "ref": PULL_REQUEST_HEAD_REF,
                    "sha": head_sha,
                    "repo": repository_object,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    comments = []
    for index, role in enumerate(packet_builder.READ_ONLY_AUDIT_CASE_IDS, start=1):
        comment_id = 7000 + index
        payload = {
            "schema_version": "1.1",
            "review_method": "read_only_agent_role_audit",
            "audit_instance_id": f"00000000-0000-4000-8000-{index:012d}",
            "role": role,
            "reviewed_commit": head_sha,
            "reviewed_tree": final_tree,
            "verdict": "PASS",
            "unresolved_blockers": 0,
            "summary": f"{role} read-only checks passed.",
        }
        comments.append(
            {
                "id": comment_id,
                "url": f"{repository_api}/issues/comments/{comment_id}",
                "html_url": f"{pull_html_url}#issuecomment-{comment_id}",
                "issue_url": issue_api_url,
                "user": {
                    "login": "elissonnog",
                    "html_url": "https://github.com/elissonnog",
                },
                "author_association": "OWNER",
                "created_at": f"2026-07-21T10:0{index}:00Z",
                "updated_at": f"2026-07-21T10:0{index}:00Z",
                "body": audit_comment_body(payload),
            }
        )
    (root / "acceptance" / "pull_request_comments.json").write_text(
        json.dumps(comments, indent=2) + "\n",
        encoding="utf-8",
    )

    run_url = f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}"
    api_url = f"{repository_api}/actions/runs/{GITHUB_RUN_ID}"
    (root / "commands" / "github_actions_candidate_commit.sh").write_text(
        f"gh api repos/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}\n",
        encoding="utf-8",
    )
    (root / "logs" / "github_actions_candidate_commit.log").write_text(
        "github_actions_metadata_ingestion=PASS\n", encoding="utf-8"
    )
    (root / "acceptance" / "github_actions_run.json").write_text(
        json.dumps(
            {
                "id": GITHUB_RUN_ID,
                "run_attempt": 1,
                "name": packet_builder.EXPECTED_GITHUB_WORKFLOW,
                "event": "push",
                "head_branch": packet_builder.EXPECTED_GITHUB_BRANCH,
                "path": packet_builder.EXPECTED_GITHUB_WORKFLOW_PATH,
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
                "html_url": run_url,
                "url": api_url,
                "jobs_url": f"{api_url}/jobs",
                "repository": {"full_name": GITHUB_REPOSITORY},
                "head_repository": {"full_name": GITHUB_REPOSITORY},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    jobs = []
    for index, expectation in enumerate(
        packet_builder.EXPECTED_GITHUB_JOBS.values(), start=1
    ):
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
                "url": f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/jobs/{job_id}",
                "run_url": api_url,
            }
        )
    (root / "acceptance" / "github_actions_jobs.json").write_text(
        json.dumps({"total_count": len(jobs), "jobs": jobs}, indent=2) + "\n",
        encoding="utf-8",
    )
    write_resolved_ci_environments(root, repo, commit)

    pr_run_url = (
        f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{PULL_REQUEST_RUN_ID}"
    )
    pr_api_url = f"{repository_api}/actions/runs/{PULL_REQUEST_RUN_ID}"
    (root / "acceptance" / "pull_request_github_actions_run.json").write_text(
        json.dumps(
            {
                "id": PULL_REQUEST_RUN_ID,
                "run_attempt": 1,
                "name": packet_builder.EXPECTED_GITHUB_WORKFLOW,
                "event": "pull_request",
                "head_branch": PULL_REQUEST_HEAD_REF,
                "path": packet_builder.EXPECTED_GITHUB_WORKFLOW_PATH,
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": "success",
                "html_url": pr_run_url,
                "url": pr_api_url,
                "jobs_url": f"{pr_api_url}/jobs",
                "repository": {"full_name": GITHUB_REPOSITORY},
                "head_repository": {"full_name": GITHUB_REPOSITORY},
                "pull_requests": [
                    {
                        "number": PULL_REQUEST_NUMBER,
                        "url": pull_api_url,
                        "head": {
                            "ref": PULL_REQUEST_HEAD_REF,
                            "sha": head_sha,
                            "repo": {
                                "name": "mito-overview",
                                "url": repository_api,
                            },
                        },
                        "base": {
                            "ref": "main",
                            "sha": base_sha,
                            "repo": {
                                "name": "mito-overview",
                                "url": repository_api,
                            },
                        },
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    pr_jobs = []
    for index, expectation in enumerate(
        packet_builder.EXPECTED_GITHUB_JOBS.values(), start=1
    ):
        job_id = 8000 + index
        pr_jobs.append(
            {
                "id": job_id,
                "run_id": PULL_REQUEST_RUN_ID,
                "run_attempt": 1,
                "workflow_name": packet_builder.EXPECTED_GITHUB_WORKFLOW,
                "head_sha": head_sha,
                "name": expectation["name"],
                "status": "completed",
                "conclusion": "success",
                "labels": [expectation["label"]],
                "html_url": f"{pr_run_url}/job/{job_id}",
                "url": f"{repository_api}/actions/jobs/{job_id}",
                "run_url": pr_api_url,
            }
        )
    (root / "acceptance" / "pull_request_github_actions_jobs.json").write_text(
        json.dumps({"total_count": len(pr_jobs), "jobs": pr_jobs}, indent=2) + "\n",
        encoding="utf-8",
    )

    if not include_public_evidence:
        return

    public_acceptance = root / "acceptance" / "ubuntu_public_validation"
    public_acceptance.mkdir(parents=True)
    public_run_url = (
        f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/"
        f"{PUBLIC_VALIDATION_RUN_ID}"
    )
    public_api_url = (
        f"{repository_api}/actions/runs/{PUBLIC_VALIDATION_RUN_ID}"
    )
    (public_acceptance / "workflow_run.json").write_text(
        json.dumps(
            {
                "id": PUBLIC_VALIDATION_RUN_ID,
                "run_attempt": 1,
                "name": packet_builder.EXPECTED_PUBLIC_VALIDATION_WORKFLOW,
                "event": "workflow_dispatch",
                "head_branch": "main",
                "path": packet_builder.EXPECTED_PUBLIC_VALIDATION_WORKFLOW_PATH,
                "head_sha": commit,
                "status": "completed",
                "conclusion": "success",
                "html_url": public_run_url,
                "url": public_api_url,
                "jobs_url": f"{public_api_url}/jobs",
                "repository": repository_object,
                "head_repository": repository_object,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    artifact_api = (
        f"{repository_api}/actions/artifacts/{PUBLIC_VALIDATION_ARTIFACT_ID}"
    )
    (public_acceptance / "artifacts.json").write_text(
        json.dumps(
            {
                "total_count": 1,
                "artifacts": [
                    {
                        "id": PUBLIC_VALIDATION_ARTIFACT_ID,
                        "name": (
                            f"public-validation-derived-{commit}-"
                            f"{PUBLIC_VALIDATION_RUN_ID}"
                        ),
                        "expired": False,
                        "url": artifact_api,
                        "archive_download_url": f"{artifact_api}/zip",
                        "workflow_run": {"id": PUBLIC_VALIDATION_RUN_ID},
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    artifact_root = public_acceptance / "artifact"
    ubuntu_results = artifact_root / "results"
    artifact_environment = artifact_root / "environment"
    artifact_environment.mkdir(parents=True)
    ubuntu_results.mkdir(parents=True)
    for name in packet_builder.CROSS_PLATFORM_SCIENTIFIC_TOP_LEVEL:
        shutil.copy2(root / "public" / name, ubuntu_results / name)
    shutil.copytree(
        root / "public" / "observed_normalized",
        ubuntu_results / "observed_normalized",
    )
    shutil.copytree(
        root / "public" / packet_builder.PUBLIC_CONTRACTS_PACKET_PATH,
        ubuntu_results / packet_builder.PUBLIC_CONTRACTS_PACKET_PATH,
    )
    staged_outputs = ubuntu_results / "report_artifacts" / "outputs"
    for inventory in sorted(
        (root / "public" / "observed_normalized").rglob(
            "visual_artifact_inventory.tsv"
        )
    ):
        case_id = inventory.parent.name
        shutil.copytree(
            root / "public" / "outputs" / case_id,
            staged_outputs / case_id,
        )
    shutil.copytree(root / "public" / "environment", ubuntu_results / "environment")
    write_tsv(
        ubuntu_results / "environment/network_isolation.tsv",
        ("field", "value"),
        [
            ["schema_version", "1.0"],
            ["platform", "Linux/x86_64"],
            ["isolation_method", "linux_unshare_network_namespace"],
            ["isolation_scope", "process_tree"],
            ["parent_loopback_control", "reachable"],
            ["isolated_loopback_probe", "blocked"],
            ["probe_target", "parent_loopback_listener"],
            ["probe_error", "PermissionError:1"],
            ["invoking_uid", "1001"],
            ["invoking_gid", "1001"],
            ["child_uid", "1001"],
            ["child_gid", "1001"],
            ["network_isolation_verdict", "PASS"],
        ],
    )
    linux_runtime = json.loads(
        (ubuntu_results / "environment/runtime_versions.json").read_text(
            encoding="utf-8"
        )
    )
    linux_runtime.update(
        {
            "platform_id": "linux-64",
            "system": "Linux",
            "machine": "x86_64",
            "python_executable": "/opt/validation-env/bin/python",
            "mito_overview_module": (
                "/opt/validation-env/lib/python3.12/site-packages/"
                "mito_overview/__init__.py"
            ),
        }
    )
    (ubuntu_results / "environment/runtime_versions.json").write_text(
        json.dumps(linux_runtime, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (ubuntu_results / "environment/conda-explicit.txt").write_text(
        "# platform: linux-64\n@EXPLICIT\nhttps://example.invalid/pinned-package.conda\n",
        encoding="utf-8",
    )
    (artifact_environment / "identity.txt").write_text(
        (
            f"repository={REPOSITORY}\n"
            f"git_commit={commit}\n"
            "runner_os=Linux\n"
            "runner_arch=X64\n"
            "runner_image=ubuntu24\n"
            "runner_image_version=fixture\n"
            f"github_run_id={PUBLIC_VALIDATION_RUN_ID}\n"
        ),
        encoding="utf-8",
    )
    artifact_files = sorted(
        path
        for path in artifact_root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    (artifact_root / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
            f"./{path.relative_to(artifact_root).as_posix()}\n"
            for path in artifact_files
        ),
        encoding="utf-8",
    )

    local_public = root / "public"
    scientific_paths = sorted(
        packet_builder.public_scientific_paths(local_public),
        key=lambda path: path.as_posix(),
    )
    visual_paths = sorted(
        packet_builder.public_visual_paths(local_public),
        key=lambda path: path.as_posix(),
    )
    comparison_rows = []
    for relative in scientific_paths:
        digest = hashlib.sha256(
            (local_public / Path(*relative.parts)).read_bytes()
        ).hexdigest()
        comparison_rows.append(
            [
                "normalized_scientific_table",
                relative.as_posix(),
                digest,
                digest,
                "PASS",
                "byte-identical normalized content",
            ]
        )
    comparison_rows.extend(
        [
            "visual_structure",
            relative.as_posix(),
            "not_compared",
            "not_compared",
            "PASS",
            "path/type/dimensions/integrity; pixel hashes are not cross-platform gates",
        ]
        for relative in visual_paths
    )
    write_tsv(
        root / "acceptance" / "cross_platform_comparison.tsv",
        (
            "evidence_type",
            "relative_path",
            "macos_sha256",
            "ubuntu_sha256",
            "verdict",
            "comparison",
        ),
        comparison_rows,
    )
    (root / "acceptance" / "cross_platform_public_reproduction.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "validation_profile": "github_release_validation_v1",
                "evidence_type": "cross_platform_public_reproduction",
                "verdict": "PASS",
                "git_commit": commit,
                "ubuntu_public_validation_run_id": PUBLIC_VALIDATION_RUN_ID,
                "macos_platform": "osx-arm64",
                "ubuntu_platform": "linux-64",
                "normalized_scientific_tables_compared": len(scientific_paths),
                "visual_inventories_compared": len(visual_paths),
                "comparison_table": "cross_platform_comparison.tsv",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png(
    path: Path,
    rgb: tuple[int, int, int] = (0, 0, 0),
    *,
    width: int = 1,
    height: int = 1,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    pixels = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(pixels))
        + png_chunk(b"IEND", b"")
    )


def write_tsv(path: Path, header: tuple[str, ...], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def frozen_oracle_rows() -> list[dict[str, str]]:
    path = ROOT / packet_builder.FROZEN_ORACLE_REPOSITORY_PATH
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            {key: "" if value in (None, ".") else value for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]


def write_public_input_evidence(public_root: Path) -> None:
    raw_manifest = public_root / packet_builder.RAW_INPUTS_PACKET_PATH
    with raw_manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=packet_builder.PUBLIC_INPUT_MANIFEST_HEADER,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(packet_builder.FROZEN_PUBLIC_INPUTS)
    assert hashlib.sha256(raw_manifest.read_bytes()).hexdigest() == (
        packet_builder.FROZEN_RAW_INPUT_MANIFEST_SHA256
    )
    (public_root / packet_builder.CACHE_SEAL_PACKET_PATH).write_text(
        f"{packet_builder.FROZEN_RAW_INPUT_MANIFEST_SHA256}  raw_inputs.tsv\n",
        encoding="utf-8",
    )
    (public_root / "inputs.sha256").write_text(
        packet_builder.canonical_public_input_hashes(
            [dict(row) for row in packet_builder.FROZEN_PUBLIC_INPUTS]
        ),
        encoding="utf-8",
    )


def write_public_oracle_evidence(public_root: Path) -> None:
    oracle_rows = frozen_oracle_rows()
    profile_rows = []
    for row in oracle_rows:
        profile_rows.append(
            [
                f"{row['dataset'].lower()}_{row['profile']}",
                row["dataset"],
                row["profile"],
                row["min_base_quality"],
                row["min_mapping_quality"],
                row["min_read_mean_quality"],
                row["candidate_sites"],
                row["accepted_observations"],
                row["excluded_observations"],
                row["m8344_present"],
                row["m8344_alt_fraction"],
            ]
        )
    write_tsv(
        public_root / "filter_profile_results.tsv",
        (
            "case_id",
            "dataset",
            "profile",
            "min_base_quality",
            "min_mapping_quality",
            "min_read_mean_quality",
            "candidate_sites",
            "accepted_observations",
            "excluded_observations",
            "m8344_A_G_present",
            "m8344_A_G_alt_allele_fraction",
        ),
        profile_rows,
    )
    required = packet_builder.expected_oracle_assertions(oracle_rows)
    write_tsv(
        public_root / packet_builder.ORACLE_ASSERTIONS_PACKET_PATH,
        ("assertion_id", "verdict", "expected", "observed", "detail"),
        [
            [assertion_id, "PASS", expected, expected, "fixture exact oracle"]
            for assertion_id, expected in sorted(required.items())
        ],
    )


def write_public_environment(public_root: Path) -> None:
    environment = public_root / "environment"
    environment.mkdir(parents=True, exist_ok=True)
    write_tsv(
        environment / "network_isolation.tsv",
        ("field", "value"),
        [
            ["schema_version", "1.0"],
            ["platform", "Darwin/arm64"],
            ["isolation_method", "macos_sandbox_exec_deny_network"],
            ["isolation_scope", "process_tree"],
            ["parent_loopback_control", "reachable"],
            ["isolated_loopback_probe", "blocked"],
            ["probe_target", "parent_loopback_listener"],
            ["probe_error", "PermissionError:1"],
            ["invoking_uid", "501"],
            ["invoking_gid", "20"],
            ["child_uid", "501"],
            ["child_gid", "20"],
            ["network_isolation_verdict", "PASS"],
        ],
    )
    runtime = {
        "schema_version": "1.0",
        "platform_id": "osx-arm64",
        "system": "Darwin",
        "machine": "arm64",
        "python": "3.12.13",
        "python_executable": "/private/tmp/validation-env/bin/python",
        "mito_overview_module": (
            "/private/tmp/validation-env/lib/python3.12/site-packages/"
            "mito_overview/__init__.py"
        ),
        "packages": packet_builder.EXPECTED_RUNTIME_PACKAGES,
        "samtools": "samtools 1.23.1",
        "htslib": "Using htslib 1.23.1",
        "minimap2": "2.31-r1302",
        "bwa": "0.7.19-r1273",
        "threads": 4,
        "installed_distribution_required": True,
    }
    (environment / "runtime_versions.json").write_text(
        json.dumps(runtime, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (environment / "pip-freeze.txt").write_text(
        "".join(
            f"{name}=={version}\n"
            for name, version in packet_builder.EXPECTED_RUNTIME_PACKAGES.items()
        ),
        encoding="utf-8",
    )
    (environment / "conda-explicit.txt").write_text(
        "# platform: osx-arm64\n@EXPLICIT\nhttps://example.invalid/pinned-package.conda\n",
        encoding="utf-8",
    )
    (environment / "network_entrypoint_contract.tsv").write_text(
        packet_builder.EXPECTED_NETWORK_ENTRYPOINT_CONTRACT,
        encoding="utf-8",
    )


def metric_table(path: Path, rows: list[tuple[str, str]]) -> None:
    write_tsv(path, ("metric", "value"), [[key, value] for key, value in rows])


def candidate_rows(dataset: str, count: int) -> list[list[str]]:
    rows: list[list[str]] = []
    if dataset == "GM11906":
        rows.append(["8344", "A", "G", "1027", "740", "305", "435", "0.720545"])
    position = 100
    while len(rows) < count:
        if position != 8344:
            rows.append([str(position), "A", "C", "100", "25", "12", "13", "0.25"])
        position += 1
    return rows


def write_normalized_case(
    root: Path,
    case_id: str,
    dataset: str,
    oracle: dict[str, str],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    scientific: list[Path] = []

    def add_metric(name: str, rows: list[tuple[str, str]]) -> None:
        path = root / name
        metric_table(path, rows)
        scientific.append(path)

    add_metric(
        "mito_heteroplasmy_summary.tsv",
        [
            ("status", oracle["heteroplasmy_module_status"]),
            ("allele_min_base_quality", oracle["min_base_quality"]),
            ("allele_min_mapping_quality", oracle["min_mapping_quality"]),
            ("allele_min_read_mean_quality", oracle["min_read_mean_quality"]),
            ("accepted_observations", oracle["accepted_observations"]),
            ("excluded_observations", oracle["excluded_observations"]),
        ],
    )
    candidates = root / "mito_heteroplasmy_candidates.tsv"
    write_tsv(
        candidates,
        (
            "position",
            "ref_base",
            "alt_base",
            "callable_depth",
            "alt_count",
            "alt_forward",
            "alt_reverse",
            "alt_allele_fraction",
        ),
        candidate_rows(dataset, int(oracle["candidate_sites"])),
    )
    scientific.append(candidates)
    consequence = root / "mito_variant_consequence_candidates.tsv"
    consequence_rows = (
        [["8344", "A", "G", "MT-TK", "Mt_tRNA", "tRNA_variant"]]
        if dataset == "GM11906"
        else [["100", "A", "C", "MT-TF", "Mt_tRNA", "tRNA_variant"]]
    )
    write_tsv(
        consequence,
        (
            "position",
            "ref_base",
            "alt_base",
            "feature_label",
            "feature_class",
            "consequence_class",
        ),
        consequence_rows,
    )
    scientific.append(consequence)

    status_values = {
        "mito_copy_number_summary.tsv": oracle["copy_number_module_status"],
        "mito_feature_annotation_summary.tsv": oracle["feature_annotation_module_status"],
        "mito_gene_summary_run_summary.tsv": oracle["gene_summary_module_status"],
        "mito_identity_qc_summary.tsv": oracle["identity_qc_module_status"],
        "mito_variant_consequence_summary.tsv": oracle["variant_consequence_module_status"],
        "mito_circularity_qc_summary.tsv": oracle["circularity_qc_module_status"],
        "mito_methylation_exploratory_summary.tsv": oracle[
            "methylation_exploratory_module_status"
        ],
        "mito_phymer_haplogroup_summary.tsv": oracle["phymer_haplogroup_module_status"],
        "mito_mvtool_annotation_summary.tsv": oracle["mvtool_annotation_module_status"],
    }
    for filename, status in status_values.items():
        add_metric(filename, [("status", status), ("reason_code", "")])
    numt_rows = [("status", oracle["numt_qc_module_status"])]
    if oracle["numt_interpretation_status"]:
        numt_rows.extend(
            [
                ("numt_interpretation_status", oracle["numt_interpretation_status"]),
                ("reason_code", oracle["numt_interpretation_reason_code"]),
            ]
        )
    else:
        numt_rows.append(("reason_code", ""))
    add_metric("mito_numt_qc_summary.tsv", numt_rows)

    qc_rows = [("status", oracle["mito_qc_module_status"])]
    if dataset == "GM12878":
        qc_rows.extend(
            (metric, oracle[field])
            for field, metric in (
                ("mapped_reads", "mapped_reads"),
                ("primary_reads", "primary_reads"),
                ("supplementary_reads", "supplementary_reads"),
                ("mean_depth", "mean_depth"),
                ("median_depth", "median_depth"),
            )
        )
    add_metric("mito_qc_summary.tsv", qc_rows)
    add_metric(
        "mito_cosegregation_summary.tsv",
        [
            ("status", oracle["cosegregation_module_status"]),
            ("selected_sites", oracle["selected_cosegregation_sites"] or "0"),
        ],
    )
    add_metric(
        "mito_deletion_summary.tsv",
        [
            ("status", oracle["deletions_module_status"]),
            ("candidate_deletion_clusters", oracle["deletion_clusters"] or "0"),
            ("reads_with_large_deletion", oracle["deletion_query_names"] or "0"),
            (
                "reads_with_supplementary_or_SA",
                oracle["supplementary_sa_query_names"] or "0",
            ),
        ],
    )
    while len(scientific) < 44:
        dummy = root / f"zz_fixture_{len(scientific):02d}.tsv"
        write_tsv(dummy, ("fixture", "value"), [[str(len(scientific)), "ok"]])
        scientific.append(dummy)
    assert len(scientific) == 44
    write_tsv(
        root / "normalized_manifest.tsv",
        ("path", "sha256"),
        [
            [path.name, hashlib.sha256(path.read_bytes()).hexdigest()]
            for path in sorted(scientific)
        ],
    )

    output_root = root.parents[1] / "outputs" / case_id
    visual_rows = []
    for index in range(int(oracle["html_count"])):
        artifact = output_root / "report" / f"{index + 1:02d}.html"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            f"<!doctype html><html><body>{case_id} report {index + 1}</body></html>\n",
            encoding="utf-8",
        )
        visual_rows.append(
            [
                f"report/{index + 1:02d}.html",
                "html",
                str(artifact.stat().st_size),
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "",
                "",
                "ok",
            ]
        )
    for index in range(int(oracle["png_count"])):
        artifact = output_root / "figures" / f"{index + 1:02d}.png"
        write_png(artifact)
        visual_rows.append(
            [
                f"figures/{index + 1:02d}.png",
                "png",
                str(artifact.stat().st_size),
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "1",
                "1",
                "ok",
            ]
        )
    write_tsv(
        root / "visual_artifact_inventory.tsv",
        (
            "relative_path",
            "artifact_type",
            "bytes",
            "sha256",
            "width_px",
            "height_px",
            "integrity_status",
        ),
        visual_rows,
    )


def write_evidence_tables(root: Path) -> None:
    oracle = {(row["dataset"], row["profile"]): row for row in frozen_oracle_rows()}
    normalized_root = root / "public" / "observed_normalized"
    for dataset_key, dataset in (("gm11906", "GM11906"), ("gm12878", "GM12878")):
        for repeat in ("run1", "run2"):
            write_normalized_case(
                normalized_root / f"{dataset_key}_default_{repeat}",
                f"{dataset_key}_default_{repeat}",
                dataset,
                oracle[(dataset, "default")],
            )
    shutil.copytree(
        ROOT / "tests/fixtures/public_validation_contracts_v0.3.0",
        root / "public" / packet_builder.PUBLIC_CONTRACTS_PACKET_PATH,
    )

    figure_rows = []
    for dataset_key, dataset in (("gm11906", "GM11906"), ("gm12878", "GM12878")):
        case_id = f"{dataset_key}_default_run1"
        png_count = int(oracle[(dataset, "default")]["png_count"])
        for index in range(png_count):
            figure = root / "figures" / case_id / f"{index + 1:02d}.png"
            write_png(figure)
            figure_rows.append(
                [
                    f"{case_id}:{figure.name}",
                    dataset,
                    case_id,
                    figure.relative_to(root).as_posix(),
                    hashlib.sha256(figure.read_bytes()).hexdigest(),
                    str(figure.stat().st_size),
                    "1",
                    "1",
                    "ok",
                    f"observed_normalized/{case_id}/visual_artifact_inventory.tsv",
                ]
            )

    table_rows = []
    for table in sorted(normalized_root.rglob("*.tsv")):
        relative = table.relative_to(normalized_root)
        with table.open(encoding="utf-8", newline="") as handle:
            parsed = list(csv.reader(handle, delimiter="\t"))
        case_id = relative.parts[0]
        dataset = "GM11906" if case_id.startswith("gm11906") else "GM12878"
        table_rows.append(
            [
                relative.as_posix(),
                dataset,
                case_id,
                f"observed_normalized/{relative.as_posix()}",
                hashlib.sha256(table.read_bytes()).hexdigest(),
                str(max(0, len(parsed) - 1)),
                str(len(parsed[0]) if parsed else 0),
                "normalized scientific evidence",
            ]
        )

    module_rows = []
    for dataset_key, dataset in (("gm11906", "GM11906"), ("gm12878", "GM12878")):
        case_id = f"{dataset_key}_default_run1"
        for table in sorted((normalized_root / case_id).glob("*.tsv")):
            with table.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            if not rows or set(rows[0]) != {"metric", "value"}:
                continue
            values = {row["metric"]: row["value"] for row in rows}
            if "status" not in values:
                continue
            module_rows.append(
                [
                    dataset,
                    case_id,
                    table.stem,
                    values["status"],
                    values.get("reason_code", ""),
                    f"observed_normalized/{case_id}/{table.name}",
                ]
            )

    public_source_rows = []
    gm11906_source_metadata = json.loads(
        (
            ROOT / packet_builder.GM11906_SOURCE_METADATA_REPOSITORY_PATH
        ).read_text(encoding="utf-8")
    )
    gm11906_source_by_run = {
        record["run_accession"]: record
        for record in gm11906_source_metadata["records"]
    }
    inputs_by_run: dict[str, list[dict[str, str]]] = {}
    for row in packet_builder.FROZEN_PUBLIC_INPUTS:
        inputs_by_run.setdefault(row["run_accession"], []).append(dict(row))
    for run_accession, metadata in packet_builder.FROZEN_PUBLIC_SOURCE_METADATA.items():
        inputs = inputs_by_run[run_accession]
        first = inputs[0]
        public_source_rows.append(
            [
                metadata["dataset"],
                run_accession,
                metadata["study_accession"],
                first["sample_accession"],
                first["source_sample_id"],
                "ILLUMINA" if first["source_sample_id"] == "GM11906" else "OXFORD_NANOPORE",
                metadata["instrument_model"],
                first["library_strategy"],
                ";".join(row["url"] for row in inputs),
                ";".join(row["md5"] for row in inputs),
                ";".join(row["sha256"] for row in inputs),
                ";".join(row["bytes"] for row in inputs),
                (
                    gm11906_source_metadata["retrieval_completed_utc"]
                    if run_accession in gm11906_source_by_run
                    else "2026-07-21T00:00:00+00:00"
                ),
                "fixed-input reproducibility and descriptive filter profile",
                "raw reads excluded from Git and validation ZIP",
            ]
        )

    with (root / "public" / "filter_profile_results.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        profile_rows = list(csv.DictReader(handle, delimiter="\t"))
    handoff_rows = packet_builder.expected_handoff_rows(profile_rows)
    rows_by_name = {
        "claim_evidence_matrix.tsv": [
            [row[field] for field in packet_builder.EVIDENCE_TABLES["claim_evidence_matrix.tsv"]]
            for row in packet_builder.FROZEN_CLAIM_EVIDENCE_ROWS
        ],
        "module_status_matrix.tsv": module_rows,
        "figure_provenance.tsv": figure_rows,
        "table_provenance.tsv": table_rows,
        "public_data_sources.tsv": public_source_rows,
        "manuscript_handoff.tsv": [
            [row[field] for field in packet_builder.EVIDENCE_TABLES["manuscript_handoff.tsv"]]
            for row in handoff_rows
        ],
        "limitations.tsv": [
            ["L1", "clinical", "No clinical validation", "Research use claims only"]
        ],
    }
    for name, rows in rows_by_name.items():
        write_tsv(root / name, packet_builder.EVIDENCE_TABLES[name], rows)

    for dataset, specification in packet_builder.DECODED_PIXEL_REPORTS.items():
        case_id = str(specification["case_id"])
        repeat_case_id = str(specification["repeat_case_id"])
        matching_figures = [
            row
            for row in figure_rows
            if row[1] == dataset and row[2] == case_id
        ]
        for row in matching_figures:
            repeat_figure = (
                root / "public/outputs" / repeat_case_id / "figures" / Path(row[3]).name
            )
            repeat_figure.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / row[3], repeat_figure)
        write_tsv(
            root / "public" / str(specification["source"]),
            packet_builder.DECODED_PIXEL_HASH_COLUMNS,
            [
                [
                    Path(row[3]).name,
                    row[6],
                    row[7],
                    hashlib.sha256(
                        packet_builder.decoded_png_rgba(root / row[3])[2]
                    ).hexdigest(),
                ]
                for row in matching_figures
            ],
        )


def write_resource_evidence(root: Path, commit: str) -> None:
    rows = []
    raw_fastq_bytes = sum(
        int(row["bytes"]) for row in packet_builder.FROZEN_PUBLIC_INPUTS
    )
    for index, case_id in enumerate(
        sorted(packet_builder.REQUIRED_RESOURCE_CASE_IDS), start=1
    ):
        command = root / "commands" / f"{case_id}.sh"
        log = root / "logs" / f"{case_id}.log"
        if not command.exists():
            command.write_text(f"echo {case_id}\n", encoding="utf-8")
        if not log.exists():
            log.write_text(f"{case_id}=PASS\n", encoding="utf-8")
        command_digest = hashlib.sha256(command.read_bytes()).hexdigest()
        log_digest = hashlib.sha256(log.read_bytes()).hexdigest()
        rows.append(
            [
                f"10000000-0000-4000-8000-{index:012d}",
                case_id,
                commit,
                f"commands/{case_id}.sh",
                command_digest,
                command_digest,
                f"logs/{case_id}.log",
                log_digest,
                log_digest,
                "1.0",
                "0.5",
                "0.1",
                "1024",
                "12",
                "2048",
                "5",
                str(raw_fastq_bytes if case_id == "public_cache_prepare" else 4096),
                "repository_root;cache_root;validation_root",
                "cache_root;validation_root",
                "broad_declared_inputs_and_changed_or_new_outputs_v3",
                packet_builder.RESOURCE_CASE_THREAD_SETTINGS[case_id],
                "test",
                "measured",
                "",
            ]
        )
    write_tsv(
        root / "resource_usage.tsv",
        packet_builder.EVIDENCE_TABLES["resource_usage.tsv"],
        rows,
    )


def create_validation_root(tmp_path: Path, repo: Path, commit: str) -> Path:
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
    shutil.copy2(
        ROOT / "examples/synthetic_data/TOY-SR-001/expected_alleles.tsv",
        root / "expected/TOY-SR-001.expected_alleles.tsv",
    )
    shutil.copy2(
        ROOT / "examples/synthetic_data/TOY-WGS-001/expected_copy_proxy.tsv",
        root / "expected/TOY-WGS-001.expected_copy_proxy.tsv",
    )
    write_public_input_evidence(root / "public")
    write_public_oracle_evidence(root / "public")
    write_public_environment(root / "public")
    write_public_provenance(root / "public")
    write_distribution_artifacts(root / "dist")
    write_evidence_tables(root)
    write_cases(root / "public" / "cases.tsv", required_pass_rows())
    write_acceptance_evidence(root, repo, commit)
    rows = [
        row
        for row in required_pass_rows()
        if row["case_id"] not in packet_builder.ACCEPTANCE_CASE_IDS
    ]
    rows.extend(
        packet_builder.validate_acceptance_evidence(
            root,
            repo,
            commit,
            REPOSITORY,
        )
    )
    write_cases(root / "cases.tsv", rows)
    (root / "environment.txt").write_text(
        (
            "release_version=v0.3.0\n"
            f"git_commit={commit}\n"
            f"repository={REPOSITORY}\n"
            f"github_actions_run_id={GITHUB_RUN_ID}\n"
            f"final_push_github_actions_run_id={GITHUB_RUN_ID}\n"
            f"pull_request_number={PULL_REQUEST_NUMBER}\n"
            f"pull_request_github_actions_run_id={PULL_REQUEST_RUN_ID}\n"
            f"public_validation_github_actions_run_id={PUBLIC_VALIDATION_RUN_ID}\n"
            "python=3.12\n"
        ),
        encoding="utf-8",
    )
    (root / "commands" / "unit_known_answer.sh").write_text(
        "pytest -q\n", encoding="utf-8"
    )
    (root / "logs" / "unit_known_answer.log").write_text(
        "tests passed\n", encoding="utf-8"
    )
    (root / "public" / "commands" / "gm11906_default_run1.sh").write_text(
        "run public fixture\n", encoding="utf-8"
    )
    (root / "public" / "logs" / "gm11906_default_run1.log").write_text(
        "public fixture passed\n", encoding="utf-8"
    )
    write_resource_evidence(root, commit)
    return root


def packet_args(
    validation_root: Path, repo: Path, output: Path
) -> argparse.Namespace:
    return argparse.Namespace(
        validation_root=validation_root,
        packet_root=output / "packet",
        zip_path=output / "mito-overview-v0.3.0-validation.zip",
        repo_root=repo,
        commit=None,
        cache_root=validation_root.parent / "raw-cache",
        version="v0.3.0",
        repository=REPOSITORY,
    )


def rewrite_manifest(packet: Path) -> None:
    rows = []
    for path in sorted(packet.rglob("*")):
        if path.is_file() and path.relative_to(packet).as_posix() != "artifacts.sha256":
            rows.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                f"{path.relative_to(packet).as_posix()}"
            )
    (packet / "artifacts.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")


def rewrite_public_artifact_manifest(artifact_root: Path) -> None:
    rows = []
    for path in sorted(artifact_root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            rows.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                f"./{path.relative_to(artifact_root).as_posix()}"
            )
    (artifact_root / "SHA256SUMS").write_text(
        "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def rebind_packet_public_provenance(packet: Path, *paths: Path) -> None:
    identity_path = packet / "release_identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    records = {
        row["path"]: row
        for row in identity["public_provenance"]
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    for path in paths:
        relative = path.relative_to(packet).as_posix()
        assert relative in records
        records[relative]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")


def mutate_tsv_value(
    path: Path,
    match_field: str,
    match_value: str,
    target_field: str,
    replacement: str,
) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = tuple(reader.fieldnames or ())
        rows = list(reader)
    matches = [row for row in rows if row.get(match_field) == match_value]
    assert len(matches) == 1
    matches[0][target_field] = replacement
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def rebind_inventory_provenance(root: Path, inventory: Path) -> None:
    public_root = root / "public"
    if inventory.is_relative_to(public_root):
        packet_path = inventory.relative_to(public_root).as_posix()
    else:
        packet_path = inventory.relative_to(root).as_posix()
    mutate_tsv_value(
        root / "table_provenance.tsv",
        "packet_path",
        packet_path,
        "sha256",
        hashlib.sha256(inventory.read_bytes()).hexdigest(),
    )


def verify_packet(packet: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(packet / "verify_bundle.sh")],
        capture_output=True,
        text=True,
        check=False,
    )


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def mutate_audit_payload(
    comments_path: Path,
    role: str,
    field: str,
    replacement: object,
) -> None:
    comments = read_json(comments_path)
    assert isinstance(comments, list)
    for comment in comments:
        assert isinstance(comment, dict)
        body = str(comment["body"])
        if packet_builder.READ_ONLY_AUDIT_MARKER not in body:
            continue
        fenced = body.split(packet_builder.READ_ONLY_AUDIT_MARKER, 1)[1].strip()
        assert fenced.startswith("```json\n") and fenced.endswith("\n```")
        payload = json.loads(fenced.removeprefix("```json\n").removesuffix("\n```"))
        if payload["role"] == role:
            payload[field] = replacement
            comment["body"] = audit_comment_body(payload)
            write_json(comments_path, comments)
            return
    raise AssertionError(f"audit role not found: {role}")


def test_release_case_gate_requires_complete_passing_set(tmp_path: Path) -> None:
    cases = tmp_path / "cases.tsv"
    rows = required_pass_rows()
    write_cases(cases, rows)
    count, verdicts = packet_builder.validate_cases(cases)
    assert count == len(rows)
    assert verdicts["PASS"] == len(rows)

    write_cases(cases, rows[1:])
    with pytest.raises(ValueError, match="do not exactly match"):
        packet_builder.validate_cases(cases)

    rows[0]["verdict"] = "FAIL"
    write_cases(cases, rows)
    with pytest.raises(ValueError, match="Required release cases did not pass"):
        packet_builder.validate_cases(cases)

    rows[0]["verdict"] = "PASS"
    rows.append(
        {
            "case_id": "unexpected_case",
            "category": "test",
            "input_available": "1",
            "expected_available": "1",
            "verdict": "PASS",
            "detail": "must be rejected",
        }
    )
    write_cases(cases, rows)
    with pytest.raises(ValueError, match="unexpected=.*unexpected_case"):
        packet_builder.validate_cases(cases)


@pytest.mark.parametrize(
    "case_id",
    ("public_oracle", "raw_cache_seal", "project_network_entrypoints"),
)
def test_release_case_gate_makes_integrity_cases_mandatory(
    tmp_path: Path, case_id: str
) -> None:
    rows = required_pass_rows()
    assert case_id in packet_builder.REQUIRED_PASS_CASES
    missing = [row for row in rows if row["case_id"] != case_id]
    cases = tmp_path / f"{case_id}.tsv"
    write_cases(cases, missing)
    with pytest.raises(ValueError, match=case_id):
        packet_builder.validate_cases(cases)

    target = next(row for row in rows if row["case_id"] == case_id)
    target["verdict"] = "SKIP"
    write_cases(cases, rows)
    with pytest.raises(ValueError, match="did not pass"):
        packet_builder.validate_cases(cases)


def test_github_only_packet_builds_and_verifies_from_fresh_extraction(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    assert (packet / "cross_platform_comparison.tsv").read_bytes() == (
        validation / "acceptance/cross_platform_comparison.tsv"
    ).read_bytes()
    source_public_manifest = (
        validation
        / "acceptance/ubuntu_public_validation/artifact/SHA256SUMS"
    )
    packaged_public_manifest = (
        packet / "acceptance/ubuntu_public_validation/artifact/SHA256SUMS"
    )
    assert packaged_public_manifest.read_bytes() == source_public_manifest.read_bytes()

    run_record = json.loads((packet / "run.json").read_text(encoding="utf-8"))
    identity = json.loads((packet / "release_identity.json").read_text(encoding="utf-8"))
    assert run_record["schema_version"] == "2.0"
    assert run_record["validation_profile"] == "github_release_validation_v1"
    assert run_record["github_actions_run_id"] == GITHUB_RUN_ID
    assert run_record["final_push_github_actions_run_id"] == GITHUB_RUN_ID
    assert run_record["pull_request_number"] == PULL_REQUEST_NUMBER
    assert run_record["pull_request_github_actions_run_id"] == PULL_REQUEST_RUN_ID
    assert (
        run_record["public_validation_github_actions_run_id"]
        == PUBLIC_VALIDATION_RUN_ID
    )
    assert identity["git_commit"] == commit
    assert identity["dist_artifacts"] == read_json(
        packet / "acceptance/fresh_clone.json"
    )["distributions"]
    assert {row["kind"] for row in identity["dist_artifacts"]} == {"wheel", "sdist"}
    for row in identity["dist_artifacts"]:
        artifact = packet / row["path"]
        assert row["bytes"] == artifact.stat().st_size
        assert row["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert row["direct_url_archive_sha256"] == row["sha256"]
    assert identity["github_actions"]["head_sha"] == commit
    assert [
        item["platform_id"] for item in identity["resolved_ci_environments"]
    ] == list(packet_builder.RESOLVED_CI_PLATFORMS)
    assert identity["pull_request"]["merge_commit_sha"] == commit
    assert identity["pull_request"]["final_commit_parents"] == [
        run(["git", "rev-parse", f"{commit}^1"], repo),
        run(["git", "rev-parse", f"{commit}^2"], repo),
    ]
    assert (
        identity["pull_request"]["final_tree_sha"]
        == identity["pull_request"]["reviewed_head_tree_sha"]
    )
    assert identity["pull_request_github_actions"]["head_sha"] == run(
        ["git", "rev-parse", f"{commit}^2"], repo
    )
    assert identity["public_validation_github_actions"]["run_id"] == (
        PUBLIC_VALIDATION_RUN_ID
    )
    assert identity["public_validation_github_actions"]["head_sha"] == commit
    assert [item["role"] for item in identity["read_only_audits"]] == list(
        packet_builder.READ_ONLY_AUDIT_CASE_IDS
    )
    assert identity["public_environment"]["platform_id"] == "osx-arm64"
    assert identity["public_environment"]["isolation_method"] == (
        "macos_sandbox_exec_deny_network"
    )
    assert identity["public_environment"]["threads"] == 4
    assert len(identity["public_environment"]["files"]) == len(
        packet_builder.PUBLIC_ENVIRONMENT_FILES
    )
    assert (packet / packet_builder.PUBLIC_ENVIRONMENT_PACKET_PATH).is_dir()
    assert set(identity["metadata_sources"]) == {
        "pyproject.toml",
        "mito_overview/__init__.py",
        "CITATION.cff",
        "README.md",
        "CHANGELOG.md",
    }
    serialized = json.dumps({"run": run_record, "identity": identity}).lower()
    assert "doi" not in serialized
    assert not (packet / "acceptance" / "zenodo_reservation.json").exists()
    assert {
        path.name
        for path in (packet / "acceptance").iterdir()
        if path.is_file()
    } == (
        packet_builder.REQUIRED_ACCEPTANCE_FILES
    )
    assert not any("paper" in path.parts for path in packet.rglob("*"))
    macos_outputs = packet / packet_builder.MACOS_REPORT_OUTPUTS_PACKET_PATH
    inventories = sorted((packet / "observed_normalized").rglob("visual_artifact_inventory.tsv"))
    assert {path.name for path in macos_outputs.iterdir()} == {
        inventory.parent.name for inventory in inventories
    }
    for inventory in inventories:
        rows = read_tsv(inventory)
        case_root = macos_outputs / inventory.parent.name
        expected = {row["relative_path"] for row in rows}
        actual = {
            path.relative_to(case_root).as_posix()
            for path in case_root.rglob("*")
            if path.is_file()
        }
        assert actual == expected
        for row in rows:
            artifact = case_root / row["relative_path"]
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == row["sha256"]

    root_check = subprocess.run(
        [str(packet / "verify_bundle.sh")], capture_output=True, text=True, check=False
    )
    assert root_check.returncode == 0, root_check.stderr

    extracted = tmp_path / "extracted"
    safe_extract.safe_extract(
        output / "mito-overview-v0.3.0-validation.zip", extracted
    )
    extracted_check = subprocess.run(
        ["bash", str(extracted / "verify_bundle.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert extracted_check.returncode == 0, extracted_check.stderr


def test_nested_artifacts_manifest_is_itself_manifested_and_verified(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    (validation / "logs/artifacts.sha256").write_text(
        "nested evidence manifest\n", encoding="utf-8"
    )
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    root_manifest = (packet / "artifacts.sha256").read_text(encoding="utf-8")
    assert "  logs/artifacts.sha256\n" in root_manifest

    (packet / "logs/artifacts.sha256").write_text("tampered\n", encoding="utf-8")
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "artifact hash mismatch: logs/artifacts.sha256" in checked.stderr


@pytest.mark.parametrize(
    "filename",
    (
        "pull_request.json",
        "pull_request_comments.json",
        "pull_request_github_actions_run.json",
        "pull_request_github_actions_jobs.json",
    ),
)
def test_packet_requires_pull_request_acceptance_evidence(
    tmp_path: Path,
    filename: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    (validation / "acceptance" / filename).unlink()
    with pytest.raises(ValueError, match="Required acceptance evidence is missing"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_incomplete_public_validation_run_evidence(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    public_acceptance = validation / "acceptance/ubuntu_public_validation"
    (public_acceptance / "workflow_run.json").write_text(
        '{"status":"completed","conclusion":"success"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="public-validation run id"):
        packet_builder.build_packet(
            packet_args(validation, repo, tmp_path / "output")
        )


@pytest.mark.parametrize(
    "mutation",
    ("run_id", "head_sha", "artifact_run", "reproduction_run", "comparison_hash"),
)
def test_packet_rejects_public_validation_identity_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    public_root = validation / "acceptance/ubuntu_public_validation"
    if mutation in {"run_id", "head_sha"}:
        run_path = public_root / "workflow_run.json"
        payload = read_json(run_path)
        assert isinstance(payload, dict)
        if mutation == "run_id":
            payload["id"] = PUBLIC_VALIDATION_RUN_ID + 1
        else:
            payload["head_sha"] = "f" * 40
        write_json(run_path, payload)
    elif mutation == "artifact_run":
        artifacts_path = public_root / "artifacts.json"
        payload = read_json(artifacts_path)
        assert isinstance(payload, dict) and isinstance(payload["artifacts"], list)
        payload["artifacts"][0]["workflow_run"]["id"] = PUBLIC_VALIDATION_RUN_ID + 1
        write_json(artifacts_path, payload)
    elif mutation == "reproduction_run":
        reproduction_path = (
            validation / "acceptance/cross_platform_public_reproduction.json"
        )
        payload = read_json(reproduction_path)
        assert isinstance(payload, dict)
        payload["ubuntu_public_validation_run_id"] = PUBLIC_VALIDATION_RUN_ID + 1
        write_json(reproduction_path, payload)
    else:
        mutate_tsv_value(
            validation / "acceptance/cross_platform_comparison.tsv",
            "relative_path",
            "cases.tsv",
            "ubuntu_sha256",
            "b" * 64,
        )

    with pytest.raises(ValueError, match="Public-validation|public-validation|Cross-platform"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_public_artifact_hash_or_inventory_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    (artifact_root / "environment/identity.txt").write_text(
        "tampered=1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))

    validation = create_validation_root(tmp_path / "second", repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    (artifact_root / "unexpected.txt").write_text("unmanifested\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest inventory mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output2"))


def test_packet_rejects_self_consistent_ubuntu_visual_structure_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    visual = next(
        (artifact_root / "results/observed_normalized").rglob(
            "visual_artifact_inventory.tsv"
        )
    )
    with visual.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = tuple(reader.fieldnames or ())
        rows = list(reader)
    row = next(item for item in rows if item["artifact_type"] == "png")
    case_id = visual.parent.name
    artifact = (
        artifact_root
        / "results/report_artifacts/outputs"
        / case_id
        / row["relative_path"]
    )
    write_png(artifact, width=2)
    row["bytes"] = str(artifact.stat().st_size)
    row["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    row["width_px"] = "2"
    with visual.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    rewrite_public_artifact_manifest(artifact_root)
    with pytest.raises(ValueError, match="visual structure differs"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    ("relative_path", "artifact_type"),
    [
        ("../report/01.html", "html"),
        ("report\\01.html", "html"),
        ("nested/report/01.html", "html"),
        ("report/01.png", "html"),
    ],
)
def test_visual_inventory_rejects_unsafe_or_type_mismatched_paths(
    tmp_path: Path,
    relative_path: str,
    artifact_type: str,
) -> None:
    inventory = tmp_path / "visual_artifact_inventory.tsv"
    write_tsv(
        inventory,
        (
            "relative_path",
            "artifact_type",
            "bytes",
            "sha256",
            "width_px",
            "height_px",
            "integrity_status",
        ),
        [[relative_path, artifact_type, "1", "a" * 64, "", "", "ok"]],
    )
    with pytest.raises(ValueError, match="visual artifact|Visual artifact"):
        packet_builder.parse_visual_inventory(inventory)


def test_packet_rejects_resealed_missing_or_unlisted_ubuntu_visual_artifact(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    report_root = artifact_root / "results/report_artifacts/outputs"
    missing = next(report_root.rglob("*.html"))
    missing.unlink()
    rewrite_public_artifact_manifest(artifact_root)
    with pytest.raises(ValueError, match="Visual artifact .*missing"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "missing"))

    validation = create_validation_root(tmp_path / "extra", repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    report_root = artifact_root / "results/report_artifacts/outputs"
    case_root = next(path for path in report_root.iterdir() if path.is_dir())
    (case_root / "report/unlisted.html").write_text(
        "<html><body>unlisted</body></html>\n", encoding="utf-8"
    )
    rewrite_public_artifact_manifest(artifact_root)
    with pytest.raises(ValueError, match="inventory coverage mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "extra-output"))


def test_packet_rejects_resealed_ubuntu_visual_hash_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    visual = next(
        (artifact_root / "results/report_artifacts/outputs").rglob("*.html")
    )
    visual.write_text(
        visual.read_text(encoding="utf-8").replace("report", "Report", 1),
        encoding="utf-8",
    )
    rewrite_public_artifact_manifest(artifact_root)
    with pytest.raises(ValueError, match="SHA-256 does not match inventory"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_resealed_undecodable_ubuntu_png(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    inventory = next(
        (artifact_root / "results/observed_normalized").rglob(
            "visual_artifact_inventory.tsv"
        )
    )
    with inventory.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    row = next(item for item in rows if item["artifact_type"] == "png")
    artifact = (
        artifact_root
        / "results/report_artifacts/outputs"
        / inventory.parent.name
        / row["relative_path"]
    )
    artifact.write_bytes(b"\x89PNG\r\n\x1a\ntruncated")
    mutate_tsv_value(
        inventory,
        "relative_path",
        row["relative_path"],
        "bytes",
        str(artifact.stat().st_size),
    )
    mutate_tsv_value(
        inventory,
        "relative_path",
        row["relative_path"],
        "sha256",
        hashlib.sha256(artifact.read_bytes()).hexdigest(),
    )
    rewrite_public_artifact_manifest(artifact_root)
    with pytest.raises(ValueError, match="PNG"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_accepts_platform_specific_png_bytes_at_same_dimensions(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    inventory = next(
        (artifact_root / "results/observed_normalized").rglob(
            "visual_artifact_inventory.tsv"
        )
    )
    with inventory.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    row = next(item for item in rows if item["artifact_type"] == "png")
    artifact = (
        artifact_root
        / "results/report_artifacts/outputs"
        / inventory.parent.name
        / row["relative_path"]
    )
    write_png(artifact, (255, 0, 0))
    mutate_tsv_value(
        inventory,
        "relative_path",
        row["relative_path"],
        "bytes",
        str(artifact.stat().st_size),
    )
    mutate_tsv_value(
        inventory,
        "relative_path",
        row["relative_path"],
        "sha256",
        hashlib.sha256(artifact.read_bytes()).hexdigest(),
    )
    rewrite_public_artifact_manifest(artifact_root)

    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    assert verify_packet(output / "packet").returncode == 0


def test_packet_rejects_private_path_in_bound_macos_html_without_sanitizing_it(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    inventory = next(
        (validation / "public/observed_normalized").rglob(
            "visual_artifact_inventory.tsv"
        )
    )
    rows = read_tsv(inventory)
    row = next(item for item in rows if item["artifact_type"] == "html")
    artifact = validation / "public/outputs" / inventory.parent.name / row["relative_path"]
    artifact.write_text(
        "<html><body>source=/" + "Users/private/reports/input.bam</body></html>\n",
        encoding="utf-8",
    )
    mutate_tsv_value(
        inventory, "relative_path", row["relative_path"], "bytes", str(artifact.stat().st_size)
    )
    mutate_tsv_value(
        inventory,
        "relative_path",
        row["relative_path"],
        "sha256",
        hashlib.sha256(artifact.read_bytes()).hexdigest(),
    )
    rebind_inventory_provenance(validation, inventory)

    with pytest.raises(ValueError, match="absolute user path"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_extracted_verifier_rejects_resealed_fictitious_macos_html_inventory(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    inventory = next(
        (packet / "observed_normalized").rglob("visual_artifact_inventory.tsv")
    )
    row = next(item for item in read_tsv(inventory) if item["artifact_type"] == "html")
    mutate_tsv_value(
        inventory, "relative_path", row["relative_path"], "bytes", "999"
    )
    mutate_tsv_value(
        inventory, "relative_path", row["relative_path"], "sha256", "f" * 64
    )
    rebind_inventory_provenance(packet, inventory)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "visual artifact byte count mismatch" in checked.stderr


@pytest.mark.parametrize("mutation", ("missing", "unlisted", "undecodable"))
def test_extracted_verifier_rejects_resealed_invalid_macos_report_collection(
    tmp_path: Path, mutation: str
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    inventory = next(
        (packet / "observed_normalized").rglob("visual_artifact_inventory.tsv")
    )
    rows = read_tsv(inventory)
    case_root = (
        packet / packet_builder.MACOS_REPORT_OUTPUTS_PACKET_PATH / inventory.parent.name
    )
    if mutation == "missing":
        row = next(item for item in rows if item["artifact_type"] == "html")
        (case_root / row["relative_path"]).unlink()
    elif mutation == "unlisted":
        (case_root / "report/unlisted.html").write_text(
            "<html><body>unlisted</body></html>\n", encoding="utf-8"
        )
    else:
        row = next(item for item in rows if item["artifact_type"] == "png")
        artifact = case_root / row["relative_path"]
        artifact.write_bytes(b"\x89PNG\r\n\x1a\ntruncated")
        mutate_tsv_value(
            inventory,
            "relative_path",
            row["relative_path"],
            "bytes",
            str(artifact.stat().st_size),
        )
        mutate_tsv_value(
            inventory,
            "relative_path",
            row["relative_path"],
            "sha256",
            hashlib.sha256(artifact.read_bytes()).hexdigest(),
        )
        rebind_inventory_provenance(packet, inventory)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "visual artifact" in checked.stderr or "PNG" in checked.stderr


def test_extracted_verifier_rejects_resealed_ubuntu_visual_hash_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    artifact_root = packet / "acceptance/ubuntu_public_validation/artifact"
    visual = next((artifact_root / "results/report_artifacts/outputs").rglob("*.html"))
    visual.write_text(
        visual.read_text(encoding="utf-8").replace("report", "Report", 1),
        encoding="utf-8",
    )
    rewrite_public_artifact_manifest(artifact_root)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "visual artifact SHA-256 mismatch" in checked.stderr


def test_extracted_verifier_binds_downloaded_public_artifact_files(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    ubuntu_table = next(
        (packet / "acceptance/ubuntu_public_validation/artifact/results/observed_normalized")
        .rglob("mito_heteroplasmy_candidates.tsv")
    )
    ubuntu_table.write_text("tampered\n", encoding="utf-8")
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "public-validation artifact hash mismatch" in checked.stderr


def test_extracted_verifier_rejects_resealed_public_validation_run_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    run_path = packet / "acceptance/ubuntu_public_validation/workflow_run.json"
    payload = read_json(run_path)
    assert isinstance(payload, dict)
    payload["id"] = PUBLIC_VALIDATION_RUN_ID + 1
    write_json(run_path, payload)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "public-validation" in checked.stderr


def test_extracted_verifier_rejects_resealed_public_main_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    fresh_path = packet / "acceptance/fresh_clone.json"
    payload = read_json(fresh_path)
    assert isinstance(payload, dict)
    payload["public_main_commit"] = "f" * 40
    write_json(fresh_path, payload)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "fresh-clone acceptance mismatch" in checked.stderr


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("missing", "do not exactly match"),
        ("nonpass", "did not pass"),
        ("unexpected", "do not exactly match"),
    ),
)
def test_extracted_verifier_enforces_exact_passing_case_inventory(
    tmp_path: Path, mutation: str, expected_error: str
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    cases_path = packet / "cases.tsv"
    rows = read_tsv(cases_path)
    if mutation == "missing":
        rows = [row for row in rows if row["case_id"] != "public_oracle"]
    elif mutation == "nonpass":
        next(row for row in rows if row["case_id"] == "raw_cache_seal")[
            "verdict"
        ] = "SKIP"
    else:
        rows.append(
            {
                "case_id": "unexpected_case",
                "category": "test",
                "input_available": "1",
                "expected_available": "1",
                "verdict": "PASS",
                "detail": "resealed unexpected row",
            }
        )
    write_cases(cases_path, rows)
    run_path = packet / "run.json"
    run_record = read_json(run_path)
    assert isinstance(run_record, dict)
    run_record["case_count"] = len(rows)
    run_record["verdict_counts"] = {
        verdict: sum(row["verdict"] == verdict for row in rows)
        for verdict in {"PASS", "FAIL", "XFAIL", "SKIP", "BLOCKED"}
    }
    write_json(run_path, run_record)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert expected_error in checked.stderr


@pytest.mark.parametrize("kind", ("wheel", "sdist"))
def test_packet_rejects_replaced_same_identity_distribution_after_fresh_install(
    tmp_path: Path, kind: str
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    fresh_path = validation / "acceptance/fresh_clone.json"
    fresh = read_json(fresh_path)
    assert isinstance(fresh, dict)
    row = next(item for item in fresh["distributions"] if item["kind"] == kind)
    artifact = validation / row["path"]
    replace_distribution_with_same_identity(artifact)
    row["bytes"] = artifact.stat().st_size
    row["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    write_json(fresh_path, fresh)

    with pytest.raises(ValueError, match="PEP 610 archive hash"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize("kind", ("wheel", "sdist"))
def test_extracted_verifier_rejects_resealed_same_identity_distribution(
    tmp_path: Path, kind: str
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    identity_path = packet / "release_identity.json"
    fresh_path = packet / "acceptance/fresh_clone.json"
    identity = read_json(identity_path)
    fresh = read_json(fresh_path)
    assert isinstance(identity, dict) and isinstance(fresh, dict)
    identity_row = next(
        item for item in identity["dist_artifacts"] if item["kind"] == kind
    )
    fresh_row = next(item for item in fresh["distributions"] if item["kind"] == kind)
    artifact = packet / identity_row["path"]
    replace_distribution_with_same_identity(artifact)
    replacement_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    for row in (identity_row, fresh_row):
        row["bytes"] = artifact.stat().st_size
        row["sha256"] = replacement_hash
    write_json(identity_path, identity)
    write_json(fresh_path, fresh)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "distribution identity mismatch" in checked.stderr


def test_extracted_verifier_rejects_resealed_extra_distribution(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    identity_path = packet / "release_identity.json"
    fresh_path = packet / "acceptance/fresh_clone.json"
    identity = read_json(identity_path)
    fresh = read_json(fresh_path)
    assert isinstance(identity, dict) and isinstance(fresh, dict)

    source_row = next(
        item for item in identity["dist_artifacts"] if item["kind"] == "wheel"
    )
    source = packet / source_row["path"]
    extra = packet / "dist/mito_overview-0.3.0-py2-none-any.whl"
    shutil.copy2(source, extra)
    extra_row = dict(source_row)
    extra_row["path"] = "dist/mito_overview-0.3.0-py2-none-any.whl"
    identity["dist_artifacts"].append(extra_row)
    fresh["distributions"].append(dict(extra_row))
    write_json(identity_path, identity)
    write_json(fresh_path, fresh)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "distribution directory must contain only" in checked.stderr


def test_packet_requires_all_resolved_ci_platforms(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    shutil.rmtree(
        validation
        / packet_builder.RESOLVED_CI_ENVIRONMENTS_RELATIVE
        / "osx-64"
    )
    with pytest.raises(ValueError, match="Resolved CI platform inventory mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_self_consistent_resolved_ci_lock_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    platform_id = "linux-64"
    platform_root = (
        validation
        / packet_builder.RESOLVED_CI_ENVIRONMENTS_RELATIVE
        / platform_id
    )
    lock_name = f"environment-{platform_id}.yml"
    (platform_root / lock_name).write_text("name: altered\n", encoding="utf-8")
    record_path = platform_root / f"platform-{platform_id}.json"
    record = read_json(record_path)
    assert isinstance(record, dict) and isinstance(record["evidence_files"], dict)
    evidence_names = sorted(record["evidence_files"])
    for name in evidence_names:
        payload = (platform_root / name).read_bytes()
        record["evidence_files"][name] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
    manifest_payload = "".join(
        f"{name}\t{record['evidence_files'][name]['sha256']}\t"
        f"{record['evidence_files'][name]['size_bytes']}\n"
        for name in evidence_names
    ).encode("utf-8")
    record["evidence_manifest_sha256"] = hashlib.sha256(manifest_payload).hexdigest()
    record["source_lock_sha256"] = record["evidence_files"][lock_name]["sha256"]
    write_json(record_path, record)
    with pytest.raises(ValueError, match="differs from the release commit"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_extracted_verifier_rejects_resealed_resolved_ci_file_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    python_evidence = (
        packet
        / packet_builder.RESOLVED_CI_ENVIRONMENTS_RELATIVE
        / "osx-arm64"
        / "python-osx-arm64.txt"
    )
    python_evidence.write_text("Python 3.12.99\n", encoding="utf-8")
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "resolved CI Python evidence mismatch" in checked.stderr


def test_packet_rejects_missing_read_only_audit_role(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    comments_path = validation / "acceptance/pull_request_comments.json"
    comments = read_json(comments_path)
    assert isinstance(comments, list)
    comments.pop()
    write_json(comments_path, comments)
    with pytest.raises(ValueError, match="Missing required read-only audit payloads"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_duplicate_read_only_audit_role(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    comments_path = validation / "acceptance/pull_request_comments.json"
    comments = read_json(comments_path)
    assert isinstance(comments, list) and isinstance(comments[0], dict)
    duplicate = dict(comments[0])
    duplicate_id = 7999
    duplicate["id"] = duplicate_id
    duplicate["url"] = (
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/comments/"
        f"{duplicate_id}"
    )
    duplicate["html_url"] = (
        f"{REPOSITORY}/pull/{PULL_REQUEST_NUMBER}#issuecomment-{duplicate_id}"
    )
    comments.append(duplicate)
    write_json(comments_path, comments)
    with pytest.raises(ValueError, match="Duplicate read-only audit payload"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    "body",
    (
        "<!-- mito-overview-read-only-audit-v1 -->\nnot-a-fence",
        "<!-- mito-overview-read-only-audit-v1 -->\n```json\n{broken\n```",
    ),
)
def test_packet_rejects_malformed_read_only_audit_comment(
    tmp_path: Path,
    body: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    comments_path = validation / "acceptance/pull_request_comments.json"
    comments = read_json(comments_path)
    assert isinstance(comments, list) and isinstance(comments[0], dict)
    comments[0]["body"] = body
    write_json(comments_path, comments)
    with pytest.raises(ValueError, match="Read-only audit"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_read_only_audit_blockers(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    mutate_audit_payload(
        validation / "acceptance/pull_request_comments.json",
        "bioinformatics",
        "unresolved_blockers",
        1,
    )
    with pytest.raises(ValueError, match="unresolved blockers"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_unauthenticated_audit_comment_author(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    comments_path = validation / "acceptance/pull_request_comments.json"
    comments = read_json(comments_path)
    assert isinstance(comments, list) and isinstance(comments[0], dict)
    comments[0]["author_association"] = "NONE"
    comments[0]["user"] = {
        "login": "untrusted-reviewer",
        "html_url": "https://github.com/untrusted-reviewer",
    }
    write_json(comments_path, comments)
    with pytest.raises(ValueError, match="repository-owner post"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_ignores_unmarked_comment_from_other_author(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    comments_path = validation / "acceptance/pull_request_comments.json"
    comments = read_json(comments_path)
    assert isinstance(comments, list)
    comment_id = 7998
    comments.append(
        {
            "id": comment_id,
            "url": (
                f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/comments/"
                f"{comment_id}"
            ),
            "html_url": (
                f"{REPOSITORY}/pull/{PULL_REQUEST_NUMBER}#issuecomment-{comment_id}"
            ),
            "issue_url": (
                f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/"
                f"{PULL_REQUEST_NUMBER}"
            ),
            "user": {
                "login": "external-reviewer",
                "html_url": "https://github.com/external-reviewer",
            },
            "author_association": "NONE",
            "body": "Ordinary discussion comment without an audit marker.",
        }
    )
    write_json(comments_path, comments)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    checked = verify_packet(output / "packet")
    assert checked.returncode == 0, checked.stderr


@pytest.mark.parametrize(
    "mutation",
    (
        {"updated_at": "2026-07-21T12:01:00Z"},
        {
            "created_at": "2026-07-21T12:01:00Z",
            "updated_at": "2026-07-21T12:01:00Z",
        },
    ),
)
def test_packet_rejects_audit_comment_posted_or_edited_after_merge(
    tmp_path: Path,
    mutation: dict[str, str],
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    comments_path = validation / "acceptance/pull_request_comments.json"
    comments = read_json(comments_path)
    assert isinstance(comments, list) and isinstance(comments[0], dict)
    comments[0].update(mutation)
    write_json(comments_path, comments)
    with pytest.raises(ValueError, match="posted or edited after merge"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_missing_audit_comment_timestamp(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    comments_path = validation / "acceptance/pull_request_comments.json"
    comments = read_json(comments_path)
    assert isinstance(comments, list) and isinstance(comments[0], dict)
    comments[0].pop("updated_at")
    write_json(comments_path, comments)
    with pytest.raises(ValueError, match="updated_at is missing"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_reused_audit_instance_id(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    comments_path = validation / "acceptance/pull_request_comments.json"
    comments = read_json(comments_path)
    assert isinstance(comments, list)
    first_body = str(comments[0]["body"])
    payload = json.loads(
        first_body.split(packet_builder.READ_ONLY_AUDIT_MARKER, 1)[1]
        .strip()
        .removeprefix("```json\n")
        .removesuffix("\n```")
    )
    mutate_audit_payload(
        comments_path,
        "bioinformatics",
        "audit_instance_id",
        payload["audit_instance_id"],
    )
    with pytest.raises(ValueError, match="instance IDs must be unique"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_casefolded_reused_audit_instance_id(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    comments_path = validation / "acceptance/pull_request_comments.json"
    shared = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    mutate_audit_payload(
        comments_path,
        "release_engineering",
        "audit_instance_id",
        shared,
    )
    mutate_audit_payload(
        comments_path,
        "bioinformatics",
        "audit_instance_id",
        shared.upper(),
    )
    with pytest.raises(ValueError, match="instance IDs must be unique"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    ("field", "error"),
    (
        ("reviewed_commit", "reviewed-commit drift"),
        ("reviewed_tree", "reviewed-tree drift"),
    ),
)
def test_packet_rejects_read_only_audit_commit_or_tree_drift(
    tmp_path: Path,
    field: str,
    error: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    mutate_audit_payload(
        validation / "acceptance/pull_request_comments.json",
        "reproducibility",
        field,
        "f" * 40,
    )
    with pytest.raises(ValueError, match=error):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    "mutation",
    ("merged_state", "base_branch", "head_repository", "canonical_url"),
)
def test_packet_rejects_wrong_pull_request_identity(
    tmp_path: Path,
    mutation: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    pull_path = validation / "acceptance/pull_request.json"
    pull = read_json(pull_path)
    assert isinstance(pull, dict)
    if mutation == "merged_state":
        pull["merged"] = False
    elif mutation == "base_branch":
        assert isinstance(pull["base"], dict)
        pull["base"]["ref"] = "develop"
    elif mutation == "head_repository":
        assert isinstance(pull["head"], dict)
        assert isinstance(pull["head"]["repo"], dict)
        pull["head"]["repo"]["full_name"] = "someone/else"
    else:
        pull["html_url"] = f"{REPOSITORY}/pull/999"
    write_json(pull_path, pull)
    with pytest.raises(ValueError, match="Pull-request"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_pull_request_other_than_three(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    pull_path = validation / "acceptance/pull_request.json"
    pull = read_json(pull_path)
    assert isinstance(pull, dict)
    pull["number"] = 31
    pull["url"] = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/pulls/31"
    pull["html_url"] = f"{REPOSITORY}/pull/31"
    pull["issue_url"] = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/31"
    pull["comments_url"] = f"{pull['issue_url']}/comments"
    write_json(pull_path, pull)
    with pytest.raises(ValueError, match="must come from pull request 3"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_fresh_clone_public_main_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    fresh_path = validation / "acceptance/fresh_clone.json"
    fresh = read_json(fresh_path)
    assert isinstance(fresh, dict)
    fresh["public_main_commit"] = "f" * 40
    write_json(fresh_path, fresh)
    with pytest.raises(ValueError, match="public_main_commit"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    "mutation",
    ("event", "head_sha", "associated_pr"),
)
def test_packet_rejects_wrong_pull_request_ci_identity(
    tmp_path: Path,
    mutation: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    run_path = validation / "acceptance/pull_request_github_actions_run.json"
    payload = read_json(run_path)
    assert isinstance(payload, dict)
    if mutation == "event":
        payload["event"] = "push"
    elif mutation == "head_sha":
        payload["head_sha"] = "f" * 40
    else:
        associations = payload["pull_requests"]
        assert isinstance(associations, list) and isinstance(associations[0], dict)
        associations[0]["number"] = 999
    write_json(run_path, payload)
    with pytest.raises(ValueError, match="Pull-request (?:GitHub Actions|workflow)"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize("mutation", ("missing", "extra", "head_sha", "label"))
def test_packet_rejects_wrong_pull_request_ci_jobs(
    tmp_path: Path,
    mutation: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    jobs_path = validation / "acceptance/pull_request_github_actions_jobs.json"
    payload = read_json(jobs_path)
    assert isinstance(payload, dict) and isinstance(payload["jobs"], list)
    jobs = payload["jobs"]
    if mutation == "missing":
        jobs.pop()
    elif mutation == "extra":
        extra = dict(jobs[0])
        extra["id"] = 8999
        extra["name"] = "Unexpected job"
        jobs.append(extra)
    elif mutation == "head_sha":
        jobs[0]["head_sha"] = "f" * 40
    else:
        jobs[0]["labels"] = ["ubuntu-latest"]
    payload["total_count"] = len(jobs)
    write_json(jobs_path, payload)
    with pytest.raises(ValueError, match="Pull-request GitHub Actions|pinned jobs"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_accepts_additional_pull_request_ci_runner_labels(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    jobs_path = validation / "acceptance/pull_request_github_actions_jobs.json"
    payload = read_json(jobs_path)
    assert isinstance(payload, dict) and isinstance(payload["jobs"], list)
    payload["jobs"][0]["labels"].append("supplemental-host-label")
    write_json(jobs_path, payload)

    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    checked = verify_packet(output / "packet")
    assert checked.returncode == 0, checked.stderr


def test_packet_rejects_pull_request_environment_identity_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    environment = validation / "environment.txt"
    environment.write_text(
        environment.read_text(encoding="utf-8").replace(
            f"pull_request_github_actions_run_id={PULL_REQUEST_RUN_ID}",
            "pull_request_github_actions_run_id=999",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pull_request_github_actions_run_id"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_final_merge_tree_relation_drift(tmp_path: Path) -> None:
    repo, _ = create_release_repo(tmp_path)
    run(["git", "checkout", "-q", "-b", "tree-drift-head"], repo)
    (repo / "HEAD_ONLY").write_text("reviewed head\n", encoding="utf-8")
    run(["git", "add", "HEAD_ONLY"], repo)
    run(["git", "commit", "-q", "-m", "reviewed head fixture"], repo)
    run(["git", "checkout", "-q", "main"], repo)
    (repo / "BASE_ONLY").write_text("unreviewed base change\n", encoding="utf-8")
    run(["git", "add", "BASE_ONLY"], repo)
    run(["git", "commit", "-q", "-m", "base drift fixture"], repo)
    run(
        [
            "git",
            "merge",
            "-q",
            "--no-ff",
            "tree-drift-head",
            "-m",
            "Merge tree-drift fixture",
        ],
        repo,
    )
    commit = run(["git", "rev-parse", "HEAD"], repo)
    validation = tmp_path / "validation"
    for relative in ("acceptance", "commands", "logs"):
        (validation / relative).mkdir(parents=True, exist_ok=True)
    write_acceptance_evidence(
        validation,
        repo,
        commit,
        include_public_evidence=False,
    )
    with pytest.raises(ValueError, match="Reviewed pull-request head tree"):
        packet_builder.validate_pull_request_evidence(
            validation,
            repo,
            commit,
            REPOSITORY,
        )


def test_packet_rejects_final_merge_parent_relation_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    pull_path = validation / "acceptance/pull_request.json"
    pull = read_json(pull_path)
    assert isinstance(pull, dict) and isinstance(pull["head"], dict)
    pull["head"]["sha"] = "f" * 40
    write_json(pull_path, pull)
    with pytest.raises(ValueError, match="Final merge parent relationship"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize("name", sorted(packet_builder.EVIDENCE_TABLES))
def test_packet_requires_every_structured_evidence_table(
    tmp_path: Path, name: str
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    (validation / name).unlink()
    with pytest.raises(ValueError, match="missing or empty"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("schema_version", "2.0"),
        ("platform", "Darwin/ppc64"),
        ("isolation_method", "curl_canary_only"),
        ("isolation_scope", "single_process"),
        ("parent_loopback_control", "unreachable"),
        ("isolated_loopback_probe", "reachable"),
        ("probe_error", ""),
        ("child_uid", "502"),
        ("child_gid", "21"),
        ("network_isolation_verdict", "FAIL"),
    ),
)
def test_packet_rejects_invalid_network_isolation_evidence(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    mutate_tsv_value(
        validation / "public/environment/network_isolation.tsv",
        "field",
        field,
        "value",
        replacement,
    )
    with pytest.raises(ValueError, match="Network-isolation"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("python", "3.12.12"),
        ("samtools", "samtools 1.22"),
        ("threads", 8),
        ("installed_distribution_required", False),
        ("mito_overview_module", "/checkout/mito_overview/__init__.py"),
    ),
)
def test_packet_rejects_invalid_public_runtime_evidence(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    runtime_path = validation / "public/environment/runtime_versions.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime[field] = replacement
    runtime_path.write_text(
        json.dumps(runtime, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Public runtime"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_public_environment_inventory_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    (validation / "public/environment/untracked-runtime.txt").write_text(
        "unexpected\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="environment evidence inventory"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_requires_offline_isolation_pass_case(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    cases_path = validation / "cases.tsv"
    with cases_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    rows = [row for row in rows if row["case_id"] != "offline_isolation"]
    write_cases(cases_path, rows)
    with pytest.raises(ValueError, match="offline_isolation"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_public_source_timestamp_is_recorded_not_live_checked(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    with (validation / "public_data_sources.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        assert "metadata_recorded_utc" in tuple(reader.fieldnames or ())
        assert "metadata_checked_utc" not in tuple(reader.fieldnames or ())
        rows = list(reader)
    metadata = json.loads(
        (repo / packet_builder.GM11906_SOURCE_METADATA_REPOSITORY_PATH).read_text(
            encoding="utf-8"
        )
    )
    assert {
        row["metadata_recorded_utc"]
        for row in rows
        if row["run_accession"] in {"SRR10804585", "SRR10804590", "SRR10804657"}
    } == {metadata["retrieval_completed_utc"]}


def test_packet_rejects_secret_like_material(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    (validation / "logs" / "unit_known_answer.log").write_text(
        "access_token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ\n", encoding="utf-8"
    )
    digest = hashlib.sha256(
        (validation / "logs" / "unit_known_answer.log").read_bytes()
    ).hexdigest()
    for field in ("log_sha256", "packaged_log_sha256"):
        mutate_tsv_value(
            validation / "resource_usage.tsv",
            "case_id",
            "unit_known_answer",
            field,
            digest,
        )
    with pytest.raises(ValueError, match="secret-like material"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_normalizes_local_absolute_paths(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    source = validation / "logs" / "unit_known_answer.log"
    source.write_text("source=/Users/alice/private/run.log\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    for field in ("log_sha256", "packaged_log_sha256"):
        mutate_tsv_value(
            validation / "resource_usage.tsv",
            "case_id",
            "unit_known_answer",
            field,
            digest,
        )
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    copied = (output / "packet" / "logs" / "unit_known_answer.log").read_text(
        encoding="utf-8"
    )
    assert "/Users/" not in copied
    assert "${HOME}" in copied
    with (output / "packet" / "resource_usage.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    resource = next(row for row in rows if row["case_id"] == "unit_known_answer")
    assert resource["log_sha256"] == digest
    assert resource["packaged_log_sha256"] == hashlib.sha256(
        copied.encode("utf-8")
    ).hexdigest()
    assert resource["packaged_log_sha256"] != resource["log_sha256"]


def test_packet_rejects_local_paths_inside_immutable_public_artifact(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    artifact_log = artifact_root / "results/logs/runner.log"
    artifact_log.parent.mkdir(parents=True, exist_ok=True)
    artifact_log.write_text("checkout=/home/runner/work/mito-overview\n", encoding="utf-8")
    rewrite_public_artifact_manifest(artifact_root)

    with pytest.raises(ValueError, match="absolute user path"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_ci_run_identity_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    environment = validation / "environment.txt"
    environment.write_text(
        environment.read_text(encoding="utf-8").replace(
            f"github_actions_run_id={GITHUB_RUN_ID}",
            "github_actions_run_id=999",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match GitHub Actions evidence"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_verifier_rejects_semantic_identity_tampering(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    identity_path = packet / "release_identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["git_commit"] = "f" * 40
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    rewrite_manifest(packet)

    checked = subprocess.run(
        [str(packet / "verify_bundle.sh")], capture_output=True, text=True, check=False
    )
    assert checked.returncode != 0
    assert "release commit" in checked.stderr


def test_extracted_verifier_rejects_rehashed_read_only_audit_blockers(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    mutate_audit_payload(
        packet / "acceptance/pull_request_comments.json",
        "release_engineering",
        "unresolved_blockers",
        1,
    )
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "read-only audit payload mismatch" in checked.stderr


def test_extracted_verifier_rejects_rehashed_postmerge_audit_edit(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    comments_path = packet / "acceptance/pull_request_comments.json"
    comments = read_json(comments_path)
    assert isinstance(comments, list) and isinstance(comments[0], dict)
    comments[0]["updated_at"] = "2026-07-21T12:01:00Z"
    write_json(comments_path, comments)
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "posted or edited after merge" in checked.stderr


def test_extracted_verifier_rejects_rehashed_pr_ci_head_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    run_path = packet / "acceptance/pull_request_github_actions_run.json"
    payload = read_json(run_path)
    assert isinstance(payload, dict)
    payload["head_sha"] = "f" * 40
    write_json(run_path, payload)
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "pull-request GitHub Actions run identity mismatch" in checked.stderr


def test_extracted_verifier_rejects_rehashed_merge_relation_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    identity_path = packet / "release_identity.json"
    identity = read_json(identity_path)
    assert isinstance(identity, dict)
    pull_request = identity["pull_request"]
    assert isinstance(pull_request, dict)
    pull_request["final_commit_parents"] = list(
        reversed(pull_request["final_commit_parents"])
    )
    write_json(identity_path, identity)
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "final merge parent/tree relationship mismatch" in checked.stderr


def test_extracted_verifier_rejects_rehashed_network_isolation_mutation(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    mutate_tsv_value(
        packet / "public_environment/network_isolation.tsv",
        "field",
        "isolated_loopback_probe",
        "value",
        "reachable",
    )
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "network-isolation evidence mismatch" in checked.stderr


def test_extracted_verifier_rejects_rehashed_isolation_receipt_change(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    mutate_tsv_value(
        packet / "public_environment/network_isolation.tsv",
        "field",
        "probe_error",
        "value",
        "PermissionError:13",
    )
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "release identity public-environment evidence mismatch" in checked.stderr


def test_extracted_verifier_rejects_rehashed_runtime_mutation(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    runtime_path = packet / "public_environment/runtime_versions.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime["threads"] = 8
    runtime_path.write_text(
        json.dumps(runtime, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "public runtime evidence mismatch for threads" in checked.stderr


def test_packet_requires_all_three_fixed_ci_jobs(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    jobs_path = validation / "acceptance" / "github_actions_jobs.json"
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    payload["jobs"] = [
        job
        for job in payload["jobs"]
        if job["name"] != "Unit and synthetic tests (macos-15)"
    ]
    payload["total_count"] = len(payload["jobs"])
    jobs_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="osx-arm64"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_generic_or_drifted_ci_runner_label(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    jobs_path = validation / "acceptance" / "github_actions_jobs.json"
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    job = next(
        item
        for item in payload["jobs"]
        if item["name"] == "Unit and synthetic tests (ubuntu-24.04)"
    )
    job["labels"] = ["ubuntu-latest"]
    jobs_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ubuntu-24.04"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_resealed_public_input_hash_mutation(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    manifest = validation / "public" / packet_builder.RAW_INPUTS_PACKET_PATH
    mutate_tsv_value(
        manifest,
        "filename",
        "SRR10804585_1.fastq.gz",
        "sha256",
        "f" * 64,
    )
    changed_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    (validation / "public" / packet_builder.CACHE_SEAL_PACKET_PATH).write_text(
        f"{changed_digest}  raw_inputs.tsv\n", encoding="utf-8"
    )
    with pytest.raises(
        ValueError,
        match="Public-input manifest mismatch|Cross-platform scientific row",
    ):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_public_source_hash_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    mutate_tsv_value(
        validation / "public_data_sources.tsv",
        "run_accession",
        "SRR18110025",
        "fastq_sha256",
        "f" * 64,
    )
    with pytest.raises(ValueError, match="public_data_sources.tsv mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_tampered_official_gm11906_metadata_copy(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    metadata_path = (
        validation
        / "public"
        / packet_builder.PUBLIC_PROVENANCE_FILES["shortread_source_metadata"]["source"]
    )
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["records"][0]["cell_line"] = "GM00000"
    canonical = json.dumps(
        payload["records"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    payload["records_sha256"] = hashlib.sha256(canonical).hexdigest()
    metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="execution copy SHA-256 mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    ("provenance_key", "field", "replacement"),
    (
        ("shortread_alignment", "command_template", "different short command"),
        ("shortread_alignment", "parameters", {"threads": "8"}),
        (
            "shortread_alignment",
            "tool_versions",
            {"bwa": "0.7.18", "samtools": "samtools 1.23.1"},
        ),
        ("longread_alignment", "command_template", "different long command"),
        (
            "longread_alignment",
            "parameters",
            {
                "selected_query_names": "1000",
                "selection_seed": "wrong-seed",
                "threads": "4",
                "unmapped_filter_flag": "4",
            },
        ),
        (
            "longread_alignment",
            "tool_versions",
            {"minimap2": "2.30", "samtools": "samtools 1.23.1"},
        ),
    ),
)
def test_packet_rejects_alignment_derivation_drift(
    tmp_path: Path,
    provenance_key: str,
    field: str,
    replacement: object,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    path = (
        validation
        / "public"
        / packet_builder.PUBLIC_PROVENANCE_FILES[provenance_key]["source"]
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["derivation"][field] = replacement
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="alignment derivation is invalid"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize("provenance_key", ("shortread_alignment", "longread_alignment"))
def test_packet_rejects_duplicate_alignment_input_labels(
    tmp_path: Path,
    provenance_key: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    path = (
        validation
        / "public"
        / packet_builder.PUBLIC_PROVENANCE_FILES[provenance_key]["source"]
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["public_inputs"].append(dict(payload["public_inputs"][0]))
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate input label"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("missing_md5", "digest field inventory"),
        ("extra_field", "digest field inventory"),
        ("wrong_md5", "does not match packaged evidence"),
    ),
)
def test_packet_rejects_inexact_nested_subset_manifest_digest_inventory(
    tmp_path: Path,
    mutation: str,
    expected_error: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    path = (
        validation
        / "public"
        / packet_builder.PUBLIC_PROVENANCE_FILES["longread_alignment"]["source"]
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    record = next(
        row
        for row in payload["public_inputs"]
        if row["label"] == "deterministic_subset_manifest"
    )
    if mutation == "missing_md5":
        record.pop("md5")
    elif mutation == "extra_field":
        record["unexpected"] = "field"
    else:
        record["md5"] = "f" * 32
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=expected_error):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize("evidence_name", ("claim", "handoff"))
def test_packet_rejects_semantically_forged_narrative_evidence(
    tmp_path: Path,
    evidence_name: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    if evidence_name == "claim":
        mutate_tsv_value(
            validation / "claim_evidence_matrix.tsv",
            "claim_id",
            "C1",
            "bounded_claim",
            "Unsupported replacement claim",
        )
        expected = "frozen bounded contract"
    else:
        handoff = validation / "manuscript_handoff.tsv"
        first = read_tsv(handoff)[0]
        mutate_tsv_value(
            handoff,
            "result_id",
            first["result_id"],
            "value",
            "999999",
        )
        expected = "do not match filter_profile_results.tsv"

    with pytest.raises(ValueError, match=expected):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_self_consistent_noncanonical_selected_name_ledger(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    public = validation / "public"
    names_path = public / packet_builder.PUBLIC_PROVENANCE_FILES[
        "selected_query_names"
    ]["source"]
    subset_path = public / packet_builder.PUBLIC_PROVENANCE_FILES["longread_subset"][
        "source"
    ]
    alignment_path = public / packet_builder.PUBLIC_PROVENANCE_FILES[
        "longread_alignment"
    ]["source"]
    names_path.write_text(
        "".join(f"arbitrary-{index:04d}\n" for index in range(1000)),
        encoding="utf-8",
    )
    selected_record = file_provenance_record(
        names_path,
        "SRR18110025.deterministic-qnames-1000.fastq.gz.selected_qnames.txt",
        include_md5=True,
    )
    subset = json.loads(subset_path.read_text(encoding="utf-8"))
    subset["selected_query_names"] = selected_record
    subset_path.write_text(json.dumps(subset, indent=2) + "\n", encoding="utf-8")
    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    for record in alignment["public_inputs"]:
        if record["label"] == "selected_query_names":
            record.clear()
            record.update(selected_record, label="selected_query_names")
    alignment_path.write_text(
        json.dumps(alignment, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="selected-query-name identity is not frozen"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_self_consistent_subset_fastq_digest_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    public = validation / "public"
    subset_path = public / packet_builder.PUBLIC_PROVENANCE_FILES["longread_subset"][
        "source"
    ]
    alignment_path = public / packet_builder.PUBLIC_PROVENANCE_FILES[
        "longread_alignment"
    ]["source"]
    drifted = dict(packet_builder.FROZEN_GM12878_SUBSET_FASTQ_RECORD)
    drifted.update(bytes=10721432, md5="e" * 32, sha256="f" * 64)
    subset = json.loads(subset_path.read_text(encoding="utf-8"))
    subset["subset_fastq"] = drifted
    subset_path.write_text(json.dumps(subset, indent=2) + "\n", encoding="utf-8")
    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    for record in alignment["public_inputs"]:
        if record["label"] == "deterministic_subset_fastq":
            record.clear()
            record.update(drifted, label="deterministic_subset_fastq")
    alignment_path.write_text(
        json.dumps(alignment, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="subset FASTQ identity is not frozen"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_public_cache_output_inventory_below_raw_bytes(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    mutate_tsv_value(
        validation / "resource_usage.tsv",
        "case_id",
        "public_cache_prepare",
        "changed_or_new_output_inventory_bytes",
        "1",
    )
    with pytest.raises(ValueError, match="excludes one or more raw downloads"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_duplicate_resource_measurement_id(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    resource_path = validation / "resource_usage.tsv"
    with resource_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    rows[1]["measurement_id"] = rows[0]["measurement_id"]
    write_tsv(resource_path, fields, [[row[field] for field in fields] for row in rows])
    with pytest.raises(ValueError, match="Duplicate resource measurement ID"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_casefolded_duplicate_resource_measurement_id(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    resource_path = validation / "resource_usage.tsv"
    with resource_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    shared = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    rows[0]["measurement_id"] = shared
    rows[1]["measurement_id"] = shared.upper()
    write_tsv(resource_path, fields, [[row[field] for field in fields] for row in rows])
    with pytest.raises(ValueError, match="Duplicate resource measurement ID"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("wall_seconds", "0", "wall_seconds must be > 0"),
        ("max_rss_kb", "NaN", "Invalid finite resource value max_rss_kb"),
        ("wall_seconds", "Inf", "Invalid finite resource value wall_seconds"),
        (
            "broad_declared_input_inventory_file_count",
            "0",
            "input_inventory_file_count must be > 0",
        ),
        (
            "broad_declared_input_inventory_bytes",
            "0",
            "input_inventory_bytes must be > 0",
        ),
        (
            "measurement_status",
            "unavailable",
            "Required resource measurement must be measured",
        ),
    ],
)
def test_packet_rejects_invalid_required_resource_measurements(
    tmp_path: Path,
    field: str,
    replacement: str,
    message: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    mutate_tsv_value(
        validation / "resource_usage.tsv",
        "case_id",
        "unit_known_answer",
        field,
        replacement,
    )
    with pytest.raises(ValueError, match=message):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_missing_resource_case(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    resource_path = validation / "resource_usage.tsv"
    with resource_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    rows = [row for row in rows if row["case_id"] != "package_build"]
    write_tsv(resource_path, fields, [[row[field] for field in fields] for row in rows])
    with pytest.raises(ValueError, match="Resource case inventory mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_resource_command_digest_or_thread_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    command = validation / "commands/unit_known_answer.sh"
    command.write_text("echo altered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="command_sha256 does not match"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "digest"))

    validation = create_validation_root(tmp_path / "thread", repo, commit)
    mutate_tsv_value(
        validation / "resource_usage.tsv",
        "case_id",
        "unit_known_answer",
        "threads",
        "8",
    )
    with pytest.raises(ValueError, match="thread setting mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "thread-output"))


def test_packet_rejects_prepackaging_resource_digest_divergence(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    mutate_tsv_value(
        validation / "resource_usage.tsv",
        "case_id",
        "unit_known_answer",
        "packaged_command_sha256",
        "f" * 64,
    )
    with pytest.raises(ValueError, match="Pre-packaging resource digest mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_requires_decoded_pixel_evidence(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    report = validation / "public/logs/gm12878_decoded_pixel_hashes.tsv"
    report.unlink()
    with pytest.raises(ValueError, match="missing|decoded-pixel"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_decoded_pixel_inventory_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    report = validation / "public/logs/gm11906_decoded_pixel_hashes.tsv"
    rows = report.read_text(encoding="utf-8").splitlines()
    report.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Decoded-pixel inventory"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_substituted_decoded_pixel_digest(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    report = validation / "public/logs/gm11906_decoded_pixel_hashes.tsv"
    with report.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    rows[0]["decoded_rgba_sha256"] = "0" * 64
    write_tsv(report, fields, [[row[field] for field in fields] for row in rows])
    with pytest.raises(ValueError, match="hash does not match repeat-1 PNG"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_repeat2_decoded_pixel_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    figure = (
        validation
        / "public/outputs/gm12878_default_run2/figures/01.png"
    )
    write_png(figure, (255, 0, 0))
    inventory = (
        validation
        / "public/observed_normalized/gm12878_default_run2/visual_artifact_inventory.tsv"
    )
    mutate_tsv_value(
        inventory,
        "relative_path",
        "figures/01.png",
        "bytes",
        str(figure.stat().st_size),
    )
    mutate_tsv_value(
        inventory,
        "relative_path",
        "figures/01.png",
        "sha256",
        hashlib.sha256(figure.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="hash does not match repeat-2 PNG"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_extracted_verifier_rejects_resealed_duplicate_measurement_id(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    resource_path = packet / "resource_usage.tsv"
    with resource_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    rows[1]["measurement_id"] = rows[0]["measurement_id"]
    write_tsv(resource_path, fields, [[row[field] for field in fields] for row in rows])
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "duplicate resource measurement ID" in checked.stderr


def test_extracted_verifier_rejects_resealed_resource_command_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    (packet / "commands/unit_known_answer.sh").write_text(
        "echo relabeled\n", encoding="utf-8"
    )
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "packaged_command_sha256 does not bind command_path" in checked.stderr


def test_extracted_verifier_rejects_resealed_resource_thread_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    mutate_tsv_value(
        packet / "resource_usage.tsv",
        "case_id",
        "synthetic_longread_smoke",
        "threads",
        "4",
    )
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "resource thread setting mismatch" in checked.stderr


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("wall_seconds", "0", "resource measurement must be positive: wall_seconds"),
        ("max_rss_kb", "NaN", "invalid finite resource measurement max_rss_kb"),
        ("wall_seconds", "Inf", "invalid finite resource measurement wall_seconds"),
        (
            "broad_declared_input_inventory_file_count",
            "0",
            "resource input inventory file count must be positive",
        ),
        (
            "broad_declared_input_inventory_bytes",
            "0",
            "resource input inventory bytes must be positive",
        ),
        (
            "measurement_status",
            "unavailable",
            "required resource measurement is not measured",
        ),
    ],
)
def test_extracted_verifier_rejects_resealed_invalid_resource_measurements(
    tmp_path: Path,
    field: str,
    replacement: str,
    message: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    mutate_tsv_value(
        packet / "resource_usage.tsv",
        "case_id",
        "unit_known_answer",
        field,
        replacement,
    )
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert message in checked.stderr


def test_extracted_verifier_rejects_resealed_decoded_pixel_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    report = packet / "decoded_pixel_hashes/GM12878.tsv"
    rows = report.read_text(encoding="utf-8").splitlines()
    report.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "decoded-pixel evidence" in checked.stderr


def test_extracted_verifier_rejects_resealed_repeat2_png_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    write_png(
        packet
        / "figures_repeat2/gm11906_default_run2/01.png",
        (255, 0, 0),
    )
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "hash does not match repeat-2 PNG" in checked.stderr


def test_extracted_verifier_rejects_rehashed_official_metadata_mutation(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    metadata_path = packet / packet_builder.GM11906_SOURCE_METADATA_PACKET_PATH
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["records"][0]["cell_line"] = "GM00000"
    canonical = json.dumps(
        payload["records"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    payload["records_sha256"] = hashlib.sha256(canonical).hexdigest()
    metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "official NCBI metadata snapshot SHA-256 mismatch" in checked.stderr


def test_packet_rejects_incomplete_three_run_shortread_derivation(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    path = (
        validation
        / "public"
        / "outputs/gm11906_default_run1/provenance/"
        "GM11906_MERRF_shortread.alignment.provenance.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["public_inputs"] = [
        row for row in payload["public_inputs"] if row["label"] != "SRR10804590_R2"
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="all six frozen mates"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_oracle_assertion_value_mutation(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    assertions = validation / "public" / packet_builder.ORACLE_ASSERTIONS_PACKET_PATH
    mutate_tsv_value(
        assertions,
        "assertion_id",
        "filter.GM11906.default.candidate_sites",
        "expected",
        "34",
    )
    mutate_tsv_value(
        assertions,
        "assertion_id",
        "filter.GM11906.default.candidate_sites",
        "observed",
        "34",
    )
    with pytest.raises(
        ValueError,
        match="expected value drifted|Cross-platform scientific row",
    ):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_validator_rejects_unexpected_oracle_assertion(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    assertions = validation / "public" / packet_builder.ORACLE_ASSERTIONS_PACKET_PATH
    with assertions.open("a", encoding="utf-8") as handle:
        handle.write("invented.assertion\tPASS\tx\tx\tunexpected fixture row\n")
    oracle_rows = packet_builder.read_frozen_oracle(
        repo / packet_builder.FROZEN_ORACLE_REPOSITORY_PATH
    )

    with pytest.raises(ValueError, match="contains unexpected rows"):
        packet_builder.validate_oracle_assertions(assertions, oracle_rows)


def test_packet_recomputes_compact_candidate_fingerprint(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    candidate = (
        validation
        / "public/observed_contracts/gm12878_lenient/mito_heteroplasmy_candidates.tsv"
    )
    rows = read_tsv(candidate)
    rows[0]["alt_count"] = str(int(rows[0]["alt_count"]) + 1)
    write_tsv(candidate, tuple(rows[0]), [list(row.values()) for row in rows])

    with pytest.raises(ValueError, match="compact-contract fingerprint mismatch"):
        packet_builder.validate_public_contract_evidence(
            validation / "public",
            frozen_oracle_rows(),
        )


def test_packet_recomputes_compact_schema_fingerprint(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    manifest = (
        validation
        / "public/observed_contracts/gm11906_strict/summary_schema_manifest.tsv"
    )
    rows = read_tsv(manifest)
    header = json.loads(rows[0]["header_json"])
    header[0] = f"{header[0]}_changed"
    rows[0]["header_json"] = json.dumps(header, separators=(",", ":"))
    write_tsv(manifest, tuple(rows[0]), [list(row.values()) for row in rows])

    with pytest.raises(ValueError, match="compact-contract fingerprint mismatch"):
        packet_builder.validate_public_contract_evidence(
            validation / "public",
            frozen_oracle_rows(),
        )


@pytest.mark.parametrize(
    "case_id",
    ("gm11906_lenient", "gm12878_strict"),
)
def test_packet_requires_lenient_and_strict_compact_evidence(
    tmp_path: Path,
    case_id: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    shutil.rmtree(validation / "public/observed_contracts" / case_id)

    with pytest.raises(ValueError, match="compact-contract case inventory mismatch"):
        packet_builder.validate_public_contract_evidence(
            validation / "public",
            frozen_oracle_rows(),
        )


def test_packet_rejects_extra_compact_evidence_file(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    case_root = validation / "public/observed_contracts/gm11906_default_run1"
    (case_root / "unbound.tsv").write_text("field\nvalue\n", encoding="utf-8")

    with pytest.raises(ValueError, match="contract directory inventory is invalid"):
        packet_builder.validate_public_contract_evidence(
            validation / "public",
            frozen_oracle_rows(),
        )


@pytest.mark.parametrize("mutation", ("extra_case", "extra_file"))
def test_packet_rejects_resealed_unexpected_ubuntu_contract_entries(
    tmp_path: Path,
    mutation: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    artifact_root = validation / "acceptance/ubuntu_public_validation/artifact"
    contracts = artifact_root / "results/observed_contracts"
    if mutation == "extra_case":
        unexpected = contracts / "unexpected_case"
        unexpected.mkdir()
        (unexpected / "unbound.txt").write_text("unbound\n", encoding="utf-8")
    else:
        case_root = contracts / "gm11906_default_run1"
        (case_root / "unbound.tsv").write_text("field\nvalue\n", encoding="utf-8")
    rewrite_public_artifact_manifest(artifact_root)

    with pytest.raises(
        ValueError,
        match="case inventory mismatch|[Cc]ontract directory inventory",
    ):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_filter_profile_oracle_mutation(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    profiles = validation / "public" / "filter_profile_results.tsv"
    mutate_tsv_value(
        profiles,
        "case_id",
        "gm12878_default",
        "candidate_sites",
        "17",
    )
    with pytest.raises(
        ValueError,
        match="Filter-profile oracle mismatch|Cross-platform scientific row",
    ):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_tracked_oracle_commit_drift(tmp_path: Path) -> None:
    repo, _ = create_release_repo(tmp_path)
    run(["git", "checkout", "-q", "-b", "oracle-drift"], repo)
    oracle = repo / packet_builder.FROZEN_ORACLE_REPOSITORY_PATH
    oracle.write_text(oracle.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    run(["git", "add", oracle.relative_to(repo).as_posix()], repo)
    run(["git", "commit", "-q", "-m", "mutate oracle"], repo)
    run(["git", "checkout", "-q", "main"], repo)
    run(
        [
            "git",
            "merge",
            "-q",
            "--no-ff",
            "oracle-drift",
            "-m",
            "Merge oracle drift fixture",
        ],
        repo,
    )
    commit = run(["git", "rev-parse", "HEAD"], repo)
    validation = create_validation_root(tmp_path, repo, commit)
    with pytest.raises(ValueError, match="frozen v0.3.0 oracle"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_extracted_verifier_rejects_rehashed_input_manifest_mutation(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    manifest = packet / "inputs.sha256"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            packet_builder.FROZEN_PUBLIC_INPUTS[0]["sha256"], "f" * 64
        ),
        encoding="utf-8",
    )
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "seven frozen public FASTQs" in checked.stderr


def test_extracted_verifier_rejects_rehashed_scientific_oracle_mutation(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    assertions = packet / packet_builder.ORACLE_ASSERTIONS_PACKET_PATH
    mutate_tsv_value(
        assertions,
        "assertion_id",
        "filter.GM12878.default.candidate_sites",
        "expected",
        "17",
    )
    mutate_tsv_value(
        assertions,
        "assertion_id",
        "filter.GM12878.default.candidate_sites",
        "observed",
        "17",
    )
    identity_path = packet / "release_identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["scientific_oracle"]["assertion_count"] = len(
        assertions.read_text(encoding="utf-8").splitlines()
    ) - 1
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "oracle assertion value drift" in checked.stderr


@pytest.mark.parametrize("evidence_name", ("claim", "handoff"))
def test_extracted_verifier_rejects_rehashed_narrative_evidence_forgery(
    tmp_path: Path,
    evidence_name: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    if evidence_name == "claim":
        mutate_tsv_value(
            packet / "claim_evidence_matrix.tsv",
            "claim_id",
            "C1",
            "bounded_claim",
            "Unsupported replacement claim",
        )
        expected = "frozen bounded contract"
    else:
        handoff = packet / "manuscript_handoff.tsv"
        first = read_tsv(handoff)[0]
        mutate_tsv_value(
            handoff,
            "result_id",
            first["result_id"],
            "value",
            "999999",
        )
        expected = "do not match filter_profile_results.tsv"
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert expected in checked.stderr


def test_extracted_verifier_rejects_unexpected_oracle_assertion(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    assertions = packet / packet_builder.ORACLE_ASSERTIONS_PACKET_PATH
    with assertions.open("a", encoding="utf-8") as handle:
        handle.write("invented.assertion\tPASS\tx\tx\tunexpected fixture row\n")
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "oracle assertion report contains unexpected rows" in checked.stderr


@pytest.mark.parametrize("mutation", ("candidate", "schema", "missing_strict"))
def test_extracted_verifier_recomputes_compact_public_contracts(
    tmp_path: Path,
    mutation: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    contracts = packet / packet_builder.PUBLIC_CONTRACTS_PACKET_PATH

    if mutation == "candidate":
        candidate = (
            contracts
            / "gm12878_lenient/mito_heteroplasmy_candidates.tsv"
        )
        rows = read_tsv(candidate)
        rows[0]["alt_count"] = str(int(rows[0]["alt_count"]) + 1)
        write_tsv(candidate, tuple(rows[0]), [list(row.values()) for row in rows])
    elif mutation == "schema":
        manifest = contracts / "gm11906_strict/summary_schema_manifest.tsv"
        rows = read_tsv(manifest)
        header = json.loads(rows[0]["header_json"])
        header[0] = f"{header[0]}_changed"
        rows[0]["header_json"] = json.dumps(header, separators=(",", ":"))
        write_tsv(manifest, tuple(rows[0]), [list(row.values()) for row in rows])
    else:
        shutil.rmtree(contracts / "gm12878_strict")

    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "compact-contract" in checked.stderr or "observed_contracts" in checked.stderr


def test_extracted_verifier_rejects_rehashed_unexpected_top_level_file(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    (packet / "unexpected_unbound_file.txt").write_text(
        "unbound evidence\n",
        encoding="utf-8",
    )
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "unexpected top-level packet evidence" in checked.stderr


@pytest.mark.parametrize("mutation", ("extra_case", "extra_file"))
def test_extracted_verifier_rejects_rehashed_unexpected_ubuntu_contract_entries(
    tmp_path: Path,
    mutation: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    artifact_root = packet / "acceptance/ubuntu_public_validation/artifact"
    contracts = artifact_root / "results/observed_contracts"
    if mutation == "extra_case":
        unexpected = contracts / "unexpected_case"
        unexpected.mkdir()
        (unexpected / "unbound.txt").write_text("unbound\n", encoding="utf-8")
    else:
        case_root = contracts / "gm11906_default_run1"
        (case_root / "unbound.tsv").write_text("field\nvalue\n", encoding="utf-8")
    rewrite_public_artifact_manifest(artifact_root)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "compact-contract" in checked.stderr or "observed_contracts" in checked.stderr


def test_extracted_verifier_rejects_rehashed_shortread_provenance_mutation(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    path = (
        packet
        / "public_provenance/GM11906_MERRF_shortread.alignment.provenance.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["public_inputs"] = [
        row for row in payload["public_inputs"] if row["label"] != "SRR10804657_R2"
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    identity_path = packet / "release_identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    for row in identity["public_provenance"]:
        if row["path"] == path.relative_to(packet).as_posix():
            row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    rewrite_manifest(packet)
    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "short-read alignment input inventory is incomplete" in checked.stderr


@pytest.mark.parametrize("dataset", ("short", "long"))
def test_extracted_verifier_rejects_rehashed_duplicate_alignment_input_label(
    tmp_path: Path,
    dataset: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    filename = (
        "GM11906_MERRF_shortread.alignment.provenance.json"
        if dataset == "short"
        else "GM12878_ONT_longread.reduced_alignment.provenance.json"
    )
    path = packet / "public_provenance" / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["public_inputs"].append(dict(payload["public_inputs"][0]))
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rebind_packet_public_provenance(packet, path)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert "duplicate input label" in checked.stderr


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("missing_md5", "digest field inventory"),
        ("extra_field", "digest field inventory"),
        ("wrong_md5", "subset-manifest linkage mismatch"),
    ),
)
def test_extracted_verifier_rejects_rehashed_inexact_nested_digest_inventory(
    tmp_path: Path,
    mutation: str,
    expected_error: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    path = (
        packet
        / "public_provenance/GM12878_ONT_longread.reduced_alignment.provenance.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    record = next(
        row
        for row in payload["public_inputs"]
        if row["label"] == "deterministic_subset_manifest"
    )
    if mutation == "missing_md5":
        record.pop("md5")
    elif mutation == "extra_field":
        record["unexpected"] = "field"
    else:
        record["md5"] = "f" * 32
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rebind_packet_public_provenance(packet, path)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert expected_error in checked.stderr


@pytest.mark.parametrize(
    ("manifest_kind", "filename", "expected_error"),
    [
        (
            "short_alignment",
            "GM11906_MERRF_shortread.alignment.provenance.json",
            "short-read alignment provenance identity mismatch",
        ),
        (
            "long_subset",
            "GM12878_ONT_longread.fastq_subset.provenance.json",
            "long-read subset provenance identity mismatch",
        ),
        (
            "long_alignment",
            "GM12878_ONT_longread.reduced_alignment.provenance.json",
            "long-read alignment provenance identity mismatch",
        ),
    ],
)
@pytest.mark.parametrize("identity_field", ("schema_version", "provenance_type", "dataset_id"))
def test_extracted_verifier_rejects_rehashed_provenance_identity_drift(
    tmp_path: Path,
    manifest_kind: str,
    filename: str,
    expected_error: str,
    identity_field: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"
    path = packet / "public_provenance" / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[identity_field] = f"tampered-{manifest_kind}-{identity_field}"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rebind_packet_public_provenance(packet, path)
    rewrite_manifest(packet)

    checked = verify_packet(packet)
    assert checked.returncode != 0
    assert expected_error in checked.stderr


def test_extracted_verifier_rejects_resealed_derivation_and_subset_semantic_drift(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    base_packet = output / "packet"

    for mutation, expected_error in (
        ("short_command", "short-read alignment derivation mismatch"),
        ("short_parameters", "short-read alignment derivation mismatch"),
        ("long_tools", "long-read alignment derivation mismatch"),
        ("selected_ledger", "long-read deterministic subset derivation mismatch"),
        ("subset_digest", "long-read deterministic subset derivation mismatch"),
    ):
        packet = tmp_path / f"packet-{mutation}"
        shutil.copytree(base_packet, packet)
        short_path = (
            packet
            / "public_provenance/GM11906_MERRF_shortread.alignment.provenance.json"
        )
        subset_path = (
            packet
            / "public_provenance/GM12878_ONT_longread.fastq_subset.provenance.json"
        )
        long_path = (
            packet
            / "public_provenance/GM12878_ONT_longread.reduced_alignment.provenance.json"
        )
        names_path = (
            packet / "public_provenance/GM12878_ONT_longread.selected_qnames.txt"
        )
        changed_paths: list[Path] = []
        if mutation in {"short_command", "short_parameters"}:
            payload = json.loads(short_path.read_text(encoding="utf-8"))
            if mutation == "short_command":
                payload["derivation"].pop("command_template")
            else:
                payload["derivation"]["parameters"] = {"threads": "8"}
            short_path.write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
            changed_paths.append(short_path)
        elif mutation == "long_tools":
            payload = json.loads(long_path.read_text(encoding="utf-8"))
            payload["derivation"]["tool_versions"]["minimap2"] = "2.30"
            long_path.write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
            changed_paths.append(long_path)
        elif mutation == "selected_ledger":
            names_path.write_text(
                "".join(f"arbitrary-{index:04d}\n" for index in range(1000)),
                encoding="utf-8",
            )
            selected_record = file_provenance_record(
                names_path,
                "SRR18110025.deterministic-qnames-1000.fastq.gz.selected_qnames.txt",
                include_md5=True,
            )
            subset = json.loads(subset_path.read_text(encoding="utf-8"))
            subset["selected_query_names"] = selected_record
            subset_path.write_text(
                json.dumps(subset, indent=2) + "\n", encoding="utf-8"
            )
            long = json.loads(long_path.read_text(encoding="utf-8"))
            for record in long["public_inputs"]:
                if record["label"] == "selected_query_names":
                    record.clear()
                    record.update(selected_record, label="selected_query_names")
            long_path.write_text(
                json.dumps(long, indent=2) + "\n", encoding="utf-8"
            )
            changed_paths.extend((names_path, subset_path, long_path))
        else:
            drifted = dict(packet_builder.FROZEN_GM12878_SUBSET_FASTQ_RECORD)
            drifted.update(bytes=10721432, md5="e" * 32, sha256="f" * 64)
            subset = json.loads(subset_path.read_text(encoding="utf-8"))
            subset["subset_fastq"] = drifted
            subset_path.write_text(
                json.dumps(subset, indent=2) + "\n", encoding="utf-8"
            )
            long = json.loads(long_path.read_text(encoding="utf-8"))
            for record in long["public_inputs"]:
                if record["label"] == "deterministic_subset_fastq":
                    record.clear()
                    record.update(drifted, label="deterministic_subset_fastq")
            long_path.write_text(
                json.dumps(long, indent=2) + "\n", encoding="utf-8"
            )
            changed_paths.extend((subset_path, long_path))

        rebind_packet_public_provenance(packet, *changed_paths)
        rewrite_manifest(packet)
        checked = verify_packet(packet)
        assert checked.returncode != 0, mutation
        assert expected_error in checked.stderr, mutation


def test_oracle_checker_reports_three_run_shortread_derivation(tmp_path: Path) -> None:
    public = tmp_path / "public"
    write_public_provenance(public)
    output = public / "outputs" / "gm11906_default_run1"
    audit = oracle_checker.Auditor()
    oracle_checker.assert_shortread_provenance(audit, "gm11906_default_run1", output)
    assert {row.verdict for row in audit.rows} == {"PASS"}
    assert {row.assertion_id for row in audit.rows} == {
        "gm11906_default_run1.shortread.dataset_id",
        "gm11906_default_run1.shortread.derivation_id",
        "gm11906_default_run1.shortread.source_runs",
        "gm11906_default_run1.shortread.raw_input_labels",
    }

    manifest = output / "provenance/GM11906_MERRF_shortread.alignment.provenance.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["public_inputs"] = [
        row for row in payload["public_inputs"] if row["label"] != "SRR10804590_R1"
    ]
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    changed = oracle_checker.Auditor()
    oracle_checker.assert_shortread_provenance(
        changed, "gm11906_default_run1", output
    )
    assert any(
        row.assertion_id.endswith("raw_input_labels") and row.verdict == "FAIL"
        for row in changed.rows
    )


def test_packet_expected_status_ids_match_the_oracle_checker_contract() -> None:
    expected = packet_builder.expected_oracle_assertions(frozen_oracle_rows())
    case_id = "gm12878_default_run1"
    for field, _ in packet_builder.PUBLIC_ORACLE_MODULE_STATUS_SPECS:
        assert f"{case_id}.module_status.{field}" in expected
        assert f"{case_id}.status.{field}" not in expected
    for field, _, _ in packet_builder.PUBLIC_ORACLE_INTERPRETATION_SPECS:
        assert f"{case_id}.interpretation_status.{field}" in expected
        assert f"{case_id}.status.{field}" not in expected


def test_cli_rejects_legacy_doi_argument(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            str(tmp_path / "validation"),
            str(tmp_path / "packet"),
            str(tmp_path / "packet.zip"),
            "--doi",
            "10.5281/zenodo.1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "unrecognized arguments" in completed.stderr


def add_nonregular_entry(root: Path, tmp_path: Path, kind: str) -> Path:
    entry = root / f"unsafe-{kind}"
    if kind == "file_symlink":
        target = root / "regular-target.txt"
        target.write_text("internal evidence\n", encoding="utf-8")
        entry.symlink_to(target)
    elif kind == "external_file_symlink":
        target = tmp_path / "external-payload.txt"
        target.write_text("external payload must not be copied\n", encoding="utf-8")
        entry.symlink_to(target)
    elif kind == "directory_symlink":
        target = tmp_path / "external-directory"
        target.mkdir()
        (target / "payload.txt").write_text("external directory\n", encoding="utf-8")
        entry.symlink_to(target, target_is_directory=True)
    elif kind == "broken_symlink":
        entry.symlink_to(tmp_path / "missing-target")
    elif kind == "fifo":
        os.mkfifo(entry)
    else:  # pragma: no cover - protects the test helper contract.
        raise AssertionError(f"Unsupported nonregular-entry fixture: {kind}")
    return entry


@pytest.mark.parametrize(
    "kind",
    (
        "file_symlink",
        "external_file_symlink",
        "directory_symlink",
        "broken_symlink",
        "fifo",
    ),
)
def test_packet_rejects_nonregular_entries_anywhere_in_source_tree(
    tmp_path: Path,
    kind: str,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, repo, commit)
    add_nonregular_entry(validation / "logs", tmp_path, kind)

    with pytest.raises(ValueError, match="contains a symlink|contains a special file"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))

    assert not (tmp_path / "output" / "packet").exists()


def test_packet_source_file_must_resolve_under_declared_root(tmp_path: Path) -> None:
    source_root = tmp_path / "declared-source"
    source_root.mkdir()
    external = tmp_path / "external-regular-file.txt"
    external.write_text("outside the declared root\n", encoding="utf-8")

    with pytest.raises(ValueError, match="resolves outside its declared source root"):
        packet_builder.validate_regular_file(external, source_root=source_root)


@pytest.mark.parametrize(
    "kind",
    (
        "file_symlink",
        "external_file_symlink",
        "directory_symlink",
        "broken_symlink",
        "fifo",
    ),
)
def test_generated_verifier_rejects_nonregular_packet_entries(
    tmp_path: Path,
    kind: str,
) -> None:
    packet = tmp_path / "unpacked-packet"
    packet.mkdir()
    packet_builder.write_verifier(packet / "verify_bundle.sh")
    add_nonregular_entry(packet, tmp_path, kind)

    checked = subprocess.run(
        [str(packet / "verify_bundle.sh")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert checked.returncode != 0
    assert "packet contains a symlink" in checked.stderr or (
        "packet contains a special file" in checked.stderr
    )
