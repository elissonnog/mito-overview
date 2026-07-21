from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mito_overview.config import detect_reference_scope
from mito_overview.steps.extract_mito_assets import write_mito_region_bed
from mito_overview.steps.mito_numt_qc import run_step

from ._helpers import metric_map


GRCH37_AUTOSOME_LENGTHS = (
    249_250_621,
    243_199_373,
    198_022_430,
    191_154_276,
    180_915_260,
    171_115_067,
    159_138_663,
    146_364_022,
    141_213_431,
    135_534_747,
    135_006_516,
    133_851_895,
    115_169_878,
    107_349_540,
    102_531_392,
    90_354_753,
    81_195_210,
    78_077_248,
    59_128_983,
    63_025_520,
    48_129_895,
    51_304_566,
)
GRCH38_AUTOSOME_LENGTHS = (
    248_956_422,
    242_193_529,
    198_295_559,
    190_214_555,
    181_538_259,
    170_805_979,
    159_345_973,
    145_138_636,
    138_394_717,
    133_797_422,
    135_086_622,
    133_275_309,
    114_364_328,
    107_043_718,
    101_991_189,
    90_338_345,
    83_257_441,
    80_373_285,
    58_617_616,
    64_444_167,
    46_709_983,
    50_818_468,
)
GRCM38_AUTOSOME_LENGTHS = (
    195_471_971,
    182_113_224,
    160_039_680,
    156_508_116,
    151_834_684,
    149_736_546,
    145_441_459,
    129_401_213,
    124_595_110,
    130_694_993,
    122_082_543,
    120_129_022,
    120_421_639,
    124_902_244,
    104_043_685,
    98_207_768,
    94_987_271,
    90_702_639,
    61_431_566,
)
GRCM39_AUTOSOME_LENGTHS = (
    195_154_279,
    181_755_017,
    159_745_316,
    156_860_686,
    151_758_149,
    149_588_044,
    144_995_196,
    130_127_694,
    124_359_700,
    130_530_862,
    121_973_369,
    120_092_757,
    120_883_175,
    125_139_656,
    104_073_951,
    98_008_968,
    95_294_699,
    90_720_763,
    61_420_004,
)
GRCH37_SEX_CHROMOSOME_LENGTHS = (155_270_560, 59_373_566)
GRCH38_SEX_CHROMOSOME_LENGTHS = (156_040_895, 57_227_415)
GRCM38_SEX_CHROMOSOME_LENGTHS = (171_031_299, 91_744_698)
GRCM39_SEX_CHROMOSOME_LENGTHS = (169_476_592, 91_455_967)


def reference_contigs(
    autosome_lengths: tuple[int, ...],
    *,
    prefix: str = "chr",
    mt_contig: str = "MT",
    mt_length: int = 16_569,
    sex_chromosome_lengths: tuple[int, int] = GRCH38_SEX_CHROMOSOME_LENGTHS,
) -> dict[str, int]:
    return {
        mt_contig: mt_length,
        **{f"{prefix}{index}": length for index, length in enumerate(autosome_lengths, 1)},
        f"{prefix}X": sex_chromosome_lengths[0],
        f"{prefix}Y": sex_chromosome_lengths[1],
    }


def test_reference_scope_auto_resolves_mt_only() -> None:
    assert detect_reference_scope(
        requested="auto", contig_lengths={"MT": 16569}, mt_contig="MT", species="human"
    ) == "mt_only"


