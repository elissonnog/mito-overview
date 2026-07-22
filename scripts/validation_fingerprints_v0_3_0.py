"""Deterministic fingerprints for public-validation table contracts."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable


FINGERPRINT_FIELDS = (
    "candidate_table_sha256",
    "summary_inventory_sha256",
    "summary_schema_sha256",
)
PUBLIC_VALIDATION_CASE_IDS = (
    "gm11906_default_run1",
    "gm11906_default_run2",
    "gm11906_lenient",
    "gm11906_strict",
    "gm12878_default_run1",
    "gm12878_default_run2",
    "gm12878_lenient",
    "gm12878_strict",
)
CANDIDATE_TABLE_NAME = "mito_heteroplasmy_candidates.tsv"
SUMMARY_SCHEMA_MANIFEST_NAME = "summary_schema_manifest.tsv"
SUMMARY_SCHEMA_MANIFEST_FIELDS = ("relative_path", "header_json")


def _add_text(digest: Any, value: str) -> None:
    encoded = value.encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)


def _read_header(path: Path) -> tuple[str, ...]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle, delimiter="\t"))
    except StopIteration as error:
        raise ValueError(f"TSV has no header: {path}") from error
    if not header or any(not column for column in header):
        raise ValueError(f"TSV has a blank or missing header field: {path}")
    if len(header) != len(set(header)):
        raise ValueError(f"TSV has duplicate header fields: {path}")
    return tuple(header)


def _summary_tsv_files(summary_dir: Path) -> list[Path]:
    if summary_dir.is_symlink() or not summary_dir.is_dir():
        raise ValueError(f"Summary directory is missing or unsafe: {summary_dir}")
    files = sorted(
        summary_dir.rglob("*.tsv"),
        key=lambda path: path.relative_to(summary_dir).as_posix(),
    )
    if not files:
        raise ValueError(f"Summary directory contains no TSV files: {summary_dir}")
    if any(path.is_symlink() or not path.is_file() for path in files):
        raise ValueError(
            f"Summary TSV inventory contains a non-regular file: {summary_dir}"
        )
    return files


def _validate_relative_tsv(value: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or relative.as_posix() != value
        or any(part in ("", ".", "..") for part in relative.parts)
        or relative.suffix != ".tsv"
    ):
        raise ValueError(f"Invalid summary-contract TSV path: {value!r}")
    return relative


def _contract_fingerprints(
    candidate_path: Path,
    schemas: Iterable[tuple[str, tuple[str, ...]]],
) -> dict[str, str]:
    entries = list(schemas)
    inventory = hashlib.sha256(b"mito-overview:summary-inventory:v1\0")
    schema_digest = hashlib.sha256(b"mito-overview:summary-schemas:v1\0")
    for relative, header in entries:
        _add_text(inventory, relative)
        _add_text(schema_digest, relative)
        schema_digest.update(len(header).to_bytes(8, "big"))
        for column in header:
            _add_text(schema_digest, column)
    return {
        "candidate_table_sha256": _candidate_fingerprint(candidate_path),
        "summary_inventory_sha256": inventory.hexdigest(),
        "summary_schema_sha256": schema_digest.hexdigest(),
    }


def _candidate_fingerprint(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = tuple(next(reader))
        except StopIteration as error:
            raise ValueError(f"Candidate TSV has no header: {path}") from error
        if not header or any(not column for column in header):
            raise ValueError(
                f"Candidate TSV has a blank or missing header field: {path}"
            )
        if len(header) != len(set(header)):
            raise ValueError(f"Candidate TSV has duplicate header fields: {path}")
        rows = [tuple(row) for row in reader]

    if any(len(row) != len(header) for row in rows):
        raise ValueError(f"Candidate TSV contains a row-width mismatch: {path}")

    digest = hashlib.sha256(b"mito-overview:candidate-table:v1\0")
    _add_text(digest, path.name)
    digest.update(len(header).to_bytes(8, "big"))
    for column in header:
        _add_text(digest, column)
    ordered_rows = sorted(rows)
    digest.update(len(ordered_rows).to_bytes(8, "big"))
    for row in ordered_rows:
        for value in row:
            _add_text(digest, value)
    return digest.hexdigest()


def summary_contract_fingerprints(summary_dir: Path) -> dict[str, str]:
    """Fingerprint candidate rows plus the closed summary inventory and schemas.

    Candidate rows are sorted before hashing so biologically equivalent row order is
    ignored. Summary inventory and schema fingerprints retain exact relative paths and
    column order. The function reads only headers outside the candidate table.
    """

    files = _summary_tsv_files(summary_dir)
    schemas = [
        (path.relative_to(summary_dir).as_posix(), _read_header(path))
        for path in files
    ]
    candidate_path = summary_dir / CANDIDATE_TABLE_NAME
    if candidate_path not in files:
        raise ValueError(
            f"Candidate table is absent from summary inventory: {candidate_path}"
        )
    return _contract_fingerprints(candidate_path, schemas)


def read_summary_schema_manifest(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    """Read and strictly validate a compact summary-schema manifest."""

    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Summary-schema manifest is missing or unsafe: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != SUMMARY_SCHEMA_MANIFEST_FIELDS:
            raise ValueError(f"Summary-schema manifest has an invalid header: {path}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Summary-schema manifest is empty: {path}")

    entries: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()
    for row in rows:
        relative = _validate_relative_tsv(row["relative_path"]).as_posix()
        if relative in seen:
            raise ValueError(f"Summary-schema manifest has a duplicate path: {relative}")
        seen.add(relative)
        try:
            parsed = json.loads(row["header_json"])
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Summary-schema manifest has invalid header JSON: {relative}"
            ) from error
        if (
            not isinstance(parsed, list)
            or not parsed
            or any(not isinstance(column, str) or not column for column in parsed)
            or len(parsed) != len(set(parsed))
        ):
            raise ValueError(
                f"Summary-schema manifest has an invalid TSV header: {relative}"
            )
        entries.append((relative, tuple(parsed)))
    if [relative for relative, _ in entries] != sorted(seen):
        raise ValueError("Summary-schema manifest paths are not canonically sorted")
    return entries


def compact_summary_contract_fingerprints(contract_dir: Path) -> dict[str, str]:
    """Recompute summary fingerprints from compact, packet-safe evidence."""

    if contract_dir.is_symlink() or not contract_dir.is_dir():
        raise ValueError(f"Summary-contract directory is missing or unsafe: {contract_dir}")
    entries = list(contract_dir.iterdir())
    expected_names = {CANDIDATE_TABLE_NAME, SUMMARY_SCHEMA_MANIFEST_NAME}
    if (
        {entry.name for entry in entries} != expected_names
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise ValueError(
            f"Summary-contract directory inventory is invalid: {contract_dir}"
        )

    candidate_path = contract_dir / CANDIDATE_TABLE_NAME
    schemas = read_summary_schema_manifest(
        contract_dir / SUMMARY_SCHEMA_MANIFEST_NAME
    )
    schema_by_path = dict(schemas)
    if CANDIDATE_TABLE_NAME not in schema_by_path:
        raise ValueError("Summary-schema manifest omits the candidate table")
    if _read_header(candidate_path) != schema_by_path[CANDIDATE_TABLE_NAME]:
        raise ValueError("Candidate table header disagrees with the schema manifest")
    return _contract_fingerprints(candidate_path, schemas)


def write_compact_summary_contract(
    summary_dir: Path,
    contract_dir: Path,
) -> dict[str, str]:
    """Write minimal evidence that reproduces all three summary fingerprints."""

    source_fingerprints = summary_contract_fingerprints(summary_dir)
    if contract_dir.is_symlink():
        raise ValueError(f"Summary-contract destination is a symlink: {contract_dir}")
    if contract_dir.exists():
        if not contract_dir.is_dir() or any(contract_dir.iterdir()):
            raise ValueError(
                f"Summary-contract destination must be absent or empty: {contract_dir}"
            )
    else:
        contract_dir.mkdir(parents=True)

    files = _summary_tsv_files(summary_dir)
    schemas = [
        (path.relative_to(summary_dir).as_posix(), _read_header(path))
        for path in files
    ]
    shutil.copyfile(
        summary_dir / CANDIDATE_TABLE_NAME,
        contract_dir / CANDIDATE_TABLE_NAME,
    )
    with (contract_dir / SUMMARY_SCHEMA_MANIFEST_NAME).open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=SUMMARY_SCHEMA_MANIFEST_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for relative, header in schemas:
            writer.writerow(
                {
                    "relative_path": relative,
                    "header_json": json.dumps(
                        list(header), ensure_ascii=True, separators=(",", ":")
                    ),
                }
            )

    compact_fingerprints = compact_summary_contract_fingerprints(contract_dir)
    if compact_fingerprints != source_fingerprints:
        raise ValueError("Compact summary contract does not reproduce source fingerprints")
    return compact_fingerprints
