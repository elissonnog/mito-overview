#!/usr/bin/env python3
"""Build the fixed v0.3.0 tracked public-validation asset inventory."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path, PurePosixPath

import pandas as pd


SHORT_CASE = "outputs/gm11906_default_run1"
LONG_CASE = "outputs/gm12878_default_run1"
SHORT_DEST = "GM11906_MERRF_shortread"
LONG_DEST = "GM12878_ONT_longread"
ORACLE_DEST = "public_validation_oracle_v0.3.0.tsv"
SHORT_README_DEST = f"{SHORT_DEST}/README.md"

REQUIRED_CASE_IDS = (
    "gm11906_default_run1",
    "gm11906_default_run2",
    "gm11906_lenient",
    "gm11906_strict",
    "gm12878_default_run1",
    "gm12878_default_run2",
    "gm12878_lenient",
    "gm12878_strict",
    "gm11906_repeatability",
    "gm12878_repeatability",
    "gm11906_visual_integrity",
    "gm12878_visual_integrity",
    "filter_profiles",
    "public_oracle",
    "raw_cache_seal",
    "offline_isolation",
    "project_network_entrypoints",
)

SHORT_SUMMARIES = (
    "mito_gene_summary.tsv",
    "mito_heteroplasmy_candidates.tsv",
    "mito_qc_summary.tsv",
    "mito_variant_consequence_candidates.tsv",
)
SHORT_FIGURES = (
    "mito_feature_annotation.png",
    "mito_gene_summary_overview.png",
    "mito_heteroplasmy_landscape.png",
    "mito_variant_consequence_classes.png",
)
SHORT_PROVENANCE = ("GM11906_MERRF_shortread.alignment.provenance.json",)

LONG_SUMMARIES = (
    "mito_circularity_qc_summary.tsv",
    "mito_copy_number_summary.tsv",
    "mito_cosegregation_pairwise.tsv",
    "mito_cosegregation_selected_sites.tsv",
    "mito_cosegregation_summary.tsv",
    "mito_deletion_clusters.tsv",
    "mito_deletion_summary.tsv",
    "mito_gene_summary.tsv",
    "mito_heteroplasmy_candidates.tsv",
    "mito_identity_qc_summary.tsv",
    "mito_methylation_exploratory_summary.tsv",
    "mito_mvtool_annotation_summary.tsv",
    "mito_numt_qc_summary.tsv",
    "mito_phymer_haplogroup_summary.tsv",
    "mito_qc_summary.tsv",
    "mito_variant_consequence_candidates.tsv",
    "mito_variant_consequence_class_summary.tsv",
)
LONG_FIGURES = (
    "mito_circularity_edge_metrics.png",
    "mito_cosegregation_heatmap.png",
    "mito_deletion_clusters.png",
    "mito_depth_profile.png",
    "mito_gene_summary_overview.png",
    "mito_heteroplasmy_landscape.png",
    "mito_numt_qc_mapq_vs_span.png",
    "mito_variant_consequence_classes.png",
)
LONG_PROVENANCE = (
    "GM12878_ONT_longread.fastq_subset.provenance.json",
    "GM12878_ONT_longread.reduced_alignment.provenance.json",
    "GM12878_ONT_longread.selected_qnames.txt",
)


def _case_copies(
    case: str, destination: str, component: str, names: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (f"{case}/{component}/{name}", f"{destination}/{component}/{name}")
        for name in names
    )


# Every byte-for-byte copy is named here. In particular, report HTML, methylation
# tracks, source-library metadata, alignments, raw reads, and run records have no entry.
COPY_SPECS = (
    ("cases.tsv", "public_validation_cases_v0.3.0.tsv"),
    ("filter_profile_results.tsv", "filter_profile_results_v0.3.0.tsv"),
    ("inputs.sha256", "public_validation_inputs_v0.3.0.sha256"),
    (
        "outputs/GM11906_MERRF_shortread.8344.mpileup",
        f"{SHORT_DEST}/GM11906_MERRF_shortread.8344.mpileup",
    ),
    (
        "outputs/GM11906_MERRF_shortread.flagstat.txt",
        f"{SHORT_DEST}/GM11906_MERRF_shortread.flagstat.txt",
    ),
    (
        "outputs/GM12878_ONT_longread.flagstat.txt",
        f"{LONG_DEST}/GM12878_ONT_longread.flagstat.txt",
    ),
    *_case_copies(SHORT_CASE, SHORT_DEST, "summary", SHORT_SUMMARIES),
    *_case_copies(SHORT_CASE, SHORT_DEST, "figures", SHORT_FIGURES),
    *_case_copies(SHORT_CASE, SHORT_DEST, "provenance", SHORT_PROVENANCE),
    *_case_copies(LONG_CASE, LONG_DEST, "summary", LONG_SUMMARIES),
    *_case_copies(LONG_CASE, LONG_DEST, "figures", LONG_FIGURES),
    *_case_copies(LONG_CASE, LONG_DEST, "provenance", LONG_PROVENANCE),
)

GENERATED_FILES = frozenset(
    {
        f"{SHORT_DEST}/GM11906_MERRF_shortread_key_findings.tsv",
        f"{SHORT_DEST}/GM11906_MERRF_shortread_site_8344.tsv",
        f"{SHORT_DEST}/GM11906_MERRF_shortread_site_8344_consequence.tsv",
        f"{SHORT_DEST}/GM11906_MERRF_shortread_top_gene_summary.tsv",
        f"{SHORT_DEST}/figures/GM11906_MERRF_shortread_montage.png",
        f"{LONG_DEST}/GM12878_ONT_longread_key_findings.tsv",
        f"{LONG_DEST}/GM12878_ONT_longread_top_deletion_clusters.tsv",
        f"{LONG_DEST}/GM12878_ONT_longread_top_gene_summary.tsv",
        f"{LONG_DEST}/GM12878_ONT_longread_top_heteroplasmy_candidates.tsv",
        f"{LONG_DEST}/figures/GM12878_ONT_longread_montage.png",
        f"{LONG_DEST}/README.md",
    }
)
PRESERVED_FILES = frozenset({ORACLE_DEST, SHORT_README_DEST})
EXPECTED_FILES = frozenset(destination for _, destination in COPY_SPECS) | GENERATED_FILES | PRESERVED_FILES


def _parent_directories(paths: frozenset[str]) -> frozenset[str]:
    directories: set[str] = set()
    for value in paths:
        parent = PurePosixPath(value).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return frozenset(directories)


EXPECTED_DIRECTORIES = _parent_directories(EXPECTED_FILES)
if len(EXPECTED_FILES) != 56:  # pragma: no cover - protects edits to the literal contract.
    raise RuntimeError(f"Internal inventory contract has {len(EXPECTED_FILES)} files, expected 56")

TEXT_SUFFIXES = frozenset({".json", ".md", ".mpileup", ".sha256", ".tsv", ".txt"})
POSIX_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9:+._~/-])/(?!/)(?:[^\s\"'<>|]+)")
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?<![A-Za-z0-9])[a-z]:[\\/]")
UNC_ABSOLUTE_PATH = re.compile(r"(?<![\\])\\\\[^\\\s]+\\[^\\\s]+")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RefreshError(RuntimeError):
    """A fail-closed validation error suitable for concise CLI output."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-root", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument(
        "--oracle",
        "--frozen-oracle",
        dest="oracle",
        type=Path,
        help=f"Frozen oracle to copy to {ORACLE_DEST}; otherwise preserve it from destination.",
    )
    parser.add_argument(
        "--gm11906-readme",
        type=Path,
        help=f"Curated README to copy to {SHORT_README_DEST}; otherwise preserve it from destination.",
    )
    return parser.parse_args(argv)


def absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def relative_inventory(root: Path, label: str) -> tuple[frozenset[str], frozenset[str]]:
    if root.is_symlink():
        raise RefreshError(f"{label} must not be a symlink")
    if not root.exists():
        raise RefreshError(f"{label} does not exist")
    if not root.is_dir():
        raise RefreshError(f"{label} must be a directory")

    files: set[str] = set()
    directories: set[str] = set()
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in sorted(dirnames):
            path = directory_path / name
            mode = path.lstat().st_mode
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                raise RefreshError(f"{label} contains a symlink: {relative}")
            if not stat.S_ISDIR(mode):
                raise RefreshError(f"{label} contains a non-directory entry: {relative}")
            directories.add(relative)
        for name in sorted(filenames):
            path = directory_path / name
            mode = path.lstat().st_mode
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                raise RefreshError(f"{label} contains a symlink: {relative}")
            if not stat.S_ISREG(mode):
                raise RefreshError(f"{label} contains a non-regular file: {relative}")
            files.add(relative)
    return frozenset(files), frozenset(directories)


def require_regular_file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise RefreshError(f"{label} must not be a symlink")
    if not path.is_file():
        raise RefreshError(f"Missing required file: {label}")
    if not stat.S_ISREG(path.stat().st_mode):
        raise RefreshError(f"{label} must be a regular file")
    if path.stat().st_size == 0:
        raise RefreshError(f"{label} must not be empty")
    return path


