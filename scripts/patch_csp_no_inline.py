#!/usr/bin/env python3
"""CSP without unsafe-inline: externalize loaders + hash remaining style/script blocks."""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASE_CSP = (
    "default-src 'self'; base-uri 'none'; connect-src 'self'; font-src 'self'; "
    "form-action 'none'; frame-src 'none'; img-src 'self' data:; object-src 'none'; "
    "upgrade-insecure-requests"
)


def sha256_csp(content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return "'sha256-%s'" % base64.b64encode(digest).decode("ascii")


def rewrite_html(path: Path) -> bool:
    html = path.read_text(encoding="utf-8")
    orig = html

    html = re.sub(r'\s*onload="this\.media=\'all\'"', ' data-async-css="1"', html, flags=re.I)

    html = re.sub(
        r'<style id="ui-critical">[\s\S]*?</style>',
        '<link rel="stylesheet" href="assets/critical.css" />',
        html,
        count=1,
        flags=re.I,
    )

    html = re.sub(
        r"<script>\(function\(\)\{var d=document\.querySelector\([\"']\.(?:ui-)?dock[\"']\)[\s\S]*?</script>",
        '<script src="assets/ui-dock.js" defer></script>',
        html,
        flags=re.I,
    )

    for needle, tag in [
        ("css-async.js", '<script src="assets/css-async.js" defer></script>'),
        ("apply-data-styles.js", '<script src="assets/apply-data-styles.js" defer></script>'),
        ("ui-dock.js", '<script src="assets/ui-dock.js" defer></script>'),
    ]:
        if needle not in html and "</body>" in html:
            html = html.replace("</body>", tag + "\n</body>", 1)

    def style_to_data(m: re.Match) -> str:
        tag = m.group(0)
        sm = re.search(r'style="([^"]*)"', tag, re.I)
        if not sm:
            return tag
        bg = fg = None
        for part in sm.group(1).split(";"):
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            k, v = k.strip().lower(), v.strip()
            if k in ("background", "background-color"):
                bg = v
            elif k == "color":
                fg = v
        if bg is None and fg is None:
            return tag
        tag2 = re.sub(r'\s*style="[^"]*"', "", tag, count=1)
        extra = ""
        if bg:
            extra += ' data-bg="%s"' % bg
        if fg:
            extra += ' data-fg="%s"' % fg
        if tag2.endswith(">"):
            tag2 = tag2[:-1] + extra + ">"
        return tag2

    html = re.sub(
        r"<(button|span|div|td|th)\b[^>]*\bstyle=\"[^\"]*(?:background|color)[^\"]*\"[^>]*>",
        style_to_data,
        html,
        flags=re.I,
    )

    style_hashes = []
    for m in re.finditer(r"<style\b[^>]*>([\s\S]*?)</style>", html, re.I):
        style_hashes.append(sha256_csp(m.group(1)))

    script_hashes = []
    for m in re.finditer(r"<script\b([^>]*)>([\s\S]*?)</script>", html, re.I):
        attrs, body = m.group(1), m.group(2)
        if re.search(r"\bsrc\s*=", attrs, re.I):
            continue
        if re.search(r'type\s*=\s*["\']application/(?:json|ld\+json)["\']', attrs, re.I):
            continue
        if not body.strip():
            continue
        script_hashes.append(sha256_csp(body))

    style_src = "style-src 'self'" + ((" " + " ".join(dict.fromkeys(style_hashes))) if style_hashes else "")
    script_src = "script-src 'self'" + ((" " + " ".join(dict.fromkeys(script_hashes))) if script_hashes else "")
    policy = "%s; %s; %s" % (BASE_CSP, script_src, style_src)

    if re.search(r'http-equiv="Content-Security-Policy"', html, re.I):
        html = re.sub(
            r'<meta[^>]*http-equiv="Content-Security-Policy"[^>]*/?>',
            '<meta http-equiv="Content-Security-Policy" content="%s" />' % policy,
            html,
            count=1,
            flags=re.I,
        )
    else:
        html = html.replace(
            "<head>",
            '<head>\n<meta http-equiv="Content-Security-Policy" content="%s" />' % policy,
            1,
        )

    if html != orig:
        path.write_text(html, encoding="utf-8")
        return True
    return False


def main() -> None:
    docs = ROOT / "docs"
    n = 0
    if docs.is_dir():
        for path in sorted(docs.glob("*.html")):
            if rewrite_html(path):
                print("rewrote", path.name)
                n += 1
    print("done", n, "files")


if __name__ == "__main__":
    main()
