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
| package isolation | build wheel and sdist; install each in a separate environment and execute outside checkout with empty `PYTHONPATH` | pending final runner |
| I/O volume provenance | inventory declared input bytes before each measured command and changed/new validation-output bytes afterward | pending final runner |
| sealed public cache | exactly seven raw FASTQs plus manifest/seal; hashes, gzip, FASTQ structure, pairing, and metadata identity pass | pending clean-room download |
| GM11906 public matrix | three filter profiles plus exact default repeat, marker/inventory/status oracles | pending exact-final-commit rerun |
| GM12878 public matrix | deterministic subset/alignment rebuild, three profiles, exact default repeat, inventory/status oracles | pending exact-final-commit rerun |
| cross-platform reproduction | macOS clean room and Ubuntu public-data workflow agree on normalized scientific outputs and states | pending |
| packet verification | packet root and fresh ZIP extraction both pass `verify_bundle.sh` | pending |
| visual QA | final report-native HTML/PNG inventory and report DOCX/PDF rendering inspected | pending |
| GitHub publication | PR merged, push CI green, immutable annotated tag and verified assets published | pending |

## Candidate Checkpoint

Candidate `0bd64d2eed7400cd8772e77504b8ceab1f668cd8` completed the sealed-cache macOS public matrix after independent review of the deterministic overlap correction. All 17 required cases and all 366 reviewed oracle assertions passed. Both default-run normalized TSV comparisons, decoded-pixel comparisons, and HTML structural comparisons were identical; cache postflight and process-tree network-isolation checks passed. GM11906 retained 33 candidates and the `m.8344A>G` result (`740/1027`, alternate allele fraction `0.720545`) after ambiguous equal-quality mate ties were moved from accepted to excluded accounting. GM12878 had no overlap ambiguities and retained its prespecified public results. This checkpoint is candidate evidence only; it does not satisfy the exact public `FINAL_SHA`, empty-cache cross-platform, packet, tag, or publication gates above.

Candidate `bb2c63228baea418526e14e3eaa550d704b4435e` was withdrawn after the reproducibility audit showed that a self-consistent but noncanonical GM12878 selected-name ledger could pass packet verification and that cached alignment verification did not enforce the recorded command, parameters, and tool versions. The successor working tree now recomputes the seeded 1,000-name minimum set from all 193,043 source FASTQ records, verifies exact subset membership, and requires the complete BWA/minimap2 derivation dictionaries during live reuse, packet construction, and fresh packet extraction. Adversarial tests reject rehashed ledgers, subset-digest substitutions, missing commands, changed parameters, and changed tool versions.

Local remediation evidence passed before freezing the successor commit: `771/771` mandatory tests, `14/14` optional archive-helper tests, all four installed-wheel synthetic workflows, two byte-identical regenerations of each tracked example bundle, wheel/sdist installation outside the checkout, the 18-step CLI listing, strict generic dry-run, package/hygiene checks, and real cached public default reruns. The current-wheel GM11906 rerun matched the reviewed normalized tables and visual inventory exactly and retained 33 candidates, 44,048,838 accepted observations, 7,296,932 excluded observations, and `m.8344A>G` at depth/count/forward/reverse/fraction `1027/740/305/435/0.720545`. The current-wheel GM12878 rerun also matched exactly, with 16 candidates, 7,143,152 accepted observations, 2,047,476 excluded observations, 13 deletion clusters, eight co-occurrence sites, and `not_evaluable` mt-only NUMT interpretation. These are local remediation checks, not substitutes for fresh exact-commit audits, empty-cache Mac/Ubuntu reproduction, or the final GitHub release gates.

Candidate `95801108c9b26178c28bd7a6cd59d9c67121c4a3` was subsequently withdrawn before push. Exact-commit review found inconsistent MD5 field inventories between the GM12878 subset and alignment records, checkout-code leakage from public helper scripts in installed-package mode, duplicate provenance labels that could be collapsed by dictionary indexing, and narrative evidence tables that were hashed but not semantically rebound to PASS cases and source values. The successor working tree standardizes selected-ledger MD5/SHA-256 identity, rejects duplicate labels in live/packet/extracted verification, isolates all provenance/subset helpers from checkout imports, freezes the six bounded claims, resolves their evidence references, and recomputes handoff values from `filter_profile_results.tsv`.