def required_matrix_file(matrix_root: Path, relative: str) -> Path:
    return require_regular_file(matrix_root / PurePosixPath(relative), relative)


def read_tsv(path: Path, expected_header: tuple[str, ...], label: str) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != expected_header:
                raise RefreshError(
                    f"{label} has header {tuple(reader.fieldnames or ())!r}; expected {expected_header!r}"
                )
            return list(reader)
    except UnicodeDecodeError as exc:
        raise RefreshError(f"{label} is not valid UTF-8") from exc


def validate_cases(matrix_root: Path) -> None:
    path = required_matrix_file(matrix_root, "cases.tsv")
    rows = read_tsv(
        path,
        ("case_id", "category", "input_available", "expected_available", "verdict", "detail"),
        "cases.tsv",
    )
    if len(rows) != len(REQUIRED_CASE_IDS):
        raise RefreshError(
            f"cases.tsv must contain exactly {len(REQUIRED_CASE_IDS)} cases; observed {len(rows)}"
        )
    identifiers = [row["case_id"] for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise RefreshError("cases.tsv contains duplicate case_id values")
    missing = sorted(set(REQUIRED_CASE_IDS) - set(identifiers))
    unexpected = sorted(set(identifiers) - set(REQUIRED_CASE_IDS))
    if missing or unexpected:
        raise RefreshError(f"cases.tsv case set mismatch: missing={missing!r} unexpected={unexpected!r}")
    failures = sorted(row["case_id"] for row in rows if row["verdict"] != "PASS")
    if failures:
        raise RefreshError(f"cases.tsv contains non-PASS verdicts: {failures!r}")
    unavailable = sorted(
        row["case_id"]
        for row in rows
        if row["input_available"] != "1" or row["expected_available"] != "1"
    )
    if unavailable:
        raise RefreshError(f"cases.tsv contains unavailable required evidence: {unavailable!r}")


def validate_oracle_assertions(matrix_root: Path) -> None:
    path = required_matrix_file(matrix_root, "oracle_assertions.tsv")
    rows = read_tsv(
        path,
        ("assertion_id", "verdict", "expected", "observed", "detail"),
        "oracle_assertions.tsv",
    )
    if not rows:
        raise RefreshError("oracle_assertions.tsv must contain at least one assertion")
    identifiers = [row["assertion_id"] for row in rows]
    if any(not identifier for identifier in identifiers) or len(set(identifiers)) != len(identifiers):
        raise RefreshError("oracle_assertions.tsv contains blank or duplicate assertion_id values")
    failures = sorted(row["assertion_id"] for row in rows if row["verdict"] != "PASS")
    if failures:
        raise RefreshError(f"oracle_assertions.tsv contains non-PASS assertions: {failures!r}")


def reject_absolute_paths(path: Path, label: str) -> None:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name != "README.md":
        return
    try:
        value = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RefreshError(f"{label} is not valid UTF-8") from exc
    if (
        POSIX_ABSOLUTE_PATH.search(value)
        or WINDOWS_ABSOLUTE_PATH.search(value)
        or UNC_ABSOLUTE_PATH.search(value)
    ):
        raise RefreshError(f"{label} contains a local absolute path")


def validate_input_manifest(matrix_root: Path) -> None:
    path = required_matrix_file(matrix_root, "inputs.sha256")
    entries: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fields = line.split("  ", 1)
        if len(fields) != 2 or not HEX_SHA256.fullmatch(fields[0]):
            raise RefreshError(f"inputs.sha256 has a malformed line {line_number}")
        relative = PurePosixPath(fields[1])
        if relative.is_absolute() or not fields[1] or ".." in relative.parts:
            raise RefreshError(f"inputs.sha256 has a non-relative path on line {line_number}")
        entries.append(fields[1])
    if not entries:
        raise RefreshError("inputs.sha256 must contain at least one entry")
    if entries != sorted(entries) or len(entries) != len(set(entries)):
        raise RefreshError("inputs.sha256 paths must be unique and sorted")


def validate_destination(destination: Path) -> None:
    if destination.is_symlink():
        raise RefreshError("Destination must not be a symlink")
    if not destination.exists():
        return
    files, directories = relative_inventory(destination, "Destination")
    unexpected_files = sorted(files - EXPECTED_FILES)
    unexpected_directories = sorted(directories - EXPECTED_DIRECTORIES)
    if unexpected_files or unexpected_directories:
        raise RefreshError(
            "Destination has unexpected inventory: "
            f"files={unexpected_files!r} directories={unexpected_directories!r}"
        )


def preservation_source(
    supplied: Path | None,
    destination: Path,
    relative: str,
    option: str,
) -> Path:
    if supplied is not None:
        return require_regular_file(absolute_lexical(supplied), option)
    if not destination.exists():
        raise RefreshError(f"{option} is required when destination does not exist")
    return require_regular_file(destination / PurePosixPath(relative), f"destination/{relative}")


def prepare_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o755)


