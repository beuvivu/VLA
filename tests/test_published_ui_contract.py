"""Hợp đồng giao diện ở lớp xuất bản, không chỉ ở từng builder.

Một trang có thể sinh đúng HTML nhưng vẫn trôi khỏi Master Design System nếu
builder quên nạp biểu định kiểu nền. Phép kiểm này nhìn thẳng vào ``docs/*.html``
— chính các tệp GitHub Pages phục vụ — và yêu cầu mọi trang đứng trên cùng một
shared base stylesheet. CSS nội tuyến/scoped overlay vẫn được phép bổ sung cho
nhu cầu riêng của từng trang, nhưng không được thay thế lớp nền dùng chung.
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SHARED_STYLESHEET = "assets/ui.css"


def _published_pages() -> list[Path]:
    pages = sorted(DOCS.glob("*.html"))
    assert pages, "không tìm thấy trang HTML đã xuất bản"
    return pages


def test_shared_stylesheet_asset_exists() -> None:
    sheet = DOCS / SHARED_STYLESHEET
    assert sheet.is_file(), f"thiếu shared design system: {sheet}"
    assert sheet.stat().st_size > 0, f"shared design system rỗng: {sheet}"


def test_every_published_page_loads_the_shared_design_system() -> None:
    missing: list[str] = []
    dead_links: list[str] = []

    for page in _published_pages():
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        hrefs = {
            str(link.get("href") or "").split("?", 1)[0]
            for link in soup.find_all("link", rel="stylesheet")
        }
        if SHARED_STYLESHEET not in hrefs:
            missing.append(page.name)
            continue
        if not (page.parent / SHARED_STYLESHEET).is_file():
            dead_links.append(page.name)

    assert not missing, f"trang rơi khỏi shared design system: {missing}"
    assert not dead_links, f"trang trỏ tới stylesheet không tồn tại: {dead_links}"


def test_no_published_page_references_the_retired_stylesheet_name() -> None:
    """Tên chuẩn hiện tại là ``assets/ui.css``; ``vla.css`` là tài liệu cũ."""
    offenders: list[str] = []
    for page in _published_pages():
        text = page.read_text(encoding="utf-8")
        if "assets/vla.css" in text:
            offenders.append(page.name)
    assert not offenders, f"còn tham chiếu assets/vla.css: {offenders}"
