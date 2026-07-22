from __future__ import annotations

from pathlib import Path

import pandas as pd
import pysam
import pytest

from mito_overview.steps.mito_feature_annotation import (
    DLOOP_INTERVALS,
    classify_position,
    load_human_mt_features,
    resolve_control_region_annotation,
    run_step as run_feature_annotation,
)
from mito_overview.steps.mito_variant_consequence import (
    ANNOTATION_COLUMNS,
    annotate_protein_change,
    run_step as run_variant_consequence,
    translate_codon,
)

from ._helpers import metric_map


RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources" / "annotations"
HUMAN_MT_FASTA = RESOURCE_DIR / "NC_012920.1.fa"
HUMAN_MT_GTF = RESOURCE_DIR / "human_mt_reference.gtf"


def canonical_mt_sequence() -> str:
    return "".join(HUMAN_MT_FASTA.read_text(encoding="ascii").splitlines()[1:])


def write_heteroplasmy_status(
    summary_dir: Path,
    *,
    status: str = "ok",
    reason_code: str = "",
) -> None:
    pd.DataFrame(
        [
            {"metric": "status", "value": status},
            {"metric": "reason_code", "value": reason_code},
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_summary.tsv", sep="\t", index=False)


def write_consequence_fixture(tmp_path: Path, *, position: int = 1000) -> tuple[Path, Path]:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir(parents=True)
    (summary_dir / "mito_heteroplasmy_candidates.tsv").write_text(
        "position\tref_base\talt_base\tdepth\talt_allele_fraction\theteroplasmy_fraction\n"
        f"{position}\tA\tC\t100\t0.25\t0.25\n",
        encoding="ascii",
    )
    write_heteroplasmy_status(summary_dir)
    fasta = tmp_path / "mt.fa"
    fasta.write_text(">MT\n" + "A" * 2000 + "\n", encoding="ascii")
    pysam.faidx(str(fasta))
    return summary_dir, fasta


def write_feature_gating_fixture(
    tmp_path: Path,
    *,
    contig: str,
    sequence: str,
    candidate_position: int = 1,
) -> tuple[Path, Path, Path]:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir(parents=True)
    (summary_dir / "mito_heteroplasmy_candidates.tsv").write_text(
        "position\tref_base\talt_base\tdepth\talt_allele_fraction\theteroplasmy_fraction\n"
        f"{candidate_position}\tA\tC\t100\t0.25\t0.25\n",
        encoding="ascii",
    )
    write_heteroplasmy_status(summary_dir)
    fasta = tmp_path / "configured_reference.fa"
    fasta.write_text(f">{contig}\n{sequence}\n", encoding="ascii")
    pysam.faidx(str(fasta))
    gtf = tmp_path / "compatible.gtf"
    gtf.write_text(
        f'{contig}\ttest\tgene\t1\t3\t.\t+\t.\tgene_id "CUSTOM-START"; '
        'gene_name "CUSTOM-START"; gene_biotype "protein_coding";\n'
        f'{contig}\ttest\tCDS\t1\t3\t.\t+\t0\tgene_id "CUSTOM-START"; '
        'gene_name "CUSTOM-START"; gene_biotype "protein_coding";\n',
        encoding="ascii",
    )
    return summary_dir, fasta, gtf


def run_canonical_consequence_fixture(
    tmp_path: Path,
    candidates: list[tuple[int, str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_dir = tmp_path / "canonical-summary"
    summary_dir.mkdir(parents=True)
    candidate_rows = [
        "position\tref_base\talt_base\tdepth\talt_allele_fraction\theteroplasmy_fraction"
    ]
    candidate_rows.extend(
        f"{position}\t{ref_base}\t{alt_base}\t100\t0.25\t0.25"
        for position, ref_base, alt_base in candidates
    )
    (summary_dir / "mito_heteroplasmy_candidates.tsv").write_text(
        "\n".join(candidate_rows) + "\n",
        encoding="ascii",
    )
    write_heteroplasmy_status(summary_dir)

    fasta = tmp_path / "NC_012920.1.fa"
    source_lines = HUMAN_MT_FASTA.read_text(encoding="ascii").splitlines()
    fasta.write_text(">MT\n" + "\n".join(source_lines[1:]) + "\n", encoding="ascii")
    pysam.faidx(str(fasta))
    run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "canonical-feature-figures",
        report_dir=tmp_path / "canonical-feature-reports",
        sample_id="CANONICAL-MT",
        species="human",
        build="hg38",
        mt_contig="MT",
        mt_length=16569,
        ref_fasta=fasta,
        human_mt_gtf=HUMAN_MT_GTF,
    )
    outputs = run_variant_consequence(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "canonical-consequence-figures",
        report_dir=tmp_path / "canonical-consequence-reports",
        sample_id="CANONICAL-MT",
        mt_contig="MT",
        mt_length=16569,
        ref_fasta=fasta,
    )
    overlaps = pd.read_csv(summary_dir / "mito_feature_overlap_candidates.tsv", sep="\t")
    annotations = pd.read_csv(outputs["annot_path"], sep="\t", keep_default_na=False)
    return overlaps, annotations


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
            {
                "feature_type": "gene",
                "gene_name": "MT-TY",
                "gene_biotype": "Mt_tRNA",
                "start": 1001,
                "end": 1002,
                "strand": "+",
            },
        ]
    )

    assert classify_position(1, features) == [("protein_coding", "OVERLAPPING-CONTROL")]

    def classify(position: int) -> list[tuple[str, str]]:
        return classify_position(
            position,
            features,
            control_region_intervals=DLOOP_INTERVALS,
        )
    assert classify(1) == [("control_region", "D-loop/control region")]
    assert classify(576) == [("control_region", "D-loop/control region")]
    assert classify(577) == [("protein_coding", "MT-ND1")]
    assert classify(579) == [("protein_coding", "MT-ND1")]
    assert classify(580) == [("intergenic", "intergenic")]
    assert classify(999) == [("intergenic", "intergenic")]
    assert classify(1000) == [("Mt_tRNA", "MT-TX")]
    assert classify(1002) == [("Mt_tRNA", "MT-TX"), ("Mt_tRNA", "MT-TY")]
    assert classify(1003) == [("intergenic", "intergenic")]
    assert classify(16023) == [("intergenic", "intergenic")]
    assert classify(16024) == [("control_region", "D-loop/control region")]
    assert classify(16569) == [("control_region", "D-loop/control region")]


@pytest.mark.parametrize("contig", ["MT", "chrM", "NC_012920.1"])
def test_control_region_requires_exact_sequence_not_contig_name(
    tmp_path: Path,
    contig: str,
) -> None:
    summary_dir, fasta, gtf = write_feature_gating_fixture(
        tmp_path,
        contig=contig,
        sequence=canonical_mt_sequence().lower(),
    )

    outputs = run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="EXACT-CANONICAL",
        species="human",
        build="custom",
        mt_contig=contig,
        mt_length=16569,
        ref_fasta=fasta,
        human_mt_gtf=gtf,
    )
    overlaps = pd.read_csv(outputs["overlap_path"], sep="\t")
    catalog = pd.read_csv(outputs["catalog_path"], sep="\t", keep_default_na=False)

    assert outputs["status"] == "ok"
    assert outputs["control_region_annotation_status"] == "ok"
    assert outputs["control_region_annotation_reason_code"] == (
        "reference_sequence_exact_match"
    )
    assert overlaps[["position", "feature_class", "feature_label"]].values.tolist() == [
        [1, "control_region", "D-loop/control region"]
    ]
    assert set(catalog["control_region_exact_sequence_match"]) == {1}
    assert set(catalog["control_region_annotation_method"]) == {
        "exact_full_sequence_identity"
    }
    assert set(catalog["control_region_intervals_applied"]) == {
        "1-576;16024-16569"
    }


def test_same_length_mutated_reference_disables_canonical_control_region_only(
    tmp_path: Path,
) -> None:
    canonical = canonical_mt_sequence()
    mutated = ("A" if canonical[0] != "A" else "C") + canonical[1:]
    summary_dir, fasta, gtf = write_feature_gating_fixture(
        tmp_path,
        contig="MT",
        sequence=mutated,
    )
    fasta_with_canonical_name = tmp_path / "NC_012920.1.fa"
    fasta.rename(fasta_with_canonical_name)
    Path(f"{fasta}.fai").rename(Path(f"{fasta_with_canonical_name}.fai"))

    outputs = run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="MUTATED-SAME-LENGTH",
        species="human",
        build="hg38",
        mt_contig="MT",
        mt_length=16569,
        ref_fasta=fasta_with_canonical_name,
        human_mt_gtf=gtf,
    )
    overlaps = pd.read_csv(outputs["overlap_path"], sep="\t")
    catalog = pd.read_csv(outputs["catalog_path"], sep="\t", keep_default_na=False)

    assert len(mutated) == len(canonical) == 16569
    assert outputs["status"] == "ok"
    assert outputs["control_region_annotation_status"] == "not_evaluable"
    assert outputs["control_region_annotation_reason_code"] == (
        "reference_sequence_not_nc_012920_1"
    )
    assert overlaps[["position", "feature_class", "feature_label"]].values.tolist() == [
        [1, "protein_coding", "CUSTOM-START"]
    ]
    assert set(catalog["control_region_exact_sequence_match"]) == {0}
    assert set(catalog["control_region_configured_sequence_length"]) == {16569}
    assert set(catalog["control_region_canonical_sequence_length"]) == {16569}
    assert set(catalog["control_region_intervals_applied"]) == {""}
    assert "reference_sequence_not_nc_012920_1" in Path(outputs["report_path"]).read_text(
        encoding="utf-8"
    )


