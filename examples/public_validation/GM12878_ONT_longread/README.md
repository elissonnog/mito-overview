# GM12878 public ONT deterministic reduced proof-of-principle example

This directory contains lightweight public example assets from a seeded deterministic query-name subset of a real ONT targeted-mt run processed with the `mito-overview` long-read profile.

Example context:
- source BioProject: `PRJNA809571`
- run used: `SRR18110025`
- public assay description: `Long read mitochondrial genome sequencing using Cas9-guided adaptor ligation`
- source publication: Vandiver et al., Mitochondrion 2022 (PMID 35787470; DOI 10.1016/j.mito.2022.06.003)
- validation scope: deterministic reduced public proof-of-principle, not the complete run
- profile used: `READ_MODE=long`, `ASSAY_TYPE=targeted_mt`
- minimum callable depth: `100`
- minimum observed alternate allele fraction: `0.1`

Included assets:
- representative report-native figures used for GitHub/manuscript panels
- key summary tables from the validation output
- condensed key-findings and top-signal tables
- alignment flagstat summary

What these assets support:
- real public ONT long-read execution of the core long-read workflow
- report-native QC, alternate-allele screening, CIGAR-deletion candidate screening, co-segregation, gene-summary, alignment-ambiguity QC, circularity-QC, and consequence outputs
- explicit assay-mode gating for targeted-mt layers that remain uninterpretable here (`copy_number` and `phymer_haplogroup`)
- explicit status-only methylation reporting when mitochondrial bedmethyl rows are unavailable

What these assets do not claim:
- clinical interpretation
- calibrated low-allele-fraction detection benchmarking
- validated deletion truth benchmarking
- formal mtDNA-versus-NUMT classification
- biological methylation conclusions

Observed packaged key values:
- mapped reads: `1271`
- mean depth: `545.484`
- median depth: `544`
- full-length fraction: `0.0343`
- alternate-allele candidate sites: `16`
- selected co-segregation sites: `8`
- top consequence class: `synonymous_variant` (`6` sites)
- singleton CIGAR-deletion bins: `13`; each packaged bin has one supporting query name
- query names with supplementary/SA evidence, summarized separately: `542`
- NUMT interpretation status: `not_evaluable` (`reference_scope_mt_only`)
- within-sample mt:nuclear depth-ratio status: `not_applicable`
- Phy-Mer status: `not_applicable`
- methylation status: `not_configured`

Important note:
- optional network-backed mvTool annotation is disabled unless explicitly configured