Post-remediation local evidence passed `783/783` complete tests and `226/226` directly affected tests. A force-installed external wheel passed all three helper import probes and all four workflow smokes. Temporary public derivatives were rebuilt without modifying the raw cache; GM11906 and GM12878 normalized scientific tables and visual structures matched prior reviewed outputs exactly, and the selected-name ledger was linked in both manifests as 18,422 bytes, MD5 `64d606e56bf8dd58ad68baad28898e18`, SHA-256 `3444cc7db3dcf78bea807d8bcc6686883a7759d128288c1d26aeae077a771a19`. These checks are still provisional until a new exact commit and fresh independent audits pass.

Candidate `b639eec19f1e30add780eb4a74c48ab8aeebee8e` was then withdrawn before push. Independent audit showed that its tracked GM12878 alignment manifest still carried the old subset-manifest size and hashes, deterministic FASTQ verification could accept a manifest with omitted digest fields, and the fresh-extraction verifier did not independently enforce schema, provenance type, and dataset identity for all three nested public records. The successor working tree binds the current 1,180-byte subset manifest by MD5 and SHA-256, requires complete name/size/MD5/SHA-256 FASTQ records, and rejects rehashed identity drift for the GM11906 alignment, GM12878 subset, and GM12878 alignment records.

The successor working tree passed `39/39` focused adversarial tests, `237/237` complete provenance/packet/tracked-report tests, and `797/797` mandatory repository tests. These tests establish fail-closed handling of the reproduced evidence defects; they do not replace exact-commit package isolation, workflow smokes, fresh read-only audits, PR/push CI, empty-cache cross-platform public reproduction, packet/report verification, or release publication.

Candidate `c260ce2484838bf89f2ae0e39fbdf2a0f1737f18` was subsequently withdrawn before push. It passed `797/797` exact-tree tests, exact-archive wheel/sdist installation, installed-package helper probes, and all four workflow smokes, and its release-engineering audit had no blocker. A separate bioinformatics audit nevertheless reproduced a one-row mitochondrial depth file being accepted as a whole-mitochondrion numerator and yielding a numeric mt:nuclear ratio. Because this violates the declared estimator, the successful predefined gates were not treated as sufficient release evidence.

The successor working tree now accepts a mitochondrial numerator only from a complete coordinate inventory with one finite, nonnegative depth at each position `1..MT_LENGTH` and a finite resulting mean. Nine malformed-profile classes fail closed as `not_evaluable/incomplete_mito_depth_profile`, while the `100/10=10.0` known answer is preserved. The focused copy-number suite passed `16/16`, the connected workflow/example surface passed `74/74` without tracked-output drift, and the complete mandatory suite passed `806/806` in 393.20 seconds. These remain working-tree results pending a new exact commit and fresh role-separated audits.

Candidate `2fb08a3b741e5ee603be075bdd1d8054d4211a18` was also withdrawn before push. It passed `806/806` exact-tree tests, exact-archive wheel/sdist installation, all four installed-wheel workflow smokes, and separate release-engineering and reproducibility reviews. Bioinformatics review nevertheless reproduced two remaining defects: circularity QC could truncate fractional coordinates and accept negative or nonfinite depths as a complete profile, and the packet builder/extracted verifier allowed the nested deterministic-subset manifest to omit MD5.

The successor working tree now requires the circularity profile to contain the exact integer coordinate inventory `1..MT_LENGTH`, finite nonnegative depths, and finite regional means; malformed present evidence is `not_evaluable/incomplete_depth_profile`. Packet construction and fresh extraction require every public input to have exactly `label`, `name`, `bytes`, `md5`, and `sha256`, and both stages validate the nested subset manifest's actual MD5, SHA-256, and byte count. Pre-freeze remediation checks passed `10/10` circularity tests, `215/215` complete packet tests before the final two wrong-MD5 cases, `6/6` direct digest-inventory/recomputation attacks after those cases were added, `133/133` connected tests, and `33/33` release-hygiene tests plus the 433-file scan. Full exact-tree validation and three replacement audits remain pending.

Candidate `a0131cf899ab4cacaa604413c121cbe96ce40764` (tree `a0231905af208d78f34f177fb657009d9436e427`) completed `817/817` exact-commit tests and `817/817` tests from the extracted source distribution. Its exact archive built and separately installed a wheel and source distribution outside the checkout, exposed the same 18-step CLI registry, passed strict dry-run, all four installed-package synthetic workflows, and byte-identical 88-file long-read and 74-file reduced-short-read example rebuilds. Read-only release-engineering and reproducibility audits returned PASS with no blockers. The independent bioinformatics audit returned HOLD after adversarially reproducing three scientific fail-closed defects, so the candidate was not pushed and the two PASS role verdicts are not transferable to a successor tree.

