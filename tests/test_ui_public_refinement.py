from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ui_page_refinements import _LEGACY_STYLE_IDS, _STYLE_ID, refine_page  # noqa: E402


def _doc(body: str) -> str:
    return f"<!doctype html><html><head></head><body>{body}</body></html>"


def test_page_output_applies_refinement_before_writing() -> None:
    source = (ROOT / "src" / "page_output.py").read_text(encoding="utf-8")
    assert "from ui_page_refinements import refine_page" in source
    assert "refine_page(path, html)" in source


def test_weekly_special_table_gets_full_width_contract() -> None:
    out = refine_page("bang-dac-biet.html", _doc('<div class="sp-scroll"><table id="sp-grid"></table></div>'))
    assert "sp-page-bang-dac-biet" in out
    assert ".sp-page-bang-dac-biet .sp-scroll{width:100%" in out
    assert "table-layout:fixed" in out
    assert ".sp-page-bang-dac-biet #sp-grid td:first-child{text-align:left}" not in out


def test_long_statistics_pages_get_bounded_scroll() -> None:
    for filename in ("lo-gan.html", "cau-dac-biet-theo-bo-so.html", "giai-db-ngay-mai.html", "cap-lon-loto.html"):
        out = refine_page(filename, _doc('<div class="sp-scroll"><table id="sp-grid"></table></div>'))
        assert "max-height:" in out
        assert "overflow:auto" in out


def test_head_tail_recent_tables_become_bento_grid() -> None:
    body = (
        '<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐẦU</h3><div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-head"></table></div>'
        '<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐUÔI (đít)</h3><div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-tail"></table></div>'
        '<h3 class="sp-subhead">20 kỳ gần nhất theo TỔNG</h3><div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-sum"></table></div>'
    )
    out = refine_page("dau-duoi-loto.html", _doc(body))
    assert 'class="sp-recent-grid"' in out
    assert out.count('class="sp-recent-card"') == 3


def test_path_pages_are_light_dock_safe_and_bounded() -> None:
    src = _doc('<div class="wrap"><div class="top"></div><div class="grid" style="margin-top:12px"></div><div style="margin-top:10px; overflow:auto"><table></table></div></div>')
    for filename in ("soi-path-loto-active.html", "soi-path-loto-stable.html", "soi-path-de-active.html", "soi-path-de-stable.html"):
        out = refine_page(filename, src)
        assert "path-page" in out
        assert "path-shell" in out
        assert "path-table-scroll" in out
        assert "safe-area-inset-bottom" in out
        assert "#F4F5FF" in out


def test_dashboard_research_and_live_receive_distinct_shells() -> None:
    dash = refine_page("dashboard.html", _doc('<header class="ui-header"></header><div class="ui-grid"></div>'))
    assert "ai-command-center" in dash and "ai-status-strip" in dash

    research = refine_page("research-lab.html", _doc('<section class="rl-hero"></section>\n<div class="ui-note">x</div><div class="ui-grid"></div>'))
    assert "research-workspace" in research and "rl-pipeline" in research and "LIVE AI PROCESSING" in research

    live = refine_page("live.html", _doc('<div class="wrap"><div class="top" style="margin-bottom:4px"></div><div class="card"></div><div class="card"></div><div class="card"></div></div>'))
    assert "live-console" in live
    assert "live-status-card" in live and "live-results-card" in live and "live-sources-card" in live


def test_refinement_is_idempotent() -> None:
    src = _doc('<div class="wrap"><div class="top" style="margin-bottom:4px"></div><div class="card"></div><div class="card"></div><div class="card"></div></div>')
    once = refine_page("live.html", src)
    twice = refine_page("live.html", once)
    # Lấy id từ hằng số của mô-đun, không chép chuỗi vào đây. Bản trước ghim
    # cứng "vla-targeted-ui-refinement" nên nó đỏ ngay khi id đổi tên, dù hành
    # vi idempotent không suy suyển gì.
    assert twice.count(f'id="{_STYLE_ID}"') == 1
    assert twice.count("live-status-card") == once.count("live-status-card")


def test_refinement_replaces_a_block_left_by_an_older_style_id() -> None:
    """Đổi id mà không nhận ra id CŨ thì khối cũ nằm lại vĩnh viễn.

    `_append_style` tìm khối để thay THEO ID. Id cũ không còn khớp gì cả, nên
    trang vừa mang id mới vừa giữ nguyên id cũ — và id cũ chứa tên dự án, thứ
    mà bộ kiểm chống lộ nguồn cấm. Đã đo: 5 trang vẫn còn chuỗi cấm sau khi
    dựng lại, cho tới khi phép gỡ nhận cả hai id.
    """
    assert _LEGACY_STYLE_IDS, "phải giữ danh sách id cũ để còn gỡ được"
    legacy = _LEGACY_STYLE_IDS[0]
    stale = _doc(
        f'<style id="{legacy}">.cu{{color:red}}</style>'
        '<div class="wrap"><div class="card"></div></div>'
    )
    out = refine_page("live.html", stale)
    assert legacy not in out, "khối mang id cũ phải bị gỡ, không được nằm lại"
    assert out.count(f'id="{_STYLE_ID}"') == 1
