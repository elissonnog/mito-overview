#!/usr/bin/env python3
"""Build the internally self-checking mito-overview v0.3.0 validation packet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import tomllib
import zipfile
import zlib
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


EXPECTED_RELEASE_VERSION = "v0.3.0"
EXPECTED_PACKAGE_NAME = "mito-overview"
EXPECTED_DISTRIBUTIONS = {
    "mito_overview-0.3.0-py3-none-any.whl": "wheel",
    "mito_overview-0.3.0.tar.gz": "sdist",
}
EXPECTED_LICENSE = "MIT"
EXPECTED_CREATORS = ("Elisson Lopes", "Xiaowu Gai")
PACKET_SCHEMA_VERSION = "2.0"
VALIDATION_PROFILE = "github_release_validation_v1"
PUBLIC_ENVIRONMENT_PACKET_PATH = "public_environment"
PUBLIC_MATRIX_CASES_PACKET_PATH = "public_matrix_cases.tsv"
PUBLIC_CONTRACTS_PACKET_PATH = "observed_contracts"
FINGERPRINT_FIELDS = (
    "candidate_table_sha256",
    "summary_inventory_sha256",
    "summary_schema_sha256",
)
SUMMARY_SCHEMA_MANIFEST_NAME = "summary_schema_manifest.tsv"
MACOS_REPORT_OUTPUTS_PACKET_PATH = "report_artifacts/macos/outputs"
RESOLVED_CI_ENVIRONMENTS_RELATIVE = "acceptance/resolved_ci_environments"
RESOLVED_CI_PLATFORMS = ("linux-64", "osx-64", "osx-arm64")
EXPECTED_PYTHON_VERSION = "3.12.13"
DECODED_PIXEL_HASH_COLUMNS = (
    "path",
    "width_px",
    "height_px",
    "decoded_rgba_sha256",
)
DECODED_PIXEL_REPORTS = {
    "GM11906": {
        "case_id": "gm11906_default_run1",
        "repeat_case_id": "gm11906_default_run2",
        "source": "logs/gm11906_decoded_pixel_hashes.tsv",
        "packet": "decoded_pixel_hashes/GM11906.tsv",
    },
    "GM12878": {
        "case_id": "gm12878_default_run1",
        "repeat_case_id": "gm12878_default_run2",
        "source": "logs/gm12878_decoded_pixel_hashes.tsv",
        "packet": "decoded_pixel_hashes/GM12878.tsv",
    },
}
PUBLIC_ENVIRONMENT_FILES = (
    "conda-explicit.txt",
    "network_entrypoint_contract.tsv",
    "network_isolation.tsv",
    "pip-freeze.txt",
    "runtime_versions.json",
)
EXPECTED_RUNTIME_PACKAGES = {
    "mito-overview": "0.3.0",
    "biopython": "1.87",
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
RESOLVED_CI_RUNNER_IDENTITY = {
    "linux-64": {"runner_os": "Linux", "runner_arch": "X64"},
    "osx-64": {"runner_os": "macOS", "runner_arch": "X64"},
    "osx-arm64": {"runner_os": "macOS", "runner_arch": "ARM64"},
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
    "shortread_source_metadata": {
        "source": (
            "outputs/gm11906_default_run1/provenance/"
            "GM11906_NCBI_source_metadata.json"
        ),
        "packet": "public_provenance/GM11906_NCBI_source_metadata.json",
    },
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
FROZEN_GM12878_SUBSET_SELECTION = {
    "algorithm": "smallest_sha256_seeded_query_names_v1",
    "requested_query_names": 1000,
    "selected_query_names": 1000,
    "source_records_seen": 193043,
    "subset_records_written": 1000,
    "seed": "mito-overview-v0.3.0-GM12878-SRR18110025",
}
FROZEN_GM12878_SUBSET_FASTQ_RECORD = {
    "name": "SRR18110025.deterministic-qnames-1000.fastq.gz",
    "bytes": 10721431,
    "md5": "a337abc2691753c56f030f7f523dd750",
    "sha256": "40e203ead1d621bfec8caa3c5d18cd1e7e70c08da27008a73364812b6871df33",
}
FROZEN_GM12878_SELECTED_QUERY_NAMES_RECORD = {
    "name": "SRR18110025.deterministic-qnames-1000.fastq.gz.selected_qnames.txt",
    "bytes": 18422,
    "md5": "64d606e56bf8dd58ad68baad28898e18",
    "sha256": "3444cc7db3dcf78bea807d8bcc6686883a7759d128288c1d26aeae077a771a19",
}
PUBLIC_ALIGNMENT_DERIVATIONS = {
    "GM11906_pooled_scATAC": {
        "derivation_id": "bwa-mem-samtools-sort-v1",
        "command_template": (
            "bwa mem -t {threads} {reference_fasta} {combined_r1} {combined_r2} "
            "| samtools sort -@ {threads} -o {alignment_bam}"
        ),
        "parameters": {"threads": "4"},
        "tool_versions": {
            "bwa": "0.7.19-r1273",
            "samtools": "samtools 1.23.1",
        },
    },
    "GM12878_SRR18110025_ONT_reduced_qn1000": {
        "derivation_id": (
            "minimap2-map-ont-deterministic-fastq-subset-mapped-only-v1"
        ),
        "command_template": (
            "minimap2 -t {threads} -ax map-ont {reference_mmi} "
            "{deterministic_subset_fastq} | samtools view -@ {threads} -b -F 4 "
            "| samtools sort -@ {threads} -o {alignment_bam}"
        ),
        "parameters": {
            "selected_query_names": "1000",
            "selection_seed": "mito-overview-v0.3.0-GM12878-SRR18110025",
            "threads": "4",
            "unmapped_filter_flag": "4",
        },
        "tool_versions": {
            "minimap2": "2.31-r1302",
            "samtools": "samtools 1.23.1",
        },
    },
}
GM11906_SOURCE_METADATA_REPOSITORY_PATH = Path(
    "resources/public_validation/gm11906_ncbi_source_metadata_v0.3.0.json"
)
GM11906_SOURCE_METADATA_PACKET_PATH = (
    "public_provenance/GM11906_NCBI_source_metadata.json"
)
GM11906_SOURCE_METADATA_SHA256 = (
    "01be488b9dc6bfce0726304be95db4259b1a85a53ac8e620cba4c337842d3185"
)
FROZEN_ORACLE_REPOSITORY_PATH = Path(
    "examples/public_validation/public_validation_oracle_v0.3.0.tsv"
)
FROZEN_ORACLE_PACKET_PATH = "public_validation_oracle_v0.3.0.tsv"
FROZEN_ORACLE_SHA256 = "221f6d4eba86d5d37e674aeaed553ac5d9829a5a216d116db38da35d58448e92"
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
PUBLIC_ORACLE_MODULE_STATUS_SPECS = (
    ("mito_qc_module_status", "mito_qc_summary.tsv"),
    ("heteroplasmy_module_status", "mito_heteroplasmy_summary.tsv"),
    ("deletions_module_status", "mito_deletion_summary.tsv"),
    ("copy_number_module_status", "mito_copy_number_summary.tsv"),
    ("feature_annotation_module_status", "mito_feature_annotation_summary.tsv"),
    ("cosegregation_module_status", "mito_cosegregation_summary.tsv"),
    ("gene_summary_module_status", "mito_gene_summary_run_summary.tsv"),
    ("numt_qc_module_status", "mito_numt_qc_summary.tsv"),
    ("identity_qc_module_status", "mito_identity_qc_summary.tsv"),
    ("variant_consequence_module_status", "mito_variant_consequence_summary.tsv"),
    ("circularity_qc_module_status", "mito_circularity_qc_summary.tsv"),
    (
        "methylation_exploratory_module_status",
        "mito_methylation_exploratory_summary.tsv",
    ),
    ("phymer_haplogroup_module_status", "mito_phymer_haplogroup_summary.tsv"),
    ("mvtool_annotation_module_status", "mito_mvtool_annotation_summary.tsv"),
)
FEATURE_ANNOTATION_SUCCESS_COLUMNS = (
    "feature_class",
    "feature_label",
    "candidate_sites",
    "mean_alt_allele_fraction",
    "mean_heteroplasmy",
    "control_region_annotation_status",
    "control_region_annotation_reason_code",
    "control_region_annotation_method",
    "control_region_annotation_mode",
    "control_region_reference_accession",
    "control_region_configured_sequence_sha256",
    "control_region_canonical_sequence_sha256",
    "control_region_exact_sequence_match",
    "control_region_configured_sequence_length",
    "control_region_canonical_sequence_length",
    "control_region_intervals_applied",
)
FEATURE_ANNOTATION_GATED_STATES = frozenset(
    {"not_configured", "not_applicable", "not_evaluable", "unavailable", "failed"}
)
PUBLIC_ORACLE_INTERPRETATION_SPECS = (
    (
        "numt_interpretation_status",
        "mito_numt_qc_summary.tsv",
        "numt_interpretation_status",
    ),
    (
        "numt_interpretation_reason_code",
        "mito_numt_qc_summary.tsv",
        "reason_code",
    ),
)

REQUIRED_TOP_LEVEL = (
    "run.json",
    "release_identity.json",
    "cases.tsv",
    "acceptance",
    "cross_platform_comparison.tsv",
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
    PUBLIC_CONTRACTS_PACKET_PATH,
    "public_provenance",
    PUBLIC_ENVIRONMENT_PACKET_PATH,
    "figures",
    "figures_repeat2",
    "decoded_pixel_hashes",
    "report_artifacts",
    "filter_profile_results.tsv",
    "inputs.sha256",
    RAW_INPUTS_PACKET_PATH,
    CACHE_SEAL_PACKET_PATH,
    FROZEN_ORACLE_PACKET_PATH,
    ORACLE_ASSERTIONS_PACKET_PATH,
    PUBLIC_MATRIX_CASES_PACKET_PATH,
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
        "measurement_id",
        "case_id",
        "candidate_commit",
        "command_path",
        "command_sha256",
        "packaged_command_sha256",
        "log_path",
        "log_sha256",
        "packaged_log_sha256",
        "wall_seconds",
        "user_cpu_seconds",
        "system_cpu_seconds",
        "max_rss_kb",
        "broad_declared_input_inventory_file_count",
        "broad_declared_input_inventory_bytes",
        "changed_or_new_output_inventory_file_count",
        "changed_or_new_output_inventory_bytes",
        "broad_declared_input_inventory_scope",
        "changed_or_new_output_inventory_scope",
        "io_measurement_method",
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

FROZEN_CLAIM_EVIDENCE_ROWS = (
    {
        "claim_id": "C1",
        "bounded_claim": (
            "Shared filtered allele counting is deterministic on known-answer fixtures"
        ),
        "evidence": (
            "unit_known_answer; synthetic_longread_smoke; "
            "expected/TOY-SR-001.expected_alleles.tsv"
        ),
        "limitation": "Reporting thresholds are not clinically calibrated",
    },
    {
        "claim_id": "C2",
        "bounded_claim": (
            "mvTool is offline by default with deterministic fixture coverage"
        ),
        "evidence": "unit_known_answer; synthetic_longread_smoke",
        "limitation": "No claim of live service availability",
    },
    {
        "claim_id": "C3",
        "bounded_claim": "Minimal standalone alignment contracts are preflighted",
        "evidence": (
            "unit_known_answer; strict_generic_dry_run; standalone_minimal_smoke"
        ),
        "limitation": "Optional sidecars remain user supplied",
    },
    {
        "claim_id": "C4",
        "bounded_claim": (
            "The WGS fixture reports a 100/10 mt:nuclear depth ratio of 10.0"
        ),
        "evidence": (
            "unit_known_answer; expected/TOY-WGS-001.expected_copy_proxy.tsv"
        ),
        "limitation": (
            "Experimental depth proxy, not absolute copies per diploid cell"
        ),
    },
    {
        "claim_id": "C5",
        "bounded_claim": "mt-only references suppress categorical NUMT interpretation",
        "evidence": (
            "unit_known_answer; gm12878_default_run1; gm12878_repeatability"
        ),
        "limitation": "Alignment-ambiguity QC is not a formal NUMT classifier",
    },
    {
        "claim_id": "C6",
        "bounded_claim": (
            "Public proof-of-principle workflows reproduce normalized TSVs"
        ),
        "evidence": (
            "gm11906_repeatability; gm12878_repeatability; "
            "filter_profile_results.tsv"
        ),
        "limitation": "Not an analytical-performance or diagnostic benchmark",
    },
)
HANDOFF_METRICS = (
    ("candidate_sites", "sites"),
    ("accepted_observations", "observations"),
    ("excluded_observations", "observations"),
    ("m8344_A_G_alt_allele_fraction", "fraction"),
)
HANDOFF_SOURCE_TABLE = "filter_profile_results.tsv"
HANDOFF_CLAIM_BOUNDARY = "descriptive fixed-input result; not diagnostic performance"
FILTER_PROFILE_HEADER = (
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

FRESH_CLONE_CASE_ID = "fresh_clone_candidate_commit"
GITHUB_ACTIONS_LINUX_CASE_ID = "github_actions_linux_candidate_commit"
GITHUB_ACTIONS_MACOS_CASE_ID = "github_actions_macos_candidate_commit"
GITHUB_ACTIONS_MACOS_ARM64_CASE_ID = "github_actions_macos_arm64_candidate_commit"
PR_HEAD_CI_CASE_ID = "pr_head_ci_candidate_commit"
REQUIRED_RESOURCE_CASE_IDS = frozenset(
    {
        FRESH_CLONE_CASE_ID,
        "package_build",
        "unit_known_answer",
        "cli_step_listing",
        "strict_generic_dry_run",
        "synthetic_longread_smoke",
        "synthetic_shortread_smoke",
        "synthetic_longread_nomethyl_smoke",
        "standalone_minimal_smoke",
        "public_cache_prepare",
        "public_validation_matrix",
    }
)
RESOURCE_CASE_THREAD_SETTINGS = {
    FRESH_CLONE_CASE_ID: "mixed",
    "package_build": "not_applicable",
    "unit_known_answer": "mixed",
    "cli_step_listing": "not_applicable",
    "strict_generic_dry_run": "4",
    "synthetic_longread_smoke": "1",
    "synthetic_shortread_smoke": "1",
    "synthetic_longread_nomethyl_smoke": "1",
    "standalone_minimal_smoke": "4",
    "public_cache_prepare": "not_applicable",
    "public_validation_matrix": "4",
}
READ_ONLY_AUDIT_MARKER = "<!-- mito-overview-read-only-audit-v1 -->"
READ_ONLY_AUDIT_SCHEMA_VERSION = "1.1"
READ_ONLY_AUDIT_METHOD = "read_only_agent_role_audit"
READ_ONLY_AUDIT_CASE_IDS = {
    "release_engineering": "read_only_audit_release_engineering",
    "bioinformatics": "read_only_audit_bioinformatics",
    "reproducibility": "read_only_audit_reproducibility",
}
EXPECTED_PUBLIC_VALIDATION_WORKFLOW = "public-validation"
EXPECTED_PUBLIC_VALIDATION_WORKFLOW_PATH = ".github/workflows/public-validation.yml"
REQUIRED_ACCEPTANCE_FILES = {
    "fresh_clone.json",
    "release_environment_verification.json",
    "github_actions_run.json",
    "github_actions_jobs.json",
    "pull_request.json",
    "pull_request_comments.json",
    "pull_request_github_actions_run.json",
    "pull_request_github_actions_jobs.json",
    "cross_platform_comparison.tsv",
    "cross_platform_public_reproduction.json",
}
REQUIRED_ACCEPTANCE_DIRECTORIES = {
    "resolved_ci_environments",
    "ubuntu_public_validation",
}
REQUIRED_PUBLIC_VALIDATION_ACCEPTANCE_FILES = {
    "ubuntu_public_validation/workflow_run.json",
    "ubuntu_public_validation/artifacts.json",
    "ubuntu_public_validation/artifact/SHA256SUMS",
    "ubuntu_public_validation/artifact/environment/identity.txt",
}

CROSS_PLATFORM_SCIENTIFIC_TOP_LEVEL = (
    "cases.tsv",
    "filter_profile_results.tsv",
    "inputs.sha256",
    "oracle_assertions.tsv",
    "raw_inputs.tsv",
    "CACHE_SEAL.sha256",
)
CROSS_PLATFORM_VISUAL_FIELDS = (
    "relative_path",
    "artifact_type",
    "width_px",
    "height_px",
    "integrity_status",
)
FORBIDDEN_PUBLIC_ARTIFACT_SUFFIXES = (
    ".fastq",
    ".fastq.gz",
    ".fq",
    ".fq.gz",
    ".bam",
    ".bai",
    ".cram",
    ".crai",
    ".sam",
)
ACCEPTANCE_CASE_IDS = {
    FRESH_CLONE_CASE_ID,
    GITHUB_ACTIONS_LINUX_CASE_ID,
    GITHUB_ACTIONS_MACOS_CASE_ID,
    GITHUB_ACTIONS_MACOS_ARM64_CASE_ID,
    PR_HEAD_CI_CASE_ID,
    *READ_ONLY_AUDIT_CASE_IDS.values(),
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
    "public_oracle",
    "raw_cache_seal",
    "offline_isolation",
    "project_network_entrypoints",
    "public_cache_prepare",
    "cross_platform_public_reproduction",
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


def md5_identity(path: Path) -> str:
    """Return an archival MD5 identity; SHA-256 remains the integrity digest."""

    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_posix_relative_path(value: str, label: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise ValueError(f"{label} is empty or uses a non-POSIX separator: {value!r}")
    relative = PurePosixPath(value.removeprefix("./"))
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise ValueError(f"{label} is unsafe: {value!r}")
    return relative


def parse_public_artifact_manifest(artifact_root: Path) -> dict[str, str]:
    if artifact_root.is_symlink() or not artifact_root.is_dir():
        raise ValueError("Downloaded public-validation artifact is not a regular directory")
    manifest_path = artifact_root / "SHA256SUMS"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Downloaded public-validation artifact lacks SHA256SUMS")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if match is None:
            raise ValueError(
                f"Malformed public-validation SHA256SUMS line {line_number}: {line!r}"
            )
        relative = safe_posix_relative_path(
            match.group(2), "public-validation manifest path"
        ).as_posix()
        if relative == "SHA256SUMS" or relative in entries:
            raise ValueError(
                f"Duplicate or self-referential public-validation manifest path: {relative}"
            )
        entries[relative] = match.group(1)
    if not entries:
        raise ValueError("Downloaded public-validation artifact manifest is empty")

    actual: set[str] = set()
    for candidate in artifact_root.rglob("*"):
        if candidate.is_symlink() or (not candidate.is_file() and not candidate.is_dir()):
            raise ValueError(
                "Downloaded public-validation artifact contains a symlink or non-regular entry"
            )
        if candidate.is_file() and candidate != manifest_path:
            relative = candidate.relative_to(artifact_root).as_posix()
            if relative.lower().endswith(FORBIDDEN_PUBLIC_ARTIFACT_SUFFIXES):
                raise ValueError(
                    f"Downloaded public-validation artifact contains raw/alignment data: {relative}"
                )
            actual.add(relative)
    if set(entries) != actual:
        raise ValueError(
            "Downloaded public-validation artifact manifest inventory mismatch: "
            f"missing={sorted(actual - set(entries))}; stale={sorted(set(entries) - actual)}"
        )
    for relative, expected in entries.items():
        observed = sha256(artifact_root / relative)
        if observed != expected:
            raise ValueError(
                f"Downloaded public-validation artifact hash mismatch: {relative}"
            )
    return entries


def public_scientific_paths(root: Path) -> set[PurePosixPath]:
    normalized_root = root / "observed_normalized"
    if normalized_root.is_symlink() or not normalized_root.is_dir():
        raise ValueError("Cross-platform observed_normalized directory is missing")
    paths = {
        PurePosixPath(path.relative_to(root).as_posix())
        for path in normalized_root.rglob("*.tsv")
        if path.name != "visual_artifact_inventory.tsv"
        and path.is_file()
        and not path.is_symlink()
    }
    contracts_root = root / PUBLIC_CONTRACTS_PACKET_PATH
    if contracts_root.is_symlink() or not contracts_root.is_dir():
        raise ValueError("Cross-platform observed_contracts directory is missing")
    paths.update(
        PurePosixPath(path.relative_to(root).as_posix())
        for path in contracts_root.rglob("*.tsv")
        if path.is_file() and not path.is_symlink()
    )
    for name in CROSS_PLATFORM_SCIENTIFIC_TOP_LEVEL:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Cross-platform scientific evidence is missing: {name}")
        paths.add(PurePosixPath(name))
    if not paths:
        raise ValueError("Cross-platform scientific evidence inventory is empty")
    return paths


def public_visual_paths(root: Path) -> set[PurePosixPath]:
    normalized_root = root / "observed_normalized"
    paths = {
        PurePosixPath(path.relative_to(root).as_posix())
        for path in normalized_root.rglob("visual_artifact_inventory.tsv")
        if path.is_file() and not path.is_symlink()
    }
    if not paths:
        raise ValueError("Cross-platform visual-inventory evidence is empty")
    return paths


def parse_visual_inventory(path: Path) -> list[dict[str, str]]:
    rows = read_tsv_rows(
        path,
        (
            "relative_path",
            "artifact_type",
            "bytes",
            "sha256",
            "width_px",
            "height_px",
            "integrity_status",
        ),
        path.name,
    )
    if not rows:
        raise ValueError(f"Cross-platform visual inventory is empty: {path}")
    seen: set[PurePosixPath] = set()
    for row in rows:
        raw_relative = row["relative_path"]
        if any(character in raw_relative for character in ("\x00", "\t", "\n", "\r")):
            raise ValueError(f"Visual artifact path contains a control character: {path}")
        relative = safe_posix_relative_path(raw_relative, "visual artifact path")
        if len(relative.parts) != 2 or relative in seen:
            raise ValueError(
                f"Visual artifact path is nested or duplicated in {path}: {raw_relative!r}"
            )
        seen.add(relative)
        expected_type = {
            ("report", ".html"): "html",
            ("figures", ".png"): "png",
        }.get((relative.parts[0], relative.suffix.lower()))
        if expected_type is None or row["artifact_type"] != expected_type:
            raise ValueError(
                f"Visual artifact type/path mismatch in {path}: {raw_relative!r}"
            )
        if row["integrity_status"] != "ok":
            raise ValueError(f"Visual artifact is not marked ok in {path}: {raw_relative}")
        if re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None:
            raise ValueError(f"Invalid visual artifact SHA-256 in {path}: {raw_relative}")
        try:
            size = int(row["bytes"])
        except ValueError as error:
            raise ValueError(
                f"Invalid visual artifact byte count in {path}: {raw_relative}"
            ) from error
        if size <= 0 or str(size) != row["bytes"]:
            raise ValueError(f"Noncanonical visual artifact byte count in {path}")
        if expected_type == "html":
            if row["width_px"] or row["height_px"]:
                raise ValueError(f"HTML visual artifact declares dimensions in {path}")
        else:
            try:
                width = int(row["width_px"])
                height = int(row["height_px"])
            except ValueError as error:
                raise ValueError(
                    f"Invalid PNG dimensions in {path}: {raw_relative}"
                ) from error
            if (
                width <= 0
                or height <= 0
                or str(width) != row["width_px"]
                or str(height) != row["height_px"]
            ):
                raise ValueError(f"Noncanonical PNG dimensions in {path}: {raw_relative}")
    return rows


def visual_inventory_structure(path: Path) -> list[tuple[str, ...]]:
    rows = parse_visual_inventory(path)
    structure = sorted(
        tuple(row[field] for field in CROSS_PLATFORM_VISUAL_FIELDS) for row in rows
    )
    return structure


def bind_visual_inventory(inventory_path: Path, case_root: Path) -> list[tuple[str, ...]]:
    """Bind one visual inventory to actual HTML/PNG bytes and decoded dimensions."""

    if case_root.is_symlink() or not case_root.is_dir():
        raise ValueError(f"Visual artifact case root is missing: {case_root}")
    rows = parse_visual_inventory(inventory_path)
    expected_paths: set[PurePosixPath] = set()
    for row in rows:
        relative = safe_posix_relative_path(row["relative_path"], "visual artifact path")
        expected_paths.add(relative)
        artifact = case_root / Path(*relative.parts)
        validate_regular_file(
            artifact,
            source_root=case_root,
            label=f"Visual artifact {relative}",
        )
        if artifact.stat().st_size != int(row["bytes"]):
            raise ValueError(
                f"Visual artifact byte count does not match inventory: {relative}"
            )
        if sha256(artifact) != row["sha256"]:
            raise ValueError(f"Visual artifact SHA-256 does not match inventory: {relative}")
        if row["artifact_type"] == "html":
            try:
                normalized = artifact.read_text(encoding="utf-8").lower()
            except UnicodeDecodeError as error:
                raise ValueError(f"Visual HTML is not UTF-8: {relative}") from error
            if not all(token in normalized for token in ("<html", "<body", "</html>")):
                raise ValueError(f"Visual HTML structure is invalid: {relative}")
        else:
            width, height, _ = decoded_png_rgba(artifact)
            if width != int(row["width_px"]) or height != int(row["height_px"]):
                raise ValueError(
                    f"Visual PNG dimensions do not match inventory: {relative}"
                )

    actual_paths: set[PurePosixPath] = set()
    for directory, suffix in (("report", ".html"), ("figures", ".png")):
        root = case_root / directory
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"Visual artifact directory is missing: {root}")
        for artifact in root.iterdir():
            if artifact.is_symlink() or not artifact.is_file():
                raise ValueError(f"Visual artifact collection contains a non-regular entry")
            if artifact.suffix.lower() != suffix:
                raise ValueError(f"Unsupported or unbound visual artifact: {artifact}")
            actual_paths.add(PurePosixPath(directory, artifact.name))
    if actual_paths != expected_paths:
        raise ValueError(
            "Visual artifact inventory coverage mismatch: "
            f"missing={sorted(map(str, actual_paths - expected_paths))}; "
            f"stale={sorted(map(str, expected_paths - actual_paths))}"
        )
    return visual_inventory_structure(inventory_path)


def visual_inventory_case_id(root: Path, path: Path) -> str:
    relative = PurePosixPath(path.relative_to(root).as_posix())
    if relative.parts[:1] != ("observed_normalized",) or len(relative.parts) != 3:
        raise ValueError(f"Unexpected visual inventory path: {relative}")
    if relative.name != "visual_artifact_inventory.tsv":
        raise ValueError(f"Unexpected visual inventory filename: {relative}")
    case_id = relative.parts[1]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", case_id):
        raise ValueError(f"Unsafe visual inventory case ID: {case_id!r}")
    return case_id


def bind_visual_collection(inventory_root: Path, outputs_root: Path) -> set[str]:
    """Require one exact report-artifact case directory per visual inventory."""

    inventories = public_visual_paths(inventory_root)
    expected_cases: set[str] = set()
    for relative in inventories:
        inventory = inventory_root / Path(*relative.parts)
        case_id = visual_inventory_case_id(inventory_root, inventory)
        if case_id in expected_cases:
            raise ValueError(f"Duplicate visual inventory case ID: {case_id}")
        expected_cases.add(case_id)
        bind_visual_inventory(inventory, outputs_root / case_id)
    if outputs_root.is_symlink() or not outputs_root.is_dir():
        raise ValueError(f"Report artifact outputs directory is missing: {outputs_root}")
    observed_cases: set[str] = set()
    for entry in outputs_root.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            raise ValueError("Report artifact collection contains a non-directory entry")
        observed_cases.add(entry.name)
    if observed_cases != expected_cases:
        raise ValueError(
            "Report artifact case inventory mismatch: "
            f"missing={sorted(expected_cases - observed_cases)}; "
            f"unexpected={sorted(observed_cases - expected_cases)}"
        )
    return expected_cases


def stage_macos_visual_artifacts(public_root: Path, destination: Path) -> None:
    """Copy only inventory-bound macOS HTML/PNG artifacts into the packet."""

    inventories = sorted(public_visual_paths(public_root), key=lambda item: item.as_posix())
    for relative in inventories:
        inventory = public_root / Path(*relative.parts)
        case_id = visual_inventory_case_id(public_root, inventory)
        source_case = public_root / "outputs" / case_id
        bind_visual_inventory(inventory, source_case)
        rows = parse_visual_inventory(inventory)
        for row in rows:
            artifact_relative = safe_posix_relative_path(
                row["relative_path"], "visual artifact path"
            )
            source = source_case / Path(*artifact_relative.parts)
            target = destination / case_id / Path(*artifact_relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_regular_file(source, target, source_root=source_case)
    bind_visual_collection(public_root, destination)


def validate_downloaded_public_artifact_identity(
    artifact_root: Path,
    expected_commit: str,
    expected_run_id: int,
) -> dict[str, str]:
    parse_public_artifact_manifest(artifact_root)
    identity_path = artifact_root / "environment/identity.txt"
    identity: dict[str, str] = {}
    for line in identity_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key or key in identity:
            raise ValueError("Public-validation artifact identity is malformed")
        identity[key] = value
    expected = {
        "git_commit": expected_commit,
        "runner_os": "Linux",
        "runner_arch": "X64",
        "github_run_id": str(expected_run_id),
    }
    for field, value in expected.items():
        if identity.get(field) != value:
            raise ValueError(
                f"Public-validation artifact identity mismatch for {field}: "
                f"{identity.get(field)!r} != {value!r}"
            )
    return identity


def _resolved_within(path: Path, root: Path, label: str) -> Path:
    try:
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"Unable to resolve {label}: {path}") from error
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"{label} resolves outside its declared source root: {path}")
    return resolved


def validate_regular_file(
    path: Path,
    *,
    source_root: Path,
    label: str = "Packet source file",
) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ValueError(f"{label} is missing or unreadable: {path}") from error
    if stat.S_ISLNK(mode):
        raise ValueError(f"{label} is a symlink: {path}")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{label} is not a regular file: {path}")
    _resolved_within(path, source_root, label)


def validate_regular_tree(
    source: Path,
    *,
    require_files: bool = True,
    label: str = "Packet source tree",
) -> list[Path]:
    try:
        source_mode = source.lstat().st_mode
    except OSError as error:
        raise ValueError(f"{label} is missing or unreadable: {source}") from error
    if stat.S_ISLNK(source_mode):
        raise ValueError(f"{label} root is a symlink: {source}")
    if not stat.S_ISDIR(source_mode):
        raise ValueError(f"{label} root is not a regular directory: {source}")

    resolved_root = _resolved_within(source, source, label)
    files: list[Path] = []
    stack = [source]
    while stack:
        directory = stack.pop()
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            try:
                mode = entry.lstat().st_mode
            except OSError as error:
                raise ValueError(f"{label} entry is unreadable: {entry}") from error
            if stat.S_ISLNK(mode):
                raise ValueError(f"{label} contains a symlink: {entry}")
            if stat.S_ISDIR(mode):
                _resolved_within(entry, resolved_root, f"{label} directory")
                stack.append(entry)
                continue
            if stat.S_ISREG(mode):
                _resolved_within(entry, resolved_root, f"{label} file")
                files.append(entry)
                continue
            raise ValueError(f"{label} contains a special file: {entry}")
    if require_files and not files:
        raise ValueError(f"{label} contains no evidence files: {source}")
    return sorted(files)


def copy_regular_file(source: Path, destination: Path, *, source_root: Path) -> None:
    validate_regular_file(source, source_root=source_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Packet destination already exists: {destination}")
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("No-follow packet copying requires os.O_NOFOLLOW")

    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise ValueError(f"Packet source changed during copy: {source}")
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            stat.S_IMODE(source_stat.st_mode),
        )
        try:
            with os.fdopen(source_fd, "rb", closefd=False) as source_handle:
                with os.fdopen(destination_fd, "wb", closefd=False) as destination_handle:
                    shutil.copyfileobj(source_handle, destination_handle)
        finally:
            os.close(destination_fd)
    finally:
        os.close(source_fd)
    os.utime(
        destination,
        ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns),
        follow_symlinks=False,
    )


def copy_tree(source: Path, destination: Path) -> None:
    files = validate_regular_tree(source)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Packet destination already exists: {destination}")
    destination.mkdir(parents=True)
    for entry in sorted(source.rglob("*")):
        relative = entry.relative_to(source)
        mode = entry.lstat().st_mode
        if stat.S_ISDIR(mode):
            (destination / relative).mkdir()
        elif stat.S_ISREG(mode):
            copy_regular_file(entry, destination / relative, source_root=source)
        else:
            raise ValueError(f"Packet source changed during copy: {entry}")
    if not files:
        raise ValueError(f"Required directory contains no evidence files: {source}")


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
        "final_push_github_actions_run_id",
        "pull_request_number",
        "pull_request_github_actions_run_id",
        "public_validation_github_actions_run_id",
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
        "README.md": repo_root / "README.md",
        "CHANGELOG.md": repo_root / "CHANGELOG.md",
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

    readme_text = metadata_paths["README.md"].read_text(encoding="utf-8")
    readme_matches = re.findall(
        r"(?m)^Version `([^`]+)` defines the workflow/resource release described here\.",
        readme_text,
    )
    if len(readme_matches) != 1:
        raise ValueError("README.md must contain one canonical release-version sentence")

    changelog_text = metadata_paths["CHANGELOG.md"].read_text(encoding="utf-8")
    changelog_match = re.search(r"(?m)^## v([^\s]+)(?:\s.*)?$", changelog_text)
    if changelog_match is None:
        raise ValueError("CHANGELOG.md does not contain a version heading")

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
        "README.md": readme_matches[0],
        "CHANGELOG.md": changelog_match.group(1),
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
        "README.md": readme_matches[0],
        "CHANGELOG.md": changelog_match.group(1),
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
        "README.md": {"version": readme_matches[0]},
        "CHANGELOG.md": {"version": changelog_match.group(1)},
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
        "README.md": {"version": canonical["version"]},
        "CHANGELOG.md": {"version": canonical["version"]},
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
        canonical_name = f"{path.name.removesuffix('.tar.gz')}/PKG-INFO"
        with tarfile.open(path, "r:gz") as archive:
            members = sorted(
                (
                    member
                    for member in archive.getmembers()
                    if member.name == canonical_name
                ),
                key=lambda member: member.name,
            )
            if len(members) != 1:
                raise ValueError(
                    "Source archive must contain exactly one canonical root "
                    f"PKG-INFO file: {path}"
                )
            if not members[0].isfile():
                raise ValueError(
                    f"Canonical root PKG-INFO must be a regular file: {path}"
                )
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
) -> list[dict[str, object]]:
    if dist_root.is_symlink() or not dist_root.is_dir():
        raise FileNotFoundError(f"Required distribution directory not found: {dist_root}")
    entries = sorted(dist_root.iterdir(), key=lambda path: path.name)
    actual_names = {path.name for path in entries}
    expected_names = set(EXPECTED_DISTRIBUTIONS)
    if actual_names != expected_names or len(entries) != len(expected_names):
        raise ValueError(
            "Distribution inventory does not match the two canonical release artifacts; "
            f"missing={sorted(expected_names - actual_names)!r}; "
            f"unexpected={sorted(actual_names - expected_names)!r}"
        )
    files = [dist_root / name for name in sorted(EXPECTED_DISTRIBUTIONS)]
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Distribution artifact must be a regular file: {path}")

    artifacts: list[dict[str, object]] = []
    for path in files:
        if path.stat().st_size == 0:
            raise ValueError(f"Distribution artifact is empty: {path}")
        kind, name, version = inspect_distribution(path)
        if kind != EXPECTED_DISTRIBUTIONS[path.name]:
            raise ValueError(f"Distribution kind mismatch in {path}: {kind!r}")
        if normalize_project_name(name) != normalize_project_name(expected_name):
            raise ValueError(f"Distribution name mismatch in {path}: {name!r}")
        if version != expected_version:
            raise ValueError(
                f"Distribution version mismatch in {path}: {version!r} != {expected_version!r}"
            )
        artifacts.append(
            {
                "path": f"dist/{path.relative_to(dist_root).as_posix()}",
                "kind": kind,
                "name": name,
                "version": version,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return artifacts


def validate_fresh_clone_distribution_inventory(
    value: object,
    actual_artifacts: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Bind fresh-clone PEP 610 installation evidence to exact dist bytes."""

    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError("Fresh-clone distribution inventory is malformed")
    expected_fields = {
        "path",
        "kind",
        "name",
        "version",
        "bytes",
        "sha256",
        "direct_url_archive_sha256",
    }
    expected_by_path = {str(row["path"]): row for row in actual_artifacts}
    observed_by_path: dict[str, dict[str, object]] = {}
    for row in value:
        if set(row) != expected_fields:
            raise ValueError("Fresh-clone distribution inventory fields do not match schema")
        path = row.get("path")
        if not isinstance(path, str) or path in observed_by_path:
            raise ValueError("Fresh-clone distribution path is missing or duplicated")
        observed_by_path[path] = row
    if set(observed_by_path) != set(expected_by_path):
        raise ValueError("Fresh-clone distribution path inventory does not match dist bytes")
    for path, actual in expected_by_path.items():
        observed = observed_by_path[path]
        for field, expected in actual.items():
            if observed.get(field) != expected:
                raise ValueError(
                    f"Fresh-clone distribution evidence mismatch for {path} field {field}"
                )
        if observed.get("direct_url_archive_sha256") != actual["sha256"]:
            raise ValueError(
                f"Fresh-clone PEP 610 archive hash does not bind installed bytes: {path}"
            )
    return [dict(observed_by_path[str(row["path"])]) for row in actual_artifacts]


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


