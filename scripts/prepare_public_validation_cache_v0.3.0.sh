#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  prepare_public_validation_cache_v0.3.0.sh --cache CACHE_ROOT
  prepare_public_validation_cache_v0.3.0.sh --verify --cache CACHE_ROOT

Prepare mode starts from an absent, empty, or interrupted unsealed cache. It
downloads the seven locked ENA FASTQs through resumable .partial files, verifies
their identities and FASTQ structure, and writes an immutable manifest/seal.
Verify mode is network-free and rejects every file outside the sealed contract.
EOF
}

MODE=prepare
CACHE_ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cache)
      [[ $# -ge 2 ]] || { echo "--cache requires a value" >&2; exit 2; }
      CACHE_ROOT="$2"
      shift 2
      ;;
    --verify)
      MODE=verify
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "${CACHE_ROOT}" ]] || { usage >&2; exit 2; }

# A cache path is part of the public-data identity contract. Do not silently
# canonicalize a caller-supplied symlink into an unrelated directory.
while [[ "${CACHE_ROOT}" != / && "${CACHE_ROOT}" == */ ]]; do
  CACHE_ROOT="${CACHE_ROOT%/}"
done
[[ ! -L "${CACHE_ROOT}" ]] || {
  echo "Cache root must not be a symlink: ${CACHE_ROOT}" >&2
  exit 1
}
if [[ -e "${CACHE_ROOT}" && ! -d "${CACHE_ROOT}" ]]; then
  echo "Cache root must be a directory path: ${CACHE_ROOT}" >&2
  exit 1
fi
if [[ "${MODE}" == verify && ! -d "${CACHE_ROOT}" ]]; then
  echo "Sealed cache root not found: ${CACHE_ROOT}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"
MANIFEST_NAME=raw_inputs.tsv
SEAL_NAME=CACHE_SEAL.sha256
MANIFEST_PATH="${CACHE_ROOT}/${MANIFEST_NAME}"
SEAL_PATH="${CACHE_ROOT}/${SEAL_NAME}"

for tool in "${PYTHON_BIN}" gzip; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "Required tool not found in PATH: ${tool}" >&2
    exit 1
  }
done
if [[ "${MODE}" == prepare ]]; then
  command -v curl >/dev/null 2>&1 || {
    echo "Required tool not found in PATH: curl" >&2
    exit 1
  }
fi

if [[ "${MODE}" == prepare ]]; then
  mkdir -p "${CACHE_ROOT}"
fi
[[ -d "${CACHE_ROOT}" && ! -L "${CACHE_ROOT}" ]] || {
  echo "Cache root must be a regular directory, not a symlink: ${CACHE_ROOT}" >&2
  exit 1
}
CACHE_ROOT="$(cd "${CACHE_ROOT}" && pwd)"
MANIFEST_PATH="${CACHE_ROOT}/${MANIFEST_NAME}"
SEAL_PATH="${CACHE_ROOT}/${SEAL_NAME}"

SPEC_PATH="$(mktemp "${TMPDIR:-/tmp}/mito-overview-public-cache-spec.XXXXXX")"
COUNTS_PATH="$(mktemp "${TMPDIR:-/tmp}/mito-overview-public-cache-counts.XXXXXX")"
trap 'rm -f "${SPEC_PATH}" "${COUNTS_PATH}"' EXIT

