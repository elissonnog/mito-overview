# Figure Plan

## Figure 1. Public-core analytical views from the tracked synthetic example bundle
- file: `paper/figures/figure2_example_core_montage.png`
- source bundle: `examples/expected_reports/TOY-001_output`
- panels:
  - heteroplasmy landscape
  - mt:nuclear depth proxy
  - feature annotation
  - gene summary

## Figure 2. Optional human-only enrichment views validated through local fixtures
- file: `paper/figures/figure3_optional_enrichment_montage.png`
- source bundle: `examples/expected_reports/TOY-001_output`
- panels:
  - Phy-Mer haplogroup ranking
  - mvTool-style status summary

## Figure 3. Auxiliary short-read proof-of-principle compatibility example
- file: `paper/figures/figure4_shortread_public_validation_montage.png`
- source bundle: `examples/public_validation/GM11906_MERRF_shortread`
- panels:
  - short-read heteroplasmy landscape
  - feature annotation
  - gene summary
  - variant consequence class summary
- role in manuscript:
  - demonstrate real-data execution of `READ_MODE=short`
  - show recovery/reporting of the known `m.8344A>G` site context
  - explicitly not presented as modality-matched or cohort-scale short-read validation

## Table 1. Core analytical layers
- step name
- biological question
- primary inputs
- main outputs
- interpretation level (`core`, `warning-oriented QC`, `exploratory`)

## Table 2. Current public release boundaries
- supported now
- optional external enrichments
- exploratory layers
- current validation type
- future benchmarking needs

## Table 3. External context and positioning
- resource/tool
- primary role
- how `mito-overview` relates to it
- whether the relation is replacement, complement, or optional integration
