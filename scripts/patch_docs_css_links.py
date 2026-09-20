#!/usr/bin/env python3
"""Rewrite CSS links to 2 parallel sheets + preload (no @import, no incomplete parts)."""
from __future__ import annotations
import re
from pathlib import Path

NEW_BLOCK = (
    '<link rel="preload" href="assets/ui.css" as="style" />\n'
    '  <link rel="preload" href="assets/ui-visual-system.css" as="style" />\n'
    '  <link rel="preload" href="assets/InterVariable.woff2" as="font" type="font/woff2" crossorigin />\n'
    '  <link rel="stylesheet" href="assets/ui.css" />\n'
    '  <link rel="stylesheet" href="assets/ui-visual-system.css" data-ui-visual-system />'
)

UI_LINK = re.compile(
    r'(?:'
    r'<link\s+[^>]*href=["\']assets/ui(?:-part[123])?\.css["\'][^>]*/?>\s*'
    r')+',
    re.I,
)
VIS_LINK = re.compile(
    r'<link\s+[^>]*href=["\']assets/ui-visual-system\.css["\'][^>]*/?>\s*',
    re.I,
)
PRELOAD = re.compile(
    r'<link\s+[^>]*rel=["\']preload["\'][^>]*(?:ui\.css|ui-visual|InterVariable)[^>]*/?>\s*',
    re.I,
)

def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    text = PRELOAD.sub("", text)
    text = UI_LINK.sub("", text)
    text = VIS_LINK.sub("", text)
    if "</title>" in text:
        text = text.replace("</title>", "</title>\n  " + NEW_BLOCK, 1)
    else:
        text = text.replace("<head>", "<head>\n  " + NEW_BLOCK, 1)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False

def main() -> None:
    docs = Path("docs")
    if not docs.is_dir():
        docs = Path(__file__).resolve().parents[1] / "docs"
    n = 0
    for path in sorted(docs.glob("*.html")):
        if patch_file(path):
            n += 1
            print("patched", path.name)
    print(f"done: {n} files")

if __name__ == "__main__":
    main()