def test_tiny_reference_control_region_requires_recorded_synthetic_override(
    tmp_path: Path,
) -> None:
    summary_dir, fasta, gtf = write_feature_gating_fixture(
        tmp_path,
        contig="MT",
        sequence="A" * 60,
        candidate_position=1,
    )

    automatic = resolve_control_region_annotation(
        ref_fasta=fasta,
        mt_contig="MT",
        mode="auto",
    )
    outputs = run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="SYNTHETIC-OVERRIDE",
        species="human",
        build="synthetic",
        mt_contig="MT",
        mt_length=60,
        ref_fasta=fasta,
        human_mt_gtf=gtf,
        control_region_annotation_mode="synthetic_fixture_override",
    )
    overlaps = pd.read_csv(outputs["overlap_path"], sep="\t")
    catalog = pd.read_csv(outputs["catalog_path"], sep="\t", keep_default_na=False)

    assert automatic.status == "not_evaluable"
    assert automatic.intervals == ()
    assert outputs["control_region_annotation_status"] == "ok"
    assert outputs["control_region_annotation_reason_code"] == "synthetic_fixture_override"
    assert overlaps[["position", "feature_class", "feature_label"]].values.tolist() == [
        [1, "control_region", "D-loop/control region"]
    ]
    assert set(catalog["control_region_annotation_mode"]) == {
        "synthetic_fixture_override"
    }
    assert set(catalog["control_region_exact_sequence_match"]) == {0}