def copy_regular(source: Path, destination: Path) -> None:
    prepare_directory(destination.parent)
    shutil.copyfile(source, destination)
    destination.chmod(0o644)


def write_dataframe(frame: pd.DataFrame, destination: Path) -> None:
    prepare_directory(destination.parent)
    frame.to_csv(destination, sep="\t", index=False, lineterminator="\n")
    destination.chmod(0o644)


def load_metric_table(summary_dir: Path, name: str) -> pd.DataFrame:
    path = summary_dir / name
    if path.is_file() and path.stat().st_size > 0:
        return pd.read_csv(path, sep="\t")
    return pd.DataFrame()


def build_short_key_tables(matrix_root: Path, stage: Path) -> None:
    source = matrix_root / SHORT_CASE / "summary"
    destination = stage / SHORT_DEST
    qc = pd.read_csv(source / "mito_qc_summary.tsv", sep="\t")
    heteroplasmy = pd.read_csv(source / "mito_heteroplasmy_candidates.tsv", sep="\t")
    heteroplasmy_summary = pd.read_csv(source / "mito_heteroplasmy_summary.tsv", sep="\t")
    gene = pd.read_csv(source / "mito_gene_summary.tsv", sep="\t")
    consequence = pd.read_csv(source / "mito_variant_consequence_candidates.tsv", sep="\t")

    qc_map = dict(zip(qc["metric"], qc["value"], strict=True))
    heteroplasmy_map = dict(
        zip(heteroplasmy_summary["metric"], heteroplasmy_summary["value"], strict=True)
    )
    findings = pd.DataFrame(
        [
            {"metric": "sample_id", "value": "GM11906_MERRF_shortread"},
            {"metric": "read_mode", "value": "short"},
            {"metric": "assay_type", "value": "targeted_mt"},
            {"metric": "source_library_strategy", "value": "ATAC-seq"},
            {"metric": "source_library_unit", "value": "single_cell_library"},
            {"metric": "pooled_source_library_count", "value": 3},
            {
                "metric": "allele_fraction_interpretation",
                "value": "pooled_read_observation_fraction",
            },
            {
                "metric": "min_callable_depth",
                "value": heteroplasmy_map.get("min_callable_depth", "NA"),
            },
            {
                "metric": "min_alt_allele_fraction",
                "value": heteroplasmy_map.get("min_alt_allele_fraction", "NA"),
            },
            {"metric": "mapped_reads", "value": qc_map.get("mapped_reads", "NA")},
            {"metric": "mean_depth", "value": qc_map.get("mean_depth", "NA")},
            {"metric": "median_depth", "value": qc_map.get("median_depth", "NA")},
            {
                "metric": "high_query_alignment_fraction",
                "value": qc_map.get("high_query_alignment_fraction", "NA"),
            },
            {"metric": "candidate_site_count", "value": len(heteroplasmy)},
        ]
    )
    write_dataframe(findings, destination / "GM11906_MERRF_shortread_key_findings.tsv")
    write_dataframe(
        heteroplasmy[heteroplasmy["position"] == 8344].copy(),
        destination / "GM11906_MERRF_shortread_site_8344.tsv",
    )
    write_dataframe(
        consequence[consequence["position"] == 8344].copy(),
        destination / "GM11906_MERRF_shortread_site_8344_consequence.tsv",
    )
    write_dataframe(gene.head(10).copy(), destination / "GM11906_MERRF_shortread_top_gene_summary.tsv")


