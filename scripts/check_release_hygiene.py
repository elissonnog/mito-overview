#!/usr/bin/env python3
"""Fail when the tracked release tree contains private or process-only material."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[bytes]
    path_prefixes: tuple[str, ...] = ()

    def applies_to(self, relative_path: str) -> bool:
        return not self.path_prefixes or relative_path.startswith(self.path_prefixes)


RULES = (
    Rule("internal_sample_id", re.compile(rb"R20[0-9]{2}-[0-9]+")),
    Rule(
        "mcw_group_path",
        re.compile(rb"/(?:group|scratch)/(?:[^\x00\r\n]*/)?xgai(?:/|\x00)", re.I),
    ),
    Rule(
        "developer_home_path",
        re.compile(b"/Users/" + rb"elopes(?:/|\x00)", re.I),
    ),
    Rule(
        "manuscript_process_wording",
        re.compile(rb"\b(?:Codex|ChatGPT|large language model|LLM)\b", re.I),
        ("paper/",),
    ),
)


def tracked_paths(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
    )
    if result.returncode != 0:
        source_manifests = sorted(repo_root.glob("*.egg-info/SOURCES.txt"))
        if len(source_manifests) == 1:
            return sorted(
                relative_path
                for relative_path in source_manifests[0].read_text(encoding="utf-8").splitlines()
                if relative_path and (repo_root / relative_path).is_file()
            )
        return sorted(
            path.relative_to(repo_root).as_posix()
            for path in repo_root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and "__pycache__" not in path.parts
            and ".pytest_cache" not in path.parts
        )
    deleted = subprocess.run(
        ["git", "ls-files", "-z", "--deleted"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    deleted_paths = {item for item in deleted.stdout.split(b"\0") if item}
    return [
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item and item not in deleted_paths
    ]


def find_violations(repo_root: Path) -> list[str]:
    violations: list[str] = []
    for relative_path in tracked_paths(repo_root):
        payload = (repo_root / relative_path).read_bytes()
        for rule in RULES:
            if rule.applies_to(relative_path) and rule.pattern.search(payload):
                violations.append(f"{relative_path}: {rule.name}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    args = parser.parse_args()
    repo_root = args.repo.expanduser().resolve()
    paths = tracked_paths(repo_root)
    violations = find_violations(repo_root)
    if violations:
        print("Release hygiene failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print(f"Release hygiene passed for {len(paths)} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
