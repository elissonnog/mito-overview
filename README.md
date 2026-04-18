# mito-overview

`mito-overview` is a modular Oxford Nanopore Technologies (ONT) mitochondrial DNA analysis and reporting framework for sample-level interpretation. The workflow decomposes mtDNA review into explicit analytical layers that each emit tabular summaries, figures, and collaborator-facing HTML pages. The current repository is a pre-public mirror of a validated internal pipeline, with the goal of releasing a portable scientific core without reproducing the private production environment.

## Why this repository exists
- ONT mtDNA interpretation is often fragmented across single-purpose scripts or web services.
- Long reads add information that is hard to summarize from flat variant tables alone, including read-level co-segregation, deletion structure, circularity effects, and NUMT-related warning signals.
- Collaborators usually need both machine-readable outputs and a compact report bundle that can be reviewed without re-running ad hoc notebooks.

`mito-overview` is designed around those needs: one analytical layer per step, one report page per major biological question, and explicit provenance carried through the final bundle.

## Highlights
- long-read mtDNA interpretation from aligned BAM or CRAM inputs
- disease-agnostic analytical layers for heteroplasmy, deletion and rearrangement burden, depth and copy-number proxy, NUMT-aware QC, circularity-aware QC, read-level co-segregation, and feature- or gene-level summaries
- provenance-aware reporting with explicit reference build, contig naming, thresholds, and input-source tracking
- one HTML page per major biological report section, paired with TSV outputs for downstream reuse
- optional human-specific enrichment kept separate from the reproducible core workflow
- exploratory methylation retained as a secondary summary layer rather than the primary biological conclusion

## Current validated scope
The public mirror currently covers the working core already ported from the internal pipeline. Best-supported use at present is sample-level ONT mtDNA analysis with:
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
- `mito_circularity_qc`
- `mito_methylation_exploratory`
- final sync into a persistent report directory

Human mtDNA currently has the clearest public configuration path. Human-specific external annotation and haplogroup layers remain optional, and non-human use should be limited to the reference-driven core modules unless separately validated.

## Representative report views
These panels come from a synthetic public-core example bundle generated from the repository's own example-builder workflow.

**Heteroplasmy landscape**

![Heteroplasmy landscape](examples/expected_reports/TOY-001_output/figures/mito_heteroplasmy_landscape.png)

**Deletion cluster overview**

![Deletion cluster overview](examples/expected_reports/TOY-001_output/figures/mito_deletion_clusters.png)

**Gene-level summary**

![Gene summary overview](examples/expected_reports/TOY-001_output/figures/mito_gene_summary_overview.png)

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

Build the synthetic public example bundle:

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
- a final sample bundle for collaborator review

A synthetic public-core example bundle is staged at:
- [`examples/expected_reports/TOY-001_output`](examples/expected_reports/TOY-001_output)

Pages `01` through `12` in the example bundle correspond to the current portable public core.

## Optional integrations
- Phy-Mer: optional human mtDNA haplogroup enrichment
- mvTool: optional human mtDNA external annotation enrichment
- these integrations are intentionally non-mandatory and should be treated as contextual support rather than the sole basis for biological interpretation
- `mito-overview` does not bundle external Phy-Mer code or mvTool data resources; see [`docs/license_notes.md`](docs/license_notes.md)

## Repository status
- active private or pre-public repository with a functional core and ongoing packaging for external release
- current repository now includes a synthetic public example bundle generated from the public-core workflow
- cite the software metadata in [`CITATION.cff`](CITATION.cff) (current version `0.1.0`) until a manuscript and/or DOI is posted
- design notes for the public package are in [`docs/overview.md`](docs/overview.md) and [`docs/methodology.md`](docs/methodology.md)
