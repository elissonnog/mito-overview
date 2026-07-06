# Overview

`mito-overview` is a modular public bioinformatics package for mode-gated mitochondrial DNA report generation from aligned sequencing data.

The software is designed around independent analytical layers that each generate:
- machine-readable summary tables
- figures
- a biologically scoped HTML report page

This design supports both collaborator-facing review and downstream computational reuse.

The public package is intended for workflow/resource use. It does not make clinical interpretation, low-VAF sensitivity, deletion-truth, absolute copy-number, or formal NUMT-classifier claims without separate validation.
