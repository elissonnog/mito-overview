from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import requests

from mito_overview.steps import mito_mvtool_annotation as mvtool

from ._helpers import metric_map


def prepare_case(root: Path) -> tuple[Path, Path, Path]:
    summary = root / "summary"
    figures = root / "figures"
    reports = root / "reports"
    summary.mkdir(parents=True)
    pd.DataFrame(
        [{"position": 10, "ref_base": "A", "alt_base": "C", "callable_depth": 100, "alt_count": 25}]
    ).to_csv(summary / "mito_heteroplasmy_candidates.tsv", sep="\t", index=False)
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
