"""Shared, auditable allele-observation counting for mtDNA report steps."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Iterator

import pysam


CANONICAL_BASES = ("A", "C", "G", "T")
UNLIMITED_PILEUP_DEPTH = 1_000_000_000


@dataclass(frozen=True)
class AlleleFilterPolicy:
    """Read and base filters applied consistently across allele-aware steps."""

    min_base_quality: int = 13
    min_mapping_quality: int = 20
    min_read_mean_quality: float = 10.0
    max_depth: int = 0
    exclude_flags: int = 3844
    ignore_overlaps: bool = True


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


@dataclass(frozen=True)
class AlleleObservation:
    """One passing base observation at a reference position."""

    read_name: str
    base: str
    base_quality: int
    mapping_quality: int
    is_reverse: bool


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
        {"metric": "allele_counting_method", "value": "pysam_pileup_shared_filter_v1"},
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
            )
        )

    if policy.ignore_overlaps:
        best_by_read: dict[str, AlleleObservation] = {}
        for observation in observations:
            current = best_by_read.get(observation.read_name)
            if current is None or (observation.base_quality, observation.mapping_quality) > (
                current.base_quality,
                current.mapping_quality,
            ):
                best_by_read[observation.read_name] = observation
        stats.excluded_overlap += len(observations) - len(best_by_read)
        if len(observations) != len(best_by_read):
            seen_names: set[str] = set()
            duplicated_names: set[str] = set()
            for item in observations:
                if item.read_name in seen_names:
                    duplicated_names.add(item.read_name)
                else:
                    seen_names.add(item.read_name)
            read_sets["overlap"].update(duplicated_names)
        observations = list(best_by_read.values())

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

    effective_max_depth = policy.max_depth if policy.max_depth > 0 else UNLIMITED_PILEUP_DEPTH
    mean_quality_cache: dict[tuple[str, int, int], float | None] = {}
    read_sets = {
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
        )
    }
    with pysam.AlignmentFile(str(bam_path), "rb") as bam:
        for column in bam.pileup(
            contig,
            start,
            end,
            truncate=True,
            stepper="all",
            min_base_quality=0,
            min_mapping_quality=0,
            max_depth=effective_max_depth,
            flag_filter=0,
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
    _finalize_stats(stats, read_sets)


def count_contig_alleles(
    *,
    bam_path: str | Path,
    contig: str,
    length: int,
    policy: AlleleFilterPolicy,
) -> AlleleCountingResult:
    """Count canonical observations and strands across a compact contig."""

    base_counts = [{base: 0 for base in CANONICAL_BASES} for _ in range(length)]
    forward_counts = [{base: 0 for base in CANONICAL_BASES} for _ in range(length)]
    reverse_counts = [{base: 0 for base in CANONICAL_BASES} for _ in range(length)]
    stats = AlleleFilterStats()
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
    return AlleleCountingResult(base_counts, forward_counts, reverse_counts, stats)


def collect_site_read_calls(
    *,
    bam_path: str | Path,
    contig: str,
    sites: dict[int, str],
    policy: AlleleFilterPolicy,
) -> tuple[dict[int, set[str]], dict[int, set[str]], AlleleFilterStats]:
    """Collect passing covered and alternate-read names at one-based sites."""

    coverage = {position: set() for position in sites}
    alternate = {position: set() for position in sites}
    stats = AlleleFilterStats()
    if not sites:
        return coverage, alternate, stats
    min_position = min(sites)
    max_position = max(sites)
    for reference_pos, observations in iter_filtered_columns(
        bam_path=bam_path,
        contig=contig,
        start=min_position - 1,
        end=max_position,
        policy=policy,
        stats=stats,
    ):
        position = reference_pos + 1
        if position not in sites:
            continue
        alt_base = sites[position].upper()
        for observation in observations:
            coverage[position].add(observation.read_name)
            if observation.base == alt_base:
                alternate[position].add(observation.read_name)
    return coverage, alternate, stats
