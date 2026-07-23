# Changelog

## v0.3.0
- corrected allele-fraction reporting so candidate sites, strand counts, and co-segregation use one auditable callable-observation policy, canonical thresholds, and uncapped default depth
- made mvTool access explicitly mode-gated and offline by default, with deterministic fixtures and non-fabricated unavailable states for requested network failures
- defined a portable standalone BAM/CRAM input contract with explicit sidecars and preflight checks for references, indexes, contigs, lengths, CRAM reference availability, and conflicting format overrides
- corrected the copy-number-named output to an unscaled within-sample mt:nuclear depth ratio, with missing or zero nuclear denominators reported as `not_evaluable` rather than zero
- added explicit reference-scope handling that suppresses categorical NUMT interpretation for mt-only or custom references and emits exact zero-based, half-open mitochondrial BED intervals
- bounded the supported claim to a reproducible, mode-gated mtDNA reporting workflow/resource; this version does not establish clinical validity, analytical sensitivity, deletion truth, absolute copy number, formal NUMT classification, or long-read/short-read equivalence
- added tracked validation-provenance tooling, known-answer coverage for the five corrections, deterministic public-input provenance, and resource-limited public proof-of-principle reruns
- aligned the focused GM11906 `m.8344A>G` mpileup with the declared BaseQ, MAPQ, flag, depth, BAQ, orphan-pair, and overlap settings while retaining it as an inspection artifact rather than an independent caller benchmark
- bound reused public alignments to exact command templates, parameters, and locked tool versions, and bound the GM12878 reduced input to the recomputed seeded minimum-name selection plus frozen subset and ledger identities
- made public-alignment input labels unique and fail-closed, standardized the selected-name ledger on SHA-256 plus MD5 linkage, and prevented installed-package public helpers from importing checkout modules
- froze the bounded claim/evidence matrix and now rederives every manuscript-handoff value from its validated filter-profile source table before packet construction and after fresh extraction
- separated repository-only archival helpers and mocked tests from default pytest, CI acceptance, and source-distribution contents so Zenodo and DOI tooling cannot gate the GitHub release
- replaced the lead workflow schematic with public ONT report-native views, tightened figure terminology and caveats, consolidated the figure set, and added a deterministic figure builder without repository-specific local paths
- synchronized package and citation metadata for version 0.3.0, the public repository, and both Medical College of Wisconsin authors

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
