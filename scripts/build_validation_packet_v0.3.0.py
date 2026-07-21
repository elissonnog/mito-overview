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
from pathlib import Path


EXPECTED_RELEASE_VERSION = "v0.3.0"
EXPECTED_PACKAGE_NAME = "mito-overview"
ZENODO_DOI_PATTERN = r"10\.5281/zenodo\.[1-9][0-9]*"
ZENODO_RESERVATION_PACKET_PATH = "acceptance/zenodo_reservation.json"
ZENODO_RESERVATION_SOURCE = "authenticated_zenodo_deposition_api"
EXPECTED_GITHUB_BRANCH = "main"
EXPECTED_GITHUB_WORKFLOW_PATH = ".github/workflows/smoke-tests.yml"

PUBLIC_PROVENANCE_FILES = {
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

REQUIRED_TOP_LEVEL = (
    "run.json",
    "release_identity.json",
    "cases.tsv",
    "acceptance",
    "claim_evidence_matrix.tsv",
    "public_data_sources.tsv",
    "environment.txt",
    "commands",
    "logs",
    "dist",
    "expected",
    "observed_normalized",
    "public_provenance",
    "filter_profile_results.tsv",
    "inputs.sha256",
    "artifacts.sha256",
    "verify_bundle.sh",
)

FRESH_CLONE_CASE_ID = "fresh_clone_candidate_commit"
GITHUB_ACTIONS_LINUX_CASE_ID = "github_actions_linux_candidate_commit"
GITHUB_ACTIONS_MACOS_CASE_ID = "github_actions_macos_candidate_commit"
ACCEPTANCE_CASE_IDS = {
    FRESH_CLONE_CASE_ID,
    GITHUB_ACTIONS_LINUX_CASE_ID,
    GITHUB_ACTIONS_MACOS_CASE_ID,
}
EXPECTED_GITHUB_WORKFLOW = "smoke-tests"
EXPECTED_GITHUB_JOBS = {
    GITHUB_ACTIONS_LINUX_CASE_ID: {
        "platform": "linux",
        "label": "ubuntu-latest",
        "name": "Unit and synthetic tests (ubuntu-latest)",
    },
    GITHUB_ACTIONS_MACOS_CASE_ID: {
        "platform": "macos",
        "label": "macos-latest",
        "name": "Unit and synthetic tests (macos-latest)",
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
} | ACCEPTANCE_CASE_IDS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
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
    parser.add_argument(
        "--zenodo-reservation-evidence",
        type=Path,
        required=True,
        help="Sanitized evidence captured from an authenticated Zenodo deposition response",
    )
    parser.add_argument("--doi", required=True)
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


def parse_environment_identity(path: Path) -> dict[str, str]:
    required = {"release_version", "git_commit", "repository", "archive_doi"}
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


def read_release_metadata(
    repo_root: Path,
) -> tuple[str, dict[str, str], dict[str, str], str]:
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

    init_text = metadata_paths["mito_overview/__init__.py"].read_text(encoding="utf-8")
    init_match = re.search(
        r"(?m)^__version__\s*=\s*['\"]([^'\"]+)['\"]\s*$",
        init_text,
    )
    if init_match is None:
        raise ValueError("mito_overview/__init__.py does not define a literal __version__")

    citation_text = metadata_paths["CITATION.cff"].read_text(encoding="utf-8")
    citation_match = re.search(r"(?m)^version:\s*([^\s#]+)", citation_text)
    if citation_match is None:
        raise ValueError("CITATION.cff does not define a top-level version")
    citation_doi_matches = re.findall(r"(?m)^doi:\s*([^\s#]+)", citation_text)
    if len(citation_doi_matches) != 1:
        raise ValueError("CITATION.cff must define exactly one top-level DOI")
    citation_version = citation_match.group(1).strip("'\"")
    citation_doi = citation_doi_matches[0].strip("'\"")

    versions = {
        "pyproject.toml": pyproject_version,
        "mito_overview/__init__.py": init_match.group(1),
        "CITATION.cff": citation_version,
    }
    hashes = {label: sha256(path) for label, path in metadata_paths.items()}
    return package_name, versions, hashes, citation_doi


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
        "schema_version": "1.0",
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
    if not isinstance(metadata, dict) or set(metadata) != {"prereserve_doi"}:
        raise ValueError("Zenodo deposition metadata must contain only prereserve_doi evidence")
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


def validate_public_provenance(public_root: Path) -> list[dict[str, str]]:
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

    alignment_expectations = (
        (
            short,
            "GM11906_MERRF_reduced_shortread",
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
        or selected_count <= 0
        or selection.get("requested_query_names") != selected_count
        or selected_count != len(query_names)
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
            "source_case": "gm11906_default_run1" if key == "shortread_alignment" else "gm12878_default_run1",
        }
        for key, specification in PUBLIC_PROVENANCE_FILES.items()
    ]


def github_repository_slug(repository: str) -> str:
    prefix = "https://github.com/"
    if not repository.startswith(prefix):
        raise ValueError(
            f"GitHub Actions evidence requires a GitHub HTTPS repository: {repository}"
        )
    slug = repository[len(prefix) :].rstrip("/")
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
        "schema_version": "1.0",
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


def resolve_release_identity(
    repo_root: Path,
    environment_path: Path,
    release_version: str,
    repository: str,
    asserted_commit: str | None,
    archive_doi: str,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    if release_version != EXPECTED_RELEASE_VERSION:
        raise ValueError(
            f"This packet builder is release-locked to {EXPECTED_RELEASE_VERSION}, got {release_version}"
        )
    if re.fullmatch(ZENODO_DOI_PATTERN, archive_doi) is None:
        raise ValueError(f"A canonical reserved Zenodo DOI is required: {archive_doi!r}")
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
    if environment["archive_doi"] != archive_doi:
        raise ValueError(
            "environment.txt archive_doi does not match requested archive DOI: "
            f"{environment['archive_doi']} != {archive_doi}"
        )

    package_name, versions, metadata_hashes, citation_doi = read_release_metadata(repo_root)
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
    if citation_doi != archive_doi:
        raise ValueError(
            f"CITATION.cff DOI does not match requested archive DOI: "
            f"{citation_doi} != {archive_doi}"
        )

    return {
        "schema_version": "1.0",
        "release_version": release_version,
        "package_name": package_name,
        "package_version": package_version,
        "repository": repository,
        "git_commit": head,
        "environment_release_version": environment["release_version"],
        "environment_git_commit": environment["git_commit"],
        "environment_archive_doi": environment["archive_doi"],
        "archive_doi": archive_doi,
        "citation_doi": citation_doi,
        "metadata_versions": versions,
        "metadata_sha256": metadata_hashes,
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
from pathlib import Path

root = Path(sys.argv[1])
required_top_level = {
    "run.json", "release_identity.json", "cases.tsv", "acceptance",
    "claim_evidence_matrix.tsv",
    "public_data_sources.tsv", "environment.txt", "commands", "logs", "dist",
    "expected", "observed_normalized", "public_provenance",
    "filter_profile_results.tsv", "inputs.sha256",
    "artifacts.sha256", "verify_bundle.sh",
}
missing = sorted(name for name in required_top_level if not (root / name).exists())
if missing:
    raise SystemExit(f"missing required evidence: {missing}")

for relative in (
    "acceptance", "commands", "commands/public", "logs", "logs/public", "dist",
    "public_provenance",
):
    evidence_root = root / relative
    if not evidence_root.is_dir() or not any(path.is_file() for path in evidence_root.rglob("*")):
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
        if packet_paths:
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise SystemExit(f"unsafe packet artifact path: {relative}")
        entries[relative] = match.group(1)
    return entries

artifact_hashes = parse_manifest(root / "artifacts.sha256", packet_paths=True)
actual_artifacts = {
    path.relative_to(root).as_posix()
    for path in root.rglob("*")
    if path.is_file() and path.name != "artifacts.sha256"
}
if set(artifact_hashes) != actual_artifacts:
    missing_hashes = sorted(actual_artifacts - set(artifact_hashes))
    stale_hashes = sorted(set(artifact_hashes) - actual_artifacts)
    raise SystemExit(
        f"artifact manifest inventory mismatch; missing={missing_hashes}, stale={stale_hashes}"
    )
for relative, expected in artifact_hashes.items():
    observed = digest(root / relative)
    if observed != expected:
        raise SystemExit(f"artifact hash mismatch: {relative}")

parse_manifest(root / "inputs.sha256", packet_paths=False)

def parse_environment(path):
    wanted = {"release_version", "git_commit", "repository", "archive_doi"}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in wanted:
            if key in values:
                raise SystemExit(f"duplicate environment identity key: {key}")
            values[key] = value.strip()
    missing_keys = sorted(wanted - values.keys())
    if missing_keys:
        raise SystemExit(f"environment identity keys missing: {missing_keys}")
    return values

run = json.loads((root / "run.json").read_text(encoding="utf-8"))
identity = json.loads((root / "release_identity.json").read_text(encoding="utf-8"))
environment = parse_environment(root / "environment.txt")
if run.get("release_version") != "v0.3.0" or identity.get("release_version") != "v0.3.0":
    raise SystemExit("release identity mismatch")
if identity.get("package_version") != "0.3.0":
    raise SystemExit("package version mismatch")
if identity.get("package_name") != "mito-overview":
    raise SystemExit("package name mismatch")
if not re.fullmatch(r"[0-9a-f]{40}", str(identity.get("git_commit", ""))):
    raise SystemExit("invalid release commit")
if len({run.get("git_commit"), identity.get("git_commit"), environment.get("git_commit"), identity.get("environment_git_commit")}) != 1:
    raise SystemExit("release commit is inconsistent across packet evidence")
if len({run.get("repository"), identity.get("repository"), environment.get("repository")}) != 1:
    raise SystemExit("repository identity is inconsistent across packet evidence")
archive_doi = run.get("archive_doi")
if not re.fullmatch(r"10\.5281/zenodo\.[1-9][0-9]*", str(archive_doi or "")):
    raise SystemExit("packet does not contain a canonical reserved Zenodo DOI")
if len({
    archive_doi,
    identity.get("archive_doi"),
    identity.get("citation_doi"),
    identity.get("environment_archive_doi"),
    environment.get("archive_doi"),
}) != 1:
    raise SystemExit("archive DOI is inconsistent across packet evidence")

zenodo_relative = "acceptance/zenodo_reservation.json"
zenodo_path = root / zenodo_relative
try:
    zenodo = json.loads(zenodo_path.read_text(encoding="utf-8"))
except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
    raise SystemExit(f"invalid Zenodo reservation evidence: {error}")
if not isinstance(zenodo, dict):
    raise SystemExit("Zenodo reservation evidence must be an object")

def reject_secret_material(value, location="root"):
    sensitive_key = re.compile(
        r"(?i)(?:^|_)(?:access_?token|refresh_?token|authorization|password|secret)(?:$|_)"
    )
    sensitive_value = re.compile(
        r"(?i)(?:access[_-]?token\s*=|authorization\s*:|bearer\s+|client[_-]?secret)"
    )
    if isinstance(value, dict):
        for key, child in value.items():
            if sensitive_key.search(str(key)):
                raise SystemExit(f"Zenodo reservation contains a sensitive key at {location}")
            reject_secret_material(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_secret_material(child, f"{location}[{index}]")
    elif isinstance(value, str) and sensitive_value.search(value):
        raise SystemExit(f"Zenodo reservation contains secret-like material at {location}")

reject_secret_material(zenodo)
zenodo_fields = {
    "schema_version", "evidence_type", "source", "captured_utc",
    "reservation_status", "doi", "record_id", "zenodo_api_url",
    "deposition_response",
}
if set(zenodo) != zenodo_fields:
    raise SystemExit("Zenodo reservation evidence is not the required sanitized field set")
if (
    zenodo.get("schema_version") != "1.0"
    or zenodo.get("evidence_type") != "zenodo_doi_reservation"
    or zenodo.get("source") != "authenticated_zenodo_deposition_api"
    or zenodo.get("reservation_status") != "reserved"
    or zenodo.get("doi") != archive_doi
):
    raise SystemExit("Zenodo reservation evidence identity or status mismatch")
captured_utc = zenodo.get("captured_utc")
try:
    captured = datetime.fromisoformat(str(captured_utc).replace("Z", "+00:00"))
except ValueError as error:
    raise SystemExit("invalid Zenodo reservation capture timestamp") from error
if captured.tzinfo is None or captured.utcoffset() is None:
    raise SystemExit("Zenodo reservation capture timestamp lacks a timezone")
record_id = zenodo.get("record_id")
if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
    raise SystemExit("invalid Zenodo reservation record ID")
zenodo_api_url = f"https://zenodo.org/api/deposit/depositions/{record_id}"
if archive_doi != f"10.5281/zenodo.{record_id}" or zenodo.get("zenodo_api_url") != zenodo_api_url:
    raise SystemExit("Zenodo reservation DOI, record ID, and API URL are inconsistent")
deposition = zenodo.get("deposition_response")
if not isinstance(deposition, dict) or set(deposition) != {
    "id", "record_id", "links", "metadata", "state", "submitted",
}:
    raise SystemExit("Zenodo deposition response is not the required sanitized field set")
links = deposition.get("links")
metadata = deposition.get("metadata")
prereserve = metadata.get("prereserve_doi") if isinstance(metadata, dict) else None
if (
    deposition.get("id") != record_id
    or deposition.get("record_id") != record_id
    or deposition.get("state") != "unsubmitted"
    or deposition.get("submitted") is not False
    or not isinstance(links, dict)
    or set(links) != {"self"}
    or links.get("self") != zenodo_api_url
    or not isinstance(metadata, dict)
    or set(metadata) != {"prereserve_doi"}
    or not isinstance(prereserve, dict)
    or set(prereserve) != {"doi", "recid"}
    or prereserve.get("doi") != archive_doi
    or prereserve.get("recid") != record_id
):
    raise SystemExit("Zenodo deposition response does not bind the DOI reservation")
expected_zenodo_identity = {
    "evidence_path": zenodo_relative,
    "evidence_sha256": digest(zenodo_path),
    "doi": archive_doi,
    "record_id": record_id,
    "zenodo_api_url": zenodo_api_url,
    "reservation_status": "reserved",
    "source": "authenticated_zenodo_deposition_api",
    "captured_utc": captured_utc,
}
if identity.get("zenodo_reservation") != expected_zenodo_identity:
    raise SystemExit("release identity does not match Zenodo reservation evidence")
if (
    run.get("archive_record_id") != record_id
    or run.get("doi_reservation_status") != "reserved"
    or run.get("doi_reservation_evidence") != zenodo_relative
):
    raise SystemExit("run record does not match Zenodo reservation evidence")
if identity.get("environment_release_version") != "v0.3.0" or environment.get("release_version") != "v0.3.0":
    raise SystemExit("environment release version mismatch")
if identity.get("source_worktree_clean") is not True:
    raise SystemExit("release identity was not built from a clean worktree")
metadata_versions = identity.get("metadata_versions", {})
required_metadata = {"pyproject.toml", "mito_overview/__init__.py", "CITATION.cff"}
if set(metadata_versions) != required_metadata or set(metadata_versions.values()) != {"0.3.0"}:
    raise SystemExit("release metadata versions are incomplete or inconsistent")
metadata_hashes = identity.get("metadata_sha256", {})
if set(metadata_hashes) != required_metadata or any(
    not re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in metadata_hashes.values()
):
    raise SystemExit("release metadata hashes are incomplete or malformed")
if run.get("diagnostic_validation_claimed") is not False:
    raise SystemExit("packet exceeds its bounded non-diagnostic claim scope")

fresh_case_id = "fresh_clone_candidate_commit"
github_jobs = {
    "github_actions_linux_candidate_commit": {
        "platform": "linux",
        "label": "ubuntu-latest",
        "name": "Unit and synthetic tests (ubuntu-latest)",
    },
    "github_actions_macos_candidate_commit": {
        "platform": "macos",
        "label": "macos-latest",
        "name": "Unit and synthetic tests (macos-latest)",
    },
}
acceptance_case_ids = {fresh_case_id, *github_jobs}
identity_acceptance = identity.get("acceptance_cases")
if (
    not isinstance(identity_acceptance, list)
    or len(identity_acceptance) != len(acceptance_case_ids)
    or set(identity_acceptance) != acceptance_case_ids
):
    raise SystemExit("release identity acceptance-case inventory is incomplete")

def evidence_json(relative):
    path = root / relative
    if not path.is_file():
        raise SystemExit(f"missing acceptance evidence: {relative}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid acceptance JSON: {relative}: {error}")
    if not isinstance(value, dict):
        raise SystemExit(f"acceptance evidence is not an object: {relative}")
    return value

def evidence_file(relative):
    path = root / relative
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"missing or empty acceptance evidence: {relative}")

def positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SystemExit(f"invalid GitHub Actions {label}: {value!r}")
    return value

repository = identity["repository"]
prefix = "https://github.com/"
if not repository.startswith(prefix):
    raise SystemExit("release repository is not a GitHub HTTPS repository")
repository_slug = repository[len(prefix):].rstrip("/")
if repository_slug.endswith(".git"):
    repository_slug = repository_slug[:-4]
if not re.fullmatch(r"[^/\s]+/[^/\s]+", repository_slug):
    raise SystemExit("invalid GitHub repository identity")
commit = identity["git_commit"]

fresh_relative = "acceptance/fresh_clone.json"
fresh_command = f"commands/{fresh_case_id}.sh"
fresh_log = f"logs/{fresh_case_id}.log"
fresh = evidence_json(fresh_relative)
fresh_fields = {
    "schema_version": "1.0",
    "evidence_type": "fresh_clone_validation",
    "case_id": fresh_case_id,
    "repository": repository,
    "command_path": fresh_command,
    "log_path": fresh_log,
    "verdict": "PASS",
    "candidate_commit": commit,
    "checked_out_commit": commit,
    "detached_head": True,
    "clone_worktree_clean": True,
}
for field, expected in fresh_fields.items():
    if fresh.get(field) != expected:
        raise SystemExit(
            f"fresh-clone acceptance mismatch for {field}: "
            f"{fresh.get(field)!r} != {expected!r}"
        )
evidence_file(fresh_command)
evidence_file(fresh_log)
expected_acceptance = {
    fresh_case_id: {
        "case_id": fresh_case_id,
        "category": "release_acceptance",
        "input_available": "1",
        "expected_available": "1",
        "verdict": "PASS",
        "detail": (
            f"{fresh_relative}; {fresh_command}; {fresh_log}; commit={commit}"
        ),
    }
}

run_relative = "acceptance/github_actions_run.json"
jobs_relative = "acceptance/github_actions_jobs.json"
github_command = "commands/github_actions_candidate_commit.sh"
github_log = "logs/github_actions_candidate_commit.log"
actions_run = evidence_json(run_relative)
jobs_payload = evidence_json(jobs_relative)
evidence_file(github_command)
evidence_file(github_log)
run_id = positive_integer(actions_run.get("id"), "run id")
run_attempt = positive_integer(actions_run.get("run_attempt"), "run attempt")
if actions_run.get("name") != "smoke-tests":
    raise SystemExit("GitHub Actions workflow mismatch")
if actions_run.get("event") != "push":
    raise SystemExit("GitHub Actions release run is not a push event")
if actions_run.get("head_branch") != "main":
    raise SystemExit("GitHub Actions release run is not a main-branch push")
if actions_run.get("path") != ".github/workflows/smoke-tests.yml":
    raise SystemExit("GitHub Actions workflow path mismatch")
if actions_run.get("head_sha") != commit:
    raise SystemExit("GitHub Actions run commit mismatch")
run_repository = actions_run.get("repository")
if not isinstance(run_repository, dict) or run_repository.get("full_name") != repository_slug:
    raise SystemExit("GitHub Actions run repository mismatch")
head_repository = actions_run.get("head_repository")
if not isinstance(head_repository, dict) or head_repository.get("full_name") != repository_slug:
    raise SystemExit("GitHub Actions head repository mismatch")
if actions_run.get("status") != "completed" or actions_run.get("conclusion") != "success":
    raise SystemExit("GitHub Actions workflow run is not successful")
run_url = f"https://github.com/{repository_slug}/actions/runs/{run_id}"
run_api_url = f"https://api.github.com/repos/{repository_slug}/actions/runs/{run_id}"
if actions_run.get("html_url") != run_url:
    raise SystemExit("GitHub Actions run URL mismatch")
if actions_run.get("url") != run_api_url:
    raise SystemExit("GitHub Actions run API URL mismatch")
if actions_run.get("jobs_url") != f"{run_api_url}/jobs":
    raise SystemExit("GitHub Actions jobs API URL mismatch")

jobs = jobs_payload.get("jobs")
if not isinstance(jobs, list) or not all(isinstance(job, dict) for job in jobs):
    raise SystemExit("GitHub Actions jobs inventory is invalid")
if jobs_payload.get("total_count") != len(jobs):
    raise SystemExit("GitHub Actions jobs inventory count mismatch")
job_ids = [positive_integer(job.get("id"), "job id") for job in jobs]
if len(job_ids) != len(set(job_ids)):
    raise SystemExit("GitHub Actions jobs inventory contains duplicate IDs")
for case_id, expectation in github_jobs.items():
    matching = [job for job in jobs if job.get("name") == expectation["name"]]
    if len(matching) != 1:
        raise SystemExit(
            f"missing or ambiguous GitHub Actions {expectation['platform']} evidence"
        )
    job = matching[0]
    labels = job.get("labels")
    if not isinstance(labels, list) or expectation["label"] not in labels:
        raise SystemExit(f"GitHub Actions {expectation['platform']} platform mismatch")
    if job.get("head_sha") != commit:
        raise SystemExit(f"GitHub Actions {expectation['platform']} commit mismatch")
    if job.get("run_id") != run_id or job.get("run_attempt") != run_attempt:
        raise SystemExit(f"GitHub Actions {expectation['platform']} run-attempt mismatch")
    if job.get("workflow_name") != "smoke-tests":
        raise SystemExit(f"GitHub Actions {expectation['platform']} workflow mismatch")
    if job.get("status") != "completed" or job.get("conclusion") != "success":
        raise SystemExit(f"GitHub Actions {expectation['platform']} job is not successful")
    job_id = positive_integer(job.get("id"), f"{expectation['platform']} job id")
    job_url = job.get("html_url")
    if job_url != f"{run_url}/job/{job_id}":
        raise SystemExit(f"GitHub Actions {expectation['platform']} job URL mismatch")
    if job.get("url") != f"https://api.github.com/repos/{repository_slug}/actions/jobs/{job_id}":
        raise SystemExit(f"GitHub Actions {expectation['platform']} job API URL mismatch")
    if job.get("run_url") != run_api_url:
        raise SystemExit(f"GitHub Actions {expectation['platform']} job run URL mismatch")
    expected_acceptance[case_id] = {
        "case_id": case_id,
        "category": "release_acceptance",
        "input_available": "1",
        "expected_available": "1",
        "verdict": "PASS",
        "detail": (
            f"{run_relative}; {jobs_relative}; {github_command}; {github_log}; "
            f"run_id={run_id}; job_id={job_id}; platform={expectation['platform']}; "
            f"event=push; commit={commit}; url={job_url}"
        ),
    }

verdicts = {"PASS", "FAIL", "XFAIL", "SKIP", "BLOCKED"}
required_pass = {
    "unit_known_answer", "cli_step_listing", "strict_generic_dry_run",
    "synthetic_longread_smoke", "synthetic_shortread_smoke",
    "synthetic_longread_nomethyl_smoke", "standalone_minimal_smoke", "package_build",
    "public_validation_matrix", "gm11906_default_run1", "gm11906_default_run2",
    "gm11906_lenient", "gm11906_strict", "gm12878_default_run1",
    "gm12878_default_run2", "gm12878_lenient", "gm12878_strict",
    "gm11906_repeatability", "gm12878_repeatability",
    "gm11906_visual_integrity", "gm12878_visual_integrity", "filter_profiles",
} | acceptance_case_ids
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
    if case.get("verdict") not in verdicts:
        raise SystemExit(f"invalid verdict: {case}")
    if case.get("verdict") == "PASS" and (
        case.get("input_available") != "1" or case.get("expected_available") != "1"
    ):
        raise SystemExit(f"unsupported PASS verdict: {case.get('case_id')}")
blockers = sorted(
    f"{case['case_id']}={case['verdict']}"
    for case in cases
    if case["verdict"] in {"FAIL", "BLOCKED"}
)
if blockers:
    raise SystemExit(f"release-blocking validation verdicts: {blockers}")
missing_required = sorted(required_pass - case_ids)
if missing_required:
    raise SystemExit(f"missing required release cases: {missing_required}")
nonpassing = sorted(
    case["case_id"] for case in cases
    if case["case_id"] in required_pass and case["verdict"] != "PASS"
)
if nonpassing:
    raise SystemExit(f"required release cases did not pass: {nonpassing}")
cases_by_id = {case["case_id"]: case for case in cases}
for case_id, expected in expected_acceptance.items():
    observed = cases_by_id[case_id]
    for field, expected_value in expected.items():
        if observed.get(field) != expected_value:
            raise SystemExit(
                f"acceptance case does not match evidence for {case_id} field {field}"
            )
observed_counts = Counter(case["verdict"] for case in cases)
expected_counts = {verdict: observed_counts.get(verdict, 0) for verdict in verdicts}
if run.get("case_count") != len(cases) or run.get("verdict_counts") != expected_counts:
    raise SystemExit("run.json case counts do not match cases.tsv")

public_provenance_paths = {
    "shortread_alignment": (
        "public_provenance/GM11906_MERRF_shortread.alignment.provenance.json"
    ),
    "longread_subset": (
        "public_provenance/GM12878_ONT_longread.fastq_subset.provenance.json"
    ),
    "longread_alignment": (
        "public_provenance/GM12878_ONT_longread.reduced_alignment.provenance.json"
    ),
    "selected_query_names": (
        "public_provenance/GM12878_ONT_longread.selected_qnames.txt"
    ),
}

def load_public_json(key):
    relative = public_provenance_paths[key]
    try:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid public provenance JSON: {relative}: {error}")
    if not isinstance(value, dict):
        raise SystemExit(f"public provenance is not an object: {relative}")
    return value

def provenance_record(value, label):
    if not isinstance(value, dict):
        raise SystemExit(f"public provenance {label} is not an object")
    if (
        not isinstance(value.get("name"), str)
        or not value.get("name")
        or Path(value["name"]).name != value["name"]
        or isinstance(value.get("bytes"), bool)
        or not isinstance(value.get("bytes"), int)
        or value["bytes"] <= 0
        or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256", "")))
    ):
        raise SystemExit(f"invalid public provenance record: {label}")
    if value.get("md5") is not None and not re.fullmatch(
        r"[0-9a-f]{32}", str(value["md5"])
    ):
        raise SystemExit(f"invalid public provenance MD5: {label}")
    return value

def same_record(left, right, label):
    for field in ("name", "bytes", "sha256", "md5"):
        if left.get(field) != right.get(field):
            raise SystemExit(f"public provenance linkage mismatch: {label} {field}")

def matches_file(record, path, label):
    if record["bytes"] != path.stat().st_size or record["sha256"] != digest(path):
        raise SystemExit(f"public provenance does not match packaged {label}")

short_provenance = load_public_json("shortread_alignment")
subset_provenance = load_public_json("longread_subset")
long_provenance = load_public_json("longread_alignment")
alignment_expectations = (
    (
        short_provenance,
        "GM11906_MERRF_reduced_shortread",
        "bwa-mem-samtools-sort-v1",
        "short-read",
    ),
    (
        long_provenance,
        "GM12878_SRR18110025_ONT_reduced_qn1000",
        "minimap2-map-ont-deterministic-fastq-subset-mapped-only-v1",
        "long-read",
    ),
)
for manifest, dataset_id, derivation_id, label in alignment_expectations:
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("provenance_type") != "public_alignment"
        or manifest.get("dataset_id") != dataset_id
    ):
        raise SystemExit(f"invalid public {label} alignment provenance identity")
    for field in ("alignment", "alignment_index", "reference", "reference_index"):
        provenance_record(manifest.get(field), f"{label} {field}")
    derivation = manifest.get("derivation")
    if not isinstance(derivation, dict) or derivation.get("derivation_id") != derivation_id:
        raise SystemExit(f"invalid public {label} alignment derivation")
    inputs = manifest.get("public_inputs")
    if not isinstance(inputs, list) or not inputs:
        raise SystemExit(f"missing public {label} alignment inputs")
    for index, record in enumerate(inputs):
        validated = provenance_record(record, f"{label} input {index}")
        if not isinstance(validated.get("label"), str) or not validated["label"]:
            raise SystemExit(f"invalid public {label} alignment input label")

if (
    subset_provenance.get("schema_version") != "1.0"
    or subset_provenance.get("provenance_type")
    != "deterministic_fastq_query_name_subset"
    or subset_provenance.get("dataset_id") != "GM12878_SRR18110025_ONT"
):
    raise SystemExit("invalid public long-read subset provenance identity")
source_fastq = provenance_record(subset_provenance.get("source_fastq"), "source FASTQ")
subset_fastq = provenance_record(subset_provenance.get("subset_fastq"), "subset FASTQ")
selected_record = provenance_record(
    subset_provenance.get("selected_query_names"), "selected query names"
)
selected_path = root / public_provenance_paths["selected_query_names"]
matches_file(selected_record, selected_path, "selected query names")
try:
    selected_names = selected_path.read_text(encoding="utf-8").splitlines()
except UnicodeDecodeError as error:
    raise SystemExit("selected query names are not UTF-8") from error
if (
    not selected_names
    or len(selected_names) != len(set(selected_names))
    or any(not name or name != name.strip() or any(c.isspace() for c in name) for name in selected_names)
):
    raise SystemExit("selected query names are empty, duplicated, or malformed")
selection = subset_provenance.get("selection")
selected_count = selection.get("selected_query_names") if isinstance(selection, dict) else None
if (
    not isinstance(selection, dict)
    or selection.get("algorithm") != "smallest_sha256_seeded_query_names_v1"
    or isinstance(selected_count, bool)
    or not isinstance(selected_count, int)
    or selected_count <= 0
    or selection.get("requested_query_names") != selected_count
    or selected_count != len(selected_names)
):
    raise SystemExit("invalid public long-read subset selection metadata")
long_inputs = {
    record.get("label"): record
    for record in long_provenance["public_inputs"]
    if isinstance(record, dict) and isinstance(record.get("label"), str)
}
if set(long_inputs) != {
    "SRR18110025_full_fastq", "deterministic_subset_fastq",
    "deterministic_subset_manifest", "selected_query_names",
}:
    raise SystemExit("incomplete public long-read alignment input inventory")
same_record(source_fastq, long_inputs["SRR18110025_full_fastq"], "source FASTQ")
same_record(subset_fastq, long_inputs["deterministic_subset_fastq"], "subset FASTQ")
same_record(selected_record, long_inputs["selected_query_names"], "selected names")
matches_file(
    long_inputs["deterministic_subset_manifest"],
    root / public_provenance_paths["longread_subset"],
    "subset manifest",
)
parameters = long_provenance["derivation"].get("parameters")
if not isinstance(parameters, dict) or (
    parameters.get("selected_query_names") != str(selected_count)
    or parameters.get("selection_seed") != selection.get("seed")
):
    raise SystemExit("public alignment is not tied to the selected query-name subset")
expected_public_inventory = [
    {
        "path": relative,
        "sha256": digest(root / relative),
        "source_case": (
            "gm11906_default_run1" if key == "shortread_alignment" else "gm12878_default_run1"
        ),
    }
    for key, relative in public_provenance_paths.items()
]
if identity.get("public_provenance") != expected_public_inventory:
    raise SystemExit("release identity public provenance inventory mismatch")

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
            members = sorted(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
            if len(members) != 1:
                raise SystemExit(f"invalid wheel metadata inventory: {path.name}")
            text = archive.read(members[0]).decode("utf-8")
        kind = "wheel"
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = sorted(
                (member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")),
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

dist_files = sorted(path for path in (root / "dist").rglob("*") if path.is_file())
declared_dist = identity.get("dist_artifacts", [])
declared_paths = {entry.get("path") for entry in declared_dist}
actual_dist_paths = {path.relative_to(root).as_posix() for path in dist_files}
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

states = {"ok", "not_configured", "not_applicable", "not_evaluable", "unavailable", "failed"}
for path in (root / "observed_normalized").rglob("*.tsv"):
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    if not rows or rows[0][:2] != ["metric", "value"]:
        continue
    for row in rows[1:]:
        if len(row) >= 2 and row[0] == "status" and row[1] not in states:
            raise SystemExit(f"invalid module status {row[1]!r} in {path}")
print(f"verified mito-overview {run['release_version']} packet at commit {run['git_commit']}")
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
    zenodo_reservation = validate_zenodo_reservation_evidence(
        getattr(args, "zenodo_reservation_evidence", None),
        args.doi,
    )
    release_identity = resolve_release_identity(
        args.repo_root,
        args.validation_root / "environment.txt",
        args.version,
        args.repository,
        args.commit,
        args.doi,
    )
    acceptance_rows = validate_acceptance_evidence(
        args.validation_root,
        str(release_identity["git_commit"]),
        str(release_identity["repository"]),
    )
    case_count, verdict_counts = validate_cases(
        args.validation_root / "cases.tsv",
        acceptance_rows,
    )
    validate_hash_manifest(public_root / "inputs.sha256", "public/inputs.sha256")
    public_provenance = validate_public_provenance(public_root)
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
    ):
        if not source.is_dir() or not any(path.is_file() for path in source.rglob("*")):
            raise ValueError(f"Required evidence directory is missing or empty: {source}")

    args.packet_root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(args.validation_root / "cases.tsv", args.packet_root / "cases.tsv")
    shutil.copy2(args.validation_root / "environment.txt", args.packet_root / "environment.txt")
    copy_tree(args.validation_root / "acceptance", args.packet_root / "acceptance")
    shutil.copy2(
        args.zenodo_reservation_evidence,
        args.packet_root / ZENODO_RESERVATION_PACKET_PATH,
    )
    copy_tree(args.validation_root / "commands", args.packet_root / "commands")
    copy_tree(public_root / "commands", args.packet_root / "commands" / "public")
    copy_tree(args.validation_root / "logs", args.packet_root / "logs")
    copy_tree(public_root / "logs", args.packet_root / "logs" / "public")
    copy_tree(args.validation_root / "dist", args.packet_root / "dist")
    copy_tree(args.validation_root / "expected", args.packet_root / "expected")
    copy_tree(
        public_root / "observed_normalized",
        args.packet_root / "observed_normalized",
    )
    shutil.copy2(
        public_root / "filter_profile_results.tsv",
        args.packet_root / "filter_profile_results.tsv",
    )
    shutil.copy2(public_root / "inputs.sha256", args.packet_root / "inputs.sha256")
    for key, specification in PUBLIC_PROVENANCE_FILES.items():
        destination = args.packet_root / str(specification["packet"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(public_root / str(specification["source"]), destination)

    release_identity["dist_artifacts"] = dist_artifacts
    release_identity["acceptance_cases"] = [row["case_id"] for row in acceptance_rows]
    release_identity["zenodo_reservation"] = zenodo_reservation
    release_identity["public_provenance"] = public_provenance
    (args.packet_root / "release_identity.json").write_text(
        json.dumps(release_identity, indent=2) + "\n",
        encoding="utf-8",
    )
    run = {
        "schema_version": "1.1",
        "release_version": release_identity["release_version"],
        "git_commit": release_identity["git_commit"],
        "repository": release_identity["repository"],
        "archive_doi": release_identity["archive_doi"],
        "archive_record_id": zenodo_reservation["record_id"],
        "doi_reservation_status": zenodo_reservation["reservation_status"],
        "doi_reservation_evidence": zenodo_reservation["evidence_path"],
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": case_count,
        "verdict_counts": verdict_counts,
        "claim_scope": "reproducible mode-gated mtDNA reporting workflow/resource",
        "diagnostic_validation_claimed": False,
    }
    (args.packet_root / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

    write_tsv(
        args.packet_root / "claim_evidence_matrix.tsv",
        ["claim_id", "bounded_claim", "evidence", "limitation"],
        [
            [
                "C1",
                "Shared filtered allele counting is deterministic on known-answer fixtures",
                "unit_known_answer; synthetic_longread_smoke; expected/TOY-SR-001.expected_alleles.tsv",
                "Reporting thresholds are not clinically calibrated",
            ],
            [
                "C2",
                "mvTool is offline by default with deterministic fixture coverage",
                "unit_known_answer; synthetic_longread_smoke",
                "No claim of live service availability",
            ],
            [
                "C3",
                "Minimal standalone BAM and CRAM contracts are preflighted",
                "unit_known_answer; strict_generic_dry_run; standalone_minimal_smoke",
                "Optional sidecars remain user supplied",
            ],
            [
                "C4",
                "The WGS fixture reports a 100/10 mt:nuclear depth ratio of 10.0",
                "unit_known_answer; expected/TOY-WGS-001.expected_copy_proxy.tsv",
                "Experimental depth proxy, not absolute copies per diploid cell",
            ],
            [
                "C5",
                "mt-only references suppress categorical NUMT interpretation",
                "unit_known_answer; gm12878_default_run1; gm12878_repeatability",
                "Alignment-ambiguity QC is not a formal NUMT classifier",
            ],
            [
                "C6",
                "Public proof-of-principle workflows reproduce normalized TSVs",
                (
                    "gm11906_repeatability; gm12878_repeatability; "
                    "filter_profile_results.tsv; public_provenance/"
                ),
                "Not a sensitivity, specificity, deletion-truth, or diagnostic benchmark",
            ],
        ],
    )
    write_tsv(
        args.packet_root / "public_data_sources.tsv",
        [
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
            "fastq_bytes",
            "metadata_checked_utc",
            "role",
            "redistribution",
        ],
        [
            [
                "GM11906 reduced short-read proof-of-principle",
                "SRR10804585",
                "PRJNA598179",
                "SAMN13699362",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_2.fastq.gz",
                "3f5ea26a5791894071462d4970bc9e5a;c5b408425612f63b33cefd2d49c157d1",
                "8795676;8817420",
                "2026-07-20",
                "default repeatability, m.8344A>G release gate, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
            [
                "GM11906 reduced short-read proof-of-principle",
                "SRR10804590",
                "PRJNA598179",
                "SAMN13699398",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_2.fastq.gz",
                "e8b5132a8be8c179bfc6dbc0f3e1bee9;4d6977526136739de2d90baa8d45b484",
                "1006749;795885",
                "2026-07-20",
                "default repeatability, m.8344A>G release gate, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
            [
                "GM11906 reduced short-read proof-of-principle",
                "SRR10804657",
                "PRJNA598179",
                "SAMN13699338",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_2.fastq.gz",
                "8f082f73cb64bf56ea8a053fe80eeb06;62b7d1b2294a580c021f5fa1f52609be",
                "21510555;21573731",
                "2026-07-20",
                "default repeatability, m.8344A>G release gate, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
            [
                "GM12878 ONT targeted-mt proof-of-principle",
                "SRR18110025",
                "PRJNA809571",
                "SAMN26195906",
                "GM12878",
                "OXFORD_NANOPORE",
                "GridION",
                "OTHER",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR181/025/SRR18110025/SRR18110025_1.fastq.gz",
                "d5bfb9aeba04cae5f3dd79462a42e5b0",
                "2033558460",
                "2026-07-20",
                "long-read repeatability, mt-only scope gating, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
        ],
    )

    write_verifier(args.packet_root / "verify_bundle.sh")
    artifact_rows: list[str] = []
    for path in sorted(args.packet_root.rglob("*")):
        if not path.is_file() or path.name == "artifacts.sha256":
            continue
        artifact_rows.append(f"{sha256(path)}  {path.relative_to(args.packet_root).as_posix()}")
    (args.packet_root / "artifacts.sha256").write_text(
        "\n".join(artifact_rows) + "\n", encoding="utf-8"
    )

    missing = [name for name in REQUIRED_TOP_LEVEL if not (args.packet_root / name).exists()]
    if missing:
        raise SystemExit(f"Packet is missing required entries: {missing}")

    args.zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(args.packet_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(args.packet_root).as_posix())
    print(args.zip_path)
    return args.zip_path


def main() -> None:
    build_packet(parse_args())


if __name__ == "__main__":
    main()
