#!/usr/bin/env python3
"""Normalize public-validation TSVs for deterministic repeat comparison."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path, help="Directory containing TSV outputs")
    parser.add_argument("output_dir", type=Path, help="Destination for normalized TSVs")
    return parser.parse_args()


def normalize_table(source: Path, destination: Path) -> None:
    """Write a path-independent, stably sorted representation of one TSV."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame = pd.read_csv(source, sep="\t", dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        destination.write_text("", encoding="utf-8")
        return
    if not frame.empty:
        frame = frame.sort_values(
            list(frame.columns),
            kind="mergesort",
            na_position="last",
        ).reset_index(drop=True)
    frame.to_csv(destination, sep="\t", index=False, lineterminator="\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    if not args.input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {args.input_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str]] = []
    for source in sorted(args.input_dir.rglob("*.tsv")):
        relative = source.relative_to(args.input_dir)
        destination = args.output_dir / relative
        normalize_table(source, destination)
        rows.append((relative.as_posix(), sha256(destination)))
    if not rows:
        raise SystemExit(f"No TSV files found under {args.input_dir}")
    manifest = args.output_dir / "normalized_manifest.tsv"
    manifest.write_text(
        "path\tsha256\n" + "".join(f"{path}\t{digest}\n" for path, digest in rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
