# Public ONT long-read proof-of-principle example

`mito-overview` now includes a bounded real-data ONT long-read example that exercises the core long-read workflow on a public targeted-mt dataset.

Current public real-data example path:
- sample source: public GM12878 ONT targeted-mt run
- public accessions: BioProject `PRJNA809571`, run `SRR18110025`
- public assay description: `Long read mitochondrial genome sequencing using Cas9-guided adaptor ligation`
- use case: proof-of-principle long-read operability, real report-native figure generation, and explicit assay-boundary handling

Included proof-of-principle script:
- `scripts/run_public_longread_validation_gm12878.sh`

Current rerun status:
- fresh rerun completed on `2026-06-23` in the local Mac reproducibility environment
- the current packaged proof-of-principle rerun uses `HET_MIN_VAF=0.10`
- the tracked light-weight asset pack under `examples/public_validation/GM12878_ONT_longread` was refreshed from that rerun
- one ambiguous-reference candidate-like site (`3107 N>T`) is now excluded from the candidate set so heteroplasmy and consequence outputs remain internally consistent

What this example is intended to demonstrate:
- configuration and execution of `READ_MODE=long`
- real public ONT generation of QC, heteroplasmy, deletion-screening, same-read co-occurrence, gene-summary, NUMT-QC, circularity-QC, and consequence outputs
- honest targeted-mt assay gating with `not_applicable` status for `copy_number` and `phymer_haplogroup`
- stable status-only methylation reporting when mitochondrial bedmethyl rows are unavailable

What this example does **not** demonstrate by itself:
- full `01-14` public page coverage
- identity-style long-read validation
- live mvTool-backed annotation validation
- low-VAF heteroplasmy benchmarking
- validated deletion truth benchmarking
- formal mtDNA-versus-NUMT classification
- biological methylation conclusions

Current observed values in the packaged proof-of-principle run:
- mapped reads: `247254`
- mean depth: `106379.759`
- median depth: `106032.0`
- full-length fraction: `0.3758`
- candidate heteroplasmy sites at `VAF>=0.10`: `28`
- selected same-read co-occurrence sites: `8`
- candidate deletion clusters: `1337`
- maximum deletion support fraction among primary reads: `2.1e-05`
- NUMT heuristic risk: `moderate`
- `copy_number` status: `not_applicable`
- `phymer_haplogroup` status: `not_applicable`
- methylation status: `no_mt_bedmethyl_rows_available`

Interpretation note:
- the deletion layer in this public example should be treated as a low-support screening layer, not as validated evidence of biologically meaningful deletion burden
- the leading candidate-site table is dominated by high-fraction background-style mtDNA differences and should not be presented as a low-fraction heteroplasmy benchmark

Tracked asset pack:
- `examples/public_validation/GM12878_ONT_longread`

References and source metadata:
- [NCBI BioProject PRJNA809571](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA809571)
- [ENA run SRR18110025](https://www.ebi.ac.uk/ena/browser/view/SRR18110025)
- [Slapnik et al., Sci Rep 2024](https://www.nature.com/articles/s41598-024-78270-0)
- [Frascarelli et al., Front Genet 2023](https://pubmed.ncbi.nlm.nih.gov/37456669/)
