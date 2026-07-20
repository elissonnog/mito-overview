# MitoOverview v0.3.0 implementation log

This log records release-hardening actions that affect the public repository. It is not a biological-results ledger; exact validation commands and outputs are captured in the versioned validation packet.

## 2026-07-20

- Confirmed branch `codex/preprint-hardening-v0.3.0` was clean at `5812799` and immutable tag `v0.2.1` remained at `2ba62b775a7204c0dc61f5408989603f536c78da`.
- Confirmed the ENA GM12878 FASTQ and full mapped BAM remained in the local validation cache after the interrupted full-depth probe; no MCW/HPC path was accessed or modified.
- Added portable public-alignment provenance and deterministic query-name subset implementation with focused known-answer and tamper-rejection tests.
- Closed reviewer-identified edge cases for absent mtDNA depth evidence, zero-support alternate alleles, auditable configured depth caps, and incomplete-reference NUMT scope assertions.
- Hardened the public validation matrix with portable cache defaults, replayable quoted commands, exact filter-profile assertions, and Python-based relative SHA-256 manifests.
- Rebuilt the GM11906 public alignment from verified FASTQs, recorded its alignment provenance, and confirmed the corrected default `m.8344A>G` result (`1027` callable depth, `740` alternate observations, `0.720545` alternate allele fraction).
- A full GM12878 BAM rebuild failed during SAMtools output merge because the Mac volume had insufficient physically writable space; the partial BAM was rejected and removed. The public long-read validation was revised to select a seeded 2,000-query-name FASTQ subset directly from the complete verified run, bind that subset to the raw FASTQ by hashes, and align only the explicitly labeled reduced input.
