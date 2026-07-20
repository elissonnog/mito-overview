#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 VALIDATION_ROOT" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VALIDATION_ROOT="$1"
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"

if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
  echo "Release validation requires a clean Git worktree." >&2
  exit 1
fi
if [[ -d "${VALIDATION_ROOT}" && -n "$(find "${VALIDATION_ROOT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Validation root must be absent or empty: ${VALIDATION_ROOT}" >&2
  exit 1
fi

mkdir -p \
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

{
  echo "release_version=v0.3.0"
  echo "git_commit=$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  echo "git_branch=$(git -C "${REPO_ROOT}" branch --show-current)"
  echo "repository=https://github.com/elissonnog/mito-overview"
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
  MITO_OVERVIEW_VALIDATION_CACHE="${MITO_OVERVIEW_VALIDATION_CACHE:-/Users/elopes/Desktop/ont_results/mito_overview_validation_cache/v0.3.0}" \
  "${REPO_ROOT}/scripts/run_public_validation_matrix_v0.3.0.sh" "${PUBLIC_ROOT}"
tail -n +2 "${PUBLIC_ROOT}/cases.tsv" >> "${CASES_TSV}"

echo "[release-validation] completed at ${VALIDATION_ROOT}"
