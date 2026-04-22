#!/usr/bin/env python3
"""Export a markdown document to a simple .docx with images, code blocks, and tables."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt


IMAGE_RE = re.compile(r"!\[(?P<alt>.*?)\]\((?P<path>.*?)\)")
LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>[^)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*(.*?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")


def normalize_inline(text: str) -> str:
    text = LINK_RE.sub(lambda m: f"{m.group('label')} ({m.group('url')})", text)
    text = CODE_RE.sub(lambda m: m.group(1), text)
    text = BOLD_RE.sub(lambda m: m.group(1), text)
    text = ITALIC_RE.sub(lambda m: m.group(1), text)
    return text.strip()


def flush_paragraph(document: Document, buffer: list[str]) -> None:
    if not buffer:
        return
    paragraph = document.add_paragraph(normalize_inline(" ".join(buffer)))
    paragraph.style = document.styles["Normal"]
    buffer.clear()


def add_image(document: Document, source_dir: Path, image_path: str) -> None:
    path = (source_dir / image_path).resolve()
    if not path.exists():
        paragraph = document.add_paragraph(f"[Missing figure: {image_path}]")
        paragraph.italic = True
        return
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(str(path), width=Inches(6.2))


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def add_table(document: Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    table = document.add_table(rows=len(padded), cols=width)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_idx, row in enumerate(padded):
        for c_idx, value in enumerate(row):
            cell = table.cell(r_idx, c_idx)
            cell.text = normalize_inline(value)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.name = "Times New Roman"
                    run.font.size = Pt(10)
                    if r_idx == 0:
                        run.bold = True
            if r_idx == 0:
                set_cell_shading(cell, "D9E2F3")
    document.add_paragraph("")


def parse_table_block(lines: list[str]) -> list[list[str]]:
    parsed: list[list[str]] = []
    for idx, line in enumerate(lines):
        if idx == 1 and TABLE_SEPARATOR_RE.match(line.strip()):
            continue
        stripped = line.strip().strip("|")
        cells = [cell.strip() for cell in stripped.split("|")]
        parsed.append(cells)
    return parsed


def add_code_block(document: Document, lines: list[str]) -> None:
    for line in lines:
        paragraph = document.add_paragraph()
        paragraph.style = document.styles["Normal"]
        run = paragraph.add_run(line.rstrip("\n"))
        run.font.name = "Courier New"
        run.font.size = Pt(9)
    document.add_paragraph("")


def build_doc(source_path: Path, output_path: Path) -> None:
    document = Document()

    section = document.sections[0]
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)

    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)

    for style_name in ("Heading 1", "Heading 2", "Heading 3"):
        style = document.styles[style_name]
        style.font.name = "Times New Roman"

    lines = source_path.read_text(encoding="utf-8").splitlines()
    paragraph_buffer: list[str] = []
    table_buffer: list[str] = []
    code_buffer: list[str] = []
    in_code_block = False

    def flush_table() -> None:
        nonlocal table_buffer
        if not table_buffer:
            return
        add_table(document, parse_table_block(table_buffer))
        table_buffer = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if in_code_block:
            if stripped.startswith("```"):
                add_code_block(document, code_buffer)
                code_buffer = []
                in_code_block = False
            else:
                code_buffer.append(line)
            continue

        if stripped.startswith("```"):
            flush_paragraph(document, paragraph_buffer)
            flush_table()
            in_code_block = True
            continue

        is_table_line = "|" in stripped and not stripped.startswith("![") and not stripped.startswith("[")
        if table_buffer and (is_table_line or TABLE_SEPARATOR_RE.match(stripped)):
            table_buffer.append(line)
            continue
        if table_buffer and not is_table_line and not TABLE_SEPARATOR_RE.match(stripped):
            flush_table()

        if is_table_line and "|" in stripped:
            flush_paragraph(document, paragraph_buffer)
            table_buffer.append(line)
            continue

        if not stripped:
            flush_paragraph(document, paragraph_buffer)
            flush_table()
            continue

        image_match = IMAGE_RE.fullmatch(stripped)
        if image_match:
            flush_paragraph(document, paragraph_buffer)
            flush_table()
            add_image(document, source_path.parent, image_match.group("path"))
            continue

        if stripped.startswith("# "):
            flush_paragraph(document, paragraph_buffer)
            flush_table()
            title = normalize_inline(stripped[2:])
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = paragraph.add_run(title)
            run.bold = True
            run.font.name = "Times New Roman"
            run.font.size = Pt(16)
            continue

        if stripped.startswith("## "):
            flush_paragraph(document, paragraph_buffer)
            flush_table()
            document.add_heading(normalize_inline(stripped[3:]), level=1)
            continue

        if stripped.startswith("### "):
            flush_paragraph(document, paragraph_buffer)
            flush_table()
            document.add_heading(normalize_inline(stripped[4:]), level=2)
            continue

        if stripped.startswith("#### "):
            flush_paragraph(document, paragraph_buffer)
            flush_table()
            document.add_heading(normalize_inline(stripped[5:]), level=3)
            continue

        if stripped.startswith("- "):
            flush_paragraph(document, paragraph_buffer)
            flush_table()
            paragraph = document.add_paragraph(normalize_inline(stripped[2:]), style="List Bullet")
            for run in paragraph.runs:
                run.font.name = "Times New Roman"
            continue

        if re.match(r"^\d+\.\s", stripped):
            flush_paragraph(document, paragraph_buffer)
            flush_table()
            paragraph = document.add_paragraph(normalize_inline(stripped), style="List Number")
            for run in paragraph.runs:
                run.font.name = "Times New Roman"
            continue

        paragraph_buffer.append(stripped)

    flush_paragraph(document, paragraph_buffer)
    flush_table()
    if code_buffer:
        add_code_block(document, code_buffer)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: export_markdown_docx.py SOURCE.md [OUTPUT.docx]", file=sys.stderr)
        return 1
    source = Path(argv[1]).resolve()
    if len(argv) > 2:
        output = Path(argv[2]).resolve()
    else:
        output = source.with_suffix(".docx")
    build_doc(source, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
