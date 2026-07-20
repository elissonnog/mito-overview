from __future__ import annotations

import importlib.util
import struct
import zlib
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "inventory_visual_artifacts.py"
SPEC = importlib.util.spec_from_file_location("inventory_visual_artifacts", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def write_one_pixel_png(path: Path) -> None:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    scanline = b"\x00\x00\x00\x00"
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(scanline))
        + png_chunk(b"IEND", b"")
    )


def test_png_crc_and_dimensions_are_validated(tmp_path: Path) -> None:
    path = tmp_path / "figure.png"
    write_one_pixel_png(path)
    assert inventory.png_dimensions(path) == (1, 1)

    corrupted = bytearray(path.read_bytes())
    corrupted[-5] ^= 1
    path.write_bytes(corrupted)
    with pytest.raises(ValueError, match="CRC mismatch"):
        inventory.png_dimensions(path)


def test_html_report_structure_is_required(tmp_path: Path) -> None:
    valid = tmp_path / "report.html"
    valid.write_text("<!doctype html><html><body>ok</body></html>", encoding="utf-8")
    row = inventory.inspect_artifact(tmp_path, valid)
    assert row["artifact_type"] == "html"
    assert row["integrity_status"] == "ok"

    invalid = tmp_path / "broken.html"
    invalid.write_text("<html>missing body and closing tag", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed HTML"):
        inventory.inspect_artifact(tmp_path, invalid)
