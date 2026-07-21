from __future__ import annotations

import importlib.util
import stat
import zipfile
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "safe_extract_validation_zip.py"
SPEC = importlib.util.spec_from_file_location("safe_extract_validation_zip_limits", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
safe_zip = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(safe_zip)


def write_zip(
    path: Path,
    members: list[tuple[str, bytes]],
    *,
    compression: int = zipfile.ZIP_STORED,
) -> None:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, content in members:
            archive.writestr(name, content)


def test_default_limits_are_auditable_and_cover_planned_packet_scale() -> None:
    limits = safe_zip.ExtractionLimits()
    assert (
        limits.max_members,
        limits.max_file_uncompressed_bytes,
        limits.max_total_uncompressed_bytes,
        limits.max_compression_ratio,
    ) == (
        10_000,
        512 * 1024 * 1024,
        2 * 1024 * 1024 * 1024,
        100.0,
    )


def test_defaults_extract_planned_v030_packet_shape(tmp_path: Path) -> None:
    archive_path = tmp_path / "mito-overview-v0.3.0-validation.zip"
    members = [
        ("run.json", b'{"release_version":"v0.3.0"}\n'),
        ("cases.tsv", b"case_id\tverdict\nunit_known_answer\tPASS\n"),
        ("claim_evidence_matrix.tsv", b"claim_id\tevidence\nC1\tunit_known_answer\n"),
        ("commands/unit.sh", b"#!/usr/bin/env bash\nexit 0\n"),
        ("logs/unit.log", b"207 passed\n"),
        ("expected/TOY-WGS-001.tsv", b"ratio\n10.0\n"),
        ("observed_normalized/TOY-WGS-001.tsv", b"ratio\n10.0\n"),
        ("artifacts.sha256", b"placeholder  run.json\n"),
        ("verify_bundle.sh", b"#!/usr/bin/env bash\nexit 0\n"),
    ]
    write_zip(archive_path, members, compression=zipfile.ZIP_DEFLATED)

    destination = tmp_path / "packet"
    safe_zip.safe_extract(archive_path, destination)

    assert (destination / "run.json").read_bytes() == members[0][1]
    assert (destination / "observed_normalized" / "TOY-WGS-001.tsv").read_bytes() == (
        b"ratio\n10.0\n"
    )


@pytest.mark.parametrize(
    ("limits", "members", "message"),
    [
        (
            safe_zip.ExtractionLimits(max_members=2),
            [("one", b"1"), ("two", b"2"), ("three", b"3")],
            "ZIP member count 3 exceeds limit 2",
        ),
        (
            safe_zip.ExtractionLimits(max_file_uncompressed_bytes=4),
            [("large.tsv", b"12345")],
            "uncompressed size 5 exceeds per-file limit 4",
        ),
        (
            safe_zip.ExtractionLimits(max_total_uncompressed_bytes=5),
            [("one.tsv", b"123"), ("two.tsv", b"456")],
            "ZIP total uncompressed size 6 exceeds limit 5",
        ),
    ],
)
def test_metadata_limits_reject_before_creating_destination(
    tmp_path: Path,
    limits: object,
    members: list[tuple[str, bytes]],
    message: str,
) -> None:
    archive_path = tmp_path / "limited.zip"
    write_zip(archive_path, members)
    destination = tmp_path / "packet"

    with pytest.raises(safe_zip.UnsafeZipError, match=message):
        safe_zip.safe_extract(archive_path, destination, limits=limits)

    assert not destination.exists()


def test_compression_ratio_rejects_before_creating_destination(tmp_path: Path) -> None:
    archive_path = tmp_path / "compressed.zip"
    write_zip(
        archive_path,
        [("highly_repetitive.tsv", b"A" * 4096)],
        compression=zipfile.ZIP_DEFLATED,
    )
    destination = tmp_path / "packet"
    limits = safe_zip.ExtractionLimits(max_compression_ratio=2.0)

    with pytest.raises(safe_zip.UnsafeZipError, match=r"compression ratio .* exceeds limit 2:1"):
        safe_zip.safe_extract(archive_path, destination, limits=limits)

    assert not destination.exists()


def test_exact_resource_boundaries_are_accepted(tmp_path: Path) -> None:
    archive_path = tmp_path / "boundary.zip"
    write_zip(archive_path, [("one", b"12"), ("two", b"345")])
    limits = safe_zip.ExtractionLimits(
        max_members=2,
        max_file_uncompressed_bytes=3,
        max_total_uncompressed_bytes=5,
        max_compression_ratio=1.0,
    )

    destination = tmp_path / "packet"
    safe_zip.safe_extract(archive_path, destination, limits=limits)

    assert (destination / "one").read_bytes() == b"12"
    assert (destination / "two").read_bytes() == b"345"


@pytest.mark.parametrize("member_name", ["../escape", "/absolute", "dir\\file"])
def test_existing_path_safeguards_remain_enforced(
    tmp_path: Path,
    member_name: str,
) -> None:
    archive_path = tmp_path / "unsafe-path.zip"
    write_zip(archive_path, [(member_name, b"unsafe")])
    destination = tmp_path / "packet"

    with pytest.raises(safe_zip.UnsafeZipError, match="unsafe ZIP member path"):
        safe_zip.safe_extract(archive_path, destination)

    assert not destination.exists()


def test_existing_encryption_safeguard_remains_enforced() -> None:
    info = zipfile.ZipInfo("encrypted.txt")
    info.flag_bits |= 0x1

    with pytest.raises(safe_zip.UnsafeZipError, match="encrypted ZIP members"):
        safe_zip._canonical_member(info)


def test_existing_symlink_safeguard_remains_enforced(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "target")
    destination = tmp_path / "packet"

    with pytest.raises(safe_zip.UnsafeZipError, match="non-regular ZIP member"):
        safe_zip.safe_extract(archive_path, destination)

    assert not destination.exists()


def test_existing_collision_safeguard_remains_enforced(tmp_path: Path) -> None:
    archive_path = tmp_path / "collision.zip"
    write_zip(archive_path, [("evidence/run.json", b"1"), ("evidence//run.json", b"2")])
    destination = tmp_path / "packet"

    with pytest.raises(safe_zip.UnsafeZipError, match="canonical destination collision"):
        safe_zip.safe_extract(archive_path, destination)

    assert not destination.exists()
