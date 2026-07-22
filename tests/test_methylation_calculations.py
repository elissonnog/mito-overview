from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mito_overview.steps.mito_methylation_exploratory import (
    ROW_COLUMNS,
    build_proxy,
    load_bedmethyl_table,
    np_proxy_comparison_summary,
    run_step,
    track_summary,
)

from ._helpers import metric_map


def summary_metrics(df: pd.DataFrame) -> dict[str, object]:
    return dict(zip(df["metric"], df["value"], strict=True))


def methylation_rows(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=ROW_COLUMNS)


def test_track_summary_exact_weighted_calculations() -> None:
    rows = methylation_rows(
        [
            {
                "track": "NP_real_all_reads",
                "position": 1,
                "valid_coverage": 10.0,
                "percent_modified": 20.0,
                "modified_count": 2.0,
                "canonical_count": 8.0,
            },
            {
                "track": "NP_real_all_reads",
                "position": 2,
                "valid_coverage": 30.0,
                "percent_modified": 60.0,
                "modified_count": 18.0,
                "canonical_count": 12.0,
            },
        ]
    )

    observed = track_summary(rows).iloc[0]

    assert observed["coverage_weighted_percent_modified"] == 50.0
    assert observed["coverage_weighted_denominator_valid_coverage"] == 40.0
    assert observed["coverage_weighted_status"] == "ok"
    assert observed["coverage_weighted_reason_code"] == ""
    assert observed["count_weighted_percent_modified"] == 50.0
    assert observed["count_weighted_denominator_calls"] == 40.0
    assert observed["count_weighted_status"] == "ok"
    assert observed["count_weighted_reason_code"] == ""


def test_track_summary_preserves_observed_zero_with_positive_denominators() -> None:
    rows = methylation_rows(
        [
            {
                "track": "NP_real_all_reads",
                "position": 1,
                "valid_coverage": 10.0,
                "percent_modified": 0.0,
                "modified_count": 0.0,
                "canonical_count": 10.0,
            }
        ]
    )

    observed = track_summary(rows).iloc[0]

    assert observed["coverage_weighted_percent_modified"] == 0.0
    assert observed["coverage_weighted_status"] == "ok"
    assert observed["count_weighted_percent_modified"] == 0.0
    assert observed["count_weighted_status"] == "ok"


def test_track_summary_marks_zero_denominators_not_evaluable() -> None:
    rows = methylation_rows(
        [
            {
                "track": "NP_real_all_reads",
                "position": 1,
                "valid_coverage": 0.0,
                "percent_modified": 0.0,
                "modified_count": 0.0,
                "canonical_count": 0.0,
            }
        ]
    )

    observed = track_summary(rows).iloc[0]

    assert pd.isna(observed["coverage_weighted_percent_modified"])
    assert observed["coverage_weighted_denominator_valid_coverage"] == 0.0
    assert observed["coverage_weighted_status"] == "not_evaluable"
    assert observed["coverage_weighted_reason_code"] == "zero_valid_coverage"
    assert pd.isna(observed["count_weighted_percent_modified"])
    assert observed["count_weighted_denominator_calls"] == 0.0
    assert observed["count_weighted_status"] == "not_evaluable"
    assert observed["count_weighted_reason_code"] == "zero_modified_plus_canonical_count"


def test_proxy_marks_zero_call_position_undefined() -> None:
    rows = methylation_rows(
        [
            {
                "track": "HP1",
                "position": 7,
                "valid_coverage": 0.0,
                "percent_modified": 0.0,
                "modified_count": 0.0,
                "canonical_count": 0.0,
            }
        ]
    )

    proxy = build_proxy(rows)

    assert len(proxy) == 1
    assert proxy.iloc[0]["track"] == "Phased_proxy_all_reads"
    assert pd.isna(proxy.iloc[0]["percent_modified"])


def test_np_proxy_summary_no_shared_positions_is_not_evaluable() -> None:
    observed = summary_metrics(
        np_proxy_comparison_summary(
            pd.DataFrame(),
            tracks_available=2,
            np_rows=1,
            proxy_rows=1,
        )
    )

    assert observed["status"] == "not_evaluable"
    assert observed["reason_code"] == "no_shared_positions"
    assert pd.isna(observed["np_proxy_mean_abs_difference"])
    assert observed["np_proxy_mean_abs_difference_denominator_positions"] == 0
    assert observed["np_proxy_mean_abs_difference_status"] == "not_evaluable"
    assert observed["np_proxy_mean_abs_difference_reason_code"] == "no_shared_positions"
    assert pd.isna(observed["np_proxy_correlation"])
    assert observed["np_proxy_correlation_denominator_positions"] == 0
    assert observed["np_proxy_correlation_status"] == "not_evaluable"
    assert observed["np_proxy_correlation_reason_code"] == "fewer_than_two_evaluable_shared_positions"


