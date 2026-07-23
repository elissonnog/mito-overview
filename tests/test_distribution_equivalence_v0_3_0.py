from __future__ import annotations

import gzip
import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "verify_distribution_equivalence_v0.3.0.py"
SPEC = importlib.util.spec_from_file_location("distribution_equivalence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


WHEEL_MEMBERS = {
    "mito_overview/__init__.py": b'__version__ = "0.3.0"\n',
    "mito_overview-0.3.0.dist-info/METADATA": (
        b"Name: mito-overview\nVersion: 0.3.0\n"
    ),
    "mito_overview-0.3.0.dist-info/WHEEL": (
        b"Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    ),
    "mito_overview-0.3.0.dist-info/RECORD": b"fixture-record\n",
}
SDIST_MEMBERS = {
    "mito_overview-0.3.0/PKG-INFO": b"Name: mito-overview\nVersion: 0.3.0\n",
    "mito_overview-0.3.0/mito_overview.egg-info/PKG-INFO": (
        b"Name: mito-overview\nVersion: 0.3.0\n"
    ),
    "mito_overview-0.3.0/mito_overview/__init__.py": (
        b'__version__ = "0.3.0"\n'
    ),
}


def _write_wheel(
    root: Path,
    *,
    year: int,
    mutation: bytes | None = None,
    executable: bool = False,
    omit_wheel_metadata: bool = False,
    extra_members: dict[str, bytes] | None = None,
) -> None:
    members = dict(WHEEL_MEMBERS)
    if mutation is not None:
        members["mito_overview/__init__.py"] = mutation
    if omit_wheel_metadata:
        members.pop("mito_overview-0.3.0.dist-info/WHEEL")
    members.update(extra_members or {})
    path = root / "mito_overview-0.3.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(year, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if executable and name == "mito_overview/__init__.py" else 0o644
            info.external_attr = (0o100000 | mode) << 16
            archive.writestr(info, payload)


def _write_sdist(
    root: Path,
    *,
    mtime: int,
    symlink: bool = False,
    omit_root_metadata: bool = False,
) -> None:
    path = root / "mito_overview-0.3.0.tar.gz"
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=mtime) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                members = dict(SDIST_MEMBERS)
                if omit_root_metadata:
                    members.pop("mito_overview-0.3.0/PKG-INFO")
                for name, payload in sorted(members.items()):
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    info.mtime = mtime
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(payload))
                if symlink:
                    info = tarfile.TarInfo("mito_overview-0.3.0/link")
                    info.type = tarfile.SYMTYPE
                    info.linkname = "PKG-INFO"
                    archive.addfile(info)


def _write_pair(
    root: Path,
    *,
    year: int,
    mtime: int,
    wheel_mutation: bytes | None = None,
    sdist_symlink: bool = False,
    wheel_executable: bool = False,
    omit_wheel_metadata: bool = False,
    wheel_extra_members: dict[str, bytes] | None = None,
    omit_sdist_root_metadata: bool = False,
) -> None:
    root.mkdir()
    _write_wheel(
        root,
        year=year,
        mutation=wheel_mutation,
        executable=wheel_executable,
        omit_wheel_metadata=omit_wheel_metadata,
        extra_members=wheel_extra_members,
    )
    _write_sdist(
        root,
        mtime=mtime,
        symlink=sdist_symlink,
        omit_root_metadata=omit_sdist_root_metadata,
    )


def test_archive_metadata_can_differ_when_member_payloads_match(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(rebuilt, year=2026, mtime=2)

    result = MODULE.verify(canonical, rebuilt)

    assert result["verdict"] == "PASS"
    assert all(row["member_payloads_identical"] for row in result["distributions"])
    assert any(not row["archive_bytes_identical"] for row in result["distributions"])


def test_changed_member_payload_fails(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(
        rebuilt,
        year=2026,
        mtime=2,
        wheel_mutation=b'__version__ = "0.3.1"\n',
    )

    with pytest.raises(MODULE.DistributionError, match="member payloads differ"):
        MODULE.verify(canonical, rebuilt)


def test_extra_distribution_file_fails(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(rebuilt, year=2026, mtime=2)
    (rebuilt / "poison.txt").write_text("poison\n", encoding="ascii")

    with pytest.raises(MODULE.DistributionError, match="inventory differs"):
        MODULE.verify(canonical, rebuilt)


def test_sdist_link_fails(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(rebuilt, year=2026, mtime=2, sdist_symlink=True)

    with pytest.raises(MODULE.DistributionError, match="link or special"):
        MODULE.verify(canonical, rebuilt)


def test_wheel_requires_canonical_metadata_inventory(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(rebuilt, year=2026, mtime=2, omit_wheel_metadata=True)

    with pytest.raises(MODULE.DistributionError, match="METADATA, WHEEL, and RECORD"):
        MODULE.verify(canonical, rebuilt)


def test_case_colliding_wheel_member_fails(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(
        rebuilt,
        year=2026,
        mtime=2,
        wheel_extra_members={
            "mito_overview/Case.py": b"upper\n",
            "mito_overview/case.py": b"lower\n",
        },
    )

    with pytest.raises(MODULE.DistributionError, match="case-colliding"):
        MODULE.verify(canonical, rebuilt)


def test_backslash_wheel_member_fails(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(
        rebuilt,
        year=2026,
        mtime=2,
        wheel_extra_members={"mito_overview\\unsafe.py": b"unsafe\n"},
    )

    with pytest.raises(MODULE.DistributionError, match="unsafe distribution member"):
        MODULE.verify(canonical, rebuilt)


def test_executable_state_difference_fails(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(rebuilt, year=2026, mtime=2, wheel_executable=True)

    with pytest.raises(MODULE.DistributionError, match="member payloads differ"):
        MODULE.verify(canonical, rebuilt)


def test_sdist_member_outside_canonical_root_fails(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(rebuilt, year=2026, mtime=2)
    sdist = rebuilt / "mito_overview-0.3.0.tar.gz"
    members: list[tuple[str, bytes, int]] = []
    with tarfile.open(sdist, "r:gz") as archive:
        for entry in archive.getmembers():
            if entry.isfile():
                handle = archive.extractfile(entry)
                assert handle is not None
                members.append((entry.name, handle.read(), entry.mode))
    with tarfile.open(sdist, "w:gz") as archive:
        for name, payload, mode in members:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = mode
            archive.addfile(info, io.BytesIO(payload))
        payload = b"outside\n"
        info = tarfile.TarInfo("outside.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    with pytest.raises(MODULE.DistributionError, match="outside canonical project root"):
        MODULE.verify(canonical, rebuilt)


def test_sdist_egg_info_cannot_replace_root_metadata(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(
        rebuilt,
        year=2026,
        mtime=2,
        omit_sdist_root_metadata=True,
    )

    with pytest.raises(MODULE.DistributionError, match="canonical root PKG-INFO"):
        MODULE.verify(canonical, rebuilt)


def test_cli_writes_machine_readable_evidence(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    rebuilt = tmp_path / "rebuilt"
    output = tmp_path / "result.json"
    _write_pair(canonical, year=2020, mtime=1)
    _write_pair(rebuilt, year=2026, mtime=2)

    result = MODULE.verify(canonical, rebuilt)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    observed = json.loads(output.read_text(encoding="utf-8"))
    assert observed["verified"] is True
    assert observed["evidence_type"] == "distribution_payload_equivalence"
