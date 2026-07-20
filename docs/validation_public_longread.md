# Public ONT long-read reduced-input workflow evidence

`mito-overview` v0.3.0 includes a bounded public GM12878 ONT targeted-mt example for exercising the long-read report workflow and its assay-mode status handling.

## Evidence scope
- evidence snapshot: `2026-07-20`
- clean source commit: `dc09114`
- public accessions: BioProject `PRJNA809571`, run `SRR18110025`
- public assay description: `Long read mitochondrial genome sequencing using Cas9-guided adaptor ligation`
- profile: `READ_MODE=long`, `ASSAY_TYPE=targeted_mt`
- runner: `scripts/run_public_longread_validation_gm12878.sh`

## Fixed reduced input
The source FASTQ contains `193,043` records. The v0.3.0 input is exactly a seeded deterministic subset of `1,000` query names, with one FASTQ record per selected name. The provenance-verified mapped-only BAM contains:

- `728` mapped unique query names
- `728` primary alignments
- `543` supplementary records
- `1,271` mapped alignment records in total

The validation matrix reuses that fixed BAM. Its repeatability result is conditional on the BAM and does not test regeneration of the query-name subset or alignment.

## Default profile
The example-specific candidate thresholds are `MIN_CALLABLE_DEPTH=100` and `MIN_ALT_ALLELE_FRACTION=0.10`. The default observation filters are `ALLELE_MIN_BASE_QUALITY=13`, `ALLELE_MIN_MAPPING_QUALITY=20`, and `ALLELE_MIN_READ_MEAN_QUALITY=10`.

The default run reports:

- `16` candidate sites
- `7,143,152` accepted observations
- `2,047,476` excluded observations
- `13` singleton CIGAR/SA structural-screen bins

The 13 screen bins each have one supporting primary read. They are descriptive workflow output from this fixed input.

Targeted-mt and optional-layer status values are:

| Layer | Status | Detail |
| --- | --- | --- |
| `copy_number` | `not_applicable` | targeted-mt input lacks the required nuclear context |
| `phymer_haplogroup` | `not_applicable` | targeted-mt assay gating |
| `mvtool_annotation` | `not_configured` | optional integration disabled |
| `methylation_exploratory` | `not_configured` | no bedmethyl sidecars configured |
| NUMT interpretation | `not_evaluable` | `reference_scope_mt_only` |

## Filter-profile matrix
Profiles vary only the allele-observation quality filters; candidate thresholds remain fixed.

Candidate counts are lenient=`32`, default=`16`, and strict=`15`; accepted observations are lenient=`8,278,969`, default=`7,143,152`, and strict=`6,046,355`.

| Profile | BaseQ | MAPQ | ReadQ | Candidate sites | Accepted observations | Excluded observations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lenient | 0 | 0 | 0 | 32 | 8,278,969 | 911,659 |
| default | 13 | 20 | 10 | 16 | 7,143,152 | 2,047,476 |
| strict | 20 | 30 | 15 | 15 | 6,046,355 | 3,144,273 |

## Repeatability and claim scope
Two default invocations from the same provenance-verified BAM produced matching normalized TSVs. HTML and PNG artifacts were readable and structurally consistent across the repeats. This evidence supports fixed-input workflow execution, report/resource generation, profile sensitivity, and status gating only.

Tracked asset pack:
- `examples/public_validation/GM12878_ONT_longread`

References and source metadata:
- [NCBI BioProject PRJNA809571](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA809571)
- [ENA run SRR18110025](https://www.ebi.ac.uk/ena/browser/view/SRR18110025)
- [Slapnik et al., Sci Rep 2024](https://www.nature.com/articles/s41598-024-78270-0)
- [Frascarelli et al., Front Genet 2023](https://pubmed.ncbi.nlm.nih.gov/37456669/)
