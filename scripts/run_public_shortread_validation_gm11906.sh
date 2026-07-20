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
source "${SCRIPT_DIR}/lib/test_assertions.sh"

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

DATA_DIR="${MITO_OVERVIEW_SHORTREAD_DATA_DIR:-${WORKDIR}/downloads}"
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

file_md5() {
  local path="$1"
  if command -v md5sum >/dev/null 2>&1; then
    md5sum "${path}" | awk '{print $1}'
  else
    md5 -q "${path}"
  fi
}

assert_md5() {
  local path="$1"
  local expected="$2"
  local observed
  observed="$(file_md5 "${path}")"
  if [[ "${observed}" != "${expected}" ]]; then
    echo "ENA MD5 mismatch for ${path}: expected ${expected}, observed ${observed}" >&2
    exit 1
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
assert_md5 "${DATA_DIR}/SRR10804585_1.fastq.gz" 3f5ea26a5791894071462d4970bc9e5a
assert_md5 "${DATA_DIR}/SRR10804585_2.fastq.gz" c5b408425612f63b33cefd2d49c157d1
assert_md5 "${DATA_DIR}/SRR10804590_1.fastq.gz" e8b5132a8be8c179bfc6dbc0f3e1bee9
assert_md5 "${DATA_DIR}/SRR10804590_2.fastq.gz" 4d6977526136739de2d90baa8d45b484
assert_md5 "${DATA_DIR}/SRR10804657_1.fastq.gz" 8f082f73cb64bf56ea8a053fe80eeb06
assert_md5 "${DATA_DIR}/SRR10804657_2.fastq.gz" 62b7d1b2294a580c021f5fa1f52609be

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
ALIGN_BAM="${MITO_OVERVIEW_SHORTREAD_ALIGN_BAM:-${HV_DIR}/GM11906_MERRF_shortread.mt.bam}"
ALIGN_PROVENANCE="${MITO_OVERVIEW_SHORTREAD_ALIGN_PROVENANCE:-${ALIGN_BAM}.provenance.json}"
ALIGN_DERIVATION_ID="bwa-mem-samtools-sort-v1"
PROVENANCE_INPUTS=(
  --input "SRR10804585_R1=${DATA_DIR}/SRR10804585_1.fastq.gz"
  --input "SRR10804585_R2=${DATA_DIR}/SRR10804585_2.fastq.gz"
  --input "SRR10804590_R1=${DATA_DIR}/SRR10804590_1.fastq.gz"
  --input "SRR10804590_R2=${DATA_DIR}/SRR10804590_2.fastq.gz"
  --input "SRR10804657_R1=${DATA_DIR}/SRR10804657_1.fastq.gz"
  --input "SRR10804657_R2=${DATA_DIR}/SRR10804657_2.fastq.gz"
  --input "combined_R1=${R1_FASTQ}"
  --input "combined_R2=${R2_FASTQ}"
)

alignment_component_count=0
for component in "${ALIGN_BAM}" "${ALIGN_BAM}.bai" "${ALIGN_PROVENANCE}"; do
  [[ -s "${component}" ]] && alignment_component_count=$((alignment_component_count + 1))
done
if [[ "${alignment_component_count}" -eq 3 ]]; then
  "${PYTHON_BIN}" "${REPO_ROOT}/scripts/public_alignment_provenance.py" verify \
    --manifest "${ALIGN_PROVENANCE}" \
    --dataset GM11906_MERRF_reduced_shortread \
    --alignment "${ALIGN_BAM}" \
    --reference "${REF_FASTA}" \
    --derivation-id "${ALIGN_DERIVATION_ID}" \
    "${PROVENANCE_INPUTS[@]}"
  echo "[shortread-gm11906] reusing provenance-verified BAM ${ALIGN_BAM}"
elif [[ "${alignment_component_count}" -eq 0 ]]; then
  echo "[shortread-gm11906] aligning public GM11906 short-read data to ${REF_FASTA}"
  mkdir -p "$(dirname "${ALIGN_BAM}")"
  bwa mem -t "${THREADS}" "${REF_FASTA}" "${R1_FASTQ}" "${R2_FASTQ}" \
    | samtools sort -@ "${THREADS}" -o "${ALIGN_BAM}"
  samtools index -@ "${THREADS}" "${ALIGN_BAM}"
  "${PYTHON_BIN}" "${REPO_ROOT}/scripts/public_alignment_provenance.py" record \
    --manifest "${ALIGN_PROVENANCE}" \
    --dataset GM11906_MERRF_reduced_shortread \
    --alignment "${ALIGN_BAM}" \
    --reference "${REF_FASTA}" \
    --derivation-id "${ALIGN_DERIVATION_ID}" \
    --command-template 'bwa mem -t {threads} {reference_fasta} {combined_r1} {combined_r2} | samtools sort -@ {threads} -o {alignment_bam}' \
    --parameter "threads=${THREADS}" \
    --tool bwa \
    --tool samtools \
    "${PROVENANCE_INPUTS[@]}"
else
  echo "Incomplete cached GM11906 alignment provenance. Refusing unsafe reuse:" >&2
  echo "  BAM: ${ALIGN_BAM}" >&2
  echo "  BAI: ${ALIGN_BAM}.bai" >&2
  echo "  manifest: ${ALIGN_PROVENANCE}" >&2
  exit 1
fi
samtools flagstat "${ALIGN_BAM}" > "${WORKDIR}/GM11906_MERRF_shortread.flagstat.txt"
samtools mpileup -r NC_012920.1:8344-8344 -f "${REF_FASTA}" "${ALIGN_BAM}" > "${WORKDIR}/GM11906_MERRF_shortread.8344.mpileup"

MVTOOL_MODE="${MITO_OVERVIEW_SHORTREAD_MVTOOL_MODE:-disabled}"
MVTOOL_FIXTURE_JSON="${MITO_OVERVIEW_SHORTREAD_MVTOOL_FIXTURE_JSON:-}"
if [[ "${MVTOOL_MODE}" == "fixture" && -z "${MVTOOL_FIXTURE_JSON}" ]]; then
  MVTOOL_FIXTURE_JSON="$(mock_mvtool_fixture_path "${REPO_ROOT}")"
fi
MIN_CALLABLE_DEPTH="${MITO_OVERVIEW_SHORTREAD_MIN_CALLABLE_DEPTH:-${MITO_OVERVIEW_SHORTREAD_HET_MIN_DEPTH:-10}}"
MIN_ALT_ALLELE_FRACTION="${MITO_OVERVIEW_SHORTREAD_MIN_ALT_ALLELE_FRACTION:-${MITO_OVERVIEW_SHORTREAD_HET_MIN_VAF:-0.20}}"
ALLELE_MIN_BASE_QUALITY="${MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_BASE_QUALITY:-13}"
ALLELE_MIN_MAPPING_QUALITY="${MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_MAPPING_QUALITY:-20}"
ALLELE_MIN_READ_MEAN_QUALITY="${MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_READ_MEAN_QUALITY:-10}"
cat > "${WORKDIR}/gm11906_shortread.env" <<EOF
WORK_ROOT=${RUN_ROOT}
RUN_NAME=mito_GM11906_MERRF_shortread
SAMPLE_ID=GM11906_MERRF_shortread
REF_FASTA=${REF_FASTA}
SOURCE_ALIGN_FILE=${ALIGN_BAM}
MT_CONTIG=NC_012920.1
THREADS=${THREADS}
SPECIES=human
READ_MODE=short
ASSAY_TYPE=targeted_mt
REFERENCE_SCOPE=auto
MIN_CALLABLE_DEPTH=${MIN_CALLABLE_DEPTH}
MIN_ALT_ALLELE_FRACTION=${MIN_ALT_ALLELE_FRACTION}
ALLELE_MIN_BASE_QUALITY=${ALLELE_MIN_BASE_QUALITY}
ALLELE_MIN_MAPPING_QUALITY=${ALLELE_MIN_MAPPING_QUALITY}
ALLELE_MIN_READ_MEAN_QUALITY=${ALLELE_MIN_READ_MEAN_QUALITY}
ALLELE_MAX_DEPTH=0
ALLELE_EXCLUDE_FLAGS=3844
ALLELE_IGNORE_OVERLAPS=1
HUMAN_MT_GTF=${REPO_ROOT}/resources/annotations/human_mt_reference.gtf
MVTOOL_MODE=${MVTOOL_MODE}
MVTOOL_FIXTURE_JSON=${MVTOOL_FIXTURE_JSON}
MSEQDR_TIMEOUT=30
FINAL_BIOINFO_DIR=${FINAL_DIR}
EOF

cd "${REPO_ROOT}"
./scripts/run_mito_pipeline.sh \
  --config "${WORKDIR}/gm11906_shortread.env" \
  --strict-files \
  --steps validate,stage,extract,mito_qc,heteroplasmy,deletions,copy_number,feature_annotation,cosegregation,gene_summary,numt_qc,phymer_haplogroup,identity_qc,variant_consequence,mvtool_annotation,circularity_qc,methylation_exploratory,sync_bioinfo

SUMMARY_DIR="${FINAL_DIR}/output/summary"
assert_allele_table_invariants "${SUMMARY_DIR}/mito_heteroplasmy_all_sites.tsv"
assert_tsv_metric "${SUMMARY_DIR}/mito_copy_number_summary.tsv" status not_applicable
assert_tsv_metric "${SUMMARY_DIR}/mito_numt_qc_summary.tsv" status not_applicable
assert_tsv_metric "${SUMMARY_DIR}/mito_mvtool_annotation_summary.tsv" status \
  "$([[ "${MVTOOL_MODE}" == "disabled" ]] && printf not_configured || printf ok)"
if [[ "${MITO_OVERVIEW_SHORTREAD_REQUIRE_8344:-1}" == "1" ]]; then
  "${PYTHON_BIN}" - "${SUMMARY_DIR}/mito_heteroplasmy_candidates.tsv" <<'PY'
import sys

import pandas as pd

path = sys.argv[1]
table = pd.read_csv(path, sep="\t")
required = {
    "position",
    "ref_base",
    "alt_base",
    "callable_depth",
    "alt_count",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "alt_forward",
    "alt_reverse",
}
missing = sorted(required - set(table.columns))
if missing:
    raise SystemExit(f"GM11906 release gate failed: candidate table missing {missing}")
hit = table[
    (table["position"] == 8344)
    & (table["ref_base"].astype(str).str.upper() == "A")
    & (table["alt_base"].astype(str).str.upper() == "G")
]
if len(hit) != 1:
    raise SystemExit(
        "GM11906 release gate failed: expected exactly one m.8344A>G candidate, "
        f"observed {len(hit)}"
    )
row = hit.iloc[0]
if int(row["alt_count"]) != int(row["alt_forward"]) + int(row["alt_reverse"]):
    raise SystemExit("GM11906 release gate failed: strand-count invariant")
if abs(float(row["alt_allele_fraction"]) - float(row["heteroplasmy_fraction"])) > 1e-9:
    raise SystemExit("GM11906 release gate failed: compatibility alias mismatch")
print(
    "[shortread-gm11906] release gate m.8344A>G "
    f"depth={int(row['callable_depth'])} alt_count={int(row['alt_count'])} "
    f"alt_fraction={float(row['alt_allele_fraction']):.6f}"
)
PY
fi

rm -rf "${OUTPUT_DIR}"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
OUTPUT_MODE="${MITO_OVERVIEW_PUBLIC_OUTPUT_MODE:-full}"
case "${OUTPUT_MODE}" in
  full)
    cp -R "${FINAL_DIR}/output" "${OUTPUT_DIR}"
    ;;
  evidence)
    mkdir -p "${OUTPUT_DIR}"
    for component in summary report figures methylation; do
      if [[ -d "${FINAL_DIR}/output/${component}" ]]; then
        cp -R "${FINAL_DIR}/output/${component}" "${OUTPUT_DIR}/"
      fi
    done
    ;;
  *)
    echo "Unsupported MITO_OVERVIEW_PUBLIC_OUTPUT_MODE: ${OUTPUT_MODE}" >&2
    exit 1
    ;;
