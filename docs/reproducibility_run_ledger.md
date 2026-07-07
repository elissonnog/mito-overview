# Reproducibility Run Ledger

This ledger records the evidence used for the workflow/resource manuscript draft for `mito-overview` v0.2.1. It is intended to make the manuscript auditable without overstating analytical validation. Runtime, memory, checksums, exact commit, and release archive identifiers should be completed at release freeze and summarized in `docs/release_validation_audit_2026-07-07.md`.

Note: the folder label `GM11906_MERRF_shortread` is a historical project label for the public short-read proof-of-principle. The supported claim is representation of the literature-associated m.8344A>G marker in a reduced short-read report, not confirmation of disease status or clinical pathogenicity in this dataset.

## Evidence Tiers

| Tier | Purpose | Command or Script | Input or Accession | Assay Mode | Key Thresholds | Expected Outputs | Supported Claim | Not Supported | Release-Freeze Fields |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Package import and registry | Confirm the Python package exposes declared workflow steps | `python -m mito_overview.cli --list-steps`; `python -m mito_overview.cli --config examples/configs/human_example.env --dry-run` | repository checkout | not assay-specific | not applicable | import success; step registry visible; dry-run plan completes | package wiring is available in the public checkout | analytical correctness of each module | exact commit; dependency lock; command transcript |
| Synthetic long-read fixture | Verify execution continuity and long-read report bundle structure | `tests/smoke_public_pipeline.sh` or synthetic example regeneration command | repository synthetic fixture `TOY-001` | long-read targeted mtDNA | toy thresholds only | `examples/expected_reports/TOY-001_output/` with HTML, TSV, figures, BAM subset | active long-read layers can execute on controlled toy input | biological realism; diagnostic performance | exact command transcript; runtime; memory; hashes |
| Synthetic short-read fixture | Verify reduced short-read mode and `not_applicable` behavior | `tests/smoke_public_pipeline_shortread.sh` | repository synthetic fixture `TOY-SR-001` | reduced short-read targeted mtDNA | toy thresholds only | `examples/expected_reports/TOY-SR-001_output/` with active compatible pages and inactive long-read-only pages | short-read mode preserves output contract and assay gating | equivalence to long-read layers; NUMT or structural claims | exact command transcript; runtime; memory; hashes |
| Public ONT proof-of-principle | Confirm real public long-read targeted-mt report generation | `scripts/run_public_longread_validation_gm12878.sh` | GM12878 ONT targeted-mt, BioProject `PRJNA809571`, run `SRR18110025` | long-read targeted mtDNA | `HET_MIN_DEPTH=100`; `HET_MIN_VAF=0.10`; `DELETION_MIN_SIZE=100`; reference `NC_012920.1` | `examples/public_validation/GM12878_ONT_longread/`; key findings table `GM12878_ONT_longread_key_findings.tsv`; four-panel manuscript Figure 1 | public ONT data can be rebuilt into synchronized report-native layers under stated thresholds | low-VAF sensitivity; deletion truth; formal NUMT classification; clinical interpretation | exact FASTQ source date; command transcript; commit; environment; runtime; memory; checksums |
| Public reduced short-read proof-of-principle | Confirm reduced short-read report generation and representation of a literature-reported marker | `scripts/run_public_shortread_validation_gm11906.sh` | GM11906 public short-read/scATAC-derived mtDNA reads from runs `SRR10804585`, `SRR10804590`, `SRR10804657`; reference `NC_012920.1` | reduced short-read targeted-mt report profile | `HET_MIN_DEPTH=10`; `HET_MIN_VAF=0.20`; expected marker m.8344A>G | `examples/public_validation/GM11906_MERRF_shortread/`; marker table `GM11906_MERRF_shortread_site_8344.tsv`; manuscript Figure 2 | reduced short-read mode can report a literature-associated mtDNA marker in applicable layers | disease confirmation; pathogenicity classification; full long-read workflow validation; NUMT discrimination | exact FASTQ source date; command transcript; commit; environment; runtime; memory; checksums |

## Public Long-Read Result Fields to Audit

| Field | Current Manuscript Value | Source File | Interpretation |
| --- | --- | --- | --- |
| mapped mitochondrial reads | approximately 247,000 | `examples/public_validation/GM12878_ONT_longread/GM12878_ONT_longread_key_findings.tsv` | report-generation scale for the proof-of-principle run |
| mean depth | approximately 106,380x | same as above | coverage context, not a diagnostic metric |
| candidate sites | 28 at `HET_MIN_VAF=0.10` | same as above | threshold-specific candidate reporting |
| same-read selected sites | 8 | same as above | selected strongest candidates for co-occurrence visualization |
| NUMT-warning label | moderate | same as above | heuristic warning label, not classifier output |
| strongest deletion-like bin support | 3 reads; maximum primary-read support fraction approximately 0.000021 | same as above and deletion summary tables | cautionary structural-screen output only |

## Public Short-Read Result Fields to Audit

| Field | Current Manuscript Value | Source File | Interpretation |
| --- | --- | --- | --- |
| expected marker | m.8344A>G in `MT-TK` | `examples/public_validation/GM11906_MERRF_shortread/GM11906_MERRF_shortread_site_8344.tsv` | literature-associated marker represented in reduced short-read report |
| depth at marker | 1,041 | same as above | implementation-specific depth from the reduced-profile run |
| alternate reads | 754 | same as above | implementation-specific alternate count |
| alternate fraction | approximately 72% | same as above | threshold-specific report value, not calibrated sensitivity |
| consequence class | `tRNA_variant` | same as above | local feature/consequence annotation summary |

## Required Before Submission

1. Freeze the repository release and insert the exact commit hash into the manuscript.
2. Archive the release with Zenodo or Software Heritage and insert the DOI or persistent identifier.
3. Re-run the synthetic and public workflows from a clean checkout.
4. Record command transcripts, runtime, memory, dependency versions, and output paths.
5. Verify expected file presence, TSV schemas, assay-mode status pages, and threshold-specific public findings.
6. Have an independent reviewer or separate thread repeat the clean-checkout validation.

## v0.2.1 Release-Freeze Evidence Plan

The current release-freeze validation packet is expected at:

- `/Users/elopes/Desktop/ont_results/mito_overview_validation_packets/mito_overview_validation_2026-07-07`

The packet should include:

- `metadata/environment_and_git.txt`
- `metadata/output_file_inventory.txt`
- `metadata/output_sha256.txt`
- numbered command transcripts under `logs/`
- regenerated outputs under `outputs/`
- public-data work directories under `work/` when public data reruns are feasible

The public proof-of-principle runs remain optional for a quick smoke-test release gate because they depend on public mirror availability and local alignment runtime. If skipped, the release audit must state that the tracked public asset packs were inspected but not regenerated in the final validation pass.
