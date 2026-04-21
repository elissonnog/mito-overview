# Examples

This directory holds packaging examples for the public mirror.

## Included now
- [`configs/human_example.env`](configs/human_example.env): example environment-style config for a human mtDNA run
- [`configs/shortread_example.env`](configs/shortread_example.env): example environment-style config for the reduced short-read profile
- [`synthetic_data/TOY-001`](synthetic_data/TOY-001): tracked toy input dataset used for installation checks and example-bundle generation
- [`expected_reports/TOY-001_output`](expected_reports/TOY-001_output): synthetic public report bundle generated from the repository's own example-builder workflow, including locally validated optional pages `13` and `14`
- [`expected_reports/TOY-SR-001_output`](expected_reports/TOY-SR-001_output): synthetic short-read report bundle that exercises the reduced short-read profile with explicit status pages for long-read-only analyses
- [`public_validation/GM11906_MERRF_shortread`](public_validation/GM11906_MERRF_shortread): light-weight figures and summary tables from a real public short-read proof-of-principle compatibility example

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

This produces a synthetic human-like toy sample that exercises the public analytical pages without relying on private project identifiers. The bundled builder uses local fixture resources for the optional Phy-Mer and mvTool-style validation layers so the example bundle can be regenerated from a fresh clone without private tool installations or live remote calls.

Note:
- analytical TSV, HTML, and figure outputs are intended to be stable across rebuilds
- the bundled mitochondrial BAM and BAM index are included for inspection convenience, but byte-level identity is not guaranteed across rebuilds because binary compression and indexing details can vary by environment
- the GM11906 public example assets are intentionally light-weight; they preserve the figures and key summary tables used for documentation and manuscript support rather than the full intermediate bundle
