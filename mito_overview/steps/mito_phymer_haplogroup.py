"""Optional human mtDNA haplogroup enrichment via a local Phy-Mer vendor tree."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pysam

from mito_overview.report_common import df_to_html_table, figure_html, metric_card, render_page
from mito_overview.table_contracts import load_metric_module_state, validate_all_site_table

RANKING_COLUMNS = ["rank", "haplogroup", "score", "defining_snps"]
PHYMER_MODES = {"external", "fixture"}
EXTERNAL_MIN_CALLABLE_FRACTION = 0.95
FIXTURE_ID = "mito-overview-phymer-wiring-v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FIXTURE_FILE_SHA256 = {
    "Phy-Mer.py": "1f5231e6958ffd731c4c644aa69168824126c251f8b8129b74c47f87a68cbb22",
    "PhyloTree_b16_k12.txt": "8bd377e62052ec9145c7078fa0dd85eb071aa7977bd225baa6ede87031fea968",
    "resources/Build_16_-_rCRS-based_haplogroup_motifs.csv": (
        "fd1d9412344b5f8a2ab878feddc6c204069ada56ee97d5982cb605cdff36f05c"
    ),
}
MAJOR_COLUMNS = [
    "position",
    "ref_base",
    "alt_base",
    "depth",
    "alt_allele_fraction",
    "heteroplasmy_fraction",
    "phymer_input",
]


@dataclass(frozen=True)
class ConsensusEvidence:
    major_variants: pd.DataFrame
    callable_positions: int
    total_positions: int
    callable_fraction: float
    masked_positions: int
    noncanonical_reference_positions: int


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--species", required=True)
    parser.add_argument("--ref-fasta", required=True)
    parser.add_argument("--phymer-root", default="")
    parser.add_argument("--phymer-mode", choices=sorted(PHYMER_MODES), default="external")
    parser.add_argument("--min-depth", type=int, default=100)
    parser.add_argument("--major-vaf", type=float, default=0.90)
    parser.add_argument("--min-callable-fraction", type=float, default=0.95)
    return parser


def load_table(path: str | Path, *, columns: list[str] | None = None) -> pd.DataFrame:
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, sep="\t")
    return pd.DataFrame(columns=columns or [])


def parse_phymer_output(text: str) -> tuple[str, pd.DataFrame]:
    sample_label = "NA"
    rows: list[dict[str, object]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                score = float(parts[1])
            except ValueError:
                if sample_label == "NA":
                    sample_label = line
                continue
            if not math.isfinite(score) or not 0 <= score <= 1:
                continue
            defining_snps = parts[2] if len(parts) > 2 else "NA"
            rows.append(
                {
                    "haplogroup": parts[0],
                    "score": score,
                    "defining_snps": defining_snps,
                }
            )
        elif sample_label == "NA":
            sample_label = line
    ranking = pd.DataFrame(rows)
    if not ranking.empty:
        ranking.insert(0, "rank", range(1, len(ranking) + 1))
    else:
        ranking = pd.DataFrame(columns=RANKING_COLUMNS)
    return sample_label, ranking


def build_consensus_fasta(
    *,
    all_sites: pd.DataFrame,
    ref_fasta: str | Path,
    mt_contig: str,
    mt_length: int,
    out_fasta: str | Path,
    min_depth: int,
    major_vaf: float,
    min_callable_fraction: float,
) -> ConsensusEvidence:
    with pysam.FastaFile(str(ref_fasta)) as fasta:
        observed_length = fasta.get_reference_length(mt_contig)
        if observed_length != mt_length:
            raise ValueError(
                "Phy-Mer reference length mismatch: "
                f"expected {mt_length}, observed {observed_length}"
            )
        reference_sequence = fasta.fetch(mt_contig, 0, mt_length).upper()
    all_sites = validate_all_site_table(
        all_sites,
        table_name="mito_heteroplasmy_all_sites.tsv",
        mt_length=mt_length,
        reference_sequence=reference_sequence,
    )
    canonical_reference_mask = all_sites["ref_base"].isin({"A", "C", "G", "T"})
    callable_mask = (all_sites["callable_depth"] >= min_depth) & canonical_reference_mask
    callable_positions = int(callable_mask.sum())
    callable_fraction = callable_positions / mt_length
    masked_positions = mt_length - callable_positions
    noncanonical_reference_positions = int((~canonical_reference_mask).sum())
    major = all_sites[
        callable_mask & (all_sites["alt_allele_fraction"] >= major_vaf)
    ].copy()
    major = major.sort_values("position")
    major["heteroplasmy_fraction"] = major["alt_allele_fraction"]
    major = major[(major["alt_base"] != ".") & (major["ref_base"] != major["alt_base"])].reset_index(drop=True)

    if callable_fraction < min_callable_fraction:
        return ConsensusEvidence(
            major_variants=pd.DataFrame(columns=MAJOR_COLUMNS),
            callable_positions=callable_positions,
            total_positions=mt_length,
            callable_fraction=callable_fraction,
            masked_positions=masked_positions,
            noncanonical_reference_positions=noncanonical_reference_positions,
        )

    seq = [
        reference_sequence[index] if bool(callable_mask.iloc[index]) else "N"
        for index in range(mt_length)
    ]

    for row in major.itertuples(index=False):
        seq[int(row.position) - 1] = str(row.alt_base)

    out_fasta = Path(out_fasta)
    with out_fasta.open("w", encoding="utf-8") as handle:
        handle.write(f">{out_fasta.stem}\n")
        joined = "".join(seq)
        for idx in range(0, len(joined), 70):
            handle.write(joined[idx : idx + 70] + "\n")

    if not major.empty:
        major["phymer_input"] = [f"m.{int(r.position)}{r.ref_base}>{r.alt_base}" for r in major.itertuples(index=False)]
        major = major[MAJOR_COLUMNS]
    else:
        major = pd.DataFrame(columns=MAJOR_COLUMNS)
    return ConsensusEvidence(
        major_variants=major,
        callable_positions=callable_positions,
        total_positions=mt_length,
        callable_fraction=callable_fraction,
        masked_positions=masked_positions,
        noncanonical_reference_positions=noncanonical_reference_positions,
    )


def _coverage_rows(
    evidence: ConsensusEvidence,
    *,
    min_depth: int,
    min_callable_fraction: float,
) -> list[dict[str, object]]:
    return [
        {"metric": "phymer_callable_positions", "value": evidence.callable_positions},
        {"metric": "phymer_total_positions", "value": evidence.total_positions},
        {
            "metric": "phymer_callable_fraction",
            "value": round(evidence.callable_fraction, 6),
        },
        {"metric": "phymer_masked_positions", "value": evidence.masked_positions},
        {
            "metric": "phymer_noncanonical_reference_positions",
            "value": evidence.noncanonical_reference_positions,
        },
        {"metric": "phymer_min_depth", "value": min_depth},
        {
            "metric": "phymer_min_callable_fraction",
            "value": min_callable_fraction,
        },
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_fixture_vendor(root: Path) -> None:
    mismatches: list[str] = []
    for relative_path, expected_sha256 in FIXTURE_FILE_SHA256.items():
        path = root / relative_path
        if not path.is_file():
            mismatches.append(f"missing:{relative_path}")
        elif _sha256(path) != expected_sha256:
            mismatches.append(f"sha256:{relative_path}")
    if mismatches:
        raise ValueError(
            "PHYMER_MODE=fixture requires the exact bundled synthetic wiring fixture; "
            + ", ".join(mismatches)
        )


def _resource_rows(
    resource_hashes: dict[str, str],
    *,
    binding_status: str,
) -> list[dict[str, object]]:
    return [
        {"metric": "phymer_resource_binding_status", "value": binding_status},
        {
            "metric": "phymer_script_sha256",
            "value": resource_hashes.get("script", "NA"),
        },
        {
            "metric": "phymer_library_sha256",
            "value": resource_hashes.get("library", "NA"),
        },
        {
            "metric": "phymer_definitions_sha256",
            "value": resource_hashes.get("definitions", "NA"),
        },
    ]


def _provenance_rows(phymer_mode: str) -> list[dict[str, object]]:
    if phymer_mode == "fixture":
        return [
            {"metric": "phymer_mode", "value": "fixture"},
            {"metric": "phymer_vendor_provenance", "value": "bundled_exact_hash_fixture"},
            {"metric": "phymer_fixture_id", "value": FIXTURE_ID},
            {"metric": "phymer_result_scope", "value": "synthetic_wiring_fixture"},
            {"metric": "biological_validation_status", "value": "not_applicable"},
            {"metric": "phymer_python_compatibility", "value": "not_required"},
        ]
    return [
        {"metric": "phymer_mode", "value": "external"},
        {"metric": "phymer_vendor_provenance", "value": "user_supplied_local_vendor"},
        {"metric": "phymer_fixture_id", "value": "NA"},
        {"metric": "phymer_result_scope", "value": "external_classifier_output"},
        {"metric": "biological_validation_status", "value": "not_established"},
        {
            "metric": "phymer_python_compatibility",
            "value": "legacy_universal_newline_adapter",
        },
    ]


def _write_status_outputs(
    *,
    report_path: Path,
    summary_path: Path,
    ranking_path: Path,
    input_path: Path,
    status_rows: list[dict[str, object]],
    message: str,
    sample_id: str,
    region: str,
) -> dict[str, Path | str]:
    status_df = pd.DataFrame(status_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    status_df.to_csv(summary_path, sep="\t", index=False)
    pd.DataFrame(columns=RANKING_COLUMNS).to_csv(ranking_path, sep="\t", index=False)
    pd.DataFrame(columns=MAJOR_COLUMNS).to_csv(input_path, sep="\t", index=False)
    intro_html = f"<p class='muted'>{message}</p>"
    body_html = "<section><h2>Status</h2>" + df_to_html_table(status_df, max_rows=20) + "</section>"
    render_page(report_path, "Mito Phy-Mer Haplogroup", sample_id, region, intro_html, body_html)
    status = next((str(row["value"]) for row in status_rows if row.get("metric") == "status"), "unavailable")
    return {
        "status": status,
        "summary_path": summary_path,
        "ranking_path": ranking_path,
        "input_path": input_path,
        "report_path": report_path,
    }


def run_step(
    *,
    summary_dir: str | Path,
    figure_dir: str | Path,
    report_dir: str | Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    species: str,
    ref_fasta: str | Path,
    phymer_root: str | Path | None,
    phymer_mode: str = "external",
    expected_script_sha256: str = "",
    expected_library_sha256: str = "",
    expected_definitions_sha256: str = "",
    min_depth: int = 100,
    major_vaf: float = 0.90,
    min_callable_fraction: float = 0.95,
) -> dict[str, Path]:
    """Run the optional Phy-Mer haplogroup enrichment step."""

    summary_dir = Path(summary_dir)
    figure_dir = Path(figure_dir)
    report_dir = Path(report_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    region = f"{mt_contig}:1-{mt_length}"
    report_path = report_dir / "13_mito_phymer_haplogroup.html"
    summary_path = summary_dir / "mito_phymer_haplogroup_summary.tsv"
    ranking_path = summary_dir / "mito_phymer_haplogroup_ranking.tsv"
    input_path = summary_dir / "mito_phymer_major_variant_input.tsv"
    raw_output_path = summary_dir / "mito_phymer_raw_output.txt"
    raw_error_path = summary_dir / "mito_phymer_raw_error.txt"
    fasta_path = summary_dir / "mito_phymer_consensus.fasta"
    rank_fig = figure_dir / "mito_phymer_haplogroup_scores.png"

    # A direct step rerun must never leave a prior categorical result visible.
    for owned_output in (
        report_path,
        summary_path,
        ranking_path,
        input_path,
        raw_output_path,
        raw_error_path,
        fasta_path,
        rank_fig,
    ):
        owned_output.unlink(missing_ok=True)

    phymer_mode = str(phymer_mode).strip().lower()
    if phymer_mode not in PHYMER_MODES:
        raise ValueError(f"Unsupported PHYMER_MODE: {phymer_mode}")
    expected_hashes = {
        "script": str(expected_script_sha256).strip().lower(),
        "library": str(expected_library_sha256).strip().lower(),
        "definitions": str(expected_definitions_sha256).strip().lower(),
    }
    invalid_expected_hashes = [
        label
        for label, value in expected_hashes.items()
        if value and not SHA256_PATTERN.fullmatch(value)
    ]
    if invalid_expected_hashes:
        raise ValueError(
            "Phy-Mer expected SHA-256 values must be 64 lowercase hexadecimal "
            f"characters: {','.join(invalid_expected_hashes)}"
        )
    if min_depth <= 0:
        raise ValueError("Phy-Mer min_depth must be positive")
    if not math.isfinite(major_vaf) or not 0 <= major_vaf <= 1:
        raise ValueError("Phy-Mer major_vaf must be finite and between 0 and 1")
    if not math.isfinite(min_callable_fraction) or not (
        0 < min_callable_fraction <= 1
    ):
        raise ValueError(
            "Phy-Mer min_callable_fraction must be finite, greater than 0, and at most 1"
        )
    if (
        phymer_mode == "external"
        and min_callable_fraction < EXTERNAL_MIN_CALLABLE_FRACTION
    ):
        raise ValueError(
            "PHYMER_MIN_CALLABLE_FRACTION cannot be below 0.95 when "
            "PHYMER_MODE=external"
        )

    print(
        f"[phymer] starting sample={sample_id} species={species} contig={mt_contig} "
        f"min_depth={min_depth} major_vaf={major_vaf} "
        f"min_callable_fraction={min_callable_fraction} phymer_mode={phymer_mode}",
        flush=True,
    )
    provenance_rows = _provenance_rows(phymer_mode)

    if species.lower() != "human":
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "not_applicable"},
                {"metric": "reason_code", "value": "non_human_sample"},
                *provenance_rows,
            ],
            message="Phy-Mer haplogroup inference is currently enabled only for human mitochondrial samples.",
            sample_id=sample_id,
            region=region,
        )

    heteroplasmy_status, heteroplasmy_reason = load_metric_module_state(
        summary_dir / "mito_heteroplasmy_summary.tsv",
        module_name="heteroplasmy",
    )
    if heteroplasmy_status != "ok":
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": heteroplasmy_status},
                {
                    "metric": "reason_code",
                    "value": f"upstream_heteroplasmy_{heteroplasmy_status}",
                },
                {
                    "metric": "upstream_heteroplasmy_status",
                    "value": heteroplasmy_status,
                },
                {
                    "metric": "upstream_heteroplasmy_reason_code",
                    "value": heteroplasmy_reason,
                },
                *provenance_rows,
            ],
            message=(
                "Phy-Mer was not run because the upstream alternate-allele module "
                f"reported {heteroplasmy_status!r}."
            ),
            sample_id=sample_id,
            region=region,
        )

    all_sites_path = summary_dir / "mito_heteroplasmy_all_sites.tsv"
    if not all_sites_path.is_file():
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "not_evaluable"},
                {"metric": "reason_code", "value": "all_site_table_missing"},
                {"metric": "upstream_heteroplasmy_status", "value": "ok"},
                *provenance_rows,
            ],
            message=(
                "The upstream alternate-allele summary was valid, but its required "
                "all-site evidence table was missing."
            ),
            sample_id=sample_id,
            region=region,
        )
    try:
        all_sites = pd.read_csv(all_sites_path, sep="\t")
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise ValueError(
            "mito_heteroplasmy_all_sites.tsv could not be parsed as internal allele evidence"
        ) from exc

    phymer_root_path = Path(phymer_root) if phymer_root else None
    phymer_script = phymer_root_path / "Phy-Mer.py" if phymer_root_path else None
    phymer_library = phymer_root_path / "PhyloTree_b16_k12.txt" if phymer_root_path else None
    phymer_defs = phymer_root_path / "resources" / "Build_16_-_rCRS-based_haplogroup_motifs.csv" if phymer_root_path else None
    if not (
        phymer_root_path
        and phymer_script
        and phymer_library
        and phymer_defs
        and phymer_script.exists()
        and phymer_library.exists()
        and phymer_defs.exists()
    ):
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "not_configured"},
                {"metric": "reason_code", "value": "phymer_resources_missing"},
                {"metric": "phymer_root", "value": str(phymer_root_path or "")},
                *provenance_rows,
            ],
            message="Phy-Mer resources were not available in the configured local vendor directory.",
            sample_id=sample_id,
            region=region,
        )

    if phymer_mode == "fixture":
        _verify_fixture_vendor(phymer_root_path)
        expected_hashes = {
            "script": FIXTURE_FILE_SHA256["Phy-Mer.py"],
            "library": FIXTURE_FILE_SHA256["PhyloTree_b16_k12.txt"],
            "definitions": FIXTURE_FILE_SHA256[
                "resources/Build_16_-_rCRS-based_haplogroup_motifs.csv"
            ],
        }

    observed_hashes = {
        "script": _sha256(phymer_script),
        "library": _sha256(phymer_library),
        "definitions": _sha256(phymer_defs),
    }
    if phymer_mode == "external" and not all(expected_hashes.values()):
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "not_configured"},
                {
                    "metric": "reason_code",
                    "value": "phymer_external_hashes_not_configured",
                },
                *provenance_rows,
                *_resource_rows(observed_hashes, binding_status="not_configured"),
            ],
            message=(
                "External Phy-Mer resources were present, but expected SHA-256 "
                "identities were not completely configured."
            ),
            sample_id=sample_id,
            region=region,
        )
    if observed_hashes != expected_hashes:
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "unavailable"},
                {"metric": "reason_code", "value": "phymer_resource_digest_mismatch"},
                *provenance_rows,
                *_resource_rows(observed_hashes, binding_status="mismatch"),
            ],
            message=(
                "Configured Phy-Mer resources did not match their expected SHA-256 "
                "identities, so no classifier code was executed."
            ),
            sample_id=sample_id,
            region=region,
        )
    resource_rows = _resource_rows(observed_hashes, binding_status="verified")

    evidence = build_consensus_fasta(
        all_sites=all_sites,
        ref_fasta=ref_fasta,
        mt_contig=mt_contig,
        mt_length=mt_length,
        out_fasta=fasta_path,
        min_depth=min_depth,
        major_vaf=major_vaf,
        min_callable_fraction=min_callable_fraction,
    )
    coverage_rows = _coverage_rows(
        evidence,
        min_depth=min_depth,
        min_callable_fraction=min_callable_fraction,
    )
    if evidence.callable_fraction < min_callable_fraction:
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "not_evaluable"},
                {
                    "metric": "reason_code",
                    "value": "insufficient_callable_genome_fraction",
                },
                {"metric": "upstream_heteroplasmy_status", "value": "ok"},
                *coverage_rows,
                *provenance_rows,
                *resource_rows,
            ],
            message=(
                "Phy-Mer was not run because the fraction of mitochondrial positions "
                "meeting its configured depth threshold was below the required minimum."
            ),
            sample_id=sample_id,
            region=region,
        )

    major = evidence.major_variants
    major.to_csv(input_path, sep="\t", index=False)

    cmd = [sys.executable]
    if phymer_mode == "external":
        compatibility_runner = Path(__file__).resolve().parents[1] / "phymer_compat.py"
        cmd.append(str(compatibility_runner))
    cmd.extend(
        [
            str(phymer_script),
            "--print-ranking",
            f"--def-snp={phymer_defs}",
            str(phymer_library),
            str(fasta_path),
        ]
    )
    print(f"[phymer] sample={sample_id} running command in {phymer_root_path}", flush=True)
    print(
        f"[phymer] consensus major variants={len(major)} min_depth={min_depth} major_vaf={major_vaf}",
        flush=True,
    )
    completed = subprocess.run(cmd, cwd=str(phymer_root_path), capture_output=True, text=True)
    raw_output_path.write_text(completed.stdout, encoding="utf-8")
    raw_error_path.write_text(completed.stderr, encoding="utf-8")
    print(f"[phymer] return_code={completed.returncode}", flush=True)
    if completed.stderr.strip():
        print(f"[phymer] stderr={completed.stderr.strip()[:400]}", flush=True)

    if completed.returncode != 0:
        return _write_status_outputs(
            report_path=report_path,
            summary_path=summary_path,
            ranking_path=ranking_path,
            input_path=input_path,
            status_rows=[
                {"metric": "status", "value": "unavailable"},
                {"metric": "reason_code", "value": "phymer_run_failed"},
                {"metric": "return_code", "value": int(completed.returncode)},
                {"metric": "stderr_preview", "value": completed.stderr.strip()[:200] or "NA"},
                *coverage_rows,
                *provenance_rows,
                *resource_rows,
            ],
            message="Phy-Mer was invoked but did not return a successful haplogroup result. See the raw output files in the summary directory for debugging context.",
            sample_id=sample_id,
            region=region,
        )

    sample_label, ranking = parse_phymer_output(completed.stdout)
    ranking.to_csv(ranking_path, sep="\t", index=False)
    best_hg = str(ranking.iloc[0]["haplogroup"]) if not ranking.empty else "NA"
    best_score = float(ranking.iloc[0]["score"]) if not ranking.empty else None
    status_df = pd.DataFrame(
        [
            {"metric": "status", "value": "ok" if not ranking.empty else "unavailable"},
            {"metric": "reason_code", "value": "" if not ranking.empty else "no_phymer_ranking_rows"},
            {"metric": "upstream_heteroplasmy_status", "value": "ok"},
            {"metric": "upstream_heteroplasmy_reason_code", "value": heteroplasmy_reason},
            {"metric": "sample_label", "value": sample_label},
            {"metric": "best_haplogroup", "value": best_hg},
            {
                "metric": "best_score",
                "value": round(best_score, 6) if best_score is not None else "NA",
            },
            {"metric": "major_variant_sites_used", "value": int(len(major))},
            *coverage_rows,
            *provenance_rows,
            *resource_rows,
            {"metric": "phymer_library", "value": phymer_library.name},
            {
                "metric": "major_variant_threshold",
                "value": f"callable_depth>={min_depth};vaf>={major_vaf}",
            },
        ]
    )
    summary_path.write_text(status_df.to_csv(sep="\t", index=False), encoding="utf-8")

    rank_fig_output = None
    if not ranking.empty:
        rank_fig_output = rank_fig
        plot_df = ranking.head(5).copy()
        plt.figure(figsize=(8, 4))
        plt.bar(plot_df["haplogroup"], plot_df["score"], color="#2563eb")
        plt.ylabel("Phy-Mer score")
        plt.title(f"{sample_id} Phy-Mer top haplogroup ranking")
        plt.tight_layout()
        plt.savefig(rank_fig_output, dpi=150)
        plt.close()

    metrics_html = "".join(
        [
            metric_card("Best haplogroup", best_hg),
            metric_card(
                "Best score",
                round(best_score, 6) if best_score is not None else "NA",
            ),
            metric_card("Major variants used", int(len(major))),
            metric_card("Ranking rows", int(len(ranking))),
            metric_card(
                "Callable mtDNA fraction",
                round(evidence.callable_fraction, 4),
            ),
        ]
    )
    if phymer_mode == "fixture":
        scope_html = (
            '<p><strong>Synthetic wiring fixture:</strong> this deterministic result '
            "tests integration behavior only and must not be interpreted as a biological "
            "haplogroup assignment.</p>"
        )
    else:
        scope_html = (
            '<p class="muted">The local external-classifier result is descriptive; '
            "biological concordance and clinical performance are not established by this workflow.</p>"
        )
    intro_html = (
        scope_html
        + '<p class="muted">This page runs a local vendor copy of Phy-Mer on a mitochondrial consensus reconstructed from complete per-base allele evidence. '
        "Callable sites use the reference base unless a high-fraction alternate passes the configured threshold, and residual low-depth sites are masked as N. "
        "The result is an optional haplogroup enrichment layer and does not alter the primary alternate-allele or deletion screens.</p>"
        f"<div class='metrics-grid'>{metrics_html}</div>"
    )
    body_parts = [
        "<section><h2>Phy-Mer run summary</h2>" + df_to_html_table(status_df, max_rows=20) + "</section>",
        "<section><h2>Consensus major-variant input</h2>" + df_to_html_table(major, max_rows=40) + "</section>",
        "<section><h2>Phy-Mer ranking table</h2>" + df_to_html_table(ranking, max_rows=20) + "</section>",
    ]
    if rank_fig_output:
        body_parts.insert(
            2,
            "<section><h2>Top haplogroup scores</h2>"
            + figure_html(rank_fig_output, "Top Phy-Mer haplogroup score ranking")
            + "</section>",
        )
    render_page(report_path, "Mito Phy-Mer Haplogroup", sample_id, region, intro_html, "".join(body_parts))
    return {
        "status": "ok" if not ranking.empty else "unavailable",
        "summary_path": summary_path,
        "ranking_path": ranking_path,
        "input_path": input_path,
        "report_path": report_path,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        summary_dir=args.summary_dir,
        figure_dir=args.figure_dir,
        report_dir=args.report_dir,
        sample_id=args.sample_id,
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
        species=args.species,
        ref_fasta=args.ref_fasta,
        phymer_root=args.phymer_root,
        phymer_mode=args.phymer_mode,
        min_depth=args.min_depth,
        major_vaf=args.major_vaf,
        min_callable_fraction=args.min_callable_fraction,
    )
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
