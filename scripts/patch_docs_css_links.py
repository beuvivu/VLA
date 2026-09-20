#!/usr/bin/env python3
"""Rewrite docs HTML heads for Critical Rendering Path CSS loading."""
from __future__ import annotations
import re
import sys
from pathlib import Path

def _new_block() -> str:
    docs = Path("docs")
    root = (docs.parent if docs.is_dir() else Path(__file__).resolve().parents[1]) / "src"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from css_links import stylesheet_link
        return stylesheet_link()
    except Exception:
        return (
            '<link rel="preload" href="assets/InterVariable.woff2" as="font" type="font/woff2" crossorigin />\n'
            '  <link rel="preload" href="assets/ui.css" as="style" />\n'
            '  <link rel="preload" href="assets/ui-visual-system.css" as="style" />\n'
            '  <link rel="stylesheet" href="assets/ui.css" media="print" onload="this.media=\'all\'" />\n'
            '  <link rel="stylesheet" href="assets/ui-visual-system.css" media="print" onload="this.media=\'all\'" data-ui-visual-system />\n'
            '  <noscript>\n'
            '  <link rel="stylesheet" href="assets/ui.css" />\n'
            '  <link rel="stylesheet" href="assets/ui-visual-system.css" data-ui-visual-system />\n'
            '  </noscript>'
        )

STRIP = re.compile(
    r"(?:"
    r"<link\s+[^>]*(?:href=[\"']assets/ui(?:-part[123])?\.css[\"']|href=[\"']assets/ui-visual-system\.css[\"']|href=[\"']assets/InterVariable\.woff2[\"'])[^>]*/?>\s*"
    r"|<style\b[^>]*\bid=[\"']ui-critical[\"'][^>]*>.*?</style>\s*"
    r"|<noscript>\s*(?:<link\s+[^>]*href=[\"']assets/ui[^>]*>\s*)+</noscript>\s*"
    r")",
    re.I | re.S,
)

def patch_file(path: Path, block: str) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    text = STRIP.sub("", text)
    if "</title>" in text:
        text = text.replace("</title>", "</title>\n  " + block, 1)
    elif "<head>" in text:
        text = text.replace("<head>", "<head>\n  " + block, 1)
    else:
        return False
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False

def main() -> None:
    docs = Path("docs")
    if not docs.is_dir():
        docs = Path(__file__).resolve().parents[1] / "docs"
    block = _new_block()
    n = 0
    for path in sorted(docs.glob("*.html")):
        if patch_file(path, block):
            n += 1
            print("patched", path.name)
    print(f"done: {n} files")

if __name__ == "__main__":
    main()
