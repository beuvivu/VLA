"""Tra cứu hôm sau phải giải thích đúng phép đối chiếu lịch sử."""
import json
import re
from pathlib import Path

from pages.build_stat_pages import PAGES, render_page
from web.evidence_catalog import registry

ROOT = Path(__file__).resolve().parents[2]


def test_tomorrow_evidence_describes_calendar_successor_not_gap_ranking():
    text=json.dumps(registry('giai-db-ngay-mai.html'),ensure_ascii=False)
    assert 'ngày lịch kế tiếp' in text
    assert 'cùng hai số cuối' in text
    assert 'dựng từ chu kỳ và tần suất' not in text


def test_tomorrow_history_scroll_is_named_and_keyboard_accessible():
    page = next(page for page in PAGES if page.slug == 'giai-db-ngay-mai')
    markup = render_page(page, [], generated='2026-01-06T20:00:00Z')
    assert 'app-tomorrow-card app-tomorrow-history' in markup
    assert re.search(r'<div class="sp-scroll" tabindex="0" role="region" '
                     r'aria-label="[^"]+"><table[^>]+id="sp-grid"', markup)
    assert 'LOTO' in page.subtitle


def test_tomorrow_cards_share_natural_height_without_the_global_scroll_ceiling():
    css = (ROOT / 'src/web/templates/tomorrow_history.css').read_text()
    workspace = re.search(r'\.app-tomorrow-workspace\{([^}]+)\}', css).group(1)
    assert 'grid-template-columns:repeat(2,minmax(0,1fr))' in workspace
    assert 'align-items:stretch' in workspace
    history = re.search(r'\.app-tomorrow-history\{([^}]+)\}', css).group(1)
    assert 'grid-template-rows:auto minmax(0,1fr)' in history
    viewport = re.search(r'body\.app-tomorrow-page \.app-tomorrow-history \.sp-scroll\{([^}]+)\}', css).group(1)
    assert 'contain:size' in viewport
    assert 'max-height:none' in viewport
    assert 'min-height:0' in viewport
    assert 'overflow:auto' in viewport
    assert 'width:100%' in viewport
    assert re.search(r'@media\(max-width:1050px\).*contain:none', css)
    assert not re.search(r'[^{}]*nth-child\(4\)[^{]*\{[^}]*display:none', css)
