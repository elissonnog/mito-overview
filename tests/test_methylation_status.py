from __future__ import annotations

from pathlib import Path

import pytest

from mito_overview.steps.mito_methylation_exploratory import run_step

from ._helpers import metric_map


TRACK_METRICS = {
    "NP_real_all_reads": "np_track_input_present",
    "HP1": "hp1_track_input_present",
    "HP2": "hp2_track_input_present",
    "Ungrouped": "ungrouped_track_input_present",
}


def run_no_data_step(
    tmp_path: Path,
    track_paths: dict[str, Path | None],
    *,
    inputs_configured: bool,
    track_inputs_configured: dict[str, bool] | None = None,
) -> tuple[dict[str, Path | str], dict[str, str]]:
    outputs = run_step(
        summary_dir=tmp_path / "summary",
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="S1",
        mt_contig="MT",
        mito_mods_np=track_paths["NP_real_all_reads"],
        mito_mods_hp1=track_paths["HP1"],
        mito_mods_hp2=track_paths["HP2"],
        mito_mods_ungrouped=track_paths["Ungrouped"],
        inputs_configured=inputs_configured,
        track_inputs_configured=track_inputs_configured,
    )
    return outputs, metric_map(Path(outputs["summary_path"]))


@pytest.mark.parametrize(
    ("inputs_configured", "expected_status", "expected_reason"),
    [
        (False, "not_configured", "no_bedmethyl_sidecars_configured"),
        (True, "not_evaluable", "no_mt_bedmethyl_rows_available"),
    ],
)
def test_absent_track_paths_are_not_present_and_preserve_status_semantics(
    tmp_path: Path,
    inputs_configured: bool,
    expected_status: str,
    expected_reason: str,
) -> None:
    track_paths = {track: tmp_path / f"missing-{track}.bed" for track in TRACK_METRICS}

    outputs, metrics = run_no_data_step(
        tmp_path,
        track_paths,
        inputs_configured=inputs_configured,
    )

    assert outputs["status"] == expected_status
    assert metrics["status"] == expected_status
    assert metrics["reason_code"] == expected_reason
    assert {metrics[metric] for metric in TRACK_METRICS.values()} == {"0"}


def test_existing_empty_track_files_are_present_but_not_evaluable(tmp_path: Path) -> None:
    track_paths = {track: tmp_path / f"empty-{track}.bed" for track in TRACK_METRICS}
    for path in track_paths.values():
        path.touch()

    outputs, metrics = run_no_data_step(tmp_path, track_paths, inputs_configured=True)

    assert outputs["status"] == "not_evaluable"
    assert metrics["status"] == "not_evaluable"
    assert metrics["reason_code"] == "no_mt_bedmethyl_rows_available"
    assert {metrics[metric] for metric in TRACK_METRICS.values()} == {"1"}


def test_mixed_track_paths_report_presence_per_track(tmp_path: Path) -> None:
    hp1_path = tmp_path / "hp1-empty.bed"
    ungrouped_path = tmp_path / "ungrouped-empty.bed"
    hp1_path.touch()
    ungrouped_path.touch()
    track_paths = {
        "NP_real_all_reads": None,
        "HP1": hp1_path,
        "HP2": tmp_path / "hp2-missing.bed",
        "Ungrouped": ungrouped_path,
    }

    outputs, metrics = run_no_data_step(
        tmp_path,
        track_paths,
        inputs_configured=True,
        track_inputs_configured={
            "NP_real_all_reads": False,
            "HP1": True,
            "HP2": False,
            "Ungrouped": True,
        },
    )

    assert outputs["status"] == "not_evaluable"
    assert metrics["status"] == "not_evaluable"
    assert metrics["np_track_input_present"] == "0"
    assert metrics["hp1_track_input_present"] == "1"
    assert metrics["hp2_track_input_present"] == "0"
    assert metrics["ungrouped_track_input_present"] == "1"


def test_placeholder_outputs_do_not_override_absent_source_configuration(tmp_path: Path) -> None:
    track_paths = {track: tmp_path / f"placeholder-{track}.bed" for track in TRACK_METRICS}
    for path in track_paths.values():
        path.touch()

    outputs, metrics = run_no_data_step(
        tmp_path,
        track_paths,
        inputs_configured=False,
        track_inputs_configured={track: False for track in TRACK_METRICS},
    )

    assert outputs["status"] == "not_configured"
    assert {metrics[metric] for metric in TRACK_METRICS.values()} == {"0"}
