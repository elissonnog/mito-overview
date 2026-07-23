# MitoOverview v0.3.0 Historical Candidate Snapshot

> **Historical local snapshot; not release evidence.** The local results below
> describe a pre-push candidate exercise and regenerated lightweight public
> assets. They are not bound to `FINAL_SHA`, a release tag, or the final
> cross-platform packet. The active release gate is defined in
> [`clean_room_validation_protocol_v0.3.0.md`](clean_room_validation_protocol_v0.3.0.md),
> and its current state is tracked in
> [`reproducibility_run_ledger.md`](reproducibility_run_ledger.md).

## Document status

This document preserves useful methods and provisional observations from an
unreleased MitoOverview v0.3.0 candidate. It must not be cited as the final
release-validation report. The authoritative report is generated outside Git
only after the exact merged commit passes macOS and Ubuntu clean-room
reproduction, packet verification, tag, and release-asset checks as
`MitoOverview_v0.3.0_release_validation_report.md`, with matching DOCX and PDF.

- Evidence date: 2026-07-21
- Repository: https://github.com/elissonnog/mito-overview
- Candidate version: `0.3.0`
- Release status: **unreleased release candidate**
- Validation status: **historical local characterization only; exact-final-commit cross-platform validation pending**

The final `v0.3.0` tag has not been assigned. Zenodo, an archival DOI, and manuscript work are outside this GitHub-only validation gate.

## Claim boundary

The unreleased MitoOverview v0.3.0 release candidate is evaluated as a reproducible, mode-gated workflow/resource package for mitochondrial evidence reporting. The evidence in this record does not establish diagnostic performance, clinically calibrated low-allele-fraction detection, pathogenicity classification, deletion sensitivity or specificity, absolute mtDNA copy number, formal NUMT classification, or equivalence between sequencing modalities.

Clair3, NanoDel, in-pipeline modkit execution, absolute copy-number estimation, and deployment-specific integrations are outside the evaluated scope. The public examples are proof-of-principle workflow executions, not clinical validation cohorts.

## Corrections and computational definitions

### 1. Filtered alternate-allele observations

The shared observation engine in `mito_overview/allele_counting.py` is used by candidate-site counting and co-segregation. Callable depth is the number of passing canonical base observations:

\[
D_{callable}=n_A+n_C+n_G+n_T
\]

For reference base \(r\), the alternate count is the largest non-reference canonical base count and the reported alternate allele fraction is:

\[
AF_{alt}=\frac{n_{alt}}{D_{callable}}
\]

The public defaults are base quality 13, mapping quality 20, mean read quality 10, no pileup depth cap, excluded SAM flag mask 3844, and overlap suppression enabled. Passing observations with the same query name and position are ranked by BaseQ and then MAPQ. Discordant top-quality ties are excluded as ambiguous; concordant ties use read 1 as the representative fragment when present, followed by read 2 and a stable alignment key. Forward/reverse counts therefore describe representative fragments after overlap suppression, not independent observations from both mates. `excluded_overlap_ambiguous` counts excluded observation records, whereas `unique_reads_excluded_overlap_ambiguous` counts unique query names. These are reporting defaults rather than clinically calibrated thresholds. `alt_allele_fraction` is canonical; `heteroplasmy_fraction` is retained as a deprecated 0.x compatibility alias.

The summary records candidate-evaluable positions and classifies candidate coverage as `none`, `partial`, or `complete`. If canonical observations exist but no position reaches `MIN_CALLABLE_DEPTH`, the layer emits `status=not_evaluable` and `reason_code=no_positions_meet_min_callable_depth`. Under partial coverage, a zero-candidate result is restricted to the evaluable positions and cannot support a whole-mtDNA absence statement. Under complete coverage, a zero-candidate result means only that no site exceeded the configured thresholds. Same-read co-occurrence ratios are also undefined when their set denominator is zero; those values are serialized as `NA` with per-statistic status fields, rather than as numerical zero.

Deterministic tests verify:

- more than 8,000 accepted observations without a hidden truncation;
- exact A/C/G/T counts and callable depth;
- `alt_count = alt_forward + alt_reverse`;
- base-quality, mapping-quality, read-quality, duplicate, secondary, supplementary, unmapped, and overlap exclusions;
- deterministic accounting when a depth cap is explicitly configured;
- identical passing read/base logic in candidate selection and co-segregation;
- no fabricated alternate candidate at all-reference positions.