esac
mkdir -p "${OUTPUT_DIR}/provenance"
copy_if_needed "${ALIGN_PROVENANCE}" "${OUTPUT_DIR}/provenance/GM11906_MERRF_shortread.alignment.provenance.json"
copy_if_needed "${WORKDIR}/GM11906_MERRF_shortread.flagstat.txt" "$(dirname "${OUTPUT_DIR}")/GM11906_MERRF_shortread.flagstat.txt"
copy_if_needed "${WORKDIR}/GM11906_MERRF_shortread.8344.mpileup" "$(dirname "${OUTPUT_DIR}")/GM11906_MERRF_shortread.8344.mpileup"

if [[ -n "${MITO_OVERVIEW_SHORTREAD_ASSET_DIR:-}" ]]; then
  ASSET_DIR="${MITO_OVERVIEW_SHORTREAD_ASSET_DIR}"
  FIG_DIR="${ASSET_DIR}/figures"
  SUMMARY_DIR="${ASSET_DIR}/summary"
  PROVENANCE_DIR="${ASSET_DIR}/provenance"
  mkdir -p "${FIG_DIR}" "${SUMMARY_DIR}" "${PROVENANCE_DIR}"
  cp "${OUTPUT_DIR}/figures/mito_heteroplasmy_landscape.png" "${FIG_DIR}/"
  cp "${OUTPUT_DIR}/figures/mito_feature_annotation.png" "${FIG_DIR}/"
  cp "${OUTPUT_DIR}/figures/mito_gene_summary_overview.png" "${FIG_DIR}/"
  cp "${OUTPUT_DIR}/figures/mito_variant_consequence_classes.png" "${FIG_DIR}/"
  "${PYTHON_BIN}" "${REPO_ROOT}/scripts/build_report_montage.py" \
    --profile short \
    --source-dir "${OUTPUT_DIR}/figures" \
    --output "${FIG_DIR}/GM11906_MERRF_shortread_montage.png" \
    --title "GM11906 public short-read workflow proof-of-principle"
  cp "${OUTPUT_DIR}/summary/mito_qc_summary.tsv" "${SUMMARY_DIR}/"
  cp "${OUTPUT_DIR}/summary/mito_heteroplasmy_candidates.tsv" "${SUMMARY_DIR}/"
  cp "${OUTPUT_DIR}/summary/mito_gene_summary.tsv" "${SUMMARY_DIR}/"
  cp "${OUTPUT_DIR}/summary/mito_variant_consequence_candidates.tsv" "${SUMMARY_DIR}/"
  copy_if_needed "${WORKDIR}/GM11906_MERRF_shortread.flagstat.txt" "${ASSET_DIR}/GM11906_MERRF_shortread.flagstat.txt"
  copy_if_needed "${WORKDIR}/GM11906_MERRF_shortread.8344.mpileup" "${ASSET_DIR}/GM11906_MERRF_shortread.8344.mpileup"
  copy_if_needed "${ALIGN_PROVENANCE}" \
    "${PROVENANCE_DIR}/GM11906_MERRF_shortread.alignment.provenance.json"
  "${PYTHON_BIN}" - <<'PY' "${OUTPUT_DIR}" "${ASSET_DIR}"
