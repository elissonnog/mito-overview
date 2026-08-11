# Public reduced short-read workflow evidence

The repository tracks a GM11906 compatibility example made by pooling three public single-cell ATAC-seq libraries into a pseudo-bulk for the reduced short-read report profile. The frozen v0.3.0 scientific protocol was validated at commit `b116430e037f4ff2f9cf6f6f3ba66150cce1303f`; v0.3.1 changes release/report tooling only and preserves these inputs, algorithms, thresholds, schemas, oracles, and normalized biological results.

## Evidence scope
- validated scientific-protocol commit: `b116430e037f4ff2f9cf6f6f3ba66150cce1303f`
- validation result: `36/36` release cases, `366/366` scientific oracle assertions, and `206/206` normalized cross-platform comparisons passed
- tracked-output status: regenerated from the sealed seven-FASTQ matrix and bound to the verified v0.3.0 validation packet
- source runs: `SRR10804585`, `SRR10804590`, and `SRR10804657`
- sample context: three single-cell ATAC-seq libraries from one GM11906 lymphoblastoid line, pooled as a pseudo-bulk
- profile: `READ_MODE=short`, `ASSAY_TYPE=targeted_mt`
- runner: `scripts/run_public_shortread_validation_gm11906.sh`

The three public runs (`GSM4238454`, `GSM4238459`, and `GSM4238526`) were combined for the reduced-profile report. GEO identifies all three as single-cell ATAC-seq libraries from GM11906. The local matrix rebuilt the pooled paired FASTQs and BWA-MEM alignment from the six sealed FASTQs before running the report profiles.

## v0.3.1 release binding

The values below are exact observations from the completed v0.3.0 scientific protocol, not provisional local estimates. The unchanged protocol was rerun for the v0.3.1 package identity from its exact release commit on macOS and Ubuntu. Authoritative assets are available from the [`v0.3.1` GitHub release](https://github.com/elissonnog/mito-overview/releases/tag/v0.3.1), [validation packet](https://github.com/elissonnog/mito-overview/releases/download/v0.3.1/mito-overview-v0.3.1-validation.zip), and [validation report](https://github.com/elissonnog/mito-overview/releases/download/v0.3.1/MitoOverview_v0.3.1_release_validation_report.pdf).

## Default profile
The example-specific candidate thresholds are `MIN_CALLABLE_DEPTH=10` and `MIN_ALT_ALLELE_FRACTION=0.20`. The default observation filters are `ALLELE_MIN_BASE_QUALITY=13`, `ALLELE_MIN_MAPPING_QUALITY=20`, and `ALLELE_MIN_READ_MEAN_QUALITY=10`.

The validated default run reported:

- `33` candidate sites
- `44,048,838` accepted observations
- `7,296,932` excluded observations
- `m.8344A>G` at depth `1,027`, with `740` alternate observations and pooled observed alternate allele fraction `0.720545`
- `MT-TK` feature context and `tRNA_variant` consequence output for position `8344`

The accompanying focused mpileup uses `-A -B -d 0 -Q 13 -q 20 --ff 3844`
with standard overlap removal. It reports canonical
counts `A=285`, `C=0`, `G=740`, and `T=2` at depth `1,027`. This matched record
is provided for read-level inspection, not as an independent caller benchmark;
mpileup does not reproduce the workflow's mean-read-quality filter or complete
equal-rank tie-resolution contract.

## Filter-profile matrix
Profiles vary only the allele-observation quality filters; candidate thresholds remain fixed.

Validated candidate counts were lenient=`33`, default=`33`, and strict=`33`; accepted observations were lenient=`44,048,838`, default=`44,048,838`, and strict=`42,675,832`.

| Profile | BaseQ | MAPQ | ReadQ | Candidate sites | Accepted observations | Excluded observations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lenient | 0 | 0 | 0 | 33 | 44,048,838 | 7,296,932 |
| default | 13 | 20 | 10 | 33 | 44,048,838 | 7,296,932 |
| strict | 20 | 30 | 15 | 33 | 42,675,832 | 8,669,938 |

## Mode-state oracle
The public oracle now requires an explicit expected workflow-module state for every one of the 14 report pages. Blank expected states, unknown states, missing status keys, and malformed status values fail validation rather than being skipped.

| Report module | State | Basis |
| --- | --- | --- |
| `mito_qc` | `ok` | short-read alignment QC executed |
| `heteroplasmy` | `ok` | filtered alternate-allele counting executed |
| `deletions` | `not_applicable` | current deletion screen is long-read-specific |
| `copy_number` | `not_applicable` | targeted-mt input lacks a nuclear denominator |
| `feature_annotation` | `ok` | candidate feature annotation executed |
| `cosegregation` | `not_applicable` | same-molecule co-occurrence is long-read-specific |
| `gene_summary` | `ok` | available candidate evidence was summarized |
| `numt_qc` | `not_applicable` | current alignment-ambiguity heuristics are long-read-specific |
| `identity_qc` | `not_applicable` | current identity workflow is long-read-specific |
| `variant_consequence` | `ok` | candidate consequence annotation executed |
| `circularity_qc` | `not_applicable` | current edge-context heuristics are long-read-specific |
| `methylation_exploratory` | `not_applicable` | ONT bedMethyl evidence does not apply to this profile |
| `phymer_haplogroup` | `not_applicable` | targeted-mt profile does not assert complete-genome context |
| `mvtool_annotation` | `not_configured` | optional network integration is disabled |

Workflow-module state and interpretation state are separate. Because `numt_qc` is skipped for this short-read profile, NUMT interpretation is explicitly recorded in the oracle as `not_applicable` with reason `module_not_applicable`; it is not treated as a blank or silently omitted expectation. The status-only module output does not carry a nested interpretation metric, so the oracle derives this one interpretation state only from the verified `numt_qc=not_applicable` gate.

## Repeatability and claim scope
The matrix first reconstructed the pooled FASTQs and alignment, then used that newly generated derivative for two default report invocations. Their normalized TSVs and decoded PNG pixels matched exactly, and their HTML structures matched; normalized scientific outputs also agreed across macOS and Ubuntu. This separates report repeatability from alignment variability while still testing the raw-FASTQ derivation once in the matrix. The evidence supports workflow execution, report/resource generation, representation of the known public `m.8344A>G` marker, descriptive filter dependence, and mode gating only. It does not establish sensitivity, pathogenicity, diagnostic validity, or short-read WGS performance, and the pooled alternate allele fraction is not a per-cell value or calibrated sample heteroplasmy estimate.

Tracked asset pack:
- `examples/public_validation/GM11906_MERRF_shortread`

References and source metadata:
- [Lareau et al., Nat Biotechnol 2021](https://www.nature.com/articles/s41587-020-0645-6)
- [GEO `GSM4238454`](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238454)
- [GEO `GSM4238459`](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238459)
- [GEO `GSM4238526`](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238526)
- [Coriell GM11906](https://www.coriell.org/0/Sections/Search/Sample_Detail.aspx?Ref=GM11906)
