#!/usr/bin/env python3
"""Create or verify a deterministic public-validation BAM read-name subset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mito_overview.validation_provenance import (  # noqa: E402
    ProvenanceError,
    create_deterministic_subset,
    verify_deterministic_subset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("--source-alignment", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output-alignment", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--selected-names", required=True, type=Path)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--count", required=True, type=int)
    parser.add_argument("--seed", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    kwargs = {
        "source_alignment": args.source_alignment,
        "source_manifest": args.source_manifest,
        "output_alignment": args.output_alignment,
        "output_manifest": args.output_manifest,
        "selected_names_path": args.selected_names,
        "dataset_id": args.dataset,
        "requested_count": args.count,
        "seed": args.seed,
    }
    try:
        if args.action == "create":
            create_deterministic_subset(**kwargs)
            print(f"[subset] created {args.output_alignment}")
        else:
            verify_deterministic_subset(**kwargs)
            print(f"[subset] verified {args.output_alignment}")
    except (FileNotFoundError, FileExistsError, ProvenanceError, ValueError) as exc:
        raise SystemExit(f"Deterministic BAM subset failed: {exc}") from exc


if __name__ == "__main__":
    main()
