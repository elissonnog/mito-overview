from __future__ import annotations

import gzip
import re
from pathlib import Path

import pytest

from mito_overview.steps.extract_mito_assets import subset_bedmethyl
from mito_overview.steps.mito_methylation_exploratory import load_bedmethyl_table


MT_ROW = "MT\t0\t1\tm\t0\t+\t0\t1\t0,0,0\t10\t30\t3\t7\t0\t0\t0\t0\t0\n"
NUCLEAR_ROW = "chr1\t0\t1\tm\t0\t+\t0\t1\t0,0,0\t10\t20\t2\t8\t0\t0\t0\t0\t0\n"


def write_gzip(path: Path, content: str) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(content)


@pytest.mark.parametrize(
    ("filename", "compressed"),
    [
        ("explicit.bedmethyl", False),
        ("explicit.bedmethyl.gz", True),
        ("gzip-without-gz-suffix.bedmethyl", True),
        ("plain-with-gz-suffix.bedmethyl.gz", False),
    ],
)
def test_subset_bedmethyl_detects_compression_from_magic(
    tmp_path: Path,
    filename: str,
    compressed: bool,
) -> None:
    source = tmp_path / filename
    content = "# source metadata\n\n" + NUCLEAR_ROW + MT_ROW
    if compressed:
        write_gzip(source, content)
    else:
        source.write_text(content, encoding="utf-8")
    destination = tmp_path / "mitochondrial.bedmethyl"

    written = subset_bedmethyl(source_gz=source, destination=destination, contig="MT")

    assert written == 1
    assert destination.read_text(encoding="utf-8") == MT_ROW


def test_subset_bedmethyl_retains_legacy_gz_to_plain_fallback(tmp_path: Path) -> None:
    configured = tmp_path / "legacy.bedmethyl.gz"
    plain_fallback = tmp_path / "legacy.bedmethyl"
    plain_fallback.write_text(MT_ROW, encoding="utf-8")
    destination = tmp_path / "mitochondrial.bedmethyl"

    written = subset_bedmethyl(source_gz=configured, destination=destination, contig="MT")

    assert written == 1
    assert destination.read_text(encoding="utf-8") == MT_ROW


def test_load_bedmethyl_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    source = tmp_path / "comments-and-blanks.bedmethyl"
    source.write_text("# header\n\n   # indented comment\n\t  \n" + MT_ROW, encoding="utf-8")

    observed = load_bedmethyl_table(source, "NP_real_all_reads")

    assert len(observed) == 1
    assert observed.iloc[0]["position"] == 1
    assert observed.iloc[0]["modified_count"] == 3.0


def test_load_bedmethyl_rejects_short_data_row_with_source_and_line(tmp_path: Path) -> None:
    source = tmp_path / "short-row.bedmethyl"
    source.write_text("# header\n\nMT\t0\t1\tm\n", encoding="utf-8")

    expected = rf"{re.escape(str(source))} at line 3: expected at least 13"
    with pytest.raises(ValueError, match=expected):
        load_bedmethyl_table(source, "NP_real_all_reads")


def test_load_bedmethyl_rejects_nonnumeric_data_with_source_and_line(tmp_path: Path) -> None:
    source = tmp_path / "nonnumeric-row.bedmethyl"
    malformed = MT_ROW.replace("\t30\t3\t7\t", "\tnot-a-number\t3\t7\t")
    source.write_text("# header\n" + malformed, encoding="utf-8")

    expected = rf"bedMethyl source {re.escape(str(source))} at line 2"
    with pytest.raises(ValueError, match=expected):
        load_bedmethyl_table(source, "NP_real_all_reads")


@pytest.mark.parametrize("value", ("nan", "inf", "-inf"))
@pytest.mark.parametrize(
    ("column_index", "field"),
    (
        (9, "valid_coverage"),
        (10, "percent_modified"),
        (11, "modified_count"),
        (12, "canonical_count"),
        (13, "other_modified_count"),
    ),
)
def test_load_bedmethyl_rejects_nonfinite_numeric_fields(
    tmp_path: Path,
    column_index: int,
    field: str,
    value: str,
) -> None:
    source = tmp_path / f"nonfinite-{field}-{value}.bedmethyl"
    fields = MT_ROW.rstrip("\n").split("\t")
    fields[column_index] = value
    source.write_text("\t".join(fields) + "\n", encoding="utf-8")

    expected = rf"bedMethyl source {re.escape(str(source))} at line 1: {field}"
    with pytest.raises(ValueError, match=expected):
        load_bedmethyl_table(source, "NP_real_all_reads")


@pytest.mark.parametrize("column_index", [9, 11, 12, 13])
def test_load_bedmethyl_rejects_fractional_count_fields(
    tmp_path: Path,
    column_index: int,
) -> None:
    source = tmp_path / f"fractional-count-{column_index}.bedmethyl"
    fields = MT_ROW.rstrip("\n").split("\t")
    fields[column_index] = "1.5"
    source.write_text("\t".join(fields) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="integer-valued counts"):
        load_bedmethyl_table(source, "NP_real_all_reads")
