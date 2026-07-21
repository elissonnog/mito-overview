#!/usr/bin/env python3
"""Safely extract a validation ZIP after a complete destination preflight."""

from __future__ import annotations

import argparse
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath


class UnsafeZipError(ValueError):
    """Raised when an archive cannot be extracted without path ambiguity."""


def _canonical_member(info: zipfile.ZipInfo) -> tuple[str, tuple[str, ...], bool]:
    name = info.filename
    member = PurePosixPath(name)
    mode_type = stat.S_IFMT((info.external_attr >> 16) & 0o177777)
    is_directory = info.is_dir()

    if (
        not name
        or "\\" in name
        or member.is_absolute()
        or ".." in member.parts
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise UnsafeZipError(f"unsafe ZIP member path: {name!r}")
    if info.flag_bits & 0x1:
        raise UnsafeZipError(f"encrypted ZIP members are not supported: {name!r}")
    if mode_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise UnsafeZipError(f"non-regular ZIP member is not supported: {name!r}")
    if (mode_type == stat.S_IFDIR) != is_directory and mode_type != 0:
        raise UnsafeZipError(f"ZIP member type disagrees with its path: {name!r}")

    parts = member.parts
    if not parts:
        raise UnsafeZipError(f"ZIP member resolves to the extraction root: {name!r}")
    canonical = "/".join(parts)
    return canonical, parts, is_directory


def _preflight(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, tuple[str, ...], bool]]:
    infos = archive.infolist()
    if not infos:
        raise UnsafeZipError("validation ZIP is empty")

    planned: list[tuple[zipfile.ZipInfo, tuple[str, ...], bool]] = []
    destinations: dict[str, str] = {}
    files: set[str] = set()
    for info in infos:
        canonical, parts, is_directory = _canonical_member(info)
        previous = destinations.get(canonical)
        if previous is not None:
            raise UnsafeZipError(
                "canonical destination collision: "
                f"{previous!r} and {info.filename!r} both resolve to {canonical!r}"
            )
        destinations[canonical] = info.filename
        if not is_directory:
            files.add(canonical)
        planned.append((info, parts, is_directory))

    for canonical, original in destinations.items():
        parts = canonical.split("/")
        for index in range(1, len(parts)):
            ancestor = "/".join(parts[:index])
            if ancestor in files:
                raise UnsafeZipError(
                    f"file/directory destination conflict: {destinations[ancestor]!r} "
                    f"is an ancestor of {original!r}"
                )
    return planned


def safe_extract(zip_path: Path, destination_root: Path) -> None:
    """Extract regular files only, rejecting aliases before creating output."""

    zip_path = zip_path.resolve(strict=True)
    if destination_root.is_symlink():
        raise UnsafeZipError(f"extraction root must not be a symlink: {destination_root}")
    destination_root = destination_root.resolve(strict=False)
    if destination_root.exists():
        if not destination_root.is_dir():
            raise UnsafeZipError(f"extraction root is not a directory: {destination_root}")
        if any(destination_root.iterdir()):
            raise UnsafeZipError(f"extraction root must be empty: {destination_root}")

    with zipfile.ZipFile(zip_path) as archive:
        planned = _preflight(archive)
        destination_root.mkdir(parents=True, exist_ok=True)
        for info, parts, is_directory in planned:
            destination = destination_root.joinpath(*parts)
            if is_directory:
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("xb") as target:
                shutil.copyfileobj(source, target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("destination_root", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        safe_extract(args.zip_path, args.destination_root)
    except (OSError, zipfile.BadZipFile, UnsafeZipError) as error:
        raise SystemExit(f"Safe ZIP extraction failed: {error}") from error


if __name__ == "__main__":
    main()
