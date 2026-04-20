# TOY-001

`TOY-001` is a synthetic mitochondrial input set for installation checks and public example generation.

## Files
- `tiny_GRCh38.fa`: minimal mitochondrial reference
- `tiny.sam`: toy read alignments against the miniature reference
- `mods.tsv`: small bedmethyl-like table used to generate synthetic methylation tracks
- `phased_snps.vcf`: phased toy mitochondrial variants
- `np_snps.vcf`: non-phased toy mitochondrial variants
- `np_clinvar.vcf`: toy ClinVar-like VCF used by the public-core consequence page
- `tiny_mt.gtf`: minimal mitochondrial annotation

## Intended use
These files are consumed by:
- `scripts/build_public_example_bundle.sh`
- `tests/smoke_public_pipeline.sh`
