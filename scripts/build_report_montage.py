#!/usr/bin/env python3
"""Build a manuscript/README montage from report-native figure panels."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont


LONGREAD_PANELS = [
    ("A", "Alternate-allele landscape", "mito_heteroplasmy_landscape.png", 70),
    ("B", "Co-segregation heatmap", "mito_cosegregation_heatmap.png", 115),
    ("C", "Gene-level summary", "mito_gene_summary_overview.png", 55),
    ("D", "Alignment-ambiguity QC", "mito_numt_qc_mapq_vs_span.png", 70),
]

SHORTREAD_PANELS = [
    ("A", "Alternate-allele landscape", "mito_heteroplasmy_landscape.png", 70),
    ("B", "Mitochondrial feature context", "mito_feature_annotation.png", 70),
    ("C", "Feature-level burden summary", "mito_gene_summary_overview.png", 55),
    ("D", "Candidate consequence classes", "mito_variant_consequence_classes.png", 70),
]

CANVAS_WIDTH = 1800
OUTER_PAD = 56
PANEL_WIDTH = 820
PANEL_HEIGHT = 520
PANEL_GUTTER_X = 48
PANEL_GUTTER_Y = 48
TITLE_HEIGHT = 82
CAPTION_HEIGHT = 50
CANVAS_HEIGHT = (
    OUTER_PAD * 2
    + TITLE_HEIGHT
    + 2 * (CAPTION_HEIGHT + PANEL_HEIGHT)
    + PANEL_GUTTER_Y
)


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


def trim_white_margin(image: Image.Image, padding: int = 16) -> Image.Image:
    """Remove unused exterior whitespace while retaining a protective margin."""
    white = Image.new("RGB", image.size, "white")
    bbox = ImageChops.difference(image.convert("RGB"), white).getbbox()
    if bbox is None:
        return image
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(image.width, bbox[2] + padding)
    bottom = min(image.height, bbox[3] + padding)
    return image.crop((left, top, right, bottom))


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
    label_font = load_font(25)
    panel_id_font = load_font(28)

    canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), "white")
    draw = ImageDraw.Draw(canvas)

    title_text = args.title
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_x = (CANVAS_WIDTH - (title_bbox[2] - title_bbox[0])) // 2
    draw.text((title_x, OUTER_PAD // 2), title_text, fill="#17212b", font=title_font)

    panels = LONGREAD_PANELS if args.profile == "long" else SHORTREAD_PANELS
    for idx, (panel_id, caption, filename, crop_top) in enumerate(panels):
        src = source_dir / filename
        if not src.exists():
            raise FileNotFoundError(f"Missing required panel: {src}")
        image = Image.open(src).convert("RGB")
        image = crop_title_band(image, crop_top)
        image = trim_white_margin(image)
        image = scale_to_box(image, PANEL_WIDTH, PANEL_HEIGHT)

        row = idx // 2
        col = idx % 2
        x = OUTER_PAD + col * (PANEL_WIDTH + PANEL_GUTTER_X)
        card_y = OUTER_PAD + TITLE_HEIGHT + row * (
            CAPTION_HEIGHT + PANEL_HEIGHT + PANEL_GUTTER_Y
        )
        image_y = card_y + CAPTION_HEIGHT

        draw.text((x, card_y + 5), panel_id, fill="#0f766e", font=panel_id_font)
        panel_id_bbox = draw.textbbox((x, card_y + 5), panel_id, font=panel_id_font)
        draw.text(
            (panel_id_bbox[2] + 12, card_y + 8),
            caption,
            fill="#17212b",
            font=label_font,
        )
        canvas.paste(image, (x, image_y))
        draw.rectangle(
            (x, image_y, x + PANEL_WIDTH - 1, image_y + PANEL_HEIGHT - 1),
            outline="#cbd5e1",
            width=1,
        )

    canvas.save(output)


if __name__ == "__main__":
    main()
