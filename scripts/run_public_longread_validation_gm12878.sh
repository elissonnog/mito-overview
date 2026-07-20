#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 OUTPUT_DIR" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="$1"
WORKDIR="${MITO_OVERVIEW_LONGREAD_WORKDIR:-$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-gm12878-longread.XXXXXX")}"
if [[ -z "${MITO_OVERVIEW_LONGREAD_WORKDIR:-}" ]]; then
  trap 'rm -rf "${WORKDIR}"' EXIT
fi

source "${SCRIPT_DIR}/lib/mock_optional_integrations.sh"
source "${SCRIPT_DIR}/lib/test_assertions.sh"

echo "[longread-gm12878] repo root: ${REPO_ROOT}"
echo "[longread-gm12878] workdir: ${WORKDIR}"
echo "[longread-gm12878] output dir: ${OUTPUT_DIR}"
echo "[longread-gm12878] python: ${MITO_OVERVIEW_PYTHON:-python3}"

if [[ -n "${MITO_OVERVIEW_PYTHON:-}" ]]; then
  TOOL_BIN="$(cd "$(dirname "${MITO_OVERVIEW_PYTHON}")" && pwd)"
  export PATH="${TOOL_BIN}${PATH:+:${PATH}}"
fi
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"

for tool in curl minimap2 samtools; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required tool not found in PATH: ${tool}" >&2
    exit 1
  fi
done

export MPLCONFIGDIR="${WORKDIR}/.mplconfig"
mkdir -p "${MPLCONFIGDIR}"
export XDG_CACHE_HOME="${WORKDIR}/.cache"
mkdir -p "${XDG_CACHE_HOME}"

DATA_DIR="${MITO_OVERVIEW_LONGREAD_DATA_DIR:-${WORKDIR}/downloads}"
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
    echo "[longread-gm12878] downloading ${url}"
    curl \
      --fail \
      --retry "${MITO_OVERVIEW_LONGREAD_CURL_RETRIES:-3}" \
      --retry-delay "${MITO_OVERVIEW_LONGREAD_CURL_RETRY_DELAY:-2}" \
      --connect-timeout "${MITO_OVERVIEW_LONGREAD_CURL_CONNECT_TIMEOUT:-20}" \
      --max-time "${MITO_OVERVIEW_LONGREAD_CURL_MAX_TIME:-1200}" \
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

copy_if_exists() {
  local src="$1"
  local dest_dir="$2"
  if [[ -f "${src}" ]]; then
    cp "${src}" "${dest_dir}/"
  fi
}

THREADS="${MITO_OVERVIEW_LONGREAD_THREADS:-2}"
ALIGN_BAM="${MITO_OVERVIEW_LONGREAD_ALIGN_BAM:-${HV_DIR}/GM12878_ONT_longread.mt.bam}"
FASTQ_GZ="${MITO_OVERVIEW_LONGREAD_FASTQ_GZ:-${DATA_DIR}/SRR18110025.fastq.gz}"

if [[ ! -s "${ALIGN_BAM}" || ! -s "${ALIGN_BAM}.bai" ]]; then
  if [[ "${FASTQ_GZ}" == "${DATA_DIR}/SRR18110025.fastq.gz" ]]; then
    download_if_missing \
      "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR181/025/SRR18110025/SRR18110025_1.fastq.gz" \
      "${FASTQ_GZ}"
  elif [[ ! -s "${FASTQ_GZ}" ]]; then
    echo "Requested MITO_OVERVIEW_LONGREAD_FASTQ_GZ does not exist or is empty: ${FASTQ_GZ}" >&2
    exit 1
  fi
fi

REF_FASTA="${REF_DIR}/NC_012920.1.fa"
cp "${REPO_ROOT}/resources/annotations/NC_012920.1.fa" "${REF_FASTA}"
samtools faidx "${REF_FASTA}"
if [[ ! -f "${REF_FASTA}.mmi" ]]; then
  minimap2 -d "${REF_FASTA}.mmi" "${REF_FASTA}"
fi

if [[ -s "${ALIGN_BAM}" && -s "${ALIGN_BAM}.bai" ]]; then
  echo "[longread-gm12878] reusing existing aligned BAM ${ALIGN_BAM}"
