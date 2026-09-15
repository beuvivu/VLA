"""Regression contracts for the September 2026 targeted UI remediation.

These tests deliberately assert source-level ownership instead of brittle pixel
snapshots.  Daily builders are allowed to refresh data, but they must preserve
page boundaries, dock safe areas and the visual hierarchy introduced here.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stat_pages_expose_page_slug_for_scoped_layout() -> None:
    source = _read("src/build_stat_pages.py")
    assert "sp-page sp-page-{page.slug}" in source


def test_weekly_special_has_full_width_layout_contract() -> None:
    css = _read("src/templates/stat_pages.css")
    assert ".sp-page-bang-dac-biet .sp-scroll" in css
    assert ".sp-page-bang-dac-biet #sp-grid" in css
    assert "table-layout:fixed" in css.replace(" ", "")


def test_lo_gan_uses_bounded_detail_regions() -> None:
    source = _read("src/build_stat_pages.py")
    css = _read("src/templates/stat_pages.css")
    assert "sp-gan-dashboard" in source
    assert ".sp-page-lo-gan" in css
    assert "max-height" in css


def test_head_tail_recent_tables_are_a_responsive_grid() -> None:
    source = _read("src/build_stat_pages.py")
    css = _read("src/templates/stat_pages.css")
    assert "sp-recent-grid" in source
    assert ".sp-page-dau-duoi-loto .sp-recent-grid" in css


def test_special_sum_page_has_scoped_overflow_contract() -> None:
    source = _read("src/build_stat_pages.py")
    css = _read("src/templates/stat_pages.css")
    assert "sp-tong-dashboard" in source
    assert ".sp-page-giai-dac-biet-theo-tong" in css


def test_path_template_reserves_dock_safe_area() -> None:
    html = _read("src/templates/path_ui_page.html.j2")
    assert 'class="ui-app ui-dock-space path-page"' in html
    assert "path-shell" in html
    assert "safe-area-inset-bottom" in html


def test_path_matrix_is_bounded_and_scrollable() -> None:
    html = _read("src/templates/path_ui_page.html.j2")
    assert "path-table-scroll" in html
    assert "max-height:min(66vh,52rem)" in html.replace(" ", "")


def test_dashboard_has_command_center_shell() -> None:
    source = _read("src/build_dashboard.py")
    assert "ai-command-center" in source
    assert "ai-signal-grid" in source
    assert "ai-status-strip" in source


def test_research_lab_has_experiment_pipeline() -> None:
    source = _read("src/build_research_lab.py")
    assert "rl-pipeline" in source
    for label in ("Giả thuyết", "Huấn luyện", "Kiểm định", "Tập giữ lại", "Cổng vận hành"):
        assert label in source


def test_live_page_keeps_shared_css_and_dock_clearance() -> None:
    live = _read("docs/live.html")
    assert 'href="assets/ui.css"' in live
    assert "var(--ui-dock-h" in live
