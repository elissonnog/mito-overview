from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pysam
import pytest

from mito_overview.steps import mito_phymer_haplogroup as phymer

from ._helpers import metric_map


MT_LENGTH = 60


def all_site_table() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for position in range(1, MT_LENGTH + 1):
        alt_count = 95 if position == 10 else 0
        rows.append(
            {
                "position": position,
                "ref_base": "A",
                "alt_base": "C" if alt_count else ".",
                "callable_depth": 100,
                "depth": 100,
                "alt_count": alt_count,
                "alt_allele_fraction": alt_count / 100,
                "heteroplasmy_fraction": alt_count / 100,
                "alt_forward": alt_count // 2,
                "alt_reverse": alt_count - (alt_count // 2),
                "A": 100 - alt_count,
                "C": alt_count,
                "G": 0,
                "T": 0,
            }
        )
    return pd.DataFrame(rows)


def prepare_case(root: Path, *, status: str = "ok", reason: str = "") -> tuple[Path, Path]:
    summary = root / "summary"
    summary.mkdir(parents=True)
    all_site_table().to_csv(
        summary / "mito_heteroplasmy_all_sites.tsv", sep="\t", index=False
    )
    pd.DataFrame(
        [
            {"metric": "status", "value": status},
            {"metric": "reason_code", "value": reason},
        ]
    ).to_csv(summary / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)

    reference = root / "reference.fa"
    reference.write_text(">MT\n" + ("A" * MT_LENGTH) + "\n", encoding="ascii")
    pysam.faidx(str(reference))
    return summary, reference


def run_phymer(
    root: Path,
    summary: Path,
    reference: Path,
    *,
    min_callable_fraction: float = 0.95,
    phymer_mode: str = "fixture",
    phymer_root: Path | None = None,
) -> dict[str, Path | str]:
    return phymer.run_step(
        summary_dir=summary,
        figure_dir=root / "figures",
        report_dir=root / "reports",
        sample_id="PHYMER-TEST",
        mt_contig="MT",
        mt_length=MT_LENGTH,
        species="human",
        ref_fasta=reference,
        phymer_root=phymer_root
        or Path(__file__).parent / "fixtures" / "mock_phymer_vendor",
        phymer_mode=phymer_mode,
        min_depth=100,
        major_vaf=0.9,
        min_callable_fraction=min_callable_fraction,
    )


def retain_callable_positions(table: pd.DataFrame, positions: set[int]) -> pd.DataFrame:
    table = table.copy()
    masked = ~table["position"].isin(positions)
    table.loc[masked, "alt_base"] = "."
    for column in (
        "callable_depth",
        "depth",
        "alt_count",
        "alt_forward",
        "alt_reverse",
        "A",
        "C",
        "G",
        "T",
    ):
        table.loc[masked, column] = 0
    table.loc[masked, ["alt_allele_fraction", "heteroplasmy_fraction"]] = float(
        "nan"
    )
    return table


def test_valid_complete_all_site_evidence_produces_mock_haplogroup(tmp_path: Path) -> None:
    summary, reference = prepare_case(tmp_path)

    outputs = run_phymer(tmp_path, summary, reference)

    metrics = metric_map(Path(outputs["summary_path"]))
    assert outputs["status"] == "ok"
    assert metrics["best_haplogroup"] == "H1a1"
    assert metrics["major_variant_sites_used"] == "1"
    assert metrics["upstream_heteroplasmy_status"] == "ok"
    assert metrics["phymer_callable_positions"] == "60"
    assert metrics["phymer_callable_fraction"] == "1.0"
    assert metrics["phymer_masked_positions"] == "0"
    assert metrics["phymer_noncanonical_reference_positions"] == "0"
    assert metrics["phymer_mode"] == "fixture"
    assert metrics["phymer_vendor_provenance"] == "bundled_exact_hash_fixture"
    assert metrics["phymer_fixture_id"] == phymer.FIXTURE_ID
    assert metrics["phymer_result_scope"] == "synthetic_wiring_fixture"
    assert metrics["biological_validation_status"] == "not_applicable"
    report = Path(outputs["report_path"]).read_text(encoding="utf-8")
    assert "Synthetic wiring fixture" in report
    assert "must not be interpreted as a biological haplogroup assignment" in report
    major = pd.read_csv(outputs["input_path"], sep="\t")
    assert major["phymer_input"].tolist() == ["m.10A>C"]


def test_sparse_reference_filled_consensus_is_not_evaluable_before_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary, reference = prepare_case(tmp_path)
    table_path = summary / "mito_heteroplasmy_all_sites.tsv"
    retain_callable_positions(pd.read_csv(table_path, sep="\t"), {10}).to_csv(
        table_path, sep="\t", index=False
    )
    monkeypatch.setattr(
        phymer.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Phy-Mer invoked")),
    )

    outputs = run_phymer(tmp_path, summary, reference)

    metrics = metric_map(Path(outputs["summary_path"]))
    assert outputs["status"] == "not_evaluable"
    assert metrics["reason_code"] == "insufficient_callable_genome_fraction"
    assert metrics["phymer_callable_positions"] == "1"
    assert metrics["phymer_total_positions"] == "60"
    assert metrics["phymer_callable_fraction"] == "0.016667"
    assert metrics["phymer_min_callable_fraction"] == "0.95"
    assert not (summary / "mito_phymer_consensus.fasta").exists()


def test_exact_callable_fraction_boundary_masks_low_depth_positions(tmp_path: Path) -> None:
    summary, reference = prepare_case(tmp_path)
    table_path = summary / "mito_heteroplasmy_all_sites.tsv"
    retain_callable_positions(
        pd.read_csv(table_path, sep="\t"), set(range(1, 58))
    ).to_csv(table_path, sep="\t", index=False)

    outputs = run_phymer(tmp_path, summary, reference)

    metrics = metric_map(Path(outputs["summary_path"]))
    consensus_path = summary / "mito_phymer_consensus.fasta"
    consensus = "".join(
        line.strip()
        for line in consensus_path.read_text(encoding="ascii").splitlines()
        if not line.startswith(">")
    )
    assert outputs["status"] == "ok"
    assert metrics["phymer_callable_fraction"] == "0.95"
    assert metrics["phymer_masked_positions"] == "3"
    assert consensus[9] == "C"
    assert consensus[-3:] == "NNN"


def test_reference_n_is_validated_but_masked_from_phymer_interpretation(
    tmp_path: Path,
) -> None:
    summary, reference = prepare_case(tmp_path)
    sequence = list("A" * MT_LENGTH)
    sequence[19] = "N"
    reference.write_text(">MT\n" + "".join(sequence) + "\n", encoding="ascii")
    Path(f"{reference}.fai").unlink()
    pysam.faidx(str(reference))

    table_path = summary / "mito_heteroplasmy_all_sites.tsv"
    table = pd.read_csv(table_path, sep="\t")
    row = table["position"] == 20
    table.loc[
        row,
        [
            "ref_base",
            "alt_base",
            "alt_count",
            "alt_allele_fraction",
            "heteroplasmy_fraction",
            "alt_forward",
            "alt_reverse",
            "A",
            "C",
        ],
    ] = ["N", "C", 100, 1.0, 1.0, 50, 50, 0, 100]
    table.to_csv(table_path, sep="\t", index=False)

    outputs = run_phymer(tmp_path, summary, reference)

    metrics = metric_map(Path(outputs["summary_path"]))
    consensus = "".join(
        line.strip()
        for line in (summary / "mito_phymer_consensus.fasta")
        .read_text(encoding="ascii")
        .splitlines()
        if not line.startswith(">")
    )
    major = pd.read_csv(outputs["input_path"], sep="\t")
    assert outputs["status"] == "ok"
    assert metrics["phymer_callable_positions"] == "59"
    assert metrics["phymer_callable_fraction"] == "0.983333"
    assert metrics["phymer_masked_positions"] == "1"
    assert metrics["phymer_noncanonical_reference_positions"] == "1"
    assert consensus[19] == "N"
    assert major["phymer_input"].tolist() == ["m.10A>C"]


def test_reference_iupac_ambiguity_other_than_n_is_rejected(tmp_path: Path) -> None:
    summary, reference = prepare_case(tmp_path)
    sequence = list("A" * MT_LENGTH)
    sequence[19] = "R"
    reference.write_text(">MT\n" + "".join(sequence) + "\n", encoding="ascii")
    Path(f"{reference}.fai").unlink()
    pysam.faidx(str(reference))

    table_path = summary / "mito_heteroplasmy_all_sites.tsv"
    table = pd.read_csv(table_path, sep="\t")
    table.loc[table["position"] == 20, "ref_base"] = "R"
    table.to_csv(table_path, sep="\t", index=False)

    with pytest.raises(ValueError, match="only A/C/G/T and unresolved N"):
        run_phymer(tmp_path, summary, reference)


def test_complete_reference_consensus_can_run_without_alternate_variants(
    tmp_path: Path,
) -> None:
    summary, reference = prepare_case(tmp_path)
    table_path = summary / "mito_heteroplasmy_all_sites.tsv"
    table = pd.read_csv(table_path, sep="\t")
    table.loc[table["position"] == 10, ["alt_base", "alt_count", "alt_forward", "alt_reverse", "C"]] = [
        ".",
        0,
        0,
        0,
        0,
    ]
    table.loc[table["position"] == 10, ["alt_allele_fraction", "heteroplasmy_fraction"]] = 0.0
    table.loc[table["position"] == 10, "A"] = 100
    table.to_csv(table_path, sep="\t", index=False)

    outputs = run_phymer(tmp_path, summary, reference)

    assert outputs["status"] == "ok"
    assert pd.read_csv(outputs["input_path"], sep="\t").empty
    assert metric_map(Path(outputs["summary_path"]))["major_variant_sites_used"] == "0"


@pytest.mark.parametrize("score", ["nan", "inf", "-inf", "-0.1", "1.1"])
def test_out_of_domain_phymer_scores_are_not_accepted(score: str) -> None:
    _, ranking = phymer.parse_phymer_output(f"H1a1\t{score}\tm.10A>C\n")

    assert ranking.empty


def test_nonfinite_only_ranking_is_unavailable_without_numeric_zero_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary, reference = prepare_case(tmp_path)
    monkeypatch.setattr(
        phymer.subprocess,
        "run",
        lambda *args, **kwargs: phymer.subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout="H1a1\tnan\tm.10A>C\n", stderr=""
        ),
    )

    outputs = run_phymer(tmp_path, summary, reference)

    metrics = metric_map(Path(outputs["summary_path"]))
    assert outputs["status"] == "unavailable"
    assert metrics["reason_code"] == "no_phymer_ranking_rows"
    assert metrics["best_score"] == "NA"
    assert pd.read_csv(outputs["ranking_path"], sep="\t").empty