The reproduced scientific defects were: nonfinite bedMethyl count values could be aggregated into an apparent zero-modification result; nonfinite, negative, out-of-range, or nonbinary required NUMT read statistics could still yield a categorical whole-genome low-risk warning; and malformed optional circularity candidate/read coordinates or soft-clip fractions could yield apparently evaluable zero/one edge fractions. The successor working tree rejects nonfinite serialized bedMethyl numerics and required count fields, requires documented finite domains for every NUMT interpretation field, and assigns explicit metric-level `NA/not_evaluable` reasons to malformed circularity optional evidence without overwriting an independently valid depth-profile status.

Pre-freeze remediation checks on the successor working tree passed `94/94` focused methylation, bedMethyl, NUMT, and circularity tests plus `59/59` connected reference-scope, example-builder, tracked-report, status, and table-contract tests. These results are not exact-commit release evidence. Complete tests, isolated distributions, installed-package workflows, deterministic example comparisons, hygiene, and three entirely new role-separated audits remain required after the successor commit is frozen.

Candidate `454c0b93e04069ffd219da0a97a00fecaf17f839` was subsequently frozen and passed the predefined exact-checkout and extracted-source-distribution suite, but it was rejected before push after all three replacement role audits returned HOLD. The scientific audit (`mito-overview-v0.3.0-20260723T032135Z-c6509d0a-44d3-4ac8-83d0-ff8d8db54d83`) identified eight connected fail-open classes spanning configuration domains, canonical reference eligibility, internal candidate contracts, stale co-segregation evidence, deletion bounds, integer bedMethyl counts, circularity coordinate ordering, and NUMT consistency/availability. The reproducibility audit (`12603a81-2120-4f20-b390-9739ec91f9bc`) demonstrated acceptance of incomplete cached digest identities. The release audit (`mitooverview-v0.3.0-20260723T032145Z-121646d6-71dc-4c3c-a273-b74c3cfc0409`) demonstrated acceptance of post-upload prerelease-state drift.

The successor tree now fails closed for those cases. Shared table validators enforce exact coordinate, allele, depth, fraction, strand, count-sum, uniqueness, and configured-reference invariants; upstream candidate state is propagated; mitochondrial deletion bounds and integer bedMethyl counts are explicit; reversed circularity read coordinates are non-evaluable; and NUMT interpretation requires MAPQ `0..254`, consistent aligned bases/fraction, and a valid required QC fraction. Public derivatives require complete exact digest records, and the release publisher requires `prerelease` to remain literal `false` at every checkpoint. Focused remediation passed `327/327`; after three expected deterministic fixtures were corrected, the complete pre-freeze suite passed `913/913` in 425.05 seconds. No successor PASS audit exists yet, so all exact-commit package, workflow, public-data, CI, packet, tag, and publication gates remain pending.

Exact candidate `87bea3bb9666b1f838bd2ab231c5c3490faab54c` subsequently passed `913/913` in both its checkout and extracted source distribution, separate installed wheel/source-distribution probes, strict dry-run, all four installed-package workflow modes, and exact long-/short-read example rebuilds. It was rejected before push after the release-engineering audit (`MO-AUDIT-20260723T044516Z-e4551c15-4d61-4d14-a811-3b92a77dfd15`) and scientific audit (`mitooverview-87bea3b-20260723T044458Z-5daf86fc-6c1d-4fc4-a00f-dd8a972f6695`) each returned HOLD. The former reproduced a last-transition window in which release identity or assets could drift before an irreversible publication. The latter reproduced permissive partial/duplicate candidate evidence and inconsistent NUMT read/upstream-QC evidence that could still produce apparently evaluable results. Two provenance-review attempts ended in agent-service errors and produced no verdict, so neither is release evidence.

The successor working tree closes those cases. Candidate tables require all 14 generated fields, two independently valid and matching fraction columns, exact depth/base/strand identities, unique variant keys, and one selected alternate per position. NUMT warning calculation requires coherent primary/secondary/supplementary flags, coherent soft-clip counts/fractions, and an upstream near-complete-alignment metric whose module status, metric status, and denominator are explicitly valid. The final GitHub publication PATCH restates tag, target commit, release name, draft state, and non-prerelease state and validates the complete returned asset inventory before writing the transition receipt. Connected checks passed `81/81`, `91/91`, and `117/117`; the complete pre-freeze suite passed `951/951` in 476.34 seconds. A new exact commit, exact-archive/package/workflow/example gates, and three fresh PASS audits remain mandatory before push.

