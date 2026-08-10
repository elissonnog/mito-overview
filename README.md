# MitoOverview

[![Release](https://img.shields.io/github/v/release/elissonnog/mito-overview)](https://github.com/elissonnog/mito-overview/releases/latest)
[![Smoke tests](https://github.com/elissonnog/mito-overview/actions/workflows/smoke-tests.yml/badge.svg)](https://github.com/elissonnog/mito-overview/actions/workflows/smoke-tests.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-2F855A.svg)](LICENSE)

MitoOverview is a per-sample mitochondrial DNA (mtDNA) reporting workflow for coordinate-sorted, indexed BAM or CRAM alignments. It integrates sequence-depth QC, observed alternate-allele-fraction screening, long-read structural evidence, mitochondrial feature annotation, read-level co-occurrence, alignment-ambiguity QC, and optional methylation or external annotation inputs into synchronized TSV, PNG, and HTML outputs.

The workflow supports ONT-oriented long-read analysis and a reduced short-read compatibility profile. Unsupported or unconfigured analyses remain visible as explicit status reports rather than silently disappearing, making each report bundle auditable across assay types.

Version `0.3.1` defines the workflow/resource release described here.

The immutable [`v0.3.1` release](https://github.com/elissonnog/mito-overview/releases/tag/v0.3.1) contains the validated software, distributions, report, and audit packet. It preserves the frozen `v0.3.0` scientific protocol; `v0.3.1` corrects release/report tooling without changing scientific algorithms, thresholds, schemas, public inputs, or normalized biological results. Documentation on `main` may receive clarifying corrections after release, so analyses intended to reproduce the reported evidence should use the tag.

## Scientific scope

MitoOverview reports evidence; it is not a clinically validated variant caller or diagnostic system. Its principal analytical layers are:

| Layer | Reported output | Interpretation boundary |
| --- | --- | --- |
| mtDNA QC | Per-base depth, read count, read length, and mapping summaries | Descriptive alignment QC |
| Candidate alleles | Callable depth, base counts, strand counts, and observed alternate allele fraction | Candidate-site screen, not calibrated low-frequency detection |
| Structural evidence | CIGAR-deletion events/clusters and supplementary-alignment summaries | Structural screen, not a validated deletion caller |
| mt:nuclear depth | Mean mtDNA depth divided by mean depth across sampled nuclear windows | Experimental within-sample ratio, not copies per cell |
| Functional context | mtDNA feature, gene, and sequence-consequence summaries | Reference-based annotation, not pathogenicity classification |
| Read co-occurrence | Pairwise support among selected sites on the same long reads | Descriptive molecule-level association |
| Alignment QC | Alignment span, MAPQ, reference-scope, and circular-edge metrics | Warning-oriented QC; not formal NUMT classification |
| Methylation | Optional bedMethyl-derived summaries | Exploratory and chemistry/input dependent |
| External enrichment | Optional Phy-Mer-style haplogroup and mvTool-style annotation pages | Secondary annotation; disabled or absent inputs do not block core reporting |

Default allele-observation filters are inclusive thresholds of BaseQ `>=13`, MAPQ `>=20`, and mean read quality `>=10`. These are reporting defaults, not clinically calibrated thresholds. The canonical fraction is:

```text
observed alternate allele fraction = alternate observations / callable depth
callable depth = A + C + G + T observations passing all filters
```

At each site, the reported alternate allele is the non-reference canonical base with the largest passing observation count.

Detailed algorithms, equations, and status rules are documented in [`docs/methodology.md`](docs/methodology.md) and [`docs/inputs_outputs.md`](docs/inputs_outputs.md).

## Input profiles

The standalone input contract requires six configuration keys:

```text
WORK_ROOT
RUN_NAME
SAMPLE_ID
REF_FASTA
SOURCE_ALIGN_FILE
MT_CONTIG
```

The reference FASTA must have a `.fai` index. BAM and CRAM inputs must be coordinate sorted and have a `.bai` or `.crai` index, respectively. BAM/CRAM mode and mitochondrial length are inferred and checked against the file content and FASTA index. CRAM decoding additionally requires a sequence-compatible reference.

`READ_MODE` and `ASSAY_TYPE` determine which layers are evaluable:

| Profile | Active emphasis | Expected status-gated layers |
| --- | --- | --- |
| `long` + `wgs` | Full long-read reporting with nuclear context when available | Methylation and external enrichments depend on optional inputs |
| `long` + `targeted_mt` | Long-read mtDNA sequence and structural evidence | mt:nuclear ratio is `not_applicable`; NUMT interpretation is not evaluable with an mt-only reference |
| `short` + `wgs` | QC, candidate alleles, annotation, and optional mt:nuclear ratio | Long-molecule analyses are `not_applicable` |
| `short` + `targeted_mt` | Reduced mtDNA QC, candidate, and annotation profile | Nuclear-context and long-molecule analyses are `not_applicable` |

Human mtDNA has the most complete packaged annotation path. Feature coordinates must be compatible with the configured reference; canonical rCRS control-region annotation additionally requires an exact full-length sequence match to packaged `NC_012920.1`. Reference-driven core modules can be configured for other species, but organism-specific annotations and interpretation require independent validation.

## Installation

Conda is the recommended installation route. Python support is intentionally restricted to `>=3.12,<3.13` for the validated release.

```bash
git clone --branch v0.3.1 --depth 1 https://github.com/elissonnog/mito-overview.git
cd mito-overview
conda env create -f environment.yml
conda activate mito-overview
python -m pip install .
```

Release validation covered `linux-64` (Ubuntu), `osx-64` (Intel macOS), and `osx-arm64` (Apple silicon macOS). Windows has not been validated. For exact environment reproduction rather than routine installation, select the platform lock and create the environment directly from its resolved artifacts, for example:

```bash
conda create --name mito-overview-v0.3.1 \
  --file locks/environment-osx-arm64.explicit.txt
conda activate mito-overview-v0.3.1
python -m pip install .
```

Confirm that the command-line interface and canonical steps are available:

```bash
python -m mito_overview.cli --list-steps
```

The pinned release environment includes Python 3.12, samtools/htslib, minimap2, BWA, pysam, pandas, NumPy, Matplotlib, Requests, pytest, and package-build tools. See [`environment.yml`](environment.yml) and [`locks/`](locks) for the platform-specific reproducibility records. Measured release-validation runtime and resource inventories are reported in the [validation report](https://github.com/elissonnog/mito-overview/releases/download/v0.3.1/MitoOverview_v0.3.1_release_validation_report.pdf).

## Five-minute validation

Run the deterministic long-read synthetic workflow supplied with the repository:

```bash
./tests/smoke_public_pipeline.sh
```

A successful run exercises the 14-page report pattern and verifies its expected files. Additional modes are covered by:

```bash
./tests/smoke_public_pipeline_shortread.sh
./tests/smoke_public_pipeline_longread_nomethyl.sh
./tests/smoke_standalone_minimal.sh
```

To build an inspectable toy report bundle, always provide a new disposable directory:

```bash
TOY_OUTPUT="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-toy.XXXXXX")"
./scripts/build_public_example_bundle.sh "$TOY_OUTPUT"
printf 'Toy report: %s\n' "$TOY_OUTPUT/report/01_mito_qc.html"
```

The example builders and public-validation scripts manage their output directories and may remove an existing directory at the supplied path. Do not point them at a directory containing unrelated data.

Tracked expected outputs are available for [long-read TOY-001](examples/expected_reports/TOY-001_output) and [short-read TOY-SR-001](examples/expected_reports/TOY-SR-001_output).

## Run a sample

Start from the generic standalone template, not the placeholder human example:

```bash
cp examples/configs/standalone_bam.env sample.env
```

Edit the six required keys in `sample.env`, set `READ_MODE` and `ASSAY_TYPE`, then create any missing indexes:

```bash
samtools faidx /path/to/reference.fa
samtools index /path/to/alignment.bam
```

Strict preflight checks paths, indexes, container type, mitochondrial contig, inferred length, and reference compatibility without creating a run directory:

```bash
python -m mito_overview.cli \
  --config sample.env \
  --dry-run \
  --strict-files
```

Run the complete workflow:

```bash
./scripts/run_mito_pipeline.sh --config sample.env
```

Or select a dependency-consistent subset:

```bash
./scripts/run_mito_pipeline.sh \
  --config sample.env \
  --steps validate,stage,extract,mito_qc,heteroplasmy
```

`WORK_ROOT/RUN_NAME` and any configured `FINAL_BIOINFO_DIR` are fresh, single-use output namespaces. MitoOverview refuses to overwrite an existing run; use a new `RUN_NAME` or a new empty output location. A dry run without `--strict-files` checks configuration parsing and step planning only.

Optional generic sidecars include variant/ClinVar VCFs and bedMethyl tracks. Explicit paths take precedence over legacy `wf-human-variation` discovery. An omitted optional input produces module-specific status or `NA` fields; an explicitly configured path that does not exist fails strict preflight. See [`examples/configs/standalone_bam.env`](examples/configs/standalone_bam.env) and the [configuration schema](resources/schemas/mito_overview_config.schema.yaml).

## Output contract

Each completed run writes a structured working directory under `WORK_ROOT/RUN_NAME`:

```text
RUN_NAME/
├── stage/
│   ├── run_context.tsv
│   └── run_context.json
├── output/
│   ├── subset/    # extracted mtDNA BAM, index, and BED interval
│   ├── methylation/ # localized optional methylation inputs
│   ├── summary/   # machine-readable TSV tables
│   ├── figures/   # report-native PNG figures
│   └── report/    # 14 numbered HTML pages
├── logs/          # step completion and execution records
└── tmp/           # temporary workflow products
```

The final sync step creates `FINAL_BIOINFO_DIR`, or `WORK_ROOT/RUN_NAME_final` when no explicit destination is supplied. That handoff bundle contains the complete `output/` and `logs/` trees, `mito.bam`, `mito.bam.bai`, `config.env.snapshot`, and `sync_manifest.tsv`.

The numbered report pattern is stable:

| Page | Analysis |
| ---: | --- |
| 01 | mtDNA QC |
| 02 | Candidate alternate alleles |
| 03 | CIGAR-deletion structural screen |
| 04 | Experimental mt:nuclear depth ratio |
| 05 | mtDNA feature annotation |
| 06 | Same-read co-occurrence |
| 07 | Gene summary |
| 08 | Alignment-ambiguity QC |
| 09 | Identity QC |
| 10 | Variant consequence |
| 11 | Circularity QC |
| 12 | Exploratory methylation |
| 13 | Optional Phy-Mer-style haplogroup enrichment |
| 14 | Optional mvTool-style annotation enrichment |

Every layer records one of the common states: `ok`, `not_configured`, `not_applicable`, `not_evaluable`, `unavailable`, or `failed`. A prescribed non-`ok` state can be the scientifically correct outcome, for example `not_applicable` copy-number reporting for a targeted-mt assay or `not_configured` methylation when no bedMethyl track was supplied.

## Report examples

The following report-native panels were generated from the fixed GM12878 reduced ONT input in the `v0.3.1` evidence bundle. They show depth, observed alternate-allele fractions, selected-site read co-occurrence, and alignment span-versus-MAPQ QC.

[![MitoOverview report-native views](https://raw.githubusercontent.com/elissonnog/mito-overview/v0.3.1/paper/figures/figure0_workflow_architecture.png)](https://raw.githubusercontent.com/elissonnog/mito-overview/v0.3.1/paper/figures/figure0_workflow_architecture.png)

The complementary short-read asset pack contains a report montage from pooled public GM11906 single-cell ATAC-seq libraries:

[![GM11906 short-read report montage](examples/public_validation/GM11906_MERRF_shortread/figures/GM11906_MERRF_shortread_montage.png)](examples/public_validation/GM11906_MERRF_shortread/figures/GM11906_MERRF_shortread_montage.png)

## Validation evidence

Release qualification reconstructed derivatives from seven identity-checked public FASTQs on macOS and Ubuntu. The `v0.3.1` validation packet records fixed inputs, commands, environments, module states, normalized outputs, and hashes. Required gates included:

- four synthetic/standalone workflow modes
- eight public-data executions across lenient, default, strict, and repeat profiles
- `36/36` release-validation cases
- `366/366` scientific-oracle assertions
- cross-platform agreement for `202/202` normalized scientific tables and `4/4` visual-structure comparisons
- zero network-canary events during offline validation

These results establish fixed-input execution and repeatability under the specified environments. They do not estimate sensitivity, specificity, limit of detection, deletion accuracy, modality equivalence, or population-level generalizability.

### Public proof-of-principle results

The long-read example uses a deterministic 1,000-query-name subset of GM12878 ONT targeted-mt data ([Vandiver et al., 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9399971/); `SRR18110025`). Candidate screening used `MIN_CALLABLE_DEPTH=100` and `MIN_ALT_ALLELE_FRACTION=0.10` across all three quality-filter profiles.

The short-read example pools three public GM11906 single-cell ATAC-seq libraries from one lymphoblastoid line ([Lareau et al., 2021](https://www.nature.com/articles/s41587-020-0645-6)); it is not a short-read WGS cohort. Candidate screening used `MIN_CALLABLE_DEPTH=10` and `MIN_ALT_ALLELE_FRACTION=0.20` across all three quality-filter profiles.

| Dataset and filter profile | BaseQ/MAPQ/readQ | Candidate sites | Accepted observations | Excluded observations |
| --- | --- | ---: | ---: | ---: |
| GM12878 lenient | `0/0/0` | 32 | 8,278,969 | 911,659 |
| GM12878 default | `13/20/10` | 16 | 7,143,152 | 2,047,476 |
| GM12878 strict | `20/30/15` | 15 | 6,046,355 | 3,144,273 |
| GM11906 lenient | `0/0/0` | 33 | 44,048,838 | 7,296,932 |
| GM11906 default | `13/20/10` | 33 | 44,048,838 | 7,296,932 |
| GM11906 strict | `20/30/15` | 33 | 42,675,832 | 8,669,938 |

In the default GM11906 run, the known public `m.8344A>G` marker was represented at callable depth `1,027`, with `740` alternate observations, forward/reverse support `305/435`, observed alternate allele fraction `0.720545`, and `MT-TK` / `tRNA_variant` annotation. The pooled fraction is weighted by passing observations from three libraries with unequal callable depth; it is not an equal-weight per-cell value. This demonstrates representation of that marker under the fixed workflow inputs, not diagnostic sensitivity, pathogenicity classification, or a calibrated sample heteroplasmy estimate.

The GM12878 targeted-mt run correctly reported the mt:nuclear depth ratio and Phy-Mer as `not_applicable`, mvTool and methylation as `not_configured`, and NUMT interpretation as `not_evaluable` under `reference_scope_mt_only`.

Evidence and methods:

- [GitHub release](https://github.com/elissonnog/mito-overview/releases/tag/v0.3.1)
- [Validation report (PDF)](https://github.com/elissonnog/mito-overview/releases/download/v0.3.1/MitoOverview_v0.3.1_release_validation_report.pdf)
- [Validation packet](https://github.com/elissonnog/mito-overview/releases/download/v0.3.1/mito-overview-v0.3.1-validation.zip)
- [Public long-read protocol](docs/validation_public_longread.md)
- [Public short-read protocol](docs/validation_public_shortread.md)

## Limitations

- MitoOverview is a research reporting workflow, not a diagnostic test.
- Candidate allele fractions depend on alignment, sequencing chemistry, filters, depth, and assay design.
- The deletion module is a CIGAR-based structural screen and has not been benchmarked as a clinical deletion caller.
- The mt:nuclear metric is a within-sample depth ratio and must not be interpreted as absolute mtDNA copies per diploid cell.
- Alignment-ambiguity metrics are warning-oriented. An mt-only reference cannot support categorical NUMT interpretation.
- Methylation outputs are exploratory and require compatible modification-aware inputs.
- Short-read support demonstrates workflow compatibility for applicable layers, not equivalence with long-read sequencing.
- Phy-Mer and mvTool-style integrations are optional, human-oriented secondary layers. mvTool network access is disabled by default.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing FASTA index | Run `samtools faidx reference.fa` and confirm `reference.fa.fai` exists |
| Missing alignment index | Run `samtools index alignment.bam` or provide the corresponding CRAM `.crai` |
| Mitochondrial contig not found | Compare `MT_CONTIG` with `samtools faidx reference.fa` and `samtools view -H alignment.bam` |
| CRAM reference error | Use the same sequence-compatible FASTA used to create the CRAM |
| Output directory already exists | Choose a new `RUN_NAME`; existing runs are not overwritten |
| Optional page is status-only | Check its status and reason code, then configure the required sidecar only if that analysis is intended |
| Placeholder example fails strict preflight | Use `examples/configs/standalone_bam.env` and replace all six required paths/identifiers |

For configuration and module details, see [`docs/overview.md`](docs/overview.md), [`docs/methodology.md`](docs/methodology.md), and [`docs/inputs_outputs.md`](docs/inputs_outputs.md). Related mtDNA software and the intended complementary scope of MitoOverview are summarized in [`docs/related_software_landscape.md`](docs/related_software_landscape.md).

## Citation

Citation metadata for the software are maintained in [`CITATION.cff`](CITATION.cff). The [version-bound free-format manuscript draft](https://github.com/elissonnog/mito-overview/blob/v0.3.1/paper/preprint_draft.md) is available for collaborator review; its formal citation will be added here when the preprint is publicly posted.

```text
Lopes E, Gai X. MitoOverview: a mode-gated mitochondrial DNA reporting workflow. Version 0.3.1. Medical College of Wisconsin.
```

## Contributing and license

Issue reports and contributions are welcome through [`CONTRIBUTING.md`](CONTRIBUTING.md). Please include the software version, read/assay profile, sanitized configuration, command, and relevant status/reason codes when reporting a problem.

MitoOverview is distributed under the [MIT License](LICENSE). External Phy-Mer code and mvTool data are not redistributed; see [`docs/license_notes.md`](docs/license_notes.md).
