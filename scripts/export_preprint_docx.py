#!/usr/bin/env python3
"""Compatibility wrapper for exporting the canonical preprint Markdown to DOCX."""

from __future__ import annotations

import sys
from pathlib import Path

from export_markdown_docx import build_doc


def main(argv: list[str]) -> int:
    source = Path(argv[1]) if len(argv) > 1 else Path("paper/preprint_draft.md")
    output = (
        Path(argv[2])
        if len(argv) > 2
        else Path("paper/mito_overview_workflow_resource_manuscript_v0.2.1.docx")
    )
    build_doc(source.resolve(), output.resolve())
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