@pytest.mark.parametrize(
    (
        "species",
        "autosome_lengths",
        "sex_chromosome_lengths",
        "prefix",
        "mt_contig",
        "mt_length",
    ),
    [
        pytest.param(
            "human",
            GRCH37_AUTOSOME_LENGTHS,
            GRCH37_SEX_CHROMOSOME_LENGTHS,
            "",
            "MT",
            16_569,
            id="grch37",
        ),
        pytest.param(
            "human",
            GRCH38_AUTOSOME_LENGTHS,
            GRCH38_SEX_CHROMOSOME_LENGTHS,
            "chr",
            "chrM",
            16_569,
            id="grch38",
        ),
        pytest.param(
            "mouse",
            GRCM38_AUTOSOME_LENGTHS,
            GRCM38_SEX_CHROMOSOME_LENGTHS,
            "chr",
            "chrM",
            16_299,
            id="grcm38",
        ),
        pytest.param(
            "mouse",
            GRCM39_AUTOSOME_LENGTHS,
            GRCM39_SEX_CHROMOSOME_LENGTHS,
            "",
            "MT",
            16_299,
            id="grcm39",
        ),
    ],
)
def test_reference_scope_auto_recognizes_complete_assemblies(
    species: str,
    autosome_lengths: tuple[int, ...],
    sex_chromosome_lengths: tuple[int, int],
    prefix: str,
    mt_contig: str,
    mt_length: int,
) -> None:
    contigs = reference_contigs(
        autosome_lengths,
        prefix=prefix,
        mt_contig=mt_contig,
        mt_length=mt_length,
        sex_chromosome_lengths=sex_chromosome_lengths,
    )
    assert detect_reference_scope(
        requested="auto", contig_lengths=contigs, mt_contig=mt_contig, species=species
    ) == "whole_genome"


@pytest.mark.parametrize(
    ("contigs", "species"),
    [
        pytest.param(
            {"MT": 16_569, **{f"chr{index}": 1_000 for index in range(1, 23)}},
            "human",
            id="toy-autosome-lengths",
        ),
        pytest.param(
            {
                "MT": 16_569,
                **{
                    f"chr{index}": length
                    for index, length in enumerate(GRCH38_AUTOSOME_LENGTHS, 1)
                },
            },
            "human",
            id="autosomes-only",
        ),
        pytest.param(
            {**reference_contigs(GRCH38_AUTOSOME_LENGTHS), "chr12": 1_000_000},
            "human",
            id="truncated-autosome",
        ),
        pytest.param(
            {
                name: length if name == "MT" else length * 99 // 100
                for name, length in reference_contigs(GRCH38_AUTOSOME_LENGTHS).items()
            },
            "human",
            id="uniformly-scaled-profile",
        ),
        pytest.param(
            reference_contigs(
                GRCH38_AUTOSOME_LENGTHS,
                sex_chromosome_lengths=GRCH37_SEX_CHROMOSOME_LENGTHS,
            ),
            "human",
            id="mixed-human-build-profile",
        ),
        pytest.param(
            {**reference_contigs(GRCH38_AUTOSOME_LENGTHS), "chr12": 133_275_310},
            "human",
            id="one-base-modified-autosome",
        ),
        pytest.param(
            reference_contigs(GRCH38_AUTOSOME_LENGTHS, mt_length=16_570),
            "human",
            id="wrong-human-mt-length",
        ),
        pytest.param(
            reference_contigs(
                GRCM39_AUTOSOME_LENGTHS,
                mt_length=16_569,
                sex_chromosome_lengths=GRCM39_SEX_CHROMOSOME_LENGTHS,
            ),
            "mouse",
            id="wrong-mouse-mt-length",
        ),
        pytest.param(
            {
                name: length
                for name, length in reference_contigs(GRCH38_AUTOSOME_LENGTHS).items()
                if name != "chr22"
            },
            "human",
            id="missing-autosome",
        ),
        pytest.param(
            {
                **reference_contigs(GRCH38_AUTOSOME_LENGTHS),
                "chrUn_hybrid": 10_000,
            },
            "human",
            id="extra-hybrid-contig",
        ),
        pytest.param(
            reference_contigs(GRCH38_AUTOSOME_LENGTHS),
            "rat",
            id="unsupported-species",
        ),
    ],
)
def test_reference_scope_auto_rejects_unrecognized_assemblies(
    contigs: dict[str, int], species: str
) -> None:
    assert detect_reference_scope(
        requested="auto", contig_lengths=contigs, mt_contig="MT", species=species
    ) == "custom"


