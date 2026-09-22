#!/usr/bin/env python3
"""Emergency UI restore: allow inline page CSS/JS + force visual CSS to media=all."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKING_CSP = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "form-action 'none'; "
    "frame-src 'none'; "
    "img-src 'self' data:; "
    "object-src 'none'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'"
)
META = (
    '<meta http-equiv="Content-Security-Policy" content="%s" />'
    % WORKING_CSP
)


def fix(html: str) -> str:
    if re.search(r'http-equiv=["\']Content-Security-Policy["\']', html, re.I):
        html = re.sub(
            r'<meta\b[^>]*http-equiv=["\']Content-Security-Policy["\'][^>]*/?>',
            META,
            html,
            count=1,
            flags=re.I,
        )
    else:
        html = html.replace("<head>", "<head>\n" + META, 1)

    # visual system must paint on screen even if onload is blocked
    html = re.sub(
        r'(href=["\']assets/ui-visual-system\.css["\'][^>]*?)\s*media=["\']print["\']',
        r'\1 media="all"',
        html,
        flags=re.I,
    )
    # drop broken onload handlers (optional cleanup)
    html = re.sub(
        r'\s*onload=["\']this\.media=\'all\'["\']',
        "",
        html,
        flags=re.I,
    )
    return html


def main() -> None:
    docs = ROOT / "docs"
    n = 0
    for path in sorted(docs.glob("*.html")):
        original = path.read_text(encoding="utf-8")
        updated = fix(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            print("fixed", path.name)
            n += 1
        else:
            print("unchanged", path.name)
    print("done", n)


if __name__ == "__main__":
    main()
