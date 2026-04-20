# mito-overview: a modular Oxford Nanopore mitochondrial DNA interpretation and reporting framework

## Running title
`mito-overview` for modular ONT mtDNA interpretation

## Authors
Elisson Lopes

## Title alternatives
1. `mito-overview`: a modular long-read mitochondrial DNA interpretation and reporting framework
2. A modular Oxford Nanopore mitochondrial DNA evidence-synthesis and reporting workflow
3. `mito-overview`: a reproducible ONT mtDNA software and reporting resource with optional external enrichment layers

## Abstract
Mitochondrial DNA analysis from Oxford Nanopore Technologies (ONT) data often remains fragmented across single-purpose callers, external annotation resources, and custom review steps. This fragmentation is especially limiting for long-read mitochondrial workflows because interpretation may depend not only on variant presence, but also on deletion structure, mtDNA burden proxies, read-level co-segregation, circular-genome edge effects, and warning-oriented quality signals relevant to nuclear mitochondrial DNA segments (NUMTs). We developed `mito-overview`, a modular mtDNA interpretation and reporting framework that converts aligned ONT mitochondrial inputs into layered tabular summaries, figures, and self-contained HTML reports. The current public core implements mitochondrial extraction, QC, heteroplasmy summarization, deletion screening, mt:nuclear depth proxy estimation, feature annotation, co-segregation, gene-level aggregation, NUMT-aware QC, identity QC, variant consequence summaries, circularity-aware QC, and an explicitly exploratory methylation layer. Two optional human-only enrichment layers are also implemented for haplogroup classification and external mtDNA variant annotation through Phy-Mer and mvTool-style integration boundaries. The public repository provides a command-line entry point, environment specification, tracked synthetic validation inputs, a synthetic example output bundle, and smoke-testable regeneration of report pages `01` through `14`. `mito-overview` is positioned as a disease-agnostic research software/resource for ONT mtDNA evidence synthesis and report generation rather than as a standalone caller benchmark or clinical diagnostic test.

## Keywords
mitochondrial DNA; Oxford Nanopore; heteroplasmy; deletions; NUMT; haplogroup; reporting workflow; bioinformatics software

## Introduction
Human mitochondrial DNA (mtDNA) is a small circular genome whose interpretation is biologically and technically distinct from standard linear nuclear analysis. Disease-relevant signal can arise through heteroplasmic single-nucleotide variants, large deletions or rearrangements, mtDNA burden differences, and molecule-level structure. At the same time, interpretation can be distorted by extreme depth, circular-reference edge effects, and nuclear mitochondrial DNA segments (NUMTs), which can generate pseudo-heteroplasmy if they are not handled carefully [1,2]. Oxford Nanopore Technologies (ONT) long reads are attractive in this setting because they can preserve molecule-scale context and improve structural interpretation, but they also increase the number of analytical layers that need to be reviewed coherently [3-6].

The current mtDNA software ecosystem includes valuable specialized resources for haplogroup classification, variant interpretation, and annotated mtDNA reporting. Examples include Phy-Mer for alignment-free haplogroup classification [7], HaploGrep 3 for phylogenetic classification and QC [8], mvTool within MSeqDR for mtDNA annotation and nomenclature handling [9], MitoVisualize for structure-aware mtDNA interpretation [10], MToolBox for automated mtDNA reconstruction and prioritization [11], and mtDNA-Server 2 for human mtDNA variant analysis and interactive reporting [12]. ONT-focused analysis tools are also emerging for long-read heteroplasmy analysis and NUMT-aware read discrimination [6,13]. However, collaborators often still need a compact sample-level workflow that integrates multiple ONT-relevant layers into one report bundle while remaining reproducible, inspectable, and portable.

`mito-overview` was developed to address that practical gap. Its goal is not to replace the strongest task-specific mtDNA tools, nor to claim a new best-in-class caller for each event type. Instead, it provides a modular ONT mtDNA evidence-synthesis and reporting framework that organizes long-read-aware analytical layers into one machine-readable and human-readable sample bundle.

