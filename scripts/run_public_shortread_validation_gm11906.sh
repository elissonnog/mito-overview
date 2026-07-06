#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 OUTPUT_DIR" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="$1"
WORKDIR="${MITO_OVERVIEW_SHORTREAD_WORKDIR:-$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-gm11906.XXXXXX")}"
if [[ -z "${MITO_OVERVIEW_SHORTREAD_WORKDIR:-}" ]]; then
  trap 'rm -rf "${WORKDIR}"' EXIT
fi

source "${SCRIPT_DIR}/lib/mock_optional_integrations.sh"

echo "[shortread-gm11906] repo root: ${REPO_ROOT}"
echo "[shortread-gm11906] workdir: ${WORKDIR}"
echo "[shortread-gm11906] output dir: ${OUTPUT_DIR}"
echo "[shortread-gm11906] python: ${MITO_OVERVIEW_PYTHON:-python3}"

if [[ -n "${MITO_OVERVIEW_PYTHON:-}" ]]; then
  TOOL_BIN="$(cd "$(dirname "${MITO_OVERVIEW_PYTHON}")" && pwd)"
  export PATH="${TOOL_BIN}${PATH:+:${PATH}}"
fi
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"

for tool in curl bwa samtools; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required tool not found in PATH: ${tool}" >&2
    exit 1
  fi
done

export MPLCONFIGDIR="${WORKDIR}/.mplconfig"
mkdir -p "${MPLCONFIGDIR}"
export XDG_CACHE_HOME="${WORKDIR}/.cache"
mkdir -p "${XDG_CACHE_HOME}"

DATA_DIR="${WORKDIR}/downloads"
REF_DIR="${WORKDIR}/reference"
SAMPLE_DIR="${WORKDIR}/sample"
HV_DIR="${SAMPLE_DIR}/human_variation"
RUN_ROOT="${WORKDIR}/runs"
FINAL_DIR="${WORKDIR}/final_bundle"
mkdir -p "${DATA_DIR}" "${REF_DIR}" "${HV_DIR}" "${RUN_ROOT}"

download_if_missing() {
  local url="$1"
  local dest="$2"
  if [[ ! -s "${dest}" ]]; then
    echo "[shortread-gm11906] downloading ${url}"
    # Use explicit retries and timeouts so stalled public mirrors fail fast
    # instead of making the validation look frozen.
    curl \
      --fail \
      --retry "${MITO_OVERVIEW_SHORTREAD_CURL_RETRIES:-3}" \
      --retry-delay "${MITO_OVERVIEW_SHORTREAD_CURL_RETRY_DELAY:-2}" \
      --connect-timeout "${MITO_OVERVIEW_SHORTREAD_CURL_CONNECT_TIMEOUT:-20}" \
      --max-time "${MITO_OVERVIEW_SHORTREAD_CURL_MAX_TIME:-300}" \
      -L "${url}" \
      -o "${dest}"
  fi
}

copy_if_needed() {
  local src="$1"
  local dest="$2"
  if [[ "$(cd "$(dirname "${src}")" && pwd)/$(basename "${src}")" == "$(cd "$(dirname "${dest}")" && pwd)/$(basename "${dest}")" ]]; then
    return 0
  fi
  cp "${src}" "${dest}"
}

download_if_missing "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_1.fastq.gz" "${DATA_DIR}/SRR10804585_1.fastq.gz"
download_if_missing "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_2.fastq.gz" "${DATA_DIR}/SRR10804585_2.fastq.gz"
download_if_missing "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_1.fastq.gz" "${DATA_DIR}/SRR10804590_1.fastq.gz"
download_if_missing "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_2.fastq.gz" "${DATA_DIR}/SRR10804590_2.fastq.gz"
download_if_missing "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_1.fastq.gz" "${DATA_DIR}/SRR10804657_1.fastq.gz"
download_if_missing "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_2.fastq.gz" "${DATA_DIR}/SRR10804657_2.fastq.gz"

R1_FASTQ="${DATA_DIR}/GM11906_MERRF_R1.fastq.gz"
R2_FASTQ="${DATA_DIR}/GM11906_MERRF_R2.fastq.gz"
cat \
  "${DATA_DIR}/SRR10804585_1.fastq.gz" \
  "${DATA_DIR}/SRR10804590_1.fastq.gz" \
  "${DATA_DIR}/SRR10804657_1.fastq.gz" \
  > "${R1_FASTQ}"
