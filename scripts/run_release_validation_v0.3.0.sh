#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<EOF
Usage: MITO_OVERVIEW_GITHUB_RUN_ID=RUN_ID \\
  MITO_OVERVIEW_ZENODO_RESERVATION_EVIDENCE=SANITIZED_JSON $0 \\
  VALIDATION_ROOT CACHE_ROOT PACKET_ROOT \\
  AUDIT_ZIP [ARCHIVE_DOI]
DOI may instead be supplied as MITO_OVERVIEW_ARCHIVE_DOI.
The sanitized evidence must be captured from an authenticated Zenodo deposition
response. Authentication and token handling stay outside this workflow.
EOF
}

if [[ $# -lt 4 || $# -gt 5 ]]; then
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"
REPOSITORY="https://github.com/elissonnog/mito-overview"
GITHUB_REPOSITORY="elissonnog/mito-overview"
GITHUB_RUN_ID="${MITO_OVERVIEW_GITHUB_RUN_ID:-}"
ZENODO_RESERVATION_EVIDENCE_INPUT="${MITO_OVERVIEW_ZENODO_RESERVATION_EVIDENCE:-}"
FRESH_CLONE_CASE_ID="fresh_clone_candidate_commit"
EXPECTED_AUDIT_ZIP="mito-overview-v0.3.0-validation.zip"

resolve_path() {
  local label="$1"
  local value="$2"
  if [[ -z "${value}" || "${value}" == *$'\n'* || "${value}" == *$'\r'* || \
    "${value}" == *$'\t'* ]]; then
    echo "${label} must be a non-empty path without control characters." >&2
    return 1
  fi
  "${PYTHON_BIN}" - "${value}" <<'PY'
import sys
from pathlib import Path

print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

VALIDATION_ROOT="$(resolve_path "Validation root" "$1")"
CACHE_ROOT="$(resolve_path "Cache root" "$2")"
PACKET_ROOT="$(resolve_path "Packet root" "$3")"
AUDIT_ZIP="$(resolve_path "Audit ZIP" "$4")"
if [[ -z "${ZENODO_RESERVATION_EVIDENCE_INPUT}" ]]; then
  echo "MITO_OVERVIEW_ZENODO_RESERVATION_EVIDENCE is required; a DOI string alone is insufficient." >&2
  exit 1
fi
ZENODO_RESERVATION_EVIDENCE="$(resolve_path \
  "Zenodo reservation evidence" "${ZENODO_RESERVATION_EVIDENCE_INPUT}")"
DOI_ARGUMENT="${5:-}"
DOI_ENVIRONMENT="${MITO_OVERVIEW_ARCHIVE_DOI:-}"
PACKET_BUILD_LOG="${AUDIT_ZIP}.build.log"
PACKET_VERIFY_LOG="${AUDIT_ZIP}.verify.log"
PACKET_SHA256="${AUDIT_ZIP}.sha256"
PACKET_RECEIPT="${AUDIT_ZIP}.verification.json"

if [[ -n "${DOI_ARGUMENT}" ]] && [[ -n "${DOI_ENVIRONMENT}" ]] && \
  [[ "${DOI_ARGUMENT}" != "${DOI_ENVIRONMENT}" ]]; then
  echo "ARCHIVE_DOI argument and MITO_OVERVIEW_ARCHIVE_DOI disagree." >&2
  exit 1
fi
ARCHIVE_DOI="${DOI_ARGUMENT:-${DOI_ENVIRONMENT}}"
if [[ ! "${ARCHIVE_DOI}" =~ ^10\.5281/zenodo\.[1-9][0-9]*$ ]]; then
  echo "A canonical Zenodo DOI (10.5281/zenodo.<record-id>) is required." >&2
  exit 1
fi
if [[ ! -f "${ZENODO_RESERVATION_EVIDENCE}" || ! -s "${ZENODO_RESERVATION_EVIDENCE}" ]]; then
  echo "Sanitized Zenodo reservation evidence is missing or empty: ${ZENODO_RESERVATION_EVIDENCE}" >&2
  exit 1
fi

"${PYTHON_BIN}" - \
  "${REPO_ROOT}" "${VALIDATION_ROOT}" "${CACHE_ROOT}" \
  "${PACKET_ROOT}" "${AUDIT_ZIP}" "${EXPECTED_AUDIT_ZIP}" <<'PY'
import sys
from pathlib import Path

repo_root, validation_root, cache_root, packet_root, audit_zip = map(
    Path, sys.argv[1:6]
)
expected_zip = sys.argv[6]
directory_roots = {
    "validation root": validation_root,
    "cache root": cache_root,
    "packet root": packet_root,
}

for label, path in directory_roots.items():
    if path == Path(path.anchor):
        raise SystemExit(f"{label} must not be a filesystem root: {path}")
if audit_zip.name != expected_zip:
    raise SystemExit(
        f"Audit ZIP must be named {expected_zip!r}, not {audit_zip.name!r}"
    )

def contains(parent: Path, child: Path) -> bool:
    return child == parent or parent in child.parents

items = list(directory_roots.items())
for index, (left_label, left) in enumerate(items):
    for right_label, right in items[index + 1 :]:
        if contains(left, right) or contains(right, left):
            raise SystemExit(
                f"{left_label} and {right_label} must not overlap: {left}; {right}"
            )
for label, path in items:
    if contains(path, audit_zip):
        raise SystemExit(f"Audit ZIP must be outside {label}: {path}")
    if contains(repo_root, path) or contains(path, repo_root):
        raise SystemExit(f"{label} must be outside the release repository: {path}")
if contains(repo_root, audit_zip):
    raise SystemExit(f"Audit ZIP must be outside the release repository: {audit_zip}")
PY

"${PYTHON_BIN}" - "${REPO_ROOT}/CITATION.cff" "${ARCHIVE_DOI}" <<'PY'
import sys
from pathlib import Path

citation_path = Path(sys.argv[1])
expected_doi = sys.argv[2]
values = []
for line in citation_path.read_text(encoding="utf-8").splitlines():
    if line.startswith("doi:"):
        values.append(line.partition(":")[2].split("#", 1)[0].strip().strip("'\""))
if values != [expected_doi]:
    raise SystemExit(
        "CITATION.cff must contain exactly one synchronized top-level DOI "
        f"matching {expected_doi!r}; observed {values!r}"
    )
PY

if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
  echo "Release validation requires a clean Git worktree." >&2
  exit 1
fi
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/check_release_hygiene.py" "${REPO_ROOT}"
CANDIDATE_COMMIT="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
if [[ -d "${VALIDATION_ROOT}" && -n "$(find "${VALIDATION_ROOT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Validation root must be absent or empty: ${VALIDATION_ROOT}" >&2
  exit 1
fi
if [[ -e "${VALIDATION_ROOT}" && ! -d "${VALIDATION_ROOT}" ]]; then
  echo "Validation root exists and is not a directory: ${VALIDATION_ROOT}" >&2
  exit 1
fi
if [[ -d "${PACKET_ROOT}" && -n "$(find "${PACKET_ROOT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Packet root must be absent or empty: ${PACKET_ROOT}" >&2
  exit 1
fi
if [[ -e "${PACKET_ROOT}" && ! -d "${PACKET_ROOT}" ]]; then
  echo "Packet root exists and is not a directory: ${PACKET_ROOT}" >&2
  exit 1
fi
if [[ -e "${CACHE_ROOT}" && ! -d "${CACHE_ROOT}" ]]; then
  echo "Cache root exists and is not a directory: ${CACHE_ROOT}" >&2
  exit 1
fi
for output in \
  "${AUDIT_ZIP}" "${PACKET_BUILD_LOG}" "${PACKET_VERIFY_LOG}" \
  "${PACKET_SHA256}" "${PACKET_RECEIPT}"; do
  if [[ -e "${output}" || -L "${output}" ]]; then
    echo "Release output must not already exist: ${output}" >&2
    exit 1
  fi
done
if [[ ! "${GITHUB_RUN_ID}" =~ ^[1-9][0-9]*$ ]]; then
  echo "MITO_OVERVIEW_GITHUB_RUN_ID must identify a completed GitHub Actions run." >&2
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "The GitHub CLI (gh) is required to retrieve real Actions evidence." >&2
  exit 1
fi

mkdir -p \
  "${VALIDATION_ROOT}/acceptance" \
  "${VALIDATION_ROOT}/commands" \
  "${VALIDATION_ROOT}/logs" \
  "${VALIDATION_ROOT}/expected" \
  "${VALIDATION_ROOT}/work" \
  "${VALIDATION_ROOT}/dist"
mkdir -p "$(dirname "${AUDIT_ZIP}")"

CASES_TSV="${VALIDATION_ROOT}/cases.tsv"
printf 'case_id\tcategory\tinput_available\texpected_available\tverdict\tdetail\n' > "${CASES_TSV}"

record_case() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" >> "${CASES_TSV}"
}

run_logged() {
  local case_id="$1"
  local category="$2"
  shift 2
  local command_file="${VALIDATION_ROOT}/commands/${case_id}.sh"
  local log_file="${VALIDATION_ROOT}/logs/${case_id}.log"
  {
    printf 'cd %q\n' "${REPO_ROOT}"
    printf '%q ' "$@"
    printf '\n'
  } > "${command_file}"
  if (cd "${REPO_ROOT}" && "$@") >"${log_file}" 2>&1; then
    record_case "${case_id}" "${category}" 1 1 PASS "see logs/${case_id}.log"
  else
    record_case "${case_id}" "${category}" 1 1 FAIL "see logs/${case_id}.log"
    tail -100 "${log_file}" >&2
    return 1
  fi
}

fetch_github_actions_evidence() {
  local command_file="${VALIDATION_ROOT}/commands/github_actions_candidate_commit.sh"
  local log_file="${VALIDATION_ROOT}/logs/github_actions_candidate_commit.log"
  local run_tmp="${VALIDATION_ROOT}/acceptance/github_actions_run.json.tmp"
  local jobs_tmp="${VALIDATION_ROOT}/acceptance/github_actions_jobs.json.tmp"
  {
    printf 'gh api %q > %q\n' \
      "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}" \
      "acceptance/github_actions_run.json"
    printf 'gh api %q > %q\n' \
      "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs?filter=latest&per_page=100" \
      "acceptance/github_actions_jobs.json"
  } > "${command_file}"

  if {
    echo "candidate_commit=${CANDIDATE_COMMIT}"
    echo "github_actions_run_id=${GITHUB_RUN_ID}"
    gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}" > "${run_tmp}"
    gh api \
      "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs?filter=latest&per_page=100" \
      > "${jobs_tmp}"
    mv "${run_tmp}" "${VALIDATION_ROOT}/acceptance/github_actions_run.json"
    mv "${jobs_tmp}" "${VALIDATION_ROOT}/acceptance/github_actions_jobs.json"
    echo "github_actions_metadata_ingestion=PASS"
  } > "${log_file}" 2>&1; then
    return 0
  fi

  tail -100 "${log_file}" >&2
  return 1
}

run_fresh_clone_validation() {
  local clone_root="${VALIDATION_ROOT}/work/fresh_clone"
  local command_file="${VALIDATION_ROOT}/commands/${FRESH_CLONE_CASE_ID}.sh"
  local log_file="${VALIDATION_ROOT}/logs/${FRESH_CLONE_CASE_ID}.log"
  {
    printf 'git clone --no-local --no-checkout %q %q\n' "${REPO_ROOT}" "${clone_root}"
    printf 'git -C %q checkout --detach %q\n' "${clone_root}" "${CANDIDATE_COMMIT}"
    printf 'git -C %q rev-parse HEAD\n' "${clone_root}"
    printf 'git -C %q status --porcelain\n' "${clone_root}"
    printf 'cd %q\n' "${clone_root}"
    printf '%q -m pytest -q\n' "${PYTHON_BIN}"
    printf '%q -m mito_overview.cli --list-steps\n' "${PYTHON_BIN}"
    printf 'MITO_OVERVIEW_PYTHON=%q ./tests/smoke_public_pipeline.sh\n' "${PYTHON_BIN}"
    printf 'MITO_OVERVIEW_PYTHON=%q ./tests/smoke_public_pipeline_shortread.sh\n' "${PYTHON_BIN}"
    printf 'MITO_OVERVIEW_PYTHON=%q ./tests/smoke_public_pipeline_longread_nomethyl.sh\n' \
      "${PYTHON_BIN}"
    printf 'MITO_OVERVIEW_PYTHON=%q ./tests/smoke_standalone_minimal.sh\n' "${PYTHON_BIN}"
    printf '%q -m build --no-isolation --outdir %q\n' \
      "${PYTHON_BIN}" "${clone_root}/dist"
  } > "${command_file}"

  if (
    echo "candidate_commit=${CANDIDATE_COMMIT}"
    git clone --no-local --no-checkout "${REPO_ROOT}" "${clone_root}"
    git -C "${clone_root}" checkout --detach "${CANDIDATE_COMMIT}"
    checked_out_commit="$(git -C "${clone_root}" rev-parse HEAD)"
    echo "checked_out_commit=${checked_out_commit}"
    [[ "${checked_out_commit}" == "${CANDIDATE_COMMIT}" ]]
    [[ -z "$(git -C "${clone_root}" status --porcelain)" ]]
    echo "clone_worktree_clean=true"
    cd "${clone_root}"
    "${PYTHON_BIN}" -m pytest -q
    "${PYTHON_BIN}" -m mito_overview.cli --list-steps
    MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" ./tests/smoke_public_pipeline.sh
    MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" ./tests/smoke_public_pipeline_shortread.sh
    MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" ./tests/smoke_public_pipeline_longread_nomethyl.sh
    MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" ./tests/smoke_standalone_minimal.sh
    "${PYTHON_BIN}" -m build --no-isolation --outdir "${clone_root}/dist"
    echo "fresh_clone_validation=PASS"
  ) > "${log_file}" 2>&1; then
    "${PYTHON_BIN}" - \
      "${VALIDATION_ROOT}/acceptance/fresh_clone.json" \
      "${CANDIDATE_COMMIT}" "${REPOSITORY}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
commit = sys.argv[2]
repository = sys.argv[3]
evidence = {
    "schema_version": "1.0",
    "evidence_type": "fresh_clone_validation",
    "case_id": "fresh_clone_candidate_commit",
    "verdict": "PASS",
    "repository": repository,
    "candidate_commit": commit,
    "checked_out_commit": commit,
    "detached_head": True,
    "clone_worktree_clean": True,
    "command_path": "commands/fresh_clone_candidate_commit.sh",
    "log_path": "logs/fresh_clone_candidate_commit.log",
}
path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
PY
    return 0
  fi

  record_case "${FRESH_CLONE_CASE_ID}" release_acceptance 1 1 FAIL \
    "fresh clone failed; see logs/${FRESH_CLONE_CASE_ID}.log"
  tail -100 "${log_file}" >&2
  return 1
}

append_acceptance_cases() {
  "${PYTHON_BIN}" - "${REPO_ROOT}" "${VALIDATION_ROOT}" \
    "${CANDIDATE_COMMIT}" "${REPOSITORY}" <<'PY'
import csv
import importlib.util
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
validation_root = Path(sys.argv[2])
commit = sys.argv[3]
repository = sys.argv[4]
script = repo_root / "scripts" / "build_validation_packet_v0.3.0.py"
spec = importlib.util.spec_from_file_location("validation_packet_builder", script)
if spec is None or spec.loader is None:
    raise SystemExit(f"Unable to import acceptance validator: {script}")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
rows = builder.validate_acceptance_evidence(validation_root, commit, repository)
writer = csv.DictWriter(
    sys.stdout,
    fieldnames=(
        "case_id",
        "category",
        "input_available",
        "expected_available",
        "verdict",
        "detail",
    ),
    delimiter="\t",
    lineterminator="\n",
)
writer.writerows(rows)
PY
}

{
  echo "release_version=v0.3.0"
  echo "git_commit=${CANDIDATE_COMMIT}"
  echo "git_branch=$(git -C "${REPO_ROOT}" branch --show-current)"
  echo "repository=${REPOSITORY}"
  echo "archive_doi=${ARCHIVE_DOI}"
  echo "validation_cache_root=${CACHE_ROOT}"
  echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  uname -a
  if command -v sw_vers >/dev/null 2>&1; then sw_vers; fi
  "${PYTHON_BIN}" --version
  "${PYTHON_BIN}" -m pip freeze
  for tool in samtools minimap2 bwa; do
    if command -v "${tool}" >/dev/null 2>&1; then
      echo "--- ${tool} ---"
      "${tool}" --version 2>&1 | head -n 4 || true
    fi
  done
} > "${VALIDATION_ROOT}/environment.txt" 2>&1

fetch_github_actions_evidence
run_fresh_clone_validation
append_acceptance_cases >> "${CASES_TSV}"

run_logged unit_known_answer unit "${PYTHON_BIN}" -m pytest -q
run_logged cli_step_listing cli "${PYTHON_BIN}" -m mito_overview.cli --list-steps

source "${REPO_ROOT}/scripts/lib/prepare_synthetic_toy_sample.sh"
STRICT_ROOT="${VALIDATION_ROOT}/work/strict_generic"
mkdir -p "${STRICT_ROOT}"
prepare_synthetic_toy_sample "${REPO_ROOT}" "${STRICT_ROOT}"
cat > "${STRICT_ROOT}/standalone.env" <<EOF
WORK_ROOT=${STRICT_ROOT}/runs
RUN_NAME=strict_generic
SAMPLE_ID=TOY-001
REF_FASTA=${STRICT_ROOT}/tiny_GRCh38.fa
SOURCE_ALIGN_FILE=${STRICT_ROOT}/sample/human_variation/TOY-001.input.bam
MT_CONTIG=MT
EOF
run_logged strict_generic_dry_run cli \
  "${PYTHON_BIN}" -m mito_overview.cli \
  --config "${STRICT_ROOT}/standalone.env" --dry-run --strict-files

run_logged synthetic_longread_smoke synthetic \
  env MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" "${REPO_ROOT}/tests/smoke_public_pipeline.sh"
run_logged synthetic_shortread_smoke synthetic \
  env MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" "${REPO_ROOT}/tests/smoke_public_pipeline_shortread.sh"
run_logged synthetic_longread_nomethyl_smoke synthetic \
  env MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" "${REPO_ROOT}/tests/smoke_public_pipeline_longread_nomethyl.sh"
run_logged standalone_minimal_smoke synthetic \
  env MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" "${REPO_ROOT}/tests/smoke_standalone_minimal.sh"
run_logged package_build package \
  "${PYTHON_BIN}" -m build --no-isolation --outdir "${VALIDATION_ROOT}/dist"

cp "${REPO_ROOT}/examples/synthetic_data/TOY-WGS-001/expected_copy_proxy.tsv" \
  "${VALIDATION_ROOT}/expected/TOY-WGS-001.expected_copy_proxy.tsv"
cp "${REPO_ROOT}/examples/synthetic_data/TOY-SR-001/expected_alleles.tsv" \
  "${VALIDATION_ROOT}/expected/TOY-SR-001.expected_alleles.tsv"

PUBLIC_ROOT="${VALIDATION_ROOT}/public"
run_logged public_validation_matrix public \
  env MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" \
  MITO_OVERVIEW_VALIDATION_CACHE="${CACHE_ROOT}" \
  "${REPO_ROOT}/scripts/run_public_validation_matrix_v0.3.0.sh" "${PUBLIC_ROOT}"
tail -n +2 "${PUBLIC_ROOT}/cases.tsv" >> "${CASES_TSV}"

if [[ "$(git -C "${REPO_ROOT}" rev-parse HEAD)" != "${CANDIDATE_COMMIT}" ]] || \
  [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
  echo "Release repository changed while validating candidate ${CANDIDATE_COMMIT}." >&2
  exit 1
fi

if ! "${PYTHON_BIN}" "${REPO_ROOT}/scripts/build_validation_packet_v0.3.0.py" \
  "${VALIDATION_ROOT}" "${PACKET_ROOT}" "${AUDIT_ZIP}" \
  --repo-root "${REPO_ROOT}" \
  --commit "${CANDIDATE_COMMIT}" \
  --cache-root "${CACHE_ROOT}" \
  --version "v0.3.0" \
  --repository "${REPOSITORY}" \
  --zenodo-reservation-evidence "${ZENODO_RESERVATION_EVIDENCE}" \
  --doi "${ARCHIVE_DOI}" > "${PACKET_BUILD_LOG}" 2>&1; then
  cat "${PACKET_BUILD_LOG}" >&2
  exit 1
fi
cat "${PACKET_BUILD_LOG}"

if [[ ! -s "${AUDIT_ZIP}" ]]; then
  echo "Audit ZIP was not created or is empty: ${AUDIT_ZIP}" >&2
  exit 1
fi
if [[ ! -x "${PACKET_ROOT}/verify_bundle.sh" ]]; then
  echo "Packet verifier was not created or is not executable: ${PACKET_ROOT}/verify_bundle.sh" >&2
  exit 1
fi

: > "${PACKET_VERIFY_LOG}"
echo "[packet-root-verifier] ${PACKET_ROOT}/verify_bundle.sh" >> "${PACKET_VERIFY_LOG}"
if ! "${PACKET_ROOT}/verify_bundle.sh" >> "${PACKET_VERIFY_LOG}" 2>&1; then
  cat "${PACKET_VERIFY_LOG}" >&2
  exit 1
fi

ZIP_VERIFY_ROOT="${VALIDATION_ROOT}/work/audit_zip_verify"
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/safe_extract_validation_zip.py" \
  "${AUDIT_ZIP}" "${ZIP_VERIFY_ROOT}"

echo "[audit-zip-verifier] ${AUDIT_ZIP}" >> "${PACKET_VERIFY_LOG}"
if ! bash "${ZIP_VERIFY_ROOT}/verify_bundle.sh" >> "${PACKET_VERIFY_LOG}" 2>&1; then
  cat "${PACKET_VERIFY_LOG}" >&2
  exit 1
fi

"${PYTHON_BIN}" - \
  "${ZIP_VERIFY_ROOT}/run.json" "${PACKET_VERIFY_LOG}" \
  "${ARCHIVE_DOI}" "${CANDIDATE_COMMIT}" <<'PY'
import json
import sys
from pathlib import Path

run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
log = Path(sys.argv[2]).read_text(encoding="utf-8")
doi = sys.argv[3]
commit = sys.argv[4]
if run.get("archive_doi") != doi:
    raise SystemExit("Audit ZIP DOI does not match the reserved DOI input")
if run.get("git_commit") != commit:
    raise SystemExit("Audit ZIP commit does not match the validated candidate")
expected = f"verified mito-overview v0.3.0 packet at commit {commit}"
if log.count(expected) != 2:
    raise SystemExit("Both packet-root and audit-ZIP verifier evidence are required")
PY
cat "${PACKET_VERIFY_LOG}"

AUDIT_ZIP_SHA256="$("${PYTHON_BIN}" - "${AUDIT_ZIP}" <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
with Path(sys.argv[1]).open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"
printf '%s  %s\n' "${AUDIT_ZIP_SHA256}" "${EXPECTED_AUDIT_ZIP}" > "${PACKET_SHA256}"

if [[ "$(git -C "${REPO_ROOT}" rev-parse HEAD)" != "${CANDIDATE_COMMIT}" ]] || \
  [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
  echo "Release repository changed while packaging candidate ${CANDIDATE_COMMIT}." >&2
  exit 1
fi

"${PYTHON_BIN}" - \
  "${PACKET_RECEIPT}" "${CANDIDATE_COMMIT}" "${ARCHIVE_DOI}" \
  "${AUDIT_ZIP}" "${AUDIT_ZIP_SHA256}" "${PACKET_ROOT}" \
  "${PACKET_BUILD_LOG}" "${PACKET_VERIFY_LOG}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

receipt = {
    "schema_version": "1.0",
    "evidence_type": "release_validation_archive_verification",
    "verdict": "PASS",
    "release_version": "v0.3.0",
    "git_commit": sys.argv[2],
    "archive_doi": sys.argv[3],
    "audit_zip": sys.argv[4],
    "audit_zip_sha256": sys.argv[5],
    "packet_root": sys.argv[6],
    "build_log": sys.argv[7],
    "verification_log": sys.argv[8],
    "verifier_runs": ["packet_root", "fresh_audit_zip_extraction"],
    "generated_utc": datetime.now(timezone.utc).isoformat(),
}
Path(sys.argv[1]).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
PY

echo "[release-validation] PASS"
echo "[release-validation] candidate commit: ${CANDIDATE_COMMIT}"
echo "[release-validation] audit ZIP: ${AUDIT_ZIP}"
echo "[release-validation] SHA-256: ${AUDIT_ZIP_SHA256}"
echo "[release-validation] verification receipt: ${PACKET_RECEIPT}"
