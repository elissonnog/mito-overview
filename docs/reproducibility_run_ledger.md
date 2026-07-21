# v0.3.0 GitHub Release Reproducibility Ledger

This ledger tracks the active GitHub-only release gate for `mito-overview` v0.3.0. A pending row is not evidence of a pass. The controlling specification is [`clean_room_validation_protocol_v0.3.0.md`](clean_room_validation_protocol_v0.3.0.md). Zenodo, a DOI, manuscript changes, bioRxiv submission, Notion, and MCW/HPC deployment are outside this release gate.

The historical `v0.2.1` release remains immutable at `2ba62b775a7204c0dc61f5408989603f536c78da`. Historical outputs must not be relabeled as v0.3.0 evidence.

## Release Identity

| Field | Required value | Current status |
| --- | --- | --- |
| version | `0.3.0` | recorded in package metadata; final agreement check pending |
| repository | `https://github.com/elissonnog/mito-overview` | recorded |
| prior release | `v0.2.1` at `2ba62b775a7204c0dc61f5408989603f536c78da` | preserved |
| frozen manuscript tree | `bfb5664db9c8b43ed5de33ecbddef88071fc6378` | frozen; `paper/**` excluded from this phase |
| final commit | one exact 40-character public `main` commit | pending |
| GitHub Actions | successful Ubuntu and macOS jobs with `head_sha=FINAL_SHA` | pending |
| tag | annotated `v0.3.0` peeled to `FINAL_SHA` | pending |
| release assets | wheel, sdist, validation ZIP, reports, environment records, release notes, and `SHA256SUMS` | pending |
| archive/DOI | not required | outside scope |

## Scientific Claim Boundary

The release may support workflow execution, declared output contracts, fixed-input repeatability, representation of a known public marker, and descriptive dependence on prespecified quality filters. It does not establish diagnostic performance, sensitivity or specificity, a limit of detection, pathogenicity classification, deletion accuracy, absolute mtDNA copy number, formal NUMT classification, modality equivalence, population generalization, or clinical utility.

The GM12878 exercise uses a deterministic 1,000-query-name reduced ONT input and cannot support full-run performance claims. The GM11906 exercise is a three-cell, read-depth-weighted C1 scATAC-seq pseudo-bulk from one donor-derived cell line. Its pooled `m.8344A>G` alternate allele fraction is not a per-cell, donor-level, cell-line-population, or calibrated sample heteroplasmy estimate.

## Five Corrections

| ID | Contract | Primary deterministic evidence | Final status |
| --- | --- | --- | --- |
| F1 | shared filtered A/C/G/T observation engine, uncapped depth, exact strand/count invariants, and shared co-occurrence observations | `tests/test_allele_counting.py`, `tests/test_cosegregation_semantics.py`, `tests/test_table_contracts.py` | pending final exact-commit run |
| F2 | mvTool disabled by default; explicit fixture/network modes; bounded unavailable state | `tests/test_mvtool_modes.py` | pending final exact-commit run |
| F3 | standalone BAM/CRAM contract, sidecar precedence, index/contig/reference preflight | `tests/test_config_and_inputs.py`, `tests/test_alignment_reference_contract.py`, `tests/smoke_standalone_minimal.sh` | pending final exact-commit run |
| F4 | experimental mt:nuclear depth ratio only; no diploid multiplier; invalid denominator is NA/not evaluable | `tests/test_copy_number.py` | pending final exact-commit run |
| F5 | reference-scope-gated alignment-ambiguity interpretation and exact zero-based BED | `tests/test_reference_scope_and_bed.py`, `tests/test_numt_qc_inputs.py` | pending final exact-commit run |

## Validation Matrix

| Gate | Required evidence | Current status |
| --- | --- | --- |
| package and known answers | complete `pytest`, CLI step list, strict generic dry-run | provisional local pass; final exact-commit rerun pending |
| synthetic workflows | standard long read, reduced short read, long read without methylation, standalone minimal | provisional local pass; final exact-commit rerun pending |
| package isolation | build wheel and sdist; install and execute outside checkout with empty `PYTHONPATH` | pending final runner |
| sealed public cache | exactly seven raw FASTQs plus manifest/seal; hashes, gzip, FASTQ structure, pairing, and metadata identity pass | pending clean-room download |
| GM11906 public matrix | three filter profiles plus exact default repeat, marker/inventory/status oracles | pending exact-final-commit rerun |
| GM12878 public matrix | deterministic subset/alignment rebuild, three profiles, exact default repeat, inventory/status oracles | pending exact-final-commit rerun |
| cross-platform reproduction | macOS clean room and Ubuntu public-data workflow agree on normalized scientific outputs and states | pending |
| packet verification | packet root and fresh ZIP extraction both pass `verify_bundle.sh` | pending |
| visual QA | final report-native HTML/PNG inventory and report DOCX/PDF rendering inspected | pending |
| GitHub publication | PR merged, push CI green, immutable annotated tag and verified assets published | pending |

## Public Input Provenance

- `SRR10804585` / `GSM4238454`, `SRR10804590` / `GSM4238459`, and `SRR10804657` / `GSM4238526` are separate C1 single-cell ATAC-seq libraries from the GM11906 lymphoblastoid line.
- The three paired-end libraries are concatenated as a deliberately selected read-depth-weighted pseudo-bulk for marker-representation testing.
- `SRR18110025` is the GM12878 ONT targeted-mt source; the clean-room process deterministically selects 1,000 query names with seed `mito-overview-v0.3.0-GM12878-SRR18110025`.
- Raw FASTQs remain outside Git and the validation ZIP. Derived alignments are rebuilt in each clean-room workspace.

## Active Release Command

```bash
MITO_OVERVIEW_GITHUB_RUN_ID=<run-id> \
./scripts/run_release_validation_v0.3.0.sh \
  <validation-root> <raw-cache-root> <packet-root> \
  <mito-overview-v0.3.0-validation.zip>
```

The runner must reject legacy DOI/Zenodo arguments, clone public GitHub HTTPS at an exact 40-character commit, build/install distributions outside the checkout, collect CI identity and resource evidence, build schema `2.0` profile `github_release_validation_v1`, and verify both the packet root and a fresh ZIP extraction.

## Ordered Finish Gate

1. Stabilize and review the GitHub-only branch without modifying `paper/**`.
2. Run complete local tests, all four synthetic workflows, both example builders, package-isolation checks, and hygiene scans.
3. Obtain independent release-engineering, bioinformatics, and reproducibility reviews; resolve every blocker and rerun affected gates.
4. Push PR #3 and require green Ubuntu/macOS CI at the exact head.
5. Merge to `main`; record `FINAL_SHA`; require successful push-event CI at that exact SHA.
6. Run a fresh macOS public clean-room reproduction from an empty cache and the Ubuntu public workflow at `FINAL_SHA`; compare normalized outputs and module states.
7. Build and verify the audit ZIP and human-readable MD/DOCX/PDF report, including report-native figures.
8. Tag exactly `FINAL_SHA` as annotated `v0.3.0`, rerun tag-clone package/unit/synthetic checks, publish verified GitHub assets, and record the publication receipt.

Any commit after `FINAL_SHA` invalidates the release evidence. Any defect after publication is corrected forward as `v0.3.1`; the `v0.3.0` tag is never moved.
