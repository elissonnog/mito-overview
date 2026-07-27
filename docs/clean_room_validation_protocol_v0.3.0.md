# MitoOverview v0.3.0 Clean-Room Validation Protocol

## Purpose and scope

This protocol is the preregistered release gate for MitoOverview v0.3.0. It
tests software installation, deterministic output contracts, public-data
workflow execution, fixed-input repeatability, and descriptive filter
dependence. It is an independent clean-room reproduction protocol, not a
clinical, diagnostic, analytical-sensitivity, deletion-truth, absolute-copy-
number, NUMT-classification, or sequencing-modality benchmark.

The release is GitHub-primary. A Zenodo record, archival DOI, manuscript, and
bioRxiv submission are not inputs to this protocol. The MCW/HPC installation is
outside scope.

## Frozen development baseline

| Item | Value |
| --- | --- |
| Repository | `https://github.com/elissonnog/mito-overview` |
| Development branch | `codex/preprint-hardening-v0.3.0` |
| Reconciled baseline | `6dc5f079745bf7732710a483e926ab27e6b94926` |
| Prior immutable release | `v0.2.1` at `2ba62b775a7204c0dc61f5408989603f536c78da` |

The manuscript tree is outside this protocol and is neither recorded nor
compared by software release acceptance. The final release commit, CI jobs,
tag, distributions, validation packet, and reports must all resolve to one
full 40-character commit.

## Locked execution environment

The tested Python line is `>=3.12,<3.13`. Release validation uses Python
3.12.13, samtools/htslib 1.23.1, minimap2 2.31-r1302, BWA 0.7.19-r1273,
BioPython 1.87, pysam 0.24.0, pandas 3.0.3, NumPy 2.5.1, Matplotlib 3.11.0, Requests
2.34.2, pytest 9.1.1, build 1.5.0, setuptools 82.0.1, wheel 0.47.0,
and python-docx 1.2.0. Platform lock records are required for Linux x86-64,
macOS x86-64, and macOS arm64.

Each clean-room run uses an isolated `HOME`, `TMPDIR`, and cache; an empty
`PYTHONPATH`; `PYTHONNOUSERSITE=1`; `LC_ALL=C`; `TZ=UTC`; four workflow
threads; and explicit numerical/font cache settings. The package is built and
installed, then exercised from outside the source checkout.

## Public input lock

Only the seven FASTQ files below are permitted in the sealed raw cache. Files
are downloaded to partial names, resumed when safe, and atomically renamed only
after byte-count, MD5, SHA-256, gzip, and FASTQ validation.

| File | Bytes | MD5 | SHA-256 |
| --- | ---: | --- | --- |
| `SRR10804585_1.fastq.gz` | 8,795,676 | `3f5ea26a5791894071462d4970bc9e5a` | `b69746cb61d8bf3bc25887d6ece3c60db3acc7baaefd84a9a8b5d6ffce33288d` |
| `SRR10804585_2.fastq.gz` | 8,817,420 | `c5b408425612f63b33cefd2d49c157d1` | `1fca2c35a955a4ed232465d8392bc04683828229178aee7915929e67b2aac961` |
| `SRR10804590_1.fastq.gz` | 1,006,749 | `e8b5132a8be8c179bfc6dbc0f3e1bee9` | `e47ceceb03d44483b4948fe9c631ebff307f5ec68a1deec978f1122695fa58fc` |
| `SRR10804590_2.fastq.gz` | 795,885 | `4d6977526136739de2d90baa8d45b484` | `05b2375b30b02c02e9206981eb2fe2d08babbc2a5809f8354ef56d0ac1550776` |
| `SRR10804657_1.fastq.gz` | 21,510,555 | `8f082f73cb64bf56ea8a053fe80eeb06` | `1afaf310ce9ffa77e1c3d61a0714e839d21000941d414cc7bf6fb590c3b665f2` |
| `SRR10804657_2.fastq.gz` | 21,573,731 | `62b7d1b2294a580c021f5fa1f52609be` | `bfc555c7e722695b02110027757bba4d7fc88f487798423cd6809e8a771a5184` |
| `SRR18110025.fastq.gz` | 2,033,558,460 | `d5bfb9aeba04cae5f3dd79462a42e5b0` | `c0872ee9ceb772ee5a4b76735c0d670e2159764b23dd800b6eb1f4933da11320` |

