# mito-overview: a mode-gated workflow for mitochondrial DNA evidence reporting from aligned sequencing data

## Running title
`mito-overview` for mode-gated mtDNA reporting

## Authors
Elisson Lopes^1,* and Xiaowu Gai^1

## Affiliation
^1 Medical College of Wisconsin, Milwaukee, Wisconsin, USA

## Correspondence
* Correspondence: Elisson Lopes, Medical College of Wisconsin, Milwaukee, Wisconsin, USA

## Software version and evidence status
This draft describes the unreleased `mito-overview` version `0.3.0` release candidate at [elissonnog/mito-overview](https://github.com/elissonnog/mito-overview). The evidence reported here is a validation snapshot dated 20 July 2026. A historical public-data matrix and pre-review deterministic checks are complete for earlier clean candidate commits, whereas reruns on the exact final commit, push-event CI evidence, the final audit packet, the `v0.3.0` tag, release date, and archival DOI remain pending release gates. The manuscript therefore describes release-candidate workflow/resource behavior rather than a final release.

## Abstract
Mitochondrial DNA (mtDNA) analysis from aligned sequencing data often remains distributed across single-purpose callers, external annotation resources, and custom review steps. Long-read interpretation can additionally require structural screening, same-read co-occurrence, circular-reference checks, and alignment-ambiguity metrics, while some of these layers are not applicable to short-read or targeted-mt assays. We developed `mito-overview`, a modular, mode-gated workflow that converts BAM or CRAM inputs into synchronized tabular summaries, figures, and HTML reports. The unreleased version 0.3.0 release candidate uses a shared filtered allele-observation engine for candidate-site selection and co-occurrence analysis, an experimental within-sample mt:nuclear depth ratio only when nuclear context is evaluable, reference-scope-dependent suppression of categorical NUMT interpretation, explicit module-status semantics, and offline-by-default optional mvTool annotation. A six-key standalone input contract separates normal execution from deployment-specific assumptions. Local implementation evidence comprised 145 passing deterministic tests and four passing synthetic smoke workflows. A prespecified 13-case public matrix passed at a historical clean v0.3.0 candidate commit, including fixed-BAM repeatability and descriptive filter-dependence profiles; exact-final-commit reruns remain a release gate. In pooled GM11906 short-read data, `m.8344A>G` had 1,027 callable observations, 740 alternate observations, and an observed alternate allele fraction of 0.720545. In a deterministic 1,000-query-name GM12878 ONT subset, the workflow reported 16 candidate sites and 13 singleton CIGAR-deletion bins. These examples demonstrate bounded workflow execution and output contracts; they do not establish diagnostic performance, clinically calibrated low-fraction detection, pathogenicity, deletion accuracy, absolute mtDNA copy number, formal NUMT classification, or equivalence between sequencing modalities.

## Keywords
mitochondrial DNA; Oxford Nanopore; alternate allele fraction; deletions; NUMT; haplogroup; reporting workflow; bioinformatics software

## Introduction
Human mitochondrial DNA is a small circular genome whose analysis is biologically and technically distinct from standard linear nuclear analysis. Relevant signals can include heteroplasmic single-nucleotide variation, large deletions or rearrangements, mtDNA burden differences, and molecule-level structure. Interpretation can be distorted by extreme depth, circular-reference edge effects, and nuclear mitochondrial DNA segments (NUMTs), which can generate apparent mtDNA variation if not handled carefully [1,2]. Oxford Nanopore Technologies (ONT) long reads preserve molecule-scale information and can improve structural interpretation, but they also increase the number of analytical layers that need to be reviewed coherently [3-6].

The mtDNA software ecosystem includes specialized resources for haplogroup classification, variant interpretation, and annotated reporting. Examples include Phy-Mer for alignment-free haplogroup classification [7], HaploGrep 3 for phylogenetic classification and quality control [8], mvTool within MSeqDR for annotation and nomenclature handling [9], MitoVisualize for structure-aware interpretation [10], MToolBox for automated mtDNA reconstruction and prioritization [11], and mtDNA-Server 2 for human mtDNA variant analysis and interactive reporting [12]. ONT-focused approaches are also emerging for long-read heteroplasmy analysis and NUMT-aware read discrimination [6,13]. These resources remain the appropriate primary methods for their specialized tasks.

`mito-overview` addresses a narrower need: a compact, per-sample workflow that organizes multiple mtDNA evidence layers into one inspectable bundle. It is not intended to replace specialized callers or classifiers. The unreleased version 0.3.0 release candidate emphasizes filtered observations, explicit mode and status gating, reference-scope-aware interpretation, and reproducible reporting from fixed inputs.

## Software scope and design
The workflow follows five design principles. First, each analytical question is implemented as an independent step with synchronized TSV, figure, and HTML outputs. Second, provenance records the reference, mitochondrial contig, thresholds, modes, and input sources. Third, unsupported, unevaluable, and unconfigured analyses are represented explicitly rather than silently omitted. Fourth, the reproducible core is separated from optional human-specific enrichments and network services. Fifth, methylation is retained only as exploratory context, consistent with studies reporting no evidence for CpG methylation above modeled background in human mtDNA and no evidence for extensive non-CpG mtDNA methylation in reanalysis studies [14,15].

The implementation contains `validate`, `stage`, `extract`, 14 analytical/reporting steps, and `sync_bioinfo`. The 12 core report pages cover mitochondrial QC, alternate-allele screening, CIGAR-deletion screening, an experimental within-sample mt:nuclear depth ratio, feature annotation, same-read co-occurrence, gene-level aggregation, alignment-ambiguity/NUMT-aware QC, identity QC, consequence summaries, circularity-aware QC, and exploratory methylation. Two optional human-only pages provide a Phy-Mer-compatible haplogroup interface and mvTool-style annotation. Long-read mode enables molecule- and alignment-structure layers when their inputs are available. Short-read mode retains applicable layers and emits explicit status pages for unsupported long-read analyses. Assay type further gates analyses requiring nuclear context.

The evaluated scope is a workflow/resource package. Clair3, NanoDel, in-pipeline modkit execution, absolute copy-number estimation, and deployment-specific integrations are outside the v0.3.0 release-candidate evidence presented here. Human mtDNA has the most complete public configuration; non-human use is limited to reference-driven core modules unless separately evaluated.

## Methods

### Standalone input and validation contract
The minimal standalone configuration requires six keys: `WORK_ROOT`, `RUN_NAME`, `SAMPLE_ID`, `REF_FASTA`, `SOURCE_ALIGN_FILE`, and `MT_CONTIG`. Alignment mode is inferred from the `.bam` or `.cram` suffix, and mitochondrial length is inferred from the FASTA index when `MT_LENGTH` is omitted. Explicit generic VCF and bedMethyl sidecars take precedence over legacy `wf-human-variation` discovery. Missing optional sidecars do not terminate the core workflow and instead produce `not_configured` outputs.

Before analytical execution, validation checks the FASTA index, BAM or CRAM index, mitochondrial contig, configured or inferred mitochondrial length, and CRAM reference accessibility. A configured length must agree with the FASTA index. The validation step cannot be omitted during normal execution. This contract permits standalone BAM/CRAM operation without deployment-specific paths or inputs.

### Public-data reference, subsampling, and alignment
Both public examples were aligned to the 16,569-bp revised Cambridge Reference Sequence accession `NC_012920.1`, supplied as an mt-only FASTA. For GM11906, BWA-MEM was selected because the input comprised pooled paired-end short reads. The tracked provenance records BWA `0.7.19-r1273` and samtools `1.23.1` with the following command template:

```bash
bwa mem -t {threads} {reference_fasta} {combined_r1} {combined_r2} | samtools sort -@ {threads} -o {alignment_bam}
```

The GM12878 targeted-mt ONT run `SRR18110025` from BioProject `PRJNA809571` was generated by Vandiver et al. [16]. Because the full source contained 193,043 FASTQ records and the example was intended to provide bounded workflow evidence rather than full-run characterization, exactly 1,000 query names were selected by the smallest seeded SHA-256 scores under `smallest_sha256_seeded_query_names_v1`, using seed `mito-overview-v0.3.0-GM12878-SRR18110025`. This fixed-size hash rule was chosen to make inclusion deterministic and auditable; it was not intended to produce a statistically representative sample. Minimap2 with the `map-ont` preset was selected for these ONT long reads. The tracked provenance records minimap2 `2.31-r1302` and samtools `1.23.1` with the following mapped-only alignment command template:

```bash
minimap2 -t {threads} -ax map-ont {reference_mmi} {deterministic_subset_fastq} | samtools view -@ {threads} -b -F 4 | samtools sort -@ {threads} -o {alignment_bam}
```

### Shared filtered allele-observation method
Candidate-site selection and same-read co-occurrence use the same implementation in `mito_overview/allele_counting.py`. At a reference position, let $n_A$, $n_C$, $n_G$, and $n_T$ be the numbers of passing canonical base observations. Callable depth is

\[
D_{callable}=n_A+n_C+n_G+n_T.
\]

For reference base $r$, the alternate count is the largest non-reference canonical base count,

\[
n_{alt}=\max_{b \in \{A,C,G,T\}\setminus\{r\}} n_b,
\]

and the observed alternate allele fraction is

\[
AF_{alt}=\frac{n_{alt}}{D_{callable}}.
\]

The canonical machine-readable field is `alt_allele_fraction`; `heteroplasmy_fraction` remains only as a deprecated compatibility alias for 0.x outputs. Candidate emission requires canonical reference and alternate bases, $D_{callable} \geq D_{min}$, and $AF_{alt} \geq AF_{min}$. An all-reference position does not receive a fabricated alternate candidate. Forward and reverse alternate counts are audit fields, with `alt_count = alt_forward + alt_reverse`.

Version 0.3.0 defaults require base quality at least 13, mapping quality at least 20, and mean read quality at least 10. The default has no pileup depth cap, uses excluded SAM flag mask 3844 (unmapped, secondary, quality-control-fail, duplicate, and supplementary records), and suppresses overlapping paired-read observations. These are reporting defaults, not clinically calibrated thresholds. Package candidate defaults are `MIN_CALLABLE_DEPTH=100` and `MIN_ALT_ALLELE_FRACTION=0.02`; the public examples retain their separately documented candidate thresholds while varying only observation-quality filters. Deterministic known-answer tests include more than 8,000 accepted observations without hidden truncation, explicit depth-cap accounting when a cap is requested, all configured quality and flag exclusions, overlap suppression, exact strand accounting, and identical passing-observation logic in candidate selection and co-occurrence.

### Coverage, CIGAR-deletion screening, and same-read co-occurrence
For mitochondrial contig length $L$ and per-base depth $d_i$, mean mitochondrial depth is

\[
\overline{D}_{mt}=\frac{1}{L}\sum_{i=1}^{L}d_i.
\]

CIGAR-deletion output is a candidate structural screen rather than a structural-variant call set. The workflow scans primary and supplementary long-read alignments for CIGAR deletion operations meeting the configured size threshold, groups their event boundaries into 10-bp bins, and reports unique query-name support and size summaries. Supplementary-alignment or `SA`-tag presence is summarized separately as alignment-structure context and does not itself create a CIGAR-deletion bin. For CIGAR-deletion bin $b$, the primary-alignment support fraction is

\[
f_b=\frac{n_b}{N_{primary}},
\]

where $n_b$ is the number of unique supporting query names and $N_{primary}$ is the number of primary mitochondrial alignments scanned. No sensitivity or specificity is inferred without orthogonal structural truth.

For selected candidate sites $p$ and $q$, let $C_{pq}$ denote the reads with a passing callable observation at both sites after applying the shared allele-observation filters. The pair-conditioned alternate-read sets are

\[
A_p^{(pq)}=\{r\in C_{pq}:r_p=a_p\},\qquad
A_q^{(pq)}=\{r\in C_{pq}:r_q=a_q\},
\]

where $a_p$ and $a_q$ are the selected alternate alleles. Same-read co-occurrence is then summarized as

\[
J_{shared}(p,q)=
\frac{|A_p^{(pq)}\cap A_q^{(pq)}|}
{|A_p^{(pq)}\cup A_q^{(pq)}|}.
\]

This conditional statistic is restricted to the shared callable read universe $C_{pq}$; it is not the Jaccard index of the two unconditioned genome-wide candidate read sets. The common-universe size and pair-conditioned support counts are reported for audit. The statistic is a descriptive same-read measure, not a biological phasing benchmark, and conditioning can change its magnitude relative to an unconditioned read-set statistic.

### Within-sample mt:nuclear depth ratio
When the assay and reference provide evaluable nuclear context, the `mito_copy_number` page reports only the within-sample mt:nuclear depth ratio

\[
R_{mt:nuclear}=\frac{\overline{D}_{mt}}{\overline{D}_{nuclear}}.
\]

The ratio is not multiplied by two and is not interpreted as mtDNA copies per diploid cell. Outputs record the requested and valid nuclear-window counts. Missing or zero nuclear depth never yields a numeric zero ratio: the ratio is `NA` (an empty machine-readable value), with `status=not_evaluable` and `reason_code=no_valid_nuclear_windows`. Targeted-mt assays yield `status=not_applicable`. A deterministic known-answer fixture with mitochondrial depth 100 and nuclear depth 10 produces exactly 10.0; negative fixtures cover missing mitochondrial evidence and absent or zero nuclear denominators.

### Reference scope, alignment ambiguity, and coordinates
`REFERENCE_SCOPE` accepts `auto`, `mt_only`, `whole_genome`, or `custom`. A reference containing only the configured mitochondrial contig resolves to `mt_only`. Automatic `whole_genome` assignment requires an exact chromosome-length profile for GRCh37, GRCh38, GRCm38, or GRCm39, including the assembly-specific mitochondrial length and no additional contigs; standard chromosome-name prefixes may differ, but scaled, hybrid, incomplete, modified, or augmented profiles resolve to `custom`. The alignment header is evaluated independently. Effective `whole_genome` scope requires the FASTA index and alignment sequence dictionary to match the same recognized complete profile; a reduced, discordant, or ambiguous alignment dictionary conservatively downgrades interpretation. The same exact FASTA profile supports species inference when a generic filename and the six-key input contract are used. An explicit false whole-genome override on an incomplete, augmented, discordant, or unrecognized reference contract is rejected.

For CRAM input, preflight establishes reference identity from sequence-dictionary MD5 metadata and the supplied FASTA sequence rather than from successful decoding of an observed mitochondrial record. A missing or discordant mitochondrial reference MD5 fails preflight, including for an empty or no-mitochondrial-record CRAM, so a same-length but incorrect reference cannot pass silently.

For `mt_only` and `custom` references, raw alignment-span, mapping-quality, clipping, and supplementary-alignment metrics remain available, but categorical NUMT-risk interpretation is suppressed. The output records `numt_interpretation_status=not_evaluable` and a scope-specific reason code. Under recognized whole-genome scope, a categorical warning is calculated only when the read table contains usable MAPQ, mitochondrial aligned-fraction, soft-clip fraction, `SA`-tag, primary, and supplementary indicators; at least one valid primary alignment is present; and the QC summary contains one numeric full-length fraction. Missing, malformed, or nonnumeric required evidence yields `not_evaluable` and an explicit reason rather than zero-filled metrics or a low-risk label. The compatible report filename is retained, while the page is titled alignment-ambiguity QC. Whole-genome categorical warning calculations remain bounded heuristics and are not formal NUMT classification. The generated mitochondrial BED interval is exactly zero-based and half-open: `MT_CONTIG\t0\tMT_LENGTH`.

### Optional mvTool integration
`MVTOOL_MODE` has three explicit states: `disabled`, `fixture`, and `network`. The default is `disabled`, with an empty default URL. Disabled mode writes deterministic `not_configured` output for report page 14 without constructing an HTTP session. Fixture mode reads bundled deterministic annotations for local validation. Network mode is opt-in; an explicit network failure yields `unavailable` with a reason code, does not fabricate annotations, and does not terminate otherwise valid core reporting. A successful fixture or network response must map every submitted unique candidate exactly once and may not contain missing, duplicate, or unexpected input identifiers; response-integrity failure is reported as `unavailable` rather than partial success. Deterministic tests cover disabled no-network behavior, exact fixture content, a mocked successful network response, timeout handling, malformed-response handling, and response-identity mismatches. Live service content and availability were not validated by the public matrix.

### Status and verdict semantics
Module states are restricted to `ok`, `not_configured`, `not_applicable`, `not_evaluable`, `unavailable`, and `failed`. `not_configured` means an optional input or integration was not supplied; `not_applicable` means the read or assay mode excludes the module; `not_evaluable` means the module ran but its available reference or denominator cannot support the interpretation; `unavailable` is reserved for failure of an explicitly requested external service; and `failed` denotes required execution failure. Validation verdicts (`PASS`, `FAIL`, `XFAIL`, `SKIP`, and `BLOCKED`) are separate from module states. A case cannot pass when required input or evidence is unavailable.

## Validation design

### Local deterministic implementation evidence
Local validation was performed on macOS with Python 3.12.13, samtools/htslib 1.23.1, pysam 0.24.0, NumPy 2.5.1, pandas 3.0.3, Matplotlib 3.11.0, Pillow 12.3.0, Requests 2.34.2, and pytest 9.1.1. The deterministic unit and known-answer suite reported exactly 145 passing tests in 10.86 s. CLI step listing exited successfully; minimal generic BAM and CRAM configurations each passed strict dry-run and full workflow execution.

Four synthetic smoke workflows were run locally:

| Workflow | Observed local result |
| --- | --- |
| `tests/smoke_public_pipeline.sh` | PASS; all applicable long-read steps completed, including fixture mvTool and methylation paths |
| `tests/smoke_public_pipeline_shortread.sh` | PASS; short-read-compatible core steps completed and long-read-only layers reported `not_applicable` |
| `tests/smoke_public_pipeline_longread_nomethyl.sh` | PASS; core long-read reporting completed and methylation reported `not_configured` |
| `tests/smoke_standalone_minimal.sh` | PASS; the six-key standalone contract completed without deployment-specific inputs |

The 145-test result and four smoke results characterize the tested release-candidate state within the stated environment and evidence boundaries.

### Public-data design and provenance
The public validation matrix was executed twice at default observation filters and once under each descriptive filter profile at historical clean validation source commit `dc09114e1a0dcec2baf83d94549dfa41f3e49c8b`. Repeatability comparisons normalized TSV outputs. HTML and PNG outputs were evaluated for inventory, readability, dimensions, structure, and visual consistency rather than byte identity. These values are release-candidate supporting evidence; rerunning the matrix and binding its evidence to the exact final v0.3.0 commit remain release gates.

The GM11906 example pooled paired-end reads from `SRR10804585`, `SRR10804590`, and `SRR10804657`. The analyzed BAM SHA-256 was `53ca478465cfdaee4eb5d7e59e14d3abfb0c72d7b366afe5e96041638b6fb6f8`.

The GM12878 example used the Vandiver et al. dataset `SRR18110025` from `PRJNA809571`/`SAMN26195906` [16], but did not analyze the full run. The selection fraction was 0.00518019. The selected-name SHA-256 was `3444cc7db3dcf78bea807d8bcc6686883a7759d128288c1d26aeae077a771a19`, the subset FASTQ SHA-256 was `40e203ead1d621bfec8caa3c5d18cd1e7e70c08da27008a73364812b6871df33`, and the analyzed BAM SHA-256 was `a36e1b5cb0f0e6576e9b4eda2cca9c527610a39b287fd2379109961b5fef24c1`. The alignment contained 728 primary and 543 supplementary records from 728 mapped query names.

### Prespecified 13-case public matrix
All 13 prespecified cases passed at the historical clean validation source commit:

| Case | Evidence class | Verdict | Evidence boundary |
| --- | --- | --- | --- |
| `gm11906_default_run1` | Public default | PASS | Fixed GM11906 BAM |
| `gm11906_default_run2` | Public default | PASS | Same fixed GM11906 BAM |
| `gm11906_lenient` | Public lenient | PASS | Descriptive 0/0/0 profile |
| `gm11906_strict` | Public strict | PASS | Descriptive 20/30/15 profile |
| `gm12878_default_run1` | Public default | PASS | Fixed provenance-bound qn1000 BAM |
| `gm12878_default_run2` | Public default | PASS | Same fixed provenance-bound qn1000 BAM |
| `gm12878_lenient` | Public lenient | PASS | Descriptive 0/0/0 profile |
| `gm12878_strict` | Public strict | PASS | Descriptive 20/30/15 profile |
| `gm11906_repeatability` | Normalized TSV repeatability | PASS | Conditional on the fixed BAM and environment |
| `gm11906_visual_integrity` | HTML/PNG integrity | PASS | Structural consistency, not byte identity |
| `gm12878_repeatability` | Normalized TSV repeatability | PASS | Conditional on the fixed reduced BAM and environment |
| `gm12878_visual_integrity` | HTML/PNG integrity | PASS | Structural consistency, not byte identity |
| `filter_profiles` | Descriptive filter dependence | PASS | Not analytical sensitivity or specificity |

Both normalized repeat diffs and both visual-structure diffs were empty. Each default normalized summary inventory contained 46 files; default public output contained 14 HTML pages and 15 report PNGs before representative figures were selected. The repeated invocations began from the same provenance-verified BAMs. They did not repeat query-name selection or alignment, so repeatability is conditional on the fixed BAMs and tested environment and does not establish reconstruction invariance across aligner or software versions.

### Observation filter profiles
Candidate thresholds remained fixed within each dataset while BaseQ/MAPQ/readQ filters varied from lenient 0/0/0, to default 13/20/10, to strict 20/30/15.

| Dataset | Profile | BaseQ/MAPQ/readQ | Candidate sites | Accepted observations | Excluded observations | `m.8344A>G` observed alternate allele fraction |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| GM11906 | lenient | 0/0/0 | 33 | 44,052,664 | 7,293,106 | 0.720545 |
| GM11906 | default | 13/20/10 | 33 | 44,052,664 | 7,293,106 | 0.720545 |
| GM11906 | strict | 20/30/15 | 33 | 42,676,166 | 8,669,604 | 0.733469 |
| GM12878 qn1000 | lenient | 0/0/0 | 32 | 8,278,969 | 911,659 | NA |
| GM12878 qn1000 | default | 13/20/10 | 16 | 7,143,152 | 2,047,476 | NA |
| GM12878 qn1000 | strict | 20/30/15 | 15 | 6,046,355 | 3,144,273 | NA |

These changes quantify filter dependence in the fixed inputs. They are not estimates of sensitivity, specificity, limit of detection, or a clinical reporting threshold.

## Results

### GM11906 reduced short-read proof of principle
The GM11906 workflow used `READ_MODE=short`, `ASSAY_TYPE=targeted_mt`, `MIN_CALLABLE_DEPTH=10`, and `MIN_ALT_ALLELE_FRACTION=0.20`. At the default 13/20/10 observation filters, it reported 33 candidate sites, 44,052,664 accepted canonical-base observations, and 7,293,106 accounted excluded observations. The literature-associated `m.8344A>G` row had exactly 1,027 callable observations, 740 alternate observations, an observed alternate allele fraction of 0.720545, 305 forward alternate observations, and 435 reverse alternate observations; the corresponding depth/count/fraction audit tuple is `1027/740/0.720545`. Its feature and consequence labels were `MT-TK` and `tRNA_variant`.

The example pools public GM11906 scATAC-seq runs associated with the single-cell mtDNA/chromatin study by Lareau and colleagues [17]. Public sample metadata identify GM11906 as a lymphoblastoid cell line carrying the literature-associated marker [19], and `m.8344A>G` has been reported in MERRF-associated `MT-TK` context [18]. The result demonstrates representation of that marker in a reduced short-read workflow. It is not a modality-matched benchmark, independent pathogenicity confirmation, calibrated allele-fraction study, or clinical validation.

### GM12878 deterministic reduced ONT proof of principle
The GM12878 workflow used the deterministic, provenance-bound 1,000-query-name subset described above with `READ_MODE=long`, `ASSAY_TYPE=targeted_mt`, `MIN_CALLABLE_DEPTH=100`, `MIN_ALT_ALLELE_FRACTION=0.10`, and default 13/20/10 observation filters. It reported 16 candidate sites, 7,143,152 accepted canonical-base observations, 2,047,476 accounted excluded observations, mean mitochondrial depth 545.484, median depth 544.0, and eight selected co-occurrence sites.

The structural screen produced 13 singleton CIGAR-deletion bins; the largest binned median CIGAR-deletion length was 1,394 bp, and the maximum bin support fraction relative to primary query names was 0.001374. Five query names had at least one qualifying CIGAR deletion. Separately, 542 query names had a supplementary alignment or `SA` tag. These are descriptive CIGAR-deletion and alignment-structure summaries without orthogonal structural truth and do not establish deletion-calling accuracy.

The targeted-mt and mt-only boundaries were explicit: the within-sample mt:nuclear depth ratio and Phy-Mer were `not_applicable`; mvTool and methylation were `not_configured`; and NUMT interpretation was `not_evaluable` with `reason_code=reference_scope_mt_only`. Raw alignment-ambiguity metrics remained inspectable, but no low/moderate/high NUMT-risk category was emitted. Candidate sites and their strong same-read co-occurrence were not independently validated variants or haplotypes. Because only 1,000 deterministically selected query names were analyzed, these outputs are neither full-run estimates nor evidence of statistical representativeness.

### Relation to published ONT mtDNA evidence
Published evidence supports the potential value of ONT reads for structural interpretation and analysis of moderate-fraction mtDNA variation in validated assay contexts. Long-read sequencing has resolved deletions and rearrangements, including complex structures that can resemble single-deletion events under less resolved inspection [3,4]. An ONT heteroplasmy study reported strong correlation above its evaluated threshold but also underreporting at high variant fractions and a need for stringent validation before diagnostic use [5]. These studies provide context; they do not validate `mito-overview` performance.

NUMT-aware interpretation remains important because NUMTs are widespread and dynamic in human genomes [1], and apparent mtDNA findings can change after improved NUMT-aware review [2]. MitSorter illustrates the value of explicit read-level discrimination strategies for ONT data [13]. In `mito-overview`, the corresponding output remains warning-oriented alignment-ambiguity QC, with categorical interpretation suppressed when reference scope is insufficient.

## Example figures

### Figure 1. GM12878 public ONT long-read report-native views
![Figure 1. GM12878 public ONT long-read report-native views](figures/figure0_workflow_architecture.png)

Representative outputs from the fixed deterministic 1,000-query-name GM12878 targeted-mt subset. (A) Mitochondrial depth profile. (B) Observed alternate allele fraction by mitochondrial position, with the configured candidate threshold shown by the dashed line. (C) Jaccard matrix for alternate-supporting read sets at eight selected sites. (D) Alignment-ambiguity QC showing aligned mitochondrial-contig fraction versus mapping quality. The montage is workflow evidence from a reduced input, not an analytical performance benchmark. Candidate sites are not independently validated variants or haplotypes, and the mt-only reference scope does not support categorical NUMT classification.

### Figure 2. GM11906 public short-read workflow proof of principle
![Figure 2. GM11906 public short-read workflow proof of principle](figures/figure2_shortread_public_validation_montage.png)

Representative outputs from pooled public GM11906 short-read/scATAC-derived reads under the targeted-mt compatibility profile. (A) Observed alternate allele fraction by mitochondrial position, with the 0.20 candidate threshold shown by the dashed line. (B) Candidate-site counts by mitochondrial feature. (C) Feature-level candidate burden summary; long-read-only co-occurrence and CIGAR-deletion-bin-overlap series are inactive in this profile. (D) Candidate counts by consequence class. The underlying default summary contains `m.8344A>G` at 1,027 callable observations, 740 alternate observations, and observed alternate allele fraction 0.720545. The montage demonstrates report generation and marker representation, not modality equivalence, calibrated detection, evaluation of the within-sample mt:nuclear depth ratio, NUMT discrimination, or validation of long-read-only layers.

## Discussion
The unreleased `mito-overview` v0.3.0 release candidate is a software/resource contribution for mode-gated mtDNA evidence synthesis. Its principal contribution is the synchronization of filtered candidate observations, structural screens, the within-sample mt:nuclear depth ratio when evaluable, feature summaries, warning-oriented QC, and explicit status pages in a per-sample bundle. The shared observation engine and scope-aware status contracts make numerical outputs and unavailable interpretations more directly auditable.

The evidence supports implementation behavior under deterministic fixtures, four synthetic workflows, and two bounded public examples. It also supports normalized table repeatability and visual-structure consistency when workflows are rerun from the same fixed BAMs. It does not support analytical accuracy, clinical validity, a low-fraction detection limit, pathogenicity classification, deletion sensitivity or specificity, absolute mtDNA copy number, formal NUMT classification, biological phasing accuracy, or equivalence of long- and short-read modes.

Additional limitations arise from the public inputs. GM11906 is a pooled, mt-only, reduced short-read proof of principle. GM12878 is a deterministic 1,000-query-name subset of a targeted-mt run rather than the full dataset or a statistically representative sample. Neither example includes orthogonal truth for all reported candidates or CIGAR-deletion bins. External mvTool content was not evaluated live, methylation remains exploratory, and deployment-specific environments were not evaluated.

## Availability and release status
The source repository, synthetic fixtures, public proof-of-principle asset packs, validation scripts, and manuscript source are available at [https://github.com/elissonnog/mito-overview](https://github.com/elissonnog/mito-overview). Optional Phy-Mer and mvTool resources are not bundled as core dependencies.

Version `0.3.0` remains an unreleased release candidate. No final `v0.3.0` tag, release date, or version-specific archival DOI is claimed in this manuscript; the reported results are release-candidate evidence within the stated validation boundaries.

## Author contributions
E.L. designed and implemented the public workflow, generated validation assets, performed the analyses, and drafted the manuscript. X.G. supervised the project, contributed mitochondrial-disease and mtDNA-analysis context, and reviewed the scientific framing.

## Funding
Not declared.

## Competing interests
The authors declare no competing interests.

## Data and code availability
Public data accessions, fixed-input provenance, hashes, result tables, and source pages for the GM11906 and GM12878 examples are recorded in the repository. The public examples support workflow reproducibility and output-contract review only. A version-specific DOI and final `v0.3.0` archive have not yet been issued and are not claimed for this release candidate.

## References
1. Wei W, et al. Nuclear-embedded mitochondrial DNA sequences in 66,083 human genomes. *Nature*. 2022. [PubMed](https://pubmed.ncbi.nlm.nih.gov/36198798/)
2. Fleischmann Z, et al. Reanalysis of mtDNA mutations of human primordial germ cells (PGCs) reveals NUMT contamination and suggests that selection in PGCs may be positive. *Mitochondrion*. 2024. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37914096/)
3. Frascarelli C, et al. Nanopore long-read next-generation sequencing for detection of mitochondrial DNA large-scale deletions. *Front Genet*. 2023. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37456669/)
4. Lopriore E, et al. An inherited mtDNA rearrangement, mimicking a single large-scale deletion, associated with MIDD and a primary cardiological phenotype. *Mitochondrion*. 2025. [PubMed](https://pubmed.ncbi.nlm.nih.gov/40164291/)
5. Slapnik B, et al. The quality and detection limits of mitochondrial heteroplasmy by long read nanopore sequencing. *Sci Rep*. 2024. [Nature](https://www.nature.com/articles/s41598-024-78270-0)
6. Jiang L, et al. CmVCall: An automated and adjustable nanopore analysis pipeline for heteroplasmy detection of the control region in human mitochondrial genome. *Forensic Sci Int Genet*. 2023. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37595417/)
7. Navarro-Gomez D, et al. Phy-Mer: a novel alignment-free and reference-independent mitochondrial haplogroup classifier. *Bioinformatics*. 2015. [PubMed](https://pubmed.ncbi.nlm.nih.gov/25505086/)
8. Schönherr S, et al. HaploGrep 3 - an interactive haplogroup classification and analysis platform. *Nucleic Acids Res*. 2023. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37070190/)
9. Shen L, et al. MSeqDR mvTool: a mitochondrial DNA web and API resource for comprehensive variant annotation, universal nomenclature collation, and reference genome conversion. *Hum Mutat*. 2018. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5992054/)
10. Lake NJ, et al. MitoVisualize: a resource for analysis of variants in human mitochondrial RNAs and DNA. *Bioinformatics*. 2022. [PubMed](https://pubmed.ncbi.nlm.nih.gov/35561159/)
11. Calabrese C, et al. MToolBox: a highly automated pipeline for heteroplasmy annotation and prioritization analysis of human mitochondrial variants in high-throughput sequencing. *Bioinformatics*. 2014. [PubMed](https://pubmed.ncbi.nlm.nih.gov/25028726/)
12. Weissensteiner H, et al. mtDNA-Server 2: advancing mitochondrial DNA analysis through highly parallelized data processing and interactive analytics. *Nucleic Acids Res*. 2024. [PubMed](https://pubmed.ncbi.nlm.nih.gov/38709886/)
13. Cox SN, et al. MitSorter: a standalone tool for accurate discrimination of mtDNA and NuMT ONT reads based on differential methylation. *Bioinformatics Advances*. 2025. [PubMed](https://pubmed.ncbi.nlm.nih.gov/40688360/)
14. Bicci I, et al. Single-molecule mitochondrial DNA sequencing shows no evidence of CpG methylation in human cells and tissues. *Nucleic Acids Res*. 2021. [PubMed](https://pubmed.ncbi.nlm.nih.gov/34850165/)
15. Guitton R, et al. No evidence of extensive non-CpG methylation in mtDNA. *Nucleic Acids Res*. 2022. [PubMed](https://pubmed.ncbi.nlm.nih.gov/35979955/)
16. Vandiver AR, Pielstick B, Gilpatrick T, et al. Long read mitochondrial genome sequencing using Cas9-guided adaptor ligation. *Mitochondrion*. 2022;65:176-183. [PMC: PMC9399971](https://pmc.ncbi.nlm.nih.gov/articles/PMC9399971/)
17. Lareau CA, Ludwig LS, Muus C, et al. Massively parallel single-cell mitochondrial DNA genotyping and chromatin profiling. *Nat Biotechnol*. 2021. [Nature](https://www.nature.com/articles/s41587-020-0645-6)
18. Shoffner JM, Lott MT, Lezza AMS, et al. Myoclonic epilepsy and ragged-red fiber disease (MERRF) is associated with a mitochondrial DNA tRNA(Lys) mutation. *Cell*. 1990. [PubMed](https://pubmed.ncbi.nlm.nih.gov/2112427/)
19. Coriell Institute for Medical Research. GM11906 sample record. [Coriell](https://www.coriell.org/0/Sections/Search/Sample_Detail.aspx?Ref=GM11906)