cat > "${SPEC_PATH}" <<'EOF'
dataset_id	run_accession	sample_accession	sample_alias	sample_title	source_sample_id	library_strategy	library_unit	source_record_url	filename	bytes	md5	sha256	url
GM11906_pooled_scATAC	SRR10804585	SAMN13699362	GSM4238454	MERFF-29-S42	GM11906	ATAC-seq	single_cell_library	https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238454	SRR10804585_1.fastq.gz	8795676	3f5ea26a5791894071462d4970bc9e5a	b69746cb61d8bf3bc25887d6ece3c60db3acc7baaefd84a9a8b5d6ffce33288d	https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_1.fastq.gz
GM11906_pooled_scATAC	SRR10804585	SAMN13699362	GSM4238454	MERFF-29-S42	GM11906	ATAC-seq	single_cell_library	https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238454	SRR10804585_2.fastq.gz	8817420	c5b408425612f63b33cefd2d49c157d1	1fca2c35a955a4ed232465d8392bc04683828229178aee7915929e67b2aac961	https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_2.fastq.gz
GM11906_pooled_scATAC	SRR10804590	SAMN13699398	GSM4238459	MERFF-33-S46	GM11906	ATAC-seq	single_cell_library	https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238459	SRR10804590_1.fastq.gz	1006749	e8b5132a8be8c179bfc6dbc0f3e1bee9	e47ceceb03d44483b4948fe9c631ebff307f5ec68a1deec978f1122695fa58fc	https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_1.fastq.gz
GM11906_pooled_scATAC	SRR10804590	SAMN13699398	GSM4238459	MERFF-33-S46	GM11906	ATAC-seq	single_cell_library	https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238459	SRR10804590_2.fastq.gz	795885	4d6977526136739de2d90baa8d45b484	05b2375b30b02c02e9206981eb2fe2d08babbc2a5809f8354ef56d0ac1550776	https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_2.fastq.gz
GM11906_pooled_scATAC	SRR10804657	SAMN13699338	GSM4238526	MERFF-94-S107	GM11906	ATAC-seq	single_cell_library	https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238526	SRR10804657_1.fastq.gz	21510555	8f082f73cb64bf56ea8a053fe80eeb06	1afaf310ce9ffa77e1c3d61a0714e839d21000941d414cc7bf6fb590c3b665f2	https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_1.fastq.gz
GM11906_pooled_scATAC	SRR10804657	SAMN13699338	GSM4238526	MERFF-94-S107	GM11906	ATAC-seq	single_cell_library	https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238526	SRR10804657_2.fastq.gz	21573731	62b7d1b2294a580c021f5fa1f52609be	bfc555c7e722695b02110027757bba4d7fc88f487798423cd6809e8a771a5184	https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_2.fastq.gz
GM12878_ONT	SRR18110025	SAMN26195906	GM12878_mtDNA	Human GM12878 Cell Line	GM12878	OTHER	targeted_mt_library	https://www.ebi.ac.uk/ena/browser/view/SRR18110025	SRR18110025.fastq.gz	2033558460	d5bfb9aeba04cae5f3dd79462a42e5b0	c0872ee9ceb772ee5a4b76735c0d670e2159764b23dd800b6eb1f4933da11320	https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR181/025/SRR18110025/SRR18110025_1.fastq.gz
EOF

expected_names() {
  awk -F '\t' 'NR > 1 {print $10}' "${SPEC_PATH}"
}

