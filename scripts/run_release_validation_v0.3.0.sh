#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: MITO_OVERVIEW_GITHUB_RUN_ID=RUN_ID $0 VALIDATION_ROOT" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VALIDATION_ROOT="$1"
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"
REPOSITORY="https://github.com/elissonnog/mito-overview"
GITHUB_REPOSITORY="elissonnog/mito-overview"
GITHUB_RUN_ID="${MITO_OVERVIEW_GITHUB_RUN_ID:-}"
FRESH_CLONE_CASE_ID="fresh_clone_candidate_commit"
CANDIDATE_COMMIT="$(git -C "${REPO_ROOT}" rev-parse HEAD)"

if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
  echo "Release validation requires a clean Git worktree." >&2
  exit 1
fi
if [[ -d "${VALIDATION_ROOT}" && -n "$(find "${VALIDATION_ROOT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Validation root must be absent or empty: ${VALIDATION_ROOT}" >&2
  exit 1
fi
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
  MITO_OVERVIEW_VALIDATION_CACHE="${MITO_OVERVIEW_VALIDATION_CACHE:-${XDG_CACHE_HOME:-${HOME}/.cache}/mito-overview/validation/v0.3.0}" \
  "${REPO_ROOT}/scripts/run_public_validation_matrix_v0.3.0.sh" "${PUBLIC_ROOT}"
tail -n +2 "${PUBLIC_ROOT}/cases.tsv" >> "${CASES_TSV}"

if [[ "$(git -C "${REPO_ROOT}" rev-parse HEAD)" != "${CANDIDATE_COMMIT}" ]] || \
  [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
  echo "Release repository changed while validating candidate ${CANDIDATE_COMMIT}." >&2
  exit 1
fi

echo "[release-validation] completed at ${VALIDATION_ROOT}"