def test_np_proxy_summary_one_shared_position_has_mean_but_no_correlation() -> None:
    comparison = pd.DataFrame(
        {
            "position": [5],
            "percent_modified_np": [20.0],
            "percent_modified_proxy": [25.0],
        }
    )

    observed = summary_metrics(
        np_proxy_comparison_summary(
            comparison,
            tracks_available=2,
            np_rows=1,
            proxy_rows=1,
        )
    )

    assert observed["status"] == "ok"
    assert observed["np_proxy_mean_abs_difference"] == 5.0
    assert observed["np_proxy_mean_abs_difference_denominator_positions"] == 1
    assert observed["np_proxy_mean_abs_difference_status"] == "ok"
    assert pd.isna(observed["np_proxy_correlation"])
    assert observed["np_proxy_correlation_denominator_positions"] == 1
    assert observed["np_proxy_correlation_status"] == "not_evaluable"
    assert observed["np_proxy_correlation_reason_code"] == "fewer_than_two_evaluable_shared_positions"


def test_np_proxy_summary_exact_two_position_statistics() -> None:
    comparison = pd.DataFrame(
        {
            "position": [5, 6],
            "percent_modified_np": [10.0, 20.0],
            "percent_modified_proxy": [15.0, 25.0],
        }
    )

    observed = summary_metrics(
        np_proxy_comparison_summary(
            comparison,
            tracks_available=2,
            np_rows=2,
            proxy_rows=2,
        )
    )

    assert observed["np_proxy_mean_abs_difference"] == 5.0
    assert observed["np_proxy_mean_abs_difference_denominator_positions"] == 2
    assert observed["np_proxy_correlation"] == pytest.approx(1.0)
    assert observed["np_proxy_correlation_denominator_positions"] == 2
    assert observed["np_proxy_correlation_status"] == "ok"
    assert observed["np_proxy_correlation_reason_code"] == ""


def test_np_proxy_summary_zero_variance_correlation_is_not_evaluable() -> None:
    comparison = pd.DataFrame(
        {
            "position": [5, 6],
            "percent_modified_np": [10.0, 10.0],
            "percent_modified_proxy": [15.0, 25.0],
        }
    )

    observed = summary_metrics(
        np_proxy_comparison_summary(
            comparison,
            tracks_available=2,
            np_rows=2,
            proxy_rows=2,
        )
    )

    assert pd.isna(observed["np_proxy_correlation"])
    assert observed["np_proxy_correlation_denominator_positions"] == 2
    assert observed["np_proxy_correlation_status"] == "not_evaluable"
    assert observed["np_proxy_correlation_reason_code"] == "undefined_zero_variance"


def write_bedmethyl(
    path: Path,
    *,
    start: int,
    coverage: int,
    percent: float,
    modified: int,
    canonical: int,
    modification_code: str = "m",
    strand: str = "+",
) -> None:
    path.write_text(
        f"MT\t{start}\t{start + 1}\t{modification_code}\t0\t{strand}\t"
        f"{start}\t{start + 1}\t0,0,0\t"
        f"{coverage}\t{percent}\t{modified}\t{canonical}\n",
        encoding="ascii",
    )


def bedmethyl_line(
    *,
    start: int,
    coverage: int,
    percent: float,
    modified: int,
    canonical: int,
    modification_code: str = "m",
    strand: str = "+",
) -> str:
    return (
        f"MT\t{start}\t{start + 1}\t{modification_code}\t0\t{strand}\t"
        f"{start}\t{start + 1}\t0,0,0\t"
        f"{coverage}\t{percent}\t{modified}\t{canonical}\n"
    )


def test_duplicate_track_coordinates_are_pooled_once_by_counts(tmp_path: Path) -> None:
    np_path = tmp_path / "np-duplicates.bed"
    hp1_path = tmp_path / "hp1.bed"
    np_path.write_text(
        bedmethyl_line(start=0, coverage=10, percent=20.0, modified=2, canonical=8)
        + bedmethyl_line(start=0, coverage=10, percent=30.0, modified=3, canonical=7),
        encoding="ascii",
    )
    hp1_path.write_text(
        bedmethyl_line(start=0, coverage=10, percent=40.0, modified=4, canonical=6),
        encoding="ascii",
    )

    outputs = run_step(
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="DUPLICATE-POSITION",
        mt_contig="MT",
        mito_mods_np=np_path,
        mito_mods_hp1=hp1_path,
        mito_mods_hp2=tmp_path / "missing-hp2.bed",
        mito_mods_ungrouped=tmp_path / "missing-ungrouped.bed",
    )

    combined = pd.read_csv(outputs["track_rows_path"], sep="\t")
    comparison = pd.read_csv(outputs["cmp_path"], sep="\t")
    metrics = metric_map(Path(outputs["cmp_summary_path"]))
    np_rows = combined[combined["track"] == "NP_real_all_reads"]

    assert len(np_rows) == 1
    assert np_rows.iloc[0]["modification_code"] == "m"
    assert np_rows.iloc[0]["strand"] == "+"
    assert np_rows.iloc[0]["modified_count"] == 5
    assert np_rows.iloc[0]["canonical_count"] == 15
    assert np_rows.iloc[0]["percent_modified"] == 25.0
    assert comparison[["position", "percent_modified_np", "percent_modified_proxy"]].values.tolist() == [
        [1.0, 25.0, 40.0]
    ]
    assert metrics["np_rows"] == "1"
    assert metrics["shared_np_proxy_positions"] == "1"
    assert metrics["evaluable_np_proxy_positions"] == "1"
    assert metrics["np_proxy_mean_abs_difference"] == "15.0"