Exact candidate `b2f520dc919b4b32dc209b7058ac753b2149fada` then completed `951/951` tests in its checkout, exact archive, and extracted source distribution, plus isolated wheel/source-distribution installation, strict CLI/dry-run checks, all four installed-wheel workflow modes, and byte-identical long-/short-read example rebuilds. Release-engineering audit `MO-RELENG-B2F520D-20260723T060629Z` and reproducibility audit `MO-REPRO-20260723T060135Z-b4854555-793e-4db7-b67a-de2fac4d8566` returned PASS for their bounded roles. Scientific audit `MO-SCI-AUDIT-20260723T055200Z-b2f520d` returned HOLD after adversarially demonstrating a non-dominant selected alternate, silent candidate deduplication or partial validation in mvTool/circularity, and categorical NUMT output from impossible query-consuming geometry. The candidate was rejected before push; no role-specific PASS transfers to a modified tree.

The successor working tree now requires a selected alternate count to equal a largest non-reference canonical-base count, applies the complete generated candidate contract in mvTool and circularity before interpretation, and enforces `aligned_reference_bases + softclip_bases <= query_length`. It corrects the impossible positive NUMT fixture and adds exact negative tests showing malformed or duplicate candidate evidence cannot create a network session or circularity candidate metric. The focused remediation suite passed `113/113`, compilation and diff hygiene passed, and the complete pre-freeze suite passed `957/957` in 425.57 seconds without valid tracked-output drift. These remain pre-freeze checks; all exact successor and independent audit gates must be repeated.

Exact candidate `7a66bfc92208cb454a7c56cf9dea8408a639cea1` repeated the complete `957/957` suite from its exact archive and extracted source distribution, installed both distributions outside source trees, passed all four installed-wheel workflow modes, and exactly rebuilt both tracked examples twice. Reproducibility audit `MO-REPRO-20260723T065259Z-bf3169cb-ca3b-4ce1-8afe-09fc4a729c04` and release-engineering audit `MO-RELENG-7A66BFC-20260723T064327Z-c80e0441-dba4-4671-88e4-b61dbce135a3` returned role-specific PASS. Scientific audit `MO-SCI-20260723T064328Z-df987b6f-9996-4e99-adad-9343a5dc1a33` returned HOLD after showing that an existing partial-header zero-row candidate file bypassed validation in mvTool and circularity. The candidate was rejected before push; no prior PASS approves changed code.

The successor working tree validates every existing candidate file before testing row count and no longer fabricates candidate columns during circularity loading. Missing candidate input, valid complete-schema emptiness, and malformed zero-row evidence now have distinct behavior. The connected candidate/mvTool/circularity/NUMT suite passed `116/116`, and the complete pre-freeze suite passed `960/960` in 452.70 seconds without valid tracked-output drift. The frozen manuscript's superseded GM11906 totals are recorded for the later manuscript phase; `paper/**` remains deliberately untouched here.

## Public Input Provenance

- `SRR10804585` / `GSM4238454`, `SRR10804590` / `GSM4238459`, and `SRR10804657` / `GSM4238526` are separate C1 single-cell ATAC-seq libraries from the GM11906 lymphoblastoid line.
- The three paired-end libraries are concatenated as a deliberately selected read-depth-weighted pseudo-bulk for marker-representation testing.
- `SRR18110025` is the GM12878 ONT targeted-mt source; the clean-room process deterministically selects 1,000 query names with seed `mito-overview-v0.3.0-GM12878-SRR18110025`.
- Raw FASTQs remain outside Git and the validation ZIP. Derived alignments are rebuilt in each clean-room workspace.

## Active Release Command

```bash
export PATH="<locked-env-prefix>/bin:$PATH"
export MITO_OVERVIEW_PYTHON="<locked-env-prefix>/bin/python"

MITO_OVERVIEW_PR_NUMBER=3 \
MITO_OVERVIEW_PR_RUN_ID=<successful-pr-smoke-run-id> \
MITO_OVERVIEW_GITHUB_RUN_ID=<successful-main-push-smoke-run-id> \
MITO_OVERVIEW_PUBLIC_RUN_ID=<successful-ubuntu-public-run-id> \
./scripts/run_release_validation_v0.3.0.sh \
  <validation-root> <raw-cache-root> <packet-root> \
  <mito-overview-v0.3.0-validation.zip>
```

