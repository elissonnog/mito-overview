from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_validation_packet_v0.3.0.py"
SPEC = importlib.util.spec_from_file_location("build_validation_packet_v030", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
packet_builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packet_builder)


def write_cases(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "case_id",
                "category",
                "input_available",
                "expected_available",
                "verdict",
                "detail",
            ),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def required_pass_rows() -> list[dict[str, str]]:
    return [
        {
            "case_id": case_id,
            "category": "test",
            "input_available": "1",
            "expected_available": "1",
            "verdict": "PASS",
            "detail": "known-answer evidence available",
        }
        for case_id in sorted(packet_builder.REQUIRED_PASS_CASES)
    ]


def test_release_case_gate_accepts_complete_pass_set(tmp_path: Path) -> None:
    path = tmp_path / "cases.tsv"
    rows = required_pass_rows()
    write_cases(path, rows)
    count, verdicts = packet_builder.validate_cases(path)
    assert count == len(rows)
    assert verdicts["PASS"] == len(rows)


def test_release_case_gate_rejects_missing_required_case(tmp_path: Path) -> None:
    path = tmp_path / "cases.tsv"
    rows = required_pass_rows()[1:]
    write_cases(path, rows)
    with pytest.raises(ValueError, match="Required release cases are missing"):
        packet_builder.validate_cases(path)


def test_release_case_gate_rejects_nonpassing_required_case(tmp_path: Path) -> None:
    path = tmp_path / "cases.tsv"
    rows = required_pass_rows()
    rows[0]["verdict"] = "FAIL"
    write_cases(path, rows)
    with pytest.raises(ValueError, match="Required release cases did not pass"):
        packet_builder.validate_cases(path)


def test_release_case_gate_rejects_unsupported_pass(tmp_path: Path) -> None:
    path = tmp_path / "cases.tsv"
    rows = required_pass_rows()
    rows[0]["input_available"] = "0"
    write_cases(path, rows)
    with pytest.raises(ValueError, match="PASS case lacks input or expected evidence"):
        packet_builder.validate_cases(path)
