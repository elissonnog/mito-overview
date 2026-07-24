#!/usr/bin/env python3
"""Stage only public report artifacts bound by normalized visual inventories."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
from pathlib import Path, PurePosixPath


INVENTORY_FIELDS = (
    "relative_path",
    "artifact_type",
    "bytes",
    "sha256",
    "width_px",
    "height_px",
    "integrity_status",
)
CASE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]*")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy exactly the HTML/PNG files named and hashed by "
            "observed_normalized/*/visual_artifact_inventory.tsv."
        )
    )
    parser.add_argument("results_root", type=Path)
    parser.add_argument("artifact_root", type=Path)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_directory(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} is missing, not a directory, or a symlink: {path}")


def safe_visual_path(raw: str, artifact_type: str) -> PurePosixPath:
    if any(character in raw for character in ("\x00", "\t", "\n", "\r")):
        raise ValueError("Visual artifact path contains a control character")
    relative = PurePosixPath(raw)
    if (
        relative.is_absolute()
        or len(relative.parts) != 2
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"Visual artifact path is unsafe or nested: {raw!r}")
    expected_type = {
        ("report", ".html"): "html",
        ("figures", ".png"): "png",
    }.get((relative.parts[0], relative.suffix.lower()))
    if expected_type is None or artifact_type != expected_type:
        raise ValueError(f"Visual artifact type/path mismatch: {raw!r}")
    return relative


def inventory_rows(path: Path) -> list[dict[str, str]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Visual inventory is missing or not a regular file: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != list(INVENTORY_FIELDS):
            raise ValueError(f"Visual inventory schema mismatch: {path}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Visual inventory is empty: {path}")
    return rows


def validate_source_file(
    case_root: Path,
    relative: PurePosixPath,
    row: dict[str, str],
) -> Path:
    parent = case_root / relative.parts[0]
    require_directory(parent, "Visual artifact source directory")
    source = parent / relative.name
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Visual artifact is missing or not a regular file: {source}")
    try:
        expected_bytes = int(row["bytes"])
    except ValueError as error:
        raise ValueError(f"Visual artifact byte count is invalid: {source}") from error
    if expected_bytes <= 0 or str(expected_bytes) != row["bytes"]:
        raise ValueError(f"Visual artifact byte count is noncanonical: {source}")
    if source.stat().st_size != expected_bytes:
        raise ValueError(f"Visual artifact byte count mismatch: {source}")
    if SHA256_PATTERN.fullmatch(row["sha256"]) is None:
        raise ValueError(f"Visual artifact SHA-256 is invalid: {source}")
    if sha256(source) != row["sha256"]:
        raise ValueError(f"Visual artifact SHA-256 mismatch: {source}")
    if row["integrity_status"] != "ok":
        raise ValueError(f"Visual artifact is not marked ok: {source}")
    return source


def stage_public_visual_artifacts(results_root: Path, artifact_root: Path) -> int:
    require_directory(results_root, "Public-validation results root")
    if artifact_root.is_symlink() or (
        artifact_root.exists() and not artifact_root.is_dir()
    ):
        raise ValueError(
            f"Public-validation artifact root is not a regular directory: {artifact_root}"
        )
    artifact_root.mkdir(parents=True, exist_ok=True)
    normalized_root = results_root / "observed_normalized"
    outputs_root = results_root / "outputs"
    require_directory(normalized_root, "Normalized public-validation evidence")
    require_directory(outputs_root, "Public-validation outputs root")

    destination_root = artifact_root / "results/report_artifacts/outputs"
    if destination_root.is_symlink() or (
        destination_root.exists()
        and (
            not destination_root.is_dir()
            or any(destination_root.iterdir())
        )
    ):
        raise ValueError(
            "Report-artifact destination must be absent or an empty regular directory"
        )

    inventories = sorted(normalized_root.rglob("visual_artifact_inventory.tsv"))
    if not inventories:
        raise ValueError("No normalized visual inventories were found")

    seen_cases: set[str] = set()
    staged_files = 0
    for inventory in inventories:
        relative_inventory = inventory.relative_to(normalized_root)
        if len(relative_inventory.parts) != 2:
            raise ValueError(f"Visual inventory is unexpectedly nested: {inventory}")
        case_id = relative_inventory.parts[0]
        if CASE_ID_PATTERN.fullmatch(case_id) is None:
            raise ValueError(f"Visual inventory case ID is unsafe: {case_id!r}")
        if case_id in seen_cases:
            raise ValueError(f"Duplicate visual inventory case ID: {case_id}")
        seen_cases.add(case_id)

        case_root = outputs_root / case_id
        require_directory(case_root, "Inventory-bound report case")
        seen_paths: set[PurePosixPath] = set()
        for row in inventory_rows(inventory):
            relative = safe_visual_path(row["relative_path"], row["artifact_type"])
            if relative in seen_paths:
                raise ValueError(
                    f"Duplicate visual artifact path for {case_id}: {relative}"
                )
            seen_paths.add(relative)
            source = validate_source_file(case_root, relative, row)
            destination = destination_root / case_id / Path(*relative.parts)
            if destination.exists() or destination.is_symlink():
                raise ValueError(f"Visual artifact destination already exists: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            staged_files += 1

    if staged_files == 0:
        raise ValueError("No visual artifacts were staged")
    return staged_files


def main() -> None:
    args = parse_args()
    count = stage_public_visual_artifacts(args.results_root, args.artifact_root)
    print(f"staged_public_visual_artifacts={count}")


if __name__ == "__main__":
    main()
