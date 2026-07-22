from __future__ import annotations

from pathlib import Path

import pandas as pd

from mito_overview.steps.mito_circularity_qc import run_step

from ._helpers import metric_map


def write_tables(
    summary_dir: Path,
    *,
    depth: pd.DataFrame,
    reads: pd.DataFrame,
    candidates: pd.DataFrame,
) -> None:
    summary_dir.mkdir(parents=True, exist_ok=True)
    depth.to_csv(summary_dir / "mito_depth_per_base.tsv", sep="\t", index=False)
    reads.to_csv(summary_dir / "mito_read_stats.tsv", sep="\t", index=False)
    candidates.to_csv(summary_dir / "mito_heteroplasmy_candidates.tsv", sep="\t", index=False)


def run_circularity(tmp_path: Path) -> tuple[dict[str, Path | str], dict[str, str]]:
    outputs = run_step(
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="S1",
        mt_contig="MT",
        mt_length=100,
        edge_window=10,
    )
    return outputs, metric_map(Path(outputs["summary_path"]))


def test_exact_edge_boundaries_and_valid_zero_depth(tmp_path: Path) -> None:
    depths = [0.0] * 10 + [5.0] * 80 + [10.0] * 10
    depth = pd.DataFrame({"position": range(1, 101), "depth": depths})
    reads = pd.DataFrame(
        [
            {"read_name": "start-edge", "read_start": 1, "read_end": 50, "softclip_fraction": 0.0, "is_primary": 1},
            {"read_name": "end-edge", "read_start": 20, "read_end": 100, "softclip_fraction": 0.3, "is_primary": 1},
            {"read_name": "interior", "read_start": 20, "read_end": 80, "softclip_fraction": 0.0, "is_primary": 1},
            {"read_name": "secondary", "read_start": 1, "read_end": 100, "softclip_fraction": 1.0, "is_primary": 0},
        ]
    )
    candidates = pd.DataFrame({"position": [10, 11, 90, 91]})
    write_tables(tmp_path / "summary", depth=depth, reads=reads, candidates=candidates)

    outputs, metrics = run_circularity(tmp_path)

    assert outputs["status"] == "ok"
    assert metrics["status"] == "ok"
    assert metrics["reason_code"] == ""
    assert metrics["edge_window_bp"] == "10"
    assert metrics["mean_depth_first_edge"] == "0.0"
    assert metrics["mean_depth_first_edge_denominator_positions"] == "10"
    assert metrics["mean_depth_first_edge_status"] == "ok"
    assert metrics["mean_depth_interior"] == "5.0"
    assert metrics["mean_depth_interior_denominator_positions"] == "80"
    assert metrics["mean_depth_last_edge"] == "10.0"
    assert metrics["mean_depth_last_edge_denominator_positions"] == "10"
    assert metrics["candidate_sites_total"] == "4"
    assert metrics["candidate_sites_in_edges"] == "2"
    assert metrics["candidate_edge_fraction_denominator_positions"] == "4"
    assert metrics["candidate_edge_fraction"] == "0.5"
    assert metrics["candidate_edge_fraction_status"] == "ok"
    assert metrics["primary_read_rows"] == "3"
    assert metrics["primary_read_start_in_edge_fraction_denominator_reads"] == "3"
    assert metrics["primary_read_start_in_edge_fraction"] == "0.333333"
    assert metrics["primary_read_end_in_edge_fraction"] == "0.333333"
    assert metrics["edge_read_heavy_softclip_fraction"] == "0.333333"


def test_unusable_or_missing_metric_evidence_is_na_not_zero(tmp_path: Path) -> None:
    depth = pd.DataFrame({"position": [50], "depth": [0.0]})
    reads = pd.DataFrame(
        [
            {
                "read_name": "unusable",
                "read_start": "bad",
                "read_end": "bad",
                "softclip_fraction": "bad",
                "is_primary": 1,
            }
        ]
    )
    candidates = pd.DataFrame({"position": ["bad"]})
    write_tables(tmp_path / "summary", depth=depth, reads=reads, candidates=candidates)

    outputs, metrics = run_circularity(tmp_path)

    assert outputs["status"] == "not_evaluable"
    assert metrics["status"] == "not_evaluable"
    assert metrics["reason_code"] == "incomplete_depth_region_evidence"
    assert metrics["mean_depth_first_edge"] == "NA"
    assert metrics["mean_depth_first_edge_denominator_positions"] == "0"
    assert metrics["mean_depth_first_edge_status"] == "not_evaluable"
    assert metrics["mean_depth_first_edge_reason_code"] == "no_positions_in_first_edge_window"
    assert metrics["mean_depth_last_edge"] == "NA"
    assert metrics["mean_depth_last_edge_status"] == "not_evaluable"
    assert metrics["mean_depth_interior"] == "0.0"
    assert metrics["mean_depth_interior_denominator_positions"] == "1"
    assert metrics["mean_depth_interior_status"] == "ok"
    assert metrics["candidate_edge_fraction"] == "NA"
    assert metrics["candidate_edge_fraction_denominator_positions"] == "0"
    assert metrics["candidate_edge_fraction_status"] == "not_evaluable"
    assert metrics["candidate_edge_fraction_reason_code"] == "no_usable_candidate_positions"
    assert metrics["primary_read_start_in_edge_fraction"] == "NA"
    assert metrics["primary_read_start_in_edge_fraction_denominator_reads"] == "0"
    assert metrics["primary_read_start_in_edge_fraction_status"] == "not_evaluable"
    assert metrics["primary_read_end_in_edge_fraction"] == "NA"
    assert metrics["edge_read_heavy_softclip_fraction"] == "NA"
    assert "NA" in Path(outputs["report_path"]).read_text(encoding="utf-8")


def test_valid_zero_fractions_remain_observed_zero(tmp_path: Path) -> None:
    depth = pd.DataFrame(
        {
            "position": range(1, 101),
            "depth": [10.0] * 100,
        }
    )
    reads = pd.DataFrame(
        [
            {
                "read_name": "interior",
                "read_start": 20,
                "read_end": 80,
                "softclip_fraction": 0.0,
                "is_primary": 1,
            }
        ]
    )
    candidates = pd.DataFrame({"position": [11, 90]})
    write_tables(tmp_path / "summary", depth=depth, reads=reads, candidates=candidates)

    outputs, metrics = run_circularity(tmp_path)

    assert outputs["status"] == "ok"
    assert metrics["candidate_edge_fraction"] == "0.0"
    assert metrics["candidate_edge_fraction_denominator_positions"] == "2"
    assert metrics["candidate_edge_fraction_status"] == "ok"
    assert metrics["primary_read_start_in_edge_fraction"] == "0.0"
    assert metrics["primary_read_start_in_edge_fraction_denominator_reads"] == "1"
    assert metrics["primary_read_start_in_edge_fraction_status"] == "ok"
    assert metrics["primary_read_end_in_edge_fraction"] == "0.0"
    assert metrics["primary_read_end_in_edge_fraction_status"] == "ok"
    assert metrics["edge_read_heavy_softclip_fraction"] == "0.0"
    assert metrics["edge_read_heavy_softclip_fraction_status"] == "ok"


def test_missing_depth_profile_has_explicit_module_status(tmp_path: Path) -> None:
    outputs, metrics = run_circularity(tmp_path)

    assert outputs["status"] == "not_evaluable"
    assert metrics == {
        "status": "not_evaluable",
        "reason_code": "no_depth_profile_available",
    }
