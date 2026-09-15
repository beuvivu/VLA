"""Regression contracts for the September 2026 targeted UI remediation.

The daily pipeline rebuilds published pages from multiple independent builders.
These tests exercise the single output-boundary refinement layer so the layout
contract remains stable even when data payloads and timestamps change.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ui_page_refinements import refine_page  # noqa: E402


def _doc(body: str, *, head: str = "") -> str:
    return f"<!doctype html><html><head>{head}</head><body>{body}</body></html>"


def test_page_output_routes_every_page_through_refinement_layer() -> None:
    source = (ROOT / "src" / "page_output.py").read_text(encoding="utf-8")
    assert "from ui_page_refinements import refine_page" in source
    assert "refine_page(path, html)" in source


def test_weekly_special_fills_the_box_without_global_table_regression() -> None:
    out = refine_page(
        "bang-dac-biet.html",
        _doc('<div class="sp-scroll"><table id="sp-grid"></table></div>'),
    )
    assert "sp-page-bang-dac-biet" in out
    assert ".sp-page-bang-dac-biet .sp-scroll{width:100%" in out
    assert "table-layout:fixed" in out
    assert "min-width:760px" in out


def test_lo_gan_uses_bounded_detail_regions() -> None:
    out = refine_page("lo-gan.html", _doc('<div class="sp-scroll"><table id="sp-grid"></table></div>'))
    assert "sp-page-lo-gan" in out
    assert "sp-gan-dashboard" in out
    assert ".sp-page-lo-gan .sp-scroll:has(#sp-grid)" in out
    assert "max-height:34rem" in out


def test_head_tail_recent_tables_are_a_responsive_grid() -> None:
    recent = (
        '<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐẦU</h3>'
        '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-head"></table></div>'
        '<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐUÔI (đít)</h3>'
        '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-tail"></table></div>'
        '<h3 class="sp-subhead">20 kỳ gần nhất theo TỔNG</h3>'
        '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-sum"></table></div>'
    )
    out = refine_page("dau-duoi-loto.html", _doc(recent))
    assert "sp-page-dau-duoi-loto" in out
    assert '<div class="sp-recent-grid">' in out
    assert out.count('class="sp-recent-card"') == 3
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in out


def test_special_sum_page_has_scoped_overflow_contract() -> None:
    out = refine_page("giai-dac-biet-theo-tong.html", _doc('<table id="sp-trans"></table>'))
    assert "sp-page-giai-dac-biet-theo-tong" in out
    assert "sp-tong-dashboard" in out
    assert ".sp-page-giai-dac-biet-theo-tong .sp-scroll" in out
    assert "max-height:38rem" in out


def test_path_pages_reserve_dock_safe_area_and_bound_the_route_matrix() -> None:
    source = _doc(
        '<div class="wrap"><div class="top">hero</div>'
        '<div class="grid" style="margin-top:12px"></div>'
        '<div style="margin-top:10px; overflow:auto"><table></table></div></div>'
    )
    out = refine_page("soi-path-de-active.html", source)
    assert "ui-dock-space path-page" in out
    assert "wrap path-shell" in out
    assert "top path-hero" in out
    assert "grid path-overview" in out
    assert "path-table-scroll" in out
    assert "safe-area-inset-bottom" in out
    assert "max-height:min(66vh,52rem)" in out


def test_loto_and_de_active_pages_share_the_same_path_layout_contract() -> None:
    source = _doc('<div class="wrap"><div class="top"></div></div>')
    loto = refine_page("soi-path-loto-active.html", source)
    special = refine_page("soi-path-de-active.html", source)
    for token in ("path-page", "path-shell", "path-hero", "vla-targeted-ui-refinement"):
        assert token in loto
        assert token in special


def test_dashboard_has_command_center_hierarchy() -> None:
    out = refine_page(
        "dashboard.html",
        _doc('<header class="ui-header"><h1>Dashboard</h1></header><div class="ui-grid"></div>'),
    )
    assert "ai-command-center" in out
    assert "ai-status-strip" in out
    assert "ai-signal-grid" in out
    assert "AI/ML Command Center" in out


def test_research_lab_has_experiment_pipeline_and_keeps_note_markup_valid() -> None:
    out = refine_page(
        "research-lab.html",
        _doc('<section class="rl-hero"></section>\n<div class="ui-note">Firewall</div><div class="ui-grid"></div>'),
    )
    assert "research-workspace" in out
    assert "rl-pipeline" in out
    assert "rl-instruments" in out
    assert '<div class="ui-note">' in out
    for label in ("Giả thuyết", "Huấn luyện", "Kiểm định", "Tập giữ lại", "Cổng vận hành"):
        assert label in out


def test_live_console_gets_shared_dock_clearance_without_touching_polling_logic() -> None:
    script = '<script>function poll(){return "keep-me"}</script>'
    out = refine_page("live.html", _doc('<div class="wrap"></div>', head=script))
    assert "live-console" in out
    assert "safe-area-inset-bottom" in out
    assert 'function poll(){return "keep-me"}' in out


def test_refinement_is_noop_for_unrelated_pages() -> None:
    source = _doc("<main>untouched</main>")
    assert refine_page("index.html", source) == source
