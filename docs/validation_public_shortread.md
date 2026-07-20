# Public reduced short-read workflow evidence

`mito-overview` v0.3.0 includes a GM11906 public short-read example for exercising the reduced report profile and explicit status pages for long-read-only layers.

## Evidence scope
- evidence snapshot: `2026-07-20`
- clean source commit: `dc09114`
- source runs: `SRR10804585`, `SRR10804590`, and `SRR10804657`
- sample context: GM11906 lymphoblastoid-cell short-read/scATAC-derived mtDNA reads
- profile: `READ_MODE=short`, `ASSAY_TYPE=targeted_mt`
- runner: `scripts/run_public_shortread_validation_gm11906.sh`

The three public runs are combined for the reduced-profile report. The v0.3.0 matrix reuses a provenance-verified fixed BAM.

## Default profile
The example-specific candidate thresholds are `MIN_CALLABLE_DEPTH=10` and `MIN_ALT_ALLELE_FRACTION=0.20`. The default observation filters are `ALLELE_MIN_BASE_QUALITY=13`, `ALLELE_MIN_MAPPING_QUALITY=20`, and `ALLELE_MIN_READ_MEAN_QUALITY=10`.

The default run reports:

- `33` candidate sites
- `44,052,664` accepted observations
- `7,293,106` excluded observations
- `m.8344A>G` at depth `1,027`, with `740` alternate observations and `AF=0.720545`
- `MT-TK` feature context and `tRNA_variant` consequence output for position `8344`

## Filter-profile matrix
Profiles vary only the allele-observation quality filters; candidate thresholds remain fixed.

Candidate counts are lenient=`33`, default=`33`, and strict=`33`; accepted observations are lenient=`44,052,664`, default=`44,052,664`, and strict=`42,676,166`.

| Profile | BaseQ | MAPQ | ReadQ | Candidate sites | Accepted observations | Excluded observations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lenient | 0 | 0 | 0 | 33 | 44,052,664 | 7,293,106 |
| default | 13 | 20 | 10 | 33 | 44,052,664 | 7,293,106 |
| strict | 20 | 30 | 15 | 33 | 42,676,166 | 8,669,604 |

## Mode-gated statuses
The reduced short-read targeted-mt profile writes `not_applicable` status outputs for `deletions`, `copy_number`, `cosegregation`, `numt_qc`, `phymer_haplogroup`, `identity_qc`, `circularity_qc`, and `methylation_exploratory`. Optional `mvtool_annotation` is `not_configured` when disabled.

## Repeatability and claim scope
Two default invocations from the same provenance-verified BAM produced matching normalized TSVs. HTML and PNG artifacts were readable and structurally consistent across the repeats. This result is conditional on the fixed BAM; it does not assess download, FASTQ combination, or alignment regeneration. The evidence supports workflow execution, report/resource generation, profile sensitivity, and mode gating only.

Tracked asset pack:
- `examples/public_validation/GM11906_MERRF_shortread`

References and source metadata:
- [Lareau et al., Nat Biotechnol 2021](https://www.nature.com/articles/s41587-020-0645-6)
- [GEO sample metadata example](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238489)
- [Coriell GM11906](https://www.coriell.org/0/Sections/Search/Sample_Detail.aspx?Ref=GM11906)