Primary tests: `tests/test_allele_counting.py`, `tests/test_table_contracts.py`, and `tests/test_config_and_inputs.py`.

### 2. mvTool network control

`MVTOOL_MODE` accepts `disabled`, `fixture`, and `network`; the default is `disabled`, with an empty default URL. Disabled mode emits deterministic `not_configured` output for report page 14 without constructing an HTTP session. Fixture mode supports deterministic CI. Explicit network failures emit `unavailable` and a reason code without fabricating annotations or terminating otherwise valid core reporting. Fixture or network success additionally requires a one-to-one, unique, complete mapping between submitted candidates and returned input identifiers; missing, duplicate, or unexpected identifiers produce `unavailable` rather than a partial `ok` result.

Deterministic tests verify disabled no-network behavior, exact fixture annotations, an explicit mock network response, timeout handling, and malformed-response handling. Primary tests: `tests/test_mvtool_modes.py`.

### 3. Standalone input contract

The minimal required configuration is `WORK_ROOT`, `RUN_NAME`, `SAMPLE_ID`, `REF_FASTA`, `SOURCE_ALIGN_FILE`, and `MT_CONTIG`. Alignment mode is inferred from `.bam` or `.cram`; the recognized suffix, optional compatibility key `SOURCE_ALIGN_MODE`, and detected BAM/CRAM container must agree. Mitochondrial length is inferred from the FASTA index when omitted. Explicit generic VCF and bedMethyl sidecars take precedence over legacy `wf-human-variation` discovery, and missing optional sidecars produce `not_configured` rather than a core-workflow failure.

Normal execution checks the encoded alignment container, FASTA index, format-appropriate BAM/CRAM index, mitochondrial contig, configured or inferred length, and CRAM reference accessibility. Deterministic tests cover minimal BAM and CRAM configurations; explicit mode/suffix conflicts; renamed CRAM, renamed BAM, nonstandard-suffix mismatches, and unrecognized containers; sidecar precedence; legacy discovery; absent optional inputs; missing indexes; missing contigs; length mismatch; missing CRAM reference; and attempts to omit the validation step. Primary tests: `tests/test_config_and_inputs.py` and `tests/smoke_standalone_minimal.sh`.

Exploratory bedMethyl sidecars are accepted only when each parsed record uses the configured mitochondrial contig and a nonnegative, single-base, zero-based interval (`end = start + 1`) contained within `MT_LENGTH`. Coverage and modification-count fields must be finite and nonnegative, and every serialized numeric bedMethyl field must be finite. A legacy missing other-modification count may be reconstructed only as the nonnegative residual of declared valid coverage. Plain-text and gzip compression are detected from file content. Wrong-contig, non-single-base, negative, out-of-bounds, or nonfinite rows fail with source and line diagnostics rather than entering methylation summaries or being interpreted as zero modification.

### 4. Within-sample mt:nuclear depth ratio

The `mito_copy_number` module reports only the within-sample mt:nuclear depth ratio:

\[
R_{mt:nuclear}=\frac{\overline{D}_{mt}}{\overline{D}_{nuclear}}
\]

The mitochondrial numerator is accepted only when `mito_depth_per_base.tsv` contains exactly one integer coordinate for every position from 1 through `MT_LENGTH` and every depth is finite and nonnegative. Missing evidence yields `not_evaluable/no_mito_depth_evidence`; a present but truncated, duplicate, out-of-range, fractional-position, nonnumeric, negative, nonfinite, or extra-row profile yields `not_evaluable/incomplete_mito_depth_profile`. The ratio is not multiplied by two and is not described as copies per diploid cell. Requested and valid nuclear-window counts are recorded. An absent valid nuclear-window set yields an empty ratio with `status=not_evaluable` and `reason_code=no_valid_nuclear_windows`; valid windows with an exactly zero mean denominator yield `status=not_evaluable` and `reason_code=zero_nuclear_depth_denominator`. Targeted-mt assays yield `not_applicable`.

