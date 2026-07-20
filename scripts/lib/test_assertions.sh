#!/usr/bin/env bash

assert_tsv_metric() {
  local path="$1"
  local metric="$2"
  local expected="$3"
  awk -F '\t' -v metric="${metric}" -v expected="${expected}" '
    NR > 1 && $1 == metric { found = 1; if ($2 == expected) matched = 1 }
    END { exit !(found && matched) }
  ' "${path}"
}

assert_tsv_header_field() {
  local path="$1"
  local field="$2"
  awk -F '\t' -v field="${field}" '
    NR == 1 { for (i = 1; i <= NF; i++) if ($i == field) found = 1 }
    END { exit !found }
  ' "${path}"
}

assert_allele_table_invariants() {
  local path="$1"
  awk -F '\t' '
    NR == 1 {
      for (i = 1; i <= NF; i++) column_index[$i] = i
      required[1] = "callable_depth"
      required[2] = "alt_count"
      required[3] = "alt_forward"
      required[4] = "alt_reverse"
      required[5] = "A"
      required[6] = "C"
      required[7] = "G"
      required[8] = "T"
      for (i = 1; i <= 8; i++) if (!(required[i] in column_index)) exit 1
      next
    }
    {
      callable = $(column_index["A"]) + $(column_index["C"]) + $(column_index["G"]) + $(column_index["T"])
      strand_alt = $(column_index["alt_forward"]) + $(column_index["alt_reverse"])
      if ($(column_index["callable_depth"]) != callable || $(column_index["alt_count"]) != strand_alt) exit 1
    }
  ' "${path}"
}

assert_allele_site() {
  local path="$1"
  local position="$2"
  local ref_base="$3"
  local alt_base="$4"
  local callable_depth="$5"
  local alt_count="$6"
  local alt_fraction="$7"
  awk -F '\t' \
    -v position="${position}" \
    -v ref_base="${ref_base}" \
    -v alt_base="${alt_base}" \
    -v callable_depth="${callable_depth}" \
    -v alt_count="${alt_count}" \
    -v alt_fraction="${alt_fraction}" '
      NR == 1 {
        for (i = 1; i <= NF; i++) column_index[$i] = i
        next
      }
      $(column_index["position"]) == position &&
      $(column_index["ref_base"]) == ref_base &&
      $(column_index["alt_base"]) == alt_base &&
      $(column_index["callable_depth"]) == callable_depth &&
      $(column_index["alt_count"]) == alt_count &&
      $(column_index["alt_allele_fraction"]) == alt_fraction { matched = 1 }
      END { exit !matched }
    ' "${path}"
}
