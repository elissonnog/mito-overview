#!/usr/bin/env python3
"""Replace machine-local paths in text evidence before hashing or publication."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_replacement(value: str) -> tuple[Path, str]:
    absolute, separator, marker = value.partition("=")
    if not separator or not absolute or not marker:
        raise argparse.ArgumentTypeError("replacement must use ABSOLUTE_PATH=MARKER")
    path = Path(absolute)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("replacement source must be an absolute path")
    return path, marker


def text_payload(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def sanitize_tree(root: Path, replacements: list[tuple[Path, str]]) -> int:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"evidence root is not a regular directory: {root}")
    ordered = sorted(
        (
            (str(path.resolve(strict=False)), marker)
            for path, marker in replacements
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    changed = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"evidence tree contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"evidence tree contains a special file: {path}")
        text = text_payload(path)
        if text is None:
            continue
        sanitized = text
        for absolute, marker in ordered:
            sanitized = sanitized.replace(absolute, marker)
        sanitized = re.sub(r"/Users/[^/\s]+", "${HOME}", sanitized)
        sanitized = re.sub(r"/home/[^/\s]+", "${HOME}", sanitized)
        sanitized = sanitized.replace("/private/tmp", "${TMPDIR}")
        sanitized = re.sub(
            r"(?i)[A-Z]:\\Users\\[^\\\s]+",
            "${HOME}",
            sanitized,
        )
        if sanitized != text:
            path.write_text(sanitized, encoding="utf-8")
            changed += 1
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        type=parse_replacement,
        metavar="ABSOLUTE_PATH=MARKER",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    changed = sanitize_tree(args.root, args.replace)
    print(f"sanitized_text_files={changed}")


if __name__ == "__main__":
    main()
