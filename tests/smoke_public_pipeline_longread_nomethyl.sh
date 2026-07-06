#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-longread-nomethyl-smoke.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

source "${REPO_ROOT}/scripts/lib/prepare_synthetic_toy_sample.sh"
source "${REPO_ROOT}/scripts/lib/mock_optional_integrations.sh"

echo "[smoke-long-nomethyl] repo root: ${REPO_ROOT}"
echo "[smoke-long-nomethyl] workdir: ${WORKDIR}"
echo "[smoke-long-nomethyl] python: ${MITO_OVERVIEW_PYTHON:-python3}"

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
rm -f \
  "${HV_DIR}/TOY-001.wf_mods.1.bedmethyl.gz" \
  "${HV_DIR}/TOY-001.wf_mods.2.bedmethyl.gz" \
  "${HV_DIR}/TOY-001.wf_mods.ungrouped.bedmethyl.gz" \
  "${HV_NP_DIR}/TOY-001.wf_mods.bedmethyl.gz"

PHYMER_ROOT="$(mock_phymer_root "${REPO_ROOT}")"
MVTOOL_API_URL="$(mock_mvtool_fixture_url "${REPO_ROOT}")"

cat > "${WORKDIR}/toy_long_nomethyl.env" <<EOF
PIPELINE_ROOT=${REPO_ROOT}
WORK_ROOT=${RUN_ROOT}
RUN_NAME=mito_TOY-001_nomethyl
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
HET_MIN_DEPTH=2
HET_MIN_VAF=0.2
HUMAN_MT_GTF=${WORKDIR}/tiny_mt.gtf
PHYMER_ROOT=${PHYMER_ROOT}
PHYMER_MIN_DEPTH=2
PHYMER_MAJOR_VAF=0.2
MVTOOL_API_URL=${MVTOOL_API_URL}
MSEQDR_TIMEOUT=10
FINAL_BIOINFO_DIR=${FINAL_DIR}
EOF

cd "${REPO_ROOT}"
./scripts/run_mito_pipeline.sh \
  --config "${WORKDIR}/toy_long_nomethyl.env" \
  --strict-files \
  --steps validate,stage,extract,mito_qc,heteroplasmy,deletions,copy_number,feature_annotation,cosegregation,gene_summary,numt_qc,phymer_haplogroup,identity_qc,variant_consequence,mvtool_annotation,circularity_qc,methylation_exploratory,sync_bioinfo

test -f "${FINAL_DIR}/output/report/12_mito_methylation_exploratory.html"
grep -q "no_mt_bedmethyl_rows_available" "${FINAL_DIR}/output/summary/mito_methylation_exploratory_summary.tsv"
grep -q "no_mt_bedmethyl_rows_available" "${FINAL_DIR}/output/summary/mito_methylation_np_vs_proxy_summary.tsv"
test -f "${FINAL_DIR}/output/summary/mito_methylation_track_rows.tsv"
test -f "${FINAL_DIR}/output/summary/mito_methylation_np_vs_proxy.tsv"
grep -q "no_mt_bedmethyl_rows_available" "${FINAL_DIR}/output/report/12_mito_methylation_exploratory.html"
grep -q $'^status\tok$' "${FINAL_DIR}/output/summary/mito_phymer_haplogroup_summary.tsv"
grep -q "rows_returned_by_mvtool" "${FINAL_DIR}/output/summary/mito_mvtool_annotation_summary.tsv"

echo "[smoke-long-nomethyl] long-read no-methylation smoke test completed successfully"
