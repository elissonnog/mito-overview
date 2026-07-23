from __future__ import annotations

from pathlib import Path

import pandas as pd
import pysam
import pytest

from mito_overview.allele_counting import (
    AlleleFilterPolicy,
    collect_site_read_calls,
    count_contig_alleles,
)
from mito_overview.steps import mito_heteroplasmy as heteroplasmy
from mito_overview.steps.mito_heteroplasmy import run_step

from ._helpers import ReadSpec, metric_map, write_alignment, write_fasta


def write_ordered_overlap_alignment(
    path: Path,
    records: list[tuple[int, str]],
) -> Path:
    """Write same-position paired records in the requested physical order."""

    header = pysam.AlignmentHeader.from_references(["MT"], [1])
    with pysam.AlignmentFile(path, "wb", header=header) as handle:
        for flag, base in records:
            segment = pysam.AlignedSegment(header)
            segment.query_name = "paired"
            segment.flag = flag
            segment.reference_id = 0
            segment.reference_start = 0
            segment.mapping_quality = 60
            segment.query_sequence = base
            segment.cigarstring = "1M"
            segment.query_qualities = [35]
            handle.write(segment)
    pysam.index(str(path))
    return path


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


def test_cosegregation_preserves_accepted_overlaps_when_suppression_is_disabled(
    tmp_path: Path,
) -> None:
    bam = write_alignment(
        tmp_path / "overlap_disabled.bam",
        {"MT": 1},
        [
            ReadSpec("paired", "MT", 0, "A", flag=65, qualities=(35,)),
            ReadSpec("paired", "MT", 0, "C", flag=129, qualities=(30,)),
        ],
    )
    policy = AlleleFilterPolicy(ignore_overlaps=False)
    counts = count_contig_alleles(
        bam_path=bam,
        contig="MT",
        length=1,
        policy=policy,
    )
    coverage, alternate, stats = collect_site_read_calls(
        bam_path=bam,
        contig="MT",
        sites={1: "C"},
        policy=policy,
    )

    assert sum(counts.base_counts[0].values()) == 2
    assert len(coverage[1]) == counts.stats.accepted_observations == stats.accepted_observations == 2
    assert len(alternate[1]) == counts.base_counts[0]["C"] == 1


def test_discordant_equal_quality_overlaps_are_excluded_independent_of_record_order(
    tmp_path: Path,
) -> None:
    records = [(65, "A"), (129, "C")]
    observed = []
    for index, order in enumerate((records, list(reversed(records)))):
        bam = write_ordered_overlap_alignment(tmp_path / f"discordant-{index}.bam", order)
        counts = count_contig_alleles(
            bam_path=bam,
            contig="MT",
            length=1,
            policy=AlleleFilterPolicy(),
        )
        coverage, alternate, calls_stats = collect_site_read_calls(
            bam_path=bam,
            contig="MT",
            sites={1: "C"},
            policy=AlleleFilterPolicy(),
        )
        assert counts.base_counts[0] == {"A": 0, "C": 0, "G": 0, "T": 0}
        assert coverage == {1: set()}
        assert alternate == {1: set()}
        for stats in (counts.stats, calls_stats):
            assert stats.pileup_observations_seen == 2
            assert stats.accepted_observations == 0
            assert stats.excluded_observations == 2
            assert stats.excluded_overlap == 2
            assert stats.excluded_overlap_ambiguous == 2
            assert stats.unique_reads_excluded_overlap_ambiguous == 1
        observed.append((counts.base_counts, coverage, alternate))
    assert observed[0] == observed[1]


def test_concordant_equal_quality_overlap_ties_use_read1_as_fragment_representative(
    tmp_path: Path,
) -> None:
    records = [(81, "A"), (129, "A")]
    observed = []
    for index, order in enumerate((records, list(reversed(records)))):
        bam = write_ordered_overlap_alignment(tmp_path / f"concordant-{index}.bam", order)
        result = count_contig_alleles(
            bam_path=bam,
            contig="MT",
            length=1,
            policy=AlleleFilterPolicy(),
        )
        assert result.base_counts[0]["A"] == 1
        assert result.forward_counts[0]["A"] == 0
        assert result.reverse_counts[0]["A"] == 1
        assert result.stats.accepted_observations == 1
        assert result.stats.excluded_overlap == 1
        assert result.stats.excluded_overlap_ambiguous == 0
        observed.append(
            (result.base_counts, result.forward_counts, result.reverse_counts)
        )
    assert observed[0] == observed[1]