cat \
  "${DATA_DIR}/SRR10804585_2.fastq.gz" \
  "${DATA_DIR}/SRR10804590_2.fastq.gz" \
  "${DATA_DIR}/SRR10804657_2.fastq.gz" \
  > "${R2_FASTQ}"

REF_FASTA="${REF_DIR}/NC_012920.1.fa"
cp "${REPO_ROOT}/resources/annotations/NC_012920.1.fa" "${REF_FASTA}"
samtools faidx "${REF_FASTA}"
if [[ ! -f "${REF_FASTA}.bwt" ]]; then
  bwa index "${REF_FASTA}"
fi

THREADS="${MITO_OVERVIEW_SHORTREAD_THREADS:-2}"
ALIGN_BAM="${HV_DIR}/GM11906_MERRF_shortread.mt.bam"
echo "[shortread-gm11906] aligning public GM11906 short-read data to ${REF_FASTA}"
bwa mem -t "${THREADS}" "${REF_FASTA}" "${R1_FASTQ}" "${R2_FASTQ}" \
  | samtools sort -@ "${THREADS}" -o "${ALIGN_BAM}"
samtools index -@ "${THREADS}" "${ALIGN_BAM}"
samtools flagstat "${ALIGN_BAM}" > "${WORKDIR}/GM11906_MERRF_shortread.flagstat.txt"
samtools mpileup -r NC_012920.1:8344-8344 -f "${REF_FASTA}" "${ALIGN_BAM}" > "${WORKDIR}/GM11906_MERRF_shortread.8344.mpileup"

MVTOOL_API_URL="${MVTOOL_API_URL:-$(mock_mvtool_fixture_url "${REPO_ROOT}")}"
cat > "${WORKDIR}/gm11906_shortread.env" <<EOF
PIPELINE_ROOT=${REPO_ROOT}
WORK_ROOT=${RUN_ROOT}
RUN_NAME=mito_GM11906_MERRF_shortread
SAMPLE_ID=GM11906_MERRF_shortread
SOURCE_SAMPLE_DIR=${SAMPLE_DIR}
SOURCE_HV_DIR=${HV_DIR}
REF_FASTA=${REF_FASTA}
SOURCE_ALIGN_FILE=${ALIGN_BAM}
SOURCE_ALIGN_MODE=bam
MT_CONTIG=NC_012920.1
MT_LENGTH=16569
THREADS=${THREADS}
SPECIES=human
READ_MODE=short
ASSAY_TYPE=targeted_mt
HET_MIN_DEPTH=${MITO_OVERVIEW_SHORTREAD_HET_MIN_DEPTH:-10}
HET_MIN_VAF=${MITO_OVERVIEW_SHORTREAD_HET_MIN_VAF:-0.20}
HUMAN_MT_GTF=${REPO_ROOT}/resources/annotations/human_mt_reference.gtf
MVTOOL_API_URL=${MVTOOL_API_URL}
MSEQDR_TIMEOUT=30
FINAL_BIOINFO_DIR=${FINAL_DIR}
EOF

cd "${REPO_ROOT}"
./scripts/run_mito_pipeline.sh \
  --config "${WORKDIR}/gm11906_shortread.env" \
  --strict-files \
  --steps validate,stage,extract,mito_qc,heteroplasmy,deletions,copy_number,feature_annotation,cosegregation,gene_summary,numt_qc,phymer_haplogroup,identity_qc,variant_consequence,mvtool_annotation,circularity_qc,methylation_exploratory,sync_bioinfo

rm -rf "${OUTPUT_DIR}"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
cp -R "${FINAL_DIR}/output" "${OUTPUT_DIR}"
copy_if_needed "${WORKDIR}/GM11906_MERRF_shortread.flagstat.txt" "$(dirname "${OUTPUT_DIR}")/GM11906_MERRF_shortread.flagstat.txt"
copy_if_needed "${WORKDIR}/GM11906_MERRF_shortread.8344.mpileup" "$(dirname "${OUTPUT_DIR}")/GM11906_MERRF_shortread.8344.mpileup"

