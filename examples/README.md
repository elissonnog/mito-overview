# Examples

This directory holds packaging examples for the public mirror.

## Included now
- [`configs/human_example.env`](configs/human_example.env): example environment-style config for a human mtDNA run
- [`synthetic_data/TOY-001`](synthetic_data/TOY-001): tracked toy input dataset used for installation checks and example-bundle generation
- [`expected_reports/TOY-001_output`](expected_reports/TOY-001_output): synthetic public report bundle generated from the repository's own example-builder workflow, including locally validated optional pages `13` and `14`

## How to regenerate
Use the builder script:

```bash
./scripts/build_public_example_bundle.sh \
  examples/expected_reports/TOY-001_output
```

This produces a synthetic human-like toy sample that exercises the public analytical pages without relying on private project identifiers. The bundled builder uses local fixture resources for the optional Phy-Mer and mvTool-style validation layers so the example bundle can be regenerated from a fresh clone without private tool installations or live remote calls.

Note:
- analytical TSV, HTML, and figure outputs are intended to be stable across rebuilds
- the bundled mitochondrial BAM and BAM index are included for inspection convenience, but byte-level identity is not guaranteed across rebuilds because binary compression and indexing details can vary by environment
