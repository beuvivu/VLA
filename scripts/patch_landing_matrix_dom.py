#!/usr/bin/env python3
"""Patch src/build_landing_page.py to emit flat matrix cells (idempotent)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "build_landing_page.py"

OLD_TINY = '''            row_cells.append(
                f"<button class='tiny-matrix-cell{active}' data-mode='loto' data-number='{n}' "
                f"style='background:{bg};color:{fg}' title='{n}: {label}'>"
                f"<b>{n}</b><span>{label}</span></button>"
            )'''

NEW_TINY = '''            row_cells.append(
                f"<button class='tiny-matrix-cell{active}' data-mode='loto' data-number='{n}' "
                f"data-value='{html.escape(str(label))}' "
                f"style='background:{bg};color:{fg}' title='{n}: {label}'>{n}</button>"
            )'''

OLD_MATRIX = '''            row.append(
                f"<button class='matrix-cell' data-mode='{mode}' data-number='{n}' "
                f"style='background:{bg};color:{fg}' title='{html.escape(title)} · {n}: {html.escape(val_label)}'>"
                f"<span class='cell-number'>{n}</span><span class='cell-value'>{html.escape(val_label)}</span></button>"
            )'''

NEW_MATRIX = '''            row.append(
                f"<button class='matrix-cell' data-mode='{mode}' data-number='{n}' "
                f"data-value='{html.escape(val_label)}' "
                f"style='background:{bg};color:{fg}' title='{html.escape(title)} · {n}: {html.escape(val_label)}'>"
                f"{n}</button>"
            )'''

OLD_CSS = '''    .tiny-matrix-cell b, .cell-number {
      font-weight: 950;
      letter-spacing: -.02em;
    }
    .tiny-matrix-cell span, .cell-value {
      font-size: 10px;
      opacity: .88;
      font-weight: 750;
    }'''

NEW_CSS = '''    .tiny-matrix-cell, .matrix-cell {
      font-weight: 950;
      letter-spacing: -.02em;
      line-height: 1.15;
    }
    .tiny-matrix-cell::after, .matrix-cell::after {
      content: attr(data-value);
      display: block;
      font-size: 10px;
      opacity: .88;
      font-weight: 750;
      letter-spacing: 0;
      line-height: 1.2;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    article.card, section.section.card {
      content-visibility: auto;
      contain-intrinsic-size: auto 280px;
    }
    #tong-quan, #live, #ket-qua {
      content-visibility: visible;
      contain-intrinsic-size: auto;
    }'''


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    orig = text
    if OLD_TINY in text:
        text = text.replace(OLD_TINY, NEW_TINY)
        print("patched tiny-matrix-cell emitter")
    else:
        print("tiny emitter already flat or mismatch")
    if OLD_MATRIX in text:
        text = text.replace(OLD_MATRIX, NEW_MATRIX)
        print("patched matrix-cell emitter")
    else:
        print("matrix emitter already flat or mismatch")
    if OLD_CSS in text:
        text = text.replace(OLD_CSS, NEW_CSS)
        print("patched matrix CSS")
    elif "content: attr(data-value)" in text:
        print("CSS already has data-value ::after")
    else:
        print("CSS block mismatch")
    if text != orig:
        TARGET.write_text(text, encoding="utf-8")
        print(f"wrote {TARGET} ({len(orig)} -> {len(text)})")
    else:
        print("no source changes")


if __name__ == "__main__":
    main()
