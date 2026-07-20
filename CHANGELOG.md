# Changelog

## Unreleased
- replaced the lead workflow schematic with public ONT report-native views
- tightened figure terminology and manuscript caveats for alternate-allele, read co-occurrence, and alignment-QC outputs
- consolidated the manuscript to one long-read lead figure and one complementary short-read figure
- added a reproducible deterministic figure builder and removed repository-specific local paths

## v0.2.1 - 2026-07-07
- synchronized release metadata across `pyproject.toml`, `CITATION.cff`, README, release checklist, and manuscript source
- added Xiaowu Gai to software and manuscript authorship metadata
- promoted the workflow architecture / public ONT proof-of-principle figure as the lead manuscript and README figure
- expanded the free-format manuscript methods with explicit calculations for depth, heteroplasmy, deletion clusters, mt:nuclear depth proxy, co-segregation, gene summaries, and NUMT-warning QC
- refreshed release-readiness documentation for a conservative workflow/resource preprint scope

## v0.2.0 - 2026-04-21
- added a reduced `READ_MODE=short` profile with assay-aware gating
- preserved long-read workflow behavior while writing explicit `not_applicable` status pages for unsupported short-read layers
- added portable bundled human mitochondrial annotation and reference resources for public validation
- added synthetic short-read smoke coverage and a tracked short-read expected example bundle
- added a public GM11906 proof-of-principle compatibility example showing reduced-profile representation of the literature-associated `m.8344A>G` marker
- updated the README, validation docs, and preprint draft to keep the short-read example auxiliary and ONT-first
