from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from mito_overview.steps import mito_mvtool_annotation as mvtool

from ._helpers import metric_map


def complete_candidate(row: dict[str, object]) -> dict[str, object]:
    position = int(row["position"])
    ref_base = str(row["ref_base"])
    alt_base = str(row["alt_base"])
    callable_depth = int(row.get("callable_depth", 100))
    alt_count = int(row.get("alt_count", 25))
    counts = {base: 0 for base in ("A", "C", "G", "T")}
    counts[ref_base] = callable_depth - alt_count
    counts[alt_base] = alt_count
    fraction = round(alt_count / callable_depth, 6)
    return {
        "position": position,
        "ref_base": ref_base,
        "alt_base": alt_base,
        "callable_depth": callable_depth,
        "depth": callable_depth,
        "alt_count": alt_count,
        "alt_allele_fraction": fraction,
        "heteroplasmy_fraction": fraction,
        "alt_forward": alt_count // 2,
        "alt_reverse": alt_count - (alt_count // 2),
        **counts,
    }


def prepare_case(
    root: Path,
    rows: list[dict[str, object]] | None = None,
) -> tuple[Path, Path, Path]:
    summary = root / "summary"
    figures = root / "figures"
    reports = root / "reports"
    summary.mkdir(parents=True)
    candidate_rows = rows if rows is not None else [
        {"position": 10, "ref_base": "A", "alt_base": "C", "callable_depth": 100, "alt_count": 25}
    ]
    pd.DataFrame([complete_candidate(row) for row in candidate_rows]).to_csv(
        summary / "mito_heteroplasmy_candidates.tsv", sep="\t", index=False
    )
    pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "reason_code", "value": ""},
            {"metric": "candidate_sites", "value": len(candidate_rows)},
        ]
    ).to_csv(summary / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)
    return summary, figures, reports


def test_disabled_mode_cannot_create_requests_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    monkeypatch.setattr(mvtool.requests, "Session", lambda: (_ for _ in ()).throw(AssertionError("network used")))
    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
    )
    assert outputs["status"] == "not_configured"
    metrics = metric_map(outputs["summary_path"])
    assert metrics["network_request_attempted"] == "0"
    assert pd.read_csv(outputs["annot_path"], sep="\t").empty
    assert pd.read_csv(outputs["batch_log_path"], sep="\t").empty


def test_fixture_mode_returns_exact_annotation(tmp_path: Path) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    fixture = Path(__file__).parent / "fixtures" / "mock_mvtool_annotations.json"
    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
        mode="fixture",
        fixture_json=fixture,
    )
    assert outputs["status"] == "ok"
    annotated = pd.read_csv(outputs["annot_path"], sep="\t")
    assert annotated.loc[0, "Input"] == "m.10A>C"
    assert annotated.loc[0, "Mitomap_status"] == "Reported"
    assert metric_map(outputs["summary_path"])["network_request_attempted"] == "0"


def test_population_frequency_bins_use_explicit_left_closed_boundaries(
    tmp_path: Path,
) -> None:
    rows = [
        {"position": position, "ref_base": "A", "alt_base": "C"}
        for position in range(10, 15)
    ]
    summary, figures, reports = prepare_case(tmp_path, rows)
    fixture = tmp_path / "frequency-boundaries.json"
    frequencies = [0.0009, 0.001, 0.01, 0.05, 0.10]
    fixture.write_text(
        json.dumps(
            {
                "records": {
                    f"m.{position}A>C": {
                        "Input": f"m.{position}A>C",
                        "AF_M1": frequency,
                    }
                    for position, frequency in zip(range(10, 15), frequencies)
                }
            }
        ),
        encoding="utf-8",
    )

    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="AF-BOUNDARIES",
        species="human",
        mode="fixture",
        fixture_json=fixture,
    )
    observed = pd.read_csv(
        summary / "mito_mvtool_population_bins.tsv",
        sep="\t",
    )

    assert outputs["status"] == "ok"
    assert observed.to_dict("records") == [
        {"AF_M1_bin": "<0.1%", "candidate_sites": 1},
        {"AF_M1_bin": "0.1-<1%", "candidate_sites": 1},
        {"AF_M1_bin": "1-<5%", "candidate_sites": 1},
        {"AF_M1_bin": "5-<10%", "candidate_sites": 1},
        {"AF_M1_bin": ">=10%", "candidate_sites": 1},
    ]


class FakeResponse:
    status_code = 200

    def __init__(self, payload: object):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def test_explicit_network_mode_with_mock_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    payload = {"mseqdr": [{"Input": "m.10A>C", "Mitomap_status": "Reported"}]}
    monkeypatch.setattr(requests.Session, "post", lambda self, *args, **kwargs: FakeResponse(payload))
    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
        mode="network",
        api_url="https://mock.invalid/mvtool",
    )
    assert outputs["status"] == "ok"
    assert metric_map(outputs["summary_path"])["network_request_attempted"] == "1"