def validate_gm11906_source_metadata(
    repo_root: Path,
    public_root: Path,
) -> dict[str, object]:
    """Validate the tracked official NCBI snapshot and its execution copy."""

    repository_path = repo_root / GM11906_SOURCE_METADATA_REPOSITORY_PATH
    output_path = public_root / str(
        PUBLIC_PROVENANCE_FILES["shortread_source_metadata"]["source"]
    )
    for path, label in (
        (repository_path, "tracked GM11906 NCBI metadata resource"),
        (output_path, "GM11906 NCBI metadata execution copy"),
    ):
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"Required {label} not found: {path}")
        if sha256(path) != GM11906_SOURCE_METADATA_SHA256:
            raise ValueError(f"{label} SHA-256 mismatch")

    payload = load_json_object(repository_path, "GM11906 NCBI metadata resource")
    records = payload.get("records")
    if (
        payload.get("schema_version") != "1.0"
        or payload.get("resource_id")
        != "gm11906_ncbi_public_source_metadata_v1"
        or payload.get("authority") != "NCBI GEO and NCBI SRA"
        or not isinstance(records, list)
    ):
        raise ValueError("GM11906 NCBI metadata resource identity is invalid")
    canonical_records = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    records_sha256 = hashlib.sha256(canonical_records).hexdigest()
    if records_sha256 != payload.get("records_sha256"):
        raise ValueError("GM11906 NCBI metadata records SHA-256 mismatch")
    try:
        retrieved = datetime.fromisoformat(
            str(payload["retrieval_completed_utc"]).replace("Z", "+00:00")
        )
    except (KeyError, ValueError) as error:
        raise ValueError("GM11906 NCBI metadata retrieval timestamp is invalid") from error
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise ValueError("GM11906 NCBI metadata retrieval timestamp lacks a timezone")

    by_run = {
        str(record.get("run_accession", "")): record
        for record in records
        if isinstance(record, dict)
    }
    expected = {
        "SRR10804585": ("SRX7478441", "SRS5922054", "SAMN13699362", "GSM4238454"),
        "SRR10804590": ("SRX7478446", "SRS5922059", "SAMN13699398", "GSM4238459"),
        "SRR10804657": ("SRX7478513", "SRS5922125", "SAMN13699338", "GSM4238526"),
    }
    if len(by_run) != 3 or set(by_run) != set(expected):
        raise ValueError("GM11906 NCBI metadata run inventory is invalid")
    for run_accession, identifiers in expected.items():
        record = by_run[run_accession]
        observed = (
            record.get("experiment_accession"),
            record.get("sra_sample_accession"),
            record.get("biosample_accession"),
            record.get("geo_accession"),
        )
        if observed != identifiers:
            raise ValueError(
                f"GM11906 NCBI metadata accession linkage mismatch for {run_accession}"
            )
        if (
            record.get("bioproject_accession") != "PRJNA598179"
            or record.get("cell_line") != "GM11906"
            or record.get("organism") != "Homo sapiens"
            or record.get("library_strategy") != "ATAC-seq"
            or record.get("library_layout") != "PAIRED"
            or record.get("instrument_model") != "NextSeq 550"
        ):
            raise ValueError(
                f"GM11906 NCBI metadata captured-value mismatch for {run_accession}"
            )
        source_files = record.get("source_files")
        if not isinstance(source_files, list) or {
            item.get("format") for item in source_files if isinstance(item, dict)
        } != {"NCBI_SRA_EFETCH_XML", "NCBI_GEO_SOFT"}:
            raise ValueError(
                f"GM11906 NCBI metadata source evidence mismatch for {run_accession}"
            )
        for source in source_files:
            if (
                not isinstance(source, dict)
                or not str(source.get("url", "")).startswith("https://")
                or "ncbi.nlm.nih.gov/" not in str(source.get("url", ""))
                or re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256", "")))
                is None
                or not isinstance(source.get("bytes"), int)
                or int(source["bytes"]) <= 0
            ):
                raise ValueError(
                    f"GM11906 NCBI metadata source evidence is invalid for {run_accession}"
                )

    return {
        "path": GM11906_SOURCE_METADATA_PACKET_PATH,
        "sha256": GM11906_SOURCE_METADATA_SHA256,
        "records_sha256": records_sha256,
        "retrieval_completed_utc": payload["retrieval_completed_utc"],
        "authority": payload["authority"],
        "records": records,
        "by_run": by_run,
    }


