"""Hợp đồng nguồn cho chủ đề màu đầy đủ, gồm các màu mang nghĩa dữ liệu."""
from pathlib import Path
import re

import pytest

from ui_theme import TAILWIND_LITE_CSS, contrast_ratio
import ui_page_refinements

ROOT = Path(__file__).resolve().parents[1]


def palette(dark: bool) -> dict[str, str]:
    """Đọc giá trị thật, không chép màu sản phẩm vào phép kiểm."""
    selector = ':root[data-ui-theme="dark"]' if dark else ':root'
    match = re.search(re.escape(selector) + r'\s*\{([^{}]*)\}', TAILWIND_LITE_CSS)
    assert match, selector
    return dict(re.findall(r'(--[\w-]+)\s*:\s*([^;{}]+)', match.group(1)))


def rules(css: str):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    return re.findall(r'([^{}]+)\{([^{}]*)\}', css)


def test_resolved_dark_class_shares_the_explicit_dark_palette():
    assert re.search(r':root\.dark\s*,\s*:root\[data-ui-theme="dark"\]\s*\{', TAILWIND_LITE_CSS.split('@media print')[0])
    assert palette(False)['--ui-surface'] != palette(True)['--ui-surface']


def test_page_owners_do_not_override_shared_theme_tokens_on_body():
    sources = {
        name: (ROOT / 'src/templates' / name).read_text()
        for name in ('ui_visual_system.css', 'frequency_bento.css', 'app_design.css')
    }
    sources['path refinement'] = ui_page_refinements._PATH_CSS
    sources['live refinement'] = ui_page_refinements._LIVE_CSS
    found = []
    for name, css in sources.items():
        for selector, block in rules(css):
            if re.search(r'\bbody\b|\.path-page|\.live-console', selector):
                if re.search(r'--ui-(?:bg|surface|ink|brand|ok|warn|bad)[\w-]*\s*:\s*(?:#|rgba?\()', block):
                    found.append((name, selector.strip()))
    assert not found, found


@pytest.mark.parametrize('dark', [False, True])
def test_data_state_pairs_are_readable_in_each_theme(dark):
    values = palette(dark)
    pairs = ['empty', 'special', 'mark', 'pending', 'n1', 'n2', 'n3', 'n4', 'n5']
    for name in pairs:
        bg, fg = f'--ui-{name}-bg', f'--ui-{name}-ink'
        assert bg in values and fg in values, (dark, name)
        assert contrast_ratio(values[fg], values[bg]) >= 4.5, (dark, name, values[fg], values[bg])
    assert values['--ui-empty-bg'] != values['--ui-n1-bg']
    if dark:
        assert all(max(int(values[f'--ui-n{n}-bg'][i:i + 2], 16) for i in (1, 3, 5)) < 100 for n in range(1, 6))


def test_stat_pages_get_theme_state_from_tokens_not_os_specific_rules():
    css = (ROOT / 'src/templates/stat_pages.css').read_text()
    assert 'data-theme=' not in css
    assert 'prefers-color-scheme' not in css
    assert 'body.sp-page .sp-table td.is-empty' not in css
    for selector, block in rules(css):
        if selector.strip() == '.sp-table td.is-empty':
            assert 'var(--ui-empty-bg)' in block
            break
    else:
        pytest.fail('không tìm thấy ô không về')


def test_crafto_content_surfaces_follow_theme():
    css = (ROOT / 'src/templates/app_design.css').read_text()
    samples = ('.main>.hero', '.app-hero-result', '.app-hero-mini', '.app-feature-link')
    for sample in samples:
        matches = [block for selector, block in rules(css) if selector.strip().endswith(sample) and 'background:' in block]
        assert matches, sample
        assert all(re.search(r'background:\s*(?:var|color-mix)\(', block) for block in matches), sample


def test_print_restores_readable_light_tokens_even_when_html_is_dark():
    print_css = TAILWIND_LITE_CSS[TAILWIND_LITE_CSS.index('@media print'):]
    match = re.search(r':root\.dark\s*,\s*:root\[data-ui-theme="dark"\]\s*\{([^{}]+)\}', print_css)
    assert match, 'bản in phải đặt lại bảng màu kể cả khi người đọc chọn tối'
    values = dict(re.findall(r'(--[\w-]+)\s*:\s*([^;{}]+)', match.group(1)))
    for key in ('--ui-ink', '--ui-ink-soft', '--ui-brand-ink', '--ui-ok', '--ui-warn', '--ui-bad'):
        assert contrast_ratio(values[key], values['--ui-surface']) >= 4.5
    assert values['--ui-special-ink'] == palette(False)['--ui-special-ink']


def test_legacy_neutral_utilities_inherit_the_selected_theme():
    for selector in ('.bg-white', '.bg-slate-50', '.text-slate-900', '.text-slate-600'):
        matched = [block for rule, block in rules(TAILWIND_LITE_CSS) if rule.strip() == selector]
        assert matched, selector
        assert all('var(--ui-' in block for block in matched), selector


def test_frequency_crosshair_keeps_the_data_fill_visible():
    css = (ROOT / 'src/templates/frequency_bento.css').read_text()
    matches = [block for selector, block in rules(css) if selector.strip().endswith('.bf-track::after')]
    assert matches, 'thiếu lớp dóng ma trận'
    assert all('background:transparent' in block for block in matches)


def _assert_selection_is_distinct(css, base_selector, selected_suffix):
    """So hai trạng thái thực từ CSS, kể cả màu cuối đã phân giải theo chủ đề."""
    from theme_palette_helpers import resolve_theme_colors
    for dark in (False, True):
        resolved = rules(resolve_theme_colors(css, dark))
        base = [block for selector, block in resolved if selector.strip() == base_selector and 'background:' in block]
        selected = [block for selector, block in resolved if selector.strip().replace('"', '').endswith(selected_suffix)]
        assert len(base) == 1 and len(selected) == 1, (base_selector, selected_suffix)
        declarations = [dict(re.findall(r'([\w-]+):([^;]+)', block)) for block in (base[0], selected[0])]
        plain, active = declarations
        assert active['background'] != plain['background'], (dark, selected_suffix)
        assert active['color'] != plain['color'], (dark, selected_suffix)
        assert contrast_ratio(active['color'], active['background']) >= 4.5
        assert 'inset' in active.get('box-shadow', ''), 'cần thêm viền để không chỉ phân biệt bằng màu'


@pytest.mark.parametrize('base,selected', [
    ('.bf-pair-grid button', '.bf-pair-grid button[aria-pressed=true]'),
    ('.bf-page .sp-pick', '.sp-pick.on'),
])
def test_selected_number_controls_are_distinct_and_readable(base, selected):
    css = (ROOT / 'src/templates/frequency_bento.css').read_text()
    _assert_selection_is_distinct(css, base, selected)
