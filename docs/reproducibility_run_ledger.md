# v0.3.0 Reproducibility Run Ledger

This ledger tracks evidence required for the intended `mito-overview` v0.3.0 release dated 2026-07-20. It supports audit planning and does not convert incomplete work into release evidence. A row marked **pending** is not a pass.

The historical `v0.2.1` release remains immutable at commit `2ba62b775a7204c0dc61f5408989603f536c78da`. Its dated audit remains in `docs/release_validation_audit_2026-07-07.md`; v0.2.1 observations must not be relabeled as v0.3.0 results.

## Release Identity Ledger

| Field | Intended or historical value | Evidence status |
| --- | --- | --- |
| release-candidate version | `0.3.0` | recorded in `pyproject.toml`, `mito_overview/__init__.py`, and `CITATION.cff` |
| release metadata date | `2026-07-20` | recorded |
| repository | `https://github.com/elissonnog/mito-overview` | recorded |
| authors | Elisson Lopes; Xiaowu Gai | recorded |
| affiliation | Medical College of Wisconsin | recorded in citation and release-control metadata |
| immutable prior release | `v0.2.1` at `2ba62b775a7204c0dc61f5408989603f536c78da` | historical record preserved |
| `v0.3.0` Git tag | intended tag `v0.3.0` | **pending**; tag not claimed |
| exact `v0.3.0` tag target | full candidate commit | **pending** until tagging |
| GitHub Actions CI pass | Linux and macOS jobs on the exact candidate commit | **pending**; CI pass not claimed |
| final validation packet pass | self-verifying v0.3.0 bundle | **pending**; final packet pass not claimed |
| release DOI | externally assigned DOI | **pending**; no DOI assigned |
| Zenodo publication | archive of the tagged release | **pending**; no Zenodo publication claimed |

## Scientific Claim Boundary

The intended release supports only a reproducible workflow/resource claim for mode-gated mtDNA evidence reporting. It does not support diagnostic use, pathogenicity classification, calibrated low-VAF performance, deletion-truth benchmarking, absolute mtDNA copy-number estimation, formal NUMT classification, biological methylation conclusions, or clinical equivalence between long- and short-read assays.

The GM12878 path uses an explicitly labeled deterministic reduced-input subset for resource-bounded workflow validation. It cannot support claims about full-run performance, analytical sensitivity, or population biology. The folder label `GM11906_MERRF_shortread` is historical; the supported claim is representation of the literature-associated `m.8344A>G` marker in applicable reduced short-read report layers, not confirmation of disease status or clinical pathogenicity.

## Five-Correction Evidence Map

| ID | Corrected behavior | Deterministic evidence source | Required final verdict |
| --- | --- | --- | --- |
| F1 | shared callable A/C/G/T depth, alternate and strand counts, uncapped default depth, common filters, and auditable exclusions | `tests/test_allele_counting.py`; `tests/test_table_contracts.py` | **pending** final packet pass |
| F2 | mvTool disabled by default; fixture and explicit network modes; unavailable failures without fabricated annotations | `tests/test_mvtool_modes.py` | **pending** final packet pass |
| F3 | generic BAM/CRAM inputs, explicit sidecar precedence, legacy compatibility, and index/contig/length/reference preflight | `tests/test_config_and_inputs.py`; `tests/smoke_standalone_minimal.sh` | **pending** final packet pass |
| F4 | `mt_mean_depth / nuclear_mean_depth`, no diploid multiplier, and NA/`not_evaluable` for an invalid denominator | `tests/test_copy_number.py` | **pending** final packet pass |
| F5 | explicit reference scope, no categorical NUMT result for mt-only/custom references, and exact zero-based half-open BED output | `tests/test_reference_scope_and_bed.py` | **pending** final packet pass |

## Validation Evidence Tiers

| Tier | Purpose | Command or script | Expected evidence | Supported claim if passing | Explicitly not supported | Status |
| --- | --- | --- | --- | --- | --- | --- |
| package and known-answer tests | verify package wiring and corrections F1-F5 | `python -m pytest -q`; `python -m mito_overview.cli --list-steps` | test transcript, step registry, package metadata agreement | declared components and corrected invariants work in the tested environment | correctness on untested biological data | **pending** exact-commit and CI evidence |
| synthetic long-read fixture | verify active long-read layers and output contract | `tests/smoke_public_pipeline.sh` | normalized outputs, transcript, hashes | controlled long-read fixture executes | biological realism or diagnostic performance | **pending** final packet pass |
| synthetic reduced short-read fixture | verify assay gating and stable inactive pages | `tests/smoke_public_pipeline_shortread.sh` | normalized outputs, transcript, hashes | reduced mode preserves the applicable contract | equivalence to long-read behavior | **pending** final packet pass |
| no-methylation and standalone fixtures | verify absent optional data and portable generic inputs | `tests/smoke_public_pipeline_longread_nomethyl.sh`; `tests/smoke_standalone_minimal.sh` | status pages, preflight evidence, transcript, hashes | optional layers and generic inputs are handled explicitly | external-service or cohort portability | **pending** final packet pass |
| public GM11906 proof of principle | rerun applicable reduced short-read layers under recorded filter profiles | `scripts/run_public_shortread_validation_gm11906.sh` through the public matrix | verified FASTQ provenance, alignment provenance, marker checks, repeatability, visual inventory | the named marker is representable in applicable report layers under stated settings | disease confirmation, pathogenicity, calibrated sensitivity | **pending** final packet pass |
| public GM12878 proof of principle | rerun long-read layers on a provenance-bound deterministic subset | `scripts/run_public_longread_validation_gm12878.sh` through the public matrix | source and subset hashes, alignment provenance, repeatability, visual inventory | a resource-limited public ONT subset can exercise applicable workflow layers | full-run performance, sensitivity, deletion truth, formal NUMT classification | **pending** final packet pass |
| release acceptance | bind all evidence to one clean commit and real CI run | `scripts/run_release_validation_v0.3.0.sh` | clean-clone transcript, Linux/macOS CI records, distributions, cases, manifests, self-verifying archive | reproducibility of the bounded release artifact in the recorded environments | universal portability or analytical validation | **pending** |

## Required Public Provenance

- Accession and retrieval metadata for each public FASTQ.
- SHA-256 hashes for source inputs and deterministic subsets.
- Exact subset algorithm, seed, query-name count, and selected-name hash for GM12878.
- Reference source, contig dictionary, aligner command, and aligner version.
- Canonical allele-filter profile and the tested lenient/default/strict profile values.
- Commands, environment, runtime, memory when available, and output manifests.
- Expected-versus-observed checks for the GM11906 marker and bounded GM12878 workflow statuses.

## Required Before Tagging

1. Freeze one exact clean candidate commit.
2. Run unit, known-answer, synthetic, standalone, packaging, and public matrix checks on that commit.
3. Obtain real passing Linux and macOS GitHub Actions evidence for the same commit.
4. Build the final packet and run its independent `verify_bundle.sh` check.
5. Record the exact tag target only when `v0.3.0` is created.
6. Archive only the tagged release, then record the DOI or persistent identifier actually assigned.
7. Complete an independent clean-checkout reproducibility review.

## Final Packet Contract

The final packet is an external release artifact and is not committed to this repository. It must contain release identity, case and claim-evidence tables, public data-source records, environment and command transcripts, expected and normalized observed outputs, distributions, input and artifact SHA-256 manifests, real CI evidence, and a verifier. Raw public data remain outside Git.

Until that packet passes against the exact accepted commit, the v0.3.0 tag, CI pass, final packet pass, DOI, and Zenodo publication all remain **pending**.
