"""Cầu hình học và tọa độ: Pascal, hình trám, kẹp nách.

Ba phương pháp này lưu truyền dưới nhiều biến thể khác nhau. Lớp dưới đây hiện
thực một cách hình thức hóa cụ thể cho mỗi phương pháp và ghi rõ ngay tại chỗ,
để kết quả đo sau này gắn được với đúng định nghĩa đã dùng — chứ không phải với
một cái tên mơ hồ.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from bridges.tensor import NUMBER_SPACE
from features.base import FeatureContext
from xsmb_domain import FIELD_WIDTHS

# Vị trí bắt đầu của mỗi trường giải trong luồng chữ số phẳng.
_OFFSETS: dict[str, int] = {}
_cursor = 0
for _field, _width in FIELD_WIDTHS:
    _OFFSETS[_field] = _cursor
    _cursor += _width


def pascal_reduce(digits: np.ndarray) -> int:
    """Rút gọn một dãy chữ số theo tam giác Pascal xuống còn hai chữ số.

    Mỗi bước thay dãy bằng tổng từng cặp kề nhau lấy theo modulo 10, lặp tới khi
    còn đúng hai chữ số; kết quả đọc là số hai chữ số.
    """
    row = np.asarray(digits, dtype=np.int16)
    if row.size < 2:
        raise ValueError("cầu Pascal cần ít nhất hai chữ số")
    while row.size > 2:
        row = (row[:-1] + row[1:]) % 10
    return int(10 * row[0] + row[1])


@dataclass
class GeometricBridgeExtractor:
    """Cầu hình học trên bảng kết quả của ngày neo.

    * **Pascal**: ghép chữ số giải Đặc Biệt với giải Nhất thành một dãy 10 chữ
      số rồi rút gọn theo tam giác Pascal.
    * **Hình trám**: quét ba giải liên tiếp tại cùng cột chữ số; nơi hai chữ số
      ngoài trùng nhau (dạng A-B-A), số dự đoán là ``BA``.
    * **Kẹp nách**: trong dãy chữ số của một giải, nơi hai chữ số hai bên trùng
      nhau, số dự đoán ghép từ chữ số bị kẹp và chữ số kẹp.

    Mỗi đặc trưng là chỉ báo 0/1 trên 100 con, cộng thêm một cột đếm chuẩn hóa
    cho biết phương pháp đó chỉ ra con này bao nhiêu lần trong ngày.
    """

    name: str = "geometric"
    description: str = "Cầu Pascal, hình trám và kẹp nách trên bảng kết quả"
    feature_names: tuple[str, ...] = field(
        default_factory=lambda: (
            "pascal_hit",
            "diamond_hit",
            "diamond_weight",
            "clamped_hit",
            "clamped_weight",
        )
    )

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        digits = ctx.last_digits()
        out = np.zeros((NUMBER_SPACE, len(self.feature_names)), dtype=np.float64)

        special = digits[_OFFSETS["special"] : _OFFSETS["special"] + 5]
        prize1 = digits[_OFFSETS["prize1"] : _OFFSETS["prize1"] + 5]
        out[pascal_reduce(np.concatenate([special, prize1])), 0] = 1.0

        diamond = self._diamond_numbers(digits)
        self._fill(out, diamond, hit_column=1, weight_column=2)

        clamped = self._clamped_numbers(digits)
        self._fill(out, clamped, hit_column=3, weight_column=4)
        return out

    @staticmethod
    def _fill(out: np.ndarray, numbers: list[int], *, hit_column: int, weight_column: int) -> None:
        if not numbers:
            return
        counts = np.bincount(np.asarray(numbers), minlength=NUMBER_SPACE).astype(float)
        out[:, hit_column] = (counts > 0).astype(float)
        out[:, weight_column] = counts / counts.sum()

    @staticmethod
    def _diamond_numbers(digits: np.ndarray) -> list[int]:
        """Ba giải liên tiếp cùng cột, dạng A-B-A, cho số ``BA``."""
        fields = [name for name, _ in FIELD_WIDTHS]
        found: list[int] = []
        for index in range(len(fields) - 2):
            trio = fields[index : index + 3]
            width = min(dict(FIELD_WIDTHS)[name] for name in trio)
            for column in range(width):
                a, b, c = (digits[_OFFSETS[name] + column] for name in trio)
                if a == c and a != b:
                    found.append(int(10 * b + a))
        return found

    @staticmethod
    def _clamped_numbers(digits: np.ndarray) -> list[int]:
        """Chữ số bị kẹp giữa hai chữ số trùng nhau trong cùng một giải."""
        found: list[int] = []
        for name, width in FIELD_WIDTHS:
            if width < 3:
                continue
            row = digits[_OFFSETS[name] : _OFFSETS[name] + width]
            for index in range(1, width - 1):
                if row[index - 1] == row[index + 1] and row[index] != row[index - 1]:
                    found.append(int(10 * row[index] + row[index - 1]))
        return found