The first six files are paired ends from three single-cell ATAC-seq libraries (`GSM4238454`, `GSM4238459`, and `GSM4238526`). NCBI GEO identifies each library as derived from the GM11906 lymphoblastoid line. They are concatenated as a pseudo-bulk compatibility input; unequal callable depth makes pooled allele fractions read-observation weighted rather than equal-weight per cell. The input is not conventional short-read WGS, three independent patients, or a bulk heteroplasmy measurement. The sealed manifest records the run, BioSample, GEO accession, source cell line, library strategy, library unit, and primary metadata URL.

The tracked `NC_012920.1.fa` reference must have SHA-256
`fc392cde8e63b4d2e3a870bb97cc0626dea33d46dfb8abdebffada040f42ec92`.
Derived FASTQs, subsets, indexes, BAMs, and provenance files are rebuilt under
the validation workspace and must never be accepted as raw-cache inputs.

## Prespecified scientific oracle

| Dataset | Profile | BaseQ/MAPQ/readQ | Candidate sites | Accepted observations | Excluded observations |
| --- | --- | --- | ---: | ---: | ---: |
| GM11906 pooled scATAC | lenient | `0/0/0` | 33 | 44,048,838 | 7,296,932 |
| GM11906 pooled scATAC | default | `13/20/10` | 33 | 44,048,838 | 7,296,932 |
| GM11906 pooled scATAC | strict | `20/30/15` | 33 | 42,675,832 | 8,669,938 |
| GM12878 qn1000 | lenient | `0/0/0` | 32 | 8,278,969 | 911,659 |
| GM12878 qn1000 | default | `13/20/10` | 16 | 7,143,152 | 2,047,476 |
| GM12878 qn1000 | strict | `20/30/15` | 15 | 6,046,355 | 3,144,273 |

The default GM11906 output must contain exactly one `m.8344A>G` row with
callable depth 1,027, alternate count 740, forward/reverse alternate counts
305/435, serialized alternate allele fraction 0.720545, feature `MT-TK`, and
consequence `tRNA_variant`.
The serialized fraction is calculated across pooled passing read observations and is not interpreted as a per-cell or calibrated sample heteroplasmy estimate.

The GM12878 source must contain 193,043 records. The deterministic selection
uses the 1,000 smallest seeded query-name hashes under seed
`mito-overview-v0.3.0-GM12878-SRR18110025`. The default alignment and output
must contain 728 primary records, 543 supplementary records, mean/median
mitochondrial depth 545.484/544.0, eight selected co-occurrence sites,
13 deletion bins, five query names with qualifying CIGAR deletions, and 542
query names with supplementary or SA evidence.

Synthetic known answers include allele tuple `10:A>C` with depth 10, alternate
count 3, and fraction 0.3; WGS depths 100/10 with mt:nuclear ratio 10.0 and
five requested/five valid nuclear windows; and BED line `MT\t0\t60`.

## Required output and status contracts

Each default public run must contain 44 summary TSV files and 14 HTML pages.
GM11906 must contain seven PNG figures and GM12878 must contain 15. The exact
candidate rows, schemas, status values, and closed-world inventories are
release gates. Same-platform default repeats require exact normalized TSV and
decoded-pixel agreement. Cross-platform validation requires identical
normalized scientific values, schemas, and statuses; BAM and rendered-image
byte identity is not required.

For every dataset/filter profile, the frozen oracle records three versioned,
canonical SHA-256 contracts: all rows and columns in
`mito_heteroplasmy_candidates.tsv`, the complete summary-TSV path inventory,
and the ordered header of every summary TSV. Candidate rows are sorted before
hashing; summary paths and column order remain exact. These fingerprints detect
row-level changes that preserve aggregate counts, schema drift, and same-count
file substitutions. Default repeats and macOS/Ubuntu comparisons additionally
gate all 44 normalized scientific TSVs byte-for-byte.