The `TOY-WGS-001` known-answer test verifies mitochondrial depth 100, nuclear depth 10, and exact ratio 10.0. Negative tests verify missing mitochondrial evidence; partial, duplicate, out-of-range, fractional-position, nonnumeric, negative, nonfinite, nonfinite-mean, and extra-row mitochondrial profiles; missing and zero nuclear denominators; and targeted-mt gating. Primary tests: `tests/test_copy_number.py`.

Circularity edge-depth summaries use the same complete-profile principle. The input must contain the exact integer coordinates `1..MT_LENGTH`, without duplicates or extras, with finite nonnegative depths and finite regional means. Fractional or nonnumeric coordinates are not silently converted to integers. Any malformed present profile produces `not_evaluable/incomplete_depth_profile` and `NA` edge/interior means. Candidate-edge metrics additionally require complete one-based integer candidate coordinates. Primary-read edge metrics require exact binary primary indicators, in-range integer start/end coordinates, ordered start/end pairs for combined soft-clip evaluation, and finite soft-clip fractions in `[0,1]`. Malformed optional evidence produces metric-level `NA/not_evaluable` with an explicit reason while preserving the independent status of a complete depth profile. Deterministic negative tests cover fractional and nonnumeric positions, negative and nonfinite depths, malformed candidate/read coordinates, invalid soft-clip fractions, and invalid primary indicators. Primary tests: `tests/test_circularity_calculations.py`.

### 5. Reference scope, alignment ambiguity, and BED coordinates

`REFERENCE_SCOPE` accepts `auto`, `mt_only`, `whole_genome`, or `custom`. A reference containing only the configured mitochondrial contig resolves to `mt_only`; exact GRCh37, GRCh38, GRCm38, or GRCm39 chromosome-length profiles resolve to `whole_genome`; ambiguous, reduced, scaled, hybrid, or modified references resolve to `custom`. Exact recognized profiles also support species inference for a generic FASTA filename.

For `mt_only` and `custom`, raw aligned-reference fraction, mapping-quality, clipping, and supplementary-alignment metrics remain available, but categorical NUMT-risk interpretation is suppressed. Effective `whole_genome` scope requires exact, concordant recognized profiles in the FASTA index and alignment sequence dictionary, including the assembly-specific mitochondrial sequence and no extra contigs. Reduced, augmented, discordant, or ambiguous alignment dictionaries cannot inherit whole-genome status from the FASTA alone. CRAM reference identity is checked from sequence MD5 metadata and the supplied FASTA even when no mitochondrial record can be decoded. Under `whole_genome`, categorical warning output additionally requires all documented read-stat fields, a valid binary primary-alignment indicator, at least one primary alignment, and a numeric near-complete aligned-reference QC metric. MAPQ must be a finite integer in `[0,255]`; aligned-reference and soft-clip fractions must be finite in `[0,1]`; aligned-reference bases must be a finite nonnegative integer; and SA-tag, primary, and supplementary indicators must be exact binary values. That fraction is the number of primary records whose CIGAR `M`, `=`, and `X` lengths sum to at least 90% of mitochondrial reference length divided by all primary records; `D` and `N` operations are excluded. The historical `primary_full_length_fraction` name is retained only as a `0.x` compatibility field and is not interpreted as molecule integrity. Incomplete or malformed required evidence yields `not_evaluable`, an explicit reason code, and `NA` rather than a fabricated zero or low-risk label. The compatible report filename is retained and the report is titled alignment-ambiguity QC. The mitochondrial BED interval is exactly zero-based, half-open: `MT_CONTIG\t0\tMT_LENGTH`.

Deterministic tests verify exact-profile scope/species inference, rejection of scaled, hybrid, incomplete, modified, and wrong-mt-length references, rejection of a false whole-genome override, mt-only/custom suppression, incomplete-input suppression, bounded whole-genome warning calculation, and exact BED coordinates. Primary tests: `tests/test_reference_scope_and_bed.py`, `tests/test_config_and_inputs.py`, and `tests/test_numt_qc_inputs.py`.

### 6. Reference-aware feature annotation, consequence units, and identity SNVs

Canonical rCRS D-loop/control-region intervals are applied only when the configured mitochondrial sequence exactly matches bundled `NC_012920.1` across the full sequence. A mismatch or unavailable sequence suppresses those intervals and records the status, reason, sequence lengths, and SHA-256 values. A separate `synthetic_fixture_override` is accepted only as explicit test provenance. Deterministic tests use an exact rCRS fixture, a same-length mutated reference, an unavailable sequence, disabled mode, and the explicit synthetic override.

