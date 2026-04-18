# Examples

This directory holds packaging examples for the public mirror.

## Included now
- [`configs/human_example.env`](configs/human_example.env): example environment-style config for a human mtDNA run
- [`expected_reports/TOY-001_output`](expected_reports/TOY-001_output): synthetic public-core report bundle generated from the repository's own example-builder workflow

## How to regenerate
Use the builder script:

```bash
./scripts/build_public_example_bundle.sh \
  examples/expected_reports/TOY-001_output
```

This produces a synthetic human-like toy sample that exercises the public-core analytical pages without relying on private project identifiers.
