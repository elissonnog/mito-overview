# v0.3.0 Release Checklist

This checklist governs the intended `mito-overview` v0.3.0 release dated 2026-07-20. Metadata describing the intended release is not evidence that a tag, external archive, or final validation result exists. The prior `v0.2.1` release remains immutable at commit `2ba62b775a7204c0dc61f5408989603f536c78da`.

## Release Identity and Gates

| Item | Required value | Status |
| --- | --- | --- |
| package and citation version | `0.3.0` | recorded in release metadata |
| intended release date | `2026-07-20` | recorded in release metadata |
| repository | `https://github.com/elissonnog/mito-overview` | recorded in release metadata |
| authors | Elisson Lopes; Xiaowu Gai | recorded in release metadata |
| affiliation | Medical College of Wisconsin | recorded in citation and release-control metadata |
| immutable prior release | `v0.2.1` at `2ba62b775a7204c0dc61f5408989603f536c78da` | verified historical record; do not retag or rewrite |
| `v0.3.0` Git tag | `v0.3.0` on the accepted release commit | **pending**; no tag is claimed by this checklist |
| exact `v0.3.0` tag target commit | full 40-character commit hash | **pending** until the tag is created |
| GitHub Actions CI pass | Linux and macOS jobs for the exact candidate commit | **pending**; no CI pass is claimed by this checklist |
| final validation packet pass | self-verifying packet bound to the exact candidate commit and CI run | **pending**; no final packet pass is claimed by this checklist |
| release DOI | DOI assigned by an external archive | **pending**; no DOI has been assigned or added to `CITATION.cff` |
| Zenodo publication | archived `v0.3.0` release | **pending**; no Zenodo publication is claimed by this checklist |
| independent reproducibility review | clean-checkout review of the accepted commit | **pending** |

## Scientific Release Goals

- Preserve the biological logic of the mitochondrial reporting workflow while keeping the public package portable outside the MCW HPC layout.
- Apply one auditable allele-observation policy across candidate, strand, and co-segregation outputs.
- Keep optional network services disabled unless explicitly requested and represent missing integrations without fabricated annotations.
- Support explicit standalone BAM/CRAM inputs with deterministic preflight validation.
- Report the copy-number layer only as an mt-to-nuclear depth ratio and gate NUMT interpretation by reference scope.
- Keep every public claim at a bounded workflow/resource level unless separate analytical or clinical validation is added.

## Candidate Contents

| Area | Repository evidence | Final release status |
| --- | --- | --- |
| five correction implementations | allele counting, mvTool modes, standalone inputs, copy-number ratio, and reference-scope/NUMT/BED handling | implementation present; **pending** final packet pass |
| deterministic known-answer tests | focused tests under `tests/` for corrections F1-F5 | present; **pending** exact-commit and CI pass |
| synthetic workflow checks | long-read, reduced short-read, no-methylation, and standalone smoke scripts | present; **pending** exact-commit and CI pass |
| public GM11906 proof of principle | provenance-bound reduced short-read workflow and marker-level checks | candidate workflow present; **pending** final packet pass |
| public GM12878 proof of principle | provenance-bound deterministic reduced-input ONT workflow | candidate workflow present; **pending** final packet pass |
| portable validation bundle | `scripts/run_release_validation_v0.3.0.sh` and `scripts/build_validation_packet_v0.3.0.py` | tooling present; final packet **pending** |

## Must-Pass Commands Before Tagging

Run local checks first from the exact candidate commit in a clean checkout:

```bash
python -m pytest -q
python -m mito_overview.cli --list-steps
python -m mito_overview.cli --config examples/configs/human_example.env --dry-run
./tests/smoke_public_pipeline.sh
./tests/smoke_public_pipeline_shortread.sh
./tests/smoke_public_pipeline_longread_nomethyl.sh
./tests/smoke_standalone_minimal.sh
```

After Linux and macOS GitHub Actions complete for that same commit, build the final evidence packet with the real completed run ID and an empty output directory:

```bash
MITO_OVERVIEW_GITHUB_RUN_ID=<completed-run-id> \
  ./scripts/run_release_validation_v0.3.0.sh <empty-validation-root>
```

The final packet must reject missing evidence, metadata-version disagreement, commit mismatch, non-passing required cases, incomplete public provenance, and CI results from a different commit.

## Evidence to Capture

- Exact candidate commit, eventual tag target, and clean-worktree state.
- Python, package, aligner, and platform versions.
- Commands and transcripts for unit, synthetic, standalone, and public validation cases.
- Source accessions, retrieval metadata, input hashes, subset parameters, and alignment provenance for public inputs.
- Runtime, maximum memory when available, expected/observed normalized outputs, and SHA-256 manifests.
- Linux and macOS GitHub Actions evidence tied to the exact candidate commit.
- Independent reviewer or separate-thread clean-checkout result.
- External archive metadata only after an archive actually assigns it.

## Release Sequence

1. Freeze and commit all intended release changes.
2. Validate the exact clean candidate commit locally.
3. Push that commit and wait for Linux and macOS GitHub Actions on the same commit.
4. Build and independently verify the final validation packet using real CI evidence.
5. Create `v0.3.0` only after all required evidence passes.
6. Publish the GitHub release from that tag.
7. Archive the tagged release with Zenodo or Software Heritage.
8. Add a DOI or persistent identifier to citation and manuscript metadata only after it is assigned.

## Claims Allowed for v0.3.0

- The package exposes a mode-gated mtDNA evidence-reporting workflow with explicit status states.
- Deterministic synthetic cases can test the public output contract and the five corrected behaviors.
- Explicitly sourced public data can exercise bounded long-read and reduced short-read proof-of-principle paths under recorded thresholds and provenance.
- Unsupported assay layers and unevaluable interpretations are emitted explicitly rather than silently converted into results.

## Claims Not Allowed Without Additional Validation

- Clinical diagnosis, pathogenicity classification, or clinical decision support.
- Calibrated low-VAF heteroplasmy sensitivity or specificity.
- Deletion-truth benchmarking or deletion-burden accuracy.
- Absolute mtDNA copy number or copies per diploid cell.
- Formal mtDNA-versus-NUMT classifier performance.
- Biological mtDNA methylation conclusions.
- Full-dataset performance or analytical sensitivity inferred from the reduced GM12878 validation subset.
- Live external-service interoperability unless a documented live run is added.
- Equivalence between long-read and short-read assays.