def build_long_assets(matrix_root: Path, stage: Path) -> int:
    source = matrix_root / LONG_CASE
    summary = source / "summary"
    provenance = source / "provenance"
    destination = stage / LONG_DEST

    qc = load_metric_table(summary, "mito_qc_summary.tsv")
    heteroplasmy = load_metric_table(summary, "mito_heteroplasmy_candidates.tsv")
    heteroplasmy_summary = load_metric_table(summary, "mito_heteroplasmy_summary.tsv")
    deletions = load_metric_table(summary, "mito_deletion_summary.tsv")
    clusters = load_metric_table(summary, "mito_deletion_clusters.tsv")
    gene = load_metric_table(summary, "mito_gene_summary.tsv")
    copy_number = load_metric_table(summary, "mito_copy_number_summary.tsv")
    phymer = load_metric_table(summary, "mito_phymer_haplogroup_summary.tsv")
    methylation = load_metric_table(summary, "mito_methylation_exploratory_summary.tsv")
    cosegregation = load_metric_table(summary, "mito_cosegregation_summary.tsv")
    numt = load_metric_table(summary, "mito_numt_qc_summary.tsv")
    mvtool = load_metric_table(summary, "mito_mvtool_annotation_summary.tsv")
    consequence_classes = load_metric_table(summary, "mito_variant_consequence_class_summary.tsv")

    subset_provenance = json.loads(
        (provenance / "GM12878_ONT_longread.fastq_subset.provenance.json").read_text(
            encoding="utf-8"
        )
    )
    alignment_provenance = json.loads(
        (provenance / "GM12878_ONT_longread.reduced_alignment.provenance.json").read_text(
            encoding="utf-8"
        )
    )
    selection = subset_provenance["selection"]
    source_fastq = subset_provenance["source_fastq"]
    subset_fastq = subset_provenance["subset_fastq"]
    selected_names = subset_provenance["selected_query_names"]
    selected_count = int(selection["selected_query_names"])
    source_count = int(selection["source_records_seen"])
    selection_fraction = selected_count / source_count if source_count else float("nan")

    def metric_map(frame: pd.DataFrame) -> dict[object, object]:
        return dict(zip(frame.get("metric", []), frame.get("value", []), strict=True))

    qc_map = metric_map(qc)
    heteroplasmy_map = metric_map(heteroplasmy_summary)
    deletion_map = metric_map(deletions)
    copy_map = metric_map(copy_number)
    phymer_map = metric_map(phymer)
    methylation_map = metric_map(methylation)
    cosegregation_map = metric_map(cosegregation)
    numt_map = metric_map(numt)
    mvtool_map = metric_map(mvtool)

    findings = pd.DataFrame(
        [
            {"metric": "sample_id", "value": f"GM12878_ONT_longread_reduced_qn{selected_count}"},
            {"metric": "source_accession", "value": "SRR18110025"},
            {
                "metric": "input_scope",
                "value": "resource-limited deterministic query-name subset",
            },
            {"metric": "complete_run_analyzed", "value": 0},
            {"metric": "statistical_representativeness_claimed", "value": 0},
            {"metric": "selector_algorithm", "value": selection["algorithm"]},
            {"metric": "selection_seed", "value": selection["seed"]},
            {"metric": "source_fastq_records", "value": source_count},
            {"metric": "selected_query_names", "value": selected_count},
            {"metric": "selection_fraction", "value": round(selection_fraction, 8)},
            {"metric": "source_fastq_sha256", "value": source_fastq["sha256"]},
            {"metric": "subset_fastq_sha256", "value": subset_fastq["sha256"]},
            {"metric": "selected_query_names_sha256", "value": selected_names["sha256"]},
            {
                "metric": "alignment_bam_sha256",
                "value": alignment_provenance["alignment"]["sha256"],
            },
            {
                "metric": "alignment_bai_sha256",
                "value": alignment_provenance["alignment_index"]["sha256"],
            },
            {"metric": "read_mode", "value": "long"},
            {"metric": "assay_type", "value": "targeted_mt"},
            {
                "metric": "min_callable_depth",
                "value": heteroplasmy_map.get("min_callable_depth", "NA"),
            },
            {
                "metric": "min_alt_allele_fraction",
                "value": heteroplasmy_map.get("min_alt_allele_fraction", "NA"),
            },
            {
                "metric": "mapped_alignment_records",
                "value": qc_map.get("mapped_reads", "NA"),
            },
            {
                "metric": "primary_alignment_records",
                "value": qc_map.get("primary_reads", "NA"),
            },
            {
                "metric": "supplementary_alignment_records",
                "value": qc_map.get("supplementary_reads", "NA"),
            },
            {
                "metric": "secondary_alignment_records",
                "value": qc_map.get("secondary_reads", "NA"),
            },
            {
                "metric": "allele_engine_unique_query_names_seen",
                "value": heteroplasmy_map.get("unique_reads_seen", "NA"),
            },
            {"metric": "mean_depth", "value": qc_map.get("mean_depth", "NA")},
            {"metric": "median_depth", "value": qc_map.get("median_depth", "NA")},
            {
                "metric": "full_length_fraction",
                "value": qc_map.get("full_length_fraction", "NA"),
            },
            {"metric": "candidate_site_count", "value": len(heteroplasmy)},
            {
                "metric": "selected_cosegregation_sites",
                "value": cosegregation_map.get("selected_sites", "NA"),
            },
            {
                "metric": "candidate_deletion_clusters",
                "value": deletion_map.get("candidate_deletion_clusters", "NA"),
            },
            {
                "metric": "deletion_screen_method",
                "value": (
                    "CIGAR-deletion candidate screen; supplementary/SA evidence summarized separately"
                ),
            },
            {
                "metric": "largest_median_deletion",
                "value": deletion_map.get("largest_median_deletion", "NA"),
            },
            {
                "metric": "max_deletion_support_fraction_primary",
                "value": deletion_map.get("max_support_fraction_primary", "NA"),
            },
            {
                "metric": "numt_interpretation_status",
                "value": numt_map.get("numt_interpretation_status", "NA"),
            },
            {"metric": "numt_reason_code", "value": numt_map.get("reason_code", "NA")},
            {"metric": "copy_number_status", "value": copy_map.get("status", "NA")},
            {"metric": "phymer_status", "value": phymer_map.get("status", "NA")},
            {"metric": "methylation_status", "value": methylation_map.get("status", "NA")},
            {"metric": "mvtool_status", "value": mvtool_map.get("status", "NA")},
        ]
    )
    write_dataframe(findings, destination / "GM12878_ONT_longread_key_findings.tsv")
    write_dataframe(
        heteroplasmy.head(25).copy(),
        destination / "GM12878_ONT_longread_top_heteroplasmy_candidates.tsv",
    )
    write_dataframe(
        clusters.head(25).copy(), destination / "GM12878_ONT_longread_top_deletion_clusters.tsv"
    )
    write_dataframe(gene.head(25).copy(), destination / "GM12878_ONT_longread_top_gene_summary.tsv")

    top_class: object = "NA"
    top_class_count: object = "NA"
    if not consequence_classes.empty and {
        "consequence_class",
        "candidate_sites",
    }.issubset(consequence_classes.columns):
        top_row = consequence_classes.sort_values(
            ["candidate_sites", "consequence_class"], ascending=[False, True]
        ).iloc[0]
        top_class = top_row["consequence_class"]
        top_class_count = top_row["candidate_sites"]

    readme_lines = [
        "# GM12878 public ONT deterministic reduced proof-of-principle example",
        "",
        (
            "This directory contains lightweight public example assets from a seeded "
            "deterministic query-name subset of a real ONT targeted-mt run processed with the "
            "`mito-overview` long-read profile."
        ),
        "",
        "Example context:",
        "- source BioProject: `PRJNA809571`",
        "- run used: `SRR18110025`",
        (
            "- public assay description: `Long read mitochondrial genome sequencing using "
            "Cas9-guided adaptor ligation`"
        ),
        (
            "- source publication: Vandiver et al., Mitochondrion 2022 (PMID 35787470; "
            "DOI 10.1016/j.mito.2022.06.003)"
        ),
        "- validation scope: deterministic reduced public proof-of-principle, not the complete run",
        "- profile used: `READ_MODE=long`, `ASSAY_TYPE=targeted_mt`",
        f"- minimum callable depth: `{heteroplasmy_map.get('min_callable_depth', 'NA')}`",
        (
            "- minimum observed alternate allele fraction: "
            f"`{heteroplasmy_map.get('min_alt_allele_fraction', 'NA')}`"
        ),
        "",
        "Included assets:",
        "- representative report-native figures used for GitHub/manuscript panels",
        "- key summary tables from the validation output",
        "- condensed key-findings and top-signal tables",
        "- alignment flagstat summary",
        "",
        "What these assets support:",
        "- real public ONT long-read execution of the core long-read workflow",
        (
            "- report-native QC, alternate-allele screening, CIGAR-deletion candidate screening, "
            "co-segregation, gene-summary, alignment-ambiguity QC, circularity-QC, and consequence "
            "outputs"
        ),
        (
            "- explicit assay-mode gating for targeted-mt layers that remain uninterpretable here "
            "(`copy_number` and `phymer_haplogroup`)"
        ),
        (
            "- explicit status-only methylation reporting when mitochondrial bedmethyl rows are "
            "unavailable"
        ),
        "",
        "What these assets do not claim:",
        "- clinical interpretation",
        "- calibrated low-allele-fraction detection benchmarking",
        "- validated deletion truth benchmarking",
        "- formal mtDNA-versus-NUMT classification",
        "- biological methylation conclusions",
        "",
        "Observed packaged key values:",
        f"- mapped reads: `{qc_map.get('mapped_reads', 'NA')}`",
        f"- mean depth: `{qc_map.get('mean_depth', 'NA')}`",
        f"- median depth: `{qc_map.get('median_depth', 'NA')}`",
        f"- full-length fraction: `{qc_map.get('full_length_fraction', 'NA')}`",
        f"- alternate-allele candidate sites: `{len(heteroplasmy)}`",
        f"- selected co-segregation sites: `{cosegregation_map.get('selected_sites', 'NA')}`",
        f"- top consequence class: `{top_class}` (`{top_class_count}` sites)",
        (
            "- singleton CIGAR-deletion bins: "
            f"`{deletion_map.get('candidate_deletion_clusters', 'NA')}`; each packaged bin has "
            "one supporting query name"
        ),
        (
            "- query names with supplementary/SA evidence, summarized separately: "
            f"`{deletion_map.get('reads_with_supplementary_or_SA', 'NA')}`"
        ),
        (
            "- NUMT interpretation status: "
            f"`{numt_map.get('numt_interpretation_status', 'NA')}` "
            f"(`{numt_map.get('reason_code', 'NA')}`)"
        ),
        f"- within-sample mt:nuclear depth-ratio status: `{copy_map.get('status', 'NA')}`",
        f"- Phy-Mer status: `{phymer_map.get('status', 'NA')}`",
        f"- methylation status: `{methylation_map.get('status', 'NA')}`",
        "",
        "Important note:",
        "- optional network-backed mvTool annotation is disabled unless explicitly configured",
    ]
    readme = destination / "README.md"
    readme.write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    readme.chmod(0o644)
    return selected_count


