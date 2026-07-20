# mito-overview

`mito-overview` is a Python-based workflow for mode-gated mitochondrial DNA (mtDNA) evidence reporting from aligned BAM or CRAM inputs. The current public implementation provides a long-read-oriented profile and a reduced short-read compatibility profile that preserves the analytical layers applicable without long molecules or ONT methylation tracks. The repository emphasizes synchronized HTML, TSV, and figure generation for mitochondrial QC, alternate-allele screening, structural screening, depth-proxy reporting when nuclear context is available, feature annotation, same-read co-occurrence, and warning-oriented QC.

Version `0.3.0` is documented as a workflow/resource release. Its public validation evidence covers report execution, synchronized artifacts, mode/status gating, filter-profile sensitivity, and repeatability from provenance-verified fixed BAM inputs.

## Scope
- aligned BAM or CRAM input
- mitochondrial subset extraction
- heteroplasmy screening
- deletion-like structural screening
- mtDNA depth and copy-number proxy estimation
- mitochondrial feature and gene-level summarization
- NUMT-aware and circularity-aware QC
- optional exploratory methylation summaries
- HTML, TSV, and figure outputs per analytical section

## Implemented read profiles
- `long`
  - intended for ONT-style mtDNA workflows
  - supports the full current report structure, including long-read-only layers such as deletion screening, same-read co-occurrence, NUMT/circularity warning pages, and exploratory methylation
  - when ONT bedmethyl sidecars are absent, the core long-read layers still run and the exploratory methylation page degrades to an explicit status-only report
- `short`
  - intended for short-read mtDNA-aligned inputs
  - retains the applicable core pages and writes explicit `not_applicable` pages for long-read-only layers
  - currently exercised in the public repository as an auxiliary compatibility path with a synthetic toy sample and one public proof-of-principle example

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

## Relationship to other mtDNA software
`mito-overview` is designed to complement, not replace, established mtDNA tools. Variant callers, haplogroup classifiers, annotation services, contamination/NUMT tools, and visualization resources remain the right primary tools for their respective tasks. The narrower contribution here is a local, per-sample, mode-gated report bundle that keeps active analyses, optional enrichments, and unsupported assay layers synchronized.

For a reviewer-facing comparison with MToolBox, mtDNA-Server, HaploGrep, Phy-Mer, mvTool/MSeqDR, MitoVisualize, Haplocheck, MitSorter, and related mtDNA caller workflows, see [`docs/related_software_landscape.md`](docs/related_software_landscape.md).

## Synthetic smoke-test dataset
The repository contains a small synthetic dataset for installation checks and public example generation:
- [`examples/synthetic_data/TOY-001`](examples/synthetic_data/TOY-001)

This dataset is intentionally small and deterministic. It is meant for:
- environment checks
- smoke testing
- generation of the public example output bundle

The repository also includes a short-read synthetic example bundle generated from the same tracked toy inputs:
- [`examples/expected_reports/TOY-SR-001_output`](examples/expected_reports/TOY-SR-001_output)

Optional human-only enrichment pages are exercised locally in this repository with bundled fixture resources:
- a tiny deterministic Phy-Mer vendor stand-in under [`tests/fixtures/mock_phymer_vendor`](tests/fixtures/mock_phymer_vendor)
- a local mvTool-style annotation fixture under [`tests/fixtures/mock_mvtool_annotations.json`](tests/fixtures/mock_mvtool_annotations.json)

## Report views
The lead figure below shows public ONT long-read report-native panels from the fixed GM12878 qn1000 asset pack.

![mito-overview public ONT report-native views](paper/figures/figure0_workflow_architecture.png)

The panels show depth, alternate-allele fractions, selected-site read co-occurrence, and alignment span-versus-MAPQ QC. These are descriptive workflow outputs from the fixed reduced input.

Regenerate the lead figure with `python scripts/build_workflow_architecture_figure.py`.

The repository also includes a complementary real public short-read proof-of-principle montage from GM11906:

