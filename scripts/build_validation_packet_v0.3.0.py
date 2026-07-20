#!/usr/bin/env python3
"""Build the self-checking mito-overview v0.3.0 validation packet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_TOP_LEVEL = (
    "run.json",
    "cases.tsv",
    "claim_evidence_matrix.tsv",
    "public_data_sources.tsv",
    "environment.txt",
    "commands",
    "logs",
    "expected",
    "observed_normalized",
    "inputs.sha256",
    "artifacts.sha256",
    "verify_bundle.sh",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("validation_root", type=Path)
    parser.add_argument("packet_root", type=Path)
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--version", default="v0.3.0")
    parser.add_argument("--repository", default="https://github.com/elissonnog/mito-overview")
    parser.add_argument("--doi", default="UNRESERVED")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Required directory not found: {source}")
    shutil.copytree(source, destination)


def write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def validate_cases(path: Path) -> tuple[int, dict[str, int]]:
    allowed = {"PASS", "FAIL", "XFAIL", "SKIP", "BLOCKED"}
    counts = {value: 0 for value in allowed}
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise ValueError("cases.tsv contains no validation cases")
    for row in rows:
        verdict = row.get("verdict", "")
        if verdict not in allowed:
            raise ValueError(f"Unsupported case verdict: {verdict}")
        if verdict == "PASS" and (
            row.get("input_available") != "1" or row.get("expected_available") != "1"
        ):
            raise ValueError(f"PASS case lacks input or expected evidence: {row.get('case_id')}")
        counts[verdict] += 1
    return len(rows), counts


def write_verifier(path: Path) -> None:
    script = r'''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

for required in run.json cases.tsv claim_evidence_matrix.tsv public_data_sources.tsv environment.txt commands logs expected observed_normalized inputs.sha256 artifacts.sha256 verify_bundle.sh; do
  [[ -e "${required}" ]] || { echo "missing required evidence: ${required}" >&2; exit 1; }
done

while read -r digest relative; do
  relative="${relative#\*}"
  [[ -f "${relative}" ]] || { echo "missing artifact: ${relative}" >&2; exit 1; }
  if command -v sha256sum >/dev/null 2>&1; then
    observed="$(sha256sum "${relative}" | awk '{print $1}')"
  else
    observed="$(shasum -a 256 "${relative}" | awk '{print $1}')"
  fi
  [[ "${observed}" == "${digest}" ]] || { echo "hash mismatch: ${relative}" >&2; exit 1; }
done < artifacts.sha256

python3 - "${ROOT}" <<'PY'
import csv
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
run = json.loads((root / "run.json").read_text(encoding="utf-8"))
if run.get("release_version") != "v0.3.0":
    raise SystemExit("release identity mismatch")
if not re.fullmatch(r"[0-9a-f]{40}", str(run.get("git_commit", ""))):
    raise SystemExit("invalid release commit")

verdicts = {"PASS", "FAIL", "XFAIL", "SKIP", "BLOCKED"}
with (root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
    cases = list(csv.DictReader(handle, delimiter="\t"))
if not cases:
    raise SystemExit("no validation cases")
for case in cases:
    if case.get("verdict") not in verdicts:
        raise SystemExit(f"invalid verdict: {case}")
    if case.get("verdict") == "PASS" and (
        case.get("input_available") != "1" or case.get("expected_available") != "1"
    ):
        raise SystemExit(f"unsupported PASS verdict: {case.get('case_id')}")

states = {"ok", "not_configured", "not_applicable", "not_evaluable", "unavailable", "failed"}
for path in (root / "observed_normalized").rglob("*.tsv"):
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    if not rows or rows[0][:2] != ["metric", "value"]:
        continue
    for row in rows[1:]:
        if len(row) >= 2 and row[0] == "status" and row[1] not in states:
            raise SystemExit(f"invalid module status {row[1]!r} in {path}")

input_lines = [line for line in (root / "inputs.sha256").read_text().splitlines() if line]
if not input_lines or any(not re.fullmatch(r"[0-9a-f]{64}  .+", line) for line in input_lines):
    raise SystemExit("invalid input hash manifest")
print(f"verified mito-overview {run['release_version']} packet at commit {run['git_commit']}")
PY
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> None:
    args = parse_args()
    if not args.validation_root.is_dir():
        raise SystemExit(f"Validation root not found: {args.validation_root}")
    if args.packet_root.exists() and any(args.packet_root.iterdir()):
        raise SystemExit(f"Packet root must be absent or empty: {args.packet_root}")
    args.packet_root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(args.validation_root / "cases.tsv", args.packet_root / "cases.tsv")
    shutil.copy2(args.validation_root / "environment.txt", args.packet_root / "environment.txt")
    copy_tree(args.validation_root / "commands", args.packet_root / "commands")
    copy_tree(args.validation_root / "logs", args.packet_root / "logs")
    copy_tree(args.validation_root / "expected", args.packet_root / "expected")
    copy_tree(
        args.validation_root / "public" / "observed_normalized",
        args.packet_root / "observed_normalized",
    )
    shutil.copy2(
        args.validation_root / "public" / "filter_profile_results.tsv",
        args.packet_root / "filter_profile_results.tsv",
    )

    case_count, verdict_counts = validate_cases(args.packet_root / "cases.tsv")
    run = {
        "schema_version": "1.0",
        "release_version": args.version,
        "git_commit": args.commit,
        "repository": args.repository,
        "archive_doi": args.doi,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": case_count,
        "verdict_counts": verdict_counts,
        "claim_scope": "reproducible mode-gated mtDNA reporting workflow/resource",
        "diagnostic_validation_claimed": False,
    }
    (args.packet_root / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

    write_tsv(
        args.packet_root / "claim_evidence_matrix.tsv",
        ["claim_id", "bounded_claim", "evidence", "limitation"],
        [
            [
                "C1",
                "Shared filtered allele counting is deterministic on known-answer fixtures",
                "unit_known_answer; synthetic_longread_smoke; expected/TOY-SR-001.expected_alleles.tsv",
                "Reporting thresholds are not clinically calibrated",
            ],
            [
                "C2",
                "mvTool is offline by default with deterministic fixture coverage",
                "unit_known_answer; synthetic_longread_smoke",
                "No claim of live service availability",
            ],
            [
                "C3",
                "Minimal standalone BAM and CRAM contracts are preflighted",
                "unit_known_answer; strict_generic_dry_run; standalone_minimal_smoke",
                "Optional sidecars remain user supplied",
            ],
            [
                "C4",
                "The WGS fixture reports a 100/10 mt:nuclear depth ratio of 10.0",
                "unit_known_answer; expected/TOY-WGS-001.expected_copy_proxy.tsv",
                "Experimental depth proxy, not absolute copies per diploid cell",
            ],
            [
                "C5",
                "mt-only references suppress categorical NUMT interpretation",
                "unit_known_answer; gm12878_default_run1; gm12878_repeatability",
                "Alignment-ambiguity QC is not a formal NUMT classifier",
            ],
            [
                "C6",
                "Public proof-of-principle workflows reproduce normalized TSVs",
                "gm11906_repeatability; gm12878_repeatability; filter_profile_results.tsv",
                "Not a sensitivity, specificity, deletion-truth, or diagnostic benchmark",
            ],
        ],
    )
    write_tsv(
        args.packet_root / "public_data_sources.tsv",
        [
            "dataset",
            "run_accession",
            "study_accession",
            "sample_accession",
            "cell_line",
            "platform",
            "instrument_model",
            "library_strategy",
            "fastq_url",
            "fastq_md5",
            "fastq_bytes",
            "metadata_checked_utc",
            "role",
            "redistribution",
        ],
        [
            [
                "GM11906 reduced short-read proof-of-principle",
                "SRR10804585",
                "PRJNA598179",
                "SAMN13699362",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_2.fastq.gz",
                "3f5ea26a5791894071462d4970bc9e5a;c5b408425612f63b33cefd2d49c157d1",
                "8795676;8817420",
                "2026-07-20",
                "default repeatability, m.8344A>G release gate, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
            [
                "GM11906 reduced short-read proof-of-principle",
                "SRR10804590",
                "PRJNA598179",
                "SAMN13699398",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_2.fastq.gz",
                "e8b5132a8be8c179bfc6dbc0f3e1bee9;4d6977526136739de2d90baa8d45b484",
                "1006749;795885",
                "2026-07-20",
                "default repeatability, m.8344A>G release gate, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
            [
                "GM11906 reduced short-read proof-of-principle",
                "SRR10804657",
                "PRJNA598179",
                "SAMN13699338",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_2.fastq.gz",
                "8f082f73cb64bf56ea8a053fe80eeb06;62b7d1b2294a580c021f5fa1f52609be",
                "21510555;21573731",
                "2026-07-20",
                "default repeatability, m.8344A>G release gate, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
            [
                "GM12878 ONT targeted-mt proof-of-principle",
                "SRR18110025",
                "PRJNA809571",
                "SAMN26195906",
                "GM12878",
                "OXFORD_NANOPORE",
                "GridION",
                "OTHER",
                "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR181/025/SRR18110025/SRR18110025_1.fastq.gz",
                "d5bfb9aeba04cae5f3dd79462a42e5b0",
                "2033558460",
                "2026-07-20",
                "long-read repeatability, mt-only scope gating, filter profiles",
                "raw reads excluded from Git and validation ZIP",
            ],
        ],
    )

    input_rows: list[str] = []
    for path in sorted(args.cache_root.rglob("*")):
        if not path.is_file() or path.name in {"inputs.sha256", "cache_provenance.tsv"}:
            continue
        input_rows.append(f"{sha256(path)}  {path.relative_to(args.cache_root).as_posix()}")
    if not input_rows:
        raise SystemExit(f"No cached validation inputs found under {args.cache_root}")
    (args.packet_root / "inputs.sha256").write_text("\n".join(input_rows) + "\n", encoding="utf-8")

    write_verifier(args.packet_root / "verify_bundle.sh")
    artifact_rows: list[str] = []
    for path in sorted(args.packet_root.rglob("*")):
        if not path.is_file() or path.name == "artifacts.sha256":
            continue
        artifact_rows.append(f"{sha256(path)}  {path.relative_to(args.packet_root).as_posix()}")
    (args.packet_root / "artifacts.sha256").write_text(
        "\n".join(artifact_rows) + "\n", encoding="utf-8"
    )

    missing = [name for name in REQUIRED_TOP_LEVEL if not (args.packet_root / name).exists()]
    if missing:
        raise SystemExit(f"Packet is missing required entries: {missing}")

    args.zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(args.packet_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(args.packet_root).as_posix())
    print(args.zip_path)


if __name__ == "__main__":
    main()
