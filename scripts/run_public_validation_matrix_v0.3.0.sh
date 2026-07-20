#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 OUTPUT_ROOT" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_ROOT="$1"
CACHE_ROOT="${MITO_OVERVIEW_VALIDATION_CACHE:-/Users/elopes/Desktop/ont_results/mito_overview_validation_cache/v0.3.0}"
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"

if [[ -d "${OUTPUT_ROOT}" && -n "$(find "${OUTPUT_ROOT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Validation output root must be absent or empty: ${OUTPUT_ROOT}" >&2
  exit 1
fi

mkdir -p \
  "${OUTPUT_ROOT}/commands" \
  "${OUTPUT_ROOT}/logs" \
  "${OUTPUT_ROOT}/outputs" \
  "${OUTPUT_ROOT}/work" \
  "${OUTPUT_ROOT}/observed_normalized" \
  "${CACHE_ROOT}/GM11906/downloads" \
  "${CACHE_ROOT}/GM12878/downloads" \
  "${CACHE_ROOT}/GM11906/alignment" \
  "${CACHE_ROOT}/GM12878/alignment"

CASES_TSV="${OUTPUT_ROOT}/cases.tsv"
printf 'case_id\tcategory\tinput_available\texpected_available\tverdict\tdetail\n' > "${CASES_TSV}"

record_case() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" >> "${CASES_TSV}"
}

run_short_case() {
  local case_id="$1"
  local profile="$2"
  local baseq="$3"
  local mapq="$4"
  local readq="$5"
  local require_8344="$6"
  local workdir="${OUTPUT_ROOT}/work/${case_id}"
  local output_dir="${OUTPUT_ROOT}/outputs/${case_id}"
  local log="${OUTPUT_ROOT}/logs/${case_id}.log"
  local command_file="${OUTPUT_ROOT}/commands/${case_id}.sh"
  mkdir -p "${workdir}"
  cat > "${command_file}" <<EOF
MITO_OVERVIEW_SHORTREAD_WORKDIR=${workdir} \\
MITO_OVERVIEW_SHORTREAD_DATA_DIR=${CACHE_ROOT}/GM11906/downloads \\
MITO_OVERVIEW_SHORTREAD_ALIGN_BAM=${CACHE_ROOT}/GM11906/alignment/GM11906_MERRF_shortread.mt.bam \\
MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_BASE_QUALITY=${baseq} \\
MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_MAPPING_QUALITY=${mapq} \\
MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_READ_MEAN_QUALITY=${readq} \\
MITO_OVERVIEW_SHORTREAD_REQUIRE_8344=${require_8344} \\
MITO_OVERVIEW_PUBLIC_OUTPUT_MODE=evidence \\
${REPO_ROOT}/scripts/run_public_shortread_validation_gm11906.sh ${output_dir}
EOF
  if env \
    MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" \
    MITO_OVERVIEW_SHORTREAD_WORKDIR="${workdir}" \
    MITO_OVERVIEW_SHORTREAD_DATA_DIR="${CACHE_ROOT}/GM11906/downloads" \
    MITO_OVERVIEW_SHORTREAD_ALIGN_BAM="${CACHE_ROOT}/GM11906/alignment/GM11906_MERRF_shortread.mt.bam" \
    MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_BASE_QUALITY="${baseq}" \
    MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_MAPPING_QUALITY="${mapq}" \
    MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_READ_MEAN_QUALITY="${readq}" \
    MITO_OVERVIEW_SHORTREAD_REQUIRE_8344="${require_8344}" \
    MITO_OVERVIEW_PUBLIC_OUTPUT_MODE=evidence \
    "${REPO_ROOT}/scripts/run_public_shortread_validation_gm11906.sh" "${output_dir}" \
    >"${log}" 2>&1; then
    rm -rf "${workdir}"
    record_case "${case_id}" "public_${profile}" 1 1 PASS "GM11906 short-read workflow completed"
  else
    record_case "${case_id}" "public_${profile}" 1 1 FAIL "see logs/${case_id}.log"
    tail -80 "${log}" >&2
    return 1
  fi
}

run_long_case() {
  local case_id="$1"
  local profile="$2"
  local baseq="$3"
  local mapq="$4"
  local readq="$5"
  local workdir="${OUTPUT_ROOT}/work/${case_id}"
  local output_dir="${OUTPUT_ROOT}/outputs/${case_id}"
  local log="${OUTPUT_ROOT}/logs/${case_id}.log"
  local command_file="${OUTPUT_ROOT}/commands/${case_id}.sh"
  mkdir -p "${workdir}"
  cat > "${command_file}" <<EOF
MITO_OVERVIEW_LONGREAD_WORKDIR=${workdir} \\
MITO_OVERVIEW_LONGREAD_DATA_DIR=${CACHE_ROOT}/GM12878/downloads \\
MITO_OVERVIEW_LONGREAD_FASTQ_GZ=${CACHE_ROOT}/GM12878/downloads/SRR18110025.fastq.gz \\
MITO_OVERVIEW_LONGREAD_ALIGN_BAM=${CACHE_ROOT}/GM12878/alignment/GM12878_ONT_longread.mt.bam \\
MITO_OVERVIEW_LONGREAD_ALLELE_MIN_BASE_QUALITY=${baseq} \\
MITO_OVERVIEW_LONGREAD_ALLELE_MIN_MAPPING_QUALITY=${mapq} \\
MITO_OVERVIEW_LONGREAD_ALLELE_MIN_READ_MEAN_QUALITY=${readq} \\
MITO_OVERVIEW_PUBLIC_OUTPUT_MODE=evidence \\
${REPO_ROOT}/scripts/run_public_longread_validation_gm12878.sh ${output_dir}
EOF
  if env \
    MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" \
    MITO_OVERVIEW_LONGREAD_WORKDIR="${workdir}" \
    MITO_OVERVIEW_LONGREAD_DATA_DIR="${CACHE_ROOT}/GM12878/downloads" \
    MITO_OVERVIEW_LONGREAD_FASTQ_GZ="${CACHE_ROOT}/GM12878/downloads/SRR18110025.fastq.gz" \
    MITO_OVERVIEW_LONGREAD_ALIGN_BAM="${CACHE_ROOT}/GM12878/alignment/GM12878_ONT_longread.mt.bam" \
    MITO_OVERVIEW_LONGREAD_ALLELE_MIN_BASE_QUALITY="${baseq}" \
    MITO_OVERVIEW_LONGREAD_ALLELE_MIN_MAPPING_QUALITY="${mapq}" \
    MITO_OVERVIEW_LONGREAD_ALLELE_MIN_READ_MEAN_QUALITY="${readq}" \
    MITO_OVERVIEW_PUBLIC_OUTPUT_MODE=evidence \
    "${REPO_ROOT}/scripts/run_public_longread_validation_gm12878.sh" "${output_dir}" \
    >"${log}" 2>&1; then
    rm -rf "${workdir}"
    record_case "${case_id}" "public_${profile}" 1 1 PASS "GM12878 long-read workflow completed"
  else
    record_case "${case_id}" "public_${profile}" 1 1 FAIL "see logs/${case_id}.log"
    tail -80 "${log}" >&2
    return 1
  fi
}

echo "[validation-matrix] GM11906 default repeat 1"
run_short_case gm11906_default_run1 default 13 20 10 1
echo "[validation-matrix] GM11906 default repeat 2"
run_short_case gm11906_default_run2 default 13 20 10 1
echo "[validation-matrix] GM11906 lenient and strict profiles"
run_short_case gm11906_lenient lenient 0 0 0 0
run_short_case gm11906_strict strict 20 30 15 0

echo "[validation-matrix] GM12878 default repeat 1"
run_long_case gm12878_default_run1 default 13 20 10
echo "[validation-matrix] GM12878 default repeat 2"
run_long_case gm12878_default_run2 default 13 20 10
echo "[validation-matrix] GM12878 lenient and strict profiles"
run_long_case gm12878_lenient lenient 0 0 0
run_long_case gm12878_strict strict 20 30 15

for dataset in gm11906 gm12878; do
  for repeat in run1 run2; do
    "${PYTHON_BIN}" "${REPO_ROOT}/scripts/normalize_validation_outputs.py" \
      "${OUTPUT_ROOT}/outputs/${dataset}_default_${repeat}/summary" \
      "${OUTPUT_ROOT}/observed_normalized/${dataset}_default_${repeat}"
  done
  if diff -ru \
    "${OUTPUT_ROOT}/observed_normalized/${dataset}_default_run1" \
    "${OUTPUT_ROOT}/observed_normalized/${dataset}_default_run2" \
    >"${OUTPUT_ROOT}/logs/${dataset}_repeatability.diff"; then
    record_case "${dataset}_repeatability" repeatability 1 1 PASS "normalized TSVs matched"
  else
    record_case "${dataset}_repeatability" repeatability 1 1 FAIL "normalized TSVs differed"
    cat "${OUTPUT_ROOT}/logs/${dataset}_repeatability.diff" >&2
    exit 1
  fi
  for repeat in run1 run2; do
    "${PYTHON_BIN}" "${REPO_ROOT}/scripts/inventory_visual_artifacts.py" \
      "${OUTPUT_ROOT}/outputs/${dataset}_default_${repeat}" \
      "${OUTPUT_ROOT}/observed_normalized/${dataset}_default_${repeat}/visual_artifact_inventory.tsv" \
      "${OUTPUT_ROOT}/logs/${dataset}_visual_structure_${repeat}.tsv"
  done
  if diff -u \
    "${OUTPUT_ROOT}/logs/${dataset}_visual_structure_run1.tsv" \
    "${OUTPUT_ROOT}/logs/${dataset}_visual_structure_run2.tsv" \
    >"${OUTPUT_ROOT}/logs/${dataset}_visual_structure.diff"; then
    record_case "${dataset}_visual_integrity" visual_integrity 1 1 PASS \
      "HTML/PNG artifacts were readable and structurally consistent across repeats"
  else
    record_case "${dataset}_visual_integrity" visual_integrity 1 1 FAIL \
      "HTML/PNG artifact structures differed across repeats"
    cat "${OUTPUT_ROOT}/logs/${dataset}_visual_structure.diff" >&2
    exit 1
  fi
done

"${PYTHON_BIN}" "${REPO_ROOT}/scripts/summarize_filter_profiles.py" \
  --output "${OUTPUT_ROOT}/filter_profile_results.tsv" \
  "gm11906_default=GM11906:default:${OUTPUT_ROOT}/outputs/gm11906_default_run1" \
  "gm11906_lenient=GM11906:lenient:${OUTPUT_ROOT}/outputs/gm11906_lenient" \
  "gm11906_strict=GM11906:strict:${OUTPUT_ROOT}/outputs/gm11906_strict" \
  "gm12878_default=GM12878:default:${OUTPUT_ROOT}/outputs/gm12878_default_run1" \
  "gm12878_lenient=GM12878:lenient:${OUTPUT_ROOT}/outputs/gm12878_lenient" \
  "gm12878_strict=GM12878:strict:${OUTPUT_ROOT}/outputs/gm12878_strict"
record_case filter_profiles descriptive_sensitivity 1 1 PASS "0/0/0, 13/20/10, and 20/30/15 profiles summarized"

find "${CACHE_ROOT}" -type f \
  ! -name inputs.sha256 \
  ! -name cache_provenance.tsv \
  -print \
  | LC_ALL=C sort \
  | while IFS= read -r input_file; do shasum -a 256 "${input_file}"; done \
  > "${OUTPUT_ROOT}/inputs.sha256"

echo "[validation-matrix] completed at ${OUTPUT_ROOT}"
