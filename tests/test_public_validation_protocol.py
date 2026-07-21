from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
PREPARE = REPO_ROOT / "scripts" / "prepare_public_validation_cache_v0.3.0.sh"
MATRIX = REPO_ROOT / "scripts" / "run_public_validation_matrix_v0.3.0.sh"
SHORT_RUNNER = REPO_ROOT / "scripts" / "run_public_shortread_validation_gm11906.sh"
LONG_RUNNER = REPO_ROOT / "scripts" / "run_public_longread_validation_gm12878.sh"
ASSERT_ORACLE = REPO_ROOT / "scripts" / "assert_public_validation_oracle_v0.3.0.py"
ORACLE = (
    REPO_ROOT
    / "examples"
    / "public_validation"
    / "public_validation_oracle_v0.3.0.tsv"
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_metric_table(path: Path, values: dict[str, object]) -> None:
    path.write_text(
        "metric\tvalue\n"
        + "".join(f"{metric}\t{value}\n" for metric, value in values.items()),
        encoding="utf-8",
    )


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
            "allele_min_base_quality": oracle["min_base_quality"],
            "allele_min_mapping_quality": oracle["min_mapping_quality"],
            "allele_min_read_mean_quality": oracle["min_read_mean_quality"],
            "accepted_observations": oracle["accepted_observations"],
            "excluded_observations": oracle["excluded_observations"],
        },
    )
    write_metric_table(
        summary / "mito_copy_number_summary.tsv", {"status": oracle["copy_number_status"]}
    )
    write_metric_table(
        summary / "mito_mvtool_annotation_summary.tsv", {"status": oracle["mvtool_status"]}
    )
    write_metric_table(
        summary / "mito_numt_qc_summary.tsv",
        {
            "status": oracle["numt_module_status"],
            "numt_interpretation_status": oracle["numt_interpretation_status"],
            "reason_code": oracle["numt_reason_code"],
        },
    )
    (summary / "mito_variant_consequence_candidates.tsv").write_text(
        "position\tref_base\talt_base\tfeature_label\tfeature_class\tconsequence_class\n"
        "8344\tA\tG\tMT-TK\tMt_tRNA\ttRNA_variant\n",
        encoding="utf-8",
    )

    if oracle["dataset"] == "GM12878":
        write_metric_table(
            summary / "mito_phymer_haplogroup_summary.tsv",
            {"status": oracle["phymer_status"]},
        )
        write_metric_table(
            summary / "mito_methylation_exploratory_summary.tsv",
            {"status": oracle["methylation_status"]},
        )
        write_metric_table(
            summary / "mito_qc_summary.tsv",
            {
                "mapped_reads": oracle["mapped_reads"],
                "primary_reads": oracle["primary_reads"],
                "supplementary_reads": oracle["supplementary_reads"],
                "mean_depth": oracle["mean_depth"],
                "median_depth": oracle["median_depth"],
            },
        )
        write_metric_table(
            summary / "mito_cosegregation_summary.tsv",
            {"selected_sites": oracle["selected_cosegregation_sites"]},
        )
        write_metric_table(
            summary / "mito_deletion_summary.tsv",
            {
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


def run_oracle(matrix_root: Path, report: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(ASSERT_ORACLE),
            "--matrix-root",
            str(matrix_root),
            "--oracle",
            str(ORACLE),
            "--report",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_owned_shell_scripts_are_syntactically_valid() -> None:
    subprocess.run(
        ["bash", "-n", str(PREPARE), str(MATRIX), str(SHORT_RUNNER), str(LONG_RUNNER)],
        check=True,
    )


def test_oracle_accepts_exact_six_profile_fixture(tmp_path: Path) -> None:
    matrix_root = tmp_path / "matrix"
    build_matrix_fixture(matrix_root)
    report = tmp_path / "oracle_assertions.tsv"
    result = run_oracle(matrix_root, report)
    assert result.returncode == 0, result.stderr
    assertions = read_tsv(report)
    assert assertions
    assert {row["verdict"] for row in assertions} == {"PASS"}


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


def test_matrix_rejects_legacy_positional_interface() -> None:
    result = subprocess.run(
        [str(MATRIX), "/tmp/legacy-output"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Unknown or legacy argument" in result.stderr


def test_oracle_has_exactly_six_unique_profiles() -> None:
    rows = read_tsv(ORACLE)
    assert len(rows) == 6
    assert {(row["dataset"], row["profile"]) for row in rows} == {
        (dataset, profile)
        for dataset in ("GM11906", "GM12878")
        for profile in ("lenient", "default", "strict")
    }
