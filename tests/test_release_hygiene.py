from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "check_release_hygiene.py"
SPEC = importlib.util.spec_from_file_location("check_release_hygiene", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
hygiene = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hygiene
SPEC.loader.exec_module(hygiene)


def make_repo(tmp_path: Path, relative_path: str, payload: bytes) -> Path:
    repo = tmp_path / "repo"
    target = repo / relative_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", relative_path], cwd=repo, check=True)
    return repo


def test_current_tracked_tree_passes_release_hygiene() -> None:
    assert hygiene.find_violations(Path(__file__).parents[1]) == []


@pytest.mark.parametrize(
    ("relative_path", "payload", "rule"),
    [
        ("examples/report.html", b"sample R20" + b"26-124", "internal_sample_id"),
        ("run.txt", b"/group/" + b"xgai/work/bioinfo", "mcw_group_path"),
        (
            "binary.bam",
            b"prefix\x00/Users/" + b"elopes/private\x00",
            "developer_home_path",
        ),
        ("paper/draft.md", b"Edited with Chat" + b"GPT", "manuscript_process_wording"),
    ],
)
def test_release_hygiene_rejects_tracked_private_material(
    tmp_path: Path, relative_path: str, payload: bytes, rule: str
) -> None:
    repo = make_repo(tmp_path, relative_path, payload)
    assert hygiene.find_violations(repo) == [f"{relative_path}: {rule}"]


def test_ignored_private_output_is_not_scanned(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, ".gitignore", b"private/\n")
    private = repo / "private" / ("R20" + "26-124.html")
    private.parent.mkdir()
    private.write_text("/group/" + "xgai/work", encoding="utf-8")
    assert hygiene.find_violations(repo) == []
