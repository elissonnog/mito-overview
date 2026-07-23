"""Auditable provenance helpers for public validation alignments.

These helpers are intentionally separate from the reporting workflow. They bind
cached validation artifacts to their public inputs and construct deterministic
read-name subsets without changing the allele-counting depth contract.
"""

from __future__ import annotations

import hashlib
import heapq
import gzip
import io
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pysam


SCHEMA_VERSION = "1.0"


class ProvenanceError(ValueError):
    """Raised when a cached validation artifact does not match its manifest."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_file(path: Path, *, include_md5: bool = False) -> dict[str, object]:
    """Return portable size and digest metadata after one sequential read."""

    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    sha256 = hashlib.sha256()
    md5 = hashlib.md5() if include_md5 else None  # noqa: S324 - archival identity only
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            sha256.update(chunk)
            if md5 is not None:
                md5.update(chunk)
    record: dict[str, object] = {
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256.hexdigest(),
    }
    if md5 is not None:
        record["md5"] = md5.hexdigest()
    return record


def alignment_index_path(alignment_path: Path) -> Path:
    """Resolve the standard adjacent BAM or CRAM index path."""

    alignment_path = alignment_path.resolve()
    if alignment_path.suffix.lower() == ".bam":
        candidates = (
            Path(f"{alignment_path}.bai"),
            alignment_path.with_suffix(".bai"),
        )
    elif alignment_path.suffix.lower() == ".cram":
        candidates = (
            Path(f"{alignment_path}.crai"),
            alignment_path.with_suffix(".crai"),
        )
    else:
        raise ProvenanceError(f"Unsupported alignment extension: {alignment_path}")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Alignment index not found for {alignment_path}")


def reference_index_path(reference_path: Path) -> Path:
    path = Path(f"{reference_path.resolve()}.fai")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def tool_version(tool: str) -> str:
    """Capture a concise tool version without assuming one CLI convention."""

    attempts = ([tool, "--version"], [tool, "version"], [tool])
    for command in attempts:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        output = (result.stdout + "\n" + result.stderr).strip()
        if not output:
            continue
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if result.returncode == 0:
            return lines[0]
        version_lines = [line for line in lines if line.lower().startswith("version:")]
        if version_lines:
            return version_lines[0].split(":", 1)[1].strip()
    return "unavailable"


def _input_records(inputs: Mapping[str, Path]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for label, path in sorted(inputs.items()):
        if not label:
            raise ProvenanceError("Input labels must be nonempty")
        record = digest_file(path, include_md5=True)
        record["label"] = label
        records.append(record)
    if not records:
        raise ProvenanceError("At least one public input is required")
    return records


def _write_json_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite provenance manifest: {path}")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def create_alignment_provenance(
    *,
    manifest_path: Path,
    dataset_id: str,
    alignment_path: Path,
    reference_path: Path,
    inputs: Mapping[str, Path],
    derivation_id: str,
    command_template: str,
    parameters: Mapping[str, str],
    tools: Sequence[str],
) -> dict[str, object]:
    """Record an alignment and the exact public inputs used to construct it."""

    alignment_path = alignment_path.resolve()
    reference_path = reference_path.resolve()
    pysam.quickcheck(str(alignment_path))
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "provenance_type": "public_alignment",
        "dataset_id": dataset_id,
        "generated_utc": _utc_now(),
        "alignment": digest_file(alignment_path),
        "alignment_index": digest_file(alignment_index_path(alignment_path)),
        "reference": digest_file(reference_path),
        "reference_index": digest_file(reference_index_path(reference_path)),
        "public_inputs": _input_records(inputs),
        "derivation": _expected_alignment_derivation(
            derivation_id=derivation_id,
            command_template=command_template,
            parameters=parameters,
            tools=tools,
        ),
    }
    _write_json_exclusive(manifest_path, payload)
    return payload


def _assert_record_matches(label: str, expected: Mapping[str, object], path: Path) -> None:
    include_md5 = "md5" in expected
    observed = digest_file(path, include_md5=include_md5)
    for field in ("bytes", "sha256", "md5"):
        if field in expected and observed.get(field) != expected.get(field):
            raise ProvenanceError(
                f"{label} {field} mismatch for {path}: "
                f"expected {expected.get(field)}, observed {observed.get(field)}"
            )


def _assert_complete_digest_record(
    label: str,
    expected: object,
    path: Path,
    *,
    require_md5: bool,
) -> None:
    """Require the complete portable digest contract before comparing a file."""

    if not isinstance(expected, Mapping):
        raise ProvenanceError(f"{label} digest record must be an object")
    required_fields = {"name", "bytes", "sha256"}
    if require_md5:
        required_fields.add("md5")
    if set(expected) != required_fields:
        raise ProvenanceError(
            f"{label} digest field inventory mismatch: "
            f"expected {sorted(required_fields)}, observed {sorted(expected)}"
        )
    resolved = path.resolve()
    if expected.get("name") != resolved.name:
        raise ProvenanceError(
            f"{label} name mismatch for {resolved}: "
            f"expected {expected.get('name')}, observed {resolved.name}"
        )
    _assert_record_matches(label, expected, resolved)


def _expected_alignment_derivation(
    *,
    derivation_id: str,
    command_template: str,
    parameters: Mapping[str, str],
    tools: Sequence[str],
) -> dict[str, object]:
    if not derivation_id.strip() or not command_template.strip():
        raise ProvenanceError("Alignment derivation identity and command must be nonempty")
    if any(not key or not isinstance(value, str) for key, value in parameters.items()):
        raise ProvenanceError("Alignment derivation parameters must be nonempty string pairs")
    if any(not tool for tool in tools) or len(set(tools)) != len(tools):
        raise ProvenanceError("Alignment derivation tools must be nonempty and unique")
    return {
        "derivation_id": derivation_id,
        "command_template": command_template,
        "parameters": dict(sorted(parameters.items())),
        "tool_versions": {tool: tool_version(tool) for tool in sorted(tools)},
    }


def load_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProvenanceError(f"Cannot read provenance manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProvenanceError(f"Provenance manifest must contain one JSON object: {path}")
    return payload


def verify_alignment_provenance(
    *,
    manifest_path: Path,
    dataset_id: str,
    alignment_path: Path,
    reference_path: Path,
    inputs: Mapping[str, Path],
    derivation_id: str,
    command_template: str,
    parameters: Mapping[str, str],
    tools: Sequence[str],
) -> dict[str, object]:
    """Verify that a cached alignment remains bound to the expected inputs."""

    payload = load_manifest(manifest_path)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ProvenanceError("Unsupported public alignment provenance schema")
    if payload.get("provenance_type") != "public_alignment":
        raise ProvenanceError("Manifest is not a public alignment provenance record")
    if payload.get("dataset_id") != dataset_id:
        raise ProvenanceError(
            f"Dataset mismatch: expected {dataset_id}, observed {payload.get('dataset_id')}"
        )
    derivation = payload.get("derivation")
    expected_derivation = _expected_alignment_derivation(
        derivation_id=derivation_id,
        command_template=command_template,
        parameters=parameters,
        tools=tools,
    )
    if not isinstance(derivation, dict):
        raise ProvenanceError(f"Derivation metadata is missing for {manifest_path}")
    for field, expected in expected_derivation.items():
        if derivation.get(field) != expected:
            raise ProvenanceError(
                f"Derivation {field} mismatch for {manifest_path}: "
                f"expected {expected!r}, observed {derivation.get(field)!r}"
            )
    if set(derivation) != set(expected_derivation):
        raise ProvenanceError(f"Derivation field inventory mismatch for {manifest_path}")

    alignment_path = alignment_path.resolve()
    reference_path = reference_path.resolve()
    _assert_record_matches("alignment", payload["alignment"], alignment_path)
    _assert_record_matches(
        "alignment index", payload["alignment_index"], alignment_index_path(alignment_path)
    )
    _assert_record_matches("reference", payload["reference"], reference_path)
    _assert_record_matches(
        "reference index", payload["reference_index"], reference_index_path(reference_path)
    )

    manifest_inputs = payload.get("public_inputs")
    if not isinstance(manifest_inputs, list):
        raise ProvenanceError("Manifest public_inputs must be a list")
    records_by_label: dict[str, dict[str, object]] = {}
    for index, record in enumerate(manifest_inputs):
        if not isinstance(record, dict):
            raise ProvenanceError(
                f"Manifest public input {index} must be an object"
            )
        label = record.get("label")
        if not isinstance(label, str) or not label:
            raise ProvenanceError(
                f"Manifest public input {index} has an invalid label"
            )
        if label in records_by_label:
            raise ProvenanceError(f"Duplicate public input label: {label}")
        records_by_label[label] = record
    if set(records_by_label) != set(inputs):
        raise ProvenanceError(
            "Public input labels differ: "
            f"expected {sorted(inputs)}, observed {sorted(records_by_label)}"
        )
    for label, path in sorted(inputs.items()):
        _assert_record_matches(f"public input {label}", records_by_label[label], path)
    pysam.quickcheck(str(alignment_path))
    return payload


def _query_name_score(seed: str, query_name: str) -> int:
    value = f"{seed}\0{query_name}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(value).digest(), byteorder="big")


def _open_fastq_text(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="ascii", newline="")
    return path.open("r", encoding="ascii", newline="")


def _iter_fastq_records(path: Path):
    with _open_fastq_text(path) as handle:
        record_number = 0
        while True:
            header = handle.readline()
            if not header:
                break
            sequence = handle.readline()
            plus = handle.readline()
            quality = handle.readline()
            record_number += 1
            if not sequence or not plus or not quality:
                raise ProvenanceError(
                    f"Truncated FASTQ record {record_number} in {path}"
                )
            if not header.startswith("@") or not plus.startswith("+"):
                raise ProvenanceError(
                    f"Malformed FASTQ record {record_number} in {path}"
                )
            query_name = header[1:].strip().split(maxsplit=1)[0]
            if not query_name:
                raise ProvenanceError(
                    f"FASTQ record {record_number} has no query name in {path}"
                )
            if len(sequence.rstrip("\r\n")) != len(quality.rstrip("\r\n")):
                raise ProvenanceError(
                    f"FASTQ sequence/quality length mismatch at record {record_number} in {path}"
                )
            yield query_name, (header, sequence, plus, quality)


def select_fastq_query_names(
    source_fastq: Path,
    *,
    requested_count: int,
    seed: str,
) -> tuple[list[str], int]:
    """Select a deterministic bounded set of names from a complete FASTQ."""

    if requested_count < 1:
        raise ValueError("requested_count must be at least 1")
    heap: list[tuple[int, str]] = []
    selected: set[str] = set()
    records_seen = 0
    for query_name, _ in _iter_fastq_records(source_fastq):
        records_seen += 1
        if query_name in selected:
            continue
        score = _query_name_score(seed, query_name)
        entry = (-score, query_name)
        if len(heap) < requested_count:
            heapq.heappush(heap, entry)
            selected.add(query_name)
            continue
        if score >= -heap[0][0]:
            continue
        _, removed_name = heapq.heapreplace(heap, entry)
        selected.remove(removed_name)
        selected.add(query_name)
    return sorted(selected), records_seen


def create_deterministic_fastq_subset(
    *,
    source_fastq: Path,
    output_fastq: Path,
    output_manifest: Path,
    selected_names_path: Path,
    dataset_id: str,
    requested_count: int,
    seed: str,
) -> dict[str, object]:
    """Create a gzip-stable FASTQ subset linked to the complete public run."""

    source_fastq = source_fastq.resolve()
    output_fastq = output_fastq.resolve()
    output_manifest = output_manifest.resolve()
    selected_names_path = selected_names_path.resolve()
    for path in (output_fastq, output_manifest, selected_names_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite deterministic FASTQ artifact: {path}")
    selected_names, records_seen = select_fastq_query_names(
        source_fastq,
        requested_count=requested_count,
        seed=seed,
    )
    if len(selected_names) != requested_count:
        raise ProvenanceError(
            f"Requested {requested_count} FASTQ names but selected {len(selected_names)}"
        )
    selected_set = set(selected_names)
    output_fastq.parent.mkdir(parents=True, exist_ok=True)
    selected_names_path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{output_fastq.name}.",
        suffix=".tmp",
        dir=output_fastq.parent,
    )
    os.close(temp_fd)
    temp_output = Path(temp_name)
    records_written = 0
    try:
        with temp_output.open("wb") as raw_output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_output, mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding="ascii", newline="") as text_output:
                    for query_name, record in _iter_fastq_records(source_fastq):
                        if query_name not in selected_set:
                            continue
                        text_output.writelines(record)
                        records_written += 1
        if records_written != requested_count:
            raise ProvenanceError(
                f"Expected {requested_count} selected FASTQ records, wrote {records_written}"
            )
        temp_output.replace(output_fastq)
    except Exception:
        temp_output.unlink(missing_ok=True)
        output_fastq.unlink(missing_ok=True)
        raise

    selected_names_path.write_text("\n".join(selected_names) + "\n", encoding="utf-8")
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "provenance_type": "deterministic_fastq_query_name_subset",
        "dataset_id": dataset_id,
        "generated_utc": _utc_now(),
        "selection": {
            "algorithm": "smallest_sha256_seeded_query_names_v1",
            "seed": seed,
            "requested_query_names": requested_count,
            "selected_query_names": len(selected_names),
            "source_records_seen": records_seen,
            "subset_records_written": records_written,
        },
        "source_fastq": digest_file(source_fastq, include_md5=True),
        "subset_fastq": digest_file(output_fastq, include_md5=True),
        "selected_query_names": digest_file(selected_names_path, include_md5=True),
    }
    _write_json_exclusive(output_manifest, payload)
    return payload


def verify_deterministic_fastq_subset(
    *,
    source_fastq: Path,
    output_fastq: Path,
    output_manifest: Path,
    selected_names_path: Path,
    dataset_id: str,
    requested_count: int,
    seed: str,
) -> dict[str, object]:
    payload = load_manifest(output_manifest)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ProvenanceError("Unsupported deterministic FASTQ provenance schema")
    if payload.get("provenance_type") != "deterministic_fastq_query_name_subset":
        raise ProvenanceError("Manifest is not a deterministic FASTQ provenance record")
    if payload.get("dataset_id") != dataset_id:
        raise ProvenanceError("Deterministic FASTQ dataset identity mismatch")
    selection = payload.get("selection")
    if not isinstance(selection, dict):
        raise ProvenanceError("Deterministic FASTQ selection metadata is missing")
    _assert_complete_digest_record(
        "source FASTQ", payload.get("source_fastq"), source_fastq, require_md5=True
    )
    expected_names, source_records_seen = select_fastq_query_names(
        source_fastq,
        requested_count=requested_count,
        seed=seed,
    )
    if len(expected_names) != requested_count:
        raise ProvenanceError(
            f"Requested {requested_count} FASTQ names but recomputed {len(expected_names)}"
        )
    expected_selection = {
        "algorithm": "smallest_sha256_seeded_query_names_v1",
        "seed": seed,
        "requested_query_names": requested_count,
        "selected_query_names": requested_count,
        "source_records_seen": source_records_seen,
        "subset_records_written": requested_count,
    }
    for key, expected in expected_selection.items():
        if selection.get(key) != expected:
            raise ProvenanceError(
                f"Deterministic FASTQ {key} mismatch: expected {expected}, "
                f"observed {selection.get(key)}"
            )
    if set(selection) != set(expected_selection):
        raise ProvenanceError("Deterministic FASTQ selection field inventory mismatch")
    _assert_complete_digest_record(
        "subset FASTQ", payload.get("subset_fastq"), output_fastq, require_md5=True
    )
    _assert_complete_digest_record(
        "selected FASTQ query names",
        payload.get("selected_query_names"),
        selected_names_path,
        require_md5=True,
    )
    selected_names = selected_names_path.read_text(encoding="utf-8").splitlines()
    if len(selected_names) != requested_count or selected_names != sorted(set(selected_names)):
        raise ProvenanceError("Selected FASTQ query-name ledger is incomplete or noncanonical")
    if selected_names != expected_names:
        raise ProvenanceError(
            "Selected FASTQ query-name ledger is not the seeded minimum-score selection"
        )
    subset_names = [query_name for query_name, _ in _iter_fastq_records(output_fastq)]
    if (
        len(subset_names) != requested_count
        or len(set(subset_names)) != requested_count
        or set(subset_names) != set(expected_names)
    ):
        raise ProvenanceError(
            "Subset FASTQ records do not match the deterministic query-name selection"
        )
    return payload


def select_query_names(
    alignment_path: Path,
    *,
    requested_count: int,
    seed: str,
) -> tuple[list[str], int]:
    """Select the smallest seeded SHA-256 query-name scores with a bounded heap."""

    if requested_count < 1:
        raise ValueError("requested_count must be at least 1")
    heap: list[tuple[int, str]] = []
    selected: set[str] = set()
    primary_records_seen = 0
    with pysam.AlignmentFile(str(alignment_path), "rb") as source:
        for record in source.fetch(until_eof=True):
            if record.is_unmapped or record.is_secondary or record.is_supplementary:
                continue
            query_name = record.query_name
            if not query_name:
                continue
            primary_records_seen += 1
            if query_name in selected:
                continue
            score = _query_name_score(seed, query_name)
            entry = (-score, query_name)
            if len(heap) < requested_count:
                heapq.heappush(heap, entry)
                selected.add(query_name)
                continue
            largest_score = -heap[0][0]
            if score >= largest_score:
                continue
            _, removed_name = heapq.heapreplace(heap, entry)
            selected.remove(removed_name)
            selected.add(query_name)
    return sorted(selected), primary_records_seen


def create_deterministic_subset(
    *,
    source_alignment: Path,
    source_manifest: Path,
    output_alignment: Path,
    output_manifest: Path,
    selected_names_path: Path,
    dataset_id: str,
    requested_count: int,
    seed: str,
) -> dict[str, object]:
    """Write all mapped records for a deterministic set of primary query names."""

    source_alignment = source_alignment.resolve()
    source_manifest = source_manifest.resolve()
    output_alignment = output_alignment.resolve()
    output_manifest = output_manifest.resolve()
    selected_names_path = selected_names_path.resolve()
    for path in (output_alignment, output_manifest, selected_names_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite deterministic subset artifact: {path}")
    output_index = Path(f"{output_alignment}.bai")
    if output_index.exists():
        raise FileExistsError(f"Refusing to overwrite deterministic subset index: {output_index}")

    selected_names, primary_records_seen = select_query_names(
        source_alignment,
        requested_count=requested_count,
        seed=seed,
    )
    if len(selected_names) != requested_count:
        raise ProvenanceError(
            f"Requested {requested_count} query names but only selected {len(selected_names)}"
        )
    selected_set = set(selected_names)
    output_alignment.parent.mkdir(parents=True, exist_ok=True)
    selected_names_path.parent.mkdir(parents=True, exist_ok=True)

    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{output_alignment.name}.",
        suffix=".tmp.bam",
        dir=output_alignment.parent,
    )
    os.close(temp_fd)
    temp_alignment = Path(temp_name)
    records_written = 0
    primary_records_written = 0
    try:
        with pysam.AlignmentFile(str(source_alignment), "rb") as source:
            with pysam.AlignmentFile(str(temp_alignment), "wb", header=source.header) as output:
                for record in source.fetch(until_eof=True):
                    if record.is_unmapped or record.query_name not in selected_set:
                        continue
                    output.write(record)
                    records_written += 1
                    if not record.is_secondary and not record.is_supplementary:
                        primary_records_written += 1
        temp_alignment.replace(output_alignment)
        pysam.index(str(output_alignment))
    except Exception:
        temp_alignment.unlink(missing_ok=True)
        output_alignment.unlink(missing_ok=True)
        output_index.unlink(missing_ok=True)
        raise

    selected_names_path.write_text("\n".join(selected_names) + "\n", encoding="utf-8")
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "provenance_type": "deterministic_query_name_subset",
        "dataset_id": dataset_id,
        "generated_utc": _utc_now(),
        "selection": {
            "algorithm": "smallest_sha256_seeded_query_names_v1",
            "seed": seed,
            "requested_primary_query_names": requested_count,
            "selected_primary_query_names": len(selected_names),
            "primary_records_seen": primary_records_seen,
            "primary_records_written": primary_records_written,
            "mapped_records_written": records_written,
        },
        "source_alignment": digest_file(source_alignment),
        "source_alignment_index": digest_file(alignment_index_path(source_alignment)),
        "source_provenance": digest_file(source_manifest),
        "subset_alignment": digest_file(output_alignment),
        "subset_alignment_index": digest_file(alignment_index_path(output_alignment)),
        "selected_query_names": digest_file(selected_names_path),
    }
    _write_json_exclusive(output_manifest, payload)
    return payload


def verify_deterministic_subset(
    *,
    source_alignment: Path,
    source_manifest: Path,
    output_alignment: Path,
    output_manifest: Path,
    selected_names_path: Path,
    dataset_id: str,
    requested_count: int,
    seed: str,
) -> dict[str, object]:
    payload = load_manifest(output_manifest)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ProvenanceError("Unsupported deterministic subset provenance schema")
    if payload.get("provenance_type") != "deterministic_query_name_subset":
        raise ProvenanceError("Manifest is not a deterministic subset provenance record")
    if payload.get("dataset_id") != dataset_id:
        raise ProvenanceError("Deterministic subset dataset identity mismatch")
    selection = payload.get("selection")
    if not isinstance(selection, dict):
        raise ProvenanceError("Deterministic subset selection metadata is missing")
    expected_selection = {
        "algorithm": "smallest_sha256_seeded_query_names_v1",
        "seed": seed,
        "requested_primary_query_names": requested_count,
        "selected_primary_query_names": requested_count,
    }
    for key, expected in expected_selection.items():
        if selection.get(key) != expected:
            raise ProvenanceError(
                f"Deterministic subset {key} mismatch: expected {expected}, "
                f"observed {selection.get(key)}"
            )
    _assert_record_matches("source alignment", payload["source_alignment"], source_alignment)
    _assert_record_matches(
        "source alignment index",
        payload["source_alignment_index"],
        alignment_index_path(source_alignment),
    )
    _assert_record_matches("source provenance", payload["source_provenance"], source_manifest)
    _assert_record_matches("subset alignment", payload["subset_alignment"], output_alignment)
    _assert_record_matches(
        "subset alignment index",
        payload["subset_alignment_index"],
        alignment_index_path(output_alignment),
    )
    _assert_record_matches(
        "selected query names", payload["selected_query_names"], selected_names_path
    )
    selected_names = selected_names_path.read_text(encoding="utf-8").splitlines()
    if len(selected_names) != requested_count or selected_names != sorted(set(selected_names)):
        raise ProvenanceError("Selected query-name ledger is incomplete or noncanonical")
    pysam.quickcheck(str(output_alignment))
    return payload


def parse_labeled_paths(values: Iterable[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        try:
            label, path = value.split("=", 1)
        except ValueError as exc:
            raise ProvenanceError(f"Expected LABEL=PATH, observed: {value}") from exc
        if not label or not path or label in parsed:
            raise ProvenanceError(f"Invalid or duplicate labeled path: {value}")
        parsed[label] = Path(path)
    return parsed


def parse_key_values(values: Iterable[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        try:
            key, item = value.split("=", 1)
        except ValueError as exc:
            raise ProvenanceError(f"Expected KEY=VALUE, observed: {value}") from exc
        if not key or key in parsed:
            raise ProvenanceError(f"Invalid or duplicate parameter: {value}")
        parsed[key] = item
    return parsed
