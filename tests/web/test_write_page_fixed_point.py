"""Ghi lại một trang đã ghi phải ra ĐÚNG trang ấy (`page_output.write_page`, 11-11-2026).

`regional-results.yml` ghi lại mọi trang qua `scripts/web/refresh_navigation.py` mỗi đêm, rồi pipeline dựng
mới chúng mỗi chiều. Tới 11-11-2026 sáu trang thống kê chi tiết không phải điểm bất động: khối CSS
`ui-source-detail-layout` bị bỏ qua khi đã có, trong khi `refine_page` bóc rồi chèn lại khối của nó ở cuối
`<head>`. Hai workflow vì thế đổi chỗ khối ấy qua lại, mỗi lần 112 dòng trên mỗi trang, hai commit mỗi ngày.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from web import page_output
from web.page_output import write_page

ROOT = Path(__file__).resolve().parents[2]
DETAIL_PAGES = sorted(page_output._DETAIL_STAT_PAGES)

SOURCE = ("<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>Lô gan</title>"
          "<style>.sp-own{{color:#123}}</style></head><body><main class='sp-page'><p>{body}</p></main>"
          "</body></html>")


def _site(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "docs" / "assets", tmp_path / "assets")
    return tmp_path


@pytest.mark.parametrize("name", DETAIL_PAGES)
def test_a_detail_page_written_twice_is_the_same_page(tmp_path: Path, name: str) -> None:
    page = _site(tmp_path) / name
    write_page(page, SOURCE.format(body="12 · 34"))   # như pipeline: dựng mới
    first = page.read_bytes()
    write_page(page, first.decode("utf-8"))            # như workflow miền: ghi lại trang đã có
    assert page.read_bytes() == first
    assert first.decode("utf-8").count(f'id="{page_output._SOURCE_DETAIL_STYLE_ID}"') == 1


def test_a_detail_page_with_stale_layout_css_gets_the_current_css(tmp_path: Path) -> None:
    """Bỏ qua trang đã có khối cũng giữ mãi CSS cũ khi `stat_detail_pages.css` đổi."""
    page = _site(tmp_path) / "lo-gan.html"
    write_page(page, SOURCE.format(body="12"))
    stale = page.read_text(encoding="utf-8").replace(
        f'<style id="{page_output._SOURCE_DETAIL_STYLE_ID}">',
        f'<style id="{page_output._SOURCE_DETAIL_STYLE_ID}">.cu-da-bo{{color:red}}', 1)
    write_page(page, stale)
    text = page.read_text(encoding="utf-8")
    assert ".cu-da-bo" not in text
    assert text.count(f'id="{page_output._SOURCE_DETAIL_STYLE_ID}"') == 1


def test_other_pages_never_get_the_detail_layout(tmp_path: Path) -> None:
    page = _site(tmp_path) / "thong-ke-tong-hop.html"
    write_page(page, SOURCE.format(body="12"))
    assert page_output._SOURCE_DETAIL_STYLE_ID not in page.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", DETAIL_PAGES)
def test_every_published_detail_page_is_a_fixed_point(tmp_path: Path, name: str) -> None:
    published = ROOT / "docs" / name
    page = _site(tmp_path) / name
    write_page(page, published.read_text(encoding="utf-8"))
    assert page.read_bytes() == published.read_bytes()


def _page(stamp: str, board: bool) -> str:
    table = "<section id='mo-phong'><table><tr><td>57630</td></tr></table></section>" if board else ""
    return (f"<!doctype html><html><head><title>Trang chủ</title></head><body><main>{table}"
            f"<p>Sinh lúc {stamp}. AI/ML là tín hiệu thống kê.</p></main></body></html>\n")


def test_a_home_page_written_in_two_steps_gets_the_committed_bytes_back(tmp_path: Path) -> None:
    """Trang chủ ghi hai bước (khung rồi bảng mô phỏng): so từng lần ghi với tệp trên đĩa thì không thấy
    kết quả cuối chỉ khác dấu giờ; so với bản HEAD sau mỗi bước thì thấy (lượt chạy lại 14-11-2026)."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True).stdout

    git("init", "-q")
    (tmp_path / "docs").mkdir()
    home, other = tmp_path / "docs" / "index.html", tmp_path / "docs" / "lo-gan.html"
    home.write_text(_page("2026-11-14 13:04 UTC", board=True), encoding="utf-8")
    other.write_text(_page("2026-11-14 13:04 UTC", board=False), encoding="utf-8")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "đầu")
    committed = home.read_bytes()

    home.write_text(_page("2026-11-14 13:12 UTC", board=False), encoding="utf-8")   # bước khung
    other.write_text(_page("2026-11-14 13:12 UTC", board=True), encoding="utf-8")   # đổi thật
    assert page_output.keep_committed_pages_when_only_stamps_changed(tmp_path) == []
    home.write_text(_page("2026-11-14 13:12 UTC", board=True), encoding="utf-8")    # bước chèn bảng
    assert page_output.keep_committed_pages_when_only_stamps_changed(tmp_path) == ["docs/index.html"]
    assert home.read_bytes() == committed
    assert "13:12" in other.read_text(encoding="utf-8")
    assert git("status", "--porcelain", "docs/index.html") == ""