## Software scope and design principles
`mito-overview` was designed around five principles.

First, each analytical question is implemented as an independent step that writes its own summaries, figures, and report page. Second, collaborator-facing report generation is always paired with TSV outputs so that visual review does not come at the expense of downstream reuse. Third, provenance is carried explicitly, including the reference build, mitochondrial contig name, threshold settings, and input-source tracing. Fourth, the reproducible public core is kept separate from optional human-specific enrichments that depend on external tools or services. Fifth, the methylation layer is retained as exploratory context rather than elevated to a primary biological or diagnostic claim, consistent with ongoing caution in the mtDNA methylation literature [14,15].

## Implementation and workflow
The workflow is driven by an environment-style configuration and accepts aligned BAM or CRAM inputs from which mitochondrial reads can be extracted. Configuration records the sample identifier, reference build, mitochondrial contig, thresholds, output paths, and optional integration settings. The public repository packages the workflow as a Python-based framework with a shell runner, CLI entry point, example configuration, smoke test, and reproducible example-bundle builder.

The current implemented workflow consists of 18 steps: `validate`, `stage`, `extract`, 14 analytical/reporting steps, and `sync_bioinfo`. The 12 public-core analytical pages are:

1. mitochondrial QC
2. heteroplasmy
3. deletion screening
4. mt:nuclear depth proxy
5. mitochondrial feature annotation
6. co-segregation
7. gene summary
8. NUMT-aware QC
9. identity QC
10. variant consequence summary
11. circularity-aware QC
12. exploratory methylation

Two optional human-only enrichment pages are also implemented:

13. Phy-Mer haplogroup classification
14. mvTool-style external mtDNA annotation

The core pages are intended to run without external network services. The optional pages are validated in the public repository through local fixtures that preserve the software contract for reproducible smoke testing, while real-world use still depends on the underlying external resources and their terms or availability.

## Public validation assets
The public repository includes tracked synthetic validation inputs (`TOY-001`), a regeneration script for the public example bundle, and a smoke workflow that exercises the full public step chain. As of April 20, 2026, the public validation path includes:

- `python -m mito_overview.cli --list-steps`
- `./tests/smoke_public_pipeline.sh`
- `./scripts/build_public_example_bundle.sh`

These validations were run successfully from the local mirror and from a fresh GitHub clone using the packaged environment. The tracked example bundle currently contains report pages `01` through `14`, corresponding figures, TSV outputs, methylation track tables, and subset assets. Analytical TSV, HTML, and figure outputs are intended to remain stable across rebuilds. The bundled mitochondrial BAM and BAM index are included for inspection convenience, but byte-level identity is not guaranteed across rebuilds because compression and indexing can vary by environment.

The public validation is therefore workflow-level and reproducibility-oriented, not a substitute for cohort-scale benchmark evaluation. The synthetic dataset is intentionally minimal and is designed to validate installation, step connectivity, and output contracts rather than biological realism.

## Relation to current ONT mtDNA evidence
The strongest evidence for ONT mtDNA analysis currently supports structural mtDNA interpretation and moderate-frequency heteroplasmy analysis. Long-read sequencing has been shown to improve detection and interpretation of mtDNA deletions and rearrangements, including cases where apparent single-deletion events resolve into more complex structures under long-read inspection [3,4]. Recent ONT heteroplasmy validation studies reported strong agreement for moderate-level heteroplasmy but also emphasized the need for stringent validation, with a practical detection limit around 12% in one recent study [5].

These observations align with the software boundaries of `mito-overview`. The framework is strongest when used to organize long-read-aware QC, heteroplasmy summaries, deletion screening, mtDNA burden context, and report generation. It is not positioned here as a validated low-VAF diagnostic caller. Likewise, the methylation page is retained as an exploratory context layer only. This is consistent with studies that found no evidence for biologically meaningful CpG methylation in human mtDNA by single-molecule ONT analysis and no evidence for extensive non-CpG mtDNA methylation in reanalysis studies [14,15].

