# Examples

This directory holds synthetic smoke-test bundles and v0.3.0 public workflow-evidence assets.

## Included now
- [`configs/human_example.env`](configs/human_example.env): example environment-style config for a human mtDNA run
- [`configs/shortread_example.env`](configs/shortread_example.env): example environment-style config for the reduced short-read profile
- [`synthetic_data/TOY-001`](synthetic_data/TOY-001): tracked toy input dataset used for installation checks and example-bundle generation
- [`expected_reports/TOY-001_output`](expected_reports/TOY-001_output): synthetic public report bundle generated from the repository's own example-builder workflow, including locally validated optional pages `13` and `14`
- [`expected_reports/TOY-SR-001_output`](expected_reports/TOY-SR-001_output): synthetic short-read report bundle that exercises the reduced short-read profile with explicit status pages for long-read-only analyses
- [`public_validation/GM12878_ONT_longread`](public_validation/GM12878_ONT_longread): figures, summaries, and provenance from the fixed deterministic GM12878 qn1000 ONT input
- [`public_validation/GM11906_MERRF_shortread`](public_validation/GM11906_MERRF_shortread): figures, summaries, and provenance from three pooled GM11906 single-cell ATAC-seq libraries analyzed in the reduced short-read profile

## How to regenerate
Use the builder script:

```bash
./scripts/build_public_example_bundle.sh \
  examples/expected_reports/TOY-001_output
```

For the synthetic short-read bundle:

```bash
./scripts/build_public_shortread_example_bundle.sh \
  examples/expected_reports/TOY-SR-001_output
```

For the public proof-of-principle short-read dataset:

```bash
./scripts/run_public_shortread_validation_gm11906.sh \
  /tmp/GM11906_MERRF_shortread_output
```

For the public proof-of-principle long-read dataset:

```bash
./scripts/run_public_longread_validation_gm12878.sh \
  /tmp/GM12878_ONT_longread_output
```

The synthetic builders exercise public analytical pages without private project identifiers. They use local fixture resources for optional Phy-Mer and mvTool-style report wiring, so no private installation or live request is needed for the smoke-test bundles.

## v0.3.0 public matrix summary
The GM12878 input is exactly a fixed deterministic `1,000`-query-name subset selected from `193,043` `SRR18110025` records. Its mapped-only BAM contains `728` mapped unique query names/primary alignments and `543` supplementary records. The default profile reports `16` candidates, `7,143,152` accepted observations, and `2,047,476` excluded observations.

The GM11906 pooled-scATAC default profile reports `33` candidates, `44,052,664` accepted observations, and `7,293,106` excluded observations. At `m.8344A>G`, depth is `1,027`, alternate count is `740`, and the pooled observed alternate allele fraction is `0.720545`. This is not a per-cell or calibrated sample heteroplasmy estimate.

The matrix's repeated invocations start from the same provenance-verified BAMs. Repeatability is conditional on those fixed inputs and does not cover subset selection or alignment regeneration. Each public asset directory documents its filter profiles, exact status values, and selected report artifacts.
