#!/usr/bin/env python3
"""Fail when the tracked release tree contains private or process-only material."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


MatchPredicate = Callable[[re.Match[bytes]], bool]


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[bytes]
    path_prefixes: tuple[str, ...] = ()
    predicate: MatchPredicate | None = None

    def applies_to(self, relative_path: str) -> bool:
        return not self.path_prefixes or relative_path.startswith(self.path_prefixes)

    def finds_violation(self, payload: bytes) -> bool:
        return any(
            self.predicate is None or self.predicate(match)
            for match in self.pattern.finditer(payload)
        )


_PLACEHOLDER_USERS = {
    b"alice",
    b"bob",
    b"demo",
    b"example",
    b"name",
    b"runner",
    b"runneradmin",
    b"user",
    b"username",
}

_PLACEHOLDER_VALUES = {
    b"change-me",
    b"changeme",
    b"disabled",
    b"dummy",
    b"example",
    b"fake",
    b"masked",
    b"none",
    b"not-configured",
    b"not-set",
    b"null",
    b"pass",
    b"password",
    b"placeholder",
    b"redacted",
    b"replace-me",
    b"secret",
    b"test",
    b"token",
    b"unset",
    b"ghp_abcdefghijklmnopqrstuvwxyz",
}

_PLACEHOLDER_COMPONENTS = {
    b"changeme",
    b"dummy",
    b"example",
    b"fake",
    b"masked",
    b"placeholder",
    b"redacted",
    b"replace",
    b"test",
    b"your",
}

_NON_SECRET_KEY_SUFFIXES = (
    b"_column",
    b"_env",
    b"_field",
    b"_header",
    b"_label",
    b"_name",
    b"_pattern",
    b"_placeholder",
    b"_regex",
    b"_variable",
)

_NON_SECRET_KEYS = {
    b"control_token",
    b"isolated_token",
}


def _strip_literal_quotes(value: bytes) -> bytes:
    value = value.strip()
    if len(value) >= 2 and value[:1] == value[-1:] and value[:1] in {b"'", b'"'}:
        return value[1:-1].strip()
    return value


def _is_placeholder(value: bytes) -> bool:
    value = _strip_literal_quotes(value)
    lowered = value.lower()
    if not lowered or lowered in _PLACEHOLDER_VALUES:
        return True
    if lowered.startswith((b"$", b"<", b"{{")) or lowered.endswith(b"}}"):
        return True
    if set(lowered) <= {ord("*"), ord("x"), ord("-")}:
        return True
    components = set(filter(None, re.split(rb"[^a-z0-9]+", lowered)))
    return bool(components & _PLACEHOLDER_COMPONENTS)


def _home_path_is_private(match: re.Match[bytes]) -> bool:
    if match.group("root_home") is not None:
        return True
    username = match.group("posix_user") or match.group("windows_user") or b""
    return username.lower() not in _PLACEHOLDER_USERS


def _credential_url_is_private(match: re.Match[bytes]) -> bool:
    return not _is_placeholder(match.group("url_password"))


def _secret_assignment_is_private(match: re.Match[bytes]) -> bool:
    key = match.group("secret_key").strip(b"'\"").lower().replace(b"-", b"_")
    if key in _NON_SECRET_KEYS or key.endswith(_NON_SECRET_KEY_SUFFIXES):
        return False

    value = _strip_literal_quotes(match.group("secret_value"))
    if _is_placeholder(value):
        return False
    if len(value) < 6 or any(character in value for character in b"\r\n\t "):
        return False
    if value.startswith(
        (
            b"env(",
            b"getenv(",
            b"os.environ",
            b"re.compile(",
            b"settings.",
        )
    ):
        return False
    return True


_HOME_PATH_PATTERN = re.compile(
    rb"(?<![A-Za-z0-9_.-])(?:"
    + b"/"
    + rb"(?:Users|home)/(?P<posix_user>[A-Za-z0-9._-]+)(?=$|[/\\\x00])"
    + rb"|(?P<root_home>"
    + b"/"
    + rb"root(?=$|[/\\\x00]))"
    + rb"|[A-Za-z]:[\\/]+Users[\\/]+(?P<windows_user>[A-Za-z0-9._-]+)"
    + rb"(?=$|[/\\\x00]))",
    re.I,
)

_PRIVATE_KEY_PATTERN = re.compile(
    b"-" * 5
    + rb"BEGIN[ \t]+(?:RSA[ \t]+|DSA[ \t]+|EC[ \t]+|OPENSSH[ \t]+|"
    + rb"ENCRYPTED[ \t]+|PGP[ \t]+)?PRIVATE[ \t]+KEY(?:[ \t]+BLOCK)?"
    + b"-" * 5,
    re.I,
)

_GITHUB_TOKEN_PATTERN = re.compile(
    rb"\b(?:"
    + b"gh"
    + rb"[pousr]_[A-Za-z0-9]{30,255}|"
    + b"github"
    + rb"_pat_[A-Za-z0-9_]{30,255})\b"
)

_AWS_ACCESS_KEY_PATTERN = re.compile(
    rb"\b(?:" + b"AK" + rb"IA|" + b"AS" + rb"IA)[0-9A-Z]{16}\b"
)

_CREDENTIAL_URL_PATTERN = re.compile(
    rb"\b(?:https?|ftp)://(?P<url_user>[^\s:/@'\"<>]+):"
    rb"(?P<url_password>[^\s/@'\"<>]+)@[^\s/'\"<>]+",
    re.I,
)

_SECRET_ASSIGNMENT_PATTERN = re.compile(
    rb"(?im)(?:^|(?<=[\s,{;(]))"
    rb"(?P<secret_key>['\"]?[A-Za-z_][A-Za-z0-9_.-]*"
    rb"(?:api[_-]?key|access[_-]?key|client[_-]?secret|password|passwd|pwd|secret|token)"
    rb"[A-Za-z0-9_.-]*['\"]?)"
    rb"[ \t]*(?:=|:)[ \t]*"
    rb"(?P<secret_value>['\"][^'\"\r\n]*['\"]|[^\s,;#}\]'\"\\\r\n]+)",
)


RULES = (
    Rule("internal_sample_id", re.compile(rb"R20[0-9]{2}-[0-9]+")),
    Rule(
        "mcw_group_path",
        re.compile(rb"/(?:group|scratch)/(?:[^\x00\r\n]*/)?xgai(?:/|\x00)", re.I),
    ),
    Rule(
        "absolute_user_home_path",
        _HOME_PATH_PATTERN,
        predicate=_home_path_is_private,
    ),
    Rule("private_key_header", _PRIVATE_KEY_PATTERN),
    Rule("github_token", _GITHUB_TOKEN_PATTERN),
    Rule("aws_access_key", _AWS_ACCESS_KEY_PATTERN),
    Rule(
        "credential_bearing_url",
        _CREDENTIAL_URL_PATTERN,
        predicate=_credential_url_is_private,
    ),
    Rule(
        "secret_literal_assignment",
        _SECRET_ASSIGNMENT_PATTERN,
        predicate=_secret_assignment_is_private,
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
            if rule.applies_to(relative_path) and rule.finds_violation(payload):
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
