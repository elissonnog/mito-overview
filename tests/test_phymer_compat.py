from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_legacy_universal_newline_adapter_preserves_vendor_arguments(
    tmp_path: Path,
) -> None:
    fasta = tmp_path / "input.fa"
    fasta.write_text(">sample\nACGT\n", encoding="ascii")
    vendor = tmp_path / "legacy_vendor.py"
    vendor.write_text(
        "from Bio import SeqIO\n"
        "import sys\n"
        "with open(sys.argv[1], 'rU') as handle:\n"
        "    record = next(SeqIO.parse(handle, 'fasta'))\n"
        "print(record.id + '\\t' + str(record.seq))\n",
        encoding="ascii",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mito_overview.phymer_compat",
            str(vendor),
            str(fasta),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "sample\tACGT\n"
    assert completed.stderr == ""


def test_compatibility_launcher_requires_vendor_script() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "mito_overview.phymer_compat"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "PHYMER_SCRIPT" in completed.stderr
