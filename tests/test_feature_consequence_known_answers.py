from __future__ import annotations

from pathlib import Path

import pandas as pd
import pysam
import pytest

from mito_overview.steps.mito_feature_annotation import (
    classify_position,
    load_human_mt_features,
    run_step as run_feature_annotation,
)
from mito_overview.steps.mito_variant_consequence import (
    ANNOTATION_COLUMNS,
    annotate_protein_change,
    run_step as run_variant_consequence,
    translate_codon,
)

from ._helpers import metric_map


def write_consequence_fixture(tmp_path: Path, *, position: int = 1000) -> tuple[Path, Path]:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir(parents=True)
    (summary_dir / "mito_heteroplasmy_candidates.tsv").write_text(
        "position\tref_base\talt_base\tdepth\talt_allele_fraction\theteroplasmy_fraction\n"
        f"{position}\tA\tC\t100\t0.25\t0.25\n",
        encoding="ascii",
    )
    fasta = tmp_path / "mt.fa"
    fasta.write_text(">MT\n" + "A" * 2000 + "\n", encoding="ascii")
    pysam.faidx(str(fasta))
    return summary_dir, fasta


def run_consequence(tmp_path: Path, summary_dir: Path, fasta: Path, **kwargs: str) -> dict[str, Path | str]:
    return run_variant_consequence(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "consequence-figures",
        report_dir=tmp_path / "consequence-reports",
        sample_id="STATE-TEST",
        mt_contig="MT",
        mt_length=2000,
        ref_fasta=fasta,
        **kwargs,
    )


def test_feature_annotation_inclusive_boundaries_and_control_region_precedence() -> None:
    features = pd.DataFrame(
        [
            {
                "feature_type": "gene",
                "gene_name": "OVERLAPPING-CONTROL",
                "gene_biotype": "protein_coding",
                "start": 1,
                "end": 3,
                "strand": "+",
            },
            {
                "feature_type": "gene",
                "gene_name": "MT-ND1",
                "gene_biotype": "protein_coding",
                "start": 577,
                "end": 579,
                "strand": "+",
            },
            {
                "feature_type": "CDS",
                "gene_name": "MT-ND1",
                "gene_biotype": "protein_coding",
                "start": 577,
                "end": 579,
                "strand": "+",
            },
            {
                "feature_type": "gene",
                "gene_name": "MT-TX",
                "gene_biotype": "Mt_tRNA",
                "start": 1000,
                "end": 1002,
                "strand": "+",
            },
        ]
    )

    assert classify_position(1, features) == ("control_region", "D-loop/control region")
    assert classify_position(576, features) == ("control_region", "D-loop/control region")
    assert classify_position(577, features) == ("protein_coding", "MT-ND1")
    assert classify_position(579, features) == ("protein_coding", "MT-ND1")
    assert classify_position(580, features) == ("intergenic", "intergenic")
    assert classify_position(999, features) == ("intergenic", "intergenic")
    assert classify_position(1000, features) == ("Mt_tRNA", "MT-TX")
    assert classify_position(1002, features) == ("Mt_tRNA", "MT-TX")
    assert classify_position(1003, features) == ("intergenic", "intergenic")
    assert classify_position(16023, features) == ("intergenic", "intergenic")
    assert classify_position(16024, features) == ("control_region", "D-loop/control region")
    assert classify_position(16569, features) == ("control_region", "D-loop/control region")


@pytest.mark.parametrize(
    ("position", "alternate", "expected"),
    [
        (1, "G", ("missense_variant", "ATG", "GTG", "p.M1V")),
        (3, "A", ("synonymous_variant", "ATG", "ATA", "p.M1M")),
        (4, "C", ("stop_lost", "TAA", "CAA", "p.*2Q")),
        (6, "G", ("synonymous_variant", "TAA", "TAG", "p.*2*")),
    ],
)
def test_positive_strand_protein_consequence_boundaries(
    position: int,
    alternate: str,
    expected: tuple[str, str, str, str],
) -> None:
    cds = pd.DataFrame(
        [{"gene_name": "GENE", "start": 1, "end": 6, "strand": "+"}]
    )

    assert annotate_protein_change(position, alternate, "GENE", cds, "ATGTAA") == expected


@pytest.mark.parametrize("position", [0, 7])
def test_protein_consequence_outside_cds_is_unspecified(position: int) -> None:
    cds = pd.DataFrame(
        [{"gene_name": "GENE", "start": 1, "end": 6, "strand": "+"}]
    )

    assert annotate_protein_change(position, "A", "GENE", cds, "ATGTAA") == (
        "protein_coding_unspecified",
        "NA",
        "NA",
        "NA",
    )


def test_mitochondrial_stop_gained_known_answer() -> None:
    cds = pd.DataFrame(
        [{"gene_name": "GENE", "start": 1, "end": 3, "strand": "+"}]
    )

    assert annotate_protein_change(2, "G", "GENE", cds, "AAA") == (
        "stop_gained",
        "AAA",
        "AGA",
        "p.K1*",
    )


@pytest.mark.parametrize(
    ("position", "genomic_alternate", "expected"),
    [
        (6, "C", ("missense_variant", "ATG", "GTG", "p.M1V")),
        (4, "T", ("synonymous_variant", "ATG", "ATA", "p.M1M")),
        (3, "G", ("stop_lost", "TAA", "CAA", "p.*2Q")),
        (1, "C", ("synonymous_variant", "TAA", "TAG", "p.*2*")),
    ],
)
def test_negative_strand_protein_consequence_known_answers(
    position: int,
    genomic_alternate: str,
    expected: tuple[str, str, str, str],
) -> None:
    cds = pd.DataFrame(
        [{"gene_name": "GENE", "start": 1, "end": 6, "strand": "-"}]
    )

    # Reverse complement of genomic TTACAT is coding-strand ATGTAA.
    assert annotate_protein_change(position, genomic_alternate, "GENE", cds, "TTACAT") == expected


