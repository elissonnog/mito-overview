from __future__ import annotations

import pandas as pd
import pysam
import pytest

from mito_overview.steps.mito_circularity_qc import (
    build_arg_parser as circularity_parser,
)
from mito_overview.steps.mito_cosegregation import build_arg_parser as cosegregation_parser
from mito_overview.steps.mito_identity_qc import build_arg_parser as identity_parser
from mito_overview.steps.mito_mvtool_annotation import build_arg_parser as mvtool_parser
from mito_overview.table_contracts import (
    MODULE_STATES,
    ensure_alt_fraction_columns,
    load_reference_sequence,
    load_metric_module_state,
    validate_module_state,
)


def test_legacy_fraction_is_promoted_without_dropping_alias() -> None:
    table = ensure_alt_fraction_columns(pd.DataFrame({"heteroplasmy_fraction": [0.25]}))
    assert table.loc[0, "alt_allele_fraction"] == pytest.approx(0.25)
    assert table.loc[0, "heteroplasmy_fraction"] == pytest.approx(0.25)


def test_conflicting_fraction_columns_fail() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        ensure_alt_fraction_columns(
            pd.DataFrame(
                {
                    "alt_allele_fraction": [0.25],
                    "heteroplasmy_fraction": [0.30],
                }
            )
        )


def test_module_state_vocabulary_is_closed() -> None:
    assert MODULE_STATES == {
        "ok",
        "not_configured",
        "not_applicable",
        "not_evaluable",
        "unavailable",
        "failed",
    }
    for state in MODULE_STATES:
        assert validate_module_state(state) == state
    with pytest.raises(ValueError, match="Unsupported module state"):
        validate_module_state("pending")


def test_metric_module_state_fails_closed_when_summary_is_missing(tmp_path) -> None:
    assert load_metric_module_state(
        tmp_path / "missing.tsv",
        module_name="heteroplasmy",
    ) == ("not_evaluable", "heteroplasmy_summary_missing")


def test_metric_module_state_preserves_explicit_status_and_reason(tmp_path) -> None:
    path = tmp_path / "summary.tsv"
    pd.DataFrame(
        [
            {"metric": "status", "value": "failed"},
            {"metric": "reason_code", "value": "upstream_failed"},
        ]
    ).to_csv(path, sep="\t", index=False)

    assert load_metric_module_state(path, module_name="heteroplasmy") == (
        "failed",
        "upstream_failed",
    )


def test_reference_loader_enforces_indexed_contig_length(tmp_path) -> None:
    fasta = tmp_path / "reference.fa"
    fasta.write_text(">MT\nACGT\n", encoding="ascii")
    pysam.faidx(str(fasta))

    assert load_reference_sequence(fasta, "MT", 4) == "ACGT"
    with pytest.raises(ValueError, match="length"):
        load_reference_sequence(fasta, "MT", 5)


@pytest.mark.parametrize(
    "parser_factory",
    [cosegregation_parser, circularity_parser, identity_parser, mvtool_parser],
)
def test_reference_aware_step_cli_requires_reference_contract(parser_factory) -> None:
    parser = parser_factory()
    required = {
        action.dest
        for action in parser._actions
        if getattr(action, "required", False)
    }
    assert {"mt_length", "ref_fasta"}.issubset(required)
