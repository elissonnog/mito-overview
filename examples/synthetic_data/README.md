# Synthetic validation data

This directory contains small synthetic input sets used for public validation of the `mito-overview` workflow.

## Included datasets
- `TOY-001/`: long-read-style end-to-end workflow fixture with optional sidecars.
- `TOY-SR-001/`: tracked reduced short-read routing and allele-count fixture.
- `TOY-WGS-001/`: whole-genome mt:nuclear depth-ratio fixture with expected `100/10 = 10.0` arithmetic.

The dataset is intentionally minimal and human-like rather than biologically realistic. Its purpose is:
- installation validation
- smoke testing
- deterministic generation of a small public example output bundle

The expected public-core output generated from these inputs is committed at:
- `examples/expected_reports/TOY-001_output`