def test_vertebrate_mitochondrial_codon_table_known_answers() -> None:
    assert translate_codon("TGA") == "W"
    assert translate_codon("AGA") == "*"
    assert translate_codon("AGG") == "*"
    assert translate_codon("ATA") == "M"


def test_feature_loader_preserves_gtf_phase(tmp_path) -> None:
    gtf = tmp_path / "mt.gtf"
    gtf.write_text(
        'MT\ttest\tCDS\t1\t6\t.\t+\t2\tgene_id "G"; gene_name "G"; '
        'gene_biotype "protein_coding";\n',
        encoding="ascii",
    )

    observed = load_human_mt_features(gtf, "MT")

    assert observed.iloc[0]["phase"] == "2"


def test_multiple_cds_intervals_are_not_silently_collapsed() -> None:
    cds = pd.DataFrame(
        [
            {"gene_name": "GENE", "start": 1, "end": 3, "strand": "+", "phase": "0"},
            {"gene_name": "GENE", "start": 4, "end": 6, "strand": "+", "phase": "0"},
        ]
    )

    assert annotate_protein_change(2, "G", "GENE", cds, "AAATTT") == (
        "protein_coding_unspecified",
        "NA",
        "NA",
        "NA",
    )


@pytest.mark.parametrize("phase", ["1", "2", "."])
def test_nonzero_or_unknown_cds_phase_is_not_guessed(phase: str) -> None:
    cds = pd.DataFrame(
        [{"gene_name": "GENE", "start": 1, "end": 3, "strand": "+", "phase": phase}]
    )

    assert annotate_protein_change(2, "G", "GENE", cds, "AAA") == (
        "protein_coding_unspecified",
        "NA",
        "NA",
        "NA",
    )


def test_consequence_propagates_nonhuman_feature_not_applicable(tmp_path: Path) -> None:
    summary_dir, fasta = write_consequence_fixture(tmp_path)
    feature_outputs = run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "feature-figures",
        report_dir=tmp_path / "feature-reports",
        sample_id="MOUSE",
        species="mouse",
        build="custom",
        mt_contig="MT",
        mt_length=2000,
        human_mt_gtf=None,
    )

    outputs = run_consequence(tmp_path, summary_dir, fasta)
    metrics = metric_map(Path(outputs["summary_path"]))
    annotations = pd.read_csv(outputs["annot_path"], sep="\t")

    assert feature_outputs["status"] == "not_applicable"
    assert outputs["status"] == "not_applicable"
    assert metrics["status"] == "not_applicable"
    assert metrics["reason_code"] == "non_human_sample"
    assert list(annotations.columns) == ANNOTATION_COLUMNS
    assert annotations.empty


def test_consequence_propagates_missing_gtf_not_configured(tmp_path: Path) -> None:
    summary_dir, fasta = write_consequence_fixture(tmp_path)
    feature_outputs = run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "feature-figures",
        report_dir=tmp_path / "feature-reports",
        sample_id="HUMAN",
        species="human",
        build="hg38",
        mt_contig="MT",
        mt_length=2000,
        human_mt_gtf=tmp_path / "missing.gtf",
    )

    outputs = run_consequence(tmp_path, summary_dir, fasta)
    metrics = metric_map(Path(outputs["summary_path"]))

    assert feature_outputs["status"] == "not_configured"
    assert outputs["status"] == "not_configured"
    assert metrics["status"] == "not_configured"
    assert metrics["reason_code"] == "human_mt_gtf_not_configured"


def test_consequence_propagates_explicit_feature_not_evaluable(tmp_path: Path) -> None:
    summary_dir, fasta = write_consequence_fixture(tmp_path)

    outputs = run_consequence(
        tmp_path,
        summary_dir,
        fasta,
        feature_annotation_status="not_evaluable",
        feature_annotation_reason_code="feature_catalog_unusable",
    )
    metrics = metric_map(Path(outputs["summary_path"]))

    assert outputs["status"] == "not_evaluable"
    assert metrics["status"] == "not_evaluable"
    assert metrics["reason_code"] == "feature_catalog_unusable"


def test_successful_feature_annotation_preserves_genuine_intergenic_result(tmp_path: Path) -> None:
    summary_dir, fasta = write_consequence_fixture(tmp_path, position=1000)
    gtf = tmp_path / "mt.gtf"
    gtf.write_text(
        'MT\ttest\tgene\t1200\t1202\t.\t+\t.\tgene_id "G"; gene_name "G"; '
        'gene_biotype "protein_coding";\n'
        'MT\ttest\tCDS\t1200\t1202\t.\t+\t0\tgene_id "G"; gene_name "G"; '
        'gene_biotype "protein_coding";\n',
        encoding="ascii",
    )
    feature_outputs = run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "feature-figures",
        report_dir=tmp_path / "feature-reports",
        sample_id="HUMAN",
        species="human",
        build="hg38",
        mt_contig="MT",
        mt_length=2000,
        human_mt_gtf=gtf,
    )

    outputs = run_consequence(tmp_path, summary_dir, fasta)
    annotations = pd.read_csv(outputs["annot_path"], sep="\t", keep_default_na=False)
    metrics = metric_map(Path(outputs["summary_path"]))

    assert feature_outputs["status"] == "ok"
    assert outputs["status"] == "ok"
    assert metrics["status"] == "ok"
    assert annotations[["position", "feature_class", "feature_label", "consequence_class"]].values.tolist() == [
        [1000, "intergenic", "intergenic", "intergenic_variant"]
    ]
