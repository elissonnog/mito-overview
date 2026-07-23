from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mito_overview.steps import mito_cosegregation as cosegregation

from ._helpers import ReadSpec, metric_map, write_alignment


def candidate_row(position: int, alt_base: str, *, depth: int = 25) -> dict[str, object]:
    alt_count = 5
    base_counts = {base: 0 for base in "ACGT"}
    base_counts["A"] = depth - alt_count
    base_counts[alt_base] = alt_count
    return {
        "position": position,
        "ref_base": "A",
        "alt_base": alt_base,
        "callable_depth": depth,
        "depth": depth,
        "alt_count": alt_count,
        "alt_allele_fraction": alt_count / depth,
        "heteroplasmy_fraction": alt_count / depth,
        "alt_forward": 2,
        "alt_reverse": 3,
        **base_counts,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, "white"), (0.59, "white"), (0.6, "black"), (1.0, "black")],
)
def test_heatmap_annotation_contrast(value: float, expected: str) -> None:
    assert cosegregation._heatmap_text_color(value) == expected


def test_alt_jaccard_is_conditioned_on_shared_spanning_reads() -> None:
    selected_sites = pd.DataFrame({"site_label": ["10:A>C", "20:A>G"]})
    coverage_by_site = {
        "10:A>C": {"both_alt", "i_alt_shared", "shared_ref", "i_only_alt"},
        "20:A>G": {"both_alt", "i_alt_shared", "shared_ref", "j_only_alt_1", "j_only_alt_2"},
    }
    alt_by_site = {
        "10:A>C": {"both_alt", "i_alt_shared", "i_only_alt"},
        "20:A>G": {"both_alt", "j_only_alt_1", "j_only_alt_2"},
    }

    pairwise, heatmap = cosegregation._summarise_pairwise(
        selected_sites,
        coverage_by_site,
        alt_by_site,
        min_shared_reads=3,
    )

    row = pairwise.iloc[0]
    global_set_jaccard = len(alt_by_site["10:A>C"] & alt_by_site["20:A>G"]) / len(
        alt_by_site["10:A>C"] | alt_by_site["20:A>G"]
    )
    assert global_set_jaccard == pytest.approx(0.2)
    assert row["conditional_universe"] == "filtered_reads_spanning_both_sites"
    assert row["shared_reads"] == 3
    assert row["alt_i_shared_reads"] == 2
    assert row["alt_j_shared_reads"] == 1
    assert row["co_alt_reads"] == 1
    assert row["alt_jaccard_within_shared_spanning_reads"] == pytest.approx(0.5)
    assert row["alt_jaccard_within_shared_spanning_reads"] != pytest.approx(global_set_jaccard)
    assert row["jaccard_alt"] == row["alt_jaccard_within_shared_spanning_reads"]
    assert row["alt_jaccard_status"] == "ok"
    assert row["fraction_alt_i_also_alt_j_status"] == "ok"
    assert row["fraction_alt_j_also_alt_i_status"] == "ok"
    assert heatmap.loc["10:A>C", "20:A>G"] == row["alt_jaccard_within_shared_spanning_reads"]


def test_pair_without_alternate_support_has_undefined_ratios() -> None:
    selected_sites = pd.DataFrame({"site_label": ["10:A>C", "20:A>G"]})
    shared_reference_reads = {f"ref-{index}" for index in range(25)}

    pairwise, heatmap = cosegregation._summarise_pairwise(
        selected_sites,
        {
            "10:A>C": shared_reference_reads,
            "20:A>G": shared_reference_reads,
        },
        {"10:A>C": set(), "20:A>G": set()},
        min_shared_reads=25,
    )

    row = pairwise.iloc[0]
    assert row["shared_reads"] == 25
    assert pd.isna(row["alt_jaccard_within_shared_spanning_reads"])
    assert pd.isna(row["jaccard_alt"])
    assert pd.isna(row["fraction_alt_i_also_alt_j"])
    assert pd.isna(row["fraction_alt_j_also_alt_i"])
    assert row["alt_jaccard_status"] == "not_evaluable_zero_alt_union"
    assert row["fraction_alt_i_also_alt_j_status"] == (
        "not_evaluable_zero_alt_i_denominator"
    )
    assert row["fraction_alt_j_also_alt_i_status"] == (
        "not_evaluable_zero_alt_j_denominator"
    )
    assert pd.isna(heatmap.loc["10:A>C", "20:A>G"])


