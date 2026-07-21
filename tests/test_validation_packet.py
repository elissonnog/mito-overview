from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
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
    # Deliberately no release date, DOI, manuscript, README, or archive metadata.
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
    payload = metadata.encode()
    member = tarfile.TarInfo(f"mito_overview-{version}/PKG-INFO")
    member.size = len(payload)
    with tarfile.open(sdist, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload))


def provenance_record(name: str, content: bytes | None = None) -> dict[str, object]:
    payload = content if content is not None else name.encode()
    return {
        "name": name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def file_provenance_record(path: Path, source_name: str) -> dict[str, object]:
    return provenance_record(source_name, path.read_bytes())


def write_public_provenance(public_root: Path) -> None:
    paths = {
        key: public_root / str(spec["source"])
        for key, spec in packet_builder.PUBLIC_PROVENANCE_FILES.items()
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    short = {
        "schema_version": "1.0",
        "provenance_type": "public_alignment",
        "dataset_id": "GM11906_pooled_scATAC",
        "alignment": provenance_record("GM11906_MERRF_shortread.mt.bam"),
        "alignment_index": provenance_record("GM11906_MERRF_shortread.mt.bam.bai"),
        "reference": provenance_record("GM11906_reference.fa"),
        "reference_index": provenance_record("GM11906_reference.fa.fai"),
        "public_inputs": [
            {**provenance_record("SRR10804585_1.fastq.gz"), "label": "SRR10804585_R1"}
        ],
        "derivation": {"derivation_id": "bwa-mem-samtools-sort-v1"},
    }
    paths["shortread_alignment"].write_text(
        json.dumps(short, indent=2) + "\n", encoding="utf-8"
    )
    paths["shortread_source_libraries"].write_text(
        "run_accession\tgeo_accession\tsource_sample_id\tlibrary_strategy\t"
        "library_unit\tcombination_role\tsource_record_url\n"
        "SRR10804585\tGSM4238454\tGM11906\tATAC-seq\tsingle_cell_library\t"
        "pooled_pseudobulk\thttps://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238454\n"
        "SRR10804590\tGSM4238459\tGM11906\tATAC-seq\tsingle_cell_library\t"
        "pooled_pseudobulk\thttps://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238459\n"
        "SRR10804657\tGSM4238526\tGM11906\tATAC-seq\tsingle_cell_library\t"
        "pooled_pseudobulk\thttps://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238526\n",
        encoding="utf-8",
    )

    paths["selected_query_names"].write_text(
        "SRR18110025.100\nSRR18110025.200\n", encoding="utf-8"
    )
    source_fastq = provenance_record("SRR18110025.fastq.gz")
    subset_fastq = provenance_record("SRR18110025.deterministic-qnames-2.fastq.gz")
    selected_names = file_provenance_record(
        paths["selected_query_names"],
        "SRR18110025.deterministic-qnames-2.fastq.gz.selected_qnames.txt",
    )
    subset = {
        "schema_version": "1.0",
        "provenance_type": "deterministic_fastq_query_name_subset",
        "dataset_id": "GM12878_SRR18110025_ONT",
        "source_fastq": source_fastq,
        "subset_fastq": subset_fastq,
        "selected_query_names": selected_names,
        "selection": {
            "algorithm": "smallest_sha256_seeded_query_names_v1",
            "requested_query_names": 2,
            "selected_query_names": 2,
            "seed": "test-selection-seed",
        },
    }
    paths["longread_subset"].write_text(
        json.dumps(subset, indent=2) + "\n", encoding="utf-8"
    )
    subset_record = file_provenance_record(
        paths["longread_subset"], "subset.provenance.json"
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
        "derivation": {
            "derivation_id": "minimap2-map-ont-deterministic-fastq-subset-mapped-only-v1",
            "parameters": {
                "selected_query_names": "2",
                "selection_seed": "test-selection-seed",
            },
        },
    }
    paths["longread_alignment"].write_text(
        json.dumps(long, indent=2) + "\n", encoding="utf-8"
    )


def write_acceptance_evidence(root: Path, commit: str) -> None:
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
                "detached_head": True,
                "clone_worktree_clean": True,
                "public_https_clone": True,
                "isolated_home": True,
                "isolated_tmpdir": True,
                "built_wheel": True,
                "built_sdist": True,
                "installed_wheel": True,
                "executed_outside_checkout": True,
                "command_path": f"commands/{fresh_case}.sh",
                "log_path": f"logs/{fresh_case}.log",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    run_url = f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}"
    api_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}"
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


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + png_chunk(b"IEND", b"")
    )


