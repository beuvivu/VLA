#!/usr/bin/env python3
"""Rewrite single ui.css <link> to parallel part links in docs/*.html."""
from __future__ import annotations
import re
from pathlib import Path

NEW_LINKS = (
    '<link rel="stylesheet" href="assets/ui-part1.css" />\n'
    '  <link rel="stylesheet" href="assets/ui-part2.css" />\n'
    '  <link rel="stylesheet" href="assets/ui-part3.css" />'
)

PATTERNS = [
    re.compile(r'<link\s+[^>]*href=["\']assets/ui\.css["\'][^>]*/?>', re.I),
    re.compile(r'<link\s+href=["\']assets/ui\.css["\']\s+rel=["\']stylesheet["\']\s*/?>', re.I),
]

def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    for pattern in PATTERNS:
        text = pattern.sub(NEW_LINKS, text)
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
