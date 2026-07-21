#!/usr/bin/env python3
"""Build the self-checking mito-overview v0.3.0 validation packet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import stat
import subprocess
import tarfile
import tomllib
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit


EXPECTED_RELEASE_VERSION = "v0.3.0"
EXPECTED_PACKAGE_NAME = "mito-overview"
EXPECTED_LICENSE = "MIT"
EXPECTED_CREATORS = ("Elisson Lopes", "Xiaowu Gai")
PACKET_SCHEMA_VERSION = "2.0"
VALIDATION_PROFILE = "github_release_validation_v1"
PUBLIC_ENVIRONMENT_PACKET_PATH = "public_environment"
PUBLIC_ENVIRONMENT_FILES = (
    "conda-explicit.txt",
    "network_entrypoint_contract.tsv",
    "network_isolation.tsv",
    "pip-freeze.txt",
    "runtime_versions.json",
)
EXPECTED_RUNTIME_PACKAGES = {
    "mito-overview": "0.3.0",
    "pysam": "0.24.0",
    "pandas": "3.0.3",
    "numpy": "2.5.1",
    "matplotlib": "3.11.0",
    "requests": "2.34.2",
    "pytest": "9.1.1",
    "build": "1.5.0",
    "setuptools": "82.0.1",
    "wheel": "0.47.0",
    "python-docx": "1.2.0",
}
PUBLIC_RUNTIME_PLATFORMS = {
    "linux-64": {
        "system": "Linux",
        "machine": "x86_64",
        "network_platform": "Linux/x86_64",
        "isolation_method": "linux_unshare_network_namespace",
    },
    "osx-64": {
        "system": "Darwin",
        "machine": "x86_64",
        "network_platform": "Darwin/x86_64",
        "isolation_method": "macos_sandbox_exec_deny_network",
    },
    "osx-arm64": {
        "system": "Darwin",
        "machine": "arm64",
        "network_platform": "Darwin/arm64",
        "isolation_method": "macos_sandbox_exec_deny_network",
    },
}
NETWORK_ISOLATION_FIELDS = (
    "schema_version",
    "platform",
    "isolation_method",
    "isolation_scope",
    "parent_loopback_control",
    "isolated_loopback_probe",
    "probe_target",
    "probe_error",
    "invoking_uid",
    "invoking_gid",
    "child_uid",
    "child_gid",
    "network_isolation_verdict",
)
EXPECTED_NETWORK_ENTRYPOINT_CONTRACT = (
    "entrypoint\tcontrol\tscope\n"
    "all IP sockets\tOS process-tree isolation\t"
    "macOS sandbox-exec deny network* or Linux network namespace\n"
    "curl\tPATH canary\trelease public-data runners\n"
    "wget\tPATH canary\tdefensive command guard\n"
    "mvTool requests\tMVTOOL_MODE=disabled\tpipeline external annotation module\n"
)
ZENODO_DOI_PATTERN = r"10\.5281/zenodo\.[1-9][0-9]*"
ZENODO_RESERVATION_PACKET_PATH = "acceptance/zenodo_reservation.json"
ZENODO_RESERVATION_SOURCE = "authenticated_zenodo_deposition_api"
EXPECTED_GITHUB_BRANCH = "main"
EXPECTED_GITHUB_WORKFLOW_PATH = ".github/workflows/smoke-tests.yml"
ZENODO_TEMPLATE_PATH = "resources/zenodo/mito_overview_v0.3.0_draft.json"
MANUSCRIPT_PATH = "paper/preprint_draft.md"
PLACEHOLDER_PATTERN = re.compile(
    r"(?i)(?:<[^>]+>|\b(?:TBD|TODO|TBA|UNRESERVED|PLACEHOLDER|EXAMPLE[-_ ]DOI)\b)"
)
ZENODO_PUBLIC_METADATA_FIELDS = {
    "title",
    "upload_type",
    "description",
    "creators",
    "license",
    "version",
    "publication_date",
    "related_identifiers",
    "keywords",
}

PUBLIC_PROVENANCE_FILES = {
    "shortread_source_libraries": {
        "source": (
            "outputs/gm11906_default_run1/provenance/"
            "GM11906_MERRF_shortread.source_libraries.tsv"
        ),
        "packet": "public_provenance/GM11906_MERRF_shortread.source_libraries.tsv",
    },
    "shortread_alignment": {
        "source": (
            "outputs/gm11906_default_run1/provenance/"
            "GM11906_MERRF_shortread.alignment.provenance.json"
        ),
        "packet": "public_provenance/GM11906_MERRF_shortread.alignment.provenance.json",
    },
    "longread_subset": {
        "source": (
            "outputs/gm12878_default_run1/provenance/"
            "GM12878_ONT_longread.fastq_subset.provenance.json"
        ),
        "packet": "public_provenance/GM12878_ONT_longread.fastq_subset.provenance.json",
    },
    "longread_alignment": {
        "source": (
            "outputs/gm12878_default_run1/provenance/"
            "GM12878_ONT_longread.reduced_alignment.provenance.json"
        ),
        "packet": (
            "public_provenance/"
            "GM12878_ONT_longread.reduced_alignment.provenance.json"
        ),
    },
    "selected_query_names": {
        "source": (
            "outputs/gm12878_default_run1/provenance/"
            "GM12878_ONT_longread.selected_qnames.txt"
        ),
        "packet": "public_provenance/GM12878_ONT_longread.selected_qnames.txt",
    },
}

PUBLIC_INPUT_MANIFEST_HEADER = (
    "schema_version",
    "dataset_id",
    "run_accession",
    "sample_accession",
    "sample_alias",
    "sample_title",
    "source_sample_id",
    "library_strategy",
    "library_unit",
    "source_record_url",
    "filename",
    "bytes",
    "md5",
    "sha256",
    "fastq_records",
    "url",
)
FROZEN_PUBLIC_INPUTS = (
    {
        "schema_version": "1.0",
        "dataset_id": "GM11906_pooled_scATAC",
        "run_accession": "SRR10804585",
        "sample_accession": "SAMN13699362",
        "sample_alias": "GSM4238454",
        "sample_title": "MERFF-29-S42",
        "source_sample_id": "GM11906",
        "library_strategy": "ATAC-seq",
        "library_unit": "single_cell_library",
        "source_record_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238454",
        "filename": "SRR10804585_1.fastq.gz",
        "bytes": "8795676",
        "md5": "3f5ea26a5791894071462d4970bc9e5a",
        "sha256": "b69746cb61d8bf3bc25887d6ece3c60db3acc7baaefd84a9a8b5d6ffce33288d",
        "fastq_records": "377587",
        "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_1.fastq.gz",
    },
    {
        "schema_version": "1.0",
        "dataset_id": "GM11906_pooled_scATAC",
        "run_accession": "SRR10804585",
        "sample_accession": "SAMN13699362",
        "sample_alias": "GSM4238454",
        "sample_title": "MERFF-29-S42",
        "source_sample_id": "GM11906",
        "library_strategy": "ATAC-seq",
        "library_unit": "single_cell_library",
        "source_record_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238454",
        "filename": "SRR10804585_2.fastq.gz",
        "bytes": "8817420",
        "md5": "c5b408425612f63b33cefd2d49c157d1",
        "sha256": "1fca2c35a955a4ed232465d8392bc04683828229178aee7915929e67b2aac961",
        "fastq_records": "377587",
        "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_2.fastq.gz",
    },
    {
        "schema_version": "1.0",
        "dataset_id": "GM11906_pooled_scATAC",
        "run_accession": "SRR10804590",
        "sample_accession": "SAMN13699398",
        "sample_alias": "GSM4238459",
        "sample_title": "MERFF-33-S46",
        "source_sample_id": "GM11906",
        "library_strategy": "ATAC-seq",
        "library_unit": "single_cell_library",
        "source_record_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238459",
        "filename": "SRR10804590_1.fastq.gz",
        "bytes": "1006749",
        "md5": "e8b5132a8be8c179bfc6dbc0f3e1bee9",
        "sha256": "e47ceceb03d44483b4948fe9c631ebff307f5ec68a1deec978f1122695fa58fc",
        "fastq_records": "70920",
        "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_1.fastq.gz",
    },
    {
        "schema_version": "1.0",
        "dataset_id": "GM11906_pooled_scATAC",
        "run_accession": "SRR10804590",
        "sample_accession": "SAMN13699398",
        "sample_alias": "GSM4238459",
        "sample_title": "MERFF-33-S46",
        "source_sample_id": "GM11906",
        "library_strategy": "ATAC-seq",
        "library_unit": "single_cell_library",
        "source_record_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238459",
        "filename": "SRR10804590_2.fastq.gz",
        "bytes": "795885",
        "md5": "4d6977526136739de2d90baa8d45b484",
        "sha256": "05b2375b30b02c02e9206981eb2fe2d08babbc2a5809f8354ef56d0ac1550776",
        "fastq_records": "70920",
        "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_2.fastq.gz",
    },
    {
        "schema_version": "1.0",
        "dataset_id": "GM11906_pooled_scATAC",
        "run_accession": "SRR10804657",
        "sample_accession": "SAMN13699338",
        "sample_alias": "GSM4238526",
        "sample_title": "MERFF-94-S107",
        "source_sample_id": "GM11906",
        "library_strategy": "ATAC-seq",
        "library_unit": "single_cell_library",
        "source_record_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238526",
        "filename": "SRR10804657_1.fastq.gz",
        "bytes": "21510555",
        "md5": "8f082f73cb64bf56ea8a053fe80eeb06",
        "sha256": "1afaf310ce9ffa77e1c3d61a0714e839d21000941d414cc7bf6fb590c3b665f2",
        "fastq_records": "915286",
        "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_1.fastq.gz",
    },
    {
        "schema_version": "1.0",
        "dataset_id": "GM11906_pooled_scATAC",
        "run_accession": "SRR10804657",
        "sample_accession": "SAMN13699338",
        "sample_alias": "GSM4238526",
        "sample_title": "MERFF-94-S107",
        "source_sample_id": "GM11906",
        "library_strategy": "ATAC-seq",
        "library_unit": "single_cell_library",
        "source_record_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238526",
        "filename": "SRR10804657_2.fastq.gz",
        "bytes": "21573731",
        "md5": "62b7d1b2294a580c021f5fa1f52609be",
        "sha256": "bfc555c7e722695b02110027757bba4d7fc88f487798423cd6809e8a771a5184",
        "fastq_records": "915286",
        "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_2.fastq.gz",
    },
    {
        "schema_version": "1.0",
        "dataset_id": "GM12878_ONT",
        "run_accession": "SRR18110025",
        "sample_accession": "SAMN26195906",
        "sample_alias": "GM12878_mtDNA",
        "sample_title": "Human GM12878 Cell Line",
        "source_sample_id": "GM12878",
        "library_strategy": "OTHER",
        "library_unit": "targeted_mt_library",
        "source_record_url": "https://www.ebi.ac.uk/ena/browser/view/SRR18110025",
        "filename": "SRR18110025.fastq.gz",
        "bytes": "2033558460",
        "md5": "d5bfb9aeba04cae5f3dd79462a42e5b0",
        "sha256": "c0872ee9ceb772ee5a4b76735c0d670e2159764b23dd800b6eb1f4933da11320",
        "fastq_records": "193043",
        "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR181/025/SRR18110025/SRR18110025_1.fastq.gz",
    },
)
FROZEN_PUBLIC_SOURCE_METADATA = {
    "SRR10804585": {
        "dataset": "GM11906 pooled single-cell ATAC-seq pseudo-bulk",
        "study_accession": "PRJNA598179",
        "instrument_model": "NextSeq 550",
    },
    "SRR10804590": {
        "dataset": "GM11906 pooled single-cell ATAC-seq pseudo-bulk",
        "study_accession": "PRJNA598179",
        "instrument_model": "NextSeq 550",
    },
    "SRR10804657": {
        "dataset": "GM11906 pooled single-cell ATAC-seq pseudo-bulk",
        "study_accession": "PRJNA598179",
        "instrument_model": "NextSeq 550",
    },
    "SRR18110025": {
        "dataset": "GM12878 ONT targeted-mt proof-of-principle",
        "study_accession": "PRJNA809571",
        "instrument_model": "GridION",
    },
}
FROZEN_ORACLE_REPOSITORY_PATH = Path(
    "examples/public_validation/public_validation_oracle_v0.3.0.tsv"
)
FROZEN_ORACLE_PACKET_PATH = "public_validation_oracle_v0.3.0.tsv"
FROZEN_ORACLE_SHA256 = "dac769dcbac622f8a2df1363c08a926b0130082208d16b77a57d581cb7ccf76e"
FROZEN_RAW_INPUT_MANIFEST_SHA256 = (
    "188d9e493c7cc43dc63c6bfe972914af5ae42cadb6cb2f59092cb13452adf756"
)
ORACLE_ASSERTIONS_PACKET_PATH = "oracle_assertions.tsv"
RAW_INPUTS_PACKET_PATH = "raw_inputs.tsv"
CACHE_SEAL_PACKET_PATH = "CACHE_SEAL.sha256"
PUBLIC_ORACLE_CASES = {
    ("GM11906", "lenient"): ("gm11906_lenient",),
    ("GM11906", "default"): ("gm11906_default_run1", "gm11906_default_run2"),
    ("GM11906", "strict"): ("gm11906_strict",),
    ("GM12878", "lenient"): ("gm12878_lenient",),
    ("GM12878", "default"): ("gm12878_default_run1", "gm12878_default_run2"),
    ("GM12878", "strict"): ("gm12878_strict",),
}

REQUIRED_TOP_LEVEL = (
    "run.json",
    "release_identity.json",
    "cases.tsv",
    "acceptance",
    "claim_evidence_matrix.tsv",
    "module_status_matrix.tsv",
    "resource_usage.tsv",
    "figure_provenance.tsv",
    "table_provenance.tsv",
    "public_data_sources.tsv",
    "manuscript_handoff.tsv",
    "limitations.tsv",
    "environment.txt",
    "commands",
    "logs",
    "dist",
    "expected",
    "observed_normalized",
    "public_provenance",
    PUBLIC_ENVIRONMENT_PACKET_PATH,
    "figures",
    "filter_profile_results.tsv",
    "inputs.sha256",
    RAW_INPUTS_PACKET_PATH,
    CACHE_SEAL_PACKET_PATH,
    FROZEN_ORACLE_PACKET_PATH,
    ORACLE_ASSERTIONS_PACKET_PATH,
    "artifacts.sha256",
    "verify_bundle.sh",
)

EVIDENCE_TABLES = {
    "claim_evidence_matrix.tsv": (
        "claim_id",
        "bounded_claim",
        "evidence",
        "limitation",
    ),
    "module_status_matrix.tsv": (
        "dataset",
        "case_id",
        "module",
        "status",
        "reason_code",
        "source_table",
    ),
    "resource_usage.tsv": (
        "case_id",
        "wall_seconds",
        "user_cpu_seconds",
        "system_cpu_seconds",
        "max_rss_kb",
        "threads",
        "platform",
        "measurement_status",
        "reason",
    ),
    "figure_provenance.tsv": (
        "figure_id",
        "dataset",
        "case_id",
        "packet_path",
        "sha256",
        "bytes",
        "width",
        "height",
        "visual_status",
        "source_inventory",
    ),
    "table_provenance.tsv": (
        "table_id",
        "dataset",
        "case_id",
        "packet_path",
        "sha256",
        "rows",
        "columns",
        "purpose",
    ),
    "public_data_sources.tsv": (
        "dataset",
        "run_accession",
        "study_accession",
        "sample_accession",
        "cell_line",
        "platform",
        "instrument_model",
        "library_strategy",
        "fastq_url",
        "fastq_md5",
        "fastq_sha256",
        "fastq_bytes",
        "metadata_recorded_utc",
        "role",
        "redistribution",
    ),
    "manuscript_handoff.tsv": (
        "result_id",
        "dataset",
        "metric",
        "value",
        "unit",
        "source_table",
        "claim_boundary",
    ),
    "limitations.tsv": (
        "limitation_id",
        "scope",
        "limitation",
        "release_effect",
    ),
}

FRESH_CLONE_CASE_ID = "fresh_clone_candidate_commit"
GITHUB_ACTIONS_LINUX_CASE_ID = "github_actions_linux_candidate_commit"
GITHUB_ACTIONS_MACOS_CASE_ID = "github_actions_macos_candidate_commit"
GITHUB_ACTIONS_MACOS_ARM64_CASE_ID = "github_actions_macos_arm64_candidate_commit"
ACCEPTANCE_CASE_IDS = {
    FRESH_CLONE_CASE_ID,
    GITHUB_ACTIONS_LINUX_CASE_ID,
    GITHUB_ACTIONS_MACOS_CASE_ID,
    GITHUB_ACTIONS_MACOS_ARM64_CASE_ID,
}
EXPECTED_GITHUB_WORKFLOW = "smoke-tests"
EXPECTED_GITHUB_JOBS = {
    GITHUB_ACTIONS_LINUX_CASE_ID: {
        "platform": "linux-64",
        "label": "ubuntu-24.04",
        "name": "Unit and synthetic tests (ubuntu-24.04)",
    },
    GITHUB_ACTIONS_MACOS_CASE_ID: {
        "platform": "osx-64",
        "label": "macos-15-intel",
        "name": "Unit and synthetic tests (macos-15-intel)",
    },
    GITHUB_ACTIONS_MACOS_ARM64_CASE_ID: {
        "platform": "osx-arm64",
        "label": "macos-15",
        "name": "Unit and synthetic tests (macos-15)",
    },
}

REQUIRED_PASS_CASES = {
    "unit_known_answer",
    "cli_step_listing",
    "strict_generic_dry_run",
    "synthetic_longread_smoke",
    "synthetic_shortread_smoke",
    "synthetic_longread_nomethyl_smoke",
    "standalone_minimal_smoke",
    "package_build",
    "public_validation_matrix",
    "gm11906_default_run1",
    "gm11906_default_run2",
    "gm11906_lenient",
    "gm11906_strict",
    "gm12878_default_run1",
    "gm12878_default_run2",
    "gm12878_lenient",
    "gm12878_strict",
    "gm11906_repeatability",
    "gm12878_repeatability",
    "gm11906_visual_integrity",
    "gm12878_visual_integrity",
    "filter_profiles",
    "offline_isolation",
} | ACCEPTANCE_CASE_IDS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a GitHub-bound v0.3.0 release-validation packet. "
            "Archive DOI and manuscript inputs are intentionally not part of this contract."
        )
    )
    parser.add_argument("validation_root", type=Path)
    parser.add_argument("packet_root", type=Path)
    parser.add_argument("zip_path", type=Path)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Clean Git repository whose HEAD and metadata define the release identity",
    )
    parser.add_argument(
        "--commit",
        help="Deprecated identity assertion; when supplied it must equal repository HEAD",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--version", default=EXPECTED_RELEASE_VERSION)
    parser.add_argument("--repository", default="https://github.com/elissonnog/mito-overview")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Required directory not found: {source}")
    if not any(path.is_file() for path in source.rglob("*")):
        raise ValueError(f"Required directory contains no evidence files: {source}")
    shutil.copytree(source, destination)


def git_output(repo_root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise ValueError(f"Unable to inspect release repository: {detail.strip()}") from error
    return result.stdout.strip()


def normalize_project_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def require_release_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    normalized = value.strip()
    if PLACEHOLDER_PATTERN.search(normalized):
        raise ValueError(f"{label} contains placeholder text: {normalized!r}")
    return normalized


def normalize_license(value: object, label: str) -> str:
    observed = require_release_text(value, label)
    if observed.lower() not in {"mit", "mit-license"}:
        raise ValueError(f"{label} must identify the MIT license: {observed!r}")
    return EXPECTED_LICENSE


def canonical_person_name(value: object, label: str) -> str:
    observed = require_release_text(value, label)
    if "," not in observed:
        return " ".join(observed.split())
    family, given = observed.split(",", 1)
    if not family.strip() or not given.strip():
        raise ValueError(f"{label} is not a valid 'Family, Given' name: {observed!r}")
    return f"{' '.join(given.split())} {' '.join(family.split())}"


def top_level_yaml_scalar(text: str, key: str, label: str) -> str:
    matches = re.findall(rf"(?m)^{re.escape(key)}:\s*([^\n#]+?)\s*$", text)
    if len(matches) != 1:
        raise ValueError(f"{label} must define exactly one top-level {key}")
    return require_release_text(matches[0].strip("'\""), f"{label} {key}")


def citation_authors(text: str) -> list[str]:
    match = re.search(r"(?ms)^authors:\s*\n(?P<body>.*?)(?=^[^\s]|\Z)", text)
    if match is None:
        raise ValueError("CITATION.cff does not define an authors list")
    authors: list[str] = []
    for index, item in enumerate(re.split(r"(?m)^  -\s+", match.group("body"))[1:]):
        family_match = re.search(r"(?m)^family-names:\s*([^\n#]+?)\s*$", item)
        given_match = re.search(r"(?m)^\s*given-names:\s*([^\n#]+?)\s*$", item)
        if family_match is None or given_match is None:
            raise ValueError(f"CITATION.cff author {index} lacks family-names or given-names")
        family = require_release_text(
            family_match.group(1).strip("'\""), f"CITATION.cff author {index} family-names"
        )
        given = require_release_text(
            given_match.group(1).strip("'\""), f"CITATION.cff author {index} given-names"
        )
        authors.append(f"{given} {family}")
    return authors


def canonicalize_zenodo_metadata(
    metadata: object,
    *,
    expected_doi: str | None,
    reservation_mode: str,
) -> dict[str, object]:
    if not isinstance(metadata, dict):
        raise ValueError("Zenodo release metadata must be an object")
    expected_fields = ZENODO_PUBLIC_METADATA_FIELDS | {"prereserve_doi"}
    if set(metadata) != expected_fields:
        raise ValueError(
            "Zenodo release metadata is not the required public field set: "
            f"missing={sorted(expected_fields - set(metadata))}, "
            f"unexpected={sorted(set(metadata) - expected_fields)}"
        )

    title = require_release_text(metadata.get("title"), "Zenodo title")
    upload_type = require_release_text(metadata.get("upload_type"), "Zenodo upload_type")
    description = require_release_text(metadata.get("description"), "Zenodo description")
    version = require_release_text(metadata.get("version"), "Zenodo version")
    publication_date = require_release_text(
        metadata.get("publication_date"), "Zenodo publication_date"
    )
    try:
        datetime.strptime(publication_date, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError("Zenodo publication_date must use YYYY-MM-DD") from error
    if upload_type != "software":
        raise ValueError(f"Zenodo upload_type must be software: {upload_type!r}")

    creators = metadata.get("creators")
    if not isinstance(creators, list) or not creators:
        raise ValueError("Zenodo creators must be a nonempty object list")
    creator_names: list[str] = []
    for index, creator in enumerate(creators):
        if not isinstance(creator, dict):
            raise ValueError(f"Zenodo creator {index} must be an object")
        unexpected = set(creator) - {"name", "affiliation", "orcid"}
        if unexpected:
            raise ValueError(f"Zenodo creator {index} has unexpected fields: {sorted(unexpected)}")
        creator_names.append(canonical_person_name(creator.get("name"), f"Zenodo creator {index}"))
        require_release_text(creator.get("affiliation"), f"Zenodo creator {index} affiliation")
        if "orcid" in creator:
            require_release_text(creator["orcid"], f"Zenodo creator {index} ORCID")

    related = metadata.get("related_identifiers")
    if not isinstance(related, list):
        raise ValueError("Zenodo related_identifiers must be a list")
    repositories: list[str] = []
    for index, item in enumerate(related):
        if not isinstance(item, dict):
            raise ValueError(f"Zenodo related identifier {index} must be an object")
        unexpected = set(item) - {"identifier", "relation", "scheme", "resource_type"}
        if unexpected:
            raise ValueError(
                f"Zenodo related identifier {index} has unexpected fields: {sorted(unexpected)}"
            )
        identifier = require_release_text(
            item.get("identifier"), f"Zenodo related identifier {index} identifier"
        )
        relation = require_release_text(
            item.get("relation"), f"Zenodo related identifier {index} relation"
        )
        if relation == "isSupplementTo":
            repositories.append(identifier)
    if len(repositories) != 1:
        raise ValueError("Zenodo metadata must identify exactly one repository as isSupplementTo")

    keywords = metadata.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("Zenodo keywords must be a nonempty list")
    canonical_keywords = [
        require_release_text(value, f"Zenodo keyword {index}")
        for index, value in enumerate(keywords)
    ]

    reservation = metadata.get("prereserve_doi")
    if reservation_mode == "template":
        if reservation is not True:
            raise ValueError("Zenodo template must request prereserve_doi=true")
    elif reservation_mode == "evidence":
        if not isinstance(reservation, dict) or set(reservation) != {"doi", "recid"}:
            raise ValueError("Zenodo evidence prereserve_doi is malformed")
        if reservation.get("doi") != expected_doi:
            raise ValueError("Zenodo evidence prereserve_doi does not match the requested DOI")
    else:
        raise ValueError(f"Unsupported Zenodo reservation mode: {reservation_mode}")

    return {
        "title": title,
        "upload_type": upload_type,
        "description": description,
        "creators": creator_names,
        "license": normalize_license(metadata.get("license"), "Zenodo license"),
        "version": version,
        "publication_date": publication_date,
        "repository": repositories[0],
        "keywords": canonical_keywords,
        **({"doi": expected_doi} if expected_doi is not None else {}),
    }


def parse_environment_identity(path: Path) -> dict[str, str]:
    required = {
        "release_version",
        "git_commit",
        "repository",
        "github_actions_run_id",
    }
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in required:
            continue
        if key in values:
            raise ValueError(f"environment.txt contains duplicate identity key: {key}")
        values[key] = value.strip()
    missing = sorted(required - values.keys())
    if missing:
        raise ValueError(f"environment.txt is missing release identity keys: {', '.join(missing)}")
    return values


def parse_network_isolation_evidence(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Network-isolation evidence must be a regular non-symlink file")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != ("field", "value"):
            raise ValueError("Network-isolation evidence has an invalid schema")
        rows = list(reader)
    if any(
        set(row) != {"field", "value"}
        or row.get("field") is None
        or row.get("value") is None
        for row in rows
    ):
        raise ValueError("Network-isolation evidence contains malformed rows")
    fields = tuple(row.get("field", "") for row in rows)
    if fields != NETWORK_ISOLATION_FIELDS:
        raise ValueError(
            "Network-isolation evidence field inventory or order is invalid: "
            f"{fields!r}"
        )
    values = {row["field"]: row.get("value", "") for row in rows}
    if len(values) != len(rows):
        raise ValueError("Network-isolation evidence contains duplicate fields")

    platform_matches = [
        specification
        for specification in PUBLIC_RUNTIME_PLATFORMS.values()
        if specification["network_platform"] == values["platform"]
    ]
    if len(platform_matches) != 1:
        raise ValueError(
            f"Network-isolation platform is unsupported: {values['platform']!r}"
        )
    specification = platform_matches[0]
    expected = {
        "schema_version": "1.0",
        "isolation_method": specification["isolation_method"],
        "isolation_scope": "process_tree",
        "parent_loopback_control": "reachable",
        "isolated_loopback_probe": "blocked",
        "probe_target": "parent_loopback_listener",
        "network_isolation_verdict": "PASS",
    }
    for field, expected_value in expected.items():
        if values[field] != expected_value:
            raise ValueError(
                f"Network-isolation evidence mismatch for {field}: "
                f"{values[field]!r} != {expected_value!r}"
            )
    if not values["probe_error"].strip():
        raise ValueError("Network-isolation evidence lacks a blocked-probe error")
    for field in ("invoking_uid", "invoking_gid", "child_uid", "child_gid"):
        if not re.fullmatch(r"[0-9]+", values[field]):
            raise ValueError(f"Network-isolation identity is invalid for {field}")
    if values["invoking_uid"] != values["child_uid"]:
        raise ValueError("Network-isolation child UID does not match the invoking UID")
    if values["invoking_gid"] != values["child_gid"]:
        raise ValueError("Network-isolation child GID does not match the invoking GID")
    return values


def validate_public_environment(
    environment_root: Path,
    repo_root: Path | None = None,
) -> dict[str, object]:
    if environment_root.is_symlink() or not environment_root.is_dir():
        raise ValueError("Public environment evidence must be a regular directory")
    children = list(environment_root.iterdir())
    if any(child.is_symlink() or not child.is_file() for child in children):
        raise ValueError("Public environment evidence must contain only regular files")
    observed_files = tuple(sorted(child.name for child in children))
    if observed_files != PUBLIC_ENVIRONMENT_FILES:
        raise ValueError(
            "Public environment evidence inventory mismatch: "
            f"{observed_files!r} != {PUBLIC_ENVIRONMENT_FILES!r}"
        )

    isolation = parse_network_isolation_evidence(
        environment_root / "network_isolation.tsv"
    )
    runtime_path = environment_root / "runtime_versions.json"
    try:
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Public runtime version evidence is malformed JSON") from error
    expected_runtime_keys = {
        "schema_version",
        "platform_id",
        "system",
        "machine",
        "python",
        "python_executable",
        "mito_overview_module",
        "packages",
        "samtools",
        "htslib",
        "minimap2",
        "bwa",
        "threads",
        "installed_distribution_required",
    }
    if not isinstance(runtime, dict) or set(runtime) != expected_runtime_keys:
        raise ValueError("Public runtime version evidence has an invalid schema")
    platform_id = runtime.get("platform_id")
    if platform_id not in PUBLIC_RUNTIME_PLATFORMS:
        raise ValueError(f"Public runtime platform is unsupported: {platform_id!r}")
    platform_specification = PUBLIC_RUNTIME_PLATFORMS[str(platform_id)]
    expected_runtime = {
        "schema_version": "1.0",
        "system": platform_specification["system"],
        "machine": platform_specification["machine"],
        "python": "3.12.13",
        "packages": EXPECTED_RUNTIME_PACKAGES,
        "samtools": "samtools 1.23.1",
        "htslib": "Using htslib 1.23.1",
        "minimap2": "2.31-r1302",
        "bwa": "0.7.19-r1273",
        "threads": 4,
        "installed_distribution_required": True,
    }
    for field, expected_value in expected_runtime.items():
        if runtime.get(field) != expected_value:
            raise ValueError(
                f"Public runtime evidence mismatch for {field}: "
                f"{runtime.get(field)!r} != {expected_value!r}"
            )
    if isolation["platform"] != platform_specification["network_platform"]:
        raise ValueError("Runtime and network-isolation platform identities disagree")

    python_executable = runtime.get("python_executable")
    if not isinstance(python_executable, str) or not python_executable.strip():
        raise ValueError("Public runtime Python executable is missing")
    module_text = runtime.get("mito_overview_module")
    if not isinstance(module_text, str) or not module_text.replace("\\", "/").endswith(
        "/site-packages/mito_overview/__init__.py"
    ):
        raise ValueError("Public runtime did not resolve mito-overview from site-packages")
    if repo_root is not None and Path(module_text).is_absolute():
        resolved_module = Path(module_text).resolve(strict=False)
        resolved_repo = repo_root.resolve(strict=False)
        if resolved_module == resolved_repo or resolved_repo in resolved_module.parents:
            raise ValueError("Public runtime imported mito-overview from the checkout")

    freeze_lines = [
        line.strip()
        for line in (environment_root / "pip-freeze.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    frozen_names: set[str] = set()
    for line in freeze_lines:
        if "==" in line:
            name = line.split("==", 1)[0]
        elif " @ " in line:
            name = line.split(" @ ", 1)[0]
        else:
            continue
        frozen_names.add(normalize_project_name(name.strip()))
    expected_names = {normalize_project_name(name) for name in EXPECTED_RUNTIME_PACKAGES}
    missing_names = sorted(expected_names - frozen_names)
    if missing_names:
        raise ValueError(
            f"Public pip-freeze evidence is missing pinned packages: {missing_names}"
        )
    if not (environment_root / "conda-explicit.txt").read_text(
        encoding="utf-8"
    ).strip():
        raise ValueError("Public conda environment evidence is empty")
    if (environment_root / "network_entrypoint_contract.tsv").read_text(
        encoding="utf-8"
    ) != EXPECTED_NETWORK_ENTRYPOINT_CONTRACT:
        raise ValueError("Public network-entrypoint contract is inconsistent")

    return {
        "path": PUBLIC_ENVIRONMENT_PACKET_PATH,
        "platform_id": platform_id,
        "network_platform": isolation["platform"],
        "isolation_method": isolation["isolation_method"],
        "isolation_scope": isolation["isolation_scope"],
        "threads": runtime["threads"],
        "installed_distribution_required": runtime["installed_distribution_required"],
    }


def read_release_metadata(repo_root: Path) -> dict[str, object]:
    metadata_paths = {
        "pyproject.toml": repo_root / "pyproject.toml",
        "mito_overview/__init__.py": repo_root / "mito_overview" / "__init__.py",
        "CITATION.cff": repo_root / "CITATION.cff",
    }
    for label, path in metadata_paths.items():
        if not path.is_file():
            raise ValueError(f"Release metadata file is missing: {label}")

    project = tomllib.loads(metadata_paths["pyproject.toml"].read_text(encoding="utf-8"))
    project_table = project.get("project", {})
    package_name = str(project_table.get("name", "")).strip()
    pyproject_version = str(project_table.get("version", "")).strip()
    pyproject_license = normalize_license(
        project_table.get("license"), "pyproject.toml project.license"
    )
    project_urls = project_table.get("urls")
    if not isinstance(project_urls, dict):
        raise ValueError("pyproject.toml project.urls must be a table")
    pyproject_repository = require_release_text(
        project_urls.get("Repository"), "pyproject.toml project.urls.Repository"
    )
    project_authors = project_table.get("authors")
    if not isinstance(project_authors, list) or not project_authors:
        raise ValueError("pyproject.toml project.authors must be a nonempty list")
    pyproject_authors: list[str] = []
    for index, author in enumerate(project_authors):
        if not isinstance(author, dict):
            raise ValueError(f"pyproject.toml author {index} must be a table")
        pyproject_authors.append(
            canonical_person_name(author.get("name"), f"pyproject.toml author {index}")
        )

    init_text = metadata_paths["mito_overview/__init__.py"].read_text(encoding="utf-8")
    init_match = re.search(
        r"(?m)^__version__\s*=\s*['\"]([^'\"]+)['\"]\s*$",
        init_text,
    )
    if init_match is None:
        raise ValueError("mito_overview/__init__.py does not define a literal __version__")

    citation_text = metadata_paths["CITATION.cff"].read_text(encoding="utf-8")
    citation_title = top_level_yaml_scalar(citation_text, "title", "CITATION.cff")
    citation_version = top_level_yaml_scalar(citation_text, "version", "CITATION.cff")
    citation_repository = top_level_yaml_scalar(
        citation_text, "repository-code", "CITATION.cff"
    )
    citation_license = normalize_license(
        top_level_yaml_scalar(citation_text, "license", "CITATION.cff"),
        "CITATION.cff license",
    )
    citation_creator_names = citation_authors(citation_text)
    preliminary_versions = {
        "pyproject.toml": pyproject_version,
        "mito_overview/__init__.py": init_match.group(1),
        "CITATION.cff": citation_version,
    }
    stale_versions = [
        f"{label}={version}"
        for label, version in preliminary_versions.items()
        if version != EXPECTED_RELEASE_VERSION.removeprefix("v")
    ]
    if stale_versions:
        raise ValueError(
            f"Release metadata mismatch for {EXPECTED_RELEASE_VERSION}: "
            f"{', '.join(stale_versions)}"
        )
    versions = {
        "pyproject.toml": pyproject_version,
        "mito_overview/__init__.py": init_match.group(1),
        "CITATION.cff": citation_version,
    }
    hashes = {label: sha256(path) for label, path in metadata_paths.items()}
    canonical = {
        "name": EXPECTED_PACKAGE_NAME,
        "version": pyproject_version,
        "repository": pyproject_repository,
        "license": EXPECTED_LICENSE,
        "creators": list(EXPECTED_CREATORS),
    }
    source_values: dict[str, dict[str, object]] = {
        "pyproject.toml": {
            "name": package_name,
            "version": pyproject_version,
            "repository": pyproject_repository,
            "license": pyproject_license,
            "creators": pyproject_authors,
        },
        "mito_overview/__init__.py": {"version": init_match.group(1)},
        "CITATION.cff": {
            "name": citation_title,
            "version": citation_version,
            "repository": citation_repository,
            "license": citation_license,
            "creators": citation_creator_names,
        },
    }
    expected_by_source: dict[str, dict[str, object]] = {
        "pyproject.toml": {
            key: canonical[key] for key in ("name", "version", "repository", "license", "creators")
        },
        "mito_overview/__init__.py": {"version": canonical["version"]},
        "CITATION.cff": {
            key: canonical[key]
            for key in (
                "name",
                "version",
                "repository",
                "license",
                "creators",
            )
        },
    }
    for source, expected in expected_by_source.items():
        if source_values[source] != expected:
            raise ValueError(
                f"Release metadata disagreement in {source}: "
                f"observed={source_values[source]!r}, expected={expected!r}"
            )

    return {
        "package_name": package_name,
        "versions": versions,
        "hashes": hashes,
        "canonical": canonical,
        "sources": source_values,
    }


def parse_distribution_metadata(text: str, source: Path) -> tuple[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"Name", "Version"} and key not in fields:
            fields[key] = value.strip()
    if not fields.get("Name") or not fields.get("Version"):
        raise ValueError(f"Distribution metadata lacks Name or Version: {source}")
    return fields["Name"], fields["Version"]


def inspect_distribution(path: Path) -> tuple[str, str, str]:
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            members = sorted(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            )
            if len(members) != 1:
                raise ValueError(f"Wheel must contain exactly one METADATA file: {path}")
            text = archive.read(members[0]).decode("utf-8")
        kind = "wheel"
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = sorted(
                (member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")),
                key=lambda member: member.name,
            )
            if len(members) != 1:
                raise ValueError(f"Source archive must contain exactly one PKG-INFO file: {path}")
            handle = archive.extractfile(members[0])
            if handle is None:
                raise ValueError(f"Unable to read PKG-INFO from source archive: {path}")
            text = handle.read().decode("utf-8")
        kind = "sdist"
    else:
        raise ValueError(f"Unsupported distribution artifact: {path}")
    name, version = parse_distribution_metadata(text, path)
    return kind, name, version


def validate_distributions(
    dist_root: Path,
    expected_name: str,
    expected_version: str,
) -> list[dict[str, str]]:
    if not dist_root.is_dir():
        raise FileNotFoundError(f"Required distribution directory not found: {dist_root}")
    files = sorted(path for path in dist_root.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"Distribution directory contains no artifacts: {dist_root}")

    artifacts: list[dict[str, str]] = []
    kinds: set[str] = set()
    for path in files:
        if path.stat().st_size == 0:
            raise ValueError(f"Distribution artifact is empty: {path}")
        kind, name, version = inspect_distribution(path)
        if normalize_project_name(name) != normalize_project_name(expected_name):
            raise ValueError(f"Distribution name mismatch in {path}: {name!r}")
        if version != expected_version:
            raise ValueError(
                f"Distribution version mismatch in {path}: {version!r} != {expected_version!r}"
            )
        kinds.add(kind)
        artifacts.append(
            {
                "path": f"dist/{path.relative_to(dist_root).as_posix()}",
                "kind": kind,
                "name": name,
                "version": version,
                "sha256": sha256(path),
            }
        )
    missing_kinds = sorted({"wheel", "sdist"} - kinds)
    if missing_kinds:
        raise ValueError(f"Distribution evidence is missing: {', '.join(missing_kinds)}")
    return artifacts


def validate_hash_manifest(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Required {label} not found: {path}")
    entries: set[str] = set()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        raise ValueError(f"{label} contains no hashes")
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise ValueError(f"Malformed line in {label}: {line!r}")
        evidence_path = match.group(2)
        if evidence_path in entries:
            raise ValueError(f"Duplicate path in {label}: {evidence_path}")
        entries.add(evidence_path)


def read_tsv_rows(
    path: Path,
    expected_header: tuple[str, ...],
    label: str,
) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required {label} not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != expected_header:
            raise ValueError(f"{label} header mismatch")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{label} contains no data rows")
    return rows


def semantically_equal(left: object, right: object) -> bool:
    left_text = "" if left is None else str(left)
    right_text = "" if right is None else str(right)
    if left_text == right_text:
        return True
    try:
        return Decimal(left_text) == Decimal(right_text)
    except InvalidOperation:
        return False


def canonical_public_input_hashes(rows: list[dict[str, str]]) -> str:
    return "".join(f"{row['sha256']}  {row['filename']}\n" for row in rows)


def validate_public_input_evidence(
    public_root: Path,
    public_sources_path: Path,
) -> dict[str, object]:
    """Bind the packet to the seven immutable FASTQs without redistributing reads."""

    manifest_path = public_root / RAW_INPUTS_PACKET_PATH
    rows = read_tsv_rows(
        manifest_path,
        PUBLIC_INPUT_MANIFEST_HEADER,
        "sealed public-input manifest",
    )
    expected_rows = [dict(row) for row in FROZEN_PUBLIC_INPUTS]
    if rows != expected_rows:
        expected_by_name = {row["filename"]: row for row in expected_rows}
        observed_by_name = {row.get("filename", ""): row for row in rows}
        if set(observed_by_name) != set(expected_by_name):
            raise ValueError("Public-input manifest does not contain the seven frozen FASTQs")
        for filename, expected in expected_by_name.items():
            observed = observed_by_name[filename]
            mismatches = {
                field: (expected[field], observed.get(field, ""))
                for field in PUBLIC_INPUT_MANIFEST_HEADER
                if observed.get(field, "") != expected[field]
            }
            if mismatches:
                raise ValueError(
                    f"Public-input manifest mismatch for {filename}: {mismatches!r}"
                )
        raise ValueError("Public-input manifest ordering differs from the frozen contract")

    manifest_sha256 = sha256(manifest_path)
    if manifest_sha256 != FROZEN_RAW_INPUT_MANIFEST_SHA256:
        raise ValueError("Public-input manifest byte identity differs from the frozen v0.3.0 seal")
    seal_path = public_root / CACHE_SEAL_PACKET_PATH
    if not seal_path.is_file():
        raise FileNotFoundError(f"Required public-cache seal not found: {seal_path}")
    seal_text = seal_path.read_text(encoding="utf-8")
    seal_match = re.fullmatch(r"([0-9a-f]{64})  raw_inputs\.tsv\n?", seal_text)
    if seal_match is None or seal_match.group(1) != manifest_sha256:
        raise ValueError("Public-cache seal does not match raw_inputs.tsv")

    source_rows = read_tsv_rows(
        public_sources_path,
        EVIDENCE_TABLES["public_data_sources.tsv"],
        "public_data_sources.tsv",
    )
    source_by_run = {row["run_accession"]: row for row in source_rows}
    if len(source_by_run) != len(source_rows) or set(source_by_run) != set(
        FROZEN_PUBLIC_SOURCE_METADATA
    ):
        raise ValueError("public_data_sources.tsv run inventory is not the frozen four-run set")

    inputs_by_run: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        inputs_by_run.setdefault(row["run_accession"], []).append(row)
    for run_accession, metadata in FROZEN_PUBLIC_SOURCE_METADATA.items():
        inputs = inputs_by_run[run_accession]
        source = source_by_run[run_accession]
        first = inputs[0]
        expected = {
            "dataset": metadata["dataset"],
            "run_accession": run_accession,
            "study_accession": metadata["study_accession"],
            "sample_accession": first["sample_accession"],
            "cell_line": first["source_sample_id"],
            "platform": "ILLUMINA" if first["source_sample_id"] == "GM11906" else "OXFORD_NANOPORE",
            "instrument_model": metadata["instrument_model"],
            "library_strategy": first["library_strategy"],
            "fastq_url": ";".join(item["url"] for item in inputs),
            "fastq_md5": ";".join(item["md5"] for item in inputs),
            "fastq_sha256": ";".join(item["sha256"] for item in inputs),
            "fastq_bytes": ";".join(item["bytes"] for item in inputs),
            "role": "fixed-input reproducibility and descriptive filter profile",
            "redistribution": "raw reads excluded from Git and validation ZIP",
        }
        mismatches = {
            field: (value, source.get(field, ""))
            for field, value in expected.items()
            if source.get(field, "") != value
        }
        if mismatches:
            raise ValueError(
                f"public_data_sources.tsv mismatch for {run_accession}: {mismatches!r}"
            )
        try:
            recorded = datetime.fromisoformat(
                source["metadata_recorded_utc"].replace("Z", "+00:00")
            )
        except ValueError as error:
            raise ValueError(
                f"public_data_sources.tsv has an invalid metadata timestamp for {run_accession}"
            ) from error
        if recorded.tzinfo is None or recorded.utcoffset() is None:
            raise ValueError(
                f"public_data_sources.tsv metadata timestamp lacks a timezone for {run_accession}"
            )

    return {
        "rows": rows,
        "manifest_sha256": manifest_sha256,
        "seal_sha256": sha256(seal_path),
        "canonical_inputs_sha256": canonical_public_input_hashes(rows),
    }


def read_frozen_oracle(path: Path) -> list[dict[str, str]]:
    if sha256(path) != FROZEN_ORACLE_SHA256:
        raise ValueError("Tracked public-validation oracle does not match the frozen v0.3.0 oracle")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [
            {key: "" if value in (None, ".") else value for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]
    keys = [(row.get("dataset", ""), row.get("profile", "")) for row in rows]
    if keys != list(PUBLIC_ORACLE_CASES):
        raise ValueError("Tracked public-validation oracle profile inventory is invalid")
    return rows


def expected_oracle_assertions(
    oracle_rows: list[dict[str, str]],
) -> dict[str, str]:
    oracle = {(row["dataset"], row["profile"]): row for row in oracle_rows}
    output_names = sorted(name for names in PUBLIC_ORACLE_CASES.values() for name in names)
    expected: dict[str, str] = {
        "oracle.profile_keys": repr(sorted(PUBLIC_ORACLE_CASES)),
        "matrix.output_directories": repr(output_names),
        "matrix.filter_profile_keys": repr(sorted(PUBLIC_ORACLE_CASES)),
    }
    filter_fields = (
        "min_base_quality",
        "min_mapping_quality",
        "min_read_mean_quality",
        "candidate_sites",
        "accepted_observations",
        "excluded_observations",
        "m8344_present",
        "m8344_alt_fraction",
    )
    case_fields = (
        "min_base_quality",
        "min_mapping_quality",
        "min_read_mean_quality",
        "candidate_sites",
        "accepted_observations",
        "excluded_observations",
    )
    inventory_fields = ("summary_tsv_count", "html_count", "png_count")
    status_fields = (
        "copy_number_status",
        "phymer_status",
        "methylation_status",
        "mvtool_status",
        "numt_module_status",
        "numt_interpretation_status",
        "numt_reason_code",
    )
    longread_fields = (
        "mapped_reads",
        "primary_reads",
        "supplementary_reads",
        "mean_depth",
        "median_depth",
        "selected_cosegregation_sites",
        "deletion_clusters",
        "deletion_query_names",
        "supplementary_sa_query_names",
        "source_records",
        "selected_names",
    )
    for key, case_ids in PUBLIC_ORACLE_CASES.items():
        row = oracle[key]
        for field in filter_fields:
            if row[field]:
                expected[f"filter.{key[0]}.{key[1]}.{field}"] = row[field]
        for case_id in case_ids:
            for field in case_fields:
                expected[f"{case_id}.{field}"] = row[field]
            expected[f"{case_id}.m8344.present"] = row["m8344_present"]
            for field in inventory_fields:
                expected[f"{case_id}.inventory.{field}"] = row[field]
            for field in status_fields:
                if row[field]:
                    expected[f"{case_id}.status.{field}"] = row[field]
            if row["m8344_alt_count"]:
                for field in (
                    "m8344_callable_depth",
                    "m8344_alt_count",
                    "m8344_alt_forward",
                    "m8344_alt_reverse",
                    "m8344_alt_fraction",
                    "m8344_feature_label",
                    "m8344_feature_class",
                    "m8344_consequence_class",
                ):
                    expected[f"{case_id}.{field}"] = row[field]
                expected[f"{case_id}.m8344_strand_sum"] = row["m8344_alt_count"]
                expected[f"{case_id}.m8344.consequence_rows"] = "1"
            if key[0] == "GM12878":
                for field in longread_fields:
                    expected[f"{case_id}.{field}"] = row[field]
                expected[f"{case_id}.selection_seed"] = (
                    "mito-overview-v0.3.0-GM12878-SRR18110025"
                )
            else:
                expected[f"{case_id}.shortread.dataset_id"] = "GM11906_pooled_scATAC"
                expected[f"{case_id}.shortread.derivation_id"] = (
                    "bwa-mem-samtools-sort-v1"
                )
                expected[f"{case_id}.shortread.source_runs"] = repr(
                    ["SRR10804585", "SRR10804590", "SRR10804657"]
                )
                expected[f"{case_id}.shortread.raw_input_labels"] = repr(
                    [
                        "SRR10804585_R1",
                        "SRR10804585_R2",
                        "SRR10804590_R1",
                        "SRR10804590_R2",
                        "SRR10804657_R1",
                        "SRR10804657_R2",
                    ]
                )
    return expected


def validate_oracle_assertions(
    path: Path,
    oracle_rows: list[dict[str, str]],
) -> dict[str, int]:
    rows = read_tsv_rows(
        path,
        ("assertion_id", "verdict", "expected", "observed", "detail"),
        "oracle_assertions.tsv",
    )
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        assertion_id = row["assertion_id"]
        if not assertion_id or assertion_id in by_id:
            raise ValueError(f"Duplicate or empty public-oracle assertion: {assertion_id!r}")
        if row["verdict"] != "PASS":
            raise ValueError(f"Public-oracle assertion is nonpassing: {assertion_id}")
        if not semantically_equal(row["expected"], row["observed"]):
            raise ValueError(f"Public-oracle PASS row disagrees semantically: {assertion_id}")
        by_id[assertion_id] = row
    required = expected_oracle_assertions(oracle_rows)
    missing = sorted(set(required) - set(by_id))
    if missing:
        raise ValueError(f"Public-oracle assertion report is incomplete: {missing}")
    for assertion_id, expected in required.items():
        row = by_id[assertion_id]
        if not semantically_equal(row["expected"], expected):
            raise ValueError(
                f"Public-oracle assertion expected value drifted for {assertion_id}: "
                f"{row['expected']!r} != {expected!r}"
            )
    return {"assertion_count": len(rows), "required_assertion_count": len(required)}


def validate_filter_profiles(
    path: Path,
    oracle_rows: list[dict[str, str]],
) -> None:
    expected_header = (
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
    )
    rows = read_tsv_rows(path, expected_header, "filter_profile_results.tsv")
    observed = {(row["dataset"], row["profile"]): row for row in rows}
    oracle = {(row["dataset"], row["profile"]): row for row in oracle_rows}
    if len(observed) != len(rows) or set(observed) != set(oracle):
        raise ValueError("Filter-profile result inventory does not match the frozen oracle")
    mappings = {
        "min_base_quality": "min_base_quality",
        "min_mapping_quality": "min_mapping_quality",
        "min_read_mean_quality": "min_read_mean_quality",
        "candidate_sites": "candidate_sites",
        "accepted_observations": "accepted_observations",
        "excluded_observations": "excluded_observations",
        "m8344_A_G_present": "m8344_present",
        "m8344_A_G_alt_allele_fraction": "m8344_alt_fraction",
    }
    for key, expected_row in oracle.items():
        row = observed[key]
        expected_case = f"{key[0].lower()}_{key[1]}"
        if row["case_id"] != expected_case:
            raise ValueError(f"Filter-profile case identity mismatch for {key}")
        for observed_field, oracle_field in mappings.items():
            expected_value = expected_row[oracle_field]
            if expected_value and not semantically_equal(row[observed_field], expected_value):
                raise ValueError(
                    f"Filter-profile oracle mismatch for {key} {observed_field}: "
                    f"{row[observed_field]!r} != {expected_value!r}"
                )


def metric_values(path: Path) -> dict[str, str]:
    rows = read_tsv_rows(path, ("metric", "value"), path.name)
    values = {row["metric"]: row["value"] for row in rows}
    if len(values) != len(rows):
        raise ValueError(f"Duplicate metric in {path}")
    return values


def validate_normalized_repeatability(
    normalized_root: Path,
    oracle_rows: list[dict[str, str]],
) -> None:
    oracle = {(row["dataset"], row["profile"]): row for row in oracle_rows}
    for dataset_key, dataset_name in (("gm11906", "GM11906"), ("gm12878", "GM12878")):
        run1 = normalized_root / f"{dataset_key}_default_run1"
        run2 = normalized_root / f"{dataset_key}_default_run2"
        if not run1.is_dir() or not run2.is_dir():
            raise ValueError(f"Normalized repeat evidence is missing for {dataset_name}")
        ignored = {"normalized_manifest.tsv", "visual_artifact_inventory.tsv"}
        files1 = {
            path.relative_to(run1).as_posix(): path
            for path in run1.rglob("*.tsv")
            if path.name not in ignored
        }
        files2 = {
            path.relative_to(run2).as_posix(): path
            for path in run2.rglob("*.tsv")
            if path.name not in ignored
        }
        if set(files1) != set(files2) or len(files1) != 44:
            raise ValueError(
                f"Normalized {dataset_name} summary inventory must contain 44 matched TSVs"
            )
        for relative, first in files1.items():
            if first.read_bytes() != files2[relative].read_bytes():
                raise ValueError(
                    f"Normalized scientific TSVs differ across {dataset_name} repeats: {relative}"
                )
        for repeat_root, files in ((run1, files1), (run2, files2)):
            manifest_rows = read_tsv_rows(
                repeat_root / "normalized_manifest.tsv",
                ("path", "sha256"),
                f"{repeat_root.name} normalized manifest",
            )
            manifest = {row["path"]: row["sha256"] for row in manifest_rows}
            expected_manifest = {
                relative: sha256(path) for relative, path in files.items()
            }
            if manifest != expected_manifest:
                raise ValueError(f"Normalized manifest mismatch for {repeat_root.name}")

        visual_rows = []
        for repeat_root in (run1, run2):
            rows = read_tsv_rows(
                repeat_root / "visual_artifact_inventory.tsv",
                (
                    "relative_path",
                    "artifact_type",
                    "bytes",
                    "sha256",
                    "width_px",
                    "height_px",
                    "integrity_status",
                ),
                f"{repeat_root.name} visual inventory",
            )
            if any(row["integrity_status"] != "ok" for row in rows):
                raise ValueError(f"Visual integrity failure for {repeat_root.name}")
            visual_rows.append(rows)
        structures = [
            [
                (
                    row["relative_path"],
                    row["artifact_type"],
                    row["width_px"],
                    row["height_px"],
                    row["integrity_status"],
                )
                for row in rows
            ]
            for rows in visual_rows
        ]
        if structures[0] != structures[1]:
            raise ValueError(f"Visual structures differ across {dataset_name} repeats")
        default_oracle = oracle[(dataset_name, "default")]
        observed_html = sum(row["artifact_type"] == "html" for row in visual_rows[0])
        observed_png = sum(row["artifact_type"] == "png" for row in visual_rows[0])
        if observed_html != int(default_oracle["html_count"]) or observed_png != int(
            default_oracle["png_count"]
        ):
            raise ValueError(f"Visual artifact inventory mismatch for {dataset_name}")

        summary = metric_values(run1 / "mito_heteroplasmy_summary.tsv")
        for oracle_field, metric in (
            ("min_base_quality", "allele_min_base_quality"),
            ("min_mapping_quality", "allele_min_mapping_quality"),
            ("min_read_mean_quality", "allele_min_read_mean_quality"),
            ("accepted_observations", "accepted_observations"),
            ("excluded_observations", "excluded_observations"),
        ):
            if not semantically_equal(summary.get(metric), default_oracle[oracle_field]):
                raise ValueError(f"Normalized oracle mismatch for {dataset_name} {metric}")

        candidate_path = run1 / "mito_heteroplasmy_candidates.tsv"
        with candidate_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                raise ValueError(
                    f"{dataset_name} heteroplasmy candidates header is missing"
                )
            candidates = list(reader)
        if not candidates:
            raise ValueError(f"{dataset_name} heteroplasmy candidates are empty")
        if len(candidates) != int(default_oracle["candidate_sites"]):
            raise ValueError(f"Normalized candidate count mismatch for {dataset_name}")
        marker = [
            row
            for row in candidates
            if row.get("position") == "8344"
            and row.get("ref_base", "").upper() == "A"
            and row.get("alt_base", "").upper() == "G"
        ]
        if len(marker) != int(default_oracle["m8344_present"]):
            raise ValueError(f"Normalized m.8344A>G presence mismatch for {dataset_name}")
        if marker:
            row = marker[0]
            for oracle_field, table_field in (
                ("m8344_callable_depth", "callable_depth"),
                ("m8344_alt_count", "alt_count"),
                ("m8344_alt_forward", "alt_forward"),
                ("m8344_alt_reverse", "alt_reverse"),
                ("m8344_alt_fraction", "alt_allele_fraction"),
            ):
                if not semantically_equal(row.get(table_field), default_oracle[oracle_field]):
                    raise ValueError(f"Normalized m.8344A>G mismatch for {oracle_field}")

        status_specs = (
            ("copy_number_status", "mito_copy_number_summary.tsv", "status"),
            ("phymer_status", "mito_phymer_haplogroup_summary.tsv", "status"),
            ("methylation_status", "mito_methylation_exploratory_summary.tsv", "status"),
            ("mvtool_status", "mito_mvtool_annotation_summary.tsv", "status"),
            ("numt_module_status", "mito_numt_qc_summary.tsv", "status"),
            (
                "numt_interpretation_status",
                "mito_numt_qc_summary.tsv",
                "numt_interpretation_status",
            ),
            ("numt_reason_code", "mito_numt_qc_summary.tsv", "reason_code"),
        )
        loaded: dict[str, dict[str, str]] = {}
        for oracle_field, filename, metric in status_specs:
            expected_value = default_oracle[oracle_field]
            if not expected_value:
                continue
            loaded.setdefault(filename, metric_values(run1 / filename))
            if loaded[filename].get(metric) != expected_value:
                raise ValueError(f"Normalized module-state mismatch for {dataset_name} {oracle_field}")

        if dataset_name == "GM12878":
            table_specs = {
                "mito_qc_summary.tsv": {
                    "mapped_reads": "mapped_reads",
                    "primary_reads": "primary_reads",
                    "supplementary_reads": "supplementary_reads",
                    "mean_depth": "mean_depth",
                    "median_depth": "median_depth",
                },
                "mito_cosegregation_summary.tsv": {
                    "selected_cosegregation_sites": "selected_sites",
                },
                "mito_deletion_summary.tsv": {
                    "deletion_clusters": "candidate_deletion_clusters",
                    "deletion_query_names": "reads_with_large_deletion",
                    "supplementary_sa_query_names": "reads_with_supplementary_or_SA",
                },
            }
            for filename, fields in table_specs.items():
                values = metric_values(run1 / filename)
                for oracle_field, metric in fields.items():
                    if not semantically_equal(values.get(metric), default_oracle[oracle_field]):
                        raise ValueError(
                            f"Normalized long-read metric mismatch for {oracle_field}"
                        )


def validate_module_status_evidence(
    path: Path,
    normalized_root: Path,
) -> None:
    rows = read_tsv_rows(
        path,
        EVIDENCE_TABLES["module_status_matrix.tsv"],
        "module_status_matrix.tsv",
    )
    observed: dict[tuple[str, str], tuple[str, str, str]] = {}
    for row in rows:
        key = (row["case_id"], row["module"])
        if key in observed:
            raise ValueError(f"Duplicate module-status evidence: {key}")
        observed[key] = (row["status"], row["reason_code"], row["source_table"])

    expected: dict[tuple[str, str], tuple[str, str, str]] = {}
    for case_id in ("gm11906_default_run1", "gm12878_default_run1"):
        case_root = normalized_root / case_id
        for table in sorted(case_root.glob("*.tsv")):
            try:
                values = metric_values(table)
            except ValueError:
                continue
            if "status" not in values:
                continue
            expected[(case_id, table.stem)] = (
                values["status"],
                values.get("reason_code", ""),
                f"observed_normalized/{case_id}/{table.name}",
            )
    if observed != expected:
        raise ValueError("module_status_matrix.tsv does not exactly inventory default module states")


def validate_scientific_evidence(
    repo_root: Path,
    validation_root: Path,
    public_root: Path,
) -> dict[str, object]:
    oracle_path = repo_root / FROZEN_ORACLE_REPOSITORY_PATH
    oracle_rows = read_frozen_oracle(oracle_path)
    assertion_summary = validate_oracle_assertions(
        public_root / ORACLE_ASSERTIONS_PACKET_PATH,
        oracle_rows,
    )
    validate_filter_profiles(public_root / "filter_profile_results.tsv", oracle_rows)
    validate_normalized_repeatability(public_root / "observed_normalized", oracle_rows)
    validate_module_status_evidence(
        validation_root / "module_status_matrix.tsv",
        public_root / "observed_normalized",
    )
    return {
        "oracle_sha256": FROZEN_ORACLE_SHA256,
        **assertion_summary,
    }


def load_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Required {label} not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to parse {label}: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def _reject_secret_material(value: object, location: str = "root") -> None:
    sensitive_key = re.compile(
        r"(?i)(?:^|_)(?:access_?token|refresh_?token|authorization|password|secret)(?:$|_)"
    )
    sensitive_value = re.compile(
        r"(?i)(?:access[_-]?token\s*=|authorization\s*:|bearer\s+|client[_-]?secret)"
    )
    if isinstance(value, dict):
        for key, child in value.items():
            if sensitive_key.search(str(key)):
                raise ValueError(f"Zenodo reservation evidence contains a sensitive key at {location}")
            _reject_secret_material(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_material(child, f"{location}[{index}]")
    elif isinstance(value, str) and sensitive_value.search(value):
        raise ValueError(f"Zenodo reservation evidence contains secret-like material at {location}")


def validate_zenodo_reservation_evidence(
    path: Path | None,
    expected_doi: str,
) -> dict[str, object]:
    if re.fullmatch(ZENODO_DOI_PATTERN, expected_doi) is None:
        raise ValueError(f"A canonical Zenodo DOI is required: {expected_doi!r}")
    if path is None:
        raise ValueError(
            "A sanitized Zenodo reservation evidence file is required; DOI text alone is insufficient"
        )
    evidence = load_json_object(path, "Zenodo reservation evidence")
    _reject_secret_material(evidence)

    required_top_level = {
        "schema_version",
        "evidence_type",
        "source",
        "captured_utc",
        "reservation_status",
        "doi",
        "record_id",
        "zenodo_api_url",
        "deposition_response",
    }
    if set(evidence) != required_top_level:
        raise ValueError(
            "Zenodo reservation evidence fields are not the required sanitized set: "
            f"missing={sorted(required_top_level - set(evidence))}, "
            f"unexpected={sorted(set(evidence) - required_top_level)}"
        )
    expected_fields = {
        "schema_version": "1.1",
        "evidence_type": "zenodo_doi_reservation",
        "source": ZENODO_RESERVATION_SOURCE,
        "reservation_status": "reserved",
        "doi": expected_doi,
    }
    for field, expected in expected_fields.items():
        if evidence.get(field) != expected:
            raise ValueError(
                f"Zenodo reservation evidence mismatch for {field}: "
                f"{evidence.get(field)!r} != {expected!r}"
            )

    captured_utc = evidence.get("captured_utc")
    if not isinstance(captured_utc, str):
        raise ValueError("Zenodo reservation captured_utc must be an ISO-8601 timestamp")
    try:
        captured = datetime.fromisoformat(captured_utc.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Zenodo reservation captured_utc must be an ISO-8601 timestamp") from error
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("Zenodo reservation captured_utc must include a timezone")

    record_id = evidence.get("record_id")
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
        raise ValueError(f"Zenodo reservation record_id must be a positive integer: {record_id!r}")
    canonical_doi = f"10.5281/zenodo.{record_id}"
    canonical_api_url = f"https://zenodo.org/api/deposit/depositions/{record_id}"
    if expected_doi != canonical_doi:
        raise ValueError(
            f"Zenodo reservation DOI is not tied to record_id {record_id}: {expected_doi!r}"
        )
    if evidence.get("zenodo_api_url") != canonical_api_url:
        raise ValueError(
            "Zenodo reservation API URL mismatch: "
            f"{evidence.get('zenodo_api_url')!r} != {canonical_api_url!r}"
        )

    response = evidence.get("deposition_response")
    if not isinstance(response, dict):
        raise ValueError("Zenodo reservation deposition_response must be an object")
    required_response = {"id", "record_id", "links", "metadata", "state", "submitted"}
    if set(response) != required_response:
        raise ValueError("Zenodo deposition_response is not the required sanitized field set")
    if response.get("id") != record_id or response.get("record_id") != record_id:
        raise ValueError("Zenodo deposition response IDs do not match the reserved record_id")
    if response.get("state") != "unsubmitted" or response.get("submitted") is not False:
        raise ValueError("Zenodo deposition response does not describe an unsubmitted reservation")

    links = response.get("links")
    if not isinstance(links, dict) or set(links) != {"self"}:
        raise ValueError("Zenodo deposition links must contain only the sanitized self URL")
    if links.get("self") != canonical_api_url:
        raise ValueError("Zenodo deposition self URL does not match the reserved record")
    metadata = response.get("metadata")
    release_metadata = canonicalize_zenodo_metadata(
        metadata,
        expected_doi=expected_doi,
        reservation_mode="evidence",
    )
    assert isinstance(metadata, dict)
    reservation = metadata.get("prereserve_doi")
    if not isinstance(reservation, dict) or set(reservation) != {"doi", "recid"}:
        raise ValueError("Zenodo prereserve_doi evidence is malformed")
    if reservation.get("doi") != expected_doi or reservation.get("recid") != record_id:
        raise ValueError("Zenodo prereserve_doi does not match the requested DOI and record ID")

    return {
        "evidence_path": ZENODO_RESERVATION_PACKET_PATH,
        "evidence_sha256": sha256(path),
        "doi": expected_doi,
        "record_id": record_id,
        "zenodo_api_url": canonical_api_url,
        "reservation_status": "reserved",
        "source": ZENODO_RESERVATION_SOURCE,
        "captured_utc": captured_utc,
        "release_metadata": release_metadata,
    }


def validate_digest_record(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Public provenance {label} must be an object")
    name = value.get("name")
    size = value.get("bytes")
    digest = value.get("sha256")
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError(f"Public provenance {label} has an invalid file name")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError(f"Public provenance {label} has an invalid byte count")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError(f"Public provenance {label} has an invalid SHA-256")
    md5 = value.get("md5")
    if md5 is not None and (
        not isinstance(md5, str) or re.fullmatch(r"[0-9a-f]{32}", md5) is None
    ):
        raise ValueError(f"Public provenance {label} has an invalid MD5")
    return value


def _require_record_content(record: dict[str, object], path: Path, label: str) -> None:
    if record["bytes"] != path.stat().st_size or record["sha256"] != sha256(path):
        raise ValueError(f"Public provenance {label} does not match packaged evidence")


def _records_match(
    left: dict[str, object],
    right: dict[str, object],
    label: str,
) -> None:
    for field in ("name", "bytes", "sha256", "md5"):
        if left.get(field) != right.get(field):
            raise ValueError(f"Public provenance linkage mismatch for {label} field {field}")


def validate_public_provenance(
    public_root: Path,
    public_input_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    paths = {
        key: public_root / str(specification["source"])
        for key, specification in PUBLIC_PROVENANCE_FILES.items()
    }
    short = load_json_object(paths["shortread_alignment"], "short-read alignment provenance")
    subset = load_json_object(paths["longread_subset"], "long-read subset provenance")
    long = load_json_object(paths["longread_alignment"], "long-read alignment provenance")
    names_path = paths["selected_query_names"]
    if not names_path.is_file() or names_path.stat().st_size == 0:
        raise FileNotFoundError(f"Required selected-query-name evidence not found: {names_path}")

    with paths["shortread_source_libraries"].open(
        encoding="utf-8", newline=""
    ) as handle:
        source_rows = list(csv.DictReader(handle, delimiter="\t"))
    expected_source_header = (
        "run_accession",
        "geo_accession",
        "source_sample_id",
        "library_strategy",
        "library_unit",
        "combination_role",
        "source_record_url",
    )
    if (
        not source_rows
        or tuple(source_rows[0]) != expected_source_header
        or [
            (
                row["run_accession"],
                row["geo_accession"],
                row["source_sample_id"],
                row["library_strategy"],
                row["library_unit"],
                row["combination_role"],
            )
            for row in source_rows
        ]
        != [
            (
                "SRR10804585",
                "GSM4238454",
                "GM11906",
                "ATAC-seq",
                "single_cell_library",
                "pooled_pseudobulk",
            ),
            (
                "SRR10804590",
                "GSM4238459",
                "GM11906",
                "ATAC-seq",
                "single_cell_library",
                "pooled_pseudobulk",
            ),
            (
                "SRR10804657",
                "GSM4238526",
                "GM11906",
                "ATAC-seq",
                "single_cell_library",
                "pooled_pseudobulk",
            ),
        ]
        or any(
            row["source_record_url"]
            != "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc="
            + row["geo_accession"]
            for row in source_rows
        )
    ):
        raise ValueError("Public GM11906 source-library provenance is invalid")

    alignment_expectations = (
        (
            short,
            "GM11906_pooled_scATAC",
            "bwa-mem-samtools-sort-v1",
            "short-read",
        ),
        (
            long,
            "GM12878_SRR18110025_ONT_reduced_qn1000",
            "minimap2-map-ont-deterministic-fastq-subset-mapped-only-v1",
            "long-read",
        ),
    )
    for manifest, dataset_id, derivation_id, label in alignment_expectations:
        if manifest.get("schema_version") != "1.0" or manifest.get("provenance_type") != "public_alignment":
            raise ValueError(f"Public {label} alignment provenance identity is invalid")
        if manifest.get("dataset_id") != dataset_id:
            raise ValueError(f"Public {label} alignment dataset identity is invalid")
        for field in ("alignment", "alignment_index", "reference", "reference_index"):
            validate_digest_record(manifest.get(field), f"{label} {field}")
        derivation = manifest.get("derivation")
        if not isinstance(derivation, dict) or derivation.get("derivation_id") != derivation_id:
            raise ValueError(f"Public {label} alignment derivation identity is invalid")
        public_inputs = manifest.get("public_inputs")
        if not isinstance(public_inputs, list) or not public_inputs:
            raise ValueError(f"Public {label} alignment inputs are missing")
        for index, record in enumerate(public_inputs):
            validated = validate_digest_record(record, f"{label} input {index}")
            if not isinstance(validated.get("label"), str) or not validated["label"]:
                raise ValueError(f"Public {label} alignment input label is invalid")

    input_by_filename = {row["filename"]: row for row in public_input_rows}
    short_inputs = {
        record.get("label"): record
        for record in short["public_inputs"]
        if isinstance(record, dict) and isinstance(record.get("label"), str)
    }
    expected_short_labels = {
        "SRR10804585_R1": "SRR10804585_1.fastq.gz",
        "SRR10804585_R2": "SRR10804585_2.fastq.gz",
        "SRR10804590_R1": "SRR10804590_1.fastq.gz",
        "SRR10804590_R2": "SRR10804590_2.fastq.gz",
        "SRR10804657_R1": "SRR10804657_1.fastq.gz",
        "SRR10804657_R2": "SRR10804657_2.fastq.gz",
    }
    if set(short_inputs) != {*expected_short_labels, "combined_R1", "combined_R2"}:
        raise ValueError(
            "Public short-read alignment must contain all six frozen mates and two combined inputs"
        )
    for label, filename in expected_short_labels.items():
        record = short_inputs[label]
        expected = input_by_filename[filename]
        for field in ("name", "bytes", "md5", "sha256"):
            expected_value: object = filename if field == "name" else expected[field]
            if field == "bytes":
                expected_value = int(str(expected_value))
            if record.get(field) != expected_value:
                raise ValueError(
                    f"Public short-read alignment input {label} is not bound to {filename} {field}"
                )
    for label, suffix, raw_labels in (
        (
            "combined_R1",
            "GM11906_MERRF_R1.fastq.gz",
            ("SRR10804585_R1", "SRR10804590_R1", "SRR10804657_R1"),
        ),
        (
            "combined_R2",
            "GM11906_MERRF_R2.fastq.gz",
            ("SRR10804585_R2", "SRR10804590_R2", "SRR10804657_R2"),
        ),
    ):
        combined = short_inputs[label]
        if combined.get("name") != suffix or combined.get("bytes") != sum(
            int(short_inputs[raw_label]["bytes"]) for raw_label in raw_labels
        ):
            raise ValueError(f"Public short-read combined input is invalid: {label}")

    if (
        subset.get("schema_version") != "1.0"
        or subset.get("provenance_type") != "deterministic_fastq_query_name_subset"
        or subset.get("dataset_id") != "GM12878_SRR18110025_ONT"
    ):
        raise ValueError("Public long-read subset provenance identity is invalid")
    source_fastq = validate_digest_record(subset.get("source_fastq"), "subset source FASTQ")
    subset_fastq = validate_digest_record(subset.get("subset_fastq"), "subset FASTQ")
    selected_names = validate_digest_record(
        subset.get("selected_query_names"), "selected query names"
    )
    _require_record_content(selected_names, names_path, "selected query names")

    try:
        query_names = names_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("Selected-query-name evidence must be UTF-8 text") from error
    if not query_names or any(not name or name != name.strip() or any(c.isspace() for c in name) for name in query_names):
        raise ValueError("Selected-query-name evidence contains an invalid query name")
    if len(query_names) != len(set(query_names)):
        raise ValueError("Selected-query-name evidence contains duplicate query names")

    selection = subset.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("Public long-read subset selection metadata is missing")
    selected_count = selection.get("selected_query_names")
    if (
        selection.get("algorithm") != "smallest_sha256_seeded_query_names_v1"
        or isinstance(selected_count, bool)
        or not isinstance(selected_count, int)
        or selected_count != 1000
        or selection.get("requested_query_names") != selected_count
        or selected_count != len(query_names)
        or selection.get("source_records_seen") != 193043
        or selection.get("seed")
        != "mito-overview-v0.3.0-GM12878-SRR18110025"
    ):
        raise ValueError("Public long-read subset selection count or algorithm is invalid")

    long_inputs = {
        record.get("label"): record
        for record in long["public_inputs"]
        if isinstance(record, dict) and isinstance(record.get("label"), str)
    }
    required_labels = {
        "SRR18110025_full_fastq",
        "deterministic_subset_fastq",
        "deterministic_subset_manifest",
        "selected_query_names",
    }
    if set(long_inputs) != required_labels:
        raise ValueError("Public long-read alignment input inventory is incomplete")
    _records_match(source_fastq, long_inputs["SRR18110025_full_fastq"], "source FASTQ")
    expected_longread = input_by_filename["SRR18110025.fastq.gz"]
    for field in ("name", "bytes", "md5", "sha256"):
        expected_value = (
            "SRR18110025.fastq.gz" if field == "name" else expected_longread[field]
        )
        if field == "bytes":
            expected_value = int(str(expected_value))
        if source_fastq.get(field) != expected_value:
            raise ValueError(
                f"Public long-read source FASTQ is not bound to the frozen input {field}"
            )
    _records_match(subset_fastq, long_inputs["deterministic_subset_fastq"], "subset FASTQ")
    _records_match(selected_names, long_inputs["selected_query_names"], "selected names")
    _require_record_content(
        long_inputs["deterministic_subset_manifest"],
        paths["longread_subset"],
        "subset manifest",
    )
    derivation_parameters = long["derivation"].get("parameters")
    if not isinstance(derivation_parameters, dict) or (
        derivation_parameters.get("selected_query_names") != str(selected_count)
        or derivation_parameters.get("selection_seed") != selection.get("seed")
    ):
        raise ValueError("Public long-read alignment is not tied to the selected query-name subset")

    return [
        {
            "path": str(specification["packet"]),
            "sha256": sha256(paths[key]),
            "source_case": (
                "gm11906_default_run1"
                if key.startswith("shortread_")
                else "gm12878_default_run1"
            ),
        }
        for key, specification in PUBLIC_PROVENANCE_FILES.items()
    ]


def github_repository_slug(repository: str) -> str:
    parsed = urlsplit(repository)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            f"GitHub Actions evidence requires a GitHub HTTPS repository: {repository}"
        )
    slug = parsed.path.strip("/")
    if slug.endswith(".git"):
        slug = slug[:-4]
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", slug):
        raise ValueError(f"Unable to derive GitHub repository identity from: {repository}")
    return slug


def require_nonempty_evidence(validation_root: Path, relative: str) -> None:
    path = validation_root / relative
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Required acceptance evidence is missing or empty: {relative}")


def positive_json_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"GitHub Actions {label} must be a positive integer: {value!r}")
    return value


def validate_fresh_clone_evidence(
    validation_root: Path,
    expected_commit: str,
    repository: str,
) -> dict[str, str]:
    relative = "acceptance/fresh_clone.json"
    fresh = load_json_object(validation_root / relative, "fresh-clone evidence")
    expected_fields = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "validation_profile": VALIDATION_PROFILE,
        "evidence_type": "fresh_clone_validation",
        "case_id": FRESH_CLONE_CASE_ID,
        "repository": repository,
        "command_path": f"commands/{FRESH_CLONE_CASE_ID}.sh",
        "log_path": f"logs/{FRESH_CLONE_CASE_ID}.log",
    }
    for field, expected in expected_fields.items():
        if fresh.get(field) != expected:
            raise ValueError(
                f"Fresh-clone evidence field mismatch for {field}: "
                f"{fresh.get(field)!r} != {expected!r}"
            )
    if fresh.get("verdict") != "PASS":
        raise ValueError(
            f"Fresh-clone validation evidence is nonpassing: {fresh.get('verdict')!r}"
        )
    for field in ("candidate_commit", "checked_out_commit"):
        if fresh.get(field) != expected_commit:
            raise ValueError(
                f"Fresh-clone commit mismatch for {field}: "
                f"{fresh.get(field)!r} != {expected_commit!r}"
            )
    if fresh.get("detached_head") is not True:
        raise ValueError("Fresh-clone evidence does not confirm a detached candidate checkout")
    if fresh.get("clone_worktree_clean") is not True:
        raise ValueError("Fresh-clone evidence does not confirm a clean candidate checkout")
    required_truths = (
        "public_https_clone",
        "isolated_home",
        "isolated_tmpdir",
        "built_wheel",
        "built_sdist",
        "installed_wheel",
        "executed_outside_checkout",
    )
    missing_truths = [field for field in required_truths if fresh.get(field) is not True]
    if missing_truths:
        raise ValueError(
            "Fresh-clone evidence lacks required isolation/package proof: "
            + ", ".join(missing_truths)
        )
    expected_remote = repository.rstrip("/") + ".git"
    if fresh.get("source_remote") != expected_remote:
        raise ValueError(
            "Fresh-clone evidence does not use the canonical public HTTPS remote: "
            f"{fresh.get('source_remote')!r} != {expected_remote!r}"
        )

    require_nonempty_evidence(validation_root, expected_fields["command_path"])
    require_nonempty_evidence(validation_root, expected_fields["log_path"])
    return {
        "case_id": FRESH_CLONE_CASE_ID,
        "category": "release_acceptance",
        "input_available": "1",
        "expected_available": "1",
        "verdict": "PASS",
        "detail": (
            f"{relative}; {expected_fields['command_path']}; {expected_fields['log_path']}; "
            f"commit={expected_commit}"
        ),
    }


def validate_github_actions_evidence(
    validation_root: Path,
    expected_commit: str,
    repository: str,
) -> list[dict[str, str]]:
    run_relative = "acceptance/github_actions_run.json"
    jobs_relative = "acceptance/github_actions_jobs.json"
    command_relative = "commands/github_actions_candidate_commit.sh"
    log_relative = "logs/github_actions_candidate_commit.log"
    run = load_json_object(validation_root / run_relative, "GitHub Actions run evidence")
    jobs_payload = load_json_object(
        validation_root / jobs_relative,
        "GitHub Actions jobs evidence",
    )
    require_nonempty_evidence(validation_root, command_relative)
    require_nonempty_evidence(validation_root, log_relative)

    repository_slug = github_repository_slug(repository)
    run_id = positive_json_integer(run.get("id"), "run id")
    run_attempt = positive_json_integer(run.get("run_attempt"), "run attempt")
    if run.get("name") != EXPECTED_GITHUB_WORKFLOW:
        raise ValueError(
            f"GitHub Actions workflow mismatch: {run.get('name')!r} "
            f"!= {EXPECTED_GITHUB_WORKFLOW!r}"
        )
    if run.get("event") != "push":
        raise ValueError(
            "GitHub Actions release acceptance requires a push-event workflow run, "
            f"not {run.get('event')!r}"
        )
    if run.get("head_branch") != EXPECTED_GITHUB_BRANCH:
        raise ValueError(
            f"GitHub Actions push branch mismatch: {run.get('head_branch')!r} "
            f"!= {EXPECTED_GITHUB_BRANCH!r}"
        )
    if run.get("path") != EXPECTED_GITHUB_WORKFLOW_PATH:
        raise ValueError(
            f"GitHub Actions workflow path mismatch: {run.get('path')!r} "
            f"!= {EXPECTED_GITHUB_WORKFLOW_PATH!r}"
        )
    if run.get("head_sha") != expected_commit:
        raise ValueError(
            f"GitHub Actions run commit mismatch: "
            f"{run.get('head_sha')!r} != {expected_commit!r}"
        )
    run_repository = run.get("repository")
    if not isinstance(run_repository, dict) or run_repository.get("full_name") != repository_slug:
        raise ValueError("GitHub Actions run repository does not match the release repository")
    head_repository = run.get("head_repository")
    if not isinstance(head_repository, dict) or head_repository.get("full_name") != repository_slug:
        raise ValueError("GitHub Actions head repository does not match the release repository")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ValueError(
            "GitHub Actions workflow run evidence is nonpassing: "
            f"status={run.get('status')!r}, conclusion={run.get('conclusion')!r}"
        )
    run_url = f"https://github.com/{repository_slug}/actions/runs/{run_id}"
    run_api_url = f"https://api.github.com/repos/{repository_slug}/actions/runs/{run_id}"
    if run.get("html_url") != run_url:
        raise ValueError(
            f"GitHub Actions run URL mismatch: {run.get('html_url')!r} != {run_url!r}"
        )
    if run.get("url") != run_api_url:
        raise ValueError(
            f"GitHub Actions run API URL mismatch: {run.get('url')!r} != {run_api_url!r}"
        )
    if run.get("jobs_url") != f"{run_api_url}/jobs":
        raise ValueError("GitHub Actions jobs API URL is not bound to the selected run")

    jobs = jobs_payload.get("jobs")
    if not isinstance(jobs, list) or not all(isinstance(job, dict) for job in jobs):
        raise ValueError("GitHub Actions jobs evidence must contain a jobs object list")
    if jobs_payload.get("total_count") != len(jobs):
        raise ValueError("GitHub Actions jobs total_count does not match the jobs inventory")
    job_ids = [positive_json_integer(job.get("id"), "job id") for job in jobs]
    if len(job_ids) != len(set(job_ids)):
        raise ValueError("GitHub Actions jobs evidence contains duplicate job IDs")

    rows: list[dict[str, str]] = []
    for case_id, expectation in EXPECTED_GITHUB_JOBS.items():
        matching = [job for job in jobs if job.get("name") == expectation["name"]]
        if len(matching) != 1:
            raise ValueError(
                "GitHub Actions platform evidence is missing or ambiguous for "
                f"{expectation['platform']}: expected one {expectation['name']!r} job"
            )
        job = matching[0]
        labels = job.get("labels")
        if not isinstance(labels, list) or expectation["label"] not in labels:
            raise ValueError(
                f"GitHub Actions platform mismatch for {expectation['platform']}: "
                f"expected label {expectation['label']!r}, observed {labels!r}"
            )
        if job.get("head_sha") != expected_commit:
            raise ValueError(
                f"GitHub Actions {expectation['platform']} job commit mismatch: "
                f"{job.get('head_sha')!r} != {expected_commit!r}"
            )
        if job.get("run_id") != run_id or job.get("run_attempt") != run_attempt:
            raise ValueError(
                f"GitHub Actions {expectation['platform']} job is not from the selected run attempt"
            )
        if job.get("workflow_name") != EXPECTED_GITHUB_WORKFLOW:
            raise ValueError(
                f"GitHub Actions {expectation['platform']} job workflow mismatch"
            )
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise ValueError(
                f"GitHub Actions {expectation['platform']} job evidence is nonpassing: "
                f"status={job.get('status')!r}, conclusion={job.get('conclusion')!r}"
            )
        job_id = positive_json_integer(job.get("id"), f"{expectation['platform']} job id")
        expected_job_url = f"{run_url}/job/{job_id}"
        job_url = job.get("html_url")
        if job_url != expected_job_url:
            raise ValueError(
                f"GitHub Actions {expectation['platform']} job URL mismatch: "
                f"{job_url!r} != {expected_job_url!r}"
            )
        expected_job_api_url = f"https://api.github.com/repos/{repository_slug}/actions/jobs/{job_id}"
        if job.get("url") != expected_job_api_url:
            raise ValueError(
                f"GitHub Actions {expectation['platform']} job API URL mismatch"
            )
        if job.get("run_url") != run_api_url:
            raise ValueError(
                f"GitHub Actions {expectation['platform']} job run URL mismatch"
            )
        rows.append(
            {
                "case_id": case_id,
                "category": "release_acceptance",
                "input_available": "1",
                "expected_available": "1",
                "verdict": "PASS",
                "detail": (
                    f"{run_relative}; {jobs_relative}; {command_relative}; {log_relative}; "
                    f"run_id={run_id}; job_id={job_id}; "
                    f"platform={expectation['platform']}; event=push; "
                    f"commit={expected_commit}; url={job_url}"
                ),
            }
        )
    return rows


def validate_acceptance_evidence(
    validation_root: Path,
    expected_commit: str,
    repository: str,
) -> list[dict[str, str]]:
    rows = [validate_fresh_clone_evidence(validation_root, expected_commit, repository)]
    rows.extend(validate_github_actions_evidence(validation_root, expected_commit, repository))
    return rows


def github_actions_identity(
    validation_root: Path,
    expected_commit: str,
    repository: str,
) -> dict[str, object]:
    """Return the already validated GitHub Actions release identity."""

    validate_github_actions_evidence(validation_root, expected_commit, repository)
    run = load_json_object(
        validation_root / "acceptance/github_actions_run.json",
        "GitHub Actions run evidence",
    )
    jobs_payload = load_json_object(
        validation_root / "acceptance/github_actions_jobs.json",
        "GitHub Actions jobs evidence",
    )
    jobs = jobs_payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("GitHub Actions jobs evidence does not contain a jobs list")
    selected = []
    for expectation in EXPECTED_GITHUB_JOBS.values():
        matching = [
            job
            for job in jobs
            if isinstance(job, dict) and job.get("name") == expectation["name"]
        ]
        if len(matching) != 1:
            raise ValueError(
                f"Validated GitHub Actions job disappeared: {expectation['name']}"
            )
        job = matching[0]
        selected.append(
            {
                "job_id": job["id"],
                "name": job["name"],
                "labels": job["labels"],
                "head_sha": job["head_sha"],
                "url": job["html_url"],
            }
        )
    return {
        "provider": "github_actions",
        "run_id": run["id"],
        "run_attempt": run["run_attempt"],
        "workflow": run["name"],
        "workflow_path": run["path"],
        "event": run["event"],
        "branch": run["head_branch"],
        "head_sha": run["head_sha"],
        "status": run["status"],
        "conclusion": run["conclusion"],
        "url": run["html_url"],
        "jobs": selected,
    }


def resolve_release_identity(
    repo_root: Path,
    environment_path: Path,
    release_version: str,
    repository: str,
    asserted_commit: str | None,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    if release_version != EXPECTED_RELEASE_VERSION:
        raise ValueError(
            f"This packet builder is release-locked to {EXPECTED_RELEASE_VERSION}, got {release_version}"
        )
    github_repository_slug(repository)
    package_version = release_version.removeprefix("v")
    head = git_output(repo_root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError(f"Repository HEAD is not a full Git commit: {head!r}")
    if git_output(repo_root, "status", "--porcelain"):
        raise ValueError("Release repository has uncommitted or untracked files")
    if asserted_commit is not None and asserted_commit != head:
        raise ValueError(f"--commit does not match repository HEAD: {asserted_commit} != {head}")

    environment = parse_environment_identity(environment_path)
    if environment["release_version"] != release_version:
        raise ValueError(
            "environment.txt release_version does not match requested release: "
            f"{environment['release_version']} != {release_version}"
        )
    if environment["git_commit"] != head:
        raise ValueError(
            "environment.txt git_commit does not match repository HEAD: "
            f"{environment['git_commit']} != {head}"
        )
    if environment["repository"] != repository:
        raise ValueError(
            "environment.txt repository does not match packet repository: "
            f"{environment['repository']} != {repository}"
        )
    if not re.fullmatch(r"[1-9][0-9]*", environment["github_actions_run_id"]):
        raise ValueError("environment.txt github_actions_run_id is not a positive integer")

    metadata = read_release_metadata(repo_root)
    package_name = str(metadata["package_name"])
    versions = metadata["versions"]
    metadata_hashes = metadata["hashes"]
    if not isinstance(versions, dict) or not isinstance(metadata_hashes, dict):
        raise ValueError("Release metadata reader returned malformed identity maps")
    if normalize_project_name(package_name) != normalize_project_name(EXPECTED_PACKAGE_NAME):
        raise ValueError(f"Unexpected project name in pyproject.toml: {package_name!r}")
    mismatches = [
        f"{label}={version}"
        for label, version in versions.items()
        if version != package_version
    ]
    if mismatches:
        raise ValueError(
            f"Release metadata mismatch for {release_version}: {', '.join(mismatches)}; "
            f"update pyproject.toml, mito_overview/__init__.py, and CITATION.cff to {package_version}"
        )
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "validation_profile": VALIDATION_PROFILE,
        "release_version": release_version,
        "package_name": package_name,
        "package_version": package_version,
        "repository": repository,
        "git_commit": head,
        "environment_release_version": environment["release_version"],
        "environment_git_commit": environment["git_commit"],
        "environment_github_actions_run_id": int(
            environment["github_actions_run_id"]
        ),
        "metadata_versions": versions,
        "metadata_sha256": metadata_hashes,
        "canonical_metadata": metadata["canonical"],
        "metadata_sources": metadata["sources"],
        "source_worktree_clean": True,
    }


def write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def validate_cases(
    path: Path,
    acceptance_rows: list[dict[str, str]] | None = None,
) -> tuple[int, dict[str, int]]:
    allowed = {"PASS", "FAIL", "XFAIL", "SKIP", "BLOCKED"}
    counts = {value: 0 for value in allowed}
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise ValueError("cases.tsv contains no validation cases")
    case_ids: set[str] = set()
    for row in rows:
        case_id = row.get("case_id", "")
        if not case_id:
            raise ValueError("Validation case is missing case_id")
        if case_id in case_ids:
            raise ValueError(f"Duplicate validation case_id: {case_id}")
        case_ids.add(case_id)
        verdict = row.get("verdict", "")
        if verdict not in allowed:
            raise ValueError(f"Unsupported case verdict: {verdict}")
        if verdict == "PASS" and (
            row.get("input_available") != "1" or row.get("expected_available") != "1"
        ):
            raise ValueError(f"PASS case lacks input or expected evidence: {row.get('case_id')}")
        counts[verdict] += 1
    missing_required = sorted(REQUIRED_PASS_CASES - case_ids)
    if missing_required:
        raise ValueError(f"Required release cases are missing: {', '.join(missing_required)}")
    nonpassing_required = sorted(
        row["case_id"] for row in rows if row["case_id"] in REQUIRED_PASS_CASES and row["verdict"] != "PASS"
    )
    if nonpassing_required:
        raise ValueError(f"Required release cases did not pass: {', '.join(nonpassing_required)}")
    if acceptance_rows is not None:
        rows_by_id = {row["case_id"]: row for row in rows}
        for expected in acceptance_rows:
            case_id = expected["case_id"]
            observed = rows_by_id[case_id]
            for field, expected_value in expected.items():
                if observed.get(field) != expected_value:
                    raise ValueError(
                        f"Acceptance case does not match validated evidence for {case_id} "
                        f"field {field}: {observed.get(field)!r} != {expected_value!r}"
                    )
    release_blockers = sorted(
        f"{row['case_id']}={row['verdict']}"
        for row in rows
        if row["verdict"] in {"FAIL", "BLOCKED"}
    )
    if release_blockers:
        raise ValueError(
            f"Validation cases contain release-blocking verdicts: {', '.join(release_blockers)}"
        )
    return len(rows), counts


def validate_evidence_tables(validation_root: Path) -> None:
    allowed_module_states = {
        "ok",
        "not_configured",
        "not_applicable",
        "not_evaluable",
        "unavailable",
    }
    for name, expected_header in EVIDENCE_TABLES.items():
        path = validation_root / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Required release evidence table is missing or empty: {name}")
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != expected_header:
                raise ValueError(
                    f"Evidence table header mismatch for {name}: "
                    f"{tuple(reader.fieldnames or ())!r} != {expected_header!r}"
                )
            rows = list(reader)
        if not rows:
            raise ValueError(f"Required release evidence table has no rows: {name}")
        if any(not row.get(expected_header[0], "").strip() for row in rows):
            raise ValueError(f"Evidence table has an empty row identity: {name}")

        if name == "module_status_matrix.tsv":
            invalid = sorted(
                {row["status"] for row in rows if row["status"] not in allowed_module_states}
            )
            if invalid:
                raise ValueError(f"Invalid module states in {name}: {invalid}")
        elif name == "resource_usage.tsv":
            for row in rows:
                status = row["measurement_status"]
                if status not in {"measured", "unavailable"}:
                    raise ValueError(f"Invalid resource measurement status: {status!r}")
                if status == "unavailable" and not row["reason"].strip():
                    raise ValueError("Unavailable resource measurement lacks a reason")
                if status == "measured":
                    for field in (
                        "wall_seconds",
                        "user_cpu_seconds",
                        "system_cpu_seconds",
                        "max_rss_kb",
                    ):
                        try:
                            if float(row[field]) < 0:
                                raise ValueError
                        except ValueError as error:
                            raise ValueError(
                                f"Invalid measured resource value {field}={row[field]!r}"
                            ) from error
        elif name in {"figure_provenance.tsv", "table_provenance.tsv"}:
            for row in rows:
                relative = Path(row["packet_path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"Unsafe packet_path in {name}: {row['packet_path']!r}")
                if re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None:
                    raise ValueError(f"Invalid SHA-256 in {name}: {row['sha256']!r}")


def _text_payload(path: Path) -> str | None:
    if any(part in {"dist", "figures"} for part in path.parts):
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def sanitize_packet_paths(packet_root: Path, replacements: dict[Path, str]) -> None:
    ordered = sorted(
        ((str(path.resolve(strict=False)), marker) for path, marker in replacements.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for path in sorted(packet_root.rglob("*")):
        if not path.is_file() or path.name == "verify_bundle.sh":
            continue
        text = _text_payload(path)
        if text is None:
            continue
        sanitized = text
        for absolute, marker in ordered:
            sanitized = sanitized.replace(absolute, marker)
        sanitized = re.sub(r"/Users/[^/\s]+", "${HOME}", sanitized)
        sanitized = re.sub(r"/home/[^/\s]+", "${HOME}", sanitized)
        sanitized = sanitized.replace("/private/tmp", "${TMPDIR}")
        sanitized = re.sub(
            r"(?i)[A-Z]:\\Users\\[^\\\s]+",
            "${HOME}",
            sanitized,
        )
        if sanitized != text:
            path.write_text(sanitized, encoding="utf-8")


def _reject_forbidden_json_keys(value: object, location: str = "root") -> None:
    forbidden = {
        "access_token",
        "refresh_token",
        "api_key",
        "authorization",
        "client_secret",
        "password",
        "cookie",
        "doi",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in forbidden:
                raise ValueError(f"Packet JSON contains forbidden key at {location}.{key}")
            _reject_forbidden_json_keys(nested, f"{location}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_forbidden_json_keys(nested, f"{location}[{index}]")


def validate_packet_hygiene(packet_root: Path) -> None:
    local_path_patterns = (
        r"/Users/[^/\s]+",
        r"/home/[^/\s]+",
        r"/private/tmp(?:/[^\s'\";]*)?",
        r"(?i)[A-Z]:\\Users\\[^\\\s]+",
    )
    secret_patterns = (
        r"(?i)https?://[^\s/:@]+:[^\s/@]+@",
        r"(?i)(?:access[_-]?token|refresh[_-]?token|api[_-]?key|password|authorization|cookie)\s*[:=]\s*\S+",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    )
    generic_doi = r"(?i)\b10\.\d{4,9}/[-._;()/:A-Z0-9]+"
    for path in sorted(packet_root.rglob("*")):
        if not path.is_file() or path.name == "verify_bundle.sh":
            continue
        text = _text_payload(path)
        if text is None:
            continue
        relative = path.relative_to(packet_root).as_posix()
        for pattern in local_path_patterns:
            if re.search(pattern, text):
                raise ValueError(f"Packet contains an absolute user path: {relative}")
        for pattern in secret_patterns:
            if re.search(pattern, text):
                raise ValueError(f"Packet contains secret-like material: {relative}")
        if re.search(generic_doi, text):
            raise ValueError(f"Core GitHub validation packet contains a DOI claim: {relative}")
        if path.suffix == ".json":
            try:
                value = json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError(f"Packet JSON is malformed: {relative}") from error
            _reject_forbidden_json_keys(value, relative)


def write_verifier(path: Path) -> None:
    script = r'''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 - "${ROOT}" <<'PY'
import csv
import hashlib
import json
import re
import sys
import tarfile
import zipfile
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

root = Path(sys.argv[1])
schema = "2.0"
profile = "github_release_validation_v1"
required_top_level = {
    "run.json", "release_identity.json", "cases.tsv", "acceptance",
    "claim_evidence_matrix.tsv", "module_status_matrix.tsv",
    "resource_usage.tsv", "figure_provenance.tsv", "table_provenance.tsv",
    "public_data_sources.tsv", "manuscript_handoff.tsv", "limitations.tsv",
    "environment.txt", "commands", "logs", "dist", "expected",
    "observed_normalized", "public_provenance", "public_environment", "figures",
    "filter_profile_results.tsv", "inputs.sha256", "raw_inputs.tsv",
    "CACHE_SEAL.sha256", "public_validation_oracle_v0.3.0.tsv",
    "oracle_assertions.tsv", "artifacts.sha256", "verify_bundle.sh",
}
missing = sorted(name for name in required_top_level if not (root / name).exists())
if missing:
    raise SystemExit(f"missing required evidence: {missing}")

for relative in (
    "acceptance", "commands", "commands/public", "logs", "logs/public",
    "dist", "expected", "observed_normalized", "public_provenance",
    "public_environment", "figures",
):
    evidence_root = root / relative
    if not evidence_root.is_dir() or not any(
        candidate.is_file() for candidate in evidence_root.rglob("*")
    ):
        raise SystemExit(f"required evidence directory is empty: {relative}")

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def parse_manifest(path, *, packet_paths):
    entries = {}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        raise SystemExit(f"empty hash manifest: {path.name}")
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise SystemExit(f"invalid hash manifest line in {path.name}: {line!r}")
        relative = match.group(2)
        if relative in entries:
            raise SystemExit(f"duplicate manifest path in {path.name}: {relative}")
        candidate = Path(relative)
        if packet_paths and (candidate.is_absolute() or ".." in candidate.parts):
            raise SystemExit(f"unsafe packet artifact path: {relative}")
        entries[relative] = match.group(1)
    return entries

artifact_hashes = parse_manifest(root / "artifacts.sha256", packet_paths=True)
actual_artifacts = {
    candidate.relative_to(root).as_posix()
    for candidate in root.rglob("*")
    if candidate.is_file() and candidate.name != "artifacts.sha256"
}
if set(artifact_hashes) != actual_artifacts:
    raise SystemExit(
        "artifact manifest inventory mismatch; "
        f"missing={sorted(actual_artifacts - set(artifact_hashes))}, "
        f"stale={sorted(set(artifact_hashes) - actual_artifacts)}"
    )
for relative, expected in artifact_hashes.items():
    if digest(root / relative) != expected:
        raise SystemExit(f"artifact hash mismatch: {relative}")

public_environment_files = (
    "conda-explicit.txt", "network_entrypoint_contract.tsv",
    "network_isolation.tsv", "pip-freeze.txt", "runtime_versions.json",
)
runtime_packages = {
    "mito-overview": "0.3.0", "pysam": "0.24.0", "pandas": "3.0.3",
    "numpy": "2.5.1", "matplotlib": "3.11.0", "requests": "2.34.2",
    "pytest": "9.1.1", "build": "1.5.0", "setuptools": "82.0.1",
    "wheel": "0.47.0", "python-docx": "1.2.0",
}
runtime_platforms = {
    "linux-64": {
        "system": "Linux", "machine": "x86_64",
        "network_platform": "Linux/x86_64",
        "isolation_method": "linux_unshare_network_namespace",
    },
    "osx-64": {
        "system": "Darwin", "machine": "x86_64",
        "network_platform": "Darwin/x86_64",
        "isolation_method": "macos_sandbox_exec_deny_network",
    },
    "osx-arm64": {
        "system": "Darwin", "machine": "arm64",
        "network_platform": "Darwin/arm64",
        "isolation_method": "macos_sandbox_exec_deny_network",
    },
}
network_fields = (
    "schema_version", "platform", "isolation_method", "isolation_scope",
    "parent_loopback_control", "isolated_loopback_probe", "probe_target",
    "probe_error", "invoking_uid", "invoking_gid", "child_uid", "child_gid",
    "network_isolation_verdict",
)
network_contract = (
    "entrypoint\tcontrol\tscope\n"
    "all IP sockets\tOS process-tree isolation\t"
    "macOS sandbox-exec deny network* or Linux network namespace\n"
    "curl\tPATH canary\trelease public-data runners\n"
    "wget\tPATH canary\tdefensive command guard\n"
    "mvTool requests\tMVTOOL_MODE=disabled\tpipeline external annotation module\n"
)

def normalized_project_name(value):
    return re.sub(r"[-_.]+", "-", value).lower()

def validate_public_environment(environment_root):
    if environment_root.is_symlink() or not environment_root.is_dir():
        raise SystemExit("public environment evidence is not a regular directory")
    children = list(environment_root.iterdir())
    if any(child.is_symlink() or not child.is_file() for child in children):
        raise SystemExit("public environment evidence contains a non-regular file")
    observed = tuple(sorted(child.name for child in children))
    if observed != public_environment_files:
        raise SystemExit("public environment evidence inventory mismatch")

    with (environment_root / "network_isolation.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != ("field", "value"):
            raise SystemExit("network-isolation evidence schema mismatch")
        isolation_rows = list(reader)
    if any(
        set(row) != {"field", "value"}
        or row.get("field") is None
        or row.get("value") is None
        for row in isolation_rows
    ):
        raise SystemExit("network-isolation evidence contains malformed rows")
    if tuple(row.get("field", "") for row in isolation_rows) != network_fields:
        raise SystemExit("network-isolation field inventory or order mismatch")
    isolation = {row["field"]: row.get("value", "") for row in isolation_rows}
    if len(isolation) != len(isolation_rows):
        raise SystemExit("network-isolation evidence contains duplicate fields")
    matching_platforms = [
        spec for spec in runtime_platforms.values()
        if spec["network_platform"] == isolation["platform"]
    ]
    if len(matching_platforms) != 1:
        raise SystemExit("network-isolation platform is unsupported")
    network_platform = matching_platforms[0]
    expected_isolation = {
        "schema_version": "1.0",
        "isolation_method": network_platform["isolation_method"],
        "isolation_scope": "process_tree",
        "parent_loopback_control": "reachable",
        "isolated_loopback_probe": "blocked",
        "probe_target": "parent_loopback_listener",
        "network_isolation_verdict": "PASS",
    }
    for field, expected in expected_isolation.items():
        if isolation[field] != expected:
            raise SystemExit(f"network-isolation evidence mismatch for {field}")
    if not isolation["probe_error"].strip():
        raise SystemExit("network-isolation blocked-probe error is missing")
    for field in ("invoking_uid", "invoking_gid", "child_uid", "child_gid"):
        if not re.fullmatch(r"[0-9]+", isolation[field]):
            raise SystemExit(f"network-isolation identity is invalid for {field}")
    if isolation["invoking_uid"] != isolation["child_uid"]:
        raise SystemExit("network-isolation child UID does not match invoking UID")
    if isolation["invoking_gid"] != isolation["child_gid"]:
        raise SystemExit("network-isolation child GID does not match invoking GID")

    try:
        runtime = json.loads(
            (environment_root / "runtime_versions.json").read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise SystemExit("public runtime version evidence is malformed") from error
    runtime_keys = {
        "schema_version", "platform_id", "system", "machine", "python",
        "python_executable", "mito_overview_module", "packages", "samtools",
        "htslib", "minimap2", "bwa", "threads",
        "installed_distribution_required",
    }
    if not isinstance(runtime, dict) or set(runtime) != runtime_keys:
        raise SystemExit("public runtime version evidence schema mismatch")
    platform_id = runtime.get("platform_id")
    if platform_id not in runtime_platforms:
        raise SystemExit("public runtime platform is unsupported")
    platform_spec = runtime_platforms[platform_id]
    expected_runtime = {
        "schema_version": "1.0", "system": platform_spec["system"],
        "machine": platform_spec["machine"], "python": "3.12.13",
        "packages": runtime_packages, "samtools": "samtools 1.23.1",
        "htslib": "Using htslib 1.23.1", "minimap2": "2.31-r1302",
        "bwa": "0.7.19-r1273", "threads": 4,
        "installed_distribution_required": True,
    }
    for field, expected in expected_runtime.items():
        if runtime.get(field) != expected:
            raise SystemExit(f"public runtime evidence mismatch for {field}")
    if isolation["platform"] != platform_spec["network_platform"]:
        raise SystemExit("runtime and network-isolation platform identities disagree")
    if not isinstance(runtime.get("python_executable"), str) or not runtime[
        "python_executable"
    ].strip():
        raise SystemExit("public runtime Python executable is missing")
    module_path = runtime.get("mito_overview_module")
    if not isinstance(module_path, str) or not module_path.replace("\\", "/").endswith(
        "/site-packages/mito_overview/__init__.py"
    ):
        raise SystemExit("public runtime did not use the installed distribution")

    freeze_names = set()
    for line in (environment_root / "pip-freeze.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" in line:
            name = line.split("==", 1)[0]
        elif " @ " in line:
            name = line.split(" @ ", 1)[0]
        else:
            continue
        freeze_names.add(normalized_project_name(name.strip()))
    expected_names = {normalized_project_name(name) for name in runtime_packages}
    if expected_names - freeze_names:
        raise SystemExit("public pip-freeze evidence lacks pinned packages")
    if not (environment_root / "conda-explicit.txt").read_text(
        encoding="utf-8"
    ).strip():
        raise SystemExit("public conda environment evidence is empty")
    if (environment_root / "network_entrypoint_contract.tsv").read_text(
        encoding="utf-8"
    ) != network_contract:
        raise SystemExit("public network-entrypoint contract mismatch")

    return {
        "path": "public_environment",
        "platform_id": platform_id,
        "network_platform": isolation["platform"],
        "isolation_method": isolation["isolation_method"],
        "isolation_scope": isolation["isolation_scope"],
        "threads": runtime["threads"],
        "installed_distribution_required": runtime[
            "installed_distribution_required"
        ],
        "files": [
            {
                "path": f"public_environment/{name}",
                "sha256": digest(environment_root / name),
                "bytes": (environment_root / name).stat().st_size,
            }
            for name in public_environment_files
        ],
    }

public_environment = validate_public_environment(root / "public_environment")

frozen_input_hashes = {
    "SRR10804585_1.fastq.gz": "b69746cb61d8bf3bc25887d6ece3c60db3acc7baaefd84a9a8b5d6ffce33288d",
    "SRR10804585_2.fastq.gz": "1fca2c35a955a4ed232465d8392bc04683828229178aee7915929e67b2aac961",
    "SRR10804590_1.fastq.gz": "e47ceceb03d44483b4948fe9c631ebff307f5ec68a1deec978f1122695fa58fc",
    "SRR10804590_2.fastq.gz": "05b2375b30b02c02e9206981eb2fe2d08babbc2a5809f8354ef56d0ac1550776",
    "SRR10804657_1.fastq.gz": "1afaf310ce9ffa77e1c3d61a0714e839d21000941d414cc7bf6fb590c3b665f2",
    "SRR10804657_2.fastq.gz": "bfc555c7e722695b02110027757bba4d7fc88f487798423cd6809e8a771a5184",
    "SRR18110025.fastq.gz": "c0872ee9ceb772ee5a4b76735c0d670e2159764b23dd800b6eb1f4933da11320",
}
input_hashes = parse_manifest(root / "inputs.sha256", packet_paths=False)
if input_hashes != frozen_input_hashes:
    raise SystemExit("inputs.sha256 does not contain the seven frozen public FASTQs")

frozen_raw_manifest_sha256 = "188d9e493c7cc43dc63c6bfe972914af5ae42cadb6cb2f59092cb13452adf756"
if digest(root / "raw_inputs.tsv") != frozen_raw_manifest_sha256:
    raise SystemExit("raw_inputs.tsv does not match the frozen v0.3.0 manifest")
seal_match = re.fullmatch(
    r"([0-9a-f]{64})  raw_inputs\.tsv\n?",
    (root / "CACHE_SEAL.sha256").read_text(encoding="utf-8"),
)
if seal_match is None or seal_match.group(1) != frozen_raw_manifest_sha256:
    raise SystemExit("CACHE_SEAL.sha256 does not bind raw_inputs.tsv")

raw_header = (
    "schema_version", "dataset_id", "run_accession", "sample_accession",
    "sample_alias", "sample_title", "source_sample_id", "library_strategy",
    "library_unit", "source_record_url", "filename", "bytes", "md5",
    "sha256", "fastq_records", "url",
)
with (root / "raw_inputs.tsv").open(encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    if tuple(reader.fieldnames or ()) != raw_header:
        raise SystemExit("raw_inputs.tsv schema mismatch")
    raw_inputs = list(reader)
if len(raw_inputs) != 7 or {row["filename"] for row in raw_inputs} != set(frozen_input_hashes):
    raise SystemExit("raw_inputs.tsv inventory mismatch")
if any(
    row["schema_version"] != "1.0"
    or row["sha256"] != frozen_input_hashes[row["filename"]]
    or not row["fastq_records"].isdigit()
    or int(row["fastq_records"]) <= 0
    for row in raw_inputs
):
    raise SystemExit("raw_inputs.tsv identity or FASTQ-record evidence mismatch")

frozen_oracle_sha256 = "dac769dcbac622f8a2df1363c08a926b0130082208d16b77a57d581cb7ccf76e"
oracle_path = root / "public_validation_oracle_v0.3.0.tsv"
if digest(oracle_path) != frozen_oracle_sha256:
    raise SystemExit("public-validation oracle is not the frozen v0.3.0 table")
with oracle_path.open(encoding="utf-8", newline="") as handle:
    oracle_rows = [
        {key: "" if value in (None, ".") else value for key, value in row.items()}
        for row in csv.DictReader(handle, delimiter="\t")
    ]
oracle = {(row["dataset"], row["profile"]): row for row in oracle_rows}
oracle_cases = {
    ("GM11906", "lenient"): ("gm11906_lenient",),
    ("GM11906", "default"): ("gm11906_default_run1", "gm11906_default_run2"),
    ("GM11906", "strict"): ("gm11906_strict",),
    ("GM12878", "lenient"): ("gm12878_lenient",),
    ("GM12878", "default"): ("gm12878_default_run1", "gm12878_default_run2"),
    ("GM12878", "strict"): ("gm12878_strict",),
}
if list(oracle) != list(oracle_cases):
    raise SystemExit("public-validation oracle profile inventory mismatch")

def semantic_equal(left, right):
    left = "" if left is None else str(left)
    right = "" if right is None else str(right)
    if left == right:
        return True
    try:
        return Decimal(left) == Decimal(right)
    except InvalidOperation:
        return False

def expected_assertions():
    output_names = sorted(name for names in oracle_cases.values() for name in names)
    required = {
        "oracle.profile_keys": repr(sorted(oracle_cases)),
        "matrix.output_directories": repr(output_names),
        "matrix.filter_profile_keys": repr(sorted(oracle_cases)),
    }
    filter_fields = (
        "min_base_quality", "min_mapping_quality", "min_read_mean_quality",
        "candidate_sites", "accepted_observations", "excluded_observations",
        "m8344_present", "m8344_alt_fraction",
    )
    case_fields = (
        "min_base_quality", "min_mapping_quality", "min_read_mean_quality",
        "candidate_sites", "accepted_observations", "excluded_observations",
    )
    statuses = (
        "copy_number_status", "phymer_status", "methylation_status",
        "mvtool_status", "numt_module_status", "numt_interpretation_status",
        "numt_reason_code",
    )
    long_fields = (
        "mapped_reads", "primary_reads", "supplementary_reads", "mean_depth",
        "median_depth", "selected_cosegregation_sites", "deletion_clusters",
        "deletion_query_names", "supplementary_sa_query_names", "source_records",
        "selected_names",
    )
    for key, case_ids in oracle_cases.items():
        row = oracle[key]
        for field in filter_fields:
            if row[field]:
                required[f"filter.{key[0]}.{key[1]}.{field}"] = row[field]
        for case_id in case_ids:
            for field in case_fields:
                required[f"{case_id}.{field}"] = row[field]
            required[f"{case_id}.m8344.present"] = row["m8344_present"]
            for field in ("summary_tsv_count", "html_count", "png_count"):
                required[f"{case_id}.inventory.{field}"] = row[field]
            for field in statuses:
                if row[field]:
                    required[f"{case_id}.status.{field}"] = row[field]
            if row["m8344_alt_count"]:
                for field in (
                    "m8344_callable_depth", "m8344_alt_count", "m8344_alt_forward",
                    "m8344_alt_reverse", "m8344_alt_fraction", "m8344_feature_label",
                    "m8344_feature_class", "m8344_consequence_class",
                ):
                    required[f"{case_id}.{field}"] = row[field]
                required[f"{case_id}.m8344_strand_sum"] = row["m8344_alt_count"]
                required[f"{case_id}.m8344.consequence_rows"] = "1"
            if key[0] == "GM12878":
                for field in long_fields:
                    required[f"{case_id}.{field}"] = row[field]
                required[f"{case_id}.selection_seed"] = (
                    "mito-overview-v0.3.0-GM12878-SRR18110025"
                )
            else:
                required[f"{case_id}.shortread.dataset_id"] = "GM11906_pooled_scATAC"
                required[f"{case_id}.shortread.derivation_id"] = "bwa-mem-samtools-sort-v1"
                required[f"{case_id}.shortread.source_runs"] = repr(
                    ["SRR10804585", "SRR10804590", "SRR10804657"]
                )
                required[f"{case_id}.shortread.raw_input_labels"] = repr(
                    [
                        "SRR10804585_R1", "SRR10804585_R2", "SRR10804590_R1",
                        "SRR10804590_R2", "SRR10804657_R1", "SRR10804657_R2",
                    ]
                )
    return required

with (root / "oracle_assertions.tsv").open(encoding="utf-8", newline="") as handle:
    assertion_reader = csv.DictReader(handle, delimiter="\t")
    if tuple(assertion_reader.fieldnames or ()) != (
        "assertion_id", "verdict", "expected", "observed", "detail",
    ):
        raise SystemExit("oracle_assertions.tsv schema mismatch")
    assertion_rows = list(assertion_reader)
assertions = {}
for row in assertion_rows:
    assertion_id = row["assertion_id"]
    if not assertion_id or assertion_id in assertions:
        raise SystemExit("oracle assertion identity is empty or duplicated")
    if row["verdict"] != "PASS" or not semantic_equal(row["expected"], row["observed"]):
        raise SystemExit(f"nonpassing or inconsistent oracle assertion: {assertion_id}")
    assertions[assertion_id] = row
required_assertions = expected_assertions()
missing_assertions = sorted(set(required_assertions) - set(assertions))
if missing_assertions:
    raise SystemExit(f"oracle assertion report is incomplete: {missing_assertions}")
for assertion_id, expected in required_assertions.items():
    if not semantic_equal(assertions[assertion_id]["expected"], expected):
        raise SystemExit(f"oracle assertion value drift: {assertion_id}")

profile_header = (
    "case_id", "dataset", "profile", "min_base_quality", "min_mapping_quality",
    "min_read_mean_quality", "candidate_sites", "accepted_observations",
    "excluded_observations", "m8344_A_G_present",
    "m8344_A_G_alt_allele_fraction",
)
with (root / "filter_profile_results.tsv").open(encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    if tuple(reader.fieldnames or ()) != profile_header:
        raise SystemExit("filter_profile_results.tsv schema mismatch")
    profile_rows = list(reader)
profiles = {(row["dataset"], row["profile"]): row for row in profile_rows}
if len(profiles) != len(profile_rows) or set(profiles) != set(oracle):
    raise SystemExit("filter-profile inventory mismatch")
profile_mapping = {
    "min_base_quality": "min_base_quality",
    "min_mapping_quality": "min_mapping_quality",
    "min_read_mean_quality": "min_read_mean_quality",
    "candidate_sites": "candidate_sites",
    "accepted_observations": "accepted_observations",
    "excluded_observations": "excluded_observations",
    "m8344_A_G_present": "m8344_present",
    "m8344_A_G_alt_allele_fraction": "m8344_alt_fraction",
}
for key, oracle_row in oracle.items():
    row = profiles[key]
    if row["case_id"] != f"{key[0].lower()}_{key[1]}":
        raise SystemExit(f"filter-profile case identity mismatch: {key}")
    for observed_field, oracle_field in profile_mapping.items():
        expected = oracle_row[oracle_field]
        if expected and not semantic_equal(row[observed_field], expected):
            raise SystemExit(f"filter-profile scientific mismatch: {key} {observed_field}")

forbidden_json_keys = {
    "access_token", "refresh_token", "api_key", "authorization",
    "client_secret", "password", "cookie", "doi",
}
local_path_patterns = (
    r"/Users/[^/\s]+", r"/home/[^/\s]+",
    r"/private/tmp(?:/[^\s'\";]*)?", r"(?i)[A-Z]:\\Users\\[^\\\s]+",
)
secret_patterns = (
    r"(?i)https?://[^\s/:@]+:[^\s/@]+@",
    r"(?i)(?:access[_-]?token|refresh[_-]?token|api[_-]?key|password|authorization|cookie)\s*[:=]\s*\S+",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", r"\bAKIA[0-9A-Z]{16}\b",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
)
generic_doi = r"(?i)\b10\.\d{4,9}/[-._;()/:A-Z0-9]+"

def reject_json_keys(value, location):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in forbidden_json_keys:
                raise SystemExit(f"forbidden JSON key at {location}.{key}")
            reject_json_keys(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_json_keys(child, f"{location}[{index}]")

for candidate in sorted(root.rglob("*")):
    if (
        not candidate.is_file()
        or candidate.name == "verify_bundle.sh"
        or "dist" in candidate.parts
        or "figures" in candidate.parts
    ):
        continue
    try:
        text = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    relative = candidate.relative_to(root).as_posix()
    if any(re.search(pattern, text) for pattern in local_path_patterns):
        raise SystemExit(f"absolute user path found in packet: {relative}")
    if any(re.search(pattern, text) for pattern in secret_patterns):
        raise SystemExit(f"secret-like material found in packet: {relative}")
    if re.search(generic_doi, text):
        raise SystemExit(f"DOI claim found in GitHub-only packet: {relative}")
    if candidate.suffix == ".json":
        reject_json_keys(json.loads(text), relative)

table_headers = {
    "claim_evidence_matrix.tsv": (
        "claim_id", "bounded_claim", "evidence", "limitation",
    ),
    "module_status_matrix.tsv": (
        "dataset", "case_id", "module", "status", "reason_code", "source_table",
    ),
    "resource_usage.tsv": (
        "case_id", "wall_seconds", "user_cpu_seconds", "system_cpu_seconds",
        "max_rss_kb", "threads", "platform", "measurement_status", "reason",
    ),
    "figure_provenance.tsv": (
        "figure_id", "dataset", "case_id", "packet_path", "sha256", "bytes",
        "width", "height", "visual_status", "source_inventory",
    ),
    "table_provenance.tsv": (
        "table_id", "dataset", "case_id", "packet_path", "sha256", "rows",
        "columns", "purpose",
    ),
    "public_data_sources.tsv": (
        "dataset", "run_accession", "study_accession", "sample_accession",
        "cell_line", "platform", "instrument_model", "library_strategy",
        "fastq_url", "fastq_md5", "fastq_sha256", "fastq_bytes",
        "metadata_recorded_utc", "role", "redistribution",
    ),
    "manuscript_handoff.tsv": (
        "result_id", "dataset", "metric", "value", "unit", "source_table",
        "claim_boundary",
    ),
    "limitations.tsv": (
        "limitation_id", "scope", "limitation", "release_effect",
    ),
}
evidence_rows = {}
for name, expected_header in table_headers.items():
    with (root / name).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != expected_header:
            raise SystemExit(f"evidence table header mismatch: {name}")
        rows = list(reader)
    if not rows or any(not row.get(expected_header[0], "").strip() for row in rows):
        raise SystemExit(f"evidence table is empty or has missing identities: {name}")
    evidence_rows[name] = rows

states = {"ok", "not_configured", "not_applicable", "not_evaluable", "unavailable"}
invalid_states = sorted(
    {
        row["status"]
        for row in evidence_rows["module_status_matrix.tsv"]
        if row["status"] not in states
    }
)
if invalid_states:
    raise SystemExit(f"invalid module states: {invalid_states}")

source_rows = evidence_rows["public_data_sources.tsv"]
source_by_run = {row["run_accession"]: row for row in source_rows}
raw_by_run = {}
for row in raw_inputs:
    raw_by_run.setdefault(row["run_accession"], []).append(row)
if len(source_by_run) != len(source_rows) or set(source_by_run) != set(raw_by_run):
    raise SystemExit("public_data_sources.tsv run inventory does not bind the raw manifest")
expected_source_metadata = {
    "SRR10804585": (
        "GM11906 pooled single-cell ATAC-seq pseudo-bulk", "PRJNA598179",
        "GM11906", "ILLUMINA", "NextSeq 550", "ATAC-seq",
    ),
    "SRR10804590": (
        "GM11906 pooled single-cell ATAC-seq pseudo-bulk", "PRJNA598179",
        "GM11906", "ILLUMINA", "NextSeq 550", "ATAC-seq",
    ),
    "SRR10804657": (
        "GM11906 pooled single-cell ATAC-seq pseudo-bulk", "PRJNA598179",
        "GM11906", "ILLUMINA", "NextSeq 550", "ATAC-seq",
    ),
    "SRR18110025": (
        "GM12878 ONT targeted-mt proof-of-principle", "PRJNA809571",
        "GM12878", "OXFORD_NANOPORE", "GridION", "OTHER",
    ),
}
for run_accession, inputs in raw_by_run.items():
    row = source_by_run[run_accession]
    first = inputs[0]
    expected_identity = expected_source_metadata[run_accession]
    observed_identity = (
        row["dataset"], row["study_accession"], row["cell_line"], row["platform"],
        row["instrument_model"], row["library_strategy"],
    )
    if observed_identity != expected_identity or row["sample_accession"] != first["sample_accession"]:
        raise SystemExit(f"public source metadata mismatch: {run_accession}")
    for field, raw_field in (
        ("fastq_url", "url"), ("fastq_md5", "md5"),
        ("fastq_sha256", "sha256"), ("fastq_bytes", "bytes"),
    ):
        if row[field] != ";".join(item[raw_field] for item in inputs):
            raise SystemExit(f"public source input mismatch: {run_accession} {field}")
    if (
        row["role"] != "fixed-input reproducibility and descriptive filter profile"
        or row["redistribution"] != "raw reads excluded from Git and validation ZIP"
    ):
        raise SystemExit(f"public source claim boundary mismatch: {run_accession}")
    try:
        recorded = datetime.fromisoformat(
            row["metadata_recorded_utc"].replace("Z", "+00:00")
        )
    except ValueError as error:
        raise SystemExit(
            f"public source metadata-recorded timestamp is invalid: {run_accession}"
        ) from error
    if recorded.tzinfo is None or recorded.utcoffset() is None:
        raise SystemExit(
            f"public source metadata-recorded timestamp lacks timezone: {run_accession}"
        )

def read_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    return fields, rows

def metric_map(path):
    fields, rows = read_rows(path)
    if fields != ("metric", "value") or not rows:
        raise SystemExit(f"metric/value table is malformed: {path}")
    values = {row["metric"]: row["value"] for row in rows}
    if len(values) != len(rows):
        raise SystemExit(f"duplicate metric: {path}")
    return values

for dataset_key, dataset_name in (("gm11906", "GM11906"), ("gm12878", "GM12878")):
    run1 = root / "observed_normalized" / f"{dataset_key}_default_run1"
    run2 = root / "observed_normalized" / f"{dataset_key}_default_run2"
    if not run1.is_dir() or not run2.is_dir():
        raise SystemExit(f"normalized repeat evidence is missing: {dataset_name}")
    ignored = {"normalized_manifest.tsv", "visual_artifact_inventory.tsv"}
    files1 = {
        path.relative_to(run1).as_posix(): path
        for path in run1.rglob("*.tsv") if path.name not in ignored
    }
    files2 = {
        path.relative_to(run2).as_posix(): path
        for path in run2.rglob("*.tsv") if path.name not in ignored
    }
    if set(files1) != set(files2) or len(files1) != 44:
        raise SystemExit(f"normalized summary inventory mismatch: {dataset_name}")
    for relative, first in files1.items():
        if first.read_bytes() != files2[relative].read_bytes():
            raise SystemExit(f"normalized repeat mismatch: {dataset_name} {relative}")
    for repeat_root, files in ((run1, files1), (run2, files2)):
        fields, rows = read_rows(repeat_root / "normalized_manifest.tsv")
        if fields != ("path", "sha256"):
            raise SystemExit(f"normalized manifest schema mismatch: {repeat_root.name}")
        manifest = {row["path"]: row["sha256"] for row in rows}
        expected_manifest = {relative: digest(path) for relative, path in files.items()}
        if manifest != expected_manifest:
            raise SystemExit(f"normalized manifest content mismatch: {repeat_root.name}")
    visual_structures = []
    visual_rows = []
    for repeat_root in (run1, run2):
        fields, rows = read_rows(repeat_root / "visual_artifact_inventory.tsv")
        if fields != (
            "relative_path", "artifact_type", "bytes", "sha256", "width_px",
            "height_px", "integrity_status",
        ) or not rows:
            raise SystemExit(f"visual inventory schema mismatch: {repeat_root.name}")
        if any(row["integrity_status"] != "ok" for row in rows):
            raise SystemExit(f"visual inventory contains a failure: {repeat_root.name}")
        visual_rows.append(rows)
        visual_structures.append([
            (
                row["relative_path"], row["artifact_type"], row["width_px"],
                row["height_px"], row["integrity_status"],
            )
            for row in rows
        ])
    if visual_structures[0] != visual_structures[1]:
        raise SystemExit(f"visual structures differ across repeats: {dataset_name}")
    default_oracle = oracle[(dataset_name, "default")]
    if (
        sum(row["artifact_type"] == "html" for row in visual_rows[0])
        != int(default_oracle["html_count"])
        or sum(row["artifact_type"] == "png" for row in visual_rows[0])
        != int(default_oracle["png_count"])
    ):
        raise SystemExit(f"visual inventory count mismatch: {dataset_name}")

    heteroplasmy = metric_map(run1 / "mito_heteroplasmy_summary.tsv")
    for oracle_field, metric in (
        ("min_base_quality", "allele_min_base_quality"),
        ("min_mapping_quality", "allele_min_mapping_quality"),
        ("min_read_mean_quality", "allele_min_read_mean_quality"),
        ("accepted_observations", "accepted_observations"),
        ("excluded_observations", "excluded_observations"),
    ):
        if not semantic_equal(heteroplasmy.get(metric), default_oracle[oracle_field]):
            raise SystemExit(f"normalized heteroplasmy oracle mismatch: {dataset_name} {metric}")
    _, candidates = read_rows(run1 / "mito_heteroplasmy_candidates.tsv")
    if len(candidates) != int(default_oracle["candidate_sites"]):
        raise SystemExit(f"normalized candidate count mismatch: {dataset_name}")
    marker = [
        row for row in candidates
        if row.get("position") == "8344"
        and row.get("ref_base", "").upper() == "A"
        and row.get("alt_base", "").upper() == "G"
    ]
    if len(marker) != int(default_oracle["m8344_present"]):
        raise SystemExit(f"normalized m.8344A>G presence mismatch: {dataset_name}")
    if marker:
        for oracle_field, table_field in (
            ("m8344_callable_depth", "callable_depth"),
            ("m8344_alt_count", "alt_count"),
            ("m8344_alt_forward", "alt_forward"),
            ("m8344_alt_reverse", "alt_reverse"),
            ("m8344_alt_fraction", "alt_allele_fraction"),
        ):
            if not semantic_equal(marker[0].get(table_field), default_oracle[oracle_field]):
                raise SystemExit(f"normalized marker oracle mismatch: {oracle_field}")
    status_specs = (
        ("copy_number_status", "mito_copy_number_summary.tsv", "status"),
        ("phymer_status", "mito_phymer_haplogroup_summary.tsv", "status"),
        ("methylation_status", "mito_methylation_exploratory_summary.tsv", "status"),
        ("mvtool_status", "mito_mvtool_annotation_summary.tsv", "status"),
        ("numt_module_status", "mito_numt_qc_summary.tsv", "status"),
        ("numt_interpretation_status", "mito_numt_qc_summary.tsv", "numt_interpretation_status"),
        ("numt_reason_code", "mito_numt_qc_summary.tsv", "reason_code"),
    )
    loaded = {}
    for oracle_field, filename, metric in status_specs:
        expected = default_oracle[oracle_field]
        if expected:
            loaded.setdefault(filename, metric_map(run1 / filename))
            if loaded[filename].get(metric) != expected:
                raise SystemExit(f"normalized module status mismatch: {dataset_name} {oracle_field}")
    if dataset_name == "GM12878":
        long_tables = {
            "mito_qc_summary.tsv": {
                "mapped_reads": "mapped_reads", "primary_reads": "primary_reads",
                "supplementary_reads": "supplementary_reads", "mean_depth": "mean_depth",
                "median_depth": "median_depth",
            },
            "mito_cosegregation_summary.tsv": {
                "selected_cosegregation_sites": "selected_sites",
            },
            "mito_deletion_summary.tsv": {
                "deletion_clusters": "candidate_deletion_clusters",
                "deletion_query_names": "reads_with_large_deletion",
                "supplementary_sa_query_names": "reads_with_supplementary_or_SA",
            },
        }
        for filename, mappings in long_tables.items():
            values = metric_map(run1 / filename)
            for oracle_field, metric in mappings.items():
                if not semantic_equal(values.get(metric), default_oracle[oracle_field]):
                    raise SystemExit(f"normalized long-read oracle mismatch: {oracle_field}")

short_manifest_path = (
    root / "public_provenance/GM11906_MERRF_shortread.alignment.provenance.json"
)
short_manifest = json.loads(short_manifest_path.read_text(encoding="utf-8"))
if (
    short_manifest.get("dataset_id") != "GM11906_pooled_scATAC"
    or short_manifest.get("derivation", {}).get("derivation_id")
    != "bwa-mem-samtools-sort-v1"
):
    raise SystemExit("short-read alignment derivation identity mismatch")
short_inputs = {
    record.get("label"): record
    for record in short_manifest.get("public_inputs", [])
    if isinstance(record, dict)
}
short_labels = {
    "SRR10804585_R1": "SRR10804585_1.fastq.gz",
    "SRR10804585_R2": "SRR10804585_2.fastq.gz",
    "SRR10804590_R1": "SRR10804590_1.fastq.gz",
    "SRR10804590_R2": "SRR10804590_2.fastq.gz",
    "SRR10804657_R1": "SRR10804657_1.fastq.gz",
    "SRR10804657_R2": "SRR10804657_2.fastq.gz",
}
if set(short_inputs) != {*short_labels, "combined_R1", "combined_R2"}:
    raise SystemExit("short-read alignment input inventory is incomplete")
raw_by_name = {row["filename"]: row for row in raw_inputs}
for label, filename in short_labels.items():
    record = short_inputs[label]
    expected = raw_by_name[filename]
    if (
        record.get("name") != filename
        or record.get("bytes") != int(expected["bytes"])
        or record.get("md5") != expected["md5"]
        or record.get("sha256") != expected["sha256"]
    ):
        raise SystemExit(f"short-read alignment is not bound to frozen input: {label}")
for label, expected_name, component_labels in (
    (
        "combined_R1", "GM11906_MERRF_R1.fastq.gz",
        ("SRR10804585_R1", "SRR10804590_R1", "SRR10804657_R1"),
    ),
    (
        "combined_R2", "GM11906_MERRF_R2.fastq.gz",
        ("SRR10804585_R2", "SRR10804590_R2", "SRR10804657_R2"),
    ),
):
    combined = short_inputs[label]
    if (
        combined.get("name") != expected_name
        or combined.get("bytes")
        != sum(short_inputs[component]["bytes"] for component in component_labels)
    ):
        raise SystemExit(f"short-read combined derivation mismatch: {label}")
source_fields, source_libraries = read_rows(
    root / "public_provenance/GM11906_MERRF_shortread.source_libraries.tsv"
)
expected_source_libraries = [
    (
        "SRR10804585", "GSM4238454", "GM11906", "ATAC-seq",
        "single_cell_library", "pooled_pseudobulk",
        "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238454",
    ),
    (
        "SRR10804590", "GSM4238459", "GM11906", "ATAC-seq",
        "single_cell_library", "pooled_pseudobulk",
        "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238459",
    ),
    (
        "SRR10804657", "GSM4238526", "GM11906", "ATAC-seq",
        "single_cell_library", "pooled_pseudobulk",
        "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238526",
    ),
]
observed_source_libraries = [
    tuple(row[field] for field in source_fields) for row in source_libraries
]
if source_fields != (
    "run_accession", "geo_accession", "source_sample_id", "library_strategy",
    "library_unit", "combination_role", "source_record_url",
) or observed_source_libraries != expected_source_libraries:
    raise SystemExit("GM11906 three-cell source-library derivation mismatch")

long_subset = json.loads(
    (root / "public_provenance/GM12878_ONT_longread.fastq_subset.provenance.json")
    .read_text(encoding="utf-8")
)
long_source = long_subset.get("source_fastq", {})
expected_long = raw_by_name["SRR18110025.fastq.gz"]
if (
    long_source.get("name") != "SRR18110025.fastq.gz"
    or long_source.get("bytes") != int(expected_long["bytes"])
    or long_source.get("md5") != expected_long["md5"]
    or long_source.get("sha256") != expected_long["sha256"]
):
    raise SystemExit("long-read subset is not bound to the frozen SRR18110025 FASTQ")
selection = long_subset.get("selection", {})
selected_names_path = root / "public_provenance/GM12878_ONT_longread.selected_qnames.txt"
selected_names = selected_names_path.read_text(encoding="utf-8").splitlines()
if (
    selection.get("algorithm") != "smallest_sha256_seeded_query_names_v1"
    or selection.get("requested_query_names") != 1000
    or selection.get("selected_query_names") != 1000
    or selection.get("source_records_seen") != 193043
    or selection.get("seed") != "mito-overview-v0.3.0-GM12878-SRR18110025"
    or len(selected_names) != 1000
    or len(set(selected_names)) != 1000
):
    raise SystemExit("long-read deterministic subset derivation mismatch")

for row in evidence_rows["resource_usage.tsv"]:
    status = row["measurement_status"]
    if status not in {"measured", "unavailable"}:
        raise SystemExit(f"invalid resource status: {status}")
    if status == "unavailable" and not row["reason"].strip():
        raise SystemExit("unavailable resource measurement lacks a reason")
    if status == "measured":
        for field in (
            "wall_seconds", "user_cpu_seconds", "system_cpu_seconds", "max_rss_kb",
        ):
            try:
                if float(row[field]) < 0:
                    raise ValueError
            except ValueError as error:
                raise SystemExit(f"invalid resource measurement {field}") from error

for name in ("figure_provenance.tsv", "table_provenance.tsv"):
    for row in evidence_rows[name]:
        relative = Path(row["packet_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise SystemExit(f"unsafe provenance packet path in {name}")
        artifact = root / relative
        if not artifact.is_file() or digest(artifact) != row["sha256"]:
            raise SystemExit(f"provenance artifact mismatch in {name}: {relative}")

actual_normalized_paths = {
    path.relative_to(root).as_posix()
    for path in (root / "observed_normalized").rglob("*.tsv")
}
declared_normalized_paths = {
    row["packet_path"] for row in evidence_rows["table_provenance.tsv"]
}
if declared_normalized_paths != actual_normalized_paths:
    raise SystemExit("table provenance does not inventory every normalized TSV exactly once")
actual_figure_paths = {
    path.relative_to(root).as_posix()
    for path in (root / "figures").rglob("*.png")
}
declared_figure_paths = {
    row["packet_path"] for row in evidence_rows["figure_provenance.tsv"]
}
if declared_figure_paths != actual_figure_paths:
    raise SystemExit("figure provenance does not inventory every packaged PNG exactly once")
for row in evidence_rows["module_status_matrix.tsv"]:
    source = root / row["source_table"]
    if not source.is_file():
        raise SystemExit(f"module status source table is missing: {row['source_table']}")
    values = metric_map(source)
    if values.get("status") != row["status"] or values.get("reason_code", "") != row["reason_code"]:
        raise SystemExit(f"module status matrix disagrees with {row['source_table']}")
observed_module_rows = {}
for row in evidence_rows["module_status_matrix.tsv"]:
    key = (row["case_id"], row["module"])
    if key in observed_module_rows:
        raise SystemExit(f"duplicate module status row: {key}")
    observed_module_rows[key] = (
        row["status"], row["reason_code"], row["source_table"],
    )
expected_module_rows = {}
for case_id in ("gm11906_default_run1", "gm12878_default_run1"):
    for table in sorted((root / "observed_normalized" / case_id).glob("*.tsv")):
        fields, rows = read_rows(table)
        if fields != ("metric", "value") or not rows:
            continue
        values = {row["metric"]: row["value"] for row in rows}
        if "status" in values:
            expected_module_rows[(case_id, table.stem)] = (
                values["status"], values.get("reason_code", ""),
                f"observed_normalized/{case_id}/{table.name}",
            )
if observed_module_rows != expected_module_rows:
    raise SystemExit("module status matrix is not the exact default-module inventory")

def parse_environment(path):
    wanted = {
        "release_version", "git_commit", "repository", "github_actions_run_id",
    }
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in wanted:
            if key in values:
                raise SystemExit(f"duplicate environment identity key: {key}")
            values[key] = value.strip()
    if set(values) != wanted:
        raise SystemExit(f"environment identity keys missing: {sorted(wanted - set(values))}")
    return values

run = json.loads((root / "run.json").read_text(encoding="utf-8"))
identity = json.loads((root / "release_identity.json").read_text(encoding="utf-8"))
environment = parse_environment(root / "environment.txt")
for label, value in (("run", run), ("identity", identity)):
    if value.get("schema_version") != schema:
        raise SystemExit(f"{label} schema version mismatch")
    if value.get("validation_profile") != profile:
        raise SystemExit(f"{label} validation profile mismatch")
if run.get("release_version") != "v0.3.0" or identity.get("release_version") != "v0.3.0":
    raise SystemExit("release identity mismatch")
if identity.get("package_version") != "0.3.0" or identity.get("package_name") != "mito-overview":
    raise SystemExit("package identity mismatch")
commit = identity.get("git_commit")
repository = identity.get("repository")
if not re.fullmatch(r"[0-9a-f]{40}", str(commit or "")):
    raise SystemExit("invalid release commit")
if repository != "https://github.com/elissonnog/mito-overview":
    raise SystemExit("unexpected GitHub repository identity")
if len({
    run.get("git_commit"), commit, environment.get("git_commit"),
    identity.get("environment_git_commit"),
}) != 1:
    raise SystemExit("release commit is inconsistent across packet evidence")
if len({run.get("repository"), repository, environment.get("repository")}) != 1:
    raise SystemExit("repository identity is inconsistent across packet evidence")
if identity.get("source_worktree_clean") is not True:
    raise SystemExit("release identity was not built from a clean worktree")
if identity.get("canonical_metadata") != {
    "name": "mito-overview",
    "version": "0.3.0",
    "repository": repository,
    "license": "MIT",
    "creators": ["Elisson Lopes", "Xiaowu Gai"],
}:
    raise SystemExit("canonical package metadata is inconsistent")
required_metadata = {
    "pyproject.toml", "mito_overview/__init__.py", "CITATION.cff",
}
if (
    set(identity.get("metadata_versions", {})) != required_metadata
    or set(identity["metadata_versions"].values()) != {"0.3.0"}
    or set(identity.get("metadata_sha256", {})) != required_metadata
):
    raise SystemExit("package metadata identity is incomplete")
if run.get("diagnostic_validation_claimed") is not False:
    raise SystemExit("packet exceeds its bounded non-diagnostic claim scope")
if run.get("evidence_tables") != sorted(table_headers):
    raise SystemExit("run record evidence-table inventory mismatch")
if identity.get("public_environment") != public_environment:
    raise SystemExit("release identity public-environment evidence mismatch")
if identity.get("public_input_evidence") != {
    "manifest_path": "raw_inputs.tsv",
    "manifest_sha256": frozen_raw_manifest_sha256,
    "seal_path": "CACHE_SEAL.sha256",
    "seal_sha256": digest(root / "CACHE_SEAL.sha256"),
    "input_count": 7,
}:
    raise SystemExit("release identity public-input evidence mismatch")
scientific_oracle = identity.get("scientific_oracle")
if not isinstance(scientific_oracle, dict) or scientific_oracle != {
    "oracle_path": "public_validation_oracle_v0.3.0.tsv",
    "oracle_sha256": frozen_oracle_sha256,
    "assertions_path": "oracle_assertions.tsv",
    "assertion_count": len(assertion_rows),
    "required_assertion_count": len(required_assertions),
}:
    raise SystemExit("release identity scientific-oracle evidence mismatch")

fresh = json.loads((root / "acceptance/fresh_clone.json").read_text(encoding="utf-8"))
fresh_truths = (
    "public_https_clone", "isolated_home", "isolated_tmpdir", "built_wheel",
    "built_sdist", "installed_wheel", "executed_outside_checkout",
)
if (
    fresh.get("schema_version") != schema
    or fresh.get("validation_profile") != profile
    or fresh.get("verdict") != "PASS"
    or fresh.get("repository") != repository
    or fresh.get("candidate_commit") != commit
    or fresh.get("checked_out_commit") != commit
    or fresh.get("source_remote") != repository + ".git"
    or fresh.get("detached_head") is not True
    or fresh.get("clone_worktree_clean") is not True
    or any(fresh.get(field) is not True for field in fresh_truths)
):
    raise SystemExit("fresh-clone acceptance mismatch")

actions_run = json.loads(
    (root / "acceptance/github_actions_run.json").read_text(encoding="utf-8")
)
actions_jobs = json.loads(
    (root / "acceptance/github_actions_jobs.json").read_text(encoding="utf-8")
)
run_id = actions_run.get("id")
if (
    isinstance(run_id, bool)
    or not isinstance(run_id, int)
    or run_id <= 0
    or actions_run.get("name") != "smoke-tests"
    or actions_run.get("event") != "push"
    or actions_run.get("head_branch") != "main"
    or actions_run.get("path") != ".github/workflows/smoke-tests.yml"
    or actions_run.get("head_sha") != commit
    or actions_run.get("status") != "completed"
    or actions_run.get("conclusion") != "success"
):
    raise SystemExit("GitHub Actions run identity mismatch")
if (
    str(run_id) != environment["github_actions_run_id"]
    or identity.get("environment_github_actions_run_id") != run_id
    or run.get("github_actions_run_id") != run_id
):
    raise SystemExit("GitHub Actions run ID is inconsistent")
jobs = actions_jobs.get("jobs")
job_expectations = {
    "github_actions_linux_candidate_commit": (
        "Unit and synthetic tests (ubuntu-24.04)", "ubuntu-24.04",
    ),
    "github_actions_macos_candidate_commit": (
        "Unit and synthetic tests (macos-15-intel)", "macos-15-intel",
    ),
    "github_actions_macos_arm64_candidate_commit": (
        "Unit and synthetic tests (macos-15)", "macos-15",
    ),
}
if not isinstance(jobs, list):
    raise SystemExit("GitHub Actions jobs evidence is malformed")
selected_jobs = []
for case_id, (name, label) in job_expectations.items():
    matching = [job for job in jobs if isinstance(job, dict) and job.get("name") == name]
    if len(matching) != 1:
        raise SystemExit(f"missing or ambiguous GitHub job: {name}")
    job = matching[0]
    if (
        label not in job.get("labels", [])
        or job.get("head_sha") != commit
        or job.get("run_id") != run_id
        or job.get("status") != "completed"
        or job.get("conclusion") != "success"
    ):
        raise SystemExit(f"GitHub Actions job identity mismatch: {name}")
    selected_jobs.append({
        "job_id": job["id"], "name": job["name"], "labels": job["labels"],
        "head_sha": job["head_sha"], "url": job["html_url"],
    })
expected_ci = {
    "provider": "github_actions",
    "run_id": run_id,
    "run_attempt": actions_run["run_attempt"],
    "workflow": actions_run["name"],
    "workflow_path": actions_run["path"],
    "event": actions_run["event"],
    "branch": actions_run["head_branch"],
    "head_sha": actions_run["head_sha"],
    "status": actions_run["status"],
    "conclusion": actions_run["conclusion"],
    "url": actions_run["html_url"],
    "jobs": selected_jobs,
}
if identity.get("github_actions") != expected_ci:
    raise SystemExit("release identity GitHub Actions evidence mismatch")

required_pass = {
    "unit_known_answer", "cli_step_listing", "strict_generic_dry_run",
    "synthetic_longread_smoke", "synthetic_shortread_smoke",
    "synthetic_longread_nomethyl_smoke", "standalone_minimal_smoke",
    "package_build", "public_validation_matrix", "gm11906_default_run1",
    "gm11906_default_run2", "gm11906_lenient", "gm11906_strict",
    "gm12878_default_run1", "gm12878_default_run2", "gm12878_lenient",
    "gm12878_strict", "gm11906_repeatability", "gm12878_repeatability",
    "gm11906_visual_integrity", "gm12878_visual_integrity", "filter_profiles",
    "offline_isolation",
    "fresh_clone_candidate_commit", "github_actions_linux_candidate_commit",
    "github_actions_macos_candidate_commit",
    "github_actions_macos_arm64_candidate_commit",
}
with (root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
    cases = list(csv.DictReader(handle, delimiter="\t"))
if not cases:
    raise SystemExit("no validation cases")
case_ids = set()
for case in cases:
    case_id = case.get("case_id", "")
    if not case_id or case_id in case_ids:
        raise SystemExit(f"missing or duplicate case_id: {case_id!r}")
    case_ids.add(case_id)
    if case.get("verdict") not in {"PASS", "FAIL", "XFAIL", "SKIP", "BLOCKED"}:
        raise SystemExit(f"invalid verdict: {case}")
    if case.get("verdict") == "PASS" and (
        case.get("input_available") != "1" or case.get("expected_available") != "1"
    ):
        raise SystemExit(f"unsupported PASS verdict: {case_id}")
blockers = sorted(
    f"{case['case_id']}={case['verdict']}"
    for case in cases
    if case["verdict"] in {"FAIL", "BLOCKED"}
)
if blockers:
    raise SystemExit(f"release-blocking validation verdicts: {blockers}")
if required_pass - case_ids:
    raise SystemExit(f"missing required release cases: {sorted(required_pass - case_ids)}")
nonpassing = sorted(
    case["case_id"]
    for case in cases
    if case["case_id"] in required_pass and case["verdict"] != "PASS"
)
if nonpassing:
    raise SystemExit(f"required release cases did not pass: {nonpassing}")
observed_counts = Counter(case["verdict"] for case in cases)
expected_counts = {
    verdict: observed_counts.get(verdict, 0)
    for verdict in {"PASS", "FAIL", "XFAIL", "SKIP", "BLOCKED"}
}
if run.get("case_count") != len(cases) or run.get("verdict_counts") != expected_counts:
    raise SystemExit("run.json case counts do not match cases.tsv")

def normalize_name(value):
    return re.sub(r"[-_.]+", "-", value).lower()

def metadata_fields(text, source):
    fields = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"Name", "Version"} and key not in fields:
            fields[key] = value.strip()
    if not fields.get("Name") or not fields.get("Version"):
        raise SystemExit(f"distribution metadata is incomplete: {source}")
    return fields["Name"], fields["Version"]

def inspect_dist(path):
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            members = sorted(
                name for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            )
            if len(members) != 1:
                raise SystemExit(f"invalid wheel metadata inventory: {path.name}")
            text = archive.read(members[0]).decode("utf-8")
        kind = "wheel"
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = sorted(
                (
                    member for member in archive.getmembers()
                    if member.name.endswith("/PKG-INFO")
                ),
                key=lambda member: member.name,
            )
            if len(members) != 1:
                raise SystemExit(f"invalid sdist metadata inventory: {path.name}")
            handle = archive.extractfile(members[0])
            if handle is None:
                raise SystemExit(f"unreadable sdist metadata: {path.name}")
            text = handle.read().decode("utf-8")
        kind = "sdist"
    else:
        raise SystemExit(f"unsupported distribution artifact: {path.name}")
    name, version = metadata_fields(text, path)
    return kind, name, version

dist_files = sorted(candidate for candidate in (root / "dist").rglob("*") if candidate.is_file())
declared_dist = identity.get("dist_artifacts", [])
declared_paths = {entry.get("path") for entry in declared_dist}
actual_dist_paths = {candidate.relative_to(root).as_posix() for candidate in dist_files}
if declared_paths != actual_dist_paths or len(declared_paths) != len(declared_dist):
    raise SystemExit("distribution inventory does not match release identity")
dist_kinds = set()
for entry in declared_dist:
    dist_path = root / entry["path"]
    kind, name, version = inspect_dist(dist_path)
    if (
        entry.get("kind") != kind
        or normalize_name(name) != "mito-overview"
        or entry.get("name") != name
        or version != "0.3.0"
        or entry.get("version") != version
        or entry.get("sha256") != digest(dist_path)
    ):
        raise SystemExit(f"distribution identity mismatch: {entry.get('path')}")
    dist_kinds.add(kind)
if dist_kinds != {"wheel", "sdist"}:
    raise SystemExit("release packet requires both wheel and sdist evidence")

normalized_tables = sorted((root / "observed_normalized").rglob("*.tsv"))
if not normalized_tables:
    raise SystemExit("normalized scientific evidence is empty")
for table in normalized_tables:
    with table.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    if not rows or rows[0][:2] != ["metric", "value"]:
        continue
    for row in rows[1:]:
        if len(row) >= 2 and row[0] == "status" and row[1] not in states:
            raise SystemExit(f"invalid module status {row[1]!r} in {table}")

public_inventory = identity.get("public_provenance")
if not isinstance(public_inventory, list) or not public_inventory:
    raise SystemExit("public provenance inventory is missing")
for entry in public_inventory:
    relative = entry.get("path")
    if not isinstance(relative, str) or not (root / relative).is_file():
        raise SystemExit("public provenance path is invalid")
    if entry.get("sha256") != digest(root / relative):
        raise SystemExit(f"public provenance hash mismatch: {relative}")

print(
    f"verified mito-overview {run['release_version']} "
    f"{run['validation_profile']} packet at commit {run['git_commit']}"
)
PY
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)



def build_packet(args: argparse.Namespace) -> Path:
    if not args.validation_root.is_dir():
        raise SystemExit(f"Validation root not found: {args.validation_root}")
    if args.packet_root.exists() and any(args.packet_root.iterdir()):
        raise SystemExit(f"Packet root must be absent or empty: {args.packet_root}")

    public_root = args.validation_root / "public"
    release_identity = resolve_release_identity(
        args.repo_root,
        args.validation_root / "environment.txt",
        args.version,
        args.repository,
        args.commit,
    )
    acceptance_rows = validate_acceptance_evidence(
        args.validation_root,
        str(release_identity["git_commit"]),
        str(release_identity["repository"]),
    )
    ci_identity = github_actions_identity(
        args.validation_root,
        str(release_identity["git_commit"]),
        str(release_identity["repository"]),
    )
    if release_identity["environment_github_actions_run_id"] != ci_identity["run_id"]:
        raise ValueError(
            "environment.txt github_actions_run_id does not match GitHub Actions evidence"
        )
    case_count, verdict_counts = validate_cases(
        args.validation_root / "cases.tsv",
        acceptance_rows,
    )
    validate_evidence_tables(args.validation_root)
    public_environment = validate_public_environment(
        public_root / "environment",
        args.repo_root,
    )
    public_inputs = validate_public_input_evidence(
        public_root,
        args.validation_root / "public_data_sources.tsv",
    )
    public_provenance = validate_public_provenance(
        public_root,
        list(public_inputs["rows"]),
    )
    scientific_evidence = validate_scientific_evidence(
        args.repo_root,
        args.validation_root,
        public_root,
    )
    dist_artifacts = validate_distributions(
        args.validation_root / "dist",
        str(release_identity["package_name"]),
        str(release_identity["package_version"]),
    )
    for source in (
        args.validation_root / "commands",
        public_root / "commands",
        args.validation_root / "logs",
        public_root / "logs",
        args.validation_root / "expected",
        public_root / "observed_normalized",
        args.validation_root / "figures",
    ):
        if not source.is_dir() or not any(candidate.is_file() for candidate in source.rglob("*")):
            raise ValueError(f"Required evidence directory is missing or empty: {source}")

    args.packet_root.mkdir(parents=True, exist_ok=True)

    for name in ("cases.tsv", "environment.txt", *EVIDENCE_TABLES):
        shutil.copy2(args.validation_root / name, args.packet_root / name)
    copy_tree(args.validation_root / "acceptance", args.packet_root / "acceptance")
    copy_tree(args.validation_root / "commands", args.packet_root / "commands")
    copy_tree(public_root / "commands", args.packet_root / "commands" / "public")
    copy_tree(args.validation_root / "logs", args.packet_root / "logs")
    copy_tree(public_root / "logs", args.packet_root / "logs" / "public")
    copy_tree(args.validation_root / "dist", args.packet_root / "dist")
    copy_tree(args.validation_root / "expected", args.packet_root / "expected")
    copy_tree(args.validation_root / "figures", args.packet_root / "figures")
    copy_tree(
        public_root / "observed_normalized",
        args.packet_root / "observed_normalized",
    )
    copy_tree(
        public_root / "environment",
        args.packet_root / PUBLIC_ENVIRONMENT_PACKET_PATH,
    )
    shutil.copy2(
        public_root / "filter_profile_results.tsv",
        args.packet_root / "filter_profile_results.tsv",
    )
    (args.packet_root / "inputs.sha256").write_text(
        str(public_inputs["canonical_inputs_sha256"]),
        encoding="utf-8",
    )
    shutil.copy2(
        public_root / RAW_INPUTS_PACKET_PATH,
        args.packet_root / RAW_INPUTS_PACKET_PATH,
    )
    shutil.copy2(
        public_root / CACHE_SEAL_PACKET_PATH,
        args.packet_root / CACHE_SEAL_PACKET_PATH,
    )
    shutil.copy2(
        public_root / ORACLE_ASSERTIONS_PACKET_PATH,
        args.packet_root / ORACLE_ASSERTIONS_PACKET_PATH,
    )
    shutil.copy2(
        args.repo_root / FROZEN_ORACLE_REPOSITORY_PATH,
        args.packet_root / FROZEN_ORACLE_PACKET_PATH,
    )
    for key, specification in PUBLIC_PROVENANCE_FILES.items():
        destination = args.packet_root / str(specification["packet"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(public_root / str(specification["source"]), destination)

    release_identity["dist_artifacts"] = dist_artifacts
    release_identity["acceptance_cases"] = [row["case_id"] for row in acceptance_rows]
    release_identity["github_actions"] = ci_identity
    release_identity["public_provenance"] = public_provenance
    release_identity["public_environment"] = public_environment
    release_identity["public_input_evidence"] = {
        "manifest_path": RAW_INPUTS_PACKET_PATH,
        "manifest_sha256": public_inputs["manifest_sha256"],
        "seal_path": CACHE_SEAL_PACKET_PATH,
        "seal_sha256": public_inputs["seal_sha256"],
        "input_count": len(public_inputs["rows"]),
    }
    release_identity["scientific_oracle"] = {
        "oracle_path": FROZEN_ORACLE_PACKET_PATH,
        "oracle_sha256": scientific_evidence["oracle_sha256"],
        "assertions_path": ORACLE_ASSERTIONS_PACKET_PATH,
        "assertion_count": scientific_evidence["assertion_count"],
        "required_assertion_count": scientific_evidence["required_assertion_count"],
    }
    (args.packet_root / "release_identity.json").write_text(
        json.dumps(release_identity, indent=2) + "\n",
        encoding="utf-8",
    )
    run = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "validation_profile": VALIDATION_PROFILE,
        "release_version": release_identity["release_version"],
        "git_commit": release_identity["git_commit"],
        "repository": release_identity["repository"],
        "github_actions_run_id": ci_identity["run_id"],
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": case_count,
        "verdict_counts": verdict_counts,
        "evidence_tables": sorted(EVIDENCE_TABLES),
        "claim_scope": "reproducible mode-gated mtDNA reporting workflow/resource",
        "diagnostic_validation_claimed": False,
    }
    (args.packet_root / "run.json").write_text(
        json.dumps(run, indent=2) + "\n",
        encoding="utf-8",
    )

    replacements = {
        args.validation_root: "${VALIDATION_ROOT}",
        args.repo_root: "${REPOSITORY_CHECKOUT}",
        args.packet_root: "${PACKET_ROOT}",
        args.zip_path: "${VALIDATION_ZIP}",
    }
    cache_root = getattr(args, "cache_root", None)
    if cache_root is not None:
        replacements[cache_root] = "${PUBLIC_CACHE}"
    sanitize_packet_paths(args.packet_root, replacements)

    packaged_environment = validate_public_environment(
        args.packet_root / PUBLIC_ENVIRONMENT_PACKET_PATH
    )
    if packaged_environment != public_environment:
        raise ValueError("Packaged public environment semantics changed during sanitization")
    packaged_environment["files"] = [
        {
            "path": f"{PUBLIC_ENVIRONMENT_PACKET_PATH}/{name}",
            "sha256": sha256(args.packet_root / PUBLIC_ENVIRONMENT_PACKET_PATH / name),
            "bytes": (args.packet_root / PUBLIC_ENVIRONMENT_PACKET_PATH / name).stat().st_size,
        }
        for name in PUBLIC_ENVIRONMENT_FILES
    ]
    identity_path = args.packet_root / "release_identity.json"
    packaged_identity = json.loads(identity_path.read_text(encoding="utf-8"))
    packaged_identity["public_environment"] = packaged_environment
    identity_path.write_text(
        json.dumps(packaged_identity, indent=2) + "\n",
        encoding="utf-8",
    )

    for name in ("figure_provenance.tsv", "table_provenance.tsv"):
        with (args.packet_root / name).open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        for row in rows:
            artifact = args.packet_root / row["packet_path"]
            if not artifact.is_file():
                raise ValueError(
                    f"Provenance table references a missing packet artifact: {row['packet_path']}"
                )
            if sha256(artifact) != row["sha256"]:
                raise ValueError(
                    f"Provenance table hash mismatch for packet artifact: {row['packet_path']}"
                )
    with (args.packet_root / "table_provenance.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        table_rows = list(csv.DictReader(handle, delimiter="\t"))
    actual_tables = {
        path.relative_to(args.packet_root).as_posix()
        for path in (args.packet_root / "observed_normalized").rglob("*.tsv")
    }
    declared_tables = {row["packet_path"] for row in table_rows}
    if declared_tables != actual_tables or len(declared_tables) != len(table_rows):
        raise ValueError("table_provenance.tsv does not exactly inventory normalized TSVs")
    with (args.packet_root / "figure_provenance.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        figure_rows = list(csv.DictReader(handle, delimiter="\t"))
    actual_figures = {
        path.relative_to(args.packet_root).as_posix()
        for path in (args.packet_root / "figures").rglob("*.png")
    }
    declared_figures = {row["packet_path"] for row in figure_rows}
    if declared_figures != actual_figures or len(declared_figures) != len(figure_rows):
        raise ValueError("figure_provenance.tsv does not exactly inventory packaged PNGs")

    write_verifier(args.packet_root / "verify_bundle.sh")
    validate_packet_hygiene(args.packet_root)

    artifact_rows: list[str] = []
    for artifact in sorted(args.packet_root.rglob("*")):
        if not artifact.is_file() or artifact.name == "artifacts.sha256":
            continue
        artifact_rows.append(
            f"{sha256(artifact)}  {artifact.relative_to(args.packet_root).as_posix()}"
        )
    (args.packet_root / "artifacts.sha256").write_text(
        "\n".join(artifact_rows) + "\n",
        encoding="utf-8",
    )

    missing = [name for name in REQUIRED_TOP_LEVEL if not (args.packet_root / name).exists()]
    if missing:
        raise SystemExit(f"Packet is missing required entries: {missing}")

    args.zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact in sorted(args.packet_root.rglob("*")):
            if artifact.is_file():
                archive.write(artifact, artifact.relative_to(args.packet_root).as_posix())
    print(args.zip_path)
    return args.zip_path



def main() -> None:
    build_packet(parse_args())


if __name__ == "__main__":
    main()
