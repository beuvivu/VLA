"""Hai bản của một bảng hay một cây JSON chỉ khác nhau ở nhiễu dấu phẩy động (14-11-2026).

Lượt pipeline chạy lại trên runner có CPU khác ghi lại những bảng mà mọi số chỉ lệch ở bit cuối:
`np.corrcoef`, `np.dot` và hàm đặc biệt của scipy chọn lệnh SIMD theo CPU. Lượt chạy lại sau PR #223
ghi lại `strategy_diversity_<mode>.csv` (phi lệch ≤ 4·10⁻¹⁵, hai cặp gần hoà đổi chỗ nên cả 378 dòng
đổi) và `loto_acf_bartlett.csv` (một giá trị p lệch 2,8·10⁻¹⁷); lượt 09-11 ghi lại 21 bảng và 10 JSON
kiểu ấy. Sửa tận gốc từng bảng là đổi phép tính thống kê, mà mỗi bảng dùng một hàm khác.

Luật so, cùng ngưỡng với tệp tóm tắt Vietlott (`vlm.forecast.service._same_up_to_float_noise`):
- CHỈ số thực được nới: lệch ≤ 10⁻⁹ tương đối (hoặc ≤ 10⁻¹² tuyệt đối gần 0). NaN bằng NaN.
- Số nguyên, chuỗi, ngày, mã có số 0 đầu, giá trị đúng/sai, khoá, độ dài danh sách, số dòng và tiêu đề
  cột phải trùng tuyệt đối.
- Bảng CSV không tính thứ tự dòng: dòng được xếp theo các cột KHÔNG phải số thực trước khi so, vì nhiễu
  đổi được thứ tự của hai dòng gần hoà ở cột số thực mà bảng xếp theo.

Chỉ dùng thư viện chuẩn: `web.page_output` nạp mô-đun này trong job Chromium, nơi không cài pandas.
"""
from __future__ import annotations

import csv
import io
import math
import re

#: Ngưỡng nhiễu: tương đối, và tuyệt đối cho số gần 0. Thay đổi thật của một xác suất hay một thống kê
#: đã công bố lớn hơn nhiều bậc.
FLOAT_NOISE_RELATIVE = 1e-9
FLOAT_NOISE_ABSOLUTE = 1e-12

#: Ô viết như số thực: có dấu chấm, số mũ hay nan/inf. Số nguyên trần («47», «05») so tuyệt đối.
_FLOAT_SPELLING = re.compile(r"[.eEnN]")


def close(x: float, y: float) -> bool:
    """Hai số thực chỉ khác nhau ở nhiễu."""
    if math.isnan(x) or math.isnan(y):
        return math.isnan(x) and math.isnan(y)
    if math.isinf(x) or math.isinf(y):
        return x == y
    return abs(x - y) <= max(FLOAT_NOISE_ABSOLUTE, FLOAT_NOISE_RELATIVE * max(abs(x), abs(y)))


def same_tree_up_to_float_noise(old: object, new: object) -> bool:
    """Hai cây JSON trùng nhau, trừ nhiễu ở số thực. Thứ tự khoá không tính; độ dài danh sách thì có."""
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(same_tree_up_to_float_noise(old[k], new[k]) for k in old)
    if isinstance(old, list) and isinstance(new, list):
        return len(old) == len(new) and all(same_tree_up_to_float_noise(a, b) for a, b in zip(old, new, strict=True))
    if type(old) is float and type(new) is float:
        return close(old, new)
    return type(old) is type(new) and old == new


def _as_float(cell: str) -> float | None:
    try:
        return float(cell)
    except ValueError:
        return None


def same_table_up_to_float_noise(old: bytes, new: bytes) -> bool:
    """Hai bản CSV trùng nhau, trừ nhiễu ở cột số thực và thứ tự dòng. Đọc hỏng thì coi là khác."""
    if old.count(b"\n") != new.count(b"\n"):   # lối tắt: khác số dòng thì khỏi đọc
        return False
    try:
        rows_old = list(csv.reader(io.StringIO(old.decode("utf-8"))))
        rows_new = list(csv.reader(io.StringIO(new.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error):
        return False
    if not rows_old or not rows_new or rows_old[0] != rows_new[0]:
        return False
    header, body_old, body_new = rows_old[0], rows_old[1:], rows_new[1:]
    width = len(header)
    if len(body_old) != len(body_new) or any(len(row) != width for row in body_old + body_new):
        return False
    floating = [
        any(_FLOAT_SPELLING.search(row[i]) and _as_float(row[i]) is not None for row in body_old + body_new)
        for i in range(width)
    ]
    keys = [i for i in range(width) if not floating[i]]

    def order(row: list[str]) -> list[str]:
        return [row[i] for i in keys]

    for row_old, row_new in zip(sorted(body_old, key=order), sorted(body_new, key=order), strict=True):
        for i in range(width):
            if row_old[i] == row_new[i]:
                continue
            if not floating[i]:
                return False
            a, b = _as_float(row_old[i]), _as_float(row_new[i])
            if a is None or b is None or not close(a, b):
                return False
    return True
