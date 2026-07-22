#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-shortread-smoke.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

source "${REPO_ROOT}/scripts/lib/prepare_synthetic_toy_sample.sh"
source "${REPO_ROOT}/scripts/lib/mock_optional_integrations.sh"
source "${REPO_ROOT}/scripts/lib/test_assertions.sh"

echo "[smoke-short] repo root: ${REPO_ROOT}"
echo "[smoke-short] workdir: ${WORKDIR}"
echo "[smoke-short] python: ${MITO_OVERVIEW_PYTHON:-python3}"

if [[ -n "${MITO_OVERVIEW_PYTHON:-}" ]]; then
  TOOL_BIN="$(cd "$(dirname "${MITO_OVERVIEW_PYTHON}")" && pwd)"
  export PATH="${TOOL_BIN}${PATH:+:${PATH}}"
fi
export MPLCONFIGDIR="${WORKDIR}/.mplconfig"
mkdir -p "${MPLCONFIGDIR}"
export XDG_CACHE_HOME="${WORKDIR}/.cache"
mkdir -p "${XDG_CACHE_HOME}"
HV_DIR="${WORKDIR}/sample/human_variation"
RUN_ROOT="${WORKDIR}/runs"
FINAL_DIR="${WORKDIR}/final_bundle"
mkdir -p "${HV_DIR}" "${RUN_ROOT}"

prepare_synthetic_shortread_toy_sample "${REPO_ROOT}" "${WORKDIR}"
PHYMER_ROOT="$(mock_phymer_root "${REPO_ROOT}")"
MVTOOL_FIXTURE_JSON="$(mock_mvtool_fixture_path "${REPO_ROOT}")"

cat > "${WORKDIR}/toy_short.env" <<EOF
PIPELINE_ROOT=${REPO_ROOT}
WORK_ROOT=${RUN_ROOT}
RUN_NAME=mito_TOY-SR-001
SAMPLE_ID=TOY-SR-001
SOURCE_SAMPLE_DIR=${WORKDIR}/sample
SOURCE_HV_DIR=${HV_DIR}
REF_FASTA=${WORKDIR}/tiny_GRCh38.fa
SOURCE_ALIGN_FILE=${HV_DIR}/TOY-SR-001.input.bam
SOURCE_ALIGN_MODE=bam
MT_CONTIG=MT
MT_LENGTH=60
THREADS=1
SPECIES=human
READ_MODE=short
ASSAY_TYPE=targeted_mt
CONTROL_REGION_ANNOTATION_MODE=synthetic_fixture_override
MIN_CALLABLE_DEPTH=2
MIN_ALT_ALLELE_FRACTION=0.2
HUMAN_MT_GTF=${WORKDIR}/tiny_mt.gtf
PHYMER_ROOT=${PHYMER_ROOT}
PHYMER_MIN_DEPTH=2
PHYMER_MAJOR_VAF=0.2
MVTOOL_MODE=fixture
MVTOOL_FIXTURE_JSON=${MVTOOL_FIXTURE_JSON}
MSEQDR_TIMEOUT=10
FINAL_BIOINFO_DIR=${FINAL_DIR}
EOF

cd "${REPO_ROOT}"
./scripts/run_mito_pipeline.sh \
  --config "${WORKDIR}/toy_short.env" \
  --strict-files \
  --steps validate,stage,extract,mito_qc,heteroplasmy,deletions,copy_number,feature_annotation,cosegregation,gene_summary,numt_qc,phymer_haplogroup,identity_qc,variant_consequence,mvtool_annotation,circularity_qc,methylation_exploratory,sync_bioinfo

for page in \
  01_mito_qc.html \
  02_mito_heteroplasmy.html \
  03_mito_deletions.html \
  04_mito_copy_number.html \
  05_mito_feature_annotation.html \
  06_mito_cosegregation.html \
  07_mito_gene_summary.html \
  08_mito_numt_qc.html \
  09_mito_identity_qc.html \
  10_mito_variant_consequence.html \
  11_mito_circularity_qc.html \
  12_mito_methylation_exploratory.html \
  13_mito_phymer_haplogroup.html \
  14_mito_mvtool_annotation.html
do
  test -f "${FINAL_DIR}/output/report/${page}"
done

grep -q "not_applicable" "${FINAL_DIR}/output/summary/mito_deletion_summary.tsv"
grep -q "not_applicable" "${FINAL_DIR}/output/summary/mito_copy_number_summary.tsv"
grep -q "not_applicable" "${FINAL_DIR}/output/summary/mito_cosegregation_summary.tsv"
grep -q "not_applicable" "${FINAL_DIR}/output/summary/mito_numt_qc_summary.tsv"
grep -q "not_applicable" "${FINAL_DIR}/output/summary/mito_identity_qc_summary.tsv"
grep -q "not_applicable" "${FINAL_DIR}/output/summary/mito_phymer_haplogroup_summary.tsv"
grep -q "not_applicable" "${FINAL_DIR}/output/summary/mito_circularity_qc_summary.tsv"
grep -q "not_applicable" "${FINAL_DIR}/output/summary/mito_methylation_exploratory_summary.tsv"
grep -q "not_applicable" "${FINAL_DIR}/output/summary/mito_methylation_np_vs_proxy_summary.tsv"
grep -q "not_applicable" "${FINAL_DIR}/output/report/03_mito_deletions.html"
grep -q "not_applicable" "${FINAL_DIR}/output/report/12_mito_methylation_exploratory.html"
grep -q "rows_returned_by_mvtool" "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv"
test "$(cat "${FINAL_DIR}/output/subset/TOY-SR-001.MT.bed")" = $'MT\t0\t60'
assert_allele_table_invariants "${FINAL_DIR}/output/summary/mito_heteroplasmy_all_sites.tsv"
assert_allele_site "${FINAL_DIR}/output/summary/mito_heteroplasmy_candidates.tsv" 10 A C 10 3 0.3
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_copy_number_summary.tsv" status not_applicable
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv" status ok
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv" mvtool_mode fixture
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv" network_request_attempted 0
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv" rows_returned_by_mvtool 1

test -f "${FINAL_DIR}/sync_manifest.tsv"

echo "[smoke-short] public short-read pipeline smoke test completed successfully"
