# Changelog

## v0.3.0
- corrected allele-fraction reporting so candidate sites, strand counts, and co-segregation use one auditable callable-observation policy, canonical thresholds, and uncapped default depth
- made mvTool access explicitly mode-gated and offline by default, with deterministic fixtures and non-fabricated unavailable states for requested network failures
- defined a portable standalone BAM/CRAM input contract with explicit sidecars and preflight checks for references, indexes, contigs, lengths, CRAM reference availability, and conflicting format overrides
- corrected the copy-number-named output to an unscaled within-sample mt:nuclear depth ratio, with missing or zero nuclear denominators reported as `not_evaluable` rather than zero
- require the mt:nuclear numerator to contain exactly one finite, nonnegative depth observation at every mitochondrial position; truncated, duplicate, out-of-range, fractional, or invalid profiles are `not_evaluable`
- require circularity edge-depth metrics to use the same complete integer-coordinate, finite, nonnegative mitochondrial depth-profile contract rather than silently truncating malformed positions or accepting invalid depths
- reject nonfinite bedMethyl coverage and count fields before aggregation so malformed modification evidence cannot become an observed zero-methylation result
- require finite, biologically bounded alignment-fraction, clipping, MAPQ, alignment-length, and binary-indicator evidence before whole-genome NUMT warning interpretation; malformed evidence is `not_evaluable`, never categorical low risk
- validate optional circularity candidate coordinates, primary-read coordinates, soft-clip fractions, and primary indicators before calculating edge fractions; malformed optional evidence yields metric-level `NA/not_evaluable` while a valid complete depth profile remains independently evaluable
- added explicit reference-scope handling that suppresses categorical NUMT interpretation for mt-only or custom references and emits exact zero-based, half-open mitochondrial BED intervals
- bounded the supported claim to a reproducible, mode-gated mtDNA reporting workflow/resource; this version does not establish clinical validity, analytical sensitivity, deletion truth, absolute copy number, formal NUMT classification, or long-read/short-read equivalence
- added tracked validation-provenance tooling, known-answer coverage for the five corrections, deterministic public-input provenance, and resource-limited public proof-of-principle reruns
- aligned the focused GM11906 `m.8344A>G` mpileup with the declared BaseQ, MAPQ, flag, depth, BAQ, orphan-pair, and overlap settings while retaining it as an inspection artifact rather than an independent caller benchmark
- bound reused public alignments to exact command templates, parameters, and locked tool versions, and bound the GM12878 reduced input to the recomputed seeded minimum-name selection plus frozen subset and ledger identities
- made public-alignment input labels unique and fail-closed, standardized the selected-name ledger on SHA-256 plus MD5 linkage, and prevented installed-package public helpers from importing checkout modules
- made deterministic FASTQ provenance require complete name/size/MD5/SHA-256 records, bound nested public manifests to their current bytes, and made fresh packet extraction reject schema, provenance-type, or dataset-identity drift
- made validation-packet public-input records require an exact label/name/size/MD5/SHA-256 inventory and made fresh extraction recompute the nested subset manifest's MD5 as well as its SHA-256 and byte count
- froze the bounded claim/evidence matrix and now rederives every manuscript-handoff value from its validated filter-profile source table before packet construction and after fresh extraction
- separated repository-only archival helpers and mocked tests from default pytest, CI acceptance, and source-distribution contents so Zenodo and DOI tooling cannot gate the GitHub release
- replaced the lead workflow schematic with public ONT report-native views, tightened figure terminology and caveats, consolidated the figure set, and added a deterministic figure builder without repository-specific local paths
- synchronized package and citation metadata for version 0.3.0, the public repository, and both Medical College of Wisconsin authors
- reject nonfinite or out-of-domain allele-filter thresholds before analysis and restrict candidate-evaluable positions to canonical reference bases
- validate candidate, feature-overlap, fingerprint, and all-site tables against strict coordinate, allele, depth, fraction, strand, count-sum, uniqueness, and configured-reference contracts before downstream interpretation
- propagate unavailable upstream candidate evidence through co-segregation rather than reusing stale tables, and reject mitochondrial CIGAR-deletion events outside the configured reference interval
- require integer bedMethyl count fields, ordered circularity read coordinates, consistent NUMT aligned-base fractions, a valid required QC denominator, and MAPQ values that distinguish unavailable `255` from high-quality mappings
- require complete exact digest identities for every cached public input and deterministic-subset derivative, including MD5 where prescribed, before reuse or packet verification
- require GitHub release state to remain explicitly non-prerelease through every draft, upload, and publication checkpoint
- require the complete generated 14-column candidate-observation schema, matching canonical and compatibility fractions, exact depth/base/strand identities, unique variant keys, and at most one selected alternate allele per mitochondrial position
- require NUMT read evidence to contain consistent primary/secondary/supplementary flags, positive query lengths, bounded soft-clip counts, and soft-clip fractions that agree with their counts; require the upstream near-complete-alignment metric to carry successful module/metric states and the `primary_alignment_records` denominator
- make the final GitHub publication transition restate the exact tag, target commit, release name, draft state, and non-prerelease state, and validate the complete assets returned by that transition before recording publication success
- require each selected candidate alternate to have a largest observed non-reference canonical-base count, and apply the complete candidate contract in mvTool and circularity without silent deduplication
- require aligned-reference plus soft-clipped query-consuming bases not to exceed read query length before categorical whole-genome NUMT-warning interpretation
- distinguish a valid complete-schema zero-candidate result from malformed zero-byte or partial-header candidate files in mvTool and circularity, validating every existing file before empty-result handling
- require successful upstream heteroplasmy provenance before Phy-Mer, mvTool, or circularity can interpret candidate evidence; failed or malformed upstream states cannot reuse stale tables
- validate the complete one-row-per-position all-site allele contract and REF-to-FASTA identity before Phy-Mer consensus construction, rejecting duplicate, out-of-range, partial, and reference-inconsistent evidence
- distinguish missing candidate files from valid observed zero-candidate tables in mvTool and circularity, and remove heteroplasmy-owned outputs before recomputation
- require GitHub native immutable releases to be enabled and re-queried successfully before publication; a disabled `GET` response triggers enablement rather than an annotated-tag fallback
- publish only the exact wheel and source distribution already bound inside the validation packet, while treating a clean public-tag rebuild as member-payload equivalence evidence rather than replacement release bytes
- make README links to repository-only manuscript assets absolute and release-tagged so source distributions contain no broken relative `paper/**` references

## v0.2.1 - 2026-07-07
- synchronized release metadata across `pyproject.toml`, `CITATION.cff`, README, release checklist, and manuscript source
- added Xiaowu Gai to software and manuscript authorship metadata
- promoted the workflow architecture / public ONT proof-of-principle figure as the lead manuscript and README figure
- expanded the free-format manuscript methods with explicit calculations for depth, heteroplasmy, CIGAR-deletion bins, the within-sample mt:nuclear depth ratio, co-segregation, gene summaries, and NUMT-warning QC
- refreshed release-readiness documentation for a conservative workflow/resource preprint scope

## v0.2.0 - 2026-04-21
- added a reduced `READ_MODE=short` profile with assay-aware gating
- preserved long-read workflow behavior while writing explicit `not_applicable` status pages for unsupported short-read layers
- added portable bundled human mitochondrial annotation and reference resources for public validation
- added synthetic short-read smoke coverage and a tracked short-read expected example bundle
- added a public GM11906 proof-of-principle compatibility example showing reduced-profile representation of the literature-associated `m.8344A>G` marker
- updated the README, validation docs, and preprint draft to keep the short-read example auxiliary and ONT-first