The runner must reject legacy DOI/Zenodo arguments, require an absent raw-cache path, clone public GitHub HTTPS at an exact 40-character commit, build/install distributions outside the checkout, collect exact PR-head, final-push, and Ubuntu-public-run evidence, build schema `2.0` profile `github_release_validation_v1`, and verify both the packet root and a fresh ZIP extraction. The environment prefix must have been solved from the matching platform specification and must satisfy the runner's exact runtime-version checks; ambient Mac tools are not accepted.

## Ordered Finish Gate

1. Stabilize and review the GitHub-only branch without modifying `paper/**`.
2. Run complete local tests, all four synthetic workflows, both example builders, package-isolation checks, and hygiene scans.
3. Run three role-separated read-only agent audits for release engineering,
   bioinformatics, and reproducibility. Bind unique audit-instance IDs to the
   reviewed PR-head tree, resolve every blocker, and rerun affected gates;
   owner-posted GitHub records are not represented as external peer review.
4. Push PR #3 and require green Ubuntu/macOS CI at the exact head.
5. Merge to `main`; record `FINAL_SHA`; require successful push-event CI at that exact SHA.
6. Run a fresh macOS public clean-room reproduction from an empty cache and the Ubuntu public workflow at `FINAL_SHA`; compare normalized outputs and module states.
7. Build and verify the audit ZIP, then tag exactly `FINAL_SHA` as annotated
   `v0.3.0`. Before any GitHub release exists, run the publisher's read-only
   `--verify-prepublication` phase and build/visually inspect the human-readable
   MD/DOCX/PDF report from that exact main/tag identity. Preserve the builder's
   `report_build_provenance.json`, render every DOCX page, inspect every page,
   and run `scripts/finalize_release_validation_report_v0.3.0.py` to bind the
   PDF and rendered-page PASS inventory to the exact validation ZIP.
8. Assemble the non-distribution assets and run
   `scripts/assemble_release_assets_v0.3.0.py`; its atomic output is the only
   accepted input to `scripts/run_fresh_public_tag_validation_v0.3.0.sh`
   against the public HTTPS tag. The assembler requires exactly five resolved
   environment records per platform and revalidates the packet-to-figure-to-
   DOCX-to-PDF-to-rendered-page provenance. Retain its semantic identity result
   plus the fresh-tag cases, commands, logs, environment, annotated-tag
   identity, trusted 12-asset manifest, hashes, and PASS receipt.
9. Supply the sealed assets and receipt to create the draft, establish the
   recorded hosting-protection state, upload and authenticated-redownload all
   assets, publish, and write the independently queried post-publication proof
   to `github_publication.json`.

The report builder accepts only a verified read-only prepublication receipt.
This avoids self-reference because the report is itself a hashed release asset.
Final upload hashes, tag identity, and the native-immutability or explicit
unsupported-feature fallback state are verified separately in
`github_publication.json`.

Any commit after `FINAL_SHA` invalidates the release evidence. Any defect after publication is corrected forward as `v0.3.1`; the `v0.3.0` tag is never moved.

## Rejected candidate `2b981a0` and successor remediation

Exact commit `2b981a018629640b81f6a7eb8ec1accab370cbc8` is rejected and was not pushed. Reproducibility audit `MOV-REPRO-20260723T074138Z-ef12f565-e795-44d8-9e8e-9f628ce8094e` passed its bounded role. Release-engineering audit `MO-RELENG-20260723T074129Z-2ef3043b-27ad-455d-89c9-c6485bd0b419` held the candidate for an unavailable immutable-release fallback and two sdist README links to excluded repository-only files. Scientific audit `MO-SCI-2B981A0-20260723T080601Z-CCD0B462` held it because Phy-Mer, mvTool, and circularity could interpret stale or malformed upstream allele evidence and because missing candidate evidence was not distinguished from an observed zero-candidate result.

