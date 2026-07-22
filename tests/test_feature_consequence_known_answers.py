from __future__ import annotations

import pandas as pd
import pytest

from mito_overview.steps.mito_feature_annotation import classify_position
from mito_overview.steps.mito_variant_consequence import (
    annotate_protein_change,
    translate_codon,
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
