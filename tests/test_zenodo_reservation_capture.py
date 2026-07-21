from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "capture_zenodo_reservation.py"
SPEC = importlib.util.spec_from_file_location("capture_zenodo_reservation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
capture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = capture
SPEC.loader.exec_module(capture)

PACKET_SCRIPT = Path(__file__).parents[1] / "scripts" / "build_validation_packet_v0.3.0.py"
PACKET_SPEC = importlib.util.spec_from_file_location(
    "build_validation_packet_for_zenodo_test", PACKET_SCRIPT
)
assert PACKET_SPEC is not None and PACKET_SPEC.loader is not None
packet_builder = importlib.util.module_from_spec(PACKET_SPEC)
sys.modules[PACKET_SPEC.name] = packet_builder
PACKET_SPEC.loader.exec_module(packet_builder)


RECORD_ID = 12345678
DOI = f"10.5281/zenodo.{RECORD_ID}"
API_URL = f"https://zenodo.org/api/deposit/depositions/{RECORD_ID}"


def deposition_response() -> dict[str, object]:
    return {
        "id": RECORD_ID,
        "record_id": RECORD_ID,
        "links": {"self": API_URL, "bucket": "not retained"},
        "metadata": {
            "prereserve_doi": {"doi": DOI, "recid": RECORD_ID},
            "title": "not retained",
        },
        "state": "unsubmitted",
        "submitted": False,
        "owner": 999,
    }


class FakeResponse:
    def __init__(self, payload: object, status_code: int) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("POST", url, kwargs))
        return self.response

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("GET", url, kwargs))
        return self.response


def test_sanitized_evidence_is_exact_and_secret_free() -> None:
    evidence = capture.sanitize_deposition(
        deposition_response(), captured_utc="2026-07-20T12:00:00+00:00"
    )
    assert evidence["doi"] == DOI
    assert evidence["record_id"] == RECORD_ID
    assert set(evidence) == {
        "schema_version",
        "evidence_type",
        "source",
        "captured_utc",
        "reservation_status",
        "doi",
        "record_id",
        "zenodo_api_url",
        "deposition_response",
    }
    serialized = json.dumps(evidence).lower()
    assert "owner" not in serialized
    assert "token" not in serialized
    assert "not retained" not in serialized


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("record_id", None, "positive record_id"),
        ("id", RECORD_ID + 1, "id and record_id"),
        ("state", "done", "unpublished draft"),
        ("submitted", True, "unpublished draft"),
    ],
)
def test_sanitizer_rejects_invalid_draft_identity(
    field: str, value: object, message: str
) -> None:
    response = deposition_response()
    response[field] = value
    with pytest.raises(ValueError, match=message):
        capture.sanitize_deposition(response)


def test_request_uses_bearer_header_without_url_token() -> None:
    session = FakeSession(FakeResponse(deposition_response(), 200))
    observed = capture.request_deposition(
        session, action="retrieve", token="test-secret", record_id=RECORD_ID
    )
    assert observed["record_id"] == RECORD_ID
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == API_URL
    assert "test-secret" not in url
    assert kwargs["headers"]["Authorization"] == "Bearer test-secret"


def test_create_requires_metadata_and_expected_status() -> None:
    session = FakeSession(FakeResponse(deposition_response(), 201))
    payload = {"metadata": {"prereserve_doi": True}}
    capture.request_deposition(
        session, action="create", token="test-secret", metadata=payload
    )
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "https://zenodo.org/api/deposit/depositions"
    assert kwargs["json"] == payload


def test_write_evidence_is_no_clobber(tmp_path: Path) -> None:
    path = tmp_path / "reservation.json"
    evidence = capture.sanitize_deposition(deposition_response())
    capture.write_evidence(path, evidence)
    assert json.loads(path.read_text(encoding="utf-8"))["doi"] == DOI
    with pytest.raises(FileExistsError, match="overwrite"):
        capture.write_evidence(path, evidence)


def test_captured_evidence_satisfies_packet_contract(tmp_path: Path) -> None:
    path = tmp_path / "reservation.json"
    capture.write_evidence(path, capture.sanitize_deposition(deposition_response()))
    validated = packet_builder.validate_zenodo_reservation_evidence(path, DOI)
    assert validated["record_id"] == RECORD_ID


def test_tracked_metadata_requests_reservation() -> None:
    path = (
        Path(__file__).parents[1]
        / "resources"
        / "zenodo"
        / "mito_overview_v0.3.0_draft.json"
    )
    payload = capture.load_create_metadata(path)
    assert payload["metadata"]["prereserve_doi"] is True
