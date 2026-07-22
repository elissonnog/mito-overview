# MitoOverview v0.3.0 Preprint-Hardening Plan

> **Superseded release-control document.** This frozen plan records the earlier DOI/archive-oriented proposal. The active GitHub-only release gate is [`clean_room_validation_protocol_v0.3.0.md`](clean_room_validation_protocol_v0.3.0.md); Zenodo, a DOI, manuscript changes, and bioRxiv submission are outside the current release acceptance criteria.

## Material Passport

- Origin: approved implementation plan
- Date frozen: 2026-07-20
- Verification status: UNVERIFIED
- Public repository: https://github.com/elissonnog/mito-overview
- Immutable prior release: `v0.2.1`
- Immutable prior release commit: `2ba62b775a7204c0dc61f5408989603f536c78da`
- Reviewed report-figure commit: `1f0928266a142a904f6fa216a2abd7c9a2b72f7d`
- Implementation branch: local release-candidate branch; branch names are not release metadata
- Intended release: `v0.3.0`
- Scope boundary: public Mac/GitHub mirror only; the MCW/HPC installation is not modified or deployed by this work

## Scientific Claim Boundary

The release supports a reproducible workflow/resource claim for mode-gated mtDNA evidence reporting. It does not support diagnostic use, calibrated low-VAF sensitivity, pathogenicity classification, deletion-truth benchmarking, absolute mtDNA copy-number estimation, formal NUMT classification, or clinical equivalence between long- and short-read assays.

Clair3, NanoDel, in-pipeline modkit execution, absolute copy-number estimation, and MCW deployment are deferred.

## Correction 1: Allele-Fraction Counting

One shared observation policy will drive candidate-site counts, strand counts, and co-segregation. Callable depth is the number of passing A/C/G/T observations after all filters, and alternate allele fraction is `alt_count / callable_depth`.

Public defaults:

| Key | Default |
| --- | ---: |
| `ALLELE_MIN_BASE_QUALITY` | `13` |
| `ALLELE_MIN_MAPPING_QUALITY` | `20` |
| `ALLELE_MIN_READ_MEAN_QUALITY` | `10` |
| `ALLELE_MAX_DEPTH` | `0` (unlimited) |
| `ALLELE_EXCLUDE_FLAGS` | `3844` |
| `ALLELE_IGNORE_OVERLAPS` | `1` |

Canonical threshold keys are `MIN_CALLABLE_DEPTH` and `MIN_ALT_ALLELE_FRACTION`. Legacy `HET_MIN_DEPTH` and `HET_MIN_VAF` remain accepted; conflicting canonical and legacy values are errors. `alt_allele_fraction` is canonical in output tables, while `heteroplasmy_fraction` remains a deprecated compatibility alias during the `0.x` series.

Required invariants:

- `alt_count = alt_forward + alt_reverse`
- `callable_depth = A + C + G + T`
- no implicit 8,000-observation cap
- candidate and co-segregation reads use the same read/base filters
- co-segregation reports a conditional statistic on reads callable at both sites and records that shared universe explicitly
- all filter settings and exclusion counts appear in run provenance

## Correction 2: mvTool Network Control

`MVTOOL_MODE` accepts `disabled`, `fixture`, or `network` and defaults to `disabled`. `MVTOOL_API_URL` defaults to empty. `MVTOOL_FIXTURE_JSON` provides deterministic local annotation data. Page 14 remains in the report sequence, but disabled mode performs no HTTP request and reports `not_configured`. Network mode requires both an explicit mode and nonempty URL. A failed requested service reports `unavailable` with a reason code and does not fabricate annotations. Success requires a unique, complete, one-to-one match between submitted candidates and returned input identifiers; missing, duplicate, or unexpected rows are response-integrity failures.

## Correction 3: Standalone Input Contract

Required keys are `WORK_ROOT`, `RUN_NAME`, `SAMPLE_ID`, `REF_FASTA`, `SOURCE_ALIGN_FILE`, and `MT_CONTIG`. BAM/CRAM mode is inferred from the extension, and `MT_LENGTH` is inferred from the FASTA index when omitted.

`PIPELINE_ROOT`, `SOURCE_SAMPLE_DIR`, `SOURCE_HV_DIR`, and `SOURCE_HV_NP_DIR` become optional legacy conveniences. Explicit generic sidecars take precedence over legacy `wf-human-variation` discovery:

- `SOURCE_VARIANT_VCF`
- `SOURCE_CLINVAR_VCF`
- `SOURCE_VARIANT_VCF_UNPHASED`
- `SOURCE_CLINVAR_VCF_UNPHASED`
- `SOURCE_BEDMETHYL`
- `SOURCE_BEDMETHYL_HP1`
- `SOURCE_BEDMETHYL_HP2`
- `SOURCE_BEDMETHYL_UNGROUPED`

Normal execution validates the FASTA index, alignment index, mitochondrial contig and length, and CRAM reference identity before analysis. CRAM identity is established from sequence-dictionary MD5 metadata and the supplied FASTA even when the file has no mitochondrial records. Optional absent sidecars report `not_configured`; they do not invalidate core reporting.

## Correction 4: Copy-Number Proxy

The module remains a configurable, lightweight within-sample ratio:

`mt_to_nuclear_depth_ratio = mt_mean_depth / nuclear_mean_depth`

