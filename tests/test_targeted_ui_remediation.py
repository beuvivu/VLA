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


def test_page_output_routes_every_page_through_refinement_layer(tmp_path: Path, monkeypatch) -> None:
    import page_output

    calls: dict[str, object] = {}

    def fake_refine(path: Path, html: str) -> str:
        calls["path"] = path
        calls["html"] = html
        return "<!doctype html><html><body>refined-output</body></html>"

    monkeypatch.setattr(page_output, "refine_page", fake_refine)
    target = tmp_path / "sample.html"
    original = "<!doctype html><html><!-- remove-me --><body>original</body></html>"

    page_output.write_page(target, original)

    written = target.read_text(encoding="utf-8")
    assert calls == {"path": target, "html": original}
    assert "refined-output" in written
    assert "original" not in written
    assert "<!--" not in written


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
    assert ".sp-page-lo-gan .sp-scroll{width:100%" in out
    assert "max-height:34rem" in out
    assert "overscroll-behavior:contain" in out


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


def test_additional_requested_stat_pages_share_master_bento_contract() -> None:
    for filename, slug in (
        ("cau-dac-biet-theo-bo-so.html", "cau-dac-biet-theo-bo-so"),
        ("giai-db-ngay-mai.html", "giai-db-ngay-mai"),
        ("cap-lon-loto.html", "cap-lon-loto"),
    ):
        out = refine_page(filename, _doc('<div class="sp-scroll"><table id="sp-grid"></table></div>'))
        assert f"sp-page-{slug}" in out
        assert "linear-gradient(135deg,#F4F5FF" in out
        assert "rgba(255,255,255,.88)" in out
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
    assert "--bg:#F4F5FF" in out
    assert "#E2E8F0" in out


def test_loto_and_de_active_pages_share_the_same_path_layout_contract() -> None:
    source = _doc('<div class="wrap"><div class="top"></div></div>')
    loto = refine_page("soi-path-loto-active.html", source)
    special = refine_page("soi-path-de-active.html", source)
    for token in ("path-page", "path-shell", "path-hero", "vla-targeted-ui-refinement"):
        assert token in loto
        assert token in special


def test_dashboard_has_glass_command_center_hierarchy() -> None:
    out = refine_page(
        "dashboard.html",
        _doc('<header class="ui-header"><h1>Dashboard</h1></header><div class="ui-grid"></div>'),
    )
    assert "ai-command-center" in out
    assert "ai-status-strip" in out
    assert "ai-signal-grid" in out
    assert "AI/ML Command Center" in out
    assert "backdrop-filter:blur(18px)" in out
    assert "linear-gradient(90deg,#4f46e5" in out


def test_research_lab_has_cyber_experiment_workspace_without_fake_probability() -> None:
    out = refine_page(
        "research-lab.html",
        _doc('<section class="rl-hero"></section>\n<div class="ui-note">Firewall</div><div class="ui-grid"></div>'),
    )
    assert "research-workspace" in out
    assert "rl-pipeline" in out
    assert "rl-console" in out
    assert "rl-instruments" in out
    assert "LIVE AI PROCESSING" in out
    assert "Bảng tham số thuật toán AI" in out
    assert "Khung chạy Backtest mô phỏng" in out
    assert "Ma trận ma sát số &amp; bóng" in out
    assert "CONFIDENCE SCORE GAUGE" in out
    assert "Gauge là trạng thái cổng kiểm chứng, không phải xác suất trúng" in out
    assert '</section><section class="rl-pipeline"' in out
    assert '<div class="ui-note">' in out
    for label in ("Giả thuyết", "Huấn luyện", "Kiểm định", "Tập giữ lại", "Cổng vận hành"):
        assert label in out


def test_live_console_becomes_bento_without_touching_polling_logic() -> None:
    body = (
        '<div class="wrap">'
        '<div class="top" style="margin-bottom:4px">hero</div>'
        '<div class="card">status</div><div class="card">results</div><div class="card">sources</div>'
        '</div>'
    )
    script = '<script>function poll(){return "keep-me"}</script>'
    out = refine_page("live.html", _doc(body, head=script))
    assert "live-console" in out
    assert "live-status-card" in out
    assert "live-results-card" in out
    assert "live-sources-card" in out
    assert "grid-template-columns:repeat(12,minmax(0,1fr))" in out
    assert "safe-area-inset-bottom" in out
    assert "#FEE2E2" in out
    assert "#E2E8F0" in out
    assert 'function poll(){return "keep-me"}' in out


def test_refinement_is_idempotent_for_structural_classes() -> None:
    source = _doc(
        '<div class="wrap"><div class="top" style="margin-bottom:4px"></div>'
        '<div class="card"></div><div class="card"></div><div class="card"></div></div>'
    )
    once = refine_page("live.html", source)
    twice = refine_page("live.html", once)
    assert twice.count("live-status-card") == once.count("live-status-card")
    assert twice.count("live-results-card") == once.count("live-results-card")
    assert twice.count("live-sources-card") == once.count("live-sources-card")
    assert twice.count('id="vla-targeted-ui-refinement"') == 1


def test_refinement_is_noop_for_unrelated_pages() -> None:
    source = _doc("<main>untouched</main>")
    assert refine_page("index.html", source) == source