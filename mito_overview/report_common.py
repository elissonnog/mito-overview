"""Portable reporting helpers for public mito-overview pages."""

from __future__ import annotations

import base64
import html
from pathlib import Path

PAGE_STYLE = """
body { font-family: Arial, sans-serif; margin: 24px; color: #1f2937; background: #f8fafc; }
header { margin-bottom: 20px; }
h1 { margin: 0 0 8px 0; font-size: 30px; }
h2 { margin: 0 0 10px 0; font-size: 24px; }
h3 { margin: 0 0 8px 0; font-size: 18px; }
code { background: #e5e7eb; padding: 2px 6px; border-radius: 4px; }
section { background: white; border: 1px solid #d1d5db; border-radius: 10px; padding: 18px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
.muted { color: #4b5563; }
.metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 14px 0; }
.metric-card { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }
.metric-label { color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
.metric-value { font-size: 24px; font-weight: 700; margin-top: 4px; }
.figure-block { margin: 16px 0; }
.figure-block img { max-width: 100%; border: 1px solid #d1d5db; border-radius: 8px; background: white; }
figcaption { font-weight: 600; margin-bottom: 8px; }
.figure-grid { display: grid; grid-template-columns: 1fr; gap: 18px; }
.table-wrap { overflow-x: auto; margin-top: 10px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; }
th { background: #eff6ff; }
.small-note { font-size: 12px; color: #6b7280; margin-top: 8px; }
ul { margin-top: 10px; }
.page-footer { margin-top: 24px; padding-top: 12px; border-top: 1px solid #d1d5db; color: #6b7280; font-size: 16px; font-weight: 600; text-align: right; }
"""


def image_to_data_uri(path: str | Path) -> str:
    """Encode a figure as a base64 PNG data URI for self-contained reports."""

    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def figure_html(path: str | Path, caption: str | None = None) -> str:
    """Render a report figure block with embedded image data."""

    path = Path(path)
    label = html.escape(caption or path.name)
    return (
        "<figure class='figure-block'>"
        f"<figcaption>{label}</figcaption>"
        f"<img alt='{label}' src='{image_to_data_uri(path)}' />"
        "</figure>"
    )


def df_to_html_table(df, max_rows: int = 25) -> str:
    """Render a pandas DataFrame as a scrollable HTML table."""

    if df is None or df.empty:
        return "<p class='muted'>No rows available.</p>"
    shown = df.head(max_rows).copy()
    columns = list(shown.columns)
    thead = "".join(f"<th>{html.escape(str(col))}</th>" for col in columns)
    rows = []
    for _, row in shown.iterrows():
        cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in row.tolist())
        rows.append(f"<tr>{cells}</tr>")
    note = ""
    if len(df) > max_rows:
        note = f"<p class='small-note'>Showing first {max_rows} of {len(df)} rows.</p>"
    return (
        "<div class='table-wrap'>"
        f"<table><thead><tr>{thead}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        "</div>"
        f"{note}"
    )


def metric_card(label: str, value) -> str:
    """Render a single metric card for report intros."""

    return (
        "<div class='metric-card'>"
        f"<div class='metric-label'>{html.escape(str(label))}</div>"
        f"<div class='metric-value'>{html.escape(str(value))}</div>"
        "</div>"
    )


def render_page(
    output_path: str | Path,
    title: str,
    sample_id: str,
    region: str,
    intro_html: str,
    body_html: str,
) -> None:
    """Write a self-contained HTML report page with a standard footer."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8' />
  <title>{html.escape(title)}</title>
  <style>{PAGE_STYLE}</style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <p class='muted'><strong>Sample:</strong> {html.escape(sample_id)} | <strong>Region:</strong> <code>{html.escape(region)}</code></p>
  </header>
  <section>
    {intro_html}
  </section>
  {body_html}
  <footer class='page-footer'><p>Author: Elisson Lopes, PhD</p></footer>
</body>
</html>
"""
    output_path.write_text(doc, encoding="utf-8")
