#!/usr/bin/env python3
"""Assert the frozen v0.3.0 public-validation characterization oracle."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validation_fingerprints_v0_3_0 import (
    FINGERPRINT_FIELDS,
    summary_contract_fingerprints,
)


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

MODULE_STATES = frozenset(
    {
        "ok",
        "not_configured",
        "not_applicable",
        "not_evaluable",
        "unavailable",
        "failed",
    }
)
MODULE_STATUS_SPECS = (
    ("mito_qc_module_status", "mito_qc_summary.tsv"),
    ("heteroplasmy_module_status", "mito_heteroplasmy_summary.tsv"),
    ("deletions_module_status", "mito_deletion_summary.tsv"),
    ("copy_number_module_status", "mito_copy_number_summary.tsv"),
    ("feature_annotation_module_status", "mito_feature_annotation_summary.tsv"),
    ("cosegregation_module_status", "mito_cosegregation_summary.tsv"),
    ("gene_summary_module_status", "mito_gene_summary_run_summary.tsv"),
    ("numt_qc_module_status", "mito_numt_qc_summary.tsv"),
    ("identity_qc_module_status", "mito_identity_qc_summary.tsv"),
    ("variant_consequence_module_status", "mito_variant_consequence_summary.tsv"),
    ("circularity_qc_module_status", "mito_circularity_qc_summary.tsv"),
    (
        "methylation_exploratory_module_status",
        "mito_methylation_exploratory_summary.tsv",
    ),
    ("phymer_haplogroup_module_status", "mito_phymer_haplogroup_summary.tsv"),
    ("mvtool_annotation_module_status", "mito_mvtool_annotation_summary.tsv"),
)
MODULE_STATUS_FIELDS = tuple(field for field, _ in MODULE_STATUS_SPECS)
INTERPRETATION_STATUS_FIELDS = ("numt_interpretation_status",)
REQUIRED_STATUS_FIELDS = MODULE_STATUS_FIELDS + INTERPRETATION_STATUS_FIELDS
NUMT_INTERPRETATION_REASON_FIELD = "numt_interpretation_reason_code"
FEATURE_ANNOTATION_SUCCESS_COLUMNS = frozenset(
    {
        "feature_class",
        "feature_label",
        "candidate_sites",
        "mean_alt_allele_fraction",
    }
)


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


def read_oracle(path: Path) -> list[dict[str, str]]:
    """Load the oracle after validating its closed status-field contract."""

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
        if len(fieldnames) != len(set(fieldnames)):
            raise ValueError("Oracle contains duplicate column names")
        observed_status_fields = {
            field for field in fieldnames if field.endswith("_status")
        }
        expected_status_fields = set(REQUIRED_STATUS_FIELDS)
        if observed_status_fields != expected_status_fields:
            missing = sorted(expected_status_fields - observed_status_fields)
            unexpected = sorted(observed_status_fields - expected_status_fields)
            raise ValueError(
                "Oracle status columns do not match the required closed set: "
                f"missing={missing or 'none'} unexpected={unexpected or 'none'}"
            )
        if NUMT_INTERPRETATION_REASON_FIELD not in fieldnames:
            raise ValueError(
                f"Oracle is missing {NUMT_INTERPRETATION_REASON_FIELD}"
            )
        rows = [
            {key: "" if value in (None, ".") else value for key, value in row.items()}
            for row in reader
        ]

    if not rows:
        raise ValueError("Oracle contains no data rows")
    for row_number, row in enumerate(rows, start=2):
        for field in FINGERPRINT_FIELDS:
            value = row.get(field, "").strip()
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(
                    f"Oracle row {row_number} has invalid {field}={value!r}"
                )
        for field in REQUIRED_STATUS_FIELDS:
            value = row.get(field, "").strip()
            if not value:
                raise ValueError(
                    f"Oracle row {row_number} has blank required status {field}"
                )
            if value not in MODULE_STATES:
                raise ValueError(
                    f"Oracle row {row_number} has invalid {field}={value!r}"
                )
        reason = row.get(NUMT_INTERPRETATION_REASON_FIELD, "").strip()
        if not reason:
            raise ValueError(
                f"Oracle row {row_number} has blank "
                f"{NUMT_INTERPRETATION_REASON_FIELD}"
            )
    return rows


def metric_map(path: Path) -> dict[str, str]:
    rows = read_tsv(path)
    if not rows or set(rows[0]) != {"metric", "value"}:
        raise ValueError(f"Expected metric/value TSV: {path}")
    metrics: dict[str, str] = {}
    for row in rows:
        metric = row["metric"].strip()
        if not metric:
            raise ValueError(f"Blank metric key in {path}")
        if metric in metrics:
            raise ValueError(f"Duplicate metric key {metric!r} in {path}")
        metrics[metric] = row["value"].strip()
    return metrics


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


def assert_summary_contract(
    audit: Auditor,
    case_id: str,
    summary: Path,
    oracle: dict[str, str],
) -> None:
    observed = summary_contract_fingerprints(summary)
    for field in FINGERPRINT_FIELDS:
        audit.assert_value(
            f"{case_id}.{field}",
            oracle[field],
            observed[field],
            detail="versioned canonical SHA-256 release contract",
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


def feature_annotation_status(path: Path) -> str:
    """Resolve the successful feature table without inventing a biological state."""

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
    if set(fieldnames) == {"metric", "value"}:
        metrics = metric_map(path)
        status = metrics.get("status", "")
        if not status:
            raise ValueError(f"Missing status metric in {path}")
        return status
    if FEATURE_ANNOTATION_SUCCESS_COLUMNS.issubset(fieldnames):
        return "ok"
    raise ValueError(
        f"Feature-annotation output has neither a status table nor the successful schema: {path}"
    )


def assert_statuses(
    audit: Auditor,
    case_id: str,
    summary: Path,
    oracle: dict[str, str],
) -> None:
    loaded: dict[str, dict[str, str]] = {}
    observed_module_statuses: dict[str, str] = {}
    for oracle_field, filename in MODULE_STATUS_SPECS:
        expected = oracle[oracle_field]
        path = summary / filename
        if oracle_field == "feature_annotation_module_status":
            observed = feature_annotation_status(path)
        else:
            loaded.setdefault(filename, metric_map(path))
            if "status" not in loaded[filename]:
                raise ValueError(f"Missing status metric in {path}")
            observed = loaded[filename]["status"]
        observed_module_statuses[oracle_field] = observed
        detail = ""
        if observed not in MODULE_STATES:
            detail = f"observed status is outside the allowed vocabulary {sorted(MODULE_STATES)}"
        audit.assert_value(
            f"{case_id}.module_status.{oracle_field}",
            expected,
            observed,
            detail=detail,
        )

    numt_metrics = loaded["mito_numt_qc_summary.tsv"]
    numt_module_status = observed_module_statuses["numt_qc_module_status"]
    expected_interpretation = oracle["numt_interpretation_status"]
    expected_reason = oracle[NUMT_INTERPRETATION_REASON_FIELD]
    if numt_module_status == "not_applicable":
        # The short-read status-only page predates a nested interpretation metric.
        # Module gating makes the interpretation explicitly not applicable.
        observed_interpretation = numt_metrics.get(
            "numt_interpretation_status", "not_applicable"
        )
        observed_reason = numt_metrics.get(
            "reason_code", "module_not_applicable"
        )
    else:
        if "numt_interpretation_status" not in numt_metrics:
            raise ValueError(
                f"Missing numt_interpretation_status metric in "
                f"{summary / 'mito_numt_qc_summary.tsv'}"
            )
        if "reason_code" not in numt_metrics:
            raise ValueError(
                f"Missing NUMT interpretation reason_code metric in "
                f"{summary / 'mito_numt_qc_summary.tsv'}"
            )
        observed_interpretation = numt_metrics["numt_interpretation_status"]
        observed_reason = numt_metrics["reason_code"]
    audit.assert_value(
        f"{case_id}.interpretation_status.numt_interpretation_status",
        expected_interpretation,
        observed_interpretation,
    )
    audit.assert_value(
        f"{case_id}.interpretation_status.{NUMT_INTERPRETATION_REASON_FIELD}",
        expected_reason,
        observed_reason,
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
        assert_summary_contract(audit, case_id, summary, oracle)
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
        oracle_rows = read_oracle(args.oracle)
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