def test_concordant_overlap_fragment_strand_tracks_read1_not_a_fixed_strand(
    tmp_path: Path,
) -> None:
    bam = write_ordered_overlap_alignment(
        tmp_path / "read1-forward.bam",
        [(65, "A"), (145, "A")],
    )
    result = count_contig_alleles(
        bam_path=bam,
        contig="MT",
        length=1,
        policy=AlleleFilterPolicy(),
    )
    assert result.base_counts[0]["A"] == 1
    assert result.forward_counts[0]["A"] == 1
    assert result.reverse_counts[0]["A"] == 0


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
    assert summary["allele_counting_method"] == "pysam_pileup_shared_filter_v2"
    assert summary["allele_overlap_resolution"] == (
        "highest_baseq_mapq_discordant_ties_excluded_concordant_read1_first"
    )
    assert summary["allele_overlap_strand_convention"] == (
        "representative_fragment_read1_then_read2_then_alignment_key"
    )
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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_read_mean_quality_policy_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        AlleleFilterPolicy(min_read_mean_quality=value)


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


def test_zero_callable_depth_has_undefined_fraction_not_observed_zero(tmp_path: Path) -> None:
    ref = write_fasta(tmp_path / "empty.fa", {"MT": "AAAA"})
    bam = write_alignment(tmp_path / "empty.bam", {"MT": 4}, [])
    outputs = run_step(
        bam=bam,
        ref_fasta=ref,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="NO-COVERAGE",
        mt_contig="MT",
        mt_length=4,
        min_depth=0,
        min_vaf=0.0,
    )

    all_sites = pd.read_csv(outputs["all_sites_path"], sep="\t")
    candidates = pd.read_csv(outputs["candidate_path"], sep="\t")
    summary = metric_map(outputs["summary_path"])

    assert outputs["status"] == "not_evaluable"
    assert (all_sites["callable_depth"] == 0).all()
    assert all_sites["alt_allele_fraction"].isna().all()
    assert all_sites["heteroplasmy_fraction"].isna().all()
    assert candidates.empty
    assert summary["status"] == "not_evaluable"
    assert summary["reason_code"] == "no_callable_positions"
    assert summary["callable_positions"] == "0"
    assert summary["uncallable_positions"] == "4"
    assert summary["max_alt_allele_fraction"] == "NA"


def test_noncanonical_reference_positions_cannot_support_zero_candidate_claim(
    tmp_path: Path,
) -> None:
    ref = write_fasta(tmp_path / "noncanonical.fa", {"MT": "NNNN"})
    bam = write_alignment(
        tmp_path / "noncanonical.bam",
        {"MT": 4},
        [ReadSpec("observed", "MT", 0, "AAAA")],
    )

    outputs = run_step(
        bam=bam,
        ref_fasta=ref,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="NONCANONICAL-REF",
        mt_contig="MT",
        mt_length=4,
        min_depth=1,
        min_vaf=0.02,
    )
    summary = metric_map(outputs["summary_path"])

    assert outputs["status"] == "not_evaluable"
    assert summary["reason_code"] == "no_canonical_reference_positions"
    assert summary["canonical_reference_positions"] == "0"
    assert summary["candidate_evaluable_positions"] == "0"
    assert summary["candidate_coverage_scope"] == "none"
    assert (
        summary["whole_mtdna_zero_candidate_interpretation_status"]
        == "not_supported_no_evaluable_positions"
    )


def test_no_position_meeting_minimum_depth_is_not_a_successful_zero_candidate_run(
    tmp_path: Path,
) -> None:
    ref = write_fasta(tmp_path / "shallow.fa", {"MT": "AAAA"})
    bam = write_alignment(
        tmp_path / "shallow.bam",
        {"MT": 4},
        [ReadSpec("shallow-reference", "MT", 0, "AAAA")],
    )
    outputs = run_step(
        bam=bam,
        ref_fasta=ref,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="SHALLOW",
        mt_contig="MT",
        mt_length=4,
        min_depth=100,
        min_vaf=0.02,
    )

    candidates = pd.read_csv(outputs["candidate_path"], sep="\t")
    summary = metric_map(outputs["summary_path"])

    assert outputs["status"] == "not_evaluable"
    assert candidates.empty
    assert summary["status"] == "not_evaluable"
    assert summary["reason_code"] == "no_positions_meet_min_callable_depth"
    assert summary["callable_positions"] == "4"
    assert summary["candidate_evaluable_positions"] == "0"
    assert summary["candidate_non_evaluable_positions"] == "4"
    assert summary["candidate_evaluable_fraction"] == "0.0"
    assert summary["candidate_coverage_scope"] == "none"
    assert (
        summary["whole_mtdna_zero_candidate_interpretation_status"]
        == "not_supported_no_evaluable_positions"
    )


