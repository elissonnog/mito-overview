# GM11906 public reduced short-read proof-of-principle compatibility example

This directory contains light-weight public example assets derived from real short-read/scATAC-derived mtDNA reads processed with the `mito-overview` reduced short-read profile.

Example context:
- source sample: GM11906 short-read/scATAC-derived mtDNA reads
- runs used: `SRR10804585`, `SRR10804590`, `SRR10804657`
- public metadata context: GM11906 lymphoblastoid cells derived from a donor with pathogenic `m.8344A>G`
- profile used: `READ_MODE=short` with the package's `ASSAY_TYPE=targeted_mt` report profile

Included assets:
- representative figures used for GitHub and manuscript panels
- key summary tables from the proof-of-principle output
- a focused `8344` mpileup record
- a condensed key-findings table

What these assets support:
- proof-of-principle reduced short-read operability on a real public sample
- representation of the `8344:A>G` signal within the current public workflow
- manuscript-ready figures and sidecar summary tables derived from a fresh reduced-profile rerun

What these assets do not claim:
- clinical validation or disease-status confirmation
- formal short-read heteroplasmy benchmarking
- definitive NUMT discrimination from mt-only alignment
