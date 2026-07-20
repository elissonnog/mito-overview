from __future__ import annotations

import os
import tempfile
from pathlib import Path


_MPL_CACHE = Path(tempfile.gettempdir()) / "mito-overview-pytest-mpl"
_MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CACHE))
