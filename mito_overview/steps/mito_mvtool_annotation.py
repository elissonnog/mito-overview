"""Optional human mtDNA external annotation enrichment via the MSeqDR mvTool API."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
from urllib.parse import unquote, urlparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import validate_candidate_table

DEFAULT_FIELDS = [
    "Input",
    "HGVS_g",
    "AF_M1",
    "AF_mitomap",
    "Mitomap_status",
    "Mitomap_Disease",
    "Heteroplasmy",
    "Homoplasmy",
    "HmtDB",
    "HmtDB_disease",
    "NT_variability",
    "AA_variability",
    "M1_cnt",
    "Mitomap_cnt",
]
STATUS_COLUMNS = ["Mitomap_status", "candidate_sites"]
DISEASE_COLUMNS = ["Reported_association", "candidate_sites", "supporting_statuses"]
POP_BIN_COLUMNS = ["AF_M1_bin", "candidate_sites"]
SUMMARY_COLUMNS = ["metric", "value"]
BATCH_COLUMNS = ["batch", "variants_submitted", "records_returned", "http_status"]
ANNOTATION_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "callable_depth",
    "depth",
    "alt_count",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "mvtool_input",
    *DEFAULT_FIELDS,
    "Mitomap_status_normalized",
    "Mitomap_Disease_normalized",
    "HmtDB_disease_normalized",
]


class MvtoolResponseValidationError(ValueError):
    """A nonfatal violation of the submitted-to-returned Input contract."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--species", required=True)
    parser.add_argument("--mode", choices=("disabled", "fixture", "network"), default="disabled")
    parser.add_argument("--api-url", default="")
    parser.add_argument("--fixture-json")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=100)
    return parser


def load_table(path: str | Path, *, columns: list[str] | None = None) -> pd.DataFrame:
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, sep="\t")
    return pd.DataFrame(columns=columns or [])


def write_status_page(
    *,
    report_path: Path,
    summary_path: Path,
    annot_path: Path,
    batch_log_path: Path,
    sample_id: str,
    status_rows: list[dict[str, object]],
    message: str,
) -> dict[str, Path | str]:
    summary_df = pd.DataFrame(status_rows)
    summary_df.to_csv(summary_path, sep="\t", index=False)
    pd.DataFrame(columns=ANNOTATION_COLUMNS).to_csv(annot_path, sep="\t", index=False)
    pd.DataFrame(columns=BATCH_COLUMNS).to_csv(batch_log_path, sep="\t", index=False)
    status_counts_path = summary_path.parent / "mito_mvtool_status_counts.tsv"
    disease_summary_path = summary_path.parent / "mito_mvtool_disease_summary.tsv"
    population_bins_path = summary_path.parent / "mito_mvtool_population_bins.tsv"
    pd.DataFrame(columns=STATUS_COLUMNS).to_csv(status_counts_path, sep="\t", index=False)
    pd.DataFrame(columns=DISEASE_COLUMNS).to_csv(disease_summary_path, sep="\t", index=False)
    pd.DataFrame(columns=POP_BIN_COLUMNS).to_csv(population_bins_path, sep="\t", index=False)
    intro_html = f"<p class='muted'>{message}</p>"
    body_html = "<section><h2>Status</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>"
    render_page(report_path, "Mito mvTool Annotation", sample_id, "MT:whole_mito", intro_html, body_html)
    status = next(
        (str(row["value"]) for row in status_rows if row.get("metric") == "status"),
        "not_evaluable",
    )
    return {
        "status": status,
        "summary_path": summary_path,
        "annot_path": annot_path,
        "batch_log_path": batch_log_path,
        "status_counts_path": status_counts_path,
        "disease_summary_path": disease_summary_path,
        "population_bins_path": population_bins_path,
        "report_path": report_path,
    }


def to_hgvs(row: object) -> str:
    return f"m.{int(row.position)}{row.ref_base}>{row.alt_base}"


def as_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def normalize_text_values(series: pd.Series) -> pd.Series:
    normalized = series.fillna("").astype(str).str.strip()
    invalid = {"", "-", "--", "na", "n/a", "nan", "none", "null"}
    return normalized.map(lambda value: pd.NA if value.lower() in invalid else value)


def describe_api_source(api_url: str) -> str:
    """Return a stable human-readable description of the annotation source."""

    if api_url.startswith("file://"):
        parsed = urlparse(api_url)
        return f"local_fixture:{Path(unquote(parsed.path)).name}"
    return api_url