else
  echo "[longread-gm12878] aligning public ONT mtDNA data to ${REF_FASTA}"
  mkdir -p "$(dirname "${ALIGN_BAM}")"
  minimap2 -t "${THREADS}" -ax map-ont "${REF_FASTA}.mmi" "${FASTQ_GZ}" \
    | samtools sort -@ "${THREADS}" -o "${ALIGN_BAM}"
  samtools index -@ "${THREADS}" "${ALIGN_BAM}"
fi
samtools flagstat "${ALIGN_BAM}" > "${WORKDIR}/GM12878_ONT_longread.flagstat.txt"

MVTOOL_MODE="${MITO_OVERVIEW_LONGREAD_MVTOOL_MODE:-disabled}"
MVTOOL_FIXTURE_JSON="${MITO_OVERVIEW_LONGREAD_MVTOOL_FIXTURE_JSON:-}"
if [[ "${MVTOOL_MODE}" == "fixture" && -z "${MVTOOL_FIXTURE_JSON}" ]]; then
  MVTOOL_FIXTURE_JSON="$(mock_mvtool_fixture_path "${REPO_ROOT}")"
fi
MIN_CALLABLE_DEPTH="${MITO_OVERVIEW_LONGREAD_MIN_CALLABLE_DEPTH:-${MITO_OVERVIEW_LONGREAD_HET_MIN_DEPTH:-100}}"
MIN_ALT_ALLELE_FRACTION="${MITO_OVERVIEW_LONGREAD_MIN_ALT_ALLELE_FRACTION:-${MITO_OVERVIEW_LONGREAD_HET_MIN_VAF:-0.10}}"
ALLELE_MIN_BASE_QUALITY="${MITO_OVERVIEW_LONGREAD_ALLELE_MIN_BASE_QUALITY:-13}"
ALLELE_MIN_MAPPING_QUALITY="${MITO_OVERVIEW_LONGREAD_ALLELE_MIN_MAPPING_QUALITY:-20}"
ALLELE_MIN_READ_MEAN_QUALITY="${MITO_OVERVIEW_LONGREAD_ALLELE_MIN_READ_MEAN_QUALITY:-10}"
cat > "${WORKDIR}/gm12878_longread.env" <<EOF
WORK_ROOT=${RUN_ROOT}
RUN_NAME=mito_GM12878_ONT_longread
SAMPLE_ID=GM12878_ONT_longread
REF_FASTA=${REF_FASTA}
SOURCE_ALIGN_FILE=${ALIGN_BAM}
MT_CONTIG=NC_012920.1
THREADS=${THREADS}
SPECIES=human
READ_MODE=long
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
DELETION_MIN_SIZE=${MITO_OVERVIEW_LONGREAD_DELETION_MIN_SIZE:-100}
HUMAN_MT_GTF=${REPO_ROOT}/resources/annotations/human_mt_reference.gtf
MVTOOL_MODE=${MVTOOL_MODE}
MVTOOL_FIXTURE_JSON=${MVTOOL_FIXTURE_JSON}
FINAL_BIOINFO_DIR=${FINAL_DIR}
EOF

cd "${REPO_ROOT}"
./scripts/run_mito_pipeline.sh \
  --config "${WORKDIR}/gm12878_longread.env" \
  --strict-files \
  --steps validate,stage,extract,mito_qc,heteroplasmy,deletions,copy_number,feature_annotation,cosegregation,gene_summary,numt_qc,phymer_haplogroup,identity_qc,variant_consequence,mvtool_annotation,circularity_qc,methylation_exploratory,sync_bioinfo

SUMMARY_DIR="${FINAL_DIR}/output/summary"
assert_allele_table_invariants "${SUMMARY_DIR}/mito_heteroplasmy_all_sites.tsv"
assert_tsv_metric "${SUMMARY_DIR}/mito_copy_number_summary.tsv" status not_applicable
assert_tsv_metric "${SUMMARY_DIR}/mito_phymer_haplogroup_summary.tsv" status not_applicable
assert_tsv_metric "${SUMMARY_DIR}/mito_numt_qc_summary.tsv" reference_scope mt_only
assert_tsv_metric "${SUMMARY_DIR}/mito_numt_qc_summary.tsv" numt_interpretation_status not_evaluable
assert_tsv_metric "${SUMMARY_DIR}/mito_numt_qc_summary.tsv" reason_code reference_scope_mt_only
assert_tsv_metric "${SUMMARY_DIR}/mito_mvtool_annotation_summary.tsv" status \
  "$([[ "${MVTOOL_MODE}" == "disabled" ]] && printf not_configured || printf ok)"
