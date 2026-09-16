"""Source-level contracts for the VLA UI redesign.

These tests deliberately inspect the builders/templates rather than generated
HTML. A post-render CSS overlay can make snapshots contain new tokens while the
underlying layout remains unchanged; these contracts prevent that regression.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_path_template_owns_light_dock_safe_bento_structure() -> None:
    source = (ROOT / "src" / "templates" / "path_ui_page.html.j2").read_text(encoding="utf-8")

    assert '<body class="ui-app ui-dock-space path-page">' in source
    assert '<div class="wrap path-shell">' in source
    assert '<div class="top path-hero">' in source
    assert 'class="grid path-overview"' in source
    assert 'class="path-table-scroll"' in source
    assert '--bg:#F4F5FF' in source
    assert 'color-scheme:dark' not in source


def test_detailed_stat_pages_have_source_level_bento_shell() -> None:
    source = (ROOT / "src" / "build_stat_pages.py").read_text(encoding="utf-8")

    assert "def detail_bento_layout(" in source
    assert 'class="sp-detail-hero"' in source
    assert 'class="sp-detail-content"' in source
    assert 'sp-page-{page.slug}' in source


def test_stat_stylesheet_owns_detail_page_layout_rules() -> None:
    source = (ROOT / "src" / "templates" / "stat_pages.css").read_text(encoding="utf-8")

    assert ".sp-detail-hero" in source
    assert ".sp-page-bang-dac-biet #sp-grid" in source
    assert ".sp-page-lo-gan .sp-scroll" in source
    assert ".sp-page-dau-duoi-loto .sp-recent-grid" in source
    assert ".sp-page-giai-dac-biet-theo-tong .sp-scroll" in source
