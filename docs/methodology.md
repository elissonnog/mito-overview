# Methodology

## Core analytical logic
The unreleased MitoOverview v0.3.0 release candidate uses a modular, mode-gated report workflow. Read mode and assay type determine whether each layer runs, writes a status-only output, or is marked `not_applicable`.

Primary analytical layers:
1. metadata discovery and provenance capture
2. mitochondrial read extraction
3. QC and coverage profiling
4. observed alternate-allele-fraction candidate screening
5. CIGAR-deletion screening with a separate supplementary-alignment/`SA` summary
6. experimental within-sample mt:nuclear depth ratio
7. mitochondrial feature annotation
8. same-read co-occurrence
9. mitochondrial gene-summary aggregation
10. reference-scope-gated alignment-ambiguity QC
11. identity and fingerprint QC
12. variant consequence and external annotation overlays
13. circularity edge QC
14. exploratory methylation summary

## Candidate and observation filters
Candidate-site selection uses the canonical configuration keys `MIN_CALLABLE_DEPTH` and `MIN_ALT_ALLELE_FRACTION`. Package defaults are `100` reads and `0.02`, respectively. Public validation examples keep their documented candidate thresholds fixed while varying the observation-quality filters.

The default allele-observation filters are:

| Filter | Default |
| --- | ---: |
| `ALLELE_MIN_BASE_QUALITY` | 13 |
| `ALLELE_MIN_MAPPING_QUALITY` | 20 |
| `ALLELE_MIN_READ_MEAN_QUALITY` | 10 |

The v0.3.0 filter-dependence matrix uses lenient `0/0/0`, default `13/20/10`, and strict `20/30/15` BaseQ/MAPQ/readQ profiles. Candidate thresholds do not change between those profiles.

Callable depth is the sum of passing canonical `A`, `C`, `G`, and `T` observations. The alternate allele fraction is the largest non-reference canonical count divided by callable depth. The summary records the number and fraction of mitochondrial positions that reach `MIN_CALLABLE_DEPTH` and classifies candidate-evaluable coverage as `none`, `partial`, or `complete`. With no candidate-evaluable positions, the module is `not_evaluable`. With partial coverage, a zero-candidate result applies only to the positions that met the depth threshold and cannot support a whole-mtDNA absence statement. Even with complete coverage, a zero-candidate result means only that no site exceeded the configured reporting thresholds; it is not evidence of biological absence.

Candidate selection and same-read co-occurrence use the same shared observation engine. For a site pair, co-occurrence is calculated only among reads with a passing callable observation at both sites; the pair-conditioned alternate-read sets and their shared callable universe are recorded explicitly. Jaccard and directional overlap fractions with a zero denominator are serialized as `NA` and accompanied by per-statistic status fields rather than being represented as zero. A module with shared callable reads but no pair with alternate support is therefore `not_evaluable`. These conditional statistics are descriptive and are not equivalent to statistics calculated from unconditioned genome-wide candidate read sets. The default excluded SAM flag mask is `3844`. Passing observations with the same query name at one position are ranked by BaseQ and then MAPQ. A unique highest-ranked observation is retained; concordant top-quality ties use read 1 as the fragment representative when present, followed by read 2 and a stable alignment key; and discordant top-quality ties are excluded as ambiguous. Strand counts therefore describe representative passing fragments after overlap suppression and must not be interpreted as independent evidence from both mates. `excluded_overlap_ambiguous` counts excluded observations and is a subset of `excluded_overlap`; `unique_reads_excluded_overlap_ambiguous` counts unique query names across the run. `ALLELE_MAX_DEPTH=0` means no pileup cap.

For the GM11906 pseudo-bulk formed from three single-cell ATAC-seq libraries, candidate counts are lenient=`33`, default=`33`, and strict=`33`, while accepted observations are lenient=`44,048,838`, default=`44,048,838`, and strict=`42,675,832`. The pooled statistic is weighted by passing read observations from libraries with unequal callable depth; it is not an equal-weight per-cell summary or a calibrated sample heteroplasmy estimate. For GM12878 qn1000, candidate counts are lenient=`32`, default=`16`, and strict=`15`, while accepted observations are lenient=`8,278,969`, default=`7,143,152`, and strict=`6,046,355`.

| Dataset | Metric | Lenient | Default | Strict |
| --- | --- | ---: | ---: | ---: |
| GM11906 pooled scATAC | candidate sites | 33 | 33 | 33 |
| GM11906 pooled scATAC | accepted observations | 44,048,838 | 44,048,838 | 42,675,832 |
| GM12878 qn1000 | candidate sites | 32 | 16 | 15 |
| GM12878 qn1000 | accepted observations | 8,278,969 | 7,143,152 | 6,046,355 |

## Status semantics
- `not_applicable`: the read/assay mode excludes the layer.
- `not_configured`: an optional input or integration was not enabled.
- `not_evaluable`: an output is generated, but its input scope does not support that interpretation.

For the GM12878 targeted-mt input, the within-sample mt:nuclear depth ratio and Phy-Mer are `not_applicable`, mvTool and methylation are `not_configured`, and NUMT interpretation is `not_evaluable` with reason `reference_scope_mt_only`.

