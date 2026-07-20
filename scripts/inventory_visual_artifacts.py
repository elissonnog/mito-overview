#!/usr/bin/env python3
"""Inventory and validate report HTML and PNG artifacts without bytewise comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
import struct
import zlib
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("inventory_tsv", type=Path)
    parser.add_argument("structure_tsv", type=Path)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    """Validate PNG chunk CRCs and return width and height from IHDR."""

    width = height = 0
    found_iend = False
    with path.open("rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Invalid PNG signature: {path}")
        while True:
            raw_length = handle.read(4)
            if not raw_length:
                break
            if len(raw_length) != 4:
                raise ValueError(f"Truncated PNG chunk length: {path}")
            length = struct.unpack(">I", raw_length)[0]
            chunk_type = handle.read(4)
            chunk_data = handle.read(length)
            raw_crc = handle.read(4)
            if len(chunk_type) != 4 or len(chunk_data) != length or len(raw_crc) != 4:
                raise ValueError(f"Truncated PNG chunk: {path}")
            observed_crc = struct.unpack(">I", raw_crc)[0]
            expected_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
            if observed_crc != expected_crc:
                raise ValueError(f"PNG chunk CRC mismatch: {path}")
            if chunk_type == b"IHDR":
                if length != 13:
                    raise ValueError(f"Invalid PNG IHDR length: {path}")
                width, height = struct.unpack(">II", chunk_data[:8])
            elif chunk_type == b"IEND":
                found_iend = True
                if handle.read(1):
                    raise ValueError(f"Unexpected bytes after PNG IEND: {path}")
                break
    if width <= 0 or height <= 0 or not found_iend:
        raise ValueError(f"Incomplete PNG structure: {path}")
    return width, height


def inspect_artifact(root: Path, path: Path) -> dict[str, str | int]:
    relative = path.relative_to(root).as_posix()
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"Empty visual artifact: {path}")
    if path.suffix.lower() == ".html":
        text = path.read_text(encoding="utf-8")
        normalized = text.lower()
        if "<html" not in normalized or "<body" not in normalized or "</html>" not in normalized:
            raise ValueError(f"Malformed HTML report: {path}")
        artifact_type = "html"
        width = ""
        height = ""
    elif path.suffix.lower() == ".png":
        width, height = png_dimensions(path)
        artifact_type = "png"
    else:
        raise ValueError(f"Unsupported visual artifact: {path}")
    return {
        "relative_path": relative,
        "artifact_type": artifact_type,
        "bytes": size,
        "sha256": sha256(path),
        "width_px": width,
        "height_px": height,
        "integrity_status": "ok",
    }


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if not args.output_dir.is_dir():
        raise SystemExit(f"Output directory not found: {args.output_dir}")
    paths = sorted((args.output_dir / "report").glob("*.html"))
    paths.extend(sorted((args.output_dir / "figures").glob("*.png")))
    if not paths:
        raise SystemExit(f"No HTML or PNG artifacts found under {args.output_dir}")
    rows = [inspect_artifact(args.output_dir, path) for path in paths]
    inventory_fields = [
        "relative_path",
        "artifact_type",
        "bytes",
        "sha256",
        "width_px",
        "height_px",
        "integrity_status",
    ]
    structure_fields = [
        "relative_path",
        "artifact_type",
        "width_px",
        "height_px",
        "integrity_status",
    ]
    write_tsv(args.inventory_tsv, inventory_fields, rows)
    write_tsv(args.structure_tsv, structure_fields, rows)


if __name__ == "__main__":
    main()
