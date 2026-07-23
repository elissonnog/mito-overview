from __future__ import annotations

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
        phymer_root=Path(__file__).parent / "fixtures" / "mock_phymer_vendor",
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


@pytest.mark.parametrize("score", ["nan", "inf", "-inf"])
def test_nonfinite_phymer_scores_are_not_accepted(score: str) -> None:
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
