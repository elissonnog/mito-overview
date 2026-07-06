# Release Checklist

This checklist defines what must be true before tagging `mito-overview` as a manuscript-supporting release. It is intentionally stricter than a development snapshot because the manuscript frames the repository as a reproducible workflow/resource artifact.

## Scientific Release Goals

- Preserve the biological logic of the internal mitochondrial reporting workflow while keeping the public package portable outside the MCW HPC layout.
- Separate core mtDNA report generation from optional human-only or external enrichment layers.
- Keep all public claims at workflow/resource level unless additional analytical validation is added.
- Provide enough documentation, examples, and scripts for a reviewer to repeat the public proof-of-principle checks from a clean checkout.

## Current Release-Candidate Status

| Area | Status | Notes |
| --- | --- | --- |
| package structure | present | Python package, CLI, shell wrapper, public configs |
| synthetic long-read smoke test | present | `tests/smoke_public_pipeline.sh` |
| synthetic short-read smoke test | present | `tests/smoke_public_pipeline_shortread.sh` |
| long-read no-methylation smoke test | present | `tests/smoke_public_pipeline_longread_nomethyl.sh` |
| public GM12878 ONT proof-of-principle assets | present | report-native figures and summary tables under `examples/public_validation/GM12878_ONT_longread/` |
| public GM11906 reduced short-read proof-of-principle assets | present | marker-focused assets under `examples/public_validation/GM11906_MERRF_shortread/` |
| release DOI or Software Heritage archive | pending | required before journal submission |
| exact release commit in manuscript | pending | required before journal submission |
| clean-checkout rerun transcript | pending | required before journal submission |
| independent reproducibility re-check | pending | required before journal submission |

## Must-Pass Commands Before Tagging

Run these from a fresh clone or a clean worktree:

```bash
python -m mito_overview.cli --list-steps
python -m mito_overview.cli --config examples/configs/human_example.env --dry-run
./tests/smoke_public_pipeline.sh
./tests/smoke_public_pipeline_shortread.sh
./tests/smoke_public_pipeline_longread_nomethyl.sh
```

Optional but manuscript-relevant public proof-of-principle reruns:

```bash
./scripts/run_public_longread_validation_gm12878.sh /tmp/GM12878_ONT_longread_output
./scripts/run_public_shortread_validation_gm11906.sh /tmp/GM11906_reduced_shortread_output
```

## Evidence to Capture

- Git commit hash and tag.
- Conda environment export or exact package versions.
- Command transcripts for each must-pass command.
- Runtime and maximum memory when feasible.
- Checksums or file inventories for public output bundles.
- FASTQ/source retrieval date for public examples.
- Expected-file and TSV-schema checks for active and `not_applicable` pages.
- Independent reviewer or separate-thread re-check of the clean checkout.

## Release Archive Steps

1. Ensure the working tree contains only intended release files.
2. Run the must-pass commands from a clean checkout.
3. Commit all release files.
4. Tag the release, for example `v0.2.0`.
5. Archive the tag through Zenodo or Software Heritage.
6. Update `CITATION.cff`, `README.md`, and the manuscript with the tag, commit, and archive DOI or persistent identifier.

## Claims Allowed for This Release

- The package exposes the declared workflow steps.
- Synthetic long- and short-read smoke tests exercise the public output contract.
- Public GM12878 ONT targeted-mt data can be converted into synchronized report-native long-read outputs under stated thresholds.
- Public GM11906 short-read/scATAC-derived mtDNA reads can be represented in the reduced short-read report profile under stated thresholds.
- Unsupported assay layers are emitted as stable status or `not_applicable` pages rather than silent failures.

## Claims Not Allowed Without Additional Validation

- Clinical diagnosis or pathogenicity classification.
- Calibrated low-VAF heteroplasmy sensitivity.
- Deletion-truth benchmarking or deletion burden accuracy.
- Absolute mtDNA copy-number truth.
- Formal mtDNA-versus-NUMT classifier performance.
- Biological mtDNA methylation conclusions.
- Live Phy-Mer or mvTool interoperability unless a documented live run is added.
- Equivalence between long-read and short-read assays.
