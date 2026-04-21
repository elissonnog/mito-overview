# GM11906 public short-read proof-of-principle compatibility example

This directory contains light-weight public example assets derived from a real short-read dataset processed with the `mito-overview` short-read profile.

Example context:
- source sample: GM11906 short-read ATAC-seq runs
- runs used: `SRR10804585`, `SRR10804590`, `SRR10804657`
- public metadata context: GM11906 lymphoblastoid cells derived from a donor with pathogenic `m.8344A>G`
- profile used: `READ_MODE=short`, `ASSAY_TYPE=targeted_mt`

Included assets:
- representative figures used for GitHub and manuscript panels
- key summary tables from the validation output
- a focused `8344` mpileup record
- a condensed key-findings table

What these assets support:
- proof-of-principle short-read operability on a real public sample
- direct representation of the `8344:A>G` signal within the current public workflow
- documentation of which pages remain active versus not applicable in the reduced short-read profile

What these assets do not claim:
- clinical validation
- formal short-read heteroplasmy benchmarking
- definitive NUMT discrimination from mt-only alignment
