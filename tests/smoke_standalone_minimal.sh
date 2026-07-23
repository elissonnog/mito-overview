#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-standalone.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

source "${REPO_ROOT}/scripts/lib/prepare_synthetic_toy_sample.sh"
source "${REPO_ROOT}/scripts/lib/test_assertions.sh"

if [[ -n "${MITO_OVERVIEW_PYTHON:-}" ]]; then
  TOOL_BIN="$(cd "$(dirname "${MITO_OVERVIEW_PYTHON}")" && pwd)"
  export PATH="${TOOL_BIN}${PATH:+:${PATH}}"
fi
export MPLCONFIGDIR="${WORKDIR}/.mplconfig"
export XDG_CACHE_HOME="${WORKDIR}/.cache"
mkdir -p "${MPLCONFIGDIR}" "${XDG_CACHE_HOME}"

prepare_synthetic_toy_sample "${REPO_ROOT}" "${WORKDIR}"
RUN_ROOT="${WORKDIR}/runs"
SOURCE_BAM="${WORKDIR}/sample/human_variation/TOY-001.input.bam"
cat > "${WORKDIR}/standalone.env" <<EOF
WORK_ROOT=${RUN_ROOT}
RUN_NAME=standalone_TOY-001
SAMPLE_ID=TOY-001
REF_FASTA=${WORKDIR}/tiny_GRCh38.fa
SOURCE_ALIGN_FILE=${SOURCE_BAM}
MT_CONTIG=MT
EOF

cd "${REPO_ROOT}"
"${MITO_OVERVIEW_PYTHON:-python3}" -I -m mito_overview.cli \
  --config "${WORKDIR}/standalone.env" --dry-run --strict-files >/dev/null
./scripts/run_mito_pipeline.sh --config "${WORKDIR}/standalone.env" --strict-files

FINAL_DIR="${RUN_ROOT}/standalone_TOY-001_final"
SUMMARY_DIR="${FINAL_DIR}/output/summary"
REPORT_DIR="${FINAL_DIR}/output/report"
test -f "${REPORT_DIR}/14_mito_mvtool_annotation.html"
test "$(cat "${FINAL_DIR}/output/subset/TOY-001.MT.bed")" = $'MT\t0\t60'
assert_tsv_metric "${SUMMARY_DIR}/mito_mvtool_annotation_summary.tsv" status not_configured
assert_tsv_metric "${SUMMARY_DIR}/mito_mvtool_annotation_summary.tsv" network_request_attempted 0
assert_tsv_metric "${SUMMARY_DIR}/mito_copy_number_summary.tsv" status not_evaluable
assert_tsv_metric "${SUMMARY_DIR}/mito_copy_number_summary.tsv" reason_code no_valid_nuclear_windows
assert_tsv_metric "${SUMMARY_DIR}/mito_numt_qc_summary.tsv" numt_interpretation_status not_evaluable
assert_tsv_metric "${SUMMARY_DIR}/mito_numt_qc_summary.tsv" reason_code reference_scope_mt_only
# An mt-only generic FASTA does not provide enough evidence for species inference.
assert_tsv_metric "${SUMMARY_DIR}/mito_phymer_haplogroup_summary.tsv" status not_applicable
assert_tsv_metric "${SUMMARY_DIR}/mito_methylation_exploratory_summary.tsv" status not_configured
assert_tsv_metric "${SUMMARY_DIR}/mito_identity_qc_summary.tsv" variant_comparison_status not_configured
assert_allele_table_invariants "${SUMMARY_DIR}/mito_heteroplasmy_all_sites.tsv"

SOURCE_CRAM="${WORKDIR}/TOY-001.input.cram"
samtools view -C -T "${WORKDIR}/tiny_GRCh38.fa" -o "${SOURCE_CRAM}" "${SOURCE_BAM}"
samtools index "${SOURCE_CRAM}"
cat > "${WORKDIR}/standalone_cram.env" <<EOF
WORK_ROOT=${RUN_ROOT}
RUN_NAME=standalone_TOY-001-cram
SAMPLE_ID=TOY-001
REF_FASTA=${WORKDIR}/tiny_GRCh38.fa
SOURCE_ALIGN_FILE=${SOURCE_CRAM}
MT_CONTIG=MT
EOF

"${MITO_OVERVIEW_PYTHON:-python3}" -I -m mito_overview.cli \
  --config "${WORKDIR}/standalone_cram.env" --dry-run --strict-files >/dev/null
./scripts/run_mito_pipeline.sh --config "${WORKDIR}/standalone_cram.env" --strict-files

CRAM_FINAL_DIR="${RUN_ROOT}/standalone_TOY-001-cram_final"
CRAM_SUMMARY_DIR="${CRAM_FINAL_DIR}/output/summary"
test "$(cat "${CRAM_FINAL_DIR}/output/subset/TOY-001.MT.bed")" = $'MT\t0\t60'
assert_tsv_metric "${CRAM_SUMMARY_DIR}/mito_mvtool_annotation_summary.tsv" status not_configured
assert_tsv_metric "${CRAM_SUMMARY_DIR}/mito_copy_number_summary.tsv" status not_evaluable
assert_tsv_metric "${CRAM_SUMMARY_DIR}/mito_numt_qc_summary.tsv" numt_interpretation_status not_evaluable
assert_allele_table_invariants "${CRAM_SUMMARY_DIR}/mito_heteroplasmy_all_sites.tsv"

echo "[smoke-standalone] minimal standalone BAM and CRAM workflows completed successfully"
