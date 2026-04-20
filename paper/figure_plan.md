# Figure Plan

## Figure 1. Workflow architecture
- show the modular step layout from `validate` through `sync_bioinfo`
- separate `12 core analytical pages` from `2 optional human-only enrichment pages`
- annotate which outputs are TSV, figures, HTML, and synced bundle assets

## Figure 2. Public example report montage
- use the synthetic `TOY-001_output` bundle
- include panels from:
  - mito QC
  - heteroplasmy
  - deletions
  - feature annotation or gene summary
  - optional page 13 or 14 as a small inset if space permits

## Figure 3. Reproducibility assets and validation path
- diagram the repository components:
  - CLI
  - shell runner
  - environment file
  - tracked synthetic inputs
  - smoke test
  - example-bundle builder
  - tracked expected outputs
- label the validations performed:
  - local mirror smoke
  - fresh-clone smoke
  - example-bundle regeneration

## Figure 4. Integration boundary
- show the public-core workflow as the central block
- show Phy-Mer and mvTool as optional external enrichments
- label local validation fixtures versus real external resources

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
