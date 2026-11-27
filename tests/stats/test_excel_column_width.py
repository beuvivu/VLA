from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.statistical_matrices import _write_excel


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
    out = tmp_path / "matrices.xlsx"
    _write_excel(path=out, sheets={"thu": frame_with_missing})
    assert out.exists()


def test_missing_cells_do_not_inflate_column_width(tmp_path, frame_with_missing) -> None:
    out = tmp_path / "matrices.xlsx"
    _write_excel(path=out, sheets={"thu": frame_with_missing})
    widths = _widths(out)
    assert widths, "không đọc được bề rộng cột nào"
    assert min(widths.values()) >= 10
    assert max(widths.values()) <= 28, "bề rộng phải bị kẹp ở 28"


def test_an_all_missing_column_still_gets_the_minimum_width(tmp_path) -> None:
    out = tmp_path / "matrices.xlsx"
    df = pd.DataFrame({"trong": [np.nan, np.nan], "co": ["a", "b"]})
    _write_excel(path=out, sheets={"thu": df})
    assert min(_widths(out).values()) >= 10
