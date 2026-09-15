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
from pathlib import Path

__all__ = ["strip_comments", "strip_css", "write_page", "write_stylesheet_text"]

_HTML_COMMENT = re.compile(r"<!--(?!\[if)(?:(?!-->).)*-->", re.S)
_BLOCK = re.compile(r"<(script|style)\b([^>]*)>(.*?)</\1\s*>", re.I | re.S)

#: Từ khoá mà sau nó, dấu ``/`` mở đầu một HẰNG REGEX chứ không phải phép chia.
#:
#: Bản đầu của tệp này chỉ nhìn KÝ TỰ đứng trước. Với ``return /[",]/`` nó
#: thấy chữ ``n`` cuối từ ``return``, kết luận là phép chia, rồi dấu ``"``
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
    # Ngăn xếp cho chuỗi mẫu: `${...}` có thể lồng chuỗi mẫu khác bên trong.
    template_depth: list[int] = []
    #: Token có nghĩa gần nhất đã ghi ra. Chỉ cần đủ để phân biệt phép chia
    #: với hằng regex, nên "chuỗi" và "số" gộp chung thành một loại.
    previous = ""

    def starts_regex() -> bool:
        if not previous:
            return True
        if previous in _REGEX_AFTER_KEYWORD:
            return True
        # Sau một giá trị (định danh, số, chuỗi, `)`, `]`) thì `/` là phép chia.
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
                # Trở lại thân chuỗi mẫu sau khi đóng `${...}`.
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
            # Hằng biểu thức chính quy: sao chép nguyên vẹn, kể cả `//` bên trong.
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
            # Số đứng trước `/` thì đó là phép chia, như mọi giá trị khác.
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
        # Tải trọng JSON không phải mã; `//` trong đó là dữ liệu.
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
    """Bóc chú thích khỏi một biểu định kiểu độc lập.

    Cùng bộ máy đã dùng cho thẻ ``<style>`` bên trong trang, chỉ khác là gọi
    thẳng cho tệp ``.css`` rời.
    """
    return _tidy(_strip_css(css))


def write_page(path: Path, html: str) -> None:
    """Ghi một trang ra đĩa, đã bóc sạch chú thích."""
    path.write_text(strip_comments(html), encoding="utf-8")


def write_stylesheet_text(path: Path, css: str) -> None:
    """Ghi một biểu định kiểu rời, đã bóc sạch chú thích.

    Biểu định kiểu dùng chung cũng là thứ gửi thẳng tới trình duyệt của khách
    y như trang HTML, nhưng trước đây nó không đi qua bộ bóc chú thích: nó
    được ghi bằng ``write_text`` trần. Kết quả là 55 chú thích tiếng Việt mô
    tả nội tình bản dựng vẫn nằm trong tệp 37 KB mà mọi trang đều tải.
    """
    path.write_text(strip_css(css), encoding="utf-8")
