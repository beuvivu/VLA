"""Gỡ mã điều hướng đã nghỉ mà không chạm tới mã nghiệp vụ."""
from pathlib import Path

from app_shell import wrap_page

ROOT = Path(__file__).resolve().parents[1]


def test_old_dock_script_is_removed_without_eating_the_next_script():
    html = '''<html><head></head><body><nav class="dock">old</nav>
<script>(function(){var d=document.querySelector(".dock");if(!d)return;})();</script>
<script>window.businessData = [12, 34];</script><main>nội dung</main></body></html>'''
    result = wrap_page(html, "index.html")
    assert 'querySelector(".dock")' not in result
    assert 'window.businessData = [12, 34];' in result
    assert 'nội dung' in result


def test_published_pages_do_not_execute_retired_dock_handlers():
    pages = list((ROOT / "docs").glob("*.html"))
    assert len(pages) >= 29
    for page in pages:
        text = page.read_text()
        assert 'var d=document.querySelector(".dock")' not in text, page.name
        assert 'var d=document.querySelector(".ui-dock")' not in text, page.name


def test_retired_assets_are_removed():
    for name in ("ui-dock.js", "live-board.js"):
        assert not (ROOT / "docs/assets" / name).exists()


def test_nested_shell_with_normalized_div_is_repaired():
    """Lượt dựng cũ đã đổi main bên trong thành div và đảo thuộc tính."""
    from app_shell import header_html, panel_html, rail_html
    page = wrap_page('<html><head></head><body><p id="payload">Nội dung thật</p></body></html>', 'live.html')
    inner = page.split('<body>', 1)[1].split('</body>', 1)[0]
    inner = inner.replace('<main class="app-main" id="app-main">', '<div id="app-main" class="app-main">').replace('</main>', '</div>')
    broken = '<html><head></head><body>' + rail_html('live.html') + panel_html('live.html') + header_html('live.html') + '<main class="app-main" id="app-main">' + inner + '</main></body></html>'
    result = wrap_page(broken, 'live.html')
    assert result.count('class="app-rail"') == 1
    assert result.count('id="app-main"') == 1
    assert '<p id="payload">Nội dung thật</p>' in result
    assert wrap_page(result, 'live.html') == result


def test_research_builder_still_imports_after_dock_retirement():
    """Trình dựng nghiên cứu là caller độc lập trong pipeline hằng ngày."""
    import importlib
    module = importlib.import_module('build_research_lab')
    assert callable(module.main)


def test_repeated_legacy_builds_do_not_leave_nested_shells():
    """Bản trực tiếp đã có 11 lớp sau các lượt dựng; không dừng ở lớp thứ 8."""
    from app_shell import header_html, panel_html, rail_html
    body = '<p id="payload">Dữ liệu trực tiếp</p>'
    for _ in range(12):
        body = rail_html('live.html') + panel_html('live.html') + header_html('live.html') + '<div class="app-main" id="app-main">' + body + '</div>'
    result = wrap_page('<html><head></head><body>' + body + '</body></html>', 'live.html')
    assert result.count('class="app-rail"') == 1
    assert '<p id="payload">Dữ liệu trực tiếp</p>' in result
