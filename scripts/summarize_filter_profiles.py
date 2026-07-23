#!/usr/bin/env python3
"""Summarize descriptive allele-filter profiles from public validation runs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


EXPECTED_THRESHOLDS = {
    "lenient": ("0", "0", "0"),
    "default": ("13", "20", "10"),
    "strict": ("20", "30", "15"),
}


def normalized_number(value: str) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else format(number, "g")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "case",
        nargs="+",
        help="CASE_ID=DATASET:PROFILE:OUTPUT_DIR",
    )
    return parser.parse_args()


def metric_map(path: Path) -> dict[str, str]:
    table = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    return dict(zip(table["metric"], table["value"]))


def summarize(case_id: str, dataset: str, profile: str, output_dir: Path) -> dict[str, object]:
    summary_dir = output_dir / "summary"
    candidates = pd.read_csv(
        summary_dir / "mito_heteroplasmy_candidates.tsv",
        sep="\t",
        dtype=str,
        keep_default_na=False,
    )
    metrics = metric_map(summary_dir / "mito_heteroplasmy_summary.tsv")
    observed_thresholds = tuple(
        normalized_number(metrics.get(metric, "nan"))
        for metric in (
            "allele_min_base_quality",
            "allele_min_mapping_quality",
            "allele_min_read_mean_quality",
        )
    )
    expected_thresholds = EXPECTED_THRESHOLDS.get(profile)
    if expected_thresholds is None:
        raise ValueError(f"Unsupported filter profile: {profile}")
    if observed_thresholds != expected_thresholds:
        raise ValueError(
            f"Filter profile {case_id} did not apply {expected_thresholds}: "
            f"observed {observed_thresholds}"
        )
    site = candidates[
        (pd.to_numeric(candidates["position"], errors="coerce") == 8344)
        & (candidates["ref_base"].str.upper() == "A")
        & (candidates["alt_base"].str.upper() == "G")
    ]
    site_fraction = site.iloc[0]["alt_allele_fraction"] if len(site) == 1 else ""
    return {
        "case_id": case_id,
        "dataset": dataset,
        "profile": profile,
        "min_base_quality": metrics.get("allele_min_base_quality", ""),
        "min_mapping_quality": metrics.get("allele_min_mapping_quality", ""),
        "min_read_mean_quality": metrics.get("allele_min_read_mean_quality", ""),
        "candidate_sites": len(candidates),
        "accepted_observations": metrics.get("accepted_observations", ""),
        "excluded_observations": metrics.get("excluded_observations", ""),
        "m8344_A_G_present": int(len(site) == 1),
        "m8344_A_G_alt_allele_fraction": site_fraction,
    }


def main() -> None:
    args = parse_args()
    rows: list[dict[str, object]] = []
    for specification in args.case:
        try:
            case_id, value = specification.split("=", 1)
            dataset, profile, path = value.split(":", 2)
        except ValueError as exc:
            raise SystemExit(f"Invalid case specification: {specification}") from exc
        rows.append(summarize(case_id, dataset, profile, Path(path)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, sep="\t", index=False, lineterminator="\n")


if __name__ == "__main__":
    main()
