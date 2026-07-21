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
EXPECTED_TITLE = "mito-overview v0.3.0"
EXPECTED_VERSION = "0.3.0"
EXPECTED_UPLOAD_TYPE = "software"
EXPECTED_LICENSE = "mit"
EXPECTED_PUBLICATION_DATE = "2026-07-20"
EXPECTED_REPOSITORY = "https://github.com/elissonnog/mito-overview"
EXPECTED_CREATORS = (
    ("Lopes, Elisson", "Medical College of Wisconsin"),
    ("Gai, Xiaowu", "Medical College of Wisconsin"),
)
PRESERVED_METADATA_FIELDS = (
    "title",
    "upload_type",
    "description",
    "creators",
    "license",
    "version",
    "publication_date",
    "related_identifiers",
    "keywords",
)


def require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    if re.search(r"(?i)(?:<[^>]+>|\b(?:TBD|TODO|TBA|UNRESERVED|PLACEHOLDER)\b)", value):
        raise ValueError(f"{label} contains placeholder text")
    return value.strip()


def sanitize_release_metadata(metadata: object) -> dict[str, object]:
    """Validate the v0.3.0 software identity and retain only public metadata."""

    source = require_object(metadata, "Zenodo metadata")
    expected_scalars = {
        "title": EXPECTED_TITLE,
        "upload_type": EXPECTED_UPLOAD_TYPE,
        "license": EXPECTED_LICENSE,
        "version": EXPECTED_VERSION,
        "publication_date": EXPECTED_PUBLICATION_DATE,
    }
    sanitized: dict[str, object] = {}
    for field, expected in expected_scalars.items():
        observed = _require_nonempty_string(source.get(field), f"Zenodo metadata {field}")
        if observed.lower() != expected.lower():
            raise ValueError(
                f"Zenodo metadata {field} does not match v0.3.0: {observed!r} != {expected!r}"
            )
        sanitized[field] = observed

    sanitized["description"] = _require_nonempty_string(
        source.get("description"), "Zenodo metadata description"
    )

    creators = source.get("creators")
    if not isinstance(creators, list) or len(creators) != len(EXPECTED_CREATORS):
        raise ValueError("Zenodo metadata creators must contain the two v0.3.0 creators")
    sanitized_creators: list[dict[str, str]] = []
    for index, (creator, expected) in enumerate(zip(creators, EXPECTED_CREATORS, strict=True)):
        creator_object = require_object(creator, f"Zenodo creator {index}")
        name = _require_nonempty_string(creator_object.get("name"), f"Zenodo creator {index} name")
        affiliation = _require_nonempty_string(
            creator_object.get("affiliation"), f"Zenodo creator {index} affiliation"
        )
        if (name, affiliation) != expected:
            raise ValueError(
                f"Zenodo creator {index} does not match v0.3.0: "
                f"{(name, affiliation)!r} != {expected!r}"
            )
        retained = {"name": name, "affiliation": affiliation}
        if "orcid" in creator_object:
            retained["orcid"] = _require_nonempty_string(
                creator_object["orcid"], f"Zenodo creator {index} ORCID"
            )
        sanitized_creators.append(retained)
    sanitized["creators"] = sanitized_creators

    related = source.get("related_identifiers")
    if not isinstance(related, list):
        raise ValueError("Zenodo metadata related_identifiers must be a list")
    repository_links: list[dict[str, str]] = []
    for index, item in enumerate(related):
        related_object = require_object(item, f"Zenodo related identifier {index}")
        identifier = _require_nonempty_string(
            related_object.get("identifier"), f"Zenodo related identifier {index} identifier"
        )
        relation = _require_nonempty_string(
            related_object.get("relation"), f"Zenodo related identifier {index} relation"
        )
        retained = {"identifier": identifier, "relation": relation}
        for optional in ("scheme", "resource_type"):
            if optional in related_object:
                retained[optional] = _require_nonempty_string(
                    related_object[optional],
                    f"Zenodo related identifier {index} {optional}",
                )
        repository_links.append(retained)
    matching_repository = [
        item
        for item in repository_links
        if item["identifier"] == EXPECTED_REPOSITORY
        and item["relation"] == "isSupplementTo"
    ]
    if len(matching_repository) != 1:
        raise ValueError(
            "Zenodo metadata must contain one isSupplementTo related identifier for the repository"
        )
    sanitized["related_identifiers"] = repository_links

    keywords = source.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("Zenodo metadata keywords must be a nonempty list")
    sanitized["keywords"] = [
        _require_nonempty_string(value, f"Zenodo keyword {index}")
        for index, value in enumerate(keywords)
    ]
    return sanitized


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

    release_metadata = sanitize_release_metadata(metadata)
    timestamp = captured_utc or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "1.1",
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
                **release_metadata,
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
    sanitize_release_metadata(metadata)
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
