"""Boc chu thich khoi trang da dung, truoc khi ghi ra `docs/`.

Vi sao boc o BUOC XUAT chu khong xoa trong ma nguon: chu thich trong
`src/` la ban ghi ky thuat cua du an. Con thu nguoi xem thay khi bam
"View Source" la TRANG DA DUNG, va trang ay sach tuyet doi sau buoc nay.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

from css_links import CRITICAL_CSS
from ui_page_refinements import refine_page

__all__ = ["strip_comments", "strip_css", "write_page", "write_stylesheet_text"]

_HTML_COMMENT = re.compile(r"<!--(?!\[if)(?:(?!-->).)*-->", re.S)
_BLOCK = re.compile(r"<(script|style)\b([^>]*)>(.*?)</\1\s*>", re.I | re.S)

_DETAIL_STAT_PAGES = frozenset({
    "bang-dac-biet.html",
    "lo-gan.html",
    "dau-duoi-loto.html",
    "giai-dac-biet-theo-tong.html",
    "cau-dac-biet-theo-bo-so.html",
    "giai-db-ngay-mai.html",
    "cap-lon-loto.html",
})
_SOURCE_DETAIL_STYLE_ID = "ui-source-detail-layout"

_REGEX_AFTER_KEYWORD = frozenset({
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "throw", "case", "do", "else", "yield", "await",
})

_IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz"
                         "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")


def _strip_css(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    quote = ""
    while i < n:
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1]); i += 2; continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "\"'":
            quote = ch; out.append(ch); i += 1; continue
        if ch == "/" and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        out.append(ch); i += 1
    return out and "".join(out) or ""


def _strip_js(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    template_depth: list[int] = []
    previous = ""

    def starts_regex() -> bool:
        if not previous:
            return True
        if previous in _REGEX_AFTER_KEYWORD:
            return True
        if previous in (")", "]", "value"):
            return False
        return not (previous[0] in _IDENT_CHARS)

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if ch == "/" and nxt == "/":
            end = text.find("\n", i)
            i = n if end == -1 else end
            continue
        if ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        if ch in "\"'":
            quote = ch; out.append(ch); i += 1
            while i < n:
                c = text[i]; out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1]); i += 2; continue
                i += 1
                if c == quote:
                    break
            previous = "value"
            continue
        if ch == "`":
            out.append(ch); i += 1
            while i < n:
                c = text[i]; out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1]); i += 2; continue
                if c == "$" and i + 1 < n and text[i + 1] == "{":
                    out.append("{"); i += 2
                    template_depth.append(1)
                    break
                i += 1
                if c == "`":
                    break
            previous = "value"
            continue
        if ch == "{" and template_depth:
            template_depth[-1] += 1
        if ch == "}" and template_depth:
            template_depth[-1] -= 1
            if template_depth[-1] == 0:
                template_depth.pop()
                out.append(ch); i += 1
                while i < n:
                    c = text[i]; out.append(c)
                    if c == "\\" and i + 1 < n:
                        out.append(text[i + 1]); i += 2; continue
                    if c == "$" and i + 1 < n and text[i + 1] == "{":
                        out.append("{"); i += 2; template_depth.append(1); break
                    i += 1
                    if c == "`":
                        break
                continue
        if ch == "/" and starts_regex():
            out.append(ch); i += 1
            in_class = False
            while i < n:
                c = text[i]; out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1]); i += 2; continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    i += 1
                    break
                elif c == "\n":
                    i += 1
                    break
                i += 1
            while i < n and text[i].isalpha():
                out.append(text[i]); i += 1
            previous = "value"
            continue

        if ch in _IDENT_CHARS:
            start = i
            while i < n and text[i] in _IDENT_CHARS:
                out.append(text[i]); i += 1
            previous = text[start:i]
            if previous[0].isdigit():
                previous = "value"
            continue
        out.append(ch)
        if not ch.isspace():
            previous = ch
        i += 1
    return "".join(out)


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]+(\r?\n)", r"\1", text)
    return re.sub(r"(\r?\n)[ \t]*(?:\r?\n)+", r"\1\1", text)


def strip_comments(html: str) -> str:
    def replace(match: re.Match[str]) -> str:
        tag, attrs, body = match.group(1), match.group(2), match.group(3)
        if "application/json" in attrs.lower():
            return match.group(0)
        cleaned = _strip_css(body) if tag.lower() == "style" else _strip_js(body)
        return f"<{tag}{attrs}>{_tidy(cleaned)}</{tag}>"

    parts: list[str] = []
    cursor = 0
    for match in _BLOCK.finditer(html):
        parts.append(_HTML_COMMENT.sub("", html[cursor:match.start()]))
        parts.append(replace(match))
        cursor = match.end()
    parts.append(_HTML_COMMENT.sub("", html[cursor:]))
    return _tidy("".join(parts))


def strip_css(css: str) -> str:
    return _tidy(_strip_css(css))


def _inject_source_detail_style(path: Path, html: str) -> str:
    if path.name not in _DETAIL_STAT_PAGES or f'id="{_SOURCE_DETAIL_STYLE_ID}"' in html:
        return html
    css_path = Path(__file__).resolve().parent / "templates" / "stat_detail_pages.css"
    css = css_path.read_text(encoding="utf-8")
    style = f'<style id="{_SOURCE_DETAIL_STYLE_ID}">{css}</style>'
    return html.replace("</head>", f"{style}\n</head>", 1)


def write_page(path: Path, html: str) -> None:
    refined = refine_page(path, html)
    refined = _inject_source_detail_style(path, refined)
    refined = _attach_visual_system(path, refined)
    path.write_text(strip_comments(refined), encoding="utf-8")


def _attach_visual_system(path: Path, html: str) -> str:
    """Publish shared skin; load non-blocking for Critical Rendering Path."""
    if "</head>" not in html or not re.search(r"<body\b", html, re.I):
        return html
    css = Path(__file__).with_name("templates") / "ui_visual_system.css"
    target = path.parent / "assets" / "ui-visual-system.css"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_stylesheet_text(target, css.read_text(encoding="utf-8"))
    # `assets/critical.css` cũng phải được ghi lại từ `CRITICAL_CSS`, không
    # phải để nguyên hiện vật đã commit. `ensure_critical_css_file` trước đây
    # KHÔNG được gọi ở đâu cả, nên tệp xuất bản là một bản chép tay đứng im:
    # nó còn mang chú thích `/* critical shell ... */` mà nguồn không có, và
    # nó trôi khỏi `CRITICAL_CSS` mà không dấu hiệu gì. Mỗi trang ghi ra đều
    # ghi lại tệp này, cùng chỗ với biểu định kiểu anh em ngay trên.
    write_stylesheet_text(
        path.parent / "assets" / "critical.css",
        CRITICAL_CSS,
    )
    head, rest = html.split("</head>", 1)
    # Bóc khối <noscript> TRƯỚC, rồi mới bóc thẻ <link> trần. Đảo thứ tự thì
    # luật đầu ăn mất chính cái <link> nằm trong <noscript>, luật sau không còn
    # gì để khớp, và một <noscript></noscript> rỗng ở lại sau mỗi lần ghi — nên
    # `write_page` không còn là điểm bất động: ghi lại một trang đã ghi cho ra
    # tệp khác.
    head = re.sub(
        r'<noscript>\s*<link\b[^>]*\bdata-ui-visual-system\b[^>]*>\s*</noscript>\s*',
        "",
        head,
        flags=re.I,
    )
    head = re.sub(r'<link\b[^>]*\bdata-ui-visual-system\b[^>]*>\s*', "", head)
    link = (
        '<link rel="stylesheet" href="assets/ui-visual-system.css" '
        'media="print" onload="this.media=\'all\'" data-ui-visual-system>'
    )
    noscript = (
        '<noscript><link rel="stylesheet" href="assets/ui-visual-system.css" '
        'data-ui-visual-system></noscript>'
    )
    html = head.rstrip() + "\n" + link + "\n" + noscript + "\n</head>" + rest
    page_key = "index" if path.stem in {"landing", "landing_desktop"} else path.stem
    html = re.sub(
        r'(<body\b[^>]*\bdata-ui-page=")[^"]*(")',
        lambda match: match[1] + escape(page_key, quote=True) + match[2],
        html, count=1, flags=re.I,
    )
    if not re.search(r'<body\b[^>]*\bdata-ui-page=', html, re.I):
        html = re.sub(r"<body\b", f'<body data-ui-page="{escape(page_key, quote=True)}"', html, count=1, flags=re.I)
    return html


def write_stylesheet_text(path: Path, css: str) -> None:
    path.write_text(strip_css(css), encoding="utf-8")