def test_run_step_is_not_evaluable_when_shared_pairs_have_no_alt_support(
    tmp_path: Path,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    pd.DataFrame(
        [
            candidate_row(10, "C"),
            candidate_row(20, "G"),
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_candidates.tsv", sep="\t", index=False)
    pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "reason_code", "value": ""},
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)
    bam = write_alignment(
        tmp_path / "reference-only.bam",
        {"MT": 30},
        [
            ReadSpec(f"reference-{index}", "MT", 0, "A" * 30)
            for index in range(25)
        ],
    )

    outputs = cosegregation.run_step(
        bam=bam,
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="REFERENCE-ONLY",
        mt_contig="MT",
    )

    pairwise = pd.read_csv(outputs["pairwise_path"], sep="\t")
    summary = metric_map(outputs["summary_path"])
    assert outputs["status"] == "not_evaluable"
    assert summary["reason_code"] == "no_pairs_with_alt_support"
    assert summary["pairwise_edges_meeting_shared_threshold"] == "1"
    assert summary["pairwise_edges_with_evaluable_alt_jaccard"] == "0"
    assert pd.isna(pairwise.loc[0, "alt_jaccard_within_shared_spanning_reads"])
    assert pairwise.loc[0, "alt_jaccard_status"] == "not_evaluable_zero_alt_union"


def test_stale_candidates_are_not_used_when_upstream_heteroplasmy_failed(
    tmp_path: Path,
) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    pd.DataFrame(
        [
            {
                "position": 10,
                "ref_base": "A",
                "alt_base": "C",
                "alt_allele_fraction": 0.2,
                "callable_depth": 25,
            }
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_candidates.tsv", sep="\t", index=False)
    pd.DataFrame(
        [
            {"metric": "status", "value": "not_evaluable"},
            {"metric": "reason_code", "value": "no_callable_positions"},
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)
    bam = write_alignment(tmp_path / "empty.bam", {"MT": 30}, [])

    outputs = cosegregation.run_step(
        bam=bam,
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="STALE",
        mt_contig="MT",
    )
    summary = metric_map(outputs["summary_path"])

    assert outputs["status"] == "not_evaluable"
    assert summary["reason_code"] == "no_callable_positions"
    assert summary["selected_sites"] == "0"
    assert pd.read_csv(outputs["selected_path"], sep="\t").empty


@pytest.mark.parametrize(
    (
        "selected_sites",
        "valid_pairs",
        "evaluable_pairs",
        "upstream_message",
        "status",
        "reason_code",
    ),
    [
        (0, 0, 0, "candidate table empty", "not_evaluable", "no_candidate_sites_available"),
        (1, 0, 0, None, "not_evaluable", "fewer_than_two_selected_sites"),
        (2, 0, 0, None, "not_evaluable", "no_pairs_meet_shared_read_threshold"),
        (2, 1, 0, None, "not_evaluable", "no_pairs_with_alt_support"),
        (2, 1, 1, None, "ok", ""),
    ],
)
def test_pairwise_status_requires_an_evaluable_pair(
    selected_sites: int,
    valid_pairs: int,
    evaluable_pairs: int,
    upstream_message: str | None,
    status: str,
    reason_code: str,
) -> None:
    observed_status, _, observed_reason, _ = cosegregation._evaluation_status(
        selected_site_count=selected_sites,
        valid_pair_count=valid_pairs,
        evaluable_jaccard_pair_count=evaluable_pairs,
        upstream_message=upstream_message,
    )
    assert observed_status == status
    assert observed_reason == reason_code
