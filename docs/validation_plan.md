# Validation Plan

## Core validation set
Representative human mtDNA samples should be used to validate:
- depth and coverage summaries
- heteroplasmy candidate detection
- deletion burden summaries
- copy-number proxy stability
- gene and feature-level summaries
- NUMT and circularity warning behavior

## Edge-case validation
The public package should explicitly test:
- empty deletion tables
- no heteroplasmy candidates
- non-human samples for human-only modules
- missing optional external integrations
- placeholder-heavy external annotation returns

## External concordance targets
Optional human-only concordance targets:
- haplogroup concordance for Phy-Mer
- external annotation stability for mvTool
- deletion summary comparison against a specialized deletion workflow when available

## Release evidence package
The initial release should include:
- one small example configuration
- one example output bundle
- one figure montage for the README
- one validation table for the software preprint
