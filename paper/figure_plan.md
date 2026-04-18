# Figure Plan

## Figure 1. Workflow architecture
- show the modular step layout from validation through report generation
- emphasize one-step/one-page design
- annotate which outputs are TSV, figure, and HTML

## Figure 2. Public example report montage
- use the synthetic `TOY-001_output` bundle
- include panels from:
  - mito QC
  - heteroplasmy
  - deletions
  - gene summary

## Figure 3. Output structure and reproducibility assets
- diagram the repository components:
  - CLI
  - shell wrapper
  - environment file
  - synthetic smoke test
  - public example-bundle builder
  - synthetic example output

## Figure 4. Optional integration boundary
- show the public-core workflow as the central block
- show Phy-Mer and mvTool as optional external enrichments
- label them as non-mandatory and outside the bundled core

## Table 1. Core analytical layers
- step name
- biological question
- primary inputs
- main outputs

## Table 2. Current release boundaries
- supported now
- exploratory
- optional external integration
- planned future work
