# Contributing

`mito-overview` is currently maintained as research software for mtDNA report generation. Contributions, bug reports, and reproducibility feedback are welcome.

## Good First Issues

- Installation problems on a fresh Linux or macOS environment.
- Missing dependency declarations.
- Broken paths in example configs or documentation.
- Inconsistent `not_applicable` behavior across read modes.
- Documentation improvements that clarify input/output contracts.

## Scientific Scope

Please keep new claims aligned with the evidence level:

- Acceptable for the current release: report generation, smoke-test execution, public proof-of-principle examples, and mode-gated status behavior.
- Requires additional validation before claiming: clinical interpretation, low-VAF sensitivity, deletion truth, absolute mtDNA copy number, formal NUMT classification, live external-tool interoperability, and cohort-scale benchmarking.

## Development Checks

Before opening a pull request, run:

```bash
python -m mito_overview.cli --list-steps
python -m mito_overview.cli --config examples/configs/human_example.env --dry-run
./tests/smoke_public_pipeline.sh
./tests/smoke_public_pipeline_shortread.sh
./tests/smoke_public_pipeline_longread_nomethyl.sh
```

The public proof-of-principle scripts download larger external data and are not required for every pull request.

## Reporting Issues

When reporting a bug, include:

- operating system
- Python or conda environment details
- command used
- full error message
- whether the input was long-read, reduced short-read, WGS, or targeted mtDNA
- whether optional Phy-Mer, mvTool-style, or methylation inputs were configured