def test_disabled_control_region_state_is_explicitly_not_configured(
    tmp_path: Path,
) -> None:
    _, fasta, _ = write_feature_gating_fixture(
        tmp_path,
        contig="MT",
        sequence=canonical_mt_sequence(),
    )

    decision = resolve_control_region_annotation(
        ref_fasta=fasta,
        mt_contig="MT",
        mode="disabled",
    )

    assert decision.status == "not_configured"
    assert decision.reason_code == "control_region_annotation_disabled"
    assert decision.intervals == ()


def test_overlapping_mitochondrial_cds_emit_one_stably_ordered_consequence_each(
    tmp_path: Path,
) -> None:
    overlaps, annotations = run_canonical_consequence_fixture(
        tmp_path,
        [(8530, "A", "C"), (9207, "A", "C"), (10762, "G", "A")],
    )
    expected = [
        (8530, "MT-ATP8"),
        (8530, "MT-ATP6"),
        (9207, "MT-ATP6"),
        (9207, "MT-CO3"),
        (10762, "MT-ND4L"),
        (10762, "MT-ND4"),
    ]

    assert list(overlaps[["position", "feature_label"]].itertuples(index=False, name=None)) == expected
    assert annotations[
        [
            "position",
            "feature_label",
            "feature_class",
            "consequence_class",
            "codon_ref",
            "codon_alt",
            "protein_change",
        ]
    ].values.tolist() == [
        [8530, "MT-ATP8", "protein_coding", "missense_variant", "TGA", "TGC", "p.W55C"],
        [8530, "MT-ATP6", "protein_coding", "missense_variant", "AAC", "CAC", "p.N2H"],
        [9207, "MT-ATP6", "protein_coding", "stop_lost", "TAA", "TAC", "p.*227Y"],
        [9207, "MT-CO3", "protein_coding", "start_lost", "ATG", "CTG", "p.M1?"],
        [10762, "MT-ND4L", "protein_coding", "missense_variant", "TGC", "TAC", "p.C98Y"],
        [10762, "MT-ND4", "protein_coding", "synonymous_variant", "ATG", "ATA", "p.M1M"],
    ]