NUMT-aware interpretation is another major reason to treat mtDNA analysis as a dedicated workflow problem rather than a simple variant-listing task. NUMTs are widespread and dynamic in human genomes [1], and published reinterpretations have shown that apparent mtDNA findings can change after better NUMT-aware review [2]. Recent tools such as MitSorter further reinforce the value of explicit read-level discrimination strategies in the ONT setting [13]. In `mito-overview`, this motivates dedicated NUMT-aware and circularity-aware QC pages as warning-oriented interpretive layers rather than hidden implementation details.

## Results and current release scope
The current public release candidate demonstrates that `mito-overview` can produce a modular sample-level mtDNA report bundle from tracked synthetic inputs with reproducible step wiring and explicit output contracts. The public-core workflow produces 12 analytical pages, and the optional enrichment boundary extends that to 14 pages when human-only Phy-Mer and mvTool-style integrations are enabled.

From a software perspective, three results are most important.

First, the workflow architecture is now executable end-to-end in the public repository rather than remaining a packaging scaffold. Second, the optional enrichment layers have been ported into the public mirror with validation fixtures, which means the full public report surface can be exercised without private project dependencies. Third, the repository now includes the assets that are typically missing from ad hoc bioinformatics pipelines: an environment definition, synthetic validation inputs, a smoke test, a reproducible example-bundle builder, tracked example outputs, and documentation that distinguishes public-core logic from optional external integrations.

From a biological interpretation perspective, the report structure intentionally separates distinct questions rather than collapsing them into a single summary statistic. Heteroplasmy, structural burden, NUMT warnings, circularity effects, consequence summaries, and methylation context are exposed as separate layers so that users can localize uncertainty or follow-up needs without losing the broader sample-level picture.

## Discussion
`mito-overview` is best understood as a software/resource contribution for ONT mtDNA evidence synthesis and reporting. Its novelty lies in modular integration, explicit long-read-aware interpretation layers, and a reproducible public-core packaging strategy. The workflow is therefore complementary to existing mtDNA utilities rather than competitive with each of them on their own most specialized task.

This distinction matters for how the framework should be presented. `mito-overview` should not be described as a new haplogroup classifier, a new annotation engine, or a new best-in-class structural variant caller. Instead, it should be positioned as a framework that organizes these analytical surfaces into a coherent report bundle while preserving machine-readable outputs and explicit provenance. This is also the most defensible publication framing given the present validation state.

The current release has clear boundaries. The public validation is synthetic and workflow-oriented rather than cohort-scale. Copy-number remains a depth proxy rather than an absolute mtDNA copy-number estimate. Deletion output is a structural screen driven by alignment structure rather than a specialized SV caller. NUMT and circularity components are warning-oriented QC layers, not formal classifiers. The clearest validated path is currently human mtDNA, and the optional enrichment modules remain human-only. These limitations are not weaknesses of the release narrative; they are part of keeping the software claims aligned with the current evidence and implementation.