def validate_mvtool_rows(
    entries: list[object],
    *,
    submitted_inputs: list[str],
) -> list[dict[str, object]]:
    """Require exactly one response row for every Input submitted in a batch."""

    submitted_counts = Counter(submitted_inputs)
    if any(count != 1 for count in submitted_counts.values()):
        raise ValueError("mvTool submitted Inputs must be unique within each batch")

    invalid_row_indexes = [idx for idx, row in enumerate(entries) if not isinstance(row, dict)]
    if invalid_row_indexes:
        raise MvtoolResponseValidationError(
            "mvtool_response_row_not_object",
            "mvTool response rows must be objects; invalid row indexes: "
            + ",".join(map(str, invalid_row_indexes[:10])),
        )

    rows = [dict(row) for row in entries]
    if rows and all("Input" not in row for row in rows):
        raise MvtoolResponseValidationError(
            "mvtool_missing_input_column",
            "mvTool response rows did not contain the required Input field",
        )

    missing_identity_indexes = [
        idx
        for idx, row in enumerate(rows)
        if "Input" not in row or not isinstance(row["Input"], str) or not row["Input"].strip()
    ]
    if missing_identity_indexes:
        raise MvtoolResponseValidationError(
            "mvtool_missing_response_input",
            "mvTool response rows had missing or blank Input values at indexes: "
            + ",".join(map(str, missing_identity_indexes[:10])),
        )

    returned_inputs = [str(row["Input"]) for row in rows]
    returned_counts = Counter(returned_inputs)
    duplicate_inputs = sorted(value for value, count in returned_counts.items() if count > 1)
    if duplicate_inputs:
        raise MvtoolResponseValidationError(
            "mvtool_duplicate_response_input",
            "mvTool returned duplicate Input values: " + ",".join(duplicate_inputs[:10]),
        )

    submitted_set = set(submitted_inputs)
    returned_set = set(returned_inputs)
    unexpected_inputs = sorted(returned_set - submitted_set)
    if unexpected_inputs:
        raise MvtoolResponseValidationError(
            "mvtool_unexpected_response_input",
            "mvTool returned Input values that were not submitted in this batch: "
            + ",".join(unexpected_inputs[:10]),
        )

    missing_inputs = sorted(submitted_set - returned_set)
    if missing_inputs:
        raise MvtoolResponseValidationError(
            "mvtool_missing_response_input",
            "mvTool omitted submitted Input values: " + ",".join(missing_inputs[:10]),
        )

    return rows


