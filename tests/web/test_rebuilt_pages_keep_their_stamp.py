"""Trang dựng lại trên cùng dữ liệu chỉ khác giờ dựng thì GIỮ bản đang có (``page_output.write_page``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from web.page_output import PAGE_BUILD_STAMPS, write_page

ROOT = Path(__file__).resolve().parents[2]

PAGE = ("<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>Lô gan</title></head>"
        "<body><main><p>Dữ liệu đến 2026-11-05 · Dựng lúc {stamp}.</p><p>{body}</p></main></body></html>")


def test_a_page_rebuilt_on_the_same_data_is_left_untouched(tmp_path: Path) -> None:
    page = tmp_path / "lo-gan.html"
    write_page(page, PAGE.format(stamp="2026-11-05T11:38:57Z", body="12 · 34"))
    first = page.read_bytes()
    write_page(page, PAGE.format(stamp="2026-11-05T12:32:58Z", body="12 · 34"))
    assert page.read_bytes() == first
    write_page(page, PAGE.format(stamp="2026-11-05T12:32:58Z", body="12 · 35"))
    assert page.read_bytes() != first
    assert "2026-11-05T12:32:58Z" in page.read_text(encoding="utf-8")


# Mỗi mẫu dấu giờ phải khớp đúng một trang đã xuất bản: trình dựng đổi định dạng mà mẫu không theo
# thì mẫu chết, và trang lại bị ghi lại sau mỗi lượt chạy lại.
@pytest.mark.parametrize(
    "pattern,page",
    list(zip(PAGE_BUILD_STAMPS, ["cap-lon-loto.html", "dashboard.html", "vietlott.html",
                                 "statistics.html", "so-ket-qua-truyen-thong.html", "index.html"], strict=True)),
    ids=["dung-luc", "ban-dung", "vietlott", "footer-built", "generated-at", "sinh-luc"],
)
def test_every_build_stamp_pattern_matches_a_published_page(pattern, page) -> None:
    text = (ROOT / "docs" / page).read_text(encoding="utf-8")
    assert pattern.search(text), f"{pattern.pattern} không còn khớp {page}"
