# Annotation resources

`human_mt_reference.gtf` is a compact human mitochondrial annotation resource bundled for the public `mito-overview` package.

`NC_012920.1.fa` is a bundled human mitochondrial reference sequence used by the short-read public validation path.

Current contents:
- canonical mitochondrial genes on `MT`
- matching duplicate entries for `NC_012920.1`
- gene and CDS rows for protein-coding loci
- gene rows for rRNA and tRNA loci
- mitochondrial reference FASTA with contig name `NC_012920.1`

Coordinate source:
- NCBI RefSeq record `NC_012920.1` feature table, fetched on 2026-04-21

Purpose:
- portable public-core mitochondrial feature annotation
- short-read and long-read human mtDNA example configurations
- avoidance of large external genome-annotation dependencies for the mtDNA-only reporting layers
