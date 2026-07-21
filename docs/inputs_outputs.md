# MitoOverview Input and Output Contract

This document is the v0.3.0 schema index for the public `mito-overview` workflow. It describes the major input classes, output folders, and expected report artifacts used for workflow/resource review.

## Major Inputs
| Input | Required | Role | Notes |
| --- | --- | --- | --- |
| aligned BAM or CRAM | yes | source alignment for mitochondrial extraction and report generation | must be indexed; sequence dictionary is evaluated independently for effective reference scope |
| reference FASTA | yes | coordinate system and base reference | must be indexed; CRAM requires sequence-MD5-compatible reference identity even when no mtDNA records are present |
| mitochondrial contig name | yes | selects the mtDNA reference sequence | examples use `NC_012920.1`; HPC human WGS runs may use `MT` depending on reference |
| mitochondrial contig length | inferred | bounds per-base summaries and report labels | inferred from FASTA index; an explicitly supplied conflicting value fails preflight |
| mitochondrial gene annotation | optional | feature/gene/consequence summaries | public package includes a human mtDNA annotation resource; absence produces an explicit `not_configured` feature-annotation page |
| run configuration env file | yes | sample ID, paths, canonical thresholds, species/build, read mode, assay type | consumed by `scripts/run_mito_pipeline.sh` and package CLI |
| bedmethyl-derived mtDNA input | optional | exploratory methylation page | absent inputs produce status-only output |
| phased/no-phased sidecar summaries | optional | identity QC | absent inputs produce status-only output or not-applicable page by mode |
| ClinVar or annotation VCF | optional | variant consequence overlay | absent inputs leave ClinVar fields as `NA` |
| Phy-Mer-style or mvTool-style inputs | optional | human-only enrichment interfaces | public repository validates report wiring with fixtures unless live external use is configured |

Whole-genome interpretation is enabled only when the FASTA index and alignment sequence dictionary independently match the same recognized complete human or mouse chromosome-length profile with no additional contigs. A reduced, augmented, discordant, or ambiguous dictionary cannot unlock categorical NUMT interpretation. For CRAM, preflight verifies sequence-dictionary MD5 metadata against the supplied FASTA rather than relying on decoding a record from the mitochondrial contig.

## Output Folder Contract
| Folder | Role | Typical contents |
| --- | --- | --- |
| `logs/` | execution trace | per-step stdout/stderr and wrapper logs when configured |
| `stage/` | staged assets | mitochondrial subset BAM and run metadata |
| `output/summary/` | machine-readable tables | TSV outputs from every active or status-only report layer |
| `output/figures/` | report-native figures | PNG figures used by HTML reports and manuscript montages |
| `output/report/` | human-readable pages | numbered HTML pages for the report bundle |
| final sample bundle | collaborator/reviewer handoff | synchronized copy of the output tree plus selected staged assets |

## Report Pages and Principal Outputs
| Page | Step | Principal TSV outputs | Principal figures | Status behavior |
| --- | --- | --- | --- | --- |
| `01_mito_qc.html` | `mito_qc` | `mito_qc_summary.tsv`, `mito_depth_per_base.tsv`, `mito_read_stats.tsv` | `mito_depth_profile.png`, `mito_read_length_hist.png` | active in supported modes |
| `02_mito_heteroplasmy.html` | `heteroplasmy` | `mito_heteroplasmy_summary.tsv`, `mito_heteroplasmy_candidates.tsv`, `mito_heteroplasmy_all_sites.tsv` | `mito_heteroplasmy_landscape.png`, candidate bar plot when available | active in supported modes |
| `03_mito_deletions.html` | `deletions` | `mito_deletion_summary.tsv`, `mito_deletion_events.tsv`, `mito_deletion_clusters.tsv`, `mito_deletion_read_flags.tsv` | `mito_deletion_clusters.png` when clusters exist | not applicable in reduced short-read mode |
| `04_mito_copy_number.html` | `copy_number` | `mito_copy_number_summary.tsv`, `mito_copy_number_windows.tsv` | `mito_copy_number_proxy.png` | not applicable for targeted-mt modes without nuclear context |
| `05_mito_feature_annotation.html` | `feature_annotation` | `mito_feature_catalog.tsv`, `mito_feature_overlap_candidates.tsv`, `mito_feature_annotation_summary.tsv` | `mito_feature_annotation.png` | active when candidate/feature data are available |
| `06_mito_cosegregation.html` | `cosegregation` | `mito_cosegregation_selected_sites.tsv`, `mito_cosegregation_pairwise.tsv`, `mito_cosegregation_summary.tsv` | `mito_cosegregation_heatmap.png` | pair statistics use reads callable at both sites; not applicable in reduced short-read mode |
| `07_mito_gene_summary.html` | `gene_summary` | `mito_gene_summary.tsv`, `mito_gene_summary_overview.tsv` when generated | `mito_gene_summary_overview.png` | active when upstream summaries exist |
| `08_mito_numt_qc.html` | `numt_qc` | `mito_numt_qc_summary.tsv` | `mito_numt_qc_mapq_vs_span.png`, `mito_numt_qc_metric_bars.png` | not applicable in reduced short-read mode; targeted-mt long-read interpretation can be `not_evaluable` |
| `09_mito_identity_qc.html` | `identity_qc` | identity/fingerprint summary tables | concordance plot when sidecars exist | conditional or not applicable |
| `10_mito_variant_consequence.html` | `variant_consequence` | `mito_variant_consequence_candidates.tsv`, `mito_variant_consequence_class_summary.tsv`, `mito_variant_consequence_clinvar_summary.tsv`, `mito_variant_consequence_summary.tsv` | `mito_variant_consequence_classes.png` | active when candidates exist; status-only otherwise |
| `11_mito_circularity_qc.html` | `circularity_qc` | `mito_circularity_qc_summary.tsv` | `mito_circularity_edge_metrics.png` | not applicable in reduced short-read mode |
| `12_mito_methylation_exploratory.html` | `methylation_exploratory` | `mito_methylation_exploratory_summary.tsv` and track summaries when available | methylation context plots when available | `not_applicable` by mode or `not_configured` when sidecars are absent |
| `13_mito_phymer_haplogroup.html` | `phymer_haplogroup` | `mito_phymer_haplogroup_summary.tsv`, ranking tables when available | haplogroup score plot when available | optional human-only or not applicable by assay |
| `14_mito_mvtool_annotation.html` | `mvtool_annotation` | `mito_mvtool_annotation_summary.tsv`, annotation tables when available | MITOMAP/status distribution plots when available | `not_configured` when the optional integration is disabled |