![GM11906 reduced short-read proof-of-principle report montage](examples/public_validation/GM11906_MERRF_shortread/figures/GM11906_MERRF_shortread_montage.png)

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

Run the short-read synthetic smoke test:

```bash
./tests/smoke_public_pipeline_shortread.sh
```

Run the long-read smoke test without methylation sidecars:

```bash
./tests/smoke_public_pipeline_longread_nomethyl.sh
```

Generate the synthetic public example bundle from the tracked toy inputs:

```bash
./scripts/build_public_example_bundle.sh \
  examples/expected_reports/TOY-001_output
```

Generate the synthetic short-read example bundle:

```bash
./scripts/build_public_shortread_example_bundle.sh \
  examples/expected_reports/TOY-SR-001_output
```

Run the public reduced short-read proof-of-principle example:

```bash
./scripts/run_public_shortread_validation_gm11906.sh \
  /tmp/GM11906_reduced_shortread_output
```

Run the public long-read proof-of-principle example:

```bash
./scripts/run_public_longread_validation_gm12878.sh \
  /tmp/GM12878_ONT_longread_output
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
- [`examples/expected_reports/TOY-SR-001_output`](examples/expected_reports/TOY-SR-001_output)

Pages `01` through `14` in the example bundle correspond to the currently ported public report pages. In the bundled toy smoke-test path, pages `13` and `14` are exercised through local fixture resources so that a fresh clone can exercise the optional human enrichment interfaces without a private Phy-Mer checkout or live network dependency.

In the short-read targeted-mt profile, pages `03`, `04`, `06`, `08`, `09`, `11`, `12`, and `13` are expected to be explicit status pages rather than active long-read analyses. In a short-read WGS profile, page `04` can remain active as a depth-proxy layer, but the long-read structural and molecule-level pages remain status-only.

In long-read mode without ONT bedmethyl sidecars, page `12` is expected to be a stable status-only methylation report while the core long-read analytical pages remain active.

## Optional integrations
- Phy-Mer: optional human mtDNA haplogroup enrichment
- mvTool: optional human mtDNA external annotation enrichment
- these integrations are intentionally non-mandatory and should be treated as secondary annotation layers rather than the core analysis
- the repository's synthetic smoke-test path uses local fixtures to exercise these layers; real biological use should point to a true Phy-Mer vendor tree and the intended mvTool-compatible endpoint
- `mito-overview` does not bundle external Phy-Mer code or mvTool data resources; see [`docs/license_notes.md`](docs/license_notes.md)

## Repository status
- public repository with a functional core, tracked synthetic smoke-test assets, and an active software/resource preprint draft
- current repository now includes a synthetic public example bundle generated from the public-core workflow
- current repository now includes a short-read synthetic bundle plus bounded public long-read and short-read proof-of-principle asset packs
- v0.3.0 public validation evidence was generated from clean commit `dc09114`
- cite the software metadata in [`CITATION.cff`](CITATION.cff) and use tagged releases for archived versions
- canonical free-format manuscript source is [`paper/preprint_draft.md`](paper/preprint_draft.md)
- design notes for the public package are in [`docs/overview.md`](docs/overview.md) and [`docs/methodology.md`](docs/methodology.md)
- public long-read proof-of-principle notes are in [`docs/validation_public_longread.md`](docs/validation_public_longread.md)
- public reduced short-read proof-of-principle notes are in [`docs/validation_public_shortread.md`](docs/validation_public_shortread.md)
- release-readiness requirements are in [`docs/release_checklist.md`](docs/release_checklist.md)
- related-software positioning is in [`docs/related_software_landscape.md`](docs/related_software_landscape.md)
- the current reproducibility evidence ledger is in [`docs/reproducibility_run_ledger.md`](docs/reproducibility_run_ledger.md)
- the current release-validation audit template is in [`docs/release_validation_audit_2026-07-07.md`](docs/release_validation_audit_2026-07-07.md)
- contribution and issue-reporting guidance is in [`CONTRIBUTING.md`](CONTRIBUTING.md)

## Public long-read reduced-input example
The repository includes an asset pack from a fixed deterministic subset of a public ONT targeted-mt run:
- [`examples/public_validation/GM12878_ONT_longread`](examples/public_validation/GM12878_ONT_longread)

This example uses a public GM12878 targeted-mt ONT run from BioProject `PRJNA809571` / run `SRR18110025`, described in the source metadata as `Long read mitochondrial genome sequencing using Cas9-guided adaptor ligation`:
- [NCBI BioProject PRJNA809571](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA809571)
- [ENA run SRR18110025](https://www.ebi.ac.uk/ena/browser/view/SRR18110025)
- [Slapnik et al., Sci Rep 2024](https://www.nature.com/articles/s41598-024-78270-0)
- [Frascarelli et al., Front Genet 2023](https://pubmed.ncbi.nlm.nih.gov/37456669/)

The v0.3.0 input is exactly a seeded deterministic subset of `1,000` query names selected from `193,043` source FASTQ records. Its provenance-verified mapped-only BAM has `728` mapped unique query names represented by `728` primary alignments and `543` supplementary records.

At `MIN_CALLABLE_DEPTH=100`, `MIN_ALT_ALLELE_FRACTION=0.10`, and default BaseQ/MAPQ/readQ filters `13/20/10`, the workflow reports `16` candidates, `7,143,152` accepted observations, and `2,047,476` excluded observations. The structural screen emits `13` singleton CIGAR/SA bins. Statuses are `not_applicable` for copy number and Phy-Mer, `not_configured` for mvTool and methylation, and `not_evaluable` for NUMT interpretation with `reference_scope_mt_only`.

| GM12878 profile | BaseQ/MAPQ/readQ | Candidates | Accepted observations |
| --- | --- | ---: | ---: |
| lenient | `0/0/0` | 32 | 8,278,969 |
| default | `13/20/10` | 16 | 7,143,152 |
| strict | `20/30/15` | 15 | 6,046,355 |

The repeated default invocations start from that same fixed BAM; they do not regenerate the query-name subset or alignment. See [`docs/validation_public_longread.md`](docs/validation_public_longread.md) for the evidence scope.

## Complementary short-read compatibility example
The repository also includes an asset pack from a fixed public short-read input:
- [`examples/public_validation/GM11906_MERRF_shortread`](examples/public_validation/GM11906_MERRF_shortread)

This example uses public GM11906 short-read/scATAC-derived mtDNA reads from the single-cell mtDNA/chromatin profiling study by Lareau and colleagues:
- [Lareau et al., Nat Biotechnol 2021](https://www.nature.com/articles/s41587-020-0645-6)
- [GEO sample metadata example](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238489)
- [Coriell GM11906](https://www.coriell.org/0/Sections/Search/Sample_Detail.aspx?Ref=GM11906)

The short-read example runs with `READ_MODE=short` and `ASSAY_TYPE=targeted_mt`. At `MIN_CALLABLE_DEPTH=10`, `MIN_ALT_ALLELE_FRACTION=0.20`, and default BaseQ/MAPQ/readQ filters `13/20/10`, it reports `33` candidates, `44,052,664` accepted observations, and `7,293,106` excluded observations. The `m.8344A>G` row has depth `1,027`, alternate count `740`, `AF=0.720545`, and `MT-TK` / `tRNA_variant` annotation.

| GM11906 profile | BaseQ/MAPQ/readQ | Candidates | Accepted observations |
| --- | --- | ---: | ---: |
| lenient | `0/0/0` | 33 | 44,052,664 |
| default | `13/20/10` | 33 | 44,052,664 |
| strict | `20/30/15` | 33 | 42,676,166 |

The repeated default invocations start from the same provenance-verified BAM and do not regenerate the alignment. See [`docs/validation_public_shortread.md`](docs/validation_public_shortread.md) for the evidence scope.

## Preprint
A software/resource preprint is in preparation. A citation link and versioned preprint reference will be added here when posted.
