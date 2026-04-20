#!/usr/bin/env python3
"""Tiny deterministic Phy-Mer stand-in for public validation."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: Phy-Mer.py <library> <fasta>", file=sys.stderr)
        return 1
    fasta_path = Path(sys.argv[-1])
    sample_label = fasta_path.stem
    defining = "m.10A>C"
    print(sample_label)
    print(f"H1a1\t0.982\t{defining}")
    print("R0\t0.251\tNA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
