# Figure Plan

## Figure 1. Representative long-read report-native analytical views
- file: `paper/figures/figure1_representative_longread_report_montage.png`
- source bundle: representative long-read report bundle rendered through the standard HTML/PNG output path
- panels:
  - heteroplasmy landscape
  - co-segregation heatmap
  - gene summary
  - NUMT-aware QC span vs MAPQ

## Figure 2. Auxiliary short-read proof-of-principle compatibility example
- file: `paper/figures/figure2_shortread_public_validation_montage.png`
- source bundle: `examples/public_validation/GM11906_MERRF_shortread`
- panels:
  - short-read heteroplasmy landscape
  - feature annotation
  - gene summary
  - variant consequence class summary
- role in manuscript:
  - demonstrate real-data execution of `READ_MODE=short`
  - show recovery/reporting of the known `m.8344A>G` site context
  - explicitly not presented as modality-matched or cohort-scale short-read validation, calibrated heteroplasmy benchmarking, non-WGS copy-number estimation, definitive NUMT discrimination, or validation of long-read-only layers

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
