# Methodology

## Core analytical logic
The public package retains the modular structure of the internal HPC workflow while making read-mode and assay-mode boundaries explicit.

Primary analytical layers:
1. metadata discovery and provenance capture
2. mitochondrial read extraction
3. QC and coverage profiling
4. heteroplasmy analysis
5. deletion and rearrangement profiling
6. copy-number proxy estimation
7. mitochondrial feature annotation
8. same-read co-occurrence
9. mitochondrial gene-summary aggregation
10. NUMT-aware QC
11. identity and fingerprint QC
12. variant consequence and external annotation overlays
13. circularity edge QC
14. exploratory methylation summary

## Scientific interpretation
The intended scientific emphasis is genetics-first and long-read-aware. Methylation remains an exploratory secondary layer rather than the central mitochondrial conclusion. Warning-oriented QC layers should not be interpreted as calibrated classifiers unless additional validation is added.
