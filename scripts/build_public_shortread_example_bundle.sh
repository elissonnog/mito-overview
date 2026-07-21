#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 OUTPUT_DIR" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="$1"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-shortread-example.XXXXXX")"
trap 'rm -rf "${WORKDIR}"' EXIT

source "${SCRIPT_DIR}/lib/prepare_synthetic_toy_sample.sh"
source "${SCRIPT_DIR}/lib/mock_optional_integrations.sh"
source "${SCRIPT_DIR}/lib/sanitize_synthetic_subset_bam.sh"

echo "[example-short] repo root: ${REPO_ROOT}"
echo "[example-short] workdir: ${WORKDIR}"
echo "[example-short] output dir: ${OUTPUT_DIR}"
echo "[example-short] python: ${MITO_OVERVIEW_PYTHON:-python3}"

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

rm -rf "${OUTPUT_DIR}"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
cp -R "${FINAL_DIR}/output" "${OUTPUT_DIR}"
sanitize_synthetic_subset_bam "${OUTPUT_DIR}/subset/TOY-SR-001.MT.bam" "MT"

echo "[example-short] public short-read example bundle created at ${OUTPUT_DIR}"
