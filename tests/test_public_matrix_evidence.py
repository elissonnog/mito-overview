from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).parents[1]
SUMMARY_SCRIPT = REPO_ROOT / "scripts" / "summarize_filter_profiles.py"
HASH_SCRIPT = REPO_ROOT / "scripts" / "hash_validation_inputs.py"
SPEC = importlib.util.spec_from_file_location("summarize_filter_profiles", SUMMARY_SCRIPT)
assert SPEC is not None and SPEC.loader is not None
summary_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary_module)


def write_profile_output(root: Path, thresholds: tuple[int, int, int]) -> Path:
    summary = root / "summary"
    summary.mkdir(parents=True)
    pd.DataFrame(
        [
            {"metric": "allele_min_base_quality", "value": thresholds[0]},
            {"metric": "allele_min_mapping_quality", "value": thresholds[1]},
            {"metric": "allele_min_read_mean_quality", "value": thresholds[2]},
            {"metric": "accepted_observations", "value": 10},
            {"metric": "excluded_observations", "value": 2},
        ]
    ).to_csv(summary / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)
    pd.DataFrame(
        columns=["position", "ref_base", "alt_base", "alt_allele_fraction"]
    ).to_csv(summary / "mito_heteroplasmy_candidates.tsv", sep="\t", index=False)
    return root


@pytest.mark.parametrize(
    ("profile", "thresholds"),
    [
        ("lenient", (0, 0, 0)),
        ("default", (13, 20, 10)),
        ("strict", (20, 30, 15)),
    ],
)
def test_filter_profile_summary_requires_exact_thresholds(
    profile: str, thresholds: tuple[int, int, int], tmp_path: Path
) -> None:
    output = write_profile_output(tmp_path / profile, thresholds)
    row = summary_module.summarize("case", "dataset", profile, output)
    assert str(row["min_base_quality"]) == str(thresholds[0])
    assert str(row["min_mapping_quality"]) == str(thresholds[1])
    assert str(row["min_read_mean_quality"]) == str(thresholds[2])


def test_filter_profile_summary_rejects_ignored_settings(tmp_path: Path) -> None:
    output = write_profile_output(tmp_path / "wrong", (13, 20, 10))
    with pytest.raises(ValueError, match="did not apply"):
        summary_module.summarize("strict-case", "dataset", "strict", output)


def test_input_hash_manifest_is_relative_sorted_and_portable(tmp_path: Path) -> None:
    cache = tmp_path / "cache with spaces"
    (cache / "b").mkdir(parents=True)
    (cache / "a.txt").write_text("alpha\n", encoding="utf-8")
    (cache / "b" / "z.txt").write_text("zeta\n", encoding="utf-8")
    output = tmp_path / "inputs.sha256"
    subprocess.run(
        ["python3", str(HASH_SCRIPT), str(cache), str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = output.read_text(encoding="utf-8").splitlines()
    assert [line.split("  ", 1)[1] for line in lines] == ["a.txt", "b/z.txt"]
    assert all(len(line.split("  ", 1)[0]) == 64 for line in lines)