def test_mt_nd2_m4471t_to_c_is_conservative_start_loss(tmp_path: Path) -> None:
    _, annotations = run_canonical_consequence_fixture(tmp_path, [(4471, "T", "C")])

    assert annotations[
        [
            "position",
            "ref_base",
            "alt_base",
            "feature_label",
            "consequence_class",
            "codon_ref",
            "codon_alt",
            "protein_change",
        ]
    ].values.tolist() == [
        [4471, "T", "C", "MT-ND2", "start_lost", "ATT", "ACT", "p.M1?"]
    ]


@pytest.mark.parametrize(
    ("position", "alternate", "expected"),
    [
        (1, "G", ("synonymous_variant", "ATG", "GTG", "p.M1M")),
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
        (6, "C", ("synonymous_variant", "ATG", "GTG", "p.M1M")),
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


@pytest.mark.parametrize(
    ("reference_codon", "position", "alternate", "alternate_codon"),
    [
        ("ATT", 3, "C", "ATC"),
        ("ATC", 3, "T", "ATT"),
        ("ATA", 3, "G", "ATG"),
        ("ATG", 1, "G", "GTG"),
        ("GTG", 1, "A", "ATG"),
    ],
)
def test_accepted_mitochondrial_initiators_encode_methionine_at_codon_one(
    reference_codon: str,
    position: int,
    alternate: str,
    alternate_codon: str,
) -> None:
    cds = pd.DataFrame(
        [{"gene_name": "GENE", "start": 1, "end": 3, "strand": "+"}]
    )

    assert annotate_protein_change(position, alternate, "GENE", cds, reference_codon) == (
        "synonymous_variant",
        reference_codon,
        alternate_codon,
        "p.M1M",
    )


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
        ref_fasta=fasta,
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
        ref_fasta=fasta,
        human_mt_gtf=tmp_path / "missing.gtf",
    )

    outputs = run_consequence(tmp_path, summary_dir, fasta)
    metrics = metric_map(Path(outputs["summary_path"]))

    assert feature_outputs["status"] == "not_configured"
    assert outputs["status"] == "not_configured"
    assert metrics["status"] == "not_configured"
    assert metrics["reason_code"] == "human_mt_gtf_not_configured"


def test_missing_candidate_table_is_not_reported_as_observed_zero(tmp_path: Path) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    write_heteroplasmy_status(summary_dir)
    fasta = tmp_path / "mt.fa"
    fasta.write_text(">MT\n" + "A" * 2000 + "\n", encoding="ascii")
    pysam.faidx(str(fasta))

    feature_outputs = run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "feature-figures",
        report_dir=tmp_path / "feature-reports",
        sample_id="NO-CANDIDATE-EVIDENCE",
        species="human",
        build="hg38",
        mt_contig="MT",
        mt_length=2000,
        ref_fasta=fasta,
        human_mt_gtf=HUMAN_MT_GTF,
    )
    feature_metrics = metric_map(Path(feature_outputs["summary_path"]))
    overlaps = pd.read_csv(feature_outputs["overlap_path"], sep="\t")
    consequence_outputs = run_consequence(tmp_path, summary_dir, fasta)
    consequence_metrics = metric_map(Path(consequence_outputs["summary_path"]))

    assert feature_outputs["status"] == "not_evaluable"
    assert feature_metrics["reason_code"] == "heteroplasmy_candidates_missing"
    assert overlaps.empty
    assert consequence_outputs["status"] == "not_evaluable"
    assert consequence_metrics["reason_code"] == "heteroplasmy_candidates_missing"


