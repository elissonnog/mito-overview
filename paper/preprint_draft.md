# mito-overview: a modular Oxford Nanopore mitochondrial DNA interpretation and reporting framework

## Running title
`mito-overview` for modular ONT mtDNA interpretation

## Authors
Elisson Lopes

## Title alternatives
1. `mito-overview`: a modular long-read mitochondrial DNA interpretation and reporting framework
2. A modular Oxford Nanopore mitochondrial DNA evidence-synthesis and reporting workflow
3. `mito-overview`: collaborator-facing reporting and quality-aware interpretation for ONT mtDNA analysis

## Abstract
Mitochondrial DNA analysis from Oxford Nanopore Technologies (ONT) data is often fragmented across single-purpose scripts, web resources, or ad hoc notebooks, which makes reproducible sample-level interpretation difficult. Long-read mtDNA analysis is also qualitatively different from short-read variant listing alone because ONT data can expose read-level co-segregation, large deletions, depth and copy-number proxies, circularity-related edge effects, and warning signals relevant to nuclear mitochondrial DNA segment (NUMT) interference. We developed `mito-overview`, a modular mitochondrial DNA interpretation and reporting framework that converts aligned ONT mtDNA inputs into layered tabular outputs, figures, and collaborator-facing HTML reports. The current core workflow includes mitochondrial asset extraction, QC, heteroplasmy summarization, deletion and rearrangement screening, copy-number proxy estimation, mitochondrial feature annotation, co-segregation analysis, gene-level aggregation, NUMT-aware QC, identity QC, local consequence summaries, circularity-aware QC, and an explicitly exploratory methylation layer. Optional human-only enrichments are designed as external integrations rather than bundled dependencies, including haplogroup classification and external mtDNA variant annotation. The public mirror is being packaged as a portable scientific core with reproducible configuration, smoke tests, and example outputs while preserving a clear boundary between core logic and optional external services. `mito-overview` is intended as a disease-agnostic research framework for mtDNA interpretation and report generation rather than a clinical diagnostic test.

## Introduction
Mitochondrial DNA (mtDNA) interpretation poses a distinctive bioinformatics challenge. Biological signal can arise through heteroplasmic single-nucleotide variation, large deletions or rearrangements, mtDNA burden differences, and locus-specific read structure. At the same time, technical interpretation is complicated by depth extremes, circular-genome representation, and the presence of nuclear mitochondrial DNA segments (NUMTs). ONT long reads add useful dimensions to this problem because they can preserve molecule-scale context, enabling read-level views of deletion structure and co-occurrence across sites. However, these same advantages increase the number of analytical layers that must be reviewed coherently.

Existing mtDNA software resources are valuable but often focused on one task at a time, such as haplogroup assignment, variant annotation, or deletion calling. In practice, collaborators frequently need a compact sample-level report that integrates multiple analytical layers while remaining reproducible and machine-readable. We therefore developed `mito-overview`, a modular ONT mtDNA reporting workflow organized around one analytical step per major biological question and one HTML page per major report layer. The goal is to support research interpretation, workflow reproducibility, and later manuscript methods generation without requiring users to reconstruct the analysis from scattered intermediate files.

## Software scope and design principles
`mito-overview` was designed around five principles.

First, each analytical question is implemented as an independent step that writes its own summaries, figures, and report page. Second, report generation is paired with tabular outputs so that collaborator-facing review does not come at the expense of downstream reuse. Third, provenance is carried explicitly, including reference build, mitochondrial contig name, threshold settings, and input-source tracing. Fourth, the reproducible core is kept separate from optional external enrichments such as haplogroup or external mtDNA annotation resources. Fifth, methylation is retained as an exploratory long-read context layer rather than elevated to a primary disease-classification claim.

## Inputs and configuration
The workflow is driven by environment-style configuration and accepts aligned mitochondrial or genome-wide BAM/CRAM inputs from which mitochondrial reads can be extracted. Optional inputs can include mitochondrial methylation summaries and human mtDNA annotation resources. Configuration records the sample identifier, mitochondrial contig, reference build, threshold settings, and output paths. This approach allows the same workflow logic to run through a shell wrapper, direct command-line execution, or synthetic smoke tests.

## Core workflow
The current core workflow proceeds through the following analytical layers:

