from __future__ import annotations

import pandas as pd
import pytest

from mito_overview.steps import mito_cosegregation as cosegregation


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
    assert heatmap.loc["10:A>C", "20:A>G"] == row["alt_jaccard_within_shared_spanning_reads"]


@pytest.mark.parametrize(
    ("selected_sites", "valid_pairs", "upstream_message", "status", "reason_code"),
    [
        (0, 0, "candidate table empty", "not_evaluable", "no_candidate_sites_available"),
        (1, 0, None, "not_evaluable", "fewer_than_two_selected_sites"),
        (2, 0, None, "not_evaluable", "no_pairs_meet_shared_read_threshold"),
        (2, 1, None, "ok", ""),
    ],
)
def test_pairwise_status_requires_an_evaluable_pair(
    selected_sites: int,
    valid_pairs: int,
    upstream_message: str | None,
    status: str,
    reason_code: str,
) -> None:
    observed_status, _, observed_reason, _ = cosegregation._evaluation_status(
        selected_site_count=selected_sites,
        valid_pair_count=valid_pairs,
        upstream_message=upstream_message,
    )
    assert observed_status == status
    assert observed_reason == reason_code
