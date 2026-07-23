# Phy-Mer Integration

Phy-Mer is implemented in the public mirror as an optional human mtDNA haplogroup enrichment layer.

Public-package rule:
- keep haplogroup calling optional
- keep species gating explicit
- do not make this dependency mandatory for the reproducible core workflow
- in the repository's fixture-backed smoke-test path, use the bundled deterministic fixture under `tests/fixtures/mock_phymer_vendor`
- in real use, point `PHYMER_ROOT` to a true local Phy-Mer vendor tree

Input eligibility is fail-closed. The upstream allele module must report
`status=ok`, and its all-site table must contain exactly one internally
consistent, reference-matching row for every mitochondrial coordinate. A
position is callable for consensus construction when
`callable_depth >= PHYMER_MIN_DEPTH`. The default
`PHYMER_MIN_CALLABLE_FRACTION=0.95` requires at least 95% of the configured
mitochondrial genome to be callable before Phy-Mer is invoked. Remaining
low-depth positions are masked as `N`; they are never silently filled from the
reference. Below-threshold inputs report
`not_evaluable/insufficient_callable_genome_fraction` with numerator,
denominator, fraction, depth threshold, and fraction threshold in the summary.

`PHYMER_MAJOR_VAF=0.90` controls which observed non-reference base is inserted
into the consensus. An eligible reference-supported consensus may contain zero
such alternate sites and is still a valid classifier input. Parsed ranking
scores must be finite. These are workflow eligibility and integrity rules, not
clinical calibration or haplogroup-accuracy validation.

The 60-bp synthetic long-read smoke fixture explicitly sets
`PHYMER_MIN_CALLABLE_FRACTION=0.30` because only one-third of its artificial
reference is covered at the fixture depth threshold. That override exists only
to exercise the bundled mock integration and is recorded in its run context;
it is not a recommended biological-analysis threshold.
