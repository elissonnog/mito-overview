#!/usr/bin/env python3
"""Write a portable SHA-256 manifest for a validation input cache."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if not root.is_dir():
        raise SystemExit(f"Validation cache root not found: {root}")
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.resolve() != output
    )
    if not files:
        raise SystemExit(f"No validation inputs found under {root}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(root).as_posix()}\n" for path in files),
        encoding="utf-8",
    )
    print(f"[input-hashes] wrote {len(files)} entries to {output}")


if __name__ == "__main__":
    main()
