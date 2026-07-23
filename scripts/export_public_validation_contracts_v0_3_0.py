#!/usr/bin/env python3
"""Export compact, independently verifiable evidence for public matrix runs."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validation_fingerprints_v0_3_0 import (
    FINGERPRINT_FIELDS,
    PUBLIC_VALIDATION_CASE_IDS,
    compact_summary_contract_fingerprints,
    write_compact_summary_contract,
)


def validate_source_cases(matrix_root: Path) -> Path:
    outputs = matrix_root / "outputs"
    if outputs.is_symlink() or not outputs.is_dir():
        raise ValueError(f"Public matrix outputs directory is missing or unsafe: {outputs}")
    entries = list(outputs.iterdir())
    if any(
        entry.is_symlink() or (not entry.is_dir() and not entry.is_file())
        for entry in entries
    ):
        raise ValueError("Public matrix outputs contain a symlink or special entry")
    observed = {entry.name for entry in entries if entry.is_dir()}
    expected = set(PUBLIC_VALIDATION_CASE_IDS)
    if observed != expected:
        raise ValueError(
            "Public matrix case inventory mismatch: "
            f"missing={sorted(expected - observed)}; "
            f"unexpected={sorted(observed - expected)}"
        )
    return outputs


def export_contracts(matrix_root: Path, output_root: Path) -> None:
    outputs = validate_source_cases(matrix_root)
    if output_root.is_symlink() or output_root.exists():
        raise ValueError(f"Contract output must be absent and non-symlink: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.partial-",
            dir=output_root.parent,
        )
    )
    try:
        for case_id in PUBLIC_VALIDATION_CASE_IDS:
            source_summary = outputs / case_id / "summary"
            fingerprints = write_compact_summary_contract(
                source_summary,
                staging / case_id,
            )
            verified = compact_summary_contract_fingerprints(staging / case_id)
            if verified != fingerprints:
                raise ValueError(f"Compact contract changed after writing: {case_id}")
            values = " ".join(
                f"{field}={verified[field]}" for field in FINGERPRINT_FIELDS
            )
            print(f"[contract] {case_id} {values}", flush=True)
        os.replace(staging, output_root)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export exact candidate tables and ordered summary-schema manifests "
            "for all eight v0.3.0 public validation cases."
        )
    )
    parser.add_argument("--matrix-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    export_contracts(args.matrix_root.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
