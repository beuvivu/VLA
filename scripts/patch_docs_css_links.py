#!/usr/bin/env python3
"""Eliminate render-blocking CSS on docs/*.html (Critical Rendering Path).

Removes every managed stylesheet/preload/critical block, then injects:
  1. Font preload
  2. Critical CSS inline (~2.3KB) for first paint
  3. Preload full sheets
  4. Non-blocking full CSS (media=print → onload media=all)
  5. noscript fallback
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

# Match ANY link tag that references our CSS/font assets (any attribute order)
LINK_MANAGED = re.compile(
    r"<link\b(?=[^>]*\bhref\s*=\s*[\"']assets/(?:ui(?:-part[123])?\.css|ui-visual-system\.css|InterVariable\.woff2)[\"'])[^>]*>\s*",
    re.I,
)
CRITICAL_STYLE = re.compile(
    r"<style\b[^>]*\bid\s*=\s*[\"']ui-critical[\"'][^>]*>.*?</style>\s*",
    re.I | re.S,
)
NOSCRIPT_UI = re.compile(
    r"<noscript>\s*(?:<link\b[^>]*href\s*=\s*[\"']assets/ui[^\"']*[\"'][^>]*>\s*)+</noscript>\s*",
    re.I,
)

def _block() -> str:
    root = Path(__file__).resolve().parents[1] / "src"
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

def patch_file(path: Path, block: str) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    text = LINK_MANAGED.sub("", text)
    text = CRITICAL_STYLE.sub("", text)
    text = NOSCRIPT_UI.sub("", text)
    text = re.sub(r"(\n[ \t]*){3,}", "\n\n", text)
    if "</title>" in text:
        text = text.replace("</title>", "</title>\n  " + block, 1)
    elif re.search(r"<head\b", text, re.I):
        text = re.sub(r"(<head\b[^>]*>)", r"\1\n  " + block, text, count=1, flags=re.I)
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
    block = _block()
    n = 0
    for path in sorted(docs.glob("*.html")):
        if patch_file(path, block):
            n += 1
            print("patched", path.name)
        else:
            print("unchanged", path.name)
    print(f"done: {n} files")

if __name__ == "__main__":
    main()
