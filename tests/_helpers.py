from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pysam


@dataclass(frozen=True)
class ReadSpec:
    name: str
    contig: str
    start: int
    sequence: str
    flag: int = 0
    mapping_quality: int = 60
    qualities: tuple[int, ...] | None = None
    cigar: tuple[tuple[int, int], ...] | None = None


def write_fasta(path: Path, contigs: dict[str, str]) -> Path:
    path.write_text(
        "".join(f">{name}\n{sequence}\n" for name, sequence in contigs.items()),
        encoding="ascii",
    )
    pysam.faidx(str(path))
    return path


def write_alignment(
    path: Path,
    contigs: dict[str, int],
    reads: list[ReadSpec],
    *,
    reference_fasta: Path | None = None,
) -> Path:
    header = pysam.AlignmentHeader.from_references(list(contigs), list(contigs.values()))
    contig_order = {name: index for index, name in enumerate(contigs)}
    ordered_reads = sorted(reads, key=lambda read: (contig_order.get(read.contig, 10**9), read.start, read.name, read.flag))
    mode = "wc" if path.suffix == ".cram" else "wb"
    kwargs = {"reference_filename": str(reference_fasta)} if mode == "wc" else {}
    with pysam.AlignmentFile(str(path), mode, header=header, **kwargs) as handle:
        for spec in ordered_reads:
            segment = pysam.AlignedSegment(header)
            segment.query_name = spec.name
            segment.flag = spec.flag
            segment.reference_id = contig_order[spec.contig]
            segment.reference_start = spec.start
            segment.mapping_quality = spec.mapping_quality
            segment.query_sequence = spec.sequence
            segment.cigartuples = list(spec.cigar or ((0, len(spec.sequence)),))
            qualities = spec.qualities or tuple([40] * len(spec.sequence))
            segment.query_qualities = list(qualities)
            handle.write(segment)
    pysam.index(str(path))
    return path


def bam_from_sam(sam_path: Path, bam_path: Path) -> Path:
    """Convert a coordinate-sorted tracked SAM fixture to indexed BAM."""

    pysam.view("-bS", "-o", str(bam_path), str(sam_path), catch_stdout=False)
    pysam.index(str(bam_path))
    return bam_path


def metric_map(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        fields = line.split("\t", 1)
        if len(fields) == 2:
            rows[fields[0]] = fields[1]
    return rows