1. **Validation and staging.** Input files, reference provenance, software dependencies, and run-directory structure are verified before analysis begins.
2. **Mitochondrial asset extraction.** Mitochondrial reads are extracted into a compact BAM and indexed for downstream analysis.
3. **Mitochondrial QC.** Read counts, depth profiles, breadth of coverage, mapping-quality summaries, and read-length distributions are summarized.
4. **Heteroplasmy analysis.** Per-position depth and alternate-allele support are summarized to generate candidate heteroplasmy tables and landscape plots.
5. **Deletion and rearrangement screening.** Long-read CIGAR and alignment structure are screened for deletion-like events and clustered candidate intervals.
6. **Copy-number proxy estimation.** Mitochondrial depth is summarized relative to nuclear windows as an mtDNA burden proxy.
7. **Feature annotation.** Candidate sites are mapped onto human mitochondrial genomic features where appropriate.
8. **Co-segregation analysis.** Read-level co-occurrence across selected mitochondrial sites is summarized.
9. **Gene-level aggregation.** Candidate burden is collapsed to mitochondrial genes or feature classes for higher-level interpretation.
10. **NUMT-aware QC.** Read characteristics that may flag NUMT-associated ambiguity are summarized as warning-oriented QC.
11. **Identity QC.** Stable high-support mitochondrial sites are summarized to support sample fingerprinting and consistency review.
12. **Variant consequence summaries.** Local consequence classes and curated context are summarized at the sample level.
13. **Circularity-aware QC.** The artificial edge introduced by linear representation of a circular genome is evaluated explicitly.
14. **Exploratory methylation.** Methylation-like summaries are shown as a secondary pattern-finding layer, with explicit caution against over-interpretation.

Each analytical layer writes tabular summaries, figures, and an HTML page within the sample bundle.

## Optional and exploratory modules
Two optional human-specific enrichments are supported conceptually as external integrations rather than bundled core dependencies. Haplogroup assignment can be added through Phy-Mer, and external mtDNA annotation can be added through mvTool/MSeqDR resources. These enrichments can broaden interpretation, but they remain non-mandatory because they depend on external licensing, service terms, or tool availability. The methylation layer is similarly marked as exploratory and should not be interpreted as the primary biological backbone of a mitochondrial disease classifier.

## Validation and release assets
The current public mirror has been structured around reproducibility and staged release rather than cohort-scale benchmarking. The packaged repository includes:
- a working shell wrapper
- a CLI entry point
- an environment specification
- a representative human example configuration
- a synthetic public example-bundle builder
- a synthetic public example report bundle
- synthetic smoke tests that exercise the public-core analytical chain

The validated internal pipeline has also been run on representative human ONT mtDNA samples, which informed the step structure, report design, and failure-mode handling. At the present stage, the strongest claims are workflow-level: executable modular design, stable sample-bundle outputs, and long-read-aware interpretability.

## Results
From a packaging and reproducibility standpoint, the workflow now supports a full public-core report chain across twelve analytical pages. The synthetic example bundle demonstrates that the public mirror can produce a collaborator-facing HTML report set with matching figures and tabular outputs while avoiding private sample identifiers. The same structure is exercised by the smoke-test workflow, which provides a compact regression target for future refactoring.

The report design intentionally keeps each analytical layer interpretable in isolation. For example, the heteroplasmy page emphasizes per-position support and landscape summaries, the deletion page focuses on structural burden rather than forcing a specialized caller claim, and the NUMT and circularity pages provide warning-oriented technical context around biological interpretation. This separation is useful for collaborator review because it allows specific concerns to be localized without losing access to the broader sample-level summary.

## Discussion
`mito-overview` is intended to fill the gap between single-purpose mtDNA utilities and full custom analysis stacks. Its main strength is not a claim to a new standalone caller for every mtDNA event class. Instead, the framework organizes multiple ONT-relevant analytical layers into a coherent report structure that is easy to inspect, archive, and reuse. This is especially useful for long-read mtDNA work, where quality signals, structural patterns, and per-read context can materially affect interpretation.

The current release also has clear boundaries. The public core does not yet make cohort-scale performance claims. Copy-number remains a proxy rather than an absolute measure. Optional external enrichments should not be confused with bundled redistributable code. Methylation remains exploratory. These boundaries are important because they keep the software claims aligned with the current evidence while leaving room for later quantitative validation.

## Availability and implementation
`mito-overview` is implemented as a modular Python-based workflow with a shell wrapper, environment specification, synthetic smoke test, public example-bundle builder, and per-step reporting utilities. The repository includes:
- a CLI
- a representative example configuration
- a synthetic public example report bundle
- citation metadata in `CITATION.cff`
- an MIT license for the core repository

Repository URL:
- `https://github.com/elissonnog/mito-overview`

The repository is being prepared for public software release as an open-source research workflow. Optional external integrations such as Phy-Mer and mvTool are intentionally kept outside the bundled reproducible core.

## Limitations and future work
Several immediate next steps remain before a final public software paper:
- add quantitative concordance tables for representative human ONT samples
- finish optional integration packaging for haplogroup and external annotation layers
- extend validated support for non-human mitochondrial genomes
- add release artifacts such as a DOI, versioned example datasets, and manuscript-ready figures