@pytest.mark.parametrize(
    ("contigs", "species"),
    [
        pytest.param({"MT": 16_569}, "human", id="mt-only"),
        pytest.param(
            {"MT": 16_569, **{f"chr{index}": 1_000 for index in range(1, 23)}},
            "human",
            id="toy-autosome-lengths",
        ),
        pytest.param(
            reference_contigs(GRCH38_AUTOSOME_LENGTHS),
            "unknown",
            id="unsupported-species",
        ),
        pytest.param(
            reference_contigs(GRCH38_AUTOSOME_LENGTHS, mt_length=16_570),
            "human",
            id="wrong-mt-length",
        ),
    ],
)
def test_whole_genome_scope_cannot_override_incomplete_reference(
    contigs: dict[str, int], species: str
) -> None:
    with pytest.raises(ValueError, match="requires a recognized complete nuclear reference"):
        detect_reference_scope(
            requested="whole_genome",
            contig_lengths=contigs,
            mt_contig="MT",
            species=species,
        )


def test_mito_bed_is_exact_zero_based_half_open(tmp_path: Path) -> None:
    path = write_mito_region_bed(tmp_path / "mt.bed", "MT", 16569)
    assert path.read_bytes() == b"MT\t0\t16569\n"


def write_numt_inputs(summary_dir: Path) -> None:
    summary_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "read_name": "r1",
                "mapq": 60,
                "query_length": 16000,
                "read_start": 1,
                "read_end": 16000,
                "aligned_span": 16000,
                "aligned_fraction_mt": 0.966,
                "softclip_bases": 0,
                "softclip_fraction": 0.0,
                "has_sa_tag": 0,
                "is_primary": 1,
                "is_supplementary": 0,
                "is_secondary": 0,
                "is_reverse": 0,
            }
        ]
    ).to_csv(summary_dir / "mito_read_stats.tsv", sep="\t", index=False)
    pd.DataFrame([{"metric": "full_length_fraction", "value": 1.0}]).to_csv(
        summary_dir / "mito_qc_summary.tsv", sep="\t", index=False
    )


@pytest.mark.parametrize(
    ("scope", "reason"),
    [("mt_only", "reference_scope_mt_only"), ("custom", "reference_scope_custom")],
)
def test_numt_interpretation_is_suppressed_without_whole_genome_scope(
    scope: str, reason: str, tmp_path: Path
) -> None:
    root = tmp_path / scope
    summary = root / "summary"
    write_numt_inputs(summary)
    outputs = run_step(
        summary_dir=summary,
        figure_dir=root / "figures",
        report_dir=root / "reports",
        sample_id="S1",
        mt_contig="MT",
        mt_length=16569,
        reference_scope=scope,
    )
    metrics = metric_map(outputs["summary_path"])
    assert metrics["numt_interpretation_status"] == "not_evaluable"
    assert metrics["reason_code"] == reason
    assert metrics["heuristic_numt_risk"] == "not_evaluable"
    assert metrics["heuristic_numt_risk_score"] == "NA"
    assert metrics["reads_evaluated"] == "1"


def test_whole_genome_scope_permits_bounded_warning_calculation(tmp_path: Path) -> None:
    summary = tmp_path / "summary"
    write_numt_inputs(summary)
    outputs = run_step(
        summary_dir=summary,
        figure_dir=tmp_path / "figures",
        report_dir=tmp_path / "reports",
        sample_id="S1",
        mt_contig="MT",
        mt_length=16569,
        reference_scope="whole_genome",
    )
    metrics = metric_map(outputs["summary_path"])
    assert metrics["numt_interpretation_status"] == "ok"
    assert metrics["heuristic_numt_risk"] in {"low", "moderate", "high"}
    assert "formal NUMT classifier" in outputs["report_path"].read_text(encoding="utf-8")
