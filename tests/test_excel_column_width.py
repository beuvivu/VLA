"""Bề rộng cột Excel phải chịu được giá trị thiếu.

pandas 3.0 GIỮ giá trị thiếu là NaN qua ``astype(str)`` thay vì tạo chuỗi
"nan" như 2.x. Mã tính bề rộng cột giả định mọi phần tử là chuỗi và vỡ bằng
``TypeError: object of type 'float' has no len()`` ngay giữa bước dựng Excel —
tức toàn bộ quy trình phát hành dừng lại.

Bộ test pytest không bắt được vì đường này chỉ chạy trong
``scripts/release_check.sh``. Đây là phép kiểm bù cho khoảng trống đó.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statistical_matrices import _write_excel


def _widths(path):
    from openpyxl import load_workbook

    ws = load_workbook(path).active
    return {k: v.width for k, v in ws.column_dimensions.items()}


@pytest.fixture
def frame_with_missing() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "number": ["01", "02", "03"],
            "ty_le": [1.5, np.nan, 3.0],
            "ghi_chu": ["ngắn", None, "một chuỗi dài hơn hẳn để nới cột"],
        }
    )


def test_writing_a_sheet_with_missing_values_does_not_raise(tmp_path, frame_with_missing) -> None:
    """Đây chính là lỗi đã làm đỏ CI khi nâng pandas lên 3.0.5."""
    out = tmp_path / "matrices.xlsx"
    _write_excel(path=out, sheets={"thu": frame_with_missing})
    assert out.exists()


def test_missing_cells_do_not_inflate_column_width(tmp_path, frame_with_missing) -> None:
    """Ô thiếu hiển thị TRỐNG trong Excel nên nó đóng góp 0 vào bề rộng.

    Đếm nó thành "nan" dài 3 ký tự là sai kể cả trên pandas 2.
    """
    out = tmp_path / "matrices.xlsx"
    _write_excel(path=out, sheets={"thu": frame_with_missing})
    widths = _widths(out)
    assert widths, "không đọc được bề rộng cột nào"
    # Cột toàn giá trị ngắn/thiếu phải giữ bề rộng tối thiểu 10, không phình.
    assert min(widths.values()) >= 10
    assert max(widths.values()) <= 28, "bề rộng phải bị kẹp ở 28"


def test_an_all_missing_column_still_gets_the_minimum_width(tmp_path) -> None:
    out = tmp_path / "matrices.xlsx"
    df = pd.DataFrame({"trong": [np.nan, np.nan], "co": ["a", "b"]})
    _write_excel(path=out, sheets={"thu": df})
    assert min(_widths(out).values()) >= 10
