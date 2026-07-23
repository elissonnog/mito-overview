"""Shared, auditable allele-observation counting for mtDNA report steps."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Callable, Iterator

import pysam


CANONICAL_BASES = ("A", "C", "G", "T")
UNLIMITED_PILEUP_DEPTH = 1_000_000_000
ALLELE_COUNTING_METHOD = "pysam_pileup_shared_filter_v2"
OVERLAP_RESOLUTION_METHOD = (
    "highest_baseq_mapq_discordant_ties_excluded_concordant_read1_first"
)
OVERLAP_STRAND_CONVENTION = "representative_fragment_read1_then_read2_then_alignment_key"


@dataclass(frozen=True)
class AlleleFilterPolicy:
    """Read and base filters applied consistently across allele-aware steps."""

    min_base_quality: int = 13
    min_mapping_quality: int = 20
    min_read_mean_quality: float = 10.0
    max_depth: int = 0
    exclude_flags: int = 3844
    ignore_overlaps: bool = True

    def __post_init__(self) -> None:
        for label, value in (
            ("min_base_quality", self.min_base_quality),
            ("min_mapping_quality", self.min_mapping_quality),
            ("max_depth", self.max_depth),
            ("exclude_flags", self.exclude_flags),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{label} must be a nonnegative integer")
        if not math.isfinite(self.min_read_mean_quality) or self.min_read_mean_quality < 0:
            raise ValueError("min_read_mean_quality must be finite and nonnegative")


@dataclass
class AlleleFilterStats:
    """Observation-level exclusion counts for provenance and testing."""

    pileup_observations_seen: int = 0
    accepted_observations: int = 0
    excluded_observations: int = 0
    excluded_flag: int = 0
    excluded_mapping_quality: int = 0
    excluded_read_quality: int = 0
    excluded_missing_read_quality: int = 0
    excluded_base_quality: int = 0
    excluded_deletion_or_refskip: int = 0
    excluded_missing_base: int = 0
    excluded_noncanonical_base: int = 0
    excluded_overlap: int = 0
    excluded_overlap_ambiguous: int = 0
    excluded_max_depth: int = 0
    unique_reads_seen: int = 0
    unique_reads_accepted: int = 0
    unique_reads_with_any_exclusion: int = 0
    unique_reads_excluded_flag: int = 0
    unique_reads_excluded_mapping_quality: int = 0
    unique_reads_excluded_read_quality: int = 0
    unique_reads_excluded_missing_read_quality: int = 0
    unique_reads_excluded_base_quality: int = 0
    unique_reads_excluded_deletion_or_refskip: int = 0
    unique_reads_excluded_missing_base: int = 0
    unique_reads_excluded_noncanonical_base: int = 0
    unique_reads_excluded_overlap: int = 0
    unique_reads_excluded_overlap_ambiguous: int = 0
    unique_reads_excluded_max_depth: int = 0


@dataclass(frozen=True)
class AlleleObservation:
    """One passing base observation at a reference position."""

    read_name: str
    base: str
    base_quality: int
    mapping_quality: int
    is_reverse: bool
    pair_order: int
    alignment_support_key: str


@dataclass
class AlleleCountingResult:
    """Per-position base and strand counts plus filter provenance."""

    base_counts: list[dict[str, int]]
    forward_counts: list[dict[str, int]]
    reverse_counts: list[dict[str, int]]
    stats: AlleleFilterStats


def policy_rows(policy: AlleleFilterPolicy, stats: AlleleFilterStats) -> list[dict[str, object]]:
    """Return metric/value rows suitable for a step summary table."""

    rows = [
        {"metric": "allele_counting_method", "value": ALLELE_COUNTING_METHOD},
        {"metric": "allele_overlap_resolution", "value": OVERLAP_RESOLUTION_METHOD},
        {"metric": "allele_overlap_strand_convention", "value": OVERLAP_STRAND_CONVENTION},
        {"metric": "allele_min_base_quality", "value": policy.min_base_quality},
        {"metric": "allele_min_mapping_quality", "value": policy.min_mapping_quality},
        {"metric": "allele_min_read_mean_quality", "value": policy.min_read_mean_quality},
        {"metric": "allele_max_depth", "value": policy.max_depth},
        {"metric": "allele_exclude_flags", "value": policy.exclude_flags},
        {"metric": "allele_ignore_overlaps", "value": int(policy.ignore_overlaps)},
    ]
    rows.extend({"metric": key, "value": value} for key, value in asdict(stats).items())
    return rows


def _read_mean_quality(alignment: pysam.AlignedSegment) -> float | None:
    qualities = alignment.query_qualities
    if qualities is None or len(qualities) == 0:
        return None
    return float(fmean(qualities))


def _alignment_support_key(alignment: pysam.AlignedSegment) -> str:
    """Return a stable key that distinguishes paired or split alignment records."""

    fields = (
        alignment.query_name,
        alignment.flag,
        alignment.reference_id,
        alignment.reference_start,
        alignment.reference_end,
        alignment.next_reference_id,
        alignment.next_reference_start,
        alignment.template_length,
        alignment.cigarstring or "",
    )
    return "\x1f".join(str(value) for value in fields)


def _resolve_overlapping_observations(
    observations: list[AlleleObservation],
    stats: AlleleFilterStats,
    read_sets: dict[str, set[str]],
) -> list[AlleleObservation]:
    """Resolve same-query observations without depending on BAM record order."""

    grouped: dict[str, list[AlleleObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.read_name, []).append(observation)

    resolved: list[AlleleObservation] = []
    for read_name in sorted(grouped):
        group = grouped[read_name]
        if len(group) == 1:
            resolved.append(group[0])
            continue

        read_sets["overlap"].add(read_name)
        best_score = max(
            (observation.base_quality, observation.mapping_quality)
            for observation in group
        )
        best = [
            observation
            for observation in group
            if (observation.base_quality, observation.mapping_quality) == best_score
        ]
        if len({observation.base for observation in best}) > 1:
            stats.excluded_overlap += len(group)
            stats.excluded_overlap_ambiguous += len(group)
            read_sets["overlap_ambiguous"].add(read_name)
            continue

        # A concordant quality tie cannot change the allele count. Represent a
        # paired fragment by read 1 when available instead of favoring one
        # genomic strand; use the stable alignment key for any remaining tie.
        winner = min(
            best,
            key=lambda observation: (
                observation.pair_order,
                observation.alignment_support_key,
            ),
        )
        resolved.append(winner)
        stats.excluded_overlap += len(group) - 1
    return resolved


def _passing_observations(
    pileups: list[pysam.PileupRead],
    policy: AlleleFilterPolicy,
    stats: AlleleFilterStats,
    mean_quality_cache: dict[tuple[str, int, int], float | None],
    read_sets: dict[str, set[str]],
) -> list[AlleleObservation]:
    observations: list[AlleleObservation] = []
    for pileup_read in pileups:
        stats.pileup_observations_seen += 1
        alignment = pileup_read.alignment
        read_name = alignment.query_name
        read_sets["seen"].add(read_name)
        if alignment.flag & policy.exclude_flags:
            stats.excluded_flag += 1
            read_sets["flag"].add(read_name)
            continue
        if alignment.mapping_quality < policy.min_mapping_quality:
            stats.excluded_mapping_quality += 1
            read_sets["mapping_quality"].add(read_name)
            continue
        if pileup_read.is_del or pileup_read.is_refskip:
            stats.excluded_deletion_or_refskip += 1
            read_sets["deletion_or_refskip"].add(read_name)
            continue
        query_position = pileup_read.query_position
        if query_position is None or alignment.query_sequence is None:
            stats.excluded_missing_base += 1
            read_sets["missing_base"].add(read_name)
            continue

        cache_key = (alignment.query_name, alignment.flag, alignment.reference_start)
        if cache_key not in mean_quality_cache:
            mean_quality_cache[cache_key] = _read_mean_quality(alignment)
        read_mean_quality = mean_quality_cache[cache_key]
        if read_mean_quality is None:
            if policy.min_read_mean_quality > 0:
                stats.excluded_missing_read_quality += 1
                read_sets["missing_read_quality"].add(read_name)
                continue
        elif read_mean_quality < policy.min_read_mean_quality:
            stats.excluded_read_quality += 1
            read_sets["read_quality"].add(read_name)
            continue

        qualities = alignment.query_qualities
        base_quality = int(qualities[query_position]) if qualities is not None else 0
        if base_quality < policy.min_base_quality:
            stats.excluded_base_quality += 1
            read_sets["base_quality"].add(read_name)
            continue
        base = alignment.query_sequence[query_position].upper()
        if base not in CANONICAL_BASES:
            stats.excluded_noncanonical_base += 1
            read_sets["noncanonical_base"].add(read_name)
            continue
        observations.append(
            AlleleObservation(
                read_name=alignment.query_name,
                base=base,
                base_quality=base_quality,
                mapping_quality=int(alignment.mapping_quality),
                is_reverse=bool(alignment.is_reverse),
                pair_order=0 if alignment.is_read1 else 1 if alignment.is_read2 else 2,
                alignment_support_key=_alignment_support_key(alignment),
            )
        )

    if policy.ignore_overlaps:
        observations = _resolve_overlapping_observations(observations, stats, read_sets)

    if policy.max_depth > 0 and len(observations) > policy.max_depth:
        observations.sort(
            key=lambda item: (
                -item.base_quality,
                -item.mapping_quality,
                item.read_name,
                item.base,
                item.is_reverse,
            )
        )
        excluded = observations[policy.max_depth :]
        stats.excluded_max_depth += len(excluded)
        read_sets["max_depth"].update(item.read_name for item in excluded)
        observations = observations[: policy.max_depth]

    stats.accepted_observations += len(observations)
    read_sets["accepted"].update(observation.read_name for observation in observations)
    return observations


def _finalize_stats(stats: AlleleFilterStats, read_sets: dict[str, set[str]]) -> None:
    """Populate aggregate observation and unique-read provenance fields."""

    exclusion_keys = (
        "flag",
        "mapping_quality",
        "read_quality",
        "missing_read_quality",
        "base_quality",
        "deletion_or_refskip",
        "missing_base",
        "noncanonical_base",
        "overlap",
        "max_depth",
    )
    excluded_reads = set().union(*(read_sets[key] for key in exclusion_keys))
    reason_total = (
        stats.excluded_flag
        + stats.excluded_mapping_quality
        + stats.excluded_read_quality
        + stats.excluded_missing_read_quality
        + stats.excluded_base_quality
        + stats.excluded_deletion_or_refskip
        + stats.excluded_missing_base
        + stats.excluded_noncanonical_base
        + stats.excluded_overlap
        + stats.excluded_max_depth
    )
    if stats.pileup_observations_seen != stats.accepted_observations + reason_total:
        raise RuntimeError("Allele observation accounting invariant failed")
    stats.excluded_observations = reason_total
    stats.unique_reads_seen = len(read_sets["seen"])
    stats.unique_reads_accepted = len(read_sets["accepted"])
    stats.unique_reads_with_any_exclusion = len(excluded_reads)
    stats.unique_reads_excluded_flag = len(read_sets["flag"])
    stats.unique_reads_excluded_mapping_quality = len(read_sets["mapping_quality"])
    stats.unique_reads_excluded_read_quality = len(read_sets["read_quality"])
    stats.unique_reads_excluded_missing_read_quality = len(read_sets["missing_read_quality"])
    stats.unique_reads_excluded_base_quality = len(read_sets["base_quality"])
    stats.unique_reads_excluded_deletion_or_refskip = len(read_sets["deletion_or_refskip"])
    stats.unique_reads_excluded_missing_base = len(read_sets["missing_base"])
    stats.unique_reads_excluded_noncanonical_base = len(read_sets["noncanonical_base"])
    stats.unique_reads_excluded_overlap = len(read_sets["overlap"])
    stats.unique_reads_excluded_overlap_ambiguous = len(read_sets["overlap_ambiguous"])
    stats.unique_reads_excluded_max_depth = len(read_sets["max_depth"])


def _reference_overlap_from_cigar(
    alignment: pysam.AlignedSegment,
    start: int,
    end: int,
) -> int:
    """Count pileup-visible reference positions overlapping one interval."""

    reference_position = alignment.reference_start
    overlap = 0
    for operation, length in alignment.cigartuples or ():
        if operation not in {0, 2, 3, 7, 8}:
            continue
        operation_end = reference_position + length
        overlap += max(0, min(operation_end, end) - max(reference_position, start))
        reference_position = operation_end
    return overlap


def _precount_flagged_observations(
    bam: pysam.AlignmentFile,
    *,
    contig: str,
    start: int,
    end: int,
    exclude_flags: int,
    stats: AlleleFilterStats,
    read_sets: dict[str, set[str]],
) -> None:
    """Account for excluded alignments once before the filtered pileup."""

    if exclude_flags == 0:
        return
    for alignment in bam.fetch(contig, start, end):
        # HTSlib never emits unmapped records into pileup, even when they carry
        # coordinates and CIGAR data, so they must not enter the oracle count.
        if alignment.is_unmapped:
            continue
        if not alignment.flag & exclude_flags:
            continue
        excluded = _reference_overlap_from_cigar(alignment, start, end)
        if excluded == 0:
            continue
        stats.pileup_observations_seen += excluded
        stats.excluded_flag += excluded
        read_sets["seen"].add(alignment.query_name)
        read_sets["flag"].add(alignment.query_name)


def _new_read_sets() -> dict[str, set[str]]:
    return {
        key: set()
        for key in (
            "seen",
            "accepted",
            "flag",
            "mapping_quality",
            "read_quality",
            "missing_read_quality",
            "base_quality",
            "deletion_or_refskip",
            "missing_base",
            "noncanonical_base",
            "overlap",
            "overlap_ambiguous",
            "max_depth",
        )
    }


def _iter_filtered_columns_from_handle(
    *,
    bam: pysam.AlignmentFile,
    contig: str,
    start: int,
    end: int,
    policy: AlleleFilterPolicy,
    stats: AlleleFilterStats,
    mean_quality_cache: dict[tuple[str, int, int], float | None],
    read_sets: dict[str, set[str]],
) -> Iterator[tuple[int, list[AlleleObservation]]]:
    _precount_flagged_observations(
        bam,
        contig=contig,
        start=start,
        end=end,
        exclude_flags=policy.exclude_flags,
        stats=stats,
        read_sets=read_sets,
    )
    for column in bam.pileup(
        contig,
        start,
        end,
        truncate=True,
        stepper="all",
        min_base_quality=0,
        min_mapping_quality=0,
        # Apply any configured cap after all observations are visible so
        # capped observations remain part of explicit provenance.
        max_depth=UNLIMITED_PILEUP_DEPTH,
        flag_filter=policy.exclude_flags,
        ignore_overlaps=False,
    ):
        if column.reference_pos < start or column.reference_pos >= end:
            continue
        observations = _passing_observations(
            list(column.pileups),
            policy,
            stats,
            mean_quality_cache,
            read_sets,
        )
        yield int(column.reference_pos), observations


def iter_filtered_columns(
    *,
    bam_path: str | Path,
    contig: str,
    start: int,
    end: int,
    policy: AlleleFilterPolicy,
    stats: AlleleFilterStats,
) -> Iterator[tuple[int, list[AlleleObservation]]]:
    """Yield zero-based positions with observations passing one shared policy."""

    mean_quality_cache: dict[tuple[str, int, int], float | None] = {}
    read_sets = _new_read_sets()
    with pysam.AlignmentFile(str(bam_path), "rb") as bam:
        yield from _iter_filtered_columns_from_handle(
            bam=bam,
            contig=contig,
            start=start,
            end=end,
            policy=policy,
            stats=stats,
            mean_quality_cache=mean_quality_cache,
            read_sets=read_sets,
        )
    _finalize_stats(stats, read_sets)


def count_contig_alleles(
    *,
    bam_path: str | Path,
    contig: str,
    length: int,
    policy: AlleleFilterPolicy,
    progress_callback: Callable[[int, int, AlleleFilterStats], None] | None = None,
    progress_interval: int = 2000,
) -> AlleleCountingResult:
    """Count canonical observations and strands across a compact contig."""

    base_counts = [{base: 0 for base in CANONICAL_BASES} for _ in range(length)]
    forward_counts = [{base: 0 for base in CANONICAL_BASES} for _ in range(length)]
    reverse_counts = [{base: 0 for base in CANONICAL_BASES} for _ in range(length)]
    stats = AlleleFilterStats()
    next_progress_position = progress_interval if progress_interval > 0 else length + 1
    last_reported_position = 0
    for reference_pos, observations in iter_filtered_columns(
        bam_path=bam_path,
        contig=contig,
        start=0,
        end=length,
        policy=policy,
        stats=stats,
    ):
        for observation in observations:
            base_counts[reference_pos][observation.base] += 1
            strand_counts = reverse_counts if observation.is_reverse else forward_counts
            strand_counts[reference_pos][observation.base] += 1
        position = reference_pos + 1
        if progress_callback is not None and position >= next_progress_position:
            progress_callback(position, length, stats)
            last_reported_position = position
            while next_progress_position <= position:
                next_progress_position += progress_interval
    if progress_callback is not None and last_reported_position < length:
        progress_callback(length, length, stats)
    return AlleleCountingResult(base_counts, forward_counts, reverse_counts, stats)


def collect_site_read_calls(
    *,
    bam_path: str | Path,
    contig: str,
    sites: dict[int, str],
    policy: AlleleFilterPolicy,
) -> tuple[dict[int, set[str]], dict[int, set[str]], AlleleFilterStats]:
    """Collect passing covered and alternate support keys at one-based sites."""

    coverage = {position: set() for position in sites}
    alternate = {position: set() for position in sites}
    stats = AlleleFilterStats()
    if not sites:
        return coverage, alternate, stats
    mean_quality_cache: dict[tuple[str, int, int], float | None] = {}
    read_sets = _new_read_sets()
    with pysam.AlignmentFile(str(bam_path), "rb") as bam:
        for position in sorted(sites):
            for _, observations in _iter_filtered_columns_from_handle(
                bam=bam,
                contig=contig,
                start=position - 1,
                end=position,
                policy=policy,
                stats=stats,
                mean_quality_cache=mean_quality_cache,
                read_sets=read_sets,
            ):
                alt_base = sites[position].upper()
                for observation in observations:
                    support_key = (
                        observation.read_name
                        if policy.ignore_overlaps
                        else observation.alignment_support_key
                    )
                    coverage[position].add(support_key)
                    if observation.base == alt_base:
                        alternate[position].add(support_key)
    _finalize_stats(stats, read_sets)
    return coverage, alternate, stats
