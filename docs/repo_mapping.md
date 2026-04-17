# Internal-to-Public Module Mapping

This document maps the validated internal HPC workflow into the planned public package structure.

## Wrappers and orchestration
- internal: `prep_mito_overview.pl`
- public target: `scripts/hpc/prep_mito_overview.pl`

- internal: `run_mito_pipeline.sh`
- public target: `scripts/run_mito_pipeline.sh` plus `mito_overview.workflow`

## Shared reporting layer
- internal: `steps/mito_report_common.py`
- public target: `mito_overview/report_common.py`

## Step modules
- internal: `03_mito_qc.py`
- public target: `mito_overview/steps/mito_qc.py`

- internal: `04_mito_heteroplasmy.py`
- public target: `mito_overview/steps/mito_heteroplasmy.py`

- internal: `05_mito_deletions.py`
- public target: `mito_overview/steps/mito_deletions.py`

- internal: `06_mito_copy_number.py`
- public target: `mito_overview/steps/mito_copy_number.py`

- internal: `07_mito_feature_annotation.py`
- public target: `mito_overview/steps/mito_feature_annotation.py`

- internal: `09_mito_cosegregation.py`
- public target: `mito_overview/steps/mito_cosegregation.py`

- internal: `10_mito_gene_summary.py`
- public target: `mito_overview/steps/mito_gene_summary.py`

- internal: `11_mito_numt_qc.py`
- public target: `mito_overview/steps/mito_numt_qc.py`

- internal: `12_mito_identity_qc.py`
- public target: `mito_overview/steps/mito_identity_qc.py`

- internal: `13_mito_variant_consequence.py`
- public target: `mito_overview/steps/mito_variant_consequence.py`

- internal: `14_mito_circularity_qc.py`
- public target: `mito_overview/steps/mito_circularity_qc.py`

- internal: `15_mito_methylation_exploratory.py`
- public target: `mito_overview/steps/mito_methylation_exploratory.py`

- internal: `16_mito_phymer_haplogroup.py`
- public target: `mito_overview/steps/mito_phymer_haplogroup.py`

- internal: `17_mito_mvtool_annotation.py`
- public target: `mito_overview/steps/mito_mvtool_annotation.py`

## Porting rule
Port modules in the following order:
1. reporting utilities
2. configuration and workflow plumbing
3. QC and heteroplasmy
4. deletions and copy-number proxy
5. feature annotation and gene summary
6. advanced QC pages
7. optional integrations
