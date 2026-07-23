from __future__ import annotations

import pandas as pd
import pytest

from mito_overview.table_contracts import validate_candidate_table


def valid_candidate() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "position": 2,
                "ref_base": "C",
                "alt_base": "A",
                "callable_depth": 10,
                "depth": 10,
                "alt_count": 3,
                "alt_allele_fraction": 0.3,
                "heteroplasmy_fraction": 0.3,
                "alt_forward": 1,
                "alt_reverse": 2,
                "A": 3,
                "C": 7,
                "G": 0,
                "T": 0,
            }
        ]
    )


def test_complete_candidate_contract_has_exact_known_answer() -> None:
    observed = validate_candidate_table(
        valid_candidate(),
        table_name="known-answer",
        mt_length=4,
        reference_sequence="ACGT",
    )

    assert observed.iloc[0]["position"] == 2
    assert observed.iloc[0]["callable_depth"] == 10
    assert observed.iloc[0]["alt_count"] == 3
    assert observed.iloc[0]["alt_forward"] + observed.iloc[0]["alt_reverse"] == 3
    assert observed.iloc[0][["A", "C", "G", "T"]].sum() == 10
    assert observed.iloc[0]["alt_allele_fraction"] == pytest.approx(0.3)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("position", 2.5, "position"),
        ("position", 5, "position"),
        ("depth", 10.5, "depth"),
        ("callable_depth", 9, "conflicts"),
        ("alt_allele_fraction", 1.1, "alt_allele_fraction"),
        ("alt_count", 11, "exceeds"),
        ("alt_forward", 2, "strand counts"),
        ("A", 2, "A/C/G/T counts"),
    ],
)
def test_malformed_candidate_evidence_is_rejected(
    column: str,
    value: object,
    message: str,
) -> None:
    candidate = valid_candidate()
    candidate[column] = candidate[column].astype(object)
    candidate.loc[0, column] = value

    with pytest.raises(ValueError, match=message):
        validate_candidate_table(
            candidate,
            table_name="malformed",
            mt_length=4,
            reference_sequence="ACGT",
        )


def test_ref_equal_alt_and_reference_disagreement_are_rejected() -> None:
    ref_equal = valid_candidate()
    ref_equal.loc[0, "alt_base"] = "C"
    with pytest.raises(ValueError, match="REF-equal-ALT"):
        validate_candidate_table(ref_equal, table_name="ref-equal-alt")

    mismatch = valid_candidate()
    mismatch.loc[0, "ref_base"] = "G"
    with pytest.raises(ValueError, match="disagree with the configured reference"):
        validate_candidate_table(
            mismatch,
            table_name="reference-mismatch",
            mt_length=4,
            reference_sequence="ACGT",
        )


@pytest.mark.parametrize(
    "column",
    [
        "position",
        "ref_base",
        "alt_base",
        "callable_depth",
        "depth",
        "alt_count",
        "alt_allele_fraction",
        "heteroplasmy_fraction",
        "alt_forward",
        "alt_reverse",
        "A",
        "C",
        "G",
        "T",
    ],
)
def test_every_generated_candidate_column_is_required(column: str) -> None:
    candidate = valid_candidate().drop(columns=[column])

    with pytest.raises(ValueError, match="lacks required columns"):
        validate_candidate_table(candidate, table_name="incomplete")


def test_non_numeric_legacy_fraction_is_not_silently_repaired() -> None:
    candidate = valid_candidate()
    candidate["heteroplasmy_fraction"] = candidate["heteroplasmy_fraction"].astype(object)
    candidate.loc[0, "heteroplasmy_fraction"] = "garbage"

    with pytest.raises(ValueError, match="heteroplasmy_fraction"):
        validate_candidate_table(candidate, table_name="bad-legacy-alias")


def test_fraction_alias_disagreement_is_rejected() -> None:
    candidate = valid_candidate()
    candidate.loc[0, "heteroplasmy_fraction"] = 0.2

    with pytest.raises(ValueError, match="aliases conflict"):
        validate_candidate_table(candidate, table_name="conflicting-aliases")


def test_duplicate_variant_keys_are_rejected() -> None:
    duplicated = pd.concat([valid_candidate(), valid_candidate()], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate variant keys"):
        validate_candidate_table(duplicated, table_name="duplicate-key")


def test_more_than_one_alternate_allele_per_position_is_rejected() -> None:
    first = valid_candidate()
    second = valid_candidate()
    second.loc[0, "alt_base"] = "G"
    second.loc[0, "alt_count"] = 2
    second.loc[0, "alt_allele_fraction"] = 0.2
    second.loc[0, "heteroplasmy_fraction"] = 0.2
    second.loc[0, "alt_forward"] = 1
    second.loc[0, "alt_reverse"] = 1
    second.loc[0, "A"] = 0
    second.loc[0, "C"] = 8
    second.loc[0, "G"] = 2
    combined = pd.concat([first, second], ignore_index=True)

    with pytest.raises(ValueError, match="more than one alternate allele per position"):
        validate_candidate_table(combined, table_name="multi-alt-position")


def test_selected_alternate_must_have_a_largest_nonreference_count() -> None:
    candidate = valid_candidate()
    candidate.loc[0, "alt_count"] = 2
    candidate.loc[0, "alt_allele_fraction"] = 0.2
    candidate.loc[0, "heteroplasmy_fraction"] = 0.2
    candidate.loc[0, "alt_forward"] = 1
    candidate.loc[0, "alt_reverse"] = 1
    candidate.loc[0, "A"] = 2
    candidate.loc[0, "C"] = 5
    candidate.loc[0, "G"] = 3

    with pytest.raises(ValueError, match="largest observed non-reference"):
        validate_candidate_table(candidate, table_name="non-dominant-alternate")