sha256_file() {
  "${PYTHON_BIN}" - "$1" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as handle:
    for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

assert_allowed_unsealed_contents() {
  local path base allowed
  while IFS= read -r -d '' path; do
    base="$(basename "${path}")"
    allowed=0
    while IFS= read -r name; do
      if [[ "${base}" == "${name}" || "${base}" == "${name}.partial" ]]; then
        allowed=1
        break
      fi
    done < <(expected_names)
    if [[ "${allowed}" -ne 1 ]]; then
      echo "Unsealed cache contains an unexpected path: ${path}" >&2
      exit 1
    fi
    if [[ -L "${path}" || ! -f "${path}" ]]; then
      echo "Unsealed cache paths must be regular, non-symlink files: ${path}" >&2
      exit 1
    fi
  done < <(find "${CACHE_ROOT}" -mindepth 1 -maxdepth 1 -print0)
}

verify_one_fastq() {
  local path="$1"
  local expected_bytes="$2"
  local expected_md5="$3"
  local expected_sha256="$4"
  gzip -t "${path}"
  "${PYTHON_BIN}" - "${path}" "${expected_bytes}" "${expected_md5}" "${expected_sha256}" <<'PY'
import gzip
import hashlib
import os
import sys

path, expected_bytes, expected_md5, expected_sha256 = sys.argv[1:]
size = os.path.getsize(path)
if size != int(expected_bytes):
    raise SystemExit(f"byte-size mismatch for {path}: expected {expected_bytes}, observed {size}")
md5 = hashlib.md5()  # nosec B324: archival ENA identity, paired with SHA-256
sha256 = hashlib.sha256()
with open(path, "rb") as handle:
    for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
        md5.update(chunk)
        sha256.update(chunk)
if md5.hexdigest() != expected_md5:
    raise SystemExit(f"MD5 mismatch for {path}: expected {expected_md5}, observed {md5.hexdigest()}")
if sha256.hexdigest() != expected_sha256:
    raise SystemExit(
        f"SHA-256 mismatch for {path}: expected {expected_sha256}, observed {sha256.hexdigest()}"
    )

records = 0
with gzip.open(path, "rt", encoding="ascii", newline="") as handle:
    while True:
        header = handle.readline()
        if not header:
            break
        sequence = handle.readline()
        plus = handle.readline()
        quality = handle.readline()
        records += 1
        if not sequence or not plus or not quality:
            raise SystemExit(f"truncated FASTQ record {records} in {path}")
        if not header.startswith("@") or not plus.startswith("+"):
            raise SystemExit(f"malformed FASTQ record {records} in {path}")
        if len(sequence.rstrip("\r\n")) != len(quality.rstrip("\r\n")):
            raise SystemExit(f"sequence/quality length mismatch at record {records} in {path}")
if records == 0:
    raise SystemExit(f"FASTQ contains no records: {path}")
print(records)
PY
}

validate_pairs() {
  "${PYTHON_BIN}" - "${CACHE_ROOT}" <<'PY'
import gzip
import sys
from pathlib import Path

root = Path(sys.argv[1])
pairs = ["SRR10804585", "SRR10804590", "SRR10804657"]

def normalized(header: str) -> str:
    name = header[1:].split(None, 1)[0]
    if name.endswith("/1") or name.endswith("/2"):
        name = name[:-2]
    return name

for accession in pairs:
    left = root / f"{accession}_1.fastq.gz"
    right = root / f"{accession}_2.fastq.gz"
    count = 0
    with gzip.open(left, "rt", encoding="ascii") as r1, gzip.open(
        right, "rt", encoding="ascii"
    ) as r2:
        while True:
            record1 = [r1.readline() for _ in range(4)]
            record2 = [r2.readline() for _ in range(4)]
            if not record1[0] and not record2[0]:
                break
            count += 1
            if not all(record1) or not all(record2):
                raise SystemExit(f"paired FASTQ record-count mismatch for {accession}")
            if normalized(record1[0]) != normalized(record2[0]):
                raise SystemExit(
                    f"paired FASTQ query-name mismatch for {accession} at record {count}"
                )
    if count == 0:
        raise SystemExit(f"paired FASTQ contains no records for {accession}")
    print(f"[public-cache] paired FASTQ verified accession={accession} records={count}")
PY
}

verify_sealed_cache() {
  [[ -f "${MANIFEST_PATH}" && ! -L "${MANIFEST_PATH}" ]] || {
    echo "Sealed cache manifest missing or invalid: ${MANIFEST_PATH}" >&2
    exit 1
  }
  [[ -f "${SEAL_PATH}" && ! -L "${SEAL_PATH}" ]] || {
    echo "Sealed cache seal missing or invalid: ${SEAL_PATH}" >&2
    exit 1
  }

  local expected_count=9 observed_count
  observed_count="$(find "${CACHE_ROOT}" -mindepth 1 -maxdepth 1 -type f ! -type l | wc -l | tr -d ' ')"
  [[ "${observed_count}" == "${expected_count}" ]] || {
    echo "Sealed cache must contain exactly seven FASTQs plus manifest and seal; observed ${observed_count} regular files" >&2
    exit 1
  }
  if find "${CACHE_ROOT}" -mindepth 1 -maxdepth 1 \( -type d -o -type l -o ! -type f \) -print -quit | grep -q .; then
    echo "Sealed cache contains a directory, symlink, or non-regular path" >&2
    exit 1
  fi

  local manifest_digest seal_digest seal_name
  manifest_digest="$(sha256_file "${MANIFEST_PATH}")"
  read -r seal_digest seal_name < "${SEAL_PATH}"
  [[ "${seal_digest}" == "${manifest_digest}" && "${seal_name}" == "${MANIFEST_NAME}" ]] || {
    echo "Cache seal does not match ${MANIFEST_NAME}" >&2
    exit 1
  }

  "${PYTHON_BIN}" - "${SPEC_PATH}" "${MANIFEST_PATH}" <<'PY'
import csv
import sys

spec_path, manifest_path = sys.argv[1:]
with open(spec_path, encoding="utf-8", newline="") as handle:
    expected = list(csv.DictReader(handle, delimiter="\t"))
with open(manifest_path, encoding="utf-8", newline="") as handle:
    observed = list(csv.DictReader(handle, delimiter="\t"))
expected_fields = [
    "schema_version", "dataset_id", "run_accession", "sample_accession",
    "sample_alias", "sample_title", "source_sample_id", "library_strategy",
    "library_unit", "source_record_url", "filename", "bytes", "md5",
    "sha256", "fastq_records", "url",
]
if not observed or list(observed[0]) != expected_fields:
    raise SystemExit("raw cache manifest schema mismatch")
if len(observed) != 7:
    raise SystemExit(f"raw cache manifest must contain seven rows, observed {len(observed)}")
expected_by_name = {row["filename"]: row for row in expected}
observed_by_name = {row["filename"]: row for row in observed}
if set(observed_by_name) != set(expected_by_name):
    raise SystemExit("raw cache manifest filenames differ from the immutable v0.3.0 specification")
for name, expected_row in expected_by_name.items():
    row = observed_by_name[name]
    if row["schema_version"] != "1.0":
        raise SystemExit(f"manifest schema version mismatch for {name}")
    for field in expected_row:
        if row[field] != expected_row[field]:
            raise SystemExit(
                f"manifest {field} mismatch for {name}: expected {expected_row[field]!r}, observed {row[field]!r}"
            )
    if not row["fastq_records"].isdigit() or int(row["fastq_records"]) < 1:
        raise SystemExit(f"invalid FASTQ record count for {name}")
PY

  : > "${COUNTS_PATH}"
  while IFS=$'\t' read -r dataset run sample alias title source_sample strategy unit source_record filename bytes md5 sha url; do
    [[ "${dataset}" == dataset_id ]] && continue
    local records
    records="$(verify_one_fastq "${CACHE_ROOT}/${filename}" "${bytes}" "${md5}" "${sha}")"
    printf '%s\t%s\n' "${filename}" "${records}" >> "${COUNTS_PATH}"
  done < "${SPEC_PATH}"

  "${PYTHON_BIN}" - "${MANIFEST_PATH}" "${COUNTS_PATH}" <<'PY'
import csv
import sys

with open(sys.argv[2], encoding="utf-8") as handle:
    counts = dict(line.rstrip("\n").split("\t", 1) for line in handle if line.strip())
with open(sys.argv[1], encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
for row in rows:
    if row["fastq_records"] != counts.get(row["filename"]):
        raise SystemExit(f"FASTQ record-count mismatch for {row['filename']}")
PY
  validate_pairs
  echo "[public-cache] sealed cache verified: ${CACHE_ROOT}"
}

if [[ "${MODE}" == verify ]]; then
  verify_sealed_cache
  exit 0
fi

if [[ -e "${SEAL_PATH}" || -e "${MANIFEST_PATH}" ]]; then
  verify_sealed_cache
  echo "[public-cache] cache was already sealed; no download performed"
  exit 0
fi
assert_allowed_unsealed_contents

while IFS=$'\t' read -r dataset run sample alias title source_sample strategy unit source_record filename bytes md5 sha url; do
  [[ "${dataset}" == dataset_id ]] && continue
  destination="${CACHE_ROOT}/${filename}"
  partial="${destination}.partial"
  if [[ ! -f "${destination}" ]]; then
    if [[ -f "${partial}" ]] && records="$(verify_one_fastq "${partial}" "${bytes}" "${md5}" "${sha}" 2>/dev/null)"; then
      echo "[public-cache] promoting complete verified partial ${filename}"
    else
      echo "[public-cache] downloading ${run} ${filename}"
      curl \
        --fail \
        --location \
        --retry "${MITO_OVERVIEW_PUBLIC_CURL_RETRIES:-5}" \
        --retry-all-errors \
        --retry-delay "${MITO_OVERVIEW_PUBLIC_CURL_RETRY_DELAY:-3}" \
        --connect-timeout "${MITO_OVERVIEW_PUBLIC_CURL_CONNECT_TIMEOUT:-30}" \
        --max-time "${MITO_OVERVIEW_PUBLIC_CURL_MAX_TIME:-0}" \
        --continue-at - \
        --output "${partial}" \
        "${url}"
      records="$(verify_one_fastq "${partial}" "${bytes}" "${md5}" "${sha}")"
    fi
    mv "${partial}" "${destination}"
  else
    records="$(verify_one_fastq "${destination}" "${bytes}" "${md5}" "${sha}")"
    rm -f "${partial}"
  fi
  printf '%s\t%s\n' "${filename}" "${records}" >> "${COUNTS_PATH}"
done < "${SPEC_PATH}"

validate_pairs

"${PYTHON_BIN}" - "${SPEC_PATH}" "${COUNTS_PATH}" "${MANIFEST_PATH}" <<'PY'
import csv
import sys

spec_path, counts_path, manifest_path = sys.argv[1:]
with open(counts_path, encoding="utf-8") as handle:
    counts = dict(line.rstrip("\n").split("\t", 1) for line in handle if line.strip())
with open(spec_path, encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
fields = [
    "schema_version", "dataset_id", "run_accession", "sample_accession",
    "sample_alias", "sample_title", "source_sample_id", "library_strategy",
    "library_unit", "source_record_url", "filename", "bytes", "md5",
    "sha256", "fastq_records", "url",
]
with open(manifest_path, "x", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "schema_version": "1.0",
                **row,
                "fastq_records": counts[row["filename"]],
            }
        )
PY

printf '%s  %s\n' "$(sha256_file "${MANIFEST_PATH}")" "${MANIFEST_NAME}" > "${SEAL_PATH}"
verify_sealed_cache
echo "[public-cache] preparation complete: ${CACHE_ROOT}"
