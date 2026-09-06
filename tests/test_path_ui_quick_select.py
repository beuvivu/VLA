from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]


def _render_quick_select(picks: list[SimpleNamespace]) -> str:
    env = Environment(loader=FileSystemLoader(str(ROOT / "src" / "templates")))
    template = env.get_template("path_ui_page.html.j2")
    return template.render(
        title="Kiểm thử",
        mode="loto",
        mode_label="Lô tô",
        kind="active",
        kind_label="Đang chạy",
        other_link=None,
        other_kind_label="Ổn định",
        other_mode_label="Lô tô",
        index_link=None,
        anchor_date="2026-09-02",
        display_days=10,
        days=[],
        rows=[],
        picks=picks,
    )


def test_quick_select_renders_top_numbers_from_prediction_rows() -> None:
    html = _render_quick_select(
        [
            SimpleNamespace(number=14, prob=0.254275, support_paths_count=27),
            SimpleNamespace(number=7, prob=0.20, support_paths_count=3),
        ]
    )

    assert 'aria-label="Danh sách chọn nhanh"' in html
    assert ">14<" in html
    assert ">07<" in html
    assert "25.43%" in html
    assert "27 đường cầu" in html
    assert "không có đường cầu nào đủ điều kiện" not in html.lower()


def test_quick_select_has_explicit_empty_state_when_no_predictions() -> None:
    """Trạng thái rỗng phải nói vì sao trống, không đổ lỗi cho dữ liệu.

    Thông điệp cũ bảo người đọc "hãy chạy lại bước tạo dữ liệu đường cầu". Với
    ĐB thì rỗng là trạng thái đúng và thường gặp — tỉ lệ nền 1% khiến xác suất
    trúng ba kỳ liên tiếp chỉ là 1e-6 — nên câu đó hướng người đọc đi sửa một
    thứ không hỏng.
    """
    html = _render_quick_select([])

    assert 'aria-label="Danh sách chọn nhanh"' not in html
    assert "không có đường cầu nào đủ điều kiện" in html.lower()
    assert "chạy lại" not in html.lower()