"${PYTHON_BIN}" - "${SUMMARY_DIR}/mito_numt_qc_summary.tsv" <<'PY'
import sys

import pandas as pd

summary = pd.read_csv(sys.argv[1], sep="\t", dtype=str, keep_default_na=False)
metrics = dict(zip(summary["metric"], summary["value"]))
risk = metrics.get("heuristic_numt_risk", "")
if risk.lower() in {"low", "moderate", "high"}:
    raise SystemExit(
        "GM12878 release gate failed: mt-only reference produced categorical NUMT risk " + risk
    )
if metrics.get("numt_interpretation_status") != "not_evaluable":
    raise SystemExit("GM12878 release gate failed: NUMT interpretation was not suppressed")
print("[longread-gm12878] release gate confirmed mt-only NUMT interpretation is not evaluable")
PY

rm -rf "${OUTPUT_DIR}"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
cp -R "${FINAL_DIR}/output" "${OUTPUT_DIR}"
copy_if_needed "${WORKDIR}/GM12878_ONT_longread.flagstat.txt" "$(dirname "${OUTPUT_DIR}")/GM12878_ONT_longread.flagstat.txt"

if [[ -n "${MITO_OVERVIEW_LONGREAD_ASSET_DIR:-}" ]]; then
  ASSET_DIR="${MITO_OVERVIEW_LONGREAD_ASSET_DIR}"
  FIG_DIR="${ASSET_DIR}/figures"
  SUMMARY_DIR="${ASSET_DIR}/summary"
  mkdir -p "${FIG_DIR}" "${SUMMARY_DIR}"

  copy_if_exists "${OUTPUT_DIR}/figures/mito_heteroplasmy_landscape.png" "${FIG_DIR}"
  copy_if_exists "${OUTPUT_DIR}/figures/mito_cosegregation_heatmap.png" "${FIG_DIR}"
  copy_if_exists "${OUTPUT_DIR}/figures/mito_gene_summary_overview.png" "${FIG_DIR}"
  copy_if_exists "${OUTPUT_DIR}/figures/mito_numt_qc_mapq_vs_span.png" "${FIG_DIR}"
  copy_if_exists "${OUTPUT_DIR}/figures/mito_depth_profile.png" "${FIG_DIR}"
  copy_if_exists "${OUTPUT_DIR}/figures/mito_variant_consequence_classes.png" "${FIG_DIR}"
  copy_if_exists "${OUTPUT_DIR}/figures/mito_circularity_edge_metrics.png" "${FIG_DIR}"
  copy_if_exists "${OUTPUT_DIR}/figures/mito_deletion_clusters.png" "${FIG_DIR}"

  copy_if_exists "${OUTPUT_DIR}/summary/mito_qc_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_heteroplasmy_candidates.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_deletion_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_deletion_clusters.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_cosegregation_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_cosegregation_selected_sites.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_cosegregation_pairwise.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_gene_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_numt_qc_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_variant_consequence_candidates.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_variant_consequence_class_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_copy_number_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_phymer_haplogroup_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_methylation_exploratory_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_circularity_qc_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_mvtool_annotation_summary.tsv" "${SUMMARY_DIR}"
  copy_if_exists "${OUTPUT_DIR}/summary/mito_identity_qc_summary.tsv" "${SUMMARY_DIR}"
  copy_if_needed "${WORKDIR}/GM12878_ONT_longread.flagstat.txt" "${ASSET_DIR}/GM12878_ONT_longread.flagstat.txt"

  if [[ -f "${OUTPUT_DIR}/figures/mito_heteroplasmy_landscape.png" \
     && -f "${OUTPUT_DIR}/figures/mito_cosegregation_heatmap.png" \
     && -f "${OUTPUT_DIR}/figures/mito_gene_summary_overview.png" \
     && -f "${OUTPUT_DIR}/figures/mito_numt_qc_mapq_vs_span.png" ]]; then
    "${PYTHON_BIN}" scripts/build_report_montage.py \
      --source-dir "${OUTPUT_DIR}/figures" \
      --output "${FIG_DIR}/GM12878_ONT_longread_montage.png" \
      --title "GM12878 public ONT long-read proof-of-principle"
  else
    echo "[longread-gm12878] skipping montage build because one or more expected long-read panels were not produced"
  fi

  "${PYTHON_BIN}" - <<'PY' "${OUTPUT_DIR}" "${ASSET_DIR}"
