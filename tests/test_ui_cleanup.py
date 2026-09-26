"""Gỡ điều hướng đã nghỉ nhưng giữ nguyên nội dung và kịch bản nghiệp vụ."""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from app_shell import wrap_page

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("selector", [".dock", ".ui-dock"])
@pytest.mark.parametrize("quote", ['"', "'"])
def test_old_dock_script_is_removed_without_eating_the_next_script(selector, quote):
    """Handler cũ biến mất; script dữ liệu kề bên và JSON phải còn nguyên."""
    business = '<script>window.businessData = [12, 34];</script>'
    data = '<script type="application/json" id="payload">{"values":[12,34]}</script>'
    old = f'<script>(function(){{var d=document.querySelector({quote}{selector}{quote});if(!d)return;}})();</script>'
    page = f'<html><head></head><body><nav class="{selector[1:]}">cũ</nav>{old}{business}{data}<main>nội dung</main></body></html>'

    result = wrap_page(page, "index.html")

    assert old not in result
    assert business in result
    assert data in result
    assert "nội dung" in result
    assert not BeautifulSoup(result, "html.parser").select("nav.dock, nav.ui-dock")


def test_business_script_mentioning_dock_is_preserved():
    """Nhắc tên lớp cũ không đủ để coi một kịch bản là handler đã nghỉ."""
    business = '<script>var legacy = document.querySelector(".ui-dock");window.businessData = [12, 34];</script>'
    page = f'<html><head></head><body><nav class="dock">cũ</nav>{business}</body></html>'
    assert business in wrap_page(page, "index.html")


@pytest.mark.parametrize("tag", ["main", "div"])
@pytest.mark.parametrize("attributes", [
    'id="app-main" class="app-main"',
    "class='app-main' id='app-main'",
    'id="app-main" data-old="true" class="legacy app-main"',
])
def test_nested_shell_with_normalized_content_tag_is_repaired(tag, attributes):
    """Khung lồng nhau vẫn phải sửa được sau lượt chuẩn hoá thuộc tính."""
    payload = '<table id="results"><tr><td>12</td><td>34</td></tr></table>'
    data = '<script type="application/json" id="payload">{"values":[12,34]}</script>'
    inner = f'<nav class="app-rail"></nav><{tag} {attributes}>{payload}{data}</{tag}>'
    page = '<html><head></head><body><nav class="app-rail"></nav><main class="app-main" id="app-main">' + inner + '</main><script defer="" src="assets/app-shell.js"></script></body></html>'

    result = wrap_page(page, "live.html")
    soup = BeautifulSoup(result, "html.parser")

    assert len(soup.select(".app-rail")) == 1
    assert len(soup.select("#app-main")) == 1
    assert len(soup.select("main")) == 1
    assert payload in result
    assert data in result
    assert wrap_page(result, "live.html") == result


def test_repair_has_no_limit_on_accumulated_legacy_shells():
    """Không để sót lớp thứ 65 sau nhiều lượt pipeline cũ."""
    payload = '<p id="payload">Dữ liệu trực tiếp</p>'
    body = payload
    for _ in range(70):
        body = '<nav class="app-rail"></nav><div class="app-main" id="app-main">' + body + '</div>'
    result = wrap_page('<html><head></head><body>' + body + '</body></html>', 'live.html')
    soup = BeautifulSoup(result, "html.parser")
    assert len(soup.select(".app-rail")) == 1
    assert len(soup.select("#app-main")) == 1
    assert payload in result


def test_retired_assets_are_removed():
    for name in ("ui-dock.js", "live-board.js"):
        assert not (ROOT / "docs/assets" / name).exists()


def test_published_pages_do_not_execute_retired_dock_handlers():
    pages = list((ROOT / "docs").glob("*.html"))
    assert pages, "không có trang xuất bản để kiểm tra"
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert 'var d=document.querySelector(".dock")' not in text, page.name
        assert 'var d=document.querySelector(".ui-dock")' not in text, page.name
