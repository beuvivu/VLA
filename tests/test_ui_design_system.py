"""Kiểm thử hệ thống thiết kế dùng chung cho trang tĩnh.

Các trang được sinh ra phải tự chứa (CSP ``default-src 'self'``), có khung căn
giữa, bảng canh cột đúng loại dữ liệu và lưới không vượt quá 12 cột.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from ui_theme import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    TAILWIND_LITE_CSS,
    card,
    dataframe_table,
    nav_links,
    page_header,
    render_table,
    shell_open,
    tailwind_style_tag,
)

ROOT = Path(__file__).resolve().parents[1]


def test_theme_stays_self_contained_without_external_assets() -> None:
    style = tailwind_style_tag()
    assert "https://" not in style
    assert "http://" not in style
    assert "@import" not in style
    assert "url(" not in style


def test_theme_keeps_layout_and_component_primitives() -> None:
    for token in (
        ".vla-shell",
        ".vla-card",
        ".vla-table",
        ".vla-badge",
        ".vla-grid",
    ):
        assert token in TAILWIND_LITE_CSS, token
    # Container căn giữa và có padding tăng dần theo breakpoint.
    assert "margin-inline:auto" in TAILWIND_LITE_CSS
    assert "min-width:640px" in TAILWIND_LITE_CSS
    assert "min-width:1024px" in TAILWIND_LITE_CSS


def test_render_table_aligns_columns_by_declared_type() -> None:
    html_out = render_table(
        ["Nhãn", "Trạng thái", "Giá trị"],
        [["a", "ok", "1.5"]],
        align=[ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT],
    )
    soup = BeautifulSoup(html_out, "html.parser")
    cells = soup.find_all("td")
    assert "vla-al" in cells[0]["class"]
    assert "vla-ac" in cells[1]["class"]
    assert "vla-ar" in cells[2]["class"]
    # Bảng luôn nằm trong vùng cuộn ngang riêng.
    assert soup.find("div", class_="vla-table-wrap") is not None


def test_render_table_infers_alignment_from_cell_values() -> None:
    """Fallback suy luận theo giá trị: số canh phải, chữ canh trái."""
    soup = BeautifulSoup(
        render_table(
            ["Nhãn", "Số", "Xác suất"], [["Lô tô", "83", "0.2491"]]
        ),
        "html.parser",
    )
    cells = soup.find_all("td")
    assert "vla-al" in cells[0]["class"]
    # Chuỗi chữ số vẫn là giá trị số nên được canh phải khi không khai báo align.
    assert "vla-ar" in cells[1]["class"]
    assert "vla-ar" in cells[2]["class"]


def test_explicit_align_overrides_numeric_inference_for_key_columns() -> None:
    """Cột khóa dạng số (ví dụ số lô tô) canh trái được khi khai báo rõ."""
    soup = BeautifulSoup(
        render_table(
            ["Số", "Xác suất"],
            [["83", "0.2491"]],
            align=[ALIGN_LEFT, ALIGN_RIGHT],
            key_column=0,
        ),
        "html.parser",
    )
    cells = soup.find_all("td")
    assert "vla-al" in cells[0]["class"]
    assert "vla-key" in cells[0]["class"]
    assert "vla-ar" in cells[1]["class"]


def test_render_table_escapes_untrusted_cell_content() -> None:
    out = render_table(["x"], [["<script>alert(1)</script>"]])
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_dataframe_table_reports_empty_frames_instead_of_raising() -> None:
    assert "vla-table-empty" in dataframe_table(pd.DataFrame())
    assert "vla-table-empty" in dataframe_table(None)


def test_dataframe_table_renders_every_row_and_column() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    soup = BeautifulSoup(dataframe_table(frame), "html.parser")
    assert len(soup.find_all("tr")) == 4  # 1 header + 3 dòng dữ liệu
    assert len(soup.find_all("th")) == 2


def test_card_span_is_clamped_into_the_twelve_column_grid() -> None:
    assert "vla-c8" in card("x", span=8)
    assert "vla-c12" in card("x", span=99)
    assert "vla-c1" in card("x", span=-3)


def test_page_header_and_nav_escape_input() -> None:
    assert "&lt;b&gt;" in page_header("<b>t</b>")
    assert "&lt;b&gt;" in nav_links([("a.html", "<b>x</b>")])
    assert 'aria-current="page"' in nav_links([("a.html", "x")], current="a.html")


def _grid_rows_do_not_overflow(page: Path) -> None:
    """Tổng span của các card trong một lưới không được vượt 12 cột."""
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    for grid in soup.find_all("div", class_="vla-grid"):
        used = 0
        for section in grid.find_all("section", class_="vla-card", recursive=False):
            spans = [
                int(m.group(1))
                for cls in section.get("class", [])
                if (m := re.fullmatch(r"vla-c(\d+)", cls))
            ]
            span = spans[0] if spans else 12
            used = span if used + span > 12 else used + span
            assert span <= 12, f"{page.name}: span {span} vượt 12 cột"


def test_generated_dashboard_pages_use_the_shared_shell_and_grid() -> None:
    subprocess.run([sys.executable, "src/build_dashboard.py"], cwd=ROOT, check=True)

    for name in ("dashboard.html", "model-quality.html"):
        page = ROOT / "docs" / name
        text = page.read_text(encoding="utf-8")
        assert "vla-shell" in text, name
        assert "https://" not in text, name
        # Không còn body margin cứng của bản cũ.
        assert "margin: 24px" not in text and "margin:24px" not in text, name
        _grid_rows_do_not_overflow(page)


def test_shell_open_offers_a_wide_variant() -> None:
    assert "vla-shell-wide" in shell_open(wide=True)
    assert "vla-shell-wide" not in shell_open()