def test_no_callable_positions_propagates_through_feature_and_consequence(
    tmp_path: Path,
) -> None:
    summary_dir, fasta = write_consequence_fixture(tmp_path)
    pd.DataFrame(
        columns=[
            "position",
            "ref_base",
            "alt_base",
            "depth",
            "alt_allele_fraction",
            "heteroplasmy_fraction",
        ]
    ).to_csv(summary_dir / "mito_heteroplasmy_candidates.tsv", sep="\t", index=False)
    write_heteroplasmy_status(
        summary_dir,
        status="not_evaluable",
        reason_code="no_callable_positions",
    )

    feature_outputs = run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "feature-figures",
        report_dir=tmp_path / "feature-reports",
        sample_id="NO-CALLABLE",
        species="human",
        build="hg38",
        mt_contig="MT",
        mt_length=2000,
        ref_fasta=fasta,
        human_mt_gtf=HUMAN_MT_GTF,
    )
    consequence_outputs = run_consequence(tmp_path, summary_dir, fasta)

    assert feature_outputs["status"] == "not_evaluable"
    assert metric_map(Path(feature_outputs["summary_path"]))["reason_code"] == "no_callable_positions"
    assert consequence_outputs["status"] == "not_evaluable"
    assert metric_map(Path(consequence_outputs["summary_path"]))["reason_code"] == "no_callable_positions"


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
        ref_fasta=fasta,
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


def test_consequence_rejects_candidate_without_explicit_feature_overlap(tmp_path: Path) -> None:
    summary_dir, fasta = write_consequence_fixture(tmp_path, position=1000)
    run_feature_annotation(
        summary_dir=summary_dir,
        figure_dir=tmp_path / "feature-figures",
        report_dir=tmp_path / "feature-reports",
        sample_id="MISSING-OVERLAP",
        species="human",
        build="hg38",
        mt_contig="MT",
        mt_length=2000,
        ref_fasta=fasta,
        human_mt_gtf=HUMAN_MT_GTF,
    )
    overlap_path = summary_dir / "mito_feature_overlap_candidates.tsv"
    pd.read_csv(overlap_path, sep="\t").iloc[0:0].to_csv(overlap_path, sep="\t", index=False)

    outputs = run_consequence(tmp_path, summary_dir, fasta)
    metrics = metric_map(Path(outputs["summary_path"]))
    annotations = pd.read_csv(outputs["annot_path"], sep="\t")

    assert outputs["status"] == "not_evaluable"
    assert metrics["reason_code"] == "feature_overlap_candidate_key_mismatch"
    assert annotations.empty
