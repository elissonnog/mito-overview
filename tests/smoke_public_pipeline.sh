#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-smoke.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

source "${REPO_ROOT}/scripts/lib/prepare_synthetic_toy_sample.sh"
source "${REPO_ROOT}/scripts/lib/mock_optional_integrations.sh"
source "${REPO_ROOT}/scripts/lib/test_assertions.sh"

echo "[smoke] repo root: ${REPO_ROOT}"
echo "[smoke] workdir: ${WORKDIR}"
echo "[smoke] python: ${MITO_OVERVIEW_PYTHON:-python3}"

if [[ -n "${MITO_OVERVIEW_PYTHON:-}" ]]; then
  TOOL_BIN="$(cd "$(dirname "${MITO_OVERVIEW_PYTHON}")" && pwd)"
  export PATH="${TOOL_BIN}${PATH:+:${PATH}}"
fi
export MPLCONFIGDIR="${WORKDIR}/.mplconfig"
mkdir -p "${MPLCONFIGDIR}"
export XDG_CACHE_HOME="${WORKDIR}/.cache"
mkdir -p "${XDG_CACHE_HOME}"
HV_DIR="${WORKDIR}/sample/human_variation"
HV_NP_DIR="${WORKDIR}/sample/human_variation_NP"
RUN_ROOT="${WORKDIR}/runs"
FINAL_DIR="${WORKDIR}/final_bundle"
mkdir -p "${HV_DIR}" "${HV_NP_DIR}" "${RUN_ROOT}"

prepare_synthetic_toy_sample "${REPO_ROOT}" "${WORKDIR}"
PHYMER_ROOT="$(mock_phymer_root "${REPO_ROOT}")"
MVTOOL_FIXTURE_JSON="$(mock_mvtool_fixture_path "${REPO_ROOT}")"

echo "[smoke] phymer root: ${PHYMER_ROOT}"
echo "[smoke] mvTool fixture: ${MVTOOL_FIXTURE_JSON}"

cat > "${WORKDIR}/toy.env" <<EOF
PIPELINE_ROOT=${REPO_ROOT}
WORK_ROOT=${RUN_ROOT}
RUN_NAME=mito_TOY-001
SAMPLE_ID=TOY-001
SOURCE_SAMPLE_DIR=${WORKDIR}/sample
SOURCE_HV_DIR=${HV_DIR}
SOURCE_HV_NP_DIR=${HV_NP_DIR}
REF_FASTA=${WORKDIR}/tiny_GRCh38.fa
SOURCE_ALIGN_FILE=${HV_DIR}/TOY-001.input.bam
SOURCE_ALIGN_MODE=bam
MT_CONTIG=MT
MT_LENGTH=60
THREADS=1
SPECIES=human
CONTROL_REGION_ANNOTATION_MODE=synthetic_fixture_override
MIN_CALLABLE_DEPTH=2
MIN_ALT_ALLELE_FRACTION=0.2
HUMAN_MT_GTF=${WORKDIR}/tiny_mt.gtf
PHYMER_ROOT=${PHYMER_ROOT}
PHYMER_MIN_DEPTH=2
PHYMER_MAJOR_VAF=0.2
PHYMER_MIN_CALLABLE_FRACTION=0.30
MVTOOL_MODE=fixture
MVTOOL_FIXTURE_JSON=${MVTOOL_FIXTURE_JSON}
MSEQDR_TIMEOUT=10
FINAL_BIOINFO_DIR=${FINAL_DIR}
EOF

cd "${REPO_ROOT}"
./scripts/run_mito_pipeline.sh \
  --config "${WORKDIR}/toy.env" \
  --strict-files \
  --steps validate,stage,extract,mito_qc,heteroplasmy,deletions,copy_number,feature_annotation,cosegregation,gene_summary,numt_qc,phymer_haplogroup,identity_qc,variant_consequence,mvtool_annotation,circularity_qc,methylation_exploratory,sync_bioinfo

test -f "${FINAL_DIR}/output/report/01_mito_qc.html"
test -f "${FINAL_DIR}/output/report/02_mito_heteroplasmy.html"
test -f "${FINAL_DIR}/output/report/03_mito_deletions.html"
test -f "${FINAL_DIR}/output/report/04_mito_copy_number.html"
test -f "${FINAL_DIR}/output/report/05_mito_feature_annotation.html"
test -f "${FINAL_DIR}/output/report/06_mito_cosegregation.html"
test -f "${FINAL_DIR}/output/report/07_mito_gene_summary.html"
test -f "${FINAL_DIR}/output/report/08_mito_numt_qc.html"
test -f "${FINAL_DIR}/output/report/09_mito_identity_qc.html"
test -f "${FINAL_DIR}/output/report/10_mito_variant_consequence.html"
test -f "${FINAL_DIR}/output/report/11_mito_circularity_qc.html"
test -f "${FINAL_DIR}/output/report/12_mito_methylation_exploratory.html"
test -f "${FINAL_DIR}/output/report/13_mito_phymer_haplogroup.html"
test -f "${FINAL_DIR}/output/report/14_mito_mvtool_annotation.html"
test -f "${FINAL_DIR}/sync_manifest.tsv"
grep -q $'^status\tok$' "${FINAL_DIR}/output/summary/mito_phymer_haplogroup_summary.tsv"
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_phymer_haplogroup_summary.tsv" phymer_min_callable_fraction 0.3
grep -q "rows_returned_by_mvtool" "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv"
test "$(cat "${FINAL_DIR}/output/subset/TOY-001.MT.bed")" = $'MT\t0\t60'
assert_tsv_header_field "${FINAL_DIR}/output/summary/mito_heteroplasmy_candidates.tsv" alt_allele_fraction
assert_tsv_header_field "${FINAL_DIR}/output/summary/mito_heteroplasmy_candidates.tsv" heteroplasmy_fraction
assert_allele_table_invariants "${FINAL_DIR}/output/summary/mito_heteroplasmy_all_sites.tsv"
assert_allele_site "${FINAL_DIR}/output/summary/mito_heteroplasmy_candidates.tsv" 10 A C 10 3 0.3
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_heteroplasmy_summary.tsv" allele_min_base_quality 13
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_heteroplasmy_summary.tsv" allele_min_mapping_quality 20
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_heteroplasmy_summary.tsv" allele_min_read_mean_quality 10.0
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_heteroplasmy_summary.tsv" allele_max_depth 0
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_copy_number_summary.tsv" status not_evaluable
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_copy_number_summary.tsv" reason_code no_valid_nuclear_windows
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_copy_number_summary.tsv" mt_to_nuclear_depth_ratio ""
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_numt_qc_summary.tsv" numt_interpretation_status not_evaluable
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_numt_qc_summary.tsv" heuristic_numt_risk not_evaluable
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv" status ok
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv" mvtool_mode fixture
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv" network_request_attempted 0
assert_tsv_metric "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv" rows_returned_by_mvtool 1

echo "[smoke] public pipeline smoke test completed successfully"