The matrix exports an `observed_contracts/<case_id>/` directory for all eight
public runs. Each directory contains the exact candidate TSV and a canonical
manifest of every summary TSV path and ordered JSON-encoded header. Packet
construction and the standalone verifier independently recompute all three
fingerprints from these files and compare them with the frozen oracle. Missing
or additional cases/files, candidate-cell changes, and manifest path/header
changes fail even if the packet's ordinary SHA-256 manifest is rewritten. This
keeps lenient and strict evidence independently auditable without packaging the
large per-base depth tables.

Expected module states may be part of a passing case. In particular, targeted-
mt copy number is `not_applicable`; absent mvTool or methylation inputs are
`not_configured`; and mt-only NUMT interpretation is `not_evaluable` with
`reference_scope_mt_only`. An unexpected state is a failure.

## Evidence-integrity contracts

Release evidence is bound to the exact candidate rather than accepted by
filename alone.

- `resource_usage.tsv` contains exactly one row for each of the 11 prescribed
  measured commands. Every row records a case-insensitive unique UUID, the
  full candidate commit, exact `commands/<case>.sh` and `logs/<case>.log`
  paths, the original execution SHA-256 values, the SHA-256 values of the
  portable sanitized copies, the case-specific thread setting, and declared
  input/output inventory file counts and bytes. Every numeric value is finite;
  wall time, peak RSS, declared input count, and declared input bytes are
  positive. `unavailable` is not valid for a required resource case. Public
  reconstruction uses four threads;
  three lightweight synthetic workflows use one; orchestration/test cases are
  labeled `mixed` or `not_applicable` rather than assigned a false count.
  Missing, duplicated, relabeled, or hash-mismatched rows fail validation.
- The resolved CI environment root contains exactly five files for each of
  `linux-64`, `osx-64`, and `osx-arm64`. The platform record binds the exact
  commit and GitHub Actions run, Python 3.12.13, architecture, every evidence
  file's size and SHA-256, the evidence-manifest SHA-256, and the tracked
  platform-lock SHA-256.
- Same-platform rendered-image repeatability is checked by decoding every
  run-1 and run-2 PNG to canonical RGBA bytes and recomputing its pixel hash.
  A syntactically valid replacement digest, changed run-2 image, missing
  image, dimension mismatch, or duplicate basename fails validation.
- The downloaded Ubuntu artifact carries the actual HTML/PNG reports as well
  as each `visual_artifact_inventory.tsv`. Every row is rebound to the staged
  file's byte count and SHA-256; PNGs are reopened and decoded and HTML is
  parsed for the required document structure. Cross-platform comparison still
  gates only path, type, dimensions, and integrity, not rendered byte identity.
- Read-only audit comments must use the structured audit marker, be posted by
  the repository owner, bind the reviewed PR-head commit and final tree, carry
  unique case-insensitive audit-instance IDs, and include GitHub `created_at`
  and `updated_at` timestamps no later than the PR merge time. Later edits do
  not qualify as pre-merge release gates.
- `cross_platform_comparison.tsv` is present both in acceptance evidence and
  at the packet root for report consumption. The root artifact manifest covers
  every other regular file, including nested files also named
  `artifacts.sha256`; only the root manifest excludes itself.

The packet builder validates these rules against the clean candidate checkout.
Verification then follows an explicit trust order:

1. Before extraction, compare the ZIP with an expected SHA-256 supplied
   outside the ZIP. During assembly this is the separate release-identity
   receipt; after publication it is the independently obtained `SHA256SUMS`
   record or an explicit trusted digest.
2. Safely extract the digest-matched ZIP.
3. Run the extracted `verify_bundle.sh` to check its closed inventory,
   internal hashes, semantic constraints, timestamps, and release identity.

`verify_bundle.sh` is deliberately an internal-consistency verifier. It cannot
authenticate a coordinated replacement in which packet content and every hash
stored inside the same ZIP are changed together. The external digest source is
therefore the trust anchor and must be authenticated through the exact tag,
immutable GitHub release record, or another separately trusted channel. A
sidecar created in the same local build proves local handoff integrity only;
it becomes an external trust anchor only after it is published and obtained
independently.

## Verdict rules

