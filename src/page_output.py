"""Bóc chú thích khỏi trang đã dựng, trước khi ghi ra `docs/`.

Vì sao bóc ở BƯỚC XUẤT chứ không xoá trong mã nguồn: chú thích trong
`src/` là bản ghi kỹ thuật của dự án — phần lớn chúng chép lại số đo đã
thực hiện ("đo được 168px mỗi bên", "0 lỗi ở Asia, 14 lỗi ở LA"). Xoá đi
là xoá lý do mã đang đúng. Còn thứ người xem thấy khi bấm "View Source"
là TRANG ĐÃ DỰNG, và trang ấy sạch tuyệt đối sau bước này.

Vì sao không dùng regex cho JavaScript: dấu ``//`` nằm trong CHUỖI, chẳng
hạn ``"http://schemas.openxmlformats.org/..."`` trong mã xuất Excel, hoặc
trong một hằng biểu thức chính quy. Một phép cắt thô sẽ xén mất nửa chuỗi
và làm hỏng trang mà không báo lỗi nào — đúng lỗi đã xảy ra một lần trong
dự án này. Nên phải quét theo TRẠNG THÁI.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

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

#: Từ khoá mà sau nó, dấu ``/`` mở đầu một HẰNG REGEX chứ không phải phép chia.
#:
#: Bản đầu của tệp này chỉ nhìn KÝ TỰ đứng trước. Với ``return /[\",]/`` nó
#: thấy chữ ``n`` cuối từ ``return``, kết luận là phép chia, rồi dấu ``\"``
#: bên trong lớp ký tự mở trạng thái chuỗi — và mọi thứ sau đó lệch pha, chú
#: thích không còn được bóc.
#:
#: 15 ca thử hiểm tự nghĩ ra đều KHÔNG bắt được lỗi này; chính tệp thật mới
#: lòi ra. Nên phải nhìn TOKEN, không nhìn ký tự.
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
    """Gộp các dòng trắng do việc bóc chú thích để lại."""
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
    """Bóc chú thích khỏi một biểu định kiểu độc lập."""
    return _tidy(_strip_css(css))


def _inject_source_detail_style(path: Path, html: str) -> str:
    """Đưa stylesheet chi tiết do source sở hữu vào đúng nhóm trang thống kê.

    Đây là lớp chống hồi quy cho các trang thống kê dài. CSS sống trong
    ``src/templates/stat_detail_pages.css`` để review/test được như mã nguồn,
    thay vì chỉ tồn tại trong một chuỗi hậu xử lý khó nhận biết trên Pages.
    """
    if path.name not in _DETAIL_STAT_PAGES or f'id="{_SOURCE_DETAIL_STYLE_ID}"' in html:
        return html
    css_path = Path(__file__).resolve().parent / "templates" / "stat_detail_pages.css"
    css = css_path.read_text(encoding="utf-8")
    style = f'<style id="{_SOURCE_DETAIL_STYLE_ID}">{css}</style>'
    return html.replace("</head>", f"{style}\n</head>", 1)


def write_page(path: Path, html: str) -> None:
    """Ghi trang đã áp dụng refinement giao diện và bóc sạch chú thích."""
    refined = refine_page(path, html)
    refined = _inject_source_detail_style(path, refined)
    refined = _attach_visual_system(path, refined)
    path.write_text(strip_comments(refined), encoding="utf-8")


def _attach_visual_system(path: Path, html: str) -> str:
    """Publish the final shared skin without reserializing scripts or DOM hooks.

    Page-specific CSS comes first; this small, cacheable stylesheet reconciles
    their shells and surfaces. Fragments are deliberately left untouched.
    """
    if "</head>" not in html or not re.search(r"<body\b", html, re.I):
        return html
    css = Path(__file__).with_name("templates") / "ui_visual_system.css"
    target = path.parent / "assets" / "ui-visual-system.css"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_stylesheet_text(target, css.read_text(encoding="utf-8"))
    head, rest = html.split("</head>", 1)
    head = re.sub(r'<link\b[^>]*\bdata-ui-visual-system\b[^>]*>\s*', "", head)
    link = '<link rel="stylesheet" href="assets/ui-visual-system.css" data-ui-visual-system>'
    html = head.rstrip() + "\n" + link + "\n</head>" + rest
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
    """Ghi một biểu định kiểu rời, đã bóc sạch chú thích."""
    path.write_text(strip_css(css), encoding="utf-8")
