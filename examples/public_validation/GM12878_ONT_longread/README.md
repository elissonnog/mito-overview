# GM12878 public ONT deterministic qn1000 workflow example

This directory contains v0.3.0 public workflow-evidence assets from a seeded deterministic query-name subset of an ONT targeted-mt run processed with the `mito-overview` long-read profile.

Example context:
- source BioProject: `PRJNA809571`
- run used: `SRR18110025`
- public assay description: `Long read mitochondrial genome sequencing using Cas9-guided adaptor ligation`
- source FASTQ records: `193,043`
- fixed subset: exactly `1,000` selected query names and `1,000` FASTQ records
- profile used: `READ_MODE=long`, `ASSAY_TYPE=targeted_mt`
- candidate thresholds: `MIN_CALLABLE_DEPTH=100`, `MIN_ALT_ALLELE_FRACTION=0.10`
- default observation filters: BaseQ `13`, MAPQ `20`, readQ `10`

Included assets:
- report-native figures from the fixed qn1000 input
- key summary tables from the validation output
- condensed key-findings and top-signal tables
- alignment flagstat summary
- reduced-input provenance records

What these assets support:
- fixed-input public ONT long-read execution of the core report workflow
- report-native QC, alternate-allele screening, deletion-screening, co-segregation, gene-summary, alignment-ambiguity QC, circularity-QC, and consequence outputs
- explicit assay-mode and optional-layer status reporting

Observed fixed-input values:
- mapped alignment records: `1,271` (`728` primary and `543` supplementary)
- mapped unique query names: `728`
- mean depth: `545.484`
- median depth: `544.0`
- full-length fraction: `0.3721`
- alternate-allele candidate sites: `16`
- accepted observations: `7,143,152`
- excluded observations: `2,047,476`
- selected co-segregation sites: `8`
- top consequence class: `synonymous_variant` (`6` sites)
- structural screen: `13` singleton CIGAR/SA bins, each with one supporting primary read; maximum support fraction `0.001374`

Status values:

| Layer | Status | Detail |
| --- | --- | --- |
| `copy_number` | `not_applicable` | targeted-mt assay |
| `phymer_haplogroup` | `not_applicable` | targeted-mt assay |
| `mvtool_annotation` | `not_configured` | optional integration disabled |
| `methylation_exploratory` | `not_configured` | no bedmethyl sidecars configured |
| NUMT interpretation | `not_evaluable` | `reference_scope_mt_only` |

Filter profiles:

| Profile | BaseQ/MAPQ/readQ | Candidates | Accepted observations | Excluded observations |
| --- | --- | ---: | ---: | ---: |
| lenient | `0/0/0` | 32 | 8,278,969 | 911,659 |
| default | `13/20/10` | 16 | 7,143,152 | 2,047,476 |
| strict | `20/30/15` | 15 | 6,046,355 | 3,144,273 |

Repeatability scope:
- two default invocations produced matching normalized TSVs and structurally consistent HTML/PNG artifacts
- this result is conditional on the provenance-verified fixed BAM and does not include subset selection or alignment regeneration
- the asset pack supports workflow execution and report/resource inspection for this reduced input
