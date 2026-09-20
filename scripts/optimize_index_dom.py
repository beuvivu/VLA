#!/usr/bin/env python3
"""Flatten matrix cell DOM on docs/index.html (and landing*.html if present).

Before: <button class=matrix-cell><span class=cell-number>00</span><span class=cell-value>1</span></button>
After:  <button class=matrix-cell data-value=1>00</button>  (+ CSS ::after)

Saves ~2000 DOM nodes and ~50KB HTML without changing data-number click behavior.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "docs" / "index.html",
    ROOT / "docs" / "landing.html",
    ROOT / "docs" / "landing_desktop.html",
]

DOM_CSS = """
/* DOM perf: flat matrix cells + content-visibility */
.tiny-matrix-cell, .matrix-cell { font-weight:950; letter-spacing:-.02em; line-height:1.15; }
.tiny-matrix-cell::after, .matrix-cell::after {
  content: attr(data-value); display:block; font-size:10px; opacity:.88; font-weight:750;
  letter-spacing:0; line-height:1.2; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
article.card, section.section.card {
  content-visibility: auto;
  contain-intrinsic-size: auto 280px;
}
#tong-quan, #live, #ket-qua { content-visibility: visible; contain-intrinsic-size: auto; }
"""


def flatten_matrix_cell(m: re.Match[str]) -> str:
    open_tag, number, value = m.group(1), m.group(2), m.group(3)
    if "data-value=" not in open_tag:
        open_tag = open_tag[:-1] + f' data-value="{value}">'
    return f"{open_tag}{number}</button>"


def flatten_tiny(m: re.Match[str]) -> str:
    open_tag, number, value = m.group(1), m.group(2), m.group(3)
    if "data-value=" not in open_tag:
        open_tag = open_tag[:-1] + f' data-value="{value}">'
    return f"{open_tag}{number}</button>"


def optimize(html: str) -> tuple[str, dict[str, int]]:
    stats = {"matrix_cell": 0, "tiny_matrix": 0, "css": 0}
    html, n1 = re.subn(
        r'(<button\b[^>]*\bclass="[^"]*matrix-cell[^"]*"[^>]*>)\s*'
        r'<span class="cell-number">([^<]*)</span>\s*'
        r'<span class="cell-value">([^<]*)</span>\s*</button>',
        flatten_matrix_cell,
        html,
        flags=re.I,
    )
    stats["matrix_cell"] = n1
    html, n2 = re.subn(
        r'(<button\b[^>]*\bclass="[^"]*tiny-matrix-cell[^"]*"[^>]*>)\s*'
        r'<b>([^<]*)</b>\s*<span>([^<]*)</span>\s*</button>',
        flatten_tiny,
        html,
        flags=re.I,
    )
    stats["tiny_matrix"] = n2
    if "content: attr(data-value)" not in html:
        if "</style>" in html:
            html = html.replace("</style>", DOM_CSS + "\n</style>", 1)
        else:
            html = html.replace(
                "</head>",
                f'<style id="dom-perf">{DOM_CSS}</style>\n</head>',
                1,
            )
        stats["css"] = 1
    return html, stats


def main() -> None:
    changed = 0
    for path in TARGETS:
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        updated, stats = optimize(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(
                f"optimized {path.name}: "
                f"matrix_cell={stats['matrix_cell']} tiny={stats['tiny_matrix']} "
                f"bytes {len(original)}->{len(updated)} ({len(original)-len(updated)} saved)"
            )
        else:
            print(f"unchanged {path.name}")
    print(f"done: {changed} files")


if __name__ == "__main__":
    main()
