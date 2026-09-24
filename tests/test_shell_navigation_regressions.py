"""Chặn lỗi đã quan sát trên điều hướng đang xuất bản."""
from bs4 import BeautifulSoup
import pytest
from app_shell import header_html, panel_html, wrap_page


def test_home_breadcrumb_does_not_use_the_last_anchor_label():
    soup = BeautifulSoup(header_html('index.html'), 'html.parser')
    assert soup.select_one('.app-crumb--now').get_text() == 'Kết quả hôm nay'


@pytest.mark.parametrize('page', ['index.html', 'landing.html', 'landing_desktop.html'])
def test_only_the_canonical_home_link_is_current(page):
    soup = BeautifulSoup(panel_html(page), 'html.parser')
    assert [a['href'] for a in soup.select('[aria-current="page"]')] == ['index.html']


@pytest.mark.parametrize('attrs', ['class="dock" aria-label="Điều hướng chính"',
    'aria-label="Điều hướng chính" class="ui-dock"', "class='dock extra'"])
def test_wrapping_removes_both_legacy_docks_without_removing_content(attrs):
    source = f'<html><head></head><body><main id="results">Dữ liệu</main><nav {attrs}><div>Menu cũ</div></nav><script>window.keep = true;</script></body></html>'
    result = wrap_page(source, 'index.html')
    soup = BeautifulSoup(result, 'html.parser')
    assert not soup.select('nav.dock, nav.ui-dock')
    assert soup.select_one('#results').get_text() == 'Dữ liệu'
    assert 'window.keep = true' in result
    assert len(soup.select('main')) == 1
    assert wrap_page(result, 'index.html') == result
