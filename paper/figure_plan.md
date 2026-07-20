# Figure Plan

## Figure 1. Public ONT long-read report-native views
- file: `paper/figures/figure0_workflow_architecture.png`
- source: `scripts/build_workflow_architecture_figure.py`
- panels:
  - mitochondrial depth profile
  - alternate-allele fraction landscape
  - selected-site read co-occurrence heatmap
  - alignment-ambiguity span-versus-MAPQ QC
- role in manuscript:
  - show representative report-native public ONT output views
  - remove the workflow schematic from the lead figure
  - keep interpretation at workflow/resource level

## Figure 2. Complementary short-read proof-of-principle compatibility example
- file: `paper/figures/figure2_shortread_public_validation_montage.png`
- source bundle: `examples/public_validation/GM11906_MERRF_shortread`
- panels:
  - short-read alternate-allele landscape
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