def fetch_mvtool_rows(
    *,
    api_url: str,
    session: requests.Session,
    variants: list[str],
    timeout: int,
) -> tuple[list[dict[str, object]], int]:
    """Fetch mvTool-style annotation rows from HTTP or a local file fixture."""

    if api_url.startswith("file://"):
        parsed = urlparse(api_url)
        fixture_path = Path(unquote(parsed.path))
        fixture_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(fixture_payload, dict):
            raise ValueError("Local mvTool fixture root must be an object")
        if "records" in fixture_payload:
            records = fixture_payload.get("records", {})
            default_row = fixture_payload.get("default", {})
            if not isinstance(records, dict) or not isinstance(default_row, dict):
                raise ValueError("Local mvTool fixture records and default values must be objects")
            rows = []
            for variant in variants:
                if variant not in records:
                    continue
                record = records[variant]
                if not isinstance(record, dict):
                    raise ValueError(f"Local mvTool fixture record for {variant} must be an object")
                row = dict(default_row)
                row.update(record)
                rows.append(row)
            return rows, 200
        if "mseqdr" in fixture_payload and isinstance(fixture_payload["mseqdr"], list):
            return list(fixture_payload["mseqdr"]), 200
        raise ValueError("Local mvTool fixture must contain either 'records' or 'mseqdr'")

    payload = ("\n".join(variants) + "\n").encode()
    response = session.post(api_url, data=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("mvTool response root was not an object")
    entries = data.get("mseqdr", [])
    if not isinstance(entries, list):
        raise ValueError("mvTool response did not contain a list under 'mseqdr'")
    return entries, int(response.status_code)


def run_step(
    *,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    species: str,
    mode: str = "disabled",
    api_url: str = "",
    fixture_json: str | Path | None = None,
    timeout: int = 120,
    batch_size: int = 100,
) -> dict[str, Path | str]:
    """Run the optional mvTool annotation step."""

    print(
        f"[mvtool] starting sample={sample_id} species={species} mode={mode} "
        f"timeout={timeout} batch_size={batch_size}",
        flush=True,
    )
    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = report_dir / "14_mito_mvtool_annotation.html"
    summary_path = summary_dir / "mito_mvtool_annotation_summary.tsv"
    annot_path = summary_dir / "mito_mvtool_annotation_candidates.tsv"
    batch_log_path = summary_dir / "mito_mvtool_annotation_batches.tsv"
    status_counts_path = summary_dir / "mito_mvtool_status_counts.tsv"
    disease_summary_path = summary_dir / "mito_mvtool_disease_summary.tsv"
    population_bins_path = summary_dir / "mito_mvtool_population_bins.tsv"

    mode = mode.strip().lower()
    if mode == "disabled":
        return write_status_page(
            report_path=report_path,
            summary_path=summary_path,
            annot_path=annot_path,
            batch_log_path=batch_log_path,
            sample_id=sample_id,
            status_rows=[
                {"metric": "status", "value": "not_configured"},
                {"metric": "reason_code", "value": "mvtool_mode_disabled"},
                {"metric": "network_request_attempted", "value": 0},
            ],
            message=(
                "mvTool enrichment is disabled. Core mitochondrial reporting completed "
                "without external network access."
            ),
        )
    if mode == "fixture":
        if not fixture_json:
            return write_status_page(
                report_path=report_path,
                summary_path=summary_path,
                annot_path=annot_path,
                batch_log_path=batch_log_path,
                sample_id=sample_id,
                status_rows=[
                    {"metric": "status", "value": "unavailable"},
                    {"metric": "reason_code", "value": "mvtool_fixture_not_configured"},
                    {"metric": "network_request_attempted", "value": 0},
                ],
                message="mvTool fixture mode was requested without a fixture JSON path.",
            )
        fixture_path = Path(fixture_json).expanduser().resolve()
        if not fixture_path.exists():
            return write_status_page(
                report_path=report_path,
                summary_path=summary_path,
                annot_path=annot_path,
                batch_log_path=batch_log_path,
                sample_id=sample_id,
                status_rows=[
                    {"metric": "status", "value": "unavailable"},
                    {"metric": "reason_code", "value": "mvtool_fixture_missing"},
                    {"metric": "network_request_attempted", "value": 0},
                ],
                message=f"The configured mvTool fixture does not exist: {fixture_path}",
            )
        api_url = fixture_path.as_uri()
    elif mode == "network":
        if not api_url.strip():
            return write_status_page(
                report_path=report_path,
                summary_path=summary_path,
                annot_path=annot_path,
                batch_log_path=batch_log_path,
                sample_id=sample_id,
                status_rows=[
                    {"metric": "status", "value": "unavailable"},
                    {"metric": "reason_code", "value": "mvtool_network_url_missing"},
                    {"metric": "network_request_attempted", "value": 0},
                ],
                message="mvTool network mode requires an explicit API URL.",
            )
        parsed_network_url = urlparse(api_url.strip())
        if (
            parsed_network_url.scheme.lower() not in {"http", "https"}
            or not parsed_network_url.netloc
            or parsed_network_url.username is not None
            or parsed_network_url.password is not None
        ):
            return write_status_page(
                report_path=report_path,
                summary_path=summary_path,
                annot_path=annot_path,
                batch_log_path=batch_log_path,
                sample_id=sample_id,
                status_rows=[
                    {"metric": "status", "value": "unavailable"},
                    {"metric": "reason_code", "value": "mvtool_network_url_invalid"},
                    {"metric": "network_request_attempted", "value": 0},
                ],
                message=(
                    "mvTool network mode requires an HTTP(S) endpoint without embedded credentials. "
                    "Use fixture mode for local JSON resources."
                ),
            )
    else:
        raise ValueError(f"Unsupported mvTool mode: {mode}")

    if species.lower() != "human":
        return write_status_page(
            report_path=report_path,
            summary_path=summary_path,
            annot_path=annot_path,
            batch_log_path=batch_log_path,
            sample_id=sample_id,
            status_rows=[
                {"metric": "status", "value": "not_applicable"},
                {"metric": "reason_code", "value": "non_human_sample"},
            ],
            message="mvTool annotation is currently enabled only for human mitochondrial samples.",
        )

    candidates = load_table(summary_dir / "mito_heteroplasmy_candidates.tsv")
    if candidates.empty:
        return write_status_page(
            report_path=report_path,
            summary_path=summary_path,
            annot_path=annot_path,
            batch_log_path=batch_log_path,
            sample_id=sample_id,
            status_rows=[
                {"metric": "status", "value": "not_evaluable"},
                {"metric": "reason_code", "value": "no_candidate_sites_available"},
            ],
            message="No mitochondrial candidate variants were available for mvTool annotation.",
        )
    candidates = validate_candidate_table(
        candidates,
        table_name="mito_heteroplasmy_candidates.tsv",
    )
    candidates["mvtool_input"] = [to_hgvs(r) for r in candidates.itertuples(index=False)]
    unique_inputs = candidates[["mvtool_input"]].reset_index(drop=True)
    session = requests.Session()
    results: list[dict[str, object]] = []
    batch_rows: list[dict[str, object]] = []
    total_batches = max(1, math.ceil(len(unique_inputs) / batch_size))

    try:
        for idx in range(total_batches):
            start = idx * batch_size
            end = min((idx + 1) * batch_size, len(unique_inputs))
            subset = unique_inputs.iloc[start:end]
            print(
                f"[mvtool] sample={sample_id} batch={idx + 1}/{total_batches} variants={len(subset)} url={api_url}",
                flush=True,
            )
            entries, http_status = fetch_mvtool_rows(
                api_url=api_url,
                session=session,
                variants=subset["mvtool_input"].tolist(),
                timeout=timeout,
            )
            entries = validate_mvtool_rows(
                entries,
                submitted_inputs=subset["mvtool_input"].tolist(),
            )
            batch_rows.append(
                {
                    "batch": idx + 1,
                    "variants_submitted": int(len(subset)),
                    "records_returned": int(len(entries)),
                    "http_status": int(http_status),
                }
            )
            results.extend(entries)
    except Exception as exc:
        if isinstance(exc, MvtoolResponseValidationError):
            reason_code = exc.reason_code
        elif isinstance(exc, requests.Timeout):
            reason_code = "mvtool_network_timeout"
        elif mode == "fixture":
            reason_code = "mvtool_fixture_malformed"
        elif isinstance(exc, ValueError):
            reason_code = "mvtool_malformed_response"
        else:
            reason_code = "mvtool_request_failed"
        return write_status_page(
            report_path=report_path,
            summary_path=summary_path,
            annot_path=annot_path,
            batch_log_path=batch_log_path,
            sample_id=sample_id,
            status_rows=[
                {"metric": "status", "value": "unavailable"},
                {"metric": "reason_code", "value": reason_code},
                {"metric": "api_url", "value": api_url},
                {"metric": "submitted_candidates", "value": int(len(unique_inputs))},
                {"metric": "network_request_attempted", "value": int(mode == "network")},
                {"metric": "error", "value": f"{type(exc).__name__}: {exc}"[:220]},
            ],
            message="The mvTool annotation request failed before a complete annotation table could be assembled.",
        )

    batch_df = pd.DataFrame(batch_rows)
    batch_df.to_csv(batch_log_path, sep="\t", index=False)
    annot_df = pd.DataFrame(results)
    if annot_df.empty:
        return write_status_page(
            report_path=report_path,
            summary_path=summary_path,
            annot_path=annot_path,
            batch_log_path=batch_log_path,
            sample_id=sample_id,
            status_rows=[
                {"metric": "status", "value": "unavailable"},
                {"metric": "reason_code", "value": "mvtool_returned_no_records"},
                {"metric": "submitted_candidates", "value": int(len(unique_inputs))},
            ],
            message="mvTool returned no annotation rows for the submitted mitochondrial candidate variants.",
        )
    if "Input" not in annot_df.columns:
        annot_df.to_csv(annot_path, sep="\t", index=False)
        return write_status_page(
            report_path=report_path,
            summary_path=summary_path,
            annot_path=annot_path,
            batch_log_path=batch_log_path,
            sample_id=sample_id,
            status_rows=[
                {"metric": "status", "value": "unavailable"},
                {"metric": "reason_code", "value": "mvtool_missing_input_column"},
                {"metric": "returned_columns", "value": ",".join(map(str, annot_df.columns.tolist()[:20]))},
            ],
            message="mvTool returned rows, but the required Input column was absent, so candidates could not be merged back to the report table.",
        )

    keep_fields = [field for field in DEFAULT_FIELDS if field in annot_df.columns]
    annot_df = annot_df[keep_fields].copy()
    merged = candidates.merge(
        annot_df,
        left_on="mvtool_input",
        right_on="Input",
        how="left",
        validate="one_to_one",
    )

    missing_values = pd.Series(pd.NA, index=merged.index, dtype="object")
    status_norm = normalize_text_values(merged.get("Mitomap_status", missing_values))
    disease_norm = normalize_text_values(merged.get("Mitomap_Disease", missing_values))
    hmtdb_disease_norm = normalize_text_values(merged.get("HmtDB_disease", missing_values))

    merged["Mitomap_status_normalized"] = status_norm
    merged["Mitomap_Disease_normalized"] = disease_norm
    merged["HmtDB_disease_normalized"] = hmtdb_disease_norm
    merged.to_csv(annot_path, sep="\t", index=False)

    status_counts = pd.DataFrame(columns=STATUS_COLUMNS)
    mitomap_status_df = merged[status_norm.notna()].copy()
    if not mitomap_status_df.empty:
        status_counts = (
            mitomap_status_df.groupby("Mitomap_status_normalized", as_index=False)
            .agg(candidate_sites=("mvtool_input", "nunique"))
            .sort_values("candidate_sites", ascending=False)
            .rename(columns={"Mitomap_status_normalized": "Mitomap_status"})
        )
    status_counts.to_csv(status_counts_path, sep="\t", index=False)

    disease_summary = pd.DataFrame(columns=DISEASE_COLUMNS)
    disease_rows = merged[disease_norm.notna()].copy()
    if not disease_rows.empty:
        disease_summary = (
            disease_rows.groupby("Mitomap_Disease_normalized", as_index=False)
            .agg(
                candidate_sites=("mvtool_input", "nunique"),
                supporting_statuses=(
                    "Mitomap_status_normalized",
                    lambda s: ", ".join(sorted({str(v) for v in s.dropna()})) or "NA",
                ),
            )
            .sort_values(["candidate_sites", "Mitomap_Disease_normalized"], ascending=[False, True])
            .rename(columns={"Mitomap_Disease_normalized": "Reported_association"})
        )
    disease_summary.to_csv(disease_summary_path, sep="\t", index=False)

    population_bin_summary = pd.DataFrame(columns=POP_BIN_COLUMNS)
    if "AF_M1" in merged.columns:
        freq_df = merged[["mvtool_input", "AF_M1"]].copy()
        freq_df["AF_M1"] = as_float(freq_df["AF_M1"])
        freq_df = freq_df.dropna(subset=["AF_M1"])
        if not freq_df.empty:
            population_bin_summary = (
                freq_df.assign(
                    AF_M1_bin=pd.cut(
                        freq_df["AF_M1"],
                        bins=[-0.000001, 0.001, 0.01, 0.05, 0.10, 1.0],
                        labels=["<0.1%", "0.1-1%", "1-5%", "5-10%", ">=10%"],
                    )
                )
                .groupby("AF_M1_bin", observed=False, as_index=False)
                .agg(candidate_sites=("mvtool_input", "nunique"))
            )
            population_bin_summary = population_bin_summary[population_bin_summary["candidate_sites"] > 0].copy()
    population_bin_summary.to_csv(population_bins_path, sep="\t", index=False)

    usable_status_rows = int(status_norm.notna().sum())
    usable_disease_rows = int(disease_norm.notna().sum())
    usable_hmtdb_rows = int(hmtdb_disease_norm.notna().sum())
    rows_without_usable_status = int(len(merged) - usable_status_rows)

    summary_df = pd.DataFrame(
        [
            {"metric": "status", "value": "ok"},
            {"metric": "candidate_sites_submitted", "value": int(len(unique_inputs))},
            {"metric": "rows_returned_by_mvtool", "value": int(len(annot_df))},
            {"metric": "sites_with_usable_mitomap_status", "value": usable_status_rows},
            {"metric": "sites_without_usable_mitomap_status", "value": rows_without_usable_status},
            {"metric": "sites_with_reported_mitomap_association", "value": usable_disease_rows},
            {"metric": "sites_with_reported_hmtdb_association", "value": usable_hmtdb_rows},
            {"metric": "annotation_source", "value": describe_api_source(api_url)},
            {"metric": "mvtool_mode", "value": mode},
            {"metric": "network_request_attempted", "value": int(mode == "network")},
        ]
    )
    summary_df.to_csv(summary_path, sep="\t", index=False)

    status_fig = None
    if not status_counts.empty:
        status_fig = figure_dir / "mito_mvtool_status_counts.png"
        plot_df = status_counts.head(8)
        plt.figure(figsize=(9, 4))
        plt.bar(plot_df["Mitomap_status"], plot_df["candidate_sites"], color="#7c3aed")
        plt.xticks(rotation=30, ha="right")
        plt.ylabel("Candidate sites")
        plt.title(f"{sample_id} mvTool / MITOMAP status distribution")
        plt.tight_layout()
        plt.savefig(status_fig, dpi=150)
        plt.close()

    af_fig = None
    if not population_bin_summary.empty:
        af_fig = figure_dir / "mito_mvtool_population_context.png"
        plt.figure(figsize=(7, 4))
        plt.bar(population_bin_summary["AF_M1_bin"].astype(str), population_bin_summary["candidate_sites"], color="#0f766e")
        plt.xlabel("mvTool AF_M1 population-frequency bin")
        plt.ylabel("Candidate sites")
        plt.title(f"{sample_id} mvTool population-frequency context")
        plt.xticks(rotation=20, ha="right")
        plt.tight_layout()
        plt.savefig(af_fig, dpi=150)
        plt.close()

    metrics_html = "".join(
        [
            metric_card("Submitted candidates", int(len(unique_inputs))),
            metric_card("Rows returned by mvTool", int(len(annot_df))),
            metric_card("Usable MITOMAP statuses", usable_status_rows),
            metric_card("Rows without usable status", rows_without_usable_status),
            metric_card("Reported disease / phenotype labels", usable_disease_rows),
        ]
    )
    intro_html = (
        '<p class="muted">This optional page enriches mitochondrial candidate variants using an explicitly configured mvTool-compatible source. It can use a deterministic local fixture or an opt-in network endpoint to recover standardized mtDNA nomenclature and external annotation context. '
        "Placeholder values are excluded from the summary metrics and status plot so that the page emphasizes usable external annotation rather than uninformative return rows.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>mvTool summary</h2>" + df_to_html_table(summary_df, max_rows=20) + "</section>",
        "<section><h2>Batch log</h2>" + df_to_html_table(batch_df, max_rows=20) + "</section>",
        "<section><h2>Annotated candidate table</h2>" + df_to_html_table(merged, max_rows=40) + "</section>",
    ]
    if status_fig:
        body_parts.insert(
            2,
            "<section><h2>MITOMAP status distribution</h2>"
            + figure_html(status_fig, "Distribution of usable mvTool / MITOMAP status labels among annotated candidates")
            + "</section>",
        )
    if af_fig:
        body_parts.insert(
            3,
            "<section><h2>Population-frequency context</h2>"
            + figure_html(af_fig, "Candidate-site counts across mvTool AF_M1 population-frequency bins")
            + "</section>",
        )
    if not population_bin_summary.empty:
        body_parts.append(
            "<section><h2>Population-frequency bin summary</h2>"
            + df_to_html_table(population_bin_summary, max_rows=10)
            + "</section>"
        )
    if not disease_summary.empty:
        body_parts.append(
            "<section><h2>Reported phenotype / disease associations</h2>"
            + df_to_html_table(disease_summary, max_rows=20)
            + "</section>"
        )
    body_parts.append("<section><h2>Authorship</h2><p>Author: Elisson Lopes, PhD</p></section>")
    render_page(report_path, "Mito mvTool Annotation", sample_id, "MT:whole_mito", intro_html, "".join(body_parts))
    return {
        "status": "ok",
        "summary_path": summary_path,
        "annot_path": annot_path,
        "batch_log_path": batch_log_path,
        "status_counts_path": status_counts_path,
        "disease_summary_path": disease_summary_path,
        "population_bins_path": population_bins_path,
        "report_path": report_path,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        summary_dir=args.summary_dir,
        figure_dir=args.figure_dir,
        report_dir=args.report_dir,
        sample_id=args.sample_id,
        species=args.species,
        mode=args.mode,
        api_url=args.api_url,
        fixture_json=args.fixture_json,
        timeout=args.timeout,
        batch_size=args.batch_size,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
