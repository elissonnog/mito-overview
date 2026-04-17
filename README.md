# mito-overview

`mito-overview` is a modular Oxford Nanopore Technologies mitochondrial DNA interpretation and reporting framework for sample-level mtDNA analysis.

## Scientific scope
The package is designed for disease-agnostic mitochondrial interpretation from long-read sequencing with emphasis on:
- mtDNA heteroplasmy
- deletion and rearrangement burden
- mtDNA depth and copy-number proxy
- NUMT-aware QC
- circularity-aware QC
- co-segregation of mtDNA variants on long reads
- mitochondrial feature and gene-level context
- optional human-only enrichment with haplogroup and external mtDNA annotation

## Design principles
- one module per analysis layer
- one HTML page per major biological report section
- machine-readable TSV outputs paired with human-readable reports
- explicit provenance for reference build, contig naming, thresholds, and input source
- optional integrations kept separate from the reproducible core workflow

## Planned repository structure
See [`docs/overview.md`](docs/overview.md) and [`docs/methodology.md`](docs/methodology.md) for the scientific design and packaging plan.

## Development status
This scaffold captures the planned public structure for the current HPC `mito_overview` workflow and will be populated module-by-module from the validated internal pipeline.

## Current scaffold usage
List the canonical workflow steps:

```bash
python -m mito_overview.cli --list-steps
```

Run a dry plan using the included example config:

```bash
python -m mito_overview.cli \
  --config examples/configs/human_example.env \
  --dry-run
```

Run through the public shell wrapper:

```bash
./scripts/run_mito_pipeline.sh \
  --config examples/configs/human_example.env \
  --steps validate,stage
```

The current public scaffold already includes:
- portable config loading
- run-layout and provenance writing
- mitochondrial asset extraction
- shared HTML report rendering
- `mito_qc`
- `mito_heteroplasmy`
- `mito_deletions`
- `mito_copy_number`
- `mito_feature_annotation` with configurable human mtDNA GTF input
- `mito_cosegregation`
- `mito_gene_summary`
- `mito_numt_qc`
- `mito_identity_qc`
- `mito_variant_consequence`
- `mito_circularity_qc`
- `mito_methylation_exploratory`
- final sync into a persistent report directory

Run the local synthetic smoke test:

```bash
./tests/smoke_public_pipeline.sh
```
