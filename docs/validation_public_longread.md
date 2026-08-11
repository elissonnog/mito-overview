# Public ONT long-read reduced-input evidence

The repository tracks a bounded public GM12878 ONT targeted-mt example for exercising the long-read report workflow and its assay-mode status handling. The frozen v0.3.0 scientific protocol was validated at commit `b116430e037f4ff2f9cf6f6f3ba66150cce1303f`; v0.3.1 changes release/report tooling only and preserves these inputs, algorithms, thresholds, schemas, oracles, and normalized biological results.

## Evidence scope
- validated scientific-protocol commit: `b116430e037f4ff2f9cf6f6f3ba66150cce1303f`
- validation result: `36/36` release cases, `366/366` scientific oracle assertions, and `206/206` normalized cross-platform comparisons passed
- tracked-output status: regenerated from the sealed seven-FASTQ matrix and bound to the verified v0.3.0 validation packet
- public accessions: BioProject `PRJNA809571`, run `SRR18110025`
- dataset source: [Vandiver et al., 2022, PMCID PMC9399971](https://pmc.ncbi.nlm.nih.gov/articles/PMC9399971/)
- public assay description: `Long read mitochondrial genome sequencing using Cas9-guided adaptor ligation`
- alignment reference: `NC_012920.1`
- profile: `READ_MODE=long`, `ASSAY_TYPE=targeted_mt`
- runner: `scripts/run_public_longread_validation_gm12878.sh`

## Fixed reduced input
The source FASTQ contains `193,043` records. To bound the workflow example while making inclusion deterministic and auditable, the release-candidate input uses exactly the `1,000` smallest seeded query-name SHA-256 scores under `smallest_sha256_seeded_query_names_v1`, with seed `mito-overview-v0.3.0-GM12878-SRR18110025`. This subset is not presented as statistically representative. The selected reads were aligned to `NC_012920.1` with minimap2 `2.31-r1302` and samtools `1.23.1` using the tracked command template:

```bash
minimap2 -t {threads} -ax map-ont {reference_mmi} {deterministic_subset_fastq} | samtools view -@ {threads} -b -F 4 | samtools sort -@ {threads} -o {alignment_bam}
```

The provenance-verified mapped-only BAM contains:

- `728` mapped unique query names
- `728` primary alignments
- `543` supplementary records
- `1,271` mapped alignment records in total

The local matrix independently recomputed the seeded query-name subset and rebuilt the mapped-only BAM from the sealed source FASTQ. It then reused that newly generated derivative for the two default report invocations so report repeatability was not conflated with a second alignment.

## v0.3.1 release binding

The values below are exact observations from the completed v0.3.0 scientific protocol, not provisional local estimates. The unchanged protocol was rerun for the v0.3.1 package identity from its exact release commit on macOS and Ubuntu. Authoritative assets are available from the [`v0.3.1` GitHub release](https://github.com/elissonnog/mito-overview/releases/tag/v0.3.1), [validation packet](https://github.com/elissonnog/mito-overview/releases/download/v0.3.1/mito-overview-v0.3.1-validation.zip), and [validation report](https://github.com/elissonnog/mito-overview/releases/download/v0.3.1/MitoOverview_v0.3.1_release_validation_report.pdf).

## Default profile
The example-specific candidate thresholds are `MIN_CALLABLE_DEPTH=100` and `MIN_ALT_ALLELE_FRACTION=0.10`. The default observation filters are `ALLELE_MIN_BASE_QUALITY=13`, `ALLELE_MIN_MAPPING_QUALITY=20`, and `ALLELE_MIN_READ_MEAN_QUALITY=10`.

The validated default run reported:

- `16` candidate sites
- `7,143,152` accepted observations
- `2,047,476` excluded observations
- `13` singleton CIGAR-deletion bins, each supported by one query name
- `542` query names with a supplementary alignment or `SA` tag, summarized separately

The bins are descriptive CIGAR-deletion workflow output from this fixed input. Supplementary-alignment/`SA` status is a separate alignment-structure summary and does not itself define a bin.

## Mode-state oracle
The public oracle requires an explicit workflow-module state for all 14 report pages. It rejects blank expectations, undeclared states, missing status keys, and malformed values.

| Report module | State | Basis |
| --- | --- | --- |
| `mito_qc` | `ok` | long-read alignment QC executed |
| `heteroplasmy` | `ok` | filtered alternate-allele counting executed |
| `deletions` | `ok` | descriptive CIGAR-deletion screen executed |
| `copy_number` | `not_applicable` | targeted-mt input lacks a nuclear denominator |
| `feature_annotation` | `ok` | candidate feature annotation executed |
| `cosegregation` | `ok` | same-molecule co-occurrence summary executed |
| `gene_summary` | `ok` | available candidate, deletion, and co-occurrence evidence was summarized |
| `numt_qc` | `ok` | alignment-ambiguity metrics executed |
| `identity_qc` | `ok` | available fingerprint evidence was summarized |
| `variant_consequence` | `ok` | candidate consequence annotation executed |
| `circularity_qc` | `ok` | circular-reference edge-context QC executed |
| `methylation_exploratory` | `not_configured` | no bedMethyl sidecars configured |
| `phymer_haplogroup` | `not_applicable` | targeted-mt profile does not assert complete-genome context |
| `mvtool_annotation` | `not_configured` | optional network integration is disabled |

Workflow-module state is not the same as interpretation state. Here, `numt_qc` is `ok` because alignment-ambiguity metrics were calculated, while `numt_interpretation_status=not_evaluable` with `numt_interpretation_reason_code=reference_scope_mt_only` because an mt-only reference cannot support categorical NUMT interpretation.

## Filter-profile matrix
Profiles vary only the allele-observation quality filters; candidate thresholds remain fixed.

Validated candidate counts were lenient=`32`, default=`16`, and strict=`15`; accepted observations were lenient=`8,278,969`, default=`7,143,152`, and strict=`6,046,355`.

| Profile | BaseQ | MAPQ | ReadQ | Candidate sites | Accepted observations | Excluded observations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lenient | 0 | 0 | 0 | 32 | 8,278,969 | 911,659 |
| default | 13 | 20 | 10 | 16 | 7,143,152 | 2,047,476 |
| strict | 20 | 30 | 15 | 15 | 6,046,355 | 3,144,273 |

## Repeatability and claim scope
The matrix first reconstructed the seeded subset and alignment, then used that newly generated derivative for two default report invocations. Their normalized TSVs and decoded PNG pixels matched exactly, and their HTML structures matched; normalized scientific outputs also agreed across macOS and Ubuntu. This evidence supports fixed-input workflow execution, report/resource generation, descriptive filter-profile dependence, and status gating only. It does not establish diagnostic performance, sensitivity, deletion accuracy, formal NUMT classification, or population generalizability.

Tracked asset pack:
- `examples/public_validation/GM12878_ONT_longread`

References and source metadata:
- [Vandiver et al., Mitochondrion 2022, PMCID PMC9399971](https://pmc.ncbi.nlm.nih.gov/articles/PMC9399971/)
- [NCBI BioProject PRJNA809571](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA809571)
- [ENA run SRR18110025](https://www.ebi.ac.uk/ena/browser/view/SRR18110025)
