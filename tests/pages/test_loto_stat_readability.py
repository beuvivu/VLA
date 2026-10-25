"""Ba trang LOTO có đường đọc chung và giữ đủ bảng, bộ lọc hiện có."""

from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from pages.build_stat_pages import PAGES, render_page
from web.page_output import write_page


SLUGS = ("dau-duoi-loto", "cap-lon-loto", "lo-gan")
TABLES = {
    "dau-duoi-loto": {"sp-head", "sp-tail", "sp-day-head", "sp-day-tail", "sp-day-sum"},
    "cap-lon-loto": {"sp-grid", "sp-kep"},
    "lo-gan": {"sp-grid", "sp-max-lo", "sp-max-hi", "sp-pair-gan"},
}
DRAWS = [{"d": "2026-10-01", "s": "00007", "n": ["07"] * 27}]


@pytest.mark.parametrize("slug", SLUGS)
def test_loto_statistics_owns_filters_and_all_accessible_tables(tmp_path: Path, slug: str) -> None:
    """Bỏ sót bảng hoặc để lớp bọc chèn hero/hướng dẫn lặp phải làm đỏ."""
    spec = next(page for page in PAGES if page.slug == slug)
    target = tmp_path / f"{slug}.html"
    write_page(target, render_page(spec, DRAWS, generated="2026-10-25T00:00:00Z"))
    page = BeautifulSoup(target.read_text(), "html.parser")
    content = page.select_one(".app-lotostats-shell[data-app-workspace-guide]")
    assert content is not None
    assert page.body is not None and "app-lotostats-page" in page.body["class"]
    assert len(content.select("h1")) == 1
    assert content.select_one(".app-workspace-hero, .app-workspace-guide") is None
    nav = content.select_one('nav[aria-label="Thống kê LOTO"]')
    assert nav is not None
    assert {anchor["href"] for anchor in nav.select("a")} == {f"{name}.html" for name in SLUGS}
    assert nav.select_one('[aria-current="page"]')["href"] == f"{slug}.html"
    controls = content.select_one(".sp-controls")
    assert controls is not None
    assert controls.select_one("#sp-count") is not None
    assert controls.select_one("#sp-clear-marks") is not None
    assert len(controls.select(".sp-chips [data-days]")) == 6
    assert {table["id"] for table in content.select("table.sp-table")} == TABLES[slug]
    for table in content.select("table.sp-table"):
        assert controls in table.find_all_previous("div")
        region = table.find_parent(class_="sp-scroll")
        assert region is not None and region.get("tabindex") == "0"
        assert region.get("role") == "region" and region.get("aria-label")
    method = content.select_one("details.app-lotostats-method")
    assert method is not None and not method.has_attr("open")
    assert "thống kê lịch sử" in method.get_text(" ", strip=True).lower()
    assert page.select_one("#app-lotostats-style") is not None
    footer = page.select_one(".app-lotostats-footer")
    assert footer is not None and "2026-10-01" in footer.get_text()


def test_loto_statistics_keeps_existing_range_and_pair_modes() -> None:
    """Đổi bố cục không đổi mặc định của bộ chọn ngày và preset."""
    for slug in SLUGS:
        spec = next(page for page in PAGES if page.slug == slug)
        page = BeautifulSoup(render_page(spec, DRAWS, generated=""), "html.parser")
        assert bool(page.select_one("#sp-from")) is (slug != "lo-gan")
        assert bool(page.select_one("#sp-to")) is (slug != "lo-gan")
        assert page.select_one(".sp-chips .on")["data-days"] == ("0" if slug == "lo-gan" else "90")
        assert bool(page.select_one("#sp-pair-mode")) is (slug != "dau-duoi-loto")


def test_loto_gap_panels_explain_selected_and_full_history_scopes() -> None:
    """Các bảng cực đại toàn lịch sử cần tên miền số riêng, không dùng phạm vi lọc."""
    spec = next(page for page in PAGES if page.slug == "lo-gan")
    page = BeautifulSoup(render_page(spec, DRAWS, generated=""), "html.parser")
    history = page.select_one(".app-lotostats-history")
    assert history is not None
    assert "toàn bộ lịch sử" in history.get_text(" ", strip=True).lower()
    for table_id, numbers in (("sp-max-lo", "00–49"), ("sp-max-hi", "50–99")):
        panel = page.select_one(f"#{table_id}").find_parent("section")
        assert panel is not None and numbers in panel.get_text(" ", strip=True)
    assert "kỳ quay" in page.get_text() and "ngày lịch" in page.get_text()


@pytest.mark.parametrize("slug", ["cau-giai-dac-biet", "giai-db-ngay-mai", "tan-suat-loto"])
def test_loto_overlay_is_scoped_to_the_three_pages(slug: str) -> None:
    """Các trang đã thiết kế trước không nhận bố cục hay CSS LOTO mới."""
    spec = next(page for page in PAGES if page.slug == slug)
    page = BeautifulSoup(render_page(spec, DRAWS, generated=""), "html.parser")
    assert page.select_one(".app-lotostats-shell, #app-lotostats-style") is None
