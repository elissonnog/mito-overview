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
| Frozen `paper/` tree | `bfb5664db9c8b43ed5de33ecbddef88071fc6378` |
| Prior immutable release | `v0.2.1` at `2ba62b775a7204c0dc61f5408989603f536c78da` |

No release-hardening commit may modify `paper/**`. The final release commit,
CI jobs, tag, distributions, validation packet, and reports must all resolve to
one full 40-character commit.

## Locked execution environment

The tested Python line is `>=3.12,<3.13`. Release validation uses Python
3.12.13, samtools/htslib 1.23.1, minimap2 2.31-r1302, BWA 0.7.19-r1273,
pysam 0.24.0, pandas 3.0.3, NumPy 2.5.1, Matplotlib 3.11.0, Requests
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
| GM11906 pooled scATAC | lenient | `0/0/0` | 33 | 44,052,664 | 7,293,106 |
| GM11906 pooled scATAC | default | `13/20/10` | 33 | 44,052,664 | 7,293,106 |
| GM11906 pooled scATAC | strict | `20/30/15` | 33 | 42,676,166 | 8,669,604 |
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

Expected module states may be part of a passing case. In particular, targeted-
mt copy number is `not_applicable`; absent mvTool or methylation inputs are
`not_configured`; and mt-only NUMT interpretation is `not_evaluable` with
`reference_scope_mt_only`. An unexpected state is a failure.

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

1. Complete PR 3 and run three role-separated read-only agent audits without
   modifying `paper/**`. Each audit uses a unique execution ID and is bound to
   the PR-head tree; owner-posted GitHub records do not imply distinct external
   reviewers.
2. Require Ubuntu and macOS PR CI at the exact final PR head.
3. Merge PR 3 and define the resulting `main` commit as `FINAL_SHA`.
4. Require push-event Ubuntu and macOS CI at `FINAL_SHA`.
5. Run independent macOS and Ubuntu clean-room public reproductions from the
   public HTTPS repository at `FINAL_SHA`.
6. Build and verify the GitHub-only validation packet from both its source
   directory and a fresh extraction.
7. Create annotated tag `v0.3.0` at `FINAL_SHA` and never move it. Capture
   `github_prepublication.json` through the publisher's read-only
   `--verify-prepublication` phase before any GitHub release exists. Build and
   visually inspect the report from that exact tag/repository identity, then
   assemble the remaining non-distribution assets with the fail-closed command
   below. The command requires an absent output directory, verifies the packet
   ZIP and its embedded verifier, checks the report/release/environment commit
   identities, and writes the manifest-bearing verification JSON atomically.

   ```bash
   python scripts/assemble_release_assets_v0.3.0.py \
     <absent-asset-source> \
     <mito-overview-v0.3.0-validation.zip> \
     <packet-verification-json> \
     <rendered-report-directory> \
     <release-notes-markdown> \
     <environment-text> \
     <resolved-platform-lock-root> \
     <FINAL_SHA>
   ```
8. Run `scripts/run_fresh_public_tag_validation_v0.3.0.sh` from absent work and
   evidence roots with the assembled asset source. The runner clones the public
   tag, builds wheel/sdist, verifies all package and synthetic gates, and seals
   all 12 canonical assets into a tag/`FINAL_SHA`-bound trusted manifest.
9. Supply that exact PASS receipt and asset directory to every mutation phase.
   The publisher verifies all trusted hashes before enabling immutable releases
   or creating the draft, uploads and authenticated-redownloads every asset,
   publishes, and captures final release/tag/asset proof in
   `github_publication.json`. The report is intentionally prepublication to
   avoid hashing a document that claims verification of its own upload.
10. Stop before manuscript, bioRxiv, Notion, or MCW/HPC work.
