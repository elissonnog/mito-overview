#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 OUTPUT_DIR" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="$1"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-example.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

source "${SCRIPT_DIR}/lib/prepare_synthetic_toy_sample.sh"

echo "[example] repo root: ${REPO_ROOT}"
echo "[example] workdir: ${WORKDIR}"
echo "[example] output dir: ${OUTPUT_DIR}"
echo "[example] python: ${MITO_OVERVIEW_PYTHON:-python3}"

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

rm -rf "${OUTPUT_DIR}"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
cp -R "${FINAL_DIR}/output" "${OUTPUT_DIR}"

echo "[example] public example bundle created at ${OUTPUT_DIR}"
