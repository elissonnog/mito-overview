from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation_fingerprints_v0_3_0 import (
    FINGERPRINT_FIELDS,
    compact_summary_contract_fingerprints,
    summary_contract_fingerprints,
    write_compact_summary_contract,
)


REPO_ROOT = Path(__file__).parents[1]
PACKET_BUILDER_PATH = REPO_ROOT / "scripts/build_validation_packet_v0.3.0.py"
PACKET_BUILDER_SPEC = importlib.util.spec_from_file_location(
    "public_protocol_packet_builder_v030",
    PACKET_BUILDER_PATH,
)
assert PACKET_BUILDER_SPEC is not None and PACKET_BUILDER_SPEC.loader is not None
packet_builder = importlib.util.module_from_spec(PACKET_BUILDER_SPEC)
PACKET_BUILDER_SPEC.loader.exec_module(packet_builder)
PREPARE = REPO_ROOT / "scripts" / "prepare_public_validation_cache_v0.3.0.sh"
MATRIX = REPO_ROOT / "scripts" / "run_public_validation_matrix_v0.3.0.sh"
ISOLATION_WRAPPER = REPO_ROOT / "scripts" / "run_network_isolated_v0.3.0.sh"
SHORT_RUNNER = REPO_ROOT / "scripts" / "run_public_shortread_validation_gm11906.sh"
LONG_RUNNER = REPO_ROOT / "scripts" / "run_public_longread_validation_gm12878.sh"
ASSERT_ORACLE = REPO_ROOT / "scripts" / "assert_public_validation_oracle_v0.3.0.py"
ORACLE = (
    REPO_ROOT
    / "examples"
    / "public_validation"
    / "public_validation_oracle_v0.3.0.tsv"
)
GM11906_SOURCE_METADATA = (
    REPO_ROOT
    / "resources"
    / "public_validation"
    / "gm11906_ncbi_source_metadata_v0.3.0.json"
)
PREPRINT_VALIDATION_DOC = REPO_ROOT / "docs" / "preprint_release_validation_v0.3.0.md"
FIXTURE_ORACLE_NAME = "_fixture_public_validation_oracle.tsv"
REPORT_MODULE_STATUS_OUTPUTS = (
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


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_valid_isolation_evidence(path: Path) -> None:
    platform_id = f"{platform.system()}/{platform.machine()}"
    method = {
        "Darwin/x86_64": "macos_sandbox_exec_deny_network",
        "Darwin/arm64": "macos_sandbox_exec_deny_network",
        "Linux/x86_64": "linux_unshare_network_namespace",
    }[platform_id]
    rows = [
        ("schema_version", "1.0"),
        ("platform", platform_id),
        ("isolation_method", method),
        ("isolation_scope", "process_tree"),
        ("parent_loopback_control", "reachable"),
        ("isolated_loopback_probe", "blocked"),
        ("probe_target", "parent_loopback_listener"),
        ("probe_error", "PermissionError:1"),
        ("invoking_uid", str(os.getuid())),
        ("invoking_gid", str(os.getgid())),
        ("child_uid", str(os.getuid())),
        ("child_gid", str(os.getgid())),
        ("network_isolation_verdict", "PASS"),
    ]
    path.write_text(
        "field\tvalue\n" + "".join(f"{key}\t{value}\n" for key, value in rows),
        encoding="utf-8",
    )


def write_fake_curl(bin_dir: Path, marker: Path, exit_code: int = 55) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    executable = bin_dir / "curl"
    executable.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> {str(marker)!r}\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)


def matrix_command(tmp_path: Path, cache: Path) -> list[str]:
    return [
        str(MATRIX),
        "--mode",
        "offline",
        "--cache",
        str(cache),
        "--work",
        str(tmp_path / "work"),
        "--output",
        str(tmp_path / "output"),
        "--oracle",
        str(ORACLE),
    ]


def write_metric_table(path: Path, values: dict[str, object]) -> None:
    path.write_text(
        "metric\tvalue\n"
        + "".join(f"{metric}\t{value}\n" for metric, value in values.items()),
        encoding="utf-8",
    )


def write_feature_annotation_state(path: Path, status: str) -> None:
    if status == "ok":
        path.write_text(
            "feature_class\tfeature_label\tcandidate_sites\t"
            "mean_alt_allele_fraction\tmean_heteroplasmy\n"
            "Mt_tRNA\tMT-TK\t1\t0.720545\t0.720545\n",
            encoding="utf-8",
        )
    else:
        write_metric_table(path, {"status": status, "reason_code": "fixture_state"})