`PASS` requires verified inputs and environment, successful execution, every
required oracle and inventory match, and zero offline network-canary events.
`FAIL` is used for executable cases with any value, status, schema, hash,
inventory, package, provenance, or network mismatch. `BLOCKED` is reserved for
an external prerequisite that prevents valid execution before analysis starts.
`SKIP` is allowed only for explicitly nonrequired platforms or live optional
services. No required release case may be `SKIP`, `BLOCKED`, `XFAIL`, or
missing.

An oracle mismatch is never updated automatically. It requires scientific
investigation, a separately reviewed commit explaining the discrepancy, and a
complete rerun from a new final commit.

## Required release sequence

1. Complete the release-candidate PR recorded by the validator and run three
   role-separated read-only software audits. Each audit uses a unique execution
   ID and is bound to the PR-head tree; owner-posted GitHub records do not imply
   distinct external reviewers.
2. Require Ubuntu and macOS PR CI at the exact final PR head.
3. Merge that PR and define the resulting `main` commit as `FINAL_SHA`.
4. Require push-event Ubuntu and macOS CI at `FINAL_SHA`.
5. Run independent macOS and Ubuntu clean-room public reproductions from the
   public HTTPS repository at `FINAL_SHA`.
6. Build and verify the GitHub-only validation packet from both its source
   directory and a fresh extraction.
7. Create annotated tag `v0.3.0` at `FINAL_SHA` and never move it. Capture
   `github_prepublication.json` through the publisher's read-only
   `--verify-prepublication` phase before any GitHub release exists. Build the
   report from that exact tag/repository identity. Render its DOCX with the
   documents workflow, inspect every `page-<N>.png`, and finalize the report
   evidence before assembly:

   ```bash
   python scripts/finalize_release_validation_report_v0.3.0.py \
     --report-root <rendered-report-directory> \
     --validation-zip <mito-overview-v0.3.0-validation.zip> \
     --packet-verification <packet-verification-json> \
     --rendered-pdf <renderer-output.pdf> \
     --rendered-pages <renderer-page-directory> \
     --final-sha <FINAL_SHA> \
     --visual-reviewer <reviewer-id> \
     --visual-review-pass
   ```

   The finalizer verifies the packet ZIP and embedded verifier, the report
   builder receipt, exact packet-native figure hashes, the final PDF page tree,
   and a contiguous PASS-reviewed page inventory whose count equals the PDF. It writes
   `report_provenance.json` beside the figure manifest. Then assemble the
   release assets with the fail-closed command below. The assembler requires
   the exact packet-built wheel and source distribution, an absent output
   directory, the complete provenance chain, and the exact environment-lock
   inventory. It copies rather than rebuilds those distributions and writes
   the manifest-bearing verification JSON atomically.

   ```bash
   python scripts/assemble_release_assets_v0.3.0.py \
     <absent-asset-source> \
     <mito-overview-v0.3.0-validation.zip> \
     <packet-verification-json> \
     <rendered-report-directory> \
     <release-notes-markdown> \
     <environment-text> \
     <resolved-platform-lock-root> \
     <packet-built-distribution-root> \
     <FINAL_SHA>
   ```
8. Run `scripts/run_fresh_public_tag_validation_v0.3.0.sh` from absent work and
   evidence roots with the assembled asset source. The runner clones the public
   tag and rebuilds wheel/sdist only to compare canonical member paths, payloads,
   sizes, and executable state. It installs the exact packet-bound wheel and
   source distribution in separate environments, verifies all package and
   synthetic gates, and seals all 12 canonical assets into a
   tag/`FINAL_SHA`-bound trusted manifest. Rebuilt archive bytes never replace
   the packet-bound release distributions.
9. Supply that exact PASS receipt and asset directory to every mutation phase.
   The publisher verifies all trusted hashes, enables native GitHub immutable
   releases when the initial query reports them disabled, re-queries until
   enabled, and only then creates the draft. It uploads and
   authenticated-redownloads every asset,
   publishes, and captures final release/tag/asset proof in
   `github_publication.json`. The report is intentionally prepublication to
   avoid hashing a document that claims verification of its own upload.
10. Stop before manuscript, bioRxiv, Notion, or MCW/HPC work.
