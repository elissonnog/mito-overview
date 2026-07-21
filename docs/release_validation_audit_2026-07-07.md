# mito-overview v0.2.1 Release Validation Audit

> **Historical immutable-release record.** This audit applies only to v0.2.1 at `2ba62b775a7204c0dc61f5408989603f536c78da`. Its public metrics and method descriptions are superseded for v0.3.0 by [preprint_release_validation_v0.3.0.md](preprint_release_validation_v0.3.0.md); they must not be used as v0.3.0 manuscript or release evidence.

Date: 2026-07-07

Repository: `https://github.com/elissonnog/mito-overview`

Release candidate branch: historical GitHub release-readiness branch

Release target: `v0.2.1`

Canonical manuscript source: `paper/preprint_draft.md`

Validation packet: external local release artifact, not included in this repository.

## Scientific Scope

This validation packet supports a conservative workflow/resource software preprint. The supported claim is that `mito-overview` provides a reproducible, mode-gated mtDNA reporting workflow with synthetic long-read and reduced short-read smoke coverage plus bounded public proof-of-principle assets. It does not support clinical diagnostic use, calibrated low-VAF sensitivity, deletion-truth benchmarking, absolute mtDNA copy-number accuracy, formal NUMT-classifier performance, mtDNA methylation biology, live external-tool validation, or long-read/short-read equivalence.

## Release Candidate Metadata

| Field | Value |
| --- | --- |
| Version | `0.2.1` |
| Tag | `v0.2.1` |
| Exact tag target commit | `2ba62b775a7204c0dc61f5408989603f536c78da` |
| GitHub release archive | `https://github.com/elissonnog/mito-overview/releases/tag/v0.2.1` |
| External archive DOI or SWHID | Not assigned at local validation time; add after Zenodo or Software Heritage archival |
| Authors | Elisson Lopes; Xiaowu Gai |
| Affiliation | Medical College of Wisconsin, Milwaukee, Wisconsin, USA |
| Funding | Not declared |
| Competing interests | The authors declare no competing interests |

## Commands

Run commands from a clean release checkout. Use `MITO_OVERVIEW_PYTHON` when validating with a dedicated local environment.

```bash
python -m mito_overview.cli --list-steps
python -m mito_overview.cli --config examples/configs/human_example.env --dry-run
./tests/smoke_public_pipeline.sh
./tests/smoke_public_pipeline_shortread.sh
./tests/smoke_public_pipeline_longread_nomethyl.sh
./scripts/build_public_example_bundle.sh "${OUT_DIR}/TOY-001_output"
./scripts/build_public_shortread_example_bundle.sh "${OUT_DIR}/TOY-SR-001_output"
./scripts/run_public_longread_validation_gm12878.sh "${OUT_DIR}/GM12878_ONT_longread_output"
./scripts/run_public_shortread_validation_gm11906.sh "${OUT_DIR}/GM11906_MERRF_shortread_output"
```

## Local Validation Results

| Check | Status | Transcript |
| --- | --- | --- |
| CLI list steps | PASS | `logs/01_list_steps.stdout`, `logs/01_list_steps.stderr` |
| CLI dry run | PASS | `logs/02_dry_run.stdout`, `logs/02_dry_run.stderr` |
| synthetic long-read smoke | PASS | `logs/03_smoke_longread.stdout`, `logs/03_smoke_longread.stderr` |
| synthetic short-read smoke | PASS | `logs/04_smoke_shortread.stdout`, `logs/04_smoke_shortread.stderr` |
| long-read no-methylation smoke | PASS | `logs/05_smoke_longread_nomethyl.stdout`, `logs/05_smoke_longread_nomethyl.stderr` |
| synthetic long-read bundle rebuild | PASS | `logs/06_build_toy_longread.stdout`, `logs/06_build_toy_longread.stderr` |
| synthetic short-read bundle rebuild | PASS | `logs/07_build_toy_shortread.stdout`, `logs/07_build_toy_shortread.stderr` |
| public GM12878 ONT rerun | DEFERRED | FASTQ `SRR18110025_1.fastq.gz` is approximately 1.9 GB before alignment; tracked public asset pack was inspected instead |
| public GM11906 short-read rerun | PASS | `logs/09_public_gm11906_shortread.stdout`, `logs/09_public_gm11906_shortread.stderr` |
| output inventory | PASS | `metadata/output_file_inventory.txt` has 251 files |
| output SHA-256 checksums | PASS | `metadata/output_sha256.txt` has 251 checksums |
| text hygiene | PASS with expected docs terms | no manuscript-body tool-process wording detected; non-release docs still use ordinary terms such as placeholder filtering |
| DOCX/PDF render QA | PASS | DOCX `paper/mito_overview_workflow_resource_manuscript_v0.2.1.docx`; PDF `paper/rendered_v0.2.1/mito_overview_workflow_resource_manuscript_v0.2.1.pdf`; 14 rendered page PNGs plus contact sheet in `paper/rendered_v0.2.1/` |

## Expected Public Long-Read Values

These values are expected from the tracked GM12878 public proof-of-principle asset pack and should be compared with any regenerated rerun:

| Metric | Expected value | Source |
| --- | --- | --- |
| mapped reads | `247254` | `examples/public_validation/GM12878_ONT_longread/GM12878_ONT_longread_key_findings.tsv` |
| mean depth | `106379.759` | same |
| candidate sites at `HET_MIN_VAF=0.10` | `28` | same |
| selected co-segregation sites | `8` | same |
| NUMT heuristic risk | `moderate` | same |
| copy-number status | `not_applicable` for targeted-mt | same |
| Phy-Mer status | `not_applicable` for targeted-mt public rerun | same |
| methylation status | status-only/no mitochondrial bedmethyl rows | `summary/mito_methylation_exploratory_summary.tsv` |

## Expected Public Short-Read Values

These values are expected from the tracked GM11906 reduced short-read asset pack and should be compared with any regenerated rerun:

| Metric | Expected value | Source |
| --- | --- | --- |
| marker | `m.8344A>G` | `examples/public_validation/GM11906_MERRF_shortread/GM11906_MERRF_shortread_site_8344.tsv` |
| depth | `1041` | same |
| alternate count | `754` | same |
| heteroplasmy fraction | `0.724304` | same |
| feature | `MT-TK` | same |
| consequence | `tRNA_variant` | `GM11906_MERRF_shortread_site_8344_consequence.tsv` |

Fresh validation on 2026-07-07 regenerated the GM11906 reduced short-read output from public FASTQs after network escalation was required for EBI DNS access. The marker-level values were reproduced exactly: position `8344`, `A>G`, depth `1041`, alternate count `754`, heteroplasmy fraction `0.724304`, `MT-TK`, and `tRNA_variant`. The fresh rerun emitted 14 report pages and retained explicit `not_applicable` status pages for unsupported long-read-only layers. The total candidate-site count was `33` in the fresh rerun versus `34` in the older tracked asset pack because one candidate-like non-canonical site was skipped by the current public implementation; marker-level representation is therefore the supported public short-read claim.

## External Audit Notes

An independent reviewer or separate thread should be able to audit the release by reading:

- `README.md`
- `paper/preprint_draft.md`
- `docs/release_checklist.md`
- `docs/reproducibility_run_ledger.md`
- this validation audit
- validation logs and output inventories under the validation packet root

The reviewer should verify that every biological claim in the manuscript maps to a tracked output, a validation transcript, or a cited external publication, and that unsupported claim classes remain explicitly excluded.