@pytest.mark.parametrize(
    "api_url",
    [
        "file:///tmp/mvtool.json",
        "ftp://example.org/mvtool",
        "https://user:password@example.org/mvtool",
        "example.org/mvtool",
    ],
)
def test_network_mode_rejects_non_http_or_credentialed_urls_without_request(
    api_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    monkeypatch.setattr(
        mvtool.requests,
        "Session",
        lambda: (_ for _ in ()).throw(AssertionError("request session created")),
    )
    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
        mode="network",
        api_url=api_url,
    )
    metrics = metric_map(outputs["summary_path"])
    assert outputs["status"] == "unavailable"
    assert metrics["reason_code"] == "mvtool_network_url_invalid"
    assert metrics["network_request_attempted"] == "0"


def test_network_submits_every_valid_candidate_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_rows = [
        {"position": 10, "ref_base": "A", "alt_base": "C"},
        {"position": 20, "ref_base": "A", "alt_base": "G"},
    ]
    summary, figures, reports = prepare_case(tmp_path, candidate_rows)
    submitted: list[str] = []

    def post(self, url, *, data, timeout):
        batch_inputs = data.decode().splitlines()
        submitted.extend(batch_inputs)
        return FakeResponse(
            {"mseqdr": [{"Input": value, "Mitomap_status": "Reported"} for value in batch_inputs]}
        )

    monkeypatch.setattr(requests.Session, "post", post)
    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
        mode="network",
        api_url="https://mock.invalid/mvtool",
        batch_size=1,
    )

    assert outputs["status"] == "ok"
    assert submitted == ["m.10A>C", "m.20A>G"]
    annotated = pd.read_csv(outputs["annot_path"], sep="\t")
    assert annotated["Input"].tolist() == submitted
    assert int(pd.read_csv(outputs["status_counts_path"], sep="\t")["candidate_sites"].sum()) == 2


def test_duplicate_internal_candidates_are_rejected_before_network_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = {"position": 10, "ref_base": "A", "alt_base": "C"}
    summary, figures, reports = prepare_case(tmp_path, [candidate, candidate])
    monkeypatch.setattr(
        mvtool.requests,
        "Session",
        lambda: (_ for _ in ()).throw(AssertionError("network session created")),
    )

    with pytest.raises(ValueError, match="duplicate variant keys"):
        mvtool.run_step(
            summary_dir=summary,
            figure_dir=figures,
            report_dir=reports,
            sample_id="S1",
            species="human",
            mode="network",
            api_url="https://mock.invalid/mvtool",
        )


def test_incomplete_internal_candidates_are_rejected_before_fixture_use(
    tmp_path: Path,
) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    candidate_path = summary / "mito_heteroplasmy_candidates.tsv"
    incomplete = pd.read_csv(candidate_path, sep="\t").drop(columns=["callable_depth"])
    incomplete.to_csv(candidate_path, sep="\t", index=False)
    fixture = Path(__file__).parent / "fixtures" / "mock_mvtool_annotations.json"

    with pytest.raises(ValueError, match="lacks required columns: callable_depth"):
        mvtool.run_step(
            summary_dir=summary,
            figure_dir=figures,
            report_dir=reports,
            sample_id="S1",
            species="human",
            mode="fixture",
            fixture_json=fixture,
        )


def test_partial_header_only_candidates_are_rejected_before_fixture_use(
    tmp_path: Path,
) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    candidate_path = summary / "mito_heteroplasmy_candidates.tsv"
    pd.DataFrame(columns=["position"]).to_csv(candidate_path, sep="\t", index=False)
    fixture = Path(__file__).parent / "fixtures" / "mock_mvtool_annotations.json"

    with pytest.raises(ValueError, match="lacks required columns"):
        mvtool.run_step(
            summary_dir=summary,
            figure_dir=figures,
            report_dir=reports,
            sample_id="S1",
            species="human",
            mode="fixture",
            fixture_json=fixture,
        )


def test_valid_header_only_candidate_table_is_an_empty_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    candidate_path = summary / "mito_heteroplasmy_candidates.tsv"
    columns = list(
        complete_candidate({"position": 10, "ref_base": "A", "alt_base": "C"})
    )
    pd.DataFrame(columns=columns).to_csv(candidate_path, sep="\t", index=False)
    monkeypatch.setattr(
        mvtool.requests,
        "Session",
        lambda: (_ for _ in ()).throw(AssertionError("network session created")),
    )
    fixture = Path(__file__).parent / "fixtures" / "mock_mvtool_annotations.json"

    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
        mode="fixture",
        fixture_json=fixture,
    )

    assert outputs["status"] == "not_applicable"
    metrics = metric_map(outputs["summary_path"])
    assert metrics["reason_code"] == "no_candidate_sites_observed"
    assert metrics["submitted_candidates"] == "0"
    assert metrics["network_request_attempted"] == "0"


