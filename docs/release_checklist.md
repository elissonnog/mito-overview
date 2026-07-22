# MitoOverview v0.3.0 Release Checklist

This checklist governs the GitHub-primary v0.3.0 software release. The
validation protocol is defined in
[`clean_room_validation_protocol_v0.3.0.md`](clean_room_validation_protocol_v0.3.0.md).
The prior `v0.2.1` tag remains immutable at
`2ba62b775a7204c0dc61f5408989603f536c78da`.

Zenodo, a DOI, bioRxiv submission, manuscript revision, Notion, and MCW/HPC
deployment are outside this release gate. `CITATION.cff` may omit a DOI. The
GitHub release timestamp is authoritative; tracked files do not prerecord a
release date.

## Scope gate

- [ ] Work only in the public Mac repository.
- [ ] Preserve the frozen `paper/` tree
  `bfb5664db9c8b43ed5de33ecbddef88071fc6378` after main reconciliation.
- [ ] Confirm no internal paths, private sample identifiers, credentials, or
  secret-like values are tracked.
- [ ] Keep claims limited to workflow execution, output contracts,
  fixed-input repeatability, public marker representation, and descriptive
  filter dependence.

## Package and environment gate

- [ ] `pyproject.toml`, `mito_overview.__version__`, `CITATION.cff`, README,
  and CHANGELOG agree on version `0.3.0`.
- [ ] Python support is `>=3.12,<3.13` and platform locks exist for Linux
  x86-64, macOS x86-64, and macOS arm64.
- [ ] Wheel and sdist build successfully and are installed into separate clean
  environments outside the repository.
- [ ] The installed module and schema resolve inside the environment rather
  than through checkout `PYTHONPATH` shadowing.
- [ ] CLI listing, strict dry-run, unit tests, four smoke workflows, and both
  example builders pass.

## Public-data gate

- [ ] The raw cache starts empty and contains only the seven locked FASTQs plus
  its manifest and seal.
- [ ] Every FASTQ passes byte-count, MD5, SHA-256, gzip, and structural checks.
- [ ] GM11906 pairing and accession/sample identities pass.
- [ ] GM12878 selection is rebuilt from the full source FASTQ with the locked
  1,000-name seed and exact selected-name/subset identities.
- [ ] BWA and minimap2 alignments are regenerated with the locked tools and
  four threads under the validation workspace.
- [ ] The six public filter profiles, two default repeats per dataset, exact
  scientific oracle, module statuses, and output inventories pass.
- [ ] Offline execution records zero network-canary events.

## Evidence gate

- [ ] `run.json`, `cases.tsv`, commands, logs, environment records, resource
  usage, input/output hashes, expected-versus-observed results, normalized
  outputs, module statuses, figure/table provenance, claim evidence,
  limitations, public sources, and manuscript handoff values are complete.
- [ ] Every required case is `PASS`; no required case is missing, `SKIP`,
  `BLOCKED`, or `XFAIL`.
- [ ] `verify_bundle.sh` passes in the packet root and after safe extraction of
  `mito-overview-v0.3.0-validation.zip`.
- [ ] The ZIP SHA-256 and verification JSON are recorded outside the ZIP.
- [ ] The human-readable Markdown, DOCX, and PDF reports use exact-final-
  commit report-native figures and pass visual review.

## GitHub identity gate

- [ ] PR 3 contains current `main`, is no longer draft, and has green Ubuntu
  and macOS checks at its exact final head.
- [ ] Three role-separated read-only agent executions (release engineering,
  bioinformatics, and reproducibility) have no unresolved blockers. Each
  record has a unique audit-instance ID and is bound to the reviewed PR-head
  tree. The repository owner may post all three structured GitHub records;
  this is execution separation, not external peer review or three distinct
  GitHub reviewers.
- [ ] The merged `main` commit is frozen as `FINAL_SHA`.
- [ ] Push-event Ubuntu and macOS CI both report `head_sha=FINAL_SHA`.
- [ ] Independent macOS and Ubuntu clean-room public runs start from public
  HTTPS clones at `FINAL_SHA` and pass.
- [ ] Annotated tag `v0.3.0` peels to `FINAL_SHA` and is never rewritten.
- [ ] `scripts/run_fresh_public_tag_validation_v0.3.0.sh` clones the public
  annotated tag through HTTPS, verifies its peeled `FINAL_SHA`, and records
  `PASS` for its pinned environment, wheel/sdist, installed CLI, complete unit
  suite, four smoke workflows, and both example builders.
- [ ] The fresh-tag evidence manifest verifies, contains no local absolute
  path, and its receipt is supplied to every publisher phase with
  `--tag-validation-receipt` except the earlier read-only prepublication phase.
  Missing, failed, or tampered evidence blocks all GitHub release mutations.

## Release asset gate

- [ ] The draft GitHub release targets the existing `v0.3.0` tag.
- [ ] `github_prepublication.json` is captured read-only after tagging but
  before any release exists; the report builder accepts only this exact-main,
  annotated-tag receipt.
- [ ] The report states that final asset publication is verified separately;
  it does not claim verification of its own upload.
- [ ] `scripts/assemble_release_assets_v0.3.0.py` creates the exact nine-file
  prebuilt asset source atomically, executes the packet verifier, confirms the
  Markdown/DOCX/release-note/environment identities, verifies all three
  platform lock records, and embeds a size/SHA-256 report-asset manifest in
  `mito-overview-v0.3.0-verification.json`.
- [ ] The assembler rejects a stale commit, incomplete platform locks,
  symlinks/special files, a failed packet verifier, and an existing output
  root; the subsequent fresh-tag gate rejects any post-assembly asset mutation.
- [ ] Fresh-tag evidence seals all 12 canonical asset names, sizes, and SHA-256
  values to `FINAL_SHA` and the annotated tag object before any release mutation.
- [ ] Repository immutable releases are enabled before draft creation, and the
  queried published release reports `immutable=true`.
- [ ] Canonical assets include wheel, sdist, validation ZIP, Markdown/DOCX/PDF
  report, the Markdown report's sibling figure directory as a tar archive,
  machine-readable verification record, release notes, environment records,
  and `SHA256SUMS`.
- [ ] `SHA256SUMS` covers every other uploaded asset; the downloaded manifest
  is byte-identical to the prepared manifest and verifies every listed asset.
- [ ] The published release, tag target, asset inventory, hashes, and hosting
  immutability/protection state are queried from GitHub and captured in
  `github_publication.json`.

## Stop rules

Do not tag or publish while any required gate is nonpassing. A scientific
oracle mismatch requires investigation and a new reviewed commit; it is never
accepted by silently changing expected values. A defect discovered after
publication is corrected forward as `v0.3.1`, never by moving `v0.3.0`.
