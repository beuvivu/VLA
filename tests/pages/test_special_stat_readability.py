"""Bốn trang Đặc Biệt phải có đường đọc rõ và giữ đầy đủ bảng/bộ lọc."""

from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from pages.build_stat_pages import PAGES, render_page
from web.page_output import write_page


SLUGS = (
    "cau-giai-dac-biet", "giai-dac-biet-theo-tong",
    "cau-dac-biet-theo-bo-so", "chu-ky-dac-biet",
)
DRAWS = [{"d": "2026-10-01", "s": "00007", "n": ["07"] * 27}]


@pytest.mark.parametrize("slug", SLUGS)
def test_special_statistics_owns_the_filter_to_table_flow(tmp_path: Path, slug: str) -> None:
    """Mất bộ lọc/bảng, menu sai trang hoặc tự chèn hero/guide phải bị phát hiện."""
    spec = next(page for page in PAGES if page.slug == slug)
    target = tmp_path / f"{slug}.html"
    write_page(target, render_page(spec, DRAWS, generated="2026-10-25T00:00:00Z"))
    page = BeautifulSoup(target.read_text(), "html.parser")
    content = page.select_one(".app-specialstats-shell[data-app-workspace-guide]")
    assert content is not None
    assert len(content.select("h1")) == 1
    assert content.select_one(".app-workspace-hero, .app-workspace-guide") is None
    nav = content.select_one('nav[aria-label="Thống kê Đặc Biệt"]')
    assert nav is not None
    assert {anchor["href"] for anchor in nav.select("a")} == {f"{name}.html" for name in SLUGS}
    current = nav.select_one('[aria-current="page"]')
    assert current is not None and current["href"] == f"{slug}.html"
    controls = content.select_one(".sp-controls")
    assert controls is not None
    assert controls.select_one("#sp-count") is not None
    assert controls.select_one("#sp-clear-marks") is not None
    assert len(controls.select(".sp-chips [data-days]")) == 6
    main = content.select_one(".app-specialstats-panel #sp-grid")
    assert main is not None
    assert controls in main.find_all_previous("div")
    for table in content.select("table.sp-table"):
        region = table.find_parent(class_="sp-scroll")
        assert region is not None
        assert region.get("tabindex") == "0" and region.get("role") == "region"
        assert region.get("aria-label")
    guide = content.select_one("details.app-specialstats-method")
    assert guide is not None and not guide.has_attr("open")
    assert "thống kê lịch sử" in content.get_text(" ", strip=True).lower()
    assert page.select_one("#app-specialstats-style") is not None
    footer = page.select_one(".app-specialstats-footer")
    assert footer is not None and "2026-10-01" in footer.get_text()
    assert "máy chủ" not in footer.get_text()


def test_special_layout_keeps_the_existing_date_and_preset_modes() -> None:
    """Đổi layout không được biến mặc định Tất cả thành 90 kỳ hay bỏ ô ngày."""
    for slug in SLUGS:
        spec = next(page for page in PAGES if page.slug == slug)
        page = BeautifulSoup(render_page(spec, DRAWS, generated=""), "html.parser")
        day_mode = slug in {"cau-giai-dac-biet", "giai-dac-biet-theo-tong"}
        assert bool(page.select_one("#sp-from")) is day_mode
        assert bool(page.select_one("#sp-to")) is day_mode
        assert page.select_one(".sp-chips .on")["data-days"] == ("90" if day_mode else "0")
        assert bool(page.select_one("#sp-pair-mode")) is (slug != "giai-dac-biet-theo-tong")


@pytest.mark.parametrize("slug", ["giai-db-ngay-mai", "lo-gan", "tan-suat-loto"])
def test_special_statistics_overlay_stays_off_other_pages(slug: str) -> None:
    """Lớp riêng không được thay bố cục trang hôm sau hoặc các thống kê khác."""
    spec = next(page for page in PAGES if page.slug == slug)
    page = BeautifulSoup(render_page(spec, DRAWS, generated=""), "html.parser")
    assert page.select_one(".app-specialstats-shell, #app-specialstats-style") is None
    if slug == "giai-db-ngay-mai":
        assert page.select_one("#sp-tomorrow-number") is not None
        assert page.select_one("#sp-tomorrow-frequencies") is not None
