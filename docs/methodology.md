# Methodology

## Core analytical logic
The unreleased v0.3.0 release candidate uses a modular, mode-gated report workflow. Read mode and assay type determine whether each layer runs, writes a status-only output, or is marked `not_applicable`.

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

Callable depth is the sum of passing canonical `A`, `C`, `G`, and `T` observations. The alternate allele fraction is the largest non-reference canonical count divided by callable depth. Candidate selection and same-read co-occurrence use the same shared observation engine. The default excluded SAM flag mask is `3844`, overlapping paired observations are suppressed, and `ALLELE_MAX_DEPTH=0` means no pileup cap.

For GM11906, candidate counts are lenient=`33`, default=`33`, and strict=`33`, while accepted observations are lenient=`44,052,664`, default=`44,052,664`, and strict=`42,676,166`. For GM12878 qn1000, candidate counts are lenient=`32`, default=`16`, and strict=`15`, while accepted observations are lenient=`8,278,969`, default=`7,143,152`, and strict=`6,046,355`.

| Dataset | Metric | Lenient | Default | Strict |
| --- | --- | ---: | ---: | ---: |
| GM11906 | candidate sites | 33 | 33 | 33 |
| GM11906 | accepted observations | 44,052,664 | 44,052,664 | 42,676,166 |
| GM12878 qn1000 | candidate sites | 32 | 16 | 15 |
| GM12878 qn1000 | accepted observations | 8,278,969 | 7,143,152 | 6,046,355 |

## Status semantics
- `not_applicable`: the read/assay mode excludes the layer.
- `not_configured`: an optional input or integration was not enabled.
- `not_evaluable`: an output is generated, but its input scope does not support that interpretation.

For the GM12878 targeted-mt input, the within-sample mt:nuclear depth ratio and Phy-Mer are `not_applicable`, mvTool and methylation are `not_configured`, and NUMT interpretation is `not_evaluable` with reason `reference_scope_mt_only`.

## Reference and NUMT interpretation gates
Automatic whole-genome scope requires an exact GRCh37, GRCh38, GRCm38, or GRCm39 chromosome-length profile, including the assembly-specific mitochondrial length. Reduced, scaled, hybrid, or modified references resolve to `custom`; mt-only references resolve to `mt_only`. Categorical NUMT-warning output is additionally withheld if required read-stat columns, valid primary-alignment indicators, at least one primary alignment, or the full-length QC metric are unavailable. Raw computable alignment metrics remain reported, and unavailable values are represented as `NA` rather than zero.

## Repeatability scope
The v0.3.0 repeatability checks invoke the workflow twice from each provenance-verified fixed BAM, compare normalized TSV outputs, and inspect HTML/PNG structure. They do not regenerate the GM12878 query-name subset or either dataset's alignment. Results therefore support fixed-input workflow and resource repeatability only.
