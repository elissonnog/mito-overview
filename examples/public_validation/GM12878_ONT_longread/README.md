# GM12878 public ONT long-read proof-of-principle example

This directory contains light-weight public example assets derived from a real ONT targeted-mt dataset processed with the `mito-overview` long-read profile.

Example context:
- source BioProject: `PRJNA809571`
- run used: `SRR18110025`
- public assay description: `Long read mitochondrial genome sequencing using Cas9-guided adaptor ligation`
- profile used: `READ_MODE=long`, `ASSAY_TYPE=targeted_mt`
- packaged proof-of-principle heteroplasmy threshold: `HET_MIN_VAF=0.10`

Included assets:
- representative report-native figures used for GitHub/manuscript panels
- key summary tables from the proof-of-principle output
- condensed key-findings and top-signal tables
- alignment flagstat summary

What these assets support:
- real public ONT long-read execution of the core long-read workflow
- report-native QC, heteroplasmy, deletion-screening, same-read co-occurrence, gene-summary, NUMT-QC, circularity-QC, and consequence outputs
- explicit assay-mode gating for targeted-mt layers that remain uninterpretable here (`copy_number` and `phymer_haplogroup`)
- explicit status-only methylation reporting when mitochondrial bedmethyl rows are unavailable

What these assets do not claim:
- clinical interpretation
- low-VAF heteroplasmy benchmarking
- validated deletion truth benchmarking
- formal mtDNA-versus-NUMT classification
- biological methylation conclusions

Observed packaged key values:
- mapped reads: `247254.0`
- mean depth: `106379.759`
- median depth: `106032.0`
- full-length fraction: `0.3758`
- candidate heteroplasmy sites (`VAF>=0.10`): `28`
- selected same-read co-occurrence sites: `8`
- top consequence class: `missense_variant` (`10` sites)
- candidate deletion clusters: `1337.0` with max support fraction `2.1e-05`
- NUMT heuristic risk: `moderate`
- copy-number status: `not_applicable`
- Phy-Mer status: `not_applicable`
- methylation status: `no_mt_bedmethyl_rows_available`

Important note:
- this light-weight public pack is intentionally focused on the real-data long-read proof-of-principle outputs and does not include `identity_qc` or `mvtool_annotation` pages
