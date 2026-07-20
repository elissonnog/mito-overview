# MitoOverview v0.3.0 implementation log

This log records release-hardening actions that affect the public repository. It is not a biological-results ledger; exact validation commands and outputs are captured in the versioned validation packet.

## 2026-07-20

- Confirmed branch `codex/preprint-hardening-v0.3.0` was clean at `5812799` and immutable tag `v0.2.1` remained at `2ba62b775a7204c0dc61f5408989603f536c78da`.
- Confirmed the ENA GM12878 FASTQ and full mapped BAM remained in the local validation cache after the interrupted full-depth probe; no MCW/HPC path was accessed or modified.
- Added portable public-alignment provenance and deterministic query-name subset implementation with focused known-answer and tamper-rejection tests.
- Closed reviewer-identified edge cases for absent mtDNA depth evidence, zero-support alternate alleles, auditable configured depth caps, and incomplete-reference NUMT scope assertions.
- Hardened the public validation matrix with portable cache defaults, replayable quoted commands, exact filter-profile assertions, and Python-based relative SHA-256 manifests.
