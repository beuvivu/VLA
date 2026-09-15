"""Trang đã xuất bản: không chú thích, không lộ nơi lưu trữ.

Quét THẲNG `docs/` chứ không hỏi `page_output`. Một phép kiểm chỉ gọi lại
hàm bóc chú thích thì chỉ chứng minh hàm ấy tự nhất quán; nó xanh y hệt khi
có một builder ghi tệp mà quên đi qua `write_page` — mà đó đúng là chuyện đã
xảy ra hai lần trong lượt dọn này (`build_fun_prediction` vá lại ba trang sau
khi chúng đã được ghi sạch, và `live.html` không do builder nào sinh ra).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "docs").glob("*.html"))

_SCRIPT = re.compile(r'<script(?![^>]*application/json)[^>]*>(.*?)</script>', re.S | re.I)
_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)


def _without_strings(code: str) -> str:
    """Bỏ nội dung mọi chuỗi nháy. Dùng được cho cả CSS lẫn JS."""
    code = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", code)
    code = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', code)
    return re.sub(r"`(?:[^`\\]|\\.)*`", "``", code)


def _without_literals(code: str) -> str:
    """Như trên, cộng thêm bỏ HẰNG REGEX. CHỈ dùng cho JavaScript.

    Vì sao phải tách làm hai: luật bóc hằng regex nuốt luôn một chú thích CSS.
    `/* bí mật */` trông y hệt một hằng regex `/.../`, nên đem hàm này áp vào
    CSS thì chú thích biến mất TRƯỚC khi được kiểm — phép kiểm xanh trong khi
    trang vẫn bẩn. Đã đo: đột biến nhét `/* bí mật */` vào `<style>` sống sót
    ở bản đầu, và chết ngay khi tách hai hàm.
    """
    # `(?![*/])`: theo chuẩn JavaScript, `/*` và `//` LUÔN mở đầu chú thích,
    # không bao giờ là hằng regex. Thiếu điều kiện này thì `/* bí mật */` bị
    # nuốt như một hằng regex và chú thích lọt qua — đã đo bằng đột biến.
    return re.sub(r"/(?![*/])(?:[^/\\\n\[]|\\.|\[(?:[^\]\\]|\\.)*\])+/[a-z]*",
                  "/re/", _without_strings(code))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_comment_survives_into_a_published_page(page: Path) -> None:
    html = page.read_text(encoding="utf-8", errors="replace")
    outside = _SCRIPT.sub("", _STYLE.sub("", html))
    assert not re.findall(r"<!--(?!\[if).*?-->", outside, flags=re.S), page.name
    for body in _STYLE.findall(html):
        assert "/*" not in _without_strings(body), page.name
    for body in _SCRIPT.findall(html):
        code = _without_literals(body)
        assert "/*" not in code, page.name
        assert not [ln for ln in code.splitlines() if ln.lstrip().startswith("//")], page.name


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_page_spells_out_where_the_data_lives(page: Path) -> None:
    """Tên kho, tên chủ kho và đường dẫn nội bộ không được nằm trong trang.

    Ngoại lệ DUY NHẤT là thẻ CSP: `connect-src` PHẢI ghi tên miền thật, nếu
    không trình duyệt chặn luôn kết nối. CSP là chốt an ninh do trình duyệt
    thi hành, không mã hoá đi được. Đây là giới hạn của cách làm, không phải
    chỗ bỏ sót.
    """
    html = page.read_text(encoding="utf-8", errors="replace")
    body = re.sub(r"<meta[^>]+Content-Security-Policy[^>]*>", "", html, flags=re.I)
    for token in ("githubusercontent", "github.io", "github.com", "beuvivu",
                  "workers.dev", "deno.dev", "data/xsmb", "data/advanced",
                  "data/path", "data/live"):
        assert token not in body, f"{page.name} lộ {token!r}"


def test_the_only_place_a_real_host_may_appear_is_the_policy_header() -> None:
    """Chốt cho chính ngoại lệ trên: nó phải HẸP, không được nới ra cả trang."""
    offenders = []
    for page in PAGES:
        html = page.read_text(encoding="utf-8", errors="replace")
        for meta in re.findall(r"<meta[^>]+Content-Security-Policy[^>]*>", html, flags=re.I):
            if "connect-src" not in meta:
                offenders.append(page.name)
    assert not offenders, offenders
