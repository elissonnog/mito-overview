# Figure Plan

## Figure 1. Workflow architecture and public ONT long-read proof-of-principle views
- file: `paper/figures/figure0_workflow_architecture.png`
- source bundle: `examples/public_validation/GM12878_ONT_longread`
- panels:
  - mode-gated workflow overview
  - mitochondrial depth profile
  - heteroplasmy landscape
  - long-read co-segregation heatmap
  - NUMT-warning span-versus-MAPQ QC
- role in manuscript:
  - introduce the algorithmic structure and output contract
  - show real report-native public ONT panels rather than a schematic-only workflow
  - keep interpretation at workflow/resource level

## Figure 2. Public ONT long-read proof-of-principle report-native montage
- file: `paper/figures/figure1_public_longread_validation_montage.png`
- source bundle: `examples/public_validation/GM12878_ONT_longread`
- panels:
  - heteroplasmy landscape
  - co-segregation heatmap
  - gene summary
  - NUMT-aware QC span vs MAPQ
- role in manuscript:
  - demonstrate real-data `READ_MODE=long` execution on a public ONT targeted-mt dataset
  - show that core long-read report-native views are generated on a bounded public example
  - keep assay boundaries explicit: `copy_number` and `phymer_haplogroup` are `not_applicable`, and methylation is status-only in this exemplar

## Figure 3. Complementary short-read proof-of-principle compatibility example
- file: `paper/figures/figure2_shortread_public_validation_montage.png`
- source bundle: `examples/public_validation/GM11906_MERRF_shortread`
- panels:
  - short-read heteroplasmy landscape
  - feature annotation
  - gene summary
  - variant consequence class summary
- role in manuscript:
  - demonstrate real-data execution of `READ_MODE=short`
  - show reduced-profile representation of the literature-associated `m.8344A>G` marker context
  - serve as the complementary reduced-profile example rather than the only real-data validation figure
  - explicitly not presented as modality-matched or cohort-scale short-read validation, calibrated heteroplasmy benchmarking, non-WGS copy-number estimation, definitive NUMT discrimination, or validation of long-read-only layers

## Notes
- This is a figure plan only.
- The free-format manuscript currently uses prose rather than manuscript tables.
- If tables are added later, they should be generated from the release validation audit and reproducibility ledger rather than written as unsupported narrative tables.