The successor clears prior heteroplasmy outputs before recounting, propagates the controlled upstream module state, validates every mitochondrial position and REF allele before Phy-Mer consensus editing, and separates missing from observed-zero candidate states. The release publisher now attempts immutable hosting first and accepts only a confirmed endpoint-unavailable fallback bound to the verified annotated tag and authenticated asset SHA-256 checks. The focused scientific and connected release suites passed `118/118` and `158/158`, respectively. Two independent checkout-mode example rebuilds were byte-identical across 88 long-read and 74 short-read files; the complete pinned suite passed `974/974` in 440.92 seconds; and all four installed-package smoke modes passed, including minimal BAM and CRAM. These are pre-freeze working-tree checks, not release evidence; exact archive/distribution validation and three fresh exact-commit audits remain pending.

## Rejected candidate `223148c` and successor remediation

Exact commit `223148c88cac9f483acc9550028ed31c179fb4ed` is rejected and was not pushed. Release-engineering audit `DA43BF39-6609-434E-AC89-23D37176298A`, reproducibility audit `MO-REPRO-20260723T091606Z-21a16b95-6d37-4081-86f1-0333ed888412`, and scientific audit `MT-AUDIT-223148C-20260723T085745Z` each returned HOLD. The release and reproducibility reviews showed that fuzzy “not found” matching and a PUT-time 404 could silently downgrade a supported GitHub immutable-release endpoint to the fallback. The scientific review showed that a single callable mitochondrial position could support a reference-filled Phy-Mer consensus, nonfinite ranking scores could be accepted, and reuse of one `RUN_NAME` could expose auxiliary artifacts from an earlier mode.

The successor recognizes only an explicit HTTP 404 on the initial endpoint query as the documented unsupported-feature fallback; any failure after support is established stops publication. Phy-Mer now requires a configurable callable-genome fraction (default `0.95` at its configured minimum depth), masks residual low-depth bases with `N`, accepts an otherwise eligible zero-alternate consensus, rejects nonfinite scores, and records the complete eligibility denominator. Real workflow runs and final sync destinations are single-use and fail before modification when pre-existing or overlapping, while dry-run is non-mutating. Focused remediation passed `122/122`, and the complete pinned working-tree suite passed `995/995` in 446.64 seconds. A wheel installed outside the checkout then passed all four workflow modes. Two independent long- and short-read example regenerations were byte-identical; only the expected Phy-Mer summary, masked consensus FASTA, and page 13 changed from the rejected candidate. These are working-tree results and do not replace a successor exact-commit suite or three new audits.

## Rejected candidate `7cecb5b` and successor remediation

Exact commit `7cecb5ba5e353a6761b981394a942df4c049ce09` is rejected and was not pushed. Release-engineering audit `MO-RELENG-7CECB5B-20260723T101337Z-95F29A02-DF3B-45AA-86F5-9B75817A9BBF` and reproducibility audit `MO-REPRO-7CECB5B-20260723T100351Z-0854f9c9-d0ec-44c0-8de3-1c87cec8fecd` returned role-specific PASS. Scientific audit `MO-SCI-7CECB5B-20260723T101602Z-164F9485-F02C-4FFA-9E5F-832DCB037A35` returned HOLD after reproducing acceptance of finite out-of-domain scores, non-fixture use of the 0.30 callable threshold, stale direct-step outputs, and an incomplete official-runtime dependency contract. No verdict transfers to a successor tree.

The successor bounds Phy-Mer scores to `[0,1]`, separates exact-hash synthetic fixture mode from external mode, enforces the external 0.95 callable floor, removes every owned output before validation, pins BioPython 1.87, and adapts only the official script's removed `rU` mode at runtime. The complete all-site contract permits an exactly reference-matching unresolved `N`, but excludes it from the callable numerator and masks it rather than treating it as a variant; all other ambiguity symbols fail. An untouched-official-tree compatibility probe against bundled `NC_012920.1` passed with top ranking `H2a2a1`, score `0.999632`, `16568/16569` callable positions, and position 3107 retained as `N`. Focused contracts passed `76/76`. The first complete run correctly detected stale generated page-13 evidence (`1008` passed, one failed); two independent source-mode rebuilds were byte-identical at 88 long-read and 74 short-read files, and only the expected Phy-Mer summary and HTML required refresh. The clean complete rerun passed `1009/1009` in 450.40 seconds. Fresh wheel and source-distribution installations in separate pinned external environments each resolved only from `site-packages`, listed all 18 steps, and passed all four workflow modes. This remains pre-freeze evidence pending a new exact commit, exact archive/distribution repetition, and three new exact-SHA audits.