def build_montage(stage: Path, profile: str, destination: str, title: str) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    builder = require_regular_file(repo_root / "scripts/build_report_montage.py", "montage builder")
    output = stage / destination
    prepare_directory(output.parent)
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC", "PYTHONHASHSEED": "0"})
    completed = subprocess.run(
        [
            sys.executable,
            str(builder),
            "--profile",
            profile,
            "--source-dir",
            str(output.parent),
            "--output",
            str(output),
            "--title",
            title,
        ],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise RefreshError(f"Montage builder failed for {profile} profile: {detail}")
    require_regular_file(output, destination)
    output.chmod(0o644)


def verify_staged_inventory(stage: Path) -> None:
    files, directories = relative_inventory(stage, "Staged inventory")
    if files != EXPECTED_FILES or directories != EXPECTED_DIRECTORIES:
        raise RefreshError(
            "Staged inventory does not match the 56-file contract: "
            f"missing_files={sorted(EXPECTED_FILES - files)!r} "
            f"unexpected_files={sorted(files - EXPECTED_FILES)!r} "
            f"missing_directories={sorted(EXPECTED_DIRECTORIES - directories)!r} "
            f"unexpected_directories={sorted(directories - EXPECTED_DIRECTORIES)!r}"
        )
    forbidden_suffixes = {".bai", ".bam", ".crai", ".cram", ".csi", ".fastq", ".fq", ".gz"}
    for relative in sorted(files):
        path = stage / PurePosixPath(relative)
        if path.suffix.lower() in forbidden_suffixes or "source_libraries" in path.name:
            raise RefreshError(f"Forbidden artifact entered staged inventory: {relative}")
        reject_absolute_paths(path, relative)


def install_stage(stage: Path, destination: Path) -> None:
    if not destination.exists():
        os.replace(stage, destination)
        return
    backup = destination.parent / f".{destination.name}.refresh-backup-{uuid.uuid4().hex}"
    os.replace(destination, backup)
    try:
        os.replace(stage, destination)
    except BaseException:
        os.replace(backup, destination)
        raise
    shutil.rmtree(backup)


def refresh(args: argparse.Namespace) -> None:
    matrix_root = absolute_lexical(args.matrix_root)
    destination = absolute_lexical(args.destination)
    if matrix_root == destination or matrix_root in destination.parents or destination in matrix_root.parents:
        raise RefreshError("Matrix root and destination must not overlap")

    relative_inventory(matrix_root, "Matrix root")
    validate_destination(destination)
    validate_cases(matrix_root)
    validate_oracle_assertions(matrix_root)
    validate_input_manifest(matrix_root)

    derivation_inputs = (
        f"{SHORT_CASE}/summary/mito_heteroplasmy_summary.tsv",
        f"{LONG_CASE}/summary/mito_heteroplasmy_summary.tsv",
        "oracle_assertions.tsv",
    )
    required_sources = {source for source, _ in COPY_SPECS} | set(derivation_inputs)
    for relative in sorted(required_sources):
        source = required_matrix_file(matrix_root, relative)
        reject_absolute_paths(source, relative)

    oracle = preservation_source(args.oracle, destination, ORACLE_DEST, "--oracle")
    short_readme = preservation_source(
        args.gm11906_readme,
        destination,
        SHORT_README_DEST,
        "--gm11906-readme",
    )
    reject_absolute_paths(oracle, "frozen oracle")
    reject_absolute_paths(short_readme, "GM11906 README")

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.refresh-", dir=destination.parent))
    stage.chmod(0o755)
    try:
        for source_relative, destination_relative in COPY_SPECS:
            copy_regular(
                required_matrix_file(matrix_root, source_relative),
                stage / PurePosixPath(destination_relative),
            )
        copy_regular(oracle, stage / ORACLE_DEST)
        copy_regular(short_readme, stage / SHORT_README_DEST)

        try:
            build_short_key_tables(matrix_root, stage)
            selected_count = build_long_assets(matrix_root, stage)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as exc:
            raise RefreshError(f"Could not derive tracked key assets: {exc}") from exc

        build_montage(
            stage,
            "short",
            f"{SHORT_DEST}/figures/GM11906_MERRF_shortread_montage.png",
            "GM11906 pooled scATAC mtDNA workflow proof-of-principle",
        )
        build_montage(
            stage,
            "long",
            f"{LONG_DEST}/figures/GM12878_ONT_longread_montage.png",
            f"GM12878 public ONT {selected_count}-query-name workflow proof-of-principle",
        )
        verify_staged_inventory(stage)
        install_stage(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    print(f"[tracked-public-validation] PASS files=56 destination={destination}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        refresh(args)
    except (OSError, RefreshError) as exc:
        print(f"[tracked-public-validation] FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
