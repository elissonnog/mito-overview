#!/usr/bin/env python3
"""Create or verify a public-validation alignment provenance manifest."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRE_INSTALLED = os.environ.get("MITO_OVERVIEW_REQUIRE_INSTALLED", "0") == "1"
if not REQUIRE_INSTALLED and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import mito_overview.validation_provenance as _provenance  # noqa: E402
from mito_overview.validation_provenance import (  # noqa: E402
    ProvenanceError,
    create_alignment_provenance,
    parse_key_values,
    parse_labeled_paths,
    verify_alignment_provenance,
)

if REQUIRE_INSTALLED:
    module_path = Path(_provenance.__file__).resolve()
    if module_path == REPO_ROOT / "mito_overview" / "validation_provenance.py":
        raise SystemExit(
            "MITO_OVERVIEW_REQUIRE_INSTALLED=1 but provenance code resolved "
            "from the source checkout"
        )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="action", required=True)
    for name in ("record", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--manifest", required=True, type=Path)
        command.add_argument("--dataset", required=True)
        command.add_argument("--alignment", required=True, type=Path)
        command.add_argument("--reference", required=True, type=Path)
        command.add_argument("--input", action="append", default=[], metavar="LABEL=PATH")
        command.add_argument("--derivation-id", required=True)
        command.add_argument("--command-template", required=True)
        command.add_argument("--parameter", action="append", default=[], metavar="KEY=VALUE")
        command.add_argument("--tool", action="append", default=[])
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        inputs = parse_labeled_paths(args.input)
        common = {
            "manifest_path": args.manifest,
            "dataset_id": args.dataset,
            "alignment_path": args.alignment,
            "reference_path": args.reference,
            "inputs": inputs,
            "derivation_id": args.derivation_id,
            "command_template": args.command_template,
            "parameters": parse_key_values(args.parameter),
            "tools": args.tool,
        }
        if args.action == "record":
            create_alignment_provenance(**common)
            print(f"[provenance] recorded {args.manifest}")
        else:
            verify_alignment_provenance(**common)
            print(f"[provenance] verified {args.manifest}")
    except (FileNotFoundError, FileExistsError, ProvenanceError, ValueError) as exc:
        raise SystemExit(f"Public alignment provenance failed: {exc}") from exc


if __name__ == "__main__":
    main()
