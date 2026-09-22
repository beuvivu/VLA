"""Source-level contracts for the VLA UI redesign.

The contracts ensure the visible redesign is owned by reviewable source files,
not only by a generated HTML snapshot. Path pages own their structure directly
in Jinja; long detail-statistics pages own their durable layout in a dedicated
source stylesheet that the page-output boundary applies by filename.
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
    assert '--bg:#f0f4fd' in source
    assert 'color-scheme:dark' not in source


def test_detail_statistics_layout_is_source_owned_and_wired_at_output() -> None:
    output_source = (ROOT / "src" / "page_output.py").read_text(encoding="utf-8")
    detail_css = ROOT / "src" / "templates" / "stat_detail_pages.css"

    assert detail_css.exists()
    assert '"stat_detail_pages.css"' in output_source
    assert "_inject_source_detail_style(path, refined)" in output_source
    assert 'id="{_SOURCE_DETAIL_STYLE_ID}"' in output_source


def test_detail_statistics_stylesheet_covers_every_reported_layout_problem() -> None:
    source = (ROOT / "src" / "templates" / "stat_detail_pages.css").read_text(encoding="utf-8")

    assert ".sp-detail-hero" in source
    assert ".sp-page-bang-dac-biet #sp-grid" in source
    assert "table-layout:fixed" in source
    assert ".sp-page-lo-gan .sp-scroll" in source
    assert "max-height:34rem" in source
    assert ".sp-page-dau-duoi-loto .sp-recent-grid" in source
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in source
    assert ".sp-page-giai-dac-biet-theo-tong .sp-scroll" in source
    assert ".sp-page-cau-dac-biet-theo-bo-so .sp-scroll" in source
    assert ".sp-page-giai-db-ngay-mai .sp-scroll" in source
    assert ".sp-page-cap-lon-loto .sp-scroll" in source


def test_dashboard_builder_owns_command_center_structure() -> None:
    source = (ROOT / "src" / "build_dashboard.py").read_text(encoding="utf-8")

    assert '<body class="ai-command-center">' in source
    assert 'class="ai-status-strip"' in source
    assert 'class="ui-grid ai-signal-grid"' in source
    assert "AI/ML Command Center" in source
    assert ".ai-command-center .ui-header" in source


def test_research_builder_owns_core_lab_structure() -> None:
    source = (ROOT / "src" / "build_research_lab.py").read_text(encoding="utf-8")

    assert 'class="rl-hero"' in source
    assert 'class="rl-metrics"' in source
    assert 'class="metric-card"' in source
    assert "Tường lửa nghiên cứu" in source
    assert "không được nối vào trọng số vận hành" in source
