"""Quét song song giá trị thực và giá trị quy đổi theo bóng số.

Bóng là một ánh xạ chữ số → chữ số, nên áp nó lên *nguồn* trước khi ghép cặp
giữ nguyên toàn bộ hình dạng vector của phép quét: không có nhánh nào rẽ riêng,
không có vòng lặp Python nào thêm vào.

Hai bảng bóng lấy thẳng từ ``number_reference`` — nơi chúng đã được dùng cho các
trang thống kê — thay vì chép lại. Chép lại sẽ tạo ra hai nguồn sự thật có thể
trôi khỏi nhau mà không ai phát hiện.
"""

from __future__ import annotations

from typing import Final

import numpy as np

from number_reference import BONG_AM, BONG_DUONG

KIND_THUC: Final[str] = "thuc"
KIND_BONG_DUONG: Final[str] = "bong_duong"
KIND_BONG_AM: Final[str] = "bong_am"

SHADOW_KINDS: Final[tuple[str, ...]] = (KIND_THUC, KIND_BONG_DUONG, KIND_BONG_AM)


def _lookup_table(mapping: dict[int, int]) -> np.ndarray:
    table = np.arange(10, dtype=np.uint8)
    for source, target in mapping.items():
        table[int(source)] = np.uint8(int(target))
    return table


_TABLES: Final[dict[str, np.ndarray]] = {
    KIND_THUC: np.arange(10, dtype=np.uint8),
    KIND_BONG_DUONG: _lookup_table(BONG_DUONG),
    KIND_BONG_AM: _lookup_table(BONG_AM),
}


def shadow_table(kind: str) -> np.ndarray:
    """Bảng tra cứu 10 phần tử cho một loại bóng."""
    try:
        return _TABLES[kind]
    except KeyError:
        raise ValueError(
            f"loại bóng không hợp lệ: {kind!r}; hiện có {list(SHADOW_KINDS)}"
        ) from None


def apply_shadow(kind: str, digits: np.ndarray) -> np.ndarray:
    """Quy đổi một mảng chữ số bất kỳ theo bóng, giữ nguyên hình dạng."""
    if digits.size and (digits.min() < 0 or digits.max() > 9):
        raise ValueError("chữ số phải nằm trong 0..9")
    return shadow_table(kind)[digits]