Variant-consequence summaries count unique genomic positions, unique `(position, reference allele, alternate allele)` variants, and annotation rows separately. Consequently, overlapping features or multiple external annotation relationships can increase row counts without inflating site or variant counts. Identity QC retains only canonical single-nucleotide REF/ALT pairs with `FILTER=PASS` or `.`, excludes `REF=ALT`, and, for genotype-bearing VCFs, requires at least one sample genotype to call the specific ALT index. Site-only VCFs remain eligible under the same allele and filter rules. Tests cover multiallelic calls, uncalled alternate alleles, filtered records, indels, noncanonical bases, overlapping features, and duplicated annotation relationships.

## Local deterministic validation

### Environment

Local deterministic validation ran on macOS in an isolated conda environment.

| Component | Version |
| --- | --- |
| Python | 3.12.13 |
| samtools / htslib | 1.23.1 / 1.23.1 |
| pysam | 0.24.0 |
| NumPy | 2.5.1 |
| pandas | 3.0.3 |
| Matplotlib | 3.11.0 |
| Pillow | 12.3.0 |
| Requests | 2.34.2 |
| pytest | 9.1.1 |

### Commands and observed verdicts

```bash
./.conda-release-check/bin/python -m pytest -q tests
./.conda-release-check/bin/python -m mito_overview.cli --list-steps
./.conda-release-check/bin/python -m mito_overview.cli \
  --config examples/configs/human_example.env --dry-run

MITO_OVERVIEW_PYTHON="$PWD/.conda-release-check/bin/python" \
  ./tests/smoke_public_pipeline.sh
MITO_OVERVIEW_PYTHON="$PWD/.conda-release-check/bin/python" \
  ./tests/smoke_public_pipeline_shortread.sh
MITO_OVERVIEW_PYTHON="$PWD/.conda-release-check/bin/python" \
  ./tests/smoke_public_pipeline_longread_nomethyl.sh
MITO_OVERVIEW_PYTHON="$PWD/.conda-release-check/bin/python" \
  ./tests/smoke_standalone_minimal.sh
```

| Check | Verdict | Observed evidence |
| --- | --- | --- |
| Deterministic unit/known-answer suite | Final count deferred | Exact count, commit, environment, and verdict must be read from final CI and the schema-2.0 packet; the post-audit local count is recorded in `analysis_log.md` rather than asserted as final release evidence here |
| CLI step listing | PASS | command exited 0 |
| Generic configured dry-run | PASS | command exited 0 |
| Synthetic long-read workflow | PASS | all applicable steps completed; fixture mvTool and methylation paths exercised |
| Synthetic reduced short-read workflow | PASS | applicable core steps completed; long-read-only layers reported `not_applicable` |
| Long-read without methylation sidecars | PASS | core workflow completed; methylation reported `not_configured` |
| Minimal standalone workflow | PASS | six-key BAM and CRAM configurations each passed strict dry-run and full execution without deployment-specific inputs |

These results characterize the tested release-candidate state within the stated environment and evidence boundaries.

Resource count and byte values in the final packet are inventories rather than operating-system I/O counters. `broad_declared_input_inventory_file_count` and `broad_declared_input_inventory_bytes` record the pre-command file count and size of the repository, cache, and validation roots. The corresponding changed/new output fields record files created or changed under the cache and validation roots. Every required row must be `measured`; all numeric values must be finite; wall time, peak RSS, input file count, and input bytes must be positive. The `public_cache_prepare` output byte value must be at least the summed byte size of the seven sealed FASTQs, so downloaded cache content cannot be omitted from the output inventory.

The packet trust boundary is ordered and explicit. The final validation ZIP must first match a SHA-256 supplied outside the ZIP, then be safely extracted, and only then be checked by its internal `verify_bundle.sh`. The internal verifier establishes packet inventory and semantic consistency but cannot authenticate a coordinated replacement that also rewrites every hash inside the archive. After GitHub publication, the independently obtained release `SHA256SUMS` record is the external archive-digest anchor; a sidecar produced by the same local run is only a local handoff-integrity receipt until independently published.

## Public-data validation design

