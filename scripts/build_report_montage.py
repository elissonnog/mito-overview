#!/usr/bin/env python3
"""Build a manuscript/README montage from report-native figure panels."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


LONGREAD_PANELS = [
    ("A", "Alternate-allele landscape", "mito_heteroplasmy_landscape.png", 70),
    ("B", "Co-segregation heatmap", "mito_cosegregation_heatmap.png", 70),
    ("C", "Gene-level summary", "mito_gene_summary_overview.png", 20),
    ("D", "Alignment-ambiguity QC", "mito_numt_qc_mapq_vs_span.png", 70),
]

SHORTREAD_PANELS = [
    ("A", "Alternate-allele landscape", "mito_heteroplasmy_landscape.png", 70),
    ("B", "Mitochondrial feature context", "mito_feature_annotation.png", 70),
    ("C", "Feature-level burden summary", "mito_gene_summary_overview.png", 20),
    ("D", "Candidate consequence classes", "mito_variant_consequence_classes.png", 70),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, help="Directory containing report figure PNGs.")
    parser.add_argument("--output", required=True, help="Output PNG path for the montage.")
    parser.add_argument(
        "--profile",
        choices=("long", "short"),
        default="long",
        help="Report panel set to assemble.",
    )
    parser.add_argument(
        "--title",
        default="Representative long-read report-native analytical views",
        help="Overall montage title.",
    )
    return parser.parse_args()


def load_font(size: int) -> ImageFont.ImageFont:
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in font_candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def crop_title_band(image: Image.Image, crop_top: int) -> Image.Image:
    width, height = image.size
    crop_top = max(0, min(crop_top, height - 1))
    return image.crop((0, crop_top, width, height))


def scale_to_box(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    image = image.copy()
    image.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), "white")
    x = (target_w - image.width) // 2
    y = (target_h - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    title_font = load_font(34)
    label_font = load_font(26)
    panel_w = 820
    panel_h = 560
    outer_pad = 50
    gutter_x = 35
    gutter_y = 55
    title_h = 90
    caption_band_h = 46

    width = outer_pad * 2 + panel_w * 2 + gutter_x
    height = outer_pad * 2 + title_h + (panel_h + caption_band_h) * 2 + gutter_y
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)

    title_text = args.title
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_x = (width - (title_bbox[2] - title_bbox[0])) // 2
    draw.text((title_x, outer_pad // 2), title_text, fill="black", font=title_font)

    panels = LONGREAD_PANELS if args.profile == "long" else SHORTREAD_PANELS
    for idx, (panel_id, caption, filename, crop_top) in enumerate(panels):
        src = source_dir / filename
        if not src.exists():
            raise FileNotFoundError(f"Missing required panel: {src}")
        image = Image.open(src).convert("RGB")
        image = crop_title_band(image, crop_top)
        image = scale_to_box(image, panel_w, panel_h)

        row = idx // 2
        col = idx % 2
        x = outer_pad + col * (panel_w + gutter_x)
        y = outer_pad + title_h + row * (panel_h + caption_band_h + gutter_y)
        canvas.paste(image, (x, y))

        label_text = f"{panel_id}. {caption}"
        draw.text((x, y + panel_h + 8), label_text, fill="black", font=label_font)

    canvas.save(output)


if __name__ == "__main__":
    main()
