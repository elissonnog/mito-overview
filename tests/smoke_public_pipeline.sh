#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-smoke.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

source "${REPO_ROOT}/scripts/lib/prepare_synthetic_toy_sample.sh"

echo "[smoke] repo root: ${REPO_ROOT}"
echo "[smoke] workdir: ${WORKDIR}"
echo "[smoke] python: ${MITO_OVERVIEW_PYTHON:-python3}"

if [[ -n "${MITO_OVERVIEW_PYTHON:-}" ]]; then
  TOOL_BIN="$(cd "$(dirname "${MITO_OVERVIEW_PYTHON}")" && pwd)"
  export PATH="${TOOL_BIN}${PATH:+:${PATH}}"
fi

HV_DIR="${WORKDIR}/sample/human_variation"
HV_NP_DIR="${WORKDIR}/sample/human_variation_NP"
RUN_ROOT="${WORKDIR}/runs"
FINAL_DIR="${WORKDIR}/final_bundle"
mkdir -p "${HV_DIR}" "${HV_NP_DIR}" "${RUN_ROOT}"

prepare_synthetic_toy_sample "${REPO_ROOT}" "${WORKDIR}"

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
HET_MIN_DEPTH=2
HET_MIN_VAF=0.2
HUMAN_MT_GTF=${WORKDIR}/tiny_mt.gtf
FINAL_BIOINFO_DIR=${FINAL_DIR}
EOF

cd "${REPO_ROOT}"
./scripts/run_mito_pipeline.sh \
  --config "${WORKDIR}/toy.env" \
  --strict-files \
  --steps validate,stage,extract,mito_qc,heteroplasmy,deletions,copy_number,feature_annotation,cosegregation,gene_summary,numt_qc,identity_qc,variant_consequence,circularity_qc,methylation_exploratory,sync_bioinfo

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
test -f "${FINAL_DIR}/sync_manifest.tsv"

echo "[smoke] public pipeline smoke test completed successfully"