## Availability and implementation
Repository:
- [elissonnog/mito-overview](https://github.com/elissonnog/mito-overview)

Implementation assets currently available in the public repository include:
- Python package modules for the workflow and report generation
- shell runner and HPC-oriented wrapper separation
- `environment.yml`
- `pyproject.toml`
- `CITATION.cff`
- tracked synthetic validation inputs
- tracked synthetic example outputs
- smoke-test workflow
- example-bundle regeneration script
- MIT license for the public core repository

Optional external enrichments such as Phy-Mer and mvTool are intentionally kept as integration boundaries rather than bundled redistributable dependencies.

## Limitations and future work
Immediate next steps before journal submission include:
- adding cohort-scale quantitative validation tables
- benchmarking selected outputs against specialized external tools where appropriate
- adding manuscript-ready workflow and report figures
- clarifying versioned release metadata and DOI minting
- extending validated support beyond the current human-focused path

A second future direction is downstream classifier work using `mito-overview` outputs as engineered features. That problem is intentionally outside the scope of the current software/resource paper, which is centered on report generation, reproducible workflow structure, and ONT-aware mtDNA interpretation.

## References
1. Wei W, et al. Nuclear-mitochondrial DNA segments resemble paternally inherited mitochondrial DNA in humans. *Nature*. 2022. [PubMed](https://pubmed.ncbi.nlm.nih.gov/36198798/)
2. Fleischmann E, et al. NUMT confounding can change biological interpretation in mitochondrial analyses. *Mitochondrion*. 2024. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37914096/)
3. Frascarelli C, et al. Nanopore long-read next-generation sequencing for detection of mitochondrial DNA large-scale deletions. *Front Genet*. 2023. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37456669/)
4. Lopriore E, et al. Long-read sequencing resolved an inherited rearranged mtDNA species initially interpreted as a large deletion. *Mitochondrion*. 2025. [PubMed](https://pubmed.ncbi.nlm.nih.gov/40164291/)
5. Slapnik B, et al. The quality and detection limits of mitochondrial heteroplasmy by long read nanopore sequencing. *Sci Rep*. 2024. [Nature](https://www.nature.com/articles/s41598-024-78270-0)
6. Jiang L, et al. CmVCall: An automated and adjustable nanopore analysis pipeline for heteroplasmy detection of the control region in human mitochondrial genome. *Forensic Sci Int Genet*. 2023. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37595417/)
7. Navarro-Gomez D, et al. Phy-Mer: a novel alignment-free and reference-independent mitochondrial haplogroup classifier. *Bioinformatics*. 2015. [PubMed](https://pubmed.ncbi.nlm.nih.gov/25505086/)
8. Schönherr S, et al. HaploGrep 3 - an interactive haplogroup classification and analysis platform. *Nucleic Acids Res*. 2023. [PubMed](https://pubmed.ncbi.nlm.nih.gov/37070190/)
9. Shen L, et al. MSeqDR mvTool: a mitochondrial DNA web and API resource for comprehensive variant annotation, universal nomenclature collation, and reference genome conversion. *Hum Mutat*. 2018. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5992054/)
10. Lake NJ, et al. MitoVisualize: a resource for analysis of variants in human mitochondrial RNAs and DNA. *Bioinformatics*. 2022. [PubMed](https://pubmed.ncbi.nlm.nih.gov/35561159/)
11. Calabrese C, et al. MToolBox: a highly automated pipeline for heteroplasmy annotation and prioritization analysis of human mitochondrial variants in high-throughput sequencing. *Bioinformatics*. 2014. [PubMed](https://pubmed.ncbi.nlm.nih.gov/25028726/)
12. Weissensteiner H, et al. mtDNA-Server 2: advancing mitochondrial DNA analysis through highly parallelized data processing and interactive analytics. *Nucleic Acids Res*. 2024. [PubMed](https://pubmed.ncbi.nlm.nih.gov/38709886/)
13. Cox SN, et al. MitSorter: a standalone tool for accurate discrimination of mtDNA and NuMT ONT reads based on differential methylation. *Bioinformatics Advances*. 2025. [PubMed](https://pubmed.ncbi.nlm.nih.gov/40688360/)
14. Bicci I, et al. Single-molecule mitochondrial DNA sequencing shows no evidence of CpG methylation in human cells and tissues. *Nucleic Acids Res*. 2021. [PubMed](https://pubmed.ncbi.nlm.nih.gov/34850165/)
15. Guitton R, et al. No evidence of extensive non-CpG methylation in mtDNA. *Nucleic Acids Res*. 2022. [PubMed](https://pubmed.ncbi.nlm.nih.gov/35979955/)