def test_mixed_modification_identity_and_strand_are_never_silently_pooled(tmp_path: Path) -> None:
    path = tmp_path / "mixed.bed"
    path.write_text(
        bedmethyl_line(
            start=0,
            coverage=10,
            percent=20.0,
            modified=2,
            canonical=8,
            modification_code="m",
            strand="+",
        )
        + bedmethyl_line(
            start=0,
            coverage=10,
            percent=30.0,
            modified=3,
            canonical=7,
            modification_code="h",
            strand="+",
        )
        + bedmethyl_line(
            start=0,
            coverage=10,
            percent=40.0,
            modified=4,
            canonical=6,
            modification_code="m",
            strand="-",
        ),
        encoding="ascii",
    )

    observed = load_bedmethyl_table(path, "NP_real_all_reads")

    assert observed[
        ["position", "modification_code", "strand", "modified_count", "canonical_count"]
    ].values.tolist() == [
        [1, "m", "+", 2.0, 8.0],
        [1, "h", "+", 3.0, 7.0],
        [1, "m", "-", 4.0, 6.0],
    ]


def test_invalid_bedmethyl_strand_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid-strand.bed"
    path.write_text(
        bedmethyl_line(
            start=0,
            coverage=10,
            percent=20.0,
            modified=2,
            canonical=8,
            strand="?",
        ),
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="Unsupported bedMethyl strand"):
        load_bedmethyl_table(path, "NP_real_all_reads")


def test_np_proxy_comparison_requires_matching_modification_identity(tmp_path: Path) -> None:
    np_path = tmp_path / "np.bed"
    hp1_path = tmp_path / "hp1.bed"
    write_bedmethyl(
        np_path,
        start=0,
        coverage=10,
        percent=20.0,
        modified=2,
        canonical=8,
        modification_code="m",
    )
    write_bedmethyl(
        hp1_path,
        start=0,
        coverage=10,
        percent=30.0,
        modified=3,
        canonical=7,
        modification_code="h",
    )

    outputs = run_step(
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="IDENTITY-MISMATCH",
        mt_contig="MT",
        mito_mods_np=np_path,
        mito_mods_hp1=hp1_path,
        mito_mods_hp2=tmp_path / "missing-hp2.bed",
        mito_mods_ungrouped=tmp_path / "missing-ungrouped.bed",
    )

    comparison = pd.read_csv(outputs["cmp_path"], sep="\t")
    metrics = metric_map(Path(outputs["cmp_summary_path"]))

    assert comparison.empty
    assert metrics["status"] == "not_evaluable"
    assert metrics["reason_code"] == "no_shared_positions"


def test_run_step_serializes_undefined_comparison_as_na(tmp_path: Path) -> None:
    np_path = tmp_path / "np.bed"
    hp1_path = tmp_path / "hp1.bed"
    write_bedmethyl(np_path, start=0, coverage=10, percent=20.0, modified=2, canonical=8)
    write_bedmethyl(hp1_path, start=1, coverage=10, percent=30.0, modified=3, canonical=7)

    outputs = run_step(
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="S1",
        mt_contig="MT",
        mito_mods_np=np_path,
        mito_mods_hp1=hp1_path,
        mito_mods_hp2=tmp_path / "missing-hp2.bed",
        mito_mods_ungrouped=tmp_path / "missing-ungrouped.bed",
    )

    metrics = metric_map(Path(outputs["cmp_summary_path"]))
    assert metrics["status"] == "not_evaluable"
    assert metrics["reason_code"] == "no_shared_positions"
    assert metrics["np_proxy_mean_abs_difference"] == "NA"
    assert metrics["np_proxy_correlation"] == "NA"
    report_html = Path(outputs["report_path"]).read_text(encoding="utf-8")
    assert "<td>nan</td>" not in report_html.lower()
    assert "<td>NA</td>" in report_html