def test_external_mode_rejects_fixture_only_callable_fraction(tmp_path: Path) -> None:
    summary, reference = prepare_case(tmp_path)

    with pytest.raises(ValueError, match="cannot be below 0.95.*PHYMER_MODE=external"):
        run_phymer(
            tmp_path,
            summary,
            reference,
            min_callable_fraction=0.30,
            phymer_mode="external",
        )

    assert not (summary / "mito_phymer_haplogroup_summary.tsv").exists()
    assert not (tmp_path / "reports" / "13_mito_phymer_haplogroup.html").exists()


def test_fixture_mode_rejects_noncanonical_vendor_tree(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    summary, reference = prepare_case(case_root)
    vendor = tmp_path / "vendor"
    shutil.copytree(
        Path(__file__).parent / "fixtures" / "mock_phymer_vendor",
        vendor,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (vendor / "Phy-Mer.py").write_text(
        (vendor / "Phy-Mer.py").read_text(encoding="utf-8") + "\n# modified\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exact bundled synthetic wiring fixture"):
        run_phymer(
            case_root,
            summary,
            reference,
            min_callable_fraction=0.30,
            phymer_mode="fixture",
            phymer_root=vendor,
        )

    assert not (summary / "mito_phymer_haplogroup_summary.tsv").exists()
    assert not (case_root / "reports" / "13_mito_phymer_haplogroup.html").exists()


def test_official_phymer_python_imports_are_available() -> None:
    import Bio
    from Bio import Seq, SeqIO, SeqRecord

    assert Bio.__version__ == "1.87"
    assert Seq is not None
    assert SeqIO is not None
    assert SeqRecord is not None


def test_external_vendor_runs_through_python3_compatibility_adapter(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    summary, reference = prepare_case(case_root)
    source_fixture = Path(__file__).parent / "fixtures" / "mock_phymer_vendor"
    vendor = tmp_path / "external-vendor"
    (vendor / "resources").mkdir(parents=True)
    shutil.copyfile(
        source_fixture / "PhyloTree_b16_k12.txt",
        vendor / "PhyloTree_b16_k12.txt",
    )
    shutil.copyfile(
        source_fixture / "resources" / "Build_16_-_rCRS-based_haplogroup_motifs.csv",
        vendor / "resources" / "Build_16_-_rCRS-based_haplogroup_motifs.csv",
    )
    (vendor / "Phy-Mer.py").write_text(
        "from Bio import SeqIO\n"
        "import sys\n"
        "with open(sys.argv[-1], 'rU') as handle:\n"
        "    record = next(SeqIO.parse(handle, 'fasta'))\n"
        "print(record.id)\n"
        "print('H2a2a1\\t0.75\\tNA')\n",
        encoding="ascii",
    )

    outputs = run_phymer(
        case_root,
        summary,
        reference,
        phymer_mode="external",
        phymer_root=vendor,
    )

    metrics = metric_map(Path(outputs["summary_path"]))
    assert outputs["status"] == "ok"
    assert metrics["best_haplogroup"] == "H2a2a1"
    assert metrics["best_score"] == "0.75"
    assert metrics["phymer_mode"] == "external"
    assert metrics["phymer_vendor_provenance"] == "user_supplied_local_vendor"
    assert metrics["phymer_result_scope"] == "external_classifier_output"
    assert metrics["biological_validation_status"] == "not_established"
    assert metrics["phymer_python_compatibility"] == "legacy_universal_newline_adapter"


def test_failed_upstream_status_blocks_stale_haplogroup_and_removes_owned_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary, reference = prepare_case(
        tmp_path, status="failed", reason="allele_counting_failed"
    )
    stale_consensus = summary / "mito_phymer_consensus.fasta"
    stale_figure = tmp_path / "figures" / "mito_phymer_haplogroup_scores.png"
    stale_figure.parent.mkdir()
    stale_consensus.write_text(">stale\nA\n", encoding="ascii")
    stale_figure.write_bytes(b"stale")
    monkeypatch.setattr(
        phymer.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Phy-Mer invoked")),
    )

    outputs = run_phymer(tmp_path, summary, reference)

    metrics = metric_map(Path(outputs["summary_path"]))
    assert outputs["status"] == "failed"
    assert metrics["reason_code"] == "upstream_heteroplasmy_failed"
    assert metrics["upstream_heteroplasmy_reason_code"] == "allele_counting_failed"
    assert pd.read_csv(outputs["ranking_path"], sep="\t").empty
    assert not stale_consensus.exists()
    assert not stale_figure.exists()


def test_direct_step_exception_clears_all_prior_owned_outputs(tmp_path: Path) -> None:
    summary, reference = prepare_case(tmp_path)
    first = run_phymer(tmp_path, summary, reference)
    owned = {
        Path(first["summary_path"]),
        Path(first["ranking_path"]),
        Path(first["input_path"]),
        Path(first["report_path"]),
        summary / "mito_phymer_raw_output.txt",
        summary / "mito_phymer_raw_error.txt",
        summary / "mito_phymer_consensus.fasta",
        tmp_path / "figures" / "mito_phymer_haplogroup_scores.png",
    }
    assert all(path.exists() for path in owned)

    table_path = summary / "mito_heteroplasmy_all_sites.tsv"
    table = pd.read_csv(table_path, sep="\t")
    table.loc[table["position"] == 10, "ref_base"] = "G"
    table.to_csv(table_path, sep="\t", index=False)

    with pytest.raises(ValueError, match="disagree with the configured reference"):
        run_phymer(tmp_path, summary, reference)

    assert all(not path.exists() for path in owned)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda table: pd.concat([table, table.iloc[[9]]], ignore_index=True),
            "duplicate positions",
        ),
        (
            lambda table: table.assign(
                position=table["position"].where(table.index != 9, 0)
            ),
            "position",
        ),
        (
            lambda table: table.assign(
                ref_base=table["ref_base"].where(table.index != 9, "G")
            ),
            "disagree with the configured reference",
        ),
        (
            lambda table: table.drop(columns=["callable_depth"]),
            "lacks required columns",
        ),
    ],
    ids=("duplicate-position", "position-zero", "reference-mismatch", "partial-schema"),
)
def test_invalid_all_site_evidence_fails_before_phymer_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutator,
    message: str,
) -> None:
    summary, reference = prepare_case(tmp_path)
    table_path = summary / "mito_heteroplasmy_all_sites.tsv"
    malformed = mutator(pd.read_csv(table_path, sep="\t"))
    malformed.to_csv(table_path, sep="\t", index=False)
    monkeypatch.setattr(
        phymer.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Phy-Mer invoked")),
    )

    with pytest.raises(ValueError, match=message):
        run_phymer(tmp_path, summary, reference)


def test_missing_all_site_file_is_distinct_from_invalid_internal_evidence(
    tmp_path: Path,
) -> None:
    summary, reference = prepare_case(tmp_path)
    (summary / "mito_heteroplasmy_all_sites.tsv").unlink()

    outputs = run_phymer(tmp_path, summary, reference)

    metrics = metric_map(Path(outputs["summary_path"]))
    assert outputs["status"] == "not_evaluable"
    assert metrics["reason_code"] == "all_site_table_missing"
    assert metrics["upstream_heteroplasmy_status"] == "ok"
