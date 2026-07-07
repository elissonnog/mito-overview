# Related Software Landscape

`mito-overview` is positioned as a mode-gated mtDNA report-generation workflow. It does not replace specialized mtDNA callers, haplogroup classifiers, NUMT-discrimination tools, or clinical interpretation resources. Its intended role is to synchronize per-sample HTML, TSV, and figure outputs while making unsupported assay contexts explicit.

## Comparator Matrix

| Tool or resource | Primary role | Typical strength | Relationship to `mito-overview` |
| --- | --- | --- | --- |
| MToolBox | mtDNA variant processing and heteroplasmy annotation from high-throughput sequencing | automated mitochondrial variant annotation and prioritization | complementary upstream or comparator workflow; `mito-overview` focuses on report bundling and assay-mode status pages |
| mtDNA-Server / mtDNA-Server 2 | scalable mtDNA analysis and interactive analytics | server-scale processing, heteroplasmy analytics, haplogroup-aware review | complementary analytical environment; `mito-overview` focuses on local per-sample HTML/TSV/figure handoff |
| HaploGrep / HaploGrep 3 | mitochondrial haplogroup classification | haplogroup assignment and interactive haplogroup analysis | preferred tool when haplogroup classification is the primary task |
| Phy-Mer | alignment-free mitochondrial haplogroup classification | reference-independent haplogroup classification | optional human-only interface target; public package uses fixtures unless live external use is documented |
| mvTool / MSeqDR | mtDNA variant annotation, nomenclature collation, and reference conversion | disease-resource context and mtDNA annotation support | optional annotation-enrichment target; not required for core report generation |
| MitoVisualize | mitochondrial DNA/RNA variant visualization and structure-aware resources | visual and structural context for mtDNA and mtRNA variants | complementary resource; `mito-overview` provides executable per-sample report bundles |
| Haplocheck | mtDNA contamination and quality assessment | mixture/contamination screening | useful external QC comparator; not implemented as a replacement in `mito-overview` |
| MitSorter | ONT mtDNA versus NuMT read discrimination | specialized modification-aware read discrimination | appropriate comparator/downstream tool for formal NUMT discrimination; `mito-overview` reports warning-oriented QC labels only |
| MitoSeek, Mutserve, mitoCaller, GATK-style mtDNA workflows | mtDNA variant calling and benchmarking contexts | variant calling and comparative performance evaluation | relevant benchmarks for future validation; `mito-overview` currently reports thresholded candidates and does not claim caller-level benchmarking |
| MultiQC | cross-tool report aggregation | standardizing scattered QC outputs into a reusable report | conceptual precedent for the report-object contribution, not an mtDNA-specific comparator |

## Gap Addressed

Existing tools solve important specialized tasks, but a per-sample mtDNA review often still requires manual inspection across alignments, thresholded candidate tables, structural-screen outputs, gene context, QC warnings, figures, and pages that are not interpretable for the assay. `mito-overview` addresses this handoff gap by:

1. Generating synchronized HTML, TSV, and figure outputs from the same staged mitochondrial assets.
2. Separating active, optional, conditional, and `not_applicable` report layers by read mode and assay type.
3. Preserving long-read evidence layers without borrowing those claims for reduced short-read inputs.
4. Exposing warning-oriented QC surfaces without presenting them as calibrated clinical or classifier outputs.

## Claim Boundary

The public repository supports workflow/resource claims: installability, step exposure, synthetic smoke tests, proof-of-principle public data report generation, and explicit assay-mode gating. It does not currently support clinical interpretation, low-VAF sensitivity, deletion-truth benchmarking, absolute copy-number truth, formal NUMT classification, live Phy-Mer/mvTool interoperability, or cohort-scale benchmarking.