import sys
from pathlib import Path
import pandas as pd

output_dir = Path(sys.argv[1])
asset_dir = Path(sys.argv[2])
summary_dir = output_dir / "summary"

def load_metric_table(name: str) -> pd.DataFrame:
    path = summary_dir / name
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, sep="\t")
    return pd.DataFrame()

qc = load_metric_table("mito_qc_summary.tsv")
het = load_metric_table("mito_heteroplasmy_candidates.tsv")
het_summary = load_metric_table("mito_heteroplasmy_summary.tsv")
deletions = load_metric_table("mito_deletion_summary.tsv")
clusters = load_metric_table("mito_deletion_clusters.tsv")
gene = load_metric_table("mito_gene_summary.tsv")
copy_number = load_metric_table("mito_copy_number_summary.tsv")
phymer = load_metric_table("mito_phymer_haplogroup_summary.tsv")
methyl = load_metric_table("mito_methylation_exploratory_summary.tsv")
coseg = load_metric_table("mito_cosegregation_summary.tsv")
numt = load_metric_table("mito_numt_qc_summary.tsv")
vc_class = load_metric_table("mito_variant_consequence_class_summary.tsv")

qc_map = dict(zip(qc.get("metric", []), qc.get("value", [])))
het_map = dict(zip(het_summary.get("metric", []), het_summary.get("value", [])))
del_map = dict(zip(deletions.get("metric", []), deletions.get("value", [])))
copy_map = dict(zip(copy_number.get("metric", []), copy_number.get("value", [])))
phymer_map = dict(zip(phymer.get("metric", []), phymer.get("value", [])))
methyl_map = dict(zip(methyl.get("metric", []), methyl.get("value", [])))
coseg_map = dict(zip(coseg.get("metric", []), coseg.get("value", [])))
numt_map = dict(zip(numt.get("metric", []), numt.get("value", [])))

findings = pd.DataFrame(
    [
        {"metric": "sample_id", "value": "GM12878_ONT_longread"},
        {"metric": "read_mode", "value": "long"},
        {"metric": "assay_type", "value": "targeted_mt"},
        {"metric": "min_callable_depth", "value": het_map.get("min_callable_depth", "NA")},
        {"metric": "min_alt_allele_fraction", "value": het_map.get("min_alt_allele_fraction", "NA")},
        {"metric": "mapped_reads", "value": qc_map.get("mapped_reads", "NA")},
        {"metric": "mean_depth", "value": qc_map.get("mean_depth", "NA")},
        {"metric": "median_depth", "value": qc_map.get("median_depth", "NA")},
        {"metric": "full_length_fraction", "value": qc_map.get("full_length_fraction", "NA")},
        {"metric": "candidate_site_count", "value": len(het)},
        {"metric": "selected_cosegregation_sites", "value": coseg_map.get("selected_sites", "NA")},
        {"metric": "candidate_deletion_clusters", "value": del_map.get("candidate_deletion_clusters", "NA")},
        {"metric": "largest_median_deletion", "value": del_map.get("largest_median_deletion", "NA")},
        {"metric": "max_deletion_support_fraction_primary", "value": del_map.get("max_support_fraction_primary", "NA")},
        {"metric": "numt_interpretation_status", "value": numt_map.get("numt_interpretation_status", "NA")},
        {"metric": "numt_reason_code", "value": numt_map.get("reason_code", "NA")},
        {"metric": "copy_number_status", "value": copy_map.get("status", "NA")},
        {"metric": "phymer_status", "value": phymer_map.get("status", "NA")},
        {"metric": "methylation_status", "value": methyl_map.get("status", "NA")},
    ]
)
findings.to_csv(asset_dir / "GM12878_ONT_longread_key_findings.tsv", sep="\t", index=False)
het.head(25).to_csv(asset_dir / "GM12878_ONT_longread_top_heteroplasmy_candidates.tsv", sep="\t", index=False)
clusters.head(25).to_csv(asset_dir / "GM12878_ONT_longread_top_deletion_clusters.tsv", sep="\t", index=False)
gene.head(25).to_csv(asset_dir / "GM12878_ONT_longread_top_gene_summary.tsv", sep="\t", index=False)

