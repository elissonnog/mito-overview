# Phy-Mer Integration

Phy-Mer is implemented in the public mirror as an optional human mtDNA haplogroup enrichment layer.

Public-package rule:
- keep haplogroup calling optional
- keep species gating explicit
- do not make this dependency mandatory for the reproducible core workflow
- in the repository's fixture-backed smoke-test path, use the bundled deterministic fixture under `tests/fixtures/mock_phymer_vendor`
- in real use, set `PHYMER_MODE=external`, point `PHYMER_ROOT` to a local
  Phy-Mer vendor tree, and provide its expected `PHYMER_SCRIPT_SHA256`,
  `PHYMER_LIBRARY_SHA256`, and `PHYMER_DEFINITIONS_SHA256` identities
- BioPython 1.87 is pinned because the official Phy-Mer script imports it; the
  external Phy-Mer code and data library remain separately installed resources
- official Phy-Mer still uses Python 2's removed `rU` file mode; external mode
  runs the unmodified script through `mito_overview.phymer_compat`, which only
  translates that legacy universal-newline flag to modern text mode

Input eligibility is fail-closed. The upstream allele module must report
`status=ok`, and its all-site table must contain exactly one internally
consistent, reference-matching row for every mitochondrial coordinate. A
position is callable for consensus construction when its reference base is
canonical A/C/G/T and `callable_depth >= PHYMER_MIN_DEPTH`. An unresolved
reference `N` is accepted only when it exactly matches the configured FASTA;
it is counted, reported, and masked as `N` rather than interpreted as a
variant. Other IUPAC ambiguity symbols fail validation. The default
`PHYMER_MIN_CALLABLE_FRACTION=0.95` requires at least 95% of the configured
mitochondrial genome to be callable before Phy-Mer is invoked. Remaining
low-depth or noncanonical-reference positions are masked as `N`; they are
never silently filled from the reference. The denominator remains the full
configured mitochondrial length, and the summary records the noncanonical
reference-position count. Thus, the single unresolved base at rCRS position
3107 is excluded from the callable numerator without preventing classification
of an otherwise complete input. Below-threshold inputs report
`not_evaluable/insufficient_callable_genome_fraction` with numerator,
denominator, fraction, depth threshold, and fraction threshold in the summary.

`PHYMER_MAJOR_VAF=0.90` controls which observed non-reference base is inserted
into the consensus. An eligible reference-supported consensus may contain zero
such alternate sites and is still a valid classifier input. Parsed ranking
scores must be finite and bounded within the official score domain `[0,1]`.
These are workflow eligibility and integrity rules, not
clinical calibration or haplogroup-accuracy validation.

The 60-bp synthetic long-read smoke fixture explicitly sets
`PHYMER_MODE=fixture` and `PHYMER_MIN_CALLABLE_FRACTION=0.30` because only
one-third of its artificial reference is covered at the fixture depth threshold.
Fixture mode verifies SHA-256 identities for the bundled stand-in script,
library, and definitions before execution. Its TSV and HTML outputs record the
fixture ID, provenance, synthetic result scope, and absence of biological
validation. External mode cannot set the callable fraction below `0.95` and
does not execute files based on expected names alone: all three configured
digests must match the local script, library, and motif-definition files. The
verified observed identities are recorded in the Phy-Mer summary. Identity QC
independently compares those recorded identities with the configured expected
hashes before retaining a formal external assignment.

Every direct invocation clears all Phy-Mer-owned summaries, ranking/input
tables, raw logs, consensus FASTA, figure, and HTML before validating the new
evidence. A failed rerun therefore cannot leave a prior categorical result in
place.

The compatibility boundary has a deterministic test in
`tests/test_phymer_compat.py` and an end-to-end external-vendor contract test in
`tests/test_phymer_haplogroup_contract.py`. Release evidence may also execute
the untouched official archive against the bundled public rCRS FASTA, but that
network-fetched probe is not required for default workflow execution or CI.