The local public validation matrix reconstructed both alignments from the seven sealed FASTQs, ran two default report invocations and one invocation per descriptive filter profile, and passed all 17 required cases and all 366 reviewed oracle assertions at candidate commit `0bd64d2eed7400cd8772e77504b8ceab1f668cd8`. Exact normalized TSV and decoded-pixel comparisons were used for same-platform repeatability; HTML files were compared structurally. The matrix ran inside macOS process-tree network isolation, with the parent connectivity control reachable and the isolated child probe blocked. This is commit-specific candidate evidence, not final release evidence: exact-`FINAL_SHA` empty-cache macOS and Ubuntu reruns, packet verification, and publication checks remain release gates.

After independent scientific review, the default public outputs were regenerated with the fail-closed upstream-status contracts and the aligned-reference completeness definition described above. A later deterministic overlap audit found that equal-quality discordant mate observations depended on BAM record order. The corrected engine excludes those ambiguous ties. In GM11906 default/lenient runs this moved 3,826 selected observations to exclusion (`7,652` ambiguous observation records from `3,543` query names); in the strict run it moved 334 selected observations (`668` records from `331` query names). Total observation accounting was conserved exactly, candidate counts remained 33, and the `m.8344A>G` depth, alternate count, strand counts, and fraction were unchanged. GM12878 had zero ambiguous overlaps and no scientific-oracle changes. For GM12878, the historical compatibility field `primary_full_length_fraction` changed from a reference-span-derived `473/728 = 0.649725` to an aligned-reference result of `25/728 = 0.034341`; the new numerator excludes CIGAR `D` and `N` operations and is not interpreted as intact-molecule evidence. The corrected two-run defaults were inserted into a fresh provisional matrix, and the fail-closed refresher rebuilt the exact 56-file tracked public asset inventory. The changed report-native figures and montage passed integrity and same-platform decoded-pixel checks. These cached reruns support candidate asset correction only and do not replace the required empty-cache exact-final-commit reproduction.

Lightweight, tracked evidence copies are:

- `examples/public_validation/public_validation_cases_v0.3.0.tsv`
- `examples/public_validation/filter_profile_results_v0.3.0.tsv`
- `examples/public_validation/public_validation_inputs_v0.3.0.sha256`
- `examples/public_validation/GM11906_MERRF_shortread/`
- `examples/public_validation/GM12878_ONT_longread/`

### Public inputs and provenance

| Dataset | Public source | Analyzed material | Key provenance |
| --- | --- | --- | --- |
| GM11906 | `SRR10804585`, `SRR10804590`, `SRR10804657` | pooled paired-end reads aligned with BWA-MEM | BWA `0.7.19-r1273`; samtools `1.23.1`; derivative hashes deferred to the final commit-bound packet |
| GM12878 [Vandiver et al. 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9399971/) | `SRR18110025`, `PRJNA809571`, `SAMN26195906` | deterministic 1,000-query-name subset, not the full run | raw FASTQ MD5 `d5bfb9aeba04cae5f3dd79462a42e5b0`; subset SHA-256 `40e203ead1d621bfec8caa3c5d18cd1e7e70c08da27008a73364812b6871df33`; selected-name SHA-256 `3444cc7db3dcf78bea807d8bcc6686883a7759d128288c1d26aeae077a771a19` |

Both datasets were aligned to the 16,569-bp `NC_012920.1` reference. BWA-MEM was selected for the pooled paired-end GM11906 reads; the tracked BWA `0.7.19-r1273` command template was:

```bash
bwa mem -t {threads} {reference_fasta} {combined_r1} {combined_r2} | samtools sort -@ {threads} -o {alignment_bam}
```

Minimap2 with the `map-ont` preset was selected for the GM12878 ONT reads; the tracked minimap2 `2.31-r1302` command template was:

```bash
minimap2 -t {threads} -ax map-ont {reference_mmi} {deterministic_subset_fastq} | samtools view -@ {threads} -b -F 4 | samtools sort -@ {threads} -o {alignment_bam}
```