def test_partial_candidate_coverage_limits_zero_candidate_interpretation_to_evaluable_positions(
    tmp_path: Path,
) -> None:
    ref = write_fasta(tmp_path / "partial.fa", {"MT": "AAAA"})
    bam = write_alignment(
        tmp_path / "partial.bam",
        {"MT": 4},
        [ReadSpec("position-one-only", "MT", 0, "A")],
    )
    outputs = run_step(
        bam=bam,
        ref_fasta=ref,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="PARTIAL-COVERAGE",
        mt_contig="MT",
        mt_length=4,
        min_depth=1,
        min_vaf=0.02,
    )

    candidates = pd.read_csv(outputs["candidate_path"], sep="\t")
    summary = metric_map(outputs["summary_path"])
    report = outputs["report_path"].read_text(encoding="utf-8")

    assert outputs["status"] == "ok"
    assert candidates.empty
    assert summary["status"] == "ok"
    assert summary["candidate_evaluable_positions"] == "1"
    assert summary["candidate_non_evaluable_positions"] == "3"
    assert summary["candidate_evaluable_fraction"] == "0.25"
    assert summary["candidate_coverage_scope"] == "partial"
    assert (
        summary["whole_mtdna_zero_candidate_interpretation_status"]
        == "not_supported_partial_candidate_coverage"
    )
    assert "No candidate sites were observed among the 1 of 4 positions" in report
    assert "must not be interpreted as a whole-mtDNA absence of candidates" in report


def test_complete_candidate_coverage_supports_threshold_specific_zero_candidate_interpretation(
    tmp_path: Path,
) -> None:
    ref = write_fasta(tmp_path / "complete.fa", {"MT": "AAAA"})
    bam = write_alignment(
        tmp_path / "complete.bam",
        {"MT": 4},
        [ReadSpec("whole-reference", "MT", 0, "AAAA")],
    )
    outputs = run_step(
        bam=bam,
        ref_fasta=ref,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="COMPLETE-COVERAGE",
        mt_contig="MT",
        mt_length=4,
        min_depth=1,
        min_vaf=0.02,
    )

    candidates = pd.read_csv(outputs["candidate_path"], sep="\t")
    summary = metric_map(outputs["summary_path"])
    report = outputs["report_path"].read_text(encoding="utf-8")

    assert outputs["status"] == "ok"
    assert candidates.empty
    assert summary["status"] == "ok"
    assert summary["candidate_evaluable_positions"] == "4"
    assert summary["candidate_non_evaluable_positions"] == "0"
    assert summary["candidate_evaluable_fraction"] == "1.0"
    assert summary["candidate_coverage_scope"] == "complete"
    assert (
        summary["whole_mtdna_zero_candidate_interpretation_status"]
        == "supported_at_configured_thresholds"
    )
    assert "above the configured thresholds across all 4 tested mtDNA positions" in report
    assert "does not establish the biological absence of heteroplasmy" in report


def test_equal_candidate_metrics_are_ordered_by_position(tmp_path: Path) -> None:
    ref = write_fasta(tmp_path / "tie.fa", {"MT": "AAAA"})
    bam = write_alignment(
        tmp_path / "tie.bam",
        {"MT": 4},
        [
            ReadSpec("alt-1", "MT", 0, "CAAC"),
            ReadSpec("alt-2", "MT", 0, "CAAC"),
            ReadSpec("ref-1", "MT", 0, "AAAA"),
            ReadSpec("ref-2", "MT", 0, "AAAA"),
        ],
    )
    outputs = run_step(
        bam=bam,
        ref_fasta=ref,
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "report",
        sample_id="TIED",
        mt_contig="MT",
        mt_length=4,
        min_depth=1,
        min_vaf=0.25,
    )
    candidates = pd.read_csv(outputs["candidate_path"], sep="\t")
    assert candidates["position"].tolist() == [1, 4]


def test_failed_recomputation_removes_prior_heteroplasmy_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = write_fasta(tmp_path / "reference.fa", {"MT": "AAAA"})
    summary_dir = tmp_path / "summary"
    figure_dir = tmp_path / "figures"
    report_dir = tmp_path / "report"
    summary_dir.mkdir()
    figure_dir.mkdir()
    report_dir.mkdir()
    owned_outputs = (
        summary_dir / "mito_heteroplasmy_all_sites.tsv",
        summary_dir / "mito_heteroplasmy_candidates.tsv",
        summary_dir / "mito_heteroplasmy_summary.tsv",
        report_dir / "02_mito_heteroplasmy.html",
        figure_dir / "mito_heteroplasmy_landscape.png",
        figure_dir / "mito_heteroplasmy_top_candidates.png",
    )
    for path in owned_outputs:
        path.write_text("stale\n", encoding="ascii")
    monkeypatch.setattr(
        heteroplasmy,
        "count_contig_alleles",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("counting failed")),
    )

    with pytest.raises(RuntimeError, match="counting failed"):
        heteroplasmy.run_step(
            bam=tmp_path / "unused.bam",
            ref_fasta=reference,
            summary_dir=summary_dir,
            figure_dir=figure_dir,
            report_dir=report_dir,
            sample_id="STALE",
            mt_contig="MT",
            mt_length=4,
            min_depth=1,
            min_vaf=0.02,
        )

    assert all(not path.exists() for path in owned_outputs)
