from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mito_overview.allele_counting import (
    AlleleFilterPolicy,
    collect_site_read_calls,
    count_contig_alleles,
)
from mito_overview.steps.mito_heteroplasmy import run_step

from ._helpers import ReadSpec, metric_map, write_alignment, write_fasta


@pytest.fixture(scope="module")
def high_depth_case(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("allele-counting")
    ref = write_fasta(root / "mt.fa", {"MT": "A" * 12})
    reads = [
        *(ReadSpec(f"ref_{index:05d}", "MT", 0, "A") for index in range(5000)),
        *(ReadSpec(f"alt_f_{index:05d}", "MT", 0, "C") for index in range(1500)),
        *(ReadSpec(f"alt_r_{index:05d}", "MT", 0, "C", flag=16) for index in range(1501)),
        ReadSpec("overlap_pair", "MT", 0, "A", flag=65, qualities=(35,)),
        ReadSpec("overlap_pair", "MT", 0, "C", flag=129, qualities=(30,)),
        ReadSpec("low_baseq", "MT", 0, "A", qualities=(12,)),
        ReadSpec("low_mapq", "MT", 0, "A", mapping_quality=19),
        ReadSpec("low_readq", "MT", 0, "A" * 10, qualities=(40, 0, 0, 0, 0, 0, 0, 0, 0, 0)),
        ReadSpec("duplicate", "MT", 0, "A", flag=1024),
        ReadSpec("secondary", "MT", 0, "A", flag=256),
        ReadSpec("supplementary", "MT", 0, "A", flag=2048),
        ReadSpec("qcfail", "MT", 0, "A", flag=512),
        ReadSpec("noncanonical", "MT", 0, "N"),
        ReadSpec("deletion", "MT", 1, "AA", cigar=((0, 1), (2, 1), (0, 1))),
    ]
    bam = write_alignment(root / "high_depth.bam", {"MT": 12}, reads)
    return ref, bam


def test_unlimited_depth_filters_and_strand_invariants(high_depth_case: tuple[Path, Path]) -> None:
    _, bam = high_depth_case
    policy = AlleleFilterPolicy()
    progress: list[tuple[int, int, int]] = []
    result = count_contig_alleles(
        bam_path=bam,
        contig="MT",
        length=12,
        policy=policy,
        progress_callback=lambda position, length, stats: progress.append(
            (position, length, stats.accepted_observations)
        ),
        progress_interval=4,
    )

    position = result.base_counts[0]
    assert sum(position.values()) == 8002
    assert position == {"A": 5001, "C": 3001, "G": 0, "T": 0}
    assert result.forward_counts[0]["C"] == 1500
    assert result.reverse_counts[0]["C"] == 1501
    assert position["C"] == result.forward_counts[0]["C"] + result.reverse_counts[0]["C"]
    assert result.stats.accepted_observations > 8000
    assert result.stats.pileup_observations_seen == (
        result.stats.accepted_observations + result.stats.excluded_observations
    )
    assert result.stats.excluded_flag == 4
    assert result.stats.excluded_mapping_quality >= 1
    assert result.stats.excluded_read_quality >= 1
    assert result.stats.excluded_base_quality >= 1
    assert result.stats.excluded_noncanonical_base >= 1
    assert result.stats.excluded_deletion_or_refskip >= 1
    assert result.stats.excluded_overlap == 1
    assert result.stats.unique_reads_with_any_exclusion == 10
    assert progress[-1] == (12, 12, 8004)


def test_cosegregation_read_sets_match_candidate_observations(high_depth_case: tuple[Path, Path]) -> None:
    _, bam = high_depth_case
    policy = AlleleFilterPolicy()
    coverage, alternate, stats = collect_site_read_calls(
        bam_path=bam,
        contig="MT",
        sites={1: "C"},
        policy=policy,
    )
    assert len(coverage[1]) == 8002
    assert len(alternate[1]) == 3001
    assert stats.accepted_observations == 8002


def test_cosegregation_counts_only_selected_sites_with_shared_filters(tmp_path: Path) -> None:
    bam = write_alignment(
        tmp_path / "selected_sites.bam",
        {"MT": 10},
        [
            ReadSpec("passing", "MT", 0, "ACCCCCCCCA"),
            ReadSpec("duplicate", "MT", 0, "ACCCCCCCCA", flag=1024),
        ],
    )
    coverage, alternate, stats = collect_site_read_calls(
        bam_path=bam,
        contig="MT",
        sites={1: "A", 10: "A"},
        policy=AlleleFilterPolicy(),
    )
    assert coverage == {1: {"passing"}, 10: {"passing"}}
    assert alternate == coverage
    assert stats.accepted_observations == 2
    assert stats.excluded_flag == 2
    assert stats.pileup_observations_seen == 4
    assert stats.unique_reads_seen == 2
    assert stats.unique_reads_accepted == 1


def test_heteroplasmy_outputs_canonical_fraction_and_compatibility_alias(
    high_depth_case: tuple[Path, Path], tmp_path: Path
) -> None:
    ref, bam = high_depth_case
    outputs = run_step(
        bam=bam,
        ref_fasta=ref,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="TOY-HIGH-DEPTH",
        mt_contig="MT",
        mt_length=12,
        min_depth=1,
        min_vaf=0.01,
    )
    all_sites = pd.read_csv(outputs["all_sites_path"], sep="\t")
    row = all_sites.loc[all_sites["position"] == 1].iloc[0]
    assert int(row["callable_depth"]) == int(row[["A", "C", "G", "T"]].sum()) == 8002
    assert int(row["alt_count"]) == int(row["alt_forward"] + row["alt_reverse"]) == 3001
    assert row["alt_allele_fraction"] == pytest.approx(3001 / 8002, abs=5e-7)
    assert row["heteroplasmy_fraction"] == row["alt_allele_fraction"]
    summary = metric_map(outputs["summary_path"])
    assert summary["allele_max_depth"] == "0"
    assert summary["allele_exclude_flags"] == "3844"
    assert int(summary["accepted_observations"]) > 8000


def test_configured_depth_cap_is_deterministic_and_fully_accounted(tmp_path: Path) -> None:
    bam = write_alignment(
        tmp_path / "cap.bam",
        {"MT": 1},
        [ReadSpec(f"read-{index:02d}", "MT", 0, "A") for index in range(20)],
    )
    result = count_contig_alleles(
        bam_path=bam,
        contig="MT",
        length=1,
        policy=AlleleFilterPolicy(max_depth=5),
    )
    assert sum(result.base_counts[0].values()) == 5
    assert result.stats.pileup_observations_seen == 20
    assert result.stats.accepted_observations == 5
    assert result.stats.excluded_max_depth == 15
    assert result.stats.excluded_observations == 15


def test_flagged_alignment_observations_are_precounted_exactly(tmp_path: Path) -> None:
    bam = write_alignment(
        tmp_path / "flagged.bam",
        {"MT": 10},
        [
            ReadSpec("primary", "MT", 0, "A" * 10),
            ReadSpec("supplementary", "MT", 0, "A" * 8, flag=2048, cigar=((0, 4), (2, 2), (0, 4))),
        ],
    )
    result = count_contig_alleles(
        bam_path=bam,
        contig="MT",
        length=10,
        policy=AlleleFilterPolicy(),
    )
    assert result.stats.accepted_observations == 10
    assert result.stats.excluded_flag == 10
    assert result.stats.pileup_observations_seen == 20
    assert result.stats.excluded_observations == 10
    assert result.stats.unique_reads_excluded_flag == 1


def test_coordinate_placed_unmapped_record_is_not_precounted(tmp_path: Path) -> None:
    bam = write_alignment(
        tmp_path / "placed_unmapped.bam",
        {"MT": 4},
        [
            ReadSpec("primary", "MT", 0, "A" * 4),
            ReadSpec("placed_unmapped", "MT", 0, "A" * 4, flag=4),
        ],
    )
    result = count_contig_alleles(
        bam_path=bam,
        contig="MT",
        length=4,
        policy=AlleleFilterPolicy(),
    )
    assert result.stats.accepted_observations == 4
    assert result.stats.pileup_observations_seen == 4
    assert result.stats.excluded_flag == 0
    assert result.stats.unique_reads_seen == 1
    assert result.stats.unique_reads_excluded_flag == 0


def test_all_reference_positions_have_no_fabricated_alternate_candidate(tmp_path: Path) -> None:
    ref = write_fasta(tmp_path / "reference.fa", {"MT": "AAAA"})
    bam = write_alignment(
        tmp_path / "reference.bam",
        {"MT": 4},
        [ReadSpec(f"ref-{index}", "MT", 0, "AAAA") for index in range(4)],
    )
    outputs = run_step(
        bam=bam,
        ref_fasta=ref,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="ALL-REF",
        mt_contig="MT",
        mt_length=4,
        min_depth=0,
        min_vaf=0.0,
    )
    all_sites = pd.read_csv(outputs["all_sites_path"], sep="\t", dtype=str)
    candidates = pd.read_csv(outputs["candidate_path"], sep="\t", dtype=str)
    assert set(all_sites["alt_base"]) == {"."}
    assert set(all_sites["alt_count"]) == {"0"}
    assert candidates.empty