The GM12878 subset used the 1,000 smallest seeded query-name hashes under `smallest_sha256_seeded_query_names_v1` with seed `mito-overview-v0.3.0-GM12878-SRR18110025`. This fixed-size hash selection bounded the example while making inclusion deterministic and auditable; it was not intended to produce a statistically representative sample. The subset contained 1,000 of 193,043 source records (fraction 0.00518019). The alignment contained 728 primary and 543 supplementary records from 728 mapped query names. Platform-specific derivative BAM and index hashes are intentionally deferred to the final commit-bound packet because BAM byte identity is not a cross-platform acceptance criterion. The two default report invocations reused the newly generated derivative; cross-platform reconstruction remains a final release gate.

## Public-data results

### Matrix verdicts

All 17 required local matrix cases passed. These provisional results remain pending release acceptance until the same contract passes on macOS and Ubuntu and is packet-bound to the exact final commit.

| Evidence class | Cases | Verdict |
| --- | ---: | --- |
| GM11906 default, two runs | 2 | PASS |
| GM11906 lenient and strict profiles | 2 | PASS |
| GM12878 default, two runs | 2 | PASS |
| GM12878 lenient and strict profiles | 2 | PASS |
| Normalized-TSV repeatability | 2 | PASS |
| HTML/PNG integrity and structural consistency | 2 | PASS |
| Filter-profile summary | 1 | PASS |
| Frozen scientific oracle | 1 | PASS |
| Raw-cache seal | 1 | PASS |
| OS process-tree network isolation | 1 | PASS |
| Project network-entrypoint canaries | 1 | PASS |

Both normalized repeat diffs and both visual-structure diffs were empty. Each default workflow contained 44 summary TSVs and 14 HTML pages; GM11906 contained seven report PNGs and GM12878 contained 15 before representative tracked figures were selected.

### GM11906 reduced short-read proof of principle

At the default 13/20/10 filter profile, the workflow reported 33 candidate sites, 44,048,838 accepted canonical-base observations, and 7,296,932 accounted excluded observations. The literature-associated `m.8344A>G` site remained present with:

| Field | Value |
| --- | ---: |
| Callable depth | 1027 |
| Alternate observations | 740 |
| Alternate allele fraction | 0.720545 |
| Forward alternate observations | 305 |
| Reverse alternate observations | 435 |
| Feature | `MT-TK` |
| Consequence label | `tRNA_variant` |

This demonstrates representation of a previously reported marker in the reduced short-read reporting profile. It is not a modality-matched benchmark, independent confirmation of pathogenicity, or calibrated allele-fraction study.

### GM12878 deterministic reduced ONT proof of principle

At the default 13/20/10 filter profile, the reduced workflow reported:

| Field | Value |
| --- | ---: |
| Candidate sites | 16 |
| Accepted canonical-base observations | 7,143,152 |
| Accounted excluded observations | 2,047,476 |
| Mean mitochondrial depth | 545.484 |
| Median mitochondrial depth | 544.0 |
| Selected co-segregation sites | 8 |
| Singleton CIGAR-deletion bins | 13 |
| Unique primary query names | 728 |
| Query names with a large CIGAR deletion | 5 |
| Query names with supplementary alignment or SA tag | 542 |
| Maximum CIGAR-deletion-bin support fraction | 0.001374 |

All 13 CIGAR-deletion bins were singletons; the largest binned median CIGAR-deletion length was 1,394 bp. Five query names had at least one qualifying CIGAR deletion. Separately, 542 query names had a supplementary alignment or `SA` tag. These descriptive CIGAR-deletion and alignment-structure summaries lack orthogonal structural truth and do not establish deletion-calling accuracy.

The targeted-mt profile correctly reported the within-sample mt:nuclear depth ratio and Phy-Mer as `not_applicable`, mvTool and methylation as `not_configured`, and mt-only NUMT interpretation as `not_evaluable` with `reason_code=reference_scope_mt_only`. The alignment-ambiguity metrics remain inspectable, but no categorical low/moderate/high NUMT-risk claim is made.

### Filter-profile description

| Dataset | Profile | BQ/MAPQ/readQ | Candidates | Accepted observations | Excluded observations | `m.8344A>G` AF |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| GM11906 | lenient | 0/0/0 | 33 | 44,048,838 | 7,296,932 | 0.720545 |
| GM11906 | default | 13/20/10 | 33 | 44,048,838 | 7,296,932 | 0.720545 |
| GM11906 | strict | 20/30/15 | 33 | 42,675,832 | 8,669,938 | 0.733469 |
| GM12878 | lenient | 0/0/0 | 32 | 8,278,969 | 911,659 | NA |
| GM12878 | default | 13/20/10 | 16 | 7,143,152 | 2,047,476 | NA |
| GM12878 | strict | 20/30/15 | 15 | 6,046,355 | 3,144,273 | NA |

