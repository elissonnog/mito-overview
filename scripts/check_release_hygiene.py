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
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


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
