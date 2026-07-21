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
| final validation packet pass | self-verifying audit ZIP bound to the exact final candidate commit, CI run, and reserved DOI | **pending**; no final packet pass is claimed by this checklist |
| Zenodo DOI reservation | DOI reserved in an unpublished Zenodo draft before the final metadata commit | **pending**; no DOI has been reserved or added to `CITATION.cff` |
| release DOI | reserved DOI resolving to the published tagged archive | **pending**; no published DOI is claimed by this checklist |
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
| public GM11906 proof of principle | tracked outputs derived from historical validated source commit `dc09114e1a0dcec2baf83d94549dfa41f3e49c8b`; provenance-bound reduced short-read workflow and marker-level checks | historical evidence present; **pending** rerun and binding in the exact-final-commit packet |
| public GM12878 proof of principle | tracked outputs derived from historical validated source commit `dc09114e1a0dcec2baf83d94549dfa41f3e49c8b`; provenance-bound deterministic reduced-input ONT workflow | historical evidence present; **pending** rerun and binding in the exact-final-commit packet |
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

After reserving the Zenodo DOI, synchronizing it into release metadata, committing those changes, and obtaining passing Linux and macOS GitHub Actions for that exact final commit, build and verify the final evidence packet. Use absolute, non-overlapping paths outside the repository; the validation and packet roots must be absent or empty, the cache may be reused, and the ZIP and its sidecars must not exist:

```bash
export MITO_OVERVIEW_ARCHIVE_DOI=10.5281/zenodo.<reserved-record-id>
MITO_OVERVIEW_GITHUB_RUN_ID=<completed-run-id> \
  ./scripts/run_release_validation_v0.3.0.sh \
  <empty-validation-root> \
  <cache-root> \
  <empty-packet-root> \
  <artifact-directory>/mito-overview-v0.3.0-validation.zip
```

The DOI may instead be supplied as the fifth positional argument. The command requires a canonical reserved Zenodo DOI, rejects `UNRESERVED`, requires the same top-level DOI in `CITATION.cff`, and passes it explicitly to the packet builder. It must build `mito-overview-v0.3.0-validation.zip`, execute the generated `verify_bundle.sh` against both the packet root and a fresh extraction of that ZIP, and write build/verification logs, a ZIP SHA-256 sidecar, and a PASS receipt. It emits no final PASS unless all of that evidence exists and both verifier runs succeed.

The final packet must reject missing evidence, metadata-version disagreement, commit mismatch, non-passing required cases, incomplete public provenance, CI results from a different commit, an absent/unreserved DOI, and a DOI that differs from synchronized citation metadata.

## Evidence to Capture

- Exact candidate commit, eventual tag target, and clean-worktree state.
- Python, package, aligner, and platform versions.
- Commands and transcripts for unit, synthetic, standalone, and public validation cases.
- Source accessions, retrieval metadata, input hashes, subset parameters, and alignment provenance for public inputs.
- Runtime, maximum memory when available, expected/observed normalized outputs, and SHA-256 manifests.
- Linux and macOS GitHub Actions evidence tied to the exact candidate commit.
- Independent reviewer or separate-thread clean-checkout result.
- Zenodo draft record and DOI-reservation evidence before the final metadata commit; reservation alone is not publication.
- Published archive metadata and DOI resolution only after the tagged archive is actually published.

## Release Sequence

1. Stabilize the intended code, documentation, and historical-evidence labels; provisional checks at this stage are not final release evidence.
2. Create an unpublished Zenodo draft and reserve its DOI. Keep DOI reservation and Zenodo publication gates **pending** until external evidence exists.
3. Synchronize the reserved DOI, version, title, authors, date, repository, license, and bounded claims across the Zenodo draft, `CITATION.cff`, release notes, and manuscript-facing metadata.
4. Commit the synchronized metadata. That new clean commit, not an earlier tested commit, is the final release candidate.
5. Repeat all local checks on that exact commit, push it, and require passing Linux and macOS GitHub Actions whose `head_sha` is the same full commit.
6. Run `scripts/run_release_validation_v0.3.0.sh` on that exact commit with the real CI run ID and reserved DOI; require the named audit ZIP, both `verify_bundle.sh` runs, ZIP hash, and PASS receipt.
7. Complete the independent clean-checkout reproducibility review against that same commit and packet.
8. Create `v0.3.0` on the accepted commit only after every required check passes; record and verify the full tag target.
9. Publish the GitHub release from that tag, then publish the matching tagged archive in Zenodo and confirm the DOI resolves to synchronized metadata and artifacts.
10. Record publication evidence without rewriting the tag or relabeling pre-final results as exact-release-commit results.

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
