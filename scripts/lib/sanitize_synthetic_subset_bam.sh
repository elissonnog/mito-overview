#!/usr/bin/env bash

# Remove path-bearing @PG header records without altering alignment records.
# samtools 1.23.1 is pinned for release validation; -P prevents reheader from
# adding its own @PG record after the filtered header is installed.
sanitize_synthetic_subset_bam() (
  set -euo pipefail

  if [[ $# -ne 2 ]]; then
    echo "Usage: sanitize_synthetic_subset_bam BAM MT_CONTIG" >&2
    exit 2
  fi

  local bam="$1"
  local mt_contig="$2"
  local samtools_bin="${SAMTOOLS:-samtools}"

  if ! command -v "${samtools_bin}" >/dev/null 2>&1; then
    echo "[example-sanitize] ERROR: samtools is required" >&2
    exit 1
  fi
  if [[ ! -s "${bam}" ]]; then
    echo "[example-sanitize] ERROR: BAM is missing or empty: ${bam}" >&2
    exit 1
  fi
  if [[ -z "${mt_contig}" ]]; then
    echo "[example-sanitize] ERROR: mitochondrial contig cannot be empty" >&2
    exit 1
  fi

  local temp_dir
  temp_dir="$(mktemp -d "${bam}.reheader.XXXXXX")"
  trap 'rm -rf "${temp_dir}"' EXIT

  local input_header="${temp_dir}/input.header.sam"
  local filtered_header="${temp_dir}/filtered.header.sam"
  local output_header="${temp_dir}/output.header.sam"
  local before_records="${temp_dir}/before.records.sam"
  local after_records="${temp_dir}/after.records.sam"
  local sanitized_bam="${temp_dir}/sanitized.bam"
  local sanitized_bai="${temp_dir}/sanitized.bam.bai"

  if ! "${samtools_bin}" quickcheck -v "${bam}"; then
    echo "[example-sanitize] ERROR: input BAM failed samtools quickcheck: ${bam}" >&2
    exit 1
  fi

  "${samtools_bin}" view --no-PG -H "${bam}" > "${input_header}"
  awk -F '\t' '$1 != "@PG"' "${input_header}" > "${filtered_header}"

  if grep -q '^@PG[[:space:]]' "${filtered_header}"; then
    echo "[example-sanitize] ERROR: filtered header still contains @PG records" >&2
    exit 1
  fi
  if ! awk -F '\t' -v target="${mt_contig}" '
    $1 == "@SQ" {
      for (field = 2; field <= NF; field++) {
        if ($field == "SN:" target) {
          found = 1
        }
      }
    }
    END { exit(found ? 0 : 1) }
  ' "${filtered_header}"; then
    echo "[example-sanitize] ERROR: header does not define mitochondrial contig ${mt_contig}" >&2
    exit 1
  fi

  "${samtools_bin}" view --no-PG "${bam}" > "${before_records}"
  local input_mt_records
  input_mt_records="$(awk -F '\t' -v target="${mt_contig}" '$3 == target { count++ } END { print count + 0 }' "${before_records}")"
  if [[ "${input_mt_records}" -le 0 ]]; then
    echo "[example-sanitize] ERROR: input BAM contains no ${mt_contig} alignment records" >&2
    exit 1
  fi

  "${samtools_bin}" reheader -P "${filtered_header}" "${bam}" > "${sanitized_bam}"
  if ! "${samtools_bin}" quickcheck -v "${sanitized_bam}"; then
    echo "[example-sanitize] ERROR: reheadered BAM failed samtools quickcheck" >&2
    exit 1
  fi

  "${samtools_bin}" view --no-PG -H "${sanitized_bam}" > "${output_header}"
  if grep -q '^@PG[[:space:]]' "${output_header}"; then
    echo "[example-sanitize] ERROR: reheadered BAM contains @PG records" >&2
    exit 1
  fi
  if ! cmp -s "${filtered_header}" "${output_header}"; then
    echo "[example-sanitize] ERROR: reheadering changed non-@PG header records" >&2
    exit 1
  fi

  "${samtools_bin}" view --no-PG "${sanitized_bam}" > "${after_records}"
  if ! cmp -s "${before_records}" "${after_records}"; then
    echo "[example-sanitize] ERROR: reheadering changed alignment records" >&2
    exit 1
  fi

  "${samtools_bin}" index "${sanitized_bam}" "${sanitized_bai}"
  if [[ ! -s "${sanitized_bai}" ]]; then
    echo "[example-sanitize] ERROR: samtools did not create a nonempty BAM index" >&2
    exit 1
  fi

  local indexed_mt_records
  indexed_mt_records="$("${samtools_bin}" view -c "${sanitized_bam}" "${mt_contig}")"
  if [[ "${indexed_mt_records}" != "${input_mt_records}" ]]; then
    echo "[example-sanitize] ERROR: indexed ${mt_contig} record count changed (${input_mt_records} -> ${indexed_mt_records})" >&2
    exit 1
  fi

  mv -f "${sanitized_bam}" "${bam}"
  mv -f "${sanitized_bai}" "${bam}.bai"

  if ! "${samtools_bin}" quickcheck -v "${bam}"; then
    echo "[example-sanitize] ERROR: installed BAM failed samtools quickcheck" >&2
    exit 1
  fi
  if [[ "$("${samtools_bin}" view -c "${bam}" "${mt_contig}")" != "${input_mt_records}" ]]; then
    echo "[example-sanitize] ERROR: installed BAM index does not preserve ${mt_contig} records" >&2
    exit 1
  fi
  "${samtools_bin}" view --no-PG -H "${bam}" > "${output_header}"
  if grep -q '^@PG[[:space:]]' "${output_header}"; then
    echo "[example-sanitize] ERROR: installed BAM contains @PG records" >&2
    exit 1
  fi
  "${samtools_bin}" view --no-PG "${bam}" > "${after_records}"
  if ! cmp -s "${before_records}" "${after_records}"; then
    echo "[example-sanitize] ERROR: installed BAM does not preserve alignment records" >&2
    exit 1
  fi

  echo "[example-sanitize] stripped @PG records and verified ${input_mt_records} indexed ${mt_contig} alignments: ${bam}"
)
