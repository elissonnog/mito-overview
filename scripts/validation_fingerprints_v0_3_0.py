"""Deterministic fingerprints for public-validation table contracts."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any


FINGERPRINT_FIELDS = (
    "candidate_table_sha256",
    "summary_inventory_sha256",
    "summary_schema_sha256",
)


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

    inventory = hashlib.sha256(b"mito-overview:summary-inventory:v1\0")
    schemas = hashlib.sha256(b"mito-overview:summary-schemas:v1\0")
    for path in files:
        relative = path.relative_to(summary_dir).as_posix()
        _add_text(inventory, relative)
        header = _read_header(path)
        _add_text(schemas, relative)
        schemas.update(len(header).to_bytes(8, "big"))
        for column in header:
            _add_text(schemas, column)

    candidate_path = summary_dir / "mito_heteroplasmy_candidates.tsv"
    if candidate_path not in files:
        raise ValueError(
            f"Candidate table is absent from summary inventory: {candidate_path}"
        )
    return {
        "candidate_table_sha256": _candidate_fingerprint(candidate_path),
        "summary_inventory_sha256": inventory.hexdigest(),
        "summary_schema_sha256": schemas.hexdigest(),
    }