These differences describe filter dependence. They are not sensitivity, specificity, limit-of-detection, or clinical-threshold estimates.

## Claim-to-evidence map

| Claim permitted for v0.3.0 | Supporting evidence | Boundary |
| --- | --- | --- |
| Shared, filtered alternate-allele counting is deterministic on known-answer fixtures | `tests/test_allele_counting.py`; exact-commit CI and final packet PASS required | No clinical calibration |
| Co-segregation reuses the same observation filters | shared engine tests and synthetic long-read smoke | No biological phasing benchmark |
| Default mvTool execution is offline | `tests/test_mvtool_modes.py`; standalone smoke reports `not_configured` | Network service content not validated |
| Generic BAM/CRAM inputs are supported | config tests plus minimal standalone smoke | Platform breadth limited to tested environments |
| The copy-number-named module reports an experimental within-sample mt:nuclear depth ratio | exact 100/10 known-answer and denominator-negative tests | Not absolute copies per cell |
| mt-only reference suppresses categorical NUMT interpretation | scope tests and GM12878 public output | Not a NUMT classifier |
| Long-read public workflow completes on a deterministic reduced ONT input | GM12878 matrix and tracked provenance | Not full-run performance or analytical validation |
| Reduced short-read profile represents `m.8344A>G` | GM11906 repeated public runs | Not diagnostic or modality-equivalence evidence |
| Fixed-input normalized tables are repeatable | two empty normalized TSV diffs per dataset | Conditional on locked fixed BAMs/environment |

## Status semantics

Module states are restricted to `ok`, `not_configured`, `not_applicable`, `not_evaluable`, `unavailable`, and `failed`. Validation verdicts are restricted to `PASS`, `FAIL`, `XFAIL`, `SKIP`, and `BLOCKED`. A case cannot be marked `PASS` when its input or expected evidence is unavailable.

The final packet applies a closed case inventory: every required case ID must be present exactly once, no additional case IDs are accepted, and all rows must be `PASS`. The mandatory set explicitly includes `public_oracle`, `raw_cache_seal`, and `project_network_entrypoints`. Fresh-clone package evidence binds the exercised wheel and sdist bytes to their PEP 610 archive hashes, packet distribution inventory, and extracted verifier. Every macOS visual row is likewise bound to packaged HTML/PNG bytes; private paths, missing or unlisted files, unsupported types, symlinks, and undecodable PNGs fail verification rather than being sanitized into different evidence.

- `not_configured`: an optional resource or integration was not supplied.
- `not_applicable`: the assay/read-mode contract excludes the module.
- `not_evaluable`: the module ran, but the available reference or denominator cannot support interpretation.
- `unavailable`: an explicitly requested external service failed.
- `failed`: required execution failed.

## Release-candidate status

Version `0.3.0` remains unreleased. The final GitHub tag, release assets, and exact-commit validation packet are pending and are not represented as completed validation results.

## Independent reproducibility checklist

An external reviewer can:

1. Run the complete current test suite and verify its exact count, commit, environment, and verdict in the final packet rather than relying on a count embedded in this provisional document.
2. Verify the GM11906 official NCBI GEO/SRA metadata snapshot, its captured source URLs and SHA-256 values, and the GM12878 tracked provenance records.
3. Confirm `m.8344A>G` is `1027/740/0.720545` in the default GM11906 output.
4. Confirm GM12878 uses exactly the labeled 1,000-query-name deterministic subset.
5. Confirm no mt-only output contains a categorical NUMT-risk label.
6. Confirm no missing or zero denominator is emitted as a numeric within-sample mt:nuclear depth ratio.
7. Confirm default mvTool mode does not construct a network session.
8. Inspect representative long- and short-read montages for legibility and correspondence to tracked summary tables.

## Reproducibility artifacts

Tracked cases, input hashes, provenance records, normalized summaries, and representative report assets are stored under `examples/public_validation/`. Raw public sequencing data remain outside Git. This document records release-candidate validation evidence and does not claim a final release.
