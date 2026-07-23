"""Run legacy Phy-Mer under modern Python without modifying vendor source."""

from __future__ import annotations

import builtins
import runpy
import sys
from pathlib import Path
from typing import Any


_ORIGINAL_OPEN = builtins.open


def _open_with_legacy_universal_newlines(
    file: Any,
    mode: str = "r",
    *args: Any,
    **kwargs: Any,
):
    """Translate Python 2's removed ``U`` mode to Python 3 text mode."""

    if "U" in mode:
        mode = mode.replace("U", "") or "r"
    return _ORIGINAL_OPEN(file, mode, *args, **kwargs)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m mito_overview.phymer_compat PHYMER_SCRIPT [ARGS ...]")
    script = Path(sys.argv[1]).resolve()
    if not script.is_file():
        raise SystemExit(f"Phy-Mer script does not exist: {script}")

    builtins.open = _open_with_legacy_universal_newlines
    sys.argv = [str(script), *sys.argv[2:]]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
