"""Hợp đồng trình bày cho các trang phân tích, không thay nghiệp vụ."""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from web.analysis_workspace import refine_workspace, workspace_pages
from web.ui_page_refinements import refine_page
from web.app_shell import wrap_page


class _Contract(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.ids = []
        self.controls = []
        self.links = []
        self.guides = []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id') and tag != 'style':
            self.ids.append(values['id'])
        if tag in {'form', 'input', 'select', 'option', 'button'}:
            self.controls.append((tag, tuple((k, v) for k, v in attrs if k != 'class')))
        if tag == 'a':
            self.links.append(values.get('href'))
        if 'data-app-workspace-guide' in values:
            self.guides.append((tag, values.get('class', '').split()))


def test_workspace_covers_actual_navigation_but_excludes_other_owners():
    from web.ui_theme import SITE_NAV_SECTIONS
    for group, sections in SITE_NAV_SECTIONS:
        if group not in {'Soi cầu', 'Dự báo', 'Nghiên cứu & công cụ'}:
            continue
        for _, links in sections:
            for href, _, _ in links:
                if not href.startswith('index.html'):
                    assert href.split('#')[0] in workspace_pages()
    for name in {'index.html', 'landing.html', 'landing_desktop.html', 'tan-suat-loto.html', 'tan-suat-cap-loto.html', 'statistics.html'}:
        sample = '<html><head></head><body><h1>Mẫu</h1></body></html>'
        assert refine_workspace(name, sample) == sample


@pytest.mark.parametrize('name', sorted(workspace_pages()))
def test_actual_pages_keep_ids_controls_data_scripts_and_existing_links(name):
    source = (ROOT / 'docs' / name).read_text(encoding='utf-8')
    result = refine_page(name, source)
    before, after = _Contract(source), _Contract(result)
    assert before.ids == after.ids
    assert before.controls == after.controls
    assert all(href in after.links for href in before.links)
    assert re.findall(r'<script\b.*?</script>', source, re.S) == re.findall(r'<script\b.*?</script>', result, re.S)
    assert result == refine_page(name, result)
    assert result.count('data-app-workspace-guide') == 1
    assert result.count('id="app-analysis-workspace-style"') == 1
    # Các trang có hướng dẫn riêng giữ khối gọn của mình, không bị thêm lại
    # thẻ hướng dẫn chung. Những trang còn lại vẫn phải có đúng khối chung.
    guide_tag, guide_class = {
        'giai-db-ngay-mai.html': ('div', 'app-tomorrow-shell'),
        'ml_top10_de.html': ('details', 'app-lab-guide'),
        'ml_top10_loto.html': ('details', 'app-lab-guide'),
        'soi-cau-vi-tri.html': ('ol', 'app-position-steps'),
        'soi-path-loto-active.html': ('ol', 'path-steps'),
        'soi-path-loto-stable.html': ('ol', 'path-steps'),
        'soi-path-de-active.html': ('ol', 'path-steps'),
        'soi-path-de-stable.html': ('ol', 'path-steps'),
        'cau-giai-dac-biet.html': ('div', 'app-specialstats-shell'),
        'giai-dac-biet-theo-tong.html': ('div', 'app-specialstats-shell'),
        'cau-dac-biet-theo-bo-so.html': ('div', 'app-specialstats-shell'),
        'chu-ky-dac-biet.html': ('div', 'app-specialstats-shell'),
        'dau-duoi-loto.html': ('div', 'app-lotostats-shell'),
        'cap-lon-loto.html': ('div', 'app-lotostats-shell'),
        'lo-gan.html': ('div', 'app-lotostats-shell'),
    }.get(name, ('aside', 'app-workspace-guide'))
    assert len(after.guides) == 1
    assert after.guides[0][0] == guide_tag
    assert guide_class in after.guides[0][1]


def test_wrapped_refresh_keeps_the_guide_inside_the_single_content_shell():
    source = (ROOT / 'docs' / 'dau-duoi-loto.html').read_text(encoding='utf-8')
    once = wrap_page(refine_page('dau-duoi-loto.html', source), current='dau-duoi-loto.html')
    twice = wrap_page(refine_page('dau-duoi-loto.html', once), current='dau-duoi-loto.html')
    assert once == twice
    assert once.index('id="app-main"') < once.index('data-app-workspace-guide') < once.rindex('</main>')
    assert once.count('id="app-main"') == 1


def test_raw_detail_has_a_real_hero_filter_heading_and_keyboard_scroll_region():
    source = '<html><head></head><body><div class="ui-shell"><h1>Đầu đuôi</h1><p>Mô tả</p><div class="sp-controls"><label>Từ ngày<input type="date" id="sp-from"></label></div><div class="sp-scroll"><table id="sp-head"></table></div></div></body></html>'
    result = refine_page('dau-duoi-loto.html', source)
    assert '<header class="app-workspace-hero">' in result
    assert '<h2>Chọn dữ liệu cần xem</h2>' in result
    assert 'tabindex="0" role="region" aria-label="Bảng phân tích có thể cuộn"' in result
    assert 'href="soi-cau-vi-tri.html"' in result
    assert 'href="model-quality.html"' in result
    assert result == refine_page('dau-duoi-loto.html', result)


def test_layout_contract_keeps_preferred_number_colour_and_mobile_grids():
    css = (ROOT / 'src/web/templates/analysis_workspace.css').read_text()
    assert '--app-workspace-accent:var(--ui-brand-ink)' in css
    assert 'grid-template-columns:repeat(2,minmax(0,1fr))' in css
    assert 'grid-template-columns:repeat(5,minmax(0,1fr))' in css
    assert '@media(prefers-reduced-motion:reduce)' in css
    assert '.app-main' not in css