def test_failed_upstream_status_blocks_stale_candidate_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    pd.DataFrame(
        [
            {"metric": "status", "value": "failed"},
            {"metric": "reason_code", "value": "allele_counting_failed"},
        ]
    ).to_csv(summary / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)
    monkeypatch.setattr(
        mvtool.requests,
        "Session",
        lambda: (_ for _ in ()).throw(AssertionError("network session created")),
    )

    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="STALE",
        species="human",
        mode="fixture",
        fixture_json=Path(__file__).parent / "fixtures" / "mock_mvtool_annotations.json",
    )

    metrics = metric_map(outputs["summary_path"])
    assert outputs["status"] == "failed"
    assert metrics["reason_code"] == "upstream_heteroplasmy_failed"
    assert metrics["upstream_heteroplasmy_reason_code"] == "allele_counting_failed"
    assert metrics["network_request_attempted"] == "0"


def test_missing_candidate_table_is_distinct_from_observed_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    (summary / "mito_heteroplasmy_candidates.tsv").unlink()
    monkeypatch.setattr(
        mvtool.requests,
        "Session",
        lambda: (_ for _ in ()).throw(AssertionError("network session created")),
    )

    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="MISSING",
        species="human",
        mode="fixture",
        fixture_json=Path(__file__).parent / "fixtures" / "mock_mvtool_annotations.json",
    )

    metrics = metric_map(outputs["summary_path"])
    assert outputs["status"] == "not_evaluable"
    assert metrics["reason_code"] == "candidate_table_missing"
    assert metrics["network_request_attempted"] == "0"


@pytest.mark.parametrize(
    ("returned_rows", "reason_code"),
    [
        (
            [
                {"Input": "m.10A>C", "Mitomap_status": "Reported"},
                {"Input": "m.10A>C", "Mitomap_status": "Reported"},
            ],
            "mvtool_duplicate_response_input",
        ),
        (
            [
                {"Input": "m.10A>C", "Mitomap_status": "Reported"},
                {"Input": "m.999A>G", "Mitomap_status": "Reported"},
            ],
            "mvtool_unexpected_response_input",
        ),
        ([{"Input": "m.10A>C", "Mitomap_status": "Reported"}], "mvtool_missing_response_input"),
        ([{"Mitomap_status": "Reported"}], "mvtool_missing_input_column"),
    ],
)
def test_invalid_network_response_inputs_are_unavailable(
    returned_rows: list[dict[str, object]],
    reason_code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_rows = [
        {"position": 10, "ref_base": "A", "alt_base": "C"},
        {"position": 20, "ref_base": "A", "alt_base": "G"},
    ]
    summary, figures, reports = prepare_case(tmp_path, candidate_rows)
    monkeypatch.setattr(
        requests.Session,
        "post",
        lambda self, *args, **kwargs: FakeResponse({"mseqdr": returned_rows}),
    )

    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
        mode="network",
        api_url="https://mock.invalid/mvtool",
    )

    assert outputs["status"] == "unavailable"
    assert metric_map(outputs["summary_path"])["reason_code"] == reason_code
    assert pd.read_csv(outputs["annot_path"], sep="\t").empty
    assert pd.read_csv(outputs["status_counts_path"], sep="\t").empty


def test_fixture_does_not_fabricate_a_missing_candidate_from_defaults(tmp_path: Path) -> None:
    summary, figures, reports = prepare_case(
        tmp_path,
        [{"position": 30, "ref_base": "A", "alt_base": "T"}],
    )
    fixture = Path(__file__).parent / "fixtures" / "mock_mvtool_annotations.json"

    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
        mode="fixture",
        fixture_json=fixture,
    )

    assert outputs["status"] == "unavailable"
    assert metric_map(outputs["summary_path"])["reason_code"] == "mvtool_missing_response_input"
    assert pd.read_csv(outputs["annot_path"], sep="\t").empty


def test_fixture_mseqdr_rejects_unexpected_input(tmp_path: Path) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    fixture = tmp_path / "unexpected_mvtool.json"
    fixture.write_text(
        json.dumps({"mseqdr": [{"Input": "m.99A>G", "Mitomap_status": "Reported"}]}),
        encoding="utf-8",
    )

    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
        mode="fixture",
        fixture_json=fixture,
    )

    assert outputs["status"] == "unavailable"
    assert metric_map(outputs["summary_path"])["reason_code"] == "mvtool_unexpected_response_input"
    assert pd.read_csv(outputs["annot_path"], sep="\t").empty


@pytest.mark.parametrize(
    ("behavior", "reason_code"),
    [("timeout", "mvtool_network_timeout"), ("malformed", "mvtool_malformed_response")],
)
def test_network_failures_return_unavailable(
    behavior: str, reason_code: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary, figures, reports = prepare_case(tmp_path)
    if behavior == "timeout":
        def post(*args, **kwargs):
            raise requests.Timeout("synthetic timeout")
    else:
        def post(*args, **kwargs):
            return FakeResponse({"mseqdr": {"not": "a list"}})
    monkeypatch.setattr(requests.Session, "post", post)
    outputs = mvtool.run_step(
        summary_dir=summary,
        figure_dir=figures,
        report_dir=reports,
        sample_id="S1",
        species="human",
        mode="network",
        api_url="https://mock.invalid/mvtool",
    )
    assert outputs["status"] == "unavailable"
    metrics = metric_map(outputs["summary_path"])
    assert metrics["reason_code"] == reason_code
    assert metrics["network_request_attempted"] == "1"
