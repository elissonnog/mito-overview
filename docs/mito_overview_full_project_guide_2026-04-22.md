# mito-overview Full Project Guide and Validation Companion

> **Historical v0.2.1 record.** This document preserves the April 2026 project state and its then-current outputs. It is not release evidence for v0.3.0. Use [clean_room_validation_protocol_v0.3.0.md](clean_room_validation_protocol_v0.3.0.md), [reproducibility_run_ledger.md](reproducibility_run_ledger.md), [methodology.md](methodology.md), and the current README for the active release contract and corrected methods. The dated [preprint_release_validation_v0.3.0.md](preprint_release_validation_v0.3.0.md) remains historical candidate evidence.

## Document purpose
This guide is the detailed technical companion for the current `mito-overview` project state. It is written to support four practical goals:

- understand the full workflow from configuration to final report bundle
- map each algorithmic step to the public codebase
- document the tested inputs, outputs, and result meaning for each step
- provide a traceable validation record that can be compared against the current preprint draft

## Current project snapshot

| Item | Current state |
| --- | --- |
| Software | `mito-overview` |
| Version used in the public repo | `0.2.1` |
| Public repository | [elissonnog/mito-overview](https://github.com/elissonnog/mito-overview) |
| Main framing | modular long-read mtDNA interpretation and reporting framework |
| Secondary framing | reduced short-read compatibility profile |
| Main manuscript source | `paper/preprint_draft.md` |
| Main report example bundle | `examples/expected_reports/TOY-001_output` |
| Main long-read public example | `examples/public_validation/GM12878_ONT_longread` |
| Main short-read public example | `examples/public_validation/GM11906_MERRF_shortread` |
| Main claim boundary | workflow/reproducibility support, not clinical validation |

## How to use this guide
Read this document in four passes:

1. read the workflow overview to understand the architecture
2. use the step catalog to find the relevant code module and output page
3. use the detailed step sections to interpret inputs, outputs, and result meaning
4. use the validation sections to decide which parts of the preprint are strongly supported and which parts remain bounded

## Workflow architecture

### Canonical step order
The public workflow order is defined in `mito_overview/workflow.py`.

```python
DEFAULT_STEP_ORDER = [
    "validate",
    "stage",
    "extract",
    "mito_qc",
    "heteroplasmy",
    "deletions",
    "copy_number",
    "feature_annotation",
    "cosegregation",
    "gene_summary",
    "numt_qc",
    "phymer_haplogroup",
    "identity_qc",
    "variant_consequence",
    "mvtool_annotation",
    "circularity_qc",
    "methylation_exploratory",
    "sync_bioinfo",
]
```

### Read profiles

| Profile | Intended input | What stays active | What becomes status-only / `not_applicable` |
| --- | --- | --- | --- |
| `READ_MODE=long` | ONT-style aligned BAM/CRAM plus optional bedmethyl tracks | full long-read report structure | none by default |
| `READ_MODE=short`, `ASSAY_TYPE=targeted_mt` | short-read mt-aligned BAM | QC, heteroplasmy, feature annotation, gene summary, variant consequence, optional mvTool-style annotation | deletions, copy-number proxy, co-segregation, NUMT-aware QC, identity QC, Phy-Mer haplogroup, circularity QC, methylation |
| `READ_MODE=short`, `ASSAY_TYPE=wgs` | short-read whole-genome BAM | same reduced short-read core; copy-number proxy can be re-enabled in principle | long-read-only structural and molecule-level steps remain unsupported |

### Why the profile split matters
The project keeps the ONT long-read logic intact. Short-read support was added as a bounded compatibility path, not as a claim that all long-read biological layers can be reinterpreted from short reads.

### Runtime full-bundle anatomy

```text
output/
  figures/
  methylation/
  report/
    01_mito_qc.html
    ...
    14_mito_mvtool_annotation.html
  subset/
    SAMPLE.MT.bam
    SAMPLE.MT.bam.bai
    SAMPLE.MT.bed
  summary/
    *.tsv
logs/
sync_manifest.tsv
config.env.snapshot
mito.bam
mito.bam.bai
```

Tracked public example directories under `examples/expected_reports/` contain the committed `output/` tree only. Runtime-only files such as `sync_manifest.tsv` are preserved in smoke-test or fresh-run destinations, not in the tracked example directories.

### Representative report views
These are the manuscript-facing long-read and short-read montages together with one supporting optional-enrichment view retained for documentation.

#### Public-core long-read example
![Public ONT long-read example](../paper/figures/figure1_public_longread_validation_montage.png)

#### Optional human-only enrichment views
![Optional enrichment views](../paper/figures/figure3_optional_enrichment_montage.png)

#### Short-read public proof-of-principle example
![Short-read proof-of-principle example](../paper/figures/figure2_shortread_public_validation_montage.png)

## Codebase map

| Module | Role |
| --- | --- |
| `mito_overview/workflow.py` | orchestrates step order, gating, and status-page behavior |
| `mito_overview/config.py` | loads environment-style configuration |
| `mito_overview/paths.py` | defines run directory layout |
| `mito_overview/report_common.py` | shared HTML report rendering helpers |
| `mito_overview/steps/*.py` | one public step module per analytical layer |
| `scripts/run_mito_pipeline.sh` | shell runner around the Python workflow |
| `tests/smoke_public_pipeline.sh` | long-read synthetic end-to-end regression test |
| `tests/smoke_public_pipeline_shortread.sh` | short-read synthetic end-to-end regression test |
| `scripts/build_public_example_bundle.sh` | rebuilds the tracked long-read example bundle |
| `scripts/build_public_shortread_example_bundle.sh` | rebuilds the tracked short-read example bundle |
| `scripts/run_public_shortread_validation_gm11906.sh` | real-data short-read proof-of-principle validation |

## Step catalog

| Step | Page / artifact | Main module | Long default | Short targeted_mt | Main purpose |
| --- | --- | --- | --- | --- | --- |
| `validate` | logs only | `workflow.py` | yes | yes | validate config and required tools |
| `stage` | run context files | `workflow.py` | yes | yes | create run layout and provenance |
| `extract` | subset BAM, BED, bedmethyl subsets | `extract_mito_assets.py` | yes | yes | derive mitochondrial working assets |
| `mito_qc` | `01_mito_qc.html` | `mito_qc.py` | yes | yes | summarize mt read and depth quality |
| `heteroplasmy` | `02_mito_heteroplasmy.html` | `mito_heteroplasmy.py` | yes | yes | detect and summarize mtDNA candidate sites |
| `deletions` | `03_mito_deletions.html` | `mito_deletions.py` | yes | no | screen long-read deletion-like events |
| `copy_number` | `04_mito_copy_number.html` | `mito_copy_number.py` | yes | no for targeted_mt | estimate mt:nuclear depth proxy |
| `feature_annotation` | `05_mito_feature_annotation.html` | `mito_feature_annotation.py` | yes | yes | assign candidate sites to mt features |
| `cosegregation` | `06_mito_cosegregation.html` | `mito_cosegregation.py` | yes | no | evaluate co-occurrence on the same long molecules |
| `gene_summary` | `07_mito_gene_summary.html` | `mito_gene_summary.py` | yes | yes | aggregate site burden to feature/gene level |
| `numt_qc` | `08_mito_numt_qc.html` | `mito_numt_qc.py` | yes | no | warn on ambiguous mt-vs-NUMT patterns |
| `phymer_haplogroup` | `13_mito_phymer_haplogroup.html` | `mito_phymer_haplogroup.py` | optional | no for targeted_mt | human haplogroup enrichment |
| `identity_qc` | `09_mito_identity_qc.html` | `mito_identity_qc.py` | yes | no | summarize fingerprint / concordance context |
| `variant_consequence` | `10_mito_variant_consequence.html` | `mito_variant_consequence.py` | yes | yes | move from site list to biological class |
| `mvtool_annotation` | `14_mito_mvtool_annotation.html` | `mito_mvtool_annotation.py` | optional | optional | attach external mtDNA annotation context |
| `circularity_qc` | `11_mito_circularity_qc.html` | `mito_circularity_qc.py` | yes | no | assess edge effects from linearized mtDNA reference |
| `methylation_exploratory` | `12_mito_methylation_exploratory.html` | `mito_methylation_exploratory.py` | yes | no | summarize ONT bedmethyl context |
| `sync_bioinfo` | final bundle + manifest | `sync_bioinfo.py` | yes | yes | copy final run into persistent destination |

## Detailed step-by-step guide

## 1. `validate`

### Code block / anchor
```python
# Orchestration entry points
mito_overview/workflow.py:365  def _run_validate(...)
mito_overview/workflow.py:348  def write_context_files(...)
```

### Goal
Check that the configuration is coherent before any biological interpretation starts.

### Main inputs
- environment-style config values
- reference FASTA path
- source alignment path
- presence of `samtools`

### Main outputs
- `logs/validate.done`
- a failure message if required configuration or tools are missing

### What the result means
- `ok` means the package can move to staging and extraction
- `failed` means nothing downstream should be trusted yet

### Why this step matters
It protects against interpreting a run that never had the correct input contract.

### Test coverage
- package/runtime checks
- both smoke tests reach `validate`
- fresh-clone validation also depends on this passing

## 2. `stage`

### Code block / anchor
```python
mito_overview/workflow.py:375  def _run_stage(...)
mito_overview/workflow.py:348  def write_context_files(...)
```

### Goal
Create a reproducible run layout and preserve provenance.

### Main inputs
- loaded config
- run root / work root

### Main outputs
- run directory tree
- `stage/run_context.tsv`
- `stage/run_context.json`
- `logs/stage.done`

### What the result means
The run now has a stable provenance footprint that can be traced later in debugging, reporting, and manuscript writing.

### Test coverage
- long-read smoke
- short-read smoke
- example-bundle builders
- fresh-clone validation

## 3. `extract`

### Code block / anchor
```python
mito_overview/workflow.py:383  def _run_extract(...)
mito_overview/steps/extract_mito_assets.py:128  def run_step(...)
```

### Goal
Create the mitochondrial working assets used by all downstream steps.

### Main inputs
- source BAM or CRAM
- reference FASTA
- mt contig name and length
- optional NP / HP1 / HP2 / ungrouped bedmethyl inputs

### Main outputs
- mitochondrial subset BAM
- BAM index
- mitochondrial BED interval
- long-read methylation subset tables when available

### Typical output files
- `subset/SAMPLE.MT.bam`
- `subset/SAMPLE.MT.bam.bai`
- `subset/SAMPLE.MT.bed`
- `methylation/SAMPLE.MT.wf_mods.*.tsv`

### What the result means
This is the working mitochondrial substrate for the rest of the pipeline. If this step is wrong, every downstream page is compromised.

### Test coverage
- long-read smoke
- short-read smoke
- example-bundle builders

## 4. `mito_qc` -> page `01`

### Code block / anchor
```python
mito_overview/steps/mito_qc.py:35  def run_step(...)
```

### Goal
Summarize the basic technical quality of the mitochondrial read set.

### Main inputs
- mitochondrial subset BAM
- species, build, read mode, assay type
- mt length

### Main outputs
- `summary/mito_qc_summary.tsv`
- `summary/mito_depth_per_base.tsv`
- `summary/mito_read_stats.tsv`
- `figures/mito_depth_profile.png`
- `figures/mito_read_length_hist.png`
- `report/01_mito_qc.html`

### What the result means
This page answers:
- how many mt-aligned reads were present
- what the depth profile looks like
- whether the reads span most of the mitochondrial genome
- whether the run has enough technical support to interpret later pages

### Result interpretation
- good depth and long aligned spans increase confidence
- patchy depth or poor alignment fraction weakens downstream interpretation

### Test coverage
- long-read smoke
- short-read smoke
- GM11906 short-read real-data example

## 5. `heteroplasmy` -> page `02`

### Code block / anchor
```python
mito_overview/steps/mito_heteroplasmy.py:81  def run_step(...)
```

### Goal
Detect and summarize candidate mitochondrial variant sites across the whole mtDNA molecule.

### Main inputs
- mitochondrial subset BAM
- reference FASTA
- minimum depth threshold
- minimum VAF threshold

### Main outputs
- `summary/mito_heteroplasmy_all_sites.tsv`
- `summary/mito_heteroplasmy_candidates.tsv`
- `summary/mito_heteroplasmy_summary.tsv`
- `figures/mito_heteroplasmy_landscape.png`
- `figures/mito_heteroplasmy_top_candidates.png`
- `report/02_mito_heteroplasmy.html`

### What the result means
This is the primary candidate-site discovery layer.

It answers:
- where variant signal exists
- how deep the site is
- which alternate base is favored
- what the estimated heteroplasmy fraction is

### Result interpretation
- candidate calls are only as strong as depth, strand balance, and broader QC context
- this step is central for the long-read and short-read paths alike

### Test coverage
- long-read smoke
- short-read smoke
- GM11906 real-data short-read proof-of-principle

## 6. `deletions` -> page `03`

### Code block / anchor
```python
mito_overview/steps/mito_deletions.py:53  def run_step(...)
```

### Goal
Screen long reads for large deletion-like events and cluster them by approximate breakpoint bins.

### Main inputs
- mitochondrial subset BAM
- minimum deletion size threshold
- mt contig and length

### Main outputs
- `summary/mito_deletion_summary.tsv`
- `summary/mito_deletion_events.tsv`
- `summary/mito_deletion_clusters.tsv`
- `summary/mito_deletion_read_flags.tsv`
- `figures/mito_deletion_clusters.png`
- `report/03_mito_deletions.html`

### What the result means
This step provides a structural screen for long-read mtDNA deletion burden.

### Result interpretation
- positive clusters suggest recurring deletion-like molecules
- this is a screen, not a specialized SV caller or breakpoint assembler

### Short-read behavior
- `not_applicable` in short-read mode

### Test coverage
- long-read smoke
- long-read example-bundle regeneration
- short-read smoke verifies correct `not_applicable` status

## 7. `copy_number` -> page `04`

### Code block / anchor
```python
mito_overview/steps/mito_copy_number.py:57  def run_step(...)
```

### Goal
Estimate a cautious mt:nuclear depth proxy by comparing mean mt depth against a small set of nuclear windows.

### Main inputs
- original source alignment
- reference FASTA
- mt depth table from `mito_qc`
- species

### Main outputs
- `summary/mito_copy_number_summary.tsv`
- `summary/mito_copy_number_windows.tsv`
- `figures/mito_copy_number_proxy.png`
- `report/04_mito_copy_number.html`

### What the result means
This step estimates mt abundance relative to nuclear depth.

### Result interpretation
- useful as a proxy for mtDNA burden in WGS-like settings
- not an absolute copy-number estimate

### Short-read behavior
- `not_applicable` for targeted mtDNA assays

### Test coverage
- long-read smoke
- long-read example-bundle regeneration
- short-read smoke verifies `not_applicable` for targeted mtDNA

## 8. `feature_annotation` -> page `05`

### Code block / anchor
```python
mito_overview/steps/mito_feature_annotation.py:106  def run_step(...)
```

### Goal
Turn site positions into mitochondrial biological context using feature annotation.

### Main inputs
- heteroplasmy candidate table
- human mtDNA GTF
- species/build/mt contig

### Main outputs
- `summary/mito_feature_catalog.tsv`
- `summary/mito_feature_overlap_candidates.tsv`
- `summary/mito_feature_annotation_summary.tsv`
- `figures/mito_feature_annotation.png`
- `report/05_mito_feature_annotation.html`

### What the result means
This step answers whether candidate sites fall in:
- control region
- protein-coding genes
- rRNA genes
- tRNA genes
- intergenic space

### Result interpretation
- it is the first transition from site discovery to biological meaning
- many downstream interpretation layers depend on it

### Test coverage
- long-read smoke
- short-read smoke
- GM11906 real-data short-read example

## 9. `cosegregation` -> page `06`

### Code block / anchor
```python
mito_overview/steps/mito_cosegregation.py:295  def run_step(...)
```

### Goal
Evaluate whether selected mtDNA candidate sites co-occur on the same long reads.

### Main inputs
- mitochondrial subset BAM
- heteroplasmy candidate table

### Main outputs
- `summary/mito_cosegregation_summary.tsv`
- `summary/mito_cosegregation_selected_sites.tsv`
- `summary/mito_cosegregation_pairwise.tsv`
- `summary/mito_cosegregation_read_burden.tsv`
- `figures/mito_cosegregation_heatmap.png`
- `report/06_mito_cosegregation.html`

### What the result means
This step is a molecule-level layer. It asks whether selected alternate alleles tend to occur together on the same long molecules.

### Result interpretation
- useful for haplotype-like context and molecule-level complexity
- not meaningful in the same way for short reads

### Short-read behavior
- `not_applicable`

### Test coverage
- long-read smoke
- short-read smoke verifies `not_applicable`

## 10. `gene_summary` -> page `07`

### Code block / anchor
```python
mito_overview/steps/mito_gene_summary.py:336  def run_step(...)
```

### Goal
Aggregate site-level burden into feature-level / gene-level summaries.

### Main inputs
- feature overlap table
- heteroplasmy candidate table
- co-segregation selected sites
- deletion event and cluster summaries when available

### Main outputs
- `summary/mito_gene_summary.tsv`
- `summary/mito_gene_summary_run_summary.tsv`
- `summary/mito_gene_summary_site_details.tsv`
- `figures/mito_gene_summary_overview.png`
- `report/07_mito_gene_summary.html`

### What the result means
This step compresses many site-level observations into a feature-centric summary, making it easier to interpret the biological burden by mitochondrial gene or feature.

### Result interpretation
- helpful for prioritization and narrative writing
- often one of the easiest pages for a reader to interpret quickly

### Test coverage
- long-read smoke
- short-read smoke
- GM11906 real-data short-read example

## 11. `numt_qc` -> page `08`

### Code block / anchor
```python
mito_overview/steps/mito_numt_qc.py:143  def run_step(...)
```

### Goal
Flag patterns that may weaken confidence because they resemble ambiguous mt-vs-NUMT behavior.

### Main inputs
- `mito_qc` summary and read-level tables
- read span, mapping quality, supplementary alignment patterns

### Main outputs
- `summary/mito_numt_qc_summary.tsv`
- `figures/mito_numt_qc_metric_bars.png`
- `figures/mito_numt_qc_mapq_vs_span.png`
- `report/08_mito_numt_qc.html`

### What the result means
This is a warning-oriented QC layer, not a formal classifier.

### Result interpretation
- helps flag caution scenarios
- should temper confidence in borderline mtDNA findings

### Short-read behavior
- `not_applicable` in the current short-read profile

### Test coverage
- long-read smoke
- short-read smoke verifies `not_applicable`

## 12. `phymer_haplogroup` -> page `13`

### Code block / anchor
```python
mito_overview/steps/mito_phymer_haplogroup.py:147  def run_step(...)
```

### Goal
Add optional human haplogroup context using a Phy-Mer-compatible interface.

### Main inputs
- all-site heteroplasmy table
- reference FASTA
- major-variant thresholds
- local Phy-Mer-compatible fixture or vendor tree

### Main outputs
- `summary/mito_phymer_haplogroup_summary.tsv`
- `summary/mito_phymer_haplogroup_ranking.tsv`
- `summary/mito_phymer_major_variant_input.tsv`
- `summary/mito_phymer_consensus.fasta`
- `summary/mito_phymer_raw_output.txt`
- `summary/mito_phymer_raw_error.txt`
- `figures/mito_phymer_haplogroup_scores.png`
- `report/13_mito_phymer_haplogroup.html`

### What the result means
This is an optional lineage-context enrichment layer for human mtDNA.

### Result interpretation
- useful for human haplogroup context
- exercised in the public repo with local fixtures, not live external benchmarking

### Short-read behavior
- `not_applicable` for targeted mtDNA in the current profile

### Test coverage
- long-read smoke with fixture-based interface testing
- short-read smoke verifies `not_applicable`

## 13. `identity_qc` -> page `09`

### Code block / anchor
```python
mito_overview/steps/mito_identity_qc.py:77  def run_step(...)
```

### Goal
Summarize mitochondrial fingerprint consistency and overlap with optional variant sources.

### Main inputs
- heteroplasmy candidates
- optional VCF-like comparison inputs
- optional haplogroup summary

### Main outputs
- `summary/mito_identity_qc_summary.tsv`
- `summary/mito_identity_major_variant_fingerprint.tsv`
- `summary/mito_identity_vcf_comparison.tsv`
- `figures/mito_identity_vcf_overlap.png`
- `report/09_mito_identity_qc.html`

### What the result means
This page gives sample-level mitochondrial identity context and overlap structure.

### Result interpretation
- useful as a coherence / concordance layer
- not a contamination classifier

### Short-read behavior
- `not_applicable`

### Test coverage
- long-read smoke
- short-read smoke verifies `not_applicable`

## 14. `variant_consequence` -> page `10`

### Code block / anchor
```python
mito_overview/steps/mito_variant_consequence.py:307  def run_step(...)
```

### Goal
Assign local biological consequence classes to candidate mtDNA sites.

### Main inputs
- heteroplasmy candidates
- feature overlap table
- feature catalog
- reference FASTA
- optional local ClinVar VCF

### Main outputs
- `summary/mito_variant_consequence_summary.tsv`
- `summary/mito_variant_consequence_candidates.tsv`
- `summary/mito_variant_consequence_class_summary.tsv`
- `summary/mito_variant_consequence_clinvar_summary.tsv`
- `figures/mito_variant_consequence_classes.png`
- `figures/mito_variant_consequence_clinvar.png`
- `report/10_mito_variant_consequence.html`

### What the result means
This page translates candidates into interpretable classes such as:
- synonymous
- nonsynonymous
- tRNA variant
- rRNA variant
- control-region or intergenic context

### Result interpretation
- moves the workflow closer to biological and pathogenicity-oriented reasoning
- still depends on exact local annotation logic and optional ClinVar configuration

### Test coverage
- long-read smoke
- short-read smoke
- GM11906 real-data short-read example

## 15. `mvtool_annotation` -> page `14`

### Code block / anchor
```python
mito_overview/steps/mito_mvtool_annotation.py:149  def run_step(...)
```

### Goal
Attach optional external mtDNA annotation context using an mvTool-style interface.

### Main inputs
- heteroplasmy candidate table
- mvTool-style endpoint or local fixture
- batch size / timeout settings

### Main outputs
- `summary/mito_mvtool_annotation_summary.tsv`
- `summary/mito_mvtool_annotation_candidates.tsv`
- `summary/mito_mvtool_annotation_batches.tsv`
- `summary/mito_mvtool_status_counts.tsv`
- `summary/mito_mvtool_disease_summary.tsv`
- `summary/mito_mvtool_population_bins.tsv`
- `figures/mito_mvtool_status_counts.png`
- `figures/mito_mvtool_population_context.png`
- `report/14_mito_mvtool_annotation.html`

### What the result means
This is an optional external-annotation context layer. It adds population-frequency and status-style interpretation on top of local candidate detection.

### Result interpretation
- useful for annotation enrichment
- placeholder values are explicitly filtered so the page focuses on usable external annotation
- public repo coverage is fixture-based interface testing, not live endpoint benchmarking

### Test coverage
- long-read smoke with local fixtures
- short-read smoke with local fixtures

## 16. `circularity_qc` -> page `11`

### Code block / anchor
```python
mito_overview/steps/mito_circularity_qc.py:135  def run_step(...)
```

### Goal
Assess whether the linear representation of the circular mtDNA molecule may bias edge behavior.

### Main inputs
- mt depth per base
- mt read stats
- heteroplasmy candidates
- edge window size

### Main outputs
- `summary/mito_circularity_qc_summary.tsv`
- `figures/mito_circularity_edge_depth.png`
- `figures/mito_circularity_edge_metrics.png`
- `report/11_mito_circularity_qc.html`

### What the result means
This is a warning-oriented QC layer that asks whether the beginning/end of the linearized reference are behaving unusually.

### Result interpretation
- useful for edge-effect caution
- not a direct variant caller

### Short-read behavior
- `not_applicable`

### Test coverage
- long-read smoke
- short-read smoke verifies `not_applicable`

## 17. `methylation_exploratory` -> page `12`

### Code block / anchor
```python
mito_overview/steps/mito_methylation_exploratory.py:152  def run_step(...)
```

### Goal
Summarize ONT bedmethyl tracks in a clearly exploratory form.

### Main inputs
- NP / HP1 / HP2 / ungrouped mt bedmethyl subsets

### Main outputs
- `summary/mito_methylation_exploratory_summary.tsv`
- `summary/mito_methylation_np_vs_proxy.tsv`
- `summary/mito_methylation_np_vs_proxy_summary.tsv`
- `summary/mito_methylation_track_rows.tsv`
- `figures/mito_methylation_profiles.png`
- `figures/mito_methylation_weighted_summary.png`
- `figures/mito_methylation_np_vs_proxy.png`
- `report/12_mito_methylation_exploratory.html`

### What the result means
This is context only. It is intentionally not positioned as a primary disease classifier or clinical layer.

### Result interpretation
- useful for exploratory signal inspection
- manuscript claims should remain very cautious here

### Short-read behavior
- `not_applicable`

### Test coverage
- long-read smoke
- short-read smoke verifies `not_applicable`

## 18. `sync_bioinfo`

### Code block / anchor
```python
mito_overview/steps/sync_bioinfo.py:33  def run_step(...)
```

### Goal
Copy the finished run products into a stable final bundle for human inspection and archival reuse.

### Main inputs
- `output/`
- `logs/`
- subset BAM and BAI
- config snapshot

### Main outputs
- final persistent bundle
- `sync_manifest.tsv`
- copied `mito.bam`
- copied `config.env.snapshot`

### What the result means
This is the final packaging step. It defines the human-facing deliverable of the workflow.

### Test coverage
- long-read smoke
- short-read smoke
- example-bundle regeneration scripts
- fresh-clone reproducibility

## Tests performed

## Validation matrix

| Test | Main script / action | Inputs | Expected result | Observed result | What it supports |
| --- | --- | --- | --- | --- | --- |
| package/runtime integrity | `python -m mito_overview.cli --list-steps` | public package install | package loads and exposes steps | passed | structural usability |
| long-read synthetic smoke | `tests/smoke_public_pipeline.sh` | `TOY-001` synthetic long-read inputs | pages `01-14` produced | passed | long-read workflow continuity |
| long-read example-bundle regeneration | `scripts/build_public_example_bundle.sh` | tracked long-read toy inputs | rebuild tracked example bundle | passed | reproducible documentation assets |
| short-read synthetic smoke | `tests/smoke_public_pipeline_shortread.sh` | synthetic short-read toy inputs | active short-read pages run, unsupported pages become `not_applicable` | passed | honest short-read gating |
| short-read example-bundle regeneration | `scripts/build_public_shortread_example_bundle.sh` | tracked short-read toy inputs | rebuild tracked short-read example bundle | passed | reproducible reduced-profile docs |
| real public ONT long-read proof-of-principle | `scripts/run_public_longread_validation_gm12878.sh` | GM12878 public ONT targeted-mt run | execute active long-read report layers on real data with explicit targeted-mt boundaries | passed | real-data long-read operability and report generation |
| real public short-read proof-of-principle | `scripts/run_public_shortread_validation_gm11906.sh` | pooled GM11906 public runs | recover and annotate `m.8344A>G` in short-read mode | passed | real-data execution and site representation |
| fresh-clone validation | clone + rerun workflow checks | published GitHub repo | public state works outside original tree | passed | published-repo reproducibility |

## Why the tests were done

| Test class | Why it exists | What a pass means | What a pass does not mean |
| --- | --- | --- | --- |
| package/runtime | prevent silent packaging breakage | code can load and steps can be discovered | not biological validation |
| smoke workflow | protect against regression in step wiring | end-to-end workflow still runs | not cohort-scale benchmarking |
| example-bundle rebuild | prove figures/docs come from rebuildable assets | documentation is tied to tracked outputs | not analytical calibration |
| short-read gating | prevent misuse of long-read-only layers | unsupported steps are honestly labeled | not modality equivalence |
| real-data proof-of-principle | show public data can run through the bounded workflow profiles | report-native outputs and key sites/signals can be recovered honestly | not clinical or cohort-scale validation |
| fresh clone | verify the published repo is usable outside the dev tree | public state is reproducible on the validated Mac | not all-environment portability |

## Real public long-read result table: GM12878

### Key findings
| Metric | Value |
| --- | --- |
| sample_id | `GM12878_ONT_longread` |
| read_mode | `long` |
| assay_type | `targeted_mt` |
| heteroplasmy_min_vaf | `0.10` |
| mapped_reads | `247254.0` |
| mean_depth | `106379.759` |
| median_depth | `106032.0` |
| full_length_fraction | `0.3758` |
| candidate_site_count | `28` |
| selected_cosegregation_sites | `8` |
| candidate_deletion_clusters | `1337.0` |
| max_deletion_support_fraction_primary | `2.1e-05` |
| numt_risk | `moderate` |
| copy_number_status | `not_applicable` |
| phymer_status | `not_applicable` |
| methylation_status | `no_mt_bedmethyl_rows_available` |

### What this result means
- the long-read profile can execute on real public ONT data and generate the expected report-native QC, heteroplasmy, deletion-screening, co-segregation, gene-summary, NUMT-QC, circularity-QC, and consequence outputs
- targeted-mt assay boundaries remain explicit instead of being silently overinterpreted
- the public asset pack now contains real ONT figures that can be used in the paper and GitHub page

### What this result does not mean
- it is not full `01-14` page coverage
- it is not identity-style long-read validation
- it is not low-VAF heteroplasmy benchmarking
- it is not deletion-truth benchmarking
- it is not clinical validation

## Real public short-read result table: GM11906

### Key findings
| Metric | Value |
| --- | --- |
| sample_id | `GM11906_MERRF_shortread` |
| read_mode | `short` |
| assay_type | `targeted_mt` |
| mapped_reads | `1357178.0` |
| mean_depth | `3098.625` |
| median_depth | `3144.0` |
| high_query_alignment_fraction | `0.9864` |
| candidate_site_count | `34` |

### Target site `m.8344A>G`
| position | ref_base | alt_base | depth | alt_count | heteroplasmy_fraction | alt_forward | alt_reverse |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8344 | A | G | 1041 | 754 | 0.724304 | 307 | 447 |

### Local biological interpretation for `m.8344A>G`
| feature_label | feature_class | consequence_class |
| --- | --- | --- |
| `MT-TK` | `Mt_tRNA` | `tRNA_variant` |

### Top feature-level summary from the public short-read example
| feature_label | feature_class | candidate_sites | max_heteroplasmy | mean_heteroplasmy | top_site |
| --- | --- | --- | --- | --- | --- |
| D-loop/control region | control_region | 11 | 1.0 | 0.997818 | 228:G>A |
| MT-CYB | protein_coding | 4 | 1.0 | 0.99825 | 14798:T>C |
| MT-RNR2 | Mt_rRNA | 3 | 0.999399 | 0.98696 | 3010:G>A |
| MT-ND4 | protein_coding | 3 | 0.99881 | 0.996443 | 12127:G>A |
| MT-CO1 | protein_coding | 3 | 0.997882 | 0.990875 | 7028:C>T |

### What this result means
- the reduced short-read profile can execute on real public data
- it can report and contextualize a previously reported pathogenic mtDNA site
- it gives a real-data proof-of-principle example for the short-read compatibility path

### What this result does not mean
- it is not modality-matched or cohort-scale short-read validation
- it is not a calibrated short-read heteroplasmy benchmark
- it is not clinical validation
- it does not establish accurate mt:nuclear copy-number estimation for non-WGS assays
- it does not validate long-read-only layers in short-read mode
- it does not establish definitive NUMT discrimination from an mt-only alignment strategy

## How the current preprint is supported

| Preprint claim type | Supported by | Current strength | Current limit |
| --- | --- | --- | --- |
| package exists and runs from the public repo | CLI step listing + fresh-clone validation | strong | validated on the current Mac environment, not every environment |
| long-read workflow produces the intended report structure | long-read smoke + long-read example-bundle rebuild | strong | workflow/reproducibility support, not cohort-scale benchmarking |
| optional human layers exist in the public repo | fixture-based smoke tests | moderate | interface/report-generation support, not live external benchmarking |
| short-read compatibility path exists | short-read smoke | strong | reduced profile only |
| long-read path runs on real public ONT data | GM12878 proof-of-principle | moderate | targeted-mt exemplar, not WGS-style or cohort-scale benchmarking |
| short-read path runs on real public data | GM11906 proof-of-principle | moderate | one public example, not modality-matched benchmarking |
| manuscript figures come from rebuildable repo assets | example-bundle regeneration scripts | strong | binary assets are not guaranteed byte-identical across every environment |

## Known project boundaries

| Area | Current boundary |
| --- | --- |
| clinical use | not a clinical diagnostic test |
| deletion calling | structural screen, not a specialized SV caller |
| copy number | mt:nuclear depth proxy, not absolute copy-number estimation |
| NUMT | warning-oriented QC, not a formal classifier |
| circularity | warning-oriented QC, not a direct variant-calling correction engine |
| methylation | exploratory only |
| short-read mode | compatibility path, not full modality-matched validation |
| optional Phy-Mer / mvTool pages | exercised with local fixtures in the public repo, not presented as live-endpoint validation |

## Key project files to inspect directly

### Workflow and orchestration
- `mito_overview/workflow.py`
- `mito_overview/config.py`
- `mito_overview/paths.py`
- `mito_overview/report_common.py`

### Step modules
- `mito_overview/steps/extract_mito_assets.py`
- `mito_overview/steps/mito_qc.py`
- `mito_overview/steps/mito_heteroplasmy.py`
- `mito_overview/steps/mito_deletions.py`
- `mito_overview/steps/mito_copy_number.py`
- `mito_overview/steps/mito_feature_annotation.py`
- `mito_overview/steps/mito_cosegregation.py`
- `mito_overview/steps/mito_gene_summary.py`
- `mito_overview/steps/mito_numt_qc.py`
- `mito_overview/steps/mito_phymer_haplogroup.py`
- `mito_overview/steps/mito_identity_qc.py`
- `mito_overview/steps/mito_variant_consequence.py`
- `mito_overview/steps/mito_mvtool_annotation.py`
- `mito_overview/steps/mito_circularity_qc.py`
- `mito_overview/steps/mito_methylation_exploratory.py`
- `mito_overview/steps/sync_bioinfo.py`

### Validation and examples
- `tests/smoke_public_pipeline.sh`
- `tests/smoke_public_pipeline_shortread.sh`
- `scripts/build_public_example_bundle.sh`
- `scripts/build_public_shortread_example_bundle.sh`
- `scripts/run_public_shortread_validation_gm11906.sh`
- `examples/expected_reports/TOY-001_output`
- `examples/expected_reports/TOY-SR-001_output`
- `examples/public_validation/GM11906_MERRF_shortread`

### Manuscript-facing files
- `paper/mito_overview_workflow_resource_manuscript_2026-06-23.md`
- `paper/figures/figure1_public_longread_validation_montage.png`
- `paper/figures/figure3_optional_enrichment_montage.png`
- `paper/figures/figure2_shortread_public_validation_montage.png`

## Bottom line
`mito-overview` currently stands on a clear and internally consistent foundation:

- the public repository contains the full current workflow structure
- each analytical layer is split into an independent module with explicit outputs
- long-read behavior is the main supported path
- short-read behavior is present as a bounded reduced profile
- the public repo includes synthetic workflow validation plus bounded real public long-read and short-read proof-of-principle examples
- the current preprint can be checked against this document step by step

This guide is therefore intended to function as the project-level reference for technical understanding, validation review, and manuscript cross-checking.
