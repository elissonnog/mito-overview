from __future__ import annotations

import csv
import gzip
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
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
