# GM11906 public reduced short-read workflow example

This directory contains v0.3.0 public workflow-evidence assets from a pseudo-bulk made by pooling three GM11906 single-cell ATAC-seq libraries and processing their mtDNA-aligned reads with the `mito-overview` reduced short-read profile.

Example context:
- source sample: one GM11906 lymphoblastoid cell line
- source libraries: three single-cell ATAC-seq libraries (`GSM4238454`, `GSM4238459`, and `GSM4238526`) pooled as a pseudo-bulk
- runs used: `SRR10804585`, `SRR10804590`, `SRR10804657`
- profile used: `READ_MODE=short` with the package's `ASSAY_TYPE=targeted_mt` report profile
- candidate thresholds: `MIN_CALLABLE_DEPTH=10`, `MIN_ALT_ALLELE_FRACTION=0.20`
- default observation filters: BaseQ `13`, MAPQ `20`, readQ `10`

Included assets:
- report-native figures from the deterministic pooled input
- key summary tables from the validation output
- a filter-matched, focused `8344` mpileup record for read-level inspection
- a condensed key-findings table
- input and run provenance records

What these assets support:
- reduced short-read workflow execution after deterministic pooled-input reconstruction
- representation of `m.8344A>G` in candidate, feature, and consequence outputs
- report/resource generation and explicit status handling

Observed default-profile values:
- candidate sites: `33`
- accepted observations: `44,048,838`
- excluded observations: `7,296,932`
- `m.8344A>G`: depth `1,027`, alternate count `740`, pooled observed alternate allele fraction `0.720545`
- feature/consequence output: `MT-TK`, `tRNA_variant`

The focused mpileup is generated with anomalous pairs retained, BAQ disabled,
unlimited depth, BaseQ/MAPQ `13/20`, excluded flag mask `3844`, and overlap
removal enabled. Its canonical-base counts are `A=285`, `C=0`, `G=740`, and
`T=2` (depth `1,027`), matching the default MitoOverview site row. It remains
an inspection artifact rather than independent validation: `samtools mpileup`
does not implement MitoOverview's mean-read-quality filter or its complete
deterministic equal-rank tie policy.

Filter profiles:

| Profile | BaseQ/MAPQ/readQ | Candidates | Accepted observations | Excluded observations |
| --- | --- | ---: | ---: | ---: |
| lenient | `0/0/0` | 33 | 44,048,838 | 7,296,932 |
| default | `13/20/10` | 33 | 44,048,838 | 7,296,932 |
| strict | `20/30/15` | 33 | 42,675,832 | 8,669,938 |

Mode-gated status values:
- `deletions`, `copy_number`, `cosegregation`, `numt_qc`, `phymer_haplogroup`, `identity_qc`, `circularity_qc`, and `methylation_exploratory`: `not_applicable`
- `mvtool_annotation`: `not_configured`

Repeatability scope:
- the pooled fraction summarizes passing read observations across three libraries; it is not a per-cell estimate, a calibrated sample heteroplasmy estimate, or a modality benchmark
- unequal callable depth across the three source libraries makes the pooled fraction read-observation weighted rather than equal-weight per cell
- each clean-room platform matrix reconstructs the paired pseudo-bulk and BWA alignment from the six sealed accession FASTQs
- two default invocations produced matching normalized TSVs and structurally consistent HTML/PNG artifacts
- those two invocations use the same newly generated within-matrix BAM, separating report repeatability from alignment reconstruction
- the asset pack supports workflow execution and report/resource inspection for this prespecified input