def validate_public_input_evidence(
    public_root: Path,
    public_sources_path: Path,
    gm11906_metadata: dict[str, object],
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
    gm11906_by_run = gm11906_metadata["by_run"]
    if not isinstance(gm11906_by_run, dict):
        raise ValueError("GM11906 NCBI metadata run mapping is malformed")
    for run_accession, metadata in FROZEN_PUBLIC_SOURCE_METADATA.items():
        inputs = inputs_by_run[run_accession]
        source = source_by_run[run_accession]
        first = inputs[0]
        official = gm11906_by_run.get(run_accession)
        if official is not None:
            if not isinstance(official, dict):
                raise ValueError(
                    f"GM11906 NCBI metadata record is malformed for {run_accession}"
                )
            manifest_expected = {
                "sample_accession": official["biosample_accession"],
                "sample_alias": official["geo_accession"],
                "sample_title": official["sample_title"],
                "source_sample_id": official["cell_line"],
                "library_strategy": official["library_strategy"],
            }
            manifest_mismatches = {
                field: (value, first.get(field, ""))
                for field, value in manifest_expected.items()
                if first.get(field, "") != value
            }
            if manifest_mismatches:
                raise ValueError(
                    f"Public-input manifest is not bound to official NCBI metadata for "
                    f"{run_accession}: {manifest_mismatches!r}"
                )
            study_accession = str(official["bioproject_accession"])
            instrument_model = str(official["instrument_model"])
        else:
            study_accession = metadata["study_accession"]
            instrument_model = metadata["instrument_model"]
        expected = {
            "dataset": metadata["dataset"],
            "run_accession": run_accession,
            "study_accession": study_accession,
            "sample_accession": first["sample_accession"],
            "cell_line": first["source_sample_id"],
            "platform": "ILLUMINA" if first["source_sample_id"] == "GM11906" else "OXFORD_NANOPORE",
            "instrument_model": instrument_model,
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
        if official is not None and source["metadata_recorded_utc"] != str(
            gm11906_metadata["retrieval_completed_utc"]
        ):
            raise ValueError(
                f"public_data_sources.tsv is not bound to the official metadata "
                f"retrieval timestamp for {run_accession}"
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
    module_status_fields = tuple(
        field for field, _ in PUBLIC_ORACLE_MODULE_STATUS_SPECS
    )
    interpretation_status_fields = tuple(
        field for field, _, _ in PUBLIC_ORACLE_INTERPRETATION_SPECS
    )
    fingerprint_fields = FINGERPRINT_FIELDS
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
            for field in fingerprint_fields:
                expected[f"{case_id}.{field}"] = row[field]
            for field in module_status_fields:
                if row[field]:
                    expected[f"{case_id}.module_status.{field}"] = row[field]
            for field in interpretation_status_fields:
                if row[field]:
                    expected[f"{case_id}.interpretation_status.{field}"] = row[field]
            if row["m8344_alt_fraction"]:
                expected[f"{case_id}.m8344_alt_fraction"] = row[
                    "m8344_alt_fraction"
                ]
            if row["m8344_alt_count"]:
                for field in (
                    "m8344_callable_depth",
                    "m8344_alt_count",
                    "m8344_alt_forward",
                    "m8344_alt_reverse",
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
    unexpected = sorted(set(by_id) - set(required))
    if unexpected:
        raise ValueError(
            f"Public-oracle assertion report contains unexpected rows: {unexpected}"
        )
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
    rows = read_tsv_rows(path, FILTER_PROFILE_HEADER, "filter_profile_results.tsv")
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


def feature_annotation_status(path: Path) -> str:
    """Resolve either the successful feature table or an explicit gated status."""

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = tuple(reader.fieldnames or ())
    if len(fieldnames) != len(set(fieldnames)):
        raise ValueError(f"Duplicate feature-annotation column in {path}")
    if fieldnames == ("metric", "value"):
        status = metric_values(path).get("status", "")
        if not status:
            raise ValueError(f"Missing status metric in {path}")
        if status not in FEATURE_ANNOTATION_GATED_STATES:
            raise ValueError(
                f"Invalid explicit feature-annotation status {status!r} in {path}"
            )
        return status
    if fieldnames == FEATURE_ANNOTATION_SUCCESS_COLUMNS:
        return "ok"
    raise ValueError(
        "Feature-annotation output has neither an explicit status table nor "
        f"the successful schema: {path}"
    )


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

        status_specs = tuple(
            (field, filename, "status")
            for field, filename in PUBLIC_ORACLE_MODULE_STATUS_SPECS
        ) + PUBLIC_ORACLE_INTERPRETATION_SPECS
        loaded: dict[str, dict[str, str]] = {}
        for oracle_field, filename, metric in status_specs:
            expected_value = default_oracle[oracle_field]
            if not expected_value:
                continue
            if oracle_field == "feature_annotation_module_status":
                if feature_annotation_status(run1 / filename) != expected_value:
                    raise ValueError(
                        f"Normalized module-state mismatch for {dataset_name} {oracle_field}"
                    )
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


def validate_public_contract_evidence(
    public_root: Path,
    oracle_rows: list[dict[str, str]],
) -> dict[str, int]:
    """Rebind every frozen fingerprint to compact evidence carried in the packet."""

    try:
        from validation_fingerprints_v0_3_0 import (
            compact_summary_contract_fingerprints,
            read_summary_schema_manifest,
        )
    except ModuleNotFoundError:  # Imported as scripts.* by the test suite.
        from scripts.validation_fingerprints_v0_3_0 import (
            compact_summary_contract_fingerprints,
            read_summary_schema_manifest,
        )

    contracts_root = public_root / PUBLIC_CONTRACTS_PACKET_PATH
    if contracts_root.is_symlink() or not contracts_root.is_dir():
        raise ValueError("Public compact-contract evidence is missing or unsafe")
    entries = list(contracts_root.iterdir())
    if any(entry.is_symlink() or not entry.is_dir() for entry in entries):
        raise ValueError("Public compact-contract root contains an unsafe entry")

    oracle = {(row["dataset"], row["profile"]): row for row in oracle_rows}
    expected_by_case = {
        case_id: oracle[key]
        for key, case_ids in PUBLIC_ORACLE_CASES.items()
        for case_id in case_ids
    }
    observed_cases = {entry.name for entry in entries}
    expected_cases = set(expected_by_case)
    if observed_cases != expected_cases:
        raise ValueError(
            "Public compact-contract case inventory mismatch: "
            f"missing={sorted(expected_cases - observed_cases)}; "
            f"unexpected={sorted(observed_cases - expected_cases)}"
        )

    for case_id, oracle_row in expected_by_case.items():
        contract_dir = contracts_root / case_id
        observed = compact_summary_contract_fingerprints(contract_dir)
        expected = {field: oracle_row[field] for field in FINGERPRINT_FIELDS}
        if observed != expected:
            mismatches = {
                field: {"expected": expected[field], "observed": observed[field]}
                for field in FINGERPRINT_FIELDS
                if observed[field] != expected[field]
            }
            raise ValueError(
                f"Public compact-contract fingerprint mismatch for {case_id}: "
                f"{mismatches}"
            )
        manifest_rows = read_summary_schema_manifest(
            contract_dir / SUMMARY_SCHEMA_MANIFEST_NAME
        )
        if len(manifest_rows) != int(oracle_row["summary_tsv_count"]):
            raise ValueError(
                f"Public compact-contract summary count mismatch for {case_id}"
            )
    return {"contract_case_count": len(expected_cases)}


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
    contract_summary = validate_public_contract_evidence(public_root, oracle_rows)
    validate_module_status_evidence(
        validation_root / "module_status_matrix.tsv",
        public_root / "observed_normalized",
    )
    return {
        "oracle_sha256": FROZEN_ORACLE_SHA256,
        **assertion_summary,
        **contract_summary,
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


def load_json_array(path: Path, label: str) -> list[object]:
    if not path.is_file():
        raise FileNotFoundError(f"Required {label} not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to parse {label}: {path}") from error
    if not isinstance(value, list):
        raise ValueError(f"{label} must contain a JSON array: {path}")
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


def validate_digest_record(
    value: object,
    label: str,
    *,
    expected_fields: frozenset[str] | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Public provenance {label} must be an object")
    if expected_fields is not None and set(value) != expected_fields:
        raise ValueError(
            f"Public provenance {label} has an invalid digest field inventory; "
            f"expected {sorted(expected_fields)}"
        )
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
    if "md5" in value and (
        not isinstance(md5, str) or re.fullmatch(r"[0-9a-f]{32}", md5) is None
    ):
        raise ValueError(f"Public provenance {label} has an invalid MD5")
    return value


def index_unique_labeled_records(
    value: object,
    label: str,
) -> dict[str, dict[str, object]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"Public {label} inputs are missing")
    indexed: dict[str, dict[str, object]] = {}
    for index, record in enumerate(value):
        validated = validate_digest_record(
            record,
            f"{label} input {index}",
            expected_fields=frozenset({"label", "name", "bytes", "md5", "sha256"}),
        )
        record_label = validated.get("label")
        if not isinstance(record_label, str) or not record_label:
            raise ValueError(f"Public {label} alignment input label is invalid")
        if record_label in indexed:
            raise ValueError(
                f"Public {label} alignment contains duplicate input label: {record_label}"
            )
        indexed[record_label] = validated
    return indexed


def _require_record_content(record: dict[str, object], path: Path, label: str) -> None:
    if (
        record["bytes"] != path.stat().st_size
        or record["sha256"] != sha256(path)
        or record.get("md5") != md5_identity(path)
    ):
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
    gm11906_metadata: dict[str, object],
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
        "metadata_snapshot_sha256",
        "metadata_record_sha256",
    )
    gm11906_by_run = gm11906_metadata["by_run"]
    if not isinstance(gm11906_by_run, dict):
        raise ValueError("GM11906 NCBI metadata run mapping is malformed")
    expected_source_rows = []
    for run_accession in ("SRR10804585", "SRR10804590", "SRR10804657"):
        record = gm11906_by_run[run_accession]
        if not isinstance(record, dict):
            raise ValueError(
                f"GM11906 NCBI metadata record is malformed for {run_accession}"
            )
        record_sha256 = hashlib.sha256(
            json.dumps(
                record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("ascii")
        ).hexdigest()
        expected_source_rows.append(
            (
                run_accession,
                record["geo_accession"],
                record["cell_line"],
                record["library_strategy"],
                "single_cell_library",
                "pooled_pseudobulk",
                GM11906_SOURCE_METADATA_SHA256,
                record_sha256,
            )
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
                row["metadata_snapshot_sha256"],
                row["metadata_record_sha256"],
            )
            for row in source_rows
        ]
        != expected_source_rows
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
            "short-read",
        ),
        (
            long,
            "GM12878_SRR18110025_ONT_reduced_qn1000",
            "long-read",
        ),
    )
    for manifest, dataset_id, label in alignment_expectations:
        if manifest.get("schema_version") != "1.0" or manifest.get("provenance_type") != "public_alignment":
            raise ValueError(f"Public {label} alignment provenance identity is invalid")
        if manifest.get("dataset_id") != dataset_id:
            raise ValueError(f"Public {label} alignment dataset identity is invalid")
        for field in ("alignment", "alignment_index", "reference", "reference_index"):
            validate_digest_record(manifest.get(field), f"{label} {field}")
        if manifest.get("derivation") != PUBLIC_ALIGNMENT_DERIVATIONS[dataset_id]:
            raise ValueError(f"Public {label} alignment derivation is invalid")
        index_unique_labeled_records(manifest.get("public_inputs"), label)

    input_by_filename = {row["filename"]: row for row in public_input_rows}
    short_inputs = index_unique_labeled_records(
        short.get("public_inputs"), "short-read"
    )
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
    complete_digest_fields = frozenset({"name", "bytes", "md5", "sha256"})
    source_fastq = validate_digest_record(
        subset.get("source_fastq"),
        "subset source FASTQ",
        expected_fields=complete_digest_fields,
    )
    subset_fastq = validate_digest_record(
        subset.get("subset_fastq"),
        "subset FASTQ",
        expected_fields=complete_digest_fields,
    )
    selected_names = validate_digest_record(
        subset.get("selected_query_names"),
        "selected query names",
        expected_fields=complete_digest_fields,
    )
    if subset_fastq != FROZEN_GM12878_SUBSET_FASTQ_RECORD:
        raise ValueError("Public long-read subset FASTQ identity is not frozen")
    if selected_names != FROZEN_GM12878_SELECTED_QUERY_NAMES_RECORD:
        raise ValueError("Public long-read selected-query-name identity is not frozen")
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
    if selection != FROZEN_GM12878_SUBSET_SELECTION:
        raise ValueError("Public long-read subset selection metadata is not frozen")
    selected_count = FROZEN_GM12878_SUBSET_SELECTION["selected_query_names"]
    if len(query_names) != selected_count:
        raise ValueError("Public long-read selected-query-name ledger count is invalid")

    long_inputs = index_unique_labeled_records(
        long.get("public_inputs"), "long-read"
    )
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
    if (
        long_inputs["deterministic_subset_manifest"]["name"]
        != "SRR18110025.deterministic-qnames-1000.fastq.gz.provenance.json"
    ):
        raise ValueError("Public long-read subset-manifest identity is invalid")
    derivation_parameters = long["derivation"]["parameters"]
    if (
        derivation_parameters["selected_query_names"] != str(selected_count)
        or derivation_parameters["selection_seed"] != selection["seed"]
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


def parse_github_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} is not a valid ISO-8601 timestamp: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def validate_acceptance_inventory(validation_root: Path) -> None:
    acceptance_root = validation_root / "acceptance"
    if acceptance_root.is_symlink() or not acceptance_root.is_dir():
        raise ValueError("Acceptance evidence must be a regular directory")
    evidence_paths = list(acceptance_root.rglob("*"))
    if any(
        path.is_symlink() or (not path.is_file() and not path.is_dir())
        for path in evidence_paths
    ):
        raise ValueError("Acceptance evidence contains a symlink or non-regular entry")
    observed = {
        path.name
        for path in acceptance_root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    missing = REQUIRED_ACCEPTANCE_FILES - observed
    if missing:
        raise ValueError(
            "Required acceptance evidence is missing: " + ", ".join(sorted(missing))
        )
    observed_directories = {
        path.name
        for path in acceptance_root.iterdir()
        if path.is_dir() and not path.is_symlink()
    }
    missing_directories = REQUIRED_ACCEPTANCE_DIRECTORIES - observed_directories
    if missing_directories:
        raise ValueError(
            "Required acceptance evidence directories are missing: "
            + ", ".join(sorted(missing_directories))
        )
    for relative in sorted(REQUIRED_ACCEPTANCE_FILES):
        require_nonempty_evidence(validation_root, f"acceptance/{relative}")
    for relative in sorted(REQUIRED_PUBLIC_VALIDATION_ACCEPTANCE_FILES):
        require_nonempty_evidence(validation_root, f"acceptance/{relative}")


def validate_release_environment_verification(
    validation_root: Path, repo_root: Path
) -> dict[str, object]:
    record = load_json_object(
        validation_root / "acceptance/release_environment_verification.json",
        "Release environment verification",
    )
    expected_fields = {
        "schema_version",
        "platform_id",
        "python",
        "artifact_count",
        "tracked_artifact_lock",
        "tracked_artifact_lock_sha256",
        "runtime_artifact_set_sha256",
        "repository_commit",
        "repository_tree",
        "repository_clean",
        "verified",
    }
    if set(record) != expected_fields:
        raise ValueError("Release environment verification schema mismatch")
    platform_id = record.get("platform_id")
    if platform_id not in RESOLVED_CI_PLATFORMS:
        raise ValueError("Release environment verification platform is unsupported")
    lock_name = f"environment-{platform_id}.explicit.txt"
    lock_path = repo_root / "locks" / lock_name
    if (
        record.get("schema_version") != "1.0"
        or record.get("python") != EXPECTED_PYTHON_VERSION
        or record.get("verified") is not True
        or record.get("tracked_artifact_lock") != lock_name
        or record.get("tracked_artifact_lock_sha256") != sha256(lock_path)
        or record.get("repository_commit") != git_output(repo_root, "rev-parse", "HEAD")
        or record.get("repository_tree")
        != git_output(repo_root, "rev-parse", "HEAD^{tree}")
        or record.get("repository_clean") is not True
        or not isinstance(record.get("artifact_count"), int)
        or record["artifact_count"] <= 0
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(record.get("runtime_artifact_set_sha256", ""))
        )
    ):
        raise ValueError("Release environment verification identity mismatch")
    return record


def validate_repository_object(
    value: object,
    repository_slug: str,
    label: str,
) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} repository metadata is not an object")
    expected_html = f"https://github.com/{repository_slug}"
    expected_api = f"https://api.github.com/repos/{repository_slug}"
    if value.get("full_name") != repository_slug:
        raise ValueError(f"{label} repository full_name mismatch")
    if value.get("html_url") != expected_html or value.get("url") != expected_api:
        raise ValueError(f"{label} repository URLs are not canonical")


def validate_pull_request_evidence(
    validation_root: Path,
    repo_root: Path,
    expected_commit: str,
    repository: str,
) -> dict[str, object]:
    relative = "acceptance/pull_request.json"
    pull_request = load_json_object(
        validation_root / relative,
        "pull-request metadata evidence",
    )
    repository_slug = github_repository_slug(repository)
    repository_api = f"https://api.github.com/repos/{repository_slug}"
    pull_number = positive_json_integer(
        pull_request.get("number"),
        "pull request number",
    )
    canonical_urls = {
        "url": f"{repository_api}/pulls/{pull_number}",
        "html_url": f"https://github.com/{repository_slug}/pull/{pull_number}",
        "issue_url": f"{repository_api}/issues/{pull_number}",
        "comments_url": f"{repository_api}/issues/{pull_number}/comments",
    }
    for field, expected in canonical_urls.items():
        if pull_request.get(field) != expected:
            raise ValueError(
                f"Pull-request canonical URL mismatch for {field}: "
                f"{pull_request.get(field)!r} != {expected!r}"
            )
    if pull_request.get("state") != "closed" or pull_request.get("merged") is not True:
        raise ValueError("Pull-request metadata does not record a merged, closed PR")
    parse_github_timestamp(pull_request.get("merged_at"), "Pull-request merged_at")
    if pull_request.get("merge_commit_sha") != expected_commit:
        raise ValueError(
            "Pull-request merge_commit_sha does not match the final release commit"
        )

    base = pull_request.get("base")
    head = pull_request.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict):
        raise ValueError("Pull-request base/head metadata is malformed")
    if base.get("ref") != EXPECTED_GITHUB_BRANCH:
        raise ValueError(
            f"Pull-request base branch mismatch: {base.get('ref')!r} "
            f"!= {EXPECTED_GITHUB_BRANCH!r}"
        )
    head_ref = head.get("ref")
    if not isinstance(head_ref, str) or not head_ref.strip():
        raise ValueError("Pull-request head branch is missing")
    validate_repository_object(base.get("repo"), repository_slug, "Pull-request base")
    validate_repository_object(head.get("repo"), repository_slug, "Pull-request head")
    base_sha = base.get("sha")
    head_sha = head.get("sha")
    for label, value in (("base", base_sha), ("head", head_sha)):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise ValueError(f"Pull-request {label} SHA is not a full Git commit")

    parent_line = git_output(repo_root, "rev-list", "--parents", "-n", "1", expected_commit)
    parent_fields = parent_line.split()
    if len(parent_fields) != 3 or parent_fields[0] != expected_commit:
        raise ValueError("Final release commit is not a two-parent merge commit")
    base_parent, head_parent = parent_fields[1:]
    if base_sha != base_parent or head_sha != head_parent:
        raise ValueError(
            "Final merge parent relationship does not match pull-request base/head metadata"
        )
    final_tree = git_output(repo_root, "rev-parse", f"{expected_commit}^{{tree}}")
    reviewed_head_tree = git_output(repo_root, "rev-parse", f"{head_sha}^{{tree}}")
    if final_tree != reviewed_head_tree:
        raise ValueError(
            "Reviewed pull-request head tree does not equal the final release tree"
        )

    return {
        "number": pull_number,
        "repository": repository_slug,
        "url": canonical_urls["html_url"],
        "api_url": canonical_urls["url"],
        "issue_api_url": canonical_urls["issue_url"],
        "comments_api_url": canonical_urls["comments_url"],
        "state": "closed",
        "merged": True,
        "merged_at": pull_request["merged_at"],
        "merge_commit_sha": expected_commit,
        "base_ref": EXPECTED_GITHUB_BRANCH,
        "base_sha": base_sha,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "final_commit_parents": [base_parent, head_parent],
        "final_tree_sha": final_tree,
        "reviewed_head_tree_sha": reviewed_head_tree,
    }


def validate_pull_request_github_actions_evidence(
    validation_root: Path,
    pull_request: dict[str, object],
    repository: str,
) -> tuple[dict[str, str], dict[str, object]]:
    run_relative = "acceptance/pull_request_github_actions_run.json"
    jobs_relative = "acceptance/pull_request_github_actions_jobs.json"
    run = load_json_object(
        validation_root / run_relative,
        "pull-request GitHub Actions run evidence",
    )
    jobs_payload = load_json_object(
        validation_root / jobs_relative,
        "pull-request GitHub Actions jobs evidence",
    )
    repository_slug = github_repository_slug(repository)
    repository_api = f"https://api.github.com/repos/{repository_slug}"
    pull_number = int(pull_request["number"])
    head_sha = str(pull_request["head_sha"])
    head_ref = str(pull_request["head_ref"])
    base_sha = str(pull_request["base_sha"])
    run_id = positive_json_integer(run.get("id"), "pull-request run id")
    run_attempt = positive_json_integer(
        run.get("run_attempt"),
        "pull-request run attempt",
    )
    expected_run_url = f"https://github.com/{repository_slug}/actions/runs/{run_id}"
    expected_run_api = f"{repository_api}/actions/runs/{run_id}"
    expected_run_fields = {
        "name": EXPECTED_GITHUB_WORKFLOW,
        "event": "pull_request",
        "head_branch": head_ref,
        "path": EXPECTED_GITHUB_WORKFLOW_PATH,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": "success",
        "html_url": expected_run_url,
        "url": expected_run_api,
        "jobs_url": f"{expected_run_api}/jobs",
    }
    for field, expected in expected_run_fields.items():
        if run.get(field) != expected:
            raise ValueError(
                f"Pull-request GitHub Actions run mismatch for {field}: "
                f"{run.get(field)!r} != {expected!r}"
            )
    run_repository = run.get("repository")
    head_repository = run.get("head_repository")
    if not isinstance(run_repository, dict) or run_repository.get("full_name") != repository_slug:
        raise ValueError("Pull-request workflow repository identity mismatch")
    if not isinstance(head_repository, dict) or head_repository.get("full_name") != repository_slug:
        raise ValueError("Pull-request workflow head repository identity mismatch")

    associations = run.get("pull_requests")
    if not isinstance(associations, list):
        raise ValueError("Pull-request workflow association inventory is malformed")
    if not associations:
        # GitHub can clear Actions pull_requests associations after merge. The
        # separately validated merged PR and exact run/job identities are the
        # fail-closed evidence path in that post-merge state.
        association_evidence_mode = "merged_pr_independent_identity"
    elif len(associations) == 1:
        association = associations[0]
        if not isinstance(association, dict):
            raise ValueError("Pull-request workflow association is malformed")
        if (
            association.get("number") != pull_number
            or association.get("url") != f"{repository_api}/pulls/{pull_number}"
        ):
            raise ValueError("Pull-request workflow association has the wrong PR identity")
        association_head = association.get("head")
        association_base = association.get("base")
        if not isinstance(association_head, dict) or not isinstance(
            association_base, dict
        ):
            raise ValueError("Pull-request workflow association lacks base/head metadata")
        if (
            association_head.get("ref") != head_ref
            or association_head.get("sha") != head_sha
            or association_base.get("ref") != EXPECTED_GITHUB_BRANCH
            or association_base.get("sha") != base_sha
        ):
            raise ValueError(
                "Pull-request workflow association does not match the reviewed head"
            )
        for label, nested in (("head", association_head), ("base", association_base)):
            nested_repo = nested.get("repo")
            if not isinstance(nested_repo, dict):
                raise ValueError(
                    f"Pull-request workflow {label} repository is malformed"
                )
            if (
                nested_repo.get("name") != repository_slug.split("/", 1)[1]
                or nested_repo.get("url") != repository_api
            ):
                raise ValueError(
                    f"Pull-request workflow {label} repository identity mismatch"
                )
        association_evidence_mode = "actions_pull_requests_canonical"
    else:
        raise ValueError(
            "Pull-request workflow association inventory must be empty or contain "
            "exactly one canonical PR"
        )

    jobs = jobs_payload.get("jobs")
    if not isinstance(jobs, list) or not all(isinstance(job, dict) for job in jobs):
        raise ValueError("Pull-request GitHub Actions jobs evidence is malformed")
    if jobs_payload.get("total_count") != 3 or len(jobs) != 3:
        raise ValueError("Pull-request workflow must contain exactly three pinned jobs")
    expected_names = {item["name"] for item in EXPECTED_GITHUB_JOBS.values()}
    if {str(job.get("name")) for job in jobs} != expected_names:
        raise ValueError("Pull-request workflow job inventory does not match the pinned matrix")
    job_ids = [positive_json_integer(job.get("id"), "pull-request job id") for job in jobs]
    if len(job_ids) != len(set(job_ids)):
        raise ValueError("Pull-request workflow contains duplicate job IDs")

    selected_jobs: list[dict[str, object]] = []
    for expectation in EXPECTED_GITHUB_JOBS.values():
        job = next(job for job in jobs if job.get("name") == expectation["name"])
        job_id = int(job["id"])
        expected_job_url = f"{expected_run_url}/job/{job_id}"
        expected_job_api = f"{repository_api}/actions/jobs/{job_id}"
        labels = job.get("labels")
        if (
            not isinstance(labels, list)
            or expectation["label"] not in labels
            or job.get("head_sha") != head_sha
            or job.get("run_id") != run_id
            or job.get("run_attempt") != run_attempt
            or job.get("workflow_name") != EXPECTED_GITHUB_WORKFLOW
            or job.get("status") != "completed"
            or job.get("conclusion") != "success"
            or job.get("html_url") != expected_job_url
            or job.get("url") != expected_job_api
            or job.get("run_url") != expected_run_api
        ):
            raise ValueError(
                f"Pull-request GitHub Actions job identity mismatch: {expectation['name']}"
            )
        selected_jobs.append(
            {
                "job_id": job_id,
                "name": job["name"],
                "labels": job["labels"],
                "head_sha": job["head_sha"],
                "url": job["html_url"],
            }
        )

    identity = {
        "provider": "github_actions",
        "run_id": run_id,
        "run_attempt": run_attempt,
        "workflow": EXPECTED_GITHUB_WORKFLOW,
        "workflow_path": EXPECTED_GITHUB_WORKFLOW_PATH,
        "event": "pull_request",
        "pull_request_number": pull_number,
        "association_evidence_mode": association_evidence_mode,
        "branch": head_ref,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": "success",
        "url": expected_run_url,
        "jobs": selected_jobs,
    }
    row = {
        "case_id": PR_HEAD_CI_CASE_ID,
        "category": "release_acceptance",
        "input_available": "1",
        "expected_available": "1",
        "verdict": "PASS",
        "detail": (
            f"{run_relative}; {jobs_relative}; run_id={run_id}; "
            f"pull_request={pull_number}; jobs=3; event=pull_request; "
            f"reviewed_commit={head_sha}; "
            f"association_mode={association_evidence_mode}"
        ),
    }
    return row, identity


def parse_read_only_audit_payload(body: str) -> dict[str, object] | None:
    if READ_ONLY_AUDIT_MARKER not in body:
        return None
    if body.count(READ_ONLY_AUDIT_MARKER) != 1:
        raise ValueError("Read-only audit comment contains a duplicate marker")
    _, suffix = body.split(READ_ONLY_AUDIT_MARKER, 1)
    match = re.fullmatch(
        r"\s*```json[ \t]*\r?\n(?P<payload>.*?)\r?\n```[ \t]*\s*",
        suffix,
        flags=re.DOTALL,
    )
    if match is None:
        raise ValueError(
            "Read-only audit marker must be followed by exactly one JSON fenced block"
        )
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError as error:
        raise ValueError("Read-only audit JSON payload is malformed") from error
    required_fields = {
        "schema_version",
        "review_method",
        "audit_instance_id",
        "role",
        "reviewed_commit",
        "reviewed_tree",
        "verdict",
        "unresolved_blockers",
        "summary",
    }
    if not isinstance(payload, dict) or set(payload) != required_fields:
        raise ValueError(
            f"Read-only audit payload fields do not match schema {READ_ONLY_AUDIT_SCHEMA_VERSION}"
        )
    return payload


def validate_read_only_audit_comments(
    validation_root: Path,
    pull_request: dict[str, object],
    repository: str,
) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    relative = "acceptance/pull_request_comments.json"
    comments = load_json_array(
        validation_root / relative,
        "pull-request issue comments evidence",
    )
    repository_slug = github_repository_slug(repository)
    repository_owner = repository_slug.split("/", 1)[0]
    repository_api = f"https://api.github.com/repos/{repository_slug}"
    pull_number = int(pull_request["number"])
    head_sha = str(pull_request["head_sha"])
    final_tree = str(pull_request["final_tree_sha"])
    merged_at = parse_github_timestamp(
        pull_request.get("merged_at"),
        "Pull-request merged_at",
    )
    observed: dict[str, dict[str, object]] = {}
    comment_ids: set[int] = set()
    for value in comments:
        if not isinstance(value, dict):
            raise ValueError("Pull-request comments evidence contains a non-object entry")
        body = value.get("body")
        if not isinstance(body, str) or READ_ONLY_AUDIT_MARKER not in body:
            continue
        comment_id = positive_json_integer(value.get("id"), "issue comment id")
        if comment_id in comment_ids:
            raise ValueError("Pull-request comments evidence contains duplicate comment IDs")
        comment_ids.add(comment_id)
        expected_urls = {
            "url": f"{repository_api}/issues/comments/{comment_id}",
            "html_url": (
                f"https://github.com/{repository_slug}/pull/{pull_number}"
                f"#issuecomment-{comment_id}"
            ),
            "issue_url": f"{repository_api}/issues/{pull_number}",
        }
        for field, expected in expected_urls.items():
            if value.get(field) != expected:
                raise ValueError(
                    f"Pull-request comment canonical URL mismatch for {field}"
                )
        user = value.get("user")
        if (
            not isinstance(user, dict)
            or user.get("login") != repository_owner
            or user.get("html_url") != f"https://github.com/{repository_owner}"
            or value.get("author_association") != "OWNER"
        ):
            raise ValueError(
                "Read-only audit comment was not authenticated as a repository-owner post"
            )
        created_at = parse_github_timestamp(
            value.get("created_at"),
            f"Read-only audit comment {comment_id} created_at",
        )
        updated_at = parse_github_timestamp(
            value.get("updated_at"),
            f"Read-only audit comment {comment_id} updated_at",
        )
        if created_at > updated_at:
            raise ValueError(
                f"Read-only audit comment {comment_id} was updated before it was created"
            )
        if updated_at > merged_at:
            raise ValueError(
                f"Read-only audit comment {comment_id} was posted or edited after merge"
            )
        payload = parse_read_only_audit_payload(body)
        if payload is None:  # Defensive: marker presence above must produce a payload.
            raise ValueError("Read-only audit marker did not produce a payload")
        role = payload.get("role")
        if role not in READ_ONLY_AUDIT_CASE_IDS:
            raise ValueError(f"Unsupported read-only audit role: {role!r}")
        if role in observed:
            raise ValueError(f"Duplicate read-only audit payload for role: {role}")
        if payload.get("schema_version") != READ_ONLY_AUDIT_SCHEMA_VERSION:
            raise ValueError(f"Read-only audit schema mismatch for role: {role}")
        if payload.get("review_method") != READ_ONLY_AUDIT_METHOD:
            raise ValueError(f"Read-only audit method mismatch for role: {role}")
        audit_instance_id = payload.get("audit_instance_id")
        if not isinstance(audit_instance_id, str) or re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            audit_instance_id,
            flags=re.IGNORECASE,
        ) is None:
            raise ValueError(f"Read-only audit instance ID is invalid for role: {role}")
        if payload.get("reviewed_commit") != head_sha:
            raise ValueError(f"Read-only audit reviewed-commit drift for role: {role}")
        if payload.get("reviewed_tree") != final_tree:
            raise ValueError(f"Read-only audit reviewed-tree drift for role: {role}")
        blockers = payload.get("unresolved_blockers")
        if isinstance(blockers, bool) or not isinstance(blockers, int) or blockers != 0:
            raise ValueError(f"Read-only audit has unresolved blockers for role: {role}")
        if payload.get("verdict") != "PASS":
            raise ValueError(f"Read-only audit verdict is not PASS for role: {role}")
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(f"Read-only audit summary is empty for role: {role}")
        observed[str(role)] = {
            **payload,
            "summary": summary.strip(),
            "comment_id": comment_id,
            "comment_url": expected_urls["html_url"],
            "posted_by": repository_owner,
            "author_association": "OWNER",
            "created_at": value["created_at"],
            "updated_at": value["updated_at"],
        }

    missing = sorted(set(READ_ONLY_AUDIT_CASE_IDS) - set(observed))
    if missing:
        raise ValueError(
            "Missing required read-only audit payloads: " + ", ".join(missing)
        )
    instance_ids = {
        str(observed[role]["audit_instance_id"]).lower()
        for role in READ_ONLY_AUDIT_CASE_IDS
    }
    if len(instance_ids) != len(READ_ONLY_AUDIT_CASE_IDS):
        raise ValueError("Read-only audit instance IDs must be unique across roles")
    rows = [
        {
            "case_id": READ_ONLY_AUDIT_CASE_IDS[role],
            "category": "release_acceptance",
            "input_available": "1",
            "expected_available": "1",
            "verdict": "PASS",
            "detail": (
                f"{relative}; method={READ_ONLY_AUDIT_METHOD}; role={role}; "
                f"reviewed_commit={head_sha}; reviewed_tree={final_tree}; "
                f"comment_id={observed[role]['comment_id']}"
            ),
        }
        for role in READ_ONLY_AUDIT_CASE_IDS
    ]
    identities = [observed[role] for role in READ_ONLY_AUDIT_CASE_IDS]
    return rows, identities


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
    for field in ("candidate_commit", "checked_out_commit", "public_main_commit"):
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
        "installed_sdist",
        "separate_distribution_environments",
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

    actual_distributions = validate_distributions(
        validation_root / "dist",
        EXPECTED_PACKAGE_NAME,
        EXPECTED_RELEASE_VERSION.removeprefix("v"),
    )
    validate_fresh_clone_distribution_inventory(
        fresh.get("distributions"), actual_distributions
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


def validate_resolved_ci_environments(
    validation_root: Path,
    repo_root: Path,
    expected_commit: str,
    expected_run_id: int,
) -> list[dict[str, object]]:
    def conda_artifact_urls(
        path: Path, label: str, expected_platform: str
    ) -> set[str]:
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines.count("@EXPLICIT") != 1:
            raise ValueError(f"{label} must contain exactly one @EXPLICIT marker")
        records = [
            line.strip()
            for line in lines
            if line.strip()
            and not line.startswith("#")
            and line.strip() != "@EXPLICIT"
        ]
        if not records:
            raise ValueError(f"{label} contains no Conda artifact URLs")
        if len(records) != len(set(records)):
            raise ValueError(f"{label} contains duplicate Conda artifact URLs")
        for url in records:
            parsed = urlsplit(url)
            path_parts = parsed.path.split("/")
            if (
                parsed.scheme != "https"
                or parsed.hostname != "conda.anaconda.org"
                or parsed.netloc != "conda.anaconda.org"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or not re.fullmatch(r"[0-9a-f]{64}", parsed.fragment)
                or len(path_parts) != 4
                or path_parts[0] != ""
                or path_parts[1] not in {"conda-forge", "bioconda"}
                or path_parts[2] not in {expected_platform, "noarch"}
                or not re.fullmatch(
                    r"[A-Za-z0-9_.+-]+\.(?:conda|tar\.bz2)", path_parts[3]
                )
            ):
                raise ValueError(f"{label} contains an unapproved Conda artifact URL")
        return set(records)

    evidence_root = validation_root / RESOLVED_CI_ENVIRONMENTS_RELATIVE
    validate_regular_tree(evidence_root, label="Resolved CI environment evidence")
    observed_entries = {path.name: path for path in evidence_root.iterdir()}
    if set(observed_entries) != set(RESOLVED_CI_PLATFORMS) or any(
        not path.is_dir() for path in observed_entries.values()
    ):
        raise ValueError(
            "Resolved CI platform inventory mismatch: "
            f"observed={sorted(observed_entries)}"
        )

    identities: list[dict[str, object]] = []
    expected_record_fields = {
        "schema_version",
        "git_commit",
        "github_run_id",
        "job",
        "platform_id",
        "runner_os",
        "runner_arch",
        "machine",
        "python",
        "resolved_environment",
        "evidence_files",
        "evidence_manifest_sha256",
        "source_solver_spec_sha256",
        "source_artifact_lock_sha256",
        "source_release_tools_lock_sha256",
    }
    for platform_id in RESOLVED_CI_PLATFORMS:
        platform_root = evidence_root / platform_id
        evidence_names = {
            f"conda-{platform_id}.explicit.txt",
            f"pip-{platform_id}.txt",
            f"environment-{platform_id}.yml",
            f"artifact-lock-{platform_id}.explicit.txt",
            "requirements-release-tools.txt",
            f"python-{platform_id}.txt",
        }
        record_name = f"platform-{platform_id}.json"
        expected_files = evidence_names | {record_name}
        observed_files = {
            path.name for path in platform_root.iterdir() if path.is_file()
        }
        if observed_files != expected_files or any(
            not path.is_file() for path in platform_root.iterdir()
        ):
            raise ValueError(
                f"Resolved CI environment inventory mismatch for {platform_id}: "
                f"missing={sorted(expected_files - observed_files)}, "
                f"unexpected={sorted(observed_files - expected_files)}"
            )
        record = load_json_object(
            platform_root / record_name,
            f"Resolved CI environment identity for {platform_id}",
        )
        if set(record) != expected_record_fields:
            raise ValueError(
                f"Resolved CI environment identity schema mismatch for {platform_id}"
            )
        expected_identity = {
            "schema_version": PACKET_SCHEMA_VERSION,
            "git_commit": expected_commit,
            "github_run_id": expected_run_id,
            "job": "Unit and synthetic tests",
            "platform_id": platform_id,
            "runner_os": RESOLVED_CI_RUNNER_IDENTITY[platform_id]["runner_os"],
            "runner_arch": RESOLVED_CI_RUNNER_IDENTITY[platform_id]["runner_arch"],
            "machine": PUBLIC_RUNTIME_PLATFORMS[platform_id]["machine"],
            "python": EXPECTED_PYTHON_VERSION,
            "resolved_environment": True,
        }
        for field, expected in expected_identity.items():
            if record.get(field) != expected:
                raise ValueError(
                    f"Resolved CI environment identity mismatch for {platform_id} "
                    f"field {field}: {record.get(field)!r} != {expected!r}"
                )
        python_text = (platform_root / f"python-{platform_id}.txt").read_text(
            encoding="utf-8"
        ).strip()
        if python_text != f"Python {EXPECTED_PYTHON_VERSION}":
            raise ValueError(
                f"Resolved CI Python evidence mismatch for {platform_id}: {python_text!r}"
            )

        evidence_files = record.get("evidence_files")
        if not isinstance(evidence_files, dict) or set(evidence_files) != evidence_names:
            raise ValueError(
                f"Resolved CI evidence-file inventory mismatch for {platform_id}"
            )
        manifest_lines: list[str] = []
        for name in sorted(evidence_names):
            path = platform_root / name
            payload_sha256 = sha256(path)
            payload_size = path.stat().st_size
            item = evidence_files.get(name)
            if (
                not isinstance(item, dict)
                or set(item) != {"sha256", "size_bytes"}
                or item.get("sha256") != payload_sha256
                or item.get("size_bytes") != payload_size
            ):
                raise ValueError(
                    f"Resolved CI evidence-file digest mismatch for {platform_id}/{name}"
                )
            manifest_lines.append(f"{name}\t{payload_sha256}\t{payload_size}\n")
        manifest_sha256 = hashlib.sha256(
            "".join(manifest_lines).encode("utf-8")
        ).hexdigest()
        if record.get("evidence_manifest_sha256") != manifest_sha256:
            raise ValueError(
                f"Resolved CI evidence-manifest digest mismatch for {platform_id}"
            )
        solver_name = f"environment-{platform_id}.yml"
        artifact_name = f"artifact-lock-{platform_id}.explicit.txt"
        tools_name = "requirements-release-tools.txt"
        solver_sha256 = str(evidence_files[solver_name]["sha256"])
        artifact_sha256 = str(evidence_files[artifact_name]["sha256"])
        tools_sha256 = str(evidence_files[tools_name]["sha256"])
        if record.get("source_solver_spec_sha256") != solver_sha256:
            raise ValueError(
                f"Resolved CI solver-spec digest mismatch for {platform_id}"
            )
        if record.get("source_artifact_lock_sha256") != artifact_sha256:
            raise ValueError(
                f"Resolved CI artifact-lock digest mismatch for {platform_id}"
            )
        if record.get("source_release_tools_lock_sha256") != tools_sha256:
            raise ValueError(
                f"Resolved CI release-tools-lock digest mismatch for {platform_id}"
            )
        observed_urls = conda_artifact_urls(
            platform_root / f"conda-{platform_id}.explicit.txt",
            f"Resolved CI runtime manifest for {platform_id}",
            platform_id,
        )
        source_urls = conda_artifact_urls(
            platform_root / artifact_name,
            f"Resolved CI source artifact lock for {platform_id}",
            platform_id,
        )
        if observed_urls != source_urls:
            raise ValueError(
                f"Resolved CI runtime artifact set differs from the source artifact lock "
                f"for {platform_id}"
            )
        tracked_sources = {
            solver_name: solver_sha256,
            f"environment-{platform_id}.explicit.txt": artifact_sha256,
            tools_name: tools_sha256,
        }
        for tracked_name, expected_sha256 in tracked_sources.items():
            tracked_lock = repo_root / "locks" / tracked_name
            validate_regular_file(
                tracked_lock,
                source_root=repo_root,
                label=f"Tracked environment source for {platform_id}: {tracked_name}",
            )
            if sha256(tracked_lock) != expected_sha256:
                raise ValueError(
                    f"Resolved CI environment source differs from the release commit "
                    f"for {platform_id}: {tracked_name}"
                )
        identities.append(
            {
                "path": f"{RESOLVED_CI_ENVIRONMENTS_RELATIVE}/{platform_id}",
                **record,
            }
        )
    return identities


def validate_acceptance_evidence(
    validation_root: Path,
    repo_root: Path,
    expected_commit: str,
    repository: str,
) -> list[dict[str, str]]:
    validate_acceptance_inventory(validation_root)
    validate_release_environment_verification(validation_root, repo_root)
    rows = [validate_fresh_clone_evidence(validation_root, expected_commit, repository)]
    rows.extend(validate_github_actions_evidence(validation_root, expected_commit, repository))
    pull_request = validate_pull_request_evidence(
        validation_root,
        repo_root,
        expected_commit,
        repository,
    )
    pr_ci_row, _ = validate_pull_request_github_actions_evidence(
        validation_root,
        pull_request,
        repository,
    )
    audit_rows, _ = validate_read_only_audit_comments(
        validation_root,
        pull_request,
        repository,
    )
    rows.append(pr_ci_row)
    rows.extend(audit_rows)
    return rows


def pull_request_acceptance_identity(
    validation_root: Path,
    repo_root: Path,
    expected_commit: str,
    repository: str,
) -> dict[str, object]:
    pull_request = validate_pull_request_evidence(
        validation_root,
        repo_root,
        expected_commit,
        repository,
    )
    _, pr_ci = validate_pull_request_github_actions_evidence(
        validation_root,
        pull_request,
        repository,
    )
    _, audits = validate_read_only_audit_comments(
        validation_root,
        pull_request,
        repository,
    )
    return {
        "pull_request": pull_request,
        "pull_request_github_actions": pr_ci,
        "read_only_audits": audits,
    }


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


def validate_public_validation_github_actions_evidence(
    validation_root: Path,
    repo_root: Path,
    expected_commit: str,
    repository: str,
    expected_run_id: int,
) -> dict[str, object]:
    """Bind the packet to one successful Ubuntu public-data workflow run."""

    run_relative = "acceptance/ubuntu_public_validation/workflow_run.json"
    artifacts_relative = "acceptance/ubuntu_public_validation/artifacts.json"
    comparison_relative = "acceptance/cross_platform_comparison.tsv"
    reproduction_relative = "acceptance/cross_platform_public_reproduction.json"
    run = load_json_object(
        validation_root / run_relative,
        "public-validation GitHub Actions run evidence",
    )
    artifacts_payload = load_json_object(
        validation_root / artifacts_relative,
        "public-validation GitHub Actions artifact evidence",
    )
    reproduction = load_json_object(
        validation_root / reproduction_relative,
        "cross-platform public reproduction evidence",
    )
    repository_slug = github_repository_slug(repository)
    repository_api = f"https://api.github.com/repos/{repository_slug}"
    run_id = positive_json_integer(run.get("id"), "public-validation run id")
    if run_id != expected_run_id:
        raise ValueError(
            "Public-validation GitHub Actions run does not match the selected run ID"
        )
    run_attempt = positive_json_integer(
        run.get("run_attempt"), "public-validation run attempt"
    )
    run_url = f"https://github.com/{repository_slug}/actions/runs/{run_id}"
    run_api = f"{repository_api}/actions/runs/{run_id}"
    expected_run_fields = {
        "name": EXPECTED_PUBLIC_VALIDATION_WORKFLOW,
        "event": "workflow_dispatch",
        "head_branch": EXPECTED_GITHUB_BRANCH,
        "path": EXPECTED_PUBLIC_VALIDATION_WORKFLOW_PATH,
        "head_sha": expected_commit,
        "status": "completed",
        "conclusion": "success",
        "html_url": run_url,
        "url": run_api,
        "jobs_url": f"{run_api}/jobs",
    }
    for field, expected in expected_run_fields.items():
        if run.get(field) != expected:
            raise ValueError(
                f"Public-validation GitHub Actions run mismatch for {field}: "
                f"{run.get(field)!r} != {expected!r}"
            )
    validate_repository_object(
        run.get("repository"), repository_slug, "Public-validation run"
    )
    validate_repository_object(
        run.get("head_repository"), repository_slug, "Public-validation head"
    )

    expected_artifact_name = (
        f"public-validation-derived-{expected_commit}-{expected_run_id}"
    )
    artifacts = artifacts_payload.get("artifacts")
    if not isinstance(artifacts, list) or not all(
        isinstance(artifact, dict) for artifact in artifacts
    ):
        raise ValueError("Public-validation artifact evidence is malformed")
    matching = [
        artifact
        for artifact in artifacts
        if artifact.get("name") == expected_artifact_name
        and artifact.get("expired") is False
        and isinstance(artifact.get("workflow_run"), dict)
        and artifact["workflow_run"].get("id") == run_id
    ]
    if len(matching) != 1:
        raise ValueError(
            "Public-validation evidence must contain exactly one selected, unexpired artifact"
        )
    artifact = matching[0]
    artifact_id = positive_json_integer(
        artifact.get("id"), "public-validation artifact id"
    )
    expected_artifact_api = f"{repository_api}/actions/artifacts/{artifact_id}"
    if (
        artifact.get("url") != expected_artifact_api
        or artifact.get("archive_download_url") != f"{expected_artifact_api}/zip"
    ):
        raise ValueError("Public-validation artifact URLs are not canonical")

    artifact_root = (
        validation_root / "acceptance/ubuntu_public_validation/artifact"
    )
    validate_downloaded_public_artifact_identity(
        artifact_root,
        expected_commit,
        run_id,
    )
    local_public_root = validation_root / "public"
    ubuntu_public_root = artifact_root / "results"
    oracle_rows = read_frozen_oracle(repo_root / FROZEN_ORACLE_REPOSITORY_PATH)
    validate_public_contract_evidence(local_public_root, oracle_rows)
    validate_public_contract_evidence(ubuntu_public_root, oracle_rows)
    local_environment = validate_public_environment(local_public_root / "environment")
    ubuntu_environment = validate_public_environment(ubuntu_public_root / "environment")
    if local_environment["platform_id"] not in {"osx-64", "osx-arm64"}:
        raise ValueError("Cross-platform local public evidence was not produced on macOS")
    if ubuntu_environment["platform_id"] != "linux-64":
        raise ValueError("Cross-platform hosted public evidence was not produced on linux-64")
    local_scientific = public_scientific_paths(local_public_root)
    ubuntu_scientific = public_scientific_paths(ubuntu_public_root)
    if local_scientific != ubuntu_scientific:
        raise ValueError(
            "Cross-platform scientific path inventories differ: "
            f"macos_only={sorted(map(str, local_scientific - ubuntu_scientific))}; "
            f"ubuntu_only={sorted(map(str, ubuntu_scientific - local_scientific))}"
        )
    local_visuals = public_visual_paths(local_public_root)
    ubuntu_visuals = public_visual_paths(ubuntu_public_root)
    if local_visuals != ubuntu_visuals:
        raise ValueError("Cross-platform visual-inventory paths differ")
    expected_visual_cases = {
        visual_inventory_case_id(ubuntu_public_root, ubuntu_public_root / Path(*path.parts))
        for path in ubuntu_visuals
    }
    ubuntu_report_outputs = ubuntu_public_root / "report_artifacts" / "outputs"
    if ubuntu_report_outputs.is_symlink() or not ubuntu_report_outputs.is_dir():
        raise ValueError("Ubuntu report_artifacts/outputs evidence is missing")
    observed_visual_cases: set[str] = set()
    for entry in ubuntu_report_outputs.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            raise ValueError("Ubuntu report artifact collection contains a non-directory entry")
        observed_visual_cases.add(entry.name)
    if observed_visual_cases != expected_visual_cases:
        raise ValueError(
            "Ubuntu report artifact case inventory mismatch: "
            f"unexpected={sorted(observed_visual_cases - expected_visual_cases)}; "
            f"missing={sorted(expected_visual_cases - observed_visual_cases)}"
        )

    expected_reproduction = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "validation_profile": VALIDATION_PROFILE,
        "evidence_type": "cross_platform_public_reproduction",
        "verdict": "PASS",
        "git_commit": expected_commit,
        "ubuntu_public_validation_run_id": run_id,
        "ubuntu_platform": "linux-64",
        "comparison_table": "cross_platform_comparison.tsv",
    }
    for field, expected in expected_reproduction.items():
        if reproduction.get(field) != expected:
            raise ValueError(
                f"Cross-platform reproduction mismatch for {field}: "
                f"{reproduction.get(field)!r} != {expected!r}"
            )
    macos_platform = reproduction.get("macos_platform")
    if macos_platform not in {"osx-64", "osx-arm64"}:
        raise ValueError(
            f"Cross-platform reproduction has unsupported macOS platform: {macos_platform!r}"
        )
    if macos_platform != local_environment["platform_id"]:
        raise ValueError("Cross-platform reproduction macOS environment identity mismatch")

    comparison_rows = read_tsv_rows(
        validation_root / comparison_relative,
        (
            "evidence_type",
            "relative_path",
            "macos_sha256",
            "ubuntu_sha256",
            "verdict",
            "comparison",
        ),
        "cross_platform_comparison.tsv",
    )
    observed_keys: set[tuple[str, PurePosixPath]] = set()
    observed_paths: dict[str, set[PurePosixPath]] = {
        "normalized_scientific_table": set(),
        "visual_structure": set(),
    }
    counts = {"normalized_scientific_table": 0, "visual_structure": 0}
    for row in comparison_rows:
        evidence_type = row["evidence_type"]
        if evidence_type not in counts:
            raise ValueError("Cross-platform comparison contains an unsupported evidence type")
        relative = safe_posix_relative_path(
            row["relative_path"], "cross-platform comparison path"
        )
        key = (evidence_type, relative)
        if key in observed_keys:
            raise ValueError("Cross-platform comparison contains an invalid or duplicate row")
        observed_keys.add(key)
        observed_paths[evidence_type].add(relative)
        if row["verdict"] != "PASS":
            raise ValueError("Cross-platform comparison contains a nonpassing row")
        if evidence_type == "normalized_scientific_table":
            if relative not in local_scientific:
                raise ValueError(
                    f"Cross-platform comparison claims an unexpected scientific path: {relative}"
                )
            local_hash = sha256(local_public_root / Path(*relative.parts))
            ubuntu_hash = sha256(ubuntu_public_root / Path(*relative.parts))
            if (
                row["macos_sha256"] != local_hash
                or row["ubuntu_sha256"] != ubuntu_hash
            ):
                raise ValueError(
                    f"Cross-platform scientific row is not bound to file content: {relative}"
                )
            if local_hash != ubuntu_hash:
                raise ValueError("Cross-platform scientific table hashes differ")
        else:
            if relative not in local_visuals:
                raise ValueError(
                    f"Cross-platform comparison claims an unexpected visual path: {relative}"
                )
            if (
                row["macos_sha256"] != "not_compared"
                or row["ubuntu_sha256"] != "not_compared"
            ):
                raise ValueError("Cross-platform visual rows must not claim bytewise comparison")
            local_inventory = local_public_root / Path(*relative.parts)
            ubuntu_inventory = ubuntu_public_root / Path(*relative.parts)
            local_case_id = visual_inventory_case_id(local_public_root, local_inventory)
            ubuntu_case_id = visual_inventory_case_id(ubuntu_public_root, ubuntu_inventory)
            if local_case_id != ubuntu_case_id:
                raise ValueError("Cross-platform visual inventory case IDs differ")
            local_structure = bind_visual_inventory(
                local_inventory,
                local_public_root / "outputs" / local_case_id,
            )
            ubuntu_structure = bind_visual_inventory(
                ubuntu_inventory,
                ubuntu_report_outputs / ubuntu_case_id,
            )
            if local_structure != ubuntu_structure:
                raise ValueError(
                    f"Cross-platform visual structure differs: {relative}"
                )
        counts[evidence_type] += 1
    if observed_paths["normalized_scientific_table"] != local_scientific:
        raise ValueError("Cross-platform comparison scientific inventory is incomplete")
    if observed_paths["visual_structure"] != local_visuals:
        raise ValueError("Cross-platform comparison visual inventory is incomplete")
    if (
        reproduction.get("normalized_scientific_tables_compared")
        != counts["normalized_scientific_table"]
        or reproduction.get("visual_inventories_compared") != counts["visual_structure"]
    ):
        raise ValueError("Cross-platform reproduction row counts do not match its table")

    return {
        "provider": "github_actions",
        "run_id": run_id,
        "run_attempt": run_attempt,
        "workflow": EXPECTED_PUBLIC_VALIDATION_WORKFLOW,
        "workflow_path": EXPECTED_PUBLIC_VALIDATION_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "branch": EXPECTED_GITHUB_BRANCH,
        "head_sha": expected_commit,
        "status": "completed",
        "conclusion": "success",
        "url": run_url,
        "artifact": {
            "id": artifact_id,
            "name": expected_artifact_name,
            "url": expected_artifact_api,
            "archive_download_url": f"{expected_artifact_api}/zip",
        },
        "cross_platform_reproduction": {
            "verdict": "PASS",
            "macos_platform": macos_platform,
            "ubuntu_platform": "linux-64",
            "normalized_scientific_tables_compared": counts[
                "normalized_scientific_table"
            ],
            "visual_inventories_compared": counts["visual_structure"],
            "comparison_sha256": sha256(validation_root / comparison_relative),
        },
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
    for key in (
        "github_actions_run_id",
        "final_push_github_actions_run_id",
        "pull_request_number",
        "pull_request_github_actions_run_id",
        "public_validation_github_actions_run_id",
    ):
        if not re.fullmatch(r"[1-9][0-9]*", environment[key]):
            raise ValueError(f"environment.txt {key} is not a positive integer")
    if (
        environment["github_actions_run_id"]
        != environment["final_push_github_actions_run_id"]
    ):
        raise ValueError(
            "environment.txt legacy github_actions_run_id does not match "
            "final_push_github_actions_run_id"
        )

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
            "update pyproject.toml, mito_overview/__init__.py, CITATION.cff, "
            f"README.md, and CHANGELOG.md to {package_version}"
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
        "environment_final_push_github_actions_run_id": int(
            environment["final_push_github_actions_run_id"]
        ),
        "environment_pull_request_number": int(
            environment["pull_request_number"]
        ),
        "environment_pull_request_github_actions_run_id": int(
            environment["pull_request_github_actions_run_id"]
        ),
        "environment_public_validation_github_actions_run_id": int(
            environment["public_validation_github_actions_run_id"]
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
    unexpected = sorted(case_ids - REQUIRED_PASS_CASES)
    if missing_required or unexpected:
        raise ValueError(
            "Validation case IDs do not exactly match the required release set: "
            f"missing={missing_required}; unexpected={unexpected}"
        )
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


def expected_handoff_rows(
    profile_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for profile in profile_rows:
        case_id = profile.get("case_id", "")
        dataset = profile.get("dataset", "")
        if not case_id or not dataset:
            raise ValueError("Filter-profile handoff source has an empty identity")
        for metric, unit in HANDOFF_METRICS:
            value = profile.get(metric, "")
            if value == "":
                continue
            rows.append(
                {
                    "result_id": f"{case_id}:{metric}",
                    "dataset": dataset,
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "source_table": HANDOFF_SOURCE_TABLE,
                    "claim_boundary": HANDOFF_CLAIM_BOUNDARY,
                }
            )
    if not rows:
        raise ValueError("No manuscript-handoff rows can be derived")
    return rows


def validate_claim_and_handoff_evidence(validation_root: Path) -> None:
    claim_rows = read_tsv_rows(
        validation_root / "claim_evidence_matrix.tsv",
        EVIDENCE_TABLES["claim_evidence_matrix.tsv"],
        "claim_evidence_matrix.tsv",
    )
    if claim_rows != [dict(row) for row in FROZEN_CLAIM_EVIDENCE_ROWS]:
        raise ValueError("Claim-evidence matrix does not match the frozen bounded contract")

    case_rows = read_tsv_rows(
        validation_root / "cases.tsv",
        (
            "case_id",
            "category",
            "input_available",
            "expected_available",
            "verdict",
            "detail",
        ),
        "cases.tsv",
    )
    cases_by_id = {row["case_id"]: row for row in case_rows}
    if len(cases_by_id) != len(case_rows):
        raise ValueError("Claim evidence cannot resolve duplicate validation cases")
    for row in claim_rows:
        for token in (part.strip() for part in row["evidence"].split(";")):
            if not token:
                raise ValueError(f"Claim {row['claim_id']} has an empty evidence token")
            if token in cases_by_id:
                if cases_by_id[token]["verdict"] != "PASS":
                    raise ValueError(
                        f"Claim {row['claim_id']} references non-PASS case {token}"
                    )
                continue
            if token.startswith("expected/"):
                evidence_path = validation_root / token
            elif token == HANDOFF_SOURCE_TABLE:
                evidence_path = validation_root / "public" / token
            else:
                raise ValueError(
                    f"Claim {row['claim_id']} references unknown evidence token {token}"
                )
            if (
                not evidence_path.is_file()
                or evidence_path.is_symlink()
                or evidence_path.stat().st_size == 0
            ):
                raise ValueError(
                    f"Claim {row['claim_id']} evidence file is unavailable: {token}"
                )

    profile_rows = read_tsv_rows(
        validation_root / "public" / HANDOFF_SOURCE_TABLE,
        FILTER_PROFILE_HEADER,
        HANDOFF_SOURCE_TABLE,
    )
    handoff_rows = read_tsv_rows(
        validation_root / "manuscript_handoff.tsv",
        EVIDENCE_TABLES["manuscript_handoff.tsv"],
        "manuscript_handoff.tsv",
    )
    if handoff_rows != expected_handoff_rows(profile_rows):
        raise ValueError(
            "Manuscript-handoff values do not match filter_profile_results.tsv"
        )


def validate_evidence_tables(validation_root: Path) -> None:
    allowed_module_states = {
        "ok",
        "not_configured",
        "not_applicable",
        "not_evaluable",
        "unavailable",
        "failed",
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
            measurement_ids: set[str] = set()
            resource_case_ids: set[str] = set()
            for row in rows:
                measurement_id = row["measurement_id"].lower()
                if re.fullmatch(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                    measurement_id,
                    flags=re.IGNORECASE,
                ) is None:
                    raise ValueError(
                        f"Invalid resource measurement ID: {measurement_id!r}"
                    )
                if measurement_id in measurement_ids:
                    raise ValueError(
                        f"Duplicate resource measurement ID: {measurement_id}"
                    )
                measurement_ids.add(measurement_id)
                case_id = row["case_id"]
                if case_id in resource_case_ids:
                    raise ValueError(f"Duplicate resource case ID: {case_id}")
                resource_case_ids.add(case_id)
                if re.fullmatch(r"[0-9a-f]{40}", row["candidate_commit"]) is None:
                    raise ValueError(
                        f"Invalid resource candidate commit for {case_id}"
                    )
                expected_paths = {
                    "command_path": f"commands/{case_id}.sh",
                    "log_path": f"logs/{case_id}.log",
                }
                for field, expected_path in expected_paths.items():
                    if row[field] != expected_path:
                        raise ValueError(
                            f"Resource {field} mismatch for {case_id}: {row[field]!r}"
                        )
                for field in (
                    "command_sha256",
                    "packaged_command_sha256",
                    "log_sha256",
                    "packaged_log_sha256",
                ):
                    if re.fullmatch(r"[0-9a-f]{64}", row[field]) is None:
                        raise ValueError(
                            f"Invalid resource {field} for {case_id}: {row[field]!r}"
                        )
                status = row["measurement_status"]
                if status != "measured":
                    raise ValueError(
                        "Required resource measurement must be measured for "
                        f"{case_id}: {status!r}"
                    )
                expected_threads = RESOURCE_CASE_THREAD_SETTINGS.get(case_id)
                if row["threads"] != expected_threads:
                    raise ValueError(
                        "Resource thread setting mismatch for "
                        f"{case_id}: {row['threads']!r} != {expected_threads!r}"
                    )
                numeric_values: dict[str, float] = {}
                for field in (
                    "wall_seconds",
                    "user_cpu_seconds",
                    "system_cpu_seconds",
                    "max_rss_kb",
                    "broad_declared_input_inventory_bytes",
                    "changed_or_new_output_inventory_bytes",
                ):
                    try:
                        value = float(row[field])
                    except ValueError as error:
                        raise ValueError(
                            f"Invalid finite resource value {field}={row[field]!r}"
                        ) from error
                    if not math.isfinite(value):
                        raise ValueError(
                            f"Invalid finite resource value {field}={row[field]!r}"
                        )
                    numeric_values[field] = value
                for field in (
                    "broad_declared_input_inventory_file_count",
                    "changed_or_new_output_inventory_file_count",
                ):
                    try:
                        value = int(row[field])
                    except ValueError as error:
                        raise ValueError(
                            f"Invalid resource inventory count {field}={row[field]!r}"
                        ) from error
                    if value < 0 or str(value) != row[field]:
                        raise ValueError(
                            f"Invalid resource inventory count {field}={row[field]!r}"
                        )
                    numeric_values[field] = float(value)
                for field in ("wall_seconds", "max_rss_kb"):
                    if numeric_values[field] <= 0:
                        raise ValueError(f"Resource {field} must be > 0 for {case_id}")
                for field in ("user_cpu_seconds", "system_cpu_seconds"):
                    if numeric_values[field] < 0:
                        raise ValueError(f"Resource {field} must be >= 0 for {case_id}")
                if numeric_values["broad_declared_input_inventory_file_count"] <= 0:
                    raise ValueError(
                        "Resource broad_declared_input_inventory_file_count must be > 0 "
                        f"for {case_id}"
                    )
                if numeric_values["broad_declared_input_inventory_bytes"] <= 0:
                    raise ValueError(
                        "Resource broad_declared_input_inventory_bytes must be > 0 "
                        f"for {case_id}"
                    )
                for field in (
                    "changed_or_new_output_inventory_file_count",
                    "changed_or_new_output_inventory_bytes",
                ):
                    if numeric_values[field] < 0:
                        raise ValueError(f"Resource {field} must be >= 0 for {case_id}")
                if (
                    row["io_measurement_method"]
                    != "broad_declared_inputs_and_changed_or_new_outputs_v3"
                ):
                    raise ValueError(
                        "Invalid resource I/O measurement method: "
                        + row["io_measurement_method"]
                    )
                if row["broad_declared_input_inventory_scope"] != (
                    "repository_root;cache_root;validation_root"
                ):
                    raise ValueError(
                        "Invalid broad declared input inventory scope: "
                        + row["broad_declared_input_inventory_scope"]
                    )
                if row["changed_or_new_output_inventory_scope"] != (
                    "cache_root;validation_root"
                ):
                    raise ValueError(
                        "Invalid changed/new output inventory scope: "
                        + row["changed_or_new_output_inventory_scope"]
                    )
            if resource_case_ids != REQUIRED_RESOURCE_CASE_IDS:
                raise ValueError(
                    "Resource case inventory mismatch: "
                    f"missing={sorted(REQUIRED_RESOURCE_CASE_IDS - resource_case_ids)}, "
                    f"unexpected={sorted(resource_case_ids - REQUIRED_RESOURCE_CASE_IDS)}"
                )
        elif name in {"figure_provenance.tsv", "table_provenance.tsv"}:
            for row in rows:
                relative = Path(row["packet_path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"Unsafe packet_path in {name}: {row['packet_path']!r}")
                if re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None:
                    raise ValueError(f"Invalid SHA-256 in {name}: {row['sha256']!r}")
    validate_claim_and_handoff_evidence(validation_root)


def validate_resource_bindings(
    root: Path,
    expected_commit: str,
    *,
    packaged: bool = False,
) -> None:
    rows = read_tsv_rows(
        root / "resource_usage.tsv",
        EVIDENCE_TABLES["resource_usage.tsv"],
        "resource_usage.tsv",
    )
    for row in rows:
        case_id = row["case_id"]
        if row["candidate_commit"] != expected_commit:
            raise ValueError(
                f"Resource candidate commit mismatch for {case_id}: "
                f"{row['candidate_commit']} != {expected_commit}"
            )
        digest_prefix = "packaged_" if packaged else ""
        for path_field, digest_field in (
            ("command_path", f"{digest_prefix}command_sha256"),
            ("log_path", f"{digest_prefix}log_sha256"),
        ):
            relative = PurePosixPath(row[path_field])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe resource evidence path for {case_id}")
            evidence_path = root / Path(*relative.parts)
            validate_regular_file(
                evidence_path,
                source_root=root,
                label=f"Resource {path_field} for {case_id}",
            )
            if sha256(evidence_path) != row[digest_field]:
                raise ValueError(
                    f"Resource {digest_field} does not match {path_field} for {case_id}"
                )
            if not packaged:
                packaged_field = f"packaged_{digest_field}"
                if row[packaged_field] != row[digest_field]:
                    raise ValueError(
                        "Pre-packaging resource digest mismatch for "
                        f"{case_id}: {packaged_field} != {digest_field}"
                    )


def rebind_packaged_resource_evidence(packet_root: Path, expected_commit: str) -> None:
    table_path = packet_root / "resource_usage.tsv"
    rows = read_tsv_rows(
        table_path,
        EVIDENCE_TABLES["resource_usage.tsv"],
        "resource_usage.tsv",
    )
    for row in rows:
        if row["candidate_commit"] != expected_commit:
            raise ValueError(
                f"Resource candidate commit changed during packaging: {row['case_id']}"
            )
        row["packaged_command_sha256"] = sha256(
            packet_root / row["command_path"]
        )
        row["packaged_log_sha256"] = sha256(packet_root / row["log_path"])
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EVIDENCE_TABLES["resource_usage.tsv"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    validate_resource_bindings(packet_root, expected_commit, packaged=True)


def decoded_png_rgba(path: Path) -> tuple[int, int, bytes]:
    """Decode a non-interlaced 8-bit PNG to canonical RGBA bytes."""

    payload = path.read_bytes()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Invalid PNG signature: {path}")
    offset = 8
    width = height = color_type = None
    bit_depth = compression = filter_method = interlace = None
    compressed = bytearray()
    saw_iend = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ValueError(f"Truncated PNG chunk header: {path}")
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            raise ValueError(f"Truncated PNG chunk payload: {path}")
        data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != expected_crc:
            raise ValueError(f"PNG chunk CRC mismatch: {path}")
        offset = crc_end
        if kind == b"IHDR":
            if width is not None or length != 13:
                raise ValueError(f"Invalid PNG IHDR inventory: {path}")
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            if length != 0:
                raise ValueError(f"Invalid PNG IEND chunk: {path}")
            saw_iend = True
            break
    if not saw_iend or offset != len(payload):
        raise ValueError(f"PNG is missing a terminal IEND chunk: {path}")
    if (
        width is None
        or height is None
        or width <= 0
        or height <= 0
        or width * height > 100_000_000
        or bit_depth != 8
        or color_type not in {0, 2, 4, 6}
        or compression != 0
        or filter_method != 0
        or interlace != 0
        or not compressed
    ):
        raise ValueError(f"Unsupported PNG encoding for decoded-pixel evidence: {path}")
    bytes_per_pixel = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    stride = width * bytes_per_pixel
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise ValueError(f"Unable to decompress PNG pixels: {path}") from error
    if len(raw) != height * (stride + 1):
        raise ValueError(f"PNG scanline length mismatch: {path}")

    def paeth(left: int, up: int, upper_left: int) -> int:
        estimate = left + up - upper_left
        distances = (
            abs(estimate - left),
            abs(estimate - up),
            abs(estimate - upper_left),
        )
        return (left, up, upper_left)[distances.index(min(distances))]

    previous = bytearray(stride)
    rgba = bytearray()
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        scanline = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        if filter_type not in {0, 1, 2, 3, 4}:
            raise ValueError(f"Unsupported PNG row filter: {path}")
        for index in range(stride):
            left = scanline[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            up = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            if filter_type == 1:
                scanline[index] = (scanline[index] + left) & 0xFF
            elif filter_type == 2:
                scanline[index] = (scanline[index] + up) & 0xFF
            elif filter_type == 3:
                scanline[index] = (scanline[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                scanline[index] = (
                    scanline[index] + paeth(left, up, upper_left)
                ) & 0xFF
        for index in range(0, stride, bytes_per_pixel):
            pixel = scanline[index : index + bytes_per_pixel]
            if color_type == 0:
                rgba.extend((pixel[0], pixel[0], pixel[0], 255))
            elif color_type == 2:
                rgba.extend((pixel[0], pixel[1], pixel[2], 255))
            elif color_type == 4:
                rgba.extend((pixel[0], pixel[0], pixel[0], pixel[1]))
            else:
                rgba.extend(pixel)
        previous = scanline
    return width, height, bytes(rgba)


def validate_decoded_pixel_evidence(validation_root: Path) -> list[dict[str, object]]:
    """Bind repeatability pixel hashes to the packet's report-native PNG inventory."""

    figure_rows = read_tsv_rows(
        validation_root / "figure_provenance.tsv",
        EVIDENCE_TABLES["figure_provenance.tsv"],
        "figure_provenance.tsv",
    )
    validated: list[dict[str, object]] = []
    for dataset, specification in DECODED_PIXEL_REPORTS.items():
        case_id = str(specification["case_id"])
        repeat_case_id = str(specification["repeat_case_id"])
        expected = {
            Path(row["packet_path"]).name: (
                row["width"],
                row["height"],
                validation_root / row["packet_path"],
                validation_root
                / "public"
                / "outputs"
                / repeat_case_id
                / "figures"
                / Path(row["packet_path"]).name,
            )
            for row in figure_rows
            if row["dataset"] == dataset and row["case_id"] == case_id
        }
        if not expected:
            raise ValueError(
                f"No report-native PNG provenance is available for {dataset}"
            )
        source = validation_root / "public" / str(specification["source"])
        if not source.is_file():
            raise ValueError(
                f"Required decoded-pixel evidence is missing for {dataset}: {source}"
            )
        rows = read_tsv_rows(
            source,
            DECODED_PIXEL_HASH_COLUMNS,
            f"{dataset} decoded-pixel evidence",
        )
        observed: dict[str, tuple[str, str, Path, Path]] = {}
        for row in rows:
            name = row["path"]
            if not name or Path(name).name != name or name in observed:
                raise ValueError(
                    f"Invalid or duplicate decoded-pixel path for {dataset}: {name!r}"
                )
            try:
                if int(row["width_px"]) <= 0 or int(row["height_px"]) <= 0:
                    raise ValueError
            except ValueError as error:
                raise ValueError(
                    f"Invalid decoded-pixel dimensions for {dataset}: {name}"
                ) from error
            if re.fullmatch(r"[0-9a-f]{64}", row["decoded_rgba_sha256"]) is None:
                raise ValueError(
                    f"Invalid decoded-pixel SHA-256 for {dataset}: {name}"
                )
            figure_paths = expected.get(name, ("", "", Path(), Path()))[2:]
            for repeat_index, figure_path in enumerate(figure_paths, start=1):
                if not figure_path.is_file() or figure_path.is_symlink():
                    raise ValueError(
                        f"Decoded-pixel repeat-{repeat_index} figure is missing "
                        f"for {dataset}: {name}"
                    )
                width, height, rgba = decoded_png_rgba(figure_path)
                actual_digest = hashlib.sha256(rgba).hexdigest()
                if (
                    str(width) != row["width_px"]
                    or str(height) != row["height_px"]
                    or actual_digest != row["decoded_rgba_sha256"]
                ):
                    raise ValueError(
                        f"Decoded-pixel hash does not match repeat-{repeat_index} "
                        f"PNG for {dataset}: {name}"
                    )
            observed[name] = (
                row["width_px"],
                row["height_px"],
                figure_paths[0],
                figure_paths[1],
            )
        if observed != expected:
            raise ValueError(
                f"Decoded-pixel inventory does not match report-native figures for {dataset}"
            )
        validated.append(
            {
                "dataset": dataset,
                "case_id": case_id,
                "path": str(specification["packet"]),
                "sha256": sha256(source),
                "figure_count": len(rows),
            }
        )
    return validated


def validate_public_cache_byte_provenance(
    validation_root: Path,
    public_input_rows: list[dict[str, str]],
) -> None:
    """Require the cache-preparation output inventory to include raw downloads."""

    rows = read_tsv_rows(
        validation_root / "resource_usage.tsv",
        EVIDENCE_TABLES["resource_usage.tsv"],
        "resource_usage.tsv",
    )
    cache_rows = [row for row in rows if row["case_id"] == "public_cache_prepare"]
    if len(cache_rows) != 1:
        raise ValueError(
            "resource_usage.tsv must contain exactly one public_cache_prepare row"
        )
    cache_row = cache_rows[0]
    if cache_row["measurement_status"] != "measured":
        raise ValueError("public_cache_prepare byte provenance must be measured")
    raw_fastq_bytes = sum(int(row["bytes"]) for row in public_input_rows)
    observed = int(cache_row["changed_or_new_output_inventory_bytes"])
    if observed < raw_fastq_bytes:
        raise ValueError(
            "public_cache_prepare changed/new output inventory excludes one or more "
            f"raw downloads: expected at least {raw_fastq_bytes}, observed {observed}"
        )


def _text_payload(path: Path) -> str | None:
    if any(part in {"dist", "figures"} for part in path.parts):
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def sanitize_packet_paths(
    packet_root: Path,
    replacements: dict[Path, str],
    immutable_roots: tuple[Path, ...] = (),
) -> None:
    protected = tuple(path.resolve(strict=False) for path in immutable_roots)
    ordered = sorted(
        ((str(path.resolve(strict=False)), marker) for path, marker in replacements.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for path in sorted(packet_root.rglob("*")):
        if not path.is_file() or path.name == "verify_bundle.sh":
            continue
        resolved = path.resolve(strict=False)
        if any(resolved.is_relative_to(root) for root in protected):
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
        r"/mnt(?:/[^\s'\";]*)?",
        r"/Volumes(?:/[^\s'\";]*)?",
        r"/(?:group|scratch)/(?:g/)?xgai(?:/[^\s'\";]*)?",
        r"(?i)\bqfs\d*\.rcc\.mcw\.edu\b",
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
# Trust boundary: this script checks packet-internal consistency only. Verify
# the enclosing ZIP against a separately trusted SHA-256 before extraction.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -I -S - "${ROOT}" <<'PY'
import csv
import hashlib
import json
import math
import os
import re
import stat
import struct
import sys
import tarfile
import zipfile
import zlib
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

root = Path(sys.argv[1])

def validate_unpacked_packet_tree(packet_root):
    try:
        root_mode = packet_root.lstat().st_mode
        resolved_root = packet_root.resolve(strict=True)
    except OSError as error:
        raise SystemExit(f"packet root is missing or unreadable: {error}") from error
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise SystemExit("packet root is a symlink or non-directory entry")

    stack = [packet_root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise SystemExit(f"packet directory is unreadable: {directory}") from error
        for entry in entries:
            path = Path(entry.path)
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as error:
                raise SystemExit(f"packet entry is unreadable: {path}") from error
            relative = path.relative_to(packet_root)
            if stat.S_ISLNK(mode):
                raise SystemExit(f"packet contains a symlink: {relative}")
            if not stat.S_ISDIR(mode) and not stat.S_ISREG(mode):
                raise SystemExit(f"packet contains a special file: {relative}")
            try:
                resolved = path.resolve(strict=True)
            except OSError as error:
                raise SystemExit(f"packet entry cannot be resolved: {relative}") from error
            if not resolved.is_relative_to(resolved_root):
                raise SystemExit(f"packet entry resolves outside packet root: {relative}")
            if stat.S_ISDIR(mode):
                stack.append(path)

validate_unpacked_packet_tree(root)
schema = "2.0"
profile = "github_release_validation_v1"
required_top_level = {
    "run.json", "release_identity.json", "cases.tsv", "acceptance",
    "cross_platform_comparison.tsv",
    "claim_evidence_matrix.tsv", "module_status_matrix.tsv",
    "resource_usage.tsv", "figure_provenance.tsv", "table_provenance.tsv",
    "public_data_sources.tsv", "manuscript_handoff.tsv", "limitations.tsv",
    "environment.txt", "commands", "logs", "dist", "expected",
    "observed_normalized", "observed_contracts", "public_provenance",
    "public_environment", "figures",
    "figures_repeat2", "decoded_pixel_hashes", "report_artifacts",
    "filter_profile_results.tsv", "inputs.sha256", "raw_inputs.tsv",
    "CACHE_SEAL.sha256", "public_validation_oracle_v0.3.0.tsv",
    "oracle_assertions.tsv", "public_matrix_cases.tsv", "artifacts.sha256",
    "verify_bundle.sh",
}
missing = sorted(name for name in required_top_level if not (root / name).exists())
if missing:
    raise SystemExit(f"missing required evidence: {missing}")
unexpected = sorted(entry.name for entry in root.iterdir() if entry.name not in required_top_level)
if unexpected:
    raise SystemExit(f"unexpected top-level packet evidence: {unexpected}")

for relative in (
    "acceptance", "commands", "commands/public", "logs", "logs/public",
    "dist", "expected", "observed_normalized", "observed_contracts",
    "public_provenance",
    "public_environment", "figures", "figures_repeat2", "decoded_pixel_hashes",
):
    evidence_root = root / relative
    if not evidence_root.is_dir() or not any(
        candidate.is_file() for candidate in evidence_root.rglob("*")
    ):
        raise SystemExit(f"required evidence directory is empty: {relative}")

required_acceptance_files = {
    "fresh_clone.json", "github_actions_run.json", "github_actions_jobs.json",
    "pull_request.json", "pull_request_comments.json",
    "pull_request_github_actions_run.json",
    "pull_request_github_actions_jobs.json",
    "cross_platform_comparison.tsv",
    "cross_platform_public_reproduction.json",
}
acceptance_root = root / "acceptance"
acceptance_entries = list(acceptance_root.rglob("*"))
if any(
    entry.is_symlink() or (not entry.is_file() and not entry.is_dir())
    for entry in acceptance_entries
):
    raise SystemExit("acceptance evidence contains a symlink or non-regular entry")
observed_acceptance_files = {
    child.name for child in acceptance_root.iterdir()
    if child.is_file() and not child.is_symlink()
}
missing_acceptance_files = required_acceptance_files - observed_acceptance_files
if missing_acceptance_files:
    raise SystemExit(
        "required acceptance evidence is missing: "
        f"{sorted(missing_acceptance_files)}"
    )
for relative in ("resolved_ci_environments", "ubuntu_public_validation"):
    evidence = acceptance_root / relative
    if evidence.is_symlink() or not evidence.is_dir():
        raise SystemExit(f"required acceptance directory is missing: {relative}")
for relative in (
    "ubuntu_public_validation/workflow_run.json",
    "ubuntu_public_validation/artifacts.json",
    "ubuntu_public_validation/artifact/SHA256SUMS",
    "ubuntu_public_validation/artifact/environment/identity.txt",
):
    evidence = acceptance_root / relative
    if evidence.is_symlink() or not evidence.is_file() or evidence.stat().st_size == 0:
        raise SystemExit(f"required public-validation evidence is missing: {relative}")

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def md5_digest(path):
    value = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def decoded_png_rgba(path):
    payload = path.read_bytes()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SystemExit(f"invalid PNG signature: {path}")
    offset = 8
    width = height = bit_depth = color_type = None
    compression = filter_method = interlace = None
    compressed = bytearray()
    saw_iend = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise SystemExit(f"truncated PNG chunk header: {path}")
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        kind = payload[offset + 4:offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            raise SystemExit(f"truncated PNG chunk payload: {path}")
        data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != expected_crc:
            raise SystemExit(f"PNG chunk CRC mismatch: {path}")
        offset = crc_end
        if kind == b"IHDR":
            if width is not None or length != 13:
                raise SystemExit(f"invalid PNG IHDR inventory: {path}")
            (
                width, height, bit_depth, color_type, compression,
                filter_method, interlace,
            ) = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            if length != 0:
                raise SystemExit(f"invalid PNG IEND chunk: {path}")
            saw_iend = True
            break
    if not saw_iend or offset != len(payload):
        raise SystemExit(f"PNG is missing a terminal IEND chunk: {path}")
    if (
        width is None or height is None or width <= 0 or height <= 0
        or width * height > 100_000_000 or bit_depth != 8
        or color_type not in {0, 2, 4, 6} or compression != 0
        or filter_method != 0 or interlace != 0 or not compressed
    ):
        raise SystemExit(f"unsupported PNG encoding: {path}")
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    stride = width * bpp
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise SystemExit(f"unable to decompress PNG pixels: {path}") from error
    if len(raw) != height * (stride + 1):
        raise SystemExit(f"PNG scanline length mismatch: {path}")

    def paeth(left, up, upper_left):
        estimate = left + up - upper_left
        distances = (
            abs(estimate - left), abs(estimate - up), abs(estimate - upper_left),
        )
        return (left, up, upper_left)[distances.index(min(distances))]

    previous = bytearray(stride)
    rgba = bytearray()
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        scanline = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        if filter_type not in {0, 1, 2, 3, 4}:
            raise SystemExit(f"unsupported PNG row filter: {path}")
        for index in range(stride):
            left = scanline[index - bpp] if index >= bpp else 0
            up = previous[index]
            upper_left = previous[index - bpp] if index >= bpp else 0
            if filter_type == 1:
                scanline[index] = (scanline[index] + left) & 0xFF
            elif filter_type == 2:
                scanline[index] = (scanline[index] + up) & 0xFF
            elif filter_type == 3:
                scanline[index] = (scanline[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                scanline[index] = (scanline[index] + paeth(left, up, upper_left)) & 0xFF
        for index in range(0, stride, bpp):
            pixel = scanline[index:index + bpp]
            if color_type == 0:
                rgba.extend((pixel[0], pixel[0], pixel[0], 255))
            elif color_type == 2:
                rgba.extend((pixel[0], pixel[1], pixel[2], 255))
            elif color_type == 4:
                rgba.extend((pixel[0], pixel[0], pixel[0], pixel[1]))
            else:
                rgba.extend(pixel)
        previous = scanline
    return width, height, bytes(rgba)

def safe_posix_relative(value, label):
    if not value or "\\" in value:
        raise SystemExit(f"{label} is empty or uses a non-POSIX separator: {value!r}")
    relative = PurePosixPath(value.removeprefix("./"))
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise SystemExit(f"{label} is unsafe: {value!r}")
    return relative

forbidden_public_suffixes = (
    ".fastq", ".fastq.gz", ".fq", ".fq.gz", ".bam", ".bai",
    ".cram", ".crai", ".sam",
)
scientific_top_level = (
    "cases.tsv", "filter_profile_results.tsv", "inputs.sha256",
    "oracle_assertions.tsv", "raw_inputs.tsv", "CACHE_SEAL.sha256",
)
visual_fields = (
    "relative_path", "artifact_type", "width_px", "height_px",
    "integrity_status",
)

def validate_public_artifact(artifact_root, expected_commit, expected_run_id):
    if artifact_root.is_symlink() or not artifact_root.is_dir():
        raise SystemExit("downloaded public-validation artifact is not a regular directory")
    manifest_path = artifact_root / "SHA256SUMS"
    entries = {}
    for line_number, line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if match is None:
            raise SystemExit(
                f"malformed public-validation SHA256SUMS line {line_number}: {line!r}"
            )
        relative = safe_posix_relative(
            match.group(2), "public-validation manifest path"
        ).as_posix()
        if relative == "SHA256SUMS" or relative in entries:
            raise SystemExit(
                f"duplicate or self-referential public-validation manifest path: {relative}"
            )
        entries[relative] = match.group(1)
    if not entries:
        raise SystemExit("downloaded public-validation artifact manifest is empty")
    actual = set()
    for candidate in artifact_root.rglob("*"):
        if candidate.is_symlink() or (not candidate.is_file() and not candidate.is_dir()):
            raise SystemExit(
                "downloaded public-validation artifact contains a symlink or non-regular entry"
            )
        if candidate.is_file() and candidate != manifest_path:
            relative = candidate.relative_to(artifact_root).as_posix()
            if relative.lower().endswith(forbidden_public_suffixes):
                raise SystemExit(
                    f"downloaded public-validation artifact contains raw/alignment data: {relative}"
                )
            actual.add(relative)
    if set(entries) != actual:
        raise SystemExit("downloaded public-validation artifact manifest inventory mismatch")
    for relative, expected in entries.items():
        if digest(artifact_root / relative) != expected:
            raise SystemExit(
                f"downloaded public-validation artifact hash mismatch: {relative}"
            )
    identity = {}
    for line in (artifact_root / "environment/identity.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key or key in identity:
            raise SystemExit("public-validation artifact identity is malformed")
        identity[key] = value
    expected_identity = {
        "git_commit": expected_commit, "runner_os": "Linux",
        "runner_arch": "X64", "github_run_id": str(expected_run_id),
    }
    for field, expected in expected_identity.items():
        if identity.get(field) != expected:
            raise SystemExit(
                f"public-validation artifact identity mismatch for {field}"
            )

def public_scientific_paths(public_root, cases_override=None):
    normalized = public_root / "observed_normalized"
    if normalized.is_symlink() or not normalized.is_dir():
        raise SystemExit("cross-platform observed_normalized directory is missing")
    paths = {
        PurePosixPath(path.relative_to(public_root).as_posix())
        for path in normalized.rglob("*.tsv")
        if path.name != "visual_artifact_inventory.tsv"
        and path.is_file() and not path.is_symlink()
    }
    contracts = public_root / "observed_contracts"
    if contracts.is_symlink() or not contracts.is_dir():
        raise SystemExit("cross-platform observed_contracts directory is missing")
    paths.update(
        PurePosixPath(path.relative_to(public_root).as_posix())
        for path in contracts.rglob("*.tsv")
        if path.is_file() and not path.is_symlink()
    )
    for name in scientific_top_level:
        path = cases_override if name == "cases.tsv" and cases_override else public_root / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"cross-platform scientific evidence is missing: {name}")
        paths.add(PurePosixPath(name))
    if not paths:
        raise SystemExit("cross-platform scientific evidence inventory is empty")
    return paths

def public_visual_paths(public_root):
    paths = {
        PurePosixPath(path.relative_to(public_root).as_posix())
        for path in (public_root / "observed_normalized").rglob(
            "visual_artifact_inventory.tsv"
        )
        if path.is_file() and not path.is_symlink()
    }
    if not paths:
        raise SystemExit("cross-platform visual-inventory evidence is empty")
    return paths

def parse_visual_inventory(path):
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected_fields = (
            "relative_path", "artifact_type", "bytes", "sha256", "width_px",
            "height_px", "integrity_status",
        )
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise SystemExit(f"cross-platform visual inventory schema mismatch: {path}")
        rows = list(reader)
    if not rows:
        raise SystemExit(f"cross-platform visual inventory is empty: {path}")
    seen = set()
    for row in rows:
        raw_relative = row.get("relative_path", "")
        if any(character in raw_relative for character in ("\x00", "\t", "\n", "\r")):
            raise SystemExit("visual artifact path contains a control character")
        relative = safe_posix_relative(raw_relative, "visual artifact path")
        if len(relative.parts) != 2 or relative in seen:
            raise SystemExit("visual artifact path is nested or duplicated")
        seen.add(relative)
        expected_type = {
            ("report", ".html"): "html",
            ("figures", ".png"): "png",
        }.get((relative.parts[0], relative.suffix.lower()))
        if expected_type is None or row.get("artifact_type") != expected_type:
            raise SystemExit("visual artifact type/path mismatch")
        if row.get("integrity_status") != "ok":
            raise SystemExit("visual artifact is not marked ok")
        if not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")):
            raise SystemExit("invalid visual artifact SHA-256")
        try:
            size = int(row.get("bytes", ""))
        except ValueError as error:
            raise SystemExit("invalid visual artifact byte count") from error
        if size <= 0 or str(size) != row.get("bytes"):
            raise SystemExit("noncanonical visual artifact byte count")
        if expected_type == "html":
            if row.get("width_px") or row.get("height_px"):
                raise SystemExit("HTML visual artifact declares dimensions")
        else:
            try:
                width = int(row.get("width_px", ""))
                height = int(row.get("height_px", ""))
            except ValueError as error:
                raise SystemExit("invalid PNG dimensions") from error
            if (
                width <= 0 or height <= 0
                or str(width) != row.get("width_px")
                or str(height) != row.get("height_px")
            ):
                raise SystemExit("noncanonical PNG dimensions")
    return rows

def visual_structure(path):
    rows = parse_visual_inventory(path)
    structure = sorted(tuple(row.get(field, "") for field in visual_fields) for row in rows)
    return structure

def bind_visual_inventory(inventory_path, case_root):
    if case_root.is_symlink() or not case_root.is_dir():
        raise SystemExit(f"visual artifact case root is missing: {case_root}")
    rows = parse_visual_inventory(inventory_path)
    expected_paths = set()
    for row in rows:
        relative = safe_posix_relative(row["relative_path"], "visual artifact path")
        expected_paths.add(relative)
        artifact = case_root / Path(*relative.parts)
        if artifact.is_symlink() or not artifact.is_file():
            raise SystemExit(f"visual artifact is missing or non-regular: {relative}")
        try:
            resolved_root = case_root.resolve(strict=True)
            resolved_artifact = artifact.resolve(strict=True)
        except OSError as error:
            raise SystemExit(f"unable to resolve visual artifact: {relative}") from error
        if not resolved_artifact.is_relative_to(resolved_root):
            raise SystemExit(f"visual artifact resolves outside case root: {relative}")
        if artifact.stat().st_size != int(row["bytes"]):
            raise SystemExit(f"visual artifact byte count mismatch: {relative}")
        if digest(artifact) != row["sha256"]:
            raise SystemExit(f"visual artifact SHA-256 mismatch: {relative}")
        if row["artifact_type"] == "html":
            try:
                normalized = artifact.read_text(encoding="utf-8").lower()
            except UnicodeDecodeError as error:
                raise SystemExit(f"visual HTML is not UTF-8: {relative}") from error
            if not all(token in normalized for token in ("<html", "<body", "</html>")):
                raise SystemExit(f"visual HTML structure is invalid: {relative}")
        else:
            width, height, _ = decoded_png_rgba(artifact)
            if width != int(row["width_px"]) or height != int(row["height_px"]):
                raise SystemExit(f"visual PNG dimensions mismatch: {relative}")
    actual_paths = set()
    for directory, suffix in (("report", ".html"), ("figures", ".png")):
        directory_root = case_root / directory
        if directory_root.is_symlink() or not directory_root.is_dir():
            raise SystemExit(f"visual artifact directory is missing: {directory_root}")
        for artifact in directory_root.iterdir():
            if artifact.is_symlink() or not artifact.is_file():
                raise SystemExit("visual artifact collection contains a non-regular entry")
            if artifact.suffix.lower() != suffix:
                raise SystemExit(f"unsupported or unbound visual artifact: {artifact}")
            actual_paths.add(PurePosixPath(directory, artifact.name))
    if actual_paths != expected_paths:
        raise SystemExit("visual artifact inventory coverage mismatch")
    return visual_structure(inventory_path)

def visual_inventory_case_id(public_root, path):
    relative = PurePosixPath(path.relative_to(public_root).as_posix())
    if (
        relative.parts[:1] != ("observed_normalized",)
        or len(relative.parts) != 3
        or relative.name != "visual_artifact_inventory.tsv"
    ):
        raise SystemExit(f"unexpected visual inventory path: {relative}")
    case_id = relative.parts[1]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", case_id):
        raise SystemExit(f"unsafe visual inventory case ID: {case_id!r}")
    return case_id

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
    if candidate.is_file()
    and candidate.relative_to(root).as_posix() != "artifacts.sha256"
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
    "mito-overview": "0.3.0", "biopython": "1.87",
    "pysam": "0.24.0", "pandas": "3.0.3",
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

gm11906_metadata_path = (
    root / "public_provenance/GM11906_NCBI_source_metadata.json"
)
gm11906_metadata_sha256 = (
    "01be488b9dc6bfce0726304be95db4259b1a85a53ac8e620cba4c337842d3185"
)
if digest(gm11906_metadata_path) != gm11906_metadata_sha256:
    raise SystemExit("GM11906 official NCBI metadata snapshot SHA-256 mismatch")
gm11906_metadata = json.loads(gm11906_metadata_path.read_text(encoding="utf-8"))
gm11906_records = gm11906_metadata.get("records")
if (
    gm11906_metadata.get("schema_version") != "1.0"
    or gm11906_metadata.get("resource_id")
    != "gm11906_ncbi_public_source_metadata_v1"
    or gm11906_metadata.get("authority") != "NCBI GEO and NCBI SRA"
    or not isinstance(gm11906_records, list)
):
    raise SystemExit("GM11906 official NCBI metadata snapshot identity mismatch")
canonical_gm11906_records = json.dumps(
    gm11906_records, sort_keys=True, separators=(",", ":"), ensure_ascii=True
).encode("ascii")
gm11906_records_sha256 = hashlib.sha256(canonical_gm11906_records).hexdigest()
if gm11906_records_sha256 != gm11906_metadata.get("records_sha256"):
    raise SystemExit("GM11906 official NCBI metadata records SHA-256 mismatch")
gm11906_by_run = {
    record.get("run_accession"): record
    for record in gm11906_records
    if isinstance(record, dict)
}
expected_gm11906_accessions = {
    "SRR10804585": ("SRX7478441", "SRS5922054", "SAMN13699362", "GSM4238454"),
    "SRR10804590": ("SRX7478446", "SRS5922059", "SAMN13699398", "GSM4238459"),
    "SRR10804657": ("SRX7478513", "SRS5922125", "SAMN13699338", "GSM4238526"),
}
if len(gm11906_by_run) != 3 or set(gm11906_by_run) != set(
    expected_gm11906_accessions
):
    raise SystemExit("GM11906 official NCBI metadata run inventory mismatch")
for run_accession, identifiers in expected_gm11906_accessions.items():
    record = gm11906_by_run[run_accession]
    if (
        (
            record.get("experiment_accession"),
            record.get("sra_sample_accession"),
            record.get("biosample_accession"),
            record.get("geo_accession"),
        )
        != identifiers
        or record.get("bioproject_accession") != "PRJNA598179"
        or record.get("cell_line") != "GM11906"
        or record.get("organism") != "Homo sapiens"
        or record.get("library_strategy") != "ATAC-seq"
        or record.get("library_layout") != "PAIRED"
        or record.get("instrument_model") != "NextSeq 550"
    ):
        raise SystemExit(
            f"GM11906 official NCBI metadata captured-value mismatch for {run_accession}"
        )
    source_files = record.get("source_files")
    if not isinstance(source_files, list) or {
        item.get("format") for item in source_files if isinstance(item, dict)
    } != {"NCBI_SRA_EFETCH_XML", "NCBI_GEO_SOFT"}:
        raise SystemExit(
            f"GM11906 official NCBI metadata source evidence mismatch for {run_accession}"
        )
    for source in source_files:
        if (
            not str(source.get("url", "")).startswith("https://")
            or "ncbi.nlm.nih.gov/" not in str(source.get("url", ""))
            or re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256", ""))) is None
            or not isinstance(source.get("bytes"), int)
            or source["bytes"] <= 0
        ):
            raise SystemExit(
                f"GM11906 official NCBI metadata source evidence is invalid for {run_accession}"
            )

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

frozen_oracle_sha256 = "221f6d4eba86d5d37e674aeaed553ac5d9829a5a216d116db38da35d58448e92"
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

def contract_add_text(hasher, value):
    encoded = value.encode("utf-8")
    hasher.update(len(encoded).to_bytes(8, "big"))
    hasher.update(encoded)

def contract_tsv_header(path):
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            header = tuple(next(csv.reader(handle, delimiter="\t")))
    except StopIteration as error:
        raise SystemExit(f"compact-contract TSV has no header: {path}") from error
    if not header or any(not field for field in header) or len(header) != len(set(header)):
        raise SystemExit(f"compact-contract TSV has an invalid header: {path}")
    return header

def candidate_contract_fingerprint(path):
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = tuple(next(reader))
        except StopIteration as error:
            raise SystemExit("compact candidate table has no header") from error
        rows = [tuple(row) for row in reader]
    if (
        not header
        or any(not field for field in header)
        or len(header) != len(set(header))
        or any(len(row) != len(header) for row in rows)
    ):
        raise SystemExit("compact candidate table is malformed")
    hasher = hashlib.sha256(b"mito-overview:candidate-table:v1\0")
    contract_add_text(hasher, path.name)
    hasher.update(len(header).to_bytes(8, "big"))
    for field in header:
        contract_add_text(hasher, field)
    ordered = sorted(rows)
    hasher.update(len(ordered).to_bytes(8, "big"))
    for row in ordered:
        for value in row:
            contract_add_text(hasher, value)
    return hasher.hexdigest()

def read_contract_schema_manifest(path):
    if path.is_symlink() or not path.is_file():
        raise SystemExit("compact summary-schema manifest is missing or unsafe")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != ("relative_path", "header_json"):
            raise SystemExit("compact summary-schema manifest header mismatch")
        rows = list(reader)
    if not rows:
        raise SystemExit("compact summary-schema manifest is empty")
    entries = []
    seen = set()
    for row in rows:
        raw = row["relative_path"]
        relative = PurePosixPath(raw)
        if (
            not raw
            or relative.is_absolute()
            or relative.as_posix() != raw
            or any(part in ("", ".", "..") for part in relative.parts)
            or relative.suffix != ".tsv"
            or raw in seen
        ):
            raise SystemExit("compact summary-schema manifest path is invalid")
        seen.add(raw)
        try:
            header = json.loads(row["header_json"])
        except json.JSONDecodeError as error:
            raise SystemExit("compact summary-schema header JSON is invalid") from error
        if (
            not isinstance(header, list)
            or not header
            or any(not isinstance(field, str) or not field for field in header)
            or len(header) != len(set(header))
        ):
            raise SystemExit("compact summary-schema TSV header is invalid")
        entries.append((raw, tuple(header)))
    if [relative for relative, _ in entries] != sorted(seen):
        raise SystemExit("compact summary-schema paths are not sorted")
    return entries

def compact_contract_fingerprints(case_root):
    if case_root.is_symlink() or not case_root.is_dir():
        raise SystemExit("compact-contract case directory is missing or unsafe")
    entries = list(case_root.iterdir())
    expected_names = {
        "mito_heteroplasmy_candidates.tsv", "summary_schema_manifest.tsv",
    }
    if (
        {entry.name for entry in entries} != expected_names
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise SystemExit("compact-contract case inventory mismatch")
    candidate = case_root / "mito_heteroplasmy_candidates.tsv"
    schemas = read_contract_schema_manifest(case_root / "summary_schema_manifest.tsv")
    schema_by_path = dict(schemas)
    if schema_by_path.get(candidate.name) != contract_tsv_header(candidate):
        raise SystemExit("compact candidate header disagrees with schema manifest")
    inventory = hashlib.sha256(b"mito-overview:summary-inventory:v1\0")
    schema_hasher = hashlib.sha256(b"mito-overview:summary-schemas:v1\0")
    for relative, header in schemas:
        contract_add_text(inventory, relative)
        contract_add_text(schema_hasher, relative)
        schema_hasher.update(len(header).to_bytes(8, "big"))
        for field in header:
            contract_add_text(schema_hasher, field)
    return {
        "candidate_table_sha256": candidate_contract_fingerprint(candidate),
        "summary_inventory_sha256": inventory.hexdigest(),
        "summary_schema_sha256": schema_hasher.hexdigest(),
    }, len(schemas)

def validate_compact_contracts(contracts_root, oracle_rows):
    if contracts_root.is_symlink() or not contracts_root.is_dir():
        raise SystemExit("observed_contracts evidence is missing or unsafe")
    expected_by_case = {
        case_id: oracle_rows[key]
        for key, case_ids in oracle_cases.items()
        for case_id in case_ids
    }
    entries = list(contracts_root.iterdir())
    if any(entry.is_symlink() or not entry.is_dir() for entry in entries):
        raise SystemExit("observed_contracts contains an unsafe entry")
    observed_cases = {entry.name for entry in entries}
    if observed_cases != set(expected_by_case):
        raise SystemExit("observed_contracts case inventory mismatch")
    for case_id, expected in expected_by_case.items():
        observed, table_count = compact_contract_fingerprints(
            contracts_root / case_id
        )
        for field in (
            "candidate_table_sha256", "summary_inventory_sha256",
            "summary_schema_sha256",
        ):
            if observed[field] != expected[field]:
                raise SystemExit(
                    f"compact-contract fingerprint mismatch for {case_id}.{field}"
                )
        if table_count != int(expected["summary_tsv_count"]):
            raise SystemExit(f"compact-contract summary count mismatch for {case_id}")

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
    module_statuses = (
        "mito_qc_module_status", "heteroplasmy_module_status",
        "deletions_module_status", "copy_number_module_status",
        "feature_annotation_module_status", "cosegregation_module_status",
        "gene_summary_module_status", "numt_qc_module_status",
        "identity_qc_module_status", "variant_consequence_module_status",
        "circularity_qc_module_status", "methylation_exploratory_module_status",
        "phymer_haplogroup_module_status", "mvtool_annotation_module_status",
    )
    interpretation_statuses = (
        "numt_interpretation_status", "numt_interpretation_reason_code",
    )
    fingerprints = (
        "candidate_table_sha256", "summary_inventory_sha256",
        "summary_schema_sha256",
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
            for field in fingerprints:
                required[f"{case_id}.{field}"] = row[field]
            for field in module_statuses:
                if row[field]:
                    required[f"{case_id}.module_status.{field}"] = row[field]
            for field in interpretation_statuses:
                if row[field]:
                    required[f"{case_id}.interpretation_status.{field}"] = row[field]
            if row["m8344_alt_fraction"]:
                required[f"{case_id}.m8344_alt_fraction"] = row[
                    "m8344_alt_fraction"
                ]
            if row["m8344_alt_count"]:
                for field in (
                    "m8344_callable_depth", "m8344_alt_count", "m8344_alt_forward",
                    "m8344_alt_reverse", "m8344_feature_label",
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
unexpected_assertions = sorted(set(assertions) - set(required_assertions))
if unexpected_assertions:
    raise SystemExit(
        f"oracle assertion report contains unexpected rows: {unexpected_assertions}"
    )
for assertion_id, expected in required_assertions.items():
    if not semantic_equal(assertions[assertion_id]["expected"], expected):
        raise SystemExit(f"oracle assertion value drift: {assertion_id}")

validate_compact_contracts(root / "observed_contracts", oracle)

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
    r"/private/tmp(?:/[^\s'\";]*)?",
    r"/mnt(?:/[^\s'\";]*)?", r"/Volumes(?:/[^\s'\";]*)?",
    r"(?i)[A-Z]:\\Users\\[^\\\s]+",
    r"/(?:group|scratch)/(?:g/)?xgai(?:/[^\s'\";]*)?",
    r"(?i)\bqfs\d*\.rcc\.mcw\.edu\b",
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
        "measurement_id", "case_id", "candidate_commit", "command_path",
        "command_sha256", "packaged_command_sha256", "log_path", "log_sha256",
        "packaged_log_sha256",
        "wall_seconds", "user_cpu_seconds",
        "system_cpu_seconds",
        "max_rss_kb", "broad_declared_input_inventory_file_count",
        "broad_declared_input_inventory_bytes",
        "changed_or_new_output_inventory_file_count",
        "changed_or_new_output_inventory_bytes",
        "broad_declared_input_inventory_scope",
        "changed_or_new_output_inventory_scope", "io_measurement_method",
        "threads", "platform", "measurement_status", "reason",
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

expected_claim_rows = [
    {
        "claim_id": "C1",
        "bounded_claim": "Shared filtered allele counting is deterministic on known-answer fixtures",
        "evidence": "unit_known_answer; synthetic_longread_smoke; expected/TOY-SR-001.expected_alleles.tsv",
        "limitation": "Reporting thresholds are not clinically calibrated",
    },
    {
        "claim_id": "C2",
        "bounded_claim": "mvTool is offline by default with deterministic fixture coverage",
        "evidence": "unit_known_answer; synthetic_longread_smoke",
        "limitation": "No claim of live service availability",
    },
    {
        "claim_id": "C3",
        "bounded_claim": "Minimal standalone alignment contracts are preflighted",
        "evidence": "unit_known_answer; strict_generic_dry_run; standalone_minimal_smoke",
        "limitation": "Optional sidecars remain user supplied",
    },
    {
        "claim_id": "C4",
        "bounded_claim": "The WGS fixture reports a 100/10 mt:nuclear depth ratio of 10.0",
        "evidence": "unit_known_answer; expected/TOY-WGS-001.expected_copy_proxy.tsv",
        "limitation": "Experimental depth proxy, not absolute copies per diploid cell",
    },
    {
        "claim_id": "C5",
        "bounded_claim": "mt-only references suppress categorical NUMT interpretation",
        "evidence": "unit_known_answer; gm12878_default_run1; gm12878_repeatability",
        "limitation": "Alignment-ambiguity QC is not a formal NUMT classifier",
    },
    {
        "claim_id": "C6",
        "bounded_claim": "Public proof-of-principle workflows reproduce normalized TSVs",
        "evidence": "gm11906_repeatability; gm12878_repeatability; filter_profile_results.tsv",
        "limitation": "Not an analytical-performance or diagnostic benchmark",
    },
]
if evidence_rows["claim_evidence_matrix.tsv"] != expected_claim_rows:
    raise SystemExit("claim-evidence matrix does not match the frozen bounded contract")

with (root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
    claim_case_reader = csv.DictReader(handle, delimiter="\t")
    if tuple(claim_case_reader.fieldnames or ()) != (
        "case_id", "category", "input_available", "expected_available", "verdict", "detail",
    ):
        raise SystemExit("cases.tsv schema mismatch while resolving claim evidence")
    claim_case_rows = list(claim_case_reader)
claim_cases = {row["case_id"]: row for row in claim_case_rows}
if len(claim_cases) != len(claim_case_rows):
    raise SystemExit("duplicate validation case while resolving claim evidence")
for row in expected_claim_rows:
    for token in (part.strip() for part in row["evidence"].split(";")):
        if token in claim_cases:
            if claim_cases[token]["verdict"] != "PASS":
                raise SystemExit(f"claim references non-PASS case: {token}")
        elif token.startswith("expected/") or token == "filter_profile_results.tsv":
            path = root / token
            if not path.is_file() or path.stat().st_size == 0:
                raise SystemExit(f"claim evidence file is unavailable: {token}")
        else:
            raise SystemExit(f"claim references unknown evidence token: {token}")

handoff_metrics = (
    ("candidate_sites", "sites"),
    ("accepted_observations", "observations"),
    ("excluded_observations", "observations"),
    ("m8344_A_G_alt_allele_fraction", "fraction"),
)
expected_handoff_rows = []
for profile_row in profile_rows:
    for metric, unit in handoff_metrics:
        value = profile_row.get(metric, "")
        if value == "":
            continue
        expected_handoff_rows.append(
            {
                "result_id": f"{profile_row['case_id']}:{metric}",
                "dataset": profile_row["dataset"],
                "metric": metric,
                "value": value,
                "unit": unit,
                "source_table": "filter_profile_results.tsv",
                "claim_boundary": "descriptive fixed-input result; not diagnostic performance",
            }
        )
if evidence_rows["manuscript_handoff.tsv"] != expected_handoff_rows:
    raise SystemExit("manuscript-handoff values do not match filter_profile_results.tsv")

states = {"ok", "not_configured", "not_applicable", "not_evaluable", "unavailable", "failed"}
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
    run_accession: (
        "GM11906 pooled single-cell ATAC-seq pseudo-bulk",
        record["bioproject_accession"],
        record["cell_line"],
        "ILLUMINA",
        record["instrument_model"],
        record["library_strategy"],
    )
    for run_accession, record in gm11906_by_run.items()
}
expected_source_metadata["SRR18110025"] = (
        "GM12878 ONT targeted-mt proof-of-principle", "PRJNA809571",
        "GM12878", "OXFORD_NANOPORE", "GridION", "OTHER",
    )
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
    official = gm11906_by_run.get(run_accession)
    if official is not None:
        expected_manifest_identity = (
            official["biosample_accession"],
            official["geo_accession"],
            official["sample_title"],
            official["cell_line"],
            official["library_strategy"],
        )
        observed_manifest_identity = (
            first["sample_accession"],
            first["sample_alias"],
            first["sample_title"],
            first["source_sample_id"],
            first["library_strategy"],
        )
        if observed_manifest_identity != expected_manifest_identity:
            raise SystemExit(
                f"public input is not bound to official NCBI metadata: {run_accession}"
            )
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
    if official is not None and row["metadata_recorded_utc"] != gm11906_metadata[
        "retrieval_completed_utc"
    ]:
        raise SystemExit(
            f"public source metadata timestamp is not bound to NCBI snapshot: {run_accession}"
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

def feature_annotation_status(path):
    fields, _ = read_rows(path)
    if len(fields) != len(set(fields)):
        raise SystemExit(f"duplicate feature-annotation column: {path}")
    if fields == ("metric", "value"):
        status = metric_map(path).get("status", "")
        if not status:
            raise SystemExit(f"feature-annotation status is missing: {path}")
        gated_states = {
            "not_configured", "not_applicable", "not_evaluable", "unavailable", "failed",
        }
        if status not in gated_states:
            raise SystemExit(f"invalid explicit feature-annotation status {status!r}: {path}")
        return status
    successful_fields = (
        "feature_class", "feature_label", "candidate_sites",
        "mean_alt_allele_fraction", "mean_heteroplasmy",
        "control_region_annotation_status", "control_region_annotation_reason_code",
        "control_region_annotation_method", "control_region_annotation_mode",
        "control_region_reference_accession",
        "control_region_configured_sequence_sha256",
        "control_region_canonical_sequence_sha256",
        "control_region_exact_sequence_match",
        "control_region_configured_sequence_length",
        "control_region_canonical_sequence_length",
        "control_region_intervals_applied",
    )
    if fields == successful_fields:
        return "ok"
    raise SystemExit(
        f"feature-annotation output has neither a status table nor the successful schema: {path}"
    )

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
        ("mito_qc_module_status", "mito_qc_summary.tsv", "status"),
        ("heteroplasmy_module_status", "mito_heteroplasmy_summary.tsv", "status"),
        ("deletions_module_status", "mito_deletion_summary.tsv", "status"),
        ("copy_number_module_status", "mito_copy_number_summary.tsv", "status"),
        ("feature_annotation_module_status", "mito_feature_annotation_summary.tsv", "status"),
        ("cosegregation_module_status", "mito_cosegregation_summary.tsv", "status"),
        ("gene_summary_module_status", "mito_gene_summary_run_summary.tsv", "status"),
        ("numt_qc_module_status", "mito_numt_qc_summary.tsv", "status"),
        ("identity_qc_module_status", "mito_identity_qc_summary.tsv", "status"),
        ("variant_consequence_module_status", "mito_variant_consequence_summary.tsv", "status"),
        ("circularity_qc_module_status", "mito_circularity_qc_summary.tsv", "status"),
        ("methylation_exploratory_module_status", "mito_methylation_exploratory_summary.tsv", "status"),
        ("phymer_haplogroup_module_status", "mito_phymer_haplogroup_summary.tsv", "status"),
        ("mvtool_annotation_module_status", "mito_mvtool_annotation_summary.tsv", "status"),
        ("numt_interpretation_status", "mito_numt_qc_summary.tsv", "numt_interpretation_status"),
        ("numt_interpretation_reason_code", "mito_numt_qc_summary.tsv", "reason_code"),
    )
    loaded = {}
    for oracle_field, filename, metric in status_specs:
        expected = default_oracle[oracle_field]
        if expected:
            if oracle_field == "feature_annotation_module_status":
                if feature_annotation_status(run1 / filename) != expected:
                    raise SystemExit(
                        f"normalized module status mismatch: {dataset_name} {oracle_field}"
                    )
                continue
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
    short_manifest.get("schema_version") != "1.0"
    or short_manifest.get("provenance_type") != "public_alignment"
    or short_manifest.get("dataset_id") != "GM11906_pooled_scATAC"
):
    raise SystemExit("short-read alignment provenance identity mismatch")
expected_short_derivation = {
    "derivation_id": "bwa-mem-samtools-sort-v1",
    "command_template": (
        "bwa mem -t {threads} {reference_fasta} {combined_r1} {combined_r2} "
        "| samtools sort -@ {threads} -o {alignment_bam}"
    ),
    "parameters": {"threads": "4"},
    "tool_versions": {
        "bwa": "0.7.19-r1273",
        "samtools": "samtools 1.23.1",
    },
}
if short_manifest.get("derivation") != expected_short_derivation:
    raise SystemExit("short-read alignment derivation mismatch")
def unique_labeled_inputs(value, description):
    if not isinstance(value, list) or not value:
        raise SystemExit(f"{description} alignment inputs are missing")
    indexed = {}
    for record in value:
        if not isinstance(record, dict):
            raise SystemExit(f"{description} alignment input is not an object")
        if set(record) != {"label", "name", "bytes", "md5", "sha256"}:
            raise SystemExit(
                f"{description} alignment input has an invalid digest field inventory"
            )
        label = record.get("label")
        if not isinstance(label, str) or not label:
            raise SystemExit(f"{description} alignment input label is invalid")
        if (
            not isinstance(record.get("name"), str)
            or not record["name"]
            or Path(record["name"]).name != record["name"]
            or isinstance(record.get("bytes"), bool)
            or not isinstance(record["bytes"], int)
            or record["bytes"] <= 0
            or not isinstance(record.get("md5"), str)
            or re.fullmatch(r"[0-9a-f]{32}", record["md5"]) is None
            or not isinstance(record.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
        ):
            raise SystemExit(f"{description} alignment input digest metadata is invalid")
        if label in indexed:
            raise SystemExit(f"{description} alignment has duplicate input label: {label}")
        indexed[label] = record
    return indexed

short_inputs = unique_labeled_inputs(
    short_manifest.get("public_inputs", []), "short-read"
)
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
expected_source_libraries = []
for run_accession in ("SRR10804585", "SRR10804590", "SRR10804657"):
    record = gm11906_by_run[run_accession]
    record_sha256 = hashlib.sha256(
        json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
    ).hexdigest()
    expected_source_libraries.append(
        (
            run_accession,
            record["geo_accession"],
            record["cell_line"],
            record["library_strategy"],
            "single_cell_library",
            "pooled_pseudobulk",
            "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc="
            + record["geo_accession"],
            gm11906_metadata_sha256,
            record_sha256,
        )
    )
observed_source_libraries = [
    tuple(row[field] for field in source_fields) for row in source_libraries
]
if source_fields != (
    "run_accession", "geo_accession", "source_sample_id", "library_strategy",
    "library_unit", "combination_role", "source_record_url",
    "metadata_snapshot_sha256", "metadata_record_sha256",
) or observed_source_libraries != expected_source_libraries:
    raise SystemExit("GM11906 three-cell source-library derivation mismatch")

long_subset = json.loads(
    (root / "public_provenance/GM12878_ONT_longread.fastq_subset.provenance.json")
    .read_text(encoding="utf-8")
)
if (
    long_subset.get("schema_version") != "1.0"
    or long_subset.get("provenance_type")
    != "deterministic_fastq_query_name_subset"
    or long_subset.get("dataset_id") != "GM12878_SRR18110025_ONT"
):
    raise SystemExit("long-read subset provenance identity mismatch")
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
expected_subset_fastq = {
    "name": "SRR18110025.deterministic-qnames-1000.fastq.gz",
    "bytes": 10721431,
    "md5": "a337abc2691753c56f030f7f523dd750",
    "sha256": "40e203ead1d621bfec8caa3c5d18cd1e7e70c08da27008a73364812b6871df33",
}
expected_selected_names = {
    "name": "SRR18110025.deterministic-qnames-1000.fastq.gz.selected_qnames.txt",
    "bytes": 18422,
    "md5": "64d606e56bf8dd58ad68baad28898e18",
    "sha256": "3444cc7db3dcf78bea807d8bcc6686883a7759d128288c1d26aeae077a771a19",
}
expected_selection = {
    "algorithm": "smallest_sha256_seeded_query_names_v1",
    "requested_query_names": 1000,
    "selected_query_names": 1000,
    "source_records_seen": 193043,
    "subset_records_written": 1000,
    "seed": "mito-overview-v0.3.0-GM12878-SRR18110025",
}
if (
    long_subset.get("subset_fastq") != expected_subset_fastq
    or long_subset.get("selected_query_names") != expected_selected_names
    or selection != expected_selection
    or selected_names_path.stat().st_size != expected_selected_names["bytes"]
    or digest(selected_names_path) != expected_selected_names["sha256"]
    or len(selected_names) != 1000
    or len(set(selected_names)) != 1000
):
    raise SystemExit("long-read deterministic subset derivation mismatch")

long_manifest_path = (
    root / "public_provenance/GM12878_ONT_longread.reduced_alignment.provenance.json"
)
long_manifest = json.loads(long_manifest_path.read_text(encoding="utf-8"))
if (
    long_manifest.get("schema_version") != "1.0"
    or long_manifest.get("provenance_type") != "public_alignment"
    or long_manifest.get("dataset_id")
    != "GM12878_SRR18110025_ONT_reduced_qn1000"
):
    raise SystemExit("long-read alignment provenance identity mismatch")
expected_long_derivation = {
    "derivation_id": "minimap2-map-ont-deterministic-fastq-subset-mapped-only-v1",
    "command_template": (
        "minimap2 -t {threads} -ax map-ont {reference_mmi} "
        "{deterministic_subset_fastq} | samtools view -@ {threads} -b -F 4 "
        "| samtools sort -@ {threads} -o {alignment_bam}"
    ),
    "parameters": {
        "selected_query_names": "1000",
        "selection_seed": "mito-overview-v0.3.0-GM12878-SRR18110025",
        "threads": "4",
        "unmapped_filter_flag": "4",
    },
    "tool_versions": {
        "minimap2": "2.31-r1302",
        "samtools": "samtools 1.23.1",
    },
}
if long_manifest.get("derivation") != expected_long_derivation:
    raise SystemExit("long-read alignment derivation mismatch")
long_inputs = unique_labeled_inputs(
    long_manifest.get("public_inputs", []), "long-read"
)
expected_long_labels = {
    "SRR18110025_full_fastq",
    "deterministic_subset_fastq",
    "deterministic_subset_manifest",
    "selected_query_names",
}
if set(long_inputs) != expected_long_labels:
    raise SystemExit("long-read alignment input inventory is incomplete")

def without_label(record):
    return {key: value for key, value in record.items() if key != "label"}

if (
    without_label(long_inputs["SRR18110025_full_fastq"]) != long_source
    or without_label(long_inputs["deterministic_subset_fastq"])
    != expected_subset_fastq
    or without_label(long_inputs["selected_query_names"])
    != expected_selected_names
):
    raise SystemExit("long-read alignment input linkage mismatch")
subset_manifest_input = long_inputs["deterministic_subset_manifest"]
subset_manifest_path = (
    root / "public_provenance/GM12878_ONT_longread.fastq_subset.provenance.json"
)
if (
    subset_manifest_input.get("name")
    != "SRR18110025.deterministic-qnames-1000.fastq.gz.provenance.json"
    or subset_manifest_input.get("bytes") != subset_manifest_path.stat().st_size
    or subset_manifest_input.get("md5") != md5_digest(subset_manifest_path)
    or subset_manifest_input.get("sha256") != digest(subset_manifest_path)
):
    raise SystemExit("long-read subset-manifest linkage mismatch")

measurement_ids = set()
resource_case_ids = set()
resource_candidate_commits = set()
resource_thread_settings = {
    "fresh_clone_candidate_commit": "mixed",
    "package_build": "not_applicable",
    "unit_known_answer": "mixed",
    "cli_step_listing": "not_applicable",
    "strict_generic_dry_run": "4",
    "synthetic_longread_smoke": "1",
    "synthetic_shortread_smoke": "1",
    "synthetic_longread_nomethyl_smoke": "1",
    "standalone_minimal_smoke": "4",
    "public_cache_prepare": "not_applicable",
    "public_validation_matrix": "4",
}
for row in evidence_rows["resource_usage.tsv"]:
    measurement_id = row["measurement_id"].lower()
    if (
        not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            measurement_id,
            flags=re.IGNORECASE,
        )
        or measurement_id in measurement_ids
    ):
        raise SystemExit(f"invalid or duplicate resource measurement ID: {measurement_id}")
    measurement_ids.add(measurement_id)
    case_id = row["case_id"]
    if case_id in resource_case_ids:
        raise SystemExit(f"duplicate resource case ID: {case_id}")
    resource_case_ids.add(case_id)
    resource_candidate_commits.add(row["candidate_commit"])
    expected_paths = {
        "command_path": f"commands/{case_id}.sh",
        "log_path": f"logs/{case_id}.log",
    }
    for path_field, expected_path in expected_paths.items():
        if row[path_field] != expected_path:
            raise SystemExit(f"resource {path_field} mismatch for {case_id}")
    for original_digest_field in ("command_sha256", "log_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", row[original_digest_field]):
            raise SystemExit(
                f"invalid original execution digest for {case_id}: "
                f"{original_digest_field}"
            )
    for path_field, digest_field in (
        ("command_path", "packaged_command_sha256"),
        ("log_path", "packaged_log_sha256"),
    ):
        evidence_path = root / row[path_field]
        if (
            not evidence_path.is_file()
            or evidence_path.is_symlink()
            or not re.fullmatch(r"[0-9a-f]{64}", row[digest_field])
            or digest(evidence_path) != row[digest_field]
        ):
            raise SystemExit(
                f"resource {digest_field} does not bind {path_field} for {case_id}"
            )
    status = row["measurement_status"]
    if status != "measured":
        raise SystemExit(f"required resource measurement is not measured: {case_id}")
    if row["threads"] != resource_thread_settings.get(case_id):
        raise SystemExit(f"resource thread setting mismatch: {case_id}")
    numeric_values = {}
    for field in (
        "wall_seconds", "user_cpu_seconds", "system_cpu_seconds", "max_rss_kb",
        "broad_declared_input_inventory_bytes",
        "changed_or_new_output_inventory_bytes",
    ):
        try:
            value = float(row[field])
        except ValueError as error:
            raise SystemExit(f"invalid finite resource measurement {field}") from error
        if not math.isfinite(value):
            raise SystemExit(f"invalid finite resource measurement {field}")
        numeric_values[field] = value
    for field in (
        "broad_declared_input_inventory_file_count",
        "changed_or_new_output_inventory_file_count",
    ):
        try:
            value = int(row[field])
        except ValueError as error:
            raise SystemExit(f"invalid resource inventory count {field}") from error
        if value < 0 or str(value) != row[field]:
            raise SystemExit(f"invalid resource inventory count {field}")
        numeric_values[field] = value
    for field in ("wall_seconds", "max_rss_kb"):
        if numeric_values[field] <= 0:
            raise SystemExit(f"resource measurement must be positive: {field}")
    for field in ("user_cpu_seconds", "system_cpu_seconds"):
        if numeric_values[field] < 0:
            raise SystemExit(f"resource measurement must be nonnegative: {field}")
    if numeric_values["broad_declared_input_inventory_file_count"] <= 0:
        raise SystemExit("resource input inventory file count must be positive")
    if numeric_values["broad_declared_input_inventory_bytes"] <= 0:
        raise SystemExit("resource input inventory bytes must be positive")
    for field in (
        "changed_or_new_output_inventory_file_count",
        "changed_or_new_output_inventory_bytes",
    ):
        if numeric_values[field] < 0:
            raise SystemExit(f"resource measurement must be nonnegative: {field}")
    if (
        row["io_measurement_method"]
        != "broad_declared_inputs_and_changed_or_new_outputs_v3"
    ):
        raise SystemExit("invalid resource I/O measurement method")
    if row["broad_declared_input_inventory_scope"] != (
        "repository_root;cache_root;validation_root"
    ):
        raise SystemExit("invalid broad declared input inventory scope")
    if row["changed_or_new_output_inventory_scope"] != (
        "cache_root;validation_root"
    ):
        raise SystemExit("invalid changed/new output inventory scope")

required_resource_cases = {
    "fresh_clone_candidate_commit", "package_build", "unit_known_answer",
    "cli_step_listing", "strict_generic_dry_run", "synthetic_longread_smoke",
    "synthetic_shortread_smoke", "synthetic_longread_nomethyl_smoke",
    "standalone_minimal_smoke", "public_cache_prepare", "public_validation_matrix",
}
if resource_case_ids != required_resource_cases:
    raise SystemExit("resource case inventory mismatch")

public_cache_resources = [
    row
    for row in evidence_rows["resource_usage.tsv"]
    if row["case_id"] == "public_cache_prepare"
]
if len(public_cache_resources) != 1:
    raise SystemExit("missing or duplicate public_cache_prepare resource evidence")
public_cache_resource = public_cache_resources[0]
raw_fastq_bytes = sum(int(row["bytes"]) for row in raw_inputs)
if (
    public_cache_resource["measurement_status"] != "measured"
    or int(public_cache_resource["changed_or_new_output_inventory_bytes"])
    < raw_fastq_bytes
):
    raise SystemExit(
        "public_cache_prepare changed/new output inventory excludes raw downloads"
    )

for name in ("figure_provenance.tsv", "table_provenance.tsv"):
    for row in evidence_rows[name]:
        relative = Path(row["packet_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise SystemExit(f"unsafe provenance packet path in {name}")
        artifact = root / relative
        if not artifact.is_file() or digest(artifact) != row["sha256"]:
            raise SystemExit(f"provenance artifact mismatch in {name}: {relative}")

pixel_reports = {
    "GM11906": (
        "gm11906_default_run1", "gm11906_default_run2",
        "decoded_pixel_hashes/GM11906.tsv",
    ),
    "GM12878": (
        "gm12878_default_run1", "gm12878_default_run2",
        "decoded_pixel_hashes/GM12878.tsv",
    ),
}
decoded_pixel_identity = []
actual_pixel_files = {
    path.relative_to(root).as_posix()
    for path in (root / "decoded_pixel_hashes").iterdir()
    if path.is_file() and not path.is_symlink()
}
if actual_pixel_files != {value[2] for value in pixel_reports.values()}:
    raise SystemExit("decoded-pixel evidence inventory mismatch")
for dataset, (case_id, repeat_case_id, relative) in pixel_reports.items():
    with (root / relative).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != (
            "path", "width_px", "height_px", "decoded_rgba_sha256",
        ):
            raise SystemExit(f"decoded-pixel schema mismatch for {dataset}")
        pixel_rows = list(reader)
    expected_pixels = {
        Path(row["packet_path"]).name: (row["width"], row["height"])
        for row in evidence_rows["figure_provenance.tsv"]
        if row["dataset"] == dataset and row["case_id"] == case_id
    }
    observed_pixels = {}
    for row in pixel_rows:
        name = row["path"]
        if (
            not name
            or Path(name).name != name
            or name in observed_pixels
            or not row["width_px"].isdigit()
            or not row["height_px"].isdigit()
            or int(row["width_px"]) <= 0
            or int(row["height_px"]) <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", row["decoded_rgba_sha256"])
        ):
            raise SystemExit(f"invalid decoded-pixel evidence for {dataset}: {name}")
        figure_paths = (
            root / "figures" / case_id / name,
            root / "figures_repeat2" / repeat_case_id / name,
        )
        for repeat_index, figure_path in enumerate(figure_paths, start=1):
            if not figure_path.is_file() or figure_path.is_symlink():
                raise SystemExit(
                    f"decoded-pixel repeat-{repeat_index} figure is missing "
                    f"for {dataset}: {name}"
                )
            width, height, rgba = decoded_png_rgba(figure_path)
            if (
                str(width) != row["width_px"]
                or str(height) != row["height_px"]
                or hashlib.sha256(rgba).hexdigest() != row["decoded_rgba_sha256"]
            ):
                raise SystemExit(
                    f"decoded-pixel hash does not match repeat-{repeat_index} "
                    f"PNG for {dataset}: {name}"
                )
        observed_pixels[name] = (row["width_px"], row["height_px"])
    if not expected_pixels or observed_pixels != expected_pixels:
        raise SystemExit(
            f"decoded-pixel evidence does not match report-native figures for {dataset}"
        )
    decoded_pixel_identity.append(
        {
            "dataset": dataset,
            "case_id": case_id,
            "path": relative,
            "sha256": digest(root / relative),
            "figure_count": len(pixel_rows),
        }
    )
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
        "final_push_github_actions_run_id", "pull_request_number",
        "pull_request_github_actions_run_id",
        "public_validation_github_actions_run_id",
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
if identity.get("decoded_pixel_evidence") != decoded_pixel_identity:
    raise SystemExit("release identity decoded-pixel evidence mismatch")
environment = parse_environment(root / "environment.txt")
for label, value in (("run", run), ("identity", identity)):
    if value.get("schema_version") != schema:
        raise SystemExit(f"{label} schema version mismatch")
    if value.get("validation_profile") != profile:
        raise SystemExit(f"{label} validation profile mismatch")
expected_public_source_metadata = {
    "path": "public_provenance/GM11906_NCBI_source_metadata.json",
    "sha256": gm11906_metadata_sha256,
    "records_sha256": gm11906_records_sha256,
    "retrieval_completed_utc": gm11906_metadata["retrieval_completed_utc"],
    "authority": gm11906_metadata["authority"],
}
if (
    run.get("public_source_metadata") != expected_public_source_metadata
    or identity.get("public_source_metadata") != expected_public_source_metadata
):
    raise SystemExit("release identity public-source metadata binding mismatch")
if run.get("release_version") != "v0.3.0" or identity.get("release_version") != "v0.3.0":
    raise SystemExit("release identity mismatch")
if identity.get("package_version") != "0.3.0" or identity.get("package_name") != "mito-overview":
    raise SystemExit("package identity mismatch")
commit = identity.get("git_commit")
repository = identity.get("repository")
if not re.fullmatch(r"[0-9a-f]{40}", str(commit or "")):
    raise SystemExit("invalid release commit")
if resource_candidate_commits != {commit}:
    raise SystemExit("resource candidate commit does not match the release commit")
if repository != "https://github.com/elissonnog/mito-overview":
    raise SystemExit("unexpected GitHub repository identity")

resolved_ci_root = root / "acceptance/resolved_ci_environments"
resolved_platforms = ("linux-64", "osx-64", "osx-arm64")
resolved_entries = {path.name: path for path in resolved_ci_root.iterdir()}
if set(resolved_entries) != set(resolved_platforms) or any(
    not path.is_dir() for path in resolved_entries.values()
):
    raise SystemExit("resolved CI platform inventory mismatch")
resolved_runner = {
    "linux-64": ("Linux", "X64", "x86_64"),
    "osx-64": ("macOS", "X64", "x86_64"),
    "osx-arm64": ("macOS", "ARM64", "arm64"),
}
resolved_ci_identity = []
for platform_id in resolved_platforms:
    platform_root = resolved_ci_root / platform_id
    evidence_names = {
        f"conda-{platform_id}.explicit.txt",
        f"pip-{platform_id}.txt",
        f"environment-{platform_id}.yml",
        f"artifact-lock-{platform_id}.explicit.txt",
        "requirements-release-tools.txt",
        f"python-{platform_id}.txt",
    }
    record_name = f"platform-{platform_id}.json"
    expected_files = evidence_names | {record_name}
    observed_files = {
        path.name for path in platform_root.iterdir() if path.is_file()
    }
    if observed_files != expected_files or any(
        not path.is_file() for path in platform_root.iterdir()
    ):
        raise SystemExit(f"resolved CI environment inventory mismatch: {platform_id}")
    record = json.loads((platform_root / record_name).read_text(encoding="utf-8"))
    expected_record_fields = {
        "schema_version", "git_commit", "github_run_id", "job", "platform_id",
        "runner_os", "runner_arch", "machine", "python", "resolved_environment",
        "evidence_files", "evidence_manifest_sha256",
        "source_solver_spec_sha256", "source_artifact_lock_sha256",
        "source_release_tools_lock_sha256",
    }
    runner_os, runner_arch, machine = resolved_runner[platform_id]
    if (
        not isinstance(record, dict)
        or set(record) != expected_record_fields
        or record.get("schema_version") != schema
        or record.get("git_commit") != commit
        or record.get("github_run_id") != run.get("github_actions_run_id")
        or record.get("job") != "Unit and synthetic tests"
        or record.get("platform_id") != platform_id
        or record.get("runner_os") != runner_os
        or record.get("runner_arch") != runner_arch
        or record.get("machine") != machine
        or record.get("python") != "3.12.13"
        or record.get("resolved_environment") is not True
    ):
        raise SystemExit(f"resolved CI environment identity mismatch: {platform_id}")
    if (
        (platform_root / f"python-{platform_id}.txt")
        .read_text(encoding="utf-8").strip()
        != "Python 3.12.13"
    ):
        raise SystemExit(f"resolved CI Python evidence mismatch: {platform_id}")
    evidence_files = record.get("evidence_files")
    if not isinstance(evidence_files, dict) or set(evidence_files) != evidence_names:
        raise SystemExit(f"resolved CI evidence-file inventory mismatch: {platform_id}")
    manifest_lines = []
    for name in sorted(evidence_names):
        path = platform_root / name
        file_sha256 = digest(path)
        file_size = path.stat().st_size
        item = evidence_files.get(name)
        if (
            not isinstance(item, dict)
            or set(item) != {"sha256", "size_bytes"}
            or item.get("sha256") != file_sha256
            or item.get("size_bytes") != file_size
        ):
            raise SystemExit(
                f"resolved CI evidence-file digest mismatch: {platform_id}/{name}"
            )
        manifest_lines.append(f"{name}\t{file_sha256}\t{file_size}\n")
    evidence_manifest_sha256 = hashlib.sha256(
        "".join(manifest_lines).encode("utf-8")
    ).hexdigest()
    solver_name = f"environment-{platform_id}.yml"
    artifact_name = f"artifact-lock-{platform_id}.explicit.txt"
    tools_name = "requirements-release-tools.txt"
    if (
        record.get("evidence_manifest_sha256") != evidence_manifest_sha256
        or record.get("source_solver_spec_sha256")
        != evidence_files[solver_name]["sha256"]
        or record.get("source_artifact_lock_sha256")
        != evidence_files[artifact_name]["sha256"]
        or record.get("source_release_tools_lock_sha256")
        != evidence_files[tools_name]["sha256"]
    ):
        raise SystemExit(f"resolved CI manifest or lock mismatch: {platform_id}")
    def conda_urls(path, expected_platform):
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines.count("@EXPLICIT") != 1:
            raise SystemExit(f"invalid Conda @EXPLICIT marker: {path.name}")
        records = [
            line.strip()
            for line in lines
            if line.strip()
            and not line.startswith("#")
            and line.strip() != "@EXPLICIT"
        ]
        if not records:
            raise SystemExit(f"Conda artifact manifest is empty: {path.name}")
        if len(records) != len(set(records)):
            raise SystemExit(f"duplicate Conda artifact URL: {path.name}")
        for url in records:
            parsed = urlsplit(url)
            path_parts = parsed.path.split("/")
            if (
                parsed.scheme != "https"
                or parsed.hostname != "conda.anaconda.org"
                or parsed.netloc != "conda.anaconda.org"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or not re.fullmatch(r"[0-9a-f]{64}", parsed.fragment)
                or len(path_parts) != 4
                or path_parts[0] != ""
                or path_parts[1] not in {"conda-forge", "bioconda"}
                or path_parts[2] not in {expected_platform, "noarch"}
                or not re.fullmatch(
                    r"[A-Za-z0-9_.+-]+\.(?:conda|tar\.bz2)", path_parts[3]
                )
            ):
                raise SystemExit(f"unapproved Conda artifact URL: {path.name}")
        return set(records)
    if conda_urls(
        platform_root / f"conda-{platform_id}.explicit.txt", platform_id
    ) != conda_urls(
        platform_root / artifact_name, platform_id
    ):
        raise SystemExit(f"resolved CI runtime/source artifact mismatch: {platform_id}")
    resolved_ci_identity.append({
        "path": f"acceptance/resolved_ci_environments/{platform_id}",
        **record,
    })
release_environment = json.loads(
    (root / "acceptance/release_environment_verification.json").read_text(
        encoding="utf-8"
    )
)
release_environment_fields = {
    "schema_version", "platform_id", "python", "artifact_count",
    "tracked_artifact_lock", "tracked_artifact_lock_sha256",
    "runtime_artifact_set_sha256", "repository_commit", "repository_tree",
    "repository_clean", "verified",
}
if set(release_environment) != release_environment_fields:
    raise SystemExit("release environment verification schema mismatch")
release_platform = release_environment.get("platform_id")
if release_platform not in resolved_platforms:
    raise SystemExit("release environment verification platform mismatch")
release_lock_name = f"artifact-lock-{release_platform}.explicit.txt"
release_lock = resolved_ci_root / release_platform / release_lock_name
release_urls = conda_urls(release_lock, release_platform)
release_url_set_sha256 = hashlib.sha256(
    ("\n".join(sorted(release_urls)) + "\n").encode("utf-8")
).hexdigest()
if (
    release_environment.get("schema_version") != "1.0"
    or release_environment.get("python") != "3.12.13"
    or release_environment.get("verified") is not True
    or release_environment.get("tracked_artifact_lock")
    != f"environment-{release_platform}.explicit.txt"
    or release_environment.get("tracked_artifact_lock_sha256")
    != digest(release_lock)
    or release_environment.get("artifact_count") != len(release_urls)
    or release_environment.get("runtime_artifact_set_sha256")
    != release_url_set_sha256
    or release_environment.get("repository_commit") != commit
    or not re.fullmatch(
        r"[0-9a-f]{40}", str(release_environment.get("repository_tree", ""))
    )
    or release_environment.get("repository_clean") is not True
):
    raise SystemExit("release environment verification identity mismatch")
if identity.get("resolved_ci_environments") != resolved_ci_identity:
    raise SystemExit("release identity resolved CI environment evidence mismatch")
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
    "README.md", "CHANGELOG.md",
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
    "contracts_path": "observed_contracts",
    "contract_case_count": len(
        {case_id for case_ids in oracle_cases.values() for case_id in case_ids}
    ),
}:
    raise SystemExit("release identity scientific-oracle evidence mismatch")

fresh = json.loads((root / "acceptance/fresh_clone.json").read_text(encoding="utf-8"))
fresh_truths = (
    "public_https_clone", "isolated_home", "isolated_tmpdir", "built_wheel",
    "built_sdist", "installed_wheel", "installed_sdist",
    "separate_distribution_environments", "executed_outside_checkout",
)
if (
    fresh.get("schema_version") != schema
    or fresh.get("validation_profile") != profile
    or fresh.get("verdict") != "PASS"
    or fresh.get("repository") != repository
    or fresh.get("candidate_commit") != commit
    or fresh.get("checked_out_commit") != commit
    or fresh.get("public_main_commit") != commit
    or fresh.get("source_remote") != repository + ".git"
    or fresh.get("detached_head") is not True
    or fresh.get("clone_worktree_clean") is not True
    or any(fresh.get(field) is not True for field in fresh_truths)
):
    raise SystemExit("fresh-clone acceptance mismatch")

repository_slug = "elissonnog/mito-overview"
repository_api = f"https://api.github.com/repos/{repository_slug}"

def positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SystemExit(f"{label} is not a positive integer")
    return value

def github_timestamp(value, label):
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SystemExit(f"{label} is not a valid ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemExit(f"{label} must include a timezone offset")
    return parsed

def canonical_repository(value, label):
    if not isinstance(value, dict) or value.get("full_name") != repository_slug:
        raise SystemExit(f"{label} repository identity mismatch")
    if (
        value.get("html_url") != repository
        or value.get("url") != repository_api
    ):
        raise SystemExit(f"{label} repository URL mismatch")

actions_run = json.loads(
    (root / "acceptance/github_actions_run.json").read_text(encoding="utf-8")
)
actions_jobs = json.loads(
    (root / "acceptance/github_actions_jobs.json").read_text(encoding="utf-8")
)
run_id = positive_integer(actions_run.get("id"), "final push run ID")
run_attempt = positive_integer(actions_run.get("run_attempt"), "final push run attempt")
final_run_url = f"https://github.com/{repository_slug}/actions/runs/{run_id}"
final_run_api = f"{repository_api}/actions/runs/{run_id}"
if (
    actions_run.get("name") != "smoke-tests"
    or actions_run.get("event") != "push"
    or actions_run.get("head_branch") != "main"
    or actions_run.get("path") != ".github/workflows/smoke-tests.yml"
    or actions_run.get("head_sha") != commit
    or actions_run.get("status") != "completed"
    or actions_run.get("conclusion") != "success"
    or actions_run.get("html_url") != final_run_url
    or actions_run.get("url") != final_run_api
    or actions_run.get("jobs_url") != f"{final_run_api}/jobs"
):
    raise SystemExit("GitHub Actions final push run identity mismatch")
if (
    not isinstance(actions_run.get("repository"), dict)
    or actions_run["repository"].get("full_name") != repository_slug
    or not isinstance(actions_run.get("head_repository"), dict)
    or actions_run["head_repository"].get("full_name") != repository_slug
):
    raise SystemExit("GitHub Actions final push repository identity mismatch")
if (
    str(run_id) != environment["github_actions_run_id"]
    or str(run_id) != environment["final_push_github_actions_run_id"]
    or identity.get("environment_github_actions_run_id") != run_id
    or identity.get("environment_final_push_github_actions_run_id") != run_id
    or run.get("github_actions_run_id") != run_id
    or run.get("final_push_github_actions_run_id") != run_id
):
    raise SystemExit("GitHub Actions final push run ID is inconsistent")
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
if (
    not isinstance(jobs, list)
    or actions_jobs.get("total_count") != len(jobs)
    or not all(isinstance(job, dict) for job in jobs)
):
    raise SystemExit("GitHub Actions final push jobs evidence is malformed")
selected_jobs = []
for case_id, (name, label) in job_expectations.items():
    matching = [job for job in jobs if job.get("name") == name]
    if len(matching) != 1:
        raise SystemExit(f"missing or ambiguous GitHub job: {name}")
    job = matching[0]
    job_id = positive_integer(job.get("id"), f"final push job ID for {name}")
    if (
        label not in job.get("labels", [])
        or job.get("head_sha") != commit
        or job.get("run_id") != run_id
        or job.get("run_attempt") != run_attempt
        or job.get("workflow_name") != "smoke-tests"
        or job.get("status") != "completed"
        or job.get("conclusion") != "success"
        or job.get("html_url") != f"{final_run_url}/job/{job_id}"
        or job.get("url") != f"{repository_api}/actions/jobs/{job_id}"
        or job.get("run_url") != final_run_api
    ):
        raise SystemExit(f"GitHub Actions final push job identity mismatch: {name}")
    selected_jobs.append({
        "job_id": job_id, "name": job["name"], "labels": job["labels"],
        "head_sha": job["head_sha"], "url": job["html_url"],
    })
expected_ci = {
    "provider": "github_actions", "run_id": run_id,
    "run_attempt": run_attempt, "workflow": "smoke-tests",
    "workflow_path": ".github/workflows/smoke-tests.yml", "event": "push",
    "branch": "main", "head_sha": commit, "status": "completed",
    "conclusion": "success", "url": final_run_url, "jobs": selected_jobs,
}
if identity.get("github_actions") != expected_ci:
    raise SystemExit("release identity GitHub Actions evidence mismatch")

public_run = json.loads(
    (root / "acceptance/ubuntu_public_validation/workflow_run.json").read_text(
        encoding="utf-8"
    )
)
public_artifacts = json.loads(
    (root / "acceptance/ubuntu_public_validation/artifacts.json").read_text(
        encoding="utf-8"
    )
)
public_run_id = positive_integer(public_run.get("id"), "public-validation run ID")
public_run_attempt = positive_integer(
    public_run.get("run_attempt"), "public-validation run attempt"
)
public_run_url = f"https://github.com/{repository_slug}/actions/runs/{public_run_id}"
public_run_api = f"{repository_api}/actions/runs/{public_run_id}"
if (
    public_run.get("name") != "public-validation"
    or public_run.get("event") != "workflow_dispatch"
    or public_run.get("head_branch") != "main"
    or public_run.get("path") != ".github/workflows/public-validation.yml"
    or public_run.get("head_sha") != commit
    or public_run.get("status") != "completed"
    or public_run.get("conclusion") != "success"
    or public_run.get("html_url") != public_run_url
    or public_run.get("url") != public_run_api
    or public_run.get("jobs_url") != f"{public_run_api}/jobs"
):
    raise SystemExit("public-validation GitHub Actions run identity mismatch")
canonical_repository(public_run.get("repository"), "public-validation run")
canonical_repository(public_run.get("head_repository"), "public-validation head")
expected_public_artifact_name = f"public-validation-derived-{commit}-{public_run_id}"
artifact_values = public_artifacts.get("artifacts")
if not isinstance(artifact_values, list):
    raise SystemExit("public-validation artifact evidence is malformed")
matching_artifacts = [
    artifact for artifact in artifact_values
    if isinstance(artifact, dict)
    and artifact.get("name") == expected_public_artifact_name
    and artifact.get("expired") is False
    and isinstance(artifact.get("workflow_run"), dict)
    and artifact["workflow_run"].get("id") == public_run_id
]
if len(matching_artifacts) != 1:
    raise SystemExit("selected public-validation artifact identity mismatch")
public_artifact = matching_artifacts[0]
public_artifact_id = positive_integer(
    public_artifact.get("id"), "public-validation artifact ID"
)
public_artifact_api = f"{repository_api}/actions/artifacts/{public_artifact_id}"
if (
    public_artifact.get("url") != public_artifact_api
    or public_artifact.get("archive_download_url") != f"{public_artifact_api}/zip"
):
    raise SystemExit("public-validation artifact URL mismatch")

public_artifact_root = root / "acceptance/ubuntu_public_validation/artifact"
validate_public_artifact(public_artifact_root, commit, public_run_id)
macos_public_root = root
ubuntu_public_root = public_artifact_root / "results"
validate_compact_contracts(ubuntu_public_root / "observed_contracts", oracle)
macos_public_environment = validate_public_environment(
    macos_public_root / "public_environment"
)
ubuntu_public_environment = validate_public_environment(
    ubuntu_public_root / "environment"
)
if macos_public_environment["platform_id"] not in {"osx-64", "osx-arm64"}:
    raise SystemExit("cross-platform local public evidence was not produced on macOS")
if ubuntu_public_environment["platform_id"] != "linux-64":
    raise SystemExit("cross-platform hosted public evidence was not produced on linux-64")
macos_cases_path = root / "public_matrix_cases.tsv"
macos_scientific = public_scientific_paths(
    macos_public_root, cases_override=macos_cases_path
)
ubuntu_scientific = public_scientific_paths(ubuntu_public_root)
if macos_scientific != ubuntu_scientific:
    raise SystemExit("cross-platform scientific path inventories differ")
macos_visuals = public_visual_paths(macos_public_root)
ubuntu_visuals = public_visual_paths(ubuntu_public_root)
if macos_visuals != ubuntu_visuals:
    raise SystemExit("cross-platform visual-inventory paths differ")
expected_visual_cases = {
    visual_inventory_case_id(
        ubuntu_public_root, ubuntu_public_root / Path(*relative.parts)
    )
    for relative in ubuntu_visuals
}
macos_report_outputs = root / "report_artifacts/macos/outputs"
ubuntu_report_outputs = ubuntu_public_root / "report_artifacts" / "outputs"
if macos_report_outputs.is_symlink() or not macos_report_outputs.is_dir():
    raise SystemExit("macOS report_artifacts/outputs evidence is missing")
if ubuntu_report_outputs.is_symlink() or not ubuntu_report_outputs.is_dir():
    raise SystemExit("Ubuntu report_artifacts/outputs evidence is missing")
for platform_label, report_outputs in (
    ("macOS", macos_report_outputs), ("Ubuntu", ubuntu_report_outputs),
):
    observed_visual_cases = set()
    for entry in report_outputs.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            raise SystemExit(
                f"{platform_label} report artifact collection has a non-directory entry"
            )
        observed_visual_cases.add(entry.name)
    if observed_visual_cases != expected_visual_cases:
        raise SystemExit(f"{platform_label} report artifact case inventory mismatch")

cross_reproduction = json.loads(
    (root / "acceptance/cross_platform_public_reproduction.json").read_text(
        encoding="utf-8"
    )
)
if (
    cross_reproduction.get("schema_version") != schema
    or cross_reproduction.get("validation_profile") != profile
    or cross_reproduction.get("evidence_type")
        != "cross_platform_public_reproduction"
    or cross_reproduction.get("verdict") != "PASS"
    or cross_reproduction.get("git_commit") != commit
    or cross_reproduction.get("ubuntu_public_validation_run_id") != public_run_id
    or cross_reproduction.get("ubuntu_platform") != "linux-64"
    or cross_reproduction.get("macos_platform") not in {"osx-64", "osx-arm64"}
    or cross_reproduction.get("macos_platform")
        != macos_public_environment["platform_id"]
    or cross_reproduction.get("comparison_table") != "cross_platform_comparison.tsv"
):
    raise SystemExit("cross-platform public reproduction identity mismatch")
with (root / "acceptance/cross_platform_comparison.tsv").open(
    encoding="utf-8", newline=""
) as handle:
    comparison_reader = csv.DictReader(handle, delimiter="\t")
    if tuple(comparison_reader.fieldnames or ()) != (
        "evidence_type", "relative_path", "macos_sha256", "ubuntu_sha256",
        "verdict", "comparison",
    ):
        raise SystemExit("cross-platform comparison schema mismatch")
    comparison_rows = list(comparison_reader)
comparison_counts = {"normalized_scientific_table": 0, "visual_structure": 0}
comparison_keys = set()
comparison_paths = {
    "normalized_scientific_table": set(), "visual_structure": set(),
}
for row in comparison_rows:
    evidence_type = row.get("evidence_type")
    if evidence_type not in comparison_counts:
        raise SystemExit("cross-platform comparison evidence type is invalid")
    relative = safe_posix_relative(
        row.get("relative_path", ""), "cross-platform comparison path"
    )
    key = (evidence_type, relative)
    if key in comparison_keys or row.get("verdict") != "PASS":
        raise SystemExit("cross-platform comparison row is invalid")
    comparison_keys.add(key)
    comparison_paths[evidence_type].add(relative)
    if evidence_type == "normalized_scientific_table":
        if relative not in macos_scientific:
            raise SystemExit("cross-platform comparison claims an unexpected scientific path")
        macos_path = (
            macos_cases_path
            if relative == PurePosixPath("cases.tsv")
            else macos_public_root / Path(*relative.parts)
        )
        macos_hash = digest(macos_path)
        ubuntu_hash = digest(ubuntu_public_root / Path(*relative.parts))
        if (
            row.get("macos_sha256") != macos_hash
            or row.get("ubuntu_sha256") != ubuntu_hash
        ):
            raise SystemExit("cross-platform scientific row is not bound to file content")
        if macos_hash != ubuntu_hash:
            raise SystemExit("cross-platform normalized scientific hashes differ")
    else:
        if relative not in macos_visuals:
            raise SystemExit("cross-platform comparison claims an unexpected visual path")
        if (
            row.get("macos_sha256") != "not_compared"
            or row.get("ubuntu_sha256") != "not_compared"
        ):
            raise SystemExit("cross-platform visual row claims a bytewise comparison")
        macos_inventory = macos_public_root / Path(*relative.parts)
        ubuntu_inventory = ubuntu_public_root / Path(*relative.parts)
        macos_case_id = visual_inventory_case_id(macos_public_root, macos_inventory)
        ubuntu_case_id = visual_inventory_case_id(ubuntu_public_root, ubuntu_inventory)
        if macos_case_id != ubuntu_case_id:
            raise SystemExit("cross-platform visual inventory case IDs differ")
        macos_structure = bind_visual_inventory(
            macos_inventory, macos_report_outputs / macos_case_id
        )
        ubuntu_structure = bind_visual_inventory(
            ubuntu_inventory, ubuntu_report_outputs / ubuntu_case_id
        )
        if macos_structure != ubuntu_structure:
            raise SystemExit("cross-platform visual structure differs")
    comparison_counts[evidence_type] += 1
if comparison_paths["normalized_scientific_table"] != macos_scientific:
    raise SystemExit("cross-platform comparison scientific inventory is incomplete")
if comparison_paths["visual_structure"] != macos_visuals:
    raise SystemExit("cross-platform comparison visual inventory is incomplete")
if (
    cross_reproduction.get("normalized_scientific_tables_compared")
        != comparison_counts["normalized_scientific_table"]
    or cross_reproduction.get("visual_inventories_compared")
        != comparison_counts["visual_structure"]
):
    raise SystemExit("cross-platform comparison counts are inconsistent")
expected_public_validation = {
    "provider": "github_actions", "run_id": public_run_id,
    "run_attempt": public_run_attempt, "workflow": "public-validation",
    "workflow_path": ".github/workflows/public-validation.yml",
    "event": "workflow_dispatch", "branch": "main", "head_sha": commit,
    "status": "completed", "conclusion": "success", "url": public_run_url,
    "artifact": {
        "id": public_artifact_id, "name": expected_public_artifact_name,
        "url": public_artifact_api,
        "archive_download_url": f"{public_artifact_api}/zip",
    },
    "cross_platform_reproduction": {
        "verdict": "PASS", "macos_platform": cross_reproduction["macos_platform"],
        "ubuntu_platform": "linux-64",
        "normalized_scientific_tables_compared": comparison_counts[
            "normalized_scientific_table"
        ],
        "visual_inventories_compared": comparison_counts["visual_structure"],
        "comparison_sha256": digest(
            root / "acceptance/cross_platform_comparison.tsv"
        ),
    },
}
if identity.get("public_validation_github_actions") != expected_public_validation:
    raise SystemExit("release identity public-validation evidence mismatch")
if (
    str(public_run_id) != environment["public_validation_github_actions_run_id"]
    or identity.get("environment_public_validation_github_actions_run_id")
        != public_run_id
    or run.get("public_validation_github_actions_run_id") != public_run_id
):
    raise SystemExit("public-validation run ID is inconsistent")

pull_request = json.loads(
    (root / "acceptance/pull_request.json").read_text(encoding="utf-8")
)
pull_number = positive_integer(pull_request.get("number"), "pull request number")
pull_api = f"{repository_api}/pulls/{pull_number}"
pull_html = f"https://github.com/{repository_slug}/pull/{pull_number}"
issue_api = f"{repository_api}/issues/{pull_number}"
if (
    pull_request.get("url") != pull_api
    or pull_request.get("html_url") != pull_html
    or pull_request.get("issue_url") != issue_api
    or pull_request.get("comments_url") != f"{issue_api}/comments"
    or pull_request.get("state") != "closed"
    or pull_request.get("merged") is not True
    or not isinstance(pull_request.get("merged_at"), str)
    or not pull_request["merged_at"].strip()
    or pull_request.get("merge_commit_sha") != commit
):
    raise SystemExit("pull-request metadata identity mismatch")
pull_merged_at = github_timestamp(pull_request["merged_at"], "pull-request merged_at")
pull_base = pull_request.get("base")
pull_head = pull_request.get("head")
if not isinstance(pull_base, dict) or not isinstance(pull_head, dict):
    raise SystemExit("pull-request base/head metadata is malformed")
canonical_repository(pull_base.get("repo"), "pull-request base")
canonical_repository(pull_head.get("repo"), "pull-request head")
base_sha = pull_base.get("sha")
head_sha = pull_head.get("sha")
head_ref = pull_head.get("ref")
if (
    pull_base.get("ref") != "main"
    or not isinstance(head_ref, str)
    or not head_ref.strip()
    or not re.fullmatch(r"[0-9a-f]{40}", str(base_sha or ""))
    or not re.fullmatch(r"[0-9a-f]{40}", str(head_sha or ""))
):
    raise SystemExit("pull-request branch or commit identity mismatch")
pr_identity = identity.get("pull_request")
if not isinstance(pr_identity, dict):
    raise SystemExit("release identity lacks pull-request evidence")
parents = pr_identity.get("final_commit_parents")
final_tree = pr_identity.get("final_tree_sha")
reviewed_tree = pr_identity.get("reviewed_head_tree_sha")
if (
    parents != [base_sha, head_sha]
    or not re.fullmatch(r"[0-9a-f]{40}", str(final_tree or ""))
    or reviewed_tree != final_tree
):
    raise SystemExit("final merge parent/tree relationship mismatch")
expected_pr_identity = {
    "number": pull_number, "repository": repository_slug, "url": pull_html,
    "api_url": pull_api, "issue_api_url": issue_api,
    "comments_api_url": f"{issue_api}/comments", "state": "closed",
    "merged": True, "merged_at": pull_request["merged_at"],
    "merge_commit_sha": commit, "base_ref": "main", "base_sha": base_sha,
    "head_ref": head_ref, "head_sha": head_sha,
    "final_commit_parents": [base_sha, head_sha],
    "final_tree_sha": final_tree, "reviewed_head_tree_sha": final_tree,
}
if pr_identity != expected_pr_identity:
    raise SystemExit("release identity pull-request evidence mismatch")
if (
    str(pull_number) != environment["pull_request_number"]
    or identity.get("environment_pull_request_number") != pull_number
    or run.get("pull_request_number") != pull_number
):
    raise SystemExit("pull-request number is inconsistent")

pr_actions_run = json.loads(
    (root / "acceptance/pull_request_github_actions_run.json")
    .read_text(encoding="utf-8")
)
pr_actions_jobs = json.loads(
    (root / "acceptance/pull_request_github_actions_jobs.json")
    .read_text(encoding="utf-8")
)
pr_run_id = positive_integer(pr_actions_run.get("id"), "pull-request run ID")
pr_run_attempt = positive_integer(
    pr_actions_run.get("run_attempt"), "pull-request run attempt"
)
pr_run_url = f"https://github.com/{repository_slug}/actions/runs/{pr_run_id}"
pr_run_api = f"{repository_api}/actions/runs/{pr_run_id}"
if (
    pr_actions_run.get("name") != "smoke-tests"
    or pr_actions_run.get("event") != "pull_request"
    or pr_actions_run.get("head_branch") != head_ref
    or pr_actions_run.get("path") != ".github/workflows/smoke-tests.yml"
    or pr_actions_run.get("head_sha") != head_sha
    or pr_actions_run.get("status") != "completed"
    or pr_actions_run.get("conclusion") != "success"
    or pr_actions_run.get("html_url") != pr_run_url
    or pr_actions_run.get("url") != pr_run_api
    or pr_actions_run.get("jobs_url") != f"{pr_run_api}/jobs"
):
    raise SystemExit("pull-request GitHub Actions run identity mismatch")
if (
    not isinstance(pr_actions_run.get("repository"), dict)
    or pr_actions_run["repository"].get("full_name") != repository_slug
    or not isinstance(pr_actions_run.get("head_repository"), dict)
    or pr_actions_run["head_repository"].get("full_name") != repository_slug
):
    raise SystemExit("pull-request GitHub Actions repository identity mismatch")
associations = pr_actions_run.get("pull_requests")
if not isinstance(associations, list):
    raise SystemExit("pull-request GitHub Actions association inventory is malformed")
if not associations:
    association_evidence_mode = "merged_pr_independent_identity"
elif len(associations) == 1:
    association = associations[0]
    association_head = association.get("head") if isinstance(association, dict) else None
    association_base = association.get("base") if isinstance(association, dict) else None
    if (
        not isinstance(association_head, dict)
        or not isinstance(association_base, dict)
        or association.get("number") != pull_number
        or association.get("url") != pull_api
        or association_head.get("ref") != head_ref
        or association_head.get("sha") != head_sha
        or association_base.get("ref") != "main"
        or association_base.get("sha") != base_sha
    ):
        raise SystemExit("pull-request GitHub Actions association identity mismatch")
    for label, nested in (("head", association_head), ("base", association_base)):
        nested_repo = nested.get("repo")
        if (
            not isinstance(nested_repo, dict)
            or nested_repo.get("name") != "mito-overview"
            or nested_repo.get("url") != repository_api
        ):
            raise SystemExit(f"pull-request GitHub Actions {label} repository mismatch")
    association_evidence_mode = "actions_pull_requests_canonical"
else:
    raise SystemExit(
        "pull-request GitHub Actions association inventory must be empty or contain "
        "exactly one canonical PR"
    )
pr_jobs = pr_actions_jobs.get("jobs")
expected_job_names = {name for name, _ in job_expectations.values()}
if (
    not isinstance(pr_jobs, list)
    or not all(isinstance(job, dict) for job in pr_jobs)
    or pr_actions_jobs.get("total_count") != 3
    or len(pr_jobs) != 3
    or {job.get("name") for job in pr_jobs} != expected_job_names
):
    raise SystemExit("pull-request GitHub Actions pinned job inventory mismatch")
pr_selected_jobs = []
for name, label in job_expectations.values():
    job = next(job for job in pr_jobs if job.get("name") == name)
    job_id = positive_integer(job.get("id"), f"pull-request job ID for {name}")
    if (
        not isinstance(job.get("labels"), list)
        or label not in job["labels"]
        or job.get("head_sha") != head_sha
        or job.get("run_id") != pr_run_id
        or job.get("run_attempt") != pr_run_attempt
        or job.get("workflow_name") != "smoke-tests"
        or job.get("status") != "completed"
        or job.get("conclusion") != "success"
        or job.get("html_url") != f"{pr_run_url}/job/{job_id}"
        or job.get("url") != f"{repository_api}/actions/jobs/{job_id}"
        or job.get("run_url") != pr_run_api
    ):
        raise SystemExit(f"pull-request GitHub Actions job identity mismatch: {name}")
    pr_selected_jobs.append({
        "job_id": job_id, "name": name, "labels": job["labels"],
        "head_sha": head_sha, "url": job["html_url"],
    })
expected_pr_ci = {
    "provider": "github_actions", "run_id": pr_run_id,
    "run_attempt": pr_run_attempt, "workflow": "smoke-tests",
    "workflow_path": ".github/workflows/smoke-tests.yml",
    "event": "pull_request", "pull_request_number": pull_number,
    "association_evidence_mode": association_evidence_mode,
    "branch": head_ref, "head_sha": head_sha, "status": "completed",
    "conclusion": "success", "url": pr_run_url, "jobs": pr_selected_jobs,
}
if identity.get("pull_request_github_actions") != expected_pr_ci:
    raise SystemExit("release identity pull-request GitHub Actions evidence mismatch")
if (
    str(pr_run_id) != environment["pull_request_github_actions_run_id"]
    or identity.get("environment_pull_request_github_actions_run_id") != pr_run_id
    or run.get("pull_request_github_actions_run_id") != pr_run_id
):
    raise SystemExit("pull-request GitHub Actions run ID is inconsistent")

audit_marker = "<!-- mito-overview-read-only-audit-v1 -->"
audit_roles = (
    "release_engineering", "bioinformatics", "reproducibility",
)
audit_cases = {
    "release_engineering": "read_only_audit_release_engineering",
    "bioinformatics": "read_only_audit_bioinformatics",
    "reproducibility": "read_only_audit_reproducibility",
}
comments = json.loads(
    (root / "acceptance/pull_request_comments.json").read_text(encoding="utf-8")
)
if not isinstance(comments, list):
    raise SystemExit("pull-request comments evidence is not a JSON array")
audits = {}
comment_ids = set()
audit_instance_ids = set()
repository_owner = repository_slug.split("/", 1)[0]
for comment in comments:
    if not isinstance(comment, dict):
        raise SystemExit("pull-request comments evidence contains a non-object")
    body = comment.get("body")
    if not isinstance(body, str) or audit_marker not in body:
        continue
    comment_id = positive_integer(comment.get("id"), "pull-request comment ID")
    if comment_id in comment_ids:
        raise SystemExit("pull-request comments evidence contains duplicate IDs")
    comment_ids.add(comment_id)
    if (
        comment.get("url") != f"{repository_api}/issues/comments/{comment_id}"
        or comment.get("html_url") != f"{pull_html}#issuecomment-{comment_id}"
        or comment.get("issue_url") != issue_api
        or not isinstance(comment.get("user"), dict)
        or comment["user"].get("login") != repository_owner
        or comment["user"].get("html_url") != f"https://github.com/{repository_owner}"
        or comment.get("author_association") != "OWNER"
    ):
        raise SystemExit("pull-request comment identity mismatch")
    created_at = github_timestamp(
        comment.get("created_at"), f"read-only audit comment {comment_id} created_at"
    )
    updated_at = github_timestamp(
        comment.get("updated_at"), f"read-only audit comment {comment_id} updated_at"
    )
    if created_at > updated_at or updated_at > pull_merged_at:
        raise SystemExit(
            f"read-only audit comment {comment_id} was posted or edited after merge"
        )
    if body.count(audit_marker) != 1:
        raise SystemExit("read-only audit comment contains a duplicate marker")
    suffix = body.split(audit_marker, 1)[1]
    fenced = re.fullmatch(
        r"\s*```json[ \t]*\r?\n(?P<payload>.*?)\r?\n```[ \t]*\s*",
        suffix, flags=re.DOTALL,
    )
    if fenced is None:
        raise SystemExit("read-only audit comment JSON fence is malformed")
    try:
        payload = json.loads(fenced.group("payload"))
    except json.JSONDecodeError as error:
        raise SystemExit("read-only audit JSON payload is malformed") from error
    audit_fields = {
        "schema_version", "review_method", "audit_instance_id", "role", "reviewed_commit",
        "reviewed_tree", "verdict", "unresolved_blockers", "summary",
    }
    if not isinstance(payload, dict) or set(payload) != audit_fields:
        raise SystemExit("read-only audit payload fields do not match schema 1.1")
    role = payload.get("role")
    if role not in audit_roles or role in audits:
        raise SystemExit(f"missing, duplicate, or unsupported read-only audit role: {role}")
    blockers = payload.get("unresolved_blockers")
    audit_instance_id = payload.get("audit_instance_id")
    if (
        payload.get("schema_version") != "1.1"
        or payload.get("review_method") != "read_only_agent_role_audit"
        or not isinstance(audit_instance_id, str)
        or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            audit_instance_id,
            flags=re.IGNORECASE,
        )
        or audit_instance_id.lower() in audit_instance_ids
        or payload.get("reviewed_commit") != head_sha
        or payload.get("reviewed_tree") != final_tree
        or payload.get("verdict") != "PASS"
        or isinstance(blockers, bool)
        or not isinstance(blockers, int)
        or blockers != 0
        or not isinstance(payload.get("summary"), str)
        or not payload["summary"].strip()
    ):
        raise SystemExit(f"read-only audit payload mismatch for role: {role}")
    audit_instance_ids.add(audit_instance_id.lower())
    audits[role] = {
        **payload, "summary": payload["summary"].strip(),
        "comment_id": comment_id, "comment_url": comment["html_url"],
        "posted_by": repository_owner, "author_association": "OWNER",
        "created_at": comment["created_at"], "updated_at": comment["updated_at"],
    }
if set(audits) != set(audit_roles):
    raise SystemExit("required read-only audit role inventory is incomplete")
expected_audits = [audits[role] for role in audit_roles]
if identity.get("read_only_audits") != expected_audits:
    raise SystemExit("release identity read-only audit evidence mismatch")
if release_environment.get("repository_tree") != final_tree:
    raise SystemExit("release environment verification tree mismatch")
expected_acceptance_cases = [
    "fresh_clone_candidate_commit", "github_actions_linux_candidate_commit",
    "github_actions_macos_candidate_commit",
    "github_actions_macos_arm64_candidate_commit",
    "pr_head_ci_candidate_commit", "read_only_audit_release_engineering",
    "read_only_audit_bioinformatics", "read_only_audit_reproducibility",
]
if identity.get("acceptance_cases") != expected_acceptance_cases:
    raise SystemExit("release identity acceptance-case inventory mismatch")

required_pass = {
    "unit_known_answer", "cli_step_listing", "strict_generic_dry_run",
    "synthetic_longread_smoke", "synthetic_shortread_smoke",
    "synthetic_longread_nomethyl_smoke", "standalone_minimal_smoke",
    "package_build", "public_validation_matrix", "gm11906_default_run1",
    "gm11906_default_run2", "gm11906_lenient", "gm11906_strict",
    "gm12878_default_run1", "gm12878_default_run2", "gm12878_lenient",
    "gm12878_strict", "gm11906_repeatability", "gm12878_repeatability",
    "gm11906_visual_integrity", "gm12878_visual_integrity", "filter_profiles",
    "public_oracle", "raw_cache_seal", "offline_isolation",
    "project_network_entrypoints", "public_cache_prepare",
    "cross_platform_public_reproduction",
    "fresh_clone_candidate_commit", "github_actions_linux_candidate_commit",
    "github_actions_macos_candidate_commit",
    "github_actions_macos_arm64_candidate_commit",
    "pr_head_ci_candidate_commit", "read_only_audit_release_engineering",
    "read_only_audit_bioinformatics", "read_only_audit_reproducibility",
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
if case_ids != required_pass:
    raise SystemExit(
        "validation case IDs do not exactly match the required release set: "
        f"missing={sorted(required_pass - case_ids)}; "
        f"unexpected={sorted(case_ids - required_pass)}"
    )
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
        canonical_name = f"{path.name.removesuffix('.tar.gz')}/PKG-INFO"
        with tarfile.open(path, "r:gz") as archive:
            members = sorted(
                (
                    member for member in archive.getmembers()
                    if member.name == canonical_name
                ),
                key=lambda member: member.name,
            )
            if len(members) != 1:
                raise SystemExit(
                    f"invalid canonical sdist metadata inventory: {path.name}"
                )
            if not members[0].isfile():
                raise SystemExit(
                    f"canonical sdist metadata is not a regular file: {path.name}"
                )
            handle = archive.extractfile(members[0])
            if handle is None:
                raise SystemExit(f"unreadable sdist metadata: {path.name}")
            text = handle.read().decode("utf-8")
        kind = "sdist"
    else:
        raise SystemExit(f"unsupported distribution artifact: {path.name}")
    name, version = metadata_fields(text, path)
    return kind, name, version

dist_root = root / "dist"
expected_dist_paths = {
    "dist/mito_overview-0.3.0-py3-none-any.whl",
    "dist/mito_overview-0.3.0.tar.gz",
}
if dist_root.is_symlink() or not dist_root.is_dir():
    raise SystemExit("distribution directory is missing or is a symlink")
dist_entries = sorted(dist_root.iterdir(), key=lambda candidate: candidate.name)
actual_dist_paths = {
    candidate.relative_to(root).as_posix() for candidate in dist_entries
}
if actual_dist_paths != expected_dist_paths or len(dist_entries) != 2:
    raise SystemExit("distribution directory must contain only the canonical wheel and sdist")
if any(candidate.is_symlink() or not candidate.is_file() for candidate in dist_entries):
    raise SystemExit("distribution artifacts must be regular files")
dist_files = dist_entries
declared_dist = identity.get("dist_artifacts", [])
if fresh.get("distributions") != declared_dist:
    raise SystemExit("fresh-clone and release-identity distribution inventories differ")
dist_fields = {
    "path", "kind", "name", "version", "bytes", "sha256",
    "direct_url_archive_sha256",
}
if not isinstance(declared_dist, list) or not all(
    isinstance(entry, dict) and set(entry) == dist_fields for entry in declared_dist
):
    raise SystemExit("distribution inventory fields do not match schema")
declared_paths = {entry.get("path") for entry in declared_dist}
if declared_paths != expected_dist_paths or len(declared_paths) != len(declared_dist):
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
        or entry.get("bytes") != dist_path.stat().st_size
        or entry.get("sha256") != digest(dist_path)
        or entry.get("direct_url_archive_sha256") != digest(dist_path)
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
    validate_regular_tree(
        args.validation_root,
        label="Validation packet source tree",
    )
    validate_regular_file(
        args.repo_root / FROZEN_ORACLE_REPOSITORY_PATH,
        source_root=args.repo_root,
        label="Tracked scientific oracle",
    )
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
        args.repo_root,
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
    if (
        release_identity["environment_final_push_github_actions_run_id"]
        != ci_identity["run_id"]
    ):
        raise ValueError(
            "environment.txt final_push_github_actions_run_id does not match "
            "the final push GitHub Actions evidence"
        )
    resolved_ci_environments = validate_resolved_ci_environments(
        args.validation_root,
        args.repo_root,
        str(release_identity["git_commit"]),
        int(ci_identity["run_id"]),
    )
    public_validation_identity = validate_public_validation_github_actions_evidence(
        args.validation_root,
        args.repo_root,
        str(release_identity["git_commit"]),
        str(release_identity["repository"]),
        int(release_identity["environment_public_validation_github_actions_run_id"]),
    )
    pr_acceptance = pull_request_acceptance_identity(
        args.validation_root,
        args.repo_root,
        str(release_identity["git_commit"]),
        str(release_identity["repository"]),
    )
    pull_request_identity = pr_acceptance["pull_request"]
    pull_request_ci_identity = pr_acceptance["pull_request_github_actions"]
    if not isinstance(pull_request_identity, dict) or not isinstance(
        pull_request_ci_identity, dict
    ):
        raise ValueError("Pull-request acceptance identity is malformed")
    if (
        release_identity["environment_pull_request_number"]
        != pull_request_identity["number"]
    ):
        raise ValueError(
            "environment.txt pull_request_number does not match pull-request evidence"
        )
    if (
        release_identity["environment_pull_request_github_actions_run_id"]
        != pull_request_ci_identity["run_id"]
    ):
        raise ValueError(
            "environment.txt pull_request_github_actions_run_id does not match "
            "pull-request GitHub Actions evidence"
        )
    case_count, verdict_counts = validate_cases(
        args.validation_root / "cases.tsv",
        acceptance_rows,
    )
    validate_evidence_tables(args.validation_root)
    validate_resource_bindings(
        args.validation_root,
        str(release_identity["git_commit"]),
    )
    decoded_pixel_evidence = validate_decoded_pixel_evidence(args.validation_root)
    public_environment = validate_public_environment(
        public_root / "environment",
        args.repo_root,
    )
    gm11906_source_metadata = validate_gm11906_source_metadata(
        args.repo_root,
        public_root,
    )
    public_inputs = validate_public_input_evidence(
        public_root,
        args.validation_root / "public_data_sources.tsv",
        gm11906_source_metadata,
    )
    validate_public_cache_byte_provenance(
        args.validation_root,
        list(public_inputs["rows"]),
    )
    public_provenance = validate_public_provenance(
        public_root,
        list(public_inputs["rows"]),
        gm11906_source_metadata,
    )
    scientific_evidence = validate_scientific_evidence(
        args.repo_root,
        args.validation_root,
        public_root,
    )
    actual_dist_artifacts = validate_distributions(
        args.validation_root / "dist",
        str(release_identity["package_name"]),
        str(release_identity["package_version"]),
    )
    fresh_clone = load_json_object(
        args.validation_root / "acceptance/fresh_clone.json",
        "fresh-clone evidence",
    )
    dist_artifacts = validate_fresh_clone_distribution_inventory(
        fresh_clone.get("distributions"), actual_dist_artifacts
    )
    for source in (
        args.validation_root / "commands",
        public_root / "commands",
        args.validation_root / "logs",
        public_root / "logs",
        args.validation_root / "expected",
        public_root / "observed_normalized",
        public_root / PUBLIC_CONTRACTS_PACKET_PATH,
        args.validation_root / "figures",
    ):
        if not source.is_dir() or not any(candidate.is_file() for candidate in source.rglob("*")):
            raise ValueError(f"Required evidence directory is missing or empty: {source}")

    args.packet_root.mkdir(parents=True, exist_ok=True)

    for name in ("cases.tsv", "environment.txt", *EVIDENCE_TABLES):
        copy_regular_file(
            args.validation_root / name,
            args.packet_root / name,
            source_root=args.validation_root,
        )
    copy_tree(args.validation_root / "acceptance", args.packet_root / "acceptance")
    copy_regular_file(
        args.validation_root / "acceptance/cross_platform_comparison.tsv",
        args.packet_root / "cross_platform_comparison.tsv",
        source_root=args.validation_root,
    )
    copy_tree(args.validation_root / "commands", args.packet_root / "commands")
    copy_tree(public_root / "commands", args.packet_root / "commands" / "public")
    copy_tree(args.validation_root / "logs", args.packet_root / "logs")
    copy_tree(public_root / "logs", args.packet_root / "logs" / "public")
    copy_tree(args.validation_root / "dist", args.packet_root / "dist")
    copy_tree(args.validation_root / "expected", args.packet_root / "expected")
    copy_tree(args.validation_root / "figures", args.packet_root / "figures")
    for specification in DECODED_PIXEL_REPORTS.values():
        repeat_case_id = str(specification["repeat_case_id"])
        copy_tree(
            public_root / "outputs" / repeat_case_id / "figures",
            args.packet_root / "figures_repeat2" / repeat_case_id,
        )
    for specification in DECODED_PIXEL_REPORTS.values():
        copy_regular_file(
            public_root / str(specification["source"]),
            args.packet_root / str(specification["packet"]),
            source_root=args.validation_root,
        )
    copy_tree(
        public_root / "observed_normalized",
        args.packet_root / "observed_normalized",
    )
    copy_tree(
        public_root / PUBLIC_CONTRACTS_PACKET_PATH,
        args.packet_root / PUBLIC_CONTRACTS_PACKET_PATH,
    )
    packaged_macos_reports = args.packet_root / MACOS_REPORT_OUTPUTS_PACKET_PATH
    stage_macos_visual_artifacts(public_root, packaged_macos_reports)
    copy_tree(
        public_root / "environment",
        args.packet_root / PUBLIC_ENVIRONMENT_PACKET_PATH,
    )
    copy_regular_file(
        public_root / "filter_profile_results.tsv",
        args.packet_root / "filter_profile_results.tsv",
        source_root=args.validation_root,
    )
    (args.packet_root / "inputs.sha256").write_text(
        str(public_inputs["canonical_inputs_sha256"]),
        encoding="utf-8",
    )
    copy_regular_file(
        public_root / RAW_INPUTS_PACKET_PATH,
        args.packet_root / RAW_INPUTS_PACKET_PATH,
        source_root=args.validation_root,
    )
    copy_regular_file(
        public_root / CACHE_SEAL_PACKET_PATH,
        args.packet_root / CACHE_SEAL_PACKET_PATH,
        source_root=args.validation_root,
    )
    copy_regular_file(
        public_root / ORACLE_ASSERTIONS_PACKET_PATH,
        args.packet_root / ORACLE_ASSERTIONS_PACKET_PATH,
        source_root=args.validation_root,
    )
    copy_regular_file(
        public_root / "cases.tsv",
        args.packet_root / PUBLIC_MATRIX_CASES_PACKET_PATH,
        source_root=args.validation_root,
    )
    copy_regular_file(
        args.repo_root / FROZEN_ORACLE_REPOSITORY_PATH,
        args.packet_root / FROZEN_ORACLE_PACKET_PATH,
        source_root=args.repo_root,
    )
    for key, specification in PUBLIC_PROVENANCE_FILES.items():
        destination = args.packet_root / str(specification["packet"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy_regular_file(
            public_root / str(specification["source"]),
            destination,
            source_root=args.validation_root,
        )

    release_identity["dist_artifacts"] = dist_artifacts
    release_identity["acceptance_cases"] = [row["case_id"] for row in acceptance_rows]
    release_identity["github_actions"] = ci_identity
    release_identity["resolved_ci_environments"] = resolved_ci_environments
    release_identity["public_validation_github_actions"] = public_validation_identity
    release_identity.update(pr_acceptance)
    release_identity["public_provenance"] = public_provenance
    release_identity["public_environment"] = public_environment
    public_source_metadata_identity = {
        key: gm11906_source_metadata[key]
        for key in (
            "path",
            "sha256",
            "records_sha256",
            "retrieval_completed_utc",
            "authority",
        )
    }
    release_identity["public_source_metadata"] = public_source_metadata_identity
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
        "contracts_path": PUBLIC_CONTRACTS_PACKET_PATH,
        "contract_case_count": scientific_evidence["contract_case_count"],
    }
    release_identity["decoded_pixel_evidence"] = decoded_pixel_evidence
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
        "final_push_github_actions_run_id": ci_identity["run_id"],
        "pull_request_number": pull_request_identity["number"],
        "pull_request_github_actions_run_id": pull_request_ci_identity["run_id"],
        "public_validation_github_actions_run_id": public_validation_identity["run_id"],
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": case_count,
        "verdict_counts": verdict_counts,
        "evidence_tables": sorted(EVIDENCE_TABLES),
        "public_source_metadata": public_source_metadata_identity,
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
    packaged_public_artifact = (
        args.packet_root / "acceptance/ubuntu_public_validation/artifact"
    )
    sanitize_packet_paths(
        args.packet_root,
        replacements,
        immutable_roots=(packaged_public_artifact, packaged_macos_reports),
    )
    rebind_packaged_resource_evidence(
        args.packet_root,
        str(release_identity["git_commit"]),
    )
    validate_downloaded_public_artifact_identity(
        packaged_public_artifact,
        str(release_identity["git_commit"]),
        int(public_validation_identity["run_id"]),
    )
    bind_visual_collection(args.packet_root, packaged_macos_reports)
    packaged_dist_artifacts = validate_distributions(
        args.packet_root / "dist",
        str(release_identity["package_name"]),
        str(release_identity["package_version"]),
    )
    packaged_fresh = load_json_object(
        args.packet_root / "acceptance/fresh_clone.json",
        "packaged fresh-clone evidence",
    )
    packaged_dist_inventory = validate_fresh_clone_distribution_inventory(
        packaged_fresh.get("distributions"), packaged_dist_artifacts
    )
    if packaged_dist_inventory != dist_artifacts:
        raise ValueError("Packaged distribution bytes changed after fresh-clone validation")

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
    if packaged_identity.get("dist_artifacts") != packaged_dist_inventory:
        raise ValueError(
            "Release identity distribution inventory does not match installed packet bytes"
        )
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
    root_manifest = args.packet_root / "artifacts.sha256"
    for artifact in sorted(args.packet_root.rglob("*")):
        if not artifact.is_file() or artifact == root_manifest:
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
    observed_top_level = {entry.name for entry in args.packet_root.iterdir()}
    unexpected = sorted(observed_top_level - set(REQUIRED_TOP_LEVEL))
    if unexpected:
        raise SystemExit(f"Packet contains unexpected top-level entries: {unexpected}")

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