def write_candidates(path: Path, count: int, marker_fraction: str) -> None:
    rows = []
    if marker_fraction:
        rows.append(
            {
                "position": "8344",
                "ref_base": "A",
                "alt_base": "G",
                "callable_depth": "1027",
                "alt_count": "740",
                "alt_allele_fraction": marker_fraction,
                "alt_forward": "305",
                "alt_reverse": "435",
            }
        )
    for index in range(count - len(rows)):
        rows.append(
            {
                "position": str(100 + index),
                "ref_base": "A",
                "alt_base": "C",
                "callable_depth": "100",
                "alt_count": "20",
                "alt_allele_fraction": "0.2",
                "alt_forward": "10",
                "alt_reverse": "10",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_case_output(root: Path, case_id: str, oracle: dict[str, str]) -> None:
    output = root / "outputs" / case_id
    summary = output / "summary"
    report = output / "report"
    figures = output / "figures"
    provenance = output / "provenance"
    for directory in (summary, report, figures, provenance):
        directory.mkdir(parents=True, exist_ok=True)

    marker_fraction = oracle["m8344_alt_fraction"] if oracle["m8344_present"] == "1" else ""
    write_candidates(summary / "mito_heteroplasmy_candidates.tsv", int(oracle["candidate_sites"]), marker_fraction)
    write_metric_table(
        summary / "mito_heteroplasmy_summary.tsv",
        {
            "status": oracle["heteroplasmy_module_status"],
            "reason_code": "",
            "allele_min_base_quality": oracle["min_base_quality"],
            "allele_min_mapping_quality": oracle["min_mapping_quality"],
            "allele_min_read_mean_quality": oracle["min_read_mean_quality"],
            "accepted_observations": oracle["accepted_observations"],
            "excluded_observations": oracle["excluded_observations"],
        },
    )
    for oracle_field, filename in (
        ("mito_qc_module_status", "mito_qc_summary.tsv"),
        ("deletions_module_status", "mito_deletion_summary.tsv"),
        ("copy_number_module_status", "mito_copy_number_summary.tsv"),
        ("cosegregation_module_status", "mito_cosegregation_summary.tsv"),
        ("gene_summary_module_status", "mito_gene_summary_run_summary.tsv"),
        ("identity_qc_module_status", "mito_identity_qc_summary.tsv"),
        ("variant_consequence_module_status", "mito_variant_consequence_summary.tsv"),
        ("circularity_qc_module_status", "mito_circularity_qc_summary.tsv"),
        (
            "methylation_exploratory_module_status",
            "mito_methylation_exploratory_summary.tsv",
        ),
        ("phymer_haplogroup_module_status", "mito_phymer_haplogroup_summary.tsv"),
        ("mvtool_annotation_module_status", "mito_mvtool_annotation_summary.tsv"),
    ):
        write_metric_table(summary / filename, {"status": oracle[oracle_field]})
    write_feature_annotation_state(
        summary / "mito_feature_annotation_summary.tsv",
        oracle["feature_annotation_module_status"],
    )
    numt_values = {"status": oracle["numt_qc_module_status"]}
    if oracle["numt_qc_module_status"] != "not_applicable":
        numt_values.update(
            {
                "numt_interpretation_status": oracle["numt_interpretation_status"],
                "reason_code": oracle["numt_interpretation_reason_code"],
            }
        )
    write_metric_table(summary / "mito_numt_qc_summary.tsv", numt_values)
    (summary / "mito_variant_consequence_candidates.tsv").write_text(
        "position\tref_base\talt_base\tfeature_label\tfeature_class\tconsequence_class\n"
        "8344\tA\tG\tMT-TK\tMt_tRNA\ttRNA_variant\n",
        encoding="utf-8",
    )

    if oracle["dataset"] == "GM12878":
        write_metric_table(
            summary / "mito_qc_summary.tsv",
            {
                "status": oracle["mito_qc_module_status"],
                "mapped_reads": oracle["mapped_reads"],
                "primary_reads": oracle["primary_reads"],
                "supplementary_reads": oracle["supplementary_reads"],
                "mean_depth": oracle["mean_depth"],
                "median_depth": oracle["median_depth"],
            },
        )
        write_metric_table(
            summary / "mito_cosegregation_summary.tsv",
            {
                "status": oracle["cosegregation_module_status"],
                "selected_sites": oracle["selected_cosegregation_sites"],
            },
        )
        write_metric_table(
            summary / "mito_deletion_summary.tsv",
            {
                "status": oracle["deletions_module_status"],
                "candidate_deletion_clusters": oracle["deletion_clusters"],
                "reads_with_large_deletion": oracle["deletion_query_names"],
                "reads_with_supplementary_or_SA": oracle["supplementary_sa_query_names"],
            },
        )
        (provenance / "GM12878_ONT_longread.fastq_subset.provenance.json").write_text(
            json.dumps(
                {
                    "selection": {
                        "source_records_seen": int(oracle["source_records"]),
                        "selected_query_names": int(oracle["selected_names"]),
                        "seed": "mito-overview-v0.3.0-GM12878-SRR18110025",
                    }
                }
            ),
            encoding="utf-8",
        )
    else:
        runs = ("SRR10804585", "SRR10804590", "SRR10804657")
        (provenance / "GM11906_MERRF_shortread.source_libraries.tsv").write_text(
            "run_accession\tgeo_accession\n"
            + "".join(f"{run}\tGSM{index}\n" for index, run in enumerate(runs, 1)),
            encoding="utf-8",
        )
        (provenance / "GM11906_MERRF_shortread.alignment.provenance.json").write_text(
            json.dumps(
                {
                    "dataset_id": "GM11906_pooled_scATAC",
                    "derivation": {"derivation_id": "bwa-mem-samtools-sort-v1"},
                    "public_inputs": [
                        {"label": f"{run}_{mate}"}
                        for run in runs
                        for mate in ("R1", "R2")
                    ],
                }
            ),
            encoding="utf-8",
        )

    existing = len(list(summary.glob("*.tsv")))
    for index in range(int(oracle["summary_tsv_count"]) - existing):
        (summary / f"zz_dummy_{index:02d}.tsv").write_text("key\tvalue\n", encoding="utf-8")
    for index in range(int(oracle["html_count"])):
        (report / f"report_{index:02d}.html").write_text("<html><body>ok</body></html>\n", encoding="utf-8")
    for index in range(int(oracle["png_count"])):
        (figures / f"figure_{index:02d}.png").write_bytes(b"not-decoded-by-oracle")


def build_matrix_fixture(root: Path) -> None:
    oracle_rows = read_tsv(ORACLE)
    by_key = {(row["dataset"], row["profile"]): row for row in oracle_rows}
    cases = {
        ("GM11906", "lenient"): ["gm11906_lenient"],
        ("GM11906", "default"): ["gm11906_default_run1", "gm11906_default_run2"],
        ("GM11906", "strict"): ["gm11906_strict"],
        ("GM12878", "lenient"): ["gm12878_lenient"],
        ("GM12878", "default"): ["gm12878_default_run1", "gm12878_default_run2"],
        ("GM12878", "strict"): ["gm12878_strict"],
    }
    for key, case_ids in cases.items():
        for case_id in case_ids:
            write_case_output(root, case_id, by_key[key])
        fingerprints = [
            summary_contract_fingerprints(
                root / "outputs" / case_id / "summary"
            )
            for case_id in case_ids
        ]
        if any(value != fingerprints[0] for value in fingerprints[1:]):
            raise AssertionError(f"Fixture repeats disagree for {key}")
        by_key[key].update(fingerprints[0])

    fixture_oracle = root / FIXTURE_ORACLE_NAME
    with fixture_oracle.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(oracle_rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(oracle_rows)

    with (root / "filter_profile_results.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fields = [
            "case_id",
            "dataset",
            "profile",
            "min_base_quality",
            "min_mapping_quality",
            "min_read_mean_quality",
            "candidate_sites",
            "accepted_observations",
            "excluded_observations",
            "m8344_A_G_present",
            "m8344_A_G_alt_allele_fraction",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in oracle_rows:
            writer.writerow(
                {
                    "case_id": f"{row['dataset'].lower()}_{row['profile']}",
                    "dataset": row["dataset"],
                    "profile": row["profile"],
                    "min_base_quality": row["min_base_quality"],
                    "min_mapping_quality": row["min_mapping_quality"],
                    "min_read_mean_quality": row["min_read_mean_quality"],
                    "candidate_sites": row["candidate_sites"],
                    "accepted_observations": row["accepted_observations"],
                    "excluded_observations": row["excluded_observations"],
                    "m8344_A_G_present": row["m8344_present"],
                    "m8344_A_G_alt_allele_fraction": row["m8344_alt_fraction"],
                }
            )


def run_oracle(
    matrix_root: Path,
    report: Path,
    oracle: Path = ORACLE,
) -> subprocess.CompletedProcess[str]:
    fixture_oracle = matrix_root / FIXTURE_ORACLE_NAME
    if oracle == ORACLE and fixture_oracle.is_file():
        oracle = fixture_oracle
    return subprocess.run(
        [
            "python3",
            str(ASSERT_ORACLE),
            "--matrix-root",
            str(matrix_root),
            "--oracle",
            str(oracle),
            "--report",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def replace_or_add_metric(path: Path, metric: str, value: str) -> None:
    rows = read_tsv(path)
    replaced = False
    for row in rows:
        if row["metric"] == metric:
            row["value"] = value
            replaced = True
    if not replaced:
        rows.append({"metric": metric, "value": value})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["metric", "value"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_oracle_fixture(
    path: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def test_owned_shell_scripts_are_syntactically_valid() -> None:
    subprocess.run(
        ["bash", "-n", str(PREPARE), str(MATRIX), str(SHORT_RUNNER), str(LONG_RUNNER)],
        check=True,
    )


def test_gm11906_source_provenance_identifies_the_pooled_scatac_libraries() -> None:
    cache_contract = PREPARE.read_text(encoding="utf-8")
    runner_contract = SHORT_RUNNER.read_text(encoding="utf-8")

    assert "GM11906_pooled_scATAC" in cache_contract
    assert "source_sample_id" in cache_contract
    assert "library_strategy" in cache_contract
    assert "single_cell_library" in cache_contract
    for run, geo in (
        ("SRR10804585", "GSM4238454"),
        ("SRR10804590", "GSM4238459"),
        ("SRR10804657", "GSM4238526"),
    ):
        assert run in cache_contract
        assert f"acc={geo}" in cache_contract

    assert "pooled pseudo-bulk of three GM11906 single-cell ATAC-seq libraries" in runner_contract
    assert "pooled_read_observation_fraction" in runner_contract
    assert "--dataset GM11906_pooled_scATAC" in runner_contract

    metadata = json.loads(GM11906_SOURCE_METADATA.read_text(encoding="utf-8"))
    records = metadata["records"]
    canonical = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    assert hashlib.sha256(canonical).hexdigest() == metadata["records_sha256"]
    assert metadata["authority"] == "NCBI GEO and NCBI SRA"
    assert metadata["retrieval_completed_utc"] == "2026-07-22T04:03:33Z"
    assert hashlib.sha256(GM11906_SOURCE_METADATA.read_bytes()).hexdigest() == (
        "01be488b9dc6bfce0726304be95db4259b1a85a53ac8e620cba4c337842d3185"
    )
    by_run = {record["run_accession"]: record for record in records}
    assert {
        run: (
            record["geo_accession"],
            record["biosample_accession"],
            record["cell_line"],
        )
        for run, record in by_run.items()
    } == {
        "SRR10804585": ("GSM4238454", "SAMN13699362", "GM11906"),
        "SRR10804590": ("GSM4238459", "SAMN13699398", "GM11906"),
        "SRR10804657": ("GSM4238526", "SAMN13699338", "GM11906"),
    }
    expected_source_hashes = {
        "d1f14494b835ab8cf440892ddb66158aab62c58ffc4f0bd973e10d78de036627",
        "80b27624e09216055020933d8cf5d81136191f2104180acf7fcb219a6acdd03a",
        "8792f8b0ff0f411afd9fbaafdb0db07f500175232345ec4e3d836c225006c9b1",
        "97a6c54e4c957b98badc373a290e3554444cab270d21b6deaf61d90df0dff097",
        "f717e8d921f2e28a796ccd77a6fb2710e7e738b1c50fea4db31ab5d539df3584",
        "c481df75f2e46ec9d11cbd6e6b035962e9b73aca4170cf5c89b20d8200403445",
    }
    assert {
        source["sha256"]
        for record in records
        for source in record["source_files"]
    } == expected_source_hashes


def test_prepare_rejects_tampered_official_metadata_before_network(
    tmp_path: Path,
) -> None:
    fixture_repo = tmp_path / "repo"
    fixture_script = fixture_repo / "scripts" / PREPARE.name
    fixture_metadata = (
        fixture_repo
        / "resources"
        / "public_validation"
        / GM11906_SOURCE_METADATA.name
    )
    fixture_script.parent.mkdir(parents=True)
    fixture_metadata.parent.mkdir(parents=True)
    shutil.copy2(PREPARE, fixture_script)
    shutil.copy2(GM11906_SOURCE_METADATA, fixture_metadata)
    metadata = json.loads(fixture_metadata.read_text(encoding="utf-8"))
    metadata["records"][0]["cell_line"] = "GM00000"
    canonical = json.dumps(
        metadata["records"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    metadata["records_sha256"] = hashlib.sha256(canonical).hexdigest()
    fixture_metadata.write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    fixture_script.chmod(0o755)

    marker = tmp_path / "curl-called.txt"
    fake_bin = tmp_path / "bin"
    write_fake_curl(fake_bin, marker)
    result = subprocess.run(
        [str(fixture_script), "--cache", str(tmp_path / "cache")],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert result.returncode != 0
    assert "snapshot SHA-256 mismatch" in result.stderr
    assert not marker.exists()


def test_provisional_validation_doc_defers_exact_final_suite_count() -> None:
    text = PREPRINT_VALIDATION_DOC.read_text(encoding="utf-8")
    opening = "\n".join(text.splitlines()[:12]).lower()
    assert "historical" in opening
    assert "not release evidence" in opening
    assert "239 passed" not in text
    assert "239-test PASS" not in text
    assert "All 256" not in text
    stale_hashes = (
        "a18f2194487dbbd0ce72eeeedcd6203d8675ec47b5fb351454b7f506ed014166",
        "11605372e020dc79d3c1f0e05bc89441c3ef132e1343a19d37379df22c2ae04a",
        "eb4dd1d907a32b0202c479215ff3a9fe3ad2788a65127bbafc6f74ac4a27b366",
    )
    assert not any(value in text for value in stale_hashes)
    assert "Final count deferred" in text
    assert "exact count, commit, environment, and verdict" in text
    assert "MitoOverview_v0.3.0_release_validation_report" in text


def test_oracle_accepts_exact_six_profile_fixture(tmp_path: Path) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    report = tmp_path / "oracle_assertions.tsv"
    result = run_oracle(matrix_root, report)
    assert result.returncode == 0, result.stderr
    assertions = read_tsv(report)
    assert assertions
    assert {row["verdict"] for row in assertions} == {"PASS"}


def test_real_checker_output_matches_the_packet_assertion_contract(
    tmp_path: Path,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    report = tmp_path / "oracle_assertions.tsv"
    result = run_oracle(matrix_root, report)
    assert result.returncode == 0, result.stderr

    oracle_rows = read_tsv(matrix_root / FIXTURE_ORACLE_NAME)
    summary = packet_builder.validate_oracle_assertions(report, oracle_rows)
    assertion_count = len(read_tsv(report))
    assert summary == {
        "assertion_count": assertion_count,
        "required_assertion_count": assertion_count,
    }


def test_oracle_rejects_deterministic_candidate_regression(tmp_path: Path) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    candidate_path = (
        matrix_root
        / "outputs"
        / "gm12878_default_run1"
        / "summary"
        / "mito_heteroplasmy_candidates.tsv"
    )
    rows = read_tsv(candidate_path)
    with candidate_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows[:-1])
    report = tmp_path / "oracle_assertions.tsv"
    result = run_oracle(matrix_root, report)
    assert result.returncode != 0
    assert "gm12878_default_run1.candidate_sites" in result.stderr
    assert any(row["verdict"] == "FAIL" for row in read_tsv(report))


def test_oracle_rejects_candidate_row_change_that_preserves_counts(
    tmp_path: Path,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    candidate_path = (
        matrix_root
        / "outputs/gm12878_default_run1/summary/mito_heteroplasmy_candidates.tsv"
    )
    rows = read_tsv(candidate_path)
    rows[0]["alt_count"] = str(int(rows[0]["alt_count"]) + 1)
    write_oracle_fixture(candidate_path, rows, list(rows[0]))

    report = tmp_path / "oracle_assertions.tsv"
    result = run_oracle(matrix_root, report)
    assert result.returncode != 0
    assert "gm12878_default_run1.candidate_table_sha256" in result.stderr


def test_oracle_rejects_summary_schema_drift_with_same_file_count(
    tmp_path: Path,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    table = matrix_root / "outputs/gm12878_default_run1/summary/zz_dummy_00.tsv"
    table.write_text("renamed_key\tvalue\n", encoding="utf-8")

    result = run_oracle(matrix_root, tmp_path / "oracle_assertions.tsv")
    assert result.returncode != 0
    assert "gm12878_default_run1.summary_schema_sha256" in result.stderr


def test_oracle_rejects_same_count_summary_inventory_substitution(
    tmp_path: Path,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    summary = matrix_root / "outputs/gm12878_default_run1/summary"
    (summary / "zz_dummy_00.tsv").rename(summary / "zz_replacement.tsv")

    result = run_oracle(matrix_root, tmp_path / "oracle_assertions.tsv")
    assert result.returncode != 0
    assert "gm12878_default_run1.summary_inventory_sha256" in result.stderr


def test_compact_contract_recomputes_all_full_summary_fingerprints(
    tmp_path: Path,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    summary = matrix_root / "outputs/gm12878_strict/summary"
    contract = tmp_path / "contract"

    written = write_compact_summary_contract(summary, contract)

    assert written == summary_contract_fingerprints(summary)
    assert compact_summary_contract_fingerprints(contract) == written


def test_compact_contract_detects_candidate_and_schema_mutations(
    tmp_path: Path,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    summary = matrix_root / "outputs/gm11906_default_run1/summary"
    contract = tmp_path / "contract"
    expected = write_compact_summary_contract(summary, contract)

    candidate = contract / "mito_heteroplasmy_candidates.tsv"
    rows = read_tsv(candidate)
    rows[0]["alt_count"] = str(int(rows[0]["alt_count"]) + 1)
    write_oracle_fixture(candidate, rows, list(rows[0]))
    assert compact_summary_contract_fingerprints(contract) != expected

    shutil.copy2(
        summary / "mito_heteroplasmy_candidates.tsv",
        candidate,
    )
    manifest = contract / "summary_schema_manifest.tsv"
    manifest_rows = read_tsv(manifest)
    header = json.loads(manifest_rows[0]["header_json"])
    header[0] = f"{header[0]}_changed"
    manifest_rows[0]["header_json"] = json.dumps(header, separators=(",", ":"))
    write_oracle_fixture(manifest, manifest_rows, list(manifest_rows[0]))
    assert compact_summary_contract_fingerprints(contract) != expected


@pytest.mark.parametrize(
    ("dataset", "case_id", "oracle_field", "filename"),
    [
        (dataset, case_id, oracle_field, filename)
        for dataset, case_id in (
            ("GM11906", "gm11906_default_run1"),
            ("GM12878", "gm12878_default_run1"),
        )
        for oracle_field, filename in REPORT_MODULE_STATUS_OUTPUTS
    ],
)
def test_oracle_rejects_every_report_module_state_regression(
    tmp_path: Path,
    dataset: str,
    case_id: str,
    oracle_field: str,
    filename: str,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    path = matrix_root / "outputs" / case_id / "summary" / filename
    if oracle_field == "feature_annotation_module_status":
        write_metric_table(path, {"status": "failed", "reason_code": "injected"})
    else:
        replace_or_add_metric(path, "status", "failed")

    report = tmp_path / "oracle_assertions.tsv"
    result = run_oracle(matrix_root, report)
    assert result.returncode != 0
    assertion_id = f"{case_id}.module_status.{oracle_field}"
    assert assertion_id in result.stderr
    assert any(
        row["assertion_id"] == assertion_id and row["verdict"] == "FAIL"
        for row in read_tsv(report)
    ), dataset


@pytest.mark.parametrize(
    ("case_id", "regressed_status"),
    (
        ("gm11906_default_run1", "not_evaluable"),
        ("gm12878_default_run1", "ok"),
    ),
)
def test_oracle_rejects_numt_interpretation_state_regression(
    tmp_path: Path,
    case_id: str,
    regressed_status: str,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    path = (
        matrix_root
        / "outputs"
        / case_id
        / "summary"
        / "mito_numt_qc_summary.tsv"
    )
    replace_or_add_metric(path, "numt_interpretation_status", regressed_status)

    report = tmp_path / "oracle_assertions.tsv"
    result = run_oracle(matrix_root, report)
    assert result.returncode != 0
    assertion_id = (
        f"{case_id}.interpretation_status.numt_interpretation_status"
    )
    assert assertion_id in result.stderr


@pytest.mark.parametrize(
    ("case_id", "regressed_reason"),
    (
        ("gm11906_default_run1", "wrong_module_reason"),
        ("gm12878_default_run1", "wrong_reference_scope"),
    ),
)
def test_oracle_rejects_numt_interpretation_reason_regression(
    tmp_path: Path,
    case_id: str,
    regressed_reason: str,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    path = (
        matrix_root
        / "outputs"
        / case_id
        / "summary"
        / "mito_numt_qc_summary.tsv"
    )
    replace_or_add_metric(path, "reason_code", regressed_reason)

    report = tmp_path / "oracle_assertions.tsv"
    result = run_oracle(matrix_root, report)
    assert result.returncode != 0
    assert (
        f"{case_id}.interpretation_status.numt_interpretation_reason_code"
        in result.stderr
    )


@pytest.mark.parametrize("value", ("", "not-a-module-state"))
def test_oracle_rejects_blank_or_malformed_expected_module_state(
    tmp_path: Path,
    value: str,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    rows = read_tsv(matrix_root / FIXTURE_ORACLE_NAME)
    fieldnames = list(rows[0])
    rows[0]["deletions_module_status"] = value
    modified_oracle = tmp_path / "modified_oracle.tsv"
    write_oracle_fixture(modified_oracle, rows, fieldnames)

    result = run_oracle(
        matrix_root,
        tmp_path / "oracle_assertions.tsv",
        modified_oracle,
    )
    assert result.returncode != 0
    assert "deletions_module_status" in result.stderr


@pytest.mark.parametrize("mutation", ("missing", "unexpected"))
def test_oracle_requires_the_exact_closed_status_key_set(
    tmp_path: Path,
    mutation: str,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    rows = read_tsv(matrix_root / FIXTURE_ORACLE_NAME)
    fieldnames = list(rows[0])
    if mutation == "missing":
        fieldnames.remove("identity_qc_module_status")
        for row in rows:
            row.pop("identity_qc_module_status")
    else:
        fieldnames.append("invented_module_status")
        for row in rows:
            row["invented_module_status"] = "ok"
    modified_oracle = tmp_path / "modified_oracle.tsv"
    write_oracle_fixture(modified_oracle, rows, fieldnames)

    result = run_oracle(
        matrix_root,
        tmp_path / "oracle_assertions.tsv",
        modified_oracle,
    )
    assert result.returncode != 0
    assert "Oracle status columns do not match the required closed set" in result.stderr


def test_oracle_rejects_blank_expected_numt_interpretation_reason(
    tmp_path: Path,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    rows = read_tsv(matrix_root / FIXTURE_ORACLE_NAME)
    fieldnames = list(rows[0])
    rows[0]["numt_interpretation_reason_code"] = ""
    modified_oracle = tmp_path / "modified_oracle.tsv"
    write_oracle_fixture(modified_oracle, rows, fieldnames)

    result = run_oracle(
        matrix_root,
        tmp_path / "oracle_assertions.tsv",
        modified_oracle,
    )
    assert result.returncode != 0
    assert "blank numt_interpretation_reason_code" in result.stderr


@pytest.mark.parametrize("field", FINGERPRINT_FIELDS)
def test_oracle_rejects_invalid_frozen_fingerprint(
    tmp_path: Path,
    field: str,
) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    rows = read_tsv(matrix_root / FIXTURE_ORACLE_NAME)
    rows[0][field] = "not-a-sha256"
    modified_oracle = tmp_path / "modified_oracle.tsv"
    write_oracle_fixture(modified_oracle, rows, list(rows[0]))

    result = run_oracle(
        matrix_root,
        tmp_path / "oracle_assertions.tsv",
        modified_oracle,
    )
    assert result.returncode != 0
    assert f"invalid {field}" in result.stderr


def test_oracle_rejects_missing_observed_status_metric(tmp_path: Path) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    path = (
        matrix_root
        / "outputs"
        / "gm12878_default_run1"
        / "summary"
        / "mito_deletion_summary.tsv"
    )
    rows = [row for row in read_tsv(path) if row["metric"] != "status"]
    write_oracle_fixture(path, rows, ["metric", "value"])

    result = run_oracle(matrix_root, tmp_path / "oracle_assertions.tsv")
    assert result.returncode != 0
    assert "Missing status metric" in result.stderr


def test_prepare_rejects_unexpected_unsealed_cache_content_without_network(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "derived.bam").write_bytes(b"must not be accepted")
    result = subprocess.run(
        [str(PREPARE), "--cache", str(cache)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "MITO_OVERVIEW_PUBLIC_CURL_MAX_TIME": "1"},
    )
    assert result.returncode != 0
    assert "unexpected path" in result.stderr.lower()
    assert list(cache.iterdir()) == [cache / "derived.bam"]


def test_prepare_rejects_symlinked_cache_root_before_network(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    cache = tmp_path / "cache"
    cache.symlink_to(target, target_is_directory=True)
    marker = tmp_path / "curl-called.txt"
    fake_bin = tmp_path / "bin"
    write_fake_curl(fake_bin, marker)

    result = subprocess.run(
        [str(PREPARE), "--cache", f"{cache}/"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert result.returncode != 0
    assert "cache root must not be a symlink" in result.stderr.lower()
    assert not marker.exists()
    assert list(target.iterdir()) == []


def test_prepare_verify_does_not_create_a_missing_cache(tmp_path: Path) -> None:
    cache = tmp_path / "missing-cache"
    result = subprocess.run(
        [str(PREPARE), "--verify", "--cache", str(cache)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "sealed cache root not found" in result.stderr.lower()
    assert not cache.exists()


def test_prepare_rejects_valid_name_symlink_without_network(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    outside = tmp_path / "outside.fastq.gz"
    outside.write_bytes(b"not public data")
    (cache / "SRR10804585_1.fastq.gz").symlink_to(outside)
    marker = tmp_path / "curl-called.txt"
    fake_bin = tmp_path / "bin"
    write_fake_curl(fake_bin, marker)

    result = subprocess.run(
        [str(PREPARE), "--cache", str(cache)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert result.returncode != 0
    assert "regular, non-symlink files" in result.stderr.lower()
    assert not marker.exists()


def test_prepare_rejects_wrong_hash_without_network(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    poisoned = cache / "SRR10804585_1.fastq.gz"
    with gzip.open(poisoned, "wt", encoding="ascii", newline="") as handle:
        handle.write("@wrong\nACGT\n+\nIIII\n")
    marker = tmp_path / "curl-called.txt"
    fake_bin = tmp_path / "bin"
    write_fake_curl(fake_bin, marker)

    result = subprocess.run(
        [str(PREPARE), "--cache", str(cache)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert result.returncode != 0
    assert "byte-size mismatch" in result.stderr
    assert not marker.exists()
    assert not (cache / "raw_inputs.tsv").exists()
    assert not (cache / "CACHE_SEAL.sha256").exists()


def test_prepare_corrupt_partial_cannot_be_promoted_or_sealed(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    partial = cache / "SRR10804585_1.fastq.gz.partial"
    partial.write_bytes(b"corrupted interrupted download")
    marker = tmp_path / "curl-called.txt"
    fake_bin = tmp_path / "bin"
    write_fake_curl(fake_bin, marker)

    result = subprocess.run(
        [str(PREPARE), "--cache", str(cache)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert result.returncode != 0
    assert marker.is_file()
    assert "--continue-at -" in marker.read_text(encoding="utf-8")
    assert not (cache / "SRR10804585_1.fastq.gz").exists()
    assert not (cache / "raw_inputs.tsv").exists()
    assert not (cache / "CACHE_SEAL.sha256").exists()


def test_prepare_completes_interrupted_manifest_to_seal_without_network(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    script = PREPARE.read_text(encoding="utf-8")
    match = re.search(
        r"cat > \"\$\{SPEC_PATH\}\" <<'EOF'\n(?P<spec>.*?)\nEOF\n",
        script,
        re.DOTALL,
    )
    assert match is not None
    spec_rows = list(csv.DictReader(match.group("spec").splitlines(), delimiter="\t"))
    assert len(spec_rows) == 7
    for row in spec_rows:
        (cache / row["filename"]).write_bytes(b"fixture-fastq\n")

    fields = [
        "schema_version", "dataset_id", "run_accession", "sample_accession",
        "sample_alias", "sample_title", "source_sample_id", "library_strategy",
        "library_unit", "source_record_url", "filename", "bytes", "md5",
        "sha256", "fastq_records", "url",
    ]
    with (cache / "raw_inputs.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in spec_rows:
            writer.writerow({"schema_version": "1.0", **row, "fastq_records": "1"})

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "gzip").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (fake_bin / "gzip").chmod(0o755)
    marker = tmp_path / "curl-called.txt"
    write_fake_curl(fake_bin, marker)
    fake_python = fake_bin / "fixture-python"
    fake_python.write_text(
        f"#!{sys.executable}\n"
        "import hashlib, sys\n"
        "source = sys.stdin.read()\n"
        "if 'print(digest.hexdigest())' in source:\n"
        "    print(hashlib.sha256(open(sys.argv[2], 'rb').read()).hexdigest())\n"
        "elif 'expected_bytes, expected_md5, expected_sha256' in source:\n"
        "    print('1')\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    result = subprocess.run(
        [str(PREPARE), "--cache", str(cache)],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "MITO_OVERVIEW_PYTHON": str(fake_python),
        },
    )
    assert result.returncode == 0, result.stderr
    assert "completed interrupted cache finalization" in result.stdout
    assert (cache / "CACHE_SEAL.sha256").is_file()
    assert not marker.exists()


def test_matrix_rejects_symlinked_cache_root_before_execution(tmp_path: Path) -> None:
    target = tmp_path / "cache-target"
    target.mkdir()
    cache = tmp_path / "cache"
    cache.symlink_to(target, target_is_directory=True)
    result = subprocess.run(
        matrix_command(tmp_path, cache),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "sealed raw cache must not be a symlink" in result.stderr.lower()
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "output").exists()


def test_matrix_rejects_symlinked_workspace_before_execution(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    work_target = tmp_path / "work-target"
    work_target.mkdir()
    (tmp_path / "work").symlink_to(work_target, target_is_directory=True)
    result = subprocess.run(
        matrix_command(tmp_path, cache),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "validation work root must not be a symlink" in result.stderr.lower()
    assert list(work_target.iterdir()) == []
    assert not (tmp_path / "output").exists()


def test_matrix_rejects_symlinked_oracle_before_execution(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    oracle_link = tmp_path / "oracle.tsv"
    oracle_link.symlink_to(ORACLE)
    command = matrix_command(tmp_path, cache)
    command[-1] = str(oracle_link)
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "oracle tsv not found or is a symlink" in result.stderr.lower()
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "output").exists()


def test_matrix_rejects_wrong_thread_count_before_execution(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    result = subprocess.run(
        matrix_command(tmp_path, cache),
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "THREADS": "8"},
    )
    assert result.returncode != 0
    assert "validation thread count mismatch: 8 != 4" in result.stderr.lower()
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "output").exists()


def test_matrix_rejects_legacy_positional_interface() -> None:
    result = subprocess.run(
        [str(MATRIX), "/tmp/legacy-output"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Unknown or legacy argument" in result.stderr


def test_matrix_rejects_a_platform_identity_mismatch_before_execution(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    result = subprocess.run(
        [
            str(MATRIX),
            "--mode",
            "offline",
            "--cache",
            str(cache),
            "--work",
            str(tmp_path / "work"),
            "--output",
            str(tmp_path / "output"),
            "--oracle",
            str(ORACLE),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "MITO_OVERVIEW_EXPECTED_PLATFORM": "unsupported-platform",
        },
    )
    assert result.returncode != 0
    assert "Validation platform mismatch" in result.stderr


def test_matrix_binds_input_hashes_to_manifest_sha256_and_filename_columns() -> None:
    contract = MATRIX.read_text(encoding="utf-8")
    assert "NR > 1 {print $14 \"  \" $11}" in contract
    assert "NR > 1 {print $10 \"  \" $7}" not in contract


def test_matrix_requires_installed_distribution_and_exact_runtime_contract() -> None:
    contract = MATRIX.read_text(encoding="utf-8")
    assert '"MITO_OVERVIEW_REQUIRE_INSTALLED=1"' in contract
    assert '"PYTHONPATH="' in contract
    assert "VALIDATION_THREADS=4" in contract
    assert "expected_threads != 4" in contract
    assert '"threads": expected_threads' in contract
    for expected in (
        '"mito-overview": "0.3.0"',
        '"pysam": "0.24.0"',
        '"samtools 1.23.1"',
        '"Using htslib 1.23.1"',
        '"2.31-r1302"',
        '"0.7.19-r1273"',
    ):
        assert expected in contract


def test_offline_mode_requires_os_isolation_and_keeps_entrypoint_canaries() -> None:
    matrix = MATRIX.read_text(encoding="utf-8")
    wrapper = ISOLATION_WRAPPER.read_text(encoding="utf-8")
    short = SHORT_RUNNER.read_text(encoding="utf-8")
    long = LONG_RUNNER.read_text(encoding="utf-8")
    mvtool = (
        REPO_ROOT / "mito_overview" / "steps" / "mito_mvtool_annotation.py"
    ).read_text(encoding="utf-8")

    assert "for guarded_command in curl wget" in matrix
    assert "run_network_isolated_v0.3.0.sh" in matrix
    assert "offline_isolation" in matrix
    assert "network_isolation_verdict" in matrix
    assert "MITO_OVERVIEW_SHORTREAD_MVTOOL_MODE=disabled" in matrix
    assert "MITO_OVERVIEW_LONGREAD_MVTOOL_MODE=disabled" in matrix
    assert "curl" in short and "wget" not in short
    assert "curl" in long and "wget" not in long
    assert "requests.Session" in mvtool
    assert "project_network_entrypoints" in matrix
    assert "sandbox-exec -p '(version 1) (allow default) (deny network*)'" in wrapper
    assert '"${SUDO_BIN}" -n "${UNSHARE_BIN}" --net --' in wrapper
    assert '--reuid="${INVOKING_UID}"' in wrapper
    assert '--regid="${INVOKING_GID}"' in wrapper
    assert "parent_loopback_control" in wrapper
    assert "isolated_loopback_probe" in wrapper
    assert "network_isolation_verdict" in wrapper
    assert "fallback" not in wrapper.lower()


def test_matrix_fails_closed_without_wrapper_evidence(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    env = os.environ.copy()
    env.pop("MITO_OVERVIEW_NETWORK_ISOLATION_ACTIVE", None)
    env.pop("MITO_OVERVIEW_NETWORK_ISOLATION_EVIDENCE", None)
    result = subprocess.run(
        [
            str(MATRIX),
            "--mode",
            "offline",
            "--cache",
            str(cache),
            "--work",
            str(tmp_path / "work"),
            "--output",
            str(tmp_path / "output"),
            "--oracle",
            str(ORACLE),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "must run through scripts/run_network_isolated_v0.3.0.sh" in result.stderr
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "output").exists()


def test_matrix_rejects_malformed_isolation_evidence_before_execution(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    evidence = tmp_path / "network_isolation.tsv"
    evidence.write_text(
        "field\tvalue\nnetwork_isolation_verdict\tPASS\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            str(MATRIX),
            "--mode",
            "offline",
            "--cache",
            str(cache),
            "--work",
            str(tmp_path / "work"),
            "--output",
            str(tmp_path / "output"),
            "--oracle",
            str(ORACLE),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "MITO_OVERVIEW_NETWORK_ISOLATION_ACTIVE": "1",
            "MITO_OVERVIEW_NETWORK_ISOLATION_EVIDENCE": str(evidence),
        },
    )
    assert result.returncode != 0
    assert "network-isolation evidence mismatch" in result.stderr
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "output").exists()


def test_matrix_executes_runtime_version_gate_and_rejects_wrong_samtools(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    evidence = tmp_path / "network_isolation.tsv"
    write_valid_isolation_evidence(evidence)

    # Install the checkout without dependencies into a disposable interpreter.
    # System-site packages supply the exact lock already used by this test run.
    venv_root = tmp_path / "runtime-venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    python_bin = venv_root / "bin" / "python"
    subprocess.run(
        [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-build-isolation",
            str(REPO_ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    fake_bin = tmp_path / "wrong-runtime-bin"
    fake_bin.mkdir()
    samtools = fake_bin / "samtools"
    samtools.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'samtools 0.0.0\\nUsing htslib 0.0.0\\n'\n",
        encoding="utf-8",
    )
    samtools.chmod(0o755)

    result = subprocess.run(
        matrix_command(tmp_path, cache),
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "MITO_OVERVIEW_PYTHON": str(python_bin),
            "MITO_OVERVIEW_NETWORK_ISOLATION_ACTIVE": "1",
            "MITO_OVERVIEW_NETWORK_ISOLATION_EVIDENCE": str(evidence),
        },
    )
    assert result.returncode != 0
    assert "samtools version mismatch" in result.stderr.lower()
    assert not (tmp_path / "output" / "cases.tsv").exists()


def test_matrix_executes_runtime_gate_and_rejects_wrong_python(tmp_path: Path) -> None:
    system_python = Path("/usr/bin/python3")
    assert system_python.is_file()
    observed = subprocess.run(
        [str(system_python), "-c", "import platform; print(platform.python_version())"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert observed != "3.12.13"

    cache = tmp_path / "cache"
    cache.mkdir()
    evidence = tmp_path / "network_isolation.tsv"
    write_valid_isolation_evidence(evidence)
    result = subprocess.run(
        matrix_command(tmp_path, cache),
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "MITO_OVERVIEW_PYTHON": str(system_python),
            "MITO_OVERVIEW_NETWORK_ISOLATION_ACTIVE": "1",
            "MITO_OVERVIEW_NETWORK_ISOLATION_EVIDENCE": str(evidence),
        },
    )
    assert result.returncode != 0
    assert f"python version mismatch: {observed} != 3.12.13" in result.stderr.lower()
    assert not (tmp_path / "output" / "cases.tsv").exists()


def test_isolation_wrapper_blocks_an_executed_network_attempt_or_fails_closed(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "network_isolation.tsv"
    attempted_network = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=0.5)\n"
        "except OSError:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit('network unexpectedly reachable')\n"
    )
    result = subprocess.run(
        [
            str(ISOLATION_WRAPPER),
            "--evidence",
            str(evidence),
            "--",
            sys.executable,
            "-I",
            "-c",
            attempted_network,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if result.returncode != 0:
        # Some outer sandboxes deny even the wrapper's pre-isolation parent
        # control socket. That is a valid fail-closed result, never a PASS.
        assert "Parent loopback listener terminated during startup" in result.stderr
        assert not evidence.exists()
        return
    rows = {row["field"]: row["value"] for row in read_tsv(evidence)}
    assert rows["parent_loopback_control"] == "reachable"
    assert rows["isolated_loopback_probe"] == "blocked"
    assert rows["network_isolation_verdict"] == "PASS"


def test_isolation_wrapper_rejects_incomplete_or_reused_interfaces(tmp_path: Path) -> None:
    missing_command = subprocess.run(
        [str(ISOLATION_WRAPPER), "--evidence", str(tmp_path / "evidence.tsv"), "--"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_command.returncode == 2
    assert "A command is required" in missing_command.stderr

    existing = tmp_path / "existing.tsv"
    existing.write_text("do not reuse\n", encoding="utf-8")
    reused = subprocess.run(
        [str(ISOLATION_WRAPPER), "--evidence", str(existing), "--", "/usr/bin/true"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert reused.returncode != 0
    assert "must not already exist" in reused.stderr


def test_network_isolation_shell_entrypoints_pass_bash_syntax() -> None:
    for path in (ISOLATION_WRAPPER, MATRIX):
        completed = subprocess.run(
            ["bash", "-n", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr


def test_oracle_has_exactly_six_unique_profiles() -> None:
    rows = read_tsv(ORACLE)
    assert len(rows) == 6
    assert {(row["dataset"], row["profile"]) for row in rows} == {
        (dataset, profile)
        for dataset in ("GM11906", "GM12878")
        for profile in ("lenient", "default", "strict")
    }