top_class = "NA"
top_class_count = "NA"
if not vc_class.empty and {"consequence_class", "candidate_sites"}.issubset(vc_class.columns):
    top_class_row = vc_class.sort_values(["candidate_sites", "consequence_class"], ascending=[False, True]).iloc[0]
    top_class = top_class_row["consequence_class"]
    top_class_count = top_class_row["candidate_sites"]

readme_lines = [
    "# GM12878 public ONT long-read proof-of-principle example",
    "",
    "This directory contains light-weight public example assets derived from a real ONT targeted-mt dataset processed with the `mito-overview` long-read profile.",
    "",
    "Example context:",
    "- source BioProject: `PRJNA809571`",
    "- run used: `SRR18110025`",
    "- public assay description: `Long read mitochondrial genome sequencing using Cas9-guided adaptor ligation`",
    "- profile used: `READ_MODE=long`, `ASSAY_TYPE=targeted_mt`",
    f"- minimum callable depth: `{het_map.get('min_callable_depth', 'NA')}`",
    f"- minimum observed alternate allele fraction: `{het_map.get('min_alt_allele_fraction', 'NA')}`",
    "",
    "Included assets:",
    "- representative report-native figures used for GitHub/manuscript panels",
    "- key summary tables from the validation output",
    "- condensed key-findings and top-signal tables",
    "- alignment flagstat summary",
    "",
    "What these assets support:",
    "- real public ONT long-read execution of the core long-read workflow",
    "- report-native QC, alternate-allele screening, deletion-screening, co-segregation, gene-summary, alignment-ambiguity QC, circularity-QC, and consequence outputs",
    "- explicit assay-mode gating for targeted-mt layers that remain uninterpretable here (`copy_number` and `phymer_haplogroup`)",
    "- explicit status-only methylation reporting when mitochondrial bedmethyl rows are unavailable",
    "",
    "What these assets do not claim:",
    "- clinical interpretation",
    "- calibrated low-allele-fraction detection benchmarking",
    "- validated deletion truth benchmarking",
    "- formal mtDNA-versus-NUMT classification",
    "- biological methylation conclusions",
    "",
    "Observed packaged key values:",
    f"- mapped reads: `{qc_map.get('mapped_reads', 'NA')}`",
    f"- mean depth: `{qc_map.get('mean_depth', 'NA')}`",
    f"- median depth: `{qc_map.get('median_depth', 'NA')}`",
    f"- full-length fraction: `{qc_map.get('full_length_fraction', 'NA')}`",
    f"- alternate-allele candidate sites: `{len(het)}`",
    f"- selected co-segregation sites: `{coseg_map.get('selected_sites', 'NA')}`",
    f"- top consequence class: `{top_class}` (`{top_class_count}` sites)",
    f"- candidate deletion clusters: `{del_map.get('candidate_deletion_clusters', 'NA')}` with max support fraction `{del_map.get('max_support_fraction_primary', 'NA')}`",
    f"- NUMT interpretation status: `{numt_map.get('numt_interpretation_status', 'NA')}` (`{numt_map.get('reason_code', 'NA')}`)",
    f"- copy-number status: `{copy_map.get('status', 'NA')}`",
    f"- Phy-Mer status: `{phymer_map.get('status', 'NA')}`",
    f"- methylation status: `{methyl_map.get('status', 'NA')}`",
    "",
    "Important note:",
    "- optional network-backed mvTool annotation is disabled unless explicitly configured",
]
(asset_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
PY
fi

echo "[longread-gm12878] validation bundle created at ${OUTPUT_DIR}"