def write_tsv(path: Path, header: tuple[str, ...], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_evidence_tables(root: Path) -> None:
    normalized = (
        root
        / "public"
        / "observed_normalized"
        / "gm11906_default_run1"
        / "summary.tsv"
    )
    normalized.parent.mkdir(parents=True, exist_ok=True)
    normalized.write_text("metric\tvalue\nstatus\tok\n", encoding="utf-8")
    figure = root / "figures" / "gm11906_default_run1" / "figure.png"
    write_png(figure)

    rows_by_name = {
        "claim_evidence_matrix.tsv": [
            ["C1", "Deterministic fixture output", "unit_known_answer", "Not clinical"]
        ],
        "module_status_matrix.tsv": [
            [
                "GM11906",
                "gm11906_default_run1",
                "mito_qc",
                "ok",
                "",
                "observed_normalized/gm11906_default_run1/summary.tsv",
            ]
        ],
        "resource_usage.tsv": [
            ["unit_known_answer", "1.0", "0.5", "0.1", "1024", "4", "test", "measured", ""]
        ],
        "figure_provenance.tsv": [
            [
                "F1",
                "GM11906",
                "gm11906_default_run1",
                "figures/gm11906_default_run1/figure.png",
                hashlib.sha256(figure.read_bytes()).hexdigest(),
                str(figure.stat().st_size),
                "1",
                "1",
                "ok",
                "observed_normalized/gm11906_default_run1/visual_artifact_inventory.tsv",
            ]
        ],
        "table_provenance.tsv": [
            [
                "T1",
                "GM11906",
                "gm11906_default_run1",
                "observed_normalized/gm11906_default_run1/summary.tsv",
                hashlib.sha256(normalized.read_bytes()).hexdigest(),
                "1",
                "2",
                "normalized scientific evidence",
            ]
        ],
        "public_data_sources.tsv": [
            [
                "GM11906",
                "SRR10804585",
                "PRJNA598179",
                "SAMN13699362",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/example.fastq.gz",
                "a" * 32,
                "b" * 64,
                "10",
                "2026-07-21T00:00:00+00:00",
                "fixed-input reproduction",
                "raw reads excluded",
            ]
        ],
        "manuscript_handoff.tsv": [
            [
                "R1",
                "GM11906",
                "candidate_sites",
                "33",
                "sites",
                "filter_profile_results.tsv",
                "descriptive only",
            ]
        ],
        "limitations.tsv": [
            ["L1", "clinical", "No clinical validation", "Research use claims only"]
        ],
    }
    for name, rows in rows_by_name.items():
        write_tsv(root / name, packet_builder.EVIDENCE_TABLES[name], rows)


def create_validation_root(tmp_path: Path, commit: str) -> Path:
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
    write_cases(root / "cases.tsv", rows)
    (root / "environment.txt").write_text(
        (
            "release_version=v0.3.0\n"
            f"git_commit={commit}\n"
            f"repository={REPOSITORY}\n"
            f"github_actions_run_id={GITHUB_RUN_ID}\n"
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
    (root / "expected" / "TOY-SR-001.tsv").write_text(
        "position\talt_count\n1\t1\n", encoding="utf-8"
    )
    (root / "public" / "filter_profile_results.tsv").write_text(
        "dataset\tprofile\tcandidate_sites\nGM11906\tdefault\t33\n",
        encoding="utf-8",
    )
    (root / "public" / "inputs.sha256").write_text(
        f"{'a' * 64}  GM11906/downloads/SRR10804585_1.fastq.gz\n",
        encoding="utf-8",
    )
    write_public_provenance(root / "public")
    write_distribution_artifacts(root / "dist")
    write_evidence_tables(root)
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
        if path.is_file() and path.name != "artifacts.sha256":
            rows.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                f"{path.relative_to(packet).as_posix()}"
            )
    (packet / "artifacts.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_release_case_gate_requires_complete_passing_set(tmp_path: Path) -> None:
    cases = tmp_path / "cases.tsv"
    rows = required_pass_rows()
    write_cases(cases, rows)
    count, verdicts = packet_builder.validate_cases(cases)
    assert count == len(rows)
    assert verdicts["PASS"] == len(rows)

    write_cases(cases, rows[1:])
    with pytest.raises(ValueError, match="Required release cases are missing"):
        packet_builder.validate_cases(cases)

    rows[0]["verdict"] = "FAIL"
    write_cases(cases, rows)
    with pytest.raises(ValueError, match="Required release cases did not pass"):
        packet_builder.validate_cases(cases)


def test_github_only_packet_builds_and_verifies_from_fresh_extraction(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    packet = output / "packet"

    run_record = json.loads((packet / "run.json").read_text(encoding="utf-8"))
    identity = json.loads((packet / "release_identity.json").read_text(encoding="utf-8"))
    assert run_record["schema_version"] == "2.0"
    assert run_record["validation_profile"] == "github_release_validation_v1"
    assert run_record["github_actions_run_id"] == GITHUB_RUN_ID
    assert identity["git_commit"] == commit
    assert identity["github_actions"]["head_sha"] == commit
    assert set(identity["metadata_sources"]) == {
        "pyproject.toml",
        "mito_overview/__init__.py",
        "CITATION.cff",
    }
    serialized = json.dumps({"run": run_record, "identity": identity}).lower()
    assert "doi" not in serialized
    assert not (packet / "acceptance" / "zenodo_reservation.json").exists()
    assert not any("paper" in path.parts for path in packet.rglob("*"))

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


@pytest.mark.parametrize("name", sorted(packet_builder.EVIDENCE_TABLES))
def test_packet_requires_every_structured_evidence_table(
    tmp_path: Path, name: str
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
    (validation / name).unlink()
    with pytest.raises(ValueError, match="missing or empty"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_secret_like_material(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
    (validation / "logs" / "unit_known_answer.log").write_text(
        "access_token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="secret-like material"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_normalizes_local_absolute_paths(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
    source = validation / "logs" / "unit_known_answer.log"
    source.write_text("source=/Users/alice/private/run.log\n", encoding="utf-8")
    output = tmp_path / "output"
    packet_builder.build_packet(packet_args(validation, repo, output))
    copied = (output / "packet" / "logs" / "unit_known_answer.log").read_text(
        encoding="utf-8"
    )
    assert "/Users/" not in copied
    assert "${HOME}" in copied


def test_packet_rejects_ci_run_identity_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
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
    validation = create_validation_root(tmp_path, commit)
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
    assert "release commit is inconsistent" in checked.stderr


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
