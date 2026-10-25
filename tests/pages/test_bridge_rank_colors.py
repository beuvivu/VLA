"""Màu ba mức số đường cầu chỉ dành cho LOTO và hai nháy, từ tám đường trở lên."""

from copy import deepcopy
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from pages import build_bridge_pages as page
from soi_cau.bridge_rules import RULES

ROOT = Path(__file__).resolve().parents[2]
COUNTS = {"00": 20, "01": 20, "02": 12, "03": 9, "04": 8, "05": 7, "06": 1}
EXPECTED = {"00": 1, "01": 1, "02": 2, "03": 3}


@pytest.mark.parametrize("key", ["loto", "hai-nhay"])
def test_static_cells_rank_distinct_counts_and_keep_ties(key: str) -> None:
    before = deepcopy(COUNTS)
    grid = BeautifulSoup(page.static_grid(COUNTS, rule_key=key), "html.parser")
    ranked = {cell.select_one("b").get_text(): int(cell["data-cau-rank"])
              for cell in grid.select(".app-cau-cell[data-cau-rank]")}
    assert ranked == EXPECTED
    assert COUNTS == before
    assert grid.select_one('.app-cau-cell[data-number="05"]').get_text(" ", strip=True) == "05 7 cầu"


def test_eight_paths_qualify_but_seven_do_not() -> None:
    grid = BeautifulSoup(page.static_grid({"07": 7, "08": 8}, rule_key="loto"), "html.parser")
    assert grid.select_one('[data-number="07"]').get("data-cau-rank") is None
    assert grid.select_one('[data-number="08"]')["data-cau-rank"] == "1"


@pytest.mark.parametrize("key", list(RULES))
def test_only_two_requested_pages_publish_colors_and_a_plain_legend(key: str) -> None:
    report = page.load(ROOT / "data")
    report["rules"][key]["counts"] = COUNTS
    soup = BeautifulSoup(page.render(key, report), "html.parser")
    legend = soup.select_one(".app-cau-rank-legend")
    if key in {"loto", "hai-nhay"}:
        assert legend is not None
        text = legend.get_text(" ", strip=True)
        assert all(label in text for label in ("Nhất", "Nhì", "Ba", ">7 đường cầu"))
        assert "không phải độ tin cậy" in text.lower()
        assert len(soup.select("#app-cau-grid [data-cau-rank]")) == 4
    else:
        assert legend is None
        assert not soup.select("[data-cau-rank]")


def test_rank_palette_uses_readable_theme_pairs_and_keeps_selected_data_colors() -> None:
    css = page.page_css()
    for rank in (1, 2, 3):
        assert f'--app-cau-rank-bg:var(--ui-n{rank}-bg)' in css
        assert f'--app-cau-rank-ink:var(--ui-n{rank}-ink)' in css
    assert ':is(:hover,:focus-visible,[aria-pressed="true"])' in css
    assert 'background:var(--app-cau-rank-bg)' in css
    assert 'color:var(--app-cau-rank-ink)' in css
