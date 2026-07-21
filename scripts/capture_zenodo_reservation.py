#!/usr/bin/env python3
"""Create or retrieve a Zenodo draft and save sanitized DOI-reservation evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


PRODUCTION_API = "https://zenodo.org/api"
TOKEN_ENV = "ZENODO_ACCESS_TOKEN"


def require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def sanitize_deposition(
    response: object,
    *,
    captured_utc: str | None = None,
) -> dict[str, object]:
    deposition = require_object(response, "Zenodo deposition response")
    record_id = deposition.get("record_id")
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
        raise ValueError("Zenodo draft is missing a positive record_id")
    if deposition.get("id") != record_id:
        raise ValueError("Zenodo deposition id and record_id do not match")
    if deposition.get("state") != "unsubmitted" or deposition.get("submitted") is not False:
        raise ValueError("Zenodo deposition is not an unpublished draft")

    metadata = require_object(deposition.get("metadata"), "Zenodo metadata")
    reservation = require_object(metadata.get("prereserve_doi"), "Zenodo prereserve_doi")
    doi = reservation.get("doi")
    if doi != f"10.5281/zenodo.{record_id}" or reservation.get("recid") != record_id:
        raise ValueError("Zenodo DOI reservation is not tied to the draft record")

    links = require_object(deposition.get("links"), "Zenodo links")
    api_url = f"{PRODUCTION_API}/deposit/depositions/{record_id}"
    if links.get("self") != api_url:
        raise ValueError("Zenodo deposition self link is not the canonical production API URL")

    timestamp = captured_utc or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "1.0",
        "evidence_type": "zenodo_doi_reservation",
        "source": "authenticated_zenodo_deposition_api",
        "captured_utc": timestamp,
        "reservation_status": "reserved",
        "doi": doi,
        "record_id": record_id,
        "zenodo_api_url": api_url,
        "deposition_response": {
            "id": record_id,
            "record_id": record_id,
            "links": {"self": api_url},
            "metadata": {
                "prereserve_doi": {"doi": doi, "recid": record_id},
            },
            "state": "unsubmitted",
            "submitted": False,
        },
    }


def request_deposition(
    session: requests.Session,
    *,
    action: str,
    token: str,
    metadata: dict[str, Any] | None = None,
    record_id: int | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if action == "create":
        if metadata is None:
            raise ValueError("Create mode requires deposition metadata")
        headers["Content-Type"] = "application/json"
        response = session.post(
            f"{PRODUCTION_API}/deposit/depositions",
            headers=headers,
            json=metadata,
            timeout=60,
        )
        expected_status = 201
    else:
        if record_id is None or record_id <= 0:
            raise ValueError("Retrieve mode requires a positive record ID")
        response = session.get(
            f"{PRODUCTION_API}/deposit/depositions/{record_id}",
            headers=headers,
            timeout=60,
        )
        expected_status = 200
    if response.status_code != expected_status:
        raise RuntimeError(
            f"Zenodo API returned HTTP {response.status_code}; no evidence file was written"
        )
    try:
        return require_object(response.json(), "Zenodo API response")
    except (requests.JSONDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Zenodo API response was not valid JSON") from error


def write_evidence(path: Path, evidence: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite evidence file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"Temporary evidence path already exists: {temporary}")
    temporary.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_create_metadata(path: Path) -> dict[str, Any]:
    payload = require_object(json.loads(path.read_text(encoding="utf-8")), "Metadata file")
    metadata = require_object(payload.get("metadata"), "Metadata file metadata")
    if metadata.get("prereserve_doi") is not True:
        raise ValueError("Create metadata must request prereserve_doi=true")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    create = subparsers.add_parser("create", help="Create one unpublished production draft")
    create.add_argument("--metadata", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    create.add_argument(
        "--confirm-create-production-draft",
        action="store_true",
        help="Required guard acknowledging that this creates a real Zenodo draft.",
    )

    retrieve = subparsers.add_parser("retrieve", help="Retrieve an existing draft")
    retrieve.add_argument("--record-id", required=True, type=int)
    retrieve.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get(TOKEN_ENV, "")
    if not token or re.search(r"[\x00-\x20]", token):
        raise SystemExit(f"Set {TOKEN_ENV} to a nonempty token without whitespace")
    output = args.output.expanduser().resolve()
    if output.exists() or output.is_symlink():
        raise SystemExit(f"Refusing to overwrite evidence file: {output}")

    if args.action == "create":
        if not args.confirm_create_production_draft:
            raise SystemExit("Create mode requires --confirm-create-production-draft")
        metadata = load_create_metadata(args.metadata.expanduser().resolve())
        response = request_deposition(
            requests.Session(), action="create", token=token, metadata=metadata
        )
    else:
        response = request_deposition(
            requests.Session(), action="retrieve", token=token, record_id=args.record_id
        )
    evidence = sanitize_deposition(response)
    write_evidence(output, evidence)
    print(f"record_id={evidence['record_id']}")
    print(f"doi={evidence['doi']}")
    print(f"evidence={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