if [[ -n "${MITO_OVERVIEW_SHORTREAD_ASSET_DIR:-}" ]]; then
  ASSET_DIR="${MITO_OVERVIEW_SHORTREAD_ASSET_DIR}"
  FIG_DIR="${ASSET_DIR}/figures"
  SUMMARY_DIR="${ASSET_DIR}/summary"
  mkdir -p "${FIG_DIR}" "${SUMMARY_DIR}"
  cp "${OUTPUT_DIR}/figures/mito_heteroplasmy_landscape.png" "${FIG_DIR}/"
  cp "${OUTPUT_DIR}/figures/mito_feature_annotation.png" "${FIG_DIR}/"
  cp "${OUTPUT_DIR}/figures/mito_gene_summary_overview.png" "${FIG_DIR}/"
  cp "${OUTPUT_DIR}/figures/mito_variant_consequence_classes.png" "${FIG_DIR}/"
  cp "${OUTPUT_DIR}/summary/mito_qc_summary.tsv" "${SUMMARY_DIR}/"
  cp "${OUTPUT_DIR}/summary/mito_heteroplasmy_candidates.tsv" "${SUMMARY_DIR}/"
  cp "${OUTPUT_DIR}/summary/mito_gene_summary.tsv" "${SUMMARY_DIR}/"
  cp "${OUTPUT_DIR}/summary/mito_variant_consequence_candidates.tsv" "${SUMMARY_DIR}/"
  copy_if_needed "${WORKDIR}/GM11906_MERRF_shortread.flagstat.txt" "${ASSET_DIR}/GM11906_MERRF_shortread.flagstat.txt"
  copy_if_needed "${WORKDIR}/GM11906_MERRF_shortread.8344.mpileup" "${ASSET_DIR}/GM11906_MERRF_shortread.8344.mpileup"
  "${PYTHON_BIN}" - <<'PY' "${OUTPUT_DIR}" "${ASSET_DIR}"
import sys
from pathlib import Path
import pandas as pd

output_dir = Path(sys.argv[1])
asset_dir = Path(sys.argv[2])
summary_dir = output_dir / "summary"

qc = pd.read_csv(summary_dir / "mito_qc_summary.tsv", sep="\t")
het = pd.read_csv(summary_dir / "mito_heteroplasmy_candidates.tsv", sep="\t")
gene = pd.read_csv(summary_dir / "mito_gene_summary.tsv", sep="\t")
vc = pd.read_csv(summary_dir / "mito_variant_consequence_candidates.tsv", sep="\t")

qc_map = dict(zip(qc["metric"], qc["value"]))
site_8344 = het[het["position"] == 8344].copy()
if site_8344.empty:
    site_8344 = pd.DataFrame([{"position": 8344, "status": "not_detected"}])
top_gene = gene.head(10).copy()
site_8344_vc = vc[vc["position"] == 8344].copy()

findings = pd.DataFrame(
    [
        {"metric": "sample_id", "value": "GM11906_MERRF_shortread"},
        {"metric": "read_mode", "value": "short"},
        {"metric": "assay_type", "value": "targeted_mt"},
        {"metric": "mapped_reads", "value": qc_map.get("mapped_reads", "NA")},
        {"metric": "mean_depth", "value": qc_map.get("mean_depth", "NA")},
        {"metric": "median_depth", "value": qc_map.get("median_depth", "NA")},
        {"metric": "high_query_alignment_fraction", "value": qc_map.get("high_query_alignment_fraction", "NA")},
        {"metric": "candidate_site_count", "value": len(het)},
    ]
)
findings.to_csv(asset_dir / "GM11906_MERRF_shortread_key_findings.tsv", sep="\t", index=False)
site_8344.to_csv(asset_dir / "GM11906_MERRF_shortread_site_8344.tsv", sep="\t", index=False)
site_8344_vc.to_csv(asset_dir / "GM11906_MERRF_shortread_site_8344_consequence.tsv", sep="\t", index=False)
top_gene.to_csv(asset_dir / "GM11906_MERRF_shortread_top_gene_summary.tsv", sep="\t", index=False)
PY
fi

echo "[shortread-gm11906] validation bundle created at ${OUTPUT_DIR}"
