#!/usr/bin/env python3
"""Safely extract a validation ZIP after a complete destination preflight."""

from __future__ import annotations

import argparse
import math
import stat
import zipfile
from pathlib import Path, PurePosixPath


# The audit packet excludes raw reads but can contain normalized tables above 90 MiB.
DEFAULT_MAX_MEMBERS = 10_000
DEFAULT_MAX_FILE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 100.0
COPY_CHUNK_BYTES = 1024 * 1024


class UnsafeZipError(ValueError):
    """Raised when an archive cannot be extracted without path ambiguity."""


class ExtractionLimits:
    """Resource limits enforced from ZIP metadata before extraction."""

    __slots__ = (
        "max_members",
        "max_file_uncompressed_bytes",
        "max_total_uncompressed_bytes",
        "max_compression_ratio",
    )

    def __init__(
        self,
        max_members: int = DEFAULT_MAX_MEMBERS,
        max_file_uncompressed_bytes: int = DEFAULT_MAX_FILE_UNCOMPRESSED_BYTES,
        max_total_uncompressed_bytes: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
        max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    ) -> None:
        integer_limits = {
            "max_members": max_members,
            "max_file_uncompressed_bytes": max_file_uncompressed_bytes,
            "max_total_uncompressed_bytes": max_total_uncompressed_bytes,
        }
        for name, value in integer_limits.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(max_compression_ratio, bool)
            or not isinstance(max_compression_ratio, (int, float))
            or not math.isfinite(max_compression_ratio)
            or max_compression_ratio <= 0
        ):
            raise ValueError("max_compression_ratio must be a finite positive number")
        self.max_members = max_members
        self.max_file_uncompressed_bytes = max_file_uncompressed_bytes
        self.max_total_uncompressed_bytes = max_total_uncompressed_bytes
        self.max_compression_ratio = float(max_compression_ratio)


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


def _preflight(
    archive: zipfile.ZipFile,
    limits: ExtractionLimits | None = None,
) -> list[tuple[zipfile.ZipInfo, tuple[str, ...], bool]]:
    limits = limits or ExtractionLimits()
    infos = archive.infolist()
    if not infos:
        raise UnsafeZipError("validation ZIP is empty")
    if len(infos) > limits.max_members:
        raise UnsafeZipError(
            f"ZIP member count {len(infos)} exceeds limit {limits.max_members}"
        )

    planned: list[tuple[zipfile.ZipInfo, tuple[str, ...], bool]] = []
    destinations: dict[str, str] = {}
    files: set[str] = set()
    total_uncompressed_bytes = 0
    for info in infos:
        canonical, parts, is_directory = _canonical_member(info)
        if not is_directory and info.file_size > limits.max_file_uncompressed_bytes:
            raise UnsafeZipError(
                f"ZIP member {info.filename!r} uncompressed size {info.file_size} "
                f"exceeds per-file limit {limits.max_file_uncompressed_bytes}"
            )
        total_uncompressed_bytes += info.file_size
        if total_uncompressed_bytes > limits.max_total_uncompressed_bytes:
            raise UnsafeZipError(
                f"ZIP total uncompressed size {total_uncompressed_bytes} exceeds limit "
                f"{limits.max_total_uncompressed_bytes}"
            )
        if info.file_size:
            if info.compress_size <= 0:
                raise UnsafeZipError(
                    f"ZIP member {info.filename!r} has a nonzero uncompressed size "
                    "but no compressed data"
                )
            compression_ratio = info.file_size / info.compress_size
            if compression_ratio > limits.max_compression_ratio:
                raise UnsafeZipError(
                    f"ZIP member {info.filename!r} compression ratio "
                    f"{compression_ratio:.2f}:1 exceeds limit "
                    f"{limits.max_compression_ratio:g}:1"
                )
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


def _copy_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    destination: Path,
    limits: ExtractionLimits,
) -> None:
    """Copy one preflighted member and verify its observed byte count."""

    written = 0
    with archive.open(info) as source, destination.open("xb") as target:
        while chunk := source.read(COPY_CHUNK_BYTES):
            written += len(chunk)
            if written > limits.max_file_uncompressed_bytes:
                raise UnsafeZipError(
                    f"ZIP member {info.filename!r} exceeded the per-file limit while reading"
                )
            if written > info.file_size:
                raise UnsafeZipError(
                    f"ZIP member {info.filename!r} exceeded its declared uncompressed size"
                )
            target.write(chunk)
    if written != info.file_size:
        raise UnsafeZipError(
            f"ZIP member {info.filename!r} produced {written} bytes; "
            f"expected {info.file_size}"
        )


def safe_extract(
    zip_path: Path,
    destination_root: Path,
    *,
    limits: ExtractionLimits | None = None,
) -> None:
    """Extract regular files only, rejecting aliases before creating output."""

    limits = limits or ExtractionLimits()
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
        planned = _preflight(archive, limits)
        destination_root.mkdir(parents=True, exist_ok=True)
        for info, parts, is_directory in planned:
            destination = destination_root.joinpath(*parts)
            if is_directory:
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            _copy_member(archive, info, destination, limits)


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("destination_root", type=Path)
    parser.add_argument(
        "--max-members",
        type=_positive_integer,
        default=DEFAULT_MAX_MEMBERS,
        help=f"maximum archive members (default: {DEFAULT_MAX_MEMBERS})",
    )
    parser.add_argument(
        "--max-file-bytes",
        type=_positive_integer,
        default=DEFAULT_MAX_FILE_UNCOMPRESSED_BYTES,
        help=(
            "maximum uncompressed bytes per regular file "
            f"(default: {DEFAULT_MAX_FILE_UNCOMPRESSED_BYTES})"
        ),
    )
    parser.add_argument(
        "--max-total-bytes",
        type=_positive_integer,
        default=DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
        help=(
            "maximum total uncompressed bytes "
            f"(default: {DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES})"
        ),
    )
    parser.add_argument(
        "--max-compression-ratio",
        type=_positive_float,
        default=DEFAULT_MAX_COMPRESSION_RATIO,
        help=(
            "maximum uncompressed-to-compressed ratio per nonempty member "
            f"(default: {DEFAULT_MAX_COMPRESSION_RATIO:g})"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        limits = ExtractionLimits(
            max_members=args.max_members,
            max_file_uncompressed_bytes=args.max_file_bytes,
            max_total_uncompressed_bytes=args.max_total_bytes,
            max_compression_ratio=args.max_compression_ratio,
        )
        safe_extract(args.zip_path, args.destination_root, limits=limits)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise SystemExit(f"Safe ZIP extraction failed: {error}") from error


if __name__ == "__main__":
    main()
