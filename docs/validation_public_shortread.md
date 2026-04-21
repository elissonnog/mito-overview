# Public short-read proof-of-principle compatibility example

`mito-overview` now includes a separate short-read profile that keeps the long-read workflow intact while marking long-read-specific analytical layers as not applicable.

Current public real-data example path:
- sample source: public GM11906 short-read ATAC-seq runs
- biological context: public sample metadata describes GM11906 as a lymphoblastoid cell line derived from a donor with pathogenic `m.8344A>G`
- use case: proof-of-principle short-read operability and pathogenic-site representation

Included validation script:
- `scripts/run_public_shortread_validation_gm11906.sh`

What this example is intended to demonstrate:
- configuration and execution of `READ_MODE=short`
- preservation of the report structure with explicit `not_applicable` pages for long-read-only layers
- detection/reporting of mtDNA variation from real public short-read data
- real figure generation from a public dataset

What this example does **not** demonstrate by itself:
- clinical-grade short-read pathogenicity calling
- formal heteroplasmy benchmarking across short-read cohorts
- accurate mt:nuclear copy-number estimation for non-WGS assays
- definitive NUMT discrimination from a mt-only alignment strategy

Current public dataset choice:
- runs `SRR10804585`, `SRR10804590`, and `SRR10804657`
- same GM11906 MERRF cell-line source in public metadata
- combined in the validation script to increase mitochondrial coverage for proof-of-principle reporting

Current observed recovery in the bundled example:
- site recovered: `m.8344A>G`
- depth at position `8344`: `1041`
- alternate count: `754`
- estimated heteroplasmy fraction in the current implementation: `0.724304`
- feature context: `MT-TK`
- consequence class: `tRNA_variant`

References and source metadata:
- [Lareau et al., Nat Biotechnol 2019](https://www.nature.com/articles/s41587-019-0147-6)
- [GEO sample metadata example](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238489)
- [Coriell GM11906](https://www.coriell.org/0/Sections/Search/Sample_Detail.aspx?Ref=GM11906)
- [Shoffner et al., Cell 1990](https://pubmed.ncbi.nlm.nih.gov/2112427/)
- [ClinVar m.8344A>G](https://www.ncbi.nlm.nih.gov/clinvar/RCV000010192.15/)
