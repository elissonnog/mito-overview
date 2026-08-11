#!/usr/bin/env python3
"""Build the lead report-native public ONT example figure."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mito_overview.steps.mito_cosegregation import (
    CANONICAL_JACCARD_COLUMN,
    CONDITIONAL_UNIVERSE,
    LEGACY_JACCARD_COLUMN,
    _write_heatmap,
)


FIGURE_DIR = ROOT / "docs" / "assets"
SOURCE_DIR = ROOT / "examples" / "public_validation" / "GM12878_ONT_longread" / "figures"
SUMMARY_DIR = SOURCE_DIR.parent / "summary"
OUT_PNG = FIGURE_DIR / "mito_overview_report_native_views.png"
OUT_SVG = FIGURE_DIR / "mito_overview_report_native_views.svg"

TEXT = "#17212b"
MUTED = "#536276"
FRAME = "#cfd9e5"
CARD = "#f8fafc"

PANELS = [
    ("A", "Mitochondrial depth profile", "mito_depth_profile.png"),
    ("B", "Alternate-allele fraction landscape", "mito_heteroplasmy_landscape.png"),
    ("C", "Conditional alt-read co-occurrence", "mito_cosegregation_heatmap.png"),
    ("D", "Alignment-ambiguity QC: span versus MAPQ", "mito_numt_qc_mapq_vs_span.png"),
]


def rebuild_conditional_cosegregation_panel() -> None:
    selected = pd.read_csv(SUMMARY_DIR / "mito_cosegregation_selected_sites.tsv", sep="\t")
    pairwise = pd.read_csv(SUMMARY_DIR / "mito_cosegregation_pairwise.tsv", sep="\t")
    required = {
        "site_i",
        "site_j",
        "conditional_universe",
        CANONICAL_JACCARD_COLUMN,
        LEGACY_JACCARD_COLUMN,
    }
    if selected.empty or pairwise.empty or not required.issubset(pairwise.columns):
        raise ValueError("Public co-occurrence tables do not satisfy the v0.3.0 figure contract")
    if set(pairwise["conditional_universe"].astype(str)) != {CONDITIONAL_UNIVERSE}:
        raise ValueError("Public co-occurrence table has an unexpected conditional universe")
    if not np.allclose(
        pairwise[CANONICAL_JACCARD_COLUMN].astype(float),
        pairwise[LEGACY_JACCARD_COLUMN].astype(float),
    ):
        raise ValueError("Public co-occurrence compatibility alias differs from the canonical field")

    labels = selected["site_label"].astype(str).tolist()
    heatmap = pd.DataFrame(np.nan, index=labels, columns=labels, dtype=float)
    for label in labels:
        heatmap.loc[label, label] = 1.0
    for row in pairwise.itertuples(index=False):
        value = float(getattr(row, CANONICAL_JACCARD_COLUMN))
        heatmap.loc[str(row.site_i), str(row.site_j)] = value
        heatmap.loc[str(row.site_j), str(row.site_i)] = value
    _write_heatmap(SOURCE_DIR, "GM12878 ONT qn1000", heatmap)


def add_panel(fig, rect: tuple[float, float, float, float], panel_id: str, title: str, filename: str) -> None:
    x, y, w, h = rect
    path = SOURCE_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing required panel image: {path}")

    fig.text(
        x,
        y + h + 0.018,
        f"{panel_id}. {title}",
        ha="left",
        va="bottom",
        fontsize=13.2,
        fontweight="bold",
        color=TEXT,
    )
    card = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.004,rounding_size=0.006",
        transform=fig.transFigure,
        linewidth=1.1,
        edgecolor=FRAME,
        facecolor="white",
        zorder=1,
    )
    fig.patches.append(card)

    ax = fig.add_axes((x + 0.015, y + 0.018, w - 0.030, h - 0.036), zorder=2)
    ax.imshow(mpimg.imread(path))
    ax.axis("off")


def build_figure() -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    rebuild_conditional_cosegregation_panel()
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "svg.fonttype": "none",
            "svg.hashsalt": "mito-overview",
        }
    )

    fig = plt.figure(figsize=(15.5, 10.0), dpi=200, facecolor="white")
    title = "Public ONT long-read report-native views"
    subtitle = (
        "Representative GM12878 targeted-mt output from the deterministic 1,000-query-name subset; "
        "shown as workflow evidence, not an analytical performance benchmark."
    )
    fig.text(0.045, 0.955, title, ha="left", va="top", fontsize=20, fontweight="bold", color=TEXT)
    fig.text(0.045, 0.918, subtitle, ha="left", va="top", fontsize=10.5, color=MUTED)

    # Subtle title-band background keeps the montage readable in GitHub previews.
    band = FancyBboxPatch(
        (0.035, 0.870),
        0.930,
        0.105,
        boxstyle="round,pad=0.008,rounding_size=0.010",
        transform=fig.transFigure,
        linewidth=0,
        facecolor=CARD,
        zorder=0,
    )
    fig.patches.append(band)

    rects = [
        (0.055, 0.525, 0.415, 0.280),
        (0.535, 0.525, 0.415, 0.280),
        (0.095, 0.115, 0.345, 0.315),
        (0.570, 0.115, 0.345, 0.315),
    ]
    if len(rects) != len(PANELS):
        raise ValueError("Panel definitions and layout rectangles must have equal lengths")
    for rect, panel in zip(rects, PANELS):
        add_panel(fig, rect, *panel)

    fig.text(
        0.055,
        0.045,
        "Figure scope: deterministic reduced public proof of principle. Candidate sites are not independently validated variants; alignment-ambiguity QC is not formal NUMT classification.",
        ha="left",
        va="bottom",
        fontsize=9.2,
        color=MUTED,
    )

    fig.savefig(OUT_PNG, dpi=200, facecolor="white")
    fig.savefig(
        OUT_SVG,
        facecolor="white",
        metadata={"Date": None, "Creator": "mito-overview"},
    )
    plt.close(fig)

    # Matplotlib emits trailing spaces in SVG path data; normalize the tracked
    # artifact so regeneration remains compatible with `git diff --check`.
    svg_text = OUT_SVG.read_text(encoding="utf-8")
    OUT_SVG.write_text(
        "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    build_figure()