import sys
from pathlib import Path
import pandas as pd

output_dir = Path(sys.argv[1])
asset_dir = Path(sys.argv[2])
summary_dir = output_dir / "summary"

qc = pd.read_csv(summary_dir / "mito_qc_summary.tsv", sep="\t")
het = pd.read_csv(summary_dir / "mito_heteroplasmy_candidates.tsv", sep="\t")
het_summary = pd.read_csv(summary_dir / "mito_heteroplasmy_summary.tsv", sep="\t")
gene = pd.read_csv(summary_dir / "mito_gene_summary.tsv", sep="\t")
vc = pd.read_csv(summary_dir / "mito_variant_consequence_candidates.tsv", sep="\t")

qc_map = dict(zip(qc["metric"], qc["value"]))
het_map = dict(zip(het_summary["metric"], het_summary["value"]))
site_8344 = het[het["position"] == 8344].copy()
top_gene = gene.head(10).copy()
site_8344_vc = vc[vc["position"] == 8344].copy()

findings = pd.DataFrame(
    [
        {"metric": "sample_id", "value": "GM11906_MERRF_shortread"},
        {"metric": "read_mode", "value": "short"},
        {"metric": "assay_type", "value": "targeted_mt"},
        {"metric": "min_callable_depth", "value": het_map.get("min_callable_depth", "NA")},
        {"metric": "min_alt_allele_fraction", "value": het_map.get("min_alt_allele_fraction", "NA")},
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
