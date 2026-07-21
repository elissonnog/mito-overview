#!/usr/bin/env python3
"""Assert the frozen v0.3.0 public-validation characterization oracle."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


EXPECTED_CASES = {
    ("GM11906", "lenient"): ("gm11906_lenient",),
    ("GM11906", "default"): ("gm11906_default_run1", "gm11906_default_run2"),
    ("GM11906", "strict"): ("gm11906_strict",),
    ("GM12878", "lenient"): ("gm12878_lenient",),
    ("GM12878", "default"): ("gm12878_default_run1", "gm12878_default_run2"),
    ("GM12878", "strict"): ("gm12878_strict",),
}
EXPECTED_GM11906_SOURCE_RUNS = ["SRR10804585", "SRR10804590", "SRR10804657"]
EXPECTED_GM11906_RAW_INPUT_LABELS = [
    "SRR10804585_R1",
    "SRR10804585_R2",
    "SRR10804590_R1",
    "SRR10804590_R2",
    "SRR10804657_R1",
    "SRR10804657_R2",
]


@dataclass
class Assertion:
    assertion_id: str
    verdict: str
    expected: str
    observed: str
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-root", required=True, type=Path)
    parser.add_argument("--oracle", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [
            {key: "" if value in (None, ".") else value for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]
    if not rows and path.name != "mito_heteroplasmy_candidates.tsv":
        raise ValueError(f"TSV contains no data rows: {path}")
    return rows


def metric_map(path: Path) -> dict[str, str]:
    rows = read_tsv(path)
    if not rows or set(rows[0]) != {"metric", "value"}:
        raise ValueError(f"Expected metric/value TSV: {path}")
    return {row["metric"]: row["value"] for row in rows}


def decimal_equal(left: str, right: str) -> bool:
    try:
        return Decimal(left) == Decimal(right)
    except InvalidOperation:
        return False


class Auditor:
    def __init__(self) -> None:
        self.rows: list[Assertion] = []

    def assert_value(
        self,
        assertion_id: str,
        expected: str,
        observed: object,
        *,
        numeric: bool = False,
        detail: str = "",
    ) -> None:
        expected_text = str(expected)
        observed_text = "" if observed is None else str(observed)
        passed = (
            decimal_equal(expected_text, observed_text)
            if numeric
            else expected_text == observed_text
        )
        self.rows.append(
            Assertion(
                assertion_id=assertion_id,
                verdict="PASS" if passed else "FAIL",
                expected=expected_text,
                observed=observed_text,
                detail=detail,
            )
        )

    def fail(self, assertion_id: str, detail: str) -> None:
        self.rows.append(Assertion(assertion_id, "FAIL", "available", "unavailable", detail))

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["assertion_id", "verdict", "expected", "observed", "detail"],
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(row.__dict__ for row in self.rows)


def exact_metric(
    audit: Auditor,
    prefix: str,
    metrics: dict[str, str],
    metric: str,
    expected: str,
    *,
    numeric: bool = False,
) -> None:
    if not expected:
        return
    audit.assert_value(
        f"{prefix}.{metric}",
        expected,
        metrics.get(metric),
        numeric=numeric,
    )


def assert_inventory(audit: Auditor, case_id: str, output: Path, oracle: dict[str, str]) -> None:
    expected_counts = {
        "summary_tsv_count": len(list((output / "summary").glob("*.tsv"))),
        "html_count": len(list((output / "report").glob("*.html"))),
        "png_count": len(list((output / "figures").glob("*.png"))),
    }
    for field, observed in expected_counts.items():
        audit.assert_value(
            f"{case_id}.inventory.{field}", oracle[field], observed, numeric=True
        )


def assert_marker(audit: Auditor, case_id: str, output: Path, oracle: dict[str, str]) -> None:
    candidates = read_tsv(output / "summary" / "mito_heteroplasmy_candidates.tsv")
    hits = [
        row
        for row in candidates
        if row.get("position") == "8344"
        and row.get("ref_base", "").upper() == "A"
        and row.get("alt_base", "").upper() == "G"
    ]
    audit.assert_value(f"{case_id}.m8344.present", oracle["m8344_present"], len(hits))
    if not hits:
        return
    row = hits[0]
    fields = {
        "m8344_callable_depth": "callable_depth",
        "m8344_alt_count": "alt_count",
        "m8344_alt_forward": "alt_forward",
        "m8344_alt_reverse": "alt_reverse",
        "m8344_alt_fraction": "alt_allele_fraction",
    }
    for oracle_field, table_field in fields.items():
        if oracle[oracle_field]:
            audit.assert_value(
                f"{case_id}.{oracle_field}",
                oracle[oracle_field],
                row.get(table_field),
                numeric=True,
            )
    if all(row.get(field) for field in ("alt_count", "alt_forward", "alt_reverse")):
        strand_sum = int(row["alt_forward"]) + int(row["alt_reverse"])
        audit.assert_value(
            f"{case_id}.m8344_strand_sum", row["alt_count"], strand_sum, numeric=True
        )

    if oracle["m8344_consequence_class"]:
        consequence = read_tsv(
            output / "summary" / "mito_variant_consequence_candidates.tsv"
        )
        consequence_hits = [
            item
            for item in consequence
            if item.get("position") == "8344"
            and item.get("ref_base", "").upper() == "A"
            and item.get("alt_base", "").upper() == "G"
        ]
        audit.assert_value(
            f"{case_id}.m8344.consequence_rows", "1", len(consequence_hits), numeric=True
        )
        if consequence_hits:
            consequence_row = consequence_hits[0]
            for oracle_field, table_field in (
                ("m8344_feature_label", "feature_label"),
                ("m8344_feature_class", "feature_class"),
                ("m8344_consequence_class", "consequence_class"),
            ):
                audit.assert_value(
                    f"{case_id}.{oracle_field}",
                    oracle[oracle_field],
                    consequence_row.get(table_field),
                )


def assert_statuses(audit: Auditor, case_id: str, summary: Path, oracle: dict[str, str]) -> None:
    specifications = (
        ("copy_number_status", "mito_copy_number_summary.tsv", "status"),
        ("phymer_status", "mito_phymer_haplogroup_summary.tsv", "status"),
        ("methylation_status", "mito_methylation_exploratory_summary.tsv", "status"),
        ("mvtool_status", "mito_mvtool_annotation_summary.tsv", "status"),
        ("numt_module_status", "mito_numt_qc_summary.tsv", "status"),
        (
            "numt_interpretation_status",
            "mito_numt_qc_summary.tsv",
            "numt_interpretation_status",
        ),
        ("numt_reason_code", "mito_numt_qc_summary.tsv", "reason_code"),
    )
    loaded: dict[str, dict[str, str]] = {}
    for oracle_field, filename, metric in specifications:
        if not oracle[oracle_field]:
            continue
        loaded.setdefault(filename, metric_map(summary / filename))
        audit.assert_value(
            f"{case_id}.status.{oracle_field}",
            oracle[oracle_field],
            loaded[filename].get(metric),
        )


def assert_longread_metrics(
    audit: Auditor, case_id: str, output: Path, oracle: dict[str, str]
) -> None:
    summary = output / "summary"
    qc = metric_map(summary / "mito_qc_summary.tsv")
    coseg = metric_map(summary / "mito_cosegregation_summary.tsv")
    deletion = metric_map(summary / "mito_deletion_summary.tsv")
    for field, metric, values, numeric in (
        ("mapped_reads", "mapped_reads", qc, True),
        ("primary_reads", "primary_reads", qc, True),
        ("supplementary_reads", "supplementary_reads", qc, True),
        ("mean_depth", "mean_depth", qc, True),
        ("median_depth", "median_depth", qc, True),
        ("selected_cosegregation_sites", "selected_sites", coseg, True),
        ("deletion_clusters", "candidate_deletion_clusters", deletion, True),
        ("deletion_query_names", "reads_with_large_deletion", deletion, True),
        (
            "supplementary_sa_query_names",
            "reads_with_supplementary_or_SA",
            deletion,
            True,
        ),
    ):
        exact_metric(audit, case_id, values, metric, oracle[field], numeric=numeric)

    provenance_path = (
        output
        / "provenance"
        / "GM12878_ONT_longread.fastq_subset.provenance.json"
    )
    payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    selection = payload.get("selection", {})
    audit.assert_value(
        f"{case_id}.source_records",
        oracle["source_records"],
        selection.get("source_records_seen"),
        numeric=True,
    )
    audit.assert_value(
        f"{case_id}.selected_names",
        oracle["selected_names"],
        selection.get("selected_query_names"),
        numeric=True,
    )
    audit.assert_value(
        f"{case_id}.selection_seed",
        "mito-overview-v0.3.0-GM12878-SRR18110025",
        selection.get("seed"),
    )


def assert_shortread_provenance(audit: Auditor, case_id: str, output: Path) -> None:
    provenance = output / "provenance"
    manifest_path = provenance / "GM11906_MERRF_shortread.alignment.provenance.json"
    libraries_path = provenance / "GM11906_MERRF_shortread.source_libraries.tsv"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    libraries = read_tsv(libraries_path)
    source_runs = [row.get("run_accession", "") for row in libraries]
    inputs = manifest.get("public_inputs", [])
    labels = sorted(
        str(record.get("label"))
        for record in inputs
        if isinstance(record, dict)
        and str(record.get("label", "")).startswith("SRR")
    )
    derivation = manifest.get("derivation", {})
    audit.assert_value(
        f"{case_id}.shortread.dataset_id",
        "GM11906_pooled_scATAC",
        manifest.get("dataset_id"),
    )
    audit.assert_value(
        f"{case_id}.shortread.derivation_id",
        "bwa-mem-samtools-sort-v1",
        derivation.get("derivation_id") if isinstance(derivation, dict) else None,
    )
    audit.assert_value(
        f"{case_id}.shortread.source_runs",
        repr(EXPECTED_GM11906_SOURCE_RUNS),
        repr(source_runs),
    )
    audit.assert_value(
        f"{case_id}.shortread.raw_input_labels",
        repr(EXPECTED_GM11906_RAW_INPUT_LABELS),
        repr(labels),
    )


def assert_output(
    audit: Auditor,
    case_id: str,
    dataset: str,
    output: Path,
    oracle: dict[str, str],
) -> None:
    try:
        summary = output / "summary"
        candidates = read_tsv(summary / "mito_heteroplasmy_candidates.tsv")
        heteroplasmy = metric_map(summary / "mito_heteroplasmy_summary.tsv")
        audit.assert_value(
            f"{case_id}.candidate_sites", oracle["candidate_sites"], len(candidates), numeric=True
        )
        for field, metric in (
            ("min_base_quality", "allele_min_base_quality"),
            ("min_mapping_quality", "allele_min_mapping_quality"),
            ("min_read_mean_quality", "allele_min_read_mean_quality"),
            ("accepted_observations", "accepted_observations"),
            ("excluded_observations", "excluded_observations"),
        ):
            audit.assert_value(
                f"{case_id}.{field}", oracle[field], heteroplasmy.get(metric), numeric=True
            )
        assert_marker(audit, case_id, output, oracle)
        assert_statuses(audit, case_id, summary, oracle)
        assert_inventory(audit, case_id, output, oracle)
        if dataset == "GM12878":
            assert_longread_metrics(audit, case_id, output, oracle)
        else:
            assert_shortread_provenance(audit, case_id, output)
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
        audit.fail(f"{case_id}.required_evidence", str(exc))


def main() -> None:
    args = parse_args()
    audit = Auditor()
    try:
        oracle_rows = read_tsv(args.oracle)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Cannot load public-validation oracle: {exc}") from exc
    oracle_by_key = {(row["dataset"], row["profile"]): row for row in oracle_rows}
    audit.assert_value(
        "oracle.profile_keys",
        repr(sorted(EXPECTED_CASES)),
        repr(sorted(oracle_by_key)),
    )

    outputs_root = args.matrix_root / "outputs"
    expected_output_names = sorted(name for names in EXPECTED_CASES.values() for name in names)
    observed_output_names = (
        sorted(path.name for path in outputs_root.iterdir() if path.is_dir())
        if outputs_root.is_dir()
        else []
    )
    audit.assert_value(
        "matrix.output_directories",
        repr(expected_output_names),
        repr(observed_output_names),
    )

    try:
        profile_rows = read_tsv(args.matrix_root / "filter_profile_results.tsv")
        profiles = {(row["dataset"], row["profile"]): row for row in profile_rows}
        audit.assert_value(
            "matrix.filter_profile_keys",
            repr(sorted(EXPECTED_CASES)),
            repr(sorted(profiles)),
        )
    except (FileNotFoundError, ValueError) as exc:
        profiles = {}
        audit.fail("matrix.filter_profiles", str(exc))

    for key, case_ids in EXPECTED_CASES.items():
        oracle = oracle_by_key.get(key)
        if oracle is None:
            continue
        profile = profiles.get(key)
        if profile is not None:
            for oracle_field, profile_field in (
                ("min_base_quality", "min_base_quality"),
                ("min_mapping_quality", "min_mapping_quality"),
                ("min_read_mean_quality", "min_read_mean_quality"),
                ("candidate_sites", "candidate_sites"),
                ("accepted_observations", "accepted_observations"),
                ("excluded_observations", "excluded_observations"),
                ("m8344_present", "m8344_A_G_present"),
                ("m8344_alt_fraction", "m8344_A_G_alt_allele_fraction"),
            ):
                if oracle[oracle_field]:
                    audit.assert_value(
                        f"filter.{key[0]}.{key[1]}.{oracle_field}",
                        oracle[oracle_field],
                        profile.get(profile_field),
                        numeric=True,
                    )
        for case_id in case_ids:
            assert_output(
                audit,
                case_id,
                key[0],
                outputs_root / case_id,
                oracle,
            )

    audit.write(args.report)
    failures = [row for row in audit.rows if row.verdict != "PASS"]
    if failures:
        for row in failures:
            print(
                f"[public-oracle] FAIL {row.assertion_id}: expected={row.expected!r} "
                f"observed={row.observed!r} {row.detail}",
                file=sys.stderr,
            )
        raise SystemExit(f"Public-validation oracle failed {len(failures)} assertion(s)")
    print(f"[public-oracle] PASS assertions={len(audit.rows)} report={args.report}")


if __name__ == "__main__":
    main()
