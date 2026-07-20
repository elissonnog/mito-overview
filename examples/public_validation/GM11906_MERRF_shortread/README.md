# GM11906 public reduced short-read workflow example

This directory contains v0.3.0 public workflow-evidence assets from short-read/scATAC-derived mtDNA reads processed with the `mito-overview` reduced short-read profile.

Example context:
- source sample: GM11906 short-read/scATAC-derived mtDNA reads
- runs used: `SRR10804585`, `SRR10804590`, `SRR10804657`
- profile used: `READ_MODE=short` with the package's `ASSAY_TYPE=targeted_mt` report profile
- candidate thresholds: `MIN_CALLABLE_DEPTH=10`, `MIN_ALT_ALLELE_FRACTION=0.20`
- default observation filters: BaseQ `13`, MAPQ `20`, readQ `10`

Included assets:
- report-native figures from the fixed input
- key summary tables from the validation output
- a focused `8344` mpileup record
- a condensed key-findings table
- input and run provenance records

What these assets support:
- fixed-input reduced short-read workflow execution
- representation of `m.8344A>G` in candidate, feature, and consequence outputs
- report/resource generation and explicit status handling

Observed default-profile values:
- candidate sites: `33`
- accepted observations: `44,052,664`
- excluded observations: `7,293,106`
- `m.8344A>G`: depth `1,027`, alternate count `740`, `AF=0.720545`
- feature/consequence output: `MT-TK`, `tRNA_variant`

Filter profiles:

| Profile | BaseQ/MAPQ/readQ | Candidates | Accepted observations | Excluded observations |
| --- | --- | ---: | ---: | ---: |
| lenient | `0/0/0` | 33 | 44,052,664 | 7,293,106 |
| default | `13/20/10` | 33 | 44,052,664 | 7,293,106 |
| strict | `20/30/15` | 33 | 42,676,166 | 8,669,604 |

Mode-gated status values:
- `deletions`, `copy_number`, `cosegregation`, `numt_qc`, `phymer_haplogroup`, `identity_qc`, `circularity_qc`, and `methylation_exploratory`: `not_applicable`
- `mvtool_annotation`: `not_configured`

Repeatability scope:
- two default invocations produced matching normalized TSVs and structurally consistent HTML/PNG artifacts
- this result is conditional on the provenance-verified fixed BAM and does not include alignment regeneration
- the asset pack supports workflow execution and report/resource inspection for this fixed input
