"""Kiểm chứng SVG Lucide thật và hợp đồng 20px đã được chủ dự án chọn.

Fixture đối chiếu lấy từ kho Lucide ở commit ghim, không gọi bộ dựng đang
kiểm thử để suy ra hình mong đợi. Hash phát hiện sửa/vẽ lại asset gốc; so
cây SVG phát hiện bộ dựng bỏ sót circle/rect/line hoặc gán nhầm biểu tượng.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = ROOT / "src" / "assets" / "icons"
sys.path.insert(0, str(ROOT / "src"))

from app_icons import icon_svg  # noqa: E402
from ui_theme import SITE_NAV  # noqa: E402

PAGES = sorted(DOCS.glob("*.html"))
UPSTREAM_COMMIT = "66d8f9fc394b8530377e5f6112f0b8908ba01280"
# Ba fixture được tải và kiểm tra độc lập từ raw.githubusercontent.com.
UPSTREAM_HASHES = {
    "search": "283d371c2e433817bb9c0c8310caa6c77fa4177c0f4f1168d9c83b97af7389dc",
    "cpu": "ec83bb69ec029d367d749afc445b39c8e95891ebf99b0400652677c2b149b99c",
    "circle": "3a991bd47beaf9874fba6fdf87bbba442970a89b5e6aa391558bc8b0a00a0513",
}
REFERENCE_MAP = {
    "tim-kiem": "search", "che-do": "sun-moon", "toan-man-hinh": "maximize",
    "truc-tiep": "radio", "hom-nay": "calendar-check", "so-ket-qua": "book-open-text",
    "ma-tran": "grid-2x2", "tan-suat": "chart-column", "gan-nhip": "clock-3",
    "cap-lon": "arrow-up-down", "cau-chay": "trending-up", "cau-on-dinh": "activity",
    "cau-de-chay": "route", "cau-de-on-dinh": "chart-no-axes-combined",
    "vi-tri-cau": "locate-fixed", "ai-ml": "cpu", "top-loto": "list-ordered",
    "top-de": "award", "chat-luong": "shield-check", "theo-ngay": "calendar-days",
    "theo-thang": "calendar-range", "theo-nam": "calendar", "chu-ky": "repeat-2",
    "bo-so": "layers-2", "ngay-mai": "calendar-arrow-up", "cap-loto": "link",
    "cap-lon-loto": "repeat", "cau-giai-db": "crosshair", "theo-tong": "sigma",
    "dau-duoi": "columns-2", "lo-gan": "hourglass", "tong-hop": "layout-dashboard",
    "nghien-cuu": "flask-conical", "kiem-dinh": "clipboard-check",
    "menu": "menu", "close": "x", "sun": "sun", "moon": "moon",
    "settings": "settings", "dashboard": "layout-dashboard",
    "menu-toggle": "panel-left", "breadcrumb-separator": "chevron-right",
}


def _geometry(svg: ET.Element) -> list[tuple[str, dict[str, str]]]:
    """So hình học, bỏ namespace do HTML/XML biểu diễn khác nhau."""
    return [(element.tag.rsplit("}", 1)[-1], dict(element.attrib)) for element in svg]


@pytest.mark.parametrize("key", REFERENCE_MAP)
def test_renderer_keeps_uniform_geometry_and_accessibility(key: str) -> None:
    """Bắt lưới cũ/stroke1, màu ghim và icon lọt vào cây trợ năng."""
    svg = ET.fromstring(icon_svg(key))
    expected = {
        "width": "20", "height": "20", "viewBox": "0 0 24 24", "fill": "none",
        "stroke": "currentColor", "stroke-width": "2", "stroke-linecap": "round",
        "stroke-linejoin": "round", "aria-hidden": "true", "focusable": "false",
    }
    for name, value in expected.items():
        assert svg.get(name) == value, (key, name)


@pytest.mark.parametrize(("key", "name"), REFERENCE_MAP.items())
def test_renderer_preserves_the_canonical_svg_primitives(key: str, name: str) -> None:
    """Không được biến cả bộ thành path tự vẽ hoặc đánh mất rect/circle/line."""
    asset = ASSETS / f"{name}.svg"
    assert asset.is_file(), f"Thiếu SVG gốc: {name}"
    assert _geometry(ET.fromstring(icon_svg(key))) == _geometry(ET.parse(asset).getroot())


def test_every_navigation_key_resolves_to_a_verified_icon() -> None:
    """Một khóa lạ/Unicode sẽ rơi vào icon dự phòng và phải bị bắt ở đây."""
    keys = [key for _, items in SITE_NAV for _, _, key in items]
    assert len(keys) >= 32
    assert all(re.fullmatch(r"[a-z0-9-]+", key) for key in keys)
    assert set(keys) <= REFERENCE_MAP.keys()
    fallback = _geometry(ET.fromstring(icon_svg("khong-co-khoa")))
    assert all(_geometry(ET.fromstring(icon_svg(key))) != fallback for key in keys)


def test_vendored_assets_match_pinned_upstream_hashes() -> None:
    """Phát hiện asset bị đổi dù API/SVG vẫn hợp lệ."""
    assert (ASSETS / "provenance.json").is_file(), "Thiếu nguồn và hash upstream"
    provenance = json.loads((ASSETS / "provenance.json").read_text())
    assert provenance["repository"] == "https://github.com/lucide-icons/lucide"
    assert provenance["commit"] == UPSTREAM_COMMIT
    names = set(REFERENCE_MAP.values()) | {"circle"}
    assert set(provenance["sha256"]) == {f"{name}.svg" for name in names}
    for filename, digest in provenance["sha256"].items():
        assert hashlib.sha256((ASSETS / filename).read_bytes()).hexdigest() == digest, filename
    for name, digest in UPSTREAM_HASHES.items():
        assert hashlib.sha256((ASSETS / f"{name}.svg").read_bytes()).hexdigest() == digest
    license_text = (ASSETS / "LICENSE").read_text()
    assert "ISC License" in license_text
    assert "The MIT License (MIT)" in license_text
    assert "Cole Bemis" in license_text
    assert "Lucide Icons and Contributors" in license_text


def test_unknown_key_uses_canonical_circle_without_reading_a_path() -> None:
    """Khóa không hợp lệ không trở thành tên tệp hay SVG chèn ngoài."""
    for key in ["", "unknown", "../../LICENSE", '<script>alert(1)</script>']:
        assert _geometry(ET.fromstring(icon_svg(key))) == [("circle", {"cx": "12", "cy": "12", "r": "10"})]


def test_css_class_is_escaped_as_an_attribute() -> None:
    """Lớp được truyền vào không thể mở thêm thuộc tính sự kiện."""
    value = 'app-ic custom" onload="alert(1)'
    svg = ET.fromstring(icon_svg("tim-kiem", value))
    assert svg.get("class") == value
    assert "onload" not in svg.attrib


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_published_page_draws_the_icon_set(page: Path) -> None:
    """Mọi trang có đủ icon của nhóm và mục; nguồn render kiểm riêng phía trên."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    expected = 11 + sum(len(items) for _, items in SITE_NAV)
    count = len(soup.select(".app-rail .app-ic, .app-panel .app-nav-ic .app-ic"))
    assert count == expected, f"{page.name}: {count} biểu tượng, cần {expected}"
