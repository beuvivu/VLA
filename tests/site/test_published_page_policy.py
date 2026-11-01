"""Mọi trang đã xuất bản khai CÙNG một Content-Security-Policy, và `docs/.nojekyll` luôn có (01-11-2026).

Trước ngày này hai điều ấy chỉ đúng nhờ may: CLAUDE.md ghi "không có phép kiểm nào bảo đảm MỌI trang đều
khai CSP" và "chưa có phép kiểm nào canh `.nojekyll`". Hôm đặt luật, 50/50 trang có CSP, nhưng ba trang
(`index`, `landing`, `landing_desktop`) mang thẻ đã bị bộ dựng chuẩn hoá thứ tự thuộc tính (`content`
trước `http-equiv`), nên mọi phép dò chuỗi `<meta http-equiv=... content=...>` đều trượt chúng. Ở đây đọc
thẻ bằng bộ phân tích HTML, không bằng chuỗi.

GitHub Pages không đặt được header HTTP, nên thẻ `<meta>` là lớp CSP duy nhất; nó chỉ có hiệu lực với phần
tài liệu SAU nó, nên phải đứng trước mọi `<script>`, `<link>` và `<style>`.
"""
from __future__ import annotations

import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from web.web_security import CONTENT_SECURITY_POLICY

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.glob("*.html"))


class _Head(HTMLParser):
    """Ghi các thẻ CSP trong `<head>` và tên thẻ tài nguyên đứng trước thẻ CSP đầu tiên."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.policies: list[str] = []
        self.before_policy: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self.in_head = True
        if not self.in_head:
            return
        values = {name.lower(): value or "" for name, value in attrs}
        if tag == "meta" and values.get("http-equiv", "").lower() == "content-security-policy":
            self.policies.append(values.get("content", ""))
        elif tag in ("script", "link", "style") and not self.policies:
            self.before_policy.append(tag)

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False


#: `connect-src` của từng trang, danh sách trắng ĐÓNG. Chỉ trang Live được nới, đúng cho Worker đúng giờ và nguồn
#: dự phòng cũ (`test_live_page_keeps_security_contract` ghim cùng chuỗi). Trang khác: chỉ `'self'`.
CONNECT_SOURCES = {"live.html": "'self' https://raw.githubusercontent.com https://*.workers.dev https://*.deno.dev"}


def policy_problems(html: str, connect: str = "'self'") -> list[str]:
    """Điều gì sai với CSP của một trang. Rỗng là đúng luật."""
    head = _Head()
    head.feed(html)
    if len(head.policies) != 1:
        return [f"{len(head.policies)} thẻ CSP trong <head>, cần đúng 1"]
    problems = []
    if head.before_policy:
        problems.append(f"thẻ CSP đứng sau {head.before_policy}: phần ấy không được bảo vệ")
    # Trùng từng chữ với chính sách chung, chỉ `connect-src` lấy theo danh sách trắng của trang. So cả chỉ thị ấy:
    # thay nó bằng `'self'` trước khi so thì một trang nới `connect-src *` vẫn lọt.
    expected = CONTENT_SECURITY_POLICY.replace("connect-src 'self'", f"connect-src {connect}")
    if head.policies[0] != expected:
        problems.append(f"chính sách khác bản chung: {head.policies[0]!r}")
    return problems


def test_there_are_pages_to_check():
    assert len(PAGES) >= 40, "docs/ gần như rỗng: phép kiểm tham số hoá sẽ không chạy lần nào"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_published_page_declares_the_shared_content_security_policy(page: Path):
    assert policy_problems(page.read_text(encoding="utf-8"), CONNECT_SOURCES.get(page.name, "'self'")) == []


def test_the_policy_rule_itself_catches_a_missing_late_or_loosened_policy():
    """Ghim chính luật trên mẫu dựng sẵn, kể cả thứ tự thuộc tính đã chuẩn hoá như ba trang landing."""
    ok = f'<meta content="{CONTENT_SECURITY_POLICY}" http-equiv="Content-Security-Policy"/>'
    page = "<html><head>{}</head><body><script>x()</script></body></html>".format
    assert policy_problems(page(ok + '<script src="a.js"></script>')) == []
    worker = "'self' https://w.example"
    live = CONTENT_SECURITY_POLICY.replace("connect-src 'self'", f"connect-src {worker}")
    assert policy_problems(page(f'<meta http-equiv="Content-Security-Policy" content="{live}">'), worker) == []
    # Nới `connect-src` ngoài danh sách trắng của trang: thêm host, hay mở hẳn `*`.
    assert policy_problems(page(f'<meta http-equiv="Content-Security-Policy" content="{live}">')) != []
    wide = CONTENT_SECURITY_POLICY.replace("connect-src 'self'", "connect-src *")
    assert policy_problems(page(f'<meta http-equiv="Content-Security-Policy" content="{wide}">')) != []
    assert policy_problems(page('<script src="a.js"></script>')) != []
    assert policy_problems(page('<script src="a.js"></script>' + ok)) != []
    loose = CONTENT_SECURITY_POLICY.replace("object-src 'none'", "object-src *")
    assert policy_problems(page(f'<meta http-equiv="Content-Security-Policy" content="{loose}">')) != []
    assert policy_problems(page(ok + ok)) != []


def test_github_pages_keeps_files_that_start_with_an_underscore():
    """Thiếu `docs/.nojekyll` thì Jekyll của Pages bỏ mọi tệp bắt đầu bằng `_`. Tệp phải được git theo dõi:
    workflow triển khai từ bản checkout, tệp chỉ có trên máy không tới được Pages."""
    marker = DOCS / ".nojekyll"
    assert marker.is_file()
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "docs/.nojekyll"], cwd=ROOT,
                             capture_output=True, text=True, check=False)
    if tracked.returncode != 0 and "not a git repository" in tracked.stderr:
        pytest.skip("không phải bản checkout git")
    assert tracked.returncode == 0, tracked.stderr
