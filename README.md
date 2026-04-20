# mito-overview

`mito-overview` is a Python-based workflow for mitochondrial DNA analysis from Oxford Nanopore Technologies (ONT) alignments. The current implementation packages a portable core that was derived from an internally exercised mtDNA reporting workflow. The repository emphasizes stepwise mitochondrial QC, heteroplasmy screening, deletion screening, copy-number proxy estimation, feature annotation, and related report generation.

## Scope
- aligned BAM or CRAM input
- mitochondrial subset extraction
- heteroplasmy screening
- deletion and rearrangement screening
- mtDNA depth and copy-number proxy estimation
- mitochondrial feature and gene-level summarization
- NUMT-aware and circularity-aware QC
- optional exploratory methylation summaries
- HTML, TSV, and figure outputs per analytical section

## Current implemented scope
The public mirror currently covers the working core already ported from the internal pipeline. The modules below are implemented in the public mirror and exercised by the current synthetic smoke-test and example-bundle workflow:
- portable config loading
- run layout and provenance writing
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
- `mito_phymer_haplogroup` (optional human haplogroup enrichment)
- `mito_mvtool_annotation` (optional human external annotation enrichment)
- `mito_circularity_qc`
- `mito_methylation_exploratory`
- final sync into a persistent report directory

Human mtDNA currently has the clearest public configuration path. Human-specific external annotation and haplogroup layers remain optional, and non-human use should be limited to the reference-driven core modules unless separately validated.

## Synthetic validation dataset
The repository contains a small synthetic dataset for installation checks and public example generation:
- [`examples/synthetic_data/TOY-001`](examples/synthetic_data/TOY-001)

This dataset is intentionally small and deterministic. It is meant for:
- environment validation
- smoke testing
- generation of the public example output bundle

Optional human-only enrichment pages are validated locally in this repository with bundled fixture resources:
- a tiny deterministic Phy-Mer vendor stand-in under [`tests/fixtures/mock_phymer_vendor`](tests/fixtures/mock_phymer_vendor)
- a local mvTool-style annotation fixture under [`tests/fixtures/mock_mvtool_annotations.json`](tests/fixtures/mock_mvtool_annotations.json)

The corresponding expected public example output bundle is:
- [`examples/expected_reports/TOY-001_output`](examples/expected_reports/TOY-001_output)

## Representative report views
These panels come from a synthetic public-core example bundle generated from the repository's own example-builder workflow.

**Heteroplasmy landscape**

![Heteroplasmy landscape](examples/expected_reports/TOY-001_output/figures/mito_heteroplasmy_landscape.png)

**Feature annotation overview**

![Feature annotation overview](examples/expected_reports/TOY-001_output/figures/mito_feature_annotation.png)

**Gene-level summary**

![Gene summary overview](examples/expected_reports/TOY-001_output/figures/mito_gene_summary_overview.png)

**Optional annotation context**

![mvTool status overview](examples/expected_reports/TOY-001_output/figures/mito_mvtool_status_counts.png)

## Installation
Create the public environment:

```bash
conda env create -f environment.yml
conda activate mito-overview
```

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

Run the local synthetic smoke test:

```bash
./tests/smoke_public_pipeline.sh
```

Generate the synthetic public example bundle from the tracked toy inputs:

```bash
./scripts/build_public_example_bundle.sh \
  examples/expected_reports/TOY-001_output
```

## Output contract
Each finished sample bundle is expected to contain:
- a mitochondrial BAM for inspection
- per-step TSV summaries
- per-step figures
- per-step HTML report pages
- a final sample bundle for archival or downstream review

A synthetic public-core example bundle is staged at:
- [`examples/expected_reports/TOY-001_output`](examples/expected_reports/TOY-001_output)

Pages `01` through `14` in the example bundle correspond to the currently ported public report pages. In the bundled toy validation path, pages `13` and `14` are exercised through local fixture resources so that a fresh clone can validate the optional human enrichment layers without a private Phy-Mer checkout or live network dependency.

## Optional integrations
- Phy-Mer: optional human mtDNA haplogroup enrichment
- mvTool: optional human mtDNA external annotation enrichment
- these integrations are intentionally non-mandatory and should be treated as secondary annotation layers rather than the core analysis
- the repository's synthetic validation path uses local fixtures for these layers; real biological use should point to a true Phy-Mer vendor tree and the intended mvTool-compatible endpoint
- `mito-overview` does not bundle external Phy-Mer code or mvTool data resources; see [`docs/license_notes.md`](docs/license_notes.md)

## Repository status
- active private or pre-public repository with a functional core and ongoing packaging for external release
- current repository now includes a synthetic public example bundle generated from the public-core workflow
- cite the software metadata in [`CITATION.cff`](CITATION.cff) (current version `0.1.0`) until a manuscript and/or DOI is posted
- design notes for the public package are in [`docs/overview.md`](docs/overview.md) and [`docs/methodology.md`](docs/methodology.md)

## Preprint
A software/resource preprint is in preparation. A citation link and versioned preprint reference will be added here when posted.