## Important Thresholds and Units
| Metric | Unit | Default or validation value | Output location |
| --- | --- | --- | --- |
| candidate callable-depth threshold | reads | default `MIN_CALLABLE_DEPTH=100`; GM11906 uses `10` | config, `mito_heteroplasmy_summary.tsv` |
| candidate alternate-fraction threshold | alternate fraction | default `MIN_ALT_ALLELE_FRACTION=0.02`; GM12878 uses `0.10`; GM11906 uses `0.20` | config, heteroplasmy report |
| allele minimum base quality | Phred | default `ALLELE_MIN_BASE_QUALITY=13` | config, heteroplasmy summary |
| allele minimum mapping quality | Phred | default `ALLELE_MIN_MAPPING_QUALITY=20` | config, heteroplasmy summary |
| allele minimum read mean quality | Phred | default `ALLELE_MIN_READ_MEAN_QUALITY=10` | config, heteroplasmy summary |
| deletion minimum size | bp | default `DELETION_MIN_SIZE=100` | config, deletion summary |
| deletion support fraction | fraction of primary reads | calculated as supporting unique read names divided by primary mitochondrial reads | `mito_deletion_clusters.tsv` |
| same-read co-occurrence site limit | sites | top `8` candidate sites | `mito_cosegregation_selected_sites.tsv` |
| same-read pair floor | reads | `25` shared reads | `mito_cosegregation_pairwise.tsv` |
| NUMT-warning MAPQ threshold | MAPQ | low `<20`, very low `<5` | `mito_numt_qc_summary.tsv` |
| NUMT-warning span threshold | aligned fraction | short span `<0.50` | `mito_numt_qc_summary.tsv` |
| copy-number window size | bp | default `100,000` | `mito_copy_number_windows.tsv` |

The v0.3.0 filter profiles are lenient BaseQ/MAPQ/readQ `0/0/0`, default `13/20/10`, and strict `20/30/15`. Candidate thresholds remain fixed within each dataset's profile comparison.

## Status Values
| Status | Meaning |
| --- | --- |
| `not_applicable` | the read/assay mode excludes the layer |
| `not_configured` | an optional input or integration was not enabled |
| `not_evaluable` | output exists, but the input scope does not support the interpretation |

For GM12878 targeted-mt, copy number and Phy-Mer are `not_applicable`, mvTool and methylation are `not_configured`, and NUMT interpretation is `not_evaluable` with reason `reference_scope_mt_only`.

## Reproducibility Checks
A reviewer should be able to audit a run by checking these conditions:

1. `python -m mito_overview.cli --list-steps` exposes the declared workflow steps.
2. Every active module writes its expected TSV and HTML outputs.
3. Every unsupported module writes a stable status or `not_applicable` output rather than silently disappearing.
4. Public proof-of-principle scripts record read mode, assay type, reference, contig, and thresholds.
5. Key public-example values match the v0.3.0 validation matrix within the documented threshold-specific context.
6. HTML and PNG outputs are compared by existence and visual/content tolerance, not byte identity.
7. Repeatability is described as conditional on the provenance-verified fixed BAM; subset and alignment regeneration are separate operations.

## Claim Boundary
This output contract supports workflow execution, report/resource generation, explicit status handling, and fixed-input reviewer inspection.