The experimental mt:nuclear depth ratio uses the arithmetic mean of a complete mitochondrial per-base depth profile as its numerator. A profile is complete only when it contains exactly one integer position for every coordinate from 1 through the configured mitochondrial length and every depth is finite and nonnegative. Missing, truncated, duplicate, out-of-range, fractional-position, nonnumeric, negative, or nonfinite profiles cannot define the whole-mitochondrion mean and are reported as `not_evaluable/incomplete_mito_depth_profile` with an empty numerator and ratio. The denominator is the arithmetic mean of all successfully measured fixed nuclear windows, including valid windows with observed depth zero. The ratio is not multiplied by two and is not an estimate of copies per diploid cell.

Circularity edge-depth QC applies the same input-quality invariant to `mito_depth_per_base.tsv`: the coordinate inventory must be exactly the integers `1..MT_LENGTH`, each once, and all depths and calculated regional means must be finite and nonnegative. A present but malformed profile is retained as evidence but yields `not_evaluable/incomplete_depth_profile` and `NA` edge/interior means; positions are never coerced by truncating fractional coordinates.

## Reference and NUMT interpretation gates
Automatic whole-genome scope requires exact and concordant GRCh37, GRCh38, GRCm38, or GRCm39 chromosome-length profiles in both the FASTA index and alignment header, including the assembly-specific mitochondrial length and no extra contigs. Reduced, scaled, hybrid, augmented, discordant, or modified profiles resolve conservatively and cannot enable categorical NUMT interpretation; mt-only references resolve to `mt_only`. CRAM preflight compares mitochondrial sequence-dictionary MD5 metadata with the supplied reference sequence even when the CRAM contains no mitochondrial records. Categorical NUMT-warning output is additionally withheld if required read-stat columns, valid primary-alignment indicators, at least one primary alignment, or the near-complete aligned-reference QC metric are unavailable. Raw computable alignment metrics remain reported, and unavailable values are represented as `NA` rather than zero.

For long-read QC, let \(L_{mt}\) be mitochondrial reference length and \(A_i\) the sum of CIGAR `M`, `=`, and `X` lengths for primary alignment record \(i\). CIGAR `D` and `N` operations are excluded. The compatibility field `primary_full_length_fraction` is

\[
F_{near-complete} = \frac{\sum_i I(A_i/L_{mt} \ge 0.90)}{N_{primary}}.
\]

The report labels this quantity the primary near-complete aligned-reference fraction. It is an alignment-completeness descriptor, not a direct measurement of intact molecule length.

## Feature, consequence, and identity contracts
Canonical rCRS D-loop/control-region coordinates are applied only when the configured mitochondrial sequence is an exact full-length match to bundled `NC_012920.1`. A nonmatching or unavailable sequence suppresses canonical control-region intervals and records the decision, reason, sequence lengths, and SHA-256 values. `CONTROL_REGION_ANNOTATION_MODE=synthetic_fixture_override` exists only to make deliberately noncanonical test fixtures explicit in provenance; it is not an analytical override for biological data. Gene-feature annotation remains available when the supplied annotation coordinates are compatible with the configured reference.

Consequence summaries distinguish three units. A candidate site is a unique genomic position, a candidate variant is a unique `(position, reference allele, alternate allele)` tuple, and an annotation row is one variant-feature or variant-database relationship. Overlapping genes/features and repeated external annotations can therefore produce more annotation rows than variants without inflating site or variant counts. Mean alternate allele fractions are calculated after deduplicating variants.

Identity QC compares exact retained mitochondrial SNV keys rather than all VCF records. Retained alleles must have single-base canonical `A/C/G/T` reference and alternate alleles, different reference and alternate alleles, and `FILTER=PASS` or `FILTER=.`. When samples and `GT` fields are present, an alternate allele is retained only if at least one sample genotype calls that specific ALT index; site-only VCFs are accepted under the same allele and filter rules. Multiallelic records are split by ALT, and exclusion counts are reported for filtered, non-SNV, noncanonical, reference-equal, and uncalled alleles. This is a VCF concordance/fingerprint check, not proof of sample identity.

## Optional mvTool response integrity
mvTool is disabled by default. Fixture or explicitly requested network output is accepted as successful only when every submitted unique candidate has exactly one matching returned input identifier and the response contains no unexpected or duplicate identifiers. Timeout, malformed content, or identity/cardinality mismatch produces `status=unavailable` with a reason code and never fabricates a successful annotation set.

## Exploratory bedMethyl input integrity
Optional bedMethyl rows used by the exploratory methylation layer must identify the configured mitochondrial contig and represent one zero-based base at a time (`end = start + 1`). Coordinates must be nonnegative and fall within the configured mitochondrial reference length. Plain-text and gzip-compressed inputs are detected by content. Malformed rows, wrong-contig records, and out-of-bounds coordinates fail with source and line diagnostics; missing optional sidecars remain `not_configured`.

## Repeatability scope
Each v0.3.0 clean-room platform run starts from the sealed seven-FASTQ cache. It reconstructs the three-library GM11906 paired pseudo-bulk and BWA alignment, independently recomputes the seeded GM12878 1,000-query-name subset, and rebuilds its minimap2 alignment. The two default workflow invocations for each dataset then use the same within-run derivative, compare normalized TSV outputs exactly, compare decoded PNG pixels on the same platform, and inspect HTML/PNG inventories and structure. Cross-platform acceptance compares normalized scientific tables, schemas, module states, and visual structure rather than BAM or PNG byte hashes. These checks support repeatability for the locked raw inputs, selection rule, toolchain, and workflow contract; they do not establish invariance across aligner versions, analytical sensitivity, or clinical performance.
