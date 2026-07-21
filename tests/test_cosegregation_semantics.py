from __future__ import annotations

import pandas as pd
import pytest

from mito_overview.steps import mito_cosegregation as cosegregation


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
