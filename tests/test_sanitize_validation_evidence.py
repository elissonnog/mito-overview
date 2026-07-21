from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "sanitize_validation_evidence.py"
SPEC = importlib.util.spec_from_file_location("sanitize_validation_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
sanitizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sanitizer)


def test_sanitize_tree_replaces_known_and_generic_local_paths(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    text = evidence / "command.txt"
    text.write_text(
        "/opt/actions/work/repo /home/runner/.cache /private/tmp/job ",
        encoding="utf-8",
    )
    binary = evidence / "figure.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\xff")

    changed = sanitizer.sanitize_tree(
        evidence,
        [(Path("/opt/actions/work/repo"), "${REPOSITORY_CHECKOUT}")],
    )

    assert changed == 1
    assert text.read_text(encoding="utf-8") == (
        "${REPOSITORY_CHECKOUT} ${HOME}/.cache ${TMPDIR}/job "
    )
    assert binary.read_bytes() == b"\x89PNG\r\n\x1a\n\xff"


def test_sanitize_tree_rejects_symlinks(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("evidence", encoding="utf-8")
    (evidence / "link.txt").symlink_to(target)

    with pytest.raises(ValueError, match="symlink"):
        sanitizer.sanitize_tree(evidence, [])