It is not multiplied by two and is never labeled copies per diploid cell. A missing valid-window set produces an empty/NA ratio with `status=not_evaluable` and `reason_code=no_valid_nuclear_windows`; valid windows with a measured zero mean denominator use `reason_code=zero_nuclear_depth_denominator`. Targeted-mt assays remain `not_applicable`. Outputs record requested and valid nuclear-window counts. A synthetic WGS known-answer case must verify `100 / 10 = 10.0`.

## Correction 5: Reference Scope, NUMT, and BED

`REFERENCE_SCOPE` accepts `auto`, `mt_only`, `whole_genome`, or `custom`. Auto-detection resolves a single-mt-contig reference as `mt_only`, recognized complete human or mouse references as `whole_genome`, and ambiguous reduced references as `custom`. Effective `whole_genome` scope requires the FASTA index and alignment header to independently match the same recognized exact profile with no extra contigs; a reduced, augmented, or discordant alignment dictionary cannot unlock categorical interpretation.

For `mt_only` or `custom`, alignment metrics remain available but categorical NUMT risk is suppressed. Outputs use `numt_interpretation_status=not_evaluable` with reason `reference_scope_mt_only` or `reference_scope_custom`. The compatible page filename remains, while the page is labeled alignment-ambiguity QC. Mitochondrial BED output is exactly `MT_CONTIG`, start `0`, end `MT_LENGTH`.

## Status Vocabulary

Module states are `ok`, `not_configured`, `not_applicable`, `not_evaluable`, `unavailable`, and `failed`. Validation verdicts are `PASS`, `FAIL`, `XFAIL`, `SKIP`, and `BLOCKED`. Missing evidence can never be recorded as `PASS`.

## Validation Contract

| ID | Deterministic proof |
| --- | --- |
| `F1` | More than 8,000 accepted observations; exact base/depth/strand counts; quality, flag, and overlap exclusions |
| `F2` | Default mvTool mode cannot call HTTP; fixture and local mock modes work; malformed, timeout, missing, duplicate, and unexpected response rows are unavailable |
| `F3` | Minimal generic BAM and CRAM configs; explicit-sidecar precedence; legacy discovery; clear index/contig/length/reference failures; CRAM MD5 identity without relying on observed mtDNA records |
| `F4` | Known ratio `10.0`; missing/zero denominator is NA rather than zero; targeted mtDNA is not applicable |
| `F5` | mt-only or reduced-header NUMT interpretation is not evaluable; concordant exact whole-genome profiles enable warnings; augmented profiles are rejected; BED is zero-based half-open |

Required executable checks:

1. `python -m pytest -q`
2. `python -m mito_overview.cli --list-steps`
3. strict generic dry-run
4. synthetic long-read smoke test
5. synthetic reduced short-read smoke test
6. synthetic long-read no-methylation smoke test
7. two Mac reruns of public GM11906 and GM12878 workflows
8. allele-filter profiles `0/0/0`, `13/20/10`, and `20/30/15`
9. fresh-clone release validation on the exact candidate commit

GM11906 must retain `m.8344A>G` for that manuscript claim to remain. GM12878 must complete applicable layers and report NUMT interpretation as not evaluable under its mt-only reference. New candidate counts are descriptive results and are not forced to match `v0.2.1`.

## Audit Outputs

The human-readable audit is `docs/preprint_release_validation_v0.3.0.md`. The portable bundle is generated outside Git at `$MITO_OVERVIEW_VALIDATION_ROOT/v0.3.0/mito-overview-v0.3.0-validation.zip` and contains `run.json`, case and claim-evidence tables, data-source records, environment and command transcripts, normalized expected/observed outputs, SHA-256 manifests, and `verify_bundle.sh`. Raw public data remain outside Git.

## Release Gates

- All five corrections have positive and negative known-answer tests.
- Unit tests, three smoke modes, and two public reruns pass on the Mac.
- Linux and macOS GitHub Actions check out and pass on the exact PR head; final release evidence additionally requires a successful push-event run bound to the exact candidate commit.
- Default execution performs no external request.
- Missing copy-number denominator is never zero.
- mt-only reference never emits categorical NUMT risk.
- README, manuscript, figures, validation audit, package metadata, release tag, captured Zenodo reservation record, and archive metadata agree.
- No internal MCW path, code, or nonpublic sample enters the release.
- `v0.2.1` remains immutable.

The guarded helper `scripts/capture_zenodo_reservation.py` creates or retrieves an unpublished production deposition using a local environment-only bearer token, then writes a minimized evidence object. The default draft metadata is versioned at `resources/zenodo/mito_overview_v0.3.0_draft.json`; publishing remains a separate, later release action.

The plan remains `UNVERIFIED` until every release gate has corresponding evidence in the completed validation bundle.

## Primary Technical References

- [SAM format specification: reference-sequence MD5 (`M5`) calculation](https://samtools.github.io/hts-specs/SAMv1.pdf)
- [CRAM format specification: reference-sequence identity requirements](https://samtools.github.io/hts-specs/CRAMv3.pdf)
- [samtools mpileup documentation: base-quality, mapping-quality, depth, flag, and overlap controls](https://www.htslib.org/doc/1.22/samtools-mpileup.html)
- [GitHub Actions event documentation: pull-request merge refs and explicit head checkout](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [Zenodo documentation: reserving a DOI before publication](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/)
