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


def run_phymer(root: Path, summary: Path, reference: Path) -> dict[str, Path | str]:
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
    )


def test_valid_complete_all_site_evidence_produces_mock_haplogroup(tmp_path: Path) -> None:
    summary, reference = prepare_case(tmp_path)

    outputs = run_phymer(tmp_path, summary, reference)

    metrics = metric_map(Path(outputs["summary_path"]))
    assert outputs["status"] == "ok"
    assert metrics["best_haplogroup"] == "H1a1"
    assert metrics["major_variant_sites_used"] == "1"
    assert metrics["upstream_heteroplasmy_status"] == "ok"
    major = pd.read_csv(outputs["input_path"], sep="\t")
    assert major["phymer_input"].tolist() == ["m.10A>C"]


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
