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
    oracle = repo / packet_builder.FROZEN_ORACLE_REPOSITORY_PATH
    oracle.parent.mkdir(parents=True, exist_ok=True)
    oracle.write_bytes(
        (ROOT / packet_builder.FROZEN_ORACLE_REPOSITORY_PATH).read_bytes()
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
        "".join(f"SRR18110025.{index}\n" for index in range(1, 1001)),
        encoding="utf-8",
    )
    source_fastq = frozen_input_record("SRR18110025.fastq.gz")
    subset_fastq = provenance_record("SRR18110025.deterministic-qnames-1000.fastq.gz")
    selected_names = file_provenance_record(
        paths["selected_query_names"],
        "SRR18110025.deterministic-qnames-1000.fastq.gz.selected_qnames.txt",
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
            "requested_query_names": 1000,
            "selected_query_names": 1000,
            "source_records_seen": 193043,
            "seed": "mito-overview-v0.3.0-GM12878-SRR18110025",
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
                "selected_query_names": "1000",
                "selection_seed": "mito-overview-v0.3.0-GM12878-SRR18110025",
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
            ("status", "ok"),
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
        "mito_copy_number_summary.tsv": oracle["copy_number_status"] or "not_applicable",
        "mito_phymer_haplogroup_summary.tsv": oracle["phymer_status"] or "not_configured",
        "mito_methylation_exploratory_summary.tsv": oracle["methylation_status"] or "not_configured",
        "mito_mvtool_annotation_summary.tsv": oracle["mvtool_status"] or "not_configured",
    }
    for filename, status in status_values.items():
        add_metric(filename, [("status", status), ("reason_code", "")])
    numt_rows = [("status", oracle["numt_module_status"] or "not_applicable")]
    if oracle["numt_interpretation_status"]:
        numt_rows.extend(
            [
                ("numt_interpretation_status", oracle["numt_interpretation_status"]),
                ("reason_code", oracle["numt_reason_code"]),
            ]
        )
    else:
        numt_rows.append(("reason_code", ""))
    add_metric("mito_numt_qc_summary.tsv", numt_rows)

    qc_rows = [("status", "ok")]
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
        [("status", "ok"), ("selected_sites", oracle["selected_cosegregation_sites"] or "0")],
    )
    add_metric(
        "mito_deletion_summary.tsv",
        [
            ("status", "ok"),
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

    visual_rows = []
    for index in range(int(oracle["html_count"])):
        visual_rows.append(
            [
                f"report/{index + 1:02d}.html",
                "html",
                "100",
                hashlib.sha256(f"html-{index}".encode()).hexdigest(),
                "",
                "",
                "ok",
            ]
        )
    for index in range(int(oracle["png_count"])):
        visual_rows.append(
            [
                f"figures/{index + 1:02d}.png",
                "png",
                "69",
                hashlib.sha256(f"png-{index}".encode()).hexdigest(),
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
                "2026-07-21T00:00:00+00:00",
                "fixed-input reproducibility and descriptive filter profile",
                "raw reads excluded from Git and validation ZIP",
            ]
        )

    rows_by_name = {
        "claim_evidence_matrix.tsv": [
            ["C1", "Deterministic fixture output", "unit_known_answer", "Not clinical"]
        ],
        "module_status_matrix.tsv": module_rows,
        "resource_usage.tsv": [
            ["unit_known_answer", "1.0", "0.5", "0.1", "1024", "4", "test", "measured", ""]
        ],
        "figure_provenance.tsv": figure_rows,
        "table_provenance.tsv": table_rows,
        "public_data_sources.tsv": public_source_rows,
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
    write_public_input_evidence(root / "public")
    write_public_oracle_evidence(root / "public")
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


def verify_packet(packet: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(packet / "verify_bundle.sh")],
        capture_output=True,
        text=True,
        check=False,
    )


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


def test_packet_requires_all_three_fixed_ci_jobs(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
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
    validation = create_validation_root(tmp_path, commit)
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
    validation = create_validation_root(tmp_path, commit)
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
    with pytest.raises(ValueError, match="Public-input manifest mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_public_source_hash_drift(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
    mutate_tsv_value(
        validation / "public_data_sources.tsv",
        "run_accession",
        "SRR18110025",
        "fastq_sha256",
        "f" * 64,
    )
    with pytest.raises(ValueError, match="public_data_sources.tsv mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_incomplete_three_run_shortread_derivation(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
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
    validation = create_validation_root(tmp_path, commit)
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
    with pytest.raises(ValueError, match="expected value drifted"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_filter_profile_oracle_mutation(tmp_path: Path) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
    profiles = validation / "public" / "filter_profile_results.tsv"
    mutate_tsv_value(
        profiles,
        "case_id",
        "gm12878_default",
        "candidate_sites",
        "17",
    )
    with pytest.raises(ValueError, match="Filter-profile oracle mismatch"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_packet_rejects_tracked_oracle_commit_drift(tmp_path: Path) -> None:
    repo, _ = create_release_repo(tmp_path)
    oracle = repo / packet_builder.FROZEN_ORACLE_REPOSITORY_PATH
    oracle.write_text(oracle.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    run(["git", "add", oracle.relative_to(repo).as_posix()], repo)
    run(["git", "commit", "-q", "-m", "mutate oracle"], repo)
    commit = run(["git", "rev-parse", "HEAD"], repo)
    validation = create_validation_root(tmp_path, commit)
    with pytest.raises(ValueError, match="frozen v0.3.0 oracle"):
        packet_builder.build_packet(packet_args(validation, repo, tmp_path / "output"))


def test_extracted_verifier_rejects_rehashed_input_manifest_mutation(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
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
    validation = create_validation_root(tmp_path, commit)
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


def test_extracted_verifier_rejects_rehashed_shortread_provenance_mutation(
    tmp_path: Path,
) -> None:
    repo, commit = create_release_repo(tmp_path)
    validation = create_validation_root(tmp_path, commit)
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
